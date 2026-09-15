RULE repo/no-claude-md - no CLAUDE.md of any kind, at any path. Rules replace it.
- Never create CLAUDE.md or CLAUDE.local.md. guard_docs.py refuses the write; post_write_checks.py renames a stray one to CLAUDE_banned.md; settings deny both.
- Why: an always-loaded file is paid for on every request whether relevant or not. A rule is loaded only when its gate matches what you touch.
- Conventions go in rules/<area>/<slug>.rule.md with a gate in rules/INDEX.md. Never in .claude/rules/: that folder is auto-loaded exactly like CLAUDE.md.
- A fact about one folder goes in a rule named by that folder's README, or in its HISTORY.jsonl: writing/readme-and-rules.
