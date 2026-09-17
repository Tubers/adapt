RULE writing/history-log - HISTORY.jsonl is THE record of a PROJECT folder's work. Every project keeps one; none is central.
- COMMANDS ONLY: never open, read, grep, edit, move or delete it directly; a hook refuses and lists the commands. Write: rules.py history add <folder> --kind finding|decision|change|dead-end|note|run --title "<t>" [--result R] [--evidence P] [--refs R] [--no-rule WHY]. It stamps id, time and session.
- Read in slices, never whole: rules.py history <folder> [findings|changes|decisions|dead-ends|notes|candidates] [--last 5|--first 5|--all] [--since YYYY-MM-DD] [--grep WORD]; history show <id>. A folder slice opens with the folder's state.
- A project is a folder whose .rs folder holds HISTORY.jsonl, TASKS.md and, unless started with --no-questions, QUESTIONS.jsonl; old layouts move with rules.py migrate. Start one with rules.py init <folder> --goal G, the repo root included (init .). Projects nest: records go to the nearest project file up the path; a sub-project names its parent task: init <sub> --task <id>. Work in a subfolder goes into its project's file, tagged with the subfolder.
- NO SILENT CHANGES: every move, rename, deletion or lasting edit is logged: repo/no-silent-changes.
- Append-only. Correct an entry with a new one naming it in --supersedes. Only exception: a candidate's status and reason, set by rules.py decide.
- A fact that holds beyond its folder is a rule candidate: writing/rule-candidates. Narrow facts stay here as findings.
- Browse it: rules.py view. Every flag: rules.py help history.
