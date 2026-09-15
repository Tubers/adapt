# Reading a handoff, and retiring it

The user has put you on the work a handoff hands off. Finding one is not being assigned it: leave a
handoff you were not given alone. A read asks the user for approval; refused means stop and leave the
file where it is.

Reading one INCLUDES retiring it. You retire it because you read it, not because you finished the
work it describes. Unfinished work lives where work lives: a folder's `TASKS.md` and `HISTORY.jsonl`, a folder doc, or
the next handoff.

## 1. Read it whole, once

The skills its front matter lists load into your context as the read completes. Treat each as
invoked, and follow any "needs the user" line the hook prints.

Start at ABANDONED. It is the most perishable part and the only content in the file with no other
owner.

## 2. Carry anything durable into the document that owns it

Before step 3, because a fact you meant to file is easy to lose once the document moves.

An abandoned experiment's state goes into that folder's doc, a measured number into the doc that owns
it, a convention into its rule. Anything you are about to act on immediately needs no home but your
own context.

## 3. Retire it with the script, never by hand

```
python .claude/skills/handoff/scripts/handoffs.py retire <path>/HANDOFF.md
```

Date and scope come from the handoff's own front matter. Pass a scope as a second argument only for
an old handoff that lacks one. The write guard permits this move deliberately: moves are judged by
destination, so retiring passes while overwriting does not.

**If the move fails, say so plainly and ask the user to relocate it.** Never leave it silently in
place and never carry on as if it were handled. A handoff still sitting at the live path after being
read is the failure this whole arrangement exists to prevent: a fresh session once picked up finished
work as pending.

## 4. Where it cost you time, review it

See `review.md` in this folder. One command, and the file it opens says what to write.

## What you may never do

Never edit a handoff: not to correct it, not to tick something off, not to add a line. A hook refuses
Write, Edit and shell commands that rewrite one, retired ones included. What makes a handoff worth
reading is that it was true when written; an edited one is a document nobody can date. Anything in it
that is now wrong is EXPECTED, and the fix belongs in the document that owns that fact.
