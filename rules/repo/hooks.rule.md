RULE repo/hooks - what each hook in .claude/hooks/ enforces.
- rule_router.py (PreToolUse): injects rules whose gate matches path or command, once per session and again when a rule's text changes; logs to .claude/rules-firings.jsonl; reminds once when a changed project goes unlogged; announces answers sent from the viewer.
- guard_records.py (PreToolUse): refuses direct access to HISTORY.jsonl, TASKS.md, QUESTIONS.jsonl and candidates.jsonl, and prints the commands.
- guard_docs.py (PreToolUse): refuses any CLAUDE.md, and modification of an EXISTING README.md. ask_rule_approval.py (PreToolUse): asks the user before a new rule, an approval, or an edit or move the audit did not flag.
- post_write_checks.py (PostToolUse): renames a stray CLAUDE.md, checks every rule against the 10-line and 2048-byte cap, re-syncs rules/INDEX.md.
- Handoffs: announce_handoff.py (SessionStart), gate_handoff_read.py, handoff_skills.py, block_handoff_write.py, handoff_registry.py; shared parsing handoff_lib.py. What they enforce: lifecycle/handoff.
- Search: query_log.py surfaces an ask.py answer; query_opened.py records which hit was opened: writing/query-log. Tools: tools_path.py (SessionStart) puts tools/bin first on Bash PATH; graphify_nudge.py passes graphify's graph nudge only for code searches, reworded; rtk's own hook rewrites Bash commands.
- _bootstrap.py puts .claude/skills/rules-system/scripts on sys.path. Every hook FAILS OPEN on bad input.
- NEVER add a gate matching a path under .claude/skills/. Skill work stays siloed; rules_lib drops such a gate.
- Tests: python .claude/hooks/test_hooks.py, test_ask_rule_approval.py, test_block_handoff_write.py, test_graphify_nudge.py. Registration: .claude/settings.json.
