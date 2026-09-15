RULE repo/automatic-checks - what already runs without you asking.
- On every rule-file write, post_write_checks.py checks the 10-line and 2048-byte cap and re-syncs the generated README section of rules/INDEX.md. It reports; read its output.
- It also renames any CLAUDE.md written anywhere: repo/no-claude-md.
- The records (HISTORY.jsonl, TASKS.md, QUESTIONS.jsonl, candidates.jsonl) are checked by the commands that write them, never by hand: rules.py upkeep reports drift.
- Nothing checks a rule's CONTENT. rules.py reconcile finds dead gates and orphans; rules.py audit finds duplicates and misfiling.
- Which hook enforces what: repo/hooks.
