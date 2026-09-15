"""The handoff record: one folder per occasion in the archive, one log in the skill.

WHY THIS EXISTS
---------------
A handoff is written once and read once, and the reader may find it wrong, thin or ambiguous. That
finding used to have nowhere to go: the handoff itself may never be edited, and the session that
wrote it had already ended. So a reader's review sat beside the skill and nobody was told.

Everything lives with the skill, because a retired handoff belongs to the handoff machinery and not
to any mechanic. They once sat in one project's archive folder, which put
repo-wide handoffs inside one mechanic's folder for no reason anyone could defend.

    <skill>/data/<occasion>/
        HANDOFF.md     the retired handoff             (always)
        REVIEW.md      the reader's feedback on it     (when reading it cost the reader time)
        RESPONSE.md    the author's reply to that      (when the author has answered)

    <skill>/data/log.jsonl   append-only, one line per event

One folder per occasion, one to three files in it, and the whole exchange about one handoff reads
top to bottom. A REVIEW.md with no RESPONSE.md beside it is a debt: the log says which session
wrote that handoff, and `handoffs.py pending` prints it so the user can resume that session.

The skill itself holds only `data/`, `scripts/` and `SKILL.md`.

An occasion is `<date the handoff was written>-<scope slug>`, e.g. `2026-09-10-rule-mining`. Three
files at most, one folder, so the whole conversation about one handoff reads top to bottom, next to
every other retired handoff rather than inside the skill.

The log is what makes the loop visible. Its `written` record carries the SESSION ID of the author,
captured at write time by a hook, because that is the only moment anything knows it. A review
arriving later leaves the occasion PENDING, and `handoffs.py pending` prints which session to resume
to answer it.

Standard library only, and nothing is imported from the repo: this folder must survive `delete
everything except this skill`, and with the repo gone the archive simply reads as empty. Repo-side
hooks import THIS, which is the allowed direction.
"""

import json
import os
import re

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# HANDOFF_DATA_DIR redirects the whole record elsewhere. It exists so the hook tests can exercise
# the real hooks without appending to the real log; nothing in normal use sets it.
DATA = os.environ.get("HANDOFF_DATA_DIR") or os.path.join(SKILL_DIR, "data")
LOG = os.path.join(DATA, "log.jsonl")

# Occasion folders sit directly in data/, beside the log.
ARCHIVE = DATA
ARCHIVE_REL = ".claude/skills/handoff/data"

# <repo>/.claude/skills/handoff -> <repo>. Computed, not imported, and used only to print short
# paths: with the repo gone the skill still works.
REPO = os.path.dirname(os.path.dirname(os.path.dirname(SKILL_DIR)))

HANDOFF_FILE = "HANDOFF.md"
REVIEW_FILE = "REVIEW.md"
RESPONSE_FILE = "RESPONSE.md"

# The states an occasion can be in, in the order they happen.
RETIRED = "retired"                  # handoff only: read, retired, no feedback offered
PENDING = "pending_author_review"    # a review is waiting for the author to answer
CLOSED = "closed"                    # the author answered the review

_OCCASION_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})(?:-(.+))?$")
_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slug(text: str) -> str:
    """A scope slug: lowercase, hyphen-separated, safe as a folder name."""
    return _SLUG_RE.sub("-", str(text or "").strip().lower()).strip("-") or "unscoped"


def occasion_id(date: str, scope: str) -> str:
    return "%s-%s" % (date, slug(scope))


def split_occasion(name: str):
    """(date, scope) for a folder name, or None when it is not shaped like an occasion."""
    m = _OCCASION_RE.match(name or "")
    return (m.group(1), m.group(2) or "") if m else None


def occasion_dir(occasion: str) -> str:
    return os.path.join(ARCHIVE, occasion)


def front_matter(path: str):
    """The scalar keys in a handoff's front matter, lowercased. {} when it has none.

    A handoff states its own `date:` and `scope:`, which is what lets anything retire it without a
    human choosing a folder name. Guessing those from the prose is how folders drift apart.
    """
    out = {}
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            lines = f.read(4096).splitlines()
    except OSError:
        return out
    if not lines or lines[0].strip() != "---":
        return out
    for line in lines[1:40]:
        if line.strip() == "---":
            break
        if ":" in line and not line.lstrip().startswith("-"):
            key, value = line.split(":", 1)
            out[key.strip().lower()] = value.strip().strip("'\"")
    return out


def review_file(occasion: str) -> str:
    return os.path.join(occasion_dir(occasion), REVIEW_FILE)


def response_file(occasion: str) -> str:
    return os.path.join(occasion_dir(occasion), RESPONSE_FILE)


def state(occasion: str) -> str:
    """What this occasion is waiting for, read straight off the files in its folder."""
    if os.path.isfile(response_file(occasion)):
        return CLOSED
    if os.path.isfile(review_file(occasion)):
        return PENDING
    return RETIRED


def occasions():
    """Every occasion in the archive, oldest first, with its state and the files it holds."""
    out = []
    if not os.path.isdir(ARCHIVE):
        return out
    for name in sorted(os.listdir(ARCHIVE)):
        d = os.path.join(ARCHIVE, name)
        if not os.path.isdir(d) or not split_occasion(name):
            continue
        date, scope = split_occasion(name)
        out.append({
            "occasion": name,
            "date": date,
            "scope": scope,
            "state": state(name),
            "files": sorted(f for f in os.listdir(d) if os.path.isfile(os.path.join(d, f))),
        })
    return out


def read_log():
    """Every event, oldest first. A malformed line is skipped rather than fatal: the log is
    appended by hooks, and a hook that cannot read its own log must not block real work."""
    out = []
    try:
        with open(LOG, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except ValueError:
                    continue
    except OSError:
        return []
    return out


def append(record: dict) -> None:
    """One event onto the log. Creates the data folder on first use."""
    os.makedirs(DATA, exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, sort_keys=True) + "\n")


def author_of(occasion: str, log=None):
    """The `written` record for this occasion, or None if the author was never recorded.

    Matched on the occasion first. Records written before an occasion existed carry only the path
    and the date, so fall back to the newest `written` record whose date matches.
    """
    log = read_log() if log is None else log
    parts = split_occasion(occasion)
    date = parts[0] if parts else None
    exact = [r for r in log if r.get("event") == "written" and r.get("occasion") == occasion]
    if exact:
        return exact[-1]
    if not date:
        return None
    same_day = [r for r in log if r.get("event") == "written"
                and str(r.get("date") or "").startswith(date)]
    return same_day[-1] if same_day else None


def origin_of(occasion: str, log=None):
    """Where this handoff LIVED before retirement, repo-relative, or ''.

    The location is not incidental: a handoff at the repo root hands off repo-wide work, one inside
    a folder hands off that folder's work. Losing the path loses that half of its meaning, so the
    log keeps it and the chart shows it.
    """
    log = read_log() if log is None else log
    # `located` is a correction recorded by hand; `written` is the live path the hook saw; `from` is
    # where retire moved it out of, which is the live path too UNLESS the file was filed by hand.
    for key, event in (("path", "located"), ("path", "written"), ("from", "retired")):
        hits = [r for r in log if r.get("event") == event and r.get("occasion") == occasion
                and r.get(key)]
        if hits:
            return str(hits[-1][key]).replace("\\", "/")
    return ""


def origin_folder(occasion: str, log=None):
    """Just the folder part of the origin: '/' for the repo root, '' when unknown."""
    origin = origin_of(occasion, log)
    if not origin:
        return ""
    folder = origin.rsplit("/", 1)[0] if "/" in origin else ""
    return folder or "/"


def pending(log=None):
    """Every review nobody has answered, with the author session to resume."""
    log = read_log() if log is None else log
    out = []
    for occ in occasions():
        if occ["state"] != PENDING:
            continue
        rec = author_of(occ["occasion"], log) or {}
        out.append(dict(occ,
                        review=review_file(occ["occasion"]),
                        author_session=rec.get("session"),
                        author_transcript=rec.get("transcript"),
                        written_at=rec.get("ts")))
    return out
