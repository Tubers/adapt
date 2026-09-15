#!/usr/bin/env python3
"""PostToolUse hook on Read: record WHICH returned hit an instance actually opened.

THE SIGNAL THIS BUYS
--------------------
A search returns five hits. Which one gets opened is the only evidence available about whether the
ranking and the gists are any good:

  opened rank 1, often          the gist and the ranking agree with reality
  opened rank 4 or 5, often     the corpus holds the right answer and the ranking buries it
  nothing opened, ever          the top hit oversells its rule, or the question was idle curiosity

None of that can be known at query time, which is why it is a SEPARATE LINE appended later rather
than a field on the answer. An absent field would read as a negative signal; an absent line reads as
what it is, nobody opened anything.

WHY A WINDOW
------------
A rule read three weeks after a question was logged has nothing to do with that question. Attribution
is limited to MAX_AGE_S and to the most recent answers, so a coincidence cannot masquerade as a
signal. The window is generous enough for a session and short enough to stay honest.

Fails OPEN and silent, appends nothing twice, and never blocks a Read.
"""

import json
import os
import pathlib
import sys
import time

LOG_NAME = "QUERIES.jsonl"
MAX_AGE_S = 6 * 3600          # an answer older than this is not credited with a later read
RECENT_ANSWERS = 20           # and only the newest few are considered at all


def _parse(path: pathlib.Path):
    """(answers newest-first, set of (query id, doc) already recorded as opened)."""
    answers, opened = [], set()
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return [], opened
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
        except ValueError:
            continue
        kind = d.get("kind")
        if kind == "answer":
            answers.append(d)
        elif kind == "opened":
            opened.add((d.get("for"), d.get("doc")))
    return list(reversed(answers))[:RECENT_ANSWERS], opened


def _age_ok(answer, now) -> bool:
    ts = answer.get("ts", "")
    try:
        t = time.mktime(time.strptime(ts, "%Y-%m-%dT%H:%M:%S"))
    except (ValueError, TypeError):
        return False
    return 0 <= now - t <= MAX_AGE_S


def _matches(doc: str, read_rel: str) -> bool:
    """Does the file just read correspond to this hit?

    A rules hit is named relative to rules/, e.g. writing/tasks.rule.md, while the Read
    carries rules/writing/tasks.rule.md. A results hit is already a repo-relative path.
    A history hit is an event id and is not a file, so it never matches.
    """
    if not doc:
        return False
    doc = doc.replace("\\", "/")
    return read_rel.endswith(doc) or read_rel.endswith("rules/" + doc)


def record(cwd: str, read_path: str):
    """Append one `opened` line to whichever log has a recent answer naming this file."""
    root = pathlib.Path(cwd)
    try:
        read_rel = pathlib.Path(read_path).resolve().relative_to(root.resolve()).as_posix()
    except (ValueError, OSError):
        read_rel = pathlib.Path(read_path).as_posix()
    read_rel = read_rel.replace("\\", "/")
    now = time.time()

    for log in sorted(root.rglob(LOG_NAME), key=lambda p: -p.stat().st_mtime):
        if "_backup" in log.parts:
            continue
        answers, already = _parse(log)
        for a in answers:
            if not _age_ok(a, now):
                continue
            for rank, hit in enumerate(a.get("hits", []), start=1):
                doc = hit.get("doc", "")
                if not _matches(doc, read_rel):
                    continue
                if (a.get("for"), doc) in already:
                    return None                    # already recorded, say nothing
                rec = {"kind": "opened", "for": a.get("for"), "doc": doc, "rank": rank,
                       "score": hit.get("score"), "ns": a.get("ns", "rules"),
                       "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
                       "after_s": int(now - time.mktime(
                           time.strptime(a.get("ts"), "%Y-%m-%dT%H:%M:%S")))}
                with open(log, "a", encoding="utf-8") as f:
                    f.write(json.dumps(rec, sort_keys=True) + "\n")
                return rec, log
    return None


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    if payload.get("tool_name") != "Read":
        return 0
    path = str((payload.get("tool_input") or {}).get("file_path", ""))
    if not path:
        return 0
    cwd = payload.get("cwd") or os.getcwd()
    try:
        record(cwd, path)
    except Exception:
        return 0
    return 0                  # silent by design: this is measurement, not advice


if __name__ == "__main__":
    sys.exit(main())
