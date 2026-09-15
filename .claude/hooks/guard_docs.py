#!/usr/bin/env python3
"""PreToolUse hook: no CLAUDE.md anywhere, at any path, under any casing.

WHY
---
This repo carries no always-loaded doc. Unbounded prose loaded whether or not it is relevant is
exactly what the rule system replaced, and `CLAUDE.md` is the one name the host would load into
every session by itself. What such a file would hold belongs in `rules/<area>/<slug>.rule.md`,
gated on the paths where it applies. A `PostToolUse` sweep renames any that slips past this arm to
`CLAUDE_banned.md`, so a file written by a script rather than by a tool is still caught.

FOLDER READMEs ARE NO LONGER GUARDED HERE, changed 2026-09-11. They were frozen while a README was
a single machine-read trigger line. A README now opens with its rule paths, one per line, then a
blank line, then a short orientation for whoever opens the folder, so it must be editable. Its
SHAPE is checked after the write instead, by `post_write_checks.py` and by `rules.py reconcile`.

TWO ARMS, NOT EQUALLY STRONG:

  Write / Edit / NotebookEdit   EXACT. `tool_input.file_path` names the file directly.
  Bash / PowerShell             HEURISTIC and deliberately narrow: denied only when the name is a
                                plain write TARGET, a redirect at it or a write verb naming it.
                                The PostToolUse sweep is the real guarantee, and a wider test
                                refused edits to OTHER files that merely quoted the name.

FAILS OPEN on unreadable input, and never blocks a Read by any route.

Tests: python .claude/hooks/test_hooks.py
"""

import json
import os
import re
import sys

MUTATION_TOKENS = (
    "tee", "sed -i", "truncate", "patch ",
    "vim", "nvim", "nano", "emacs",
    "'w'", '"w"', "'a'", '"a"', "write_text", "writelines", "os.replace",
    "set-content", "add-content", "out-file", "new-item",
)

_REDIRECT_RE = re.compile(r">>?\s*\S*(?:claude\.md|readme\.md)", re.IGNORECASE)
_README_PATH_RE = re.compile(r"[A-Za-z0-9_./\\:~+-]*readme\.md", re.IGNORECASE)

# Verbs that WRITE to the path that follows them, on the same command segment. Used to decide
# whether a banned filename in a command is a TARGET rather than a mention.
_WRITE_VERBS = (r"mv|cp|copy|move|rename|move-item|copy-item|touch|new-item|out-file|"
                r"set-content|add-content|tee|truncate|patch|vim|nvim|nano|emacs")
_CLAUDE_TARGET_RE = re.compile(
    r"(?:\b(?:" + _WRITE_VERBS + r")\b|sed\s+-i)[^|;&\n]*?claude\.md", re.IGNORECASE)

DENY_CLAUDE = (
    "CLAUDE.md is PROHIBITED in this repo. It was removed on 2026-09-09 and replaced by path-gated "
    "rules, because always-loaded prose is paid for on every request whether or not it is relevant.\n\n"
    "Put the content in rules/<slug>.rule.md instead - at most 10 lines and 2048 bytes - and add a "
    "gate for it in rules/INDEX.md so it reaches a session only on the paths where it applies. "
    "rules/writing/readme-and-rules.rule.md states the convention.\n\n"
    "If a CLAUDE.md is created by some route this hook cannot see, the PostToolUse sweep renames it "
    "to CLAUDE_banned.md and tells you it did."
)

DENY_README = (
    "This README.md already exists, and an existing README.md may not be modified.\n\n"
    "A README.md here is not a document. It holds exactly ONE line: the path of the rule file that "
    "folder triggers. There is nothing in it to edit.\n\n"
    "What you almost certainly want is the RULE file it names, under rules/. Those are freely "
    "editable at any time - make them more accurate, more pertinent or shorter - as long as each "
    "stays within 10 lines and 2048 bytes. Longer prose belongs in the folder's own docs/, its "
    "HISTORY.jsonl, or AMALGAMATED_DOCS.md.\n\n"
    "Creating a NEW README.md is allowed and is not blocked."
)

SHELL_NOTE = (
    "\n\n(Refused by the shell arm of this hook, which matches on command text and is approximate. "
    "If this command only READS the file, re-run it without a redirect or a write mode in the same "
    "command, or use the Read tool.)"
)


SKILL_PREFIX = os.path.join(".claude", "skills")


def in_a_skill(path: str) -> bool:
    """A README under .claude/skills/ belongs to that skill, not to the repo.

    The one-line-trigger convention is a REPO convention: a folder here names the rule it fires.
    A skill is self-contained and documents itself, so its own READMEs are ordinary documents and
    are freely editable. Without this the guard made every skill README permanently frozen.
    """
    norm = str(path).replace("\\", "/")
    return "/.claude/skills/" in norm or norm.startswith(".claude/skills/")


def basename(path: str) -> str:
    return os.path.basename(path.replace("\\", "/")).lower()


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        print(json.dumps({"systemMessage": "guard_docs.py: unreadable hook input"}))
        return 0

    tool = payload.get("tool_name", "")
    ti = payload.get("tool_input") or {}
    cwd = payload.get("cwd") or os.getcwd()

    def exists(p: str) -> bool:
        return os.path.isfile(p if os.path.isabs(p) else os.path.join(cwd, p))

    reason = None

    if tool in ("Write", "Edit", "NotebookEdit"):
        path = str(ti.get("file_path", "") or "")
        if basename(path) == "claude.md":
            reason = DENY_CLAUDE

    elif tool in ("Bash", "PowerShell"):
        command = str(ti.get("command", "") or "")
        lowered = command.lower()
        if "claude.md" not in lowered:
            return 0
        redirected = bool(_REDIRECT_RE.search(command))

        # The banned root doc: deny only when the name is plainly a WRITE TARGET - a redirect
        # pointing at it, or a write verb naming it on the same command segment. Denying on any
        # mutation token plus the name appearing anywhere was too wide in practice: it refused an
        # edit to a DIFFERENT file whose replacement text merely quoted the name. That is a real
        # cost with no matching benefit, because the PostToolUse sweep is the actual guarantee -
        # it walks the repo after every mutating tool and renames whatever it finds, whichever
        # route created it. This arm is a courtesy that catches the obvious case early.
        if redirected and re.search(r">>?\s*\S*claude\.md", command, re.IGNORECASE):
            reason = DENY_CLAUDE + SHELL_NOTE
        elif _CLAUDE_TARGET_RE.search(command):
            reason = DENY_CLAUDE + SHELL_NOTE

    if reason is None:
        return 0

    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
