#!/usr/bin/env python3
"""PreToolUse hook: inject the project rules that govern the path a tool is about to touch.

WHY THIS EXISTS
---------------
Until 2026-09-09 this repo's conventions lived in a 28 KB `CLAUDE.md` loaded into every session and
in 92 free-text `README.md` files nobody was obliged to open. That is the worst of both trades: the
always-loaded half is paid for on every request whether or not it is relevant, and the optional half
is free but routinely skipped - a fresh session once picked up an archived, finished experiment as
if it were a task list.

The rule system inverts both halves. A rule is at most 10 lines, it is loaded ONLY when a gate
matches the path in front of you, and when it does load it is compulsory rather than skimmable.

WHAT IT NEVER DOES
------------------
It never fires on a path under the skills directory. Three sub-agents edit, extend and repair those
skills, and their contexts are meant to be silos: a rule about repo documentation conventions
arriving in the middle of a skill repair is noise at best, and at worst it widens the agent's scope.
`rules_lib` enforces that in code, so an accidental gate in `rules/INDEX.md` is dropped rather than
honoured.

ONCE PER SESSION
----------------
A rule is injected the first time it matches and never again in that session. State lives in the
system temp folder keyed by session id, so it is per-session and self-cleaning rather than another
file in the repo. If a rule genuinely needs restating after a compaction, reading the rule file is
one Read away and its path is in `rules/INDEX.md`.

NO SILENT CHANGES
-----------------
It also remembers, per session, which projects a Write, Edit or NotebookEdit changed and when. When the
session's tools reach ANOTHER project and a changed one has no history entry stamped since, it adds one
reminder naming the files and the `history add` command (rules/repo/no-silent-changes). Once per stretch
of unlogged work; a project whose history catches up is forgotten. Shell writes are free text and are not
seen, and nothing fires at the end of a session, since a Stop hook would fire on every turn.

FAILS OPEN, ALWAYS
------------------
Every failure path here returns 0 with no output. A hook that cannot read its own index must not
stand between the session and its work.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _bootstrap  # noqa: E402

HEADER = (
    "PROJECT RULES for the path you are touching. These are compulsory and replace the repo's old "
    "CLAUDE.md. Each is shown once per session; re-read it from rules/ if you need it again."
)


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0

    lib = _bootstrap.load(payload)
    if lib is None:
        return 0

    try:
        root = lib.repo_root(payload)
        rels, command = lib.paths_from_tool(payload)
        session = payload.get("session_id", "")
        reminder = None
        try:
            # which project this session is working in, so `rules.py view` needs no folder; and whether it
            # is leaving another project whose changes it never logged (rules/repo/no-silent-changes)
            now_project = lib.note_focus(root, session, rels)
            lib.note_change(root, session, payload.get("tool_name", ""), rels)
            reminder = lib.unlogged_reminder(root, session, now_project)
        except Exception:
            pass
        answers = None
        try:
            # the user sent an answer from the viewer that this session has not been told about
            answers = lib.answers_waiting(root, session, now_project)
        except Exception:
            pass
        matches = lib.match_paths(root, rels)
        have = {m.rule for m in matches}
        for m in lib.match_command(root, command):
            if m.rule not in have:
                have.add(m.rule)
                matches.append(m)

        # A rule goes out once per session, and again if its text has changed since this session was sent it:
        # gates and rule files are read fresh on every call, so an edit reaches the session without a reload.
        seen = lib.sent_versions(session)

        blocks = []
        fired = []
        versions = {}
        for m in matches:
            body = lib.read_rule(root, m.rule)
            if not body:
                continue
            h = lib.text_hash(body)
            if m.rule in seen and seen[m.rule] in (None, h):
                continue
            changed = m.rule in seen
            blocks.append(f"--- rules/{m.rule} ---" + (" (CHANGED since you were last shown it)" if changed else "")
                          + f"\n{body}")
            fired.append(m)
            versions[m.rule] = h
        if not blocks and not reminder and not answers:
            return 0

        parts = []
        if blocks:
            lib.mark_sent(session, versions)
            # Recorded with the gate that pulled each rule in, so `rules.py stats` can say which gates
            # are doing the work and which have never fired. Without the provenance an over-broad glob
            # and a genuinely universal rule are indistinguishable from the outside.
            lib.log_firings(root, session, payload.get("tool_name", ""), fired)
            parts.append(HEADER + "\n\n" + "\n\n".join(blocks))
        if reminder:
            parts.append(reminder)
        if answers:
            parts.append(answers)
        lib.emit({
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "additionalContext": "\n\n".join(parts),
            }
        })
    except Exception:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
