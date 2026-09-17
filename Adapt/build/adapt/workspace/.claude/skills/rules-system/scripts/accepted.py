"""The accepted-findings list: refactoring candidates a person has read and decided to keep.

    .claude/skills/rules-system/data/<repo>/accepted.json

Every embedding report prints CANDIDATES. A candidate that has been read and kept on purpose - two
halves of a deliberate split, a rule filed by what its gates reach rather than by its vocabulary -
comes back on every pass unless something remembers the decision. Re-reading the same 34 pairs each
time is how a worklist stops being read at all.

The list is data this skill owns. vector-search never opens it: rules.py hands its path over with
`--accepted`, so the other skill stays a silo that is told what to hide rather than reaching in.

Each entry carries a `why`, because an acceptance nobody can explain is a finding that was silenced
rather than decided. A fact is matched on the TEXT of both lines, not their line numbers, so editing
either statement brings the pair back for a fresh look.

Kinds and what identifies an entry:
    facts      a, text_a, b, text_b    two rule lines, by rule name and line text
    dupes      a, b                   two rules, in either order
    coherence  rule                   one rule sitting nearer another area
    missing    file, rule             a rule near a file its gates never reach
    overbroad  rule                   a rule whose gate fires on distant files
"""

from __future__ import annotations

import datetime
import json
from pathlib import Path

# this repository's own list, beside its candidates: data/<repo root folder name>/accepted.json
DATA = Path(__file__).resolve().parents[1] / "data" / Path(__file__).resolve().parents[4].name / "accepted.json"
KINDS = ("facts", "dupes", "coherence", "missing", "overbroad")
SUFFIX = ".rule.md"
ABOUT = ("Refactoring candidates a person read and kept on purpose. Managed with "
         "`rules.py accept`; every entry needs a why. A fact is matched on line TEXT, so "
         "editing either line brings the pair back.")


def stem(name: str) -> str:
    return name[:-len(SUFFIX)] if name.endswith(SUFFIX) else name


def load(path: Path = None) -> dict:
    path = path or DATA
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        data = {}
    out = {"_about": ABOUT}
    for kind in KINDS:
        out[kind] = list(data.get(kind, []))
    return out


def save(data: dict, path: Path = None) -> None:
    path = path or DATA
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def rule_line(root: Path, rule: str, line_no: int) -> str:
    """A rule line exactly as the index stores it: stripped, with the bullet dash removed."""
    p = root / "rules" / (stem(rule) + SUFFIX)
    lines = p.read_text(encoding="utf-8").splitlines()
    if not 1 <= line_no <= len(lines):
        raise ValueError(f"{stem(rule)} has no line {line_no}")
    s = lines[line_no - 1].strip()
    body = s[2:].strip() if s.startswith("- ") else s
    if len(body) < 25:
        raise ValueError(f"{stem(rule)}:{line_no} is too short to be a fact the report compares")
    return body


def key(kind: str, e: dict):
    """What makes two entries the same decision. Mirrors the matching in vector-search report.py."""
    if kind == "facts":
        return frozenset([(stem(e["a"]), e["text_a"]), (stem(e["b"]), e["text_b"])])
    if kind == "dupes":
        return frozenset([stem(e["a"]), stem(e["b"])])
    if kind in ("coherence", "overbroad"):
        return stem(e["rule"])
    if kind == "missing":
        return (e["file"], stem(e["rule"]))
    raise ValueError(f"unknown kind: {kind} (want one of {', '.join(KINDS)})")


def make_entry(root: Path, kind: str, args: list, why: str, resolve) -> dict:
    """Build one entry from command-line arguments. `resolve` turns a rule token into a rule name
    or None. Raises ValueError with a message a person can act on."""
    if kind not in KINDS:
        raise ValueError(f"unknown kind: {kind} (want one of {', '.join(KINDS)})")
    if not why or not why.strip():
        raise ValueError("--why is required: an acceptance nobody can explain is a silenced finding")

    def rule(token):
        name = resolve(token)
        if name is None:
            raise ValueError(f"no such rule, or ambiguous: {token}")
        return stem(name)

    want = {"facts": 2, "dupes": 2, "coherence": 1, "missing": 2, "overbroad": 1}[kind]
    if len(args) != want:
        raise ValueError(f"accept {kind} takes {want} argument(s), got {len(args)}")

    e = {}
    if kind == "facts":
        for side, token in zip(("a", "b"), args):
            name, _, num = token.rpartition(":")
            if not name or not num.isdigit():
                raise ValueError(f"a fact is <rule>:<line>, got {token}")
            e[side] = rule(name)
            e["text_" + side] = rule_line(root, e[side], int(num))
        if e["a"] == e["b"]:
            raise ValueError("a fact pair is two DIFFERENT rules")
    elif kind == "dupes":
        e["a"], e["b"] = rule(args[0]), rule(args[1])
        if e["a"] == e["b"]:
            raise ValueError("a dupe pair is two DIFFERENT rules")
    elif kind in ("coherence", "overbroad"):
        e["rule"] = rule(args[0])
    else:
        f = args[0].replace("\\", "/").lstrip("./")
        if not (root / f).is_file():
            raise ValueError(f"no such file: {f}")
        e["file"], e["rule"] = f, rule(args[1])
    e["why"] = why.strip()
    e["date"] = datetime.date.today().isoformat()
    return e


def add(data: dict, kind: str, entry: dict) -> bool:
    """False when the same decision is already recorded; the older why is kept."""
    k = key(kind, entry)
    if any(key(kind, e) == k for e in data[kind]):
        return False
    data[kind].append(entry)
    return True


def describe(kind: str, e: dict) -> str:
    if kind == "facts":
        return f"{e['a']} = {e['b']}   \"{e['text_a'][:50]}...\""
    if kind == "dupes":
        return f"{e['a']} = {e['b']}"
    if kind == "missing":
        return f"{e['rule']} near {e['file']}"
    return e["rule"]


def rename_rule(data: dict, old: str, new: str) -> int:
    """Follow a `rules.py move`, so an acceptance survives its rule being refiled."""
    old, new, n = stem(old), stem(new), 0
    for kind in KINDS:
        for e in data[kind]:
            for field in ("a", "b", "rule"):
                if e.get(field) == old:
                    e[field] = new
                    n += 1
    return n
