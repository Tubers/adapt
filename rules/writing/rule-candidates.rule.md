RULE writing/rule-candidates - a new rule starts as a parked candidate, recorded twice, decided against one embedding pass.
- Name the rule set: --repo <this repository's folder name>, or once per session: rules.py use <name>. Park at the moment of insight: rules.py park "<fact>" --in <folder> --no-run WHY (or --run <run folder> where a project keeps runs).
- Parking stamps time and session and writes the same line, pending, to <folder>/HISTORY.jsonl AND .claude/skills/rules-system/data/<repo>/candidates.jsonl. A candidate is never guidance.
- From a cold start: rules.py candidates next gives the oldest pending one, a fresh pass and the decide commands. Never open candidates.jsonl or a HISTORY.jsonl directly.
- rules.py decide <id> approve --rule <area/slug>, after writing and gating that rule; or reject --reason WHY. Both copies change together.
- NOT NEW: refused while ANOTHER rule says it at 0.80. Fold it in, or --overlap-ok WHY. SAME SUBJECT at 0.70: read each line, then --agrees.
- A subject fact may be contradicted only with --contradicts <rule> --proof <entry id>, once the old rule is corrected. WORK PROCEDURE never: writing/, lifecycle/, repo/, tooling/.
- SCOPE comes from the same pass. The gate always reaches the fact's folder; widen only on evidence. Nothing near: NICHE, folder-gated, found by search.
- The pass cannot run: approval refused unless --unchecked WHY.
