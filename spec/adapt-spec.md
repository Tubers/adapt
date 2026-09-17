# Adapt: specification

Adapt is a Claude Code skill for skills. It lives inside a project, takes requests from that
project's agent for new skills, extensions and repairs, and does the work in an isolated
environment of its own, so the project's agent never spends its context on skill work.

This document states what Adapt is. It is the crystallized form of `spec/revised.txt`, which
recorded the design as it was argued, and it supersedes it wherever the two differ. The reasoning
behind each decision lives in the spec project's history (`rules.py history spec`); supporting
analysis lives in `spec/launch-options.md` and in the draft rules under `spec/drafts/`. Points still
open are listed at the end, each with the task that owns it.

---

## 1. Purpose and constants

Skills are never finished. They should get better as they are used, and the agent using them
should not have to stop its own work to improve them. Adapt is the place where that improvement
happens: an agent in the project says what it needs from a skill, and Adapt delivers it.

Terms used throughout:

- **Host project**: the project Adapt is installed in.
- **Host agent**: the Claude Code session working in the host project. It is Adapt's client.
- **Sibling skills**: the skills in the host project's `.claude/skills/`, other than Adapt itself.
  These are what Adapt repairs, extends and adds to.
- **Workspace**: the folder where Adapt does its work, outside the host repository.
- **Manager**: the headless session that runs Adapt's work.
- **Specialist**: a subagent the manager assigns to one skill.
- **Round**: one start-to-finish cycle of work on one work item.

Five rules are **constants**. They are never modified or removed, by any agent, for any reason:

1. Adapt's purpose is to serve the host agent's skill requests, and its scope is the skills of the
   one project it is installed in.
2. An agent controls only its own home folder.
3. No instance ratifies its own request.
4. Tests gate every merge.
5. The central Adapt repository and its starting configuration are never modified by an instance
   working in a project. An instance acts only on its own installation.

Adapt answers to the **host agent**, not to the user. The line between them is interface against
implementation: the host agent cares about its intent, the surface a skill presents, and whether
that surface serves the intent. Everything below that line (how a skill works, how it is built,
what the build costs) is the manager's. The host agent never does skill work itself while Adapt is
installed; keeping that work out of the host's context is the reason Adapt exists.

---

## 2. Architecture

Adapt comes in two parts.

- **The shim** is a thin skill inside the host project, at `<host>/.claude/skills/adapt/`. It holds
  `SKILL.md` and the scripts the host agent runs: init, submit a request, start a round, and read
  the manager's records. It has no `.claude` tree of its own.
- **The workspace** holds everything else. It sits beside the host project as a sibling folder
  named after it, `<host>.adapt/`, so it is easy to find and identify. It is never inside the host
  repository, and it is the root of its own git repository.

This split is what keeps the two sides apart, and every part of it rests on documented or tested
Claude Code behaviour:

- Claude Code finds skills and agent definitions by walking up from the folder a session starts in
  to the repository root. The manager starts in the workspace, which has no parent in common with
  the host inside any repository, so the host's skills and agents never reach it (probed).
- The manager reaches host files through `permissions.additionalDirectories`, which grants file
  access and never loads that folder's skills, CLAUDE.md or rules. The `--add-dir` flag does load
  skills, so Adapt does not use it. The setting takes effect only once the workspace is trusted.
- Adapt's own skills are not under the host tree, so a host session can never discover them.

### Folder layout

```
<parent>/
├─ <host>/                                    the host project (its own git repository)
│  └─ .claude/skills/
│     ├─ adapt/                               the shim: SKILL.md, scripts/
│     ├─ adapt-tests/                         the test skill: every acceptance test Adapt has written
│     ├─ <skill-a>/                           sibling skills, each its own git repository
│     └─ <skill-b>/
│
├─ <host>.adapt/                              the workspace (its own git repository)
│  ├─ .claude/
│  │  ├─ settings.json                        exclusions, trust, hooks, permissions, cache TTLs
│  │  ├─ copy-map.json                        real path of each skill copy → its mapped path
│  │  ├─ agents/                              manager-spawned agent definitions
│  │  │  ├─ specialist.md                     medium model
│  │  │  ├─ code-specialist.md                medium model, with graphify and its hooks
│  │  │  ├─ verifier.md                       medium model, verifier protocol
│  │  │  └─ chore.md                          low model
│  │  ├─ skills/
│  │  │  ├─ rules-system/                     Adapt's own copy
│  │  │  ├─ vector-search/                    Adapt's own copy
│  │  │  ├─ meta-tools/                       the agents' own small tools
│  │  │  └─ graphify/                         code graphs, preloaded into code specialists only
│  │  └─ hooks/                               rules router, rtk, metrics, locks, watcher
│  ├─ rules/
│  │  ├─ INDEX.md                             gates; written only by the manager
│  │  ├─ constants.json                       names the five constant rules
│  │  ├─ protocols/manager/                   the manager's protocol, as a rule collection
│  │  ├─ protocols/specialist/                the specialists' template protocol, and the chore protocol
│  │  ├─ skills/<skill>/                      one specialist's protocol copy and its findings
│  │  └─ tooling/                             graphify, rtk
│  ├─ INBOX/                                  raw requests, one file each, and the inbox log
│  ├─ NEW/  EXTEND/  REPAIR/                  work folders, by kind
│  ├─ Fulfilled/  Aborted/  Postponed/        work folders at rest
│  ├─ manager_home/                           notes/, metrics.json, the round's records, rounds/
│  ├─ verifier_home/                          notes/, metrics.json, findings
│  ├─ specialists/<skill>/<home>/             one specialist's home
│  ├─ tools/                                  pinned Python environment (graphify), rtk binary
│  └─ config.json                             per-skill options
│
└─ <host>.adapt-copies/                       working copies of skills, outside the manager's start folder
   └─ <skill>-<work id>/                      a worktree of that skill's repository
```

The names `adapt-tests`, `verifier_home` and `<host>.adapt-copies` are working names (see Open
items).

### How a session learns of Adapt

There is no CLAUDE.md anywhere in Adapt, on either side. A gated rule tells a host session about
Adapt when it runs one of the shim's commands or touches the workspace, so a session that never
uses Adapt pays nothing for it.

---

## 3. Agents

### The manager

A headless Claude Code session on Opus 5, started by the shim in the workspace. It:

- reads the inbox and decides what becomes work;
- is the only agent that spawns or removes a subagent, and the only one that creates work items;
- designs the acceptance test for each work item;
- decides merges, on evidence;
- writes everything that persists beyond a home folder: rules, `INDEX.md`, surface documents,
  configuration;
- spends its attention on architecture and ergonomics: whether a surface is the right one, whether
  a run of repairs means the implementation should be rebuilt, whether a surface should be
  deprecated for a more stable one that asks for more input.

Subagent nesting is off: `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH=1`.

While specialists work, the manager is idle. A **watcher** script checks the group channels of the
active work folders for new messages addressed to the manager and wakes it, most likely by posting
into the manager session's own messaging socket, which starts a turn when the session is idle.

### Specialists

Subagents on a medium model, one per skill. A specialist's home and rules folder are created on
its first assignment, not at inventory; a skill nobody has asked about has neither.

Specialists of different skills may run at the same time when a work item spans skills, such as
an extension that uses functions from another skill. A brand new skill gets a specialist of its
own, in a new home.

A **code specialist** is a specialist whose skill is code. It is preloaded with graphify and runs
graphify's hooks.

### The verifier

A medium-model agent spawned under the verifier protocol, with a home of its own. It takes the
manager's test design, writes the acceptance test, runs it, and reads the code the test touches to
confirm the result was reached fairly. It never sees the implementing specialist's account of its
work.

### The chore worker

A low-model agent for small, direct, stateless tasks, starting with file and folder operations.
Specialists order it in a short command code designed to cost few tokens. Its context is fresh for
every batch, so every order must stand on its own. A specialist asks the manager for one; the
manager decides whether it is worth invoking. What a low model can reliably be trusted with is a
research question, and its repertoire grows as that research answers it.

### What every agent starts with

Each agent starts with the least it needs, in this order:

1. its own short system prompt;
2. its protocol, as a collection of rules;
3. the work item, with its acceptance criteria;
4. pointers to where it works and what it may touch.

Nothing else is loaded. Everything further is looked up: its rules, its history, its notes, the
skill's documentation, vector-search. Whatever is worth keeping is written back before the agent
ends, because the next agent reads the files, not the conversation.

Agent definitions set `omitClaudeMd`, a short body, the few skills the agent needs, and a tools
list that leaves out what it must not use.

---

## 4. Lifecycle of a request

### 4.1 Submitting

The shim's `SKILL.md` offers a command that interviews the host agent. The questions depend on the
kind of request (a new capability, an extension, a repair), and each answer is parsed as it is
given to choose the next question. The interview captures the **surface**: what goes in and what
should come out. A repair has the same shape: input x went in, z came out, y should have. It never
asks how the thing should be built. The aim is one pass, with no follow-up to the host.

The interview writes one raw request file into `INBOX/`. An automated log records everything that
happens to it afterwards.

### 4.2 Triage

The manager reads every request in the inbox before acting on any of them, writing notes as it
reads. For each request:

1. **Is it already answered?** For a new capability or an extension, the manager first checks
   whether an existing skill already does it. If one does, it answers the host with that skill's
   surface and a short piece of documentation, closes the request, and makes no work item.
2. **Does it belong with others?** Requests naming the same skill and the same need (the same
   defect, or the same missing capability) are amalgamated. vector-search suggests matches; the
   manager confirms each one. The original files are kept untouched, and the manager drafts one
   condensed request combining them with its own insight into the underlying issue.
3. **What shape is the answer?** In order of how little it disturbs: repair what is broken; extend
   a skill that already does something close; wrap several skills behind one surface; or build a
   brand new skill, when nothing existing does the thing or anything like it. The manager may also
   look past the request: several repairs on one surface can mean the implementation should be
   rebuilt.

To make the first question answerable, every maintained skill carries a **surface document**: terse
and machine-facing, listing what goes in and what comes out, kept current after every merge, and
searchable across all skills through vector-search. The manager can also read a skill's graph,
building one itself when no specialist has yet.

### 4.3 The work folder

The manager turns a request into a **work folder** and places it in `NEW/` (an entirely new skill,
wrappers included), `EXTEND/` or `REPAIR/`. A work folder keeps one piece of work apart from every
home folder. It holds:

- the original request files;
- the manager's condensed request, where requests were amalgamated;
- the manager's coarse process spec: what to build, in outline, or for a repair, how to probe for
  the fault, using the skill's graph;
- the acceptance criteria;
- an aggregated history log, pulled automatically from the history of every agent working on it;
- a group channel: an append-only message sequence every agent on the item posts to, and reads
  from in order, fetching only what it has not yet seen;
- anything else that turns out to belong there.

Content is structured, JSON where structure helps. The manager tracks the work folder as one task in
its task file. A specialist that takes it up breaks it into tasks of its own, in its own task file,
linked back to the work folder.

When the work ends, the folder moves to `Fulfilled/`, `Aborted/` or `Postponed/`.

### 4.4 A round

A round is one start-to-finish cycle on one work item:

1. The manager triages the inbox and creates or updates the work folder.
2. It designs the acceptance test in plain English, with loose pseudocode.
3. It spawns the specialists the item needs, and a chore worker if one is worth it.
4. The specialists work on copies of the skill.
5. The verifier writes and runs the acceptance test against the copy.
6. The manager merges on a pass, or sends the work back.
7. The change is mirrored where needed, the surface document refreshed, the return file written,
   and the request closed.

What may join a round: only an internal tool that directly improves the delivery of that work item
on speed, token efficiency, or ease of implementation (less to build, less to break later). The
manager may put such a tool first; when it does, the external request waits for the next round.

**Starting rounds.** Nothing starts the manager automatically. For now the user or the host agent
starts a round by invoking the shim; in future only the host agent will. An invocation names one
request, or a batch of requests for one skill. Each round is its own `claude -p` run: when the
manager decides to chain another round on the same skill, the launcher starts a new run with fresh
context. Chaining never crosses to another skill.

**Rounds are stateless.** No round carries a follow-up of an earlier one. What persists between
rounds is the inbox, the work folders, the home folders, the rules and the configuration. A host
agent unhappy with a result files a new request.

**What a round leaves behind.** The manager's history, task and questions files belong to the
round. When the next round starts they move into `manager_home/rounds/<round>/`, together with a
file referencing the work items the round touched, and the manager starts with empty ones. Round
folders are diagnostic material. A round with nothing to do may read back through them and propose
improvements, as requests like any other.

### 4.5 Proving delivery

A claim is never evidence. This is the hardest part of the design, because nothing is caught by
someone remembering.

1. The work item carries its acceptance criteria before any specialist touches it. A work item
   without them is not assignable.
2. A repair starts with a failing test that reproduces the fault. An extension or a new skill lands
   with tests for what it added.
3. The specialist reports evidence: the diff, the commands it ran and their output, and each
   criterion paired with what satisfies it. An unmet criterion is reported as unmet.
4. The acceptance tests live in the **test skill**, `adapt-tests`, a sibling of the other skills in
   the host project. Implementing specialists cannot read it. The host agent and the user can run it
   whenever they want.
5. The verifier runs the tests before any merge, checks the code they touch for fairness, and posts
   the results to the work folder's group channel.
6. The manager merges only on a pass. A failure found later, by anyone running the test skill,
   reverts the merge.
7. The host agent receives a **return file**: terse, surface only, saying what it can now expect
   ("repaired: `<command>` now outputs y given x", or a pointer to a new surface). It never mentions
   implementation. The manager's task for the item ends with a one-line outcome and a one-word
   status.

### 4.6 Skill initialization

At init, Adapt takes inventory of the sibling skills. The first time it works on one, that skill is
initialized before any change: an automated test suite is built for it, robust enough to catch the
change that quietly breaks something nobody thought to check, and a surface document is written.
Both are maintained from then on.

---

## 5. Records and communication

Everything is a file, so everything can be read, even while a round runs.

| Record | Kept by | Lives in | Survives the round |
|---|---|---|---|
| History log | every agent | its home; the manager's in `manager_home/` | agents: yes; manager: archived to `rounds/` |
| Task file | every agent | as above | as above |
| Questions file | every agent | as above | as above |
| Notes folder | every agent | its home | yes |
| Metrics file | hooks, per agent | its home | yes |
| Group channel | agents on a work item | the work folder | with the work folder |
| Inbox log | automatic | `INBOX/` | yes |

**Status.** The manager's task file is the status surface. The host agent reads it through the
shim; the user watches it in the rules-system viewer. There is no other status channel.

**Questions.** A specialist writes a question into its own questions file; a hook tells the manager,
which answers it, passes it to the host agent or the user, or turns it into work. Whatever carries
the answer, the outcome lands in a history log. While the design settles, the manager's own
questions file is a diagnostic: when it does not know what to do, it writes the question instead of
guessing, and those questions are later answered with rules, protocol lines, better briefings or
tools. A question that keeps returning is a hole in the design.

**Notes.** Every agent has a freeform notes folder it organizes as it likes, for anything niche or
half-formed. Notes are looked up, never loaded whole. They never become a second home for a fact:
a note that proves durable graduates into a rule, scoped to where it is needed, and the note is
removed. In time each specialist gets vector-search files over its own notes.

**Metrics and thresholds.** Each home keeps one metrics file, maintained by hooks and never written
by hand, counting note lookups, friction entries and rule firings. When a count crosses its
threshold, a hook tells the agent to review it: a hot note is a candidate rule; many similar
friction entries are a reason to ask the manager to look.

**Friction.** A friction entry records something cumbersome in an agent's own work. One entry is
noise; a pattern is a candidate for a tool or a skill change. Diagnostic tools and boilerplate
generators are the usual answers. The host agent may use the same entries to judge its own skills.

**Acclimatization.** A newly started agent records what made its task hard to take up: what it had
to hunt for, what it misread, what its home or rules failed to say. The manager records the same
about its own start and its state mid-round. These findings are how the next agent's start gets
easier.

**Stalls.** While Adapt is young, a stalled round notifies the host agent and the user directly. A
stall is any of: no record written for 20 minutes, the launcher exiting with an error, or a round
ending with its work item still open. The user is told in the viewer when it is open, and by a
Windows desktop notification when it is not.

**Writing register.** Records follow the writing rules Adapt's rules-system copy carries:
`writing/fact-ownership` (every fact written once, pointers elsewhere) and
`writing/compressed-register` (dense, never dropping negation, numbers or names). Agents' speech is
compressed further (section 7).

---

## 6. Rules and protocols

Rules are the main force that guides agents. Adapt ships a starting set, and it will change.

**Protocols.** Each kind of agent has a protocol: a collection of rules that carries the sequence
of its work, not advice, because a fresh agent has nothing else to go on. The manager's lives in
`rules/protocols/manager/`; the specialists' template and the chore protocol live in
`rules/protocols/specialist/`. Each specialist gets its own copy of the template on first
assignment, in `rules/skills/<skill>/`, so it can be tailored without touching other specialists.
Protocols are injected at session start, before any path is touched, so a startup mechanism
delivers the whole collection. The protocols are expected to be rebuilt many times.

**Scoped rules.** Everything else arrives through a gate, when an agent touches a matching path or
runs a matching command. A specialist's findings live in its rules folder and are gated to the
code and documents they concern. vector-search finds niche rules on demand, and its audit tools
keep the set free of redundancy, concise and properly scoped. There is a separate vector-search
index per kind of agent.

**Reaching skill copies.** A skill copy sits outside the workspace, where the rules router would not
see it. The script that makes a copy adds an entry to `.claude/copy-map.json`, pairing the copy's
real folder with a mapped path such as `copies/<skill>/`; the router rewrites real paths to mapped
ones before matching, and gates for a skill's code are written against the mapped path. The mapped
path leaves out `.claude/skills/`, which the router never gates. Merge, discard and rollback remove
the entry. Both protocols tell agents the map exists, so a rule seeded for a skill is written
against the mapped path.

**Changing rules.** No agent edits a rule on its own authority. A change is requested through the
inbox. A specialist's request is reviewed by the manager. A rule change the manager itself wants is
ratified only by a later round's manager, with fresh context. Constants cannot be changed at all.

**Documentation dogma**, for the manager's and specialists' rules and documents:

1. *Information independence.* Each fact lives in one place; see `writing/fact-ownership`.
2. *Condense.* Say it as densely as meaning allows; see `writing/compressed-register`.
3. *Context is tax free.* Never too many details for a fresh agent to resurrect its predecessor's
   context from its folder alone. This pulls against the second rule on purpose: dense, but complete.

---

## 7. Tooling

| Tool | What it gives | Who gets it |
|---|---|---|
| rules-system | records, tasks, questions, rules, gates, viewer | every agent |
| vector-search | search by meaning over rules, history, notes, surfaces, code | every agent |
| meta-tools | the agents' own small tools | every agent |
| graphify | code graphs: query, path, explain, affected, god-nodes | code specialists; the manager builds graphs directly |
| rtk | condensed command output | every agent |
| caveman | compressed speech | every agent |
| LSP plugins | definitions, references, type errors | code specialists |

**meta-tools** is a skill of Adapt's own, in the workspace's `.claude/skills/`. A meta tool is a
single file of at most 200 lines and 12KB, with no network access, used only by Adapt's agents. All
of that must hold for a tool to be one and stay one; it then carries lighter scrutiny and whatever
documentation its builders want. A tool that outgrows the limits goes through the full process.

**graphify** (PyPI `graphifyy`) parses code locally with tree-sitter, with no model or key, into a
graph a specialist can query. Its install writes two CLAUDE.md files and two hooks. Adapt's install
script runs it, mines the instruction files into a rule, compares them with the kept source text at
each upgrade, and deletes them. The hooks go into the code specialist's definition, calling the
pinned graphify by absolute path. Output always goes into the specialist's home with `--out`. Draft
rule: `spec/drafts/workspace-rule-tooling-graphify.md`.

**rtk** rewrites every Bash command into a compressed form through a PreToolUse hook. Its project
init writes only an instruction block, so Adapt mines that into a rule, deletes it, keeps
`.rtk/filters.toml`, and writes the hook into the workspace settings itself, for every agent.
Telemetry is disabled. Test output must stay readable for the merge gate: the verifier re-runs with
`rtk proxy` when condensed output hides a failure. Draft rule:
`spec/drafts/workspace-rule-tooling-rtk.md`.

**caveman** reaches the manager as the workspace's output style. Output styles do not reach
subagents, so every agent definition carries the caveman rules in its body.

**LSP plugins** give a code specialist code intelligence for its skill's language. Plugins load at
session start, so a plugin a specialist adds reaches the next session.

**Tool access.** Agents run in `dontAsk` mode: anything not approved is refused. A specialist starts
with only what its skill needs. When it needs more, it asks the manager with a reason; an approval
is kept in its home, and every later instance of that specialist inherits it.

---

## 8. Isolation and launch

### Launch

The shim's launcher starts one `claude -p` run per round, in the workspace. It is probed: a run
started from a host session uses the same subscription login and usage, runs in `dontAsk` mode,
spawns the workspace's own agents, and stays open until background subagents finish. The host
agent may carry on with work that does not depend on the request, or wait; waiting is better when
usage is already high. `spec/launch-options.md` compares this with the alternatives and explains
why it can be swapped later.

The run is launched with:

- `--setting-sources project,local`, which drops the user's personal settings, hooks and plugins
  while keeping the login;
- `--permission-mode dontAsk`;
- `CLAUDE_AGENT_SDK_DISABLE_BUILTIN_AGENTS=1` in the process environment, which removes every
  built-in agent (it has no effect when set in the settings file);
- the regenerated exclusions below.

### What is stripped away

The manager starts with as little as possible, and a capability comes back only when something
needs it, one at a time, recorded.

- **Personal skills and agents.** At every launch the launcher scans the user's skills and agents
  folders and writes a `skillOverrides: "off"` entry for each skill and a
  `permissions.deny: Agent(<name>)` entry for each agent. It keeps a manifest, so a newly seen name
  is both switched off and logged.
- **Bundled skills.** `disableBundledSkills`, plus `skillOverrides: "off"` for `design` and
  `doctor`, which survive it. Probed: no skills remain.
- **CLAUDE.md and rules from above the workspace.** `claudeMdExcludes`.
- **Auto memory.** Off.
- **MCP servers.** None.
- **Personal settings.** Dropped by `--setting-sources`.

### Workspace settings

`.claude/settings.json` in the workspace carries the exclusions above,
`permissions.additionalDirectories` for the host folders the manager may reach, the hooks (rules
router, rtk, metrics, locks, stall detection), `promptCacheTtl` and `subagentPromptCacheTtl` set to
`1h` (subagents otherwise keep a five-minute cache even on a subscription), and
`CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH=1`.

### Scope

Each agent controls its own home folder and nothing else. Nothing outside a home is changed on an
agent's own authority, whether it belongs to the host or to Adapt. An agent that thinks something
outside its home is wrong files a request, which a manager with fresh context decides. Network
access is minimal; the exception is the manager researching a topic to write a good build request.

---

## 9. Skill repositories and where improvements go

**Repositories.** Every sibling skill is its own git repository, with a private remote on GitHub:
one remote per skill, with a branch per host project. Each project's version of a skill is a branch
off the original. When the host project is not a git repository, init offers to set this up.

**Working on a skill.** A specialist changes a skill only on a copy: a worktree of that skill's
repository, in `<host>.adapt-copies/`, reached through `additionalDirectories`. Copies sit outside
the manager's start folder, so Claude Code never lazily loads the skills inside them. Every agent,
inside Adapt or outside, keeps using the working version while a copy is under way, and the copy
merges only when the tests pass.

**Two specialists, one file.** A file being modified is locked until the holder's task moves on. A
specialist that meets a lock reads the holder's log, works on another unblocked task meanwhile, and
otherwise waits.

**Mirroring.** Adapt carries its own copies of rules-system and vector-search. Changes are mirrored
between a host skill and Adapt's copy of it. When they conflict, the host's version wins, and Adapt
starts again from it.

**Where an improvement goes.** `config.json` holds options per skill, written at init and kept
current by a script that keys in newly found skills:

- **Local** (default): the improvement stays on this project's branch.
- **Global**: it is also merged into the skill's main branch.
- **Reconciliation** (later): the project branches of every Adapt installation are reconciled onto
  the main branch.

**Adapt's own development.** Rules, findings and meta tools an installation produces stay in that
workspace, because they come from that project's cases. No instance changes the central Adapt
repository. Later, a manager may send it a pull-request-style proposal for a change that would
benefit every installation, possibly started by a specialist but forwarded only by the manager, and
the user reviews and applies it in a session in the central repository.

**Retirement.** Adapt may retire a skill, a rule or a meta tool. Retirement is a request like any
other, ratified by a fresh manager, argued from use counts and firing logs. A skill the host still
uses is not retired, and constants never are. Retired things are archived with the reason, not
erased.

---

## 10. Failure

**A crashed round is redone, never salvaged.** Rollback comes first, in code: discard the copy's
branch, remove its worktree, revert a merge already made, clear its copy-map entry and file locks.
Agents log as they go and mark active worktrees active, so the state is discoverable. When the
rollback cannot be automatic, the manager establishes what happened and decides what to roll back.
Then the round runs again from the start.

**Running out of usage** mid-round is handled exactly like a crash.

**Budget.** No caps on specialists, turns or time for now.

---

## 11. Experimental: nested Adapt

An Adapt may be installed inside another Adapt's workspace, when the user configures it, to at most
two levels: host, Adapt, inner Adapt. The inner Adapt reports to the outer manager the way a host
agent reports to Adapt, through the inbox and return files. It is to be tried on a complex project
before it counts as supported. Where the inner Adapt's workspace goes is not yet decided.

---

## 12. Open items

Build work and tests, each owned by a task in the spec project (`rules.py tasks --in spec`):

| Area | Open | Task |
|---|---|---|
| Setup | the shim's command list and outputs | t22 |
| | the request interview's question sets and generator | t10 |
| | trial of a low-model interviewer | t51 |
| | duplicate check before filing | t11 |
| | skill initialization: suites and surface documents | t32, t69 |
| | per-skill configuration and discovery script | t46 |
| Launch | launcher with regenerated exclusions | t26 |
| | stripped settings folded into the workspace | t27 |
| | plugin packaging on top, if wanted | t13 (closed; revisit) |
| Agents | subagent model and chore lifecycle | t15 |
| | system prompts | t17 |
| | startup injection of protocols | t18 |
| | first drafts of the three protocols | t52 |
| | the briefing order and owners | t31 |
| | the verifier: test skill layout and read denial | t56 |
| | low-model scope and chore command code | t73 |
| | LSP plugins without the interactive command | t28 |
| | graphify install and pinning | t29 |
| | manager-built graphs | t67 |
| | caveman and rtk install, hook ordering, rtk data folder | t71 |
| Work | quality assurance steps as commands and rules | t30 |
| | group channel and watcher | t65 |
| | aggregated history | t66 |
| | task links from manager to specialists | t68 |
| | request archive and ids | t34 |
| | ratification check with round ids | t35 |
| | tool approval format | t36 |
| | skill copies, merge and mirroring | t20 |
| | file locks | t45 |
| | router path map | t64 |
| | per-specialist rule curation | t24 |
| | constants config and enforcement | t16 |
| Records | friction entries and grouping | t19 |
| | metrics file, thresholds, trigger hook | t70 |
| | notes folders, counts and graduation | t49 |
| | manager questions as diagnostics | t48 |
| | re-indexing vector-search | t44 |
| Failure | rollback script and active markers | t38 |
| | budget, if caps are ever wanted | t37 |
| | stall detector and notices | t47 |
| Other | retirement thresholds and archive | t50 |
| | nested Adapt | t23 |
| | Windows specifics | t43 |
| | proposals to the central repository | t72 |
| | whether claude --bg should replace -p later | launch-options.md |

Decisions this document made where the recorded answers left a gap, for the user to confirm:
see the consistency notes delivered with it.

---

## Glossary

- **Amalgamation**: merging inbox requests with the same skill and need into one work folder.
- **Chore worker**: the low-model agent for small stateless tasks.
- **Constant**: one of the five rules no agent may change.
- **Copy map**: the file pairing each skill copy's real path with its mapped path, so rules reach it.
- **Group channel**: a work folder's append-only message sequence.
- **Home folder**: the one folder an agent controls.
- **Mapped path**: the made-up, workspace-relative path the rules router uses for a skill copy.
- **Protocol**: an agent kind's workflow, as a collection of rules, injected at start.
- **Return file**: what the host agent receives when its request is done: surface only.
- **Round**: one start-to-finish cycle on one work item, in one `claude -p` run.
- **Shim**: the thin Adapt skill inside the host project.
- **Surface document**: a skill's terse, machine-facing list of inputs and outputs.
- **Test skill**: `adapt-tests`, the sibling skill holding every acceptance test.
- **Watcher**: the script that wakes the manager when a message addressed to it arrives.
- **Work folder**: the folder holding everything about one work item.
- **Workspace**: `<host>.adapt/`, where Adapt does its work.
