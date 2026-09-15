#!/usr/bin/env python3
"""SessionStart hook: if a handoff is waiting, say so - and say it is not automatically yours.

WHY THIS IS A HOOK AND NOT JUST A LINE IN CLAUDE.md
---------------------------------------------------
The handoff lifecycle is: written once, read once, retired. Nothing can make a session read a file,
and nothing can verify it did. What IS enforceable is that no session can start next to a waiting
handoff without being told, in its own context, that the file exists.

WHO READS IT
------------
A handoff is addressed to whichever session the USER puts on its work, not to whichever session
starts next to it. So this notice announces, and tells the session to leave the file alone unless
the user has assigned it the work. gate_handoff_read.py backs that up by asking the user before any
read of a live handoff, and handoff_skills.py loads the skills its front matter asks for once the
assigned reader has read it.

WHAT IT DOES NOT DO
-------------------
It does not enforce retirement. A `Stop` hook could check whether the handoff survived the session,
but `Stop` fires at the end of every turn, so it would nag continuously, and blocking a session
from ending is worse than a stale file. Retirement stays the reading session's job; this makes
forgetting it hard rather than impossible.

Companion to `block_handoff_write.py`, which enforces the part that IS mechanical: a handoff may be
created, moved and deleted, never modified.
"""

import json
import os
import sys

# A handoff sits at the level of the work it hands off, so there is no fixed list of places to
# look: the repo root for repo-wide work, a mechanic's or tool's folder for work owned by it, and
# more than one may be live at once. So scan, but scan a PRUNED tree - a retired handoff in the
# archive and the byte-identical copies under .claude/_backup/ must never be announced as waiting.
# Measured at 1289 directories, the walk is a few milliseconds, which a session start can afford.
SKIP_DIRS = frozenset({
    "archive", "_backup", "node_modules", "__pycache__", ".git", ".venv", "venv",
})

# Where a spent handoff is retired to: its own occasion folder in the handoff skill's data folder,
# which is also where the reader's review and the author's reply to it end up.
ARCHIVE = ".claude/skills/handoff/data"

NOTICE = """A HANDOFF IS WAITING: {path}
{extra}
It is addressed to whichever session the USER assigns its work to, which may not be you.
Do NOT read, move or act on it unless the user has asked you to take that work over. A read of a
live handoff asks the user for approval first, so an unasked one shows up as a prompt they can
refuse.

If the user HAS assigned it to you, read .claude/skills/handoff/docs/reading.md first. It is short
and it is the whole protocol: reading one includes retiring it with
`python .claude/skills/handoff/scripts/handoffs.py retire <path>`, which files it under {archive}/.

Never edit a handoff, before or after retirement. Anything in it that is now wrong is EXPECTED, and
that fix belongs in the document that owns the fact.
"""


def find_handoffs(cwd: str):
    """Every live handoff, repo-relative, shallowest first so the repo-wide one leads.

    Only the exact name counts. A dated name is an archived one that has been moved out of an
    archive folder or was never in one, and announcing it would resurrect a spent message.
    """
    out = []
    for root, dirs, files in os.walk(cwd):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
        if "HANDOFF.md" in files:
            rel = os.path.relpath(os.path.join(root, "HANDOFF.md"), cwd)
            out.append(rel.replace("\\", "/"))
    out.sort(key=lambda p: (p.count("/"), p))
    return out


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        payload = {}
    cwd = payload.get("cwd") or os.getcwd()

    found = find_handoffs(cwd)
    if found:
        extra = ""
        if len(found) > 1:
            rest = "\n".join("    " + p for p in found[1:])
            extra = ("\nAND THESE ARE WAITING TOO. Each one is a separate body of work for whichever "
                     "session the user\nassigns it to, on the same terms:\n" + rest + "\n")
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": NOTICE.format(path=found[0], extra=extra, archive=ARCHIVE),
            }
        }))
        return 0

    # No handoff waiting. Say nothing at all - a session that starts clean should not pay any
    # attention cost for a mechanism that is not currently relevant.
    return 0


if __name__ == "__main__":
    sys.exit(main())
