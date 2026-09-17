RULE writing/tasks - TASKS.md is a project's live task window: just done, NOW, next. Every project keeps its own TASKS.md, HISTORY.jsonl and QUESTIONS.jsonl in <project>/.rs/.
- FORMAT: heading "# 📋 TASKS · <project>", a **Goal:** line, a sub-project's **Parent:** <project>/ · <task> line, then one line per task ending in its short id (`t7`).
- The window: ✅ done, at most 2, date at the end. 🔄 in progress, exactly 1, bold, "since <date>". ⛔ blocked, reason in its details. 🔜 not started, any number, no date. ❓ after the status icon marks an open question, ❗ an action waiting on the user.
- Below "## Details": EVERY task has one short paragraph: what it is for and what done means. tasks add needs --details.
- COMMANDS ONLY: rules.py tasks [--in <folder>]; tasks add "<task>" --details P | start | done [--result R] | block --reason | unblock | drop --reason | detail | goal. done logs the task in history.
- Questions for the user: tasks ask <task> "<q>"; the user answers; tasks answers logs each as a decision. tasks withdraw <q> --reason takes one back.
- Actions, for what only the user can do (log in, accept a dialog, install): tasks act <task> "<what to do>"; the user marks it done in the viewer, or tasks acted <a> on their word; tasks answers logs it.
- rules.py view [folder] shows tasks, history and candidates as one live page. Once it opens, say NOTHING about it; speak only if it failed.
- While a viewer is open (rules.py view --status), questions and actions for the user go to it, not to chat; run tasks wait in the background to be told. No viewer open: ask in chat.
