"""Live check for tests/t1: does a rule created, then edited, during a session reach that session's prompt?

    python tests/probe/live_check.py

Starts a real headless Claude Code session in this project (so this project's hooks run), which reads
tests/probe/target.txt, then waits. While it waits, this script edits rules/tests/probe.rule.md to a new
version and lets it go on; it reads the file again and reports, word for word, which probe rule text arrived
with each read. The rule's text says PROBE-V<n>, so the version that arrived is unambiguous.
"""

import pathlib
import re
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[2]
PROBE = ROOT / "tests" / "probe"
RULE = ROOT / "rules" / "tests" / "probe.rule.md"
READY, GO = PROBE / "ready.flag", PROBE / "go.flag"

PROMPT = (
    "This is a test of this project's rule hooks. Do exactly these steps and nothing else.\n"
    "1. Read the file tests/probe/target.txt with the Read tool.\n"
    "2. Run this exact shell command: python -c \"import time,pathlib; "
    "pathlib.Path('tests/probe/ready.flag').write_text('x'); "
    "[time.sleep(1) for _ in range(60) if not pathlib.Path('tests/probe/go.flag').exists()]\"\n"
    "3. Read the file tests/probe/target.txt again with the Read tool.\n"
    "Then report in this exact form, quoting the text that arrived as project-rules context with each Read:\n"
    "READ1: <the full line starting 'RULE tests/probe', plus the '--- rules/tests/probe' header line if one came, or NONE>\n"
    "READ2: <the same for the second Read, or NONE>\n"
)


INDEX = ROOT / "rules" / "INDEX.md"
GATE = "- **tests/probe.rule.md** | `tests/probe/**` | throwaway probe for the tests project's live-injection check\n"
RULE_V1 = ("RULE tests/probe - PROBE-V1: a throwaway rule for the tests project's live-injection check.\n"
           "- If this text reaches the prompt, a rule created during the session is injected with no reload.\n")


def install_probe():
    """Create the probe rule and its gate for this run; remove_probe() takes both away again."""
    RULE.parent.mkdir(parents=True, exist_ok=True)
    RULE.write_text(RULE_V1, encoding="utf-8")
    text = INDEX.read_text(encoding="utf-8")
    if GATE not in text:
        INDEX.write_text(text.replace("\n## README triggers", GATE + "\n## README triggers", 1), encoding="utf-8")


def remove_probe():
    RULE.unlink(missing_ok=True)
    try:
        RULE.parent.rmdir()
    except OSError:
        pass
    INDEX.write_text(INDEX.read_text(encoding="utf-8").replace(GATE, ""), encoding="utf-8")


def main():
    for f in (READY, GO):
        f.unlink(missing_ok=True)
    install_probe()
    try:
        return run()
    finally:
        remove_probe()


def run():
    before = RULE.read_text(encoding="utf-8")
    m = re.search(r"PROBE-V(\d+)", before)
    old, new = m.group(0), "PROBE-V%d" % (int(m.group(1)) + 1)
    import shutil
    exe = (shutil.which("claude") or shutil.which("claude.exe")
           or str(pathlib.Path.home() / ".local" / "bin" / ("claude.exe" if sys.platform == "win32" else "claude")))
    # --allowedTools lets the one sync command run without trusting the workspace or asking anyone
    proc = subprocess.Popen([exe, "-p", PROMPT, "--output-format", "text", "--max-turns", "10",
                             "--allowedTools", "Bash(python -c:*)", "Read"],
                            cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                            encoding="utf-8")
    t0 = time.time()
    while not READY.exists() and proc.poll() is None and time.time() - t0 < 240:
        time.sleep(0.5)
    edited = READY.exists()
    if edited:
        RULE.write_text(before.replace(old, new), encoding="utf-8")
        print("edited the rule %s -> %s while the session waited, %.1fs in" % (old, new, time.time() - t0))
        GO.write_text("go", encoding="utf-8")
    else:
        print("the session never reached its wait step")
    out, _ = proc.communicate(timeout=300)
    for f in (READY, GO):
        f.unlink(missing_ok=True)
    print("--- headless session report ---")
    print(out.strip())
    print("--- expected ---")
    print("READ1 carries %s; READ2 carries %s marked CHANGED" % (old, new))
    return 0 if edited else 1


if __name__ == "__main__":
    sys.exit(main())
