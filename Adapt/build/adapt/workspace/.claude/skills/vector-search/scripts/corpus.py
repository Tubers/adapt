"""What gets indexed, and what a hit is allowed to say.

A rule is indexed TWICE over: once whole, and once per bullet line. Whole-rule vectors answer "which
rule is about this subject"; line vectors answer "which fact is this", and the niche facts live in
single lines. 233 rules give about 1,600 vectors in total, so both is affordable and neither has to
win an argument.

A hit carries the rule name, its GATE from rules/INDEX.md, and the matching line. Never the rule body:
the body arrives because a gate fired or because the instance opened the file. That keeps the one
property the rule system has that a retriever must not erode - what is injected is decided by the
index in rules/INDEX.md and by nothing else.
"""

import ast
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parents[3]
RULES = REPO / "rules"
sys.path.insert(0, str(REPO / ".claude" / "skills" / "rules-system" / "scripts"))

def working_rule_set(cwd=None):
    """The nested rule set holding the working folder (a folder below the repository root that keeps its own
    rules/), as a repo-relative path, or None. It outranks the session's `use`, as in rules-system."""
    import os
    here = pathlib.Path(cwd or os.getcwd()).resolve()
    top = REPO.resolve()
    try:
        here.relative_to(top)
    except ValueError:
        return None
    for d in [here] + list(here.parents):
        if d == top:
            return None
        if (d / "rules").is_dir():
            return d.relative_to(top).as_posix()
    return None


def session_use():
    """The rule set this session chose with `rules.py use`, or None. Read from the file the rules-system skill
    writes (<state dir>/claude_rule_router/<session>.use.json); read here, never imported, because skills are
    silos. A sub-agent has its parent's session id, so it shares the choice."""
    import json
    import os
    session = os.environ.get("CLAUDE_CODE_SESSION_ID", "")
    if not session:
        return None
    base = pathlib.Path(os.environ.get("CLAUDE_RULE_STATE_DIR") or os.environ.get("TEMP") or os.environ.get("TMP") or ".")
    p = base / "claude_rule_router" / (re.sub(r"[^A-Za-z0-9_.-]", "_", session) + ".use.json")
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return d.get("ecosystem") if isinstance(d, dict) else None


def parse_repo(argv):
    """argv without --repo, which every command takes. Only this repository has indexes today, so any
    other rule ecosystem is refused by name rather than silently answered from this one's rules
    (knowledge_upkeep PLAN item 29 builds an index per ecosystem)."""
    argv = list(argv)
    if "--repo" not in argv:
        here = working_rule_set()
        if here:
            raise SystemExit("the working folder is inside the rule set %s, and vector-search indexes %s only so far "
                             "(knowledge_upkeep PLAN item 29). Pass --repo %s to search this repository."
                             % (here, REPO.name, REPO.name))
        used = session_use()
        if used and used != REPO.name and (REPO / used).resolve() != REPO.resolve():
            raise SystemExit("this session uses the rule set %s (rules.py use), and vector-search indexes %s only so "
                             "far (knowledge_upkeep PLAN item 29). Pass --repo %s, or: rules.py use --clear"
                             % (used, REPO.name, REPO.name))
        return argv
    i = argv.index("--repo")
    if i + 1 >= len(argv):
        raise SystemExit("--repo needs a name or a folder. For this repository: --repo %s" % REPO.name)
    val = argv[i + 1]
    del argv[i:i + 2]
    p = pathlib.Path(val) if pathlib.Path(val).is_absolute() else REPO / val
    if val != REPO.name and p.resolve() != REPO.resolve():
        raise SystemExit("vector-search indexes the rules, history, results and skills of %s only, not --repo %s. "
                         "A separate index per rule ecosystem is not built yet (knowledge_upkeep PLAN item 29)."
                         % (REPO.name, val))
    return argv


_GATE_RE = re.compile(r"^- \*\*(?P<rule>[^*]+\.rule\.md)\*\* \| (?P<trig>.+?) \| (?P<gist>.*)$")


def gates() -> dict:
    """rule name -> (triggers, one-line gist) straight out of the hand-maintained index."""
    out = {}
    idx = RULES / "INDEX.md"
    if not idx.is_file():
        return out
    for line in idx.read_text(encoding="utf-8").splitlines():
        m = _GATE_RE.match(line.strip())
        if m:
            out[m.group("rule")] = (m.group("trig").strip(), m.group("gist").strip())
    return out


def rule_texts():
    """[(name, whole_text, [(line_no, line_text), ...]), ...] for every rule on disk."""
    out = []
    for p in sorted(RULES.rglob("*.rule.md")):
        name = p.relative_to(RULES).as_posix()
        text = p.read_text(encoding="utf-8")
        lines = []
        for i, raw in enumerate(text.splitlines(), start=1):
            s = raw.strip()
            if not s:
                continue
            body = s[2:].strip() if s.startswith("- ") else s
            if len(body) < 25:                     # a stub line carries no retrievable fact
                continue
            lines.append((i, body))
        out.append((name, text, lines))
    return out


RULE_REF_RE = re.compile(r"\b([a-z][a-z0-9-]*(?:/[a-z0-9-]+)+)\b")


def rule_stems() -> dict:
    """stem without the .rule.md suffix -> full rule name, for resolving in-text pointers."""
    out = {}
    for p in RULES.rglob("*.rule.md"):
        name = p.relative_to(RULES).as_posix()
        out[name[:-len(".rule.md")]] = name
    return out


def referenced_rules(line: str, stems: dict):
    """Rules a line points AT. A pointer line should credit its target, not itself."""
    hits = []
    for cand in RULE_REF_RE.findall(line):
        full = stems.get(cand)
        if full and full not in hits:
            hits.append(full)
    return hits


def area_of(rule_name: str) -> str:
    return rule_name.split("/")[0]


def is_hub(rule_name: str) -> bool:
    return rule_name.endswith("hub.rule.md")


def repo_files(exts=(".py", ".xs", ".per", ".md")):
    """Live repo files a gate could plausibly fire on. Skips the machinery and the archives."""
    skip = {".claude", "test_runs", "__pycache__", "_backup", "archive", ".git"}
    out = []
    for p in sorted(REPO.rglob("*")):
        if not p.is_file() or p.suffix not in exts:
            continue
        rel = p.relative_to(REPO).as_posix()
        if any(s in rel.split("/") for s in skip):
            continue
        out.append(rel)
    return out


# ------------------------------------------------------------------------------------------------
# The other two corpora. SEPARATE NAMESPACES, never mixed into one index.
#
# A rule says what to DO and is compulsory. A history event says what HAPPENED, with a run id. A
# results abstract is the raw ground truth a rule was distilled from. Mixed together, a run record
# could outrank the rule that governs the same subject, which inverts the whole arrangement. Kept
# apart, a query can be aimed and an answer can say which corpus produced it.
# ------------------------------------------------------------------------------------------------

def history_events():
    """[(id, text, path), ...] one document per event across every HISTORY.jsonl in the repo."""
    import json
    out = []
    for p in sorted(REPO.rglob("HISTORY.jsonl")):
        rel = p.relative_to(REPO).as_posix()
        if ".claude" in rel.split("/"):
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
            except ValueError:
                continue
            bits = [e.get("title", ""), e.get("what", ""), e.get("result", "")]
            nums = e.get("numbers") or {}
            if nums:
                bits.append(" ".join("%s %s" % (k.replace("_", " "), v) for k, v in nums.items()))
            for k in ("tags", "refs"):
                if e.get(k):
                    bits.append(" ".join(str(x) for x in e[k]))
            text = " . ".join(b for b in bits if b)
            out.append((e.get("id", rel), text, rel, e.get("status", ""), e.get("kind", "")))
    return out


RESULT_SECTION = re.compile(r"^## (Abstract|Implications.*)$", re.M | re.I)


def results_docs():
    """[(run id, text, path), ...] the Abstract and Implications of each run's RESULTS.md.

    Those two sections are what a person wrote about the run. The tables under Results are raw and
    would swamp the vector with numbers that mean nothing out of context.
    """
    out = []
    for p in sorted((REPO / "test_runs").rglob("RESULTS.md")):
        raw = p.read_text(encoding="utf-8", errors="replace")
        parts, keep = [], False
        for line in raw.splitlines():
            if line.startswith("## "):
                keep = bool(RESULT_SECTION.match(line))
                continue
            if line.startswith("# "):
                parts.append(line[2:].strip())
                continue
            if keep and line.strip() and not line.strip().startswith("!["):
                parts.append(line.strip())
        text = " ".join(parts)[:4000]
        if len(text) < 120:
            continue
        rel = p.relative_to(REPO).as_posix()
        out.append((rel.split("/")[-2], text, rel))
    return out


# ------------------------------------------------------------------------------------------------
# SKILLS. One index PER SKILL, each in its own files under data/skills/<name>/.
#
# A skill is a silo: its own docs, its own code, its own tests. Searching one skill answers "where in
# the harness is the restart handled" without the data-modding reference outranking it on vocabulary.
# `--skill all` searches every skill index and labels each hit with the skill it came from.
#
# These files are read as TEXT to be embedded. Nothing here imports another skill, so the silo rule
# holds: delete every other skill and this one still builds an index of what is left.
# ------------------------------------------------------------------------------------------------

SKILLS = REPO / ".claude" / "skills"
SKILL_EXTS = {".md", ".py", ".js", ".ts", ".sh", ".ps1", ".toml", ".json", ".c", ".cpp", ".h", ".xs", ".per"}
# data/ is output, not source. project_snapshot/ is a vendored COPY of repo files, so indexing it would
# answer a question about _shared/ with a stale duplicate. The rest hold images and build artefacts.
SKILL_SKIP_DIRS = {"data", "__pycache__", "project_snapshot", "build_files", "testdata", "assets",
                   "state_captures", "node_modules", ".venv"}
CHUNK_MAX = 1800          # about 450 tokens: one idea, well under the model's 1024-token window
CHUNK_MIN = 120           # a section shorter than this is a heading with no body; it joins the next
CHUNK_DROP = 60           # anything shorter after chunking carries nothing retrievable

_MD_HEAD = re.compile(r"^(#{1,4})\s+(.*\S)")


def skill_files(name: str):
    """Every indexable file of one skill, as paths, in a stable order."""
    root = SKILLS / name
    if not root.is_dir():
        return []
    out = []
    for p in sorted(root.rglob("*")):
        if not p.is_file() or p.suffix.lower() not in SKILL_EXTS:
            continue
        if any(part in SKILL_SKIP_DIRS for part in p.relative_to(root).parts[:-1]):
            continue
        out.append(p)
    return out


def skill_names():
    """Skills that have at least one indexable file. An empty skill folder gets no index."""
    if not SKILLS.is_dir():
        return []
    return sorted(p.name for p in SKILLS.iterdir() if p.is_dir() and skill_files(p.name))


def _split_long(start: int, text: str, limit: int = CHUNK_MAX):
    """[(line, text)] a block too long for one chunk, cut at line boundaries."""
    out, cur, first, size = [], [], start, 0
    for i, line in enumerate(text.split("\n")):
        line = line[:limit]
        if cur and size + len(line) + 1 > limit:
            out.append((first, "\n".join(cur)))
            cur, size, first = [], 0, start + i
        cur.append(line)
        size += len(line) + 1
    if cur:
        out.append((first, "\n".join(cur)))
    return out


def _pack(blocks, limit: int = CHUNK_MAX):
    """[(line, text)] -> [(line, text)] consecutive blocks joined up to `limit` characters."""
    out, cur, first, size = [], [], None, 0
    for line_no, text in blocks:
        for ln, piece in ([(line_no, text)] if len(text) <= limit else _split_long(line_no, text, limit)):
            if cur and size + len(piece) + 2 > limit:
                out.append((first, "\n\n".join(cur)))
                cur, first, size = [], None, 0
            if first is None:
                first = ln
            cur.append(piece)
            size += len(piece) + 2
    if cur:
        out.append((first, "\n\n".join(cur)))
    return out


def _paragraphs(lines, first_line: int):
    """[(line, text)] blank-line separated blocks. A fenced code block is never split at a blank."""
    out, cur, start, fence = [], [], first_line, False
    for i, line in enumerate(lines):
        if line.lstrip().startswith("```"):
            fence = not fence
        if not line.strip() and not fence:
            if cur:
                out.append((start, "\n".join(cur)))
            cur, start = [], first_line + i + 1
            continue
        if not cur:
            start = first_line + i
        cur.append(line)
    if cur:
        out.append((start, "\n".join(cur)))
    return out


def md_chunks(text: str):
    """[(line, label, text)] a markdown file cut at its headings, labelled by the heading trail.

    The trail matters more than it looks. "Tests" is a heading in half the skills; "SKILL.md > Index >
    Tests" is not, and it is what tells a reader which part of which document answered.
    """
    sections, trail, fence = [], [], False
    cur_line, cur = 1, []
    for i, line in enumerate(text.splitlines(), start=1):
        if line.lstrip().startswith("```"):
            fence = not fence
        m = None if fence else _MD_HEAD.match(line)
        if m:
            if cur:
                sections.append((cur_line, " > ".join(h for _, h in trail), cur))
            level = len(m.group(1))
            trail = [(lv, h) for lv, h in trail if lv < level] + [(level, m.group(2).strip())]
            cur_line, cur = i, [line]
        else:
            cur.append(line)
    if cur:
        sections.append((cur_line, " > ".join(h for _, h in trail), cur))

    out, pending, pending_line = [], "", None
    for line_no, label, lines in sections:
        body = "\n".join(lines).strip()
        if len(body) < CHUNK_MIN:
            pending = (pending + "\n\n" + body).strip()
            pending_line = pending_line or line_no
            continue
        blocks = _paragraphs(lines, line_no)
        if pending:
            blocks = [(pending_line, pending)] + blocks
            pending, pending_line = "", None
        for ln, chunk in _pack(blocks):
            out.append((ln, label, chunk))
    if pending:
        out.append((pending_line, "", pending))
    return [c for c in out if len(c[2]) >= CHUNK_DROP]


def py_chunks(text: str):
    """[(line, label, text)] a Python file cut at its top-level definitions.

    Module-level code between definitions - the docstring, imports, constants - is one block labelled
    `module`. A class too long for one chunk is cut into its header and one chunk per method, labelled
    `Class.method`, because a 3000-line class is not one idea. A file that does not parse falls back
    to blank-line blocks rather than being skipped.
    """
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return code_chunks(text)
    lines = text.splitlines()

    def span(a, b):
        return "\n".join(lines[a - 1:b]).strip()

    def start_of(node, floor):
        first = min([node.lineno] + [d.lineno for d in getattr(node, "decorator_list", [])])
        while first - 1 > floor and lines[first - 2].strip().startswith("#"):
            first -= 1                      # a comment block directly above belongs to the definition
        return first

    out, loose, loose_line, prev_end = [], [], None, 0
    defs = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)

    def flush_loose():
        nonlocal loose, loose_line
        if loose:
            for ln, chunk in _pack(loose):
                out.append((ln, "module", chunk))
        loose, loose_line = [], None

    for node in tree.body:
        if not isinstance(node, defs):
            a = prev_end + 1
            b = node.end_lineno
            piece = span(a, b)
            if piece:
                loose.append((a, piece))
            prev_end = b
            continue
        flush_loose()
        a = start_of(node, prev_end)
        whole = span(a, node.end_lineno)
        if isinstance(node, ast.ClassDef) and len(whole) > CHUNK_MAX:
            methods = [n for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
            head_end = (start_of(methods[0], a) - 1) if methods else node.end_lineno
            head = span(a, head_end)
            if head:
                for ln, chunk in _split_long(a, head):
                    out.append((ln, node.name, chunk))
            m_prev = head_end
            for m in methods:
                ma = start_of(m, m_prev)
                for ln, chunk in _split_long(ma, span(ma, m.end_lineno)):
                    out.append((ln, "%s.%s" % (node.name, m.name), chunk))
                m_prev = m.end_lineno
        else:
            for ln, chunk in _split_long(a, whole):
                out.append((ln, node.name, chunk))
        prev_end = node.end_lineno
    tail = span(prev_end + 1, len(lines))
    if tail:
        loose.append((prev_end + 1, tail))
    flush_loose()
    return [c for c in out if len(c[2]) >= CHUNK_DROP]


def code_chunks(text: str):
    """[(line, label, text)] any other source file, packed from blank-line separated blocks."""
    return [(ln, "", chunk) for ln, chunk in _pack(_paragraphs(text.splitlines(), 1))
            if len(chunk) >= CHUNK_DROP]


def skill_chunks(name: str):
    """[(path, line, label, text)] every chunk of one skill. `path` is relative to the skill root."""
    root = SKILLS / name
    out = []
    for p in skill_files(name):
        rel = p.relative_to(root).as_posix()
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        suffix = p.suffix.lower()
        cut = md_chunks if suffix == ".md" else py_chunks if suffix == ".py" else code_chunks
        for line, label, chunk in cut(text):
            out.append((rel, line, label, chunk))
    return out
