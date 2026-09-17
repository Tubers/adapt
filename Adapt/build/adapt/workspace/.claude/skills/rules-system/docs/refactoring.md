# Refactoring the rules with evidence

`reconcile` answers *is this system internally consistent*. It cannot answer *are these good rules*,
because every question worth asking there is about meaning: do two rules say the same thing in
different words, is this rule filed under the right area, does this gate reach the files the rule is
actually about. Those were all done by eye until the `vector-search` skill existed, and by eye they
are done badly - a four-word overlap detector catches literal restatement and nothing else, and
nobody can hold 235 rules in their head at once to notice that two of them agree.

```bash
python .claude/skills/rules-system/scripts/rules.py audit           # the whole pass
python .claude/skills/rules-system/scripts/rules.py audit --gates   # including the slow one
```

`audit` reindexes, runs the free text checks, and then runs the four semantic reports **in the order
they must be acted on**. The order is not presentation. Merging a fact rewrites both rules, so the
whole-rule comparison is only meaningful afterwards; moving a rule between areas moves two centroids
and changes two hubs; and a gate is written against a rule's final path and final text, so it is
written last or written twice.

| # | command | the question it answers | what a finding justifies |
|---|---|---|---|
| 1 | `facts` | is this one statement living in two rules? | keep one owner, leave a pointer, per `writing/fact-ownership` |
| 2 | `dupes` | are these two rules about one subject? | merge them, or confirm the split was deliberate |
| 3 | `coherence` | is this rule nearer another area's centre than its own? | refile it with `rules.py move`, after reading why it sits where it does |
| 4 | `hubs` | does each hub still name every rule in its area? | add the missing line to the hub |
| 5 | `coverage` | which files is this rule near but never injected on? | add the missing gate, or narrow the over-broad one |

**Acting on a coherence finding.** `rules.py move <rule> <new-name>` renames the file and rewrites
every reference to it: its gate line in `rules/INDEX.md`, pointers inside other rules, every README
that lists it, and its own header. It matches a name only where it stands alone, so
a script named `naming.py` is never touched, and it preserves line endings byte for byte.
Two things it does not do. It does not move the gate line into its new area's section of the index,
and it does not reword the gate description. The firing log also keeps the old name, because it
records what fired. Run it with `--dry-run` first.

**Keeping a candidate on purpose.** A pair read and kept - a deliberate split, a rule filed by what
its gates reach - would otherwise come back on every pass, and a worklist that repeats itself stops
being read. Record the decision instead:

```bash
python .claude/skills/rules-system/scripts/rules.py accept dupes <rule> <rule> --why "deliberate split: rule vs history"
python .claude/skills/rules-system/scripts/rules.py accept facts <rule>:<line> <rule>:<line> --why "..."
python .claude/skills/rules-system/scripts/rules.py accept coherence|overbroad <rule> --why "..."
python .claude/skills/rules-system/scripts/rules.py accept missing <file> <rule> --why "..."
python .claude/skills/rules-system/scripts/rules.py accept --list [kind]      # and --drop <kind> <n>
```

The list lives in this skill's own `data/accepted.json`. vector-search never opens it: `rules.py`
passes the path with `--accepted`, and a report run with `--all` shows everything. A `why` is
required, because an acceptance nobody can explain is a silenced finding rather than a decision. A
fact is matched on the TEXT of both lines, so editing either statement brings the pair back for a
fresh read. An acceptance that matches nothing any more is printed as STALE; drop it. `rules.py move`
renames entries along with the rule.

Most coherence candidates are NOT misfiled. An area is defined by what its gates reach, so a rule
gated on one project's folders belongs in that project's area even when its prose reads like a
`writing/` rule. A real misfiling is a rule whose subject, gate and area table all point somewhere
else; only then does `rules.py move` refile it.

**`facts` is the one that finds what nothing else could.** Redundancy does not usually look like two
rules about the same subject; it looks like one fact stated inside two rules about different
subjects, where neither reader ever learns the other copy exists and the two drift apart until they
contradict. It compares rule LINES rather than whole rules, and skips lines that are mostly a
cross-reference, because every pointer resembles every other pointer.

**`coverage` is gate auditing with evidence instead of judgement.** NEAR BUT NOT GATED means a rule
scores high against a file it is never injected on, which is a candidate missing gate. GATED BUT FAR
means the opposite, and counts how many files a gate reaches at low similarity. One caveat that
matters: a genuinely universal rule scores low against everything, so a low score is not on its own
evidence of an over-broad gate.

**Every number here is a candidate, never a verdict.** Two rules can sit at 0.87 because one
duplicates the other, or because they are the two deliberate halves of a split. No threshold can
tell those apart and none of these reports tries to; they narrow 235 rules to a dozen pairs a person
can actually read.

The reports live in the `vector-search` skill, because that is where the model, the index and the
corpus code live, and `rules.py` **shells out** to them rather than importing. Skills are silos: repo
code may read a skill, a skill may not read the repo, and cross-skill work goes through a subprocess.
If that skill or its model is absent, every command above prints one line saying so and the text
checks still run.
