#!/usr/bin/env python3
"""SessionStart hook: put this repo's tools/bin first on PATH for every later Bash tool call.

WHY
---
rtk's hook rewrites commands to a bare `rtk`, and graphify's nudge tells the agent to run a bare
`graphify`. Both only work if the pinned tools are on PATH. Copying them into a folder on the
user's own PATH works but is machine-wide; this keeps them inside the repo.

HOW
---
Claude Code gives SessionStart hooks a file, CLAUDE_ENV_FILE, whose export lines are sourced before
each Bash tool call. This hook appends one PATH export to it. Probed on Windows with Claude Code
2.1.273 (2026-09-17): it works for a fresh session. GitHub issues report it is not re-sourced after
/clear or on a resumed session, so a resumed session may lose the tools until it is restarted.

The PowerShell tool does not source the file. tools/bin also holds graphify.cmd for that case, but
PowerShell only finds it if tools/bin is on the Windows PATH.

Fails open: any problem, and the hook prints nothing and exits 0.
"""

import os
import sys


def bash_path(path: str) -> str:
    """C:\\dev\\Adapt -> /c/dev/Adapt, the form Git Bash expects in PATH."""
    p = path.replace("\\", "/")
    if len(p) > 1 and p[1] == ":":
        p = "/" + p[0].lower() + p[2:]
    return p


def main() -> int:
    env_file = os.environ.get("CLAUDE_ENV_FILE", "")
    project = os.environ.get("CLAUDE_PROJECT_DIR", "")
    if not env_file or not project:
        return 0
    tools_bin = os.path.join(project, "tools", "bin")
    if not os.path.isdir(tools_bin):
        return 0
    with open(env_file, "a", encoding="utf-8") as fh:
        fh.write('export PATH="%s:$PATH"\n' % bash_path(tools_bin))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)
