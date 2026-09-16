# 📋 TASKS · spec

**Goal:** revise the Adapt skill spec with the user: spec/original.txt is the untouched first draft, spec/revised.txt the working revision

- ✅ where the user is required, and how a round reports in · *2026-09-16* `t42`
- ✅ one workspace per host, or a shared layer across hosts · *2026-09-16* `t41`
- 🔄 **fold in the user's own changes to the spec** · *since 2026-09-15* `t1`
- 🔜 reconcile Documentation Dogma with the existing writing rules `t4`
- 🔜 define THE MANAGER without a persistent instance `t6`
- 🔜 separate NEW, EXTEND and REPAIR, and define amalgamation `t9`
- 🔜 specify the request form and its python generator `t10`
- 🔜 fix When to Trigger and the duplicate check `t11`
- 🔜 define a round `t12`
- 🔜 manager launch: --bare or a normal session fenced by settings `t13`
- 🔜 specialists as subagents, not agent teams; haiku worker lifecycle `t15`
- 🔜 constant rules: a rules-system config for rules never removed or modified `t16`
- 🔜 agent system prompts for manager, specialist-medium and specialist-low `t17`
- 🔜 protocol rules for specialists and manager, and how they attach at spawn `t18`
- 🔜 friction entries: history kind, threshold hook, similarity grouping `t19`
- 🔜 skill copies, manager-approved merge, and two-way mirroring `t20`
- 🔜 first-run install: what Adapt init sets up `t21`
- 🔜 host-side Adapt commands `t22`
- 🔜 nested Adapt: an Adapt inside an Adapt `t23`
- 🔜 per-specialist rules folders and finding curation `t24`
- 🔜 place META TOOLS: root folder, inner skill, or both `t25`
- 🔜 launcher: regenerate the personal exclusions at every manager launch `t26`
- 🔜 strip the manager down: bundled skills, built-in agents, user plugins `t27`
- 🔜 let a specialist add its own LSP plugin without the interactive plugin command `t28`
- 🔜 code graph tooling for specialists, on top of LSP `t29`
- 🔜 quality assurance: how a round proves it delivered `t30`
- 🔜 the briefing: what each agent is given, and in what order `t31`
- 🔜 skill initialization: build a skill's automated test suite before the first change `t32`
- 🔜 meta tool exemption: the size and line limit below which scrutiny is reduced `t33`
- 🔜 request archive: every request kept, automatically `t34`
- 🔜 ratification: enforcing that no instance ratifies its own request `t35`
- 🔜 permissions posture: what agents may run and touch `t36`
- 🔜 budget for a round: caps, and what happens at the usage limit `t37`
- 🔜 recovery: what happens to a round that dies mid-way `t38`
- 🔜 Windows specifics: the mechanisms that carry a Windows footnote `t43`
- 🔜 who re-indexes vector-search, and what it costs `t44`
- 🔜 two specialists needing the same file `t45`
- 🔜 skill configuration: per-skill options, defaults, and the script that keeps it current `t46`
- 🔜 stall notice: tell the user when a round stalls or crashes `t47`
- 🔜 the manager's questions file as a diagnostic, and turning its entries into rules `t48`
- 🔜 notes folders: freeform space for the manager and every specialist `t49`

---

## Details

**t42** · The user starts a round and nothing else requires them until it ends. Needed: which acts need approval, such as a new skill, a rule deleted or changed, or a merge into a skill the user relies on; and how the user learns a round finished or stalled, beyond watching the manager's task file. Done when the gates and the notice are written.

**t41** · The workspace is per host project, so meta tools, findings and specialist rules would be rebuilt from scratch in every project. Needed: whether a shared layer exists, what it may hold, and how a project-specific fact is kept out of it. Done when the boundary is written.

**t1** · The user has many changes of their own: some needed, some functional alternatives judged better than the original. Take each in chat, write it into spec/revised.txt, and split out any that opens a new question as its own task. Done when the user says the list is exhausted.

**t4** · User scoped the dogma to the rules for THE MANAGER and SPECIALISTS and the documents they keep; now in spec/revised.txt. Open: dogma 1 restates writing/fact-ownership, dogma 2 writing/compressed-register; point, not restate. Dogma 3 fits on-demand folders read once on resume, but 'never have too few details' likely means too many. Done when each dogma points to its rule or is reworded.

**t6** · User defined the manager: a headless Opus 5 session launched in the Adapt folder, bare bones, only spawner of subagents and only creator of work items, with a home folder of continuity files plus its own history log and tasks file. Open: Notes and Memories overlap the history log and tasks file; decide which record owns each kind of fact.

**t9** · Proposal now in spec/revised.txt: requests naming the same skill and same need merge into one work item; vector-search suggests, manager confirms; source ids kept, details appended. Still open: NEW says new skills and improvements, which overlaps EXTEND. Done when the user accepts or changes the proposal and the categories no longer overlap.

**t10** · 'Mechanics of Request Submission' is empty, and the form is described twice: there and under 'When to Trigger'. Needed: headers, seed prompts that draw out friction (comprehension, time cost, intent cost, other vectors), use for both new requests and piggybacks on existing ones, and the command that generates it. Done when one section owns the form and the other points to it.

**t11** · When to Trigger now names INBOX (done under t3). Still open: before filing, an instance checks for a similar request; vector-search could do that check by meaning. Done when the trigger conditions and the duplicate check are defined.

**t12** · A round is a start-to-finish cycle on one work item, with the five steps in spec/revised.txt. It can grow when the manager ratifies a request raised inside it, and it can be reordered when the manager promotes an internal tool above the external request, which then waits for the next round. Open: how much work one round takes on, and when the manager may start one itself. Done when the user accepts both.

**t13** · One claude -p run per round in the workspace, no --bare and no resume. The comparison and the untested list live in spec/launch-options.md. Exclusions regenerated per launch (t26); bundled skills, built-in agents, plugins, auto memory and MCP off (t27). Left here: write the launch command with its permission mode and output capture, test --setting-sources project,local, test crossSessionInbound accept. Done when a run shows nothing host or personal.

**t15** · Docs: agent teams need an interactive session, never -p. Subagents may spawn subagents by default, 3 layers deep; CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH=1 turns it off and so enforces manager-only spawning. The skills field preloads full content but does not restrict; omit Skill from tools to restrict. omitClaudeMd exists. A fresh haiku subagent per batch is stateless. Done when spec fixes the agent model and haiku lifecycle.

**t16** · User wants some rules fixed for good. Needed: the config file and format naming them, and the enforcement point, likely the existing rule-approval hook refusing edits, moves and deletes of a listed rule. Done when format and enforcement are defined.

**t17** · Minimal starting directives that breadcrumb each agent to what it needs: its skill, its rules folder, its records, the commands it uses. Done when three drafts exist and the user approves them.

**t18** · Protocols are the workflow rules every specialist gets when spawned, tailorable per specialist; the manager has its own. Open: how a rule attaches at spawn (gate on the specialist folders, spawn prompt, SubagentStart hook injection). Includes the starting rule set Adapt ships. Done when the initial set is drafted and the attach mechanism chosen.

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

**t29** · The user is looking for a plugin or tool that builds a graph of a codebase, like a compiler AST, so an instance can see which parts affect which. Once found, decide how a specialist reaches it: a plugin loaded at launch, or a meta tool. Done when the tool is named and wired in, or the idea is dropped.

**t30** · Layers sketched in spec/revised.txt: acceptance criteria in the work item before assignment; a failing test first for a REPAIR; evidence not claims from the specialist; a verifier subagent with fresh context that re-runs tests and never sees the specialist's narrative; the manager merging only on that pass; a host-side check after the merge that reverts on failure; the round closed against the original request. Done when each step has a concrete form, a command and a rule.

**t31** · No agent carries context between sessions, so the briefing is the design. Order: own system prompt, protocol rules for its kind, work item with acceptance criteria, pointers to where it works and what it may touch, nothing else. Everything further is looked up, and what is worth keeping is written back before the agent ends. Relates to t17 and t18. Done when the order is fixed and each part has an owner.

**t32** · At init Adapt inventories the sibling skills. The first time it extends or repairs one, that skill goes through initialization: an automated suite is built first, robust enough to catch a quiet regression, and maintained afterwards. Needed: what the suite must cover, who writes it, how long it may take, what happens when a skill resists testing, and how the suite is kept current. Done when the process is defined and one skill has been through it.

**t33** · A small meta tool is narrow, internal-facing and built by the agents for themselves, so it carries less process: documentation is whatever its builders need. Needed: the actual limit in files, lines and blast radius, what scrutiny still applies (a smoke test, a name, an owner), and what happens when a tool grows past the limit. Done when the limit and the remaining checks are written.

**t34** · Requests are archived automatically so what was asked survives the work item it became. Needed: where the archive lives, the id a request keeps from submission through amalgamation to the closing report, what a submitter can look up later, and retention. Relates to t9 and t10. Done when the lifecycle of one request is written end to end.

**t35** · A manager may not ratify a request written in the round that wrote it; that takes a later round with fresh context. A specialist's request is reviewed by the manager. Needed: a round id and an author stamped on every request, the check that refuses same-round ratification, and where it lives: a rule, a hook, or the request tool itself. Done when the check exists and is tested.

**t36** · Unwritten today: whether a specialist may run arbitrary shell, install packages, reach the network, push to git, or edit host files outside .claude/skills/; and which unattended mode the manager runs in (dontAsk, auto, bypassPermissions). Inbox requests are written by other agents, so this is also the prompt-injection surface. The user is writing an answer in chat. Done when the posture is written into the spec.

**t37** · Answered (q2): no caps for now, keep it simple. A round that stops because the plan's included usage ran out is treated exactly as a crash: the same automated rollback, then the round is redone from the known state. Left open: whether the launcher should notice the limit and stop cleanly rather than being cut off mid-tool, and whether caps are wanted once rounds have been run a few times. Done when the stop path shares the rollback of t38.

**t38** · Answered (q3): a crashed round is redone from a known state, never salvaged. Automated rollback first, in code: discard the branch, remove the worktree, revert a merge already made. Agents log as they go and an active worktree is marked active, so the wreckage is discoverable. Where rollback cannot be automatic, the manager establishes what was done and decides what to roll back. Done when the rollback script, the active marker and the manager path exist.

**t43** · Everything runs on Windows, where settings.local.json is not kept at the repository root, cross-session messaging uses named pipes with a required auth line, and worktrees, symlinks and long paths behave differently. Needed: one pass over the launch, worktree and messaging paths before building. Done when each footnote is checked and the spec says what it means here.

**t44** · Answered in part: vector-search keeps a separate index per kind of agent, so a specialist never carries rules that do not apply to it. Still needed: when each index is rebuilt and by whom, whether a specialist re-indexes its own skill after a merge, and what the embedding pass costs in time. Done when the trigger and the owner are written.

**t45** · Each specialist owns one skill, but a change can touch a shared file or a second skill. Needed: who arbitrates, whether the manager serialises that work, and what stops two worktrees merging conflicting edits. Done when the arbitration is written.

**t46** · Adapt writes a configuration at init with options per skill, and scripts key a newly discovered skill into it when it is found. The first option is where an improvement goes: local (default), global (merged into the skill's own repo), and later a retroactive reconciliation onto a branch of that repo. Needed: the file, its format and place, the defaults, the discovery script, and what else belongs per skill. Relates to Adapt t6. Done when the configuration exists.

**t47** · While Adapt is young the user wants to hear about a stalled or crashed round directly, not by watching a file. Needed: what counts as a stall (no record written for N minutes, a launcher that exited non-zero, a round that ended without closing its work item), how the notice reaches the user, and when the safeguard can be retired. Done when the detector and the notice exist.

**t48** · The manager writes a question whenever it does not know what to do, without waiting for an answer. Later review turns each into a structural fix: a rule, a protocol line, a better briefing, or a tool. Needed: the instruction that makes the manager write instead of guess, how the entries are reviewed and grouped, and how a recurring question becomes a rule candidate. Relates to t18 and t31. Done when the loop runs once.

**t49** · Each agent gets a notes folder it organises itself and writes to without reservation. It is never read whole at session start; it is looked up. Needed: where it lives, whether vector-search indexes it and under which index, how a note graduates into a finding or rule, and whether anything prunes it. Relates to t31 and t44. Done when the folder has a place, an index and a graduation path.
