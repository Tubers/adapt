# Folder records and rule candidates

Maintainer reference for `scripts/history.py` and `scripts/candidates.py`. The conventions an instance
follows are in `rules/writing/history-log.rule.md` and `rules/writing/rule-candidates.rule.md`; this
explains why they are shaped the way they are.

## Every folder keeps its own record

A mechanic, a pattern, a tool: each folder with its own agenda keeps its own `HISTORY.jsonl`, what
happened, and `TASKS.md`, what is next. There is no central one of either. Work done briefly in another
folder is logged in THAT folder, so no change is silent.

## Written by command, never by hand

```bash
rules.py history add <folder> --kind run|finding|decision|change|dead-end|note --title "<t>" [--result R] \
    [--evidence P]... [--refs R]... [--no-rule WHY] [--numbers k=v]... [--tags T]... [--supersedes ID]
```

A hand-typed entry is missing its id, time or session, or breaks the one-object-per-line shape, and
nothing notices until a reader trips on it. `history add` stamps id, date, time and session, creates the
file, and refuses a run entry that names no `test_runs/<scenario>/runs/<stamp>` folder or closes with
neither `--refs` nor `--no-rule`. Candidates are the one kind it will not write.

## Read in slices

```bash
rules.py history <folder> [runs|findings|changes|decisions|dead-ends|notes|candidates] [--last 5|--first 5|--all]
rules.py history --grep <word> [--since YYYY-MM-DD]          # across the whole repository
rules.py history show <id>
```

One line per entry, the last five by default, the folder and its subfolders. A folder slice opens with
the folder's state: its NOW task from `TASKS.md`, its latest entry and its pending candidates. Every
folder-scoped command prints the same block, so a session working in a folder learns its state from the
command it was going to run anyway, and nothing runs unscoped at session start.

## Rule candidates: two copies, one record

```bash
rules.py park "<fact>" --repo <repo> --in <folder> --run test_runs/<scenario>/runs/<stamp>
rules.py candidates --repo <repo> [next | --all]
rules.py decide <id> approve --repo <repo> --rule <area/slug> [--agrees] [--contradicts <rule> --proof <run>]
rules.py decide <id> reject --repo <repo> --reason "<why>"
```

A candidate is the same JSON line in two places: the `HISTORY.jsonl` of the folder whose work found it,
for provenance beside the work, and `data/<repo root name>/candidates.jsonl`, so a session that knows
nothing can list every pending candidate and work through them with `candidates next`. It is stamped
with the time, the session (`CLAUDE_CODE_SESSION_ID`), the entry point, the run it came from or why
there is none, and what the cosine pass found at that moment.

Neither copy ever drops a candidate. A decision sets `status` (pending, approved, rejected), `reason`
and a stamped `decided` record on that same line in both files, which is the only in-place change
these files ever see. Both copies are checked to hold the line before either changes, and
`rules.py upkeep` reports a candidate whose copies disagree.

## `--repo`: the rule ecosystem

`rules.py use <name|folder>` sets the rule set once per session, like OpenGL state, and every later command of
both skills follows it. The order is `--repo` on a command, then a nested rule set holding the working folder,
then `use`, then this repository. The working folder outranks `use` because a sub-agent cannot be told apart
from its parent: an adapt sub-agent works in its home folder, and that gives it its own rules. The choice is stored per session (`<state dir>/claude_rule_router/<session>.use.json`,
which vector-search reads itself). A sub-agent has its parent's session id, and nothing in the environment tells them
apart, so it shares the choice, and its home folder is what sets its own rule set.

Every command takes `--repo`; without it (and without `use`) a command works on this repository, except park, candidates and
decide, which require it. `main` reads it for the commands that do not read it themselves, so a `--repo`
is never taken for an argument. list, show, gates, which, budget and the record commands work on any
ecosystem. The rest (stats, log, accept, move, audit, the reports, reconcile, sync) still read data kept
for this repository alone, so they refuse another ecosystem by name rather than answer for the wrong one.
vector-search takes `--repo` on search, ask, index and report, and refuses any ecosystem but this one until
it keeps an index per ecosystem (knowledge_upkeep PLAN item 29).

Every command that reads or writes candidates names its ecosystem. This repository is `--repo <repo>`; a
folder under it that keeps its own `rules/`, such as a skill whose development has rules of its own, is
`--repo <that folder>`. Its records live in `data/<that folder's name>/`, so ecosystems never share a
file. The cosine pass is available for this repository only until vector-search indexes other ecosystems.

## The cosine pass

One call to vector-search's `report.py scope` compares the candidate with every rule line, every whole
rule, and every live repo file in the gate report's cache.

| check | from the pass | enforced |
|---|---|---|
| not new | another rule at 0.80, the cut `facts` uses | refused; fold it in, or `--overlap-ok WHY` |
| same subject | another rule at 0.70 | each answered: `--agrees`, or `--contradicts` |
| game fact contradicted | a named same-subject rule | only with `--proof` AND the old rule already corrected |
| work procedure contradicted | `writing/`, `lifecycle/`, `repo/`, `tooling/`, `candidates.PROCEDURE` | always refused |
| scope | the fact's folder, same-subject gates, folders with files at 0.60 | the rule must fire on the fact's folder; wider is proposed, never applied; nothing near is NICHE |

An embedding finds that two statements are about the same thing but cannot tell whether they agree, so
the promoter, who has just read the listed lines, says which. The rule approved into is excluded, so
folding a fact into an existing rule is fine. When the pass cannot run, approval needs `--unchecked WHY`.

## What makes a project

A project is a folder in the work tree whose `.rs` folder holds any of HISTORY.jsonl, TASKS.md or
QUESTIONS.jsonl; never under .claude/, rules/ or test_runs/. The three files always live together in
`<project>/.rs/` (the user, 2026-09-17), found through `scripts/records.py`. QUESTIONS.jsonl is optional:
`init --no-questions` starts a project no person answers without it, and upkeep does not report it missing.
Records still sitting directly in a folder are the old layout; `rules.py migrate` moves them, with `git mv`
when git tracks them, and logs the move in each project. Projects nest: `rules.py init <subfolder>` inside a project starts a sub-project
with its own tasks, history and questions, and logs that in the parent's history. Records always go to the
nearest project file up the path from the folder a command names or runs in, and `history merge` never folds in
a sub-project's history. The repo root can be a project too (`init .`), the last stop up the path. A sub-project
names the parent task it serves (`init <sub> --task <id>`), kept as a `**Parent:**` line in its TASKS.md; the
parent's `tasks` and its viewer list each task's sub-projects, and the viewer opens one and links back up. `rules.py upkeep` reports, as its
PROJECT class, a project missing any of the three, a TASKS.md out of format, a task in progress over 14
days, and records kept in a subfolder of a project. `rules.py init <folder>` completes an older project that
has only some of the files, and never touches one already there.

## Questions for the user

```bash
rules.py tasks ask t8 "<question>"        # an instance asks; t8 shows ❓ until it is answered
rules.py tasks answer q3 "<answer>"       # the user's answer is written in
rules.py tasks answers                    # an instance reads the answers, which consumes them
```

`QUESTIONS.jsonl` holds one line per question, tied to a task id, and only questions not yet read back.
Reading the answers logs each question and its answer as a stamped `decision` entry in the project's history,
keyed by `question` and `task`, and only then removes the line. A read that stopped between those two writes
is safe to repeat: an answer already in history is removed without being logged again. The ❓ on a task line
is derived from the file each time the window is loaded, so it cannot drift from the questions. The folder
state every command prints counts open questions and answers waiting.

The viewer shows every question above the task list, with a reply box. The page posts the reply to its own
local server, which writes it through `questions.answer`; the request carries a per-server token in a custom
header and must name the server's own host, so no other page can write. While a viewer is open, instances ask
the user through it instead of chat (rules/writing/tasks).

## The viewer

```bash
rules.py view                     # the project this command runs inside, or this session last worked in
rules.py view Adapt         # a named project; a subfolder walks up to it
rules.py view --static            # a snapshot in the temp folder that never updates
```

One page with three tabs. **Tasks** shows TASKS.md in large type with its icons, and a click opens a task's
details. **History** shows every entry newest first, filtered by kind, status, dates, words, rule referenced,
tag, subfolder and session, with a click opening the whole entry. **Candidates** shows this project's rule
candidates by status.

`rules.py view` starts a small server in its own process on 127.0.0.1, using only the standard library, and
opens the page. The page asks every two seconds whether the project's records changed, from file sizes and
times, and redraws in place, keeping filters, open entries and the tab. The server stops three minutes after
the last request, a margin over the once-a-minute timers a browser allows a hidden tab. A second `view` for the
same project reuses the running server. The page is built from `web/` in memory and only reads.

**Which project, with no folder:** the rule-router hook records, per session, the project of the last file the
session touched, so an instance working in `Adapt` just runs `rules.py view`.

