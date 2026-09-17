"""The four maintenance reports. These are why the index is worth having even if nobody ever queries it.

    python .claude/skills/vector-search/scripts/report.py dupes      [--cut 0.80]
    python .claude/skills/vector-search/scripts/report.py gates      [--limit 40]
    python .claude/skills/vector-search/scripts/report.py coherence  [--worst 15]
    python .claude/skills/vector-search/scripts/report.py hubs
    python .claude/skills/vector-search/scripts/report.py queries
    python .claude/skills/vector-search/scripts/report.py facts      [--cut 0.78]
    python .claude/skills/vector-search/scripts/report.py refactor [--gates]
    python .claude/skills/vector-search/scripts/report.py all

`--json` on facts, dupes, coherence, hubs or gates prints every finding as one JSON object instead of
the text, for a caller that acts on them (rules-system's audit worklist).

Pass `--accepted <file>` to hide findings a person already read and kept. The file belongs to the
CALLER: rules-system keeps it in its own data folder and hands the path over, so this skill never
reaches into another one. Accepted entries that match nothing any more are printed as STALE.

Every one of them reports a CANDIDATE, not a verdict. Two rules can be close because one duplicates the
other, or because they are the two halves of a split that was done on purpose. A number cannot tell
those apart; a person reading the pair can.
"""

import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import corpus                                                     # noqa: E402
import index as index_mod                                         # noqa: E402


ACCEPTED = {}      # kind -> [entry], handed in with --accepted; empty means hide nothing
HIDDEN = {}        # kind -> how many findings the list hid on this run, for the worklist
HUB_GAPS = {}      # hub rule -> [rules in its area it does not name], filled by hubs() for --json


def _stem(name):
    return name[:-len(".rule.md")] if name.endswith(".rule.md") else name


def load_accepted(path):
    """Read a caller's accepted list. A missing or broken file hides nothing, loudly."""
    import json
    global ACCEPTED
    ACCEPTED = {}
    try:
        data = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return ACCEPTED
    except (OSError, ValueError) as e:
        print("   accepted list unreadable, so nothing is hidden: %s" % e)
        return ACCEPTED
    ACCEPTED = {k: v for k, v in data.items() if isinstance(v, list)}
    return ACCEPTED


def _accept_key(kind, e):
    if kind == "facts":
        return frozenset([(_stem(e["a"]), e["text_a"]), (_stem(e["b"]), e["text_b"])])
    if kind == "dupes":
        return frozenset([_stem(e["a"]), _stem(e["b"])])
    if kind in ("coherence", "overbroad"):
        return _stem(e["rule"])
    if kind == "missing":
        return (e["file"], _stem(e["rule"]))
    raise KeyError(kind)


def split_accepted(kind, findings, keyof):
    """(shown, hidden, stale). A malformed entry is skipped, never allowed to hide something."""
    wanted = {}
    for e in ACCEPTED.get(kind, []):
        try:
            wanted[_accept_key(kind, e)] = e
        except (KeyError, TypeError):
            continue
    shown, hidden, used = [], [], set()
    for f in findings:
        k = keyof(f)
        if k in wanted:
            hidden.append(f)
            used.add(k)
        else:
            shown.append(f)
    stale = [e for k, e in wanted.items() if k not in used]
    HIDDEN[kind] = len(hidden)
    return shown, hidden, stale


def _describe(kind, e):
    if kind in ("facts", "dupes"):
        return "%s = %s" % (e.get("a"), e.get("b"))
    if kind == "missing":
        return "%s near %s" % (e.get("rule"), e.get("file"))
    return str(e.get("rule"))


def _print_accepted(kind, hidden, stale, what="at this cut"):
    if hidden:
        print("   %d accepted finding(s) hidden. See them: rules.py accept --list %s" % (len(hidden), kind))
    for e in stale:
        print("   STALE acceptance, matches nothing %s: %s" % (what, _describe(kind, e)))


def _rule_matrix():
    """One vector per rule: the whole-rule vector, which is what 'about the same subject' means here."""
    import numpy as np

    keys, mat, man = index_mod.load()
    if keys is None:
        raise SystemExit("no index yet: run index.py")
    meta = man["meta"]
    names, rows = [], []
    for k, row in zip(keys, mat):
        m = meta.get(k, {})
        if m.get("kind") == "rule":
            names.append(m["rule"])
            rows.append(row)
    return names, np.stack(rows), man


def dupes(cut=0.80, top=30):
    import numpy as np

    names, mat, _ = _rule_matrix()
    sims = mat @ mat.T
    np.fill_diagonal(sims, -1)
    pairs = []
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            if sims[i, j] >= cut:
                pairs.append((float(sims[i, j]), names[i], names[j]))
    pairs.sort(reverse=True)
    pairs, hidden, stale = split_accepted(
        "dupes", pairs, lambda p: frozenset([_stem(p[1]), _stem(p[2])]))
    print("\n== DUPES: rule pairs whose whole-rule vectors sit above %.2f ==" % cut)
    print("   A pair here is either restatement, or a deliberate split. Read both before merging.\n")
    if not pairs:
        print("   none")
    for s, a, b in pairs[:top]:
        same = "same area" if corpus.area_of(a) == corpus.area_of(b) else "ACROSS AREAS"
        print("   %.3f  %-44s %-44s %s" % (s, a, b, same))
    print("\n   %d pair(s) above the cut." % len(pairs))
    _print_accepted("dupes", hidden, stale)
    return pairs


FILE_HEAD = 2500          # a file's subject is in its head: docstring, imports, first definitions
FILE_BATCH = 16


def _file_vectors(files, emb, man):
    """One vector per repo file, batched and cached by content hash.

    The cache lives beside the indexes and is keyed by path plus content hash plus the model
    fingerprint, so a model change invalidates it rather than silently mixing two vector spaces.
    Comparing vectors from two models is the quiet-wrong-answer failure this repo keeps paying for.
    """
    import numpy as np
    import embed                                                  # noqa: E402

    cache_path = index_mod.DATA / "filecache.npz"
    fp = "%s|%s|%d" % (man["model"].get("graph", "?"),
                       man["model"].get("graph_sha256_16", "?"), man["model"]["dim"])
    have = {}
    if cache_path.is_file():
        z = np.load(cache_path, allow_pickle=False)
        if str(z["fingerprint"]) == fp:
            have = {str(k): v for k, v in zip(z["keys"], z["vectors"].astype("float32"))}

    wanted, todo = {}, []
    for rel in files:
        text = (corpus.REPO / rel).read_text(encoding="utf-8", errors="replace")[:FILE_HEAD]
        if len(text.strip()) < 200:
            continue
        key = "%s:%s" % (rel, embed.sha1(text))
        wanted[rel] = key
        if key not in have:
            todo.append((key, rel + "\n" + text))

    if todo:
        print("   embedding %d file(s) of %d, the rest are cached" % (len(todo), len(wanted)))
        rows = emb.queries([x for _, x in todo], batch=FILE_BATCH)
        for (key, _), row in zip(todo, rows):
            have[key] = row
        # drop the older versions of the files just embedded, and files that are gone, so the cache holds
        # one vector per live file rather than every version it ever saw
        live = set(wanted.values())
        keys = sorted(k for k in have if k in live or (k.rsplit(":", 1)[0] not in wanted
                                                        and (corpus.REPO / k.rsplit(":", 1)[0]).is_file()))
        np.savez_compressed(cache_path, keys=np.array(keys),
                            vectors=np.stack([have[k] for k in keys]).astype(np.float16),
                            fingerprint=np.array(fp))
    else:
        print("   every file vector was cached")
    return {rel: have[key] for rel, key in wanted.items() if key in have}


MISSING_FLOOR = 0.45      # below this a rule is not near a file in any useful sense
MISSING_COUNTED = 0.70    # the worklist counts only these: every real missing gate found so far
                          # scored 0.70 or more, and the 0.45 floor admits a thousand weak pairs


def _clip(rel, width):
    """Keep the END of a long path: the filename is what identifies it, and what `accept` needs."""
    return rel if len(rel) <= width else "..." + rel[-(width - 3):]


def gates(limit=40):
    """Semantic nearest rules per file against the rules the gates actually inject."""
    import numpy as np
    sys.path.insert(0, str(corpus.REPO / ".claude" / "skills" / "rules-system" / "scripts"))
    import rules_lib as lib                                       # noqa: E402
    import embed                                                  # noqa: E402

    names, mat, man = _rule_matrix()
    emb = embed.Embedder(dim=man["model"]["dim"])
    files = corpus.repo_files(exts=(".py", ".xs", ".per"))
    print("\n== GATES: what fires against what is near ==")
    print("   NEAR BUT NOT GATED is a candidate missing gate. GATED BUT FAR is a candidate over-broad")
    print("   gate. %d files, showing the %d strongest signals.\n" % (len(files), limit))

    vecs = _file_vectors(files, emb, man)

    missing, overbroad = [], []
    for rel in files:
        q = vecs.get(rel)
        if q is None:
            continue
        sims = mat @ q
        order = np.argsort(-sims)[:5]
        near = {names[i]: float(sims[i]) for i in order}
        fired = {m.rule for m in lib.match_paths(corpus.REPO, [rel])}
        for rule, s in near.items():
            if rule not in fired and s >= MISSING_FLOOR and not corpus.is_hub(rule):
                missing.append((s, rel, rule))
        for rule in fired:
            if corpus.is_hub(rule):
                continue
            i = names.index(rule) if rule in names else None
            if i is not None and float(sims[i]) < 0.25:
                overbroad.append((float(sims[i]), rel, rule))

    missing.sort(reverse=True)
    overbroad.sort()
    missing, hid_m, stale_m = split_accepted("missing", missing, lambda m: (m[1], _stem(m[2])))
    ob_rules = sorted({r for _, _, r in overbroad})
    _, hid_o, stale_o = split_accepted("overbroad", ob_rules, _stem)
    overbroad = [o for o in overbroad if o[2] not in set(hid_o)]
    print("   MISSING GATE candidates")
    for s, rel, rule in missing[:limit]:
        print("     %.3f  %-58s %s" % (s, _clip(rel, 58), rule))
    if not missing:
        print("     none")
    _print_accepted("missing", hid_m, stale_m, "above 0.45")
    print("\n   OVER-BROAD GATE candidates, counted per rule")
    per = {}
    for s, rel, rule in overbroad:
        per.setdefault(rule, []).append(s)
    for rule, ss in sorted(per.items(), key=lambda kv: -len(kv[1]))[:limit]:
        print("     %-52s fired on %3d files at mean similarity %.3f"
              % (rule, len(ss), sum(ss) / len(ss)))
    if not per:
        print("     none")
    _print_accepted("overbroad", hid_o, stale_o, "below 0.25")
    return missing, per


def coherence(worst=15):
    """Distance from each rule to its own area's centroid. A far rule may be filed wrongly."""
    import numpy as np

    names, mat, _ = _rule_matrix()
    areas = {}
    for i, n in enumerate(names):
        areas.setdefault(corpus.area_of(n), []).append(i)
    print("\n== COHERENCE: each rule against its own area's centre ==")
    print("   A rule far from its area, and nearer another area's centre, is a filing candidate.\n")
    centroids = {}
    for a, idx in areas.items():
        c = mat[idx].mean(0)
        centroids[a] = c / np.linalg.norm(c)
    rows = []
    for i, n in enumerate(names):
        own = corpus.area_of(n)
        mine = float(mat[i] @ centroids[own])
        best_other, best_s = None, -1
        for a, c in centroids.items():
            if a == own:
                continue
            s = float(mat[i] @ c)
            if s > best_s:
                best_other, best_s = a, s
        rows.append((mine - best_s, n, own, mine, best_other, best_s))
    rows.sort()
    _, hidden, stale = split_accepted("coherence", [r for r in rows if r[0] < 0],
                                      lambda r: _stem(r[1]))
    rows = [r for r in rows if r not in hidden]
    for gap, n, own, mine, other, s in rows[:worst]:
        flag = "  <-- nearer %s" % other if gap < 0 else ""
        print("   %+.3f  %-50s own %.3f   %s %.3f%s" % (gap, n, mine, other, s, flag))
    misfiled = [r for r in rows if r[0] < 0]
    print("\n   %d rule(s) sit nearer another area's centre." % len(misfiled))
    _print_accepted("coherence", hidden, stale, "- it now sits nearest its own area")
    return misfiled


def hubs():
    """Does each hub still describe its area: every line resolvable, every rule covered."""
    import numpy as np

    names, mat, man = _rule_matrix()
    keys, all_mat, man2 = index_mod.load()
    meta = man2["meta"]
    stems = corpus.rule_stems()
    print("\n== HUBS: do the hub rules still describe their areas ==\n")
    problems = 0
    for name, whole, lines in corpus.rule_texts():
        if not corpus.is_hub(name):
            continue
        area = corpus.area_of(name)
        # A hub names its members by BARE SLUG, e.g. "enumeration-semantics what a list contains",
        # because full paths would eat the 2048-byte cap. So resolve slugs within the hub's own area
        # as well as full stems.
        by_slug = {}
        for n in names:
            if corpus.area_of(n) == area:
                by_slug[n[:-len(".rule.md")].split("/")[-1]] = n
        mentioned = set()
        for _, body in lines:
            for r in corpus.referenced_rules(body, stems):
                mentioned.add(r)
            words = re.findall(r"[a-z][a-z0-9-]{3,}", body)
            for w in words:
                if w in by_slug:
                    mentioned.add(by_slug[w])
        in_area = {n for n in names if corpus.area_of(n) == area and not corpus.is_hub(n)}
        missing = sorted(in_area - mentioned)
        print("   %-22s mentions %3d rules, area holds %3d" % (name, len(mentioned & in_area),
                                                               len(in_area)))
        HUB_GAPS[name] = missing
        if missing:
            problems += len(missing)
            print("     NOT MENTIONED BY THE HUB:")
            for m in missing:
                print("       %s" % m)
    print("\n   %d rule(s) their own area's hub does not name." % problems)
    return problems


def facts(cut=0.78, top=40):
    """Lines from DIFFERENT rules that say the same thing.

    A pointer line is excluded: "see xs/guard" resembles every other pointer and means nothing here.
    Everything surviving is a candidate for one owner plus a pointer, per writing/fact-ownership.
    """
    import numpy as np

    keys, mat, man = index_mod.load("rules")
    if keys is None:
        raise SystemExit("no index yet: run index.py")
    meta = man["meta"]
    stems = corpus.rule_stems()

    idx, rows = [], []
    for k, row in zip(keys, mat):
        m = meta.get(k, {})
        if m.get("kind") != "line":
            continue
        text = m.get("text", "")
        if len(text) < 60:
            continue
        # a line whose content is mostly a cross-reference is not a fact
        refs = corpus.referenced_rules(text, stems)
        if refs and len(text) < 160:
            continue
        idx.append((m["rule"], m.get("line", 0), text))
        rows.append(row)
    if not rows:
        print("no line vectors")
        return []
    arr = np.stack(rows)
    sims = arr @ arr.T
    np.fill_diagonal(sims, -1)

    pairs = []
    n = len(idx)
    for i in range(n):
        for j in range(i + 1, n):
            if idx[i][0] == idx[j][0]:
                continue
            s = float(sims[i, j])
            if s >= cut:
                pairs.append((s, idx[i], idx[j]))
    pairs.sort(key=lambda x: -x[0])
    pairs, hidden, stale = split_accepted(
        "facts", pairs,
        lambda p: frozenset([(_stem(p[1][0]), p[1][2]), (_stem(p[2][0]), p[2][2])]))

    print("")
    print("== FACTS: the same statement living in two different rules, above %.2f ==" % cut)
    print("   %d line(s) compared. Each pair is a CANDIDATE: one owner plus a pointer, or a" % n)
    print("   deliberate restatement that earns its place. Read both before merging.")
    print("")
    for s, a, b in pairs[:top]:
        print("   %.3f  %s:%d" % (s, a[0], a[1]))
        print("          %s" % a[2][:150])
        print("          %s:%d" % (b[0], b[1]))
        print("          %s" % b[2][:150])
        print("")
    print("   %d pair(s) above the cut." % len(pairs))
    _print_accepted("facts", hidden, stale, "at this cut, or a line was edited")
    return pairs


def nearest(text, top=5):
    """The rules nearest to one piece of text: raw cosine, best vector per rule, no ranking bonuses.

    Used to prove a rule candidate is NEW before it is promoted. The text is embedded as a DOCUMENT,
    the same way every rule line was, so a score here means what a score in `facts` means: 0.80 and
    above is one statement written twice. search.py is the wrong tool for this, because its pointer,
    support and lexical bonuses move a score by up to 0.11 and would shift that cut.
    """
    q, man, keys, mat = _doc_vector(text)
    return _nearest_rules(q, keys, mat, man, top)


def _doc_vector(text):
    """(vector, manifest, keys, matrix): one text embedded as a DOCUMENT, beside the rules index."""
    import embed                                                  # noqa: E402

    keys, mat, man = index_mod.load("rules")
    if keys is None:
        raise SystemExit("no rules index yet: run index.py")
    emb = embed.Embedder(dim=man["model"]["dim"])
    if emb.fingerprint()["graph_sha256_16"] != man["model"]["graph_sha256_16"]:
        raise SystemExit("the rules index was built with a different model. Rebuild: index.py --rebuild")
    return emb.documents([text])[0], man, keys, mat


def _nearest_rules(q, keys, mat, man, top):
    import numpy as np

    sims = mat @ q
    meta = man["meta"]
    best = {}
    for i in np.argsort(-sims):
        m = meta.get(keys[i], {})
        rule = m.get("rule")
        if not rule or rule in best:
            continue
        best[rule] = {"rule": rule, "score": round(float(sims[i]), 3), "kind": m.get("kind", ""),
                      "line": m.get("line", 0), "text": (m.get("text") or "")[:220]}
        if len(best) >= top:
            break
    return list(best.values())


def scope(text, top_rules=8, top_files=10):
    """The same cosine pass widened to live repo files: {rules, files, files_skipped}.

    A rule candidate's scope is decided from this. Rules come from the rules index, files from
    data/filecache.npz, which `gates` builds. The text is embedded once, as a document, which is how a
    rule is embedded, so a file score here means what a file score in the gate report means. The cache is
    never rebuilt from here, because that takes minutes: a missing or foreign-model cache is reported as
    skipped. A cached file that no longer exists is left out.
    """
    import numpy as np

    q, man, keys, mat = _doc_vector(text)
    out = {"rules": _nearest_rules(q, keys, mat, man, top_rules), "files": [], "files_skipped": None}
    cache = index_mod.DATA / "filecache.npz"
    fp = "%s|%s|%d" % (man["model"].get("graph", "?"), man["model"].get("graph_sha256_16", "?"),
                       man["model"]["dim"])
    if not cache.is_file():
        out["files_skipped"] = "no file cache yet: run report.py gates once"
        return out
    z = np.load(cache, allow_pickle=False)
    if str(z["fingerprint"]) != fp:
        out["files_skipped"] = "the file cache was built by a different model: run report.py gates"
        return out
    import embed                                                  # noqa: E402
    best, head = {}, {}
    for k, s in zip(z["keys"], z["vectors"].astype("float32") @ q):
        rel, sha = str(k).rsplit(":", 1)
        path = corpus.REPO / rel
        if not path.is_file():
            continue
        # only the vector of the file as it is now: an older cached version must not make it look near
        if rel not in head:
            head[rel] = embed.sha1(path.read_text(encoding="utf-8", errors="replace")[:FILE_HEAD])
        if sha == head[rel] and (rel not in best or float(s) > best[rel]):
            best[rel] = float(s)
    out["files"] = [{"path": p, "score": round(s, 3)}
                    for p, s in sorted(best.items(), key=lambda kv: -kv[1])[:top_files]]
    return out


def queries(top=20):
    """What the query logs say about the corpus. This is the loop that improves gists and gates.

    Three signals, and only the first two are actionable on their own:
      ZERO-HIT     a question nothing covered. Either a gist gap or a genuinely missing rule, and
                   reading the question is what says which.
      REPEATED     the same question asked in more than one folder. A rule that does not exist, or a
                   gate that should have injected one without anyone having to ask.
      STALE-INDEX  an answer produced against an index older than the corpus, so it may describe text
                   that has since changed.
    """
    sys.path.insert(0, str(HERE))
    import qlog

    logs = qlog.find_logs()
    built = {}
    for ns in ("rules", "history", "results"):
        _, _, man = index_mod.load(ns)
        built[ns] = man.get("built", "")

    zero, asked, stale, total = [], {}, [], 0
    ranks, never = [], []
    for p in logs:
        qs, ans = qlog.read_log(p)
        folder = p.parent.relative_to(corpus.REPO).as_posix()
        for q in qs:
            total += 1
            a = ans.get(q["id"])
            key = " ".join(q["q"].lower().split())
            asked.setdefault(key, set()).add(folder)
            ns = q.get("ns", "rules")
            if not a or not a.get("hits"):
                zero.append((q["ts"][:10], folder, ns, q["q"]))
            elif a.get("index_built") and built.get(ns, "") > a["index_built"]:
                stale.append((q["ts"][:10], folder, q["q"]))
            if a and a.get("hits"):
                op = a.get("opened") or []
                if op:
                    ranks.extend(o.get("rank", 0) for o in op)
                else:
                    never.append((q["ts"][:10], folder, a["hits"][0]["doc"], q["q"]))

    print("")
    print("== QUERIES: what the logs say ==")
    print("   %d log(s), %d question(s)" % (len(logs), total))
    print("")
    print("   ZERO-HIT, a gist gap or a missing rule")
    for ts, folder, ns, q in zero[:top]:
        print("     %s  %-26s [%s] %s" % (ts, folder[:26], ns[:7], q[:58]))
    if not zero:
        print("     none")
    print("")
    print("   REPEATED across folders")
    rep = [(k, v) for k, v in asked.items() if len(v) > 1]
    for k, v in sorted(rep, key=lambda kv: -len(kv[1]))[:top]:
        print("     %2d folders  %s" % (len(v), k[:70]))
    if not rep:
        print("     none")
    print("")
    print("   WHICH HIT WAS OPENED")
    if ranks:
        at_one = sum(1 for r in ranks if r == 1)
        print("     %d opened, %d of them the top hit (%.0f%%), mean rank %.2f"
              % (len(ranks), at_one, 100.0 * at_one / len(ranks), sum(ranks) / len(ranks)))
        print("     A low share at rank 1 means the corpus has the answer and the ranking buries it.")
    else:
        print("     nothing opened yet, so no ranking evidence either way")
    print("")
    print("   ANSWERED, NOTHING OPENED: the top hit may oversell its rule")
    for ts, folder, doc, q in never[:top]:
        print("     %s  %-24s %-34s %s" % (ts, folder[:24], doc[:34], q[:34]))
    if not never:
        print("     none")
    print("")
    print("   ANSWERED AGAINST AN INDEX OLDER THAN THE CORPUS")
    for ts, folder, q in stale[:top]:
        print("     %s  %-26s %s" % (ts, folder[:26], q[:58]))
    if not stale:
        print("     none")
    return zero, rep, stale, ranks, never


ORDER = """   1  FACTS      one statement in two rules      keep one owner, leave a pointer
   2  DUPES      two rules on one subject        merge, or confirm a deliberate split
   3  COHERENCE  a rule filed under the wrong area   refile it: rules.py move
   4  HUBS       a hub that no longer lists its area  add the missing line
   5  GATES      a gate that misses, or over-reaches  narrow or add the trigger"""


def refactor(with_gates=True, cut_facts=0.80, cut_dupes=0.82, worst=12, limit=25):
    """Every structural check, in the order they must be acted on, then one worklist.

    Acting out of order wastes the work: merging a fact changes both rules' whole-rule vectors, so
    DUPES is only meaningful after FACTS; moving a rule changes two area centroids and two hubs, so
    HUBS is only meaningful after COHERENCE; and a gate is written against a rule's final path and
    final content, so GATES is last.
    """
    print("")
    print("=" * 78)
    print("REFACTOR PASS - every finding is a CANDIDATE. Act in this order:")
    print(ORDER)
    print("=" * 78)

    f = facts(cut=cut_facts)
    d = dupes(cut=cut_dupes)
    c = coherence(worst=worst)
    h = hubs()
    g = ([], {})
    if with_gates:
        g = gates(limit=limit)
    else:
        print("\n== GATES: skipped, pass --gates to include it ==")
        print("   It embeds every repo file, so it is the slow one. Run it once the rules")
        print("   have stopped moving.")

    rows = [
        ("FACTS", len(f), "duplicated statement(s)", "facts --cut %.2f" % cut_facts),
        ("DUPES", len(d), "overlapping rule pair(s)", "dupes --cut %.2f" % cut_dupes),
        ("COHERENCE", len(c), "rule(s) nearer another area", "coherence"),
        ("HUBS", h, "rule(s) no hub names", "hubs"),
    ]
    if with_gates:
        strong = [m for m in g[0] if m[0] >= MISSING_COUNTED]
        rows.append(("GATES", len(strong), "missing gate(s) at %.2f+" % MISSING_COUNTED,
                     "gates / coverage"))
        rows.append(("GATES", len(g[1]), "over-broad gate candidate(s)", "gates / coverage"))

    print("")
    print("=" * 78)
    print("WORKLIST")
    for label, n, what, cmd in rows:
        mark = "  " if n == 0 else "->"
        print("   %s %-10s %4d  %-30s %s" % (mark, label, n, what, cmd))
    total = sum(r[1] for r in rows)
    if with_gates:
        print("")
        print("   %d weaker missing-gate pair(s) between %.2f and %.2f are listed above but not counted."
              % (len(g[0]) - len(strong), MISSING_FLOOR, MISSING_COUNTED))
    print("")
    print("   %d candidate(s) in total. None of them is a defect until a person reads the pair." % total)
    if sum(HIDDEN.values()):
        print("   %d more were read and kept on purpose, and are hidden. Keep one yourself:"
              % sum(HIDDEN.values()))
        print("     rules.py accept <kind> ... --why TEXT      (rules.py help accept)")
    print("")
    print("   Run one on its own from either side:")
    print("     python .claude/skills/rules-system/scripts/rules.py <command>")
    print("     python .claude/skills/vector-search/scripts/report.py <command>")
    print("   The rule-system names the gate report `coverage`, because `gates` there already")
    print("   prints the gate table.")
    print("=" * 78)
    return rows


JSON_REPORTS = ("facts", "dupes", "coherence", "hubs", "gates")


def findings_json(what, cut=None, **_):
    """One report's findings as plain data, with its printed text suppressed.

    For callers that act on the findings rather than read them, such as the rules-system audit
    worklist. Every finding is returned, not the top N the text shows, and accepted findings are
    already removed when --accepted was given. Missing gates carry `counted`, true at the cut the
    refactor worklist counts.
    """
    import contextlib
    import io

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        if what == "facts":
            pairs = facts(cut=cut if cut is not None else 0.78, top=0)
            found = [{"score": round(s, 3), "a": a[0], "line_a": a[1], "text_a": a[2],
                      "b": b[0], "line_b": b[1], "text_b": b[2]} for s, a, b in pairs]
        elif what == "dupes":
            pairs = dupes(cut=cut if cut is not None else 0.80, top=0)
            found = [{"score": round(s, 3), "a": a, "b": b} for s, a, b in pairs]
        elif what == "coherence":
            found = [{"rule": n, "area": own, "own": round(mine, 3), "nearer": other,
                      "other": round(s, 3), "gap": round(gap, 3)}
                     for gap, n, own, mine, other, s in coherence(worst=0)]
        elif what == "hubs":
            HUB_GAPS.clear()
            hubs()
            found = [{"hub": h, "missing": m} for h, m in sorted(HUB_GAPS.items())]
        elif what == "gates":
            missing, per = gates(limit=0)
            found = {"missing": [{"score": round(s, 3), "file": rel, "rule": rule,
                                  "counted": s >= MISSING_COUNTED} for s, rel, rule in missing],
                     "overbroad": [{"rule": rule, "files": len(ss), "mean": round(sum(ss) / len(ss), 3)}
                                   for rule, ss in sorted(per.items())]}
        else:
            raise ValueError(what)
    return {"report": what, "findings": found, "hidden": dict(HIDDEN)}


if __name__ == "__main__":
    argv = corpus.parse_repo(sys.argv[1:])
    what = argv[0] if argv else "all"

    def opt(flag, default):
        return type(default)(argv[argv.index(flag) + 1]) if flag in argv else default

    if "--accepted" in argv:
        load_accepted(argv[argv.index("--accepted") + 1])

    if what in ("nearest", "scope"):
        import json
        words, skip = [], False
        for a in argv[1:]:
            if skip:
                skip = False
                continue
            if a in ("--top", "--accepted"):
                skip = True
                continue
            if a.startswith("--"):
                continue
            words.append(a)
        if not words:
            raise SystemExit("usage: report.py nearest|scope [--json] [--top N] <text>")
        if what == "scope":
            found = scope(" ".join(words))
            if "--json" in argv:
                print(json.dumps(found))
            else:
                for h in found["rules"]:
                    print("  rule  %.3f  %s:%s" % (h["score"], h["rule"], h["line"]))
                for f in found["files"]:
                    print("  file  %.3f  %s" % (f["score"], f["path"]))
                if found["files_skipped"]:
                    print("  files skipped: %s" % found["files_skipped"])
            sys.exit(0)
        hits = nearest(" ".join(words), top=opt("--top", 5))
        if "--json" in argv:
            print(json.dumps(hits))
        else:
            for h in hits:
                print("  %.3f  %-46s %s" % (h["score"], "%s:%s" % (h["rule"], h["line"]), h["text"][:90]))
        sys.exit(0)
    if "--json" in argv and what in JSON_REPORTS:
        import json
        print(json.dumps(findings_json(what, cut=opt("--cut", 0.0) if "--cut" in argv else None)))
        sys.exit(0)
    if what == "refactor":
        refactor(with_gates="--gates" in argv,
                 cut_facts=opt("--cut", 0.80),
                 worst=opt("--worst", 12),
                 limit=opt("--limit", 25))
    if what in ("dupes", "all"):
        dupes(cut=opt("--cut", 0.80))
    if what in ("coherence", "all"):
        coherence(worst=opt("--worst", 15))
    if what in ("hubs", "all"):
        hubs()
    if what in ("gates", "all"):
        gates(limit=opt("--limit", 40))
    if what in ("facts", "all"):
        facts(cut=opt("--cut", 0.78))
    if what in ("queries", "all"):
        queries(top=opt("--top", 20))
