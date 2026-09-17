#!/usr/bin/env python3
"""QUESTIONS.jsonl: what a project waits on the user for, one item per line, each tied to a task.

Two kinds share the file, because both are the user's turn and both are read back the same way:

    a question  {"id": "q3", "ts": ..., "time": ..., "session": ..., "task": "t8", "question": "..."}
                ... once the user answers:  "answer": "...", "answered": "<time>"
    an action   {"id": "a2", "kind": "action", "ts": ..., "time": ..., "session": ..., "task": "t5", "action": "..."}
                ... once the user has done it:  "done": "<time>", and an optional "note": "..."

A question asks the user to decide; an action asks the user to DO something only they can do: log in, accept a
dialog, install a program, press a button in another app (the user, 2026-09-15).

The loop (knowledge_upkeep PLAN item 38; actions added 2026-09-15):
    rules.py tasks ask <task> "<question>"   an instance asks; the task line shows ❓ while it is unanswered
    rules.py tasks act <task> "<action>"     an instance asks the user to do something; the task line shows ❗
    rules.py tasks answer <q> "<answer>"     the user's answer is written in, by the viewer or from chat
    rules.py tasks acted <a> ["<note>"]      the user marks the action done, by the viewer or from chat
    rules.py tasks answers                   an instance reads the replies. Reading consumes them: each answer is
                                             logged as a `decision` entry, each done action as a `note` entry, in
                                             the project's history, THEN removed from the file.

So the file holds only items not yet read back, and the history keeps every reply for good. A consume that
stopped between the two writes is safe to repeat: a reply already in history (matched by its `question` or
`action` key) is not logged twice, only removed.

The ❓ and ❗ on a task line are derived from this file by tasks.load, never set by hand.
"""

from __future__ import annotations

import datetime
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import records  # noqa: E402

QUESTIONS_NAME = records.QUESTIONS
MIN_TEXT, MAX_QUESTION, MAX_ANSWER = 8, 1200, 10000
ACTION = "action"


def path(root, project) -> Path:
    return records.path(Path(root) / project, QUESTIONS_NAME)


def is_action(q) -> bool:
    return q.get("kind") == ACTION


def replied(q) -> bool:
    """The user's turn is over: a question answered, or an action done."""
    return bool(q.get("done") if is_action(q) else q.get("answer"))


def read(root, project) -> list:
    """Every question and action in the file, oldest first. Lines that are neither are skipped."""
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
        if isinstance(q, dict) and q.get("id") and (q.get(ACTION) if is_action(q) else q.get("question")):
            out.append(q)
    return out


def open_tasks(root, project) -> set:
    """Task ids with a question the user has not answered yet."""
    return {q.get("task") for q in read(root, project) if not is_action(q) and not q.get("answer")}


def open_actions(root, project) -> set:
    """Task ids with an action the user has not done yet."""
    return {q.get("task") for q in read(root, project) if is_action(q) and not q.get("done")}


def _text(text, what, most):
    text = " ".join(str(text).split())
    if len(text) < MIN_TEXT:
        raise ValueError("%s needs a full sentence" % what)
    if len(text) > most:
        raise ValueError("%s is at most %d characters" % (what, most))
    return text


def _next_id(root, project, prefix, key) -> str:
    """One more than any id of this kind the project has used, in the file or in its history."""
    import history
    used = [q["id"] for q in read(root, project)]
    used += [str(e.get(key, "")) for e in history.entries(root, project)]
    nums = [int(m.group(1)) for m in (re.match(r"^%s(\d+)$" % prefix, u) for u in used) if m]
    return "%s%d" % (prefix, max(nums) + 1 if nums else 1)


def next_qid(root, project) -> str:
    return _next_id(root, project, "q", "question")


def next_aid(root, project) -> str:
    return _next_id(root, project, "a", ACTION)


def _open_task(root, project, task_id, what):
    import tasks
    k = tasks._find(tasks.load(root, project), task_id)
    if k["status"] == "done":
        raise ValueError("%s is done; %s belongs to a task still open" % (task_id, what))
    return k


def ask(root, project, task_id, text) -> dict:
    import history
    import tasks
    _open_task(root, project, task_id, "a question")
    record = {"id": next_qid(root, project)}
    record.update(history.stamp())
    record.update({"task": task_id, "question": _text(text, "a question", MAX_QUESTION)})
    history.append_line(path(root, project), record)
    tasks.sync(root, project)
    return record


def act(root, project, task_id, text) -> dict:
    """Ask the user to do something only they can do. The task line shows ❗ until they mark it done."""
    import history
    import tasks
    _open_task(root, project, task_id, "an action")
    record = {"id": next_aid(root, project), "kind": ACTION}
    record.update(history.stamp())
    record.update({"task": task_id, ACTION: _text(text, "an action", MAX_QUESTION)})
    history.append_line(path(root, project), record)
    tasks.sync(root, project)
    return record


def _find(root, project, qid) -> dict:
    for q in read(root, project):
        if q["id"] == qid:
            return q
    raise ValueError("no open question or action %s in %s/. See them: rules.py tasks questions" % (qid, project))


def answer(root, project, qid, text) -> dict:
    import history
    import tasks
    q = _find(root, project, qid)
    if is_action(q):
        raise ValueError("%s is an action, not a question; mark it done with: rules.py tasks acted %s" % (qid, qid))
    if q.get("answer"):
        raise ValueError("%s is already answered; read it with rules.py tasks answers" % qid)
    q = history.set_keys(path(root, project), qid, {
        "answer": _text(text, "an answer", MAX_ANSWER),
        "answered": datetime.datetime.now().isoformat(timespec="seconds")})
    tasks.sync(root, project)
    return q


def acted(root, project, aid, note="") -> dict:
    """The user has done the action. A note is optional: what they did differently, or what came of it."""
    import history
    import tasks
    a = _find(root, project, aid)
    if not is_action(a):
        raise ValueError("%s is a question, not an action; answer it with: rules.py tasks answer %s \"<answer>\"" % (aid, aid))
    if a.get("done"):
        raise ValueError("%s is already done; read it with rules.py tasks answers" % aid)
    changes = {"done": datetime.datetime.now().isoformat(timespec="seconds")}
    note = " ".join(str(note or "").split())
    if note:
        if len(note) > MAX_ANSWER:
            raise ValueError("a note is at most %d characters" % MAX_ANSWER)
        changes["note"] = note
    a = history.set_keys(path(root, project), aid, changes)
    tasks.sync(root, project)
    return a


def _remove(root, project, qid) -> None:
    i, lines, _, _ = __import__("history").find_line(path(root, project), qid)
    del lines[i]
    p = path(root, project)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_bytes(b"".join(lines))
    os.replace(tmp, p)


def consume(root, project) -> list:
    """Every reply: an answered question logged as a decision, a done action as a note, then removed from the file.
    Each item returned carries the record under "question" or "action", its history entry and its task's text."""
    import history
    import tasks
    done = []
    ready = [q for q in read(root, project) if replied(q)]
    if not ready:
        return done
    entries = history.entries(root, project)
    logged = {("q", str(e["question"])): e for e in entries if e.get("question")}
    logged.update({("a", str(e[ACTION])): e for e in entries if e.get(ACTION)})
    try:
        window = {k["id"]: k["text"] for k in tasks.load(root, project)["tasks"]}
    except ValueError:
        window = {}
    for q in ready:
        if is_action(q):
            entry = logged.get(("a", q["id"]))
            if entry is None:
                entry = history.add(root, project, "note", ("user did %s: %s" % (q["id"], q[ACTION]))[:140],
                                    what="Action (%s): %s Done (%s)%s" % (
                                        q.get("time", q.get("ts", "")), q[ACTION], q["done"],
                                        (": " + q["note"]) if q.get("note") else "."),
                                    extra={"task": q.get("task", ""), ACTION: q["id"]})["entry"]
            item = {ACTION: q}
        else:
            entry = logged.get(("q", q["id"]))
            if entry is None:
                title = "answered %s: %s" % (q["id"], q["question"])
                entry = history.add(root, project, "decision", title[:140],
                                    what="Question (%s): %s Answer (%s): %s" % (q.get("time", q.get("ts", "")),
                                                                                q["question"], q["answered"], q["answer"]),
                                    extra={"task": q.get("task", ""), "question": q["id"]})["entry"]
            item = {"question": q}
        _remove(root, project, q["id"])
        item.update({"entry": entry, "task_text": window.get(q.get("task"), "")})
        done.append(item)
    tasks.sync(root, project)
    return done


def withdraw(root, project, qid, reason) -> dict:
    """Take back a question the user has not answered, or an action not yet done, e.g. one whose premise turned
    out false. Logged as a note first, then removed, so the history says what was asked and why it was withdrawn."""
    import history
    import tasks
    q = _find(root, project, qid)
    action = is_action(q)
    if replied(q):
        raise ValueError("%s is already %s; read it with rules.py tasks answers" % (qid, "done" if action else "answered"))
    reason = _text(reason, "a reason (--reason)", MAX_ANSWER)
    text = q[ACTION] if action else q["question"]
    entry = history.add(root, project, "note", ("withdrew %s: %s" % (qid, text))[:140],
                        what="%s: %s Withdrawn because: %s" % ("Action" if action else "Question", text, reason),
                        extra={"task": q.get("task", ""), (ACTION if action else "question"): qid})["entry"]
    _remove(root, project, qid)
    tasks.sync(root, project)
    return {("action" if action else "question"): q, "item": q, "entry": entry}


def wait(root, project, timeout=43200.0, interval=2.0) -> list:
    """Block until the user has answered a question or done an action, or the timeout passes. An instance runs this
    in the background after asking through the viewer: the command exiting is what tells the instance a reply came."""
    import time
    end = time.time() + timeout
    while True:
        got = [q for q in read(root, project) if replied(q)]
        if got or time.time() >= end:
            return got
        time.sleep(min(interval, max(0.05, end - time.time())))


def summary(root, project) -> str:
    """One line for the folder state, or "" when the project waits on the user for nothing."""
    qs = read(root, project)
    if not qs:
        return ""
    asks = [q for q in qs if not is_action(q)]
    acts = [q for q in qs if is_action(q)]
    parts = []
    if any(not replied(q) for q in asks):
        parts.append("%d open for the user" % sum(1 for q in asks if not replied(q)))
    if any(not replied(q) for q in acts):
        n = sum(1 for q in acts if not replied(q))
        parts.append("%d action%s for the user" % (n, "" if n == 1 else "s"))
    waiting = sum(1 for q in qs if replied(q))
    if waiting:
        parts.append("%d answered, waiting to be read: rules.py tasks answers" % waiting)
    return ", ".join(parts)


def show(root, project) -> str:
    qs = read(root, project)
    out = ["QUESTIONS %s/" % project]
    for q in qs:
        if is_action(q):
            out.append("  %s  %s  ❗ %s" % (q["id"], q.get("task", ""), q[ACTION]))
            if q.get("done"):
                out.append("        done %s%s" % (q["done"], (": " + q["note"]) if q.get("note") else ""))
        else:
            out.append("  %s  %s  %s" % (q["id"], q.get("task", ""), q["question"]))
            if q.get("answer"):
                out.append("        answered %s: %s" % (q["answered"], q["answer"]))
    if not qs:
        out.append("  none open")
    return "\n".join(out)
