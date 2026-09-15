RULE writing/viewer-replies - a reply the user sends through the viewer is answered through the viewer, never in chat.
- Covers every reply sent from the viewer page: an answer to a question (tasks ask) and an action marked done (tasks act).
- When tasks wait returns or ANSWERS WAITING arrives: run tasks answers, act on each reply, write NOTHING in chat. No echo of the answer, no summary, no "noted".
- Respond through the records the page shows live: tasks start | done --result | detail | block | unblock | drop, history add, or a follow-up tasks ask / tasks act on the same task. The change is the response.
- Not understood by the user: ask again, plainer, with tasks ask. Re-arm tasks wait in the background, default timeout, so it wakes the session only for a reply.
- NO TEXT after any submission to or from the viewer: no reply, no status, nothing after Claude Code's own "Background command ... completed" line. The harness prints that line; no rule can suppress it, and nothing may follow it.
- Chat only when the viewer cannot carry it: a long explanation, code or a diff to review, an error the user must see, a security warning, an irreversible step to confirm. Then say only that.
- Only if the harness then demands visible text: one line, "Replied in the viewer." Nothing more.
- A reply typed in chat is answered in chat. The viewer opening itself, and asking through it: writing/tasks.
