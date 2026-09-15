#!/usr/bin/env python3
"""The project viewer: one live browser page with a project's tasks, history and rule candidates.

    rules.py view [folder] [--static] [--no-open]

WHICH PROJECT
-------------
The folder named, walked up to its project. With no folder: the project the command runs inside, then
the project this session last worked in, which the rule-router hook records as the session touches files.
So a user or an instance working in Adapt just runs `rules.py view`.

LIVE, AND GONE WHEN CLOSED
--------------------------
The command starts a small local server in its own process (standard library only, 127.0.0.1) and
opens the page. The page asks every two seconds whether the project's HISTORY.jsonl, TASKS.md,
QUESTIONS.jsonl or the candidate master copy changed, from file sizes and times, and redraws in place
when one did, keeping filters, open entries and the tab. The server exits three minutes after the last
request: browsers slow timers in a hidden tab to once a minute, so a shorter wait would close a page
that is only in the background. Running the command again for the same project reuses a live server.

THE PAGE IS BUILT FROM THE SKILL
--------------------------------
web/view.html, view.css and view.js are joined into one page in memory, so nothing lands in the repo.
`--static` writes that page with the data inside it to the temp folder, a snapshot that never updates.
The page only reads. Every change still goes through the record commands.
"""

from __future__ import annotations

import datetime
import http.server
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
import history  # noqa: E402
import rules_lib as lib  # noqa: E402
import tasks as tasks_mod  # noqa: E402

WEB = Path(__file__).resolve().parents[1] / "web"
POLL_MS = 2000
IDLE_EXIT = 180           # seconds after the last request; a hidden tab may poll only once a minute
FIRST_WAIT = 300          # seconds to wait for the browser's first request
MAX_LIFE = 12 * 3600
VIEWS = Path(tempfile.gettempdir()) / "rules-system-views"


# --------------------------------------------------------------------------------------------------
# which project
# --------------------------------------------------------------------------------------------------

def projects(root) -> list:
    """Every project folder, most recently changed first."""
    root = Path(root)
    found = {}
    for p in lib.walk_repo(root, prune_test_runs=True):
        if p.name in lib.PROJECT_MARKERS:
            rel = p.parent.relative_to(root).as_posix()
            if not rel.startswith(".claude"):
                found[rel] = max(found.get(rel, 0), p.stat().st_mtime)
    return [k for k, _ in sorted(found.items(), key=lambda kv: -kv[1])]


def resolve_project(root, folder=None, cwd=None, session=None):
    """(project, how it was chosen). Raises ValueError, naming the projects, when there is nothing to go on."""
    root = Path(root).resolve()
    if folder:
        rel = history.norm_folder(root, folder)
        if not (root / rel).is_dir():
            raise ValueError("no such folder: %s" % rel)
        return (lib.project_of(root, rel) or rel or "."), "named"
    try:
        here = Path(cwd or os.getcwd()).resolve().relative_to(root).as_posix()
    except ValueError:
        here = ""
    if here and here != ".":
        proj = lib.project_of(root, here)
        if proj:
            return proj, "the folder this command ran in"
    focus = lib.read_focus(session if session is not None else os.environ.get("CLAUDE_CODE_SESSION_ID", ""))
    if focus and (root / focus.get("project", "")).is_dir():
        return focus["project"], "the project this session last worked in"
    if lib.project_of(root, "") == lib.ROOT_PROJECT:
        return lib.ROOT_PROJECT, "the repository root's project"
    known = projects(root)
    raise ValueError("no project to show. Name one: rules.py view <folder>%s"
                     % (". Projects: " + ", ".join(known[:12]) if known else ""))


# --------------------------------------------------------------------------------------------------
# what the page shows
# --------------------------------------------------------------------------------------------------

def _watched(root, project):
    root = Path(root)
    paths = [root / project / m for m in lib.PROJECT_MARKERS]
    paths.append(history.master_path(root))
    # an unmerged subfolder history is on the page too, so a change to it must redraw the page
    paths += sorted(p for p in (root / project).rglob("HISTORY.jsonl")
                    if p.parent != root / project and "_backup" not in p.parts)
    return paths


def signature(root, project) -> str:
    parts = []
    for p in _watched(root, project):
        try:
            st = p.stat()
            parts.append("%d:%d" % (st.st_size, st.st_mtime_ns))
        except OSError:
            parts.append("-")
    return "|".join(parts)


def payload(root, project) -> dict:
    root = Path(root)
    entries = []
    for e in history.entries(root, project):
        clean = {k: v for k, v in e.items() if not k.startswith("_")}
        clean["_folder"] = history.effective_folder(e)
        entries.append(clean)
    t = root / project / history.TASKS_NAME
    parsed = tasks_mod.parse(t.read_text(encoding="utf-8", errors="replace")) if t.is_file() else None
    import questions
    asked = questions.read(root, project)
    if parsed:
        waiting = {q.get("task") for q in asked if not q.get("answer")}
        for k in parsed["tasks"]:
            k["question"] = k["id"] in waiting
    cands = []
    master = history.master_path(root)
    if master.is_file():
        for line in master.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                c = json.loads(line)
            except ValueError:
                continue
            if not isinstance(c, dict):
                continue
            f = str(c.get("folder", "")).strip("/")
            if project in ("", ".") or f == project or f.startswith(project + "/"):
                cands.append(c)
    return {"project": project, "repo": root.name, "signature": signature(root, project),
            "generated": datetime.datetime.now().isoformat(timespec="seconds"),
            "history": entries, "tasks": parsed, "candidates": cands, "questions": asked,
            "children": tasks_mod.children(root, project), "parent_task": _parent_task(root, parsed)}


def _parent_task(root, parsed):
    """The text of the parent task a sub-project serves, for its page's link back up."""
    par = (parsed or {}).get("parent")
    if not par:
        return None
    try:
        for k in tasks_mod.load(root, par["project"])["tasks"]:
            if k["id"] == par["task"]:
                return {"project": par["project"], "task": k["id"], "text": k["text"], "status": k["status"]}
    except ValueError:
        pass
    return {"project": par["project"], "task": par["task"], "text": "(no longer in its window)", "status": ""}


def build_page(boot: dict) -> str:
    html = (WEB / "view.html").read_text(encoding="utf-8")
    css = (WEB / "view.css").read_text(encoding="utf-8")
    js = (WEB / "view.js").read_text(encoding="utf-8")
    boot_js = "window.VIEW = %s;" % json.dumps(boot, ensure_ascii=False).replace("</", "<\\/")
    return html.replace("/*CSS*/", css).replace("/*BOOT*/", boot_js).replace("/*JS*/", js)


def _slug(root, project) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", "%s-%s" % (Path(root).name, project)).strip("-").lower()


def write_static(root, project) -> Path:
    VIEWS.mkdir(parents=True, exist_ok=True)
    path = VIEWS / (_slug(root, project) + ".html")
    path.write_text(build_page({"mode": "static", "data": payload(root, project)}), encoding="utf-8")
    return path


# --------------------------------------------------------------------------------------------------
# the live server
# --------------------------------------------------------------------------------------------------

def make_server(root, project, port=0, idle=IDLE_EXIT, first_wait=FIRST_WAIT, max_life=MAX_LIFE):
    """(server, start_watchdog). The watchdog shuts the server down once nobody is looking."""
    import secrets
    root = Path(root)
    # The page's one write, an answer to a question, carries this token in a custom header. Only the page this
    # server served knows it, and a custom header makes any other site's request fail its CORS preflight.
    token = secrets.token_hex(16)
    page = build_page({"mode": "live", "poll": POLL_MS, "token": token}).encode("utf-8")
    activity = {"last": time.time(), "seen": False}

    class Handler(http.server.BaseHTTPRequestHandler):
        def _send(self, code, kind, body):
            self.send_response(code)
            self.send_header("Content-Type", kind)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            url = urlparse(self.path)
            port_ = self.server.server_address[1]
            if self.headers.get("Host", "") not in ("127.0.0.1:%d" % port_, "localhost:%d" % port_):
                # a page on another site that re-points its own hostname at 127.0.0.1 must not read the records
                self._send(403, "text/plain; charset=utf-8", b"forbidden")
                return
            activity["last"] = time.time()
            if url.path == "/":
                activity["seen"] = True
                self._send(200, "text/html; charset=utf-8", page)
            elif url.path == "/data":
                activity["seen"] = True
                sig = signature(root, project)
                if parse_qs(url.query).get("sig", [""])[0] == sig:
                    body = {"signature": sig, "unchanged": True}
                else:
                    body = payload(root, project)
                self._send(200, "application/json; charset=utf-8",
                           json.dumps(body, ensure_ascii=False).encode("utf-8"))
            elif url.path == "/ping":
                self._send(200, "text/plain; charset=utf-8", project.encode("utf-8"))
            else:
                self._send(404, "text/plain; charset=utf-8", b"not found")

        def do_POST(self):
            """POST /answer {"id": "q3", "answer": "..."}: the user's reply, written through questions.answer."""
            port_ = self.server.server_address[1]
            if self.headers.get("Host", "") not in ("127.0.0.1:%d" % port_, "localhost:%d" % port_) \
                    or self.headers.get("X-View-Token", "") != token:
                self._send(403, "text/plain; charset=utf-8", b"forbidden")
                return
            route = urlparse(self.path).path
            if route not in ("/answer", "/open"):
                self._send(404, "text/plain; charset=utf-8", b"not found")
                return

            def reply(code, body):
                self._send(code, "application/json; charset=utf-8", json.dumps(body).encode("utf-8"))

            if route == "/open":
                # drill down to a sub-project, or back up to a parent: start (or reuse) that project's viewer
                target = parse_qs(urlparse(self.path).query).get("project", [""])[0]
                try:
                    rel = lib.project_of(root, history.norm_folder(root, target or "."))
                    if not rel:
                        raise ValueError("no project at %s" % (target or "."))
                    link, _reused = launch(root, rel, open_browser=False)
                except (ValueError, RuntimeError) as e:
                    reply(400, {"error": str(e)})
                    return
                activity["last"] = time.time()
                reply(200, {"url": link, "project": rel})
                return

            try:
                n = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                n = -1
            if not 0 < n <= 16384:
                reply(400, {"error": "an answer is one short JSON body"})
                return
            try:
                body = json.loads(self.rfile.read(n).decode("utf-8"))
                qid, text = str(body["id"]), str(body["answer"])
            except (ValueError, KeyError, TypeError):
                reply(400, {"error": "send {\"id\": ..., \"answer\": ...}"})
                return
            activity["last"] = time.time()
            import questions
            try:
                q = questions.answer(root, project, qid, text)
            except ValueError as e:
                reply(400, {"error": str(e)})
                return
            reply(200, {"ok": True, "id": q["id"]})

        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True

    def watchdog():
        started = time.time()
        while True:
            time.sleep(1)
            quiet = time.time() - activity["last"]
            if (activity["seen"] and quiet > idle) or (not activity["seen"] and quiet > first_wait) \
                    or time.time() - started > max_life:
                server.shutdown()
                return

    return server, lambda: threading.Thread(target=watchdog, daemon=True).start()


def _state_file(root, project) -> Path:
    return VIEWS / (_slug(root, project) + ".json")


def _read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _ping(port, project) -> bool:
    if not port:
        return False
    try:
        with urllib.request.urlopen("http://127.0.0.1:%d/ping" % port, timeout=0.7) as r:
            return r.read().decode("utf-8") == project
    except OSError:
        return False


def running(root, project):
    """The URL of a live viewer for this project, or None. While one is open, questions for the user go to it."""
    info = _read_json(_state_file(root, project))
    if info and _ping(info.get("port"), project):
        return "http://127.0.0.1:%d/" % info["port"]
    return None


def serve(root, project, state: Path = None):
    server, start = make_server(root, project)
    if state:
        state.parent.mkdir(parents=True, exist_ok=True)
        state.write_text(json.dumps({"port": server.server_address[1], "pid": os.getpid(), "project": project,
                                     "started": time.strftime("%Y-%m-%dT%H:%M:%S")}), encoding="utf-8")
    start()
    try:
        server.serve_forever()
    finally:
        if state:
            try:
                state.unlink()
            except OSError:
                pass


def launch(root, project, open_browser=True, timeout=8.0):
    """(url, reused). Reuses a live server for this project, or starts one in its own process."""
    state = _state_file(root, project)
    info = _read_json(state)
    if info and _ping(info.get("port"), project):
        url = "http://127.0.0.1:%d/" % info["port"]
        if open_browser:
            webbrowser.open(url)
        return url, True
    VIEWS.mkdir(parents=True, exist_ok=True)
    try:
        state.unlink()
    except OSError:
        pass
    cmd = [sys.executable, str(Path(__file__).resolve()), "--serve", str(root), project, str(state)]
    kw = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL,
          "cwd": str(root)}
    if os.name == "nt":
        kw["creationflags"] = 0x00000008 | 0x00000200        # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    else:
        kw["start_new_session"] = True
    subprocess.Popen(cmd, **kw)
    deadline = time.time() + timeout
    while time.time() < deadline:
        info = _read_json(state)
        if info and info.get("port"):
            url = "http://127.0.0.1:%d/" % info["port"]
            if open_browser:
                webbrowser.open(url)
            return url, False
        time.sleep(0.1)
    raise RuntimeError("the viewer server did not start within %d seconds" % timeout)


if __name__ == "__main__":
    if len(sys.argv) == 5 and sys.argv[1] == "--serve":
        serve(Path(sys.argv[2]), sys.argv[3], Path(sys.argv[4]))
