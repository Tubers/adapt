#!/usr/bin/env python3
"""Tests for ask_rule_approval.py.  Run: python .claude/hooks/test_ask_rule_approval.py

Payloads are built here and handed to the hook by subprocess, as test_block_handoff_write.py does,
so no rule path next to a write verb ever appears on a real command line. Each case runs against a
throwaway repo in a temp folder, named to the hook through CLAUDE_PROJECT_DIR and the payload cwd:

    FRESH    a worklist written now that flags xs/guard only
    STALE    the same worklist dated 30 hours ago
    NOLIST   no worklist at all
    BROKEN   a worklist that is not JSON

The worklist loader itself (audit_worklist.py) is imported from this repo and checked directly first.
"""

import datetime
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HOOKS = Path(__file__).resolve().parent
HOOK = HOOKS / "ask_rule_approval.py"
REPO = HOOKS.parent.parent
sys.path.insert(0, str(REPO / ".claude" / "skills" / "rules-system" / "scripts"))
import audit_worklist as aw  # noqa: E402

SUFFIX = ".rule" + ".md"
GUARD = "rules/xs/guard" + SUFFIX          # on the worklist
OTHER = "rules/xs/other" + SUFFIX          # exists, not on the worklist
NEW = "rules/xs/brand-new" + SUFFIX        # does not exist
INDEX = "rules/INDEX.md"

INDEX_TEXT = (
    "# rules INDEX\n\n"
    "Some header prose.\n\n"
    "### `xs/`\n\n"
    "- **xs/guard" + SUFFIX + "** | `**/*.xs` | the checker\n"
    "- **xs/other" + SUFFIX + "** | `**/*_lib.xs` | another rule\n"
)

BASE = Path(tempfile.mkdtemp(prefix="ask-rule-hook-test-"))


def make_repo(name, worklist):
    root = BASE / name
    (root / "rules" / "xs").mkdir(parents=True)
    (root / GUARD).write_text("RULE xs/guard - the checker.\n- line one\n", encoding="utf-8")
    (root / OTHER).write_text("RULE xs/other - another rule.\n- line one\n", encoding="utf-8")
    (root / INDEX).write_text(INDEX_TEXT, encoding="utf-8")
    (root / "rules" / "xs" / "notes.md").write_text("not a rule\n", encoding="utf-8")
    skill_rules = root / ".claude" / "skills" / "foo" / "rules" / "xs"
    skill_rules.mkdir(parents=True)
    if worklist is not None:
        path = root / aw.WORKLIST_REL
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(worklist if isinstance(worklist, str) else json.dumps(worklist), encoding="utf-8")
    return root


def stamp(hours_ago):
    t = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=hours_ago)
    return t.isoformat(timespec="seconds")


LIST = {"rules": ["xs/guard"], "why": {"xs/guard": ["facts"]}}
FRESH = make_repo("fresh", {**LIST, "generated": stamp(0)})
STALE = make_repo("stale", {**LIST, "generated": stamp(30)})
NOLIST = make_repo("nolist", None)
BROKEN = make_repo("broken", "{not json")
FUTURE = make_repo("future", {**LIST, "generated": stamp(-5)})

# The candidate master copy the hook reads to show an approval's fact text.
FACT = "Every fact is written once, in the document that owns it."
(FRESH / aw.DATA_REL / ("candidates" + ".jsonl")).write_text(
    json.dumps({"id": "c-other", "what": "a different candidate", "status": "pending"}) + "\n"
    + json.dumps({"id": "c-123", "kind": "candidate", "title": "fact ownership", "what": FACT,
                  "folder": "mechanics/inventory/", "status": "pending"}) + "\n", encoding="utf-8")

RESULTS = []


def check(label, ok, detail=""):
    RESULTS.append((label, bool(ok)))
    print("[%s] %s%s" % ("PASS" if ok else "FAIL", label, "" if ok else "  -> %s" % str(detail)[:300]))


def run(payload, root, raw=None):
    """-> (decision or None, reason). Raises on a non-zero exit or unexpected output."""
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(root))
    out = subprocess.run([sys.executable, str(HOOK)], input=raw if raw is not None else json.dumps(payload),
                         capture_output=True, text=True, env=env)
    if out.returncode != 0:
        raise SystemExit("hook exited %d: %s" % (out.returncode, out.stderr.strip()))
    if not out.stdout.strip():
        return None, ""
    o = json.loads(out.stdout)["hookSpecificOutput"]
    return o["permissionDecision"], o["permissionDecisionReason"]


def tool(name, root=FRESH, **kw):
    return {"tool_name": name, "tool_input": kw, "cwd": str(root)}


def worklist_checks():
    print("audit_worklist.py")
    check("a fresh list returns its rules", aw.load_worklist(FRESH) == {"xs/guard"})
    check("a stale list pre-approves nothing", aw.load_worklist(STALE) == set())
    check("the age limit is the caller's", aw.load_worklist(STALE, max_age_hours=48) == {"xs/guard"})
    check("a missing list pre-approves nothing", aw.load_worklist(NOLIST) == set())
    check("a broken list pre-approves nothing", aw.load_worklist(BROKEN) == set())
    check("a future-dated list pre-approves nothing", aw.load_worklist(FUTURE) == set())
    check("stale says how old", "hours old" in aw.status(STALE)[1], aw.status(STALE)[1])
    check("stem strips path and suffix", aw.stem("C:\\x\\repo\\rules\\xs\\guard" + SUFFIX) == "xs/guard")
    names = aw.names_in("**xs/guard" + SUFFIX + "** and rules/**/*" + SUFFIX + " and xs/other plus a/b",
                        known={"xs/other"})
    check("names_in: suffixed, known bare, never a glob or an unknown pair", names == {"xs/guard", "xs/other"},
          names)
    check("flagged_by reads each report shape",
          aw.flagged_by("facts", {"findings": [{"a": "x/a" + SUFFIX, "b": "y/b" + SUFFIX}]}) == {"x/a", "y/b"}
          and aw.flagged_by("hubs", {"findings": [{"hub": "x/hub" + SUFFIX, "missing": []},
                                                   {"hub": "y/hub" + SUFFIX, "missing": ["y/z"]}]}) == {"y/hub"}
          and aw.flagged_by("coverage", {"findings": {"missing": [{"rule": "x/a" + SUFFIX, "counted": True},
                                                                  {"rule": "x/b" + SUFFIX, "counted": False}],
                                                      "overbroad": [{"rule": "x/c" + SUFFIX}]}}) == {"x/a", "x/c"})
    moved = make_repo("moved", {**LIST, "generated": stamp(0)})
    check("rename_in_worklist carries a flagged rule to its new name",
          aw.rename_in_worklist(moved, "xs/guard", "xs/lang/guard")
          and aw.load_worklist(moved) == {"xs/guard", "xs/lang/guard"})
    check("rename_in_worklist leaves an unflagged rule alone", not aw.rename_in_worklist(moved, "xs/other", "xs/o2"))
    print("")


def py(cmd):
    return "python - <<'EOF'\nfrom pathlib import Path\n" + cmd + "\nEOF"


CASES = [
    # (expect "ask" or None, label, payload, root, text the reason must contain)
    # --- NEW RULES: always ask ---------------------------------------------------------------
    ("ask", "Write a new rule", tool("Write", file_path=NEW, content="RULE xs/brand-new - x"), FRESH, ("NEW RULE rules/xs/brand-new" + SUFFIX, "+ RULE xs/brand-new - x")),
    ("ask", "Edit a rule that does not exist", tool("Edit", file_path=NEW, old_string="a", new_string="b"), FRESH, "NEW"),
    ("ask", "NotebookEdit a new rule path", tool("NotebookEdit", notebook_path=NEW, new_source="x"), FRESH, "NEW"),
    ("ask", "a new rule even when its name is on the worklist",
     tool("Write", file_path="rules/xs/lang/guard" + SUFFIX, content="x"),
     make_repo("listed-new", {"rules": ["xs/lang/guard"], "generated": stamp(0)}), "NEW"),

    # --- EXISTING RULES: the worklist decides -------------------------------------------------
    (None, "Write a flagged rule", tool("Write", file_path=GUARD, content="RULE xs/guard - new"), FRESH, ""),
    (None, "Edit a flagged rule by absolute path",
     tool("Edit", file_path=str(FRESH / GUARD), old_string="line one", new_string="line 1"), FRESH, ""),
    ("ask", "Edit an unflagged rule, showing old and new",
     tool("Edit", file_path=OTHER, old_string="line one", new_string="a weird one-off change"), FRESH,
     "a weird one-off change"),
    ("ask", "Write over an unflagged rule", tool("Write", file_path=OTHER, content="RULE xs/other - y"), FRESH, "xs/other"),
    ("ask", "Edit an unflagged rule by backslash path",
     tool("Edit", file_path="rules\\xs\\other" + SUFFIX, old_string="a", new_string="b"), FRESH, "xs/other"),
    ("ask", "Edit a flagged rule, worklist STALE",
     tool("Edit", file_path=GUARD, old_string="a", new_string="b", root=STALE), STALE, "hours old"),
    ("ask", "Edit a flagged rule, NO worklist",
     tool("Edit", file_path=GUARD, old_string="a", new_string="b", root=NOLIST), NOLIST, "no audit worklist"),
    ("ask", "Edit a flagged rule, BROKEN worklist",
     tool("Edit", file_path=GUARD, old_string="a", new_string="b", root=BROKEN), BROKEN, "unreadable"),

    # --- rules/INDEX.md: every rule in the changed lines must be flagged ----------------------
    (None, "Edit INDEX on a flagged rule's gate",
     tool("Edit", file_path=INDEX, old_string="| `**/*.xs` | the checker", new_string="| `**/*.xs`, `**/*.per` | the checker"),
     FRESH, ""),
    ("ask", "Edit INDEX on an unflagged rule's gate",
     tool("Edit", file_path=INDEX, old_string="- **xs/other" + SUFFIX + "** | `**/*_lib.xs`",
          new_string="- **xs/other" + SUFFIX + "** | `**/*.xs`"), FRESH, "xs/other"),
    ("ask", "Edit INDEX touching a flagged and an unflagged gate",
     tool("Edit", file_path=INDEX, old_string=INDEX_TEXT.split("### `xs/`\n\n")[1],
          new_string=INDEX_TEXT.split("### `xs/`\n\n")[1].replace("checker", "guard").replace("another", "a")),
     FRESH, "xs/other"),
    (None, "Edit INDEX whose unchanged context names an unflagged rule",
     tool("Edit", file_path=INDEX, old_string=INDEX_TEXT.split("### `xs/`\n\n")[1],
          new_string=INDEX_TEXT.split("### `xs/`\n\n")[1].replace("the checker", "the XS checker")), FRESH, ""),
    ("ask", "Edit INDEX header prose naming no rule",
     tool("Edit", file_path=INDEX, old_string="Some header prose.", new_string="Other prose."), FRESH,
     ("no rule", "- Some header prose.", "+ Other prose.")),
    (None, "Write INDEX changing only a flagged gate",
     tool("Write", file_path=INDEX, content=INDEX_TEXT.replace("the checker", "the XS checker")), FRESH, ""),
    ("ask", "Write INDEX adding an unflagged gate",
     tool("Write", file_path=INDEX, content=INDEX_TEXT + "- **xs/third" + SUFFIX + "** | `x` | new\n"), FRESH, "xs/third"),
    ("ask", "Edit INDEX on a flagged gate, worklist STALE",
     tool("Edit", file_path=INDEX, old_string="the checker", new_string="xs/guard" + SUFFIX + " checker", root=STALE),
     STALE, "hours old"),

    # --- CANDIDATE APPROVAL: always ask ------------------------------------------------------
    ("ask", "rules.py decide approve",
     tool("Bash", command="python .claude/skills/rules-system/scripts/rules.py decide c-123 approve --rule xs/guard"),
     FRESH, ("CANDIDATE APPROVAL c-123", "Every fact is written once, in the document that owns it.",
             "Target rule: rules/xs/guard" + SUFFIX + " (exists)")),
    ("ask", "rules.py decide approve from PowerShell, flags first",
     tool("PowerShell", command="python .claude\\skills\\rules-system\\scripts\\rules.py decide --rule xs/guard c-9 approve"),
     FRESH, ("CANDIDATE APPROVAL c-9", "was not found")),
    (None, "rules.py decide reject",
     tool("Bash", command="python .claude/skills/rules-system/scripts/rules.py decide c-123 reject --reason dup"),
     FRESH, ""),

    # --- rules.py move ----------------------------------------------------------------------
    (None, "move a flagged rule", tool("Bash", command="python .claude/skills/rules-system/scripts/rules.py move xs/guard xs/lang/guard"), FRESH, ""),
    (None, "move a flagged rule named by path", tool("Bash", command="python rules.py move " + GUARD + " xs/lang/guard"), FRESH, ""),
    (None, "move a flagged rule by bare leaf", tool("Bash", command="python rules.py move guard xs/lang/guard"), FRESH, ""),
    ("ask", "move an unflagged rule", tool("Bash", command="python rules.py move xs/other xs/lang/other"), FRESH, ("RULE MOVE rules/xs/other" + SUFFIX, "Old name: rules/xs/other" + SUFFIX,
                                                                                             "New name: rules/xs/lang/other" + SUFFIX)),
    (None, "move --dry-run of an unflagged rule", tool("Bash", command="python rules.py move xs/other xs/lang/other --dry-run"), FRESH, ""),
    ("ask", "move a flagged rule, worklist STALE", tool("Bash", command="python rules.py move xs/guard xs/lang/guard"), STALE, "hours old"),

    # --- SHELL WRITES to a rule --------------------------------------------------------------
    (None, "append redirect onto a flagged rule", tool("Bash", command="echo x >> " + GUARD), FRESH, ""),
    ("ask", "redirect onto an unflagged rule", tool("Bash", command="echo x > " + OTHER), FRESH, "xs/other"),
    ("ask", "redirect creating a new rule", tool("Bash", command="echo x > " + NEW), FRESH, "NEW"),
    ("ask", "sed -i on an unflagged rule", tool("Bash", command="sed -i s/a/b/ " + OTHER), FRESH, "xs/other"),
    ("ask", "python heredoc write_text on an unflagged rule",
     tool("Bash", command=py('p = Path("' + OTHER + '")\ntext = p.read_text()\np.write_text(text + "x")')), FRESH, "xs/other"),
    (None, "python open(...,'w') on a flagged rule", tool("Bash", command="python -c \"open('" + GUARD + "','w').write('x')\""), FRESH, ""),
    ("ask", "PowerShell Set-Content on an unflagged rule",
     tool("PowerShell", command="Set-Content -Path rules\\xs\\other" + SUFFIX + " -Value x"), FRESH, "xs/other"),
    ("ask", "cp onto an unflagged rule", tool("Bash", command="cp draft.md " + OTHER), FRESH, "xs/other"),
    (None, "Copy-Item onto a flagged rule", tool("PowerShell", command="Copy-Item draft.md " + GUARD), FRESH, ""),
    (None, "mv an unflagged rule away (source, not target)", tool("Bash", command="mv " + OTHER + " archive/other.md"), FRESH, ""),
    ("ask", "redirect onto a flagged rule, worklist STALE", tool("Bash", command="echo x >> " + GUARD), STALE, "hours old"),
    ("ask", "sed -i over a rule pattern", tool("Bash", command="sed -i s/a/b/ rules/**/*" + SUFFIX), FRESH, "pattern"),

    # --- SHELL WRITES to rules/INDEX.md: keyed on the rules the command names ------------------
    (None, "sed -i INDEX naming a flagged rule", tool("Bash", command="sed -i 's#xs/guard" + SUFFIX + "#xs/guard" + SUFFIX + " #' " + INDEX), FRESH, ""),
    ("ask", "sed -i INDEX naming an unflagged rule", tool("Bash", command="sed -i 's#xs/other" + SUFFIX + "#y#' " + INDEX), FRESH, "xs/other"),
    ("ask", "append to INDEX naming no rule", tool("Bash", command="echo prose >> " + INDEX), FRESH,
     ("no rule", "Full command:\necho prose >> " + INDEX)),

    # --- THE REASON SHOWS THE CHANGE ITSELF ---------------------------------------------------
    ("ask", "Edit headline, then removed, added and unchanged lines",
     tool("Edit", file_path=OTHER, old_string="RULE xs/other - another rule.\n- line one",
          new_string="RULE xs/other - another rule.\n- line uno\n- line two"), FRESH,
     ("RULE EDIT rules/xs/other" + SUFFIX + ", not on the audit worklist", "  RULE xs/other - another rule.",
      "- - line one", "+ - line uno", "+ - line two")),
    ("ask", "Edit with replace_all says so",
     tool("Edit", file_path=OTHER, old_string="line", new_string="row", replace_all=True), FRESH,
     ("replace_all", "- line", "+ row")),
    ("ask", "Write over a rule diffs against the file on disk",
     tool("Write", file_path=OTHER, content="RULE xs/other - another rule.\n- line changed\n"), FRESH,
     ("RULE EDIT rules/xs/other" + SUFFIX, "Write replaces the whole file", "  RULE xs/other - another rule.",
      "- - line one", "+ - line changed")),
    ("ask", "Write a new rule shows its full text",
     tool("Write", file_path=NEW, content="RULE xs/brand-new - x\n- first\n- second\n"), FRESH,
     ("NEW RULE rules/xs/brand-new" + SUFFIX, "+ - first", "+ - second")),
    ("ask", "NotebookEdit on a rule shows the replaced cell and the new source",
     tool("NotebookEdit", notebook_path=OTHER, cell_id="c1", new_source="brand new source"), FRESH,
     ("RULE EDIT rules/xs/other" + SUFFIX, "Cell source being replaced", "not a notebook", "New source:\nbrand new source")),
    ("ask", "Edit INDEX shows the whole old and new gate lines",
     tool("Edit", file_path=INDEX, old_string="`**/*_lib.xs` | another rule", new_string="`**/*_lib.xs` | a changed rule"),
     FRESH, ("INDEX EDIT rules/INDEX.md", "- - **xs/other" + SUFFIX + "** | `**/*_lib.xs` | another rule",
             "+ - **xs/other" + SUFFIX + "** | `**/*_lib.xs` | a changed rule")),
    ("ask", "Write INDEX shows the added gate line",
     tool("Write", file_path=INDEX, content=INDEX_TEXT + "- **xs/third" + SUFFIX + "** | `x` | new\n"), FRESH,
     ("+ - **xs/third" + SUFFIX + "** | `x` | new",)),
    ("ask", "a shell write shows the full command and the rule files it names",
     tool("Bash", command="echo 'a long appended line' >> " + OTHER + " && echo done"), FRESH,
     ("RULE EDIT rules/xs/other" + SUFFIX + " by a shell command", "Rule files it writes: rules/xs/other" + SUFFIX,
      "Full command:\necho 'a long appended line' >> " + OTHER + " && echo done")),
    ("ask", "decide approve shows contradicts and proof",
     tool("Bash", command='python rules.py decide c-123 approve --rule xs/new-home --contradicts xs/other '
                          '--proof "test_runs/x/runs/1"'), FRESH,
     ("CANDIDATE APPROVAL c-123 into rules/xs/new-home" + SUFFIX, FACT, "does not exist yet: a NEW rule",
      "--contradicts xs/other", "--proof test_runs/x/runs/1", "mechanics/inventory/")),
    ("ask", "a very large change is cut at 6000 characters, saying how much",
     tool("Write", file_path=NEW, content="x" * 9000), FRESH, ("NEW RULE", "[cut ")),

    # --- SILENT: reads, other files, other tools ---------------------------------------------
    (None, "cat an unflagged rule", tool("Bash", command="cat " + OTHER), FRESH, ""),
    (None, "grep INDEX", tool("Bash", command="grep -n xs/other " + INDEX), FRESH, ""),
    (None, "grep a rule into another file", tool("Bash", command="grep x " + OTHER + " > out.txt"), FRESH, ""),
    (None, "2>&1 pipeline that reads a rule", tool("Bash", command="python t.py 2>&1 | tail -3 && cat " + OTHER), FRESH, ""),
    (None, "rules.py show", tool("Bash", command="python .claude/skills/rules-system/scripts/rules.py show xs/other"), FRESH, ""),
    (None, "rules.py history add whose text names a rule and a write verb",
     tool("Bash", command='python .claude/skills/rules-system/scripts/rules.py history add f --kind change --title t '
                          '--what "tee and write_text into ' + OTHER + '; see ' + INDEX + '"'), FRESH, ""),
    (None, "Edit a file outside rules/", tool("Edit", file_path="docs/x.md", old_string="a", new_string="b"), FRESH, ""),
    (None, "Write a non-rule file under rules/", tool("Write", file_path="rules/xs/notes.md", content="x"), FRESH, ""),
    (None, "Write a rule-shaped file inside a skill", tool("Write", file_path=".claude/skills/foo/rules/xs/new" + SUFFIX, content="x"), FRESH, ""),
    (None, "Read tool on a rule", tool("Read", file_path=OTHER), FRESH, ""),
    (None, "an unrelated command", tool("Bash", command="python inventory_dev.py"), FRESH, ""),
    (None, "empty tool_input", {"tool_name": "Write", "tool_input": {}, "cwd": str(FRESH)}, FRESH, ""),
]


def main() -> int:
    worklist_checks()
    print("ask_rule_approval.py")
    try:
        for expect, label, payload, root, needle in CASES:
            payload["cwd"] = str(root)            # the payload's cwd is the case's own repo
            got, reason = run(payload, root)
            needles = needle if isinstance(needle, tuple) else ((needle,) if needle else ())
            ok = got == expect and all(n in reason for n in needles)
            check("%-5s %s" % ("ASK" if expect else "quiet", label), ok, "got %s: %s" % (got, reason))
            if got == "ask" and "sub-agent" not in reason:
                check("   and the reason says a sub-agent cannot answer", False, reason)
        got, _ = run(None, FRESH, raw="{not json")
        check("quiet unreadable input fails open", got is None)
        got, _ = run(None, FRESH, raw="[1, 2]")
        check("quiet a JSON list fails open", got is None)
    finally:
        shutil.rmtree(BASE, ignore_errors=True)
    failed = [l for l, ok in RESULTS if not ok]
    print("\n%d/%d checks passed" % (len(RESULTS) - len(failed), len(RESULTS)))
    if failed:
        print("FAILED: " + "; ".join(failed))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
