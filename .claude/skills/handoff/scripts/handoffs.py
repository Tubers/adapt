"""The handoff record, on the command line. `help` lists everything.

    python .claude/skills/handoff/scripts/handoffs.py pending

`pending` is the one the user asks for by name: which retired handoffs have a reader's review that
nobody has answered, and which session to resume to answer each.
"""

import json
import os
import re
import shutil
import sys

try:                                   # box glyphs must survive a cp1252 console
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import handoff_data as hd                                          # noqa: E402

HELP = """handoffs.py - write a handoff, retire one, review one, answer a review

  WRITING ONE
  create <scope>     propose where this handoff could live. The USER picks; nothing is written
  create <scope> <path> [--skills a,b] [--date YYYY-MM-DD]
                     create the file at the chosen path, with its generated head

  THE RECORD
  status             the whole record as a chart, and what is owed             <- the usual one
  pending            only what is owed, with the session to resume for each
  list               the chart alone
  log [N]            the last N log events (default 20)

  MOVING FILES
  retire <path> [scope] [--date YYYY-MM-DD]
                     file a read handoff into its occasion folder. Date and scope come from the
                     handoff's own front matter; pass a scope only for one that lacks it
  draft <occasion>   open the review file at the right path, with its shape ready to fill in
  review <occasion> <file>
                     file a review you already wrote, if you did not use `draft`
  respond <occasion> <file>
                     answer a review: files the reply as RESPONSE.md and closes the occasion
  check              report anything inconsistent between the folders and the log

An occasion is <date the handoff was written>-<scope slug>, e.g. 2026-09-10-rule-mining. Its folder
holds HANDOFF.md, plus REVIEW.md when the reader had feedback and RESPONSE.md once the author
answered it. One to three files per occasion, nothing else.

Occasions: %s/<occasion>/
Log:       %s
""" % (hd.ARCHIVE_REL, ".claude/skills/handoff/data/log.jsonl")

STATE_LABEL = {
    hd.RETIRED: "retired, no review",
    hd.PENDING: "REVIEW WAITING ON AUTHOR",
    hd.CLOSED:  "closed",
}

# --- the chart -----------------------------------------------------------------------------------
# `status` is read by a person at a glance, so it is a table and not prose. Colour is switched off
# when the output is piped or NO_COLOR is set, and the glyphs stay ASCII-safe on a cp1252 console
# because stdout is reconfigured to UTF-8 below.

_COLOUR = os.environ.get("NO_COLOR") is None and sys.stdout.isatty()


def _c(code, text):
    return text if not (_COLOUR and code) else "\033[%sm%s\033[0m" % (code, text)


BOLD, DIM, RED, GREEN, YELLOW, CYAN = "1", "2", "31", "32", "33", "36"

STATE_CELL = {
    hd.RETIRED: (DIM, "filed"),
    hd.PENDING: (YELLOW, "OWED"),
    hd.CLOSED:  (GREEN, "closed"),
}

PRESENT, ABSENT = "●", "·"          # filled dot, middle dot


def _pad(text, width):
    """Pad to a visible width, ignoring colour codes, which have no width on screen."""
    bare = re.sub(r"\033\[[0-9;]*m", "", text)
    return text + " " * max(0, width - len(bare))


def _chart(rows, log):
    if not rows:
        return ["  no occasions on record"]
    origins = {r["occasion"]: (hd.origin_folder(r["occasion"], log) or "?") for r in rows}
    cols = [
        ("OCCASION", max(8, max(len(r["occasion"]) for r in rows))),
        ("STATE", 6), ("H", 1), ("R", 1), ("A", 1),
        ("LIVED IN", max(8, max(len(v) for v in origins.values()))),
        ("AUTHOR", 8), ("WRITTEN", 10),
    ]
    head = "  " + "  ".join(_pad(_c(BOLD, name), width) for name, width in cols)
    out = [head, "  " + _c(DIM, "─" * (sum(w for _, w in cols) + 2 * (len(cols) - 1)))]
    for r in rows:
        rec = hd.author_of(r["occasion"], log) or {}
        who = rec.get("session") or ""
        colour, label = STATE_CELL[r["state"]]
        cells = [
            _c(CYAN if r["state"] == hd.PENDING else "", r["occasion"]),
            _c(colour, label),
            PRESENT if hd.HANDOFF_FILE in r["files"] else _c(DIM, ABSENT),
            PRESENT if hd.REVIEW_FILE in r["files"] else _c(DIM, ABSENT),
            PRESENT if hd.RESPONSE_FILE in r["files"] else _c(DIM, ABSENT),
            origins[r["occasion"]] if origins[r["occasion"]] != "?" else _c(DIM, "?"),
            who[:8] if who else _c(DIM, "unknown"),
            str(rec.get("ts") or r["date"])[:10],
        ]
        out.append("  " + "  ".join(_pad(cell, width) for cell, (_, width) in zip(cells, cols)))
    return out


def _now():
    import datetime
    return datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def _today():
    import datetime
    return datetime.datetime.now().strftime("%Y-%m-%d")


def _title(path):
    """The first heading in a file, which is how a person recognises which handoff this is."""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f.read(4096).splitlines():
                if line.startswith("#"):
                    return line.lstrip("# ").strip()
    except OSError:
        pass
    return ""


def _opening_words(transcript, limit=140):
    """What the user asked that session to do, from the first user turn in its transcript.

    A session id identifies nothing to a person. The first thing the user typed identifies it
    immediately, which is the difference between "resume 41c82fdd" and "resume the rule-mining one".
    """
    if not transcript or not os.path.isfile(transcript):
        return ""
    try:
        with open(transcript, encoding="utf-8", errors="replace") as f:
            for _ in range(400):
                line = f.readline()
                if not line:
                    break
                if '"type":"user"' not in line and '"type": "user"' not in line:
                    continue
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                content = (rec.get("message") or {}).get("content")
                if isinstance(content, list):
                    content = " ".join(c.get("text", "") for c in content if isinstance(c, dict))
                text = " ".join(str(content or "").split())
                if not text or text.startswith("<"):
                    continue
                return text[:limit] + ("..." if len(text) > limit else "")
    except OSError:
        return ""
    return ""


def cmd_pending(argv):
    rows = hd.pending()
    if not rows:
        print("No review is waiting on an author. %d occasion(s) on record." % len(hd.occasions()))
        return 0
    print("%d handoff(s) have feedback waiting on the session that wrote them:\n" % len(rows))
    for r in rows:
        occ = r["occasion"]
        handoff = os.path.join(hd.occasion_dir(occ), hd.HANDOFF_FILE)
        print("  %s" % occ)
        print("    handoff: %s" % (_title(handoff) or handoff))
        print("    folder:  %s/%s/" % (hd.ARCHIVE_REL, occ))
        print("    review:  %s  (%s)" % (hd.REVIEW_FILE, _title(r["review"]) or "no heading"))
        if r.get("author_session"):
            print("    AUTHOR:  session %s" % r["author_session"])
            words = _opening_words(r.get("author_transcript"))
            if words:
                print("             that session opened with: \"%s\"" % words)
            print("             handoff written %s" % (r.get("written_at") or "date not logged"))
            if r.get("author_transcript"):
                print("             transcript %s" % r["author_transcript"])
            print("    RESUME:  claude --resume %s" % r["author_session"])
        else:
            print("    AUTHOR:  not in the log - this handoff predates the record, so pick the "
                  "session yourself")
        print("    then:    handoffs.py respond %s <the reply that session writes>" % occ)
        print()
    return 0


def cmd_status(argv):
    """The whole record as one chart. A person reads this, so it is a table, not prose."""
    rows = hd.occasions()
    log = hd.read_log()
    owed = [r for r in rows if r["state"] == hd.PENDING]
    tally = "%d occasions   %s" % (
        len(rows),
        _c(YELLOW, "%d owed" % len(owed)) if owed else _c(GREEN, "0 owed"))
    print()
    print("  " + _pad(_c(BOLD, "HANDOFF RECORD"), 30) + tally)
    print()
    for line in _chart(rows, log):
        print(line)
    print()
    print("  " + _c(DIM, "H handoff   R review   A answer            %s/" % hd.ARCHIVE_REL))
    if owed:
        print()
        for r in owed:
            rec = hd.author_of(r["occasion"], log) or {}
            sess = rec.get("session")
            print("  " + _c(YELLOW, "OWED  ") + r["occasion"] + "   " +
                  (_c(BOLD, "claude --resume " + sess) if sess
                   else _c(DIM, "author not in the log, pick the session yourself")))
    print()
    return 0


def cmd_list(argv):
    rows = hd.occasions()
    if not rows:
        print("No occasions in %s" % hd.ARCHIVE_REL)
        return 0
    for line in _chart(rows, hd.read_log()):
        print(line)
    return 0


def cmd_log(argv):
    n = int(argv[0]) if argv and argv[0].isdigit() else 20
    log = hd.read_log()
    if not log:
        print("The log is empty: %s" % hd.LOG)
        return 0
    for rec in log[-n:]:
        print(json.dumps(rec, sort_keys=True))
    print("\n%d event(s) total." % len(log))
    return 0


def _repo_relative(path):
    """A path as the repo sees it, so the log records `ai/HANDOFF.md`, not a machine-specific one."""
    try:
        rel = os.path.relpath(os.path.abspath(path), hd.REPO)
    except ValueError:                       # another drive on Windows
        return path.replace("\\", "/")
    return path.replace("\\", "/") if rel.startswith("..") else rel.replace("\\", "/")


def _log(event, occasion, **extra):
    rec = {"event": event, "occasion": occasion, "ts": _now(),
           "session": os.environ.get("CLAUDE_SESSION_ID", "")}
    rec.update(extra)
    hd.append(rec)


def cmd_retire(argv):
    """Retire a handoff without anyone choosing a folder name.

    The handoff states its own date and scope in front matter, so both come from the file. They are
    overridable for the older handoffs that predate the convention, and only then.
    """
    if not argv:
        print("usage: retire <path to the live HANDOFF.md> [scope] [--date YYYY-MM-DD]")
        return 2
    src = argv[0]
    if not os.path.isfile(src):
        print("No such file: %s" % src)
        return 2
    front = hd.front_matter(src)
    scope = argv[1] if len(argv) > 1 and not argv[1].startswith("--") else front.get("scope", "")
    date = front.get("date", "")
    if "--date" in argv:
        date = argv[argv.index("--date") + 1]
    if not date:
        date = _today()
        print("No `date:` in its front matter, so using today: %s" % date)
    if not scope:
        print("No `scope:` in its front matter and none given, so this handoff cannot be filed.\n"
              "Pass one: retire %s <scope>   (a short slug, e.g. rule-mining)" % src)
        return 2
    occasion = hd.occasion_id(date, scope)
    d = hd.occasion_dir(occasion)
    if os.path.isdir(d):
        print("Occasion %s already exists. A handoff retires once." % occasion)
        return 2
    os.makedirs(d)
    dest = os.path.join(d, hd.HANDOFF_FILE)
    shutil.move(src, dest)
    _log("retired", occasion, **{"from": _repo_relative(src)})
    print("retired -> %s/%s/%s" % (hd.ARCHIVE_REL, occasion, hd.HANDOFF_FILE))
    print("If reading it cost you time, start the review with:")
    print("    handoffs.py draft %s" % occasion)
    return 0


HEADER = """---
skills: %(skills)s
date: %(date)s
scope: %(scope)s
---

# HANDOFF %(date)s - %(scope)s

> **READ ONCE, THEN RETIRE ME.** Written once, read once, then filed away. Never edit this file and
> never maintain it: it is a snapshot, so anything in it that is now wrong is EXPECTED, and the fix
> belongs in the document that owns the fact. When you have read it and moved anything durable into
> the documents that own it, retire it with
> `python .claude/skills/handoff/scripts/handoffs.py retire <path to this file>`, which files it
> under `.claude/skills/handoff/data/%(date)s-%(scope)s/`. If you cannot, ask the user to.
>
> **If reading this costs you time - it is wrong, thin, ambiguous, or it sends you down a dead end -
> say so.** Run `python .claude/skills/handoff/scripts/handoffs.py draft %(date)s-%(scope)s` and
> write it up in the file that opens. It waits there for the session that wrote this handoff, which
> the user can resume to answer it. That is the only way anything here gets better: this file cannot
> be corrected, only answered.

"""


SKIP_DIRS = {".claude", ".git", "__pycache__", "archive", "_backup", "node_modules"}


def _candidates(scope):
    """Folders whose name shares a word with the scope, nearest match first.

    A handoff's folder IS half its meaning, so the choice is put in front of the user rather than
    guessed. One handoff once landed in a mechanic's folder having nothing to do with its work.
    """
    words = [w for w in scope.split("-") if len(w) > 3]
    hits = []
    for depth1 in sorted(os.listdir(hd.REPO)) if os.path.isdir(hd.REPO) else []:
        p1 = os.path.join(hd.REPO, depth1)
        if not os.path.isdir(p1) or depth1 in SKIP_DIRS or depth1.startswith("."):
            continue
        if any(w in depth1.lower() for w in words):
            hits.append(depth1)
        for depth2 in sorted(os.listdir(p1)):
            p2 = os.path.join(p1, depth2)
            if not os.path.isdir(p2) or depth2 in SKIP_DIRS or depth2.startswith("."):
                continue
            if any(w in depth2.lower() for w in words):
                hits.append(depth1 + "/" + depth2)
    return hits[:4]


def _propose(scope, argv):
    """Print where this handoff could live and stop. The user picks; nothing is written."""
    print("Scope: %s\n" % scope)
    print("WHERE SHOULD IT GO? Ask the user and let them choose. Do not pick one silently.\n")
    options = [(hd.HANDOFF_FILE, "repo-wide work: a convention, tooling, the rule system")]
    options += [("%s/%s" % (f, hd.HANDOFF_FILE), "work owned by %s" % f) for f in _candidates(scope)]
    width = max(len(path) for path, _ in options) + 3
    for i, (path, why) in enumerate(options, start=1):
        print("  %d  %s%s" % (i, _pad(_c(BOLD, path), width), _c(DIM, why)))
    n = len(options)
    if n == 1:
        print("     (no folder name matches this scope, so name the folder the work belongs to)")
    print("\nA handoff's folder is half its meaning: root means repo-wide, a folder means that")
    print("folder's work. Never two live handoffs in one folder.\n")
    print("Once the user has chosen:\n")
    print("    handoffs.py create %s <their choice>/HANDOFF.md [--skills a,b]" % scope)
    return 0


def cmd_create(argv):
    """Start a handoff: print or create the head every handoff opens with.

    With no scope it explains the job rather than erroring, because `create` is also how an
    instance is told to write one.
    """
    if not argv:
        print("Writing a handoff. Read this first, it is the whole procedure:\n")
        print("    .claude/skills/handoff/docs/writing.md\n")
        print("Then name the scope to see where it could go:\n")
        print("    handoffs.py create <scope>")
        return 0

    if len(argv) == 1 or argv[1].startswith("--"):
        return _propose(hd.slug(argv[0]), argv)
    scope = hd.slug(argv[0])
    date = argv[argv.index("--date") + 1] if "--date" in argv else _today()
    skills = argv[argv.index("--skills") + 1].replace(",", ", ") if "--skills" in argv else "none"
    text = HEADER % {"skills": skills, "date": date, "scope": scope}
    path = argv[1] if len(argv) > 1 and not argv[1].startswith("--") else ""
    if not path:
        print(text)
        return 0
    if os.path.exists(path):
        print("%s already exists. A handoff is written once." % path)
        return 2
    parent = os.path.dirname(os.path.abspath(path))
    if parent and not os.path.isdir(parent):
        os.makedirs(parent)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    print("created %s with its front matter and notice. Write the four sections under it." % path)
    return 0


DRAFT = """# Reader feedback: %(occasion)s

From: the session that read that handoff, on %(today)s.
To: the session that wrote it. The handoff itself: `%(handoff)s`.

**How to use this.** Each item is a real gap in the handoff or a misreading by the reader. Either
way the prose did not close it, so each ends with the lesson for `SKILL.md`. Mark the items where
you misread it as such, and say what your share was.

Written in compressed register: an LLM reads this. Measure anything you assert here.

---

## 1. <what the handoff said, in one line>

**Handoff said:**

**Found:**

**Cost:**

**Lesson:**

---

## Reader-side errors (mine), for completeness

-

## Summary for the skill

1.
"""


def cmd_draft(argv):
    """Create the review file inside the occasion folder, ready to fill in.

    The reader never chooses where feedback lives, which is the whole point: a review written to a
    path somebody invented is a review the author never sees.
    """
    if not argv:
        print("usage: draft <occasion>      (see: handoffs.py list)")
        return 2
    occasion = argv[0]
    if not hd.split_occasion(occasion):
        print("Not an occasion id: %s (want <YYYY-MM-DD>-<scope>)" % occasion)
        return 2
    if not os.path.isdir(hd.occasion_dir(occasion)):
        print("No such occasion: %s. Retire the handoff first." % occasion)
        return 2
    dest = hd.review_file(occasion)
    if os.path.isfile(dest):
        print("A review for %s is already open: %s" % (occasion, dest))
        return 0
    with open(dest, "w", encoding="utf-8") as f:
        f.write(DRAFT % {
            "occasion": occasion, "today": _today(),
            "handoff": "%s/%s/%s" % (hd.ARCHIVE_REL, occasion, hd.HANDOFF_FILE),
        })
    _log("reviewed", occasion, file=os.path.basename(dest), note="draft opened")
    rec = hd.author_of(occasion) or {}
    print("Write your feedback into: %s" % dest)
    print("It is already in the right place. Do not move it.")
    print("What to put in it: .claude/skills/handoff/docs/review.md")
    if rec.get("session"):
        print("It is now waiting on session %s, which wrote that handoff." % rec["session"])
    return 0


def cmd_review(argv):
    """File a review you wrote elsewhere into its occasion folder."""
    if len(argv) < 2:
        print("usage: review <occasion> <path to the review you wrote>")
        return 2
    occasion, src = argv[0], argv[1]
    if not os.path.isdir(hd.occasion_dir(occasion)):
        print("No such occasion: %s. Retire the handoff first." % occasion)
        return 2
    if not os.path.isfile(src):
        print("No such file: %s" % src)
        return 2
    dest = hd.review_file(occasion)
    if os.path.isfile(dest):
        print("A review for %s is already there. One review per handoff." % occasion)
        return 2
    shutil.move(src, dest)
    _log("reviewed", occasion, file=os.path.basename(dest))
    rec = hd.author_of(occasion) or {}
    print("filed -> %s" % os.path.relpath(dest, hd.REPO).replace("\\", "/"))
    if rec.get("session"):
        print("waiting on session %s. Resume it with: claude --resume %s"
              % (rec["session"], rec["session"]))
    else:
        print("no author in the log for %s, so the user must choose the session" % occasion)
    return 0


def cmd_respond(argv):
    """The author answers the review, which closes the occasion."""
    if len(argv) < 2:
        print("usage: respond <occasion> <path to the reply you wrote>")
        return 2
    occasion, src = argv[0], argv[1]
    d = hd.occasion_dir(occasion)
    if not os.path.isdir(d):
        print("No such occasion: %s" % occasion)
        return 2
    if not os.path.isfile(src):
        print("No such file: %s" % src)
        return 2
    if not os.path.isfile(hd.review_file(occasion)):
        print("Nothing to answer: no review for %s" % occasion)
        return 2
    dest = hd.response_file(occasion)
    if os.path.isfile(dest):
        print("%s already answered." % occasion)
        return 2
    shutil.move(src, dest)
    _log("answered", occasion, file=hd.RESPONSE_FILE)
    print("answered -> %s/%s/ now holds %s"
          % (hd.ARCHIVE_REL, occasion, ", ".join(sorted(os.listdir(d)))))
    return 0


def cmd_check(argv):
    problems = 0
    for occ in hd.occasions():
        d = hd.occasion_dir(occ["occasion"])
        if not os.path.isfile(os.path.join(d, hd.HANDOFF_FILE)):
            print("  no %s in %s" % (hd.HANDOFF_FILE, occ["occasion"]))
            problems += 1
        stray = [f for f in occ["files"]
                 if f not in (hd.HANDOFF_FILE, hd.REVIEW_FILE, hd.RESPONSE_FILE)]
        if stray:
            print("  unexpected file(s) in %s: %s" % (occ["occasion"], ", ".join(stray)))
            problems += 1
        if occ["state"] != hd.RETIRED and not hd.author_of(occ["occasion"]):
            print("  %s has a review but no author in the log, so nobody can be resumed for it"
                  % occ["occasion"])
            problems += 1
    loose = []
    if os.path.isdir(hd.ARCHIVE):
        loose = [f for f in sorted(os.listdir(hd.ARCHIVE))
                 if os.path.isfile(os.path.join(hd.ARCHIVE, f)) and f.lower().startswith("handoff")]
    for f in loose:
        print("  loose handoff not in an occasion folder: %s" % f)
        problems += 1
    stale_inbox = os.path.join(hd.SKILL_DIR, "reader-feedback")
    if os.path.isdir(stale_inbox):
        print("  reader-feedback/ still exists. Reviews live in their occasion folder now.")
        problems += 1
    print("\n%d problem(s)." % problems if problems else "\nclean.")
    return 1 if problems else 0


COMMANDS = {
    "create": cmd_create, "new": cmd_create,      # `new` is the old name, kept working
    "pending": cmd_pending, "status": cmd_status, "list": cmd_list, "log": cmd_log,
    "retire": cmd_retire, "draft": cmd_draft, "review": cmd_review, "respond": cmd_respond,
    "check": cmd_check,
}


def main(argv):
    if not argv or argv[0] in ("help", "-h", "--help"):
        print(HELP)
        return 0
    cmd = COMMANDS.get(argv[0])
    if not cmd:
        print("Unknown command: %s\n" % argv[0])
        print(HELP)
        return 2
    return cmd(argv[1:])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
