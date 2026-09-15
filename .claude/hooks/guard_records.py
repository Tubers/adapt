#!/usr/bin/env python3
"""PreToolUse hook: a project's records are reached through commands, never directly.

    HISTORY.jsonl      rules.py history <folder> ... | history show <id> | history add <folder> ...
    TASKS.md           rules.py tasks [show|add|start|done|block|unblock|drop|detail|goal] | init <folder>
    QUESTIONS.jsonl    rules.py tasks ask | answer | act | acted | questions | answers
    candidates.jsonl   rules.py candidates --repo <repo> [next] | park | decide

WHY
---
A record read whole costs a session thousands of tokens it did not need, and a record edited by hand loses
its stamps, breaks its shape, or skips the second copy a candidate must also change. The commands print
one line per entry, stamp every write, and keep the two copies of a candidate in step. So an instance does
not open, read, grep, edit, move or delete these files: it runs the command, and this hook refuses the
direct route and prints the commands instead, so the refusal is also the instruction.

WHAT IT MATCHES
---------------
Read, Write, Edit and NotebookEdit aimed at a record, by file name, ignoring case because Windows does.
Grep and Glob whose path, glob or pattern would reach a record's name. A shell command, split at `&&`,
`||`, `;`, `|` and newlines, where one piece names a record and reads or changes a file, or where any
redirect writes into a record. A piece that STARTS by running one of the commands themselves (rules.py,
vector-search's scripts, the test suites) is exempt; merely mentioning one elsewhere in the command is not,
and a redirect into a record is refused even after an exempt command. Hardened 2026-09-13 after a review:
`rules.py history x > x/HISTORY.jsonl` and `cat x/HISTORY.jsonl  # rules.py` were getting through.

WHAT IT DOES NOT CATCH
----------------------
A command is free text, so this is a guard against habit, not against intent: a wildcard that happens to
expand to a record, a Grep over a whole folder, or a script built to read one. The rules say commands only,
and the refusal message teaches them.

Fails OPEN on unreadable input: a guard that cannot read its payload must not stop work.
"""

import fnmatch
import json
import os
import re
import sys

RULES_PY = "python .claude/skills/rules-system/scripts/rules.py"

RECORDS = {
    "HISTORY.jsonl": ("a project's history",
                      [RULES_PY + " history <folder> [runs|findings|changes|decisions|dead-ends|notes|candidates] "
                                  "[--last 5|--first 5|--all] [--since YYYY-MM-DD] [--grep WORD]",
                       RULES_PY + " history show <id>",
                       RULES_PY + ' history add <folder> --kind <kind> --title "<title>" [--result R] '
                                  "[--evidence P] [--refs R] [--no-rule WHY]",
                       RULES_PY + ' park "<fact>" --repo <repo> --in <folder> --run <run folder>   (a rule candidate)',
                       RULES_PY + " view   (the tasks, history and candidates in the browser)"]),
    "TASKS.md": ("a project's task window",
                 [RULES_PY + " tasks [--in <folder>]   (show)",
                  RULES_PY + ' tasks add "<task>" | start <id> | done [<id>] --result R | block <id> --reason WHY',
                  RULES_PY + ' tasks unblock <id> | drop <id> --reason WHY | detail <id> "<paragraph>" | goal "<goal>"',
                  RULES_PY + ' init <project folder> --goal "<goal>"   (a new project)',
                  RULES_PY + " view   (the tasks, history and candidates in the browser)"]),
    "QUESTIONS.jsonl": ("a project's questions and actions for the user",
                        [RULES_PY + ' tasks ask <task id> "<question>"   (the task shows ❓ until answered)',
                         RULES_PY + ' tasks answer <q id> "<the user\'s answer>"',
                         RULES_PY + ' tasks act <task id> "<what the user must do>"   (the task shows ❗ until done)',
                         RULES_PY + ' tasks acted <a id> ["<note>"]   (the user did it)',
                         RULES_PY + " tasks questions   (list them)",
                         RULES_PY + " tasks answers   (read the replies; each is logged in history and removed)"]),
    "candidates.jsonl": ("the master copy of the rule candidates",
                         [RULES_PY + " candidates --repo <repo> [next|--all]",
                          RULES_PY + " decide <id> approve|reject --repo <repo> ...",
                          RULES_PY + ' park "<fact>" --repo <repo> --in <folder> --run <run folder>']),
}
CANON = {k.lower(): k for k in RECORDS}

# A draft editable by hand until its format is frozen. Empty since 2026-09-13; kept as the mechanism.
DRAFTS = set()

_NAMES = r"(HISTORY\.jsonl|TASKS\.md|QUESTIONS\.jsonl|candidates\.jsonl)"
NAME = re.compile(r"(?<![\w.])" + _NAMES + r"(?![\w.])", re.IGNORECASE)

# A piece of a shell command that starts by running one of the commands, and so is allowed to name a record.
EXEMPT_START = re.compile(
    r"^(?:\w+=\S*\s+)*(?:&\s*)?[\"']?(?:python3?|py)(?:\.exe)?[\"']?\s+[\"']?[^\s\"']*"
    r"(?:rules-system[\\/]scripts[\\/]\w+\.py|rules\.py|vector-search[\\/]scripts[\\/]\w+\.py|run_tests\.py|"
    r"test_\w+\.py|handoffs\.py)[\"']?(?:\s|$)", re.IGNORECASE)

# A verb that reads or changes a file. Without one, a piece that merely names a record does nothing to it.
TOUCH = re.compile(
    r"\b(cat|head|tail|less|more|type|sed|awk|grep|rg|findstr|select-string|sls|get-content|gc|set-content|sc|"
    r"add-content|ac|out-file|tee|tee-object|cp|copy|copy-item|cpi|mv|move|move-item|mi|rm|del|erase|"
    r"remove-item|ri|rename|ren|rename-item|rni|truncate|wc|jq|code|notepad|vim|nano|dd|patch|"
    r"readalltext|readalllines|readallbytes|writealltext|appendalltext|writeallbytes)\b|"
    r"open\(|read_text|read_bytes|write_text|write_bytes", re.IGNORECASE)

# Any redirect whose target is a record, wherever it sits. `2>&1` is not one: a stream, not a file.
REDIRECT_INTO = re.compile(r"(?<![0-9&])>{1,2}\s*[\"']?[^\s\"'|;&<>]*?(?<![\w.])" + _NAMES + r"(?![\w.])",
                           re.IGNORECASE)

SEGMENTS = re.compile(r"&&|\|\||;|\||\r?\n")


def canon(name: str) -> str:
    return CANON[name.lower()]


def rel(path: str, cwd: str) -> str:
    p = path.replace("\\", "/")
    c = (cwd or "").replace("\\", "/").rstrip("/")
    if c and p.lower().startswith(c.lower() + "/"):
        p = p[len(c) + 1:]
    return p.lstrip("./")


def message(name: str) -> str:
    what, commands = RECORDS[canon(name)]
    return ("%s is %s, and it is reached through commands only: never open, read, grep, edit, move or "
            "delete it directly. A whole record costs thousands of tokens and a hand edit loses its stamps "
            "and its shape. Use:\n  %s\n\nEvery command and flag: %s help. If this command only mentions the "
            "name inside text for another file, use Edit or Write on that file instead."
            % (canon(name), what, "\n  ".join(commands), RULES_PY))


def deny(reason: str) -> int:
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                             "permissionDecision": "deny",
                                             "permissionDecisionReason": reason}}))
    return 0


def glob_reaches_record(pattern: str):
    """The record a Grep glob or Glob pattern would match by file name, or None."""
    base = pattern.replace("\\", "/").rsplit("/", 1)[-1]
    if not base or base in ("*", "**"):
        return None
    # a bare extension wildcard (*.md, *.jsonl) is ordinary searching, not aimed at a record: refuse only a
    # glob that spells out part of a record's own name, such as HIST*.jsonl or *ASKS.md
    stem = base.rsplit(".", 1)[0]
    if not stem.strip("*?"):
        return None
    for name in RECORDS:
        if fnmatch.fnmatch(name.lower(), base.lower()):
            return name
    return None


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    if not isinstance(payload, dict):
        return 0
    tool = payload.get("tool_name", "")
    ti = payload.get("tool_input") or {}
    cwd = payload.get("cwd") or os.getcwd()

    if tool in ("Read", "Write", "Edit", "NotebookEdit"):
        path = str(ti.get("file_path") or ti.get("notebook_path") or "")
        name = os.path.basename(path.replace("\\", "/")).lower()
        if name in CANON and rel(path, cwd) not in DRAFTS:
            return deny(message(name))
        return 0

    if tool in ("Grep", "Glob"):
        m = NAME.search(str(ti.get("path") or ""))
        if m:
            return deny(message(m.group(1)))
        for field in ("glob", "pattern" if tool == "Glob" else None):
            if field:
                hit = glob_reaches_record(str(ti.get(field) or ""))
                if hit:
                    return deny(message(hit))
        return 0

    if tool in ("Bash", "PowerShell"):
        command = str(ti.get("command") or "")
        if not NAME.search(command):
            return 0
        m = REDIRECT_INTO.search(command)
        if m:
            return deny(message(m.group(1)))
        for piece in SEGMENTS.split(command):
            s = piece.strip()
            n = NAME.search(s)
            if not n or EXEMPT_START.match(s) or not TOUCH.search(s):
                continue
            return deny(message(n.group(1)))
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
