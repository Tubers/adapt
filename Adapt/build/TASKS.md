# 📋 TASKS · Adapt/build

**Goal:** build the Adapt skill as specified in spec/adapt-spec.md, phase by phase, following BUILD-PLAN.md

**Parent:** Adapt/ · t16

- ✅ 0.1 package layout: adapt/ (shim, workspace, install), tests/harness, scripts · *2026-09-17* `t1`
- 🔄 **0.2a harness: fixture host maker** · *since 2026-09-17* `t2`
- 🔜 0.2b harness: probe runner for claude -p `t3`
- 🔜 0.2c harness: leave-nothing-behind check `t4`
- 🔜 0.3 vendoring: copy rules-system and vector-search into the workspace template `t5`
- 🔜 0.4a tool fetcher: rtk at a pinned version with checksum `t6`
- 🔜 0.4b tool fetcher: graphify in a pinned uv environment `t7`
- 🔜 0.4c tool fetcher: tools/bin launchers `t8`
- 🔜 1.1 install: create the workspace beside the host `t9`
- 🔜 1.2 install: base workspace settings `t10`
- 🔜 1.3 install: trust and reach `t11`
- 🔜 1.4 install: write the shim into the host `t12`
- 🔜 1.5 install: skill inventory and config.json `t13`
- 🔜 1.6 install: manager records `t14`
- 🔜 1.7 install: idempotent re-init and clean removal `t15`

---

## Details

**t1** · Create the folders BUILD-PLAN.md names, with a short README for adapt/ saying what a host receives. Done when the tree exists and is committed.

**t2** · A function that creates a throwaway host project in the scratch folder: git init, two sample skills (one with a planted bug and a failing case), and removes it afterwards. Done when its own test creates and removes one cleanly.

**t3** · Start claude -p on the cheapest model in a given folder with given flags and environment, capture stream-json, parse the init event (model, skills, agents, plugins, permission mode) and the result, then delete the run's transcript and any config entry it created. Done when a probe in a fixture returns parsed data and leaves nothing behind.

**t4** · Snapshot the user's Claude config folders, the scratch folder and the machine's rtk and graphify data folders before a test run and compare after; fail the run on any residue. Done when a deliberately leaky test is caught.

**t5** · A script that copies both skills from this repo into adapt/workspace/.claude/skills/, excluding machine data, and reports drift between the copies and the originals. Done when both skills' own test suites pass inside the template copy.

**t6** · Download the pinned rtk release for the platform with gh or https, verify it against the release checksums, place it in a workspace's tools/bin. Done when a fixture workspace runs tools/bin/rtk --version and a bad checksum is refused.

**t7** · Create tools/graphify-venv with uv and install graphifyy at the pinned version; fail clearly when uv or Python 3.10+ is missing. Done when a fixture workspace runs the environment's graphify.

**t8** · Write the graphify launchers (sh and cmd) that call the pinned environment relative to their own location. Done when tools/bin/graphify --help works from Git Bash and PowerShell in a fixture workspace.

**t9** · Create <host>.adapt/ beside the host, git init it, lay out INBOX, NEW, EXTEND, REPAIR, Fulfilled, Aborted, Postponed, the homes, rules and tools. Done when init on a fixture host produces the tree.

**t10** · Write .claude/settings.json with claudeMdExcludes, disableBundledSkills, the design and doctor overrides, auto memory off, both cache TTLs at 1h, spawn depth 1 and RTK_TELEMETRY_DISABLED. Done when the file validates and a probe run shows no bundled skills.

**t11** · Mark the workspace trusted by writing hasTrustDialogAccepted for its path, and set permissions.additionalDirectories to the host's skill folder and the copies folder. Done when a probe run reads a host skill file without the untrusted-workspace warning, and uninstall removes the trust entry.

**t12** · Write <host>/.claude/skills/adapt/ with a placeholder SKILL.md and the script entry points (init, request, round, status). Done when a host session lists the adapt skill and nothing from the workspace.

**t13** · Scan the host's sibling skills into config.json with default per-skill options, and a discovery script that keys in a skill added later. Done when adding a skill to the fixture and rerunning discovery adds exactly that key.

**t14** · Create the manager's history, task and questions files in manager_home with the vendored rules-system. Done when rules.py tasks on manager_home shows an empty window with the manager's goal.

**t15** · A second init changes nothing and says so; an uninstall leaves the host byte-identical to before init. Done when both are tested on a fixture host.
