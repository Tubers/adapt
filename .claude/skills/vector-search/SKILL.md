---
name: vector-search
description: Search the project rules, the run history, past run results and every skill's own docs and code by meaning rather than by path. Ask a question in plain words. Use it liberally, before designing a run, before building a tool, before writing a rule, before claiming something is untested, on arriving in an unfamiliar subtree, and whenever a number or id is about to be typed from memory.
---

# vector-search

## RUN THIS

```bash
python .claude/skills/vector-search/scripts/search.py "how long may a rule file be"
python .claude/skills/vector-search/scripts/search.py --file Adapt/README.md
python .claude/skills/vector-search/scripts/search.py --json "retire a handoff"
python .claude/skills/vector-search/scripts/search.py --skill rules-system "where are gates matched against a path"
python .claude/skills/vector-search/scripts/search.py --skill all "retire a finished handoff"
```

Every script takes `--repo <repo>` (or no `--repo`). Another rule ecosystem is refused by name: only this
repository is indexed so far.

**Search on a LOW bar.** A query costs about 300 ms and a few hundred tokens. Re-deriving a measured
fact costs a session. The named moments, all cheap to check:

- before designing a run or writing a generator, on the subject of the run;
- before building any tool or helper, to find out whether one already exists;
- before writing a new rule, to find the rule it probably belongs in;
- before asserting that something is untested, unmeasured or impossible;
- on arriving in an unfamiliar subtree, on that subtree's subject;
- when a number, an id or a constant is about to be typed from memory.

**A hit is a POINTER.** It gives the rule name, the gate that would inject it, and the line that
matched. Open `rules/<name>` before acting on it. Do not act on the printed line alone.

**"Nothing close" is a real answer** and will be common. Below a per-namespace similarity floor the
tool refuses rather than offering the least-bad three. Those refusals are tested.

## What it is

An embedding model turns text into a vector whose position encodes meaning, so two texts about the
same thing land near each other. Every rule is embedded three ways — whole, one vector per bullet
line, and its one-line gist from `rules/INDEX.md` — about eight vectors per rule. A query is
embedded the same way and compared against all of them by dot product. There is no approximate index
and none is needed at this size; the exact comparison takes under a millisecond.

Three things sharpen the ranking beyond raw similarity, each added because the golden set demanded it:

| device | why |
|---|---|
| pointer resolution | a line in rule A that merely names rule B is evidence about B, so B gets credited just under that line's score |
| evidence accumulation | a rule matching on several of its own vectors beats one matching on a single line, capped so it cannot invent a winner |
| small lexical bonus | at most 0.05 for query-word overlap, enough to break a tie and not enough to overturn a ranking |

## WHEN A RULE CANNOT BE FOUND, FIX THE GIST, NOT THE RULE

A miss in the golden set means a rule exists and nobody can reach it by the words they would actually
use. There are three places that could be edited and only one of them is usually right.

| edit | when | why |
|---|---|---|
| **the GIST in `rules/INDEX.md`** | almost always | It is indexed as its own vector, it is written in plain "what this is about" register, it sits OUTSIDE the 2048-byte rule cap, and nobody reads it in bulk. Widening it costs nothing that matters. |
| the rule's HEADLINE | only when the headline misdescribes the rule | A headline that names a mechanism but never the symptom people meet is a real defect in the rule, not a retrieval problem: anyone hunting it searches the symptom. |
| the rule's BODY | almost never | The body is compulsory injected context, capped, and paid for on every gate match. Padding it with search terms taxes every future session to fix one query. |

**Never add keyword soup to any of the three.** Tuning text until a golden question passes is teaching
to the test, and the test then measures nothing. The honest sequence is: read the question, decide
what a person genuinely means by it, and ask whether the gist says that thing in those terms. If it
already does and retrieval still misses, the problem is retrieval and belongs in `search.py`.

**Record the failing question in `golden.jsonl` either way.** A miss that gets fixed silently comes
back.

## The model

`voyage-4-nano`, Apache 2.0, open weights, community ONNX export, int8, 512 of its 2048 dimensions
(Matryoshka truncation, then re-normalised). Mean pooling over unmasked tokens. Query and document
text get DIFFERENT prefixes, which the model card requires and `embed.py` applies.

Weights live **outside the repo**, default
`C:\Users\ljcg3\OneDrive\Desktop\models\voyage-4-nano-onnx`, 431 MB. Override with
`RULE_SEARCH_MODEL`. They are build input, not source, and this repo has no version control.

CPU only, eight threads, override with `RULE_SEARCH_THREADS`. Not the GPU, which other work on the machine may need.

## THREE NAMESPACES, NEVER MERGED

```bash
search.py "question"                      # rules, the default
search.py --history "has anyone measured the claim radius"
search.py --history "was this already tried"
```

| namespace | documents | answers | built from |
|---|---:|---|---|
| `rules` | every rule, about eight vectors each | what to DO. Compulsory guidance | `rules/**` whole, per line, and per gist |
| `history` | 58 events | what HAPPENED, with a run id and a status | every `HISTORY.jsonl` |
| `results` | 267 runs | the raw GROUND TRUTH a rule was distilled from | Abstract and Implications of each `RESULTS.md` |

They are separate indexes on purpose. Merged, a run record could outrank the rule governing the same
subject, which inverts the arrangement the repo rests on: rules are the compulsory layer and records
are evidence for them.

## ONE INDEX PER SKILL

```bash
search.py --skill rules-system "where are gates matched against a path"
search.py --skill all "how does a handoff get retired"
index.py --ns skills                      # every skill; prunes the index of a skill no longer on disk
index.py --ns skill:handoff  # one skill
```

Every skill gets its OWN vector file and manifest, in `data/skills/<name>/`. One skill can be rebuilt,
inspected or deleted without touching another, and a skill that disappears from disk has its index
pruned on the next `--ns skills` run.

**What is indexed.** A skill's `.md`, `.py`, `.js`, `.ts`, `.sh`, `.ps1`, `.toml`, `.json`, `.c`, `.cpp` and `.h` files (plus `.xs` and `.per`), cut
into chunks of at most 1,800 characters:

| file | cut at | a hit's label |
|---|---|---|
| markdown | its headings; a long section at paragraph breaks; a heading with no body joins the next section | the heading trail, `SKILL.md > Index > Tests` |
| Python | its top-level definitions; module-level code is one block; a class too long for one chunk is cut per method | the definition, `match_paths` or `Gate.matches_path` |
| anything else | blank-line blocks, packed | none |

Skipped: `data/` (output, not source), `project_snapshot/` (a vendored COPY of repo files, which would
answer a question about `_shared/` with a stale duplicate), and image and build folders. At the first
build over every skill in the repository.

**A hit is a place to look**: `<skill>/<path>:<line>`, the section or definition, and the start of the
chunk. Only the best chunk of each FILE is returned, so five hits are five files. `--skill all` loads
every skill index in turn, embeds the question once, and merges by score, each hit naming its skill.
Every skill shares one floor, 0.45 (calibrated 2026-09-13 against the golden set), because a chunk is the same shape whichever skill it came from.

**The silo rule still holds.** Skill files are read as text to embed. Nothing is imported, and the
suite builds its skill checks in a temp folder, so deleting every other skill leaves this one passing.

**The similarity floor is per namespace**, 0.40 for rules and history, 0.28 for results. Similarity is
not comparable across document shapes: a rule is a dense statement and scores high against a matching
question, while a results abstract is several paragraphs of narrative and its best true match sits
lower. Each floor is set where the off-topic questions still return nothing.

## THE QUERY LOG: ask once, the next session inherits it

```bash
python .claude/skills/vector-search/scripts/ask.py "how long may a rule file be"
python .claude/skills/vector-search/scripts/ask.py --history "has anyone measured the claim radius"
python .claude/skills/vector-search/scripts/qlog.py digest Adapt
python .claude/skills/vector-search/scripts/qlog.py collect
```

`ask.py` is `search.py` plus a record. It searches, prints the hits, and appends BOTH the question and
its answer to `QUERIES.jsonl` in the folder you are working in. A `PostToolUse` hook then puts the same
answer into the session's context, because a command fired for its side effect often has its stdout
skimmed, and an answer nobody reads is the same as no answer.

**Read a log with `digest`, never raw.** A hundred questions with answers is thousands of tokens; the
same hundred as a digest is a few hundred.

**A query log is a record of questions asked, not a list of open ones.** `rules/writing/query-log`
says so, because this repo has already lost a session to reading finished work as pending.

Every answer line carries the namespace, the floor, the model fingerprint and the index build time.
Those four are mandatory: without them a later reader cannot tell a bad answer from a stale-index
answer, and that distinction is the only reason the log exists.

A third line kind, `opened`, is appended by `.claude/hooks/query_opened.py` when a Read matches a hit
that a recent answer returned. It records WHICH rank was opened and how long after the question, which
is the only evidence available about whether the ranking and the gists are any good. Attribution is
limited to six hours and the twenty newest answers, so a coincidence cannot masquerade as a signal.
Nothing opened is recorded as nothing, not as a zero.

`report.py queries` turns the collated logs into five signals: questions that returned nothing, which
are gist gaps or missing rules; questions asked in several folders, which are missing rules or missing
gates; answers produced against an index older than the corpus, the share of opens that landed on the top
hit, and answers where nothing was opened at all, which is where a gist oversells its rule.

## Maintenance reports — the other half of the value

```bash
python .claude/skills/vector-search/scripts/report.py dupes      [--cut 0.80]
python .claude/skills/vector-search/scripts/report.py gates      [--limit 40]
python .claude/skills/vector-search/scripts/report.py coherence  [--worst 15]
python .claude/skills/vector-search/scripts/report.py hubs
python .claude/skills/vector-search/scripts/report.py facts     [--cut 0.78]
python .claude/skills/vector-search/scripts/report.py refactor  [--gates]
```

The rule-system skill runs all of them for you, in the order they must be acted on, and reindexes
first: `python .claude/skills/rules-system/scripts/rules.py audit`. Prefer that when the job is to
improve the rules rather than to inspect one report.

- **facts** — lines from DIFFERENT rules that say the same thing. This is the one that finds what no
  other check can: redundancy is rarely two rules about one subject, it is one fact sitting inside two
  rules about different subjects, where neither reader learns the other copy exists and the two drift
  until they disagree. Lines that are mostly a cross-reference are skipped, because every pointer
  resembles every other pointer.
- **--accepted <file>** — hide findings a person already read and kept, listed in a file the
  CALLER owns. rules-system keeps its list in its own `data/` and hands the path over; this skill
  never reads another skill's data or settings. Entries that match nothing are printed as STALE.
- **missing-gate count** — `gates` lists every pair above 0.45, but the `refactor` worklist counts
  only those at 0.70 or more. Every real missing gate found so far scored there; the 0.45 floor
  admits about a thousand weak pairs and made the count meaningless.
- **refactor** — every structural report in one pass, then a worklist. The order is load-bearing:
  merging a fact rewrites both rules, so `dupes` only means something after `facts`; moving a rule
  shifts two area centroids and two hubs, so `hubs` only means something after `coherence`; and a gate
  is written against a rule's final path and final text, so `gates` is last or it is written twice.
- **dupes** — rule pairs whose whole-rule vectors sit close. Catches paraphrase that the phrase-level
  detector in the rules-system skill cannot see by construction.
- **gates** — for every repo file, the rules the gates inject against the rules that are semantically
  nearest. Near but never injected is a candidate missing gate; it found nine real ones on first run.
  It is the slow one, because it embeds every repo file. File vectors are cached in
  `data/filecache.npz`, keyed by path, content hash and the model fingerprint, so a second run
  re-embeds only what changed and a model change throws the cache away rather than mixing two vector
  spaces. That cache is not a namespace: nothing queries it. Code inside the SKILLS is searchable
  through the per-skill indexes; repo code outside them is still not a namespace.
- **coherence** — each rule against its own area's centroid, flagging a rule filed in the wrong area.
- **hubs** — every rule an area hub fails to name. It found 22 on first run, all created by a rename
  or a split that the hub text never caught up with.

**Every report prints CANDIDATES, not verdicts.** Two rules can sit close because one restates the
other or because they are the two halves of a deliberate split, and no number tells those apart.

One caveat worth knowing before reading the over-broad column: a universal syntax rule scores low
against every file, because rule prose about a parameter list does not look like code. Low similarity
is not evidence of a wrong gate for that kind of rule.

## Index

```bash
python .claude/skills/vector-search/scripts/index.py                 # rules, refresh what changed
python .claude/skills/vector-search/scripts/index.py --ns history
python .claude/skills/vector-search/scripts/index.py --ns results
python .claude/skills/vector-search/scripts/index.py --ns skills
python .claude/skills/vector-search/scripts/index.py --ns skill:<name>
python .claude/skills/vector-search/scripts/index.py --ns all --rebuild     # includes every skill
```

Incremental by content hash, so editing one rule re-embeds one rule, about 14 seconds. A full rebuild
is about 10 minutes on this machine. `data/manifest.json` pins model, graph hash and dimension, and a
search refuses to run against an index built by a different model rather than silently comparing
incomparable vectors.

## Tests

```bash
python .claude/skills/vector-search/scripts/run_tests.py
```

Plumbing checks plus the **golden set**, `golden.jsonl`: real questions each naming the rule that
must come back, and 3 off-topic questions that must return nothing. Current, across all three namespaces: 49 questions, recall@3 94%, recall@1 69%, median
query 300 ms, and five off-topic refusals.

**recall@3 is the ship gate at 90%.** recall@1 is a regression guard at a lower bar on purpose,
because several rules legitimately touch one subject here and which ranks first is often a coin toss
between two right answers. The three refusals are the test that catches a retriever which always
finds something.

## Files

| path | what |
|---|---|
| `scripts/embed.py` | the model: prefixes, pooling, truncation, normalisation, fingerprint |
| `scripts/corpus.py` | what gets indexed, gate parsing, pointer resolution |
| `scripts/index.py` | build and refresh, incremental by hash |
| `scripts/search.py` | query, ranking devices, refusal floor, search log |
| `scripts/report.py` | the maintenance reports, and `refactor` which runs them in order |
| `scripts/run_tests.py` | plumbing checks and the golden set |
| `golden.jsonl` | the golden questions |
| `scripts/ask.py` | search and record: appends the question and answer to the folder's log |
| `scripts/qlog.py` | `digest`, `collect`, `stats` over the query logs |
| `data/` | vectors, manifests, `filecache.npz`, `searches.jsonl`, `queries-all.jsonl`, `surfaced.json` |
| `data/skills/<name>/` | one skill's own `vectors.npz` and `manifest.json` |

`data/searches.jsonl` records every query with its hits and latency. It exists so under-use is
visible: the expected failure of this tool is nobody reaching for it, not wrong answers.

Attribution: voyage-4-nano by Voyage AI, Apache 2.0. ONNX export by the onnx-community.
