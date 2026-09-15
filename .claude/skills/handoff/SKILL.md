---
name: handoff
description: Route to the handoff docs and run the handoff record CLI. Ending a session with work still open, reading a handoff you were assigned, leaving feedback on one, answering feedback on one you wrote, or maintaining the machinery each read one small doc from this skill. Use when approaching a usage limit, before a long break, or whenever the session should end in a state the next instance can pick up cold.
---

# /handoff — index

## RUN THE CLI FIRST

`/handoff <args>` means run the record CLI with those arguments and report what it says, before
anything else:

```bash
python .claude/skills/handoff/scripts/handoffs.py <args>
```

**`/handoff` with NO arguments is not a request to write a handoff.** Run `help` and print the
command list. Writing one is `/handoff create`, and nothing else starts it: a bare invocation that
silently began writing a file was bad form.

`status` prints the whole record as a chart with what is owed. `pending` prints only the debts, each
with the session to resume.

## WHICH DOC IS YOURS

Read the ONE row that matches what you are doing. Each doc stands alone; none of them needs the
others.

| you are | read | in one line |
|---|---|---|
| writing a handoff (`/handoff create`) | `docs/writing.md` | where the file goes, what goes in it, the pre-write check |
| assigned to the work a handoff hands off | `docs/reading.md` | read it, file its facts, retire it with the script |
| finished reading one and it cost you time | `docs/review.md` | one command opens the review in the right place |
| the session that WROTE a handoff, resumed to answer feedback | `docs/answering.md` | judge each item, fix what has an owner, file the reply |
| changing the scripts, hooks, or the record itself | `docs/internals.md` | layout, states, log, hooks, tests |

## THE THREE FACTS EVERY AUDIENCE NEEDS

1. **A handoff is written once and read once.** Never edit one, before or after retirement. A hook
   refuses. Anything in it that is now wrong is EXPECTED; the fix belongs in the document that owns
   that fact.
2. **A handoff is read only by the session the user assigns to its work.** Finding one is not being
   assigned it.
3. **`scripts/handoffs.py` owns every path under `data/`.** Retire, review and answer through it.
   Never place a file there by hand.

The same conventions reach a session that loads no skill through
`rules/lifecycle/handoff.rule.md`, gated on `**/HANDOFF*.md`.
