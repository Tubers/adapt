"""Shared by the handoff hooks: what counts as a LIVE handoff, and which skills one asks for.

A live handoff is a file named exactly HANDOFF.md that is not under an archive/, _backup/ or
.claude/ folder. A retired one keeps the same name but sits in its occasion folder under
.claude/skills/handoff/data/, so it never matches: that is the whole difference between a message
still waiting to be read and a record of one that was.

A handoff asks for skills in front matter at the very top of the file:

    ---
    skills: rules-system, vector-search
    ---

`skills: none` asks for nothing. A YAML list (`skills:` then `  - name` lines) is read too.
"""

import json
import os
import re

LIVE_NAME = "HANDOFF.md"
RETIRED_DIRS = frozenset({"archive", "_backup", ".claude"})
SKILLS_DIR = ".claude/skills"

_KEY_RE = re.compile(r"\s*skills\s*:\s*(.*)$", re.IGNORECASE)
_ITEM_RE = re.compile(r"\s*-\s*(\S+)\s*$")


def _parts(path: str, cwd: str):
    """Path segments, relative to the repo when the path is inside it, so that a folder named
    `archive` somewhere ABOVE the repo cannot make a live handoff look retired."""
    path = path.replace("\\", "/")
    if cwd and os.path.isabs(path):
        try:
            rel = os.path.relpath(path, cwd).replace("\\", "/")
            if not rel.startswith(".."):
                path = rel
        except ValueError:          # another drive on Windows
            pass
    return [p for p in path.split("/") if p not in ("", ".")]


def is_live_handoff(path: str, cwd: str = "") -> bool:
    parts = _parts(str(path or ""), cwd)
    return bool(parts) and parts[-1] == LIVE_NAME and not RETIRED_DIRS.intersection(parts[:-1])


def _names(raw: str):
    names = [n.strip(" '\"`/") for n in re.split(r"[,\s]+", raw.strip().strip("[]"))]
    return [n for n in names if n]


def requested_skills(path: str):
    """The skill names a handoff's front matter lists, [] for none, None when it has no
    front matter or no skills key."""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            lines = f.read(8192).splitlines()
    except OSError:
        return None
    if not lines or lines[0].strip() != "---":
        return None
    for i, line in enumerate(lines[1:40], start=1):
        if line.strip() == "---":
            return None
        m = _KEY_RE.match(line)
        if not m:
            continue
        names = _names(m.group(1))
        if not names:                       # a YAML list on the lines below
            for item in lines[i + 1:40]:
                im = _ITEM_RE.match(item)
                if not im:
                    break
                names += _names(im.group(1))
        return [] if [n.lower() for n in names] in ([], ["none"]) else names
    return None


def switched_off(cwd: str):
    """Skills .claude/settings.json turns off for everyone. Loading one would bypass that."""
    try:
        with open(os.path.join(cwd, ".claude", "settings.json"), encoding="utf-8") as f:
            overrides = json.load(f).get("skillOverrides") or {}
    except (OSError, ValueError, AttributeError):
        return set()
    return {name for name, mode in overrides.items() if mode == "off"}
