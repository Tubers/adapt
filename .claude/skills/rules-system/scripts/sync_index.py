#!/usr/bin/env python3
"""Rebuild the generated README-trigger section of rules/INDEX.md.

Run by hand:

    python .claude/skills/rules-system/scripts/sync_index.py [--check]

`post_write_checks.py` calls the same function automatically after any tool that could create a
README, so the file stays current without anyone remembering. This entry point exists for the times
a person moves or deletes folders in bulk, where no single tool call is the trigger.

Only the text between the two generated markers is touched. The hand-maintained gate table above
them is never rewritten.

`--check` reports whether the file is stale and exits 1 if it is, without writing anything.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rules_lib as lib  # noqa: E402


def project_root() -> Path:
    # <project>/.claude/skills/rules-system/scripts/sync_index.py
    return Path(__file__).resolve().parents[4]


def main(argv) -> int:
    check_only = "--check" in argv
    root = project_root()
    index = root / lib.RULES_DIRNAME / lib.INDEX_NAME

    if not index.is_file():
        print(f"no index at {index}", file=sys.stderr)
        return 2

    before = index.read_text(encoding="utf-8")
    if lib.GEN_BEGIN not in before or lib.GEN_END not in before:
        print("index is missing its generated markers; nothing was written", file=sys.stderr)
        return 2

    readmes = lib.find_readmes(root)

    if check_only:
        # Sync into a copy so nothing is written, then compare.
        changed = _would_change(root, before, readmes)
        print(f"{len(readmes)} README.md files; index is {'STALE' if changed else 'current'}")
        return 1 if changed else 0

    changed = lib.sync_index(root)
    print(f"{len(readmes)} README.md files; index {'updated' if changed else 'already current'}")
    return 0


def _would_change(root: Path, before: str, readmes) -> bool:
    rows = []
    for p in readmes:
        rel = p.relative_to(root).as_posix()
        rows.append(f"- `{rel}` | `{lib.readme_rule(p) or '(none)'}`")
    block = lib.GEN_BEGIN + "\n" + "\n".join(rows) + "\n" + lib.GEN_END
    head, _, tail = before.partition(lib.GEN_BEGIN)
    _, _, tail = tail.partition(lib.GEN_END)
    return (head + block + tail) != before


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
