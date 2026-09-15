RULE repo/dependency-direction - project code may depend on a skill. A skill may NEVER depend on the project.
- A skill is self-contained inside .claude/skills/<skill>/: its scripts, docs, tests and data.
- Test: delete everything except .claude/skills/<skill>/ and that skill must still run and pass every one of its own tests with nothing SKIPPED.
- Forbidden: a skill importing project code, and a skill importing a sibling skill. Cross-skill work goes through a subprocess and a documented contract, as rules-system reaches vector-search.
- Hooks are project-side: a hook may import a skill's library (hooks/_bootstrap.py does), never the reverse.
- Anything spanning two skills lives in project code that calls both. It never becomes a skill of its own by default.
