#!/usr/bin/env python3
"""One entry point for the rule system. Run `help` for the command list.

    python .claude/skills/rules-system/scripts/rules.py <command> [args]

Everything a person needs to inspect, audit or repair the rule system is a subcommand here. The
standalone `sync_index.py` and `reconcile.py` still exist because the hooks and the documentation
name them directly; this dispatches to the same code rather than duplicating it.

Exit codes: 0 success, 1 the command found something to report, 2 a usage or setup problem.
"""

import os
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rules_lib as lib  # noqa: E402


def project_root() -> Path:
    # <project>/.claude/skills/rules-system/scripts/rules.py
    return Path(__file__).resolve().parents[4]


# name -> (argument spec, one-line summary, longer note or "")
COMMANDS = {
    "help": ("[command]",
             "this listing, or the detail for one command",
             "With no argument it prints every command. With one it prints that command's note."),
    "list": ("[area]",
             "every rule, grouped by area folder, with its size and gate count",
             "Sizes are shown against the 10-line / 2048-byte cap so a rule near the limit is "
             "visible before it breaks. Pass an area (writing, xs, ai, ...) to narrow it."),
    "show": ("<rule>",
             "print one rule's full text and every gate that fires it",
             "The rule may be given as `xs/authoring`, `xs/authoring.rule.md` or "
             "`rules/xs/authoring.rule.md`."),
    "gates": ("[area]",
             "the gate table: which triggers pull in which rule",
             "Command gates are shown with their `cmd:` prefix; everything else is a path glob."),
    "which": ("<path> [path...]",
              "what WOULD fire for these paths, and which gate does it",
              "The single most useful command when tuning. It runs the real matcher, so it also "
              "shows you the silence on a path inside a skill, where nothing may ever fire."),
    "audit": ("[--gates]",
              "the whole refactoring pass: text checks, then every embedding report, in order",
              "The command to run when the job is IMPROVE THE RULES rather than answer a question. "
              "It runs reconcile and budget first, because they are free and because a dead gate or "
              "an over-budget rule makes every later report describe something that is already "
              "wrong. Then facts, dupes, coherence, hubs and, with --gates, coverage. That order is "
              "not cosmetic: merging a fact changes both rules' vectors, so dupes is only meaningful "
              "after facts; moving a rule changes two area centroids and two hubs, so hubs is only "
              "meaningful after coherence; and a gate is written against a rule's final path and "
              "final text, so coverage is last. Needs the vector-search index for everything past "
              "the text checks."),
    "upkeep": ("[--full] [--gates] [--json] [--stats]",
               "knowledge upkeep: indexes behind, runs missing their record, broken history, drift",
               "BRIEF by default: the cheap classes, and nothing printed when clean. --full adds reconcile, "
               "folders with code and no README, and results files outside the run layout. --gates also "
               "runs the slow semantic coverage report. --stats reads how runs close and what candidates "
               "became. A state report, not a task list; nothing runs it at session start. "
               "Plan: tool_development/knowledge_upkeep/PLAN.md."),
    "history": ("[folder] [runs|findings|changes|...] [--last N|--first N|--all] | show <id> | add <folder> ...",
                "read a folder's HISTORY.jsonl in slices, or write one stamped entry to it",
                "Every folder with its own agenda keeps its own HISTORY.jsonl; there is no central one. A "
                "slice is one line per entry, the last 5 by default, and a folder slice opens with that "
                "folder's state: its NOW task, latest entry and pending candidates. `add <folder> --kind K "
                "--title T [--result R] [--evidence P] [--refs R] [--no-rule WHY]` stamps id, time and "
                "session, creates the file, and refuses a run entry that names no run folder or closes with "
                "neither --refs nor --no-rule. Never edit the file by hand. --repo <name> targets another rule "
                "ecosystem; the default is this repository."),
    "use": ("[<name|folder> | --clear]",
            "set the rule set this session works with, once; every later command of both skills follows it",
            "Like OpenGL state: run it at the start of a session and then run commands as normal. The rule set is "
            "this repository by name or a folder under it that keeps its own rules/. With no argument it says "
            "which rule set is in force. Order: --repo on a command, then a nested rule set holding the working "
            "folder, then use, then this repository. Stored per session. A sub-agent has its parent's session id, so "
            "its own rule set comes from its home folder, which outranks the shared choice."),
    "view": ("[folder] [--static] [--no-open]",
             "open a project's tasks, history and candidates as one live page in the browser",
             "With no folder it opens the project this command runs inside, or the project this session "
             "last worked in. A named subfolder walks up to its project. The page redraws when HISTORY.jsonl, "
             "TASKS.md or the candidates change, keeps its filters and open entries, and its server stops "
             "three minutes after the page closes. Running it again for the same project reuses the page's "
             "server. --static writes a snapshot to the temp folder instead. The page only reads."),
    "tasks": ("[show|add|start|done|block|unblock|drop|detail|goal|ask|answer|act|acted|questions|wait|answers|withdraw] ... [--in <folder>]",
              "read or change a project's TASKS.md and QUESTIONS.jsonl; the only way they are written",
              "show (default); add \"<task>\" --details P [--at N]; start <id>; done [<id>] [--result R] "
              "[--kind K] [--evidence P] [--refs R] [--no-rule WHY]; block <id> --reason WHY; unblock <id> [--at N] "
              "(N places it among the not-started tasks; past the end puts it last); "
              "drop <id> --reason WHY; detail <id> \"<paragraph>\"; goal \"<goal>\". Every task carries its "
              "paragraph. Questions: ask <task id> \"<question>\" (the task shows ❓ until answered); "
              "answer <q id> \"<the user's answer>\"; questions lists them; wait [--timeout S] returns when the user "
              "has answered one in the viewer (run it in the background after asking); withdraw <q id> --reason WHY takes back an unanswered question, "
              "logged in history; answers reads the answered ones and "
              "consumes them, each logged as a history decision and removed from the file. Actions, for what only "
              "the user can do (log in, accept a dialog): act <task id> \"<what to do>\" (the task shows ❗ until "
              "done); acted <a id> [\"<note>\"] marks it done, as the viewer's button does; questions, wait, "
              "withdraw and answers handle actions too, a done action logged as a history note. Without --in it "
              "acts on the project the command runs inside or this session last worked in; a subfolder walks "
              "up. done logs the task in the project's history at once, starts the next task, and lets the "
              "oldest done task leave the window."),
    "init": ('<project folder> --goal "<goal>" [--task <parent task id>] [--no-questions]',
             "start a project: HISTORY.jsonl, TASKS.md and QUESTIONS.jsonl in its .rs folder, from the templates",
             "--no-questions leaves out QUESTIONS.jsonl, for a project no person answers. "
             "Creates the folder if needed. Refuses a folder inside another project, or one that already has "
             "all three files. A project that has only some of them, such as an older one with only its history, "
             "gets the missing ones and nothing already there is touched. Logs it in the project's history. "
             "Any folder may be a project, the repo root included (init .), and projects nest: records go to the "
             "nearest project file up the path. A project inside another names the parent task it serves with "
             "--task, recorded as its **Parent:** line; the parent's tasks list their sub-projects."),
    "migrate": ("[--dry-run]",
                "move every project's record files into its .rs folder",
                "Records used to sit directly in a project folder. Each project folder now keeps them in "
                "<folder>/.rs/. migrate finds every project still using the old place, moves each record "
                "file into .rs (with git mv when git tracks it, so history follows), and logs the move in "
                "that project's history. It refuses a folder whose .rs already holds a file of the same "
                "name. --dry-run lists what would move and changes nothing."),
    "park": ('"<fact>" --repo <repo> --in <folder> --run <run> | --no-run WHY',
             "park a possible rule: stamped, passed against every rule, written to its folder and the master",
             "A candidate is written to <folder>/HISTORY.jsonl AND .claude/skills/rules-system/data/<repo>/"
             "candidates.jsonl, as the same line, pending, with the time, the session, the run it came from "
             "and what the cosine pass found. It is never guidance. Parking shows near duplicates and "
             "same-subject rules at once but never refuses one. --repo is required: this repository's folder name, unless set once with rules.py use."),
    "candidates": ("--repo <repo> [next | --all]",
                   "pending rule candidates from the master copy; `next` gives the oldest, freshly checked",
                   "`next` prints the oldest pending candidate, runs the cosine pass again, proposes its scope, "
                   "shows its folder's state and prints the exact decide commands, so a session that knows "
                   "nothing can work through the queue one by one. --all includes decided ones."),
    "decide": ("<id> approve|reject --repo <repo> [--rule R ...] [--reason WHY]",
               "approve a candidate into the rule that carries it, or reject it; set in both copies",
               "approve --rule <area/slug> is refused unless the rule exists, is gated, fires on the fact's "
               "folder, and the pass shows no OTHER rule saying it at 0.80 (--overlap-ok WHY). Every other "
               "rule on the same subject at 0.70 must be answered: --agrees, or --contradicts <rule> --proof "
               "<run or entry id> for a GAME FACT the evidence overturns, and only once the old rule is "
               "corrected. Work procedure can never be contradicted. --unchecked WHY when the pass cannot run. "
               "reject needs --reason. The status, reason and a stamped decision record are set on the same "
               "line in the folder copy and the master copy."),
    "facts": ("[--cut 0.78]",
              "the SAME statement living in two different rules",
              "Needs the vector-search index. Compares every rule LINE against every other rule's "
              "lines, which is where redundancy actually hides: one fact in two rules about "
              "different subjects, drifting apart, with neither reader learning the other exists. "
              "Pointer lines are excluded. Every pair is a candidate, not a verdict."),
    "dupes": ("[--cut 0.80]",
              "whole rules that cover the same subject",
              "Needs the vector-search index. Coarser than `facts`: it fires when two rules are "
              "about the same thing, which is usually a deliberate split and occasionally a "
              "duplicate nobody noticed."),
    "coherence": ("[--worst 15]",
                  "rules sitting nearer another area's centre than their own",
                  "Needs the vector-search index. A filing check: a rule far from its own area and "
                  "near another is a candidate for moving, not proof that it belongs elsewhere."),
    "hubs": ("",
             "rules their own area's hub does not name",
             "Needs the vector-search index. A hub lists its area's rules; a rename or a split "
             "leaves the hub describing something that no longer exists, silently."),
    "coverage": ("[--limit 40]",
                 "rules near a file they never fire on, and gates that fire on distant files",
                 "Needs the vector-search index. This is the gate-mismatch report: NEAR BUT NOT "
                 "GATED is a candidate missing gate, GATED BUT FAR a candidate over-broad one. A "
                 "universal syntax rule scores low against every file, so low similarity alone is "
                 "not evidence there."),
    "asked": ("[--top 20]",
              "what the query logs say: zero-hit questions, repeats, and which hit got opened",
              "Needs the vector-search index. Reads every QUERIES.jsonl. A question that returned "
              "nothing names a gist gap; the same question in several folders names a missing rule "
              "or a missing gate; an answer nobody opened suggests a gist that oversells its rule."),
    "stats": ("",
              "firing counts per rule and per gate, and everything that has NEVER fired",
              "Reads .claude/rules-firings.jsonl, which the router appends to. A never-fired gate "
              "is the failure `reconcile` cannot see: a gate can match files on disk and still "
              "never be reached in real work."),
    "log": ("[n]",
            "the most recent firings, newest last (default 25)",
            "Each line is one injection: when, which rule, which gate, and what it matched."),
    "reconcile": ("",
                  "audit for dead globs, orphan rules and unpaired READMEs",
                  "Exits 1 when it finds anything, so it can be wired into a check."),
    "move": ("<rule> <new-name> [--dry-run]",
             "rename a rule and rewrite every reference: index, rules, READMEs",
             "The act half of a `coherence` finding. Names are area/[group/]slug, with or without "
             ".rule.md. Line endings are preserved, the README map is re-synced, and the firing "
             "log keeps the old name. `--dry-run` lists what would change and writes nothing. "
             "Check the gate description in rules/INDEX.md afterwards: it moves, it is not reworded."),
    "accept": ("<kind> <args> --why TEXT | --list [kind] | --drop <kind> <n>",
               "record a refactoring candidate you read and kept, so the reports stop showing it",
               "Kinds: facts <rule>:<line> <rule>:<line> | dupes <rule> <rule> | coherence <rule> | "
               "missing <file> <rule> | overbroad <rule>. Stored in this skill's data/accepted.json "
               "and handed to the reports with --accepted. A fact is matched on line TEXT, so "
               "editing either line brings the pair back. An acceptance matching nothing is "
               "reported STALE. `rules.py move` renames entries along with the rule."),
    "sync": ("[--check]",
             "rebuild the generated README section of rules/INDEX.md",
             "`--check` reports staleness and exits 1 without writing."),
    "test": ("",
             "run both suites: the library's and the hooks'",
             "The library suite builds its fixtures in a temp directory and reads nothing from "
             "the repo. The hook suite drives the real hooks against a throwaway repo."),
    "budget": ("",
               "every rule's size against the cap, worst first",
               "Exits 1 if any rule is over. The same check the PostToolUse hook runs."),
}


def cmd_help(root, args):
    if args:
        name = args[0].lstrip("-")
        if name not in COMMANDS:
            print(f"no such command: {name}")
            return 2
        spec, summary, note = COMMANDS[name]
        print(f"rules.py {name} {spec}\n\n  {summary}")
        if note:
            print(f"\n  {note}")
        return 0

    print("rules.py - inspect and maintain the path-gated rule system\n")
    print("  python .claude/skills/rules-system/scripts/rules.py <command> [args]\n")
    width = min(34, max(len(f"{n} {s}") for n, (s, _, _) in COMMANDS.items()))
    for name, (spec, summary, _) in COMMANDS.items():
        left = f"{name} {spec}".rstrip()
        if len(left) > width:
            print(f"  {left}")
            print(f"  {'':<{width}}   {summary}")
        else:
            print(f"  {left:<{width}}   {summary}")
    print("\n  `help <command>` prints the longer note for one of them.")
    print("  every command takes --repo <name|folder>, the rule ecosystem; without it, this repository. "
          "park, candidates and decide require it.")
    print(f"\n  rules live in {lib.RULES_DIRNAME}/<area>/[<group>/]<slug>{lib.RULE_SUFFIX}, "
          f"capped at {lib.MAX_RULE_LINES} lines and {lib.MAX_RULE_BYTES} bytes each.")
    print("  discovery is recursive: an area splits into groups when a subject needs several rules.")
    print("  the gate table is hand-maintained in rules/INDEX.md; the README section is generated.")
    return 0


def _by_area(names):
    out = defaultdict(list)
    for n in names:
        area = n.split("/")[0] if "/" in n else "(root)"
        out[area].append(n)
    return out


def cmd_list(root, args):
    names = lib.all_rules(root)
    if not names:
        print("no rule files found")
        return 2
    gate_count = defaultdict(int)
    for g in lib.load_gates(root):
        gate_count[g.rule] += 1

    wanted = args[0].strip("/") if args else None
    areas = _by_area(names)
    shown = 0
    for area in sorted(areas):
        if wanted and area != wanted:
            continue
        print(f"\n{area}/")
        for n in sorted(areas[area]):
            lines, size = lib.rule_size(root, n)
            flag = " OVER" if (lines > lib.MAX_RULE_LINES or size > lib.MAX_RULE_BYTES) else ""
            leaf = n.split("/", 1)[1] if "/" in n else n
            print(f"  {leaf:<34} {lines:2d} lines {size:5d} B  "
                  f"{gate_count.get(n, 0)} gate(s){flag}")
            shown += 1
    if wanted and shown == 0:
        print(f"no area called {wanted!r}. areas: {', '.join(sorted(areas))}")
        return 2
    print(f"\n{shown} rule(s)")
    return 0


def _resolve(root, token: str) -> str | None:
    t = token.replace("\\", "/").strip().lstrip("./")
    if t.startswith(lib.RULES_DIRNAME + "/"):
        t = t[len(lib.RULES_DIRNAME) + 1:]
    if not t.endswith(lib.RULE_SUFFIX):
        t += lib.RULE_SUFFIX
    names = lib.all_rules(root)
    if t in names:
        return t
    # allow a bare leaf name when it is unambiguous
    hits = [n for n in names if n.rsplit("/", 1)[-1] == t]
    return hits[0] if len(hits) == 1 else None


def cmd_show(root, args):
    if not args:
        print("usage: rules.py show <rule>")
        return 2
    name = _resolve(root, args[0])
    if not name:
        print(f"no rule matches {args[0]!r}. try: rules.py list")
        return 2
    body = lib.read_rule(root, name)
    lines, size = lib.rule_size(root, name)
    print(f"rules/{name}   ({lines} lines, {size} bytes)\n")
    print(body)
    gates = [g.raw for g in lib.load_gates(root) if g.rule == name]
    print("\nfires on:")
    for g in gates:
        print(f"  {g}")
    readmes = [p.relative_to(root).as_posix() for p in lib.find_readmes(root)
               if lib.readme_rule(p) == name]
    if readmes:
        print(f"\nnamed by {len(readmes)} README stub(s), e.g. {readmes[0]}")
    if not gates and not readmes:
        print("  NOTHING. This rule is orphaned and can never be injected.")
        return 1
    return 0


def cmd_gates(root, args):
    wanted = args[0].strip("/") if args else None
    gates = lib.load_gates(root)
    rows = defaultdict(list)
    for g in gates:
        rows[g.rule].append(g.raw)
    shown = 0
    for rule in sorted(rows):
        if wanted and not rule.startswith(wanted + "/"):
            continue
        print(f"{rule}")
        for raw in rows[rule]:
            kind = "cmd " if raw.startswith("cmd:") else "path"
            print(f"    {kind}  {raw}")
        shown += 1
    print(f"\n{shown} rule(s), {sum(len(v) for k, v in rows.items() if not wanted or k.startswith((wanted or '') + '/'))} gate(s)")
    return 0


def cmd_which(root, args):
    if not args:
        print("usage: rules.py which <path> [path...]")
        return 2
    rels = []
    for a in args:
        rel = lib.rel_posix(root, a)
        rels.append(rel if rel else a.replace("\\", "/"))
    for rel in rels:
        print(f"\n{rel}")
        if lib.is_skill_path(rel):
            print("  NOTHING - this is inside a skill, where no gate may ever fire.")
            continue
        matches = lib.match_paths(root, [rel])
        if not matches:
            print("  nothing fires here")
            continue
        for m in matches:
            print(f"  rules/{m.rule}")
            print(f"      via {m.gate}")
    return 0


def cmd_stats(root, args):
    s = lib.firing_stats(root)
    if s["records"] == 0:
        print("no firings recorded yet. The router writes "
              f"{lib.FIRING_LOG} the first time a rule is injected.")
        print(f"\n{len(s['declared_gates'])} gates declared, "
              f"{len(s['never_fired_rules'])} rules never fired.")
        return 0

    print(f"{s['records']} firings across {s['sessions']} session(s)")
    print(f"first {s['first']}   last {s['last']}\n")

    print("most-fired rules")
    for rule, n in sorted(s["per_rule"].items(), key=lambda kv: (-kv[1], kv[0]))[:15]:
        print(f"  {n:5d}  rules/{rule}")

    print("\nmost-fired gates")
    for (rule, gate), n in sorted(s["per_gate"].items(), key=lambda kv: (-kv[1], kv[0]))[:15]:
        print(f"  {n:5d}  {gate:<44} -> {rule}")

    if s["never_fired_gates"]:
        print(f"\ngates that have NEVER fired ({len(s['never_fired_gates'])}) - "
              "either too narrow, or aimed at work nobody does")
        for rule, gate in sorted(s["never_fired_gates"]):
            print(f"         {gate:<44} -> {rule}")

    if s["never_fired_rules"]:
        print(f"\nrules that have NEVER fired ({len(s['never_fired_rules'])})")
        for r in sorted(s["never_fired_rules"]):
            print(f"         rules/{r}")
    return 0


def cmd_log(root, args):
    try:
        n = int(args[0]) if args else 25
    except ValueError:
        print("usage: rules.py log [n]")
        return 2
    records = lib.read_firings(root)
    if not records:
        print("no firings recorded yet")
        return 0
    for r in records[-n:]:
        print(f"{r.get('ts','?')}  {r.get('tool',''):<10} rules/{r.get('rule','?')}")
        print(f"                     via {r.get('gate','?')}  <- {r.get('subject','')[:70]}")
    print(f"\n{len(records)} total, showing the last {min(n, len(records))}")
    return 0


def cmd_budget(root, args):
    names = lib.all_rules(root)
    rows = [(n, *lib.rule_size(root, n)) for n in names]
    rows.sort(key=lambda r: (-r[2], -r[1]))
    over = 0
    for n, lines, size in rows:
        bad = lines > lib.MAX_RULE_LINES or size > lib.MAX_RULE_BYTES
        over += bad
        print(f"  {'OVER' if bad else '  ok'}  {lines:2d}/{lib.MAX_RULE_LINES} lines  "
              f"{size:5d}/{lib.MAX_RULE_BYTES} B   rules/{n}")
    print(f"\n{len(rows)} rules, {over} over budget")
    return 1 if over else 0


def cmd_reconcile(root, args):
    import reconcile
    return reconcile.main(args)


def cmd_move(root, args):
    dry = "--dry-run" in args
    args = [a for a in args if a != "--dry-run"]
    if len(args) != 2:
        print("usage: rules.py move <rule> <new-name> [--dry-run]")
        return 2
    old = _resolve(root, args[0])
    if old is None:
        print(f"no such rule, or ambiguous: {args[0]}")
        return 2
    try:
        changed = lib.move_rule(root, old, args[1], write=not dry)
    except ValueError as e:
        print(e)
        return 2
    new = args[1][:-len(lib.RULE_SUFFIX)] if args[1].endswith(lib.RULE_SUFFIX) else args[1]
    print(("would move" if dry else "moved") + f" {old[:-len(lib.RULE_SUFFIX)]} -> {new}")
    for p, count in changed:
        print(f"  {count:3d}  {p.relative_to(root).as_posix()}")
    print(f"  {sum(c for _, c in changed)} reference(s) in {len(changed)} file(s)")
    if not dry:
        import accepted
        data = accepted.load()
        n = accepted.rename_rule(data, old, new)
        if n:
            accepted.save(data)
            print(f"  {n} accepted finding(s) renamed to follow it")
        import audit_worklist
        if audit_worklist.rename_in_worklist(root, old, new):
            print("  the audit worklist follows it, so its gate line can be refiled without asking")
    return 0


def cmd_accept(root, args):
    import accepted
    data = accepted.load()

    if not args or args[0] == "--list":
        kinds = [args[1]] if len(args) > 1 else list(accepted.KINDS)
        total = 0
        for kind in kinds:
            if kind not in accepted.KINDS:
                print(f"unknown kind: {kind}")
                return 2
            rows = data[kind]
            total += len(rows)
            print(f"{kind}: {len(rows)}")
            for n, e in enumerate(rows):
                print(f"  {n:3d}  {accepted.describe(kind, e)}")
                print(f"       why: {e.get('why', '')}")
        print(f"\n{total} accepted finding(s) in {accepted.DATA.relative_to(root).as_posix()}")
        return 0

    if args[0] == "--drop":
        if len(args) != 3 or args[1] not in accepted.KINDS or not args[2].isdigit():
            print("usage: rules.py accept --drop <kind> <n>   (n from accept --list)")
            return 2
        rows = data[args[1]]
        n = int(args[2])
        if n >= len(rows):
            print(f"{args[1]} has no entry {n}")
            return 2
        gone = rows.pop(n)
        accepted.save(data)
        print(f"dropped {args[1]} {n}: {accepted.describe(args[1], gone)}")
        return 0

    why = ""
    if "--why" in args:
        i = args.index("--why")
        why = " ".join(args[i + 1:i + 2])
        args = args[:i] + args[i + 2:]
    kind, rest = args[0], args[1:]
    try:
        entry = accepted.make_entry(root, kind, rest, why, lambda t: _resolve(root, t))
    except (ValueError, OSError) as e:
        print(e)
        return 2
    if not accepted.add(data, kind, entry):
        print(f"already accepted: {accepted.describe(kind, entry)}")
        return 0
    accepted.save(data)
    print(f"accepted {kind}: {accepted.describe(kind, entry)}")
    return 0


def cmd_sync(root, args):
    import sync_index
    return sync_index.main(args)


def cmd_test(root, args):
    import subprocess
    here = Path(__file__).resolve().parent
    rc = 0
    for label, script in (("library", here / "run_tests.py"),
                          ("hooks", root / ".claude" / "hooks" / "test_hooks.py")):
        if not script.is_file():
            print(f"{label}: MISSING {script}")
            rc = 1
            continue
        print(f"--- {label} ---")
        p = subprocess.run([sys.executable, str(script)])
        rc = rc or p.returncode
    return rc


def reindex():
    """Bring the embedding index up to date before reporting on it.

    An audit against a stale index quotes rules as they used to read, which is worse than no audit
    because the quotes look authoritative. The index is content-hashed and incremental, so this
    costs seconds unless rules actually changed.
    """
    import subprocess

    root = project_root()
    script = root.joinpath(".claude", "skills", "vector-search", "scripts", "index.py")
    if not script.is_file():
        return 2
    print("")
    print("reindexing, so the reports below describe the rules as they are now")
    try:
        return subprocess.run([sys.executable, str(script)], cwd=str(root)).returncode
    except OSError as e:
        print("could not reindex: %s" % e)
        return 2


def cmd_audit(root, args):
    """Text checks, then the embedding reports, in the order a person should act on them."""
    print("=" * 78)
    print("TEXT CHECKS - deterministic, no model. A finding here is a DEFECT, not a candidate.")
    print("=" * 78)
    import reconcile
    rc_text = reconcile.main([])
    print("")
    rc_text = cmd_budget(root, []) or rc_text
    reindex()
    rc_vec = vector_report("refactor", args)
    if rc_vec == 2:
        print("")
        print("The text checks above still stand. The rest of the pass needs the index:")
        print("    python .claude/skills/vector-search/scripts/index.py")
        return 2
    try:
        import audit_worklist
        data = audit_worklist.write_worklist(root, do_reindex=False)   # reindex() already ran above
        print("\naudit worklist: %d rule(s) may now be edited or moved without asking, for %d hours"
              % (len(data["rules"]), audit_worklist.MAX_AGE_HOURS))
    except Exception as e:                                            # noqa: BLE001
        print("\naudit worklist not written: %s" % e)
    return 1 if rc_text else rc_vec


def cmd_upkeep(root, args):
    import json
    import upkeep
    try:
        root, args = _scope(args)
    except ValueError as e:
        print(e)
        return 2
    if "--stats" in args:
        print(upkeep.stats(root))
        return 0
    full = "--full" in args or "--gates" in args
    classes = upkeep.report(root, full=full)
    if "--json" in args:
        print(json.dumps({"full": full, "baseline": upkeep.BASELINE, "classes": classes}, indent=1))
    else:
        text = upkeep.render_full(classes) if full else upkeep.render_brief(classes)
        if text:
            print(text)
    rc = 1 if any(c["items"] for c in classes) else 0
    if "--gates" in args:
        print("")
        vector_report("gates", [a for a in args if a not in ("--gates", "--full", "--json")])
    return rc


def _opt(args, flag, default=""):
    if flag in args:
        i = args.index(flag)
        if i + 1 < len(args):
            return args[i + 1]
    return default


def _many(args, flag):
    return [args[i + 1] for i, a in enumerate(args) if a == flag and i + 1 < len(args)]


def _positional(args, valued):
    out, skip = [], False
    for a in args:
        if skip:
            skip = False
            continue
        if a in valued:
            skip = True
            continue
        if a.startswith("--"):
            continue
        out.append(a)
    return out


def _show_path(p):
    try:
        return Path(p).resolve().relative_to(project_root().resolve()).as_posix()
    except ValueError:
        return str(p)


def _scope(args, required=False):
    """(ecosystem root, remaining args). --repo names the rule ecosystem a command works on: this
    repository by its folder name, or a folder under it that keeps its own rules/, such as a skill whose
    development has rules of its own. Its records live in the skill's data/<that folder's name>/."""
    project = project_root()
    if "--repo" in args:
        i = args.index("--repo")
        if i + 1 >= len(args):
            raise ValueError("--repo needs a name or a folder")
        return _ecosystem(args[i + 1]), list(args[:i]) + list(args[i + 2:])
    here = _from_cwd(project)
    if here != project:
        # working inside a nested rule set decides it, ahead of the session's choice: a sub-agent shares its
        # parent's session, and its home folder is the only thing that is its own (the user, 2026-09-14, q4)
        return here, list(args)
    used = read_use()
    if used:
        try:
            return _ecosystem(used["ecosystem"]), list(args)
        except ValueError as e:
            raise ValueError("this session uses the rule set %s, which is no longer valid: %s. Choose again: "
                             "rules.py use <name|folder>" % (used["ecosystem"], e))
    if required:
        raise ValueError("this command needs a rule set: --repo %s, or once per session: rules.py use %s"
                         % (project.name, project.name))
    return project, list(args)


# --------------------------------------------------------------------------------------------------
# the session's rule set, set once like OpenGL state (the user, 2026-09-14): rules.py use <name|folder>
# --------------------------------------------------------------------------------------------------
# Precedence: --repo on the command, then a nested rule set holding the working folder, then the session's
# `use`, then this repository. The working folder outranks `use` because sub-agents cannot be told apart from
# their parent (below): an adapt sub-agent works in its home folder, and that is what gives it its own rules. vector-search reads the same file (corpus.parse_repo), so one `use` sets both skills.
# Stored per session, keyed by CLAUDE_CODE_SESSION_ID. Measured 2026-09-14: a sub-agent has its parent's session
# id, and nothing in the environment tells them apart (CLAUDE_CODE_CHILD_SESSION=1 is set in the main session
# too), so a sub-agent sees and can change its parent's choice. How adapt sub-agents keep their own rule set is
# an open question to the user (knowledge_upkeep t12).

def _use_path():
    session = os.environ.get("CLAUDE_CODE_SESSION_ID", "")
    if not session:
        return None
    p = lib._state_path(session)
    return p.with_name(p.stem + ".use.json")


def read_use():
    """{"ecosystem": name, "set": time} this session chose with `rules.py use`, or None."""
    import json
    p = _use_path()
    if p is None:
        return None
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return d if isinstance(d, dict) and d.get("ecosystem") else None


def _from_cwd(project: Path) -> Path:
    """The nearest folder at or above the working folder that keeps its own rules/, inside this repository."""
    here, top = Path(os.getcwd()).resolve(), project.resolve()
    try:
        here.relative_to(top)
    except ValueError:
        return project
    for d in [here] + list(here.parents):
        if (d / lib.RULES_DIRNAME).is_dir():
            return project if d == top else d
        if d == top:
            break
    return project


def _eco_name(eco: Path, project: Path) -> str:
    return project.name if eco.resolve() == project.resolve() else eco.resolve().relative_to(project.resolve()).as_posix()


def cmd_use(root, args):
    import datetime
    import json
    project = project_root()
    if not args:
        used = read_use()
        if used:
            print("this session uses the rule set %s (set %s). Every rules-system and vector-search command works "
                  "on it; rules.py use --clear undoes it." % (used["ecosystem"], used.get("set", "")))
        else:
            eco = _from_cwd(project)
            print("no rule set chosen for this session: commands use %s, %s" % (
                _eco_name(eco, project), "the one holding the working folder" if eco != project else "this repository"))
        return 0
    p = _use_path()
    if p is None:
        print("no session id (CLAUDE_CODE_SESSION_ID), so there is no session to remember it for: pass --repo instead")
        return 2
    if args[0] == "--clear":
        try:
            p.unlink()
        except OSError:
            pass
        print("cleared: commands use the rule set holding the working folder, or this repository")
        return 0
    try:
        eco = _ecosystem(args[0])
    except ValueError as e:
        print(e)
        return 2
    name = _eco_name(eco, project)
    p.write_text(json.dumps({"ecosystem": name, "set": datetime.datetime.now().isoformat(timespec="seconds")}),
                 encoding="utf-8")
    print("this session now uses the rule set %s. Every rules-system and vector-search command works on it; "
          "rules.py use --clear undoes it." % name)
    return 0


def _ecosystem(val: str) -> Path:
    """A rule set named on the command line: this repository by name or ".", or a folder under it with rules/."""
    project = project_root()
    if val in (project.name, "."):
        return project
    p = Path(val) if Path(val).is_absolute() else project / val
    p = p.resolve()
    try:
        p.relative_to(project.resolve())
    except ValueError:
        raise ValueError("--repo %s is outside %s" % (val, project.name))
    if not p.is_dir():
        raise ValueError("--repo %s: no such folder. For this repository: --repo %s" % (val, project.name))
    if not (p / lib.RULES_DIRNAME).is_dir():
        raise ValueError("--repo %s keeps no rules/ of its own, so it is not a rule ecosystem yet" % val)
    return project if p == project.resolve() else p


def _nearest(root):
    import candidates

    def run(text):
        if Path(root).resolve() != project_root().resolve():
            raise candidates.Unavailable("the vector-search index holds the rules of %s only, not %s"
                                         % (project_root().name, Path(root).name))
        return candidates.pass_by_subprocess(root, text)
    return run


def _resolver(root):
    def resolve(t):
        # an existing rule resolves to its name; a missing one passes through so the library can name it
        return _resolve(root, t) or (t if t.endswith(lib.RULE_SUFFIX) else t + lib.RULE_SUFFIX)
    return resolve


HISTORY_USAGE = ("usage: rules.py history [folder] [runs|findings|changes|decisions|dead-ends|notes|candidates] "
                 "[--last N|--first N|--all] [--since DATE] [--grep WORD] [--status S] [--repo R]\n"
                 "       rules.py history show <id>\n"
                 "       rules.py history merge <project folder> [--dry-run]\n"
                 '       rules.py history add <folder> --kind <kind> --title "<title>" [--result R] '
                 "[--evidence P]... [--refs R]... [--no-rule WHY]")


def cmd_history(root, args):
    import history
    try:
        root, args = _scope(args)
    except ValueError as e:
        print(e)
        return 2
    if args and args[0] == "add":
        return _history_add(root, args[1:])
    if args and args[0] == "merge":
        pos = _positional(args[1:], ())
        if len(pos) != 1:
            print("usage: rules.py history merge <project folder> [--dry-run]")
            return 2
        try:
            s = history.merge(root, pos[0], write="--dry-run" not in args)
        except ValueError as e:
            print(e)
            return 2
        print("%s %d entries from %d subfolder histories into %s"
              % ("would merge" if "--dry-run" in args else "merged", s["entries"], len(s["sources"]),
                 _show_path(s["target"])))
        for src in s["sources"]:
            print("  %s" % src)
        if s["backup"]:
            print("originals moved to %s" % _show_path(s["backup"]))
            print("")
            print(history.folder_state(root, s["project"]))
        return 0
    if args and args[0] == "show":
        if len(args) < 2:
            print(HISTORY_USAGE)
            return 2
        try:
            print(history.show(root, args[1]))
        except ValueError as e:
            print(e)
            return 2
        return 0
    kinds, folder = [], None
    for a in _positional(args, ("--first", "--last", "--since", "--grep", "--status")):
        if a in history.KIND_WORDS:
            kinds.append(history.KIND_WORDS[a])
        elif a in history.ADD_KINDS or a == "candidate":
            kinds.append(a)
        elif folder is None:
            folder = a
        else:
            print(HISTORY_USAGE)
            return 2

    def num(flag):
        v = _opt(args, flag)
        return int(v) if v.isdigit() else None
    try:
        print(history.render_slice(root, folder, kinds, first=num("--first"), last=num("--last"),
                                   everything="--all" in args, since=_opt(args, "--since") or None,
                                   grep=_opt(args, "--grep") or None, status=_opt(args, "--status") or None))
    except ValueError as e:
        print(e)
        return 2
    return 0


def _history_add(root, args):
    import history
    valued = ("--kind", "--title", "--what", "--result", "--evidence", "--refs", "--no-rule", "--numbers",
              "--tags", "--status", "--supersedes")
    pos = _positional(args, valued)
    if len(pos) != 1 or not _opt(args, "--kind") or not _opt(args, "--title"):
        print(HISTORY_USAGE)
        return 2
    try:
        r = history.add(root, pos[0], _opt(args, "--kind"), _opt(args, "--title"), what=_opt(args, "--what"),
                        result=_opt(args, "--result"), evidence=_many(args, "--evidence"),
                        refs=_many(args, "--refs"), no_rule=_opt(args, "--no-rule"),
                        numbers=_many(args, "--numbers"), tags=_many(args, "--tags"),
                        status=_opt(args, "--status"), supersedes=_opt(args, "--supersedes"))
    except ValueError as e:
        print(e)
        return 2
    print("logged %s in %s" % (r["entry"]["id"], _show_path(r["path"])))
    print("")
    print(history.folder_state(root, r["folder"]))
    return 0


def _task_project(root, args):
    import viewer
    return viewer.resolve_project(root, _opt(args, "--in") or None, os.getcwd(),
                                  os.environ.get("CLAUDE_CODE_SESSION_ID", ""))[0]


def cmd_tasks(root, args):
    import history
    import questions
    import tasks
    try:
        root, args = _scope(args)
        project = _task_project(root, args)
        pos = _positional(args, ("--in", "--details", "--at", "--result", "--kind", "--evidence", "--refs",
                                 "--no-rule", "--reason", "--timeout"))
        verb = pos[0] if pos else "show"
        rest = pos[1:]
        if verb == "show":
            print(tasks.show(root, project))
            return 0
        if verb == "add":
            k = tasks.add(root, project, " ".join(rest), details=_opt(args, "--details"), at=_opt(args, "--at") or None)
            print("added %s: %s" % (k["id"], k["text"]))
        elif verb == "start":
            k = tasks.start(root, project, rest[0] if rest else "")
            print("started %s: %s" % (k["id"], k["text"]))
        elif verb == "done":
            r = tasks.done(root, project, rest[0] if rest else None, result=_opt(args, "--result"),
                           kind=_opt(args, "--kind") or "change", evidence=_many(args, "--evidence"),
                           refs=_many(args, "--refs"), no_rule=_opt(args, "--no-rule"))
            print("done %s, logged as %s" % (r["task"]["id"], r["entry"]["id"]))
            if r["started"]:
                print("started %s: %s" % (r["started"]["id"], r["started"]["text"]))
        elif verb == "block":
            r = tasks.block(root, project, rest[0] if rest else "", _opt(args, "--reason"))
            print("blocked %s" % r["task"]["id"] + ("; started %s" % r["started"]["id"] if r["started"] else ""))
        elif verb == "unblock":
            print("unblocked %s" % tasks.unblock(root, project, rest[0] if rest else "", at=_opt(args, "--at") or None)["id"])
        elif verb == "drop":
            r = tasks.drop(root, project, rest[0] if rest else "", _opt(args, "--reason"))
            print("dropped %s, logged as %s" % (r["task"]["id"], r["entry"]["id"]))
        elif verb == "detail":
            tasks.detail(root, project, rest[0] if rest else "", " ".join(rest[1:]))
            print("details set for %s" % rest[0])
        elif verb == "goal":
            tasks.set_goal(root, project, " ".join(rest))
            print("goal set")
        elif verb == "ask":
            q = questions.ask(root, project, rest[0] if rest else "", " ".join(rest[1:]))
            print("asked %s on %s: %s" % (q["id"], q["task"], q["question"]))
            import viewer
            print("the viewer is open, so the user sees and answers it there" if viewer.running(root, project)
                  else "no viewer is open for %s: ask the user in chat as well, or open it: rules.py view" % project)
        elif verb == "answer":
            q = questions.answer(root, project, rest[0] if rest else "", " ".join(rest[1:]))
            print("answer recorded for %s. An instance reads it with: rules.py tasks answers" % q["id"])
        elif verb == "act":
            a = questions.act(root, project, rest[0] if rest else "", " ".join(rest[1:]))
            print("asked the user to act, %s on %s: %s" % (a["id"], a["task"], a["action"]))
            import viewer
            print("the viewer is open, so the user sees it there and marks it done" if viewer.running(root, project)
                  else "no viewer is open for %s: tell the user in chat as well, or open it: rules.py view" % project)
        elif verb == "acted":
            a = questions.acted(root, project, rest[0] if rest else "", " ".join(rest[1:]))
            print("%s marked done. An instance reads it with: rules.py tasks answers" % a["id"])
        elif verb == "questions":
            print(questions.show(root, project))
            return 0
        elif verb == "withdraw":
            r = questions.withdraw(root, project, rest[0] if rest else "", _opt(args, "--reason"))
            print("withdrew %s, logged as %s" % (r["item"]["id"], r["entry"]["id"]))
        elif verb == "wait":
            got = questions.wait(root, project, timeout=float(_opt(args, "--timeout") or 43200))
            print(("the user replied to %s in the viewer. Read them: rules.py tasks --in %s answers"
                   % (", ".join(q["id"] for q in got), project)) if got else "no answer arrived before the timeout")
            return 0
        elif verb == "answers":
            got = questions.consume(root, project)
            if not got:
                print("no answered questions or done actions waiting in %s/" % project)
                print(questions.show(root, project))
                return 0
            for r in got:
                q = r.get("question") or r["action"]
                print("%s  on %s %s" % (q["id"], q.get("task", ""), r["task_text"]))
                if "action" in r:
                    print("  ❗ %s" % q["action"])
                    print("  done %s%s" % (q["done"], (": " + q["note"]) if q.get("note") else ""))
                else:
                    print("  Q: %s" % q["question"])
                    print("  A: %s" % q["answer"])
                print("  logged as %s; removed from QUESTIONS.jsonl" % r["entry"]["id"])
            return 0
        else:
            print("no such tasks verb: %s. See: rules.py help tasks" % verb)
            return 2
    except (ValueError, IndexError) as e:
        print(e)
        return 2
    print("")
    print(tasks.show(root, project))
    return 0


def cmd_init(root, args):
    import history
    import tasks
    try:
        root, args = _scope(args)
        no_questions = "--no-questions" in args
        args = [a for a in args if a != "--no-questions"]
        pos = _positional(args, ("--goal", "--task"))
        if len(pos) != 1 or not _opt(args, "--goal"):
            print('usage: rules.py init <project folder> --goal "<goal>" [--task <parent task id>] [--no-questions]')
            return 2
        r = tasks.init(root, pos[0], _opt(args, "--goal"), task=_opt(args, "--task") or None,
                       questions=not no_questions)
    except ValueError as e:
        print(e)
        return 2
    print(("completed project %s/, adding:" if r["entry"]["title"].startswith("project files completed") else "started project %s/") % r["project"])
    for f in r["files"]:
        print("  %s" % f)
    print("")
    print(history.folder_state(root, r["project"]))
    print("Add its first tasks: rules.py tasks add \"<task>\" --in %s" % r["project"])
    return 0


def cmd_view(root, args):
    import viewer
    try:
        root, args = _scope(args)
    except ValueError as e:
        print(e)
        return 2
    pos = _positional(args, ())
    try:
        project, how = viewer.resolve_project(root, pos[0] if pos else None, os.getcwd(),
                                              os.environ.get("CLAUDE_CODE_SESSION_ID", ""))
    except ValueError as e:
        print(e)
        return 2
    if "--status" in args:
        url = viewer.running(root, project)
        print(("a viewer is open for %s at %s: ask the user questions there (rules.py tasks ask)" % (project, url))
              if url else "no viewer is open for %s: ask the user in chat" % project)
        return 0
    if "--static" in args:
        path = viewer.write_static(root, project)
        print("wrote a snapshot of %s to %s" % (project, path))
        if "--no-open" not in args:
            viewer.webbrowser.open(path.as_uri())
        return 0
    try:
        url, reused = viewer.launch(root, project, open_browser="--no-open" not in args)
    except RuntimeError as e:
        print(e)
        return 2
    print("%s %s at %s  (chosen: %s)" % ("showing" if reused else "opened", project, url, how))
    print("Live: it redraws when the project's records change, and stops three minutes after the page is closed.")
    return 0


def cmd_park(root, args):
    import candidates
    import history
    try:
        root, args = _scope(args, required=True)
    except ValueError as e:
        print(e)
        return 2
    words = _positional(args, ("--in", "--run", "--no-run", "--evidence", "--title"))
    folder = _opt(args, "--in")
    if not words or not folder:
        print('usage: rules.py park "<fact>" --repo <repo> --in <folder> --run test_runs/<scenario>/runs/<stamp> '
              "| --no-run WHY [--evidence P]... [--title T]")
        return 2
    try:
        r = candidates.park(root, " ".join(words), folder, run=_opt(args, "--run") or None,
                            no_run=_opt(args, "--no-run"), evidence=_many(args, "--evidence"),
                            title=_opt(args, "--title") or None, nearest=_nearest(root))
    except ValueError as e:
        print(e)
        return 2
    c = r["candidate"]
    print("parked %s  [pending]" % c["id"])
    print("  in  %s" % _show_path(r["path"]))
    print("  and %s" % _show_path(r["master"]))
    print("It is not a rule, and reaches no session until it is approved.")
    print("")
    print("nearest existing rules, from the cosine pass:")
    print(candidates.render_neighbours(r["neighbours"], r["unavailable"]))
    if r["scope"]:
        print("")
        print("scope, from the same pass:")
        print(candidates.render_scope(r["scope"], r["pass"]["files_skipped"]))
    print("")
    print(history.folder_state(root, r["folder"]))
    return 0


def cmd_candidates(root, args):
    import candidates
    import history
    try:
        root, args = _scope(args, required=True)
    except ValueError as e:
        print(e)
        return 2
    repo = Path(root).name
    if args and args[0] == "next":
        c = candidates.next_pending(root)
        if not c:
            print("no pending rule candidates in %s." % repo)
            return 0
        print("NEXT PENDING CANDIDATE in %s, 1 of %d" % (repo, len(candidates.queue(root))))
        print(candidates.render_candidate(c))
        print("")
        folder = str(c.get("folder", "")).strip("/")
        try:
            found = candidates.as_pass(_nearest(root)(c.get("what") or c.get("title", "")))
            print("the cosine pass, run now:")
            print(candidates.render_neighbours(found["rules"]))
            print("")
            print("scope:")
            print(candidates.render_scope(candidates.propose_scope(root, folder, found["rules"], found["files"]),
                                          found["files_skipped"]))
        except candidates.Unavailable as e:
            print(candidates.render_neighbours(None, str(e)))
        print("")
        print(history.folder_state(root, folder))
        print("")
        print("decide it:")
        print("  rules.py decide %s approve --repo %s --rule <area/slug> [--agrees] "
              "[--contradicts <rule> --proof <run>]" % (c["id"], repo))
        print('  rules.py decide %s reject --repo %s --reason "<why>"' % (c["id"], repo))
        return 0
    rows = candidates.queue(root, include_decided="--all" in args)
    if not rows:
        print("no rule candidates %s in %s." % ("recorded" if "--all" in args else "pending", repo))
        return 0
    for c in rows:
        print("  %s  [%s]  %s" % (c.get("id"), c.get("status", "pending"), c.get("folder", "")))
        print("      %s" % str(c.get("title", ""))[:110])
        if c.get("status", "pending") != "pending":
            print("      %s" % c.get("reason", ""))
    pending = sum(1 for c in rows if c.get("status", "pending") == "pending")
    print("\n%d candidate(s), %d pending, from %s. Work through them: rules.py candidates next --repo %s"
          % (len(rows), pending, _show_path(history.master_path(root)), repo))
    return 0


def cmd_decide(root, args):
    import candidates
    import history
    try:
        root, args = _scope(args, required=True)
    except ValueError as e:
        print(e)
        return 2
    pos = _positional(args, ("--rule", "--reason", "--why", "--overlap-ok", "--unchecked", "--contradicts",
                             "--proof"))
    if len(pos) != 2:
        print("usage: rules.py decide <id> approve --repo <repo> --rule <area/slug> [--agrees] "
              "[--contradicts <rule> --proof <p>] | <id> reject --repo <repo> --reason WHY")
        return 2
    try:
        r = candidates.decide(root, pos[0], pos[1], rule=_opt(args, "--rule") or None,
                              reason=_opt(args, "--reason") or _opt(args, "--why"),
                              overlap_ok=_opt(args, "--overlap-ok"), unchecked=_opt(args, "--unchecked"),
                              agrees="--agrees" in args, contradicts=_many(args, "--contradicts"),
                              proof=_many(args, "--proof"), nearest=_nearest(root), resolve=_resolver(root))
    except ValueError as e:
        print(e)
        return 2
    c = r["candidate"]
    print("%s %s: %s" % (c["id"], c["status"], c["reason"]))
    print("  set in %s" % _show_path(r["path"]))
    print("  and    %s" % _show_path(r["master"]))
    decided = c.get("decided") or {}
    if r["neighbours"] is not None:
        print("")
        print("nearest other rules, from the cosine pass:")
        print(candidates.render_neighbours(r["neighbours"]))
        print("")
        print("scope. Gates on the rule now: %s" % ", ".join((decided.get("scope") or {}).get("gates") or []))
        print(candidates.render_scope(r["scope"], r.get("files_skipped")))
    elif decided.get("unchecked"):
        print("cosine pass NOT run: %s" % decided["unchecked"])
    print("")
    print(history.folder_state(root, r["folder"]))
    return 0


def cmd_facts(root, args):
    return vector_report("facts", args)


def cmd_dupes(root, args):
    return vector_report("dupes", args)


def cmd_coherence(root, args):
    return vector_report("coherence", args)


def cmd_hubs(root, args):
    return vector_report("hubs", args)


def cmd_coverage(root, args):
    return vector_report("gates", args)          # named `gates` there, `coverage` here: this file
                                                 # already has a `gates` command for the gate table


def cmd_asked(root, args):
    return vector_report("queries", args)


def cmd_migrate(root, args):
    import shutil
    import subprocess
    import history
    import records
    import upkeep
    try:
        root, args = _scope(args)
    except ValueError as e:
        print(e)
        return 2
    dry = "--dry-run" in args
    _, _, legacy = upkeep.project_folders(root)
    if not legacy:
        print("nothing to migrate: every project keeps its records in its .rs folder")
        return 0
    status = 0
    for rel in legacy:
        d = root if rel == "." else root / rel
        files = records.legacy(d)
        clash = [f.name for f in files if records.path(d, f.name).exists()]
        if clash:
            print("%s/: .rs already holds %s; move by hand after comparing" % (rel, ", ".join(clash)))
            status = 1
            continue
        print("%s/: %s -> %s/" % (rel, ", ".join(f.name for f in files), records.RECORDS_DIR))
        if dry:
            continue
        records.folder(d).mkdir(parents=True, exist_ok=True)
        moved = []
        for f in files:
            dst = records.path(d, f.name)
            tracked = subprocess.run(["git", "ls-files", "--error-unmatch", str(f)], cwd=root,
                                     capture_output=True).returncode == 0
            if tracked:
                subprocess.run(["git", "mv", str(f), str(dst)], cwd=root, check=True, capture_output=True)
            else:
                shutil.move(str(f), str(dst))
            moved.append(f.name)
        history.add(root, "" if rel == "." else rel, "change",
                    "record files moved into the project's .rs folder",
                    what="%s moved from %s/ to %s/%s/ by rules.py migrate"
                         % (", ".join(moved), rel, rel, records.RECORDS_DIR))
    return status


DISPATCH = {
    "help": cmd_help, "list": cmd_list, "show": cmd_show, "gates": cmd_gates,
    "which": cmd_which, "stats": cmd_stats, "log": cmd_log, "budget": cmd_budget,
    "reconcile": cmd_reconcile, "sync": cmd_sync, "move": cmd_move, "accept": cmd_accept, "test": cmd_test,
    "audit": cmd_audit,
    "upkeep": cmd_upkeep,
    "history": cmd_history,
    "view": cmd_view,
    "use": cmd_use,
    "tasks": cmd_tasks,
    "init": cmd_init,
    "migrate": cmd_migrate,
    "park": cmd_park,
    "candidates": cmd_candidates,
    "decide": cmd_decide,
    "facts": cmd_facts,
    "dupes": cmd_dupes,
    "coherence": cmd_coherence,
    "hubs": cmd_hubs,
    "coverage": cmd_coverage,
    "asked": cmd_asked,
}


VECTOR_SEARCH = ("vector-search", "scripts", "report.py")
VECTOR_REPORTS = ("facts", "dupes", "coherence", "hubs", "gates", "queries",
                  "refactor")


FILTERED_REPORTS = ("facts", "dupes", "coherence", "gates", "refactor")


def report_args(which, extra=None, accepted_path=None):
    """The report's argument list. Reports that can hide accepted findings are handed this skill's
    list by path: vector-search never opens a file inside another skill on its own."""
    import accepted
    path = accepted_path or accepted.DATA
    args = [which] + list(extra or [])
    if which in FILTERED_REPORTS and "--all" not in args and Path(path).is_file():
        args += ["--accepted", str(path)]
    return [a for a in args if a != "--all"]


def vector_report(which, extra=None):
    """Run one of vector-search's embedding reports. Shells out on purpose: skills are silos, and a
    missing model must degrade to a message rather than a traceback."""
    import subprocess

    root = project_root()
    script = root.joinpath(".claude", "skills", *VECTOR_SEARCH)
    if not script.is_file():
        print("the vector-search skill is not installed, so %s is unavailable." % which)
        print("Text-only checks still run: reconcile, budget, stats.")
        return 2
    cmd = [sys.executable, str(script)] + report_args(which, extra)
    try:
        return subprocess.run(cmd, cwd=str(root)).returncode
    except OSError as e:
        print("could not run %s: %s" % (which, e))
        return 2


def main(argv) -> int:
    # Records carry icons and non-ASCII text, and a Windows console defaults to cp1252, which cannot print
    # them: the command would do its work and then crash on the report. Always write UTF-8, and replace
    # anything the terminal still cannot show rather than failing.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    root = project_root()
    if not argv or argv[0] in ("-h", "--help"):
        return cmd_help(root, [])
    name, args = argv[0], argv[1:]
    fn = DISPATCH.get(name)
    if fn is None:
        print(f"no such command: {name}\n")
        cmd_help(root, [])
        return 2
    if name not in SCOPES_ITSELF and name != "help":
        try:
            root, args = _scope(args)
        except ValueError as e:
            print(e)
            return 2
        if root.resolve() != project_root().resolve() and name not in ANY_ECOSYSTEM:
            print("%s works on %s's own rules only for now, not --repo %s: it reads data or indexes kept for "
                  "this repository alone (knowledge_upkeep PLAN items 29 and 31). Commands that take any "
                  "ecosystem: %s." % (name, project_root().name, root.relative_to(project_root()).as_posix(),
                                      ", ".join(sorted(ANY_ECOSYSTEM | SCOPES_ITSELF))))
            return 2
    return fn(root, args)


# Every command takes --repo. These read it themselves (park, candidates and decide require it); main reads it
# for the rest, so a --repo is never mistaken for an argument, and refuses another ecosystem to any command
# that still reads this repository's own data: the firing log, accepted findings, the audit worklist, the index.
SCOPES_ITSELF = {"upkeep", "history", "tasks", "init", "migrate", "view", "park", "candidates", "decide", "use"}
ANY_ECOSYSTEM = {"list", "show", "gates", "which", "budget"}


if __name__ == "__main__":
    try:
        code = main(sys.argv[1:])
    except (BrokenPipeError, OSError) as e:
        # Output piped into something that stopped reading (`| head`): the work is already done, so exit
        # quietly. Windows reports this as EINVAL rather than a broken pipe, so an EINVAL counts only when
        # stdout itself can no longer be written; any other EINVAL is a real error and is raised. A bare flush
        # is no test, since the failed write already emptied the buffer: write one byte and flush it.
        closed = isinstance(e, BrokenPipeError)
        if not closed and getattr(e, "errno", None) == 22:
            try:
                sys.stdout.write("\n")
                sys.stdout.flush()
            except OSError:
                closed = True
        if closed:
            try:
                sys.stdout = open(os.devnull, "w")
            except OSError:
                pass
            code = 0
        else:
            raise
    sys.exit(code)
