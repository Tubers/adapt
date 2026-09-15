"""Ask the rules a question in your own words.

    python .claude/skills/vector-search/scripts/search.py "my clone has no build button"
    python .claude/skills/vector-search/scripts/search.py --file Adapt/README.md
    python .claude/skills/vector-search/scripts/search.py --json "retire a handoff"
    python .claude/skills/vector-search/scripts/search.py --history "has anyone measured the claim radius"
    python .claude/skills/vector-search/scripts/search.py --history "was this already tried"
    python .claude/skills/vector-search/scripts/search.py --skill rules-system "where are gates matched against a path"
    python .claude/skills/vector-search/scripts/search.py --skill all "retire a finished handoff"

A hit is a POINTER: rule name, its gate, and the line that matched. Open the rule before acting on it.
Below the floor the answer is "nothing close", which is a real answer and will be common.
"""

import json
import pathlib
import re
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import corpus                                                     # noqa: E402
import embed                                                      # noqa: E402
import index as index_mod                                         # noqa: E402

FLOOR = 0.40        # below this, say nothing was close rather than offer the least-bad three
# The floor is PER NAMESPACE, because similarity is not comparable across document shapes. A rule is
# ~900 bytes of dense statement and scores high against a matching question. A results abstract is
# several paragraphs of narrative, so its best true match sits lower: the isolation run, which IS the
# right answer to "which run isolated the container field", scored 0.311 while the whole corpus
# topped out at 0.355. One global floor either refuses every correct results hit or lets rule noise
# through. Each floor is set where the off-topic questions in the golden set still return nothing.
FLOORS = {"rules": 0.40, "history": 0.40, "results": 0.28, "skill": 0.45}
# skill, calibrated 2026-09-13 with no floor: the seven golden skill questions' right answers scored 0.469
# to 0.708, eight off-topic questions 0.265 to 0.427 ("write a cover letter for a job" passed the old 0.40).
# 0.45 sits between; the margin is thin on both sides, so a new miss or leak belongs in golden.jsonl.


def floor_for(ns: str) -> float:
    """Every skill index shares one floor: a skill chunk is the same shape whichever skill it is from."""
    return FLOORS.get("skill" if ns == "skills" or ns.startswith("skill:") else ns, FLOOR)


def parse_ns(argv):
    """(namespace, remaining argv) from --rules / --history / --results / --skill <name|all>."""
    ns = "rules"
    argv = list(argv)
    for flag in ("--history", "--results", "--rules"):
        if flag in argv:
            ns = flag[2:]
            argv = [a for a in argv if a != flag]
    if "--skill" in argv:
        i = argv.index("--skill")
        if i + 1 >= len(argv):
            raise SystemExit("--skill needs a skill name, or all")
        name = argv[i + 1]
        argv = argv[:i] + argv[i + 2:]
        ns = "skills" if name == "all" else "skill:" + name
        if ns != "skills" and name not in corpus.skill_names():
            raise SystemExit("no skill named %s. Skills: %s" % (name, ", ".join(corpus.skill_names())))
    return ns, argv


TOP = 5
POINTER_PENALTY = 0.02    # a pointer line credits its target just under its own score
LEXICAL_MAX = 0.05        # token overlap can break a tie, never overturn a ranking
SUPPORT_STEP = 0.015      # per extra matching vector from the same rule
SUPPORT_CAP = 4           # and no more than four of them count
_WORD = re.compile(r"[a-z_][a-z0-9_]{3,}")
_STOP = {"that", "this", "with", "from", "what", "when", "does", "have", "will", "into", "they",
         "there", "which", "would", "about", "after", "where", "should", "could", "still", "than",
         "then", "them", "their", "been", "being", "because", "every", "here", "just", "only",
         "rule", "rules"}


def _lexical(query: str, text: str) -> float:
    q = {w for w in _WORD.findall(query.lower()) if w not in _STOP}
    if not q:
        return 0.0
    t = set(_WORD.findall(text.lower()))
    return LEXICAL_MAX * (len(q & t) / len(q))
LOG = HERE.parent / "data" / "searches.jsonl"


def query(text: str, top: int = TOP, floor: float = None, ns: str = "rules"):
    """Search one namespace. rules answers what to DO, history what HAPPENED, results the raw ground
    truth a rule came from. They are never merged, so an answer always knows which corpus it is."""
    floor = floor_for(ns) if floor is None else floor
    if ns == "skills" or ns.startswith("skill:"):
        return _query_skills(text, top, floor, ns)
    if ns != "rules":
        return _query_flat(text, top, floor, ns)

    import numpy as np

    keys, mat, man = index_mod.load()
    if keys is None:
        raise SystemExit("no index yet: run index.py")
    emb = embed.Embedder(dim=man["model"]["dim"])
    if emb.fingerprint()["graph_sha256_16"] != man["model"]["graph_sha256_16"]:
        raise SystemExit("index was built with a different model. Rebuild: index.py --rebuild")

    t0 = time.time()
    q = emb.queries([text])[0]
    sims = mat @ q
    order = np.argsort(-sims)
    meta, g = man["meta"], corpus.gates()
    stems = corpus.rule_stems()
    whole = {name: text for name, text, _ in corpus.rule_texts()}

    scored = {}

    support = {}

    def offer(rule, score, line, kind):
        score += _lexical(text, whole.get(rule, ""))
        support[rule] = support.get(rule, 0) + 1
        if rule not in scored or score > scored[rule]["score_raw"]:
            trig, gist = g.get(rule, ("(no gate)", ""))
            scored[rule] = {"rule": rule, "score_raw": score, "score": round(score, 3),
                            "gate": trig, "gist": gist, "line": line, "matched": kind}

    for i in order[:80]:
        s = float(sims[i])
        if s < floor - LEXICAL_MAX:
            break
        m = meta.get(keys[i], {})
        rule = m.get("rule")
        if not rule:
            continue
        line = m.get("text", "")
        offer(rule, s, line, m.get("kind", ""))
        # A pointer line is evidence about the rule it NAMES, which is usually the better answer.
        for target in corpus.referenced_rules(line, stems):
            if target != rule:
                offer(target, s - POINTER_PENALTY, line, "pointer from " + rule)

    # EVIDENCE ACCUMULATION. A rule that matched on several of its own vectors - its title, its gist
    # and two of its lines - is a better answer than one that matched on a single line, even when the
    # single line scored a shade higher. Capped, so it breaks ties and cannot invent a winner.
    for rule, h in scored.items():
        h["support"] = support.get(rule, 1)
        h["score_raw"] += SUPPORT_STEP * min(SUPPORT_CAP, h["support"] - 1)
        h["score"] = round(h["score_raw"], 3)

    hits = sorted((h for h in scored.values() if h["score_raw"] >= floor),
                  key=lambda h: -h["score_raw"])[:top]
    for h in hits:
        h.pop("score_raw", None)
    ms = (time.time() - t0) * 1000
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps({"q": text[:200], "ns": ns, "ms": round(ms),
                                "top": [h["rule"] for h in hits],
                                "best": hits[0]["score"] if hits else None}) + "\n")
    except OSError:
        pass
    return hits, ms


def _query_flat(text, top, floor, ns):
    """history and results are one vector per document, so no pointer or support machinery."""
    import numpy as np

    keys, mat, man = index_mod.load(ns)
    if keys is None:
        raise SystemExit("no %s index yet: run index.py --ns %s" % (ns, ns))
    emb = embed.Embedder(dim=man["model"]["dim"])
    t0 = time.time()
    q = emb.queries([text])[0]
    sims = mat @ q
    meta = man["meta"]
    hits = []
    for i in np.argsort(-sims)[:top * 2]:
        s = float(sims[i]) + _lexical(text, meta.get(keys[i], {}).get("text", ""))
        if s < floor:
            break
        m = meta.get(keys[i], {})
        hits.append({"rule": m.get("id") or m.get("run") or keys[i], "score": round(s, 3),
                     "gate": m.get("path", ""), "gist": m.get("event_kind", "") or m.get("kind", ""),
                     "line": (m.get("text") or "")[:220], "ns": ns,
                     "status": m.get("status", "")})
        if len(hits) >= top:
            break
    return hits, (time.time() - t0) * 1000


def _query_skills(text, top, floor, ns):
    """One skill index, or every one. Best chunk per FILE, so five hits are five places to look.

    Each skill keeps its own vector file, so `--skill all` loads them in turn and embeds the question
    once. The hits are merged by score and each carries the skill it came from.
    """
    import numpy as np

    names = index_mod.skill_namespaces() if ns == "skills" else [ns]
    loaded = []
    for one in names:
        keys, mat, man = index_mod.load(one)
        if keys is not None:
            loaded.append((one, keys, mat, man))
    if not loaded:
        raise SystemExit("no skill index yet: run index.py --ns skills")
    emb = embed.Embedder(dim=loaded[0][3]["model"]["dim"])
    fp = emb.fingerprint()["graph_sha256_16"]
    t0 = time.time()
    q = emb.queries([text])[0]
    best = {}
    for one, keys, mat, man in loaded:
        if man["model"]["graph_sha256_16"] != fp:
            raise SystemExit("%s was indexed with a different model. Rebuild: index.py --ns %s --rebuild"
                             % (one, one))
        if not len(keys):
            continue
        sims = mat @ q
        meta = man["meta"]
        for i in np.argsort(-sims)[:top * 6]:
            raw = float(sims[i])
            if raw + LEXICAL_MAX < floor:
                break
            m = meta.get(keys[i], {})
            s = raw + _lexical(text, m.get("text", ""))
            if s < floor:
                continue
            doc = "%s/%s" % (m.get("skill", one[6:]), m.get("path", ""))
            if doc in best and best[doc]["score"] >= s:
                continue
            best[doc] = {"rule": "%s:%d" % (doc, m.get("line", 0)), "score": round(s, 3),
                         "gate": m.get("label", ""), "gist": m.get("skill", ""),
                         "line": " ".join((m.get("text") or "").split())[:220], "ns": ns,
                         "status": "", "skill": m.get("skill", ""), "path": m.get("path", "")}
    hits = sorted(best.values(), key=lambda h: -h["score"])[:top]
    return hits, (time.time() - t0) * 1000


def main(argv):
    argv = corpus.parse_repo(argv)
    as_json = "--json" in argv
    argv = [a for a in argv if a != "--json"]
    ns, argv = parse_ns(argv)
    if argv and argv[0] == "--file":
        p = pathlib.Path(argv[1])
        text = p.read_text(encoding="utf-8", errors="replace")[:6000]
        label = "file " + p.as_posix()
    else:
        text = " ".join(argv).strip()
        label = text
    if not text:
        print(__doc__)
        return 2

    hits, ms = query(text, ns=ns)
    if as_json:
        print(json.dumps(hits, indent=1))
        return 0
    print()
    if not hits:
        print("  nothing close in %s to: %s" % (ns.upper(), label[:70]))
        print("  best similarity was under the %s floor of %.2f, so nothing covers this."
              % (ns, floor_for(ns)))
        print("  %.0f ms" % ms)
        return 0
    print("  %d hit(s) in %s for: %s" % (len(hits), ns.upper(), label[:70]))
    print()
    for h in hits:
        print("  %.3f  %s%s" % (h["score"], h["rule"],
                                 "   [%s]" % h["status"] if h.get("status") else ""))
        if h["line"]:
            print("         %s" % h["line"][:150])
        where = "gate" if ns == "rules" else "section" if h.get("skill") else "file"
        if h["gate"]:
            print("         %s: %s" % (where, h["gate"][:120]))
    print()
    if ns == "rules":
        print("  %.0f ms. A hit is a pointer: open rules/<name> before acting on it." % ms)
    elif ns == "skills" or ns.startswith("skill:"):
        print("  %.0f ms. A hit is .claude/skills/<skill>/<path>:<line>. Open it before acting." % ms)
    else:
        print("  %.0f ms." % ms)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
