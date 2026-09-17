"""Tests for the leave-nothing-behind check. Run: python Adapt/build/tests/test_residue.py"""

import sys
import unittest
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness import fixtures, probe, residue  # noqa: E402


class ResidueTest(unittest.TestCase):
    def test_clean_fixture_passes(self):
        with residue.guard():
            host = fixtures.make_host()
            fixtures.remove_host(host)

    def test_leftover_fixture_is_caught(self):
        host = None
        with self.assertRaises(residue.ResidueError) as caught:
            with residue.guard():
                host = fixtures.make_host()
        fixtures.remove_host(host)
        self.assertIn("adapt-fixture-", str(caught.exception))

    def test_leftover_session_trace_is_caught(self):
        folder = probe.CLAUDE_HOME / "session-env"
        folder.mkdir(parents=True, exist_ok=True)
        leak = folder / ("residue-test-%s" % uuid.uuid4().hex)
        try:
            with self.assertRaises(residue.ResidueError) as caught:
                with residue.guard():
                    leak.write_text("x")
            self.assertIn(leak.name, str(caught.exception))
        finally:
            leak.unlink(missing_ok=True)

    def test_ignore_pattern(self):
        folder = probe.CLAUDE_HOME / "session-env"
        folder.mkdir(parents=True, exist_ok=True)
        leak = folder / ("residue-test-%s" % uuid.uuid4().hex)
        try:
            with residue.guard(ignore=("*residue-test-*",)):
                leak.write_text("x")
        finally:
            leak.unlink(missing_ok=True)

    @unittest.skipIf(probe.live_disabled(), "live probe tests disabled")
    def test_probe_leaves_nothing(self):
        with residue.guard():
            host = fixtures.make_host()
            try:
                probe.run(host.root, "Reply with the single word OK.", "--permission-mode", "dontAsk")
            finally:
                fixtures.remove_host(host)


if __name__ == "__main__":
    unittest.main()
