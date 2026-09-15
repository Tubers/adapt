RULE lifecycle/handoff - written once, read once, then RETIRED.
- A handoff sits at the LEVEL OF THE WORK it hands off: repo-wide work in HANDOFF.md at the repo root, one folder's work in <that folder>/HANDOFF.md. One per scope. The SessionStart hook announces every one it finds.
- Read one ONLY when the user has put you on its work. Announcement is not assignment. gate_handoff_read.py asks the user before any read.
- Reading one INCLUDES retiring it: read it in full, move anything durable into the document that owns it, then python .claude/skills/handoff/scripts/handoffs.py retire <path>. Never move one by hand.
- Its front matter skills: names the skills its work needs; handoff_skills.py loads each SKILL.md when the read completes: treat each as invoked.
- Retiring is NOT conditional on finishing the work. You retire it because you read it.
- NEVER edit one, live or archived; a hook refuses. Anything in it that is now wrong is expected: fix that fact where it is owned.
- Archived handoffs are records. Do not read one for current state.
- Where a handoff cost you time: handoffs.py draft <occasion>, fill in the REVIEW.md it opens. handoffs.py pending names the session to resume to answer one.
