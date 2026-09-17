#!/usr/bin/env python3
"""PreToolUse hook: graphify's graph nudge, only for code searches, in milder words.

WHY
---
graphify's own hook (`graphify hook-guard search|read`) fires on every Bash, Grep, Read and Glob
call once a graph exists, and says "MANDATORY: ... You MUST run graphify query". In use it fired on
an exact symbol lookup and on a shell listing piped to grep. The advice is good for questions about
how code connects; it is noise for everything else.

WHAT IT DOES
------------
1. Decides whether the call is a code search:
   - Grep: the search is restricted to code (glob, type or path) or not restricted at all, and is
     not aimed at one named file.
   - Glob: the pattern names a code extension.
   - Read: the file has a code extension.
   - Bash: the first command is a search tool (grep, rg, ag, ack, find) and it is not piped from
     another command.
2. Only then asks graphify's own guard, which keeps its own checks (a graph exists, the file is in
   the project and indexed).
3. Replaces graphify's wording with a milder note, keeping graphify's decision.

The guard command is graphify in tools/graphify-venv, or GRAPHIFY_GUARD_CMD (a JSON list) for
tests. Fails open: any problem, and the hook prints nothing and exits 0.
"""

import json
import os
import re
import subprocess
import sys

CODE_EXT = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".go", ".rs", ".java", ".kt", ".c",
    ".h", ".cc", ".cpp", ".hpp", ".cs", ".rb", ".php", ".swift", ".scala", ".lua", ".zig",
    ".sh", ".ps1", ".sql", ".dart", ".ml", ".hs", ".ex", ".exs", ".clj", ".r", ".jl",
}
CODE_TYPES = {
    "py", "python", "js", "ts", "go", "rust", "java", "kotlin", "c", "cpp", "cs", "ruby",
    "php", "swift", "scala", "lua", "zig", "sh", "sql", "dart",
}
SEARCH_TOOLS = {"grep", "rg", "ag", "ack", "find"}

NUDGE = (
    "A code graph exists at graphify-out/graph.json. For a question about how code connects, "
    '`graphify query "<question>"`, `graphify path "A" "B"` or `graphify affected "X"` is usually '
    "cheaper than reading files. For an exact lookup, search directly."
)


def has_code_ext(text: str) -> bool:
    text = text.lower()
    return any(text.endswith(ext) or ("*" + ext) in text or (ext + "}") in text
               or re.search(re.escape(ext) + r"[,}]", text) for ext in CODE_EXT)


def is_code_search(tool: str, ti: dict) -> bool:
    if tool == "Grep":
        path = str(ti.get("path") or "")
        if path and os.path.splitext(path)[1]:
            return False                                   # aimed at one named file
        glob = str(ti.get("glob") or "")
        ftype = str(ti.get("type") or "").lower()
        if glob:
            return has_code_ext(glob)
        if ftype:
            return ftype in CODE_TYPES
        return True                                        # unrestricted search
    if tool == "Glob":
        return has_code_ext(str(ti.get("pattern") or ""))
    if tool == "Read":
        return os.path.splitext(str(ti.get("file_path") or ""))[1].lower() in CODE_EXT
    if tool == "Bash":
        cmd = str(ti.get("command") or "").strip()
        first_segment = re.split(r"\|\||&&|;|\|", cmd, maxsplit=1)[0].strip()
        words = first_segment.split()
        while words and "=" in words[0] and not words[0].startswith("-"):
            words = words[1:]                              # leading VAR=value assignments
        if not words:
            return False
        head = os.path.basename(words[0]).lower()
        if head.endswith(".exe"):
            head = head[:-4]
        return head in SEARCH_TOOLS
    return False


def guard_cmd(kind: str) -> list:
    override = os.environ.get("GRAPHIFY_GUARD_CMD")
    if override:
        return json.loads(override) + ["hook-guard", kind]
    project = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    exe = os.path.join(project, "tools", "graphify-venv", "Scripts", "graphify.exe")
    if not os.path.isfile(exe):
        exe = os.path.join(project, "tools", "graphify-venv", "bin", "graphify")
    return [exe, "hook-guard", kind]


def main() -> int:
    raw = sys.stdin.buffer.read()
    data = json.loads(raw.decode("utf-8", "replace"))
    tool = data.get("tool_name", "")
    ti = data.get("tool_input") or {}
    if not isinstance(ti, dict) or not is_code_search(tool, ti):
        return 0
    kind = "read" if tool in ("Read", "Glob") else "search"
    proc = subprocess.run(guard_cmd(kind), input=raw, capture_output=True, timeout=8)
    out = proc.stdout.decode("utf-8", "replace").strip()
    if not out:
        return 0
    payload = json.loads(out)
    hso = payload.get("hookSpecificOutput")
    if isinstance(hso, dict) and hso.get("additionalContext"):
        hso["additionalContext"] = NUDGE
        payload.pop("systemMessage", None)
    sys.stdout.write(json.dumps(payload))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)
