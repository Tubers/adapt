---
name: rules-system
description: The repo's knowledge machinery - path-gated rules, each folder's HISTORY.jsonl and TASKS.md, rule candidates, and the upkeep and refactoring reports. Every record is written by command. Start with rules.py help.
---

# rules-system

Conventions live in small rule files under `rules/`, and a rule reaches a session only when a gate in
`rules/INDEX.md` matches what it is touching. Every folder with its own agenda keeps its own
`HISTORY.jsonl` (what happened) and `TASKS.md` (what is next). A fact that may become a rule is parked
as a candidate and approved or rejected against one embedding pass.

**Nothing in those records is written by hand.** Every write is a command below. Every command that
reads or writes candidates names its rule ecosystem: `--repo <repo>` for this repository.

`/rules-system <args>` runs `python .claude/skills/rules-system/scripts/rules.py <args>` and reports what
it prints. **`/rules-system` alone, or `rules.py help`, lists every command; `help <command>` explains one.**
**`view` is the exception: once the page opens, say nothing at all.** Speak only if it failed. (The user, 2026-09-13.)
**While a viewer is open, questions for the user go to it, not to chat:** `tasks ask <task> "<q>"`, answered in the
page's reply box, read back with `tasks answers`. `view --status` says whether one is open. (The user, 2026-09-14.)

## Commands

All are `python .claude/skills/rules-system/scripts/rules.py <command>`.

| command | what it does |
|---|---|
| `help [command]` | every command, or the detail for one |
| `use [<name\|folder> \| --clear]` | set this session's rule set once; every later command of both skills follows it |
| `history <folder> [runs\|findings\|changes\|...] [--last 5\|--first 5]` | a folder's history in slices, one line each, opening with the folder's state |
| `tasks [show\|add\|start\|done\|block\|unblock\|drop\|detail\|goal] [--in F]` | read or change a project's TASKS.md; the only way it is written |
| `tasks ask <task> "<q>"` / `answer <q> "<a>"` / `questions` / `answers` | a project's questions for the user; `answers` logs each answer as a decision and removes it |
| `tasks act <task> "<what to do>"` / `acted <a> ["<note>"]` | an action only the user can do; the task shows ❗ until the user marks it done; `answers` logs it as a note |
| `init <folder> --goal G` | start a project: HISTORY.jsonl, TASKS.md, QUESTIONS.jsonl |
| `view [folder]` | a project's tasks, history and candidates as one live browser page; no folder needed inside a project |
| `history show <id>` | one history entry in full |
| `history add <folder> --kind K --title T ...` | write one stamped history entry; the only way entries are made |
| `park "<fact>" --repo <repo> --in <folder> --run <run>` | park a possible rule in its folder and the master copy, with the embedding pass |
| `candidates --repo <repo> [next\|--all]` | pending candidates; `next` gives the oldest, freshly checked, with the decide commands |
| `decide <id> approve\|reject --repo <repo> ...` | approve a candidate into its rule, or reject it; set in both copies |
| `upkeep [--full\|--stats]` | where knowledge has fallen behind its homes |
| `which <path>` | which rules would fire on a path, and the gate that pulls each in |
| `show <rule>` / `list [area]` / `gates [area]` | read a rule, the rules by area, the gate table |
| `audit [--gates]` | the refactoring pass: text checks, then facts, dupes, coherence, hubs, coverage |
| `facts` / `dupes` / `coherence` / `hubs` / `coverage` / `asked` | one refactoring report on its own |
| `move <rule> <new-name>` | refile a rule and rewrite every reference to it |
| `accept <kind> ... --why` | keep a reviewed refactoring finding out of later reports |
| `stats` / `log [n]` | what rules fired, and what never has |
| `reconcile` / `budget` / `sync` | dead gates and orphans; rule sizes; regenerate the README map |
| `test` | the library and hook suites |

## Files

| path | what it is |
|---|---|
| `scripts/rules.py` | the CLI; every command above |
| `scripts/rules_lib.py` | gate parsing and matching, README discovery, firing log, index sync, budget |
| `scripts/history.py` | stamped HISTORY.jsonl writes, slices, folder state, the one in-place key change |
| `scripts/candidates.py` | park, queue and decide; the newness, contradiction and scope checks |
| `scripts/upkeep.py` | the upkeep classes and `--stats` |
| `scripts/tasks.py` | the frozen TASKS.md format: parse, check, write, the tasks commands and init |
| `scripts/questions.py` | QUESTIONS.jsonl: ask, answer, and consuming answers into history |
| `scripts/audit_worklist.py` | the rules the last audit flagged, which the rule-approval hook lets through unasked |
| `scripts/viewer.py` | `view`: which project, the page's data, the live local server, `--static` |
| `web/view.html`, `view.css`, `view.js` | the viewer page, joined into one page in memory |
| `scripts/accepted.py` | the accepted-findings list for the refactoring reports |
| `scripts/reconcile.py` | the dead-gate, orphan and README audit |
| `scripts/sync_index.py` | regenerates the README section of `rules/INDEX.md` |
| `scripts/run_tests.py` | the library suite, in temp folders |
| `data/<repo>/candidates.jsonl` | the master copy of this repository's rule candidates |
| `data/<repo>/audit-worklist.json` | written by `audit`; rules on it may be edited or moved without asking for 24 hours |
| `data/<repo>/accepted.json` | refactoring findings read and kept on purpose |
| `docs/rules.md` | how the rule system works: areas, budget, gates, observing, visibility, hooks |
| `docs/refactoring.md` | the audit and its reports, `move`, accepted findings |
| `docs/records.md` | history commands, rule candidates, `--repo`, the cosine pass |
| `docs/upkeep.md` | the upkeep classes |
