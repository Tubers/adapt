#!/usr/bin/env python3
"""PreToolUse hook: a live handoff is read only with the user's say-so.

A handoff is addressed to whichever session the USER puts on its work, not to whichever session
happens to start next to it. Reading one retires it, so a session that reads a handoff it was never
assigned takes that work away from the session that should have had it. This hook makes every such
read visible: a Read or Grep of a live HANDOFF.md, and any shell command naming one, returns "ask",
so the user approves or refuses it in the permission prompt.

Only LIVE handoffs are gated (handoff_lib.is_live_handoff). A retired one under archive/ or a copy
under _backup/ is a record and reads freely, and a dated name is always a retired one.

Writing is not this hook's business: block_handoff_write.py refuses modification, and creating a
new handoff through the Write tool is how /handoff works, so Write is not gated here.

HOW RELIABLY
------------
  Read / Grep      EXACT. The path is a field of the tool input.
  Bash / PowerShell  HEURISTIC. Matches the literal name in the command text, which also catches
                   the retiring `mv`, so retirement is approved too. A command that reaches a
                   handoff without naming it - a glob, a variable - is not caught.

Fails OPEN on unreadable input: a hook that cannot parse its payload must not block real work.
"""

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from handoff_lib import is_live_handoff  # noqa: E402

_NAMED_RE = re.compile(r"""[^\s"'`|;&<>()]*HANDOFF\.md(?![\w-])""")

REASON = (
    "LIVE HANDOFF: {path}\n"
    "A handoff belongs to whichever session the user puts on its work, and reading it is the first "
    "step of retiring it. Approve only if you have assigned this session that work. Refuse, and the "
    "handoff stays waiting for the session that should have it."
)


def target(tool: str, tool_input: dict, cwd: str):
    """The live handoff this call would touch, or None."""
    if tool == "Read":
        path = str(tool_input.get("file_path", ""))
        return path if is_live_handoff(path, cwd) else None
    if tool == "Grep":
        path = str(tool_input.get("path", ""))
        return path if is_live_handoff(path, cwd) else None
    if tool in ("Bash", "PowerShell"):
        for token in _NAMED_RE.findall(str(tool_input.get("command", ""))):
            if is_live_handoff(token, cwd):
                return token
    return None


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    cwd = payload.get("cwd") or os.getcwd()
    hit = target(payload.get("tool_name", ""), payload.get("tool_input") or {}, cwd)
    if hit is None:
        return 0
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "ask",
            "permissionDecisionReason": REASON.format(path=hit),
        }
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
