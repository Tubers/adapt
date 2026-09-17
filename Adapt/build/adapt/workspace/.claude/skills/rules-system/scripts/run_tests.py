#!/usr/bin/env python3
"""Self-tests for rules_lib. Builds its fixtures in a temp directory and reads nothing from the repo.

    python .claude/skills/rules-system/scripts/run_tests.py

Repo-independent on purpose: the standing rule here is that a skill must still pass every one of its
own tests when the rest of the repo is deleted, with nothing SKIPPED. A suite that read the live
`rules/` folder would fail that, and would also go red every time a rule was edited, which teaches
people to ignore it.

Companion suite for the hooks themselves:
    python .claude/hooks/test_hooks.py
"""

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rules_lib as lib  # noqa: E402

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


INDEX = """# fixture index

- **xs/alpha.rule.md** | `**/*.xs`, `mechanics/*/README.md` | alpha
- **repo/beta.rule.md** | `cmd:\\bgit\\b` | beta
- **evil/nope.rule.md** | `.claude/skills/**` | must be dropped
- not a gate line at all
- **repo/gamma.rule.md** | `_shared/**` | gamma

<!-- BEGIN GENERATED readme-triggers -->
stale content
<!-- END GENERATED readme-triggers -->
"""

FIXTURE_RULES = {
    "xs/alpha.rule.md": "RULE xs/alpha\n- a line\n",
    "repo/beta.rule.md": "RULE repo/beta\n- a line\n",
    "repo/gamma.rule.md": "RULE repo/gamma\n- a line\n",
    "evil/nope.rule.md": "RULE evil/nope\n- a line\n",
    "writing/delta.rule.md": "RULE writing/delta\n- a line\n",
    "writing/huge.rule.md": "\n".join(f"- line {i}" for i in range(20)) + "\n",
}


def build_repo(root: Path):
    for name, body in FIXTURE_RULES.items():
        p = root / "rules" / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    (root / "rules" / "INDEX.md").write_text(INDEX, encoding="utf-8")

    (root / "mechanics" / "inventory").mkdir(parents=True)
    (root / "mechanics" / "inventory" / "README.md").write_text(
        "rules/writing/delta.rule.md\n", encoding="utf-8")
    (root / "mechanics" / "inventory" / "thing.xs").write_text("// xs\n", encoding="utf-8")
    (root / "mechanics" / "inventory" / "deep").mkdir()
    (root / "mechanics" / "inventory" / "deep" / "README.md").write_text(
        "rules/xs/alpha.rule.md\n", encoding="utf-8")

    (root / "_shared").mkdir()
    (root / "_shared" / "x.py").write_text("x = 1\n", encoding="utf-8")

    skills = root / ".claude" / "skills" / "some-skill"
    skills.mkdir(parents=True)
    (skills / "thing.xs").write_text("// inside a skill\n", encoding="utf-8")
    (skills / "README.md").write_text("a real readme inside a skill\n", encoding="utf-8")


def test_glob():
    print("glob_to_regex")
    check("** crosses directories",
          bool(lib.glob_to_regex("**/*.xs").match("a/b/c.xs")))
    check("**/x.md matches at the root",
          bool(lib.glob_to_regex("**/README.md").match("README.md")))
    check("single * does NOT cross a slash",
          not lib.glob_to_regex("mechanics/*/README.md").match("mechanics/a/b/README.md"))
    check("single * matches one segment",
          bool(lib.glob_to_regex("mechanics/*/README.md").match("mechanics/a/README.md")))
    check("prefix glob anchors at the start",
          not lib.glob_to_regex("_shared/**").match("x/_shared/y.py"))
    check("a literal dot is escaped",
          not lib.glob_to_regex("**/*.xs").match("a/bcxs"))


def test_discovery(root):
    print("nested rule discovery")
    names = lib.all_rules(root)
    check("rules are found recursively in area folders",
          "xs/alpha.rule.md" in names and "writing/delta.rule.md" in names, names)
    check("a rule's name is its path under rules/",
          all("/" in n for n in names), names)
    check("every fixture rule is found", len(names) == len(FIXTURE_RULES), names)
    check("read_rule resolves a nested name",
          (lib.read_rule(root, "xs/alpha.rule.md") or "").startswith("RULE xs/alpha"))
    check("read_rule returns None for a name that is not there",
          lib.read_rule(root, "xs/missing.rule.md") is None)


def test_gates(root):
    print("raw_gates / load_gates")
    # One parser, two callers. reconcile.py once kept a second copy of this regex; when rule names
    # gained a "/" that copy matched nothing and the audit reported every rule as an orphan while
    # exiting as though it had checked. Assert the unfiltered view directly.
    raw = lib.raw_gates(root)
    check("raw_gates parses every gate line, unfiltered", len(raw) == 5, raw)
    check("raw_gates KEEPS the skill-targeted gate so an audit can see it",
          ("evil/nope.rule.md", ".claude/skills/**") in raw, raw)
    check("is_skill_gate identifies it", lib.is_skill_gate(".claude/skills/**"))
    check("is_skill_gate does not fire on a command gate",
          not lib.is_skill_gate("cmd:\\bgit\\b"))

    gates = lib.load_gates(root)
    rules = {g.rule for g in gates}
    check("parses a gate line whose rule name contains a slash",
          {"xs/alpha.rule.md", "repo/beta.rule.md", "repo/gamma.rule.md"} <= rules, rules)
    check("DROPS a gate aimed at the skills directory", "evil/nope.rule.md" not in rules, rules)
    check("ignores a non-gate list item", not any(r.startswith("not") for r in rules))
    cmd = [g for g in gates if g.is_cmd]
    check("a cmd: gate is a command gate", len(cmd) == 1 and cmd[0].rule == "repo/beta.rule.md")
    check("cmd gate matches command text", cmd[0].matches_command("git status"))
    check("cmd gate does not match a lookalike word",
          not cmd[0].matches_command("digital thing"))


def test_matches(root):
    print("match_paths / match_command")
    got = lib.match_paths(root, ["mechanics/inventory/thing.xs"])
    check("a path gate fires", [m.rule for m in got] == ["xs/alpha.rule.md"], got)
    check("the match records WHICH gate pulled it in", got[0].gate == "**/*.xs", got[0].gate)
    check("the match records what it matched",
          got[0].subject == "mechanics/inventory/thing.xs")
    check("the match records its kind", got[0].kind == "path")

    got = lib.match_paths(root, [".claude/skills/some-skill/thing.xs"])
    check("NOTHING fires for a path inside a skill", got == [], got)

    got = lib.match_paths(root, [".claude/skills/some-skill/README.md"])
    check("a README inside a skill triggers nothing either", got == [], got)

    got = lib.match_paths(root, ["mechanics/inventory/README.md"])
    check("a README's own line is honoured",
          "writing/delta.rule.md" in [m.rule for m in got], got)
    check("a README match is labelled as such",
          any(m.kind == "readme" for m in got))

    check("a shallow gate does not leak into a deep folder",
          "xs/alpha.rule.md" not in lib.rules_for_paths(root, ["mechanics/inventory/deep/x.py"]))

    got = lib.rules_for_paths(root, ["mechanics/inventory/thing.xs",
                                     "mechanics/inventory/thing.xs"])
    check("a rule is listed once for repeated paths", got.count("xs/alpha.rule.md") == 1, got)

    got = lib.match_command(root, "git status")
    check("command matching returns provenance too",
          got and got[0].rule == "repo/beta.rule.md" and got[0].kind == "command", got)
    check("an unrelated command matches nothing", lib.match_command(root, "echo hi") == [])


def test_tool_extraction(root):
    print("paths_from_tool")
    os.environ["CLAUDE_PROJECT_DIR"] = str(root)
    rels, cmd = lib.paths_from_tool({
        "tool_name": "Write",
        "cwd": str(root),
        "tool_input": {"file_path": str(root / "mechanics" / "inventory" / "thing.xs")},
    })
    check("Write file_path resolves relative to the repo",
          rels == ["mechanics/inventory/thing.xs"], rels)

    rels, cmd = lib.paths_from_tool({
        "tool_name": "Bash",
        "cwd": str(root),
        "tool_input": {"command": "cat mechanics/inventory/thing.xs | head"},
    })
    check("Bash command paths are extracted",
          "mechanics/inventory/thing.xs" in rels, rels)
    check("Bash command text is returned", "cat" in cmd)

    rels, _ = lib.paths_from_tool({
        "tool_name": "Bash", "cwd": str(root),
        "tool_input": {"command": "echo hello world"},
    })
    check("a command with no path yields no paths", rels == [], rels)
    os.environ.pop("CLAUDE_PROJECT_DIR", None)


def test_budget(root):
    print("oversized_rules")
    over = {n for n, _, _ in lib.oversized_rules(root)}
    check("an over-long nested rule is reported", "writing/huge.rule.md" in over, over)
    check("a rule inside budget is not reported", "xs/alpha.rule.md" not in over, over)
    lines, size = lib.rule_size(root, "xs/alpha.rule.md")
    check("rule_size counts lines and bytes", lines == 2 and size > 0, (lines, size))


def test_readme_scan(root):
    print("find_readmes / readme_rule / sync_index")
    found = {p.relative_to(root).as_posix() for p in lib.find_readmes(root)}
    check("finds repo READMEs", "mechanics/inventory/README.md" in found, found)
    check("SKIPS READMEs inside a skill",
          not any(x.startswith(".claude/skills/") for x in found), found)

    check("reads the nested rule a README names",
          lib.readme_rule(root / "mechanics" / "inventory" / "README.md")
          == "writing/delta.rule.md")

    p = root / "tmp_readme_probe.md"
    p.write_text("xs/alpha.rule.md\n", encoding="utf-8")
    check("a stub without the rules/ prefix still resolves",
          lib.readme_rule(p) == "xs/alpha.rule.md")
    p.write_text("some prose, not a rule path\n", encoding="utf-8")
    check("a README naming no rule returns None", lib.readme_rule(p) is None)

    # The 2026-09-11 shape: several rule paths, a blank line, then orientation for a person.
    p.write_text("rules/xs/alpha.rule.md\nwriting/delta.rule.md\n\nWhat this folder is.\nAnd how "
                 "it is laid out.\n", encoding="utf-8")
    names, body = lib.readme_parse(p)
    check("every rule path in the head is read", names == ["xs/alpha.rule.md",
                                                           "writing/delta.rule.md"], names)
    check("orientation is returned separately", len(body) == 2, body)
    check("readme_rule still returns the first", lib.readme_rule(p) == "xs/alpha.rule.md")

    p.write_text("xs/alpha.rule.md\n", encoding="utf-8")
    names, body = lib.readme_parse(p)
    check("a bare trigger parses with no orientation", names == ["xs/alpha.rule.md"] and body == [])

    p.write_text("prose first\n\nxs/alpha.rule.md\n", encoding="utf-8")
    names, _ = lib.readme_parse(p)
    check("a rule path BELOW prose is not a trigger", names == [], names)
    p.unlink()

    changed = lib.sync_index(root)
    text = (root / "rules" / "INDEX.md").read_text(encoding="utf-8")
    check("sync rewrites the generated block", changed and "stale content" not in text)
    check("generated block lists a README row with its nested rule",
          "- `mechanics/inventory/README.md` | `writing/delta.rule.md`" in text)
    check("hand-maintained gates survive the sync", "**xs/alpha.rule.md**" in text)
    check("a second sync is a no-op", lib.sync_index(root) is False)


def test_session_memory():
    print("session memory")
    with tempfile.TemporaryDirectory() as d:
        os.environ["CLAUDE_RULE_STATE_DIR"] = d
        check("a fresh session has sent nothing", lib.already_sent("s1") == set())
        lib.mark_sent("s1", ["xs/alpha.rule.md"])
        check("a sent rule is remembered", "xs/alpha.rule.md" in lib.already_sent("s1"))
        check("sessions do not share state", lib.already_sent("s2") == set())
        lib.mark_sent("s1", ["repo/beta.rule.md"])
        check("marking is additive",
              lib.already_sent("s1") == {"xs/alpha.rule.md", "repo/beta.rule.md"})
        os.environ.pop("CLAUDE_RULE_STATE_DIR", None)


def test_firing_log(root):
    print("firing log")
    log = root / lib.FIRING_LOG
    check("no log exists before anything fires", not log.is_file())
    check("reading an absent log is empty, not an error", lib.read_firings(root) == [])

    stats = lib.firing_stats(root)
    check("with no firings, every declared gate is never-fired",
          len(stats["never_fired_gates"]) == len(stats["declared_gates"]) > 0, stats["records"])

    matches = lib.match_paths(root, ["mechanics/inventory/thing.xs"])
    lib.log_firings(root, "sess-abc", "Read", matches)
    check("the log is created on the first firing", log.is_file())

    recs = lib.read_firings(root)
    check("one record per match", len(recs) == len(matches), recs)
    check("the record carries the rule", recs[0]["rule"] == "xs/alpha.rule.md", recs[0])
    check("the record carries the GATE that fired it", recs[0]["gate"] == "**/*.xs", recs[0])
    check("the record carries the tool", recs[0]["tool"] == "Read")
    check("the session id is recorded", recs[0]["session"] == "sess-abc")

    lib.log_firings(root, "sess-abc", "Read", matches)
    stats = lib.firing_stats(root)
    check("counts accumulate", stats["per_rule"]["xs/alpha.rule.md"] == 2, stats["per_rule"])
    check("a fired gate leaves the never-fired list",
          ("xs/alpha.rule.md", "**/*.xs") not in stats["never_fired_gates"])
    check("gates that did not fire are still listed",
          ("repo/gamma.rule.md", "_shared/**") in stats["never_fired_gates"],
          stats["never_fired_gates"])
    check("rules that never fired are listed",
          "writing/huge.rule.md" in stats["never_fired_rules"], stats["never_fired_rules"])
    check("logging nothing writes nothing",
          (lib.log_firings(root, "s", "Read", []) or True) and len(lib.read_firings(root)) == 2)

    log.unlink()


def test_refactor_commands(root):
    """The seam between this skill and vector-search: reachable, described, and absent-safe."""
    import io
    import contextlib

    print("\nrefactoring commands")
    import rules

    for name in ("audit", "facts", "dupes", "coherence", "hubs", "coverage", "asked", "move", "upkeep"):
        check(f"`{name}` is dispatchable", name in rules.DISPATCH)
        check(f"`{name}` is in the help listing", name in rules.COMMANDS)
        spec = rules.COMMANDS.get(name, ("", "", ""))
        check(f"`{name}` has a one-line summary", bool(spec[1]))

    check("`coverage` maps onto the report named `gates` there",
          "gates" in rules.VECTOR_REPORTS)
    check("`refactor` is the whole-pass report", "refactor" in rules.VECTOR_REPORTS)

    # With the other skill missing, every one of these must SAY so and return 2, not raise. The
    # suite has to pass in a folder holding nothing but this skill.
    real = rules.project_root
    rules.project_root = lambda: root / "no-such-repo"
    try:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = rules.vector_report("facts")
        out = buf.getvalue()
        check("a missing vector-search skill returns 2", rc == 2, rc)
        check("and says so in words", "not installed" in out, out.strip()[:60])
        check("and points at what still works", "reconcile" in out, out.strip()[:60])
    finally:
        rules.project_root = real


def test_move(root):
    """A move rewrites every reference, touches nothing that only looks like one, and keeps CRLF."""
    print("\nmoving a rule")
    rules = root / "rules"
    (rules / "xs" / "alpha.rule.md").write_bytes(b"RULE xs/alpha - a\r\n- see repo/beta.\r\n")
    (rules / "writing" / "delta.rule.md").write_bytes(
        b"RULE writing/delta\n- owner: xs/alpha. Not _shared/xs/alpha.py, not xs/alpha-old.\n")

    before = (rules / "writing" / "delta.rule.md").read_bytes()
    changed = lib.move_rule(root, "xs/alpha", "repo/group/alpha", write=False)
    check("a dry run writes nothing", (rules / "xs" / "alpha.rule.md").is_file()
          and (rules / "writing" / "delta.rule.md").read_bytes() == before)
    check("a dry run still lists the files", len(changed) >= 3, changed)

    for bad, why in (("xs/alpha", "repo/beta"), ("xs/nothing", "repo/new"), ("xs/alpha", "Bad Name")):
        try:
            lib.move_rule(root, bad, why)
            check(f"move {bad} -> {why} is refused", False)
        except ValueError:
            check(f"move {bad} -> {why} is refused", True)

    lib.move_rule(root, "xs/alpha", "repo/group/alpha")
    moved = rules / "repo" / "group" / "alpha.rule.md"
    check("the file moved", moved.is_file() and not (rules / "xs" / "alpha.rule.md").exists())
    check("its own header was renamed", moved.read_bytes().startswith(b"RULE repo/group/alpha - a"))
    check("CRLF survived the rewrite", b"\r\n- see repo/beta.\r\n" in moved.read_bytes())
    delta = (rules / "writing" / "delta.rule.md").read_text(encoding="utf-8")
    check("a prose pointer was rewritten", "owner: repo/group/alpha." in delta, delta)
    check("a longer path that only contains the name was not",
          "_shared/xs/alpha.py" in delta and "xs/alpha-old" in delta, delta)
    index = (rules / "INDEX.md").read_text(encoding="utf-8")
    check("the gate line follows the rule", "**repo/group/alpha.rule.md**" in index
          and "**xs/alpha.rule.md**" not in index)
    readme = (root / "mechanics" / "inventory" / "deep" / "README.md").read_text(encoding="utf-8")
    check("a README naming it was rewritten", "rules/repo/group/alpha.rule.md" in readme, readme)
    check("the moved rule still has its gates",
          "repo/group/alpha.rule.md" in {g.rule for g in lib.load_gates(root)})


def test_accepted(root):
    """The accepted list: entries need a why, facts key on text, moves follow, reports get the path."""
    print("\naccepted findings")
    import accepted
    import rules

    rules_dir = root / "rules"
    (rules_dir / "repo" / "long.rule.md").write_text(
        "RULE repo/long\n- a statement long enough to count as a fact in the report\n", encoding="utf-8")
    (rules_dir / "writing" / "other.rule.md").write_bytes(
        b"RULE writing/other\r\n- another statement long enough to count as a fact\r\n")
    resolve = lambda t: rules._resolve(root, t)
    data = accepted.load(root / "nothing.json")
    check("a missing list loads empty", all(data[k] == [] for k in accepted.KINDS))

    def refused(kind, args, why="because"):
        try:
            accepted.make_entry(root, kind, args, why, resolve)
            return False
        except ValueError:
            return True

    check("an entry without a why is refused", refused("dupes", ["repo/long", "writing/other"], ""))
    check("an unknown kind is refused", refused("nope", ["repo/long"]))
    check("an unknown rule is refused", refused("coherence", ["repo/missing"]))
    check("a fact line that does not exist is refused", refused("facts", ["repo/long:9", "writing/other:2"]))
    check("a fact line too short to be compared is refused", refused("facts", ["repo/long:1", "writing/other:2"]))
    check("a pair of one rule with itself is refused", refused("dupes", ["repo/long", "repo/long"]))
    check("a missing-gate entry names a real file", refused("missing", ["no/such.py", "repo/long"]))

    e = accepted.make_entry(root, "facts", ["repo/long:2", "writing/other.rule.md:2"], "split", resolve)
    check("a fact stores the line TEXT as the index does, dash stripped",
          e["text_a"] == "a statement long enough to count as a fact in the report", e)
    check("CRLF does not leak into the stored text", not e["text_b"].endswith("\r"), e["text_b"])
    check("a rule name is stored without its suffix", e["b"] == "writing/other", e["b"])
    check("the first add records it", accepted.add(data, "facts", e))
    flipped = dict(e, a=e["b"], b=e["a"], text_a=e["text_b"], text_b=e["text_a"])
    check("the same pair in the other order is not recorded twice", not accepted.add(data, "facts", flipped))
    accepted.add(data, "coherence", accepted.make_entry(root, "coherence", ["repo/long"], "tree", resolve))

    path = root / "data" / "accepted.json"
    accepted.save(data, path)
    back = accepted.load(path)
    check("the list round-trips through its file", back["facts"] == data["facts"])

    n = accepted.rename_rule(back, "repo/long.rule.md", "repo/group/long")
    check("a move renames every entry naming the rule", n == 2
          and back["facts"][0]["a"] == "repo/group/long" and back["coherence"][0]["rule"] == "repo/group/long")

    args = rules.report_args("facts", ["--cut", "0.8"], accepted_path=path)
    check("a filtering report is handed the list", args[-2:] == ["--accepted", str(path)], args)
    check("`hubs` is not, it has nothing to accept", "--accepted" not in rules.report_args("hubs", [], path))
    check("`--all` shows everything", "--accepted" not in rules.report_args("dupes", ["--all"], path)
          and "--all" not in rules.report_args("dupes", ["--all"], path))
    check("no list on disk, no flag", "--accepted" not in rules.report_args("facts", [], root / "none.json"))
    check("`accept` is dispatchable and described", "accept" in rules.DISPATCH and "accept" in rules.COMMANDS)


def test_upkeep(tmp: Path):
    """Knowledge upkeep on a throwaway repo: each drift class fires on its own fixture and nothing else."""
    print("\nknowledge upkeep")
    import upkeep

    root = tmp / "upkeep_repo"
    (root / "rules").mkdir(parents=True)
    (root / "rules" / "INDEX.md").write_text(
        "# idx\n\n- **writing/a.rule.md** | `mech/**` | a\n\n"
        "<!-- BEGIN GENERATED readme-triggers -->\n<!-- END GENERATED readme-triggers -->\n",
        encoding="utf-8")
    (root / "rules" / "writing").mkdir()
    (root / "rules" / "writing" / "a.rule.md").write_text("RULE writing/a - a\n- one\n", encoding="utf-8")
    mech = root / "mech"
    mech.mkdir()
    (mech / "README.md").write_text("rules/writing/a.rule.md\n", encoding="utf-8")
    (mech / "thing_dev.py").write_text("x = 1\n", encoding="utf-8")

    def run(stamp, results=True):
        d = root / "test_runs" / "scen_dev" / "runs" / ("scen_%s" % stamp)
        d.mkdir(parents=True)
        if results:
            (d / "RESULTS.md").write_text("# r\n", encoding="utf-8")
        return d.relative_to(root).as_posix()

    old = run("20260801-100000")
    closed = run("20260913-100000")
    exempt = run("20260913-110000")
    no_event = run("20260913-120000")
    no_rule = run("20260914-090000")
    no_results = run("20260914-100000", results=False)
    events = [
        {"id": "2026-09-13-a", "ts": "2026-09-13", "kind": "run", "title": "t", "evidence": [closed + "/"],
         "refs": ["writing/a"]},
        {"id": "2026-09-13-b", "ts": "2026-09-14", "kind": "run", "title": "t", "evidence": [exempt],
         "no_rule": "narrow to this folder"},
        {"id": "2026-09-14-c", "ts": "2026-09-14", "kind": "run", "title": "t", "evidence": [no_rule + "/"],
         "refs": ["2026-09-13-a"]},
        {"id": "2026-09-14-d", "ts": "2026-09-14", "kind": "run", "title": "t",
         "evidence": [no_results + "/"], "refs": ["writing/a"]},
    ]
    (mech / ".rs" / "HISTORY.jsonl").parent.mkdir(parents=True, exist_ok=True)
    (mech / ".rs" / "HISTORY.jsonl").write_text("\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8")

    brief = upkeep.report(root, full=False, running=False)
    by = {c["name"]: c for c in brief}
    check("brief holds the cheap classes", [c["name"] for c in brief] == ["INDEX", "RUN", "HISTORY", "CANDIDATE", "PROJECT"])
    check("with no vector-search skill, INDEX says SKIPPED and why",
          by["INDEX"]["skipped"] and "not installed" in by["INDEX"]["skipped"], by["INDEX"])
    runs = " ".join(by["RUN"]["items"])
    check("a run with no history event is reported", no_event in runs, runs)
    check("a run whose event names no rule and no reason is reported", no_rule in runs, runs)
    check("a run with no RESULTS.md is reported", no_results in runs and "no RESULTS.md" in runs, runs)
    check("a run closed by a rule is not", closed not in runs, runs)
    check("a run closed by a no_rule reason is not", exempt not in runs, runs)
    check("a run before the baseline is never listed", old not in runs, runs)
    check("but it is counted in a note", by["RUN"]["note"] and "1 run(s)" in by["RUN"]["note"], by["RUN"]["note"])
    check("valid history reports nothing", by["HISTORY"]["count"] == 0, by["HISTORY"]["items"])

    with open(mech / ".rs" / "HISTORY.jsonl", "a", encoding="utf-8") as f:
        f.write("{not json\n")
        f.write(json.dumps({"id": "x", "ts": "2026-09-14", "kind": "musing", "title": "t"}) + "\n")
        f.write(json.dumps({"id": "y", "kind": "note"}) + "\n")
    items = upkeep.report(root, running=False)[2]["items"]
    check("a line that is not JSON is reported with file and line", any("HISTORY.jsonl:5" in i and "JSON" in i
                                                                         for i in items), items)
    check("an unknown kind is reported", any("musing" in i for i in items), items)
    check("a missing required key is reported", any("lacks ts, title" in i for i in items), items)

    fake = root / ".claude" / "skills" / "vector-search" / "scripts" / "index.py"
    fake.parent.mkdir(parents=True)
    fake.write_text("print('[]')\n", encoding="utf-8")
    check("the game running skips INDEX rather than competing with it",
          "game is running" in (upkeep.report(root, running=True)[0]["skipped"] or ""))
    check("an index with nothing behind reports nothing",
          upkeep.report(root, running=False)[0] == upkeep.result("INDEX", fix=upkeep.check_index(
              root)["fix"]))
    shutil.rmtree(root / ".claude")

    # full classes
    (root / "loose").mkdir()
    (root / "loose" / "probe.py").write_text("x = 1\n", encoding="utf-8")
    (root / "loose" / "RESULTS.md").write_text("# stray\n", encoding="utf-8")
    (root / "tool_development" / "old").mkdir(parents=True)
    (root / "tool_development" / "old" / "x.py").write_text("x = 1\n", encoding="utf-8")
    (root / "tool_development" / "old" / "RESULTS.md").write_text("# inert\n", encoding="utf-8")
    full = {c["name"]: c for c in upkeep.report(root, full=True, running=False)}
    check("full adds RULES, FOLDER and RESULTS", {"RULES", "FOLDER", "RESULTS"} <= set(full))
    check("a live folder with code and no README is reported", any("loose/" in i for i in full["FOLDER"]["items"]),
          full["FOLDER"]["items"])
    check("a folder with a README is not", not any(i.startswith("mech/") for i in full["FOLDER"]["items"]))
    check("tool_development is historical and never reported",
          not any("tool_development" in i for i in full["FOLDER"]["items"] + full["RESULTS"]["items"]))
    check("a RESULTS.md outside the run layout is reported",
          any("loose/RESULTS.md" in i for i in full["RESULTS"]["items"]), full["RESULTS"]["items"])
    check("reconcile runs against the repo it was given", full["RULES"]["skipped"] is None
          and full["RULES"]["count"] == 0, full["RULES"])

    # output
    clean = [upkeep.result("INDEX"), upkeep.result("RUN"), upkeep.result("HISTORY")]
    check("brief prints NOTHING when every class ran and found nothing", upkeep.render_brief(clean) == "")
    only_skip = [upkeep.result("INDEX", skipped="why not"), upkeep.result("RUN")]
    check("a skipped class is never silent", "SKIPPED: why not" in upkeep.render_brief(only_skip))
    text = upkeep.render_brief(brief)
    check("brief names each drifting class once, with the detail command",
          text.count("\n  RUN ") == 1 and upkeep.DETAIL in text, text)
    check("full says when a class ran clean", "no drift" in upkeep.render_full(clean))

    s = upkeep.stats(root)
    check("stats measures days from run to its entry", "days from run to entry" in s, s)


def test_project_upkeep(tmp: Path):
    """The PROJECT class: every project keeps all three files, a TASKS.md in format and moving, no nested records."""
    print("\nproject upkeep")
    import datetime
    import tasks
    import upkeep

    root = tmp / "project_repo"
    (root / "rules").mkdir(parents=True)
    old = root / "mech" / "old"
    old.mkdir(parents=True)
    (old / ".rs" / "HISTORY.jsonl").parent.mkdir(parents=True, exist_ok=True)
    (old / ".rs" / "HISTORY.jsonl").write_text(json.dumps({"id": "a", "ts": "2026-09-01", "kind": "note", "title": "an old note"})
                                       + "\n", encoding="utf-8")
    (root / ".claude" / "x").mkdir(parents=True)
    (root / ".claude" / "x" / ".rs" / "HISTORY.jsonl").parent.mkdir(parents=True, exist_ok=True)
    (root / ".claude" / "x" / ".rs" / "HISTORY.jsonl").write_text("", encoding="utf-8")
    (root / "_backup" / "y").mkdir(parents=True)
    (root / "_backup" / "y" / ".rs" / "TASKS.md").parent.mkdir(parents=True, exist_ok=True)
    (root / "_backup" / "y" / ".rs" / "TASKS.md").write_text("junk\n", encoding="utf-8")

    def items(now=None):
        return upkeep.check_projects(root, now=now)["items"]

    got = items()
    check("a project with only its history is reported, with the command that completes it",
          any(i.startswith("mech/old/ has no TASKS.md") and "rules.py init mech/old" in i for i in got), got)
    check("records under .claude/ or _backup/ are no project", not any(".claude" in i or "_backup" in i for i in got), got)
    before = (old / ".rs" / "HISTORY.jsonl").read_text(encoding="utf-8")
    r = tasks.init(root, "mech/old", "bring the old project into the format")
    check("init completes an older project without touching its history lines",
          (old / ".rs" / "HISTORY.jsonl").read_text(encoding="utf-8").startswith(before)
          and r["entry"]["title"].startswith("project files completed") and (old / ".rs" / "QUESTIONS.jsonl").is_file())
    check("a complete, empty project reports nothing", items() == [], items())

    tasks.add(root, "mech/old", "the first task in the window", details="what the first task is for and what done means")
    since = tasks.load(root, "mech/old")["tasks"][0]["date"]
    later = datetime.date.fromisoformat(since) + datetime.timedelta(days=upkeep.STALE_DAYS + 1)
    check("a task in progress past the stale limit is reported", any("t1 in progress 15 days" in i for i in items(later)),
          items(later))
    check("and not before it", items() == [], items())

    t = old / ".rs" / "TASKS.md"
    t.write_text(t.read_text(encoding="utf-8").replace("**t1** ·", "**t9** ·"), encoding="utf-8")
    check("a TASKS.md out of format is reported with its problems", any("out of format" in i and "t1" in i for i in items()),
          items())

    (old / "sub").mkdir()
    (old / "sub" / ".rs" / "HISTORY.jsonl").parent.mkdir(parents=True, exist_ok=True)
    (old / "sub" / ".rs" / "HISTORY.jsonl").write_text("", encoding="utf-8")
    check("a history-only subfolder inside a project is reported, with the merge and init commands",
          any(i.startswith("mech/old/sub/") and "history merge mech/old" in i and "init mech/old/sub" in i for i in items()), items())
    (old / "sub" / ".rs" / "HISTORY.jsonl").unlink()
    tasks.init(root, "mech/old/sub", "a sub-project made on purpose", task="t1")
    check("a sub-project made by init is not reported", not any(i.startswith("mech/old/sub/") for i in items()), items())


def test_root_and_parent(tmp: Path):
    """The repo root as a project, and a sub-project linked to the parent task it serves (the user, 2026-09-14)."""
    print("\nroot projects and parent links")
    import history
    import rules_lib as lib
    import tasks
    import upkeep
    import viewer

    def refused(fn, *a, **k):
        try:
            fn(*a, **k)
            return ""
        except ValueError as e:
            return str(e)

    root = tmp / "rootproj_repo"
    (root / "rules").mkdir(parents=True)
    (root / "other").mkdir()
    r = tasks.init(root, ".", "the whole repository's work")
    check("init . makes the repo root a project",
          all((root / ".rs" / m).is_file() for m in ("HISTORY.jsonl", "TASKS.md", "QUESTIONS.jsonl")), r)
    check("the root's project is named '.' and is the last stop up the path",
          lib.project_of(root, "") == "." and lib.project_of(root, "other/x.py") == ".")
    check("machinery is never part of the root's project",
          lib.project_of(root, ".claude/x.py") is None and lib.project_of(root, "rules/a.rule.md") is None)
    history.add(root, "other", "note", "a note from a folder with no project of its own")
    check("a folder with no project of its own logs to the root's file, tagged with the folder",
          any(e["title"] == "a note from a folder with no project of its own" and e["_file"] == ".rs/HISTORY.jsonl"
              and history.effective_folder(e) == "other" for e in history.entries(root, ".")))
    (root / "sub").mkdir()
    check("a sub-project must name the parent task it serves", "--task" in refused(tasks.init, root, "sub", "the sub goal"))
    check("and nothing is written when it does not", not (root / "sub" / ".rs" / "TASKS.md").exists())
    tasks.add(root, ".", "build the sub thing", details="the task a sub-project will be started for")
    check("the named task must be in the parent's window", "no task t9" in refused(tasks.init, root, "sub", "the sub goal", task="t9"))
    tasks.init(root, "sub", "the sub goal", task="t1")
    p = tasks.load(root, "sub")
    check("the sub-project's window carries its parent line", p["parent"] == {"project": ".", "task": "t1"}, p.get("parent"))
    check("the parent line survives a rewrite", tasks.parse(tasks.render(p))["parent"] == {"project": ".", "task": "t1"})
    check("the parent task lists its sub-project", tasks.children(root, ".") == {"t1": ["sub"]}, tasks.children(root, "."))
    check("show names the sub-project on its parent task's line", "-> sub-project sub/" in tasks.show(root, "."), tasks.show(root, "."))
    check("show names the parent in the sub-project", "parent: ./ task t1" in tasks.show(root, "sub"), tasks.show(root, "sub"))
    check("the parent's history records which task started it",
          any(e.get("subproject") == "sub" and e.get("task") == "t1" for e in history.entries(root, ".")))
    check("upkeep finds nothing wrong with a root project and its sub-project", upkeep.check_projects(root)["items"] == [],
          upkeep.check_projects(root)["items"])
    data = viewer.payload(root, ".")
    check("the viewer gives the parent's tasks their sub-projects", data["children"] == {"t1": ["sub"]}, data["children"])
    up = viewer.payload(root, "sub")["parent_task"] or {}
    check("and gives the sub-project its parent task, for the link back up", up.get("text") == "build the sub thing", up)
    proj, how = viewer.resolve_project(root, None, str(root), "no-such-session")
    check("run from the repo root with nothing else to go on, the root's project is used", proj == ".", (proj, how))


def test_history(tmp: Path):
    """History through commands: stamped writes, refused bad runs, slices by kind, folder state."""
    print("\nfolder history commands")
    import history
    import upkeep

    os.environ["CLAUDE_CODE_SESSION_ID"] = "test-session-1"
    root = tmp / "hist_repo"
    (root / "rules" / "writing").mkdir(parents=True)
    (root / "rules" / "INDEX.md").write_text("# idx\n\n- **writing/a.rule.md** | `mech/**` | a\n", encoding="utf-8")
    (root / "rules" / "writing" / "a.rule.md").write_text("RULE writing/a - a\n- one fact line long enough\n",
                                                          encoding="utf-8")
    run = root / "test_runs" / "scen_dev" / "runs" / "scen_20260913-100000"
    run.mkdir(parents=True)
    (root / "mech" / "sub").mkdir(parents=True)
    (root / "other").mkdir()
    RUN = run.relative_to(root).as_posix()

    def refused(*a, **k):
        try:
            history.add(root, *a, **k)
            return ""
        except ValueError as e:
            return str(e)

    check("a candidate cannot be added directly", "rules.py park" in refused("mech", "candidate", "a fact here"))
    check("a run must name its run folder", "--evidence" in refused("mech", "run", "ran the thing", refs=["writing/a"]))
    check("a run must close with a rule, a candidate or a reason",
          "--no-rule" in refused("mech", "run", "ran the thing", evidence=[RUN]))
    check("refs must name a real rule", "no rule" in refused("mech", "finding", "found a thing", refs=["writing/nope"]))
    check("no history is kept under test_runs/", "keeps no HISTORY" in refused("test_runs", "note", "a note here"))
    check("an unknown kind is refused", bool(refused("mech", "musing", "a thought here")))
    check("a folder that does not exist is refused", "no such folder" in refused("nowhere", "note", "a note here"))

    e = history.add(root, "mech", "run", "ran scen_dev at three distances", result="entered at 4.0",
                    evidence=[RUN], refs=["writing/a"])["entry"]
    check("history add creates the folder's HISTORY.jsonl", (root / "mech" / ".rs" / "HISTORY.jsonl").is_file())
    check("and stamps id, date, time and session", e["id"] == e["ts"] + "-ran-scen-dev-at-three-distances"
          and e["session"] == "test-session-1" and "T" in e["time"], e)
    history.add(root, "mech/sub", "finding", "a finding in the sub folder")
    history.add(root, "mech", "change", "moved the probes into the sub folder")
    history.add(root, "other", "note", "visited other to fix a path")
    for i in range(7):
        history.add(root, "mech", "note", "note number %d in sequence" % i)

    evs = history.entries(root, "mech")
    check("subfolder work lands in the project's file, tagged with its subfolder",
          any(x["_file"] == "mech/.rs/HISTORY.jsonl" and history.effective_folder(x) == "mech/sub" for x in evs), evs)
    check("and never a sibling folder", not any(x["_file"].startswith("other/") for x in evs))
    def body(text):
        return text.split("\n\n", 1)[-1]        # the entries, after the folder's state

    txt = body(history.render_slice(root, "mech", ["note"]))
    check("a kind slice shows the last 5 by default", txt.count("note number") == 5
          and "note number 6" in txt and "note number 1 in" not in txt, txt)
    txt = body(history.render_slice(root, "mech", ["note"], first=5))
    check("--first 5 shows the earliest five", "note number 0" in txt and "note number 6" not in txt, txt)
    runs = body(history.render_slice(root, "mech", ["run"]))
    check("runs slice by kind", "ran scen_dev" in runs and "note number" not in runs, runs)
    check("every entry is one line", all(len(line) < 240 for line in txt.splitlines()))
    check("grep narrows a slice across the repo", "moved the probes" in history.render_slice(root, None, [], grep="probes"))
    check("a folder slice opens with the folder's state", history.render_slice(root, "mech", []).startswith("FOLDER mech/"))
    (root / "mech" / ".rs" / "TASKS.md").parent.mkdir(parents=True, exist_ok=True)
    (root / "mech" / ".rs" / "TASKS.md").write_text("TASKS mech - x\n- [x] 2026-09-12 done thing\n"
                                             "- [ ] NOW 2026-09-13 current thing\n- [ ] next one\n- [ ] next two\n",
                                             encoding="utf-8")
    st = history.folder_state(root, "mech")
    check("folder state shows the NOW task and how many are next", "NOW 2026-09-13 current thing" in st
          and "+2 next" in st, st)
    check("a project's state counts every entry in its file, subfolder work included", "10 entries" in st, st)
    check("show prints one entry in full", '"result": "entered at 4.0"' in history.show(root, e["id"]))

    path = root / "mech" / ".rs" / "HISTORY.jsonl"
    lines_before = path.read_text(encoding="utf-8").splitlines()
    history.set_keys(path, e["id"], {"status": "closed"})
    after = path.read_text(encoding="utf-8").splitlines()
    check("set_keys changes one entry in place and nothing else", len(after) == len(lines_before)
          and json.loads(after[0])["status"] == "closed" and after[1:] == lines_before[1:])
    check("everything the commands wrote is valid history", not upkeep.read_history(root)[1],
          upkeep.read_history(root)[1])
    check("records live under data/<repo root folder name>/", history.data_dir(root).name == "hist_repo")


def test_project_history(tmp: Path):
    """A project keeps one history: subfolder work logs there with its folder, and merge folds old files in."""
    print("\nproject-level history")
    import history
    import upkeep

    root = tmp / "proj_repo"
    for sub in ("pickup", "garrison", "empty"):
        (root / "mech" / "inv" / sub).mkdir(parents=True)
    (root / "rules").mkdir()
    history.add(root, "mech/inv/pickup", "note", "an old pickup note one", when="2026-08-02")
    history.add(root, "mech/inv/garrison", "note", "an old garrison note", when="2026-08-01")
    history.add(root, "mech/inv/pickup", "finding", "an old pickup finding", when="2026-08-03")
    check("before a project file exists, a subfolder starts its own",
          (root / "mech/inv/pickup/.rs/HISTORY.jsonl").is_file() and not (root / "mech/inv/.rs/HISTORY.jsonl").is_file())

    dry = history.merge(root, "mech/inv", write=False)
    check("a dry run writes nothing", dry["entries"] == 3 and not (root / "mech/inv/.rs/HISTORY.jsonl").is_file(), dry)
    s = history.merge(root, "mech/inv", when="2026-09-13")
    merged = [json.loads(l) for l in (root / "mech/inv/.rs/HISTORY.jsonl").read_text(encoding="utf-8").splitlines()]
    check("every entry is merged, in date order, then the merge logs itself",
          [e["title"] for e in merged] == ["an old garrison note", "an old pickup note one", "an old pickup finding",
                                           "merged 2 subfolder histories into this project's HISTORY.jsonl"], merged)
    check("each merged entry keeps its subfolder", merged[0]["folder"] == "mech/inv/garrison/"
          and merged[1]["folder"] == "mech/inv/pickup/", merged[:2])
    check("the originals are moved to a dated backup, not deleted",
          not (root / "mech/inv/pickup/.rs/HISTORY.jsonl").exists()
          and (root / ".claude/_backup/history-merge-2026-09-13/mech/inv/pickup/.rs/HISTORY.jsonl").is_file())
    check("merging again finds nothing to merge", "no subfolder histories" in _err(lambda: history.merge(root, "mech/inv")))

    e = history.add(root, "mech/inv/pickup", "note", "a new note from the pickup subfolder")["entry"]
    check("new subfolder work goes to the project's file, with its folder",
          e["_file"] == "mech/inv/.rs/HISTORY.jsonl" and e["folder"] == "mech/inv/pickup/", e)
    check("no subfolder file is created again", not (root / "mech/inv/pickup/.rs/HISTORY.jsonl").exists())
    sub = history.render_slice(root, "mech/inv/pickup", [])
    check("a subfolder slice shows only that subfolder's entries",
          "pickup" in sub and "garrison note" not in sub, sub)
    check("a project slice shows them all", "garrison note" in history.render_slice(root, "mech/inv", [], everything=True))
    check("the merged file is valid history", not upkeep.read_history(root)[1], upkeep.read_history(root)[1])


def _err(fn):
    try:
        fn()
        return ""
    except ValueError as e:
        return str(e)


def test_candidates(tmp: Path):
    """Park, queue, decide: stamped, written twice, decided against one cosine pass, resolved in both copies."""
    print("\nrule candidates")
    import datetime
    import candidates
    import history
    import rules
    import upkeep

    real_base = history.DATA_BASE
    history.DATA_BASE = tmp / "skill_data"
    os.environ["CLAUDE_CODE_SESSION_ID"] = "test-session-2"
    try:
        root = tmp / "cand_repo"
        (root / "rules" / "writing").mkdir(parents=True)
        (root / "rules" / "xs").mkdir()
        (root / "rules" / "INDEX.md").write_text(
            "# idx\n\n- **writing/a.rule.md** | `mech/**` | a\n- **writing/new.rule.md** | `mech/**` | new\n"
            "- **xs/far.rule.md** | `other/**` | far\n- **xs/fact.rule.md** | `mech/**` | fact\n\n"
            "<!-- BEGIN GENERATED readme-triggers -->\n<!-- END GENERATED readme-triggers -->\n", encoding="utf-8")
        for n in ("writing/a", "writing/new", "writing/ungated", "xs/far"):
            (root / "rules" / (n + ".rule.md")).write_text("RULE %s - x\n- a line long enough to be a fact\n" % n,
                                                           encoding="utf-8")
        OLD = "reach is measured between the two unit centres"
        fact = root / "rules" / "xs" / "fact.rule.md"
        fact.write_text("RULE xs/fact - x\n- %s\n- another line entirely\n" % OLD, encoding="utf-8")
        (root / "mech").mkdir()
        (root / ".claude").mkdir()
        run = root / "test_runs" / "scen_dev" / "runs" / "scen_20260913-100000"
        run.mkdir(parents=True)
        RUN = run.relative_to(root).as_posix()
        FACT = "a garrison order only reaches a container within work_range of its collision box"

        def near(rule="writing/a", score=0.5, said="said"):
            return lambda text: [{"rule": rule + ".rule.md", "score": score, "line": 2, "kind": "line", "text": said}]

        def down(text):
            raise candidates.Unavailable("no model here")

        def refused(fn, *a, **k):
            try:
                fn(root, *a, **k)
                return ""
            except ValueError as e:
                return str(e)

        def read(p):
            return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]

        folder_file = root / "mech" / ".rs" / "HISTORY.jsonl"
        master = history.master_path(root)
        c = candidates.park(root, FACT, "mech", run=RUN, nearest=near())["candidate"]
        check("the master copy lives in data/<repo root name>/candidates.jsonl",
              master == tmp / "skill_data" / "cand_repo" / "candidates.jsonl", master)
        check("parking writes the same record to the folder's history and the master copy",
              read(folder_file) == read(master) == [c], (read(folder_file), read(master)))
        check("it starts pending with no reason", c["status"] == "pending" and c["reason"] == "")
        check("it is stamped with time and session", c["found"]["session"] == "test-session-2"
              and "T" in c["found"]["time"], c["found"])
        check("it names the run it came from", c["run"] == RUN and c["evidence"] == [RUN])
        check("it keeps what the pass found when parked", c["pass"]["nearest"][0]["rule"] == "writing/a"
              and c["pass"]["scope"]["minimum"] == "mech/**", c["pass"])
        check("a fact needs its run, or a reason there is none",
              "--no-run" in refused(candidates.park, FACT, "mech", nearest=near()))
        check("--run must be a run folder",
              "no run folder" in refused(candidates.park, FACT, "mech", run="test_runs/scen_dev", nearest=near()))
        for args, why in ((("too short", "mech"), "a fragment"), ((FACT, "nowhere"), "a missing folder"),
                          ((FACT, ".claude"), ".claude/"), ((FACT, "rules"), "rules/")):
            check("parking refuses %s" % why, bool(refused(candidates.park, *args, no_run="x", nearest=near())))
        c2 = candidates.park(root, FACT, "mech", no_run="read offline from the dataset", nearest=down)["candidate"]
        check("the same fact twice gets its own id", c2["id"] == c["id"] + "-2", c2["id"])
        check("a pass that cannot run is recorded as such, and still parks",
              c2["pass"] == {"unavailable": "no model here"} and c2["no_run"])
        check("the queue lists pending candidates in the order found",
              [x["id"] for x in candidates.queue(root)] == [c["id"], c2["id"]])
        check("next is the oldest pending", candidates.next_pending(root)["id"] == c["id"])

        def deny(cid, outcome, **k):
            return refused(candidates.decide, cid, outcome, **k)

        check("approve needs a rule", "--rule" in deny(c["id"], "approve", nearest=near()))
        check("approve refuses a rule file that does not exist",
              "no rule file" in deny(c["id"], "approve", rule="writing/missing", nearest=near()))
        check("approve refuses a rule nothing gates", "no gate" in deny(c["id"], "approve", rule="writing/ungated", nearest=near()))
        check("approve refuses a rule that does not fire on the fact's folder",
              "does not fire on mech/" in deny(c["id"], "approve", rule="xs/far", nearest=near()))
        msg = deny(c["id"], "approve", rule="writing/new", nearest=near("writing/a", 0.86))
        check("approve refuses a fact ANOTHER rule already says", "already says" in msg and "writing/a" in msg, msg)
        check("a pass that cannot run blocks approval unless --unchecked says why",
              "--unchecked" in deny(c["id"], "approve", rule="writing/new", nearest=down))
        before = (folder_file.read_bytes(), master.read_bytes())
        deny(c["id"], "approve", rule="writing/new", nearest=near("writing/a", 0.9))
        check("a refused decision changes neither copy", before == (folder_file.read_bytes(), master.read_bytes()))

        d = candidates.decide(root, c["id"], "approve", rule="writing/new", nearest=near("writing/new", 0.97))["candidate"]
        fc, mc = read(folder_file), read(master)
        check("approval is set on the SAME line in both copies", fc[0] == mc[0] and fc[0]["status"] == "approved"
              and len(fc) == len(mc) == 2, (fc[0], mc[0]))
        check("the rule approved INTO is never its own duplicate", d["decided"]["rule"] == "writing/new"
              and d["decided"]["nearest"] == [], d["decided"])
        check("the decision is stamped, with a default reason", d["decided"]["session"] == "test-session-2"
              and d["reason"] == "approved into writing/new", d)
        check("an approved candidate leaves the pending queue", [x["id"] for x in candidates.queue(root)] == [c2["id"]])
        check("deciding it twice is refused", "already approved" in deny(c["id"], "reject", reason="x"))
        check("a rejection needs a reason", "--reason" in deny(c2["id"], "reject"))
        candidates.decide(root, c2["id"], "reject", reason="already folded into writing/new")
        fc, mc = read(folder_file), read(master)
        check("a rejection keeps the candidate, marked, in both copies", fc[1] == mc[1]
              and mc[1]["status"] == "rejected" and mc[1]["reason"] == "already folded into writing/new", mc[1])
        check("an unknown id is refused", "no candidate" in deny("2026-01-01-nope", "reject", reason="x"))

        same = near("xs/fact", 0.75, OLD)
        p4 = candidates.park(root, "reach is measured between collision boxes, not centres", "mech", run=RUN)["candidate"]["id"]
        check("a same-subject rule must be answered", "same subject" in deny(p4, "approve", rule="writing/new", nearest=same))
        check("contradicting a game fact needs --proof",
              "--proof" in deny(p4, "approve", rule="writing/new", nearest=same, contradicts=["xs/fact"]))
        check("--proof must exist", "nothing that exists" in deny(p4, "approve", rule="writing/new", nearest=same,
                                                                  contradicts=["xs/fact"], proof=["mech/nope"]))
        check("the old rule must be corrected first", "still says" in deny(p4, "approve", rule="writing/new",
                                                                           nearest=same, contradicts=["xs/fact"], proof=[RUN]))
        check("work procedure is never contradicted", "WORK PROCEDURE" in deny(
            p4, "approve", rule="writing/new", nearest=near("writing/a", 0.75, "x"), contradicts=["writing/a"], proof=[RUN]))
        fact.write_text("RULE xs/fact - x\n- FALSIFIED: centres were assumed\n- another line entirely\n", encoding="utf-8")
        a = candidates.decide(root, p4, "approve", rule="writing/new", nearest=same, contradicts=["xs/fact"],
                              proof=[RUN])["candidate"]["decided"]
        check("a proven, corrected contradiction approves and is recorded",
              a["contradicts"] == ["xs/fact"] and a["proof"] == [RUN], a)
        p5 = candidates.park(root, "a building container reaches as far as a unit container", "mech", run=RUN)["candidate"]["id"]
        a = candidates.decide(root, p5, "approve", rule="writing/new", nearest=near("xs/fact", 0.72, "x"),
                              agrees=True)["candidate"]["decided"]
        check("--agrees approves and records what it was checked against",
              a.get("agrees") is True and a["checked_against"] == ["xs/fact:2"], a)

        s = candidates.propose_scope(root, "mech", [{"rule": "xs/far.rule.md", "score": 0.76}],
                                     [{"path": "ai/thing.py", "score": 0.72}, {"path": "mech/in.py", "score": 0.9}])
        check("scope proposes a same-subject gate and a near file's folder, never the fact's own",
              [g for g, _ in s["wider"]] == ["ai/**", "other/**"] and not s["niche"], s)
        check("with nothing near, the fact is niche",
              "NICHE" in candidates.render_scope(candidates.propose_scope(root, "mech", [], [])))

        events, problems = upkeep.read_history(root)
        check("everything the commands wrote is valid history", not problems, problems)
        check("the folder and master copies agree", upkeep.candidate_problems(root, events) == [],
              upkeep.candidate_problems(root, events))
        history.set_keys(master, p5, {"status": "pending"})
        probs = upkeep.candidate_problems(root, upkeep.read_history(root)[0])
        check("a status that differs between the copies is reported", any(p5 in p and "master" in p for p in probs), probs)
        old = candidates.park(root, "an old fact nobody ever came back to decide on", "mech", no_run="x",
                              when="2026-08-01")["candidate"]
        cc = upkeep.check_candidates(upkeep.read_history(root)[0], now=datetime.date(2026, 9, 20))
        check("a candidate pending over a week is reported", any(old["id"] in i for i in cc["items"]), cc)
        check("a run entry naming a parked candidate counts as closed", upkeep._closes({"refs": [c["id"]]}, {c["id"]}))
        for name in ("history", "park", "candidates", "decide"):
            check("`%s` is a described command" % name, name in rules.DISPATCH and bool(rules.COMMANDS[name][1]))
    finally:
        history.DATA_BASE = real_base


def test_pipe_in_command_gate(tmp: Path):
    """A `cmd:` regex holding an alternation is one trigger, not cut at its first pipe."""
    print("\ncommand gates with alternation")
    root = tmp / "pipe_repo"
    (root / "rules" / "repo").mkdir(parents=True)
    (root / "rules" / "INDEX.md").write_text(
        "# idx\n\n- **repo/keys.rule.md** | `scenarios/cam/**`, `cmd:pyautogui|keybind|hotkey` | keys\n"
        "- **repo/moves.rule.md** | `cmd:(?i)\\b(mv|move-item)\\b`, `cmd:rules\\.py\\W+move\\b` | moves\n",
        encoding="utf-8")
    for n in ("keys", "moves"):
        (root / "rules" / "repo" / (n + ".rule.md")).write_text("RULE repo/%s - x\n- a line\n" % n, encoding="utf-8")
    raw = lib.raw_gates(root)
    check("an alternation inside a cmd: gate survives parsing",
          ("repo/keys.rule.md", "cmd:pyautogui|keybind|hotkey") in raw, raw)
    check("the path trigger before it is still parsed", ("repo/keys.rule.md", "scenarios/cam/**") in raw, raw)
    check("every alternative matches", all("repo/keys.rule.md" in lib.rules_for_command(root, c)
                                           for c in ("pyautogui.press('a')", "find keybind", "hotkey F3")))
    check("a grouped alternation with flags matches", "repo/moves.rule.md" in lib.rules_for_command(root, "Move-Item a b"))
    check("two cmd: gates on one line are both parsed",
          len([t for r, t in raw if r == "repo/moves.rule.md"]) == 2, raw)
    check("the blurb after ' | ' is never read as a trigger", not any("keys" == t for _, t in raw))


def test_viewer(tmp: Path):
    """The viewer: which project, the tasks format, the page payload, the live server, the snapshot."""
    print("\nproject viewer")
    import json as _json
    import threading
    import urllib.request
    import history
    import tasks
    import viewer

    root = tmp / "view_repo"
    (root / "mech" / "inv" / "pickup").mkdir(parents=True)
    (root / "mech" / "lonely").mkdir(parents=True)
    (root / "rules").mkdir()
    history.add(root, "mech/inv", "note", "a note at the project level")
    history.add(root, "mech/inv/pickup", "finding", "a finding from the pickup subfolder")

    check("a file deep in a project belongs to that project", lib.project_of(root, "mech/inv/pickup/x.py") == "mech/inv")
    check("a folder with no records belongs to no project", lib.project_of(root, "mech/lonely/x.py") is None)
    check("rules/ and .claude/ are never projects", lib.project_of(root, "rules/x.rule.md") is None
          and lib.project_of(root, ".claude/skills/x") is None)

    os.environ["CLAUDE_RULE_STATE_DIR"] = str(tmp / "state")
    lib.note_focus(root, "sess-view", ["mech/lonely/a.py", "mech/inv/pickup/b.py"])
    check("the session's focus is the first touched path inside a project",
          (lib.read_focus("sess-view") or {}).get("project") == "mech/inv")
    check("a named subfolder opens its project", viewer.resolve_project(root, "mech/inv/pickup")[0] == "mech/inv")
    check("run from inside a project, no folder is needed",
          viewer.resolve_project(root, None, root / "mech/inv/pickup", "")[0] == "mech/inv")
    how = viewer.resolve_project(root, None, root, "sess-view")
    check("run from the repo root, the session's focus decides", how == ("mech/inv", "the project this session last worked in"), how)
    try:
        viewer.resolve_project(root, None, root, "no-such-session")
        check("with nothing to go on it asks for a folder and lists projects", False)
    except ValueError as e:
        check("with nothing to go on it asks for a folder and lists projects", "mech/inv" in str(e), e)

    TASKS = ("# 📋 TASKS · mech/inv\n\n**Goal:** make items work end to end.\n\n"
             "- ✅ first thing done · *2026-09-12* `t1`\n"
             "- 🔄 ❓ **the thing in progress** · *since 2026-09-13* `t2`\n"
             "- ⛔ blocked on a data mod rebuild `t3`\n"
             "- 🔜 next one `t4`\n- 🔜 next two `t5`\n- 🔜 next three `t6`\n\n---\n\n## Details\n\n"
             "**t1** · The first thing, now done.\n\n**t2** · What is happening, over\ntwo source lines.\n\n"
             "**t3** · Waiting for the dataset.\n\n**t4** · The next one to do.\n\n**t5** · The one after that.\n\n"
             "**t6** · The third one waiting.\n")
    (root / "mech/inv/.rs/TASKS.md").parent.mkdir(parents=True, exist_ok=True)
    (root / "mech/inv/.rs/TASKS.md").write_text(TASKS, encoding="utf-8")
    p = tasks.parse(TASKS)
    now = [t for t in p["tasks"] if t["status"] == "now"][0]
    check("tasks parse: heading, goal and every status", p["project"] == "mech/inv" and p["goal"].startswith("make items")
          and [t["status"] for t in p["tasks"]] == ["done", "now", "blocked", "next", "next", "next"], p)
    act_line = tasks.parse(TASKS.replace("- ⛔ blocked on", "- ⛔ ❗ blocked on"))
    check("tasks parse: the action mark after the status icon", [t["action"] for t in act_line["tasks"]]
          == [False, False, True, False, False, False] and act_line["tasks"][2]["text"] == "blocked on a data mod rebuild",
          act_line["tasks"])
    check("tasks parse: question, bold, since-date and id", now["question"] and now["bold"] and now["since"]
          and now["date"] == "2026-09-13" and now["id"] == "t2" and now["text"] == "the thing in progress", now)
    check("a details paragraph joins its lines", p["details"]["t2"] == "What is happening, over two source lines.", p["details"])
    check("a file in the frozen format has no problems", p["problems"] == [], p["problems"])
    bad = tasks.parse(TASKS.replace("- ✅ first thing done", "- 🔄 first thing done").replace("**t3** · Waiting for the dataset.\n", "").replace("**t4** · The next one to do.\n", ""))
    check("the check names two tasks in progress, a blocked task with no reason and a task with no paragraph",
          any("2 tasks in progress" in x for x in bad["problems"]) and any("t3 has no details" in x for x in bad["problems"])
          and any("t4 has no details paragraph" in x for x in bad["problems"]), bad["problems"])

    data = viewer.payload(root, "mech/inv")
    check("the payload holds the project's history with each entry's subfolder",
          len(data["history"]) == 2 and {e["_folder"] for e in data["history"]} == {"mech/inv", "mech/inv/pickup"}, data["history"])
    check("the payload holds the parsed tasks", data["tasks"]["goal"].startswith("make items"))
    sig = viewer.signature(root, "mech/inv")
    history.add(root, "mech/inv", "note", "a change the page must notice")
    check("the signature changes when the history does", viewer.signature(root, "mech/inv") != sig)

    page = viewer.build_page({"mode": "static", "data": {"x": "</script><b>"}})
    check("the page inlines its css, js and boot data", "/*CSS*/" not in page and "/*JS*/" not in page
          and "window.VIEW" in page and "--font" in page and "renderEntries" in page)
    check("data cannot close the script tag it is embedded in", "</script><b>" not in page)

    server, start = viewer.make_server(root, "mech/inv", port=0, idle=60, first_wait=60)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = "http://127.0.0.1:%d" % server.server_address[1]
    try:
        html = urllib.request.urlopen(base + "/", timeout=5).read().decode("utf-8")
        live = _json.loads(urllib.request.urlopen(base + "/data", timeout=5).read().decode("utf-8"))
        again = _json.loads(urllib.request.urlopen(base + "/data?sig=" + urllib.request.quote(live["signature"]), timeout=5).read())
        ping = urllib.request.urlopen(base + "/ping", timeout=5).read().decode("utf-8")
        check("the live server serves the page", '"mode": "live"' in html)
        check("and the project's data", live["project"] == "mech/inv" and len(live["history"]) == 3)
        check("and says unchanged when nothing changed, instead of resending", again == {"signature": live["signature"], "unchanged": True}, again)
        check("and answers a ping with its project, so a second view reuses it", ping == "mech/inv")

        import re as _re
        import urllib.error
        import questions as _q
        q = _q.ask(root, "mech/inv", "t2", "which map size should the probe use?")
        token = _re.search(r'"token": "([0-9a-f]+)"', html).group(1)

        def post(body, tok=token):
            req = urllib.request.Request(base + "/answer", data=_json.dumps(body).encode("utf-8"), method="POST",
                                         headers={"Content-Type": "application/json", "X-View-Token": tok})
            try:
                with urllib.request.urlopen(req, timeout=5) as r:
                    return r.status, _json.loads(r.read())
            except urllib.error.HTTPError as e:
                return e.code, e.read()

        check("a reply without the page's token is refused", post({"id": q["id"], "answer": "the small map"}, tok="x")[0] == 403)
        code, body = post({"id": q["id"], "answer": "the small map, it loads faster"})
        check("a reply sent from the page is written as the question's answer", code == 200
              and _q.read(root, "mech/inv")[0].get("answer") == "the small map, it loads faster", (code, body))
        check("a second reply to an answered question is refused with the reason",
              post({"id": q["id"], "answer": "the large map instead"})[0] == 400)
        check("the payload carries the questions for the page",
              _json.loads(urllib.request.urlopen(base + "/data", timeout=5).read())["questions"][0]["id"] == q["id"])
        act = _q.act(root, "mech/inv", "t3", "rebuild the data mod, which only the user can do")
        live = _json.loads(urllib.request.urlopen(base + "/data", timeout=5).read())
        check("the payload marks a task with an open action",
              [k for k in live["tasks"]["tasks"] if k["id"] == "t3"][0]["action"] is True)

        def post_done(body, tok=token):
            req = urllib.request.Request(base + "/done", data=_json.dumps(body).encode("utf-8"), method="POST",
                                         headers={"Content-Type": "application/json", "X-View-Token": tok})
            try:
                with urllib.request.urlopen(req, timeout=5) as r:
                    return r.status, _json.loads(r.read())
            except urllib.error.HTTPError as e:
                return e.code, e.read()

        check("marking an action done without the page's token is refused", post_done({"id": act["id"]}, tok="x")[0] == 403)
        check("an answer sent to an action is refused", post({"id": act["id"], "answer": "done it just now"})[0] == 400)
        code, body = post_done({"id": act["id"], "note": "rebuilt with the new dataset"})
        done = [x for x in _q.read(root, "mech/inv") if x["id"] == act["id"]][0]
        check("marking done from the page writes the time and the note", code == 200 and done.get("done")
              and done.get("note") == "rebuilt with the new dataset", (code, body, done))
        check("marking it done twice is refused", post_done({"id": act["id"]})[0] == 400)
        check("running() finds no viewer for a project that has none", viewer.running(root, "mech/nothing") is None)
    finally:
        server.shutdown()
    snap = viewer.write_static(root, "mech/inv")
    check("--static writes one self-contained snapshot to the temp folder",
          snap.is_file() and '"mode": "static"' in snap.read_text(encoding="utf-8") and "a change the page must notice" in snap.read_text(encoding="utf-8"))
    snap.unlink()


def test_tasks_commands(tmp: Path):
    """init, and every tasks command keeping the file in the frozen format."""
    print("\ntasks commands")
    import history
    import tasks

    root = tmp / "tasks_repo"
    (root / "rules").mkdir(parents=True)
    r = tasks.init(root, "mech/newthing", "make the new thing work")
    base = root / "mech/newthing"
    check("init creates the three files", all((base / ".rs" / m).exists() for m in ("HISTORY.jsonl", "TASKS.md", "QUESTIONS.jsonl")))
    check("and logs the project's start", r["entry"]["title"] == "project started: make the new thing work")
    p = tasks.load(root, "mech/newthing")
    check("a fresh TASKS.md is in format, with its goal and no tasks", p["goal"] == "make the new thing work"
          and p["tasks"] == [] and p["problems"] == [], p)

    def refused(fn, *a, **k):
        try:
            fn(*a, **k)
            return ""
        except ValueError as e:
            return str(e)

    check("a sub-project must name the parent task it serves", "--task" in refused(tasks.init, root, "mech/newthing/sub", "a goal for the sub-project"))
    check("init refuses a folder that already has the files", "already has" in refused(tasks.init, root, "mech/newthing", "a goal here"))
    check("init refuses rules/", bool(refused(tasks.init, root, "rules/x", "a goal here")))

    check("add refuses a task without its paragraph", "--details" in refused(tasks.add, root, "mech/newthing", "a task with no paragraph"))
    a = tasks.add(root, "mech/newthing", "build the first scenario", details="the fixture map and the probe, built and compiling")
    check("the first task added starts at once", a["id"] == "t1" and tasks.load(root, "mech/newthing")["tasks"][0]["status"] == "now")
    for n in range(2, 7):
        tasks.add(root, "mech/newthing", "task number %d to do" % n, details="what task %d is for, and what done means" % n)
    check("a sixth not-started task is accepted: the window has no cap", not refused(tasks.add, root, "mech/newthing", "a sixth task, which fits", details="a paragraph for a task past the old cap of five"))
    p = tasks.load(root, "mech/newthing")
    check("the window is in format after adds", p["problems"] == [], p["problems"])

    tasks.detail(root, "mech/newthing", "t1", "building the fixture map first, then the probe")
    s = tasks.start(root, "mech/newthing", "t3")
    p = tasks.load(root, "mech/newthing")
    check("start switches the task in progress, the old one goes back to not started",
          [k["status"] for k in p["tasks"] if k["id"] in ("t1", "t3")] == ["now", "next"][::-1] or
          ({k["id"]: k["status"] for k in p["tasks"]}["t3"] == "now" and {k["id"]: k["status"] for k in p["tasks"]}["t1"] == "next"), p["tasks"])
    tasks.start(root, "mech/newthing", "t1")

    d = tasks.done(root, "mech/newthing", result="the scenario builds")
    entry = [e for e in history.entries(root, "mech/newthing") if e.get("task") == "t1"]
    check("done logs the task in history at once, keyed by its id", len(entry) == 1 and entry[0]["result"] == "the scenario builds", entry)
    check("done starts the next task", d["started"] and d["started"]["status"] == "now")
    check("a done task keeps its paragraph while it is in the window", "t1" in tasks.load(root, "mech/newthing")["details"])
    check("an empty paragraph is refused, every task keeps one", bool(refused(tasks.detail, root, "mech/newthing", d["started"]["id"], "")))
    tasks.done(root, "mech/newthing")
    tasks.done(root, "mech/newthing")
    p = tasks.load(root, "mech/newthing")
    done_ids = [k["id"] for k in p["tasks"] if k["status"] == "done"]
    check("only the two newest done tasks stay in the window", len(done_ids) == 2 and "t1" not in done_ids, done_ids)
    check("a task that left the window is still in history", any(e.get("task") == "t1" for e in history.entries(root, "mech/newthing")))
    check("details of a task that left the window go with it", "t1" not in p["details"], p["details"])

    now = [k for k in p["tasks"] if k["status"] == "now"][0]
    para = p["details"][now["id"]]
    b = tasks.block(root, "mech/newthing", now["id"], "waiting for the data mod rebuild")
    p = tasks.load(root, "mech/newthing")
    check("blocking the task in progress starts the next one", b["started"] is not None)
    check("the block reason goes in front of its paragraph, which stays",
          p["details"][now["id"]] == "Blocked: waiting for the data mod rebuild · " + para, p["details"])
    tasks.detail(root, "mech/newthing", now["id"], "a rewritten paragraph for the blocked task")
    check("rewriting a blocked task's paragraph keeps the reason in front",
          tasks.load(root, "mech/newthing")["details"][now["id"]] == "Blocked: waiting for the data mod rebuild · a rewritten paragraph for the blocked task",
          tasks.load(root, "mech/newthing")["details"])
    check("a block needs a reason", "--reason" in refused(tasks.block, root, "mech/newthing", b["started"]["id"], ""))
    tasks.unblock(root, "mech/newthing", now["id"])
    check("unblock returns it to not started", {k["id"]: k["status"] for k in tasks.load(root, "mech/newthing")["tasks"]}[now["id"]] == "next")
    check("unblock takes the reason off and keeps the paragraph",
          tasks.load(root, "mech/newthing")["details"][now["id"]] == "a rewritten paragraph for the blocked task")
    extra = [tasks.add(root, "mech/newthing", "a queued task number %d" % i, details="only here to test where unblock places a task")["id"]
             for i in (1, 2)]
    nexts = lambda: [k["id"] for k in sorted(tasks.load(root, "mech/newthing")["tasks"], key=lambda k: tasks.RANK[k["status"]])
                     if k["status"] == "next"]
    tasks.block(root, "mech/newthing", extra[0], "waiting only for this check")
    tasks.unblock(root, "mech/newthing", extra[0], at=99)
    check("unblock --at past the end puts the task last among the not-started", nexts()[-1] == extra[0], nexts())
    tasks.block(root, "mech/newthing", extra[0], "waiting only for this check")
    tasks.unblock(root, "mech/newthing", extra[0], at=1)
    check("unblock --at 1 puts it first among the not-started", nexts()[0] == extra[0], nexts())
    for tid in extra:
        tasks.drop(root, "mech/newthing", tid, "only here to test unblock --at")
    tasks.add(root, "mech/newthing", "a task that turns out not to be needed", details="kept only to be dropped by the next check")
    last = tasks.load(root, "mech/newthing")["tasks"][-1]["id"]
    dr = tasks.drop(root, "mech/newthing", last, "superseded by the new plan")
    check("drop removes it and records why in history", dr["entry"]["kind"] == "decision"
          and last not in [k["id"] for k in tasks.load(root, "mech/newthing")["tasks"]])
    check("ids are never reused, even after tasks leave", tasks.next_id(root, "mech/newthing", tasks.load(root, "mech/newthing")) == "t%d" % (int(last[1:]) + 1))
    check("details are one short paragraph", "one short paragraph" in refused(tasks.detail, root, "mech/newthing", "t2", "x" * 600))
    tasks.set_goal(root, "mech/newthing", "make the new thing work end to end")
    p = tasks.load(root, "mech/newthing")
    check("render and parse round-trip without problems", tasks.parse(tasks.render(p))["tasks"] == p["tasks"] and p["problems"] == [], p["problems"])
    check("show lists the window with its goal", "goal: make the new thing work end to end" in tasks.show(root, "mech/newthing"))

    import questions
    proj = "mech/newthing"
    now = [k for k in tasks.load(root, proj)["tasks"] if k["status"] == "now"][0]["id"]
    check("a question needs a task in the window", "no task" in refused(questions.ask, root, proj, "t99", "is this the right map size?"))
    q = questions.ask(root, proj, now, "should the probe use the small or the large map?")
    check("ask writes a numbered question tied to its task", q["id"] == "q1" and q["task"] == now)
    raw = (root / proj / ".rs" / "TASKS.md").read_text(encoding="utf-8")
    check("the task line shows the question mark while it is unanswered", "❓" in raw, raw)
    check("the folder state counts the open question", "1 open for the user" in history.folder_state(root, proj))
    check("answers with nothing answered consumes nothing", questions.consume(root, proj) == []
          and len(questions.read(root, proj)) == 1)
    questions.answer(root, proj, "q1", "the small map, it loads in half the time")
    check("an answer is refused twice", "already answered" in refused(questions.answer, root, proj, "q1", "the large map after all"))
    check("an answered question takes the question mark off", "❓" not in (root / proj / ".rs" / "TASKS.md").read_text(encoding="utf-8"))
    check("the folder state says an answer is waiting", "1 answered, waiting" in history.folder_state(root, proj))
    got = questions.consume(root, proj)
    dec = [e for e in history.entries(root, proj) if e.get("question") == "q1"]
    check("answers logs each answer as a decision keyed by question and task", len(got) == 1 and len(dec) == 1
          and dec[0]["kind"] == "decision" and dec[0]["task"] == now and "the small map" in dec[0]["what"], dec)
    check("and removes it from the file", questions.read(root, proj) == [])
    check("question ids are never reused once consumed", questions.next_qid(root, proj) == "q2")
    q2 = questions.ask(root, proj, now, "is one run per arm enough here?")
    questions.answer(root, proj, q2["id"], "yes, one run per arm is enough")
    real_remove = questions._remove
    questions._remove = lambda *a: (_ for _ in ()).throw(OSError("disk went away"))
    refused_io = ""
    try:
        questions.consume(root, proj)
    except OSError as e:
        refused_io = str(e)
    questions._remove = real_remove
    questions.consume(root, proj)
    check("a consume interrupted after logging is not logged twice when repeated", bool(refused_io)
          and len([e for e in history.entries(root, proj) if e.get("question") == q2["id"]]) == 1
          and questions.read(root, proj) == [])
    qw = questions.ask(root, proj, now, "a question whose premise turns out false?")
    check("withdraw needs a reason", "reason" in refused(questions.withdraw, root, proj, qw["id"], ""))
    w = questions.withdraw(root, proj, qw["id"], "its premise turned out false")
    check("withdraw logs the question and why, then removes it", w["entry"]["kind"] == "note"
          and w["entry"]["question"] == qw["id"] and all(q["id"] != qw["id"] for q in questions.read(root, proj)))
    check("wait returns at the timeout when nothing is answered",
          questions.wait(root, proj, timeout=0.1, interval=0.05) == [])
    q3 = questions.ask(root, proj, now, "does the wait command see this answer?")
    questions.answer(root, proj, q3["id"], "yes, it returns at once")
    check("wait returns at once when an answer is waiting",
          [q["id"] for q in questions.wait(root, proj, timeout=5)] == [q3["id"]])
    questions.consume(root, proj)

    # actions: something only the user can do, marked ❗ until the user marks it done (the user, 2026-09-15)
    check("an action needs a task in the window", "no task" in refused(questions.act, root, proj, "t99", "log in to GitHub once"))
    a = questions.act(root, proj, now, "run gh auth login once in a terminal")
    check("act writes a numbered action tied to its task", a["id"] == "a1" and a["task"] == now and a["kind"] == "action")
    raw = (root / proj / ".rs" / "TASKS.md").read_text(encoding="utf-8")
    check("the task line shows the exclamation mark while the action is open", "❗" in raw and "❓" not in raw, raw)
    check("the parsed window carries the action mark", [k for k in tasks.load(root, proj)["tasks"] if k["id"] == now][0]["action"])
    check("the folder state counts the open action", "1 action for the user" in history.folder_state(root, proj))
    check("an action is not answered like a question", "is an action" in refused(questions.answer, root, proj, a["id"], "done it now"))
    check("a question is not marked done like an action", "is a question" in refused(
        questions.acted, root, proj, questions.ask(root, proj, now, "which of the two maps loads faster?")["id"]))
    both = (root / proj / ".rs" / "TASKS.md").read_text(encoding="utf-8")
    check("a task can carry both marks, question first", "❓ ❗" in both, both)
    check("render and parse round-trip with both marks", tasks.parse(tasks.render(tasks.load(root, proj)))["tasks"]
          == tasks.load(root, proj)["tasks"])
    questions.withdraw(root, proj, [q for q in questions.read(root, proj) if not questions.is_action(q)][0]["id"],
                       "only here to test the two marks together")
    check("wait does not return for an action still open", questions.wait(root, proj, timeout=0.1, interval=0.05) == [])
    questions.acted(root, proj, a["id"], "logged in as the repo owner")
    check("acted is refused twice", "already done" in refused(questions.acted, root, proj, a["id"]))
    check("a done action takes the exclamation mark off", "❗" not in (root / proj / ".rs" / "TASKS.md").read_text(encoding="utf-8"))
    check("wait returns at once when an action is done", [x["id"] for x in questions.wait(root, proj, timeout=5)] == [a["id"]])
    got = questions.consume(root, proj)
    note = [e for e in history.entries(root, proj) if e.get("action") == a["id"]]
    check("answers logs a done action as a note keyed by action and task, with the user's note",
          len(got) == 1 and got[0]["action"]["id"] == a["id"] and len(note) == 1 and note[0]["kind"] == "note"
          and note[0]["task"] == now and "logged in as the repo owner" in note[0]["what"], note)
    check("and removes it from the file", questions.read(root, proj) == [])
    check("action ids are never reused once consumed", questions.next_aid(root, proj) == "a2")
    aw = questions.act(root, proj, now, "an action that turns out not to be needed")
    w = questions.withdraw(root, proj, aw["id"], "the instance could do it after all")
    check("withdraw takes back an open action and logs why", w["entry"]["action"] == aw["id"]
          and "Withdrawn because" in w["entry"]["what"] and questions.read(root, proj) == [])


def test_review_fixes(tmp: Path):
    """Regressions from the 2026-09-13 fresh-instance review, one check per finding."""
    print("\nreview fixes")
    import candidates
    import history
    import tasks
    import upkeep
    import viewer

    root = tmp / "review_repo"
    (root / "mech" / "a").mkdir(parents=True)
    (root / "rules").mkdir()
    (root / ".claude").mkdir()

    def err(fn, *a, **k):
        try:
            fn(*a, **k)
            return ""
        except ValueError as e:
            return str(e)

    for bad in ("..", "mechanics/../.claude", ".Claude", "Rules", "../elsewhere"):
        check("history add refuses the folder %r" % bad, bool(err(history.add, root, bad, "note", "a note here")))
    other = tmp / "rootlog_repo"
    other.mkdir()
    history.add(other, ".", "note", "a note for the whole repository")
    check("the repo root may keep a history of its own (the user, 2026-09-14)", (other / ".rs" / "HISTORY.jsonl").is_file())
    check("no history file was written outside the repo", not (tmp / ".rs" / "HISTORY.jsonl").exists())
    check("--numbers refuses NaN and infinity", "finite" in err(history.add, root, "mech", "note", "a note here", numbers=["x=nan"])
          and "finite" in err(history.add, root, "mech", "note", "a note here", numbers=["x=inf"]))

    (root / "mech" / "b").mkdir()
    history.add(root, "mech/a", "note", "a note in a", when="2026-08-01")
    same = json.loads([l for l in (root / "mech/a/.rs/HISTORY.jsonl").read_text(encoding="utf-8").splitlines()][0])
    (root / "mech/b/.rs/HISTORY.jsonl").parent.mkdir(parents=True, exist_ok=True)
    (root / "mech/b/.rs/HISTORY.jsonl").write_text(json.dumps(same) + "\n", encoding="utf-8")
    check("merge refuses an id that two source files share", "appears in both" in err(history.merge, root, "mech"))

    p = root / "mech/mixed.jsonl"
    p.write_bytes(b'{"id": "one", "kind": "note"}\r\n{"id": "two", "kind": "note"}\n{"id": "three"}\r\n')
    history.set_keys(p, "two", {"status": "closed"})
    raw = p.read_bytes()
    check("set_keys finds a line in a file with mixed line endings, and keeps each ending",
          b'"status": "closed"}\n{"id": "three"}\r\n' in raw and raw.startswith(b'{"id": "one", "kind": "note"}\r\n'), raw)

    t = root / "mech/.rs/TASKS.md"
    tasks.init(root, "proj", "a goal for the project")
    tp = root / "proj/.rs/TASKS.md"
    legacy = tp.read_text(encoding="utf-8").replace("## Details", "- [ ] an old checkbox task\n\nsome prose\n\n## Details")
    tp.write_text(legacy, encoding="utf-8")
    check("a tasks write refuses a file whose lines the format cannot keep", "cannot keep" in err(tasks.add, root, "proj", "a new task", details="a paragraph for the new task"))
    check("and leaves the file as it was", tp.read_text(encoding="utf-8") == legacy)

    run = root / "test_runs/s/runs/s_20260913-100000"
    run.mkdir(parents=True)
    check("proof must be a run folder or an entry, not any path",
          not candidates._proof_exists(root, ".", []) and not candidates._proof_exists(root, "rules", [])
          and candidates._proof_exists(root, run.relative_to(root).as_posix(), []))

    real = history.DATA_BASE
    history.DATA_BASE = tmp / "review_data"
    try:
        folder_file = history.history_file_for(root, "mech/a")
        before = folder_file.read_bytes()
        orig = history.append_line
        calls = {"n": 0}

        def failing(path, record):
            calls["n"] += 1
            if calls["n"] == 2:
                raise OSError("the sync client held the file")
            orig(path, record)
        history.append_line = failing
        try:
            candidates.park(root, "a fact long enough to be parked in two places", "mech/a", no_run="x")
            check("a failed second write of a candidate rolls the first back", False)
        except OSError:
            check("a failed second write of a candidate rolls the first back", folder_file.read_bytes() == before)
        finally:
            history.append_line = orig
        master = history.master_path(root)
        master.parent.mkdir(parents=True, exist_ok=True)
        master.write_text("[1, 2]\n", encoding="utf-8")
        check("upkeep reports a master line that is not a candidate", any("not a candidate" in x for x in upkeep.candidate_problems(root, [])))
        (root / "mech/a/.rs/TASKS.md").parent.mkdir(parents=True, exist_ok=True)
        (root / "mech/a/.rs/TASKS.md").write_text("", encoding="utf-8")
        check("the viewer payload skips a master line that is not an object", viewer.payload(root, "mech/a")["candidates"] == [])
    finally:
        history.DATA_BASE = real

    import threading
    import urllib.request
    import urllib.error
    server, _ = viewer.make_server(root, "mech/a", port=0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    port = server.server_address[1]
    try:
        req = urllib.request.Request("http://127.0.0.1:%d/data" % port, headers={"Host": "evil.example:%d" % port})
        try:
            urllib.request.urlopen(req, timeout=5)
            check("the viewer refuses a request for another host name", False)
        except urllib.error.HTTPError as e:
            check("the viewer refuses a request for another host name", e.code == 403, e.code)
        check("and still serves its own", urllib.request.urlopen("http://127.0.0.1:%d/ping" % port, timeout=5).read() == b"mech/a")
    finally:
        server.shutdown()


def test_scope():
    """--repo names the rule ecosystem; candidate commands refuse to guess it."""
    print("\nrepo scoping")
    import contextlib
    import io
    import rules

    import os as _os
    import tempfile as _tf
    # never read the real session's `use` choice: a test run must not depend on what the session chose
    st = Path(_tf.mkdtemp(prefix="use_state_"))
    _os.environ["CLAUDE_RULE_STATE_DIR"] = str(st)
    _os.environ.pop("CLAUDE_CODE_CHILD_SESSION", None)
    project = rules.project_root()
    root, rest = rules._scope(["--repo", project.name, "x"])
    check("--repo <this repository's name> is this repository", root == project and rest == ["x"], (root, rest))
    check("a history command without --repo defaults to this repository", rules._scope(["x"])[0] == project)
    for args, why in ((["x"], "a candidate command with no --repo"),
                      (["--repo", "../elsewhere"], "a folder outside the repository"),
                      (["--repo", "no-such-folder-here"], "a folder that does not exist")):
        try:
            rules._scope(args, required=True)
            check("--repo refuses %s" % why, False)
        except ValueError:
            check("--repo refuses %s" % why, True)
    saved_sid = _os.environ.get("CLAUDE_CODE_SESSION_ID")
    _os.environ["CLAUDE_CODE_SESSION_ID"] = "use-test-1"
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            rc = rules.main(["use", "no-such-folder-here"])
        check("use refuses a rule set that does not exist", rc == 2)
        with contextlib.redirect_stdout(io.StringIO()):
            rc = rules.main(["use", project.name])
        check("use remembers the session's rule set", rc == 0 and (rules.read_use() or {}).get("ecosystem") == project.name)
        check("and every later command works on it with no --repo", rules._scope(["x"])[0] == project)
        check("a candidate command needs no --repo once the session has chosen", rules._scope(["x"], required=True)[0] == project)
        _os.environ["CLAUDE_CODE_SESSION_ID"] = "use-test-2"
        check("another session does not see this session's choice", rules.read_use() is None)
        _os.environ["CLAUDE_CODE_SESSION_ID"] = "use-test-1"
        with contextlib.redirect_stdout(io.StringIO()):
            rules.main(["use", "--clear"])
        check("use --clear forgets the choice", rules.read_use() is None)

        # nesting: a working folder inside a nested rule set outranks the session's choice
        fake = Path(_tf.mkdtemp(prefix="eco_")) / "proj"
        for d in ("rules", "adapt/rules", "adapt/agents/x/rules", "adapt/agents/x/work"):
            (fake / d).mkdir(parents=True)
        real_root, real_cwd = rules.project_root, _os.getcwd()
        try:
            rules.project_root = lambda: fake
            _os.chdir(fake / "adapt" / "agents" / "x" / "work")
            check("the working folder's nearest rule set is found by walking up",
                  rules._from_cwd(fake) == (fake / "adapt" / "agents" / "x").resolve())
            with contextlib.redirect_stdout(io.StringIO()):
                rules.main(["use", "adapt"])
            check("a sub-agent in its home folder gets its own rule set, ahead of the session's use",
                  rules._scope(["x"])[0] == (fake / "adapt" / "agents" / "x").resolve())
            _os.chdir(fake)
            check("at the repository root the session's use applies", rules._scope(["x"])[0] == (fake / "adapt").resolve())
            check("and --repo on the command outranks both", rules._scope(["--repo", "proj", "x"])[0] == fake)
            with contextlib.redirect_stdout(io.StringIO()):
                rules.main(["use", "--clear"])
        finally:
            rules.project_root = real_root
            _os.chdir(real_cwd)
            shutil.rmtree(fake.parent, ignore_errors=True)
    finally:
        if saved_sid is None:
            _os.environ.pop("CLAUDE_CODE_SESSION_ID", None)
        else:
            _os.environ["CLAUDE_CODE_SESSION_ID"] = saved_sid
    with contextlib.redirect_stdout(io.StringIO()) as out:
        rc = rules.main(["budget", "--repo", project.name])
    check("every command takes --repo: budget reads it instead of mistaking it for an argument",
          rc != 2 and "rules," in out.getvalue(), out.getvalue()[-200:])
    with contextlib.redirect_stdout(io.StringIO()) as out:
        rc = rules.main(["list", "--repo", "no-such-folder-here"])
    check("a command given a bad --repo stops and says so", rc == 2 and "no such folder" in out.getvalue(), out.getvalue())
    real_scope = rules._scope
    try:
        rules._scope = lambda a, required=False: (project / ".claude", [x for x in a if x != "--repo"])
        with contextlib.redirect_stdout(io.StringIO()) as out:
            rc = rules.main(["stats", "--repo", ".claude"])
        check("a command that reads this repository's own data refuses another ecosystem by name",
              rc == 2 and "own rules only" in out.getvalue(), out.getvalue())
    finally:
        rules._scope = real_scope
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = rules.cmd_candidates(project, [])
    check("candidates without --repo says what to pass", rc == 2 and "--repo " + project.name in buf.getvalue(),
          buf.getvalue())


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="rules_test_"))
    try:
        root = tmp / "repo"
        root.mkdir()
        build_repo(root)
        test_glob()
        test_discovery(root)
        test_gates(root)
        test_matches(root)
        test_tool_extraction(root)
        test_budget(root)
        test_readme_scan(root)
        test_session_memory()
        test_firing_log(root)
        test_refactor_commands(root)
        test_move(root)
        test_accepted(root)
        test_upkeep(tmp)
        test_project_upkeep(tmp)
        test_root_and_parent(tmp)
        test_candidates(tmp)
        test_history(tmp)
        test_project_history(tmp)
        test_pipe_in_command_gate(tmp)
        test_viewer(tmp)
        test_tasks_commands(tmp)
        test_review_fixes(tmp)
        test_scope()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print(f"\n{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
