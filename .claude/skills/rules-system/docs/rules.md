# How the rule system works

Maintainer reference, moved out of SKILL.md on 2026-09-13. SKILL.md is the index.

## What changed, and why

Before 2026-09-09 this repo's conventions lived in two places, and both were the wrong shape:

| where | problem |
|---|---|
| `CLAUDE.md`, 28 KB | loaded into **every** session and every sub-agent, whether or not any of it was relevant. Paid for on every request. |
| 92 free-text `README.md` files, 367 KB | free, but optional. Nobody was obliged to read one, and a session once picked up an archived, finished experiment as a task list because it had not. |

The rule system inverts both halves. Conventions are cut into small rule files, and a rule reaches a
session **only when a path gate matches what a tool is about to touch** - at which point it is
compulsory rather than skimmable, because it arrives as injected context rather than as a file
someone might open.

```
rules/INDEX.md              the gate table (hand-maintained) + the README map (generated)
rules/<area>/<slug>.rule.md         one rule. HARD CAP 10 lines and 2048 bytes.
rules/<area>/<group>/<slug>.rule.md the same, one level deeper, when a subject needs several rules
<folder>/README.md          ONE line: the path of the rule file that folder triggers
.claude/rules-firings.jsonl what actually fired, and which gate pulled it in
AMALGAMATED_DOCS.md         the full original text of CLAUDE.md and all 92 READMEs, archived
.claude/_backup/docs-2026-09-09/   byte-identical copies of those files at their original paths
```

## Nothing here is auto-loaded, and there is no frontmatter

A rule file is **inert data**. It has no frontmatter, declares nothing about itself, and is read
only when `rule_router.py` decides a gate matched. If you want to know what a rule will do, the
answer is in `rules/INDEX.md`, never in the file.

**The folder is `rules/` at the repo root, not `.claude/rules/`, and that is deliberate.**
`.claude/rules/` is an auto-loaded memory location in Claude Code - files there are pulled into
every session exactly the way `CLAUDE.md` was. Putting the rules there would rebuild the problem
this replaced. If you ever move them, do not move them there.

## The areas

Three to start, chosen so that a rule's gate and its folder usually agree. The folder is part of the rule's
name: `writing/tasks.rule.md`, and that string is what gates, README stubs and the firing log use.

| area | what it covers |
|---|---|
| `writing/` | how this repo writes things down: ownership, register, records, tasks |
| `lifecycle/` | documents that expire or are finished: handoffs, archives |
| `repo/` | the repo and its own machinery: hooks, rules, search, dependency direction |

Adding an area, or a group inside one, needs no code change: discovery is recursive and a rule's
name is simply its path under `rules/`. Group a subject once it needs more than two or three rules.
One rule owns one topic, and a one-off fact gets its own small rule rather than a paragraph inside
a larger one.

## The parts, and which file owns each

| part | file | what it does |
|---|---|---|
| library | `scripts/rules_lib.py` | glob-to-regex, gate parsing, match provenance, README discovery, session memory, firing log, index sync, budget check |
| CLI | `scripts/rules.py` | every maintenance command, `help` first |
| upkeep | `scripts/upkeep.py` | the knowledge-upkeep classes, their output, the session-start log |
| history | `scripts/history.py` | write stamped HISTORY.jsonl entries, read slices, folder state, the one in-place key change |
| candidates | `scripts/candidates.py` | park, queue and decide rule candidates; the newness, contradiction and scope checks |
| after-run prompt | `.claude/hooks/prompt_after_run.py` | PostToolUse. When an orchestrator run returns, asks for its history event and any candidate |
| injector | `.claude/hooks/rule_router.py` | PreToolUse. Matches, injects once per session, appends to the firing log |
| guard | `.claude/hooks/guard_docs.py` | PreToolUse. Refuses any `CLAUDE.md`; refuses modification of an **existing** `README.md`; allows creating a new one |
| post checks | `.claude/hooks/post_write_checks.py` | PostToolUse. Renames a stray `CLAUDE.md` to `CLAUDE_banned.md`, enforces the rule budget, re-syncs the index |
| bootstrap | `.claude/hooks/_bootstrap.py` | puts `scripts/` on `sys.path` for the hooks, and fails open if it cannot |
| settings | `.claude/settings.json` | registers the hooks, sets `outputStyle`, hides every skill from the model |
| permissions | `.claude/settings.local.json` | denies `Write`/`Edit` on `**/README.md` |

## The one gate that may never exist

**No gate may match a path under `.claude/skills/`.** Sub-agents that edit, extend and repair those skills have contexts that are meant
to be silos. A rule about repo documentation conventions arriving mid-way through a skill repair is
noise at best, and at worst it widens the agent's scope.

This is enforced in code, not by convention: `rules_lib.load_gates()` **drops** any gate whose
pattern contains the skills prefix, so an accidental entry in `rules/INDEX.md` is refused rather
than honoured. Both suites assert it, and `rules.py which` will show you the silence directly.

## The budget, and why it is hard

10 lines and 2048 bytes per rule file. A rule is injected **in full** every time its gate matches,
so an unbounded rule is an unbounded tax on every session that touches those paths. When a rule
outgrows the cap, the answer is never a longer rule:

1. cut examples, prose, tables, and anything a competent reader infers;
2. move what will not fit into the folder's own `docs/`, and point at it from the rule;
3. if it is really two rules, split it and give each its own, narrower gate.

`post_write_checks.py` reports a violation and asks for a rewrite. It never truncates anything.
`rules.py budget` is the same check on demand.

## Writing a good gate

**As niche as the rule.** A gate that fires everywhere costs what `CLAUDE.md` cost. Prefer a
filename or an extension over a directory, and a directory over a top-level prefix.

```
- **<area>/<slug>.rule.md** | `<trigger>`, `<trigger>` | one line on what it says
```

- `**/` crosses directories, a bare `*` does not. `docs/*/README.md` will not match
  `docs/a/b/README.md`, which is deliberate - shallow gates must not leak into deep folders.
- A trigger prefixed `cmd:` is a **regex** matched against Bash/PowerShell command text instead of
  a path. `cmd:\bgit\b` is how the no-version-control rule reaches a session.
- A rule may NAME a skill as a reference, but must tell the instance to ask the user to run it.
  Every skill is `user-invocable-only` here, so the model cannot load one. A rule that says
  "invoke X" is an instruction that cannot be followed. See Skill visibility below.

**Check your work with `rules.py which <path>`.** It runs the real matcher and prints every rule
that would fire and the gate that pulled each in. It is the fastest way to find a glob that is
wider than you meant.

## Observing what is actually happening

`rule_router.py` appends one line to `.claude/rules-firings.jsonl` per injection, recording the
rule, **the gate that matched**, what it matched, the tool and the session. `rules.py stats` reads
that back.

The provenance is the point. Without it an over-broad glob and a genuinely universal rule look
identical from the inside, and a gate that stopped matching because a folder was renamed is
completely silent. Two questions it answers that nothing else can:

- **which gates are doing the work** - if one glob accounts for most firings, it is probably too
  wide, or the rule behind it belongs in more than one place;
- **which gates have NEVER fired** - a failure `reconcile` cannot see, because a gate can match
  files on disk and still never be reached in real work.

A never-fired gate is not automatically wrong. `**/HANDOFF*.md` will not fire until someone writes a
script. Read it as a question, not a defect.

The log is trimmed to its newest half once it passes 4000 lines, so it never needs pruning by hand.
Deleting it is safe and simply resets the counts.

## Running the scripts

```bash
python .claude/skills/rules-system/scripts/rules.py help          # every command
python .claude/skills/rules-system/scripts/rules.py which <path>  # what would fire here
python .claude/skills/rules-system/scripts/rules.py stats         # firings, and what never fires
python .claude/skills/rules-system/scripts/rules.py reconcile     # audit
python .claude/skills/rules-system/scripts/rules.py test          # both suites
python .claude/skills/rules-system/scripts/rules.py audit         # the refactoring pass
python .claude/skills/rules-system/scripts/rules.py upkeep --full # has knowledge fallen behind its homes
python .claude/skills/rules-system/scripts/rules.py move <rule> <new-name> [--dry-run]  # refile a rule
```

`sync_index.py` and `reconcile.py` still exist as standalone scripts because the hooks and the
documentation name them directly; `rules.py` dispatches to the same code rather than duplicating it.

`reconcile` exits non-zero when it finds a problem, so it can be wired into a check. It reports:

| class | meaning |
|---|---|
| **dead glob** | a gate matches nothing on disk. Either the path moved or the gate has a typo. |
| **orphan rule** | a `.rule.md` no gate and no README references. It can never be injected. |
| **unpaired README** | a README naming a rule file that does not exist, or naming nothing at all. |
| **malformed README** | more than one line, or a line that is not a rule path. |
| **skill gate** | a gate aimed at the skills directory. Dropped at load time, so it silently never fires. |
| **over budget** | a rule past 10 lines or 2048 bytes. |
| **headline** | a rule whose first line names a different path than the file it sits in. Every instance so far came from a regroup whose rename was applied to names that already carried the prefix, and it is invisible in normal use because nothing reads the headline. |

## Self-containment

The repo's own rule is that a skill must survive `delete everything except this folder`. This one
does: `rules_lib.py` imports only the standard library, and `run_tests.py` builds its fixtures in a
temp directory rather than reading the repo. The hooks import **from** here, which is the allowed
direction - repo-side code may read a skill; a skill may never read the repo.

`rules.py test` also runs `.claude/hooks/test_hooks.py`, which is repo-side by nature because it
drives the real hooks. If the repo is gone that one is reported MISSING rather than skipped
silently.

## Skill visibility

**Every skill is `user-invocable-only`: hidden from the model completely, and typable by the user as
`/name`.** No skill name and no skill description reaches a session, which is the whole point - that
listing was per-prompt injection paid for on every request.

The consequence is real and worth stating plainly: **the model cannot load a skill, and neither can
a sub-agent.** The three specialist agents can no longer pull in their reference skills on their
own. Rules therefore name a skill and tell the instance to ask for it, rather than pretending it can
be invoked.

There is no middle setting. The Skill tool validates a name against the listing, so anything hidden
from the listing is also unreachable; `name-only` would restore model invocation at the cost of
listing 21 names on every request. If one sub-agent's reference skill turns out to be needed often,
set that ONE skill to `name-only` rather than changing the policy.

The `off` entries are bundled skills switched off before this refactor. They are invocable by
nobody, including the user.

**Two exceptions, both `name-only`: vector-search and rules-system.** Every session records history,
parks candidates and searches rules, so both are core to how work is done here rather than reference
material, and a session must be able to find them by name.

## If you need to turn it off

Remove the three hook entries from `.claude/settings.json`. The rule files, the READMEs and the
index are inert data on their own; nothing else in the repo imports them.
