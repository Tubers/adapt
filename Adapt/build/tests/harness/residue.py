"""Fail a test run that leaves anything behind.

guard() snapshots the places a test run can litter, runs the body, and raises if anything new
appeared there that the body did not clean up:

- the user's Claude folder: projects, session-env, file-history, todos, shell-snapshots, jobs,
  down to two levels;
- project entries in ~/.claude.json;
- fixture parents (adapt-fixture-*) in the test root;
- the data folders rtk and graphify create for the user: %LOCALAPPDATA%/rtk, %APPDATA%/rtk,
  ~/.config/rtk, ~/.graphify.

It compares NEW entries only. A file that already existed and changed (this session's own
transcript, say) is not residue. A Claude session running elsewhere on the machine at the same
time can create entries too; pass ignore= patterns, or rerun, if that happens.
"""

import contextlib
import fnmatch
import os
import tempfile
from pathlib import Path

from . import probe

CLAUDE_SUBDIRS = ("projects", "session-env", "file-history", "todos", "shell-snapshots", "jobs")


def _watched_roots() -> list:
    roots = [probe.CLAUDE_HOME / d for d in CLAUDE_SUBDIRS]
    for var in ("LOCALAPPDATA", "APPDATA"):
        if os.environ.get(var):
            roots.append(Path(os.environ[var]) / "rtk")
    roots += [Path.home() / ".config" / "rtk", Path.home() / ".graphify"]
    return roots


def _test_root() -> Path:
    return Path(os.environ.get("ADAPT_TEST_ROOT") or tempfile.gettempdir())


def snapshot() -> set:
    entries = set()
    for root in _watched_roots():
        if root.exists():
            entries.add(str(root))
            if root.is_dir():
                for child in root.iterdir():
                    entries.add(str(child))
                    if child.is_dir():
                        entries.update(str(g) for g in child.iterdir())
    entries.update("~/.claude.json:" + k for k in probe._project_keys())
    entries.update(str(p) for p in _test_root().glob("adapt-fixture-*"))
    return entries


class ResidueError(AssertionError):
    pass


@contextlib.contextmanager
def guard(ignore: tuple = ()):
    before = snapshot()
    yield
    new = sorted(e for e in snapshot() - before
                 if not any(fnmatch.fnmatch(e, pat) for pat in ignore))
    if new:
        raise ResidueError("test run left %d new entries:\n  %s" % (len(new), "\n  ".join(new)))
