# Adapt build plan

How Adapt, as specified in `spec/adapt-spec.md`, gets built. This is the ordered process list: phases,
the processes inside them, and what each one needs before it can be tested. The lowest-level steps
become tasks in this folder's task window (`rules.py tasks --in Adapt/build`), one phase at a time.

## Where things go

```
Adapt/build/
├─ BUILD-PLAN.md            this document
├─ adapt/                   the distributable package: what a host project receives
│  ├─ shim/                 SKILL.md and the host-side scripts
│  ├─ workspace/            the template the workspace is created from (.claude tree, rules, folders)
│  └─ install/              init, tool fetching, upgrade
├─ tests/                   the build's own tests, run against throwaway hosts
│  └─ harness/              fixture hosts, probe runner, cleanup
└─ scripts/                 build-time helpers: vendoring, packaging
```

`Adapt/build_manifest.py`, `Adapt/selftest/` and `Adapt/skills.manifest.json` are earlier installer
work; phase 12 decides what of them survives.

## How the order was reached

The list was sorted three times, each time asking of every item: *what must already exist before
this can be tested?*

- **Pass 1** followed the spec's architecture: install, launcher, rules, records, copies, agents,
  intake, round.
- **Pass 2** found one hidden dependency under many items: a hook has to know *which agent* is
  calling. Protocol injection, per-agent metrics, file locks, tool allowlists and hiding the test
  skill from implementers all need it. It became its own early phase (3), with stub agent
  definitions so it can be tested before the real agents exist. The copy map was split: its
  rewrite logic is unit-testable early (phase 4), its integration waits for real copies (phase 6).
- **Pass 3** moved the test harness to the very front (everything is tested through it), put the
  tool fetcher before the launcher (the launcher's tests need rtk on PATH), and kept surface
  documents after the agents, because writing one needs a model. Skill repositories need GitHub
  access, so tests use local bare repositories and the real remote is a single user action.

## Phases

Each process lists what it needs (**needs**) and how it is proven (**proof**).

### Phase 0: Foundations

0.1 **Package layout.** Create the folders above, and a README for `adapt/`.
    Needs: nothing. Proof: the tree exists.

0.2 **Test harness.** Everything else is tested through it.
    - A fixture maker: a throwaway host project with `git init`, two sample skills and a planted
      bug, created in the scratch folder and removed afterwards.
    - A probe runner: starts `claude -p` on the cheapest model, captures stream-json, parses the
      init event (model, skills, agents, plugins), and deletes the run's transcript and any config
      entry it created.
    - A cleanup check that fails the test run if anything was left behind.
    Needs: 0.1. Proof: the harness's own tests pass and leave nothing behind.

0.3 **Vendoring.** Copy rules-system and vector-search from this repo into the workspace template,
    with a script that re-syncs them and reports drift.
    Needs: 0.1. Proof: both skills' own test suites pass inside the template.

0.4 **Tool fetcher.** Download rtk at a pinned version and verify its checksum; create the
    graphify environment with uv at a pinned version; write the `tools/bin` launchers.
    Needs: 0.1. Proof: `tools/bin/rtk --version` and `tools/bin/graphify --help` run in a fixture
    workspace.

### Phase 1: Install skeleton (Adapt's own init, without agents)

1.1 **Workspace creation.** Create `<host>.adapt/` beside the host, `git init` it, lay out the
    folders (INBOX, NEW, EXTEND, REPAIR, the rest states, homes, rules, tools).
1.2 **Base settings.** Write `.claude/settings.json`: `claudeMdExcludes`, `disableBundledSkills`
    and the two leftover skill overrides, auto memory off, cache TTLs, spawn depth 1,
    `RTK_TELEMETRY_DISABLED`.
1.3 **Trust and reach.** Write `hasTrustDialogAccepted` for the workspace, and
    `permissions.additionalDirectories` for the host's skill folder and the copies folder.
1.4 **Shim.** Write `<host>/.claude/skills/adapt/` with a placeholder `SKILL.md` and the script
    entry points.
1.5 **Inventory and configuration.** Scan the host's sibling skills into `config.json`, with
    defaults, and a discovery script that keys in new ones.
1.6 **Manager records.** Create the manager's history and task files with rules-system. Its init
    also creates a questions file, which Adapt does not use and removes.
1.7 **Re-running init.** A second init changes nothing and reports that.
    Needs: phase 0. Proof: init on a fixture host produces the whole tree; a second run is a no-op;
    removing the workspace and shim leaves the host exactly as before.

### Phase 2: Launcher and isolation

2.1 **Exclusion regenerator.** Scan the user's personal skills and agents; write the
    `skillOverrides` and `Agent(<name>)` deny entries; keep the manifest; log names not seen before.
2.2 **Launcher.** Start `claude -p` in the workspace with `--setting-sources project,local`,
    `--permission-mode dontAsk`, `CLAUDE_AGENT_SDK_DISABLE_BUILTIN_AGENTS=1` and `tools/bin` first
    on `PATH`, capturing stream-json to a round log.
2.3 **Tool hooks.** Port `tools_path.py`, the rtk hook and `graphify_nudge.py` from this repo into
    the template.
2.4 **Manager output style.** caveman as the workspace's output style.
2.5 **Stripped-baseline test.** A launched manager lists no skills or agents but Adapt's own, no
    plugins, and runs an rtk-rewritten command successfully.
    Needs: phases 0 and 1. Proof: 2.5 passes on a machine whose personal folders hold a probe skill
    and agent, which the harness creates and removes.

### Phase 3: Agent identity in hooks

3.1 **Spike.** Establish what a hook can see about its caller: the main session versus a subagent,
    and which agent type. Check the SubagentStart and PreToolUse inputs.
3.2 **Stub agents.** Four minimal definitions (specialist, code specialist, verifier, chore) that
    do nothing but answer, so identity can be tested.
3.3 **Identity helper.** One shared function every Adapt hook uses to name the calling agent and
    find its home.
    Needs: phase 2. Proof: a hook run inside each stub agent reports the right identity.

### Phase 4: Rules infrastructure

4.1 **Rules tree.** `rules/INDEX.md`, the protocol folders for all four agent kinds,
    `rules/skills/`, `rules/tooling/` with the graphify and rtk rules from `spec/drafts/`.
4.2 **Constants.** `rules/constants.json` naming the five constants, and a hook that refuses any
    edit, move or deletion of them.
4.3 **Protocol injection.** A SessionStart hook for the manager and a SubagentStart hook for
    subagents that inject the caller's whole protocol collection, preferring a specialist's own
    copy under `rules/skills/<skill>/`.
4.4 **Copy map, unit level.** The router rewrites a real path under a mapped folder into its
    mapped path before matching; tested with a hand-written map.
4.5 **Index per agent kind.** vector-search namespaces per agent kind, built from the rules each
    kind can receive.
    Needs: phase 3 (4.3 needs identity). Proof: each stub agent starts with its own protocol text in
    context and nothing else; constant edits are refused; a mapped path fires its gate.

### Phase 5: Records and communication

5.1 **Round record.** Round ids; moving the manager's history and task files into `rounds/<round>/` at the next
    round's start; the reference file.
5.2 **Inbox.** The raw request schema; one file per request; the automated inbox log; the archive.
5.3 **Work folder.** Schema; create in NEW, EXTEND or REPAIR; move to Fulfilled, Aborted or
    Postponed; the manager task that points at it.
5.4 **Group channel.** Post and read-unseen commands, with an addressee on each message, and an
    open marker for questions nobody has answered yet.
5.5 **Aggregated history.** Pull the history of every agent on a work item into its log.
5.6 **Homes on first assignment.** Create a specialist's home, notes folder and rules copy when it
    is first assigned.
5.7 **File locks.** Take and release commands, and a hook that refuses a write to a file locked by
    another agent and points at the holder's log.
5.8 **Metrics.** The per-home metrics file, the hooks that count note lookups, friction entries and
    rule firings, and the threshold hook that tells an agent to review an indicator.
5.9 **Ratification check.** Every request carries its author and round; approving one from the same
    round is refused.
5.10 **Task links.** A specialist's tasks link back to the work folder, and the viewer can walk
    from the manager's task to them.
    Needs: phases 3 and 4. Proof: each has unit tests; a scripted two-stub-agent exchange over a
    group channel and a lock passes.

### Phase 6: Skill repositories and copies

6.1 **Skill repository setup.** Make a sibling skill its own repository with a project branch and
    a remote. Tests use local bare repositories; the private GitHub remote is created once with
    `gh`, which needs the user's login.
6.2 **Copies.** Create a worktree in `<host>.adapt-copies/` and its copy-map entry.
6.3 **Merge and discard.** Merge a copy into the skill's project branch, or discard it; remove the
    map entry.
6.4 **Mirroring.** Mirror between a host skill and Adapt's own copy; the host's version wins on
    conflict.
6.5 **Rollback.** Undo everything a round did: branches, worktrees, merges, map entries, locks,
    anything else it recorded as active.
6.6 **Copy map, integration.** A gated rule fires on a real copy.
    Needs: phases 4 and 5. Proof: a scripted round on a fixture skill can be rolled back to a state
    byte-identical to its start.

### Phase 7: Agents

7.1 **Agent definitions.** The four real definitions: models, tools lists, `omitClaudeMd`, preloaded
    skills, caveman rules in the body; graphify's hooks in the code specialist only.
7.2 **Tool allowlists.** Per-specialist approved tools in its home, a permission hook enforcing
    them, and the request-and-approve cycle through the manager.
7.3 **Test skill denial.** Implementing specialists cannot read `adapt-tests`; the verifier can.
7.4 **Chore command code, version 0,** and the chore protocol.
7.5 **System prompts.**
7.6 **Protocols, version 0,** for all four kinds, written against the settled workflow. Expected to
    be rewritten often.
    Needs: phases 3 to 6. Proof: the manager spawns each kind; each starts with its protocol; a
    denied tool is refused and becomes a request; a specialist cannot read the test skill.

### Phase 8: Intake and surfaces

8.1 **Request interview, version 0.** A scripted decision tree in the shim, with separate question
    sets for a new capability, an extension and a repair.
8.2 **Surface documents.** Generated for every sibling skill at Adapt's init, kept in the
    workspace, and indexed across skills in vector-search.
8.3 **Triage aids.** vector-search suggestions for "an existing skill already does this" and for
    amalgamation candidates.
    Needs: phases 5 and 7 (8.2 needs a model through the launcher). Proof: the interview files a
    well-formed request; a request for an existing capability is matched to the right surface.

### Phase 9: Skill initialization and the test skill

9.1 **The test skill.** `adapt-tests` created in the host, runnable by the host agent or the user.
9.2 **Skill initialization.** On first work on a skill: gather what matters into its rules, set up
    its repository and worktrees, build its automated suite, write or refresh its surface document.
9.3 **Graphs.** graphify builds into the specialist's home with `--out`; the manager can build one
    for a skill with no specialist.
    Needs: phases 6 to 8. Proof: initializing a fixture skill yields rules, a passing suite, a
    surface document and a graph.

### Phase 10: The round, end to end

10.1 **Manager protocol, round loop.** Review the previous round's internal requests, triage, work folder, test design, spawn, work, verify, merge,
     mirror, return file, close.
10.2 **Watcher.** Wake the manager on a new message addressed to it; raise the `-p` idle ceiling if
     needed.
10.3 **Chained rounds.** The launcher starts a fresh run when the manager chains a round on the
     same skill.
10.4 **Return file.**
10.5 **Stalls.** The detector, the viewer notice and the Windows notification.
10.6 **Usage stop.** A round stopped by the usage limit is rolled back like a crash.
10.7 **End-to-end tests.** A REPAIR on the fixture's planted bug; an EXTEND; a request already
     answered by an existing skill; a crashed round rolled back and rerun.
    Needs: phases 0 to 9. Proof: 10.7 passes.

### Phase 11: Improvement loops

11.1 Friction entries: the history kind, the threshold, grouping by similarity.
11.2 The manager's questions file reviewed and turned into rules.
11.3 Note graduation into rules; retirement of skills, rules and meta tools.
11.4 Acclimatization findings.
11.5 Requests from inside Adapt, ratified by a later round, in practice.
11.6 Low-model research: the chore worker's scope, and a low-model request interviewer.
    Needs: phase 10.

### Phase 12: Packaging and platform

12.1 The host-side install from GitHub, version pinning, upgrade (including re-mining graphify and
     rtk instructions).
12.2 A pass over every Windows footnote.
12.3 What survives of the earlier installer work in `Adapt/`.
12.4 Documentation for a person installing Adapt.

### Deferred

Nested Adapt; proposals to the central repository; cross-project reconciliation; a resident
`claude --bg` manager; plugin packaging.

## One user action to plan for

Phase 6.1 needs a private GitHub remote per skill, created with `gh` under the user's login. Tests
never need it; the first real skill does.
