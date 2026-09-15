# 📋 TASKS · spec

**Goal:** revise the Adapt skill spec with the user: spec/original.txt is the untouched first draft, spec/revised.txt the working revision

- 🔄 **fold in the user's own changes to the spec** · *since 2026-09-15* `t1`
- 🔜 load Adapt at session start without a CLAUDE.md `t2`
- 🔜 name the global repo and where skill_improvement and skill_development live `t3`
- 🔜 reconcile Documentation Dogma with the existing writing rules `t4`
- 🔜 fix where Adapt sits: skill folder, project folder, or both `t5`
- 🔜 define THE MANAGER without a persistent instance `t6`
- 🔜 define how sub-agents route requests through THE MANAGER `t7`
- 🔜 define SPECIALISTS as per-skill context folders `t8`
- 🔜 separate NEW, EXTEND and REPAIR, and define amalgamation `t9`
- 🔜 specify the request form and its python generator `t10`
- 🔜 fix When to Trigger and the duplicate check `t11`
- 🔜 define a round `t12`

---

## Details

**t1** · The user has many changes of their own: some needed, some functional alternatives judged better than the original. Take each in chat, write it into spec/revised.txt, and split out any that opens a new question as its own task. Done when the user says the list is exhausted.

**t2** · The original puts 'all instances must load Adapt at the start' in a global CLAUDE.md at AOE folder level. repo/no-claude-md bans every CLAUDE.md and guard_docs.py refuses the write. Candidates: a SessionStart hook, a gated rule, or the skill description alone. Weigh that anything loaded every session is paid on every request, the reason CLAUDE.md is banned. Done when the spec names the mechanism and its cost.

**t3** · AOE appears here only as a rule-set name (.claude/skills/rules-system/data/AOE/). Neither skill_improvement nor skill_development is in this repo, yet the spec says Adapt subsumes both. Done when the spec names the source repo, both folder locations, and how their contents migrate into Adapt.

**t4** · Dogma 1 (Information Independence) is already writing/fact-ownership; dogma 2 (Condense, Compress, Refactor) is writing/compressed-register. Dogma 3 (Context Is Tax Free) contradicts the premise of repo/no-claude-md that context is paid on every request, and 'never have too few details' likely means too many. Done when each dogma points to its rule or is reworded, with no duplicated fact.

**t5** · rules/INDEX.md forbids any gate matching .claude/skills/**, so Adapt-wide RULES stored inside the skill cannot be gated rules. repo/dependency-direction: a skill never depends on the project or a sibling skill, yet Adapt edits other skills. Adapt task t4 (bundling rules-system, vector-search and Adapt into one skill) bears on this. Done when the spec fixes the location and the dependency direction.

**t6** · Claude Code has no persistent instance. The workable form is a folder a fresh session reads to resume as the manager. Its Notes and Memories overlap each project's history log, task window and handoffs. Done when the spec says how a session becomes the manager, which files it keeps, and which existing record owns each kind of fact.

**t7** · The original says Adapt sub-agents file requests only via THE MANAGER, with its approval. Sub-agents are short-lived and report only to their parent. Done when the spec gives the concrete path a sub-agent request takes and where approval is recorded.

**t8** · The original calls SPECIALISTS sub-agent managed directories. Sub-agents do not persist, so each subfolder is the context a fresh agent reads to work on that one skill. Done when the spec lists what a specialist folder holds and who writes it.

**t9** · NEW says 'new skills and improvements', which overlaps EXTEND. The manager amalgamates inbox requests into single submissions, but the unit and the merge rule are undefined. Done when each category has a non-overlapping definition and the spec says how requests merge.

**t10** · 'Mechanics of Request Submission' is empty, and the form is described twice: there and under 'When to Trigger'. Needed: headers, seed prompts that draw out friction (comprehension, time cost, intent cost, other vectors), use for both new requests and piggybacks on existing ones, and the command that generates it. Done when one section owns the form and the other points to it.

**t11** · 'When to Trigger' still names the old skill_improvments folder, not INBOX. Before filing, an instance checks for a similar request; vector-search could do that check by meaning. Done when the trigger conditions name INBOX and the spec defines the duplicate check.

**t12** · The original says Adapt executes a round, a top-to-bottom sweep acting on current state, usually started by the user. Undefined: who may start one, its steps in order, and what it outputs. Done when the spec defines all three.
