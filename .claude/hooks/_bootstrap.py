"""Put the rules-system skill's script folder on sys.path, or say why it could not.

The machinery these hooks run on lives inside `.claude/skills/rules-system/scripts/`, with its own
documentation and its own tests. That direction is the sanctioned one in this repo: repo-side code
may read a skill, a skill may never read the repo.

`load()` returns the module or None. Every caller must treat None as FAIL OPEN - a hook that cannot
import its library must not block work, and must not silently pretend it checked something.
"""

import os
import sys
from pathlib import Path

REL = Path(".claude") / "skills" / "rules-system" / "scripts"


def project_dir(payload=None) -> Path:
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    if env:
        return Path(env)
    if payload and payload.get("cwd"):
        return Path(payload["cwd"])
    # These hooks live at <project>/.claude/hooks/, so the project is two levels up.
    return Path(__file__).resolve().parent.parent.parent


def load(payload=None):
    root = project_dir(payload)
    scripts = root / REL
    if not (scripts / "rules_lib.py").is_file():
        return None
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    try:
        import rules_lib  # noqa: E402
        return rules_lib
    except Exception:
        return None
