"""Shared plumbing for the self-tests: checks, a throwaway clone of the project, and hook and CLI runners.

A self-test proves an INSTALLED skill works in this project: its files are where they should be, its hooks
are registered in .claude/settings.json and answer the way their safeguards promise, and its commands carry
out a real workflow. Anything that writes runs in a clone under the temp folder, so the project's own
records are never touched. Read-only checks run against the real project.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]          # <project>/Adapt/selftest/_common.py
PY = sys.executable


class Suite:
    def __init__(self, name):
        self.name, self.passed, self.failed = name, 0, []
        print("=" * 78 + "\n%s\n" % name + "=" * 78)

    def section(self, title):
        print("\n" + title)

    def check(self, what, ok, detail=""):
        if ok:
            self.passed += 1
            print("  PASS  " + what)
        else:
            self.failed.append(what)
            print("  FAIL  %s   %s" % (what, str(detail)[:300]))

    def finish(self):
        print("\n%s: %d passed, %d failed" % (self.name, self.passed, len(self.failed)))
        for f in self.failed:
            print("  failed: " + f)
        return 1 if self.failed else 0


def env_for(root, state, session="selftest-session"):
    env = dict(os.environ)
    env.update({"CLAUDE_PROJECT_DIR": str(root), "CLAUDE_RULE_STATE_DIR": str(state),
                "CLAUDE_CODE_SESSION_ID": session, "PYTHONIOENCODING": "utf-8"})
    return env


def clone(tmp: Path) -> Path:
    """A copy of the project's machinery (skills without their data, hooks, settings, rules) to write into."""
    dst = tmp / ROOT.name
    (dst / ".claude").mkdir(parents=True)
    noise = shutil.ignore_patterns("__pycache__", "*.pyc")
    for skill in (ROOT / ".claude" / "skills").iterdir():
        shutil.copytree(skill, dst / ".claude" / "skills" / skill.name,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "data"))
        (dst / ".claude" / "skills" / skill.name / "data").mkdir(exist_ok=True)
    shutil.copytree(ROOT / ".claude" / "hooks", dst / ".claude" / "hooks", ignore=noise)
    for f in ("settings.json",):
        shutil.copy2(ROOT / ".claude" / f, dst / ".claude" / f)
    shutil.copytree(ROOT / "rules", dst / "rules", ignore=noise)
    return dst


def hook(root, name, payload, state, env_extra=None):
    """Run one hook of `root` with a payload. Returns (parsed JSON or None, raw stdout)."""
    env = env_for(root, state)
    env.update(env_extra or {})
    payload = dict(payload)
    payload.setdefault("cwd", str(root))
    p = subprocess.run([PY, str(Path(root) / ".claude" / "hooks" / name)], input=json.dumps(payload),
                       capture_output=True, text=True, encoding="utf-8", env=env, cwd=str(root), timeout=120)
    out = p.stdout.strip()
    try:
        return (json.loads(out) if out else None), out
    except ValueError:
        return None, out


def decision(obj):
    return ((obj or {}).get("hookSpecificOutput") or {}).get("permissionDecision")


def context(obj):
    return ((obj or {}).get("hookSpecificOutput") or {}).get("additionalContext", "")


def cli(root, script, args, state, session="selftest-session", timeout=300):
    """Run a skill script of `root`, e.g. ('rules-system', 'rules.py'). Returns (returncode, stdout+stderr)."""
    path = Path(root) / ".claude" / "skills" / script[0] / "scripts" / script[1]
    p = subprocess.run([PY, str(path)] + list(args), capture_output=True, text=True, encoding="utf-8",
                       env=env_for(root, state, session), cwd=str(root), timeout=timeout)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def settings(root=ROOT) -> dict:
    return json.loads((Path(root) / ".claude" / "settings.json").read_text(encoding="utf-8"))


def registered(root, hook_file):
    """[(event, matcher)] for every place .claude/settings.json runs this hook file."""
    out = []
    for event, groups in (settings(root).get("hooks") or {}).items():
        for g in groups:
            for h in g.get("hooks", []):
                if hook_file in h.get("command", ""):
                    out.append((event, g.get("matcher", "")))
    return out


def temp_dir(prefix):
    return Path(tempfile.mkdtemp(prefix=prefix))
