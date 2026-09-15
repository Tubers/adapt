"""Read the query logs without paying for them.

    python .claude/skills/vector-search/scripts/qlog.py digest [folder]   # one line per question
    python .claude/skills/vector-search/scripts/qlog.py collect          # merge every log into one
    python .claude/skills/vector-search/scripts/qlog.py stats

A QUERIES.jsonl is a RECORD OF QUESTIONS ASKED, not a list of open ones. Nothing in it is a task.

The digest exists because reading a raw log is the expensive path: a hundred questions with their
answers is thousands of tokens, and the same hundred as a digest is a few hundred. An instance
arriving in a folder should read the digest, and the raw lines only when auditing one answer.
"""

import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import corpus                                                     # noqa: E402

LOG_NAME = "QUERIES.jsonl"
MERGED = HERE.parent / "data" / "queries-all.jsonl"


def read_log(p: pathlib.Path):
    """([query...], {query id: answer}) - malformed lines are skipped, never fatal.

    `opened` lines are attached to their answer under the "opened" key, so a caller sees which hit
    was actually read without needing to know the file has three line kinds."""
    queries, answers = [], {}
    opened = []
    try:
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return [], {}
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if d.get("kind") == "query":
            queries.append(d)
        elif d.get("kind") == "answer" and d.get("for"):
            answers[d["for"]] = d
        elif d.get("kind") == "opened" and d.get("for"):
            opened.append(d)
    for o in opened:
        answers.setdefault(o["for"], {}).setdefault("opened", []).append(o)
    return queries, answers


def find_logs(root: pathlib.Path = None):
    root = root or corpus.REPO
    return [p for p in sorted(root.rglob(LOG_NAME)) if "_backup" not in p.parts]


def digest(folder=None, limit=60):
    logs = find_logs(pathlib.Path(folder)) if folder else find_logs()
    if not logs:
        print("  no query log%s" % (" in " + str(folder) if folder else " anywhere in the repo"))
        return 0
    for p in logs:
        qs, ans = read_log(p)
        rel = p.relative_to(corpus.REPO).as_posix() if corpus.REPO in p.parents else p.as_posix()
        print("\n  %s   %d question(s)" % (rel, len(qs)))
        for q in qs[-limit:]:
            a = ans.get(q["id"])
            hits = a.get("hits", []) if a else []
            top = hits[0] if hits else None
            print("   %s  [%s]  %s" % (q["ts"][:10], q.get("ns", "rules")[:7], q["q"][:64]))
            if top:
                mark = ""
                for o in (a or {}).get("opened", []):
                    mark = "   OPENED rank %d" % o.get("rank", 0)
                print("        -> %.3f %s%s" % (top["score"], top["doc"], mark))
            else:
                print("        -> nothing above the floor")
    return 0


def collect():
    MERGED.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with open(MERGED, "w", encoding="utf-8") as out:
        for p in find_logs():
            rel = p.relative_to(corpus.REPO).as_posix()
            qs, ans = read_log(p)
            for q in qs:
                rec = {"folder": rel.rsplit("/", 1)[0], **q}
                a = ans.get(q["id"])
                if a:
                    rec["answer"] = a
                out.write(json.dumps(rec, sort_keys=True) + "\n")
                n += 1
    print("  merged %d question(s) from %d log(s) into %s"
          % (n, len(find_logs()), MERGED.relative_to(corpus.REPO).as_posix()))
    return 0


def stats():
    logs = find_logs()
    total = empty = 0
    per_ns = {}
    for p in logs:
        qs, ans = read_log(p)
        for q in qs:
            total += 1
            per_ns[q.get("ns", "rules")] = per_ns.get(q.get("ns", "rules"), 0) + 1
            a = ans.get(q["id"])
            if not a or not a.get("hits"):
                empty += 1
    print("  logs %d   questions %d   answered-with-nothing %d   by namespace %s"
          % (len(logs), total, empty, per_ns or "-"))
    return 0


if __name__ == "__main__":
    argv = sys.argv[1:]
    cmd = argv[0] if argv else "digest"
    if cmd == "digest":
        sys.exit(digest(argv[1] if len(argv) > 1 else None))
    if cmd == "collect":
        sys.exit(collect())
    if cmd == "stats":
        sys.exit(stats())
    print(__doc__)
    sys.exit(2)
