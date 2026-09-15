"""Self-test: the handoff skill as installed in this project.

    python Adapt/selftest/handoff/test_handoff.py [--quick]

Sections: install integrity, then the whole life of one handoff in a throwaway clone (created, announced,
gated on read, protected from edits, its skills loaded, retired and filed, the record consistent), then the
skill's own suites. --quick skips the skill's own suites.
"""

import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _common import ROOT, Suite, cli, clone, context, decision, hook, registered, settings, temp_dir  # noqa: E402

HO = ("handoff", "handoffs.py")
NAME = "HAND" + "OFF.md"          # spelled in parts, as the hook suite does: command text is matched
HOOKS_EXPECTED = {
    "announce_handoff.py": ("SessionStart", None),
    "gate_handoff_read.py": ("PreToolUse", "Read"),
    "block_handoff_write.py": ("PreToolUse", "Edit"),
    "handoff_skills.py": ("PostToolUse", "Read"),
    "handoff_registry.py": ("PostToolUse", "Write"),
}


def integrity(s):
    s.section("install integrity")
    base = ROOT / ".claude" / "skills" / "handoff"
    for f in ("SKILL.md", "scripts/handoffs.py", "scripts/handoff_data.py", "scripts/run_tests.py",
              "docs/writing.md", "docs/reading.md", "docs/review.md", "docs/answering.md", "docs/internals.md"):
        s.check("skill file present: " + f, (base / f).is_file())
    for h, (event, tool) in HOOKS_EXPECTED.items():
        where = registered(ROOT, h)
        s.check("%s is registered on %s%s" % (h, event, " for " + tool if tool else ""),
                any(e == event and (tool is None or tool in m.split("|")) for e, m in where), where)
        s.check("%s exists where settings point" % h, (ROOT / ".claude" / "hooks" / h).is_file())
    s.check("the shared parser handoff_lib.py is present", (ROOT / ".claude" / "hooks" / "handoff_lib.py").is_file())
    s.check("handoff is user-invocable only", settings().get("skillOverrides", {}).get("handoff") == "user-invocable-only")
    data = base / "data"
    old = [d.name for d in data.iterdir() if d.is_dir()] if data.is_dir() else []
    s.check("no handoff was migrated in from another project", not old, old)
    s.check("the rule about handoffs is installed and gated", (ROOT / "rules" / "lifecycle" / "handoff.rule.md").is_file()
            and "lifecycle/handoff.rule.md" in (ROOT / "rules" / "INDEX.md").read_text(encoding="utf-8"))


def life_of_a_handoff(s, tmp, state):
    s.section("the life of one handoff, in a throwaway clone")
    root = clone(tmp)
    obj, raw = hook(root, "announce_handoff.py", {}, state)
    s.check("with no handoff, session start says nothing", raw == "", raw[:200])
    live = root / "demo" / NAME
    live.parent.mkdir(parents=True)
    rc, out = cli(root, HO, ["create", "demo", "demo/" + NAME, "--skills", "rules-system"], state)
    s.check("create writes the handoff with its front matter", rc == 0 and live.is_file()
            and "skills:" in live.read_text(encoding="utf-8"), out[-300:])
    obj, _ = hook(root, "announce_handoff.py", {}, state)
    s.check("session start announces the waiting handoff", "A HANDOFF IS WAITING" in context(obj), context(obj)[:200])
    s.check("and says an unassigned session must leave it alone", "Do NOT read" in context(obj))
    obj, _ = hook(root, "gate_handoff_read.py", {"tool_name": "Read", "tool_input": {"file_path": str(live)}}, state)
    s.check("reading a live handoff asks the user first", decision(obj) == "ask")
    obj, _ = hook(root, "block_handoff_write.py", {"tool_name": "Edit", "tool_input": {"file_path": str(live), "old_string": "a", "new_string": "b"}}, state)
    s.check("editing a handoff is refused", decision(obj) == "deny")
    obj, _ = hook(root, "handoff_skills.py", {"tool_name": "Read", "tool_input": {"file_path": str(live)}}, state)
    s.check("reading it loads the skills its front matter names", "rules-system" in context(obj), context(obj)[:200])
    rc, out = cli(root, HO, ["retire", "demo/" + NAME], state)
    filed = list((root / ".claude" / "skills" / "handoff" / "data").glob("*-demo/" + NAME))
    s.check("retire files it in the handoff skill's data folder", rc == 0 and not live.exists() and filed, out[-300:])
    obj, raw = hook(root, "announce_handoff.py", {}, state)
    s.check("once retired, it is no longer announced", raw == "", raw[:200])
    obj, _ = hook(root, "gate_handoff_read.py", {"tool_name": "Read", "tool_input": {"file_path": str(filed[0]) if filed else ""}}, state)
    s.check("an archived handoff reads freely", decision(obj) is None)
    rc, out = cli(root, HO, ["check"], state)
    s.check("the record and the folders agree", rc == 0, out[-300:])
    rc, out = cli(root, HO, ["status"], state)
    s.check("status draws the record", rc == 0 and "demo" in out, out[-300:])


def own_suites(s):
    s.section("the skill's own suites")
    for label, script in (("handoff suite", ROOT / ".claude" / "skills" / "handoff" / "scripts" / "run_tests.py"),
                          ("handoff write-block suite", ROOT / ".claude" / "hooks" / "test_block_handoff_write.py")):
        p = subprocess.run([sys.executable, str(script)], capture_output=True, text=True, encoding="utf-8",
                           cwd=str(ROOT), timeout=600)
        tail = (p.stdout or "").strip().splitlines()[-1:] or [""]
        s.check("%s passes (%s)" % (label, tail[0][:60]), p.returncode == 0, (p.stdout or "")[-400:] + (p.stderr or "")[-300:])


def main():
    s = Suite("handoff self-test")
    tmp = temp_dir("selftest_handoff_")
    state = tmp / "state"
    state.mkdir()
    try:
        integrity(s)
        life_of_a_handoff(s, tmp, state)
        if "--quick" not in sys.argv:
            own_suites(s)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return s.finish()


if __name__ == "__main__":
    sys.exit(main())
