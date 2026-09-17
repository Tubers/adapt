"""Throwaway host projects for testing Adapt.

make_host() builds a small host project the way Adapt will meet one in the wild: a git repository
with a .claude/skills folder holding two sibling skills. One skill is sound; the other carries a
planted bug with a test that exposes it, so a REPAIR round has something real to fix.

Everything is created under one parent folder, because Adapt places its workspace and its copies
beside the host. remove_host() deletes that parent and nothing else.
"""

import os
import shutil
import stat
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

HOST_NAME = "host"

GREET_SKILL = '''---
name: greet
description: Greets a person by name. Use when asked to greet someone.
---

Run `python scripts/greet.py <name>`. It prints `Hello, <name>!`.
'''

GREET_SCRIPT = '''import sys


def greet(name: str) -> str:
    return "Hello, %s!" % name


if __name__ == "__main__":
    print(greet(sys.argv[1] if len(sys.argv) > 1 else "world"))
'''

GREET_TEST = '''import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from greet import greet  # noqa: E402


class GreetTest(unittest.TestCase):
    def test_greets_by_name(self):
        self.assertEqual(greet("Ada"), "Hello, Ada!")


if __name__ == "__main__":
    unittest.main()
'''

CALC_SKILL = '''---
name: calc
description: Adds two numbers. Use when asked to add numbers.
---

Run `python scripts/calc.py add <a> <b>`. It prints the sum.
'''

# The planted bug: add() subtracts. test_add_positive exposes it; test_add_zero does not.
CALC_SCRIPT = '''import sys


def add(a: int, b: int) -> int:
    return a - b


if __name__ == "__main__":
    op, a, b = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
    if op == "add":
        print(add(a, b))
'''

CALC_TEST = '''import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from calc import add  # noqa: E402


class CalcTest(unittest.TestCase):
    def test_add_zero(self):
        self.assertEqual(add(5, 0), 5)

    def test_add_positive(self):
        self.assertEqual(add(2, 3), 5)


if __name__ == "__main__":
    unittest.main()
'''

SKILLS = {
    "greet": {"SKILL.md": GREET_SKILL, "scripts/greet.py": GREET_SCRIPT,
              "tests/test_greet.py": GREET_TEST},
    "calc": {"SKILL.md": CALC_SKILL, "scripts/calc.py": CALC_SCRIPT,
             "tests/test_calc.py": CALC_TEST},
}
BUGGY_SKILL = "calc"
BUGGY_TEST = "test_add_positive"


@dataclass
class Host:
    parent: Path          # the folder holding the host and, later, its workspace and copies
    root: Path            # the host project
    skills: Path          # root/.claude/skills

    def skill(self, name: str) -> Path:
        return self.skills / name


def _git(cwd: Path, *args: str) -> str:
    out = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True)
    return out.stdout.strip()


def make_host(base: Path | None = None) -> Host:
    """Create a fresh host project under a new parent folder and return its paths.

    base defaults to ADAPT_TEST_ROOT, or the system temp folder.
    """
    base = Path(base or os.environ.get("ADAPT_TEST_ROOT") or tempfile.gettempdir())
    base.mkdir(parents=True, exist_ok=True)
    parent = Path(tempfile.mkdtemp(prefix="adapt-fixture-", dir=base))
    root = parent / HOST_NAME
    skills = root / ".claude" / "skills"
    for skill, files in SKILLS.items():
        for rel, text in files.items():
            path = skills / skill / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8", newline="\n")
    (root / "README.md").write_text("A throwaway host project for Adapt tests.\n", encoding="utf-8")
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.name", "adapt-fixture")
    _git(root, "config", "user.email", "adapt-fixture@example.invalid")
    _git(root, "config", "core.autocrlf", "false")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "fixture host")
    return Host(parent=parent, root=root, skills=skills)


def _force_remove(func, path, _exc):
    # git marks its object files read-only; Windows refuses to delete those without this.
    os.chmod(path, stat.S_IWRITE)
    func(path)


def remove_host(host: Host) -> None:
    """Delete the fixture's parent folder, and with it the host and anything placed beside it."""
    if host.parent.name.startswith("adapt-fixture-") and host.parent.exists():
        shutil.rmtree(host.parent, onerror=_force_remove)


def run_skill_tests(host: Host, skill: str) -> subprocess.CompletedProcess:
    """Run one skill's unittest suite and return the completed process."""
    return subprocess.run(
        ["python", "-m", "unittest", "discover", "-s", "tests", "-q"],
        cwd=host.skill(skill), capture_output=True, text=True,
    )
