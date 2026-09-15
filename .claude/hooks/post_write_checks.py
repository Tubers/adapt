#!/usr/bin/env python3
"""PostToolUse hook: three checks that can only be made after a write has landed.

Each is a separate concern and each early-exits when it has nothing to say. They share one process
because a hook costs a process spawn and three spawns per tool call is a tax on every edit in the
repo, not just on the ones these checks care about.

  1. CLAUDE.md SWEEP - the safety net under `guard_docs.py`.
     That hook refuses a CLAUDE.md written through Write, Edit or a recognisable shell mutation.
     What it cannot see is a Python script that writes one three calls later. So after any tool that
     could create a file, this walks the repo and RENAMES every `CLAUDE.md` it finds to
     `CLAUDE_banned.md`, then tells the session it did and where. Renaming rather than deleting is
     deliberate: this repo has no version control, so nothing here may destroy content.

  2. RULE FILE BUDGET - 10 lines and 2048 bytes, per rule file.
     Silent when every rule passes, which is the normal case. When one is over it names the file,
     both measured numbers, and asks for a rewrite rather than truncating anything itself. The cap
     is the whole economics of the system: a rule is injected in full whenever its gate matches, so
     an unbounded rule is an unbounded tax on every session that touches those paths.

  3. INDEX SYNC - `rules/INDEX.md` lists which README triggers which rule.
     A new README.md means a new row. Regenerating the block beats asking a session to remember,
     and it only ever rewrites the text between the two generated markers - the hand-maintained
     gate table above them is never touched.

Every failure path returns 0 with no output. A post-write check that breaks must not look like a
failed write.

Tests: python .claude/skills/rules-system/scripts/run_tests.py
"""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _bootstrap  # noqa: E402

# Only tools that can put a file on disk are worth sweeping after.
CREATING_TOOLS = {"Write", "Edit", "NotebookEdit", "Bash", "PowerShell"}


def sweep_claude_md(lib, root: Path) -> list[str]:
    """Rename every CLAUDE.md found to CLAUDE_banned.md. Returns what was renamed."""
    renamed = []
    for p in lib.walk_repo(root, prune_test_runs=True):
        if p.name.lower() != "claude.md":
            continue
        dst = p.with_name("CLAUDE_banned.md")
        n = 1
        while dst.exists():
            n += 1
            dst = p.with_name(f"CLAUDE_banned.{n}.md")
        try:
            p.rename(dst)
            renamed.append(f"{p.relative_to(root).as_posix()} -> {dst.name}")
        except OSError:
            renamed.append(f"{p.relative_to(root).as_posix()} (RENAME FAILED - remove it by hand)")
    return renamed


def check_readme_shape(lib, payload, root: Path):
    """A README just written must still open with its rule paths and stay inside the cap.

    This replaced the old freeze on README modification. A README carries orientation again, so it
    has to be writable; what protects it now is that the shape is checked immediately afterwards,
    where the writing session still has the context to fix it.
    """
    path = str((payload.get("tool_input") or {}).get("file_path", "") or "")
    if os.path.basename(path.replace("\\", "/")).lower() != "readme.md":
        return None
    full = Path(path if os.path.isabs(path) else os.path.join(root, path))
    if not full.is_file() or ".claude/skills/" in full.as_posix():
        return None
    named, body = lib.readme_parse(full)
    rel = full.as_posix()
    if not named:
        return (f"README NAMES NO RULE: {rel}\nA folder README opens with the path of each rule it "
                "triggers, one per line, e.g. rules/writing/fact-ownership.rule.md. Put the shared "
                "rule for this kind of folder first, then any rule peculiar to this folder.")
    missing = [n for n in named if not (root / "rules" / n).is_file()]
    if missing:
        return (f"README NAMES A RULE THAT DOES NOT EXIST: {rel}\n  "
                + "\n  ".join("rules/" + m for m in missing))
    if len(body) > lib.ORIENTATION_MAX_LINES:
        return (f"README ORIENTATION TOO LONG: {rel} has {len(body)} lines, cap is "
                f"{lib.ORIENTATION_MAX_LINES}.\nOrientation says what the folder IS and how it is "
                "laid out. A finding belongs in a rule, an event in HISTORY.jsonl.")
    return None


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0

    lib = _bootstrap.load(payload)
    if lib is None:
        return 0

    tool = payload.get("tool_name", "")
    if tool not in CREATING_TOOLS:
        return 0

    notes = []
    try:
        root = lib.repo_root(payload)

        renamed = sweep_claude_md(lib, root)
        if renamed:
            notes.append(
                "CLAUDE.md IS PROHIBITED IN THIS REPO AND YOUR FILE HAS BEEN RENAMED:\n  "
                + "\n  ".join(renamed)
                + "\nAlways-loaded prose was replaced by path-gated rules on 2026-09-09. Put the "
                  "content in rules/<slug>.rule.md (10 lines, 2048 bytes) and add a gate for it in "
                  "rules/INDEX.md. Then delete the renamed file once its content has a home."
            )

        over = lib.oversized_rules(root)
        if over:
            rows = "\n  ".join(f"{n}: {ln} lines, {sz} bytes" for n, ln, sz in over)
            notes.append(
                "RULE FILE OVER BUDGET. A rule file must be at most 10 LINES and 2048 BYTES:\n  "
                + rows
                + "\nRewrite it to fit. Cut examples, prose and tables before cutting facts; move "
                  "anything that will not fit into the folder's own docs/ and point at it. The cap "
                  "exists because a rule is injected in full every time its gate matches."
            )

        bad = check_readme_shape(lib, payload, root)
        if bad:
            notes.append(bad)

        if lib.sync_index(root):
            notes.append("rules/INDEX.md README-trigger section re-synced.")
    except Exception:
        return 0

    if not notes:
        return 0

    lib.emit({
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": "\n\n".join(notes),
        }
    })
    return 0


if __name__ == "__main__":
    sys.exit(main())
