#!/usr/bin/env python3
"""PostToolUse hook on Read: load the skills a handoff asks for, the moment it is read.

A handoff opens with front matter naming the skills its remaining work needs (format in
handoff_lib.py). Every skill in this repo is user-invocable-only (.claude/settings.json), so a
session cannot load one with the Skill tool. This hook is the one sanctioned exception, and it is
narrow on purpose: it fires only after a completed Read of a LIVE handoff, which
gate_handoff_read.py has already put in front of the user for approval. What it does is what
invoking a skill does - it puts the skill's SKILL.md into the session's context - so the assigned
reader starts the handed-off work with the instructions a user-typed /name would have given it.

Nothing needs cleaning up afterwards. The request lives in the handoff's own front matter, and a
retired handoff never matches, so the request retires with the file.

Bodies are inlined up to INLINE_BUDGET characters in total. Hook context much larger than that is
spilled to a file with only a preview shown, so a skill that would overflow is named with its path
and an instruction to read it in full instead. A skill switched off in settings.json is never
loaded, and a skill that expects $ARGUMENTS is flagged for the user to run with them.

Fails OPEN and silent on anything unexpected: this hook only ever adds context.
"""

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from handoff_lib import SKILLS_DIR, is_live_handoff, requested_skills, switched_off  # noqa: E402

INLINE_BUDGET = 9000
_FRONT_MATTER_RE = re.compile(r"\A---\s*\n.*?\n---\s*\n", re.DOTALL)


def build(cwd: str, handoff: str) -> str:
    full = handoff if os.path.isabs(handoff) else os.path.join(cwd, handoff)
    names = requested_skills(full)
    if names is None:
        return ("HANDOFF SKILLS: this handoff has no `skills:` front matter, so nothing was loaded. "
                "If its work needs a skill, ask the user to run it.")
    if not names:
        return ""

    off = switched_off(cwd)
    inline, by_path, flagged, spent = [], [], [], 0
    for name in dict.fromkeys(names):
        rel = f"{SKILLS_DIR}/{name}/SKILL.md"
        if name in off:
            flagged.append(f"    /{name}  - switched off in .claude/settings.json, not loaded")
            continue
        try:
            with open(os.path.join(cwd, rel), encoding="utf-8", errors="replace") as f:
                body = f.read()
        except OSError:
            flagged.append(f"    /{name}  - no such skill: {rel} does not exist")
            continue
        if "$ARGUMENTS" in body:
            flagged.append(f"    /{name}  - takes arguments: ask the user to run it with them")
        body = _FRONT_MATTER_RE.sub("", body, count=1).strip()
        if spent + len(body) <= INLINE_BUDGET:
            inline.append(f"===== SKILL /{name} ({rel}) =====\n{body}")
            spent += len(body)
        else:
            by_path.append(f"    /{name:<26} {rel}")

    out = ["HANDOFF SKILLS - loaded because the handoff you just read asks for them. Every skill "
           "here is user-invocable-only; this is the one sanctioned exception. Treat each as "
           "invoked, exactly as if the user had typed the command."]
    if by_path:
        out += ["", "TOO LARGE TO INLINE - Read each of these in full NOW, before any other work, "
                "and follow it as if invoked:"] + by_path
    if flagged:
        out += ["", "NEEDS THE USER:"] + flagged
    out += [""] + inline
    return "\n".join(out)


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    if payload.get("tool_name") != "Read":
        return 0
    cwd = payload.get("cwd") or os.getcwd()
    path = str((payload.get("tool_input") or {}).get("file_path", ""))
    if not is_live_handoff(path, cwd):
        return 0
    try:
        text = build(cwd, path)
    except Exception:
        return 0
    if not text:
        return 0
    print(json.dumps({
        "hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": text}
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
