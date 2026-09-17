# 📋 TASKS · spec

**Goal:** revise the Adapt skill spec with the user: spec/original.txt is the untouched first draft, spec/revised.txt the working revision

- ✅ define THE MANAGER without a persistent instance · *2026-09-16* `t6`
- ✅ separate NEW, EXTEND and REPAIR, and define amalgamation · *2026-09-16* `t9`
- 🔄 **fold in the user's own changes to the spec** · *since 2026-09-15* `t1`
- 🔜 specify the request form and its python generator `t10`
- 🔜 fix When to Trigger and the duplicate check `t11`
- 🔜 ❓ define a round `t12`
- 🔜 manager launch: --bare or a normal session fenced by settings `t13`
- 🔜 specialists as subagents, not agent teams; haiku worker lifecycle `t15`
- 🔜 ❓ constant rules: a rules-system config for rules never removed or modified `t16`
- 🔜 agent system prompts for manager, specialist-medium and specialist-low `t17`
- 🔜 protocol rules for specialists and manager, and how they attach at spawn `t18`
- 🔜 friction entries: history kind, threshold hook, similarity grouping `t19`
- 🔜 ❓ skill copies, manager-approved merge, and two-way mirroring `t20`
- 🔜 first-run install: what Adapt init sets up `t21`
- 🔜 host-side Adapt commands `t22`
- 🔜 ❓ nested Adapt: an Adapt inside an Adapt `t23`
- 🔜 per-specialist rules folders and finding curation `t24`
- 🔜 ❓ place META TOOLS: root folder, inner skill, or both `t25`
- 🔜 launcher: regenerate the personal exclusions at every manager launch `t26`
- 🔜 strip the manager down: bundled skills, built-in agents, user plugins `t27`
- 🔜 let a specialist add its own LSP plugin without the interactive plugin command `t28`
- 🔜 code graph tooling for specialists, on top of LSP `t29`
- 🔜 quality assurance: how a round proves it delivered `t30`
- 🔜 the briefing: what each agent is given, and in what order `t31`
- 🔜 skill initialization: build a skill's automated test suite before the first change `t32`
- 🔜 request archive: every request kept, automatically `t34`
- 🔜 ratification: enforcing that no instance ratifies its own request `t35`
- 🔜 ❓ permissions posture: what agents may run and touch `t36`
- 🔜 budget for a round: caps, and what happens at the usage limit `t37`
- 🔜 recovery: what happens to a round that dies mid-way `t38`
- 🔜 Windows specifics: the mechanisms that carry a Windows footnote `t43`
- 🔜 who re-indexes vector-search, and what it costs `t44`
- 🔜 ❓ two specialists needing the same file `t45`
- 🔜 ❓ skill configuration: per-skill options, defaults, and the script that keeps it current `t46`
- 🔜 stall notice: tell the user when a round stalls or crashes `t47`
- 🔜 the manager's questions file as a diagnostic, and turning its entries into rules `t48`
- 🔜 notes folders: freeform space for the manager and every specialist `t49`
- 🔜 retirement: the evidence, the path, and what archiving means `t50`
- 🔜 trial: a low-model instance running the request interview from a decision tree `t51`
- 🔜 draft the starting protocols: manager round, specialist work, chore worker `t52`
- 🔜 the verifier: a third agent kind, or a mode of the specialist `t56`
- 🔜 router: rewrite paths under a mapped copy before matching gates `t64`
- 🔜 group channel: an append-only message file per work item `t65`
- 🔜 aggregated history: fixtures that pull specialist history into the work item `t66`
- 🔜 manager-built graphs for skills with no specialist yet `t67`
- 🔜 task links: manager task to work folder to specialist sub-tasks `t68`
- 🔜 surface documents: format, the updater after merge, and the cross-skill index `t69`
- 🔜 metrics file per home, and the hooks that keep it current `t70`

---

## Details

**t6** · The manager's history, task and questions files now rotate per round into the rounds folder; its notes folder persists. Still open: whether the original draft's Notes and Memories survive as separate things, or are replaced by the notes folder (niche information) and the round archive (the running log). Done when the manager's home layout is fixed.

**t9** · Categories settled: NEW holds work folders for entirely new skills, wrappers included; EXTEND for extensions of an existing skill; REPAIR for fixes; the original NEW wording is marked revised in the spec. Still open: the amalgamation proposal, merging requests that name the same skill and need into one work folder, awaits the user. Done when it is accepted or changed.

**t1** · The user has many changes of their own: some needed, some functional alternatives judged better than the original. Take each in chat, write it into spec/revised.txt, and split out any that opens a new question as its own task. Done when the user says the list is exhausted.

**t10** · The form is an interview invoked from the shim's SKILL.md, with different questions for a new capability, an extension and a repair. It captures the surface: inputs and what they deliver, or for a repair input x, actual z, expected y. It never asks about implementation. It is dynamic, routing on parsed answers (t51), and aims to capture everything in one pass. Needed: the question sets, the generator, where the filled form lands. Done when a request can be filed end to end.

**t11** · When to Trigger now names INBOX (done under t3). Still open: before filing, an instance checks for a similar request; vector-search could do that check by meaning. Done when the trigger conditions and the duplicate check are defined.

**t12** · A round is one start-to-finish cycle on one work item, with the five steps in spec/revised.txt. Only an internal tool that improves delivery of that item may join it, judged on speed, usage and token efficiency, or ease of implementation. The round can grow by ratification and be reordered when a tool is promoted, in which case the external request waits for the next round. Open: when the manager may start a round itself. Done when the user accepts.

**t13** · One claude -p run per round in the workspace, no --bare and no resume. The comparison and the untested list live in spec/launch-options.md. Exclusions regenerated per launch (t26); bundled skills, built-in agents, plugins, auto memory and MCP off (t27). Left here: write the launch command with its permission mode and output capture, test --setting-sources project,local, test crossSessionInbound accept. Done when a run shows nothing host or personal.

**t15** · Docs: agent teams need an interactive session, never -p. Subagents may spawn subagents by default, 3 layers deep; CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH=1 turns it off and so enforces manager-only spawning. The skills field preloads full content but does not restrict; omit Skill from tools to restrict. omitClaudeMd exists. A fresh haiku subagent per batch is stateless. Done when spec fixes the agent model and haiku lifecycle.

**t16** · User wants some rules fixed for good. Needed: the config file and format naming them, and the enforcement point, likely the existing rule-approval hook refusing edits, moves and deletes of a listed rule. Done when format and enforcement are defined.

**t17** · Minimal starting directives that breadcrumb each agent to what it needs: its skill, its rules folder, its records, the commands it uses. Done when three drafts exist and the user approves them.

**t18** · Protocols arrive nearly at session start, before any path is touched, so a path gate cannot deliver them. This task owns that startup mechanism: a hook at session or subagent start that injects the agent's whole protocol collection, and how a specialist's own copy is found in place of the common branch. Done when a fresh specialist starts with its own collection in context and nothing else.

**t19** · Needs a friction kind in rules-system history; a hook that notifies an instance after N new friction entries since its last notice, N configurable; grouping of similar entries by meaning with vector-search; manager commands to read specialist histories filtered for friction. Done when kind, hook, config and grouping are defined.

**t20** · Specialists work on copies; the manager approves merges; two-way mirror with Adapt's inner copies. Under B a host skill copy is a git worktree made in the host repo by script, placed outside the workspace start folder and reached through additionalDirectories; isolation worktree would copy the workspace repo instead. Needed: branch naming, conflicts, which side wins. Done when the flow is defined.

**t21** · First init creates the workspace outside the host repo as its own git repo, writes the shim into the host's .claude/skills/adapt/, marks the workspace trusted by writing hasTrustDialogAccepted for that path, spawns the manager, and runs build scripts: inventory the user's skills, create data folders and configs, load Adapt's own skills, create the manager's records. Needed: where the workspace lives, idempotent re-init, later inits. Done when defined.

**t22** · What a host instance can run against Adapt: init, submit a request, start a round, and read the manager's records in filtered slices. The manager's task file is the status surface, watched in the viewer or read through the shim; there is no second status channel. Needed: the command list, each command's output, and how a host instance is told a round finished or stalled. Done when the list is defined.

**t23** · User allows chains of Adapts building tools to build tools. Needed: which Adapt owns which skills, how a nested manager is launched and reports up, and any depth limit. Done when the spec states them.

**t24** · Each specialist gets rules/<skill name>/ holding its findings; it curates them into rules gated to code files or skill documents. Needed: how this fits rules-system candidates and approval, and who approves a specialist's new rule. Done when defined.

**t25** · The spec keeps META TOOLS as a root folder, and specialists are preloaded with it as a skill, which lives in .claude/skills/. Decide the one real location and how the other refers to it. Done when the spec names it.

**t26** · The launcher scans the user's skills and agents folders, writes a skillOverrides off entry per skill name and a permissions.deny Agent(name) entry per agent name into the workspace settings, keeps a manifest of names already nullified, and logs any name it has not seen. Also test --setting-sources project,local, which should drop the personal settings file and its hooks while leaving the login alone. Done when the launcher exists and a run shows nothing personal.

**t27** · Test disableBundledSkills for the bundled skills such as code-review and loop; CLAUDE_AGENT_SDK_DISABLE_BUILTIN_AGENTS=1 for Explore, Plan and general-purpose in a -p session; and whether workspace settings can switch off a plugin enabled in the user's settings. Then define how a capability comes back: one at a time, on evidence it is needed, each re-enable recorded. Done when the stripped baseline is defined and tested.

**t28** · A specialist needs code intelligence for its skill's language. Plugins can carry .lsp.json, and the official marketplace has TypeScript, Python, Go and Rust plugins. Plugins load at session start, so an install reaches the next session. Investigate: claude plugin CLI subcommands, writing enabledPlugins and marketplaces into the workspace settings, --plugin-dir at launch, and skills-directory plugins that auto-load. Done when a specialist can request one and the next launch has it.

**t29** · graphify (graphifyy 0.9.63), uv installed. The install script runs graphify install in the workspace, compares its two instruction files against the source text kept with the draft rule, updates the rule if they changed, then deletes both files. Its hooks move into the code specialist's agent definition, calling the pinned graphify by absolute path. Always pass --out into the specialist's home. Depends on t63. Done when a specialist queries a graph and the rule fires.

**t30** · Layers sketched in spec/revised.txt: acceptance criteria in the work item before assignment; a failing test first for a REPAIR; evidence not claims from the specialist; a verifier subagent with fresh context that re-runs tests and never sees the specialist's narrative; the manager merging only on that pass; a host-side check after the merge that reverts on failure; the round closed against the original request. Done when each step has a concrete form, a command and a rule.

**t31** · No agent carries context between sessions, so the briefing is the design. Order: own system prompt, protocol rules for its kind, work item with acceptance criteria, pointers to where it works and what it may touch, nothing else. Everything further is looked up, and what is worth keeping is written back before the agent ends. Relates to t17 and t18. Done when the order is fixed and each part has an owner.

**t32** · At init Adapt inventories the sibling skills. The first time it extends or repairs one, that skill goes through initialization: an automated suite is built first, robust enough to catch a quiet regression, and maintained afterwards. Needed: what the suite must cover, who writes it, how long it may take, what happens when a skill resists testing, and how the suite is kept current. Done when the process is defined and one skill has been through it.

**t34** · Requests are archived automatically so what was asked survives the work item it became. Needed: where the archive lives, the id a request keeps from submission through amalgamation to the closing report, what a submitter can look up later, and retention. Relates to t9 and t10. Done when the lifecycle of one request is written end to end.

**t35** · A manager may not ratify a request written in the round that wrote it; that takes a later round with fresh context. A specialist's request is reviewed by the manager. Needed: a round id and an author stamped on every request, the check that refuses same-round ratification, and where it lives: a rule, a hook, or the request tool itself. Done when the check exists and is tested.

**t36** · Unwritten today: whether a specialist may run arbitrary shell, install packages, reach the network, push to git, or edit host files outside .claude/skills/; and which unattended mode the manager runs in (dontAsk, auto, bypassPermissions). Inbox requests are written by other agents, so this is also the prompt-injection surface. The user is writing an answer in chat. Done when the posture is written into the spec.

**t37** · Answered (q2): no caps for now, keep it simple. A round that stops because the plan's included usage ran out is treated exactly as a crash: the same automated rollback, then the round is redone from the known state. Left open: whether the launcher should notice the limit and stop cleanly rather than being cut off mid-tool, and whether caps are wanted once rounds have been run a few times. Done when the stop path shares the rollback of t38.

**t38** · Answered (q3): a crashed round is redone from a known state, never salvaged. Automated rollback first, in code: discard the branch, remove the worktree, revert a merge already made. Agents log as they go and an active worktree is marked active, so the wreckage is discoverable. Where rollback cannot be automatic, the manager establishes what was done and decides what to roll back. Done when the rollback script, the active marker and the manager path exist.

**t43** · Everything runs on Windows, where settings.local.json is not kept at the repository root, cross-session messaging uses named pipes with a required auth line, and worktrees, symlinks and long paths behave differently. Needed: one pass over the launch, worktree and messaging paths before building. Done when each footnote is checked and the spec says what it means here.

**t44** · Separate index per kind of agent, and in time a per-specialist index over that specialist's notes, so it can find detail it would otherwise miss. Still needed: when each index is rebuilt and by whom, whether a specialist re-indexes its own skill after a merge, what the note index costs to keep current, and the embedding pass cost in time. Done when the triggers and the owner are written.

**t45** · Each specialist owns one skill, but a change can touch a shared file or a second skill. Needed: who arbitrates, whether the manager serialises that work, and what stops two worktrees merging conflicting edits. Done when the arbitration is written.

**t46** · Adapt writes a per-skill configuration at init; scripts key newly found skills into it. Where an improvement goes: local (default), global (merged into the skill's own repo), later a retroactive reconciliation. Skills live in private GitHub repos: choose one remote per skill-project pair, or one remote per skill with a branch per project, which suits reconciliation. Needed: that choice, the file, format, defaults and discovery script. Done when the configuration exists.

**t47** · Answered (q31): a stall is any of no record for 20 minutes, a launcher error exit, or a round ending with its work item open, with room for more indicators. It notifies the host instance and the user: in the viewer when one is open, otherwise a Windows desktop notification. Needed: the detector, the viewer notice, the desktop notification path, and how the host instance is told. Done when a forced stall reaches both.

**t48** · The manager writes a question whenever it does not know what to do, without waiting for an answer. Later review turns each into a structural fix: a rule, a protocol line, a better briefing, or a tool. Needed: the instruction that makes the manager write instead of guess, how the entries are reviewed and grouped, and how a recurring question becomes a rule candidate. Relates to t18 and t31. Done when the loop runs once.

**t49** · Each agent gets a freeform notes folder it organises itself, never read whole at session start. Use is counted per note, and a high count surfaces it to the manager as a candidate finding; graduating one moves its information into a rule scoped to where it will be needed and removes the note. Each specialist gets vector-search files of its own over its notes. Needed: where the folders live, the counter, the graduation path, and the per-specialist index. Done when all four exist.

**t50** · Adapt can retire a skill, a rule or a meta tool, through a request ratified by a fresh manager context. Needed: the evidence thresholds (unused tool, never-firing or superseded rule, skill nothing asks for), how the host's use of a skill is checked first, where an archived thing goes, and how a retirement is reversed if it was wrong. Relates to t16. Done when the path is written and one retirement has been run.

**t51** · The dynamic request form routes on parsed answers. One candidate is a Haiku-class instance running the interview against a decision tree. It may be too much for that model. Needed: the decision tree, a trial on real requests, and a measure of whether the asking instance was routed down the right branch. The fallback is a scripted form with fixed branches. Done when the trial has a verdict.

**t52** · Answered (q18): work from both ends, iteratively. Each protocol is a collection of rules in a protocols folder with a manager branch and a specialist branch; the chore protocol sits with the specialists'. Each specialist gets its own copy on first assignment, changed only by request. Both protocols must describe the copy map and the made-up path of the agent's copy. Draft all three against the settled workflow, alongside t53 to t55. Done when three first drafts exist.

**t56** · Settled: the verifier is a medium specialist under a verifier protocol, with its own home. The manager designs each test in plain English with loose pseudocode; the verifier adapts it to the skill and environment, writes it into the sibling test skill, runs it before merge, checks the code it touches for fairness, and posts results to the group channel. Open: the test skill's name and layout, and the read denial for implementers. Done when those exist.

**t64** · Build option 1b of t63. The copy script writes .claude/copy-map.json entries pairing a copy's real folder with copies/<skill>/; merge, discard and rollback remove them. rule_router rewrites a real path under a mapped folder into its made-up path before matching, outside the never-gate-skills prefix. Tests: a gated rule fires on a copy, a removed entry stops it, a stale entry is cleared by rollback. Done when the tests pass in the workspace's rules-system copy.

**t65** · Per work folder, an append-only message sequence that every instance posts to with a command and reads in order, fetching only unseen entries. Messages carry an addressee, so a watcher can find new ones addressed to the manager and deliver them, likely by posting into the manager session's messaging socket, which starts a turn when it is idle. Needed: the file shape, read positions, post and read commands, the watcher, and the -p idle ceiling. Done when a specialist wakes the manager.

**t66** · A work item's history log gathers the entries of every specialist working on it. Needed: whether entries are copied or referenced, when the pull runs (on each write, at round end, or on read), how duplicates and ordering are handled, and whether rules-system gains an aggregate command. Done when a work item shows one ordered log of its specialists' events.

**t67** · The manager must see a skill's internals before any specialist exists, to decide whether an existing surface answers a request. Needed: where such a graph lives (manager home or a shared graphs folder), when it is built and refreshed, and whether a specialist inherits it on first assignment. Relates to t29. Done when the manager can query a graph of an unassigned skill.

**t68** · The manager's task points at a work folder; each specialist processifies the item into its own tasks linked back to that folder. rules-system links a sub-project to a parent task today (init --task, Parent line, viewer drill-down). Needed: check whether that covers a work folder as the link target and several specialists under one item, and extend it if not. Done when the viewer walks from the manager's task to every specialist's sub-tasks.

**t69** · Every maintained skill gets a terse, machine-facing surface document. Needed: its format and place, the step in the merge path that refreshes it, how it is generated at skill initialization, the scoped rule that delivers it, and a vector-search namespace spanning all surface documents for capability search. Relates to t32, t44, t67. Done when one skill has a current surface document the manager can search.

**t70** · One small metrics file per home folder holds note lookup counts, friction entry counts and rule firing counts for that agent. Needed: its format, the hooks that increment each count (a read of a note, a friction entry written, a rule injected for that agent), how an agent is identified from inside a hook, and the command that reads the file for the manager's reviews. Relates to t19, t49, t50. Done when all three counts rise without anyone writing them.
