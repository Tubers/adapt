"""Ask a question AND leave the question and its answer in the folder's log.

    python .claude/skills/vector-search/scripts/ask.py "how long may a rule file be"
    python .claude/skills/vector-search/scripts/ask.py --history "has anyone measured the claim radius"
    python .claude/skills/vector-search/scripts/ask.py --in Adapt "why a manifest"
    python .claude/skills/vector-search/scripts/ask.py --skill rules-system "where are gates matched"

Same retrieval as search.py. The difference is the record: the question and what came back are
appended to QUERIES.jsonl in the folder the work is happening in, so the NEXT instance in that folder
inherits the lookup instead of repeating it.

WHY A COMMAND RATHER THAN THE INSTANCE WRITING THE FILE ITSELF
--------------------------------------------------------------
The first design had the instance append a line to QUERIES.jsonl and a hook answer it. That cannot
work as stated: Edit needs a unique anchor string and Write replaces whole contents, so appending by
tool means first knowing everything already in the file - which is the re-read cost the whole design
exists to avoid. A command appends in one call, and the hook keys off the command instead.

The log is a BYPRODUCT. This prints its own answer, so retrieval never depends on hooks being alive.
"""

import json
import os
import pathlib
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import corpus                                                     # noqa: E402
import index as index_mod                                         # noqa: E402
import search as search_mod                                       # noqa: E402

LOG_NAME = "QUERIES.jsonl"


def log_path(folder: pathlib.Path) -> pathlib.Path:
    return folder / LOG_NAME


def append(folder: pathlib.Path, q: str, ns: str, hits, ms: float, why: str = "") -> pathlib.Path:
    """One query line and one answer line. Mandatory fields are mandatory: without ns, floor, model
    and index_built, a line cannot be judged later and the log stops being evidence."""
    _, _, man = index_mod.load(ns)
    qid = "%s-%04d" % (time.strftime("%Y%m%d-%H%M%S"), os.getpid() % 10000)
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    query = {"kind": "query", "id": qid, "ts": now, "ns": ns, "q": q,
             "by": os.environ.get("CLAUDE_SESSION_ID", "")}
    if why:
        query["why"] = why
    answer = {"kind": "answer", "for": qid, "ts": now, "ns": ns,
              "floor": search_mod.floor_for(ns),
              "model": (man.get("model") or {}).get("graph_sha256_16", ""),
              "index_built": man.get("built", ""),
              "ms": round(ms),
              "hits": [{"doc": h["rule"], "score": h["score"],
                        "where": h.get("gate", ""), "line": (h.get("line") or "")[:200]}
                       for h in hits]}
    p = log_path(folder)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps(query, sort_keys=True) + "\n")
        f.write(json.dumps(answer, sort_keys=True) + "\n")
    return p


def main(argv):
    ns, argv = search_mod.parse_ns(search_mod.corpus.parse_repo(argv))
    folder = pathlib.Path(".")
    if "--in" in argv:
        i = argv.index("--in")
        folder = pathlib.Path(argv[i + 1])
        argv = argv[:i] + argv[i + 2:]
    why = ""
    if "--why" in argv:
        i = argv.index("--why")
        why = argv[i + 1]
        argv = argv[:i] + argv[i + 2:]

    q = " ".join(argv).strip()
    if not q:
        print(__doc__)
        return 2

    hits, ms = search_mod.query(q, ns=ns)
    print()
    if not hits:
        print("  nothing close in %s to: %s" % (ns.upper(), q[:70]))
    else:
        print("  %d hit(s) in %s for: %s\n" % (len(hits), ns.upper(), q[:70]))
        for h in hits:
            print("  %.3f  %s" % (h["score"], h["rule"]))
            if h.get("line"):
                print("         %s" % h["line"][:150])
            print("         %s: %s" % ("gate" if ns == "rules" else "file", h.get("gate", "")[:110]))
    p = append(folder, q, ns, hits, ms, why)
    print("\n  %.0f ms. logged to %s" % (ms, p.as_posix()))
    if ns == "rules" and hits:
        print("  A hit is a pointer: open rules/<name> before acting on it.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
