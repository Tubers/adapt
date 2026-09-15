RULE writing/readme-and-rules - README shape, and where a folder fact goes.
- SHAPE: one or more rule paths, one per line, then a blank line, then at most 10 lines of orientation. Machinery reads the paths; orientation is for whoever opens the folder.
- ORIENTATION is what the folder IS, what sits in it, and how to run it. Never a finding, never a number, never a history.
- MULTIPLE rule lines are the point. Put the rule shared by that CLASS of folder first, then any rule peculiar to this one.
- A FINDING goes in a rule. An EVENT or decision goes in the project's HISTORY.jsonl: writing/history-log.
- Rules live in rules/<area>/[<group>/]<slug>.rule.md, carry NO frontmatter, and are inert until a gate in rules/INDEX.md matches.
- HARD CAP per rule: 10 lines AND 2048 bytes. post_write_checks.py enforces the cap and the README shape on every write.
- Curate. Rule context is compulsory and paid on every match: bullets only, no prose, no examples, no decorative tables.
- Creating, changing, moving and deleting a rule: repo/rule-lifecycle. Every command: .claude/skills/rules-system/scripts/rules.py help.
