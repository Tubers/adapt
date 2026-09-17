"""Run `claude -p` as a probe, read what the session loaded, and leave nothing behind.

A probe is how Adapt's build proves claims about Claude Code: which skills, agents and plugins a
session sees, whether a hook fired, whether a subagent ran. Each probe:

1. starts `claude -p` in a given folder, on the cheapest model, with stream-json output;
2. parses the init event (model, skills, agents, plugins, permission mode) and the result events;
3. removes every trace the run left in the user's Claude folder: the transcript, any per-session
   folders named after the session, and a project entry in ~/.claude.json that the run added.

Probes cost a real (small) request. Set ADAPT_SKIP_LIVE=1 to skip tests that run them.
"""

import json
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

CLAUDE_HOME = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")
CLAUDE_JSON = Path.home() / ".claude.json"
DEFAULT_MODEL = "haiku"


@dataclass
class ProbeResult:
    returncode: int
    init: dict = field(default_factory=dict)
    results: list = field(default_factory=list)
    events: list = field(default_factory=list)
    stderr: str = ""
    session_ids: set = field(default_factory=set)
    removed: list = field(default_factory=list)

    @property
    def skills(self) -> list:
        return list(self.init.get("skills") or [])

    @property
    def agents(self) -> list:
        return list(self.init.get("agents") or [])

    @property
    def plugins(self) -> list:
        return [p.get("name") for p in self.init.get("plugins") or []]

    @property
    def final_text(self) -> str:
        return str(self.results[-1].get("result", "")) if self.results else ""

    @property
    def is_error(self) -> bool:
        return self.returncode != 0 or any(r.get("is_error") for r in self.results)


def live_disabled() -> bool:
    return os.environ.get("ADAPT_SKIP_LIVE") == "1"


def _project_keys() -> set:
    try:
        return set(json.loads(CLAUDE_JSON.read_text(encoding="utf-8")).get("projects", {}))
    except (OSError, ValueError):
        return set()


def _drop_project_keys(keys: set) -> list:
    if not keys:
        return []
    data = json.loads(CLAUDE_JSON.read_text(encoding="utf-8"))
    projects = data.get("projects", {})
    gone = [k for k in keys if k in projects]
    for k in gone:
        del projects[k]
    if gone:
        CLAUDE_JSON.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return ["~/.claude.json projects[%s]" % k for k in gone]


def _remove_session_traces(session_id: str) -> list:
    """Delete files and folders named after the session, one and two levels under CLAUDE_HOME."""
    removed = []
    if not session_id or not CLAUDE_HOME.is_dir():
        return removed
    candidates = list(CLAUDE_HOME.glob("*/%s*" % session_id))
    candidates += list(CLAUDE_HOME.glob("*/*/%s*" % session_id))
    parents = set()
    for path in candidates:
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
        else:
            path.unlink(missing_ok=True)
        removed.append(str(path))
        if path.parent.parent == CLAUDE_HOME / "projects":
            parents.add(path.parent)
    for project_dir in parents:                    # a project folder the run itself emptied
        if project_dir.is_dir() and not any(project_dir.iterdir()):
            project_dir.rmdir()
            removed.append(str(project_dir))
    return removed


def run(cwd: Path, prompt: str, *flags: str, model: str = DEFAULT_MODEL,
        env: dict | None = None, timeout: int = 300, keep: bool = False) -> ProbeResult:
    """Run one probe in cwd and clean up after it unless keep is set."""
    before = _project_keys()
    cmd = ["claude", "-p", prompt, "--model", model, "--output-format", "stream-json",
           "--verbose", *flags]
    proc = subprocess.run(cmd, cwd=cwd, env={**os.environ, **(env or {})},
                          stdin=subprocess.DEVNULL, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=timeout)
    result = ProbeResult(returncode=proc.returncode, stderr=proc.stderr)
    for line in proc.stdout.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        result.events.append(event)
        if event.get("session_id"):
            result.session_ids.add(event["session_id"])
        if event.get("type") == "system" and event.get("subtype") == "init" and not result.init:
            result.init = event
        elif event.get("type") == "result":
            result.results.append(event)
    if not keep:
        for sid in result.session_ids:
            result.removed += _remove_session_traces(sid)
        result.removed += _drop_project_keys(_project_keys() - before)
    return result
