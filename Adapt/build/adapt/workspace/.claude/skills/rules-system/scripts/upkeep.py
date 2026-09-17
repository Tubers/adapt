#!/usr/bin/env python3
"""Knowledge upkeep: is what the repo learns still reaching the places that keep it?

    python .claude/skills/rules-system/scripts/rules.py upkeep            # brief: the session-start classes
    python .claude/skills/rules-system/scripts/rules.py upkeep --full     # every class
    python .claude/skills/rules-system/scripts/rules.py upkeep --json
    python .claude/skills/rules-system/scripts/rules.py upkeep --stats    # what the upkeep log says

The plan and the requirements it answers: tool_development/knowledge_upkeep/PLAN.md.

WHAT THIS IS, AND WHAT IT IS NOT
--------------------------------
Work produces facts, events, runs and questions, and each has one correct home. Nothing forces a
session to put them there, so this reports where the homes have fallen behind. It never writes a rule,
a history line or a results file on anyone's behalf, and nothing it prints is work the next session
must clear: it is a state report, and a person decides what to act on.

BRIEF AND FULL
--------------
BRIEF is the quick form, about a second, and prints nothing when there is nothing to say. Nothing runs it
unprompted: the session-start notice was removed on 2026-09-13, and nothing runs unscoped at session start. It holds the classes that are cheap: index staleness from content hashes,
runs missing their artefacts, malformed history lines. FULL adds the classes that need a walk of the
repo or the 2.5-second reconcile. Semantic gate coverage needs the model and stays behind --gates.

HONEST SILENCE
--------------
A class with nothing to report prints nothing. A class that could not run says so, with the reason,
in one SKIPPED line. The two must never look alike, because "nothing found" and "nothing checked" read
the same to someone skimming.
"""

from __future__ import annotations

import datetime
import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rules_lib as lib  # noqa: E402

# R3 applies to runs stamped AFTER this day. 273 runs predate it and 18 of those are linked from any
# history event, because history began in August and was written retroactively. Listing the other 255
# would turn a state report into a task list, which the requirements rule out. They are counted once in
# the full report and never listed.
BASELINE = "20260912"

HISTORY_NAME = "HISTORY.jsonl"
HISTORY_REQUIRED = ("id", "ts", "kind", "title")
HISTORY_KINDS = ("run", "finding", "decision", "change", "dead-end", "note", "candidate")  # writing/history-log
# A candidate parked this long with no decision is reported. Younger ones are counted in a note: a fact
# parked this morning is the loop working, not drift.
CANDIDATE_DAYS = 7

# The live trees. tool_development/ is declared historical by rules/tooling/development-inert, test_runs/
# is checked by its own class, and .claude/, rules/ and user_docs/ hold no work folders.
LIVE_EXCLUDE = {".claude", "test_runs", "tool_development", "rules", "user_docs"}
SKIP_PARTS = {"archive", "__pycache__", "_backup", "node_modules", ".venv", "venv"}
CODE_EXTS = {".py", ".js", ".ts", ".sh", ".ps1", ".go", ".rs", ".java", ".cs", ".c", ".cpp", ".h", ".xs", ".per"}
RESULTS_LAYOUT = re.compile(r"^test_runs/[^/]+/runs/[^/]+/RESULTS\.md$")
RUN_STAMP = re.compile(r"_(\d{8})-(\d{6})$")

# The same name _shared/scripts/scenario/game_paths.py exports. Written again here because a skill may
# not import from _shared/.
GAME_PROCESS = ""          # a process that upkeep must not compete with for CPU; empty checks for none

DETAIL = "python .claude/skills/rules-system/scripts/rules.py upkeep --full"
VECTOR_INDEX = Path(".claude") / "skills" / "vector-search" / "scripts" / "index.py"

BRIEF_CLASSES = ("INDEX", "RUN", "HISTORY", "CANDIDATE", "PROJECT")
STALE_DAYS = 14               # a task in progress this long is either done, blocked or abandoned
FULL_CLASSES = BRIEF_CLASSES + ("RULES", "FOLDER", "RESULTS")

WHAT = {
    "INDEX": "a search index built before its corpus changed",
    "RUN": "a run since %s missing its results file, history event, or rule-or-exemption" % BASELINE,
    "HISTORY": "a HISTORY.jsonl line that is not valid",
    "CANDIDATE": "a rule candidate parked over %d days ago with no decision" % CANDIDATE_DAYS,
    "PROJECT": "a project missing one of its three files, a TASKS.md out of format or stalled, or nested records",
    "RULES": "a dead gate, orphan rule, missing rule, unpaired README or wrong headline",
    "FOLDER": "a live folder holding code with no README.md",
    "RESULTS": "a RESULTS.md outside test_runs/<scenario>/runs/<stamp>/",
}


def result(name, items=(), fix="", skipped=None, note=None) -> dict:
    items = list(items)
    return {"name": name, "count": len(items), "items": items, "fix": fix,
            "skipped": skipped, "note": note, "what": WHAT.get(name, "")}


# --------------------------------------------------------------------------------------------------
# the checks
# --------------------------------------------------------------------------------------------------

def game_running() -> bool:
    """True while the game process exists. Upkeep must not compete with a run for CPU (N3).

    UPKEEP_GAME_RUNNING=0 or 1 overrides the process check, so a test does not pass or fail depending
    on whether the game happens to be open on the machine running it.
    """
    forced = os.environ.get("UPKEEP_GAME_RUNNING")
    if forced in ("0", "1"):
        return forced == "1"
    if os.name != "nt" or not GAME_PROCESS:
        return False
    try:
        out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq %s" % GAME_PROCESS, "/NH", "/FO", "CSV"],
                             capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.TimeoutExpired):
        return False
    return GAME_PROCESS.lower() in out.lower()


def check_index(root: Path, running: bool = False) -> dict:
    """Ask vector-search, by subprocess, which indexes are behind their corpus. Loads no model."""
    fix = "python .claude/skills/vector-search/scripts/index.py --ns <namespace>"
    script = root / VECTOR_INDEX
    if not script.is_file():
        return result("INDEX", fix=fix, skipped="the vector-search skill is not installed")
    if running:
        return result("INDEX", fix=fix,
                      skipped="the game is running, and hashing the corpus would compete with it")
    try:
        p = subprocess.run([sys.executable, str(script), "--status", "--json"], cwd=str(root),
                           capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as e:
        return result("INDEX", fix=fix, skipped="index.py --status did not answer: %s" % e)
    try:
        rows = json.loads(p.stdout)
    except ValueError:
        tail = (p.stderr.strip().splitlines() or ["no output"])[-1]
        return result("INDEX", fix=fix, skipped="index.py --status failed: %s" % tail[:160])
    items = []
    for r in rows:
        if r.get("state") == "missing":
            items.append("%s: no index built. Build it: index.py --ns %s" % (r["ns"], r["ns"]))
        elif r.get("state") == "stale" and r.get("reason"):
            items.append("%s: %s. Rebuild: index.py --ns %s" % (r["ns"], r["reason"], r["ns"]))
        elif r.get("state") == "stale":
            names = r.get("changed", []) + ["%s (removed)" % n for n in r.get("removed", [])]
            shown = ", ".join(names[:4]) + (" and %d more" % (len(names) - 4) if len(names) > 4 else "")
            items.append("%s: %d document(s) changed since the %s build: %s. Refresh: index.py --ns %s"
                         % (r["ns"], len(names), (r.get("built") or "?")[:16].replace("T", " "),
                            shown, r["ns"]))
    return result("INDEX", items, fix)


def history_files(root: Path):
    out = []
    for p in lib.walk_repo(root, prune_test_runs=True):
        if p.name != HISTORY_NAME:
            continue
        parts = p.relative_to(root).parts
        if parts and parts[0] == ".claude":
            continue
        out.append(p)
    return sorted(out)


def read_history(root: Path):
    """(events, problems). Every parseable event is returned, valid or not, so a run can still be
    matched against a line whose only fault is a missing title."""
    events, problems = [], []
    for p in history_files(root):
        rel = p.relative_to(root).as_posix()
        try:
            lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError as e:
            problems.append("%s could not be read: %s" % (rel, e))
            continue
        for i, line in enumerate(lines, start=1):
            if not line.strip():
                continue
            try:
                e = json.loads(line)
            except ValueError:
                problems.append("%s:%d is not valid JSON" % (rel, i))
                continue
            if not isinstance(e, dict):
                problems.append("%s:%d is not a JSON object" % (rel, i))
                continue
            missing = [k for k in HISTORY_REQUIRED if not e.get(k)]
            if missing:
                problems.append("%s:%d lacks %s" % (rel, i, ", ".join(missing)))
            elif e["kind"] not in HISTORY_KINDS:
                problems.append("%s:%d has kind %r, not one of %s"
                                % (rel, i, e["kind"], ", ".join(HISTORY_KINDS)))
            e = dict(e, _file=rel, _line=i)
            events.append(e)
    return events, problems


def check_history(problems) -> dict:
    return result("HISTORY", problems, "correct a line by appending one with supersedes: writing/history-log")


def run_dirs(root: Path):
    """[(repo-relative run folder, YYYYMMDD or None)] for every test_runs/<scenario>/runs/<run>/."""
    base = root / "test_runs"
    out = []
    if not base.is_dir():
        return out
    for scenario in sorted(base.iterdir()):
        runs = scenario / "runs"
        if not runs.is_dir():
            continue
        for d in sorted(runs.iterdir()):
            if d.is_dir():
                m = RUN_STAMP.search(d.name)
                out.append((d.relative_to(root).as_posix(), m.group(1) if m else None))
    return out


def _closes(event: dict, candidate_ids=frozenset()) -> bool:
    """A run event is closed by a rule it names, a rule candidate it parked, or an explicit no_rule
    reason (PLAN Q5)."""
    if str(event.get("no_rule") or "").strip():
        return True
    return any(isinstance(r, str) and ("/" in r or r in candidate_ids) for r in (event.get("refs") or []))


def check_runs(root: Path, events, baseline: str = BASELINE) -> dict:
    candidate_ids = {e.get("id") for e in events if e.get("kind") == "candidate"}
    linked = {}
    for e in events:
        for ev in e.get("evidence") or []:
            if isinstance(ev, str) and ev.replace("\\", "/").startswith("test_runs/"):
                linked.setdefault(ev.replace("\\", "/").rstrip("/"), []).append(e)
    items, legacy = [], 0
    for rel, day in run_dirs(root):
        evs = [e for k, es in linked.items() if k == rel or k.startswith(rel + "/") for e in es]
        if day is None or day <= baseline:
            if not evs:
                legacy += 1
            continue
        missing = []
        if not (root / rel / "RESULTS.md").is_file():
            missing.append("no RESULTS.md")
        if not evs:
            missing.append("no history event naming it in evidence")
        elif not any(_closes(e, candidate_ids) for e in evs):
            missing.append("a history event with no rule or candidate in refs and no no_rule reason")
        if missing:
            items.append("%s: %s" % (rel, "; ".join(missing)))
    note = None
    if legacy:
        note = ("%d run(s) stamped on or before %s have no history event. They predate this check and "
                "are not listed." % (legacy, baseline))
    return result("RUN", items, "append a run event to the folder's HISTORY.jsonl: writing/history-log",
                  note=note)


def check_rules(root: Path) -> dict:
    """reconcile.py's problems, captured rather than re-implemented."""
    import contextlib
    import io
    try:
        import reconcile
    except Exception as e:                                            # noqa: BLE001
        return result("RULES", skipped="reconcile.py could not be imported: %s" % e)
    real = reconcile.project_root
    reconcile.project_root = lambda: root
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            rc = reconcile.main(["--quiet"])
    finally:
        reconcile.project_root = real
    if rc == 2:
        return result("RULES", skipped="reconcile could not run: %s" % buf.getvalue().strip()[:160])
    items = [" ".join(l.split()) for l in buf.getvalue().splitlines()
             if l.startswith("  ") and not l.strip().startswith("note")]
    return result("RULES", items, "python .claude/skills/rules-system/scripts/rules.py reconcile")


def live_files(root: Path):
    for p in lib.walk_repo(root, prune_test_runs=True):
        rel = p.relative_to(root)
        if not rel.parts or rel.parts[0] in LIVE_EXCLUDE:
            continue
        if any(part in SKIP_PARTS for part in rel.parts[:-1]):
            continue
        yield p, rel.as_posix()


def check_folders(root: Path) -> dict:
    dirs = sorted({str(Path(rel).parent.as_posix()) for p, rel in live_files(root)
                   if p.suffix in CODE_EXTS})
    items = ["%s/ holds code and has no README.md" % d for d in dirs
             if d != "." and not (root / d / "README.md").is_file()]
    return result("FOLDER", items, "open a README naming its rule: writing/readme-and-rules")


def check_results(root: Path) -> dict:
    items = ["%s is outside test_runs/<scenario>/runs/<stamp>/" % rel
             for p, rel in live_files(root) if p.name == "RESULTS.md"]
    base = root / "test_runs"
    if base.is_dir():
        for p in sorted(base.rglob("RESULTS.md")):
            rel = p.relative_to(root).as_posix()
            if p.name == "RESULTS.md" and not RESULTS_LAYOUT.match(rel):
                items.append("%s is outside test_runs/<scenario>/runs/<stamp>/" % rel)
    return result("RESULTS", items, "a run writes its results through the harness, which owns the layout")


CANDIDATE_STATUSES = ("pending", "approved", "rejected")


def candidate_problems(root: Path, events) -> list:
    """A candidate's folder copy and master copy must agree, and a decided one must say what was decided."""
    import history
    out = []
    here = {e["id"]: e for e in events if e.get("kind") == "candidate" and e.get("id")}
    master, mp = {}, history.master_path(root)
    shown = mp.name
    try:
        shown = mp.resolve().relative_to(Path(root).resolve()).as_posix()
    except ValueError:
        pass
    if mp.is_file():
        for i, line in enumerate(mp.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                e = json.loads(line)
            except ValueError:
                out.append("%s:%d is not valid JSON" % (shown, i))
                continue
            if isinstance(e, dict) and e.get("id"):
                master[e["id"]] = e
            else:
                out.append("%s:%d is not a candidate object with an id" % (shown, i))
    for cid, e in here.items():
        where = "%s:%d" % (e["_file"], e["_line"])
        st = e.get("status", "pending")
        if st not in CANDIDATE_STATUSES:
            out.append("%s has status %r, not pending, approved or rejected" % (where, st))
        elif st == "approved" and not (e.get("decided") or {}).get("rule"):
            out.append("%s is approved with no rule recorded" % where)
        elif st == "rejected" and not str(e.get("reason", "")).strip():
            out.append("%s is rejected with no reason" % where)
        m = master.get(cid)
        if m is None:
            out.append("%s: candidate %s is missing from the master copy %s" % (where, cid, shown))
        elif m.get("status", "pending") != st:
            out.append("%s: candidate %s is %s here and %s in the master copy"
                       % (where, cid, st, m.get("status", "pending")))
    for cid, m in master.items():
        if cid not in here:
            out.append("the master copy holds %s, which %sHISTORY.jsonl does not" % (cid, m.get("folder", "?")))
    return out


def check_candidates(events, now=None, days: int = CANDIDATE_DAYS) -> dict:
    now = now or datetime.date.today()
    items, fresh = [], 0
    for e in events:
        if e.get("kind") != "candidate" or e.get("status", "pending") != "pending":
            continue
        try:
            age = (now - datetime.date.fromisoformat(str(e.get("ts"))[:10])).days
        except ValueError:
            age = days + 1
        if age <= days:
            fresh += 1
            continue
        items.append("%s in %s/, pending %d days: %s"
                     % (e.get("id"), Path(e["_file"]).parent.as_posix(), age, str(e.get("title", ""))[:80]))
    note = "%d more parked in the last %d days" % (fresh, days) if fresh else None
    return result("CANDIDATE", items, "rules.py candidates next --repo <repo>", note=note)


def project_folders(root: Path):
    """{project: markers present} and [(subfolder, its project)] for a marker file nested inside a project.

    A PROJECT is a folder in the work tree holding any of HISTORY.jsonl, TASKS.md or QUESTIONS.jsonl. Projects
    may nest: a sub-project holds its own TASKS.md or QUESTIONS.jsonl (the user, 2026-09-14). Never under
    .claude/, rules/ or test_runs/."""
    found = {}
    for p in lib.walk_repo(root, prune_test_runs=True):
        if p.name not in lib.PROJECT_MARKERS:
            continue
        parts = p.parent.relative_to(root).parts
        if parts and (parts[0].lower() in {x.lower() for x in lib.NOT_PROJECTS} or set(parts) & SKIP_PARTS):
            continue
        found.setdefault(Path(*parts).as_posix() if parts else ".", set()).add(p.name)
    # A folder below a project that holds a TASKS.md or QUESTIONS.jsonl is a sub-project, made by init and fine.
    # One holding only a HISTORY.jsonl is an old subfolder history: fold it in, or make it a sub-project.
    projects, nested = {}, []
    for rel in sorted(found):
        owner = next((q for q in sorted(projects, key=len, reverse=True)
                      if (q == "." and rel != ".") or rel.startswith(q + "/")), None)
        if owner and found[rel] == {"HISTORY.jsonl"}:
            nested.append((rel, owner))
        else:
            projects[rel] = found[rel]
    return projects, nested


def check_projects(root: Path, now=None, stale_days: int = STALE_DAYS) -> dict:
    import tasks
    now = now or datetime.date.today()
    projects, nested = project_folders(root)
    items = []
    for rel, have in projects.items():
        missing = [m for m in lib.PROJECT_MARKERS if m not in have]
        if missing:
            items.append("%s/ has no %s. Complete it: rules.py init %s --goal \"<goal>\""
                         % (rel, " or ".join(missing), rel))
        if tasks.TASKS_NAME not in have:
            continue
        p = tasks.parse((root / rel / tasks.TASKS_NAME).read_text(encoding="utf-8", errors="replace"))
        if p["problems"]:
            items.append("%s/TASKS.md is out of format: %s" % (rel, "; ".join(p["problems"])[:200]))
        for k in p["tasks"]:
            if k["status"] != "now" or not k["date"]:
                continue
            try:
                age = (now - datetime.date.fromisoformat(k["date"])).days
            except ValueError:
                continue
            if age > stale_days:
                items.append("%s/ task %s in progress %d days: %s. Finish, block or drop it: rules.py tasks --in %s"
                             % (rel, k["id"], age, k["text"][:70], rel))
    for rel, owner in nested:
        items.append("%s/ keeps only a history, inside the project %s/. Fold it in: rules.py history merge %s; "
                     "or make it a sub-project: rules.py init %s --goal G" % (rel, owner, owner, rel))
    return result("PROJECT", items, "rules.py init <folder> --goal G; rules.py tasks --in <folder>")


def report(root: Path, full: bool = False, running: bool = None, now=None) -> list:
    """Every class the mode covers, in a fixed order, each a dict from result()."""
    root = Path(root)
    if running is None:
        running = game_running()
    events, problems = read_history(root)
    problems = problems + candidate_problems(root, events)
    out = [check_index(root, running), check_runs(root, events), check_history(problems),
           check_candidates(events, now), check_projects(root, now)]
    if full:
        out += [check_rules(root), check_folders(root), check_results(root)]
    return out


# --------------------------------------------------------------------------------------------------
# output
# --------------------------------------------------------------------------------------------------

def render_brief(classes) -> str:
    """Nothing at all when every class ran and found nothing."""
    live = [c for c in classes if c["items"]]
    skipped = [c for c in classes if c["skipped"]]
    if not live and not skipped:
        return ""
    lines = []
    if live:
        lines.append("KNOWLEDGE UPKEEP: %d kind(s) of drift. Detail: %s"
                     % (len(live), DETAIL))
        for c in live:
            more = " (and %d more)" % (c["count"] - 1) if c["count"] > 1 else ""
            lines.append("  %-9s %s%s" % (c["name"], c["items"][0], more))
    for c in skipped:
        lines.append("  %-9s SKIPPED: %s" % (c["name"], c["skipped"]))
    return "\n".join(lines)


def render_full(classes) -> str:
    lines = []
    for c in classes:
        if c["skipped"]:
            lines.append("%-9s SKIPPED  %s" % (c["name"], c["skipped"]))
        else:
            lines.append("%-9s %4d     %s" % (c["name"], c["count"], c["what"]))
            for item in c["items"]:
                lines.append("           %s" % item)
            if c["items"] and c["fix"]:
                lines.append("           fix: %s" % c["fix"])
        if c["note"]:
            lines.append("           note: %s" % c["note"])
    total = sum(c["count"] for c in classes)
    ran = [c["name"] for c in classes if not c["skipped"]]
    lines.append("")
    if total:
        lines.append("%d drift item(s). A state report, not a task list: act on what your work touches."
                     % total)
    else:
        lines.append("no drift in the %d class(es) that ran: %s" % (len(ran), ", ".join(ran)))
    return "\n".join(lines)


# --------------------------------------------------------------------------------------------------
# what the records say about whether the loop is used
# --------------------------------------------------------------------------------------------------

def stats(root: Path, path: Path = None) -> str:
    """Whether the loop is used: how long runs wait for their entry, how they close, what candidates became."""
    events, _ = read_history(root)
    candidate_ids = {e.get("id") for e in events if e.get("kind") == "candidate"}
    lines = ["KNOWLEDGE UPKEEP, from the records"]
    lags, exempt, closed = [], 0, 0
    for rel, day in run_dirs(root):
        if day is None or day <= BASELINE:
            continue
        for e in events:
            if any(isinstance(x, str) and x.replace("\\", "/").rstrip("/").startswith(rel)
                   for x in e.get("evidence") or []):
                try:
                    d0 = datetime.datetime.strptime(day, "%Y%m%d").date()
                    lags.append((datetime.date.fromisoformat(str(e.get("ts"))[:10]) - d0).days)
                except ValueError:
                    pass
                if _closes(e, candidate_ids):
                    closed += 1
                    exempt += 1 if str(e.get("no_rule") or "").strip() else 0
                break
    if lags:
        lags.sort()
        lines.append("  runs since %s with a history entry: %d, days from run to entry: median %d, worst %d"
                     % (BASELINE, len(lags), lags[len(lags) // 2], lags[-1]))
        lines.append("  closed by a rule or candidate: %d, by a no_rule reason: %d" % (closed - exempt, exempt))
    else:
        lines.append("  no run since %s has a history entry yet" % BASELINE)
    cands = [e for e in events if e.get("kind") == "candidate"]
    by = {s: sum(1 for c in cands if c.get("status", "pending") == s) for s in CANDIDATE_STATUSES}
    lines.append("  rule candidates %d: pending %d, approved %d, rejected %d"
                 % (len(cands), by["pending"], by["approved"], by["rejected"]))
    return "\n".join(lines)
