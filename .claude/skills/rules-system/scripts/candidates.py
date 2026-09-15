#!/usr/bin/env python3
"""Rule candidates: park a fact the moment it shows, record it twice, and decide on it against one
cosine pass that checks it is new, contradicts nothing it may not, and has a scope the evidence supports.

    rules.py park "<fact>" --in <folder> --run test_runs/<scenario>/runs/<stamp> [--evidence P]... [--title T]
    rules.py park "<fact>" --in <folder> --no-run "<why there is no run>"
    rules.py candidates [--all]          every candidate, pending first
    rules.py candidates next             the oldest pending one, with a fresh pass and the commands to decide it
    rules.py decide <id> approve --rule <area/slug> [--agrees] [--contradicts <rule> --proof <p>] [--overlap-ok WHY]
    rules.py decide <id> reject --reason "<why>"

TWO COPIES, ONE RECORD
----------------------
A candidate is written to the HISTORY.jsonl of the folder whose work found it AND to the master copy,
.claude/skills/rules-system/data/<repo root name>/candidates.jsonl. The two lines are identical. The
folder copy keeps provenance beside the work; the master copy lets an instance that knows nothing start
a session, ask for every pending candidate, and work through them one by one. Neither ever leaves:
a decision sets `status` (pending, approved, rejected), `reason` and `decided` on the SAME line in both
files at once, and that is the only in-place change these files ever see.

EVERY APPEND IS STAMPED
-----------------------
When it was found and by which session (CLAUDE_CODE_SESSION_ID), the entry point, the run folder the
fact came from or the reason there is none, and what the pass found at that moment. A decision stamps
the same about itself.

THE COSINE PASS
---------------
One call to vector-search's `report.py scope`, shelled out and never imported, compares the candidate
with every rule line, every whole rule and every live repo file in the gate report's cache:

  NOT NEW        another rule says it at 0.80 or more. Refused unless --overlap-ok says why they differ.
                 The rule approved INTO is excluded: folding a fact into an existing rule is legitimate.
  SAME SUBJECT   another rule at 0.70 or more. An embedding cannot tell agreement from contradiction, so
                 each must be answered: --agrees, or --contradicts <rule>.
  CONTRADICTION  of a GAME FACT needs --proof and the old rule already corrected. Of WORK PROCEDURE it
                 is refused outright; changing a procedure is an edit to that procedure rule.
  SCOPE          the rule must fire on the fact's own folder. Wider globs are proposed only from evidence
                 in the pass. With none the fact is NICHE: folder-gated, found elsewhere by vector-search.

When the pass cannot run, approval is refused unless --unchecked records why. Nothing here writes rule text.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import history  # noqa: E402
import rules_lib as lib  # noqa: E402
import upkeep  # noqa: E402

DUPLICATE = 0.80        # a candidate this close to another rule's line says what that rule says
NEAR = 0.70             # the same subject: agreement or contradiction must be declared
FILE_NEAR = 0.60        # a live file this close is work the fact bears on
# Calibrated 2026-09-13 (knowledge_upkeep t16): five known facts scored their own folders' files at 0.53 to
# 0.66, so the old 0.70 never proposed anything. At 0.60 the only outside files proposed were genuinely the
# same subject (an XS array fact reaching ai/array_ladder at 0.66 and 0.62); unrelated helpers sat below 0.60.
MIN_TEXT = 25
LOG_FILES = {"HISTORY.jsonl", "QUERIES.jsonl"}
REPORT = Path(".claude") / "skills" / "vector-search" / "scripts" / "report.py"
SUFFIX = ".rule.md"
OUTCOMES = {"approve": "approved", "approved": "approved", "promote": "approved",
            "reject": "rejected", "rejected": "rejected"}
STATUSES = ("pending", "approved", "rejected")

# WORK PROCEDURE: how this repo does its work, as opposed to facts about its subject. No new rule may
# contradict one. A rule missing here is treated as a subject fact, which still needs proof and a corrected
# old rule, so a gap errs strict. Add a procedure area here when this repository grows one.
PROCEDURE = ("writing/", "lifecycle/", "repo/", "tooling/")


class Unavailable(Exception):
    """The cosine pass could not run. Carries the reason, which is always shown."""


def stem(name: str) -> str:
    return name[:-len(SUFFIX)] if name.endswith(SUFFIX) else name


def is_procedure(rule: str) -> bool:
    s = stem(rule)
    return any(s == p or s.startswith(p) for p in PROCEDURE)


def _title(text: str, limit: int = 90) -> str:
    first = re.split(r"(?<=[.;:])\s", text, maxsplit=1)[0]
    return first.rstrip(".;:") if len(first) <= limit else first[:limit].rsplit(" ", 1)[0]


def _squash(text: str) -> str:
    return " ".join(str(text).split()).lstrip("- ").strip()


def as_pass(result) -> dict:
    """A pass result in one shape. A bare list is rules only, with no file comparison."""
    if isinstance(result, dict):
        return {"rules": list(result.get("rules") or []), "files": list(result.get("files") or []),
                "files_skipped": result.get("files_skipped")}
    return {"rules": list(result or []), "files": [], "files_skipped": "no file comparison was made"}


def pass_by_subprocess(root, text: str) -> dict:
    """{rules, files, files_skipped} from vector-search's `report.py scope`. Raises Unavailable."""
    script = Path(root) / REPORT
    if not script.is_file():
        raise Unavailable("the vector-search skill is not installed")
    try:
        p = subprocess.run([sys.executable, str(script), "scope", "--json", text],
                           cwd=str(root), capture_output=True, text=True, timeout=180)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise Unavailable("report.py scope did not answer: %s" % e)
    if p.returncode != 0:
        tail = ((p.stderr or p.stdout).strip().splitlines() or ["no output"])[-1]
        raise Unavailable("report.py scope failed: %s" % tail[:200])
    try:
        return as_pass(json.loads(p.stdout))
    except ValueError:
        raise Unavailable("report.py scope printed something that is not JSON")


# --------------------------------------------------------------------------------------------------
# scope
# --------------------------------------------------------------------------------------------------

def propose_scope(root, folder: str, rules, files) -> dict:
    """{minimum, wider: [(glob, [reasons])], niche}. A glob is proposed only because a same-subject rule
    already fires there, or because a live file there sits near the fact."""
    folder = folder.strip("/")
    minimum = folder + "/**"
    gates = {}
    for rule, trig in lib.raw_gates(Path(root)):
        gates.setdefault(stem(rule), []).append(trig)
    wider = {}
    for n in rules:
        if n.get("score", 0) < NEAR:
            continue
        for trig in gates.get(stem(n.get("rule", "")), []):
            if trig.startswith("cmd:") or trig == minimum:
                continue
            wider.setdefault(trig, []).append("gate of %s (%.2f)" % (stem(n["rule"]), n["score"]))
    for f in files:
        path = str(f.get("path", ""))
        if f.get("score", 0) < FILE_NEAR or path == folder or path.startswith(folder + "/"):
            continue
        parent = Path(path).parent.as_posix()
        if parent not in ("", "."):
            wider.setdefault(parent + "/**", []).append("near file %s (%.2f)" % (path, f["score"]))
    return {"minimum": minimum, "wider": sorted(wider.items()), "niche": not wider}


def reaches_folder(root, name: str, folder: str) -> bool:
    """Does rules/<name> fire on work in `folder`? Tested on the folder's own files, so a suffix gate
    counts, and on a probe path, so a directory gate counts in a near-empty folder. Logs are left out."""
    root = Path(root)
    folder = folder.strip("/")
    rels = [folder + "/__scope_probe__"]
    for p in sorted((root / folder).rglob("*")):
        if p.is_file() and p.name not in LOG_FILES and "__pycache__" not in p.parts:
            rels.append(p.relative_to(root).as_posix())
            if len(rels) > 400:
                break
    return name in lib.rules_for_paths(root, rels)


def reachable(root, name: str) -> bool:
    if any(rule == name for rule, _ in lib.raw_gates(root)):
        return True
    return any(name in lib.readme_rules(p) for p in lib.find_readmes(root))


def _pass_summary(found, scope, unavailable=None, index_built=None) -> dict:
    if unavailable:
        return {"unavailable": unavailable}
    return {"nearest": [{"rule": stem(n["rule"]), "score": n["score"], "line": n.get("line", 0)}
                        for n in found["rules"][:3]],
            "scope": {"minimum": scope["minimum"], "wider": [g for g, _ in scope["wider"]],
                      "niche": scope["niche"]},
            "files_skipped": found["files_skipped"]}


# --------------------------------------------------------------------------------------------------
# park
# --------------------------------------------------------------------------------------------------

def park(root, text, folder, run=None, no_run="", evidence=(), title=None, nearest=None, when=None) -> dict:
    """Write one stamped candidate to <folder>/HISTORY.jsonl and to the master copy. Parking never refuses
    a near duplicate: seeing the neighbour at the moment of insight is the point."""
    root = Path(root)
    text = " ".join(str(text).split())
    if len(text) < MIN_TEXT:
        raise ValueError("a candidate is a statement of at least %d characters" % MIN_TEXT)
    rel = history.norm_folder(root, folder)
    history.check_work_folder(root, rel)
    run = str(run).replace("\\", "/").rstrip("/") if run else ""
    if run:
        if not (history.RUN_DIR.match(run) and (root / run).is_dir()):
            raise ValueError("--run names %s, which is no run folder: test_runs/<scenario>/runs/<stamp>" % run)
    elif not str(no_run).strip():
        raise ValueError("a candidate names the run it came from: --run test_runs/<scenario>/runs/<stamp>, "
                         "or --no-run WHY when it came from somewhere else")
    evidence = [str(e).replace("\\", "/").rstrip("/") for e in evidence]
    for e in evidence:
        if not (root / e).exists():
            raise ValueError("evidence path does not exist: %s" % e)
    if run and run not in evidence:
        evidence = [run] + evidence

    found, scope, unavailable = None, None, None
    if nearest is not None:
        try:
            found = as_pass(nearest(text))
            scope = propose_scope(root, rel, found["rules"], found["files"])
        except Unavailable as e:
            unavailable = str(e)
    else:
        unavailable = "no cosine pass was supplied"

    events, _ = upkeep.read_history(root)
    master = history.master_path(root)
    taken = {e.get("id") for e in events} | set(_master_ids(master))
    s = history.stamp(when)
    rec = {"id": history.unique_id(taken, "%s-%s" % (s["ts"], history.slug(title or text))), "ts": s["ts"],
           "kind": "candidate", "title": title or _title(text), "what": text, "folder": rel + "/",
           "status": "pending", "reason": ""}
    if run:
        rec["run"] = run
    else:
        rec["no_run"] = " ".join(str(no_run).split())
    if evidence:
        rec["evidence"] = evidence
    rec["found"] = {"time": s["time"], "session": s["session"], "by": "rules.py park",
                    "entrypoint": os.environ.get("CLAUDE_CODE_ENTRYPOINT", "")}
    rec["pass"] = _pass_summary(found, scope, unavailable)

    folder_path = history.history_file_for(root, rel)
    before = folder_path.read_bytes() if folder_path.is_file() else None
    history.append_line(folder_path, rec)
    try:
        history.append_line(master, rec)
    except Exception:
        _restore(folder_path, before)       # two copies or none: never one
        raise
    return {"candidate": rec, "path": folder_path, "master": master, "folder": rel,
            "neighbours": found["rules"] if found else None, "pass": found, "scope": scope,
            "unavailable": unavailable}


# --------------------------------------------------------------------------------------------------
# the queue
# --------------------------------------------------------------------------------------------------

def _master_rows(master: Path):
    rows = []
    if master.is_file():
        for line in master.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                e = json.loads(line)
            except ValueError:
                continue
            if isinstance(e, dict) and e.get("id"):
                rows.append(e)
    return rows


def _master_ids(master: Path):
    return [e["id"] for e in _master_rows(master)]


def queue(root, include_decided: bool = False) -> list:
    """Candidates from the master copy, in the order they were found. Pending only unless asked."""
    rows = _master_rows(history.master_path(root))
    return [e for e in rows if include_decided or e.get("status", "pending") == "pending"]


def next_pending(root):
    q = queue(root)
    return q[0] if q else None


# --------------------------------------------------------------------------------------------------
# decide
# --------------------------------------------------------------------------------------------------

def _restore(path: Path, before) -> None:
    if before is None:
        try:
            path.unlink()
        except OSError:
            pass
    else:
        path.write_bytes(before)


def _proof_exists(root: Path, proof: str, events) -> bool:
    """Proof is a history entry, or a run folder or a file inside one. `.` or `rules` is not evidence."""
    if any(e.get("id") == proof for e in events):
        return True
    p = proof.replace("\\", "/").strip().rstrip("/")
    return bool(re.match(r"^test_runs/[^/]+/runs/[^/]+(/.+)?$", p)) and (root / p).exists()


def decide(root, cand_id, outcome, rule=None, reason="", overlap_ok="", unchecked="", agrees=False,
           contradicts=(), proof=(), nearest=None, resolve=None) -> dict:
    """Set a candidate's status, reason and decision record in BOTH copies. Raises ValueError, writing
    nothing, when the decision is refused."""
    root = Path(root)
    outcome = OUTCOMES.get(str(outcome).lower())
    if not outcome:
        raise ValueError("decide takes approve or reject")
    master = history.master_path(root)
    rows = [e for e in _master_rows(master) if e.get("id") == cand_id]
    if not rows:
        raise ValueError("no candidate with id %s in %s. List them: rules.py candidates" % (cand_id, master))
    cand = rows[0]
    if cand.get("status", "pending") != "pending":
        raise ValueError("%s was already %s: %s" % (cand_id, cand.get("status"), cand.get("reason", "")))
    folder = str(cand.get("folder", "")).strip("/")
    folder_path = history.history_file_for(root, folder)
    _, _, _, here = history.find_line(folder_path, cand_id)   # both copies must hold it before either changes
    history.find_line(master, cand_id)
    if here.get("status", "pending") != "pending":
        raise ValueError("%s is %s in %s but pending in the master copy; the copies disagree, and rules.py upkeep "
                         "reports it. Settle that before deciding" % (cand_id, here.get("status"), folder_path.name))

    events, _ = upkeep.read_history(root)
    s = history.stamp()
    decided = {"time": s["time"], "session": s["session"], "by": "rules.py decide",
               "entrypoint": os.environ.get("CLAUDE_CODE_ENTRYPOINT", "")}
    neighbours, scope, result = None, None, None

    if outcome == "rejected":
        if not str(reason).strip():
            raise ValueError("a rejection needs --reason: later, an unexplained rejection and a lost "
                             "candidate look the same")
    else:
        if not rule:
            raise ValueError("approve needs --rule <area/slug>: the rule that now carries the fact. "
                             "Write or extend and gate that rule first, then decide")
        name = resolve(rule) if resolve else (rule if rule.endswith(SUFFIX) else rule + SUFFIX)
        if not name or not (root / lib.RULES_DIRNAME / name).is_file():
            raise ValueError("no rule file for %s. Write the rule first, then decide" % rule)
        if not reachable(root, name):
            raise ValueError("rules/%s has no gate in rules/INDEX.md and no README names it, so it could "
                             "never reach a session. Gate it first" % name)
        if not reaches_folder(root, name, folder):
            raise ValueError("rules/%s does not fire on %s/, where the fact was found. At the very least a rule "
                             "is scoped to that folder: add `%s/**` to its gate in rules/INDEX.md"
                             % (name, folder, folder))
        target = stem(name)

        contradicted = []
        for c in contradicts:
            c_name = resolve(c) if resolve else (c if c.endswith(SUFFIX) else c + SUFFIX)
            if not c_name or not (root / lib.RULES_DIRNAME / c_name).is_file():
                raise ValueError("--contradicts names %s, which is no rule" % c)
            if is_procedure(c_name):
                raise ValueError("rules/%s is WORK PROCEDURE, and no rule may contradict current procedure. "
                                 "If the procedure should change, that is an edit to rules/%s on its own, not "
                                 "a rule candidate" % (c_name, c_name))
            contradicted.append(stem(c_name))
        if contradicted:
            if not proof:
                raise ValueError("contradicting a game fact needs --proof: a run folder or history entry id "
                                 "showing the old content false or the new more accurate")
            missing = [p for p in proof if not _proof_exists(root, p, events)]
            if missing:
                raise ValueError("--proof names nothing that exists as a run folder or a history entry: %s"
                             % ", ".join(missing))

        try:
            if nearest is None:
                raise Unavailable("no cosine pass was supplied")
            result = as_pass(nearest(cand.get("what") or cand.get("title", "")))
            neighbours = result["rules"]
        except Unavailable as e:
            if not str(unchecked).strip():
                raise ValueError("the cosine pass could not run: %s. Fix that and decide again, or pass "
                                 "--unchecked WHY to approve without it" % e)
            decided["unchecked"] = str(unchecked).strip()

        if neighbours is not None:
            others = [n for n in neighbours if stem(n.get("rule", "")) != target]
            dupes = [n for n in others if n.get("score", 0) >= DUPLICATE]
            subject = [n for n in others if n.get("score", 0) >= NEAR]
            if dupes and not str(overlap_ok).strip():
                raise ValueError(
                    "not new: an existing rule already says this.\n" + _lines(dupes)
                    + "\nFold the fact into that rule and approve with --rule naming it, reject the candidate, "
                      "or pass --overlap-ok WHY if the two genuinely differ")
            for n in subject:
                if stem(n["rule"]) in contradicted and n.get("text"):
                    body = (root / lib.RULES_DIRNAME / (stem(n["rule"]) + SUFFIX)).read_text(
                        encoding="utf-8", errors="replace")
                    if _squash(n["text"]) and _squash(n["text"]) in " ".join(body.split()):
                        raise ValueError("rules/%s still says: %s\nCorrect that rule first, citing the proof, "
                                         "then decide" % (stem(n["rule"]) + SUFFIX, n["text"][:160]))
            unanswered = [n for n in subject if stem(n["rule"]) not in contradicted
                          and not (n in dupes and str(overlap_ok).strip())]
            if unanswered and not agrees:
                proc = [n for n in unanswered if is_procedure(n["rule"])]
                raise ValueError(
                    "these rules are on the same subject. An embedding cannot tell agreement from "
                    "contradiction, so read each and say:\n" + _lines(unanswered)
                    + "\n  --agrees                         the new rule contradicts none of them"
                      "\n  --contradicts <rule> --proof <p>  a GAME FACT the evidence overturns"
                    + ("\nWork procedure among them may not be contradicted at all: %s"
                       % ", ".join(stem(n["rule"]) for n in proc) if proc else ""))
            scope = propose_scope(root, folder, neighbours, result["files"])
            decided["nearest"] = [{"rule": stem(n["rule"]), "score": n["score"], "line": n.get("line", 0)}
                                  for n in others[:3]]
            if subject:
                decided["checked_against"] = sorted({"%s:%s" % (stem(n["rule"]), n.get("line", 0))
                                                     for n in subject})
            if dupes:
                decided["overlap_ok"] = str(overlap_ok).strip()
        decided["rule"] = target
        decided["scope"] = {"folder": folder + "/", "gates": [t for r, t in lib.raw_gates(root) if r == name],
                            "proposed": [g for g, _ in scope["wider"]] if scope else None,
                            "niche": scope["niche"] if scope else None}
        if agrees:
            decided["agrees"] = True
        if contradicted:
            decided["contradicts"] = contradicted
            decided["proof"] = list(proof)
        if not str(reason).strip():
            reason = "approved into %s" % target

    changes = {"status": outcome, "reason": " ".join(str(reason).split()), "decided": decided}
    folder_before = folder_path.read_bytes()
    history.set_keys(folder_path, cand_id, changes)
    try:
        history.set_keys(master, cand_id, changes)
    except Exception:
        folder_path.write_bytes(folder_before)      # two copies or none: never one
        raise
    updated = dict(cand, **changes)
    return {"candidate": updated, "path": folder_path, "master": master, "folder": folder,
            "neighbours": neighbours, "scope": scope,
            "files_skipped": result["files_skipped"] if result else None}


# --------------------------------------------------------------------------------------------------
# output
# --------------------------------------------------------------------------------------------------

def _lines(neighbours) -> str:
    return "\n".join("  %.3f  %s:%s%s  %s" % (n["score"], stem(n["rule"]), n.get("line", 0),
                                             " [procedure]" if is_procedure(n["rule"]) else "",
                                             (n.get("text") or "")[:110]) for n in neighbours)


def render_neighbours(neighbours, unavailable=None) -> str:
    if unavailable:
        return "  the cosine pass did NOT run: %s" % unavailable
    if not neighbours:
        return "  nothing in the rules index is near it"
    lines = []
    for n in neighbours:
        s = n.get("score", 0)
        tag = ("SAYS THIS ALREADY" if s >= DUPLICATE else "same subject: agrees or contradicts?"
               if s >= NEAR else "")
        if tag and is_procedure(n.get("rule", "")):
            tag += " [procedure]"
        lines.append("  %.3f  %-46s %s" % (s, "%s:%s" % (stem(n.get("rule", "")), n.get("line", 0)), tag))
        if s >= NEAR and n.get("text"):
            lines.append("         %s" % n["text"][:140])
    return "\n".join(lines)


def render_scope(scope, files_skipped=None) -> str:
    if not scope:
        return ""
    lines = ["  minimum  %-40s the folder it was found in" % scope["minimum"]]
    for glob, reasons in scope["wider"]:
        lines.append("  wider    %-40s %s" % (glob, "; ".join(reasons[:3])))
    if scope["niche"]:
        lines.append("  NICHE: nothing outside %s bears on it. Gate it to %s alone; vector-search finds it "
                     "from anywhere else." % (scope["minimum"][:-3] + "/", scope["minimum"]))
    if files_skipped:
        lines.append("  (live files were not compared: %s)" % files_skipped)
    return "\n".join(lines)


def render_candidate(c: dict) -> str:
    found = c.get("found") or {}
    lines = ["%s  [%s]  %s" % (c.get("id"), c.get("status", "pending"), c.get("folder", "")),
             "  fact     %s" % c.get("what", ""),
             "  source   %s" % (c.get("run") or "no run: %s" % c.get("no_run", "")),
             "  found    %s by session %s" % (found.get("time", "?"), found.get("session") or "unknown")]
    if c.get("status") != "pending":
        lines.append("  %s  %s" % (c.get("status"), c.get("reason", "")))
    return "\n".join(lines)
