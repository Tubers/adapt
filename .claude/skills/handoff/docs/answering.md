# Answering a review of a handoff you wrote

The user resumed this session because `handoffs.py pending` named it. A `REVIEW.md` sits in an
occasion folder addressed to you, and the occasion stays a debt until you answer.

1. **Read the review, then the handoff beside it**, in that order. The handoff is retired, so reading
   it is free of the assignment rule.
2. **Judge each item: a real gap in what you wrote, or a misreading by the reader.** Say which. Where
   you are wrong, say so plainly. A review answered defensively teaches the skill nothing.
3. **Fix what has an owner.** A wrong fact belongs in the document that owns it, a repeatable mistake
   in the pre-write drill in `writing.md`, a convention in `rules/lifecycle/handoff.rule.md`. The
   response records what you did with each item; it is not where a fix is stored.
4. **File the reply:**

   ```
   python .claude/skills/handoff/scripts/handoffs.py respond <occasion> <your file>
   ```

   It lands as `RESPONSE.md` and closes the occasion, so the folder holds the handoff, the feedback
   and the answer together.

Never edit the other two files. Both were written once; your answer is the third file, not a
correction of the first two.
