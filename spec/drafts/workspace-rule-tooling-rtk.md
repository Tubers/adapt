Draft of a rule for the Adapt workspace, not a rule of this repository. It is mined from the
instruction block `rtk init` (0.49.0) writes into a project, and it becomes
`rules/tooling/rtk.rule.md` in the workspace, gated on `cmd:` triggers for any Bash command, since
the rtk hook rewrites every Bash call for every agent.

--- rule text ---
RULE tooling/rtk - command output is condensed by rtk; trust it, batch commands, and fall back to rtk proxy only when output is unusable.
- A hook rewrites your Bash commands into their rtk form and condenses what they print. Treat the condensed result as complete: every signal is kept, noise is dropped.
- Run commands normally. Batch related commands into one call to save turns.
- A truncated result states its own recovery path in its output. Follow it.
- Re-run a command as rtk proxy <cmd> only when its result is unusable: empty when output was clearly expected, contradicting its exit code, or garbled.
- Test evidence for a merge needs the full failure detail: when a condensed test result hides it, re-run with rtk proxy.
--- end ---

Source text, as rtk wrote it, for comparison at each upgrade:

    <!-- rtk-instructions v2 -->
    # Command output

    Command output here is condensed to save tokens, keeping every signal and
    dropping costly noise. Treat it as the complete result: run commands
    normally, and batch related commands into one call to avoid extra turns.
    Truncated results state their recovery path in their own output. Re-run a
    command as `rtk proxy <cmd>` only when its result is unusable: empty when
    output was clearly expected, contradicting its exit code, or garbled.
    <!-- /rtk-instructions -->

Hook, as Adapt writes it (rtk's own global init would put it in the user's settings instead):

    PreToolUse, matcher "Bash": <pinned rtk path> hook claude

What the hook returns, observed in the trial for `git status`:

    {"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecisionReason":"RTK auto-rewrite","updatedInput":{"command":"rtk git status"}}}

Added by the rule above and not in rtk's text: the line on test evidence, because Adapt's merge gate
reads test output.
