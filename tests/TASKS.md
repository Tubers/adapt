# 📋 TASKS · tests

**Goal:** prove how the rule system behaves in a live session: injection, scope and runtime changes

- ✅ live check: a new rule, and an edited rule, reach the prompt with no reload · *2026-09-14* `t1`
- 🔄 **test every kind of sub-agent and session, down to the barest instance Claude Code allows** · *since 2026-09-14* `t2`

---

## Details

**t1** · Create a throwaway rule gated to one file in this folder, then touch that file in the same session and see whether the rule is injected; touch a file outside its gate and see nothing. Then edit the rule and touch the file again. Expected from the router code: rules and gates are read fresh on every tool call, so a NEW rule fires at once, but a rule is sent once per session, so an EDITED rule that already fired is not re-sent until a new session.

**t2** · Asked for by the user 2026-09-14. Built-in and custom agents, forks, background agents, new, resumed and headless sessions, and a bare instance with as few defaults as possible. For each: session and agent ids, hooks fired and their payload, rules injected, working folder, settings and permissions applied, context size. Feeds AOE's parked sub-agent rules draft (t20). Done means a findings table in history.
