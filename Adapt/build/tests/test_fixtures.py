"""Tests for the fixture host maker. Run: python Adapt/build/tests/test_fixtures.py"""

import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness import fixtures  # noqa: E402


class FixtureHostTest(unittest.TestCase):
    def setUp(self):
        self.host = fixtures.make_host()

    def tearDown(self):
        fixtures.remove_host(self.host)

    def test_layout(self):
        self.assertTrue((self.host.root / ".git").is_dir())
        for skill in fixtures.SKILLS:
            self.assertTrue((self.host.skill(skill) / "SKILL.md").is_file())
        self.assertEqual(self.host.root.parent, self.host.parent)

    def test_clean_committed_tree(self):
        status = subprocess.run(["git", "status", "--porcelain"], cwd=self.host.root,
                                capture_output=True, text=True, check=True).stdout
        self.assertEqual(status, "")

    def test_sound_skill_passes(self):
        self.assertEqual(fixtures.run_skill_tests(self.host, "greet").returncode, 0)

    def test_planted_bug_is_exposed(self):
        result = fixtures.run_skill_tests(self.host, fixtures.BUGGY_SKILL)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(fixtures.BUGGY_TEST, result.stderr)
        self.assertIn("failures=1", result.stderr)


class RemovalTest(unittest.TestCase):
    def test_remove_leaves_nothing(self):
        host = fixtures.make_host()
        (host.parent / "host.adapt").mkdir()          # something placed beside the host
        fixtures.remove_host(host)
        self.assertFalse(host.parent.exists())

    def test_remove_refuses_foreign_folders(self):
        host = fixtures.make_host()
        try:
            foreign = fixtures.Host(parent=host.root, root=host.root, skills=host.skills)
            fixtures.remove_host(foreign)             # parent name lacks the fixture prefix
            self.assertTrue(host.root.exists())
        finally:
            fixtures.remove_host(host)


if __name__ == "__main__":
    unittest.main()
