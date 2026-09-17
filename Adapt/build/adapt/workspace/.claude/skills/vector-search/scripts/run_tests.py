"""Tests. The golden set is the thing that decides whether this is worth having.

    python .claude/skills/vector-search/scripts/run_tests.py

Two kinds of check. Unit checks on the plumbing, which need no model and run in a temp folder. And the
GOLDEN SET: real questions in the words someone would actually use, each naming the rule that must
come back. Recall at 1 and at 3 are reported, and three entries expect NOTHING - the retriever that
always finds something is the failure mode worth catching early.
"""

import json
import pathlib
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import corpus                                                     # noqa: E402
import embed                                                      # noqa: E402
import index as index_mod                                         # noqa: E402
import search as search_mod                                       # noqa: E402

PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  PASS  %s" % name)
    else:
        FAIL += 1
        print("  FAIL  %s   %s" % (name, detail))


def unit_checks():
    print("plumbing")
    g = corpus.gates()
    check("gates parse out of rules/INDEX.md, one line per rule at least", len(g) >= len(corpus.rule_texts()) > 0, len(g))
    check("a known rule has a gate", "lifecycle/handoff.rule.md" in g)
    rules = corpus.rule_texts()
    check("every rule on disk is in the corpus", len(rules) == len(list((corpus.REPO / "rules").rglob("*.rule.md"))), len(rules))
    name, whole, lines = rules[0]
    check("a rule yields its own lines", len(lines) >= 2, (name, len(lines)))
    check("short stub lines are dropped", all(len(t) >= 25 for _, t in lines))
    check("hub rules are identified", corpus.is_hub("xs/hub.rule.md")
          and not corpus.is_hub("xs/guard.rule.md"))
    check("sha1 is stable", embed.sha1("abc") == embed.sha1("abc"))
    check("sha1 separates texts", embed.sha1("abc") != embed.sha1("abd"))

    keys, mat, man = index_mod.load()
    check("an index exists", keys is not None)
    if keys is None:
        return
    check("index has a rule vector per rule",
          sum(1 for k in keys if k.startswith("R|")) == man["rules"], man["rules"])
    check("vectors are unit length", abs(float((mat[0] ** 2).sum()) - 1.0) < 0.01,
          float((mat[0] ** 2).sum()))
    check("manifest pins the model", set(man["model"]) >= {"graph", "dim", "graph_sha256_16"})
    stale = index_mod.stale_rules(man)
    check("index is current for every rule", not stale, stale[:4])


def skill_checks():
    """Per-skill indexes: chunking, what is skipped, one file set per skill, pruning, one hit per file.

    Built against a FAKE embedder in a temp folder. Real vectors are not needed to prove that a skill
    gets its own files, that a second build embeds nothing, or that a deleted skill loses its index.
    """
    import shutil
    import tempfile

    import numpy as np

    print("")
    print("skill indexes")

    # ---- markdown: cut at headings, labelled by the trail, fences respected
    md = ("# Top\n\nintro paragraph long enough to stand as a section on its own, " + "x " * 60 + "\n\n"
          "## Short\n\n## Real\n\n" + "a real body line. " * 20 + "\n\n```\n# not a heading\n```\n\n"
          "### Deep\n\n" + "deep body. " * 30 + "\n\n## Long\n\n" + ("para " * 60 + "\n\n") * 12)
    chunks = corpus.md_chunks(md)
    labels = [c[1] for c in chunks]
    check("a markdown chunk is labelled by its heading trail", "Top > Real > Deep" in labels, labels)
    check("a heading inside a code fence is not a heading", not any("not a heading" == l for l in labels))
    check("a heading with no body joins the next section",
          not any(l == "Top > Short" for l in labels) and any("## Short" in c[2] for c in chunks))
    check("a long section is cut into several chunks", labels.count("Top > Long") >= 2, labels)
    check("no chunk passes the size cap", all(len(c[2]) <= corpus.CHUNK_MAX for c in chunks),
          max(len(c[2]) for c in chunks))
    check("a chunk knows its starting line", chunks[0][0] == 1 and all(c[0] >= 1 for c in chunks))

    # ---- python: cut at definitions, big classes cut per method
    big_method = "        x = 1\n" * 150
    py = ('"""module doc long enough to count as something worth retrieving on its own merits."""\n'
          "import os\n\nLIMIT = 3\n\n\n# a comment that belongs to the function below it\n"
          "def small(a):\n    return a + 1  # " + "padding " * 10 + "\n\n\n"
          "class Big:\n    \"\"\"doc for the class, which is long enough to keep.\"\"\"\n\n"
          "    def one(self):\n" + big_method + "\n    def two(self):\n" + big_method)
    chunks = corpus.py_chunks(py)
    labels = [c[1] for c in chunks]
    check("module-level code is labelled module", labels[0] == "module", labels)
    check("a function is labelled by its name", "small" in labels, labels)
    check("the comment above a function travels with it",
          any(c[1] == "small" and c[2].startswith("# a comment") for c in chunks))
    check("an oversized class is cut per method", "Big.one" in labels and "Big.two" in labels, labels)
    broken = corpus.py_chunks("def broken(:\n" + "    pass  # filler words here\n" * 10)
    check("a file that does not parse still yields chunks", len(broken) >= 1, broken)

    # ---- a temp skills tree
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="skill_index_"))
    real = (corpus.SKILLS, index_mod.DATA, index_mod.SKILL_DATA, embed.Embedder)

    class FakeEmb:
        def __init__(self, *a, dim=4, **k):
            self.dim = 4
            FakeEmb.last = self
            self.embedded = 0

        def fingerprint(self):
            return {"graph": "fake", "graph_sha256_16": "fake", "dim": 4}

        def documents(self, texts, batch=16):
            self.embedded += len(texts)
            FakeEmb.total = getattr(FakeEmb, "total", 0) + len(texts)
            return np.tile(np.array([1.0, 0, 0, 0], dtype="float32"), (len(texts), 1))

        def queries(self, texts, batch=16):
            return np.tile(np.array([1.0, 0, 0, 0], dtype="float32"), (len(texts), 1))

    try:
        skills = tmp / "skills"
        a = skills / "alpha"
        (a / "scripts").mkdir(parents=True)
        (a / "data").mkdir()
        (a / "scripts" / "_common" / "project_snapshot").mkdir(parents=True)
        body = "useful words about restarting the game after a rebuild. " * 8
        (a / "SKILL.md").write_text("# Alpha\n\n" + body + "\n\n## Part\n\n" + body, encoding="utf-8")
        (a / "scripts" / "tool.py").write_text('def restart():\n    """' + body + '"""\n', encoding="utf-8")
        (a / "data" / "out.md").write_text("# output\n\n" + body, encoding="utf-8")
        (a / "scripts" / "_common" / "project_snapshot" / "copy.py").write_text("x = 1  # " + body,
                                                                                  encoding="utf-8")
        (a / "picture.png").write_bytes(b"\x89PNG" + b"0" * 200)
        (skills / "beta").mkdir()
        (skills / "beta" / "SKILL.md").write_text("# Beta\n\n" + body, encoding="utf-8")
        (skills / "empty").mkdir()

        corpus.SKILLS = skills
        index_mod.DATA = tmp / "data"
        index_mod.SKILL_DATA = tmp / "data" / "skills"
        embed.Embedder = FakeEmb

        files = [p.relative_to(a).as_posix() for p in corpus.skill_files("alpha")]
        check("a skill's docs and code are indexed", sorted(files) == ["SKILL.md", "scripts/tool.py"], files)
        check("data/, vendored snapshots and images are not", len(files) == 2, files)
        check("an empty skill folder gets no index", corpus.skill_names() == ["alpha", "beta"],
              corpus.skill_names())

        va, _ = index_mod.paths("skill:alpha")
        vb, _ = index_mod.paths("skill:beta")
        check("each skill has its OWN vector file", va != vb and va.parent.name == "alpha"
              and va.parent.parent == index_mod.SKILL_DATA, (va, vb))
        check("`skills` means every skill", index_mod.expand("skills") == ["skill:alpha", "skill:beta"])
        check("`all` means the three corpora and every skill",
              index_mod.expand("all") == ["rules", "history", "results", "skill:alpha", "skill:beta"])
        try:
            index_mod.expand("skill:nope")
            check("an unknown skill namespace is refused", False)
        except SystemExit:
            check("an unknown skill namespace is refused", True)

        m1 = index_mod.build("skill:alpha")
        index_mod.build("skill:beta")
        check("a skill build writes its own files", va.is_file() and vb.is_file())
        check("its manifest counts files as documents", m1["documents"] == 2, m1["documents"])
        m2 = index_mod.build("skill:alpha")
        check("a second build embeds nothing", m2["embedded_this_run"] == 0, m2["embedded_this_run"])
        keys, _, man = index_mod.load("skill:alpha")
        meta = man["meta"][keys[0]]
        check("a chunk records skill, path, line and label",
              {"skill", "path", "line", "label", "text"} <= set(meta), meta)

        hits, _ = search_mod.query("restart the game", ns="skills")
        docs = [h["rule"].rsplit(":", 1)[0] for h in hits]
        check("`--skill all` searches every skill index", {"alpha/SKILL.md", "beta/SKILL.md"} <= set(docs), docs)
        check("one hit per FILE", len(docs) == len(set(docs)), docs)
        check("a hit names skill, path and line", hits and hits[0]["skill"] and ":" in hits[0]["rule"])
        hits, _ = search_mod.query("restart the game", ns="skill:beta")
        check("one skill's search stays inside that skill", all(h["skill"] == "beta" for h in hits), hits)

        shutil.rmtree(skills / "beta")
        gone = index_mod.prune_skills()
        check("a skill removed from disk loses its index", gone == ["beta"] and not vb.parent.exists(), gone)
        check("and nothing else is touched", va.is_file())

        check("--skill all parses to skills", search_mod.parse_ns(["--skill", "all", "q"]) == ("skills", ["q"]))
        check("--skill <name> parses to that skill",
              search_mod.parse_ns(["q", "--skill", "alpha"]) == ("skill:alpha", ["q"]))
        check("--history still parses", search_mod.parse_ns(["--history", "q"]) == ("history", ["q"]))
        try:
            search_mod.parse_ns(["--skill", "nope", "q"])
            check("an unknown skill is refused by name", False)
        except SystemExit:
            check("an unknown skill is refused by name", True)
        check("every skill shares one floor", search_mod.floor_for("skill:alpha") == search_mod.FLOORS["skill"]
              == search_mod.floor_for("skills"))
    finally:
        corpus.SKILLS, index_mod.DATA, index_mod.SKILL_DATA, embed.Embedder = real
        shutil.rmtree(tmp, ignore_errors=True)


def status_checks():
    """index.py --status: from hashes alone, which documents changed since a build."""
    import shutil
    import tempfile

    print("")
    print("index status")
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="index_status_"))
    real = index_mod.DATA
    try:
        index_mod.DATA = tmp
        check("an unbuilt namespace is missing", index_mod.status("history")["state"] == "missing")
        docs = index_mod._documents("history")
        vec, man = index_mod.paths("history")
        vec.write_bytes(b"not read by status")
        meta = {d[0]: {} for d in docs}
        man.write_text(json.dumps({"built": "2026-09-12T00:00:00", "meta": meta}), encoding="utf-8")
        s = index_mod.status("history")
        check("an index holding exactly the corpus is current", s["state"] == "current", s)

        edited = docs[0][0]
        name = edited.split("|")[1]
        meta.pop(edited)
        meta[edited.rsplit("|", 1)[0] + "|0000000000000000"] = {}
        meta["H|2020-01-01-gone|1111111111111111"] = {}
        man.write_text(json.dumps({"built": "2026-09-12T00:00:00", "meta": meta}), encoding="utf-8")
        s = index_mod.status("history")
        check("an edited document is stale and named once, as changed",
              s["state"] == "stale" and s["changed"] == [name] and name not in s["removed"], s)
        check("a document gone from the corpus is named as removed", s["removed"] == ["2020-01-01-gone"], s)
        real_fp = embed.fingerprint_for
        try:
            embed.fingerprint_for = lambda *a, **k: {"graph_sha256_16": "the-model-now"}
            man.write_text(json.dumps({"built": "2026-09-12T00:00:00", "meta": {d[0]: {} for d in docs},
                                       "model": {"graph_sha256_16": "the-model-then"}}), encoding="utf-8")
            s = index_mod.status("history")
            check("an index built by another model is stale, and says why", s["state"] == "stale"
                  and "model changed" in s.get("reason", "") and not s["changed"], s)
            embed.fingerprint_for = lambda *a, **k: None
            check("with the model folder missing, status judges by hashes alone",
                  index_mod.status("history")["state"] == "current")
        finally:
            embed.fingerprint_for = real_fp
        import subprocess
        probe = ("import sys; sys.path.insert(0, %r); import index; index.status('rules'); "
                 "print(sorted(m for m in ('onnxruntime', 'tokenizers') if m in sys.modules))" % str(HERE))
        out = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True, timeout=300)
        check("status loads no model: onnxruntime and tokenizers stay unimported", out.returncode == 0
              and out.stdout.strip().endswith("[]"), (out.stdout[-200:], out.stderr[-300:]))
    finally:
        index_mod.DATA = real
        shutil.rmtree(tmp, ignore_errors=True)


def nearest_checks():
    """report.nearest: raw cosine, best vector per rule, top honoured. Fake embedder, temp index."""
    import shutil
    import tempfile

    import numpy as np

    import report

    print("")
    print("nearest rules")
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="nearest_"))
    real = (index_mod.DATA, embed.Embedder)

    class FakeEmb:
        def __init__(self, *a, **k):
            pass

        def fingerprint(self):
            return {"graph": "fake", "graph_sha256_16": "fake", "dim": 4}

        def documents(self, texts, batch=16):
            return np.tile(np.array([1.0, 0, 0, 0], dtype="float32"), (len(texts), 1))

    try:
        index_mod.DATA = tmp
        keys = ["R|a/x.rule.md|h1", "L|a/x.rule.md|2|h2", "L|b/y.rule.md|3|h3", "L|c/z.rule.md|4|h4"]
        rows = np.array([[0.6, 0.8, 0, 0], [1, 0, 0, 0], [0.8, 0.6, 0, 0], [0, 1, 0, 0]], dtype="float16")
        vec, man = index_mod.paths("rules")
        np.savez_compressed(vec, keys=np.array(keys), vectors=rows)
        man.write_text(json.dumps({"model": {"graph_sha256_16": "fake", "dim": 4}, "meta": {
            keys[0]: {"kind": "rule", "rule": "a/x.rule.md", "line": 0},
            keys[1]: {"kind": "line", "rule": "a/x.rule.md", "line": 2, "text": "the same statement"},
            keys[2]: {"kind": "line", "rule": "b/y.rule.md", "line": 3, "text": "a near statement"},
            keys[3]: {"kind": "line", "rule": "c/z.rule.md", "line": 4, "text": "unrelated"}}}),
            encoding="utf-8")
        embed.Embedder = FakeEmb
        hits = report.nearest("anything", top=5)
        check("the nearest rule comes first, by its best vector", hits[0]["rule"] == "a/x.rule.md"
              and hits[0]["score"] == 1.0 and hits[0]["line"] == 2, hits[:1])
        check("one entry per rule, not per vector", [h["rule"] for h in hits]
              == ["a/x.rule.md", "b/y.rule.md", "c/z.rule.md"], hits)
        check("scores are raw cosine, with no ranking bonus", hits[1]["score"] == 0.8, hits[1])
        check("top is honoured", len(report.nearest("anything", top=1)) == 1)

        real_repo = corpus.REPO
        try:
            corpus.REPO = tmp
            (tmp / "ai").mkdir()
            (tmp / "ai" / "near.py").write_text("x", encoding="utf-8")
            (tmp / "ai" / "far.py").write_text("x", encoding="utf-8")
            now = embed.sha1("x")
            np.savez_compressed(tmp / "filecache.npz",
                                keys=np.array(["ai/near.py:" + now, "ai/far.py:" + now, "gone/old.py:h3",
                                               "ai/near.py:0ldversion0000000"]),
                                vectors=np.array([[0.8, 0.6, 0, 0], [0, 1, 0, 0], [1, 0, 0, 0], [1, 0, 0, 0]],
                                                 dtype="float16"),
                                fingerprint=np.array("?|fake|4"))
            found = report.scope("anything")
            paths = [f["path"] for f in found["files"]]
            check("scope ranks live files in the same pass", paths == ["ai/near.py", "ai/far.py"], found["files"])
            check("a cached file that no longer exists is left out", "gone/old.py" not in paths, paths)
            check("a file is scored by its current text only, never an older cached version",
                  found["files"][0]["score"] == 0.8, found["files"])
            check("scope carries the rules too", found["rules"][0]["rule"] == "a/x.rule.md")
            np.savez_compressed(tmp / "filecache.npz", keys=np.array(["ai/near.py:h1"]),
                                vectors=np.array([[1, 0, 0, 0]], dtype="float16"), fingerprint=np.array("x|y|4"))
            other = report.scope("anything")
            check("a file cache from another model is skipped, and says so",
                  other["files_skipped"] and not other["files"], other)
        finally:
            corpus.REPO = real_repo
    finally:
        index_mod.DATA, embed.Embedder = real
        shutil.rmtree(tmp, ignore_errors=True)


def hit_matches(name, wanted):
    """A golden answer names a rule, a run, or for a skill a FILE: any chunk of that file will do."""
    return any(name == w or name.startswith(w + ":") for w in wanted)


def golden():
    print("\ngolden set")
    items = [json.loads(l) for l in
             (HERE.parent / "golden.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    expect = [i for i in items if i["want"]]
    nothing = [i for i in items if not i["want"]]
    at1 = at3 = 0
    misses = []
    times = []
    for i in expect:
        hits, ms = search_mod.query(i["q"], top=3, ns=i.get("ns", "rules"))
        times.append(ms)
        names = [h["rule"] for h in hits]
        ok = i["want"] if isinstance(i["want"], list) else [i["want"]]
        if names[:1] and hit_matches(names[0], ok):
            at1 += 1
        if any(hit_matches(n, ok) for n in names):
            at3 += 1
        else:
            misses.append((i["q"], " or ".join(ok), names))
    for i in nothing:
        hits, ms = search_mod.query(i["q"], top=3, ns=i.get("ns", "rules"))
        times.append(ms)
        check("refuses off-topic in %-7s %s" % (i.get("ns", "rules"), i["q"][:34]), not hits,
              hits[0]["rule"] + " %.2f" % hits[0]["score"] if hits else "")

    n = len(expect)
    print("\n  recall@1 %d/%d = %.0f%%   recall@3 %d/%d = %.0f%%"
          % (at1, n, 100 * at1 / n, at3, n, 100 * at3 / n))
    print("  median query %.0f ms, slowest %.0f ms" % (sorted(times)[len(times) // 2], max(times)))
    if misses:
        print("\n  misses:")
        for q, w, got in misses:
            print("    %-52s wanted %s" % (q[:52], w))
            print("      got %s" % ", ".join(got[:3]))
    # recall@3 is the SHIP GATE, because the tool returns five hits and a reader scans them. recall@1
    # is a regression guard at a deliberately lower bar: several rules legitimately touch one subject
    # in this corpus, so which of them ranks first is often a coin toss between two right answers.
    check("recall@3 is at least 90%%", at3 / n >= 0.90, "%.0f%%" % (100 * at3 / n))
    check("recall@1 is at least 60%%", at1 / n >= 0.60, "%.0f%%" % (100 * at1 / n))


def query_log_checks():
    """The passive layer: ask.py writes a usable record, the hook surfaces it once and never twice."""
    import json
    import os
    import shutil
    import subprocess
    import tempfile

    print("")
    print("query log")
    import ask as ask_mod
    import qlog

    tmp = pathlib.Path(tempfile.mkdtemp(prefix="qlog_test_"))
    state = tmp / "surfaced.json"
    try:
        hits = [{"rule": "x/y.rule.md", "score": 0.5, "gate": "`**/*.xs`", "line": "a line"}]
        p = ask_mod.append(tmp, "a question", "rules", hits, 123.0)
        check("ask writes a log beside the work", p.is_file())
        lines = [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
        check("two lines per question, the query and its answer", len(lines) == 2, len(lines))
        q, a = lines
        check("the query line carries the question and its namespace",
              q["kind"] == "query" and q["ns"] == "rules" and q["q"] == "a question", q)
        check("the answer names the query it answers", a["for"] == q["id"], a.get("for"))
        for field in ("ns", "floor", "model", "index_built"):
            check("the answer carries %-11s without which it is not evidence" % field,
                  field in a, sorted(a))

        with open(p, "a", encoding="utf-8") as f:
            f.write("not json at all\n")
        qs, ans = qlog.read_log(p)
        check("a malformed line is skipped, never fatal", len(qs) == 1 and len(ans) == 1)

        hook = pathlib.Path(__file__).resolve().parents[3] / "hooks" / "query_log.py"
        env = dict(os.environ)
        env["VECTOR_SEARCH_STATE"] = str(state)
        payload = json.dumps({"tool_name": "Bash", "cwd": str(tmp),
                              "tool_input": {"command": "python ask.py \"a question\""}})

        def run_hook(pl=payload):
            r = subprocess.run([sys.executable, str(hook)], input=pl,
                               capture_output=True, text=True, env=env)
            return r.stdout.strip()

        first = run_hook()
        check("the hook surfaces the answer", "VECTOR SEARCH" in first, first[:60])
        check("and it carries the hit", "x/y.rule.md" in first, first[:80])
        check("the SAME answer is not surfaced twice", run_hook() == "", "repeated")

        other = json.dumps({"tool_name": "Bash", "cwd": str(tmp),
                            "tool_input": {"command": "echo nothing to do with it"}})
        check("an unrelated command says nothing", run_hook(other) == "")

        empty = pathlib.Path(tempfile.mkdtemp(prefix="qlog_empty_"))
        none_there = json.dumps({"tool_name": "Bash", "cwd": str(empty),
                                 "tool_input": {"command": "python ask.py \"x\""}})
        check("no log in the folder means silence, not an error", run_hook(none_there) == "")
        shutil.rmtree(empty, ignore_errors=True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    check("digest runs over a real folder", qlog.digest(str(corpus.REPO / "mechanics")) == 0)
    check("collect merges every log without error", qlog.collect() == 0)


def opened_checks():
    """The opened hook: attributes a Read to the answer that returned it, once, and only in window."""
    import json
    import os
    import shutil
    import subprocess
    import tempfile
    import time

    print("")
    print("opened hook")
    import ask as ask_mod
    import qlog

    hook = pathlib.Path(__file__).resolve().parents[3] / "hooks" / "query_opened.py"
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="opened_test_"))
    try:
        rules_dir = tmp / "rules" / "xs"
        rules_dir.mkdir(parents=True)
        target = rules_dir / "thing.rule.md"
        target.write_text("RULE xs/thing - a fixture\n- one line\n", encoding="utf-8")
        other = tmp / "unrelated.md"
        other.write_text("nothing to do with it\n", encoding="utf-8")

        hits = [{"rule": "xs/thing.rule.md", "score": 0.61, "gate": "`**/*.xs`", "line": "one line"},
                {"rule": "xs/other.rule.md", "score": 0.44, "gate": "`**/*.xs`", "line": "two"}]
        log = ask_mod.append(tmp, "a question", "rules", hits, 42.0)

        def read_hook(path, cwd=tmp):
            payload = json.dumps({"tool_name": "Read", "cwd": str(cwd),
                                  "tool_input": {"file_path": str(path)}})
            subprocess.run([sys.executable, str(hook)], input=payload,
                           capture_output=True, text=True)

        read_hook(other)
        _, ans = qlog.read_log(log)
        check("reading an unrelated file records nothing",
              not any(a.get("opened") for a in ans.values()))

        read_hook(target)
        _, ans = qlog.read_log(log)
        op = [o for a in ans.values() for o in a.get("opened", [])]
        check("reading a returned rule records it", len(op) == 1, op)
        check("and records the RANK it was returned at", op and op[0]["rank"] == 1, op)
        check("and how long after the question", op and "after_s" in op[0], op)

        read_hook(target)
        _, ans = qlog.read_log(log)
        op = [o for a in ans.values() for o in a.get("opened", [])]
        check("reading it twice records once", len(op) == 1, len(op))

        # an answer older than the window must not be credited with a later read
        stale_dir = pathlib.Path(tempfile.mkdtemp(prefix="opened_stale_"))
        (stale_dir / "rules" / "xs").mkdir(parents=True)
        st = stale_dir / "rules" / "xs" / "thing.rule.md"
        st.write_text("RULE xs/thing - fixture\n", encoding="utf-8")
        old_ts = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(time.time() - 48 * 3600))
        (stale_dir / "QUERIES.jsonl").write_text(
            json.dumps({"kind": "query", "id": "old-1", "ts": old_ts, "ns": "rules",
                        "q": "old question"}) + "\n"
            + json.dumps({"kind": "answer", "for": "old-1", "ts": old_ts, "ns": "rules",
                          "floor": 0.4, "model": "x", "index_built": old_ts,
                          "hits": [{"doc": "xs/thing.rule.md", "score": 0.5, "where": "", "line": ""}]})
            + "\n", encoding="utf-8")
        read_hook(st, cwd=stale_dir)
        _, ans = qlog.read_log(stale_dir / "QUERIES.jsonl")
        check("an answer outside the window is not credited",
              not any(a.get("opened") for a in ans.values()))
        shutil.rmtree(stale_dir, ignore_errors=True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def report_checks():
    """The maintenance reports: present, ordered, and the file cache behaves."""
    import shutil
    import tempfile

    import numpy as np

    print("")
    print("maintenance reports")
    import report
    import index as index_mod
    import corpus

    for name in ("facts", "dupes", "coherence", "hubs", "gates", "queries", "refactor"):
        check(f"report.{name} exists", callable(getattr(report, name, None)))

    # The worklist order is load-bearing, not presentation: acting out of order invalidates the
    # passes that follow. If a line ever goes missing from ORDER, the pass stops teaching the order.
    for step in ("FACTS", "DUPES", "COHERENCE", "HUBS", "GATES"):
        check(f"the refactor order names {step}", step in report.ORDER)

    class FakeEmb:
        """Counts what it is asked to embed, and never loads a model."""

        def __init__(self):
            self.calls = 0
            self.texts = 0

        def queries(self, texts, batch=16):
            self.calls += 1
            self.texts += len(texts)
            return np.eye(4, dtype="float32")[[i % 4 for i in range(len(texts))]]

    tmp = pathlib.Path(tempfile.mkdtemp(prefix="report_cache_"))
    real_repo, real_data = corpus.REPO, index_mod.DATA
    try:
        corpus.REPO = tmp
        index_mod.DATA = tmp / "data"
        index_mod.DATA.mkdir()
        for i in range(3):
            (tmp / f"f{i}.py").write_text("# a file about garrison reach\n" + "x = %d\n" % i
                                          + "pad\n" * 100, encoding="utf-8")
        (tmp / "tiny.py").write_text("x = 1\n", encoding="utf-8")
        files = ["f0.py", "f1.py", "f2.py", "tiny.py"]
        man = {"model": {"graph": "g", "graph_sha256_16": "aaaa", "dim": 4}}

        e1 = FakeEmb()
        got = report._file_vectors(files, e1, man)
        check("a file under the length floor is not embedded", "tiny.py" not in got, sorted(got))
        check("every other file gets a vector", len(got) == 3, sorted(got))
        check("all of them in ONE batched call", e1.calls == 1, e1.calls)

        e2 = FakeEmb()
        report._file_vectors(files, e2, man)
        check("a second run embeds nothing", e2.texts == 0, e2.texts)

        (tmp / "f1.py").write_text("# a file about banner glyphs\n" + "pad\n" * 100,
                                   encoding="utf-8")
        e3 = FakeEmb()
        report._file_vectors(files, e3, man)
        check("a changed file is re-embedded, alone", e3.texts == 1, e3.texts)

        e4 = FakeEmb()
        report._file_vectors(files, e4, {"model": {"graph": "g", "graph_sha256_16": "bbbb",
                                                   "dim": 4}})
        check("a different model invalidates the whole cache", e4.texts == 3, e4.texts)

        # the accepted list is the CALLER's file, handed in by path
        acc = tmp / "accepted.json"
        acc.write_text(json.dumps({
            "facts": [{"a": "x/one", "text_a": "same words", "b": "y/two.rule.md", "text_b": "said again"}],
            "dupes": [{"a": "x/one", "b": "y/two"}, {"a": "x/gone", "b": "y/two"}],
            "coherence": [{"rule": "x/one"}, {"broken": True}],
            "missing": [{"file": "f.py", "rule": "x/one"}],
            "overbroad": [{"rule": "x/one.rule.md"}],
        }), encoding="utf-8")
        report.load_accepted(acc)
        pair = (0.9, ("y/two.rule.md", 3, "said again"), ("x/one.rule.md", 5, "same words"))
        fkey = lambda p: frozenset([(report._stem(p[1][0]), p[1][2]), (report._stem(p[2][0]), p[2][2])])
        shown, hidden, stale = report.split_accepted("facts", [pair], fkey)
        check("an accepted fact is hidden whichever side comes first", hidden == [pair] and not shown)
        edited = (0.9, ("y/two.rule.md", 3, "said again, edited"), pair[2])
        shown, _, stale = report.split_accepted("facts", [edited], fkey)
        check("editing either line brings the fact back", shown == [edited], shown)
        check("and the old acceptance is reported stale", len(stale) == 1, stale)

        dkey = lambda p: frozenset([report._stem(p[1]), report._stem(p[2])])
        shown, hidden, stale = report.split_accepted(
            "dupes", [(0.9, "y/two.rule.md", "x/one.rule.md"), (0.85, "x/one.rule.md", "z/new.rule.md")], dkey)
        check("an accepted dupe hides in either order, and only that pair",
              len(hidden) == 1 and len(shown) == 1 and shown[0][2] == "z/new.rule.md")
        check("an acceptance matching no finding is stale", [e["a"] for e in stale] == ["x/gone"], stale)

        shown, hidden, stale = report.split_accepted(
            "coherence", [(-0.1, "x/one.rule.md"), (-0.1, "q/other.rule.md")], lambda r: report._stem(r[1]))
        check("a malformed entry hides nothing, and is not stale either",
              len(hidden) == 1 and len(shown) == 1 and len(stale) == 0, (shown, stale))
        _, hidden, _ = report.split_accepted("missing", [(0.7, "f.py", "x/one.rule.md"),
                                                         (0.7, "g.py", "x/one.rule.md")],
                                             lambda m: (m[1], report._stem(m[2])))
        check("a missing-gate acceptance is for that FILE only", len(hidden) == 1)
        _, hidden, _ = report.split_accepted("overbroad", ["x/one.rule.md"], report._stem)
        check("an over-broad acceptance names the rule", hidden == ["x/one.rule.md"])
        check("the worklist counts what was hidden", sum(report.HIDDEN.values()) >= 4, report.HIDDEN)

        (tmp / "bad.json").write_text("{not json", encoding="utf-8")
        check("an unreadable list hides nothing", report.load_accepted(tmp / "bad.json") == {})
        check("a missing list hides nothing", report.load_accepted(tmp / "none.json") == {})

        check("a long path keeps its filename end", report._clip("a/" * 40 + "file_dev.xs", 30).endswith("file_dev.xs")
              and len(report._clip("a/" * 40 + "file_dev.xs", 30)) == 30)
        check("a short path is left alone", report._clip("x/y.py", 30) == "x/y.py")
        check("the worklist counts a narrower band than the report lists",
              report.MISSING_FLOOR < report.MISSING_COUNTED)
    finally:
        corpus.REPO, index_mod.DATA = real_repo, real_data
        shutil.rmtree(tmp, ignore_errors=True)


def json_checks():
    """report.py --json: every finding as data, none of the report's text, no model needed."""
    import contextlib
    import io

    print("")
    print("report --json")
    import report

    names = ("facts", "dupes", "coherence", "hubs", "gates")
    real = {n: getattr(report, n) for n in names}

    def noisy(value):
        def fn(*a, **k):
            print("report text that must not reach stdout")
            return value
        return fn

    def fake_hubs():
        report.HUB_GAPS["x/hub.rule.md"] = ["x/a.rule.md"]
        report.HUB_GAPS["y/hub.rule.md"] = []
        print("report text")
        return 1

    try:
        report.facts = noisy([(0.81, ("x/a.rule.md", 2, "one"), ("y/b.rule.md", 3, "two"))])
        report.dupes = noisy([(0.9, "x/a.rule.md", "x/b.rule.md")])
        report.coherence = noisy([(-0.02, "x/a.rule.md", "x", 0.6, "y", 0.62)])
        report.hubs = fake_hubs
        report.gates = noisy(([(0.75, "f.py", "x/a.rule.md"), (0.5, "g.py", "x/b.rule.md")],
                              {"x/c.rule.md": [0.1, 0.2]}))
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            got = {n: report.findings_json(n) for n in names}
        check("--json prints none of the report text", out.getvalue() == "", out.getvalue()[:80])
        f = got["facts"]["findings"][0]
        check("a fact names both rules and lines", (f["a"], f["line_a"], f["b"], f["line_b"])
              == ("x/a.rule.md", 2, "y/b.rule.md", 3), f)
        check("a dupe names both rules", got["dupes"]["findings"] == [{"score": 0.9, "a": "x/a.rule.md",
                                                                     "b": "x/b.rule.md"}])
        check("a coherence finding names the rule and the nearer area",
              got["coherence"]["findings"][0]["rule"] == "x/a.rule.md"
              and got["coherence"]["findings"][0]["nearer"] == "y")
        check("hubs lists each hub's gaps", got["hubs"]["findings"][0] == {"hub": "x/hub.rule.md",
                                                                          "missing": ["x/a.rule.md"]})
        g = got["gates"]["findings"]
        check("a missing gate at the counted cut is marked counted",
              [m["counted"] for m in g["missing"]] == [True, False], g["missing"])
        check("over-broad gates are counted per rule", g["overbroad"] == [{"rule": "x/c.rule.md", "files": 2,
                                                                         "mean": 0.15}], g["overbroad"])
        try:
            report.findings_json("queries")
            check("an unsupported report is refused", False)
        except ValueError:
            check("an unsupported report is refused", True)
    finally:
        for n, fn in real.items():
            setattr(report, n, fn)
        report.HUB_GAPS.clear()


def repo_checks():
    print("\n--repo")
    import subprocess
    check("--repo with this repository's name is accepted and removed",
          corpus.parse_repo(["--repo", corpus.REPO.name, "a", "question"]) == ["a", "question"])
    check("--repo . is this repository too", corpus.parse_repo(["q", "--repo", "."]) == ["q"])
    import os
    import shutil
    import tempfile
    keys = ("CLAUDE_RULE_STATE_DIR", "CLAUDE_CODE_SESSION_ID", "CLAUDE_CODE_CHILD_SESSION")
    saved = {k: os.environ.get(k) for k in keys}
    st = pathlib.Path(tempfile.mkdtemp(prefix="use_state_"))
    try:
        os.environ.update({"CLAUDE_RULE_STATE_DIR": str(st), "CLAUDE_CODE_SESSION_ID": "use-test-1"})
        os.environ.pop("CLAUDE_CODE_CHILD_SESSION", None)
        (st / "claude_rule_router").mkdir()
        f = st / "claude_rule_router" / "use-test-1.use.json"
        f.write_text(json.dumps({"ecosystem": corpus.REPO.name}), encoding="utf-8")
        check("a session that uses this repository's rule set searches as normal", corpus.parse_repo(["q"]) == ["q"])
        f.write_text(json.dumps({"ecosystem": "some/other"}), encoding="utf-8")
        try:
            corpus.parse_repo(["q"])
            said = ""
        except SystemExit as e:
            said = str(e)
        check("a session that uses another rule set is refused by name, pointing at rules.py use", "rules.py use" in said, said)
        check("--repo on the command wins over the session's choice", corpus.parse_repo(["--repo", corpus.REPO.name, "q"]) == ["q"])
        check("a working folder in no nested rule set is this repository's", corpus.working_rule_set(str(corpus.REPO)) is None)
        check("a folder outside the repository names no rule set", corpus.working_rule_set(tempfile.gettempdir()) is None)
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(st, ignore_errors=True)
    for script in ("search.py", "index.py", "report.py", "ask.py"):
        p = subprocess.run([sys.executable, str(HERE / script), "--repo", "some/other/ecosystem", "--status", "x"],
                           capture_output=True, text=True, timeout=120)
        check("%s refuses another ecosystem by name rather than answering from this one" % script,
              p.returncode != 0 and "PLAN item 29" in p.stderr, (p.returncode, p.stderr[-200:]))


def main():
    t0 = time.time()
    repo_checks()
    unit_checks()
    query_log_checks()
    opened_checks()
    report_checks()
    json_checks()
    skill_checks()
    status_checks()
    nearest_checks()
    golden()
    print("\n%d passed, %d failed in %.1fs" % (PASS, FAIL, time.time() - t0))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
