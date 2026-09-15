#!/usr/bin/env python3
"""PostToolUse hook: record who wrote each handoff, and notice when its review arrives.

WHAT IT IS FOR
--------------
A handoff is written by one session and read by another, and the reader's review lands days later
in the archive. By then nothing knows which session wrote the thing being reviewed, and a review
nobody can route is a review nobody answers.

The session id is knowable at exactly one moment: the write. So this hook watches for a live
HANDOFF.md being written and appends one `written` record carrying the session id and the
transcript path. Everything after that is state the filesystem already shows, so the hook simply
compares each occasion's files against the last event logged for it and appends what changed:
`retired` when a handoff lands in the archive, `reviewed` when a REVIEW.md appears beside it,
`answered` when a RESPONSE.md does. That way a move done by hand logs the same as one done through
`handoffs.py`.

The log lives with the skill (`.claude/skills/handoff/data/log.jsonl`); the occasion folders live
in the repo archive. `handoffs.py pending` joins the two and prints the session to resume.

Fails OPEN and silent. A record that cannot be written is worth less than a session that cannot
work, and `handoffs.py check` reports anything the log missed.
"""

import datetime
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from handoff_lib import is_live_handoff                                       # noqa: E402

_SKILL_SCRIPTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                              "skills", "handoff", "scripts")
sys.path.insert(0, _SKILL_SCRIPTS)
import handoff_data as hd                                                     # noqa: E402

WRITE_TOOLS = ("Write", "NotebookEdit")
MOVE_TOOLS = ("Bash", "PowerShell")

# What each state should have been logged as, once the occasion reaches it.
EVENT_FOR_STATE = {hd.RETIRED: "retired", hd.PENDING: "reviewed", hd.CLOSED: "answered"}
ORDER = {"retired": 0, "reviewed": 1, "answered": 2}


def _now():
    return datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def _front_matter_value(path: str, key: str):
    """One scalar out of a handoff's front matter, or '' - front matter is the only place a
    handoff states its own scope, and the scope is half of the occasion id."""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            lines = f.read(4096).splitlines()
    except OSError:
        return ""
    if not lines or lines[0].strip() != "---":
        return ""
    for line in lines[1:40]:
        if line.strip() == "---":
            break
        if line.lower().startswith(key + ":"):
            return line.split(":", 1)[1].strip().strip("'\"")
    return ""


def record_write(payload, cwd, log):
    path = str((payload.get("tool_input") or {}).get("file_path", ""))
    if not path or not is_live_handoff(path, cwd):
        return None
    full = path if os.path.isabs(path) else os.path.join(cwd, path)
    if not os.path.isfile(full):
        return None
    rel = os.path.relpath(full, cwd).replace("\\", "/")
    date = _front_matter_value(full, "date") or datetime.date.today().isoformat()
    scope = _front_matter_value(full, "scope")
    # One record per path per HANDOFF DATE: a handoff is often written in several passes before the
    # session ends, and each pass is the same authorship, not a new one.
    #
    # This compared the record's TIMESTAMP against the handoff's own date, which are the same string
    # only while the clock has not passed midnight. Writing a 2026-09-11 handoff on 2026-09-12 logged
    # a second author. Found by the suite the day the date rolled over.
    for rec in log:
        if (rec.get("event") == "written" and rec.get("path") == rel
                and rec.get("date") == date):
            return None
    rec = {
        "event": "written",
        "path": rel,
        "date": date,
        "scope": scope,
        "occasion": hd.occasion_id(date, scope) if scope else "",
        "session": payload.get("session_id") or "",
        "transcript": (payload.get("transcript_path") or "").replace("\\", "/"),
        "ts": _now(),
    }
    hd.append(rec)
    if not scope:
        return ("HANDOFF LOGGED, BUT WITHOUT A SCOPE. Its front matter has no `scope:` line, so the "
                "archive folder it retires into cannot be named from the file, and the review that "
                "comes back cannot be matched to this session automatically. Add a short `scope:` "
                "slug to the front matter.")
    return None


def reconcile(payload, log):
    """Append an event for any occasion whose files have moved past what the log last said."""
    last = {}
    for rec in log:
        occ, ev = rec.get("occasion"), rec.get("event")
        if occ and ev in ORDER and ORDER[ev] >= ORDER.get(last.get(occ, ""), -1):
            last[occ] = ev
    notes = []
    for occ in hd.occasions():
        want = EVENT_FOR_STATE[occ["state"]]
        seen = last.get(occ["occasion"])
        if seen is not None and ORDER[want] <= ORDER[seen]:
            continue
        hd.append({"event": want, "occasion": occ["occasion"], "ts": _now(),
                   "session": payload.get("session_id") or "", "by": "reconcile"})
        if want == "reviewed":
            rec = hd.author_of(occ["occasion"]) or {}
            who = rec.get("session")
            notes.append(
                "A REVIEW WAS FILED for handoff %s. It is now waiting on the session that WROTE "
                "that handoff%s. Tell the user; `handoffs.py pending` lists it."
                % (occ["occasion"], (", session " + who) if who else
                   ", which is not in the log, so the user must pick the session"))
    return notes


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    tool = payload.get("tool_name", "")
    if tool not in WRITE_TOOLS + MOVE_TOOLS:
        return 0
    cwd = payload.get("cwd") or os.getcwd()
    try:
        log = hd.read_log()
        notes = []
        if tool in WRITE_TOOLS:
            note = record_write(payload, cwd, log)
            if note:
                notes.append(note)
        notes += reconcile(payload, hd.read_log())
    except Exception:
        return 0
    if notes:
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PostToolUse", "additionalContext": "\n\n".join(notes)}}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
