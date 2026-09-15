# 📋 TASKS · Adapt

**Goal:** build the Adapt environment and the Adapt skill: its spec, how its skills are bundled, installed, configured, versioned and shown

- ✅ viewer: click a task with a sub-project to open that sub-project's tasks in a separate window · *2026-09-15* `t12`
- ✅ git and GitHub integration: version the Adapt repo and publish the skills from GitHub · *2026-09-15* `t5`
- 🔄 **delete the stale OneDrive copy of Adapt** · *since 2026-09-15* `t14`
- 🔜 review and revise the Adapt spec, Adaptive Tools.txt `t1`
- 🔜 an installer script per skill that reads the manifest and terraforms a project `t2`
- 🔜 fetch the embedding model when no preinstalled copy is found `t3`
- 🔜 consider bundling rules-system, vector-search and the Adapt skill into one skill named adapt `t4`
- 🔜 consider a configuration file for each custom skill and for the Adapt skill `t6`
- 🔜 consider packaging the status line as a personal Claude Code plugin `t7`
- 🔜 history friction log line, built with a rule `t8`
- 🔜 mirror Adapt changes into every project that uses its skills `t13`
- 🔜 a custom lightweight executable for the task and history viewer `t10`

---

## Details

**t12** · Asked for by the user 2026-09-14. Today a sub-project link replaces the current page. Instead, clicking a task with a sub-project (the 🗂 marker) opens a second window on that sub-project's viewer, so parent and sub-tasks stay visible side by side. Decide: the task line or a button, one window per sub-project or one reused. Done means drill-down opens its own window and both stay live.

**t5** · Asked for by the user 2026-09-14. git init in Adapt with a .gitignore for machine state (search indexes, per-session state, rules-firings.jsonl, __pycache__), a GitHub remote through the gh CLI, and the rules and hooks that go with version control. GitHub also becomes the installer's source: install a skill from a tagged release. Done means Adapt is committed and pushed, and an install from GitHub works.

**t14** · The user said yes to deleting C:\Users\ljcg3\OneDrive\Desktop\Adapt permanently (q7, 2026-09-15), so it cannot be confused with C:\dev\Adapt. Not done in the session that asked: that session ran from the OneDrive folder, and its hooks load from there. Done from a session started in C:\dev\Adapt: confirm nothing there is newer than C:\dev\Adapt, then Remove-Item -Recurse -Force, then log it.

**t1** · Read the spec whole, then propose changes: gaps (request template, the round, manager and specialist scope), conflicts with what is built (rules, not a CLAUDE.md line; per-project records; the parked sub-agent rules work). ADDENDUM (the user, 2026-09-14): also weigh a claudeMdExcludes setting in Adapt, so no CLAUDE.md from a parent folder or the user level loads; none exists yet. Changes go to the user first. Done: an accepted revised spec.

**t2** · Copies the skill, merges its hooks and settings into .claude/settings.json without clobbering, writes its rules and gate lines, creates data folders, checks Python packages, and installs a required skill first. Idempotent, with a dry run and an uninstall. Done means installing into an empty folder reproduces this setup.

**t3** · vector-search needs voyage-4-nano ONNX (431 MB). The installer looks for RULE_SEARCH_MODEL or the default Desktop path, and downloads it when absent, checking its hash. Done means a machine with no model gets a working search index from one install.

**t4** · Asked for by the user 2026-09-14. Weigh one skill against three: one install, one config and no cross-skill import (vector-search today imports rules-system's rules_lib), against size, a single point of failure, and the parked sub-agent rules subsystem, which wants each rule set to have its own search. Map what moves where and what the hooks and manifest become. Done means a proposal the user accepts.

**t6** · Asked for by the user 2026-09-14; caveman is left out. Settings now hard-coded in each skill would move to one config file per skill with project overrides: rules-system thresholds (0.80, 0.70, 0.60, stale days, window sizes, viewer timings, procedure areas, tolerated globs), vector-search floors, model path and threads, handoff data paths, and whatever the Adapt spec needs. The installer writes them. Done means an accepted proposal, then the files in use.

**t7** · Asked for by the user 2026-09-14: a personal plugin, not a skill. Now user-level in ~/.claude: settings.json statusLine runs statusline-command.py (with its .sh twin, a toggle, a notice state, a RAG config, a usage cache) and a Stop hook, hooks/usage_notice.py. Work out the plugin format (manifest, hooks, statusLine, install scope), then build it. Done means a proposal the user accepts, then the plugin installed and working.

**t8** · The user, 2026-09-14. A friction entry records any time a plan was thwarted and had to divert: a pivot, a detour, a new path, what forced it and what it cost. It also covers a cumbersome, slow or input-heavy skill, command or rule. history add --kind friction, a rule for when to log one and how it differs from dead-end (an approach dropped for good), a viewer chip, upkeep counts. Feeds Adapt's improvement requests. Done: kind, rule, viewer support.

**t13** · So a skill, hook or rule improved here reaches every other project that uses the Adapt skills without copying by hand; carries t5's second goal (q8): a project installs the skills from github.com/Tubers/adapt. Candidates: a Claude Code plugin marketplace served from the repo (/plugin update), a git submodule or subtree of .claude/ per project, or the t2 installer pulling a tagged release. Project records stay local. Done: a change pushed here reaches a second project with one command.

**t10** · Asked for by the user 2026-09-14. A small native window instead of a browser tab, hosting the same page and local server: candidates are a WebView2 host in C++ or C#, pywebview, or Tauri, judged on size, start time and no install step. For the future: the user is still iterating on the viewer (q5, 2026-09-15), so it waits at the back of the queue until they call the look settled. Done means one small executable that replaces the browser tab.
