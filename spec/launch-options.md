# How the Adapt manager should be launched: a comparison

This document compares the ways the Adapt manager session can be started, against the criteria this
skill has settled on. It exists because the choice is hard to reverse cheaply once specialists,
records and scripts are built around it, and because most of the differences only show up in
failure, cost or isolation rather than in whether the thing runs at all.

Everything here comes from the Claude Code documentation (the `headless`, `cli-reference`,
`agent-view`, `cross-session-messaging`, `sessions`, `sub-agents`, `agent-teams`, `skills` and
`settings` pages), checked on 2026-09-15, plus the probe recorded in this project's history. Where a
point is untested or inferred, it says so.

## The criteria

The spec has already fixed what matters, so the comparison is against these and nothing else:

1. **Subscription login, not an API key billed directly.**
2. **The manager can spawn subagents**, and remains the only thing that does.
3. **Startup context is as small as possible**, for the manager and for every specialist.
4. **Context lives in files, rules and vector-search**, not in a long conversation.
5. **Isolation**: nothing from the host project or the personal configuration leaks in.
6. **It runs unattended**, since a round is started and then left alone.
7. **It is observable afterwards**, because the records are the product.
8. **It is swappable**, so a different launch can replace it without rewriting Adapt.

## The candidates

| Tag | Launch | One line |
|---|---|---|
| **A** | `claude -p "<round prompt>"` | One headless run per round. The default in the spec. |
| **B** | `claude -p --input-format stream-json` | One headless run per round, fed more than one message by a driver process. |
| **C** | `claude -p --resume <session-id>` | Headless, but continuing the manager's previous conversation each round. |
| **D** | `claude --bg "<round prompt>"` | A supervised background session that outlives the round. |
| **E** | Agent SDK (Python or TypeScript) | Adapt drives the agent loop as a library. |

An ordinary interactive session is not a candidate. It needs a terminal and a person in front of it,
which defeats criterion 6.

## Comparison

### What it is, and how it is driven

| | A | B | C | D | E |
|---|---|---|---|---|---|
| Driver | One shell command | A process that writes JSON lines to stdin | One shell command | One shell command, then a supervisor | Adapt's own program |
| Ends when | The turn ends | The driver closes stdin | The turn ends | You stop it, or it idles out | Your loop exits |
| Extra dependency | None | A small driver script | None | The supervisor, which Claude Code manages | The SDK package, Python or TypeScript |

### Authentication and billing

| | A | B | C | D | E |
|---|---|---|---|---|---|
| Subscription login | Yes | Yes | Yes | Yes | Not offered. The SDK documentation says Anthropic does not allow claude.ai login for agents built on the Agent SDK and directs you to API-key authentication |
| Quota | Counts against the subscription like any session | Same | Same | Each background session uses the subscription quota independently | API billing |

This alone puts E out of reach while the subscription is the requirement, and is the same reason
`--bare` was set aside.

### Lifetime and idle behaviour

| | A | B | C | D |
|---|---|---|---|---|
| Lives for | One round | One round, several messages | One round | Indefinitely |
| After the turn | Process exits | Waits for the next message on stdin | Process exits | Stays available; the supervisor stops the process after about an hour unattached and restores it on the next attach or reply |
| Crash | The round fails; rerun it | Same | Same | The supervisor restarts the process automatically, and state persists on disk through restarts and auto-updates |
| Background work at exit | A background subagent keeps `-p` open until it finishes, with a ten-minute idle ceiling by default (`CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS`) | Same | Same | Not applicable; the session does not exit |

### Startup context and token profile

| | A | B | C | D |
|---|---|---|---|---|
| Loaded at start | The workspace's configuration only, once per round | Same, once per round | Same, plus the whole prior conversation | Same, once, then kept |
| Grows over time | No | Within the round | Yes, every round adds to the transcript | Yes, within the session |
| Cache | A fresh cache each round | Warm within the round | The prior history is re-processed and re-cached on resume, at a cost that scales with its size | Warm while the process lives |
| Fits criterion 4 | Yes | Yes | No. It is the long conversation the spec rejects | Partly. The conversation persists whether or not it is used |

C also inherits the Pro and Max resume behaviour: a session idle for over an hour and over 100,000
tokens opens a dialog offering a summary instead of the full history, which a headless run cannot
answer.

### Cache warmth, and what actually keeps it

A fresh session per round sounds like a cold cache every time. It mostly isn't, and where it is, a
setting fixes it more cheaply than any polling scheme.

- **Every cache hit resets the TTL.** The cache expires only after a gap with no request that reads
  it.
- **The main conversation already gets a one-hour TTL** on a Claude subscription within the plan's
  included usage. Once usage passes the plan limit and draws on credits, Claude Code drops it to
  five minutes, and `promptCacheTtl` or `CLAUDE_CODE_PROMPT_CACHE_TTL` set to `1h` puts it back.
- **Subagents are in the other bucket and get five minutes by default**, even on a subscription.
  `subagentPromptCacheTtl`, the `CLAUDE_CODE_SUBAGENT_PROMPT_CACHE_TTL` variable, or a per-agent
  `experimental.cacheTtl` raises that to `1h`. A `1h` in the per-agent field is ignored while the
  subscription is drawing on usage credits.
- **Polling a subagent to keep its cache warm is the wrong tool.** The five-minute window is a
  default, not a law, and every poll costs a real request; the setting costs nothing. Nothing in the
  documentation says the timer needs input from a person: it is reset by any request that reads the
  cache.
- **A subagent never reads the parent's cache**, because its prefix is its own. A fork does, since
  it inherits the parent's prompt, tools and history exactly.
- **The cache is scoped to a machine and a working directory**, and each conversation also carries
  the git status snapshot taken at startup. So two rounds launched in the same workspace can read
  the same system-prompt and project-context prefix, as long as neither the configuration nor that
  snapshot changed between them. Parallel sessions in one directory share a cache; a worktree has
  its own working directory and therefore its own.

The practical reading for Adapt: statelessness costs the conversation layer, which is small and
which the spec wants discarded anyway, not the system prompt and project context, which are the
expensive parts and which a per-round session can still hit.

### Subagents

Every candidate can spawn subagents. The differences are small:

- A subagent may spawn its own subagents, three layers deep by default. Setting
  `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH=1` enforces the rule that only the manager spawns.
- Agent teams are unavailable in every `-p` candidate, and teammates cannot nest in any case.
- In D, a subagent inherits the background session's working directory, which is not the directory
  the session was started in. See the worktree row below.

### Multi-turn within one round

| A | B | C | D | E |
|---|---|---|---|---|
| One prompt. The manager must finish the round from a single instruction | Many messages, with `--max-turns` capping the agentic turns | One prompt per run, but the thread continues | Many messages, sent by attaching or by another session | Full control |

This matters only if a round needs the manager to come back for input. The spec's round is defined
to be finishable in one pass, with everything else written to files, so A is sufficient by design.

### Talking to the manager while it works

A `-p` session binds a messaging inbox, so it appears to your other sessions and can receive
messages from them; a bare-mode session does not. That gives A, B and C a channel the host project
can use mid-round, with two caveats: a `-p` session cannot show an approval dialog, so held messages
expire after the `dialogExpiry` deadline unless the launcher passes `crossSessionInbound: "accept"`
in its settings; and a script or hook can post into its own session's socket using
`CLAUDE_CODE_MESSAGING_SOCKET` and `CLAUDE_CODE_MESSAGING_TOKEN`.

D is the strongest here: a background session can be attached, peeked at, replied to, listed with
`claude agents`, and messaged like any other session.

### Permissions, unattended

All candidates start in the permission mode a new session would use unless `--permission-mode` says
otherwise. For an unattended round the relevant settings are `--permission-mode dontAsk`, which
denies anything that would prompt, or `auto`, together with `--permission-prompts none`, which stops
the run waiting on a prompt nobody will answer. D can instead sit at `Needs input` until someone
attaches, which is a liveness risk for an unattended round but a useful property for a resident
manager.

### Working directory and where edits land

This is D's one serious surprise: **before editing files, a background session moves itself into an
isolated git worktree under `.claude/worktrees/`**. For Adapt that means the manager would no longer
be writing in the workspace it was started in, and its subagents would inherit that relocated
directory. Every path Adapt records would need care, and the host worktrees the specialists work in
sit outside it. A, B, C and E all write where they were started.

### Observability

| | A, B, C | D | E |
|---|---|---|---|
| Live | `--output-format stream-json` gives every event, and subagent messages carry the id of the call that spawned them | `claude logs <id>`, agent view, attach | Every message as an object in your own code |
| After | The transcript at `~/.claude/projects/<project>/<session-id>.jsonl`, and `--output-format json` gives result, session id, usage and cost | The same transcript, plus the session stays listed | Whatever the program records |
| Off | `--no-session-persistence` suppresses the transcript for one run; `CLAUDE_CODE_SKIP_PROMPT_HISTORY` suppresses it everywhere | | |

Adapt's real record is its own history log and task window, written by the agents themselves. The
transcript is a debugging aid, not the record, in every candidate.

### Failure and recovery

| | A, B, C | D | E |
|---|---|---|---|
| Round dies | Rerun the round. Nothing carries over except the files the round already wrote | The supervisor restarts the process and the conversation continues | Your own retry logic |
| SIGTERM | Exit code 143, the in-progress turn is left unfinished with no result recorded, `SessionEnd` hooks still run | Same underneath | Same |
| Runaway | `--max-turns` (B, and A with one turn) | No equivalent; stop it with `claude stop <id>` | Your own limit |
| Resume gap | Configuration flags are not restored on resume: `--settings`, `--plugin-dir`, `--mcp-config`, `--add-dir` and the system-prompt flags must be passed again. Settings files are re-read | The supervisor keeps the flags the session carries | Not applicable |

That resume gap is a strong argument against C for Adapt specifically: the launcher's regenerated
exclusions are passed as settings, and a resume that forgets them is a resume with the personal
configuration back in the session.

### Concurrency

A, B and C run one process per round, so several rounds can run at once if the work items do not
touch the same files; git refuses two worktrees on one branch, which is the backstop. D lists and
supervises many sessions at once and is designed for it. E is whatever the program does.

### Effort to build

Roughly, from least to most: A, then D, then B, then C, then E. A is a single command in the shim's
launcher. D adds session-id bookkeeping and a stop path. B adds a driver process that must speak
stream-json. C adds session-id bookkeeping plus re-passing every flag. E is a program, a package
dependency and an authentication change.

## Swappability

The swap is cheap if, and only if, the launch is behind one interface and no state lives in the
session. Adapt is already built that way:

- **The launcher is one script in the shim.** Everything Adapt runs goes through it: regenerate the
  exclusions, then start the manager on one work item.
- **The manager's state is files.** Its history log, task window, notes and the work item itself are
  on disk. A round can be replayed by a different kind of session because nothing it needs is in a
  transcript.

So the contract to hold stable is: *the launcher takes a work item and returns when the round is
finished or failed, having written the round's result into the records.*

Given that contract:

| Swap | Cost |
|---|---|
| A to B | Small. The same prompt becomes the first message; a driver process feeds the rest. Nothing in the records changes |
| A to D | Medium. Session-id bookkeeping, a stop path, and the worktree relocation has to be handled or ruled out |
| A or B to C | Small mechanically, but it changes the context model from files to a growing conversation, which is a spec decision, not a launch detail |
| Any to E | Large. New dependency, new authentication and billing, and the exclusions move from CLI flags into the program |
| D back to A | Small. The supervised session is abandoned; the files are already the record |

The one thing that would make a swap expensive is letting the manager keep working state in its
conversation instead of its files. That is already forbidden by the spec, and this is the second
reason for it.

## Recommendation

**Start with A**: one `claude -p` run per round, `--permission-mode` set for unattended work,
`--output-format stream-json` captured to a log, and the regenerated exclusions passed as
`--settings`. It satisfies every criterion, costs one line in the launcher, and keeps the context
model the spec wants.

**Add B when, and only when, a round needs a second exchange** with the manager. It is the smallest
step from A and changes nothing in the records.

**Keep D in view for a resident manager.** It is the only candidate that survives between rounds,
can be attached to and messaged, and restarts itself after a crash. Before adopting it, test the
`.claude/worktrees/` relocation, because a manager that silently moves out of its workspace breaks
every path Adapt records.

**Rule out C** while context is meant to come from files, and **rule out E** while the subscription
login is a requirement.

## Glossary

**The supervisor** (candidate D). A background service Claude Code starts the first time you
background a session or open agent view. It runs each background session as its own Claude Code
process and manages that process for you: it keeps it running while the session is working, paused
on a prompt or attached; it stops it to free resources once the session is finished or waiting for a
message and has been unattached for about an hour; it restarts it if it exits unexpectedly; and it
moves idle sessions onto a new version after an auto-update. The conversation stays on disk
throughout, so a stopped session resumes where it left off when you attach or reply. It authenticates
with the same stored credentials as an interactive session. Its state lives in `~/.claude/daemon.log`,
`~/.claude/daemon/roster.json` and `~/.claude/jobs/<id>/`, and each session gets a scratch directory
at `$CLAUDE_JOB_DIR/tmp`. Background shell commands and background subagents carry over when a
session's process restarts; monitors and a subagent's own shell commands stop with it.

**"Each background session uses the subscription quota independently."** They do not share a budget
between them. Every background session draws on the same plan limits as any other session, and none
of them is discounted for running in the background, so ten sessions burn the plan roughly ten times
as fast as one. The warning is about dispatching many at once, not about background sessions costing
more per token.

**Session-id bookkeeping** (candidates C and D). Anything that outlives one command has an id that
the launcher must store, look up and clean up: write the session id somewhere durable when the
session starts, find it again on the next round, decide what to do when it is missing, stopped or
belongs to a crashed run, and stop or delete it when it is no longer wanted. With A there is nothing
to keep, because the id dies with the round and the records hold the state.

## What is still untested

1. The `.claude/worktrees/` relocation in a background session: when it happens, and what the
   working directory becomes for the session and for its subagents.
2. Whether `--setting-sources project,local` drops the personal settings file and its hooks while
   leaving the login intact.
3. `disableBundledSkills`, and whether the workspace can switch off a plugin enabled in the user's
   settings.
4. Whether `crossSessionInbound: "accept"` in the launcher's settings is enough for the host to
   message a running `-p` manager.
5. Whether a background session, which is not `-p`, is treated as interactive for agent teams. It
   should not matter, since Adapt uses subagents, but it would change what a resident manager could
   do.
6. Whether a background session can be reset in place. Claude has no tool that clears its own
   context: `/clear` and `/compact` are commands a person types, a message from another session
   arrives as plain text and is never executed as a command, and compaction otherwise happens on its
   own when the window fills. What is untested is whether a reply sent into a background session
   through agent view counts as typing the command, which is what a "clear yourself and start again"
   instruction would need. If it does not, resetting a resident manager means stopping it and
   launching a new one, which is what A does every round anyway.
