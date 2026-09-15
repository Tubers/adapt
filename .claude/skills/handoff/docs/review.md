# Filing feedback on a handoff you read

Read this file only. Nothing else in the skill is needed to leave feedback.

Do it when reading the handoff cost you time: it was wrong, thin or ambiguous, or it sent you down a
dead end. Write none when the handoff held up.

## One command

```
python .claude/skills/handoff/scripts/handoffs.py draft <date>-<scope>
```

That creates `REVIEW.md` inside that handoff's own folder, with its shape already in it. Fill it in
where it sits. Never move it, never rename it, never place feedback anywhere else: the author is
pointed at that path and at no other.

`handoffs.py list` prints the occasion ids if you do not have one.

## What to write

Per item: what the handoff SAID, what you FOUND, what it COST you, and the LESSON for the skill.

- **Measure what you assert.** The review is read by the session that wrote the handoff, and a claim
  you did not check wastes that session as surely as the handoff wasted yours.
- **Mark the items where you misread it as such**, and say what your share was. A gap the prose
  failed to close is worth recording either way.
- **Every item ends in a lesson**, because the writing drill is built out of these files. An item
  with no lesson is a complaint.
- Compressed register: an LLM reads this.

## What happens next

The review sits unanswered until the user resumes the session that WROTE that handoff, which the log
identifies. That session answers it, which closes the occasion. You are not expected to fix the
handoff, and you may not edit it.
