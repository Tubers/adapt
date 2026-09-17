"""Tests for the probe runner. Run: python Adapt/build/tests/test_probe.py

Live: each test makes a small claude -p request. ADAPT_SKIP_LIVE=1 skips them.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness import fixtures, probe  # noqa: E402


@unittest.skipIf(probe.live_disabled(), "live probe tests disabled")
class ProbeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.host = fixtures.make_host()
        cls.result = probe.run(cls.host.root, "Reply with the single word OK.",
                               "--permission-mode", "dontAsk")

    @classmethod
    def tearDownClass(cls):
        fixtures.remove_host(cls.host)

    def test_run_succeeds(self):
        self.assertFalse(self.result.is_error, self.result.stderr[-500:])
        self.assertIn("OK", self.result.final_text)

    def test_init_event_parsed(self):
        self.assertIn("haiku", str(self.result.init.get("model")))
        self.assertEqual(self.result.init.get("permissionMode"), "dontAsk")
        self.assertIsInstance(self.result.skills, list)
        self.assertIsInstance(self.result.agents, list)

    def test_host_skills_visible_from_host(self):
        # Started inside the host, the session sees the host's own project skills.
        self.assertIn("greet", self.result.skills)
        self.assertIn("calc", self.result.skills)

    def test_session_traces_removed(self):
        self.assertTrue(self.result.session_ids)
        for sid in self.result.session_ids:
            left = list(probe.CLAUDE_HOME.glob("*/%s*" % sid))
            left += list(probe.CLAUDE_HOME.glob("*/*/%s*" % sid))
            self.assertEqual(left, [], "traces left for %s" % sid)

    def test_no_project_entry_left(self):
        keys = probe._project_keys()
        host = str(self.host.root).replace("\\", "/").lower()
        self.assertFalse([k for k in keys if k.replace("\\", "/").lower() == host])


if __name__ == "__main__":
    unittest.main()
