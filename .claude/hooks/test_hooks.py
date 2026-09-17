#!/usr/bin/env python3
"""End-to-end tests for guard_docs.py, rule_router.py and post_write_checks.py.

    python .claude/hooks/test_hooks.py

WHY THESE CANNOT BE HAND-RUN FROM A SHELL
------------------------------------------
The obvious way to check `guard_docs.py` is to pipe a payload into it from Bash. That does not
work here, and the reason is worth recording: the payload has to contain a string like
`> some/CLAUDE.md`, and the hook is registered on Bash, so the guard refuses the very command that
was going to test it. The hook is right and the test method was wrong. Every payload below is
therefore built in Python and handed to the hook on stdin by `subprocess`, never typed into a shell.

Each hook runs against a THROWAWAY REPO in a temp directory, not against this one. That matters most
for `post_write_checks.py`, whose sweep RENAMES files: pointed at the real repo it would rename the
archived copy of the old CLAUDE.md under `.claude/_backup/`, which in a repo with no version control
is the only copy there is.

Companion suite for the library itself:
    python .claude/skills/rules-system/scripts/run_tests.py
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HOOKS = Path(__file__).resolve().parent
REPO = HOOKS.parent.parent

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        print(f"  FAIL  {name}  {detail}")


def run(hook: str, payload: dict, env_extra=None):
    """Run a hook with `payload` on stdin. Returns (parsed json or None, raw stdout)."""
    env = dict(os.environ)
    env.pop("CLAUDE_PROJECT_DIR", None)
    if env_extra:
        env.update(env_extra)
    proc = subprocess.run(
        [sys.executable, str(HOOKS / hook)],
        input=json.dumps(payload), capture_output=True, text=True, env=env,
    )
    out = proc.stdout.strip()
    if not out:
        return None, out
    try:
        return json.loads(out), out
    except json.JSONDecodeError:
        return None, out


def decision(obj):
    if not obj:
        return None
    return (obj.get("hookSpecificOutput") or {}).get("permissionDecision")


def context(obj):
    if not obj:
        return ""
    return (obj.get("hookSpecificOutput") or {}).get("additionalContext", "")


# ------------------------------------------------------------------------------------------------
# a throwaway repo, shaped like the real one in the ways these hooks care about
# ------------------------------------------------------------------------------------------------

def build_sandbox(root: Path):
    (root / "rules").mkdir(parents=True)
    (root / "rules" / "INDEX.md").write_text(
        "# fixture\n\n"
        "- **alpha.rule.md** | `**/*.xs` | alpha\n"
        "- **beta.rule.md** | `cmd:\\bgit\\b` | beta\n\n"
        "<!-- BEGIN GENERATED readme-triggers -->\n<!-- END GENERATED readme-triggers -->\n",
        encoding="utf-8")
    (root / "rules" / "alpha.rule.md").write_text("RULE alpha\n- one line\n", encoding="utf-8")
    (root / "rules" / "beta.rule.md").write_text("RULE beta\n- one line\n", encoding="utf-8")

    (root / "mechanics").mkdir()
    (root / "mechanics" / "README.md").write_text("rules/alpha.rule.md\n", encoding="utf-8")
    (root / "mechanics" / "thing.xs").write_text("// xs\n", encoding="utf-8")

    skill = root / ".claude" / "skills" / "some-skill"
    skill.mkdir(parents=True)
    (skill / "thing.xs").write_text("// xs inside a skill\n", encoding="utf-8")

    # The real machinery must be reachable from the sandbox, because _bootstrap resolves the library
    # relative to the project directory it is told about.
    dst = root / ".claude" / "skills" / "rules-system" / "scripts"
    dst.mkdir(parents=True)
    for name in ("rules_lib.py", "upkeep.py"):
        shutil.copy2(REPO / ".claude" / "skills" / "rules-system" / "scripts" / name, dst / name)


BANNED = "CLAUDE" + ".md"      # assembled, so this file never carries the literal token
BANNED_LOWER = BANNED.lower()


def test_guard(root: Path):
    print("guard_docs.py")
    base = {"cwd": str(root)}

    obj, _ = run("guard_docs.py", {**base, "tool_name": "Write",
                                   "tool_input": {"file_path": str(root / "docs" / BANNED)}})
    check("Write of a banned root doc is DENIED", decision(obj) == "deny", decision(obj))

    # READMEs carry orientation again since 2026-09-11, so they must be editable. Their SHAPE is
    # checked after the write by post_write_checks.py instead of being frozen here.
    obj, raw = run("guard_docs.py", {**base, "tool_name": "Edit",
                                     "tool_input": {"file_path": str(root / "mechanics" / "README.md")}})
    check("Edit of an EXISTING README is allowed", raw == "", raw[:80])

    obj, raw = run("guard_docs.py", {**base, "tool_name": "Write",
                                    "tool_input": {"file_path": str(root / "new" / "README.md")}})
    check("Write of a NEW README is allowed", raw == "", raw[:80])

    obj, raw = run("guard_docs.py", {**base, "tool_name": "Write",
                                     "tool_input": {"file_path": str(root / "mechanics" / "README.md")}})
    check("Write OVER an existing README is allowed", raw == "", raw[:80])

    obj, raw = run("guard_docs.py", {**base, "tool_name": "Edit",
                                     "tool_input": {"file_path": str(root / "rules" / "alpha.rule.md")}})
    check("editing a RULE file is never blocked", raw == "", raw[:80])

    obj, _ = run("guard_docs.py", {**base, "tool_name": "Bash",
                                   "tool_input": {"command": f"echo hi > docs/{BANNED}"}})
    check("shell redirect into a banned doc is DENIED", decision(obj) == "deny", decision(obj))

    obj, raw = run("guard_docs.py", {**base, "tool_name": "Bash",
                                     "tool_input": {"command": "cat mechanics/README.md"}})
    check("shell READ of a README is allowed", raw == "", raw[:80])

    obj, raw = run("guard_docs.py", {**base, "tool_name": "Bash",
                                     "tool_input": {"command": "sed -i s/a/b/ mechanics/README.md"}})
    check("in-place shell edit of a README is allowed", raw == "", raw[:80])

    obj, raw = run("guard_docs.py", {**base, "tool_name": "Bash",
                                     "tool_input": {"command": "echo x > new/other/README.md"}})
    check("shell creation of a NEW README is allowed", raw == "", raw[:80])

    obj, raw = run("guard_docs.py", {**base, "tool_name": "Read",
                                     "tool_input": {"file_path": str(root / "mechanics" / "README.md")}})
    check("Read is never blocked", raw == "", raw[:80])

    # Regression: this exact shape was refused while patching the three agent definitions. The
    # command writes to a .md that is NOT banned, and only QUOTES the banned name inside the
    # replacement text. Denying it bought nothing - the PostToolUse sweep is the real guarantee -
    # and cost a legitimate edit.
    mention = (f"python -c \"p.write_text(s.replace('see `{BANNED}`', 'see rules/'))\" "
               "agents/specialist.md")
    obj, raw = run("guard_docs.py", {**base, "tool_name": "Bash",
                                     "tool_input": {"command": mention}})
    check("a command that only MENTIONS the banned name is allowed", raw == "", raw[:120])

    obj, _ = run("guard_docs.py", {**base, "tool_name": "Bash",
                                   "tool_input": {"command": f"cp template.md docs/{BANNED}"}})
    check("a copy whose TARGET is the banned name is DENIED", decision(obj) == "deny")


def test_readme_shape(root: Path):
    """A README is writable now, so the shape check after the write is what protects it."""
    print("post_write_checks.py: README shape")
    env = {"CLAUDE_PROJECT_DIR": str(root)}
    folder = root / "shaped"
    folder.mkdir()
    readme = folder / "README.md"

    def problem(obj):
        """Only the shape complaints, so the index-resync note does not read as a failure."""
        ctx = context(obj)
        return next((m for m in ("NAMES NO RULE", "DOES NOT EXIST", "TOO LONG") if m in ctx), "")

    def written():
        return run("post_write_checks.py",
                   {"tool_name": "Write", "cwd": str(root),
                    "tool_input": {"file_path": str(readme)}}, env)

    readme.write_text("rules/alpha.rule.md\n\nWhat this folder is.\n", encoding="utf-8")
    obj, _ = written()
    check("a rule path plus orientation passes", not problem(obj), context(obj)[:120])

    readme.write_text("rules/alpha.rule.md\nrules/beta.rule.md\n\nTwo rules, one folder.\n",
                      encoding="utf-8")
    obj, _ = written()
    check("several rule paths pass", not problem(obj), context(obj)[:120])

    readme.write_text("just some prose, no rule at all\n", encoding="utf-8")
    obj, _ = written()
    check("a README naming no rule is reported", "NAMES NO RULE" in context(obj), context(obj)[:80])

    readme.write_text("rules/nope.rule.md\n\norientation\n", encoding="utf-8")
    obj, _ = written()
    check("a README naming a missing rule is reported",
          "DOES NOT EXIST" in context(obj), context(obj)[:80])

    readme.write_text("rules/alpha.rule.md\n\n" + "line\n" * 11, encoding="utf-8")
    obj, _ = written()
    check("orientation past the cap is reported",
          "TOO LONG" in context(obj), context(obj)[:80])

    readme.write_text("rules/alpha.rule.md\n", encoding="utf-8")
    obj, _ = written()
    check("a bare trigger, with no orientation, still passes",
          not problem(obj), context(obj)[:120])
    shutil.rmtree(folder)


def test_router(root: Path, state: Path):
    print("rule_router.py")
    env = {"CLAUDE_PROJECT_DIR": str(root), "CLAUDE_RULE_STATE_DIR": str(state)}
    base = {"cwd": str(root)}

    obj, _ = run("rule_router.py", {**base, "session_id": "s1", "tool_name": "Read",
                                    "tool_input": {"file_path": str(root / "mechanics" / "thing.xs")}}, env)
    check("a matching path injects its rule", "rules/alpha.rule.md" in context(obj), context(obj)[:80])

    obj, raw = run("rule_router.py", {**base, "session_id": "s1", "tool_name": "Read",
                                      "tool_input": {"file_path": str(root / "mechanics" / "thing.xs")}}, env)
    check("the same rule is NOT injected twice in one session", raw == "", raw[:80])

    obj, _ = run("rule_router.py", {**base, "session_id": "s2", "tool_name": "Read",
                                    "tool_input": {"file_path": str(root / "mechanics" / "thing.xs")}}, env)
    check("a new session gets it again", "rules/alpha.rule.md" in context(obj))

    obj, raw = run("rule_router.py",
                   {**base, "session_id": "s3", "tool_name": "Read",
                    "tool_input": {"file_path": str(root / ".claude" / "skills" / "some-skill" / "thing.xs")}},
                   env)
    check("a path inside a SKILL injects NOTHING", raw == "", raw[:120])

    obj, _ = run("rule_router.py", {**base, "session_id": "s4", "tool_name": "Bash",
                                    "tool_input": {"command": "git status"}}, env)
    check("a cmd: gate fires on command text", "rules/beta.rule.md" in context(obj))

    obj, raw = run("rule_router.py", {**base, "session_id": "s5", "tool_name": "Bash",
                                      "tool_input": {"command": "echo nothing to see"}}, env)
    check("an unrelated command injects nothing", raw == "", raw[:80])

    obj, _ = run("rule_router.py", {**base, "session_id": "s6", "tool_name": "Read",
                                    "tool_input": {"file_path": str(root / "mechanics" / "README.md")}}, env)
    check("a README injects the rule its own line names",
          "rules/alpha.rule.md" in context(obj), context(obj)[:80])

    # The firing log is what makes gate tuning possible after the fact. If the router injects but
    # records nothing, `rules.py stats` reports every gate as never-fired and quietly misleads.
    log = root / ".claude" / "rules-firings.jsonl"
    check("the router wrote a firing log", log.is_file(), str(log))
    if log.is_file():
        recs = [json.loads(x) for x in log.read_text(encoding="utf-8").splitlines() if x.strip()]
        check("the log records the gate, not just the rule",
              any(r.get("gate") == "**/*.xs" for r in recs), recs[:2])
        check("the log records a command gate too",
              any(r.get("kind") == "command" for r in recs), recs[:2])


def test_post(root: Path):
    print("post_write_checks.py")
    env = {"CLAUDE_PROJECT_DIR": str(root)}
    base = {"cwd": str(root), "tool_name": "Bash", "tool_input": {"command": "true"}}

    stray = root / "mechanics" / BANNED
    stray.write_text("smuggled in by a script\n", encoding="utf-8")
    obj, _ = run("post_write_checks.py", base, env)
    ctx = context(obj)
    check("a stray banned doc is reported", "PROHIBITED" in ctx, ctx[:100])
    check("it is RENAMED, not deleted", (root / "mechanics" / "CLAUDE_banned.md").is_file())
    check("the original name is gone", not stray.exists())
    check("its content survives the rename",
          "smuggled" in (root / "mechanics" / "CLAUDE_banned.md").read_text(encoding="utf-8"))

    (root / "rules" / "huge.rule.md").write_text(
        "\n".join(f"- line {i}" for i in range(30)) + "\n", encoding="utf-8")
    obj, _ = run("post_write_checks.py", base, env)
    ctx = context(obj)
    check("an over-budget rule is reported", "OVER BUDGET" in ctx, ctx[:120])
    check("the report names the file and both numbers",
          "huge.rule.md" in ctx and "30 lines" in ctx, ctx[:200])
    check("the over-budget file is NOT truncated",
          len((root / "rules" / "huge.rule.md").read_text(encoding="utf-8").splitlines()) == 30)
    (root / "rules" / "huge.rule.md").unlink()

    (root / "fresh").mkdir()
    (root / "fresh" / "README.md").write_text("rules/alpha.rule.md\n", encoding="utf-8")
    obj, _ = run("post_write_checks.py", base, env)
    check("a new README re-syncs the index", "re-synced" in context(obj), context(obj)[:120])
    idx = (root / "rules" / "INDEX.md").read_text(encoding="utf-8")
    check("the generated block lists the new README",
          "- `fresh/README.md` | `alpha.rule.md`" in idx)
    check("the hand-maintained gates survive", "**alpha.rule.md**" in idx.split("BEGIN GENERATED")[0])

    obj, raw = run("post_write_checks.py", base, env)
    check("a clean repo produces NO output", raw == "", raw[:120])

    obj, raw = run("post_write_checks.py", {**base, "tool_name": "Read",
                                            "tool_input": {"file_path": "x"}}, env)
    check("a read-only tool is skipped entirely", raw == "", raw[:80])


def test_announce(root: Path):
    """A handoff sits at the level of its work, so discovery is a pruned scan, not a fixed list.

    The decoys are the whole point: a spent handoff in the archive and the byte-identical copies
    under a backup folder must never be announced as waiting, and a dated name is already spent.
    """
    print("announce_handoff.py discovery")
    name = "HAND" + "OFF.md"          # spelled in parts: the write guard matches on command text
    live = root / name
    scoped = root / "mechanics" / "inventory"
    archived = scoped / "archive" / "handoffs"
    backup = root / ".claude" / "_backup" / "docs"
    for d in (scoped, archived, backup):
        d.mkdir(parents=True, exist_ok=True)

    obj, raw = run("announce_handoff.py", {"cwd": str(root)})
    check("no handoff anywhere produces NO output", raw == "", raw[:120])

    live.write_text("repo-wide\n", encoding="utf-8")
    archived.joinpath(name).write_text("spent\n", encoding="utf-8")
    backup.joinpath(name).write_text("backup copy\n", encoding="utf-8")
    root.joinpath("HAND" + "OFF-2026-09-05.md").write_text("dated\n", encoding="utf-8")
    obj, _ = run("announce_handoff.py", {"cwd": str(root)})
    ctx = context(obj)
    check("a repo-root handoff is announced", ctx.startswith("A HANDOFF IS WAITING: " + name),
          ctx[:80])
    check("an ARCHIVED handoff is not announced", "archive/handoffs/" + name not in ctx)
    check("a handoff under _backup is not announced", "_backup" not in ctx)
    check("a DATED name is not announced", "2026-09-05" not in ctx)

    scoped.joinpath(name).write_text("one mechanic\n", encoding="utf-8")
    obj, _ = run("announce_handoff.py", {"cwd": str(root)})
    ctx = context(obj)
    check("a second, folder-scoped handoff is announced too",
          "mechanics/inventory/" + name in ctx, ctx[:200])
    check("the repo-wide one still leads", ctx.splitlines()[0].endswith(name)
          and "mechanics" not in ctx.splitlines()[0], ctx.splitlines()[0])

    live.unlink()
    obj, _ = run("announce_handoff.py", {"cwd": str(root)})
    ctx = context(obj)
    check("with only a scoped handoff left, IT leads",
          ctx.splitlines()[0].endswith("mechanics/inventory/" + name), ctx.splitlines()[0])
    check("one handoff gets no also-waiting block", "WAITING TOO" not in ctx)
    check("the notice says an unassigned session must leave it alone",
          "Do NOT read" in ctx and "unless the user has asked you" in ctx)
    scoped.joinpath(name).unlink()


def test_gate(root: Path):
    """Only the session the user assigns may read a live handoff, so every read asks first."""
    print("gate_handoff_read.py")
    name = "HAND" + "OFF.md"          # spelled in parts: the write guard matches on command text
    live = root / "mechanics" / "inventory" / name
    live.parent.mkdir(parents=True, exist_ok=True)
    live.write_text("live\n", encoding="utf-8")
    archived = "mechanics/inventory/archive/handoffs/" + name
    dated = "mechanics/inventory/archive/handoffs/" + name.replace(".md", "-2026-09-05.md")

    def gate(tool, tool_input):
        obj, _ = run("gate_handoff_read.py", {"tool_name": tool, "tool_input": tool_input,
                                              "cwd": str(root)})
        return decision(obj)

    check("a Read of a live handoff asks the user",
          gate("Read", {"file_path": str(live)}) == "ask")
    check("a repo-relative Read asks too",
          gate("Read", {"file_path": "mechanics/inventory/" + name}) == "ask")
    check("a Grep aimed at a live handoff asks", gate("Grep", {"path": str(live)}) == "ask")
    check("a shell read naming a live handoff asks",
          gate("Bash", {"command": "cat mechanics/inventory/" + name}) == "ask")
    check("the retiring move asks too, so retirement is approved",
          gate("PowerShell", {"command": f"Move-Item mechanics/inventory/{name} {dated}"}) == "ask")
    check("an ARCHIVED handoff reads freely", gate("Read", {"file_path": archived}) is None)
    check("a DATED handoff reads freely", gate("Read", {"file_path": dated}) is None)
    check("a copy under _backup reads freely",
          gate("Read", {"file_path": ".claude/_backup/docs/" + name}) is None)
    check("the rule ABOUT handoffs reads freely",
          gate("Read", {"file_path": "rules/lifecycle/handoff.rule.md"}) is None)
    check("a shell command naming only a dated handoff passes",
          gate("Bash", {"command": "cat " + dated}) is None)
    check("Write is not gated here - /handoff creates through it",
          gate("Write", {"file_path": str(live)}) is None)
    proc = subprocess.run([sys.executable, str(HOOKS / "gate_handoff_read.py")],
                          input="not json at all", capture_output=True, text=True)
    check("gate fails open and silent on unreadable input",
          proc.returncode == 0 and proc.stdout.strip() == "", proc.stdout[:80])
    live.unlink()


def test_handoff_skills(root: Path):
    """Reading a live handoff loads the skills its front matter asks for; nothing else does."""
    print("handoff_skills.py")
    name = "HAND" + "OFF.md"
    live = root / "mechanics" / "inventory" / name
    live.parent.mkdir(parents=True, exist_ok=True)
    skills = root / ".claude" / "skills"
    for skill, body in (("some-skill", "---\nname: some-skill\n---\nSOME SKILL BODY\n"),
                        ("dead-skill", "DEAD SKILL BODY\n"),
                        ("arg-skill", "ARG SKILL BODY uses $ARGUMENTS\n"),
                        ("big-skill", "BIG SKILL BODY " + "x" * 12000 + "\n")):
        (skills / skill).mkdir(parents=True, exist_ok=True)
        (skills / skill / "SKILL.md").write_text(body, encoding="utf-8")
    (root / ".claude" / "settings.json").write_text(
        json.dumps({"skillOverrides": {"dead-skill": "off"}}), encoding="utf-8")

    def read(path):
        obj, raw = run("handoff_skills.py", {"tool_name": "Read", "tool_input": {"file_path": path},
                                             "cwd": str(root)})
        return context(obj), raw

    live.write_text("---\nskills: some-skill, /arg-skill, missing-skill, dead-skill, big-skill\n"
                    "---\n\n# body\n", encoding="utf-8")
    ctx, _ = read(str(live))
    check("a requested skill's SKILL.md body is loaded", "SOME SKILL BODY" in ctx, ctx[:300])
    check("the skill's own front matter is stripped", "name: some-skill" not in ctx)
    check("a skill taking arguments is loaded AND flagged for the user",
          "ARG SKILL BODY" in ctx and "/arg-skill  - takes arguments" in ctx)
    check("an unknown skill is reported, not dropped", "/missing-skill  - no such skill" in ctx)
    check("a skill switched off in settings is never loaded",
          "DEAD SKILL BODY" not in ctx and "/dead-skill  - switched off" in ctx)
    check("a skill too large to inline is named by path to read in full",
          "BIG SKILL BODY" not in ctx and ".claude/skills/big-skill/SKILL.md" in ctx, ctx[:600])

    live.write_text("---\nskills:\n  - some-skill\n---\n", encoding="utf-8")
    ctx, _ = read(str(live))
    check("a YAML list of skills is read too", "SOME SKILL BODY" in ctx)

    live.write_text("---\nskills: none\n---\n", encoding="utf-8")
    ctx, raw = read(str(live))
    check("skills: none produces no output", raw == "", raw[:120])

    live.write_text("# no front matter\n", encoding="utf-8")
    ctx, _ = read(str(live))
    check("a handoff with no front matter says nothing was loaded", "no `skills:` front matter" in ctx)

    archived = root / "mechanics" / "inventory" / "archive" / "handoffs" / name
    archived.parent.mkdir(parents=True, exist_ok=True)
    archived.write_text("---\nskills: some-skill\n---\n", encoding="utf-8")
    ctx, raw = read(str(archived))
    check("reading an ARCHIVED handoff loads nothing", raw == "", raw[:120])
    live.unlink()


def test_registry(root: Path):
    """The author of a handoff is knowable only at the moment it is written, so the hook logs it.

    Redirected at a throwaway data folder through HANDOFF_DATA_DIR, so the real record is untouched.
    """
    print("handoff_registry.py")
    name = "HAND" + "OFF.md"                  # in parts: the write guard matches on command text
    data = root / "registry_data"
    env = {"HANDOFF_DATA_DIR": str(data)}
    live = root / name
    live.write_text("---\nskills: none\ndate: 2026-09-11\nscope: widgets\n---\n\nbody\n",
                    encoding="utf-8")

    payload = {"tool_name": "Write", "cwd": str(root), "session_id": "sess-abc",
               "transcript_path": "/tmp/sess-abc.jsonl",
               "tool_input": {"file_path": str(live)}}
    run("handoff_registry.py", payload, env)
    log = [json.loads(l) for l in (data / "log.jsonl").read_text(encoding="utf-8").splitlines() if l]
    written = [r for r in log if r["event"] == "written"]
    check("writing a live handoff logs one `written` record", len(written) == 1, log)
    check("it carries the session that wrote it",
          written and written[0]["session"] == "sess-abc", written)
    check("it carries the occasion from the file's own front matter",
          written and written[0]["occasion"] == "2026-09-11-widgets", written)

    run("handoff_registry.py", payload, env)
    log = [json.loads(l) for l in (data / "log.jsonl").read_text(encoding="utf-8").splitlines() if l]
    check("writing it again the same day does not log a second author",
          len([r for r in log if r["event"] == "written"]) == 1, log)

    occ = data / "2026-09-11-widgets"
    occ.mkdir(parents=True)
    (occ / name).write_text("body\n", encoding="utf-8")
    run("handoff_registry.py", {"tool_name": "Bash", "cwd": str(root), "session_id": "sess-def",
                                "tool_input": {"command": "mv x y"}}, env)
    log = [json.loads(l) for l in (data / "log.jsonl").read_text(encoding="utf-8").splitlines() if l]
    check("the retirement is noticed without being told",
          any(r["event"] == "retired" and r.get("occasion") == "2026-09-11-widgets" for r in log), log)

    (occ / "REVIEW.md").write_text("feedback\n", encoding="utf-8")
    obj, _ = run("handoff_registry.py", {"tool_name": "Write", "cwd": str(root),
                                         "session_id": "sess-def",
                                         "tool_input": {"file_path": str(occ / "REVIEW.md")}}, env)
    ctx = context(obj)
    check("a review is logged and reported", "A REVIEW WAS FILED" in ctx, ctx[:120])
    check("the report names the session that must answer it", "sess-abc" in ctx, ctx[:200])

    obj, raw = run("handoff_registry.py", {"tool_name": "Write", "cwd": str(root),
                                           "session_id": "sess-def",
                                           "tool_input": {"file_path": str(root / "unrelated.md")}},
                   env)
    check("an unrelated write says nothing", raw == "", raw[:120])
    live.unlink()



def test_guard_records(root: Path):
    """Records are reached through commands: direct access is refused and the refusal lists the commands."""
    print("guard_records.py")
    H, T, Q, C = "HISTORY" + ".jsonl", "TASKS" + ".md", "QUESTIONS" + ".jsonl", "candidates" + ".jsonl"
    rp = "python .claude/skills/rules-system/scripts/rules.py"

    def go(tool, **ti):
        obj, _ = run("guard_records.py", {"tool_name": tool, "tool_input": ti, "cwd": str(root)})
        return decision(obj), (obj or {}).get("hookSpecificOutput", {}).get("permissionDecisionReason", "")

    for label, (tool, ti) in {
            "Read a history file": ("Read", {"file_path": str(root / "mech" / H)}),
            "Edit a history file": ("Edit", {"file_path": "mech/" + H}),
            "Write a tasks file": ("Write", {"file_path": "mech/" + T}),
            "Read the candidate master copy": ("Read", {"file_path": ".claude/skills/rules-system/data/AOE/" + C}),
            "Grep inside a history file": ("Grep", {"pattern": "run", "path": "mech/" + H}),
            "Glob for history files": ("Glob", {"pattern": "**/" + H}),
            "cat a history file": ("Bash", {"command": "cat mech/" + H}),
            "append to one by redirect": ("Bash", {"command": "echo {} >> mech/" + H}),
            "Get-Content a questions file": ("PowerShell", {"command": "Get-Content mech\\" + Q}),
            "python open() on a tasks file": ("Bash", {"command": "python -c \"open('mech/" + T + "').read()\""}),
            "delete a history file": ("Bash", {"command": "rm mech/" + H})}.items():
        d, reason = go(tool, **ti)
        check("refuses: " + label, d == "deny", d)
    d, reason = go("Read", file_path="mech/" + H)
    check("the refusal lists the history commands", "history add" in reason and "history show" in reason, reason[:200])
    for label, (tool, ti) in {
            "a redirect into a record after an exempt command": ("Bash", {"command": rp + " history mech > mech/" + H}),
            "an exempt name only in a comment": ("Bash", {"command": "cat mech/" + H + "  # rules.py"}),
            "an exempt command chained to a direct read": ("Bash", {"command": rp + " history mech && cat mech/" + H}),
            "a lowercase record name through Read": ("Read", {"file_path": "mech/" + H.lower()}),
            "a lowercase record name in the shell": ("Bash", {"command": "cat mech/" + H.lower()}),
            "the gc alias": ("PowerShell", {"command": "gc mech\\" + H}),
            "ReadAllText": ("PowerShell", {"command": "[IO.File]::ReadAllText('mech/" + H + "')"}),
            "a Grep glob that matches a record": ("Grep", {"pattern": "run", "glob": "HIST*.jsonl"}),
            "a Glob wildcard that matches a record": ("Glob", {"pattern": "**/*ASKS.md"})}.items():
        d, _ = go(tool, **ti)
        check("refuses: " + label, d == "deny", d)
    for label, (tool, ti) in {
            "a stream redirect that is not a file": ("PowerShell", {"command": "Test-Path mech/" + H + " 2>&1"}),
            "a Grep glob over markdown in general": ("Grep", {"pattern": "run", "glob": "*.md"})}.items():
        d, _ = go(tool, **ti)
        check("allows: " + label, d != "deny", d)
    for label, (tool, ti) in {
            "the history command": ("Bash", {"command": rp + " history mech --last 5"}),
            "a history add naming the file in its text": ("Bash", {"command": rp + " history add mech --kind note --title \"x\" --what \"wrote " + H + "\""}),
            "vector-search indexing history": ("Bash", {"command": "python .claude/skills/vector-search/scripts/index.py --ns history"}),
            "a test suite naming a record": ("Bash", {"command": "python .claude/hooks/test_hooks.py --only " + H + " 2>&1"}),
            "a command that only names it, touching nothing": ("Bash", {"command": "echo see " + H + " for runs"}),
            "an unrelated Read": ("Read", {"file_path": "mech/README.md"}),
            "a Grep whose pattern is the name": ("Grep", {"pattern": H, "path": "rules"}),
            "a longer name that only contains it": ("Read", {"file_path": "mech/OLD_" + H})}.items():
        d, _ = go(tool, **ti)
        check("allows: " + label, d != "deny", d)
    proc = subprocess.run([sys.executable, str(HOOKS / "guard_records.py")], input="not json",
                          capture_output=True, text=True)
    check("unreadable input fails open", proc.returncode == 0 and proc.stdout == "")


def test_focus(root: Path, state: Path):
    """The router remembers which project a session works in, for rules.py view."""
    print("session focus")
    env = {"CLAUDE_PROJECT_DIR": str(root), "CLAUDE_RULE_STATE_DIR": str(state)}
    (root / "mechanics" / ".rs" / "HISTORY.jsonl").parent.mkdir(parents=True, exist_ok=True)
    (root / "mechanics" / ".rs" / "HISTORY.jsonl").write_text("", encoding="utf-8")
    try:
        run("rule_router.py", {"cwd": str(root), "session_id": "focus-1", "tool_name": "Read",
                               "tool_input": {"file_path": str(root / "mechanics" / "thing.xs")}}, env)
        p = state / "claude_rule_router" / "focus-1.focus.json"
        got = json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}
        check("touching a file in a project records it as the session's focus", got.get("project") == "mechanics", got)
    finally:
        (root / "mechanics" / ".rs" / "HISTORY.jsonl").unlink()


def test_no_silent_changes(root: Path, state: Path):
    """A session leaving a project it changed without logging anything is reminded, once."""
    print("no silent changes")
    env = {"CLAUDE_PROJECT_DIR": str(root), "CLAUDE_RULE_STATE_DIR": str(state)}
    a, b = root / "mechanics", root / "patterns_nsc"
    a.mkdir(exist_ok=True)
    b.mkdir(exist_ok=True)
    (a / ".rs" / "HISTORY.jsonl").parent.mkdir(parents=True, exist_ok=True)
    (a / ".rs" / "HISTORY.jsonl").write_text("", encoding="utf-8")
    (b / ".rs" / "HISTORY.jsonl").parent.mkdir(parents=True, exist_ok=True)
    (b / ".rs" / "HISTORY.jsonl").write_text("", encoding="utf-8")

    def ctx(sid, tool, path):
        ti = {"file_path": str(path)}
        if tool == "Edit":
            ti.update(old_string="x", new_string="y")
        j, _ = run("rule_router.py", {"cwd": str(root), "session_id": sid, "tool_name": tool, "tool_input": ti}, env)
        return ((j or {}).get("hookSpecificOutput") or {}).get("additionalContext", "")

    try:
        check("an edit inside a project says nothing yet", "NO SILENT CHANGES" not in ctx("nsc-1", "Edit", a / "thing.xs"))
        got = ctx("nsc-1", "Read", b / "x.py")
        check("moving to another project names the unlogged one, its files and the command",
              "NO SILENT CHANGES" in got and "history add mechanics" in got and "mechanics/thing.xs" in got, got[-400:])
        check("the reminder is shown once", "NO SILENT CHANGES" not in ctx("nsc-1", "Read", b / "y.py"))
        check("reading is never a change", "NO SILENT CHANGES" not in
              ctx("nsc-2", "Read", a / "t.xs") + ctx("nsc-2", "Read", b / "x.py"))
        ctx("nsc-3", "Edit", a / "thing.xs")
        (a / ".rs" / "HISTORY.jsonl").parent.mkdir(parents=True, exist_ok=True)
        (a / ".rs" / "HISTORY.jsonl").write_text(json.dumps({"id": "z", "ts": "2099-01-01", "time": "2099-01-01T00:00:00",
                                                     "kind": "change", "title": "logged it"}) + "\n", encoding="utf-8")
        check("a change logged before moving on is not reminded", "NO SILENT CHANGES" not in ctx("nsc-3", "Read", b / "x.py"))
    finally:
        (a / ".rs" / "HISTORY.jsonl").unlink()
        shutil.rmtree(b, ignore_errors=True)


def test_answers_waiting(root: Path, state: Path):
    """An answer the user sent from the viewer is announced to the session on its next tool call, once."""
    print("answers waiting")
    env = {"CLAUDE_PROJECT_DIR": str(root), "CLAUDE_RULE_STATE_DIR": str(state)}
    a = root / "mechanics"
    a.mkdir(exist_ok=True)
    (a / ".rs" / "HISTORY.jsonl").parent.mkdir(parents=True, exist_ok=True)
    (a / ".rs" / "HISTORY.jsonl").write_text("", encoding="utf-8")
    (a / ".rs" / "QUESTIONS.jsonl").parent.mkdir(parents=True, exist_ok=True)
    (a / ".rs" / "QUESTIONS.jsonl").write_text(json.dumps({"id": "q1", "task": "t1", "question": "which map?", "answer":
                                                   "the small one", "answered": "2026-09-14T10:00:00"}) + "\n",
                                       encoding="utf-8")

    def ctx(sid):
        j, _ = run("rule_router.py", {"cwd": str(root), "session_id": sid, "tool_name": "Read",
                                      "tool_input": {"file_path": str(a / "x.xs")}}, env)
        return ((j or {}).get("hookSpecificOutput") or {}).get("additionalContext", "")

    try:
        got = ctx("ans-1")
        check("an answer sent in the viewer is announced on the session's next tool call, with the command",
              "ANSWERS WAITING" in got and "q1" in got and "tasks --in mechanics answers" in got, got[-300:])
        check("and only once", "ANSWERS WAITING" not in ctx("ans-1"))
    finally:
        (a / ".rs" / "HISTORY.jsonl").unlink()
        (a / ".rs" / "QUESTIONS.jsonl").unlink()


def test_changed_rule(root: Path, state: Path):
    """A rule is sent once per session, and again when its text changes: no reload needed for an edit."""
    print("an edited rule reaches a session that already has it")
    env = {"CLAUDE_PROJECT_DIR": str(root), "CLAUDE_RULE_STATE_DIR": str(state)}
    target = root / "mechanics" / "thing.xs"

    def ctx(sid):
        j, _ = run("rule_router.py", {"cwd": str(root), "session_id": sid, "tool_name": "Read",
                                      "tool_input": {"file_path": str(target)}}, env)
        return ((j or {}).get("hookSpecificOutput") or {}).get("additionalContext", "")

    first = ctx("chg-1")
    names = re.findall(r"^--- rules/(\S+) ---", first, flags=re.M)
    check("a gated file injects at least one rule", bool(names), first[:200])
    if not names:
        return
    rule = root / "rules" / names[0]
    before = rule.read_text(encoding="utf-8")
    try:
        check("the same file again injects nothing", "--- rules/" not in ctx("chg-1"))
        rule.write_text(before.rstrip("\n") + "\n- an added line, to prove an edit is re-sent.\n", encoding="utf-8")
        again = ctx("chg-1")
        check("after the rule is edited, the same session gets it again, marked CHANGED",
              "--- rules/%s --- (CHANGED" % names[0] in again and "an added line" in again, again[:300])
        check("and only once", "--- rules/" not in ctx("chg-1"))
        check("an unchanged rule is still never repeated", all(("--- rules/%s ---" % n) not in again for n in names[1:]))
    finally:
        rule.write_text(before, encoding="utf-8")


def test_fail_open():
    print("fail-open behaviour")
    for hook in ("rule_router.py", "post_write_checks.py"):
        proc = subprocess.run([sys.executable, str(HOOKS / hook)],
                              input="not json at all", capture_output=True, text=True)
        check(f"{hook} exits 0 on unreadable input", proc.returncode == 0, proc.returncode)
        check(f"{hook} stays silent on unreadable input", proc.stdout.strip() == "",
              proc.stdout[:80])

    proc = subprocess.run([sys.executable, str(HOOKS / "guard_docs.py")],
                          input="not json at all", capture_output=True, text=True)
    check("guard_docs.py exits 0 on unreadable input", proc.returncode == 0)
    check("guard_docs.py says so rather than failing silently",
          "unreadable" in proc.stdout, proc.stdout[:80])


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="hook_test_"))
    try:
        root = tmp / "repo"
        state = tmp / "state"
        root.mkdir()
        state.mkdir()
        build_sandbox(root)
        test_guard(root)
        test_router(root, state)
        test_post(root)
        test_readme_shape(root)
        test_announce(root)
        test_gate(root)
        test_handoff_skills(root)
        test_registry(root)
        test_guard_records(root)
        test_focus(root, state)
        test_no_silent_changes(root, state)
        test_answers_waiting(root, state)
        test_changed_rule(root, state)
        test_fail_open()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
