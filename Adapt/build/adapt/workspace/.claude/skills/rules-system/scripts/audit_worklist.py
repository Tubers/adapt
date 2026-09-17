#!/usr/bin/env python3
"""Which rules the refactoring audit flagged, so a change to one of them needs no approval.

    python .claude/skills/rules-system/scripts/audit_worklist.py [--no-reindex]

Writes data/<repo>/audit-worklist.json:

    {"generated": "2026-09-13T10:00:00+00:00",
     "rules": ["repo/no-silent-changes", "xs/guard", ...],
     "why": {"xs/guard": ["facts", "reconcile"], ...},
     "skipped": {"coverage": "why that source could not run"}}

WHY
---
A rule change needs the user's approval (.claude/hooks/ask_rule_approval.py), except a change the
audit asked for: new wording for a duplicated fact, a merge, a move, a hub line, a gate. Those are
worked through in bulk, and asking about each would bury the one-off change that deserves a look.
This file is how the hook tells the two apart: a rule named here may be edited or moved without
asking, for as long as the list is fresh.

WHERE THE NAMES COME FROM
-------------------------
  reconcile   every rule a reconcile problem names (orphan, headline, dead glob, over budget ...),
              captured from reconcile.py in this folder, as upkeep.py check_rules does
  facts       both rules of every duplicated statement, at the audit's cut (0.80)
  dupes       both rules of every overlapping pair, at the audit's cut (0.82)
  coherence   every rule nearer another area's centre
  hubs        every hub that fails to name a rule in its area
  coverage    every rule with a missing gate at the counted cut (0.70), or an over-broad gate

The embedding reports are vector-search's. They are run by subprocess with `--json`, never imported,
because skills are silos, and they are handed data/<repo>/accepted.json so a finding a person already
read and kept is not flagged again. A source that cannot run is recorded under `skipped` and adds
nothing: an unrun report pre-approves no change.

FRESHNESS
---------
load_worklist() returns the names only while the file is under 24 hours old. A missing, broken,
future-dated or stale list pre-approves nothing, so an old audit cannot license edits forever.
"""

from __future__ import annotations

import datetime
import json
import os
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_NAME = Path(__file__).resolve().parents[4].name      # the repository's own folder name
DATA_REL = Path(".claude") / "skills" / "rules-system" / "data" / REPO_NAME
WORKLIST_REL = DATA_REL / "audit-worklist.json"
ACCEPTED_REL = DATA_REL / "accepted.json"
VECTOR_SCRIPTS = Path(".claude") / "skills" / "vector-search" / "scripts"
RULE_SUFFIX = ".rule.md"
MAX_AGE_HOURS = 24

# (source name in `why`, report.py command, extra arguments). The cuts are the ones `rules.py audit`
# uses (report.refactor), because that is the command whose findings pre-approve a change.
REPORTS = (
    ("facts", "facts", ["--cut", "0.80"]),
    ("dupes", "dupes", ["--cut", "0.82"]),
    ("coherence", "coherence", []),
    ("hubs", "hubs", []),
    ("coverage", "gates", []),
)

# A rule named with its suffix, anywhere in text: rules/xs/guard.rule.md, **xs/guard.rule.md**, an
# absolute path. A glob such as rules/**/*.rule.md never matches, because `*` is not a name character.
_SUFFIXED = re.compile(r"[A-Za-z0-9_.-]+(?:[/\\][A-Za-z0-9_.-]+)*\.rule\.md(?![\w.-])")
# A bare area/slug token, counted only when it is a rule that exists.
_BARE = re.compile(r"(?<![\w/.\\-])[A-Za-z0-9_-]+(?:/[A-Za-z0-9_-]+)+(?![\w/.\\-])")


def stem(name: str) -> str:
    """`rules/xs/guard.rule.md`, `xs\\guard.rule.md`, `xs/guard` -> `xs/guard`."""
    n = name.replace("\\", "/").strip().strip("*`\"'")
    if "/rules/" in "/" + n:
        n = ("/" + n).rsplit("/rules/", 1)[1]
    if n.endswith(RULE_SUFFIX):
        n = n[:-len(RULE_SUFFIX)]
    return n.lstrip("./")


def known_rules(root: Path) -> set[str]:
    base = Path(root) / "rules"
    if not base.is_dir():
        return set()
    return {stem(p.relative_to(base).as_posix()) for p in base.rglob("*" + RULE_SUFFIX)}


def names_in(text: str, known: set[str] | None = None) -> set[str]:
    """Every rule named in text. Suffixed names always count; bare area/slug only if in `known`."""
    out = set()
    for m in _SUFFIXED.finditer(text or ""):
        n = stem(m.group(0))
        if "/" in n:
            out.add(n)
    if known:
        for m in _BARE.finditer(text or ""):
            if m.group(0) in known:
                out.add(m.group(0))
    return out


# ------------------------------------------------------------------------------------------ sources

def reconcile_names(root: Path) -> set[str]:
    """Rules named by reconcile's problems. Raises RuntimeError when reconcile cannot run."""
    import contextlib
    import io
    if str(HERE) not in sys.path:
        sys.path.insert(0, str(HERE))
    import reconcile
    real = reconcile.project_root
    reconcile.project_root = lambda: Path(root)
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            rc = reconcile.main(["--quiet"])
    finally:
        reconcile.project_root = real
    if rc == 2:
        raise RuntimeError("reconcile could not run: %s" % buf.getvalue().strip()[:160])
    out = set()
    for line in buf.getvalue().splitlines():
        if line.startswith("  ") and not line.strip().startswith("note"):
            out |= names_in(line)
    return out


def flagged_by(source: str, data: dict) -> set[str]:
    """The rules one report's --json findings ask to change."""
    f = data.get("findings")
    out = set()
    if source in ("facts", "dupes"):
        for x in f:
            out |= {stem(x["a"]), stem(x["b"])}
    elif source == "coherence":
        out = {stem(x["rule"]) for x in f}
    elif source == "hubs":
        out = {stem(x["hub"]) for x in f if x.get("missing")}
    elif source == "coverage":
        out = {stem(x["rule"]) for x in f.get("missing", []) if x.get("counted")}
        out |= {stem(x["rule"]) for x in f.get("overbroad", [])}
    return out


def run_report(root: Path, which: str, extra: list[str], timeout: int = 1800) -> dict:
    script = Path(root) / VECTOR_SCRIPTS / "report.py"
    if not script.is_file():
        raise RuntimeError("the vector-search skill is not installed")
    cmd = [sys.executable, str(script), which, "--json"] + list(extra)
    accepted = Path(root) / ACCEPTED_REL
    if accepted.is_file():
        cmd += ["--accepted", str(accepted)]
    p = subprocess.run(cmd, cwd=str(root), capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=timeout)
    lines = [l for l in p.stdout.splitlines() if l.strip()]
    if p.returncode != 0 or not lines:
        why = (p.stderr.strip().splitlines() or p.stdout.strip().splitlines() or ["no output"])[-1]
        raise RuntimeError("report.py %s exited %d: %s" % (which, p.returncode, why[:200]))
    return json.loads(lines[-1])


def reindex(root: Path) -> str | None:
    """Refresh the rules index as `rules.py audit` does. Returns a reason when it could not."""
    script = Path(root) / VECTOR_SCRIPTS / "index.py"
    if not script.is_file():
        return "the vector-search skill is not installed"
    try:
        p = subprocess.run([sys.executable, str(script)], cwd=str(root), capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=1800)
    except (OSError, subprocess.TimeoutExpired) as e:
        return str(e)
    return None if p.returncode == 0 else "index.py exited %d" % p.returncode


# ------------------------------------------------------------------------------------ write and load

def worklist_path(root: Path) -> Path:
    return Path(root) / WORKLIST_REL


def write_worklist(root: Path, do_reindex: bool = True) -> dict:
    """Run every source, write the worklist, and return what was written."""
    root = Path(root)
    why: dict[str, set[str]] = {}
    skipped: dict[str, str] = {}

    def add(names, source):
        for n in names:
            why.setdefault(n, set()).add(source)

    try:
        add(reconcile_names(root), "reconcile")
    except Exception as e:                                            # noqa: BLE001
        skipped["reconcile"] = str(e)[:200]

    if do_reindex:
        note = reindex(root)
        if note:
            skipped["reindex"] = note
    for source, which, extra in REPORTS:
        try:
            add(flagged_by(source, run_report(root, which, extra)), source)
        except Exception as e:                                        # noqa: BLE001
            skipped[source] = str(e)[:200]

    data = {
        "generated": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "rules": sorted(why),
        "why": {n: sorted(s) for n, s in sorted(why.items())},
        "skipped": skipped,
    }
    path = worklist_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    return data


def status(root: Path, max_age_hours: float = MAX_AGE_HOURS) -> tuple[set[str], str]:
    """(pre-approved rule names, one line saying why). The set is empty unless the list is fresh."""
    path = worklist_path(root)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        generated = datetime.datetime.fromisoformat(str(data["generated"]))
        rules = data["rules"]
        if not isinstance(rules, list):
            raise ValueError("rules is not a list")
    except FileNotFoundError:
        return set(), "there is no audit worklist"
    except (OSError, ValueError, KeyError, TypeError) as e:
        return set(), "the audit worklist is unreadable (%s)" % str(e)[:80]
    if generated.tzinfo is None:
        generated = generated.replace(tzinfo=datetime.timezone.utc)
    age = (datetime.datetime.now(datetime.timezone.utc) - generated).total_seconds() / 3600.0
    if age < -0.1:
        return set(), "the audit worklist is dated in the future (%s)" % data["generated"]
    if age > max_age_hours:
        return set(), "the audit worklist is %.0f hours old, past the %g-hour limit" % (age, max_age_hours)
    names = {stem(str(r)) for r in rules}
    return names, "the audit worklist from %s flags %d rule(s)" % (data["generated"], len(names))


def load_worklist(root: Path, max_age_hours: float = MAX_AGE_HOURS) -> set[str]:
    """The rule names a fresh worklist flags; empty when it is missing, broken or stale."""
    return status(root, max_age_hours)[0]


def rename_in_worklist(root: Path, old: str, new: str) -> bool:
    """After `rules.py move`, carry a flagged rule's entry to its new name. True if it changed."""
    path = worklist_path(root)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    o, n = stem(old), stem(new)
    rules = [stem(str(r)) for r in data.get("rules", [])]
    if o not in rules or n in rules:
        return False
    data["rules"] = sorted(set(rules) | {n})
    why = data.setdefault("why", {})
    why[n] = sorted(set(why.get(o, [])) | {"moved from " + o})
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    return True


def project_root() -> Path:
    # <project>/.claude/skills/rules-system/scripts/audit_worklist.py
    return HERE.parents[3]


def main(argv) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    root = project_root()
    data = write_worklist(root, do_reindex="--no-reindex" not in argv)
    print("wrote %s: %d rule(s) flagged by the audit" % (WORKLIST_REL.as_posix(), len(data["rules"])))
    for name in data["rules"]:
        print("  %-52s %s" % (name, ", ".join(data["why"][name])))
    for source, reason in data["skipped"].items():
        print("  SKIPPED %s: %s" % (source, reason))
    print("Edits and moves of these rules pass without asking for %d hours." % MAX_AGE_HOURS)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
