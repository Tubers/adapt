"""Self-test: the rules-system skill as installed in this project.

    python Adapt/selftest/rules-system/test_rules_system.py [--quick]

Sections: install integrity, rule health, the safeguards its hooks promise, a full workflow in a clone
(project, tasks, history, questions, the session's rule set, a rule candidate, upkeep, the viewer), and
the skill's own suites. --quick skips the skill's own suites.
"""

import json
import re
import shutil
import sys
import threading
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _common import (ROOT, Suite, cli, clone, context, decision, hook, registered, settings,  # noqa: E402
                     temp_dir)

RS = ("rules-system", "rules.py")
HOOKS_EXPECTED = {   # hook file: (event, a tool its matcher must include)
    "rule_router.py": ("PreToolUse", "Read"),
    "guard_records.py": ("PreToolUse", "Read"),
    "guard_docs.py": ("PreToolUse", "Write"),
    "ask_rule_approval.py": ("PreToolUse", "Edit"),
    "post_write_checks.py": ("PostToolUse", "Write"),
}


def integrity(s):
    s.section("install integrity")
    base = ROOT / ".claude" / "skills" / "rules-system"
    for f in ("SKILL.md", "scripts/rules.py", "scripts/rules_lib.py", "scripts/history.py", "scripts/tasks.py",
              "scripts/questions.py", "scripts/candidates.py", "scripts/upkeep.py", "scripts/viewer.py",
              "scripts/reconcile.py", "scripts/sync_index.py", "scripts/accepted.py", "scripts/audit_worklist.py",
              "scripts/run_tests.py", "web/view.html", "web/view.css", "web/view.js"):
        s.check("skill file present: " + f, (base / f).is_file())
    st = settings()
    for h, (event, tool) in HOOKS_EXPECTED.items():
        where = registered(ROOT, h)
        s.check("%s is registered on %s for %s" % (h, event, tool),
                any(e == event and tool in m.split("|") for e, m in where), where)
        s.check("%s exists where settings point" % h, (ROOT / ".claude" / "hooks" / h).is_file())
    s.check("hooks import the skill through _bootstrap.py", (ROOT / ".claude" / "hooks" / "_bootstrap.py").is_file())
    s.check("rules-system is visible to instances by name", st.get("skillOverrides", {}).get("rules-system") == "name-only")
    deny = st.get("permissions", {}).get("deny", [])
    s.check("settings deny editing any CLAUDE.md, in the Edit() form Claude Code honours for every file tool",
            "Edit(**/CLAUDE.md)" in deny and not any(d.startswith("Write(") for d in deny), deny)
    s.check("the output style is caveman", st.get("outputStyle") == "caveman")
    style = ROOT / ".claude" / "output-styles" / "caveman.md"
    s.check("the caveman output style defaults to ultra", style.is_file() and "**ultra**" in style.read_text(encoding="utf-8"))
    stray = [p for p in ROOT.rglob("CLAUDE*.md") if "selftest" not in p.parts]
    s.check("no CLAUDE.md of any kind anywhere in the project", not stray, stray)
    s.check("rules live in rules/, never the auto-loaded .claude/rules/",
            (ROOT / "rules" / "INDEX.md").is_file() and not (ROOT / ".claude" / "rules").exists())
    data = base / "data"
    foreign = [d.name for d in data.iterdir() if d.is_dir() and d.name != ROOT.name] if data.is_dir() else []
    s.check("the skill's data holds this project's records only, nothing migrated from elsewhere", not foreign, foreign)


def rule_health(s, state):
    s.section("rule health")
    rc, out = cli(ROOT, RS, ["budget"], state)
    s.check("every rule is within 10 lines and 2048 bytes", "0 over budget" in out, out[-200:])
    rc, out = cli(ROOT, RS, ["reconcile"], state)
    s.check("reconcile is clean: no dead gate, orphan rule or missing rule", out.strip().endswith("clean."), out[-400:])
    sys.path.insert(0, str(ROOT / ".claude" / "skills" / "rules-system" / "scripts"))
    import rules_lib as lib
    gated = {g.rule for g in lib.load_gates(ROOT)}
    s.check("every rule on disk has a gate", set(lib.all_rules(ROOT)) <= gated, set(lib.all_rules(ROOT)) - gated)
    rc, out = cli(ROOT, RS, ["which", "Adapt/TASKS.md"], state)
    s.check("a TASKS.md path pulls in writing/tasks", "rules/writing/tasks.rule.md" in out, out)
    rc, out = cli(ROOT, RS, ["which", ".claude/skills/rules-system/SKILL.md"], state)
    s.check("nothing ever fires inside a skill", "NOTHING" in out, out)


def safeguards(s, state):
    s.section("safeguards, on the real project (read-only)")
    rules_py = "python .claude/skills/rules-system/scripts/rules.py"
    obj, _ = hook(ROOT, "guard_records.py", {"tool_name": "Read", "tool_input": {"file_path": str(ROOT / "Adapt" / "HISTORY.jsonl")}}, state)
    s.check("a direct Read of a project history is refused", decision(obj) == "deny")
    obj, _ = hook(ROOT, "guard_records.py", {"tool_name": "Bash", "tool_input": {"command": "cat Adapt/TA" + "SKS.md"}}, state)
    s.check("a shell read of a task window is refused", decision(obj) == "deny")
    obj, raw = hook(ROOT, "guard_records.py", {"tool_name": "Bash", "tool_input": {"command": rules_py + " tasks --in Adapt"}}, state)
    s.check("the tasks command itself is allowed", raw == "", raw[:200])
    obj, _ = hook(ROOT, "guard_records.py", {"tool_name": "Glob", "tool_input": {"pattern": "**/HIST*.jsonl"}}, state)
    s.check("a Glob spelling out a record's name is refused", decision(obj) == "deny")
    obj, _ = hook(ROOT, "guard_docs.py", {"tool_name": "Write", "tool_input": {"file_path": str(ROOT / "CLAUDE.md"), "content": "x"}}, state)
    s.check("writing a CLAUDE.md is refused", decision(obj) == "deny")
    obj, raw = hook(ROOT, "guard_docs.py", {"tool_name": "Write", "tool_input": {"file_path": str(ROOT / "newfolder" / "README.md"), "content": "x"}}, state)
    s.check("writing a NEW README is allowed", decision(obj) != "deny", raw[:200])
    obj, _ = hook(ROOT, "ask_rule_approval.py", {"tool_name": "Write", "tool_input": {"file_path": str(ROOT / "rules" / "zz" / "selftest-new.rule.md"), "content": "RULE zz/selftest-new - x\n- y\n"}}, state)
    s.check("a new rule asks the user first", decision(obj) == "ask" and "NEW RULE" in json.dumps(obj), json.dumps(obj)[:200])
    obj, _ = hook(ROOT, "ask_rule_approval.py", {"tool_name": "Bash", "tool_input": {"command": rules_py + " decide c-1 approve --rule writing/tasks"}}, state)
    s.check("approving a candidate asks the user first", decision(obj) == "ask")
    obj, _ = hook(ROOT, "rule_router.py", {"tool_name": "Read", "session_id": "st-router-1", "tool_input": {"file_path": str(ROOT / "Adapt" / "README.md")}}, state)
    s.check("touching a gated path injects its rules", "PROJECT RULES" in context(obj), context(obj)[:120])
    obj2, raw2 = hook(ROOT, "rule_router.py", {"tool_name": "Read", "session_id": "st-router-1", "tool_input": {"file_path": str(ROOT / "Adapt" / "README.md")}}, state)
    s.check("and never twice in one session", "PROJECT RULES" not in context(obj2))
    obj, _ = hook(ROOT, "rule_router.py", {"tool_name": "Bash", "session_id": "st-router-2", "tool_input": {"command": rules_py + " view"}}, state)
    s.check("running the viewer brings in the rule that says to open it silently", "say NOTHING" in context(obj), context(obj)[:200])
    obj, raw = hook(ROOT, "rule_router.py", {"tool_name": "Read", "session_id": "st-router-3", "tool_input": {"file_path": str(ROOT / ".claude" / "skills" / "rules-system" / "SKILL.md")}}, state)
    s.check("reading a skill's own file injects nothing", "PROJECT RULES" not in context(obj))


def workflow(s, tmp, state):
    s.section("workflow, in a throwaway clone")
    root = clone(tmp)
    name = root.name
    rc, out = cli(root, RS, ["init", "demo", "--goal", "prove the rule system works end to end"], state)
    s.check("init starts a project with its three files", rc == 0 and all((root / "demo" / f).is_file()
            for f in ("HISTORY.jsonl", "TASKS.md", "QUESTIONS.jsonl")), out[-300:])
    rc, out = cli(root, RS, ["tasks", "--in", "demo", "add", "a task with no paragraph"], state)
    s.check("a task without its paragraph is refused", rc == 2 and "--details" in out, out[-200:])
    cli(root, RS, ["tasks", "--in", "demo", "add", "write the first thing", "--details", "what the first thing is for and what done means"], state)
    cli(root, RS, ["tasks", "--in", "demo", "add", "write the second thing", "--details", "what the second thing is for and what done means"], state)
    rc, out = cli(root, RS, ["tasks", "--in", "demo"], state)
    s.check("the first task starts at once and the window is in format", "t1" in out and "problems" not in out, out[-400:])
    rc, out = cli(root, RS, ["tasks", "--in", "demo", "done", "t1", "--result", "the first thing is written", "--no-rule", "a selftest"], state)
    s.check("done logs the task in history and starts the next", rc == 0 and "started t2" in out, out[-300:])
    rc, out = cli(root, RS, ["history", "demo", "--all"], state)
    s.check("history shows the finished task", "write the first thing" in out, out[-400:])
    rc, out = cli(root, RS, ["history", "add", "demo", "--kind", "finding", "--title", "a finding from the selftest", "--result", "it holds", "--no-rule", "a selftest"], state)
    s.check("history add writes a stamped entry", rc == 0 and "logged" in out, out[-200:])
    rc, out = cli(root, RS, ["tasks", "--in", "demo", "ask", "t2", "is the second thing worth doing at all?"], state)
    s.check("a question is asked on its task", rc == 0 and "asked q1" in out, out[-200:])
    rc, out = cli(root, RS, ["tasks", "--in", "demo", "answer", "q1", "yes, it is the point of the demo"], state)
    rc, out = cli(root, RS, ["tasks", "--in", "demo", "answers"], state)
    s.check("reading the answer consumes it into a history decision", "logged as" in out and "yes, it is the point" in out, out[-300:])
    rc, out = cli(root, RS, ["use", "demo"], state)
    s.check("use refuses a folder that keeps no rules of its own", rc == 2, out[-200:])
    rc, out = cli(root, RS, ["use", name], state)
    s.check("use remembers this project's rule set for the session", rc == 0 and "now uses" in out, out[-200:])
    rc, out = cli(root, RS, ["use"], state)
    s.check("and says so when asked", name in out, out[-200:])
    cli(root, RS, ["use", "--clear"], state)
    rc, out = cli(root, RS, ["park", "a selftest fact long enough to be parked as a candidate", "--repo", name,
                             "--in", "demo", "--no-run", "a selftest"], state)
    m = re.search(r"\b(20\d\d-\d\d-\d\d-[a-z0-9-]+)", out)
    s.check("park records a pending candidate", rc == 0 and m is not None, out[-400:])
    if m:
        rc, out = cli(root, RS, ["candidates", "--repo", name], state)
        s.check("the candidate queue lists it", m.group(1) in out, out[-300:])
        rc, out = cli(root, RS, ["decide", m.group(1), "reject", "--repo", name, "--reason", "only a selftest"], state)
        s.check("decide rejects it in both copies", rc == 0 and "rejected" in out.lower(), out[-300:])
    rc, out = cli(root, RS, ["upkeep"], state)
    s.check("upkeep runs and finds no broken project", "PROJECT" not in out, out[-400:])
    rc, out = cli(root, RS, ["tasks", "--in", "demo", "ask", "t2", "does the viewer take this answer?"], state)
    sys.path.insert(0, str(root / ".claude" / "skills" / "rules-system" / "scripts"))
    import viewer
    server, _start = viewer.make_server(root, "demo", port=0, idle=60, first_wait=60)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = "http://127.0.0.1:%d" % server.server_address[1]
    try:
        page = urllib.request.urlopen(base + "/", timeout=10).read().decode("utf-8")
        data = json.loads(urllib.request.urlopen(base + "/data", timeout=10).read().decode("utf-8"))
        s.check("the viewer serves the project's tasks, history and questions",
                data["project"] == "demo" and data["tasks"] and data["questions"], list(data))
        token = re.search(r'"token": "([0-9a-f]+)"', page).group(1)
        req = urllib.request.Request(base + "/answer", method="POST",
                                     data=json.dumps({"id": "q2", "answer": "yes, the viewer took it"}).encode("utf-8"),
                                     headers={"Content-Type": "application/json", "X-View-Token": token})
        ok = urllib.request.urlopen(req, timeout=10).status == 200
        s.check("an answer sent from the viewer page is written", ok)
    finally:
        server.shutdown()
    obj, _ = hook(root, "post_write_checks.py", {"tool_name": "Write", "tool_input": {"file_path": str(root / "CLAUDE.md")}}, state) \
        if (root / "CLAUDE.md").write_text("stray\n", encoding="utf-8") or True else (None, "")
    s.check("a stray CLAUDE.md is renamed after a write", (root / "CLAUDE_banned.md").is_file() and not (root / "CLAUDE.md").exists())
    over = root / "rules" / "writing" / "too-long.rule.md"
    over.write_text("RULE writing/too-long - x\n" + "".join("- line %d\n" % i for i in range(12)), encoding="utf-8")
    obj, raw = hook(root, "post_write_checks.py", {"tool_name": "Write", "tool_input": {"file_path": str(over)}}, state)
    s.check("a rule over the cap is reported on write", "too-long" in raw and ("OVER" in raw or "cap" in raw or "lines" in raw), raw[:300])


def own_suites(s, state):
    s.section("the skill's own suites")
    for label, script in (("library suite", ROOT / ".claude" / "skills" / "rules-system" / "scripts" / "run_tests.py"),
                          ("hook suite", ROOT / ".claude" / "hooks" / "test_hooks.py"),
                          ("rule-approval suite", ROOT / ".claude" / "hooks" / "test_ask_rule_approval.py")):
        import subprocess
        p = subprocess.run([sys.executable, str(script)], capture_output=True, text=True, encoding="utf-8",
                           cwd=str(ROOT), timeout=900)
        tail = (p.stdout or "").strip().splitlines()[-1:] or [""]
        s.check("%s passes (%s)" % (label, tail[0][:60]), p.returncode == 0, (p.stdout or "")[-400:] + (p.stderr or "")[-300:])


def main():
    s = Suite("rules-system self-test")
    tmp = temp_dir("selftest_rules_")
    state = tmp / "state"
    state.mkdir()
    try:
        integrity(s)
        rule_health(s, state)
        safeguards(s, state)
        workflow(s, tmp, state)
        if "--quick" not in sys.argv:
            own_suites(s, state)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return s.finish()


if __name__ == "__main__":
    sys.exit(main())
