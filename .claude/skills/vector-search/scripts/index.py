"""Build or refresh a vector index. Three corpora plus one index per skill, never mixed.

    python .claude/skills/vector-search/scripts/index.py                  # rules, refresh what changed
    python .claude/skills/vector-search/scripts/index.py --ns history
    python .claude/skills/vector-search/scripts/index.py --ns results
    python .claude/skills/vector-search/scripts/index.py --ns skills      # every skill, one file set each
    python .claude/skills/vector-search/scripts/index.py --ns skill:rules-system
    python .claude/skills/vector-search/scripts/index.py --ns all --rebuild
    python .claude/skills/vector-search/scripts/index.py --status [--ns <ns>] [--json]

`--status` says which indexes are behind their corpus, from content hashes alone. It loads no model
and embeds nothing, so knowledge upkeep can ask it at every session start for under a second.

A skill index lives in data/skills/<name>/, so each skill's vectors are their own files: one skill
can be rebuilt, inspected or deleted without touching another, and a skill that is removed from disk
has its index pruned on the next `--ns skills` run.

WHY THREE FILES AND NOT ONE
---------------------------
A rule says what to DO and is compulsory. A history event says what HAPPENED, with a run id. A
results abstract is the ground truth a rule was distilled from. In one index a run record could
outrank the rule governing the same subject, which inverts the arrangement the whole repo rests on.
Separate, a query is aimed and an answer names its corpus.

Incremental by content hash, so editing one rule re-embeds one rule. A model or dimension change
invalidates that namespace, because vectors from two models are not comparable and comparing them
anyway is the silent-wrong-answer failure this repo keeps paying for.
"""

import json
import pathlib
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import corpus                                                     # noqa: E402
import embed                                                      # noqa: E402

DATA = HERE.parent / "data"
NAMESPACES = ("rules", "history", "results")
SKILL_PREFIX = "skill:"
SKILL_DATA = DATA / "skills"


def skill_namespaces():
    """`skill:<name>` for every skill with something to index, in name order."""
    return [SKILL_PREFIX + n for n in corpus.skill_names()]


def expand(ns: str):
    """A command-line namespace to the namespaces it means. `all` includes every skill."""
    if ns == "all":
        return list(NAMESPACES) + skill_namespaces()
    if ns == "skills":
        return skill_namespaces()
    if ns in NAMESPACES:
        return [ns]
    if ns.startswith(SKILL_PREFIX) and ns[len(SKILL_PREFIX):] in corpus.skill_names():
        return [ns]
    raise SystemExit("unknown namespace: %s\nknown: %s, skills, all, or skill:<name> for one of: %s"
                     % (ns, ", ".join(NAMESPACES), ", ".join(corpus.skill_names())))


def paths(ns: str):
    if ns == "rules":                      # the original filenames, so nothing already built moves
        return DATA / "vectors.npz", DATA / "manifest.json"
    if ns.startswith(SKILL_PREFIX):
        d = SKILL_DATA / ns[len(SKILL_PREFIX):]
        return d / "vectors.npz", d / "manifest.json"
    return DATA / ("vectors-%s.npz" % ns), DATA / ("manifest-%s.json" % ns)


def prune_skills():
    """Delete the index of a skill that is no longer on disk. Only ever inside data/skills/."""
    import shutil
    if not SKILL_DATA.is_dir():
        return []
    live = set(corpus.skill_names())
    gone = [d for d in SKILL_DATA.iterdir() if d.is_dir() and d.name not in live]
    for d in gone:
        shutil.rmtree(d)
    return [d.name for d in gone]


def _documents(ns: str):
    """[(key, text, meta), ...] for the namespace. The key carries a content hash, so a changed
    document gets a new key and everything else is reused."""
    docs = []
    if ns == "rules":
        gists = corpus.gates()
        for name, whole, lines in corpus.rule_texts():
            docs.append(("R|%s|%s" % (name, embed.sha1(whole)), whole,
                         {"kind": "rule", "rule": name, "line": 0}))
            _, gist = gists.get(name, ("", ""))
            if gist:
                docs.append(("G|%s|%s" % (name, embed.sha1(gist)), gist,
                             {"kind": "gist", "rule": name, "line": 0, "text": gist}))
            for no, body in lines:
                docs.append(("L|%s|%d|%s" % (name, no, embed.sha1(body)), body,
                             {"kind": "line", "rule": name, "line": no, "text": body}))
    elif ns == "history":
        for eid, text, rel, status, kind in corpus.history_events():
            docs.append(("H|%s|%s" % (eid, embed.sha1(text)), text,
                         {"kind": "event", "id": eid, "path": rel, "status": status,
                          "event_kind": kind, "text": text[:400]}))
    elif ns.startswith(SKILL_PREFIX):
        name = ns[len(SKILL_PREFIX):]
        for rel, line, label, text in corpus.skill_chunks(name):
            head = "%s / %s%s" % (name, rel, (" / " + label) if label else "")
            docs.append(("K|%s|%d|%s" % (rel, line, embed.sha1(text)), head + "\n" + text,
                         {"kind": "chunk", "skill": name, "path": rel, "line": line,
                          "label": label, "text": text[:400]}))
    elif ns == "results":
        for run, text, rel in corpus.results_docs():
            docs.append(("S|%s|%s" % (run, embed.sha1(text)), text,
                         {"kind": "result", "run": run, "path": rel, "text": text[:400]}))
    else:
        raise SystemExit("unknown namespace: %s" % ns)
    return docs


def build(ns: str = "rules", rebuild: bool = False) -> dict:
    import numpy as np

    vec_path, man_path = paths(ns)
    vec_path.parent.mkdir(parents=True, exist_ok=True)
    emb = embed.Embedder()
    fp = emb.fingerprint()
    old = embed.load_manifest(man_path)
    reusable = {}
    if not rebuild and old.get("model") == fp and vec_path.is_file():
        z = np.load(vec_path, allow_pickle=False)
        for k, row in zip(list(z["keys"]), z["vectors"]):
            reusable[str(k)] = row

    docs = _documents(ns)
    keys = [d[0] for d in docs]
    meta = {d[0]: d[2] for d in docs}
    todo = [(k, t) for k, t, _ in docs if k not in reusable]
    t0 = time.time()
    if todo:
        new = emb.documents([t for _, t in todo])
        for (k, _), row in zip(todo, new):
            reusable[k] = row
    took = time.time() - t0

    mat = (np.stack([reusable[k] for k in keys]) if keys
           else np.zeros((0, fp["dim"]))).astype(np.float16)
    np.savez_compressed(vec_path, keys=np.array(keys), vectors=mat)
    manifest = {"namespace": ns, "model": fp, "built": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "documents": len({m.get("rule") or m.get("id") or m.get("run") or m.get("path")
                                  for m in meta.values()}),
                "vectors": len(keys), "embedded_this_run": len(todo),
                "seconds_embedding": round(took, 2), "meta": meta}
    if ns == "rules":
        manifest["rules"] = len(corpus.rule_texts())
    man_path.write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    return manifest


def load(ns: str = "rules"):
    """(keys, matrix, manifest) or (None, None, {}) when that namespace is missing."""
    import numpy as np

    vec_path, man_path = paths(ns)
    man = embed.load_manifest(man_path)
    if not man or not vec_path.is_file():
        return None, None, {}
    z = np.load(vec_path, allow_pickle=False)
    return [str(k) for k in z["keys"]], z["vectors"].astype("float32"), man


def _doc_name(key: str) -> str:
    """The document a vector key belongs to: a rule name, an event id, a run, or a skill file path."""
    parts = key.split("|")
    return parts[1] if len(parts) > 2 else key


def status(ns: str = "rules") -> dict:
    """Is this namespace's index behind its corpus? Hashes only; no model is loaded.

    `changed` names every document whose text is new or different since the build, `removed` every
    document the index still holds and the corpus no longer does. An edited document is only in
    `changed`, because its old key disappearing is the same edit.
    """
    vec_path, man_path = paths(ns)
    man = embed.load_manifest(man_path)
    if not man or not vec_path.is_file():
        return {"ns": ns, "state": "missing", "built": "", "changed": [], "removed": []}
    have = set(man.get("meta", {}))
    want = {d[0] for d in _documents(ns)}
    changed = sorted({_doc_name(k) for k in want - have})
    removed = sorted({_doc_name(k) for k in have - want} - set(changed)
                     - {_doc_name(k) for k in want})
    # build() throws every vector away when the model changed, so status must call that stale too
    model_changed = False
    if man.get("model"):
        fp = embed.fingerprint_for()
        model_changed = fp is not None and man["model"] != fp
    out = {"ns": ns, "state": "stale" if changed or removed or model_changed else "current",
           "built": man.get("built", ""), "changed": changed, "removed": removed}
    if model_changed:
        out["reason"] = "model changed: every vector is rebuilt on the next index run"
    return out


def stale_rules(man: dict):
    """Rules whose text no longer matches the hash in the index."""
    have = {(v["rule"], v["kind"]): k for k, v in man.get("meta", {}).items() if v.get("rule")}
    out = []
    for name, whole, _ in corpus.rule_texts():
        k = have.get((name, "rule"))
        if not k or not k.endswith(embed.sha1(whole)):
            out.append(name)
    return out


if __name__ == "__main__":
    argv = corpus.parse_repo(sys.argv[1:])
    ns = argv[argv.index("--ns") + 1] if "--ns" in argv else "rules"
    if "--status" in argv:
        rows = [status(one) for one in (expand(ns) if "--ns" in argv else NAMESPACES)]
        if "--json" in argv:
            print(json.dumps(rows))
        else:
            for r in rows:
                detail = ""
                if r["state"] == "stale":
                    detail = "  %d changed, %d removed since %s" % (len(r["changed"]), len(r["removed"]),
                                                                    r["built"])
                    if r.get("reason"):
                        detail += "; " + r["reason"]
                print("%-30s %s%s" % (r["ns"], r["state"], detail))
        sys.exit(0)
    todo = expand(ns)
    if ns in ("all", "skills"):
        for name in prune_skills():
            print("pruned the index of %s, which is no longer on disk" % name)
    for one in todo:
        m = build(one, "--rebuild" in argv)
        v, _ = paths(one)
        print("%-30s documents %4d   vectors %5d   embedded now %5d   %7.1fs   %7.1f KB"
              % (one, m["documents"], m["vectors"], m["embedded_this_run"],
                 m["seconds_embedding"], v.stat().st_size / 1024))
