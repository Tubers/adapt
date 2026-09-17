# Knowledge upkeep

```bash
rules.py upkeep            # brief: indexes behind, runs without their entry, broken history, stale candidates
rules.py upkeep --full     # plus reconcile, code folders with no README, results files out of layout
rules.py upkeep --stats    # how long runs wait for their entry, how they close, what candidates became
```

A state report, never a task list, and never run unprompted: nothing runs unscoped at session start. It is
run before a handoff is written (Step 5 of the handoff writing doc) and whenever a session wants it.

| class | brief | reports |
|---|---|---|
| INDEX | yes | a vector-search index built before its corpus changed, from `index.py --status`, which loads no model |
| RUN | yes | a run stamped after 2026-09-12 with no RESULTS.md, no history entry naming it, or an entry closed by neither a rule, a candidate nor a `no_rule` reason |
| HISTORY | yes | a line that is not JSON, lacks `id`/`ts`/`kind`/`title`, has an unknown kind; a candidate whose two copies disagree or whose decision is incomplete |
| CANDIDATE | yes | a candidate pending more than 7 days |
| RULES | full | everything `reconcile` reports |
| FOLDER | full | a live folder holding code with no README.md |
| RESULTS | full | a RESULTS.md outside `test_runs/<scenario>/runs/<stamp>/` |

Runs before 2026-09-12 are never listed: 273 predate the check and history was written retroactively.
A class that cannot run says SKIPPED and why. Silence always means checked and clean.
