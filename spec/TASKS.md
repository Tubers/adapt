# 📋 TASKS · spec

**Goal:** revise the Adapt skill spec with the user: spec/original.txt is the untouched first draft, spec/revised.txt the working revision

- ✅ fix where Adapt sits: skill folder, project folder, or both · *2026-09-15* `t5`
- ✅ define SPECIALISTS as per-skill context folders · *2026-09-15* `t8`
- 🔄 **fold in the user's own changes to the spec** · *since 2026-09-15* `t1`
- 🔜 reconcile Documentation Dogma with the existing writing rules `t4`
- 🔜 define THE MANAGER without a persistent instance `t6`
- 🔜 define how sub-agents route requests through THE MANAGER `t7`
- 🔜 separate NEW, EXTEND and REPAIR, and define amalgamation `t9`
- 🔜 specify the request form and its python generator `t10`
- 🔜 fix When to Trigger and the duplicate check `t11`
- 🔜 define a round `t12`
- 🔜 manager launch: --bare or a normal session fenced by settings `t13`
- 🔜 keep Adapt's inner skills away from host-project instances `t14`
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

---

## Details

**t5** · rules/INDEX.md forbids any gate matching .claude/skills/**, so Adapt-wide RULES stored inside the skill cannot be gated rules. repo/dependency-direction: a skill never depends on the project or a sibling skill, yet Adapt edits other skills. Adapt task t4 (bundling rules-system, vector-search and Adapt into one skill) bears on this. Done when the spec fixes the location and the dependency direction.

**t8** · The original calls SPECIALISTS sub-agent managed directories. Sub-agents do not persist, so each subfolder is the context a fresh agent reads to work on that one skill. Done when the spec lists what a specialist folder holds and who writes it.

**t1** · The user has many changes of their own: some needed, some functional alternatives judged better than the original. Take each in chat, write it into spec/revised.txt, and split out any that opens a new question as its own task. Done when the user says the list is exhausted.

**t4** · User scoped the dogma to the rules for THE MANAGER and SPECIALISTS and the documents they keep; now in spec/revised.txt. Open: dogma 1 restates writing/fact-ownership, dogma 2 writing/compressed-register; point, not restate. Dogma 3 fits on-demand folders read once on resume, but 'never have too few details' likely means too many. Done when each dogma points to its rule or is reworded.

**t6** · User defined the manager: a headless Opus 5 session launched in the Adapt folder, bare bones, only spawner of subagents and only creator of work items, with a home folder of continuity files plus its own history log and tasks file. Open: Notes and Memories overlap the history log and tasks file; decide which record owns each kind of fact.

**t7** · Specialists talk to the manager through their questions file or built-in instance-to-instance messaging; user undecided. Docs: named subagents can message each other; agent teams are unavailable in -p. Done when the spec picks the channel and says where approval of a specialist request is recorded.

**t9** · Proposal now in spec/revised.txt: requests naming the same skill and same need merge into one work item; vector-search suggests, manager confirms; source ids kept, details appended. Still open: NEW says new skills and improvements, which overlaps EXTEND. Done when the user accepts or changes the proposal and the categories no longer overlap.

**t10** · 'Mechanics of Request Submission' is empty, and the form is described twice: there and under 'When to Trigger'. Needed: headers, seed prompts that draw out friction (comprehension, time cost, intent cost, other vectors), use for both new requests and piggybacks on existing ones, and the command that generates it. Done when one section owns the form and the other points to it.

**t11** · When to Trigger now names INBOX (done under t3). Still open: before filing, an instance checks for a similar request; vector-search could do that check by meaning. Done when the trigger conditions and the duplicate check are defined.

**t12** · User leans: a round is a start-to-finish cycle on one manager-created work item from the inbox. Proposal with five steps now in spec/revised.txt. Open: how much work one round takes on, and when the manager may start one itself. Done when the user accepts or changes it.

**t13** · Docs: --bare skips hooks, skills, subagents, plugins, MCP, auto memory and CLAUDE.md; only --add-dir skills load. Without --bare, a session in the Adapt folder loads host skills from every parent up to repo root, and user ~/.claude files unless --setting-sources drops user. Verify whether --settings and --agents restore hooks and agents under --bare; tests/ t2 overlaps. Done when the launch command is fixed and tested.

**t14** · Docs: a nested <subdir>/.claude/skills/ loads the first time a session reads or edits a file in that subdir; nested rules and CLAUDE.md load the same way. A host session touching Adapt files would gain rules-system, vector-search and meta-tools. Options: host settings written at init (skillOverrides off, deny Skill(...)), a hook that blocks host reads inside Adapt, an Adapt command as the only interface. Done when chosen and tested.

**t15** · Docs: agent teams need an interactive session; in -p no teammates spawn; teammates cannot nest; a definition's skills field is not applied to teammates. So specialists are subagents of the manager, persistent only through files. Verify subagents cannot spawn subagents and that the skills field preloads. A fresh haiku subagent per batch is stateless by construction; no idle instance needed. Done when spec fixes both.

**t16** · User wants some rules fixed for good. Needed: the config file and format naming them, and the enforcement point, likely the existing rule-approval hook refusing edits, moves and deletes of a listed rule. Done when format and enforcement are defined.

**t17** · Minimal starting directives that breadcrumb each agent to what it needs: its skill, its rules folder, its records, the commands it uses. Done when three drafts exist and the user approves them.

**t18** · Protocols are the workflow rules every specialist gets when spawned, tailorable per specialist; the manager has its own. Open: how a rule attaches at spawn (gate on the specialist folders, spawn prompt, SubagentStart hook injection). Includes the starting rule set Adapt ships. Done when the initial set is drafted and the attach mechanism chosen.

**t19** · Needs a friction kind in rules-system history; a hook that notifies an instance after N new friction entries since its last notice, N configurable; grouping of similar entries by meaning with vector-search; manager commands to read specialist histories filtered for friction. Done when kind, hook, config and grouping are defined.

**t20** · Specialists work on copies, probably git worktrees (verify the subagent isolation worktree field). The manager approves each merge. Changes mirror between a host sibling skill and Adapt's inner copy both ways. Needed: branch naming, conflict handling, which side wins. Relates to Adapt t13. Done when the flow is defined.

**t21** · First init spawns the manager and runs build scripts: inventory the user's skill environment, create local data folders and configs, load Adapt's own skills, create the manager's records, write any host-side settings. Needed: the step list, idempotent re-init, and what later inits do. Relates to Adapt t2. Done when the step list is defined.

**t22** · What a host-project instance can run against Adapt: init, submit a request (the form), read the manager's tasks and history in filtered slices, start a round. Done when the command list and each command's output are defined.

**t23** · User allows chains of Adapts building tools to build tools. Needed: which Adapt owns which skills, how a nested manager is launched and reports up, and any depth limit. Done when the spec states them.

**t24** · Each specialist gets rules/<skill name>/ holding its findings; it curates them into rules gated to code files or skill documents. Needed: how this fits rules-system candidates and approval, and who approves a specialist's new rule. Done when defined.

**t25** · The spec keeps META TOOLS as a root folder, and specialists are preloaded with it as a skill, which lives in .claude/skills/. Decide the one real location and how the other refers to it. Done when the spec names it.
