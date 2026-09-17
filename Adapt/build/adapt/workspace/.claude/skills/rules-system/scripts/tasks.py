#!/usr/bin/env python3
"""TASKS.md, the frozen format: parsed here, checked here, and (item 16) written here.

The format is owned by rules/writing/tasks and lives in this file as code, so a TASKS.md cannot drift
from the rule without the check saying so:

    # 📋 TASKS · <project>

    **Goal:** <one line>

    - ✅ <done task> · *<date>* `t1`                      at most 2
    - 🔄 ❓ **<the task in progress>** · *since <date>* `t3`  exactly 1; ❓ marks an open question
    - ⛔ ❗ <blocked task> `t4`                           its reason is in its details; ❗ marks an action for the user
    - 🔜 <not started task> `t5`                         any number, no date

❓ and ❗ follow QUESTIONS.jsonl (questions.py) and are never set by hand; a task may carry both, ❓ first.

    ---

    ## Details

    **t3** · One short paragraph per task, every task: what it is for and what done means.

Every task carries its paragraph from `add` until it leaves the window (2026-09-13, the user: the viewer
shows each task's paragraph on click). A done task keeps it; its result is in the history entry keyed by id.
A blocked task's reason goes in front of the paragraph, "Blocked: <why> · <paragraph>", and unblock takes it off.
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

ICONS = {"✅": "done", "🔄": "now", "⛔": "blocked", "🔜": "next"}
ICON_OF = {v: k for k, v in ICONS.items()}
QUESTION = "❓"
ACTION = "❗"                                    # an action only the user can do (the user, 2026-09-15)
MAX_DONE, NOW_COUNT, MAX_NEXT = 2, 1, None     # no cap on not-started tasks (the user, 2026-09-14)

HEAD = re.compile(r"^#\s+(?:📋\s+)?TASKS\s+·\s+(?P<project>\S.*?)\s*$")
GOAL = re.compile(r"^\*\*Goal:\*\*\s*(?P<goal>.*\S)\s*$")
# a sub-project's link to the parent task it serves (the user, 2026-09-14): **Parent:** <project>/ · <task id>
PARENT = re.compile(r"^\*\*Parent:\*\*\s*(?P<project>\S+?)/?\s+·\s+(?P<task>t\d+)\s*$")
LINE = re.compile(r"^-\s+(?P<icon>✅|🔄|⛔|🔜)\s+(?P<q>❓\s+)?(?P<a>❗\s+)?(?P<text>.*?)"
                  r"(?:\s+·\s+\*(?P<date>[^*]+)\*)?(?:\s+`(?P<id>t\d+)`)?\s*$")
DETAIL = re.compile(r"^\*\*(?P<id>t\d+)\*\*\s+·\s+(?P<text>.*\S)\s*$")


def parse(text: str) -> dict:
    """{project, goal, tasks: [{status, question, action, text, bold, date, since, id}], details: {id: text}, problems}"""
    out = {"project": None, "goal": "", "parent": None, "tasks": [], "details": {}, "problems": []}
    in_details, current = False, None
    for raw in text.splitlines():
        s = raw.strip()
        if s == "## Details":
            in_details, current = True, None
            continue
        if not in_details:
            m = HEAD.match(s)
            if m:
                out["project"] = m.group("project")
                continue
            m = GOAL.match(s)
            if m:
                out["goal"] = m.group("goal")
                continue
            m = PARENT.match(s)
            if m:
                out["parent"] = {"project": m.group("project").strip("/") or ".", "task": m.group("task")}
                continue
            m = LINE.match(s)
            if m:
                body = m.group("text").strip()
                bold = body.startswith("**") and body.endswith("**") and len(body) > 4
                date = (m.group("date") or "").strip()
                since = date.startswith("since ")
                out["tasks"].append({"status": ICONS[m.group("icon")], "question": bool(m.group("q")),
                                     "action": bool(m.group("a")), "text": body[2:-2].strip() if bold else body, "bold": bold,
                                     "date": date[len("since "):] if since else date, "since": since,
                                     "id": m.group("id") or ""})
            elif s and s != "---":
                out["problems"].append("not a task line: %s" % s[:80])
            continue
        m = DETAIL.match(s)
        if m:
            current = m.group("id")
            out["details"][current] = m.group("text")
        elif s and current:
            out["details"][current] += " " + s
        elif not s:
            current = None
    out["problems"] += check(out)
    return out


def check(parsed: dict) -> list:
    """What breaks the frozen format. Empty when the file is in shape."""
    tasks = parsed["tasks"]
    count = {k: sum(1 for t in tasks if t["status"] == k) for k in ICON_OF}
    problems = []
    if not parsed["project"]:
        problems.append('no heading "# 📋 TASKS · <project>"')
    if not parsed["goal"]:
        problems.append("no **Goal:** line")
    if count["done"] > MAX_DONE:
        problems.append("%d done tasks in the window, at most %d" % (count["done"], MAX_DONE))
    if tasks and count["now"] != NOW_COUNT:
        problems.append("%d tasks in progress, exactly %d" % (count["now"], NOW_COUNT))
    # uncapped since 2026-09-14 at the user's request: the window lists every task queued for the project
    if MAX_NEXT is not None and count["next"] > MAX_NEXT:
        problems.append("%d not-started tasks, at most %d" % (count["next"], MAX_NEXT))
    ids = [t["id"] for t in tasks if t["id"]]
    if len(ids) != len(tasks):
        problems.append("%d task line(s) without an id" % (len(tasks) - len(ids)))
    if len(set(ids)) != len(ids):
        problems.append("a task id is used twice")
    for t in tasks:
        if t["status"] in ("done", "now") and not t["date"]:
            problems.append("%s task %s has no date" % (t["status"], t["id"] or t["text"][:30]))
        if t["status"] == "next" and t["date"]:
            problems.append("not-started task %s carries a date" % (t["id"] or t["text"][:30]))
        if t["status"] == "blocked" and t["id"] and t["id"] not in parsed["details"]:
            problems.append("blocked task %s has no details saying why" % t["id"])
        elif t["id"] and t["id"] not in parsed["details"]:
            problems.append("task %s has no details paragraph: rules.py tasks detail %s \"<paragraph>\""
                            % (t["id"], t["id"]))
    for tid in parsed["details"]:
        if tid not in ids:
            problems.append("details for %s, which is no task in the window" % tid)
    return problems


# --------------------------------------------------------------------------------------------------
# writing: every change to a TASKS.md goes through these, so the file never leaves the format
# --------------------------------------------------------------------------------------------------

TASKS_NAME = records.TASKS
QUESTIONS_NAME = records.QUESTIONS
RANK = {"done": 0, "now": 1, "blocked": 2, "next": 3}
MAX_DETAIL = 500


def today() -> str:
    return datetime.date.today().isoformat()


def render(p: dict) -> str:
    """The frozen format, from a parsed window. Tasks are ordered done, in progress, blocked, not started."""
    tasks = sorted(p["tasks"], key=lambda k: RANK[k["status"]])
    lines = []
    for k in tasks:
        text = "**%s**" % k["text"] if k["status"] == "now" else k["text"]
        date = ""
        if k["status"] == "done" and k.get("date"):
            date = " · *%s*" % k["date"]
        elif k["status"] == "now" and k.get("date"):
            date = " · *since %s*" % k["date"]
        lines.append("- %s%s%s %s%s `%s`" % (ICON_OF[k["status"]], " " + QUESTION if k.get("question") else "",
                                             " " + ACTION if k.get("action") else "", text, date, k["id"]))
    details = ["**%s** · %s" % (k["id"], p["details"][k["id"]]) for k in tasks if k["id"] in p["details"]]
    out = "# 📋 TASKS · %s\n\n**Goal:** %s\n\n" % (p["project"], p["goal"])
    if p.get("parent"):
        out += "**Parent:** %s/ · %s\n\n" % (p["parent"]["project"], p["parent"]["task"])
    if lines:
        out += "\n".join(lines) + "\n\n"
    out += "---\n\n## Details\n"
    if details:
        out += "\n" + "\n\n".join(details) + "\n"
    return out


def _path(root, project) -> Path:
    return records.path(Path(root) / project, TASKS_NAME)


def load(root, project) -> dict:
    path = _path(root, project)
    if not path.is_file():
        raise ValueError("%s/ has no TASKS.md. Start the project with: rules.py init %s --goal \"<goal>\"" % (project, project))
    p = parse(path.read_text(encoding="utf-8", errors="replace"))
    import questions
    asking = questions.open_tasks(root, project)      # ❓ and ❗ follow QUESTIONS.jsonl, never set by hand
    doing = questions.open_actions(root, project)
    for k in p["tasks"]:
        k["question"] = k["id"] in asking
        k["action"] = k["id"] in doing
    return p


def sync(root, project) -> None:
    """Rewrite the window when its ❓ and ❗ marks no longer match the open questions and actions."""
    path = _path(root, project)
    if not path.is_file():
        return
    on_disk = parse(path.read_text(encoding="utf-8", errors="replace"))
    p = load(root, project)
    marks = lambda w: [(k["question"], k["action"]) for k in w["tasks"]]
    if marks(on_disk) != marks(p):
        save(root, project, p)


def save(root, project, p: dict) -> None:
    """Write the window. Refuses when the file on disk holds lines the format cannot keep, since rendering
    from the parse would drop them without a word: an old checkbox line, prose, a task with no id."""
    path = _path(root, project)
    if path.is_file():
        lost = [x for x in parse(path.read_text(encoding="utf-8", errors="replace"))["problems"]
                if x.startswith("not a task line") or "without an id" in x]
        if lost:
            raise ValueError("%s/TASKS.md holds lines the format cannot keep, and writing now would drop them: %s. "
                             "Ask the user how to bring them into the format." % (project, "; ".join(lost)))
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(render(p), encoding="utf-8")
    os.replace(tmp, path)


def _find(p, tid):
    for k in p["tasks"]:
        if k["id"] == tid:
            return k
    raise ValueError("no task %s in the window. See it: rules.py tasks" % tid)


def _now(p):
    return next((k for k in p["tasks"] if k["status"] == "now"), None)


def _promote_next(p):
    """Keep exactly one task in progress: the first not-started task starts when none is."""
    if _now(p):
        return None
    nxt = next((k for k in sorted(p["tasks"], key=lambda k: RANK[k["status"]]) if k["status"] == "next"), None)
    if nxt:
        nxt["status"], nxt["date"], nxt["since"] = "now", today(), True
    return nxt


def next_id(root, project, p) -> str:
    """One more than any id this project has used, in the window or in its history, so ids never repeat."""
    import history
    used = [int(k["id"][1:]) for k in p["tasks"] if re.fullmatch(r"t\d+", k["id"] or "")]
    for e in history.entries(root, project):
        if re.fullmatch(r"t\d+", str(e.get("task", ""))):
            used.append(int(e["task"][1:]))
    return "t%d" % (max(used) + 1 if used else 1)


def _clean(text, what="a task"):
    text = " ".join(str(text).split())
    if len(text) < 4:
        raise ValueError("%s needs a few words" % what)
    if len(text) > 140:
        raise ValueError("%s is one terse line of at most 140 characters; put the rest in its details" % what)
    return text


def add(root, project, text, details="", at=None) -> dict:
    details = _detail(details)
    if len(details) < 20:
        raise ValueError('every task carries a short paragraph: what it is for and what done means. '
                         '--details "<paragraph>"')
    p = load(root, project)
    nexts = [k for k in p["tasks"] if k["status"] == "next"]
    if MAX_NEXT is not None and len(nexts) >= MAX_NEXT and _now(p):
        raise ValueError("the window already holds %d not-started tasks. Finish, drop or block one first" % MAX_NEXT)
    k = {"status": "next", "question": False, "action": False, "text": _clean(text), "bold": False, "date": "", "since": False,
         "id": next_id(root, project, p)}
    order = sorted(p["tasks"], key=lambda x: RANK[x["status"]])
    first_next = next((i for i, x in enumerate(order) if x["status"] == "next"), len(order))
    pos = first_next + max(0, min(int(at) - 1, len(nexts))) if at else len(order)
    order.insert(pos, k)
    p["tasks"] = order
    p["details"][k["id"]] = details
    _promote_next(p)
    save(root, project, p)
    return k


def _detail(text):
    text = " ".join(str(text).split())
    if len(text) > MAX_DETAIL:
        raise ValueError("details are at most one short paragraph, %d characters" % MAX_DETAIL)
    return text


def start(root, project, tid) -> dict:
    p = load(root, project)
    k = _find(p, tid)
    if k["status"] == "done":
        raise ValueError("%s is done; add a new task instead" % tid)
    cur = _now(p)
    if cur and cur is not k:
        cur["status"], cur["date"], cur["since"] = "next", "", False
    k["status"], k["date"], k["since"] = "now", today(), True
    save(root, project, p)
    return k


def done(root, project, tid=None, result="", kind="change", evidence=(), refs=(), no_rule="") -> dict:
    """Finish a task: it is logged in the project's history now, marked done in the window, the oldest done task
    leaves the window when more than two are shown, and the next not-started task starts."""
    import history
    p = load(root, project)
    k = _find(p, tid) if tid else _now(p)
    if not k:
        raise ValueError("no task is in progress; name one: rules.py tasks done <id>")
    if k["status"] == "done":
        raise ValueError("%s is already done" % k["id"])
    entry = history.add(root, project, kind, k["text"], result=result, evidence=evidence, refs=refs,
                        no_rule=no_rule, extra={"task": k["id"]})["entry"]
    k["status"], k["date"], k["since"], k["question"], k["action"] = "done", today(), False, False, False
    dropped = []
    while sum(1 for x in p["tasks"] if x["status"] == "done") > MAX_DONE:
        oldest = next(x for x in p["tasks"] if x["status"] == "done")
        p["tasks"].remove(oldest)
        p["details"].pop(oldest["id"], None)
        dropped.append(oldest["id"])
    started = _promote_next(p)
    save(root, project, p)
    return {"task": k, "entry": entry, "left_window": dropped, "started": started}


def block(root, project, tid, reason) -> dict:
    p = load(root, project)
    k = _find(p, tid)
    if k["status"] == "done":
        raise ValueError("%s is done" % tid)
    reason = _detail(reason)
    if len(reason) < 8:
        raise ValueError("a blocked task says why, in its details: --reason \"<why>\"")
    was_now = k["status"] == "now"
    k["status"], k["date"], k["since"] = "blocked", "", False
    reason = re.sub(r"^blocked:?\s*", "", reason, flags=re.IGNORECASE).replace(BLOCK_SEP, ", ")
    rest = _unblocked(p["details"].get(tid, ""))
    p["details"][tid] = "Blocked: " + reason + (BLOCK_SEP + rest if rest else "")
    started = _promote_next(p) if was_now else None
    save(root, project, p)
    return {"task": k, "started": started}


def unblock(root, project, tid, at=None) -> dict:
    """Back to not started. `at` places it among the not-started tasks, 1 first, as add --at does; a number past
    the end puts it last, for a task put back "on the stack for the future" (the user, 2026-09-15). Without it the
    task keeps its place, which is ahead of every not-started task, so it would be the next one to start."""
    p = load(root, project)
    k = _find(p, tid)
    if k["status"] != "blocked":
        raise ValueError("%s is not blocked" % tid)
    k["status"] = "next"
    rest = _unblocked(p["details"].get(tid, ""))
    if rest:
        p["details"][tid] = rest
    else:
        p["details"].pop(tid, None)     # blocked before paragraphs were required: check will ask for one
    if at:
        order = [x for x in sorted(p["tasks"], key=lambda x: RANK[x["status"]]) if x is not k]
        first_next = next((i for i, x in enumerate(order) if x["status"] == "next"), len(order))
        nexts = sum(1 for x in order if x["status"] == "next")
        order.insert(first_next + max(0, min(int(at) - 1, nexts)), k)
        p["tasks"] = order
    _promote_next(p)
    save(root, project, p)
    return k


BLOCK_SEP = " · "


def _unblocked(text):
    """The paragraph without its "Blocked: <why> · " prefix."""
    if not text.startswith("Blocked: "):
        return text
    return text.split(BLOCK_SEP, 1)[1] if BLOCK_SEP in text else ""


def drop(root, project, tid, reason) -> dict:
    """Take a task out of the window without doing it. The history records that, and why."""
    import history
    p = load(root, project)
    k = _find(p, tid)
    if k["status"] == "done":
        raise ValueError("%s is done; it leaves the window on its own" % tid)
    if len(" ".join(str(reason).split())) < 8:
        raise ValueError("dropping a task says why: --reason \"<why>\"")
    entry = history.add(root, project, "decision", "dropped task: " + k["text"], what=reason,
                        extra={"task": k["id"]})["entry"]
    p["tasks"].remove(k)
    p["details"].pop(tid, None)
    _promote_next(p)
    save(root, project, p)
    return {"task": k, "entry": entry}


def detail(root, project, tid, text) -> dict:
    p = load(root, project)
    _find(p, tid)
    text = _detail(text)
    if len(text) < 20:
        raise ValueError("every task keeps a short paragraph; give at least a sentence")
    k = _find(p, tid)
    if k["status"] == "blocked" and not text.startswith("Blocked: "):
        why = p["details"].get(tid, "").split(BLOCK_SEP, 1)[0]
        text = (why + BLOCK_SEP if why.startswith("Blocked: ") else "") + text   # the reason stays in front
    p["details"][tid] = text
    save(root, project, p)
    return p


def set_goal(root, project, text) -> dict:
    p = load(root, project)
    p["goal"] = _clean(text, "a goal")
    save(root, project, p)
    return p


def init(root, folder, goal, task=None, questions=True) -> dict:
    """Start a project: HISTORY.jsonl opened with a stamped entry, TASKS.md with its goal, an empty QUESTIONS.jsonl,
    all three in the project's .rs folder. questions=False leaves out QUESTIONS.jsonl, for projects that never
    wait on a person (Adapt's agents).

    Any folder may be a project, the repo root included, and projects nest (the user, 2026-09-14): records go to
    the nearest project file up the path. A project inside another is a sub-project and names the parent task
    it serves with `task`, so every sub-project can be traced back to the task it came from."""
    import history
    import rules_lib as lib
    root = Path(root)
    rel = history.norm_folder(root, folder)
    if rel and Path(rel).parts[0].lower() in {x.lower() for x in lib.NOT_PROJECTS}:
        raise ValueError("a project lives in the work tree, not under %s/" % Path(rel).parts[0])
    shown = rel or "."
    parent = lib.project_of(root, Path(rel).parent.as_posix()) if rel else None
    d = root / rel
    link = None
    if parent and not records.path(d, TASKS_NAME).exists():
        try:
            ptasks = load(root, parent)["tasks"]
        except ValueError:
            ptasks = None               # an older parent with only a history has no tasks to link to
        if ptasks is not None:
            if not task:
                listed = ", ".join("%s %s" % (k["id"], k["text"][:50]) for k in ptasks if k["status"] != "done")
                raise ValueError("%s/ sits inside the project %s/, so it names the parent task it serves: --task <id>. "
                                 "%s/ tasks: %s" % (shown, parent, parent, listed or "none yet; add one there first"))
            if task not in {k["id"] for k in ptasks}:
                raise ValueError("%s/ has no task %s in its window: rules.py tasks --in %s" % (parent, task, parent))
            link = {"project": parent, "task": task}
    if records.legacy(d):
        raise ValueError("%s/ keeps its records in the old place (%s); move them first: rules.py migrate"
                         % (shown, ", ".join(p.name for p in records.legacy(d))))
    wanted = [m for m in records.NAMES if questions or m != QUESTIONS_NAME]
    existing = [m for m in records.NAMES if records.path(d, m).exists()]
    if all(m in existing for m in wanted):
        raise ValueError("%s/ already has %s" % (shown, ", ".join(existing)))
    goal = _clean(goal, "a goal")
    d.mkdir(parents=True, exist_ok=True)
    made = []
    # an older project may have only its history: init completes it, never touching a file already there
    records.folder(d).mkdir(parents=True, exist_ok=True)
    if questions and QUESTIONS_NAME not in existing:
        records.path(d, QUESTIONS_NAME).write_text("", encoding="utf-8")
        made.append(QUESTIONS_NAME)
    if TASKS_NAME not in existing:
        save(root, rel, {"project": rel or root.name, "goal": goal, "parent": link, "tasks": [], "details": {},
                         "problems": []})
        made.append(TASKS_NAME)
    if records.HISTORY not in existing:
        records.path(d, records.HISTORY).touch()  # made first, so a sub-project's start is logged in its own
        made.append(records.HISTORY)              # file, not the parent's: records go to the nearest file up the path
    title = ("project started: " if not existing else "project files completed: ") + goal
    entry = history.add(root, rel, "decision", title,
                        what="created %s with rules.py init" % ", ".join(made)
                        + (", inside the project %s/ for its task %s" % (parent, task) if link else
                           ", inside the project %s/" % parent if parent else ""),
                        extra={"parent": parent, "parent_task": task} if link else None)["entry"]
    if parent and not existing:
        history.add(root, parent, "decision",
                    ("sub-project started%s: %s/: %s" % (" for " + task if link else "", shown, goal))[:140],
                    what="a project of its own inside this one, with its own tasks, history and questions",
                    extra={"task": task, "subproject": shown} if link else {"subproject": shown})
    return {"project": shown, "entry": entry, "parent": link,
            "files": [(rel + "/" if rel else "") + records.RECORDS_DIR + "/" + m for m in made]}


def children(root, project) -> dict:
    """{parent task id: [sub-project folder, ...]} for every sub-project below `project` that names one of its
    tasks in its **Parent:** line. How a task's work can be followed down into the folders it spawned."""
    import rules_lib as lib
    root = Path(root)
    proj = (project or ".").strip("/") or "."
    base = root if proj == "." else root / proj
    out = {}
    for t in sorted(base.rglob(TASKS_NAME)):
        owner = records.project_of_file(t)
        if owner is None or owner == base or "_backup" in t.parts:
            continue
        parts = owner.relative_to(root).parts
        if parts and parts[0].lower() in {x.lower() for x in lib.NOT_PROJECTS}:
            continue
        try:
            par = parse(t.read_text(encoding="utf-8", errors="replace")).get("parent") or {}
        except OSError:
            continue
        if (par.get("project") or "").strip("/") == proj and par.get("task"):
            out.setdefault(par["task"], []).append(owner.relative_to(root).as_posix())
    return out


def show(root, project) -> str:
    p = load(root, project)
    out = ["TASKS %s/" % project, "  goal: %s" % p["goal"]]
    if p.get("parent"):
        out.append("  parent: %s/ task %s" % (p["parent"]["project"], p["parent"]["task"]))
    kids = children(root, project)
    for k in sorted(p["tasks"], key=lambda k: RANK[k["status"]]):
        date = (" (since %s)" if k["since"] else " (%s)") % k["date"] if k["date"] else ""
        sub = ("   -> sub-project " + ", ".join(x + "/" for x in kids[k["id"]])) if k["id"] in kids else ""
        out.append("  %s %-4s %s%s%s%s%s" % (ICON_OF[k["status"]], k["id"], QUESTION + " " if k["question"] else "",
                                             ACTION + " " if k.get("action") else "", k["text"], date, sub))
    now = _now(p)
    if now and now["id"] in p["details"]:
        out.append("  now: %s" % p["details"][now["id"]])
    for k in p["tasks"]:
        if k["status"] == "blocked" and k["id"] in p["details"]:
            out.append("  %s: %s" % (k["id"], p["details"][k["id"]]))
    if p["problems"]:
        out.append("  problems: " + "; ".join(p["problems"]))
    return "\n".join(out)
