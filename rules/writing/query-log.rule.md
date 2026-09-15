RULE writing/query-log - QUERIES.jsonl records what was ASKED. It is not a task list.
- Beside HISTORY.jsonl, the same shape: append-only JSONL, read by tooling, not by eye. HISTORY says what HAPPENED, QUERIES what was asked and what came back.
- NOTHING in it is open work. A question here was answered when it was asked.
- Write one with python .claude/skills/vector-search/scripts/ask.py "question", which searches, prints, and appends the question and its answer. Never hand-edit the file.
- Read one with qlog.py digest <folder>: one line per question and its top hit.
- Every answer line carries ns, floor, model fingerprint and index_built, so a bad answer can be told from a stale-index answer.
- A question that returned NOTHING is the useful kind: it names a gist gap or a missing rule: repo/vector-search.
