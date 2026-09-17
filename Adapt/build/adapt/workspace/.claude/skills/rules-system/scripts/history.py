#!/usr/bin/env python3
"""Folder records: every HISTORY.jsonl entry is written by a command and read back in slices.

    rules.py history [folder] [runs|findings|changes|decisions|dead-ends|notes|candidates]
                     [--last 5 | --first 5 | --all] [--since YYYY-MM-DD] [--grep WORD] [--status S]
    rules.py history show <id>
    rules.py history add <folder> --kind <kind> --title "<title>" [--what W] [--result R]
                     [--evidence P]... [--refs R]... [--no-rule WHY] [--numbers key=value]...
                     [--tags T]... [--status open|closed|withdrawn] [--supersedes ID]

EVERY FOLDER KEEPS ITS OWN
--------------------------
A mechanic, a pattern, a tool: each folder with its own agenda has its own HISTORY.jsonl, and there is
no central one. Work done briefly in another folder is logged in THAT folder, so no change is silent.

WHY A COMMAND AND NOT THE FILE
------------------------------
An entry typed by hand is missing its id, its time or its session, or it breaks the one-object-per-line
shape, and nothing notices until a reader trips on it. `history add` stamps id, date, time and session,
refuses a run entry that does not name its run folder and close with a rule, a candidate or a reason,
and creates the file when the folder has none. Rule candidates are the one kind it will not write:
they go through `rules.py park`, which checks them against every rule first.

WHY SLICES
----------
A history file grows without bound and a session needs a few lines of it. A slice is one kind, the
first or last few, one line each, and a folder-scoped slice opens with the folder's state: its NOW
task, its latest entry and its pending candidates.

The one in-place change anywhere in these files is a candidate's status and reason, set by
`rules.py decide` in the folder copy and the master copy together. Everything else is append-only.
"""

from __future__ import annotations

import datetime
import json
import math
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import upkeep  # noqa: E402

# The skill keeps this repo's records in data/<repo root folder name>/. A sub-agent that borrows the
# skill to keep rules for a different tree gets its own folder beside it, never a shared file.
DATA_BASE = Path(__file__).resolve().parents[1] / "data"
CANDIDATES_NAME = "candidates.jsonl"
TASKS_NAME = "TASKS.md"

KIND_WORDS = {"runs": "run", "findings": "finding", "changes": "change", "decisions": "decision",
              "dead-ends": "dead-end", "deadends": "dead-end", "notes": "note", "candidates": "candidate"}
ADD_KINDS = ("run", "finding", "decision", "change", "dead-end", "note")
STATUSES = ("open", "closed", "withdrawn")
NO_HISTORY_ROOTS = {".claude", "test_runs", "rules"}
RUN_DIR = re.compile(r"^test_runs/[^/]+/runs/[^/]+$")
DEFAULT_SLICE = 5
SUFFIX = ".rule.md"


# --------------------------------------------------------------------------------------------------
# shared primitives: where things live, what every append carries, how a line changes in place
# --------------------------------------------------------------------------------------------------

def data_dir(root) -> Path:
    return DATA_BASE / Path(root).resolve().name


def master_path(root) -> Path:
    return data_dir(root) / CANDIDATES_NAME


def stamp(when: str = None) -> dict:
    now = datetime.datetime.now()
    return {"ts": when or now.date().isoformat(), "time": now.isoformat(timespec="seconds"),
            "session": os.environ.get("CLAUDE_CODE_SESSION_ID") or os.environ.get("CLAUDE_SESSION_ID") or ""}


def slug(text: str, words: int = 6) -> str:
    return "-".join(re.findall(r"[a-z0-9]+", str(text).lower())[:words]) or "entry"


def unique_id(taken, base: str) -> str:
    eid, n = base, 2
    while eid in taken:
        eid = "%s-%d" % (base, n)
        n += 1
    return eid


def norm_folder(root, folder) -> str:
    """A folder as a repo-relative posix path, with `..` and `.` resolved. "" for the repo root.
    Raises for a path that resolves outside the repo, which `..` once reached."""
    root_r = Path(root).resolve()
    raw = str(folder).replace("\\", "/").strip()
    p = Path(raw)
    full = (p if p.is_absolute() else root_r / raw).resolve()
    try:
        rel = full.relative_to(root_r).as_posix()
    except ValueError:
        raise ValueError("%s is outside the repo" % folder)
    return "" if rel == "." else rel


def check_work_folder(root, rel: str) -> None:
    if not rel:
        return                  # the repo root may keep a project's records too (the user, 2026-09-14)
    if not (Path(root) / rel).is_dir():
        raise ValueError("no such folder: %s" % rel)
    top = Path(rel).parts[0]
    if top.lower() in {r.lower() for r in NO_HISTORY_ROOTS}:
        raise ValueError("%s/ keeps no HISTORY.jsonl. Log the work in the folder whose agenda it served" % top)


def history_file_for(root, rel: str) -> Path:
    """The HISTORY.jsonl a folder's work is logged in: its own, or the nearest ancestor's.

    A PROJECT folder keeps one history for everything under it (tools/indexer, not
    tools/indexer/parsers). So work in a subfolder goes to the first folder above it, up to but not
    including the repo root, that already keeps a HISTORY.jsonl. A folder with no such ancestor starts its
    own, which is how a new project gets its first file.
    """
    root = Path(root)
    parts = Path(rel.strip("/")).parts
    for n in range(len(parts), 0, -1):
        candidate = root.joinpath(*parts[:n]) / upkeep.HISTORY_NAME
        if candidate.is_file():
            return candidate
    if (root / upkeep.HISTORY_NAME).is_file():
        return root / upkeep.HISTORY_NAME       # the repo root's project is the last stop up the path
    return root.joinpath(*parts) / upkeep.HISTORY_NAME


def effective_folder(e: dict) -> str:
    """The folder an entry is about: its `folder` key when it was logged from a subfolder, else its file's."""
    return str(e.get("folder") or Path(e["_file"]).parent.as_posix() + "/").strip("/")


def append_line(path: Path, record: dict) -> None:
    """One line at the end, matching the file's own line endings, never rewriting what is there."""
    path.parent.mkdir(parents=True, exist_ok=True)
    nl, prefix = "\n", ""
    if path.is_file():
        raw = path.read_bytes()
        if b"\r\n" in raw:
            nl = "\r\n"
        if raw and not raw.endswith(b"\n"):
            prefix = nl
    clean = {k: v for k, v in record.items() if not k.startswith("_")}
    line = json.dumps(clean, ensure_ascii=False, allow_nan=False)      # NaN is not JSON; a browser refuses it
    with open(path, "a", encoding="utf-8", newline="") as f:
        f.write(prefix + line + nl)


def find_line(path: Path, entry_id: str):
    """(index, lines, newline, entry) for the ONE line whose id is entry_id. Raises otherwise."""
    raw = path.read_bytes() if path.is_file() else b""
    lines = raw.splitlines(keepends=True)        # each line keeps its own ending, so mixed CRLF/LF files work
    nl = None
    hits = []
    for i, line in enumerate(lines):
        if not line.strip():
            continue
        try:
            e = json.loads(line.rstrip(b"\r\n").decode("utf-8"))
        except ValueError:
            continue
        if isinstance(e, dict) and e.get("id") == entry_id:
            hits.append((i, e))
    if len(hits) != 1:
        raise ValueError("%s holds %d entries with id %s, not one" % (path, len(hits), entry_id))
    return hits[0][0], lines, nl, hits[0][1]


def set_keys(path: Path, entry_id: str, changes: dict) -> dict:
    """Change keys on one entry, leaving every other byte of the file as it was."""
    i, lines, _, e = find_line(path, entry_id)
    e.update(changes)
    ending = lines[i][len(lines[i].rstrip(b"\r\n")):]
    lines[i] = json.dumps(e, ensure_ascii=False, allow_nan=False).encode("utf-8") + ending
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(b"".join(lines))
    os.replace(tmp, path)
    return e


# --------------------------------------------------------------------------------------------------
# reading
# --------------------------------------------------------------------------------------------------

def entries(root, folder: str = None) -> list:
    """Every entry under `folder` (the folder and its subfolders), or the whole repo, oldest first."""
    events, _ = upkeep.read_history(Path(root))
    if folder and folder.strip("/") not in ("", "."):       # the root's project sees every entry below it
        f = folder.strip("/")
        events = [e for e in events if effective_folder(e) == f or effective_folder(e).startswith(f + "/")]
    return sorted(events, key=lambda e: (str(e.get("ts", "")), str(e.get("time", "")), e["_file"], e["_line"]))


def select(events, kinds=(), since=None, grep=None, status=None) -> list:
    out = []
    for e in events:
        if kinds and e.get("kind") not in kinds:
            continue
        if since and str(e.get("ts", "")) < since:
            continue
        if status and str(e.get("status", "")) != status:
            continue
        if grep:
            body = json.dumps({k: v for k, v in e.items() if not k.startswith("_")}, ensure_ascii=False)
            if grep.lower() not in body.lower():
                continue
        out.append(e)
    return out


def one_line(e: dict, show_folder: bool) -> str:
    decided = e.get("decided") if isinstance(e.get("decided"), dict) else {}
    refs = list(e.get("refs") or []) + ([decided["rule"]] if decided.get("rule") else [])
    tail = ""
    if e.get("status"):
        tail += "  [%s]" % e["status"]
    if refs:
        tail += "  -> %s" % ", ".join(str(r) for r in refs[:3])
    where = "%s/  " % effective_folder(e) if show_folder else ""
    return "%s  %-9s %s%s  %s%s" % (e.get("ts", "?"), e.get("kind", "?"), where, e.get("id", "?"),
                                    str(e.get("title", ""))[:90], tail)


def tasks_summary(root, rel: str) -> str:
    p = Path(root) / rel / TASKS_NAME
    if not p.is_file():
        return "no TASKS.md"
    rows = [l.strip() for l in p.read_text(encoding="utf-8", errors="replace").splitlines()]
    # The format is still being iterated with the user (PLAN.md section 7, item 14), so both drafts
    # are read: the checkbox form `- [ ] NOW ...` and the icon form `- 🔄 ...` / `- ⬜ ...`.
    now = next((l for l in rows if l.startswith("- [ ] NOW") or l.startswith("- \U0001F504")), None)
    nxt = sum(1 for l in rows if (l.startswith("- [ ]") and not l.startswith("- [ ] NOW"))
              or l.startswith("- ⬜") or l.startswith("- 🔜"))
    if now:
        head = now[len("- [ ] "):] if now.startswith("- [ ]") else "NOW " + now[len("- \U0001F504"):].strip()
        head = head.replace("**", "")
    else:
        head = "no NOW task"
    return head + ("  (+%d next)" % nxt if nxt else "")


def folder_state(root, rel: str) -> str:
    rel = rel.strip("/") or "."
    own = [e for e in entries(root, rel) if Path(e["_file"]).parent.as_posix() == rel or effective_folder(e) == rel]
    lines = ["FOLDER %s/" % rel, "  tasks       %s" % tasks_summary(root, rel)]
    if own:
        last = own[-1]
        lines.append("  history     %d entries, latest %s %s: %s"
                     % (len(own), last.get("ts"), last.get("kind"), str(last.get("title", ""))[:70]))
    else:
        lines.append("  history     no entries yet")
    try:
        import questions
        asked = questions.summary(root, rel)
    except Exception:                                   # noqa: BLE001 - the state line must never break a command
        asked = ""
    if asked:
        lines.append("  questions   " + asked)
    pending = [e for e in own if e.get("kind") == "candidate" and e.get("status", "pending") == "pending"]
    if pending:
        lines.append("  candidates  %d pending here. Work through them: rules.py candidates next" % len(pending))
    return "\n".join(lines)


def render_slice(root, folder=None, kinds=(), first=None, last=None, everything=False,
                 since=None, grep=None, status=None) -> str:
    root = Path(root)
    rel = None
    if folder:
        rel = norm_folder(root, folder)
        if not (root / rel).is_dir():
            raise ValueError("no such folder: %s" % rel)
    found = select(entries(root, rel), kinds, since, grep, status)
    if everything:
        shown, which = found, "all"
    elif first:
        shown, which = found[:first], "first %d" % first
    else:
        n = last or DEFAULT_SLICE
        shown, which = found[-n:], "last %d" % n
    folders = {effective_folder(e) for e in shown}
    what = "/".join(kinds) if kinds else "all kinds"
    out = []
    if rel:
        out += [folder_state(root, rel), ""]
    out.append("%s: %s of %d %s entries" % ((rel + "/") if rel else "whole repo", which, len(found), what))
    out += ["  " + one_line(e, show_folder=len(folders) > 1 or not rel) for e in shown]
    if not shown:
        out.append("  none")
    return "\n".join(out)


def show(root, entry_id: str) -> str:
    hits = [e for e in entries(root) if e.get("id") == entry_id]
    if not hits:
        raise ValueError("no history entry with id %s" % entry_id)
    return "\n\n".join("%s:%d\n%s" % (e["_file"], e["_line"], json.dumps(
        {k: v for k, v in e.items() if not k.startswith("_")}, indent=2, ensure_ascii=False)) for e in hits)


# --------------------------------------------------------------------------------------------------
# writing
# --------------------------------------------------------------------------------------------------

def _number(v: str):
    for cast in (int, float):
        try:
            n = cast(v)
        except ValueError:
            continue
        if isinstance(n, float) and not math.isfinite(n):
            raise ValueError("%s is not a finite number" % v)
        return n
    return v


def add(root, folder, kind, title, what="", result="", evidence=(), refs=(), no_rule="", numbers=(),
        tags=(), status="", supersedes="", when=None, extra=None) -> dict:
    """Append one stamped entry to <folder>/HISTORY.jsonl, creating the file. Raises ValueError, writing
    nothing, when the entry would break the conventions in rules/writing/history-log."""
    root = Path(root)
    rel = norm_folder(root, folder)
    check_work_folder(root, rel)
    if kind == "candidate":
        raise ValueError("a rule candidate is parked, so it is checked against every rule first: rules.py park")
    if kind not in ADD_KINDS:
        raise ValueError("kind %r is not one of %s" % (kind, ", ".join(ADD_KINDS)))
    title = " ".join(str(title).split())
    if len(title) < 8:
        raise ValueError("a title says what happened, in a few words")
    if status and status not in STATUSES:
        raise ValueError("status %r is not one of %s" % (status, ", ".join(STATUSES)))
    evidence = [str(e).replace("\\", "/").rstrip("/") for e in evidence]
    for e in evidence:
        if not (root / e).exists():
            raise ValueError("evidence path does not exist: %s" % e)
    events, _ = upkeep.read_history(root)
    ids = {e.get("id") for e in events}
    refs = [str(r) for r in refs]
    for r in refs:
        if "/" in r:
            s = r[:-len(SUFFIX)] if r.endswith(SUFFIX) else r
            if not (root / "rules" / (s + SUFFIX)).is_file():
                raise ValueError("--refs names %s, which is no rule" % r)
        elif r not in ids:
            raise ValueError("--refs names %s, which is neither a rule nor an entry id" % r)
    if kind == "run":
        if not any(RUN_DIR.match(e) and (root / e).is_dir() for e in evidence):
            raise ValueError("a run entry names its run folder: --evidence test_runs/<scenario>/runs/<stamp>")
        if not refs and not str(no_rule).strip():
            raise ValueError("a run entry closes with --refs <rule or candidate id>, or --no-rule WHY no rule "
                             "changed")
    if supersedes and supersedes not in ids:
        raise ValueError("--supersedes names %s, which is no entry" % supersedes)

    s = stamp(when)
    rec = {"id": unique_id(ids, "%s-%s" % (s["ts"], slug(title))), "ts": s["ts"], "kind": kind, "title": title}
    if what:
        rec["what"] = " ".join(str(what).split())
    if result:
        rec["result"] = " ".join(str(result).split())
    if numbers:
        rec["numbers"] = {k: _number(v) for k, _, v in (str(n).partition("=") for n in numbers)}
    if evidence:
        rec["evidence"] = evidence
    if refs:
        rec["refs"] = [r[:-len(SUFFIX)] if r.endswith(SUFFIX) else r for r in refs]
    if str(no_rule).strip():
        rec["no_rule"] = " ".join(str(no_rule).split())
    if tags:
        rec["tags"] = list(tags)
    if supersedes:
        rec["supersedes"] = supersedes
    if status:
        rec["status"] = status
    for key, value in (extra or {}).items():
        rec.setdefault(key, value)
    rec["time"], rec["session"] = s["time"], s["session"]
    path = history_file_for(root, rel)
    if path.parent != root / rel:
        rec["folder"] = rel + "/"
    append_line(path, rec)
    return {"entry": dict(rec, _file=path.relative_to(root).as_posix()), "path": path, "folder": rel}


def merge(root, project: str, write: bool = True, when=None) -> dict:
    """Fold every HISTORY.jsonl below `project` into the project's own, each entry keeping its subfolder.

    Nothing is lost: every line is copied whole with a `folder` key added, in date order, the count is
    checked, and only then are the originals MOVED into .claude/_backup/history-merge-<date>/ at their old
    paths. The merge logs itself as a `change` entry in the project's history. Refuses, writing nothing, if
    any source has a line that does not parse or an id already in the project's file.
    """
    import shutil

    root = Path(root)
    rel = norm_folder(root, project)
    check_work_folder(root, rel)
    target = root / rel / upkeep.HISTORY_NAME
    def in_subproject(p):
        """True when p sits in or under a sub-project: its history is that project's, never folded into this one."""
        d = p.parent
        while d != root / rel:
            if (d / "TASKS.md").is_file() or (d / "QUESTIONS.jsonl").is_file():
                return True
            d = d.parent
        return False

    sources = sorted(p for p in (root / rel).rglob(upkeep.HISTORY_NAME)
                     if p != target and "_backup" not in p.parts and not in_subproject(p))
    if not sources:
        raise ValueError("%s/ has no subfolder histories to merge" % rel)

    existing_ids = set()
    if target.is_file():
        for n, line in enumerate(target.read_text(encoding="utf-8").splitlines(), start=1):
            if line.strip():
                try:
                    existing_ids.add(json.loads(line).get("id"))
                except ValueError:
                    raise ValueError("%s:%d is not valid JSON; fix it before merging" % (target.relative_to(root).as_posix(), n))
    seen = {}
    rows = []
    for order, src in enumerate(sources):
        sub = src.parent.relative_to(root).as_posix()
        for n, line in enumerate(src.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                e = json.loads(line)
            except ValueError:
                raise ValueError("%s:%d is not valid JSON; fix it before merging" % (src.relative_to(root).as_posix(), n))
            if e.get("id") in existing_ids:
                raise ValueError("%s is already in %s" % (e.get("id"), target.relative_to(root).as_posix()))
            here = src.relative_to(root).as_posix()
            if e.get("id") in seen:
                raise ValueError("%s appears in both %s and %s; ids must be unique before merging"
                                 % (e.get("id"), seen[e.get("id")], here))
            seen[e.get("id")] = here
            e.setdefault("folder", sub + "/")
            rows.append((str(e.get("ts", "")), str(e.get("time", "")), order, n, e))
    rows.sort(key=lambda r: r[:4])
    summary = {"project": rel, "target": target, "sources": [s.relative_to(root).as_posix() for s in sources],
               "entries": len(rows), "backup": None}
    if not write:
        return summary

    before = 0
    if target.is_file():
        before = sum(1 for line in target.read_text(encoding="utf-8").splitlines() if line.strip())
    for *_, e in rows:
        append_line(target, e)
    after = sum(1 for line in target.read_text(encoding="utf-8").splitlines() if line.strip())
    if after != before + len(rows):
        raise ValueError("merge wrote %d lines, expected %d; the sources were left in place" % (after - before, len(rows)))

    stamp_ = stamp(when)
    backup = root / ".claude" / "_backup" / ("history-merge-%s" % stamp_["ts"])
    for src in sources:
        dst = backup / src.relative_to(root)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
    summary["backup"] = backup
    add(root, rel, "change", "merged %d subfolder histories into this project's HISTORY.jsonl" % len(sources),
        what="%d entries from %s, each keeping its subfolder in folder; originals moved to %s"
             % (len(rows), ", ".join(summary["sources"]), backup.relative_to(root).as_posix()), when=when)
    return summary
