# 📋 TASKS · Adapt/build

**Goal:** build the Adapt skill as specified in spec/adapt-spec.md, phase by phase, following BUILD-PLAN.md

**Parent:** Adapt/ · t16

- ✅ 0.2c harness: leave-nothing-behind check · *2026-09-17* `t4`
- ✅ 0.3 vendoring: copy rules-system and vector-search into the workspace template · *2026-09-17* `t5`
- 🔄 **0.3b portable tests for the vendored vector-search** · *since 2026-09-17* `t16`
- 🔜 0.4a tool fetcher: rtk at a pinned version with checksum `t6`
- 🔜 0.4b tool fetcher: graphify in a pinned uv environment `t7`
- 🔜 0.4c tool fetcher: tools/bin launchers `t8`
- 🔜 0.4d embedding model: where the workspace finds it, and fetching it `t17`
- 🔜 1.1 install: create the workspace beside the host `t9`
- 🔜 1.2 install: base workspace settings `t10`
- 🔜 1.3 install: trust and reach `t11`
- 🔜 1.4 install: write the shim into the host `t12`
- 🔜 1.5 install: skill inventory and config.json `t13`
- 🔜 1.6 install: manager records `t14`
- 🔜 1.7 install: idempotent re-init and clean removal `t15`

---

## Details

**t4** · Snapshot the user's Claude config folders, the scratch folder and the machine's rtk and graphify data folders before a test run and compare after; fail the run on any residue. Done when a deliberately leaky test is caught.

**t5** · A script that copies both skills from this repo into adapt/workspace/.claude/skills/, excluding machine data, and reports drift between the copies and the originals. Done when both skills' own test suites pass inside the template copy.

**t16** · vector-search's run_tests.py assumes this repository's own rules (it expects lifecycle/handoff among them) and its golden set asks about them, so it fails inside the workspace template. Needed: split plumbing checks from repository-specific ones, and give the workspace copy a fixture rule set and a small golden set of its own. Done when the vendored copy's suite passes against a fixture workspace.

**t6** · Download the pinned rtk release for the platform with gh or https, verify it against the release checksums, place it in a workspace's tools/bin. Done when a fixture workspace runs tools/bin/rtk --version and a bad checksum is refused.

**t7** · Create tools/graphify-venv with uv and install graphifyy at the pinned version; fail clearly when uv or Python 3.10+ is missing. Done when a fixture workspace runs the environment's graphify.

**t8** · Write the graphify launchers (sh and cmd) that call the pinned environment relative to their own location. Done when tools/bin/graphify --help works from Git Bash and PowerShell in a fixture workspace.

**t17** · vector-search defaults to a model folder on this machine's OneDrive desktop (voyage-4-nano-onnx), overridable by RULE_SEARCH_MODEL. A workspace must name its model location explicitly and fetch the model when it is missing. Relates to Adapt task t3. Done when a fixture workspace runs a search with the model found or fetched, and a missing model gives a clear message.

**t9** · Create <host>.adapt/ beside the host, git init it, lay out INBOX, NEW, EXTEND, REPAIR, Fulfilled, Aborted, Postponed, the homes, rules and tools. Done when init on a fixture host produces the tree.

**t10** · Write .claude/settings.json with claudeMdExcludes, disableBundledSkills, the design and doctor overrides, auto memory off, both cache TTLs at 1h, spawn depth 1 and RTK_TELEMETRY_DISABLED. Done when the file validates and a probe run shows no bundled skills.

**t11** · Mark the workspace trusted by writing hasTrustDialogAccepted for its path, and set permissions.additionalDirectories to the host's skill folder and the copies folder. Done when a probe run reads a host skill file without the untrusted-workspace warning, and uninstall removes the trust entry.

**t12** · Write <host>/.claude/skills/adapt/ with a placeholder SKILL.md and the script entry points (init, request, round, status). Done when a host session lists the adapt skill and nothing from the workspace.

**t13** · Scan the host's sibling skills into config.json with default per-skill options, and a discovery script that keys in a skill added later. Done when adding a skill to the fixture and rerunning discovery adds exactly that key.

**t14** · Create the manager's history and task files in manager_home with the vendored rules-system. Its init also creates a questions file, which Adapt does not use: remove it. Done when rules.py tasks on manager_home shows an empty window with the manager's goal and no questions file is left.

**t15** · A second init changes nothing and says so; an uninstall leaves the host byte-identical to before init. Done when both are tested on a fixture host.
