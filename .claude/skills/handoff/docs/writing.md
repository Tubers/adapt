# Writing a handoff

You are ending a session with work still open. Read this file only; the reader's protocol, the
review loop and the machinery are separate docs, named in `SKILL.md`.

## Placement — THE USER CHOOSES, YOU PROPOSE

One file, `HANDOFF.md`, at the level of the work it hands off. **Its folder is half its meaning**: a
handoff at the repo root hands off repo-wide work, one inside a folder hands off that folder's work.
A handoff filed somewhere unrelated to its work misleads every later reader, and that has happened.

So start here, before writing anything:

```
python .claude/skills/handoff/scripts/handoffs.py create <scope>
```

It prints the candidate locations: the repo root, plus every folder whose name shares a word with
the scope. **Put that list to the user and let them pick.** Never choose silently, and never assume
the folder you happen to have been working in is the right one. The log records the chosen location
permanently and `status` shows it, so a wrong choice is visible for as long as the record exists.

| work handed off | where |
|---|---|
| whole repo: a convention, the rule system, a cross-cutting refactor | `HANDOFF.md` at repo root |
| one mechanic, tool or discipline | `<that folder>/HANDOFF.md` |

Several may be live at once, one per scope: two unrelated bodies of open work are two messages, and
merging them buries both. Never two in one folder, because the name is the whole identity. The name
needs no date and no version while live: the session that read the last one at that path retired it,
so the name is free. Write a SECOND handoff only when the open work is genuinely a separate body of
work with a separate reader. One session's work is usually one handoff.

## The one idea: detail decays with distance from the present

| distance | what the handoff carries |
|---|---|
| in flight, being abandoned | everything not in the files, in full |
| finished this session | headline, where it landed, anything surprising the docs lack |
| earlier sessions, documented | one line and a pointer to the owning document |
| older | named in a list, or left out |

Test every sentence: **would this be lost if the session ended right now?** Obtainable by opening a
file means write the pointer instead. Existing only in this conversation means it goes in, at
whatever length it takes. The abandonment note is where that inverts: no finished artifact owns that
content, so the handoff IS its owner and carries it whole.

Writing effort runs opposite to reading effort. Almost all of it goes to the last hour.

**Anything that does NOT decay must not be in a handoff at all.** It survives exactly one reading, so
a fact placed there and nowhere else survives one session. Standing rules, retracted claims, which
folders are archives, traps that cost a run: none of it is news. It belongs in the rule or document
that owns it, permanently. Ask whether a section will still be true in a month; if yes, put it
somewhere that still exists in a month and point at it.

Earlier drafts of this skill demanded a "what is dead" section and a "standing constraints" section.
Both were wrong for that reason. Wanting to write either is the signal that a RULE is missing
something; add it there.

---

## Step 1 — take stock, do not start writing

Check rather than remember: a background task may have finished, a build may have failed. Read the
run folder, the task output, the file you think you wrote.

- What is in flight this minute? Half-written generator, mod mid-rebuild, launched run, half-applied
  edits?
- What finished this session and is not written up?
- What is dirty on the machine? A deployed build, a service left running, a file written outside the repo,
  game process running, background task going.
- What did this session decide or rule out that is in no file?

## Step 2 — abandon in-flight work deliberately

Abandon it. Do not try to finish it. Do not leave it half-applied without saying so.

The note is maximally descriptive of the work, limited to what is necessary and NOT discernible from
the work itself. The next instance can read the code. Give what the code cannot:

- **The question.** What was being established and why it was worth a run. The motive, not the
  mechanism.
- **How far it got, artifact by artifact.** Each file and its true state: written and building,
  written and never executed, built but never run, deployed but never loaded. "Mostly done" is how a
  half-finished thing gets treated as finished.
- **The literal next command**, copy-pasteable.
- **What is dirty on the machine**, and what must be true before that command is safe: a rebuild
  needing a restart, an installed artefact, a version or hash to pin.
- **What was decided and not yet written down.** Choices made in conversation die with it.
- **What was ruled out, and why.** Highest-value line in the document. It stops the next instance
  spending a session on a dead end.
- **The one thing most likely to mislead someone cold**: the obvious reading that is wrong.

Then say in the file that it was abandoned mid-flight and is NOT a task list item until someone
re-reads it. An abandoned thing that looks finished is worse than no note.

## Step 3 — discharge documentation debt FIRST

The record is not the handoff's job. Before writing a word of it, for EVERY folder this session
touched, including one it only visited:

- its `HISTORY.jsonl` holds an entry for each run, finding, decision and change:
  `python .claude/skills/rules-system/scripts/rules.py history add <folder> --kind ... --title ...`;
- every fact that may be a rule is parked: `rules.py park "<fact>" --repo <repo> --in <folder> --run <run>`;
- its `TASKS.md` shows what was done, what is NOW and what is next.

Then the handoff restates none of it. History and tasks written into a handoff go stale there, because
nobody returns to an old handoff to correct it, and a reader can get them fresh with one command.

## Step 4 — write it

Compressed register, caveman `full`, per `rules/writing/compressed-register.rule.md`. Not `ultra`:
structural tables stay. Compression never touches the abandonment note's WHY. Drop filler around a
reason, never the reasoning inside it. A sentence that is the only place a reason exists stays whole.

Generate the head rather than typing it:

```
python .claude/skills/handoff/scripts/handoffs.py create <scope> <path>/HANDOFF.md --skills a,b
```

That writes front matter with nothing above it, since the hooks read only the top, and under it the
standing notice: read once, never edit, retire with the script, and how to answer back. Every handoff
carries identical words because a generator writes them, so the feedback loop does not depend on the
writing session remembering to invite feedback.

`skills:` lists folder names under `.claude/skills/` that the READING session needs for the work left
behind: the abandoned work plus the ranked next steps. Not every skill this session used.
`skills: none` when none. Never omit it. `date:` and `scope:` are what the retire command files the
occasion by, so a missing `scope:` means nobody can file this handoff without guessing.

Five sections under the head, in reading order:

1. When it was written, and what the session was doing when it stopped. No predecessor to name.
2. **ABANDONED MID-FLIGHT** — step 2 in full, first, because it is most perishable.
3. **Where the record is** — one line per folder touched, naming its `TASKS.md` and the command that
   shows its history: `rules.py history <folder> --last 5`. Pointers only, never the entries.
4. **What the record cannot hold** — the body of the handoff now. The reasoning behind the direction
   taken; the options weighed and why each lost; doubts about a result, a convention or a tool; what the
   user said that is written nowhere else; considerations about the project as a whole that a next
   session would otherwise have to re-derive. Abstract is right here. Restated history is not.
5. **What to do next** — only what the folders' `TASKS.md` cannot say: the order across folders and the
   judgement behind it. Mark it a recommendation, not an instruction already given.

No pointer to update afterwards: nothing stores a live handoff path.

## Step 5 — pre-write check against the draft

A handoff is an instruction to a stranger who can act on it, not notes to a successor who shares your
context. Each check below was paid for by a failure recorded in a `REVIEW.md` under `data/`; read
those first, since they are the evidence. `handoffs.py list` shows which occasions have one.

1. **Reproduce every number using nothing but the draft.** Carry the CRITERION inline and name the
   script that produced the figure by repo-relative path. A scratchpad script you do not name dies
   with the session. A count over a file tree has hidden parameters that each change the answer: size
   threshold, what counts as a folder already owning a document, whether folders that no longer exist
   count. State the scope scanned and every deliberate exclusion. A deliberate exclusion and a folder
   you never looked at read identically.
2. **Mark every inference as an inference.** A cold reader treats a stated conclusion as input, not as
   a judgement to re-check, so an in-flight judgement arrives with more authority than its evidence.
   Where a claim rests on a rule, quote the clause that permits it. The nearest rule on the subject is
   not a citation, and a loose one invites the reader to "fix" the rule.
3. **For a question put to the user, record the options, what each covers, and what to do with an
   off-menu answer.** State coverage item by item or by criterion, so an option that silently includes
   wrong members is visible. A reader given two branches and a third answer will guess.
4. **Define the terms of any mechanical instruction, with one worked transform.** "Strip the stale
   framing" is not an instruction. Flag known hazards: a restored dated record can contradict a newer
   rule, and `writing/fact-ownership` then hands the stale copy the win.
5. **Every path repo-relative, no "here".** The file always moves.
6. **Put each next-work item in the `TASKS.md` of the folder that owns it before writing.** The only
   task lists are `TASKS.md` files and a live handoff's next-work section, and a handoff is read once:
   an item that lives only in the handoff dies at retirement.
7. **Run `python .claude/skills/rules-system/scripts/rules.py upkeep --full` before writing.** A run
   this session made with no history event, a rule edited without refreshing the index, a history line
   that does not parse: fix the ones this session caused, and name any you leave in the handoff with
   the reason. Drift that predates the session is not yours to clear.

## Rules

- Never edit an existing `HANDOFF*.md`. Write a new one.
- Never write a fact a document already owns. Point at it.
- Report abandonment honestly. A run launched with an unknown end is stated as exactly that. Never
  infer a result from a command that exited 0.
- No version control in this repo. No undo. Read a file before overwriting it.
- Never invent progress for tidiness. A short honest handoff beats a full one that must be
  un-believed.
