#!/usr/bin/env python3
"""Tests for graphify_nudge.py and tools_path.py. Run: python .claude/hooks/test_graphify_nudge.py

graphify itself is replaced by a stub (GRAPHIFY_GUARD_CMD) that always answers with a nudge, so
these tests check only the wrapper's own decisions: when to ask graphify, and what wording leaves.
"""

import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
NUDGE_HOOK = os.path.join(HERE, "graphify_nudge.py")
PATH_HOOK = os.path.join(HERE, "tools_path.py")

STUB = (
    "import sys, json\n"
    "sys.stdin.read()\n"
    "print(json.dumps({'hookSpecificOutput': {'hookEventName': 'PreToolUse',"
    " 'additionalContext': 'MANDATORY: You MUST run graphify query'}}))\n"
)

results = []


def check(name, ok):
    results.append(ok)
    print(("  PASS  " if ok else "  FAIL  ") + name)


def run_nudge(tool, tool_input, stub):
    env = dict(os.environ, GRAPHIFY_GUARD_CMD=json.dumps([sys.executable, stub]))
    payload = json.dumps({"tool_name": tool, "tool_input": tool_input})
    p = subprocess.run([sys.executable, NUDGE_HOOK], input=payload.encode(), capture_output=True,
                       env=env, timeout=30)
    return p.returncode, p.stdout.decode().strip()


def nudged(out):
    return bool(out) and "graphify query" in out


def main():
    tmp = tempfile.mkdtemp()
    stub = os.path.join(tmp, "stub.py")
    with open(stub, "w") as fh:
        fh.write(STUB)

    cases = [
        ("an unrestricted Grep is a code search", "Grep", {"pattern": "load_gates"}, True),
        ("a Grep limited to *.py is a code search", "Grep", {"pattern": "x", "glob": "*.py"}, True),
        ("a Grep of type py is a code search", "Grep", {"pattern": "x", "type": "py"}, True),
        ("a Grep limited to *.md is not", "Grep", {"pattern": "x", "glob": "*.md"}, False),
        ("a Grep aimed at one named file is not", "Grep",
         {"pattern": "def rel_posix", "path": "scripts/rules_lib.py"}, False),
        ("a Grep over a folder with no filter is a code search", "Grep",
         {"pattern": "x", "path": "scripts"}, True),
        ("a Glob for **/*.py is a code search", "Glob", {"pattern": "**/*.py"}, True),
        ("a Glob for **/*.md is not", "Glob", {"pattern": "**/*.md"}, False),
        ("reading a .py file is a code search", "Read", {"file_path": "a/b.py"}, True),
        ("reading a .md file is not", "Read", {"file_path": "a/b.md"}, False),
        ("a Bash grep is a code search", "Bash", {"command": "grep -rn foo ."}, True),
        ("a Bash rg with an env prefix is a code search", "Bash", {"command": "FOO=1 rg foo"}, True),
        ("a Bash find is a code search", "Bash", {"command": "find . -name '*.py'"}, True),
        ("ls piped to grep is not", "Bash", {"command": "ls /tmp | grep x"}, False),
        ("git status is not", "Bash", {"command": "git status"}, False),
        ("a python script is not", "Bash", {"command": "python run.py"}, False),
        ("an unrelated tool is not", "Write", {"file_path": "a.py", "content": ""}, False),
    ]
    for name, tool, ti, want in cases:
        code, out = run_nudge(tool, ti, stub)
        check(name, code == 0 and nudged(out) == want)

    code, out = run_nudge("Grep", {"pattern": "x"}, stub)
    check("the nudge is reworded: no MANDATORY", "MANDATORY" not in out and "MUST" not in out)
    check("the output is valid hook JSON",
          json.loads(out)["hookSpecificOutput"]["hookEventName"] == "PreToolUse")

    env = dict(os.environ, GRAPHIFY_GUARD_CMD=json.dumps([sys.executable, "no-such-file.py"]))
    p = subprocess.run([sys.executable, NUDGE_HOOK], input=b'{"tool_name":"Grep","tool_input":{}}',
                       capture_output=True, env=env, timeout=30)
    check("a broken graphify fails open", p.returncode == 0 and not p.stdout.strip())
    p = subprocess.run([sys.executable, NUDGE_HOOK], input=b"not json", capture_output=True,
                       timeout=30)
    check("bad input fails open", p.returncode == 0 and not p.stdout.strip())

    project = os.path.join(tmp, "proj")
    os.makedirs(os.path.join(project, "tools", "bin"))
    env_file = os.path.join(tmp, "env.sh")
    open(env_file, "w").close()
    env = dict(os.environ, CLAUDE_ENV_FILE=env_file, CLAUDE_PROJECT_DIR=project)
    p = subprocess.run([sys.executable, PATH_HOOK], env=env, capture_output=True, timeout=30)
    line = open(env_file).read()
    check("tools_path writes one PATH export ending in :$PATH",
          p.returncode == 0 and line.startswith('export PATH="') and line.rstrip().endswith(':$PATH"')
          and "/tools/bin:" in line)
    check("tools_path writes a Git Bash path, not a Windows one", "\\" not in line)
    env = dict(os.environ, CLAUDE_PROJECT_DIR=project)
    env.pop("CLAUDE_ENV_FILE", None)
    p = subprocess.run([sys.executable, PATH_HOOK], env=env, capture_output=True, timeout=30)
    check("tools_path without CLAUDE_ENV_FILE does nothing", p.returncode == 0 and not p.stdout)

    print("\n%d passed, %d failed" % (results.count(True), results.count(False)))
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
