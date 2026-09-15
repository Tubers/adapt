#!/usr/bin/env python3
"""Shared machinery for the path-gated rule system.

WHAT THE RULE SYSTEM IS
-----------------------
This repo used to load a 28 KB `CLAUDE.md` into every session and rely on 92 free-text `README.md`
files being skimmed. Both cost context unconditionally and neither was compulsory. As of 2026-09-09:

    rules/<area>/[<group>/]<slug>.rule.md   one curated rule, at most 10 lines and 2048 bytes
    rules/INDEX.md                which rule fires on which path, and the README -> rule map
    <folder>/README.md            ONE line naming the rule file that folder triggers

A rule reaches a session only when a gate matches the path (or the shell command) a tool is about
to touch, and only once per session. That makes the information compulsory where it is relevant and
free everywhere else - the opposite trade to a README, which was optional everywhere and paid for
nowhere.

RULE FILES ARE NESTED, AND A RULE'S NAME IS ITS PATH UNDER `rules/`
------------------------------------------------------------------
`xs/authoring.rule.md`, not `xs-authoring.rule.md`. Everything here - gates, README stubs, the
firing log, the CLI - uses that relative posix path as the rule's identity, so a rule can be moved
between areas by renaming it in `rules/INDEX.md` and in whichever READMEs point at it. Discovery is
recursive, so adding an area folder needs no code change.

THE ONE GATE THAT MAY NEVER EXIST
---------------------------------
Nothing here ever matches a path under the skills directory (see SKILLS_PREFIX below). Three
sub-agents edit, extend and repair those skills, and their contexts are deliberate silos: a rule
about repo conventions arriving mid-way through a skill repair is noise at best and a
scope-widening instruction at worst. The exclusion is enforced here, in code, rather than left to
whoever edits `rules/INDEX.md`.

Tests: python .claude/skills/rules-system/scripts/run_tests.py
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

# Rule files that live under this prefix are never gated on, and paths under it never match a gate.
# Kept as a constant so the test suite can assert against the same string the router uses.
SKILLS_PREFIX = ".claude/skills/"

RULES_DIRNAME = "rules"
INDEX_NAME = "INDEX.md"
RULE_SUFFIX = ".rule.md"

MAX_RULE_LINES = 10
MAX_RULE_BYTES = 2048

# Where the router records what it injected. Repo-local on purpose: the point of the log is that a
# person can look at it, and a file in the system temp folder is neither findable nor durable.
FIRING_LOG = ".claude/rules-firings.jsonl"
FIRING_LOG_MAX_LINES = 4000      # trimmed to the newest half when it grows past this

# The generated half of rules/INDEX.md sits between these two markers. Everything outside them is
# hand-maintained and is never touched by the sync.
GEN_BEGIN = "<!-- BEGIN GENERATED readme-triggers -->"
GEN_END = "<!-- END GENERATED readme-triggers -->"

# A gate line in rules/INDEX.md:
#     - **xs/authoring.rule.md** | `**/*.xs`, `**/*.xsdat` | what it says in one line
# The rule name may carry `/` because rules live in area folders.
_GATE_RE = re.compile(r"^-\s+\*\*(?P<rule>[A-Za-z0-9_./-]+\.rule\.md)\*\*\s*\|(?P<rest>.*)$")
_TICKED_RE = re.compile(r"`([^`]+)`")

# Path-ish tokens inside a shell command. Deliberately narrow: an extension this repo actually uses,
# or a bare directory name followed by a slash. Anything wider turns every `grep -r foo .` into a
# rule storm.
_CMD_PATH_RE = re.compile(
    r"[A-Za-z0-9_./\\~+-]*\.(?:md|py|xs|xsdat|per|ai|toml|json|dat|aoe2scenario|txt|h|cpp)\b"
)


def repo_root(payload: dict | None = None) -> Path:
    """The project directory. `CLAUDE_PROJECT_DIR` wins; the hook payload's cwd is the fallback."""
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    if env:
        return Path(env)
    if payload:
        cwd = payload.get("cwd")
        if cwd:
            return Path(cwd)
    return Path.cwd()


def rel_posix(root: Path, path: str) -> str | None:
    """`path` as a repo-relative posix string, or None if it is outside the repo."""
    if not path:
        return None
    p = Path(path)
    try:
        if not p.is_absolute():
            p = (root / p)
        return p.resolve().relative_to(root.resolve()).as_posix()
    except (ValueError, OSError):
        return None


def is_skill_path(rel: str) -> bool:
    """True for anything a sub-agent might be working on inside a skill. Never gated."""
    return rel.startswith(SKILLS_PREFIX)


def glob_to_regex(pattern: str) -> re.Pattern:
    """Translate a `**`-aware glob into a regex anchored at both ends.

    `fnmatch` is not usable here: its `*` crosses `/`, so `docs/*/README.md` would match
    `docs/a/b/README.md` and every shallow gate would leak into deep folders.
    """
    out = []
    i = 0
    n = len(pattern)
    while i < n:
        c = pattern[i]
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif c == "*":
            out.append("[^/]*")
            i += 1
        elif c == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(c))
            i += 1
    return re.compile("^" + "".join(out) + "$")


class Gate:
    """One trigger: either a path glob or, when `is_cmd`, a regex over shell command text."""

    __slots__ = ("rule", "raw", "is_cmd", "matcher")

    def __init__(self, rule: str, raw: str):
        self.rule = rule
        self.raw = raw
        self.is_cmd = raw.startswith("cmd:")
        if self.is_cmd:
            self.matcher = re.compile(raw[4:], re.IGNORECASE)
        else:
            self.matcher = glob_to_regex(raw)

    def matches_path(self, rel: str) -> bool:
        return (not self.is_cmd) and bool(self.matcher.match(rel))

    def matches_command(self, command: str) -> bool:
        return self.is_cmd and bool(self.matcher.search(command))


class Match:
    """A rule that fired, and WHY it fired.

    The provenance is the whole point. A rule arriving with no explanation of which gate pulled it
    in is impossible to tune: you cannot tell an over-broad glob from a rule that genuinely applies
    everywhere. `subject` is the path or the command text that matched.
    """

    __slots__ = ("rule", "gate", "subject", "kind")

    def __init__(self, rule: str, gate: str, subject: str, kind: str):
        self.rule = rule
        self.gate = gate
        self.subject = subject
        self.kind = kind          # "path", "command" or "readme"

    def as_dict(self) -> dict:
        return {"rule": self.rule, "gate": self.gate,
                "subject": self.subject, "kind": self.kind}


def raw_gates(root: Path) -> list[tuple[str, str]]:
    """(rule, trigger) pairs exactly as written in rules/INDEX.md, nothing filtered.

    THE ONLY PLACE THE INDEX IS PARSED. `reconcile.py` used to keep its own copy of this regex so it
    could see the gates `load_gates` drops; the two then drifted, and when rule names gained a `/`
    the reconciler silently parsed ZERO gates and reported all 39 rules as orphans. One parser, two
    callers, and the filtering happens afterwards.
    """
    index = root / RULES_DIRNAME / INDEX_NAME
    if not index.is_file():
        return []
    out: list[tuple[str, str]] = []
    for line in index.read_text(encoding="utf-8", errors="replace").splitlines():
        m = _GATE_RE.match(line.strip())
        if not m:
            continue
        # Only the first ` | `-delimited field carries triggers; the rest is the human blurb. The
        # separator is a pipe WITH spaces: a bare `|` split cut every `cmd:` regex holding an
        # alternation, so `cmd:pyautogui|keybind|hotkey|VK_` parsed to nothing and that gate never
        # fired, silently, from the day it was written. Found 2026-09-13.
        triggers = m.group("rest").split(" | ", 1)[0]
        for raw in _TICKED_RE.findall(triggers):
            raw = raw.strip()
            if raw:
                out.append((m.group("rule"), raw))
    return out


def is_skill_gate(trigger: str) -> bool:
    return (not trigger.startswith("cmd:")) and SKILLS_PREFIX.rstrip("/") in trigger


def load_gates(root: Path) -> list[Gate]:
    """Every USABLE gate: skill-targeted and unparseable ones are dropped, not honoured."""
    gates: list[Gate] = []
    for rule, raw in raw_gates(root):
        if is_skill_gate(raw):
            # Refused rather than honoured. A gate on a skill path is the one thing this system
            # must never do, and silently dropping it beats trusting the index.
            continue
        try:
            gates.append(Gate(rule, raw))
        except re.error:
            continue
    return gates


def match_paths(root: Path, rels: list[str]) -> list[Match]:
    """Every rule triggered by these repo-relative paths, with the gate that pulled each in."""
    gates = load_gates(root)
    seen = set()
    out: list[Match] = []
    for rel in rels:
        if is_skill_path(rel):
            continue
        for g in gates:
            if g.rule in seen or not g.matches_path(rel):
                continue
            seen.add(g.rule)
            out.append(Match(g.rule, g.raw, rel, "path"))
        # A README names its own rule directly. That line is the single source of truth for the
        # folder, so it wins even if the index has drifted.
        if rel.endswith("README.md"):
            for named in readme_rules(root / rel):
                if named in seen:
                    continue
                seen.add(named)
                out.append(Match(named, "(named by the README itself)", rel, "readme"))
    return out


def match_command(root: Path, command: str) -> list[Match]:
    if not command:
        return []
    seen = set()
    out = []
    for g in load_gates(root):
        if g.rule in seen or not g.matches_command(command):
            continue
        seen.add(g.rule)
        out.append(Match(g.rule, g.raw, command[:120], "command"))
    return out


def rules_for_paths(root: Path, rels: list[str]) -> list[str]:
    """Rule names only. Kept because most callers do not need the provenance."""
    return [m.rule for m in match_paths(root, rels)]


def rules_for_command(root: Path, command: str) -> list[str]:
    return [m.rule for m in match_command(root, command)]


ORIENTATION_MAX_LINES = 10


def _normalise_rule_line(line: str) -> str | None:
    """`rules/xs/authoring.rule.md`, `xs/authoring.rule.md` or `authoring.rule.md` -> the name
    `all_rules()` would return. None when the line is not a rule path at all."""
    line = line.strip().strip("`").strip().lstrip("- ").strip()
    if not line.endswith(RULE_SUFFIX):
        return None
    line = line.replace("\\", "/").lstrip("./")
    if line.startswith(RULES_DIRNAME + "/"):
        line = line[len(RULES_DIRNAME) + 1:]
    return line


def readme_parse(readme: Path) -> tuple[list[str], list[str]]:
    """(rule names, orientation lines) for a README.

    Shape, since 2026-09-11: one or more rule paths on the leading lines, then a blank line, then
    orientation prose written for whoever opens the folder. Several rules are allowed because the
    common logic of a folder CLASS belongs in one shared rule, scoped to each folder that shares
    it, while what is peculiar to this folder goes in its own. The orientation is ignored by the
    machinery and is capped so a folder note cannot grow back into the free-text README this
    system replaced.
    """
    try:
        text = readme.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return [], []
    rules, body, in_head = [], [], True
    for line in text.splitlines():
        if in_head:
            if not line.strip():
                if rules:                       # blank line ends the rule block
                    in_head = False
                continue
            name = _normalise_rule_line(line)
            if name:
                rules.append(name)
                continue
            in_head = False                     # prose before any blank line: still orientation
        body.append(line)
    while body and not body[0].strip():
        body.pop(0)
    while body and not body[-1].strip():
        body.pop()
    return rules, body


def readme_rule(readme: Path) -> str | None:
    """The FIRST rule a README names, kept for callers that want one. None when it names none."""
    rules, _ = readme_parse(readme)
    return rules[0] if rules else None


def readme_rules(readme: Path) -> list[str]:
    return readme_parse(readme)[0]


def all_rules(root: Path) -> list[str]:
    """Every rule file, as a path relative to `rules/`, sorted. Recursive over area folders."""
    d = root / RULES_DIRNAME
    if not d.is_dir():
        return []
    return sorted(p.relative_to(d).as_posix() for p in d.rglob("*" + RULE_SUFFIX))


def rule_path(root: Path, name: str) -> Path:
    return root / RULES_DIRNAME / name


def read_rule(root: Path, name: str) -> str | None:
    p = rule_path(root, name)
    if not p.is_file():
        return None
    return p.read_text(encoding="utf-8", errors="replace").rstrip()


def rule_size(root: Path, name: str) -> tuple[int, int]:
    """(lines, bytes) for one rule file."""
    p = rule_path(root, name)
    if not p.is_file():
        return (0, 0)
    t = p.read_text(encoding="utf-8", errors="replace")
    lines = len(t.rstrip("\n").split("\n")) if t.strip() else 0
    return (lines, len(t.encode("utf-8")))


def oversized_rules(root: Path) -> list[tuple[str, int, int]]:
    """(name, lines, bytes) for every rule file over the 10-line / 2048-byte cap."""
    out = []
    for name in all_rules(root):
        lines, size = rule_size(root, name)
        if lines > MAX_RULE_LINES or size > MAX_RULE_BYTES:
            out.append((name, lines, size))
    return out


def paths_from_tool(payload: dict) -> tuple[list[str], str]:
    """(repo-relative paths this tool touches, shell command text or "")."""
    root = repo_root(payload)
    ti = payload.get("tool_input") or {}
    tool = payload.get("tool_name", "")
    raw: list[str] = []
    command = ""

    for key in ("file_path", "notebook_path", "path"):
        v = ti.get(key)
        if isinstance(v, str) and v:
            raw.append(v)

    if tool in ("Bash", "PowerShell"):
        command = str(ti.get("command", "") or "")
        raw.extend(_CMD_PATH_RE.findall(command))

    rels = []
    for r in raw:
        rel = rel_posix(root, r.strip("'\""))
        if rel and rel not in rels:
            rels.append(rel)
    return rels, command


# --------------------------------------------------------------------------------------------
# session memory: a rule is injected once per session, not once per tool call
# --------------------------------------------------------------------------------------------

def _state_path(session_id: str) -> Path:
    base = Path(os.environ.get("CLAUDE_RULE_STATE_DIR")
                or os.environ.get("TEMP")
                or os.environ.get("TMP")
                or ".")
    d = base / "claude_rule_router"
    d.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", session_id or "nosession")
    return d / f"{safe}.json"


PROJECT_MARKERS = ("HISTORY.jsonl", "TASKS.md", "QUESTIONS.jsonl")
NOT_PROJECTS = {".claude", "rules", "test_runs"}
ROOT_PROJECT = "."          # the repo root, when it holds a project's files itself


def project_of(root: Path, rel: str):
    """The project a path belongs to: the nearest folder at or above it holding a HISTORY.jsonl, TASKS.md
    or QUESTIONS.jsonl, below the repo root. None for a path in no project."""
    rel = (rel or "").replace("\\", "/").strip().strip("/")
    root = Path(root)
    # the repo root is the last stop up the path when it keeps a project's files itself (the user, 2026-09-14)
    at_root = ROOT_PROJECT if any((root / m).is_file() for m in PROJECT_MARKERS) else None
    if not rel or rel == ".":
        return at_root
    parts = Path(rel).parts
    if not parts or parts[0].lower() in {x.lower() for x in NOT_PROJECTS} or parts[0] == "..":
        return None             # outside the repo, or machinery that is never a project
    n = len(parts) if root.joinpath(*parts).is_dir() else len(parts) - 1
    for k in range(n, 0, -1):
        d = root.joinpath(*parts[:k])
        if any((d / m).is_file() for m in PROJECT_MARKERS):
            return Path(*parts[:k]).as_posix()
    return at_root


def _focus_path(session_id: str) -> Path:
    p = _state_path(session_id)
    return p.with_name(p.stem + ".focus.json")


def note_focus(root: Path, session_id: str, rels) -> str | None:
    """Remember the project this session is working in, from the paths its tools touch. `rules.py view`
    with no folder opens it. Written only when the project changes, so it costs one stat per path."""
    if not session_id:
        return None
    for rel in rels or ():
        proj = project_of(root, rel)
        if not proj:
            continue
        p = _focus_path(session_id)
        current = read_focus(session_id) or {}
        if current.get("project") != proj:
            try:
                p.write_text(json.dumps({"project": proj, "path": rel,
                                         "ts": time.strftime("%Y-%m-%dT%H:%M:%S")}), encoding="utf-8")
            except OSError:
                pass
        return proj
    return None


def read_focus(session_id: str):
    if not session_id:
        return None
    try:
        return json.loads(_focus_path(session_id).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


# --------------------------------------------------------------------------------------------
# no silent changes (knowledge_upkeep PLAN item 12, rules/repo/no-silent-changes): a session that changed
# files in a project and moves on to another project without logging anything is reminded, once
# --------------------------------------------------------------------------------------------

WRITE_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}
MAX_TRACKED_FILES = 12


def _changes_path(session_id: str) -> Path:
    p = _state_path(session_id)
    return p.with_name(p.stem + ".changes.json")


def _read_changes(session_id: str) -> dict:
    try:
        d = json.loads(_changes_path(session_id).read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_changes(session_id: str, d: dict) -> None:
    try:
        _changes_path(session_id).write_text(json.dumps(d), encoding="utf-8")
    except OSError:
        pass


def note_change(root: Path, session_id: str, tool: str, rels) -> None:
    """Remember, per project, when this session first changed a file there. Only the file tools are seen:
    a shell command that writes is free text, so a move, a delete or a generator run is not tracked."""
    if not session_id or tool not in WRITE_TOOLS:
        return
    d, touched = _read_changes(session_id), False
    for rel in rels or ():
        proj = project_of(root, rel)
        if not proj or Path(rel).name in PROJECT_MARKERS:
            continue
        ent = d.setdefault(proj, {"since": time.strftime("%Y-%m-%dT%H:%M:%S"), "files": [], "reminded": False})
        if rel not in ent["files"] and len(ent["files"]) < MAX_TRACKED_FILES:
            ent["files"].append(rel)
        touched = True
    if touched:
        _write_changes(session_id, d)


def logged_since(root: Path, project: str, since: str) -> bool:
    """True when the project's history holds an entry stamped at or after `since`."""
    p = Path(root) / project / "HISTORY.jsonl"
    try:
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return False
    for line in reversed(lines):
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if isinstance(e, dict) and str(e.get("time", "")) >= since:
            return True
    return False


def unlogged_reminder(root: Path, session_id: str, now_project) -> str | None:
    """Once per stretch of unlogged work: when the session's tools reach another project, name each project
    it changed and logged nothing in since. A project whose history caught up is forgotten, so the next
    change there starts a new stretch."""
    if not session_id or not now_project:
        return None
    d = _read_changes(session_id)
    if not d:
        return None
    out, changed = [], False
    for proj in list(d):
        ent = d[proj]
        if proj == now_project:
            continue
        if logged_since(root, proj, ent.get("since", "")):
            del d[proj]
            changed = True
            continue
        if ent.get("reminded"):
            continue
        ent["reminded"] = changed = True
        files = ", ".join(ent.get("files", [])[:4]) + (" and more" if len(ent.get("files", [])) > 4 else "")
        out.append("  %s/ since %s: %s\n    log it: python .claude/skills/rules-system/scripts/rules.py history add %s "
                   "--kind change --title \"<what changed>\" --result \"<why>\" --no-rule \"<why no rule>\""
                   % (proj, ent.get("since", "?")[11:16], files, proj))
    if changed:
        _write_changes(session_id, d)
    if not out:
        return None
    return ("NO SILENT CHANGES (rules/repo/no-silent-changes). You are moving on to %s/, and changed files in "
            "another project with nothing logged in its history since:\n%s\nLog each lasting change now, or say "
            "why it needs no entry. This reminder is shown once." % (now_project, "\n".join(out)))


def answers_waiting(root: Path, session_id: str, project) -> str | None:
    """Once per reply: the user answered a question or marked an action done in the viewer, and this session has
    not been told yet.
    The backstop to `rules.py tasks wait`, for a session that asked and did not start one."""
    if not session_id:
        return None
    project = project or (read_focus(session_id) or {}).get("project")
    if not project:
        return None
    try:
        lines = (Path(root) / project / "QUESTIONS.jsonl").read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    ids = []
    for line in lines:
        try:
            q = json.loads(line)
        except ValueError:
            continue
        if isinstance(q, dict) and (q.get("answer") or q.get("done")) and q.get("id"):
            ids.append(str(q["id"]))
    p = _state_path(session_id)
    p = p.with_name(p.stem + ".answers.json")
    try:
        told = set(json.loads(p.read_text(encoding="utf-8")))
    except (OSError, ValueError, TypeError):
        told = set()
    new = [i for i in ids if i not in told]
    if not new:
        return None
    try:
        p.write_text(json.dumps(sorted(told | set(new))), encoding="utf-8")
    except OSError:
        pass
    return ("ANSWERS WAITING: the user replied to %s in the viewer for %s/. Read them before acting on those decisions: "
            "python .claude/skills/rules-system/scripts/rules.py tasks --in %s answers"
            % (", ".join(new), project, project))


def text_hash(text: str) -> str:
    import hashlib
    return hashlib.sha1((text or "").encode("utf-8")).hexdigest()[:16]


def sent_versions(session_id: str) -> dict:
    """{rule: hash of the text this session was sent}. An older state file holds a plain list of names;
    those read as sent with no known text, so they are not re-sent."""
    p = _state_path(session_id)
    if not p.is_file():
        return {}
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if isinstance(d, list):
        return {n: None for n in d}
    return d if isinstance(d, dict) else {}


def already_sent(session_id: str) -> set:
    return set(sent_versions(session_id))


def mark_sent(session_id: str, names) -> None:
    """Remember what was sent: a list of names, or {name: hash of the text sent} so that an edited rule can
    be told apart from the one the session already has."""
    p = _state_path(session_id)
    have = sent_versions(session_id)
    have.update(names if isinstance(names, dict) else {n: have.get(n) for n in names})
    try:
        p.write_text(json.dumps(have, sort_keys=True), encoding="utf-8")
    except OSError:
        pass


# --------------------------------------------------------------------------------------------
# firing log: what actually fired, and which gate pulled it in
# --------------------------------------------------------------------------------------------
#
# Session memory answers "have I sent this already". The log answers a different and more useful
# question: WHICH GATES ARE DOING THE WORK. Without it, tuning a gate is guesswork - an over-broad
# glob and a genuinely universal rule look identical from the inside, and a gate that stopped
# matching because a folder was renamed is completely silent. `rules.py stats` reads this back and
# names the gates that have never fired, which is the failure the reconciler cannot see (a gate can
# match files on disk and still never be reached in real work).

def log_firings(root: Path, session_id: str, tool: str, matches: list[Match]) -> None:
    if not matches:
        return
    p = root / FIRING_LOG
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y-%m-%dT%H:%M:%S")
        with p.open("a", encoding="utf-8") as fh:
            for m in matches:
                fh.write(json.dumps({
                    "ts": stamp,
                    "session": (session_id or "")[:12],
                    "tool": tool,
                    **m.as_dict(),
                }) + "\n")
    except OSError:
        return
    _trim_log(p)


def _trim_log(p: Path) -> None:
    """Keep the log bounded without ever losing the recent half."""
    try:
        if p.stat().st_size < 200_000:
            return
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
        if len(lines) <= FIRING_LOG_MAX_LINES:
            return
        keep = lines[-(FIRING_LOG_MAX_LINES // 2):]
        p.write_text("\n".join(keep) + "\n", encoding="utf-8")
    except OSError:
        pass


def read_firings(root: Path) -> list[dict]:
    p = root / FIRING_LOG
    if not p.is_file():
        return []
    out = []
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def firing_stats(root: Path) -> dict:
    """Counts per rule and per gate, plus the gates and rules that have never fired."""
    records = read_firings(root)
    per_rule: dict[str, int] = {}
    per_gate: dict[tuple[str, str], int] = {}
    sessions = set()
    for r in records:
        per_rule[r.get("rule", "?")] = per_rule.get(r.get("rule", "?"), 0) + 1
        key = (r.get("rule", "?"), r.get("gate", "?"))
        per_gate[key] = per_gate.get(key, 0) + 1
        if r.get("session"):
            sessions.add(r["session"])

    declared = [(g.rule, g.raw) for g in load_gates(root)]
    never_fired_gates = [k for k in declared if k not in per_gate]
    never_fired_rules = [n for n in all_rules(root) if n not in per_rule]

    return {
        "records": len(records),
        "sessions": len(sessions),
        "per_rule": per_rule,
        "per_gate": per_gate,
        "declared_gates": declared,
        "never_fired_gates": never_fired_gates,
        "never_fired_rules": never_fired_rules,
        "first": records[0].get("ts") if records else None,
        "last": records[-1].get("ts") if records else None,
    }


# --------------------------------------------------------------------------------------------
# README discovery and index sync
# --------------------------------------------------------------------------------------------

PRUNE_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv"}


def walk_repo(root: Path, prune_test_runs: bool = False, prune_backup: bool = True):
    """Every file under the repo, skipping skills and machine noise.

    `.claude/_backup/` is pruned by DEFAULT because the CLAUDE.md sweep must never touch the
    archived copy of the old CLAUDE.md sitting there - renaming that would destroy the only record
    of what the file said, in a repo with no version control. `reconcile.py` passes False, because
    a gate pointing at the backup folder is legitimate and must not be reported as dead.
    """
    for dirpath, dirnames, filenames in os.walk(root):
        rel_dir = Path(dirpath).relative_to(root).as_posix()
        if rel_dir == ".":
            rel_dir = ""
        dirnames[:] = [
            d for d in dirnames
            if d not in PRUNE_DIRS
            and not (rel_dir == ".claude" and d == "skills")
            and not (prune_backup and rel_dir == ".claude" and d == "_backup")
            and not (prune_test_runs and rel_dir == "" and d == "test_runs")
        ]
        for f in filenames:
            yield Path(dirpath) / f


def find_readmes(root: Path) -> list[Path]:
    return sorted(p for p in walk_repo(root) if p.name == "README.md")


def sync_index(root: Path) -> bool:
    """Rewrite the generated README->rule section of rules/INDEX.md. True if the file changed."""
    index = root / RULES_DIRNAME / INDEX_NAME
    if not index.is_file():
        return False
    text = index.read_text(encoding="utf-8")
    if GEN_BEGIN not in text or GEN_END not in text:
        return False

    rows = []
    for p in find_readmes(root):
        rel = p.relative_to(root).as_posix()
        rows.append(f"- `{rel}` | `{lib_or_none(p)}`")

    block = GEN_BEGIN + "\n" + "\n".join(rows) + "\n" + GEN_END
    head, _, tail = text.partition(GEN_BEGIN)
    _, _, tail = tail.partition(GEN_END)
    new = head + block + tail
    if new != text:
        index.write_text(new, encoding="utf-8")
        return True
    return False


# --------------------------------------------------------------------------------------------
# Moving a rule
# --------------------------------------------------------------------------------------------

RULE_NAME_RE = re.compile(r"^[a-z0-9-]+(/[a-z0-9-]+)+$")


def reference_pattern(stem: str) -> re.Pattern:
    """A rule name as it appears in prose, a README or the index, and never inside a longer path.

    `scenario/naming` must match in `scenario/naming.rule.md` and at the end of a sentence, and must
    NOT match inside `_shared/scripts/scenario/naming.py` or `scenario/naming-old`. A README
    writes it as `rules/scenario/naming.rule.md`, so a bare `rules/` prefix is allowed.
    """
    return re.compile(r"(?:(?<=^rules/)|(?<=[^\w/.-]rules/)|(?<![\w/.-]))" + re.escape(stem)
                      + r"(?=\.rule\.md|(?!\.\w)[^\w/-]|$)", re.M)


def move_rule(root: Path, old: str, new: str, write: bool = True) -> list[tuple[Path, int]]:
    """Rename a rule and rewrite every reference to it: the index, other rules, every README.

    Returns (file, replacements) for each file that changed. Raises ValueError, writing nothing,
    when the move is not well formed. Line endings are preserved byte for byte, because this repo
    has no version control and a silent CRLF rewrite of forty files is not reviewable.
    The firing log keeps the old name: it is a record of what fired, not a reference.
    """
    o = old[:-len(RULE_SUFFIX)] if old.endswith(RULE_SUFFIX) else old
    n = new[:-len(RULE_SUFFIX)] if new.endswith(RULE_SUFFIX) else new
    if not RULE_NAME_RE.match(n):
        raise ValueError(f"not a rule name: {n} (want area/[group/]slug, lowercase)")
    src, dst = rule_path(root, o + RULE_SUFFIX), rule_path(root, n + RULE_SUFFIX)
    if not src.is_file():
        raise ValueError(f"no such rule: {o}")
    if dst.exists():
        raise ValueError(f"already exists: {n}")

    pat = reference_pattern(o)
    files = sorted(set((root / RULES_DIRNAME).rglob("*.md")) | set(find_readmes(root)))
    changed = []
    for p in files:
        with open(p, encoding="utf-8", newline="") as fh:
            text = fh.read()
        new_text, count = pat.subn(n, text)
        if count:
            changed.append((p, count))
            if write:
                with open(p, "w", encoding="utf-8", newline="") as fh:
                    fh.write(new_text)
    if write:
        dst.parent.mkdir(parents=True, exist_ok=True)
        src.rename(dst)
        try:
            src.parent.rmdir()          # only succeeds when the group folder is now empty
        except OSError:
            pass
        sync_index(root)
    return changed


def lib_or_none(p: Path) -> str:
    return ", ".join(readme_rules(p)) or "(none)"


def emit(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj))
