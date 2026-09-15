# rules INDEX - which rule fires on which path

Every rule in `rules/<area>/[<group>/]<slug>.rule.md` is at most **10 lines and 2048 bytes**, is injected only
when a gate below matches the path (or shell command) a tool is about to touch, and is injected
**once per session**, and again, marked CHANGED, if its text is edited later in that session. Rules and
gates are read fresh on every tool call, so nothing needs a reload. There is no `CLAUDE.md`: this index
and the rules it gates replace it.

**Rule files carry NO frontmatter, and nothing here is ever loaded automatically.** A rule's gate
lives in this file and nowhere else, so a rule file is inert data until the router injects it. The
folder is `rules/` at the repo root rather than `.claude/rules/` precisely because the latter IS an
auto-loaded memory location in Claude Code, which would defeat the whole arrangement.

**Gate line format:** `- **<area>/<slug>.rule.md** | <backticked triggers> | what it says`
A trigger prefixed `cmd:` is a regex matched against Bash/PowerShell command text instead of a path.
In a glob, `**` crosses directories and a bare `*` does not. The last field is the rule's GIST: search
indexes it, so write it in the words someone looking for the rule would use.

**No gate may match a path under `.claude/skills/`.** Skill work stays siloed.
`rules_lib.load_gates()` drops such a gate rather than honouring it.

Areas: `writing/` how this repo writes things down; `lifecycle/` documents that expire; `repo/` the repo
and its own machinery. Add an area by adding a folder: discovery is recursive.

Machinery: `.claude/skills/rules-system/` - run `scripts/rules.py help` for every command.
Hooks: `.claude/hooks/`, listed in `repo/hooks`. Firing log: `.claude/rules-firings.jsonl`, summarised by `rules.py stats`.

## Path and command gates

- **writing/readme-and-rules.rule.md** | `**/README.md`, `rules/**/*.rule.md`, `rules/INDEX.md` | a README is rule paths then a short orientation; rule files cap at 10 lines / 2048 bytes; where a folder fact goes
- **writing/compressed-register.rule.md** | `**/HANDOFF*.md`, `rules/**/*.rule.md` | handoffs, history lines and rules are written compressed, never in ultra
- **writing/fact-ownership.rule.md** | `**/docs/**`, `**/NOTES.md`, `**/README.md` | every fact is written once, in the document that owns it; everywhere else a pointer
- **writing/history-log.rule.md** | `**/HISTORY.jsonl`, `cmd:HISTORY\.jsonl`, `cmd:rules\.py\W+(history|init)\b` | a project's record of findings, decisions and changes: written by history add, read in slices, never by hand
- **writing/tasks.rule.md** | `**/TASKS.md`, `**/QUESTIONS.jsonl`, `cmd:TASKS\.md`, `cmd:QUESTIONS\.jsonl`, `cmd:rules\.py\W+(tasks|view)\b` | a project's live task window and its questions for the user, written only by command; the viewer opens without a word and takes the questions while it is open
- **writing/viewer-replies.rule.md** | `**/TASKS.md`, `**/QUESTIONS.jsonl`, `cmd:rules\.py\W+(tasks|view)\b` | the user answered in the viewer or marked an action done there: respond through the viewer's records, never in chat, unless the viewer cannot carry it
- **writing/rule-candidates.rule.md** | `**/HISTORY.jsonl`, `cmd:rules\.py\W+(park|decide|candidates)\b` | park a possible new rule, recorded in its folder and the master copy; approve or reject it past one embedding pass
- **writing/query-log.rule.md** | `**/QUERIES.jsonl`, `cmd:ask\.py` | what was asked and what came back; a record, never a task list
- **lifecycle/handoff.rule.md** | `**/HANDOFF*.md`, `cmd:handoffs\.py` | a handoff is written once, read once, then retired into the handoff skill's data folder
- **lifecycle/archive-folders.rule.md** | `**/archive/**` | finished business; not a task list; never edited, never imported
- **repo/rule-lifecycle.rule.md** | `rules/**`, `cmd:rules\.py\W+(move|audit|reconcile|decide)\b` | how a rule is observed, created, changed, moved and deleted, and who is asked first
- **repo/no-claude-md.rule.md** | `**/CLAUDE*.md`, `.claude/rules/**`, `cmd:CLAUDE\.md` | no CLAUDE.md of any kind; conventions live in gated rules instead
- **repo/hooks.rule.md** | `.claude/hooks/**`, `.claude/settings*.json` | what each hook enforces, and the one gate that may never exist
- **repo/automatic-checks.rule.md** | `rules/**/*.rule.md`, `rules/INDEX.md` | what already runs on a write: the rule cap, the index re-sync, the CLAUDE.md sweep
- **repo/dependency-direction.rule.md** | `.claude/hooks/**`, `cmd:(?i)\bimport\b.*skills` | project code may depend on a skill; a skill never depends on the project or a sibling skill
- **repo/vector-search.rule.md** | `**/*.py`, `**/*.md`, `cmd:vector-search` | search rules, history and skill code by meaning: does a tool exist, is there a rule for this, was this already tried
- **repo/no-silent-changes.rule.md** | `**/HISTORY.jsonl`, `cmd:(?i)\b(mv|move-item|rename-item|rm|rmdir|remove-item|shutil\.(move|rmtree|copytree)|os\.(rename|replace|remove|unlink))\b`, `cmd:rules\.py\W+move\b` | log every move, rename, deletion or lasting edit in the project it touched, even one that is not yours

## README triggers

Generated from each folder's README by `rules.py sync`. Do not edit by hand.

<!-- BEGIN GENERATED readme-triggers -->

<!-- END GENERATED readme-triggers -->
