#!/usr/bin/env python3
"""Audit the rule system against what is actually on disk.

    python .claude/skills/rules-system/scripts/reconcile.py [--quiet]

Exits 0 when clean, 1 when anything is reported, 2 on a setup problem. The non-zero exit is so this
can be wired into a check rather than read by eye every time.

WHY EACH CLASS IS WORTH A REPORT
--------------------------------
Every failure here is SILENT in normal use. A gate whose folder was renamed simply stops firing;
a rule nothing references simply never arrives. Nothing errors, nothing is logged, and the first
symptom is a session that did not know something it should have - which looks exactly like a
session that ignored a rule. That is the same failure mode the game itself has, and the same answer
applies: build the check that makes a wrong state LOOK wrong.

  DEAD GLOB          a path gate that matches no file in the repo. Either the path moved, or the
                     glob has a typo. `**/*.xsdat` is expected to be dead when no run has been
                     kept, so a gate may be listed as tolerated below.
  ORPHAN RULE        a rules/<area>/[<group>/]<slug>.rule.md no gate and no README references. It can never be
                     injected, so it is 10 lines of pure cost.
  MISSING RULE       a gate, or a README, naming a rule file that does not exist.
  UNPAIRED README    a README.md naming nothing, so its folder triggers no rule of its own.
  OVERLONG README    more orientation lines than the cap. A README opens with its rule paths, one
                     per line, then a blank line, then a short orientation and nothing more.
  HEADLINE           a rule whose first line names a different path than the file it is in. Every
                     instance of this so far was a regroup rename applied twice, and it is invisible
                     in normal use because nothing reads the headline.
  SKILL GATE         a gate matching a path under the skills directory. This must never exist:
                     sub-agents work in those folders and their contexts are silos. rules_lib drops
                     such a gate at load time, so this reports one that was written but ignored.
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rules_lib as lib  # noqa: E402

# Globs that are allowed to match nothing right now, with the reason. A gate for a file kind the
# repo does not currently hold is not a mistake.
TOLERATED_DEAD = {
    "**/QUESTIONS.jsonl": "a project's questions for the user; none are open until an instance asks one",
    "**/HANDOFF*.md": "a handoff exists only while one is waiting",
    "**/README.md": "a folder gets its README when it gets its first rule",
    "**/docs/**": "a docs folder exists once a project writes one",
    "**/NOTES.md": "a notes file exists once a project writes one",
    "**/QUERIES.jsonl": "written the first time ask.py is run in a folder",
    "**/archive/**": "nothing is archived until work finishes",
    "**/CLAUDE*.md": "must never exist: the gate is there to catch one being made",
    ".claude/rules/**": "must never exist: the gate is there to catch one being made",
}

def project_root() -> Path:
    return Path(__file__).resolve().parents[4]


# Gate parsing lives in rules_lib and nowhere else. This file kept its own copy of the regex once,
# so that it could see the gates the loader drops; the two drifted, and the moment rule names gained
# a "/" this reconciler parsed ZERO gates and cheerfully reported every rule as an orphan. A check
# that fails by finding nothing is worse than no check. lib.raw_gates() is unfiltered, which is all
# this needed in the first place.


def main(argv) -> int:
    quiet = "--quiet" in argv
    root = project_root()
    problems = []
    notes = []

    rules_dir = root / lib.RULES_DIRNAME
    if not rules_dir.is_dir():
        print(f"no rules directory at {rules_dir}", file=sys.stderr)
        return 2

    # Paths relative to rules/, not basenames: rules live in area folders, so `xs/authoring.rule.md`
    # is the identity everything else uses. A basename set here reported all 92 READMEs as naming a
    # rule that does not exist.
    on_disk = set(lib.all_rules(root))
    gates = lib.raw_gates(root)
    readmes = lib.find_readmes(root)

    # Every repo-relative path once, so each glob is tested against the same corpus.
    all_paths = []
    for p in lib.walk_repo(root, prune_backup=False):
        rel = p.relative_to(root).as_posix()
        if not lib.is_skill_path(rel):
            all_paths.append(rel)

    referenced = set()

    for rule, trigger in gates:
        if rule not in on_disk:
            problems.append(f"MISSING RULE    gate names rules/{rule}, which does not exist")
            continue
        referenced.add(rule)

        if trigger.startswith("cmd:"):
            try:
                re.compile(trigger[4:])
            except re.error as e:
                problems.append(f"BAD REGEX       {rule}: cmd:{trigger[4:]} ({e})")
            continue

        if lib.is_skill_gate(trigger):
            problems.append(
                f"SKILL GATE      {rule}: `{trigger}` targets the skills directory. "
                "rules_lib drops it, so the rule silently never fires there. Remove the gate.")
            continue

        rx = lib.glob_to_regex(trigger)
        if not any(rx.match(rel) for rel in all_paths):
            if trigger in TOLERATED_DEAD:
                notes.append(f"dead but expected: `{trigger}` ({TOLERATED_DEAD[trigger]})")
            else:
                problems.append(
                    f"DEAD GLOB       {rule}: `{trigger}` matches nothing in the repo")

    for p in readmes:
        rel = p.relative_to(root).as_posix()
        named, body = lib.readme_parse(p)
        if not named:
            problems.append(
                f"UNPAIRED        {rel}: names no rule file, so this folder triggers nothing of "
                "its own. Open it with one rule path per line, e.g. "
                "rules/writing/fact-ownership.rule.md")
            continue
        missing = [n for n in named if n not in on_disk]
        if missing:
            problems.append(f"MISSING RULE    {rel} names {', '.join('rules/' + m for m in missing)}"
                            ", which does not exist")
            continue
        if len(body) > lib.ORIENTATION_MAX_LINES:
            problems.append(
                f"OVERLONG        {rel}: {len(body)} lines of orientation, cap is "
                f"{lib.ORIENTATION_MAX_LINES}. Orientation says what the folder IS; findings belong "
                "in a rule and events in HISTORY.jsonl.")
            continue
        referenced.update(named)

    for name in sorted(on_disk - referenced):
        problems.append(
            f"ORPHAN RULE     rules/{name}: no gate and no README references it, so it can never "
            "be injected. Give it a gate in rules/INDEX.md or delete it.")

    for name in sorted(on_disk):
        first = (root / lib.RULES_DIRNAME / name).read_text(
            encoding="utf-8", errors="replace").split("\n", 1)[0]
        stem = name[:-len(lib.RULE_SUFFIX)]
        m = re.match(r"RULE ([^\s]+)", first)
        if not m:
            problems.append(f"HEADLINE        rules/{name}: first line is not 'RULE <name> - ...'")
        elif m.group(1) != stem:
            problems.append(
                f"HEADLINE        rules/{name}: headline says {m.group(1)}, file says {stem}")

    over = lib.oversized_rules(root)
    for name, lines, size in over:
        problems.append(
            f"OVER BUDGET     rules/{name}: {lines} lines, {size} bytes (cap is "
            f"{lib.MAX_RULE_LINES} lines and {lib.MAX_RULE_BYTES} bytes)")

    print(f"rules: {len(on_disk)}   gates: {len(gates)}   READMEs: {len(readmes)}   "
          f"files scanned: {len(all_paths)}")
    if notes and not quiet:
        print()
        for n in notes:
            print(f"  note  {n}")
    if problems:
        print()
        for p in problems:
            print(f"  {p}")
        print(f"\n{len(problems)} problem(s).")
        return 1
    print("\nclean.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
