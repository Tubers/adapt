"""Run every skill's self-test and summarise.

    python Adapt/selftest/run_all.py [--quick]

Each self-test lives in Adapt/selftest/<skill>/test_<skill>.py and proves the installed skill works in
this project: files in place, hooks registered and answering as their safeguards promise, a real workflow
in a throwaway clone, and the skill's own suites (skipped with --quick). Exit code 1 if any fails.
"""

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main():
    results = []
    for test in sorted(HERE.glob("*/test_*.py")):
        p = subprocess.run([sys.executable, str(test)] + sys.argv[1:], capture_output=True, text=True,
                           encoding="utf-8")
        print(p.stdout)
        if p.stderr.strip():
            print(p.stderr[-2000:])
        last = [l for l in p.stdout.splitlines() if " passed, " in l][-1:] or ["no summary line"]
        results.append((test.parent.name, p.returncode, last[0]))
    print("=" * 78)
    for skill, rc, line in results:
        print("%-14s %s   %s" % (skill, "OK  " if rc == 0 else "FAIL", line))
    return 1 if any(rc for _, rc, _ in results) else 0


if __name__ == "__main__":
    sys.exit(main())
