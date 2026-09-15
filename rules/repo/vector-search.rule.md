RULE repo/vector-search - rules, project history and every skill's docs and code are searchable BY MEANING. Use it on a low bar.
- Skill /vector-search is instance-invocable: only its NAME is listed per request; this rule is its description, paid for once.
- Direct: python .claude/skills/vector-search/scripts/search.py "question in plain words", or --file <path>. --history asks what the project already did; --skill <name|all> searches a skill's own docs and code.
- SEARCH BEFORE: building any tool or helper, writing a new rule, claiming something is untested or impossible, working in an unfamiliar folder, or typing a number, id or constant from memory.
- A hit is a POINTER: rule name, its gate, the matching line. OPEN rules/<name> before acting. Never act on the printed line alone.
- "Nothing close" is a real answer. The floor is deliberate: a retriever that always finds something is worse than one that admits it found nothing.
- It cannot replace a gate. Rules that carry expensive traps still arrive by path gate; search is for the niche tail.
- After editing rules: python .claude/skills/vector-search/scripts/index.py, or --ns all after history changes. It re-embeds only what changed.
- A rule search cannot find is fixed by widening its GIST in rules/INDEX.md, never by padding the rule body.
