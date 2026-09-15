#!/usr/bin/env python3
"""PostToolUse hook: when a question was asked, put the answer in front of the session.

WHAT IT IS FOR
--------------
`ask.py` prints its hits and appends them to the folder's QUERIES.jsonl. A command fired for its side
effect often has its stdout skimmed or ignored, and an answer nobody reads is the same as no answer.
This hook reads the log line the command just wrote and returns it as context, where it cannot be
missed.

It does NOT run the search. The search already happened, synchronously, inside the command. This hook
only surfaces the newest answer, which keeps it to a few milliseconds and means a broken model can
never block a write.

WHY IT MATCHES THE COMMAND AND NOT THE FILE
-------------------------------------------
An earlier design had the hook watch writes to QUERIES.jsonl. That would also fire on the tooling's
own maintenance - `qlog.py collect` reads every log, a digest touches them - and on any hand edit.
Matching the ask command is narrower and has no such overlap.

Fails OPEN and silent. A retrieval convenience must never stand between a session and its work.
"""

import json
import os
import pathlib
import sys

MARKER = "ask.py"                      # the command that asks a question
LOG_NAME = "QUERIES.jsonl"
MAX_HITS = 5
# Surfacing the same answer twice is worse than not surfacing it: an instance cannot tell a repeat
# from a new result. The marker alone is not enough, because a command that merely QUOTES ask.py -
# writing documentation about it, for instance - matches the text and produces no new answer. Caught
# in the first hour: writing the rule that documents the command re-surfaced the previous answer.
STATE = pathlib.Path(os.environ.get(
    "VECTOR_SEARCH_STATE",
    pathlib.Path(__file__).resolve().parents[1] / "skills" / "vector-search" / "data"
    / "surfaced.json"))


def newest_answer(cwd: str):
    """The last query and its answer from the most recently touched log under cwd."""
    root = pathlib.Path(cwd)
    logs = [p for p in root.rglob(LOG_NAME) if "_backup" not in p.parts]
    if not logs:
        return None, None, None
    p = max(logs, key=lambda x: x.stat().st_mtime)
    queries, answers = [], {}
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
        except ValueError:
            continue                    # a malformed line is skipped, never fatal
        if d.get("kind") == "query":
            queries.append(d)
        elif d.get("kind") == "answer" and d.get("for"):
            answers[d["for"]] = d
    if not queries:
        return None, None, p
    q = queries[-1]
    return q, answers.get(q["id"]), p


def render(q, a, path, cwd) -> str:
    rel = path.as_posix()
    try:
        rel = path.relative_to(pathlib.Path(cwd)).as_posix()
    except ValueError:
        pass
    head = "VECTOR SEARCH, %s namespace: %s" % (q.get("ns", "rules"), q.get("q", "")[:120])
    if not a or not a.get("hits"):
        return (head + "\n  nothing scored above the floor, so nothing in that corpus covers it. "
                       "That is a real answer.\n  logged in " + rel)
    lines = [head, ""]
    for h in a["hits"][:MAX_HITS]:
        lines.append("  %.3f  %s" % (h.get("score", 0), h.get("doc", "")))
        if h.get("line"):
            lines.append("         %s" % h["line"][:160])
        if h.get("where"):
            lines.append("         %s" % h["where"][:110])
    lines.append("")
    lines.append("  A hit is a POINTER. Open the rule or the file before acting on it.")
    lines.append("  Logged in %s, so the next session here inherits this lookup." % rel)
    stale = a.get("index_built", "")
    if stale:
        lines.append("  Index built %s." % stale)
    return "\n".join(lines)


def already_surfaced(path, qid) -> bool:
    """True when this exact answer has been handed to a session already."""
    try:
        seen = json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        seen = {}
    key = path.as_posix()
    if seen.get(key) == qid:
        return True
    seen[key] = qid
    try:
        STATE.parent.mkdir(parents=True, exist_ok=True)
        STATE.write_text(json.dumps(seen, indent=1), encoding="utf-8")
    except OSError:
        pass
    return False


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    if payload.get("tool_name") not in ("Bash", "PowerShell"):
        return 0
    command = str((payload.get("tool_input") or {}).get("command", ""))
    if MARKER not in command:
        return 0
    cwd = payload.get("cwd") or os.getcwd()
    try:
        q, a, path = newest_answer(cwd)
        if not q or already_surfaced(path, q["id"]):
            return 0
        text = render(q, a, path, cwd)
    except Exception:
        return 0
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PostToolUse", "additionalContext": text}}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
