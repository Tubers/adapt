#!/usr/bin/env python3
"""Tests for block_handoff_write.py.  Run: python .claude/hooks/test_block_handoff_write.py

WHY THESE LIVE IN A FILE RATHER THAN IN A SHELL ONE-LINER
---------------------------------------------------------
The obvious way to test this hook is to pipe a JSON payload at it from Bash. That does not work:
the payloads contain the protected filename next to a mutation token, so the hook fires on the TEST
COMMAND ITSELF and refuses to run it. Measured, not predicted - it happened on the first attempt.
Building the payloads here, out of fragments, keeps the trigger string out of any command line.
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

HOOK = Path(__file__).with_name("block_handoff_write.py")

# Assembled from fragments so this source file never contains the literal trigger next to a
# mutation token either - the hook would refuse an Edit to its own test file otherwise.
NAME = "HAND" + "OFF.md"
DIR = "mechanics/inventory/"
GONE = "HAND" + "OFF-2026-01-01.md"      # a name that is never created below

# The create-vs-modify rule is about a file's EXISTENCE, so the tests need a real one. Every
# payload carries this directory as `cwd`, and the hook resolves relative paths against it.
TMP = Path(tempfile.mkdtemp(prefix="handoff-hook-test-"))
(TMP / DIR).mkdir(parents=True, exist_ok=True)
(TMP / DIR / NAME).write_text("a handoff that exists\n", encoding="utf-8")
(TMP / NAME).write_text("a handoff that exists\n", encoding="utf-8")

# A handoff that has already been retired. These are STILL one-time-use documents and still
# read-only: an archived handoff records what one session believed at one moment, and editing it
# would make it a record of nothing.
ARCHIVED_DIR = DIR + "archive/handoffs/"
ARCHIVED = "HAND" + "OFF-2026-08-17.md"
(TMP / ARCHIVED_DIR).mkdir(parents=True, exist_ok=True)
(TMP / ARCHIVED_DIR / ARCHIVED).write_text("a retired handoff\n", encoding="utf-8")

# Names that CONTAIN the word without being a handoff. The folder is a real measurement folder here.
WORD_DIR = "mechanics/spatial_hash/measurements/value_hand" + "off_to_xs/"
WORD_MD = "notes_on_hand" + "off.md"
(TMP / DIR / WORD_MD).write_text("not a handoff, only about one\n", encoding="utf-8")


def run(payload: dict) -> bool:
    """-> True if the hook DENIED the call."""
    out = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(payload),
                         capture_output=True, text=True)
    if out.returncode != 0:
        raise SystemExit(f"hook exited {out.returncode}: {out.stderr.strip()}")
    if not out.stdout.strip():
        return False
    return json.loads(out.stdout)["hookSpecificOutput"]["permissionDecision"] == "deny"


def tool(name, **kw):
    payload = {"tool_name": name, "tool_input": kw}
    payload["cwd"] = str(TMP)
    return payload


CASES = [
    # (expect_deny, label, payload)
    # --- MODIFY an existing handoff: always refused -------------------------------------------
    (True,  "Edit an existing handoff",        tool("Edit", file_path=NAME)),
    (True,  "Edit it via a subdirectory path", tool("Edit", file_path=DIR + NAME)),
    (True,  "Edit it via an absolute path",    tool("Edit", file_path=str(TMP / DIR / NAME))),
    (True,  "Write over an existing handoff",  tool("Write", file_path=DIR + NAME)),
    # Edit is refused on name alone, without an existence check: the Edit tool only ever targets a
    # file that is already there, so there is no create case to let through. GONE is absent on
    # disk and this is still a DENY - that asymmetry with Write below is deliberate, not a gap.
    (True,  "Edit a dated handoff (name alone)", tool("Edit", file_path=GONE)),

    # --- CREATE: allowed, because that is how the next handoff gets written --------------------
    # This is the case that makes the lifecycle work. /handoff runs at the END of a session, after
    # the session that read the last handoff deleted it, so the name is free at that moment.
    (False, "Create a handoff where none exists", tool("Write", file_path="fresh/" + NAME)),
    (False, "Create a dated handoff",          tool("Write", file_path=GONE)),
    (False, "Shell-create where none exists",  tool("Bash", command="echo x > fresh/" + NAME)),

    # --- AN ARCHIVED HANDOFF IS STILL ONE-TIME-USE, AND STILL READ-ONLY -----------------------
    # Retiring a handoff files it away; it does not turn it into an editable document. These must
    # behave exactly like the live one.
    (True,  "Edit an archived handoff",        tool("Edit", file_path=ARCHIVED_DIR + ARCHIVED)),
    (True,  "Write over an archived handoff",  tool("Write", file_path=ARCHIVED_DIR + ARCHIVED)),
    (True,  "sed -i an archived handoff",      tool("Bash", command="sed -i s/a/b/ " + ARCHIVED_DIR + ARCHIVED)),
    (True,  "redirect into an archived one",   tool("Bash", command="echo x > " + ARCHIVED_DIR + ARCHIVED)),
    (True,  "overwrite an archived one by mv", tool("Bash", command="mv new.md " + ARCHIVED_DIR + ARCHIVED)),
    (False, "read an archived handoff",        tool("Bash", command="cat " + ARCHIVED_DIR + ARCHIVED)),

    # --- unrelated files are never touched ----------------------------------------------------
    (False, "Edit some other file",            tool("Edit", file_path="CLAUDE.md")),

    # The shell arm. These are the routes an in-place edit actually took in practice.
    (True,  "python open(...) write mode",     tool("Bash", command='io.open("' + NAME + '","w").write(s)')),
    (True,  "assign path then write far below", tool("Bash", command='p = "' + DIR + NAME + '"\n' + "\n" * 40 + 'io.open(p,"w",encoding="utf-8").write(s)')),
    (True,  "sed in place",                    tool("Bash", command="sed -i s/a/b/ " + DIR + NAME)),
    (True,  "shell redirect",                  tool("Bash", command="echo x > " + NAME)),
    (True,  "append redirect",                 tool("Bash", command="echo x >> " + NAME)),
    (True,  "overwrite by move",               tool("Bash", command="mv new.md " + NAME)),
    (True,  "overwrite by copy",               tool("Bash", command="cp new.md " + DIR + NAME)),

    # ARCHIVING. A handoff is retired by RELOCATING it, not by deleting it, so the move that takes
    # it to the archive must pass. `mv` was a flat mutation token until 2026-09-05 and refused all
    # of these - the same mistake `rm ` made, and caught the same way: the sanctioned operation was
    # blocked in order to catch an exotic one. Move and copy are now judged by DESTINATION.
    (False, "archive it",                      tool("Bash", command="mv " + DIR + NAME + " " + DIR + "archive/handoffs/HAND" + "OFF-2026-09-05.md")),
    (False, "archive it, quoted paths",        tool("Bash", command='mv "' + DIR + NAME + '" "' + DIR + 'archive/handoffs/HAND' + 'OFF-2026-09-05.md"')),
    (False, "archive it with PowerShell",      tool("PowerShell", command="Move-Item " + DIR + NAME + " " + DIR + "archive/handoffs/")),
    (False, "archive it with a flag",          tool("Bash", command="mv -f " + DIR + NAME + " " + DIR + "archive/handoffs/HAND" + "OFF-x.md")),
    (True,  "PowerShell Set-Content",          tool("PowerShell", command="Set-Content " + NAME + " -Value x")),

    # Reading is never blocked, by any route.
    (False, "cat it",                          tool("Bash", command="cat " + DIR + NAME)),
    (False, "grep it",                         tool("Bash", command="grep -n section " + DIR + NAME)),
    (False, "head it",                         tool("Bash", command="head -40 " + DIR + NAME)),

    # An unparseable mutation FAILS CLOSED: something is writing a handoff and we cannot tell which.
    (True,  "mutation with no parseable path", tool("Bash", command="cat x > $HANDOFF_FILE")),

    # REGRESSION: a bare `>` used to count as a mutation token, so ANY command carrying `2>&1`
    # while mentioning a handoff was refused - including the run of this very test file. A redirect
    # only counts when it points AT something handoff-shaped.
    (False, "2>&1 while naming a handoff",     tool("Bash", command="python t.py 2>&1 | tail -3 && grep -n x " + DIR + NAME)),
    (False, "2>/dev/null while naming one",    tool("Bash", command="grep -c x " + DIR + NAME + " 2>/dev/null")),
    (False, "a pipeline that reads one",       tool("Bash", command="cat " + DIR + NAME + " | wc -l")),

    # BURN AFTER READING. Deleting a handoff is the intended end of its life, so every one of these
    # must pass. An earlier version of the token list carried `rm ` and `del ` and refused them all,
    # which would have made the lifecycle unenforceable by the very hook meant to protect it.
    (False, "rm it",                           tool("Bash", command="rm " + DIR + NAME)),
    (False, "rm -f it",                        tool("Bash", command="rm -f " + DIR + NAME)),
    (False, "del it",                          tool("Bash", command="del " + NAME)),
    (False, "Remove-Item it",                  tool("PowerShell", command="Remove-Item " + DIR + NAME)),
    (False, "os.remove it",                    tool("Bash", command='python -c "import os; os.remove(' + repr(NAME) + ')"')),
    (False, "Path.unlink it",                  tool("Bash", command='python -c "from pathlib import Path; Path(' + repr(NAME) + ').unlink()"')),

    # SCOPE: ONLY ACTUAL HANDOFF FILES. A word inside a folder or file name is not a handoff. This
    # refused a real rules/INDEX.md edit on 2026-09-12, because the same command named the gate for
    # the `value_handoff_to_xs/` measurement folder.
    (False, "write while naming a folder with the word", tool("Bash", command='Path("rules/INDEX.md").write_text(s)  # ' + WORD_DIR + "**")),
    (False, "redirect into a folder with the word",      tool("Bash", command="echo x > " + WORD_DIR + "notes.txt")),
    (False, "sed -i an existing .md that only contains it", tool("Bash", command="sed -i s/a/b/ " + DIR + WORD_MD)),
    (False, "Write an existing .md that only contains it",  tool("Write", file_path=DIR + WORD_MD)),
    (True,  "redirect into a braced variable",           tool("Bash", command="cat x > ${HAND" + "OFF}")),
    (True,  "PowerShell env variable target",            tool("PowerShell", command="Set-Content $env:HAND" + "OFF_PATH -Value x")),
    (True,  "redirect into a handoff inside a folder with the word", tool("Bash", command="echo x > " + DIR + NAME + " # " + WORD_DIR)),

    # Unrelated work is never touched.
    (False, "an ordinary build",               tool("Bash", command="python inventory_ducwr_dev.py")),
    (False, "an unrelated delete",             tool("Bash", command="rm scratch/tmp.txt")),
]


def main() -> int:
    failures = []
    for expect_deny, label, payload in CASES:
        got_deny = run(payload)
        ok = got_deny == expect_deny
        want = "DENY" if expect_deny else "ALLOW"
        print(f"[{'PASS' if ok else 'FAIL'}] {want:<5} {label}")
        if not ok:
            failures.append(label)
    print(f"\n{len(CASES) - len(failures)}/{len(CASES)} checks passed")
    if failures:
        print("FAILED: " + ", ".join(failures))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
