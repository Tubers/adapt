# Internals: the record, the hooks, the tests

Read this when maintaining the machinery. Nobody writing, reading or reviewing a handoff needs it.

## Layout

```
.claude/skills/handoff/
    SKILL.md            router: which audience reads which doc
    docs/               writing.md, reading.md, review.md, answering.md, this file
    scripts/            handoffs.py (CLI), handoff_data.py (paths and states), run_tests.py
    data/               log.jsonl, plus one folder per occasion
        <date>-<scope>/ HANDOFF.md, optionally REVIEW.md, optionally RESPONSE.md
```

An occasion is `<date the handoff was written>-<scope slug>`. One to three files, nothing else.

| file | who writes it |
|---|---|
| `HANDOFF.md` | `handoffs.py retire`, byte for byte, never touched again |
| `REVIEW.md` | `handoffs.py draft` opens it; the reader fills it in place |
| `RESPONSE.md` | `handoffs.py respond` |

`REVIEW.md` with no `RESPONSE.md` beside it is a debt. `handoffs.py pending` prints it with the
session that wrote that handoff, its opening words from that session's transcript, and the
`claude --resume` line.

**Never place a file in `data/` by hand.** The scripts own those paths. Before 2026-09-11 handoffs
were filed by hand into one project's archive folder, which put repo-wide handoffs inside
one mechanic's folder and drifted apart.

## States

| state | means |
|---|---|
| `retired` | handoff alone: read, filed, no feedback offered |
| `pending_author_review` | a review is waiting on the session that wrote it |
| `closed` | that session answered |

## The log

`data/log.jsonl`, append-only, one JSON object per event: `written`, `retired`, `reviewed`,
`answered`, and `located`. `written` is the important one, because it carries the author's `session`
id, the `transcript` path, and the `path` the handoff lived at. The session id is knowable only at
the moment of writing, which is why a hook records it rather than a person.

**The live path is kept deliberately.** A handoff's folder says what it hands off, so losing it
loses half the meaning. `origin_of` prefers a `located` record, then `written.path`, then the path
`retire` moved the file out of. `located` exists for corrections: the three handoffs migrated on
2026-09-11 had their archive path logged as their origin, and a `located` record fixed each to the
project path they were written at. The chart shows it as LIVED IN.

`HANDOFF_DATA_DIR` redirects the whole record elsewhere. It exists so the hook tests can drive the
real hooks without appending to the real log. Nothing in normal use sets it.

## Hooks

| hook | event | job |
|---|---|---|
| `announce_handoff.py` | SessionStart | scans a pruned tree, announces every live handoff, says announcement is not assignment |
| `gate_handoff_read.py` | PreToolUse | asks the user before any read of a live handoff or shell command naming one |
| `block_handoff_write.py` | PreToolUse | refuses every modification of a handoff; permits moves judged by destination |
| `handoff_skills.py` | PostToolUse on Read | loads the `SKILL.md` of each skill the handoff's front matter lists |
| `handoff_registry.py` | PostToolUse | logs the author at write time; notices retirement, review and answer by comparing folders against the log |

Live versus retired is decided in `.claude/hooks/handoff_lib.py`: a live handoff is named exactly
`HANDOFF.md` and sits outside any `archive`, `_backup` or `.claude` folder. A retired one keeps the
name but sits under `.claude/skills/handoff/data/`, so it never matches.

Hooks fail open and silent. A record that cannot be written is worth less than a session that cannot
work, and `handoffs.py check` reports whatever the log missed.

## Tests

```
python .claude/skills/handoff/scripts/run_tests.py     # 38 checks: naming, states, CLI, check
python .claude/hooks/test_hooks.py                     # includes announce and registry
python .claude/hooks/test_block_handoff_write.py       # the write guard
```

Both skill-side suites build fixtures in a temp folder and read nothing from the repo, so the skill
survives `delete everything except this folder`. Repo-side hooks import the skill, which is the
allowed direction; the skill never imports the repo.

## Where the conventions live for a session that loads no skill

`rules/lifecycle/handoff.rule.md`, gated on `**/HANDOFF*.md`. It carries placement, the assignment
rule, retirement through the script, and the review loop in ten lines.
