#!/usr/bin/env python3
"""QUESTIONS.jsonl: a project's open questions for the user, one per line, each tied to a task.

    {"id": "q3", "ts": ..., "time": ..., "session": ..., "task": "t8", "question": "..."}
    ... once the user answers:  "answer": "...", "answered": "<time>"

The loop (knowledge_upkeep PLAN item 38):
    rules.py tasks ask <task> "<question>"   an instance asks; the task line shows ❓ while it is unanswered
    rules.py tasks answer <q> "<answer>"     the user's answer is written in (later also by the viewer)
    rules.py tasks answers                   an instance reads the answers. Reading consumes them: each one is
                                             logged as a `decision` entry in the project's history, THEN
                                             removed from the file.

So the file holds only questions not yet read back, and the history keeps every decision for good. A
consume that stopped between the two writes is safe to repeat: an answer already in history (matched by its
`question` key) is not logged twice, only removed.

The ❓ on a task line is derived from this file by tasks.load, never set by hand.
"""

from __future__ import annotations

import datetime
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

QUESTIONS_NAME = "QUESTIONS.jsonl"
MIN_TEXT, MAX_QUESTION, MAX_ANSWER = 8, 400, 1000


def path(root, project) -> Path:
    return Path(root) / project / QUESTIONS_NAME


def read(root, project) -> list:
    """Every question in the file, oldest first. Lines that are not question objects are skipped."""
    p = path(root, project)
    out = []
    if not p.is_file():
        return out
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            q = json.loads(line)
        except ValueError:
            continue
        if isinstance(q, dict) and q.get("id") and q.get("question"):
            out.append(q)
    return out


def open_tasks(root, project) -> set:
    """Task ids with a question the user has not answered yet."""
    return {q.get("task") for q in read(root, project) if not q.get("answer")}


def _text(text, what, most):
    text = " ".join(str(text).split())
    if len(text) < MIN_TEXT:
        raise ValueError("%s needs a full sentence" % what)
    if len(text) > most:
        raise ValueError("%s is at most %d characters" % (what, most))
    return text


def next_qid(root, project) -> str:
    """One more than any question id this project has used, in the file or in its history."""
    import history
    used = [q["id"] for q in read(root, project)]
    used += [str(e.get("question", "")) for e in history.entries(root, project)]
    nums = [int(m.group(1)) for m in (re.match(r"^q(\d+)$", u) for u in used) if m]
    return "q%d" % (max(nums) + 1 if nums else 1)


def ask(root, project, task_id, text) -> dict:
    import history
    import tasks
    p = tasks.load(root, project)
    k = tasks._find(p, task_id)
    if k["status"] == "done":
        raise ValueError("%s is done; a question belongs to a task still open" % task_id)
    record = {"id": next_qid(root, project)}
    record.update(history.stamp())
    record.update({"task": task_id, "question": _text(text, "a question", MAX_QUESTION)})
    history.append_line(path(root, project), record)
    tasks.sync(root, project)
    return record


def _find(root, project, qid) -> dict:
    for q in read(root, project):
        if q["id"] == qid:
            return q
    raise ValueError("no open question %s in %s/. See them: rules.py tasks questions" % (qid, project))


def answer(root, project, qid, text) -> dict:
    import history
    import tasks
    q = _find(root, project, qid)
    if q.get("answer"):
        raise ValueError("%s is already answered; read it with rules.py tasks answers" % qid)
    q = history.set_keys(path(root, project), qid, {
        "answer": _text(text, "an answer", MAX_ANSWER),
        "answered": datetime.datetime.now().isoformat(timespec="seconds")})
    tasks.sync(root, project)
    return q


def _remove(root, project, qid) -> None:
    i, lines, _, _ = __import__("history").find_line(path(root, project), qid)
    del lines[i]
    p = path(root, project)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_bytes(b"".join(lines))
    os.replace(tmp, p)


def consume(root, project) -> list:
    """Every answered question: logged in history as a decision, then removed from the file."""
    import history
    import tasks
    done = []
    answered = [q for q in read(root, project) if q.get("answer")]
    if not answered:
        return done
    logged = {str(e.get("question")): e for e in history.entries(root, project) if e.get("question")}
    try:
        window = {k["id"]: k["text"] for k in tasks.load(root, project)["tasks"]}
    except ValueError:
        window = {}
    for q in answered:
        entry = logged.get(q["id"])
        if entry is None:
            title = "answered %s: %s" % (q["id"], q["question"])
            entry = history.add(root, project, "decision", title[:140],
                                what="Question (%s): %s Answer (%s): %s" % (q.get("time", q.get("ts", "")),
                                                                            q["question"], q["answered"], q["answer"]),
                                extra={"task": q.get("task", ""), "question": q["id"]})["entry"]
        _remove(root, project, q["id"])
        done.append({"question": q, "entry": entry, "task_text": window.get(q.get("task"), "")})
    tasks.sync(root, project)
    return done


def withdraw(root, project, qid, reason) -> dict:
    """Take back a question the user has not answered, e.g. one whose premise turned out false. Logged as a note
    first, then removed, so the history says what was asked and why it was withdrawn."""
    import history
    import tasks
    q = _find(root, project, qid)
    if q.get("answer"):
        raise ValueError("%s is already answered; read it with rules.py tasks answers" % qid)
    reason = _text(reason, "a reason (--reason)", MAX_ANSWER)
    entry = history.add(root, project, "note", ("withdrew %s: %s" % (qid, q["question"]))[:140],
                        what="Question: %s Withdrawn because: %s" % (q["question"], reason),
                        extra={"task": q.get("task", ""), "question": qid})["entry"]
    _remove(root, project, qid)
    tasks.sync(root, project)
    return {"question": q, "entry": entry}


def wait(root, project, timeout=43200.0, interval=2.0) -> list:
    """Block until the user has answered at least one question, or the timeout passes. An instance runs this in
    the background after asking through the viewer: the command exiting is what tells the instance an answer came."""
    import time
    end = time.time() + timeout
    while True:
        got = [q for q in read(root, project) if q.get("answer")]
        if got or time.time() >= end:
            return got
        time.sleep(min(interval, max(0.05, end - time.time())))


def summary(root, project) -> str:
    """One line for the folder state, or "" when the project has no questions."""
    qs = read(root, project)
    waiting = sum(1 for q in qs if q.get("answer"))
    open_ = len(qs) - waiting
    if not qs:
        return ""
    parts = []
    if open_:
        parts.append("%d open for the user" % open_)
    if waiting:
        parts.append("%d answered, waiting to be read: rules.py tasks answers" % waiting)
    return ", ".join(parts)


def show(root, project) -> str:
    qs = read(root, project)
    out = ["QUESTIONS %s/" % project]
    for q in qs:
        out.append("  %s  %s  %s" % (q["id"], q.get("task", ""), q["question"]))
        if q.get("answer"):
            out.append("        answered %s: %s" % (q["answered"], q["answer"]))
    if not qs:
        out.append("  none open")
    return "\n".join(out)
