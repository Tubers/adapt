#!/usr/bin/env python3
"""PreToolUse hook: a rule change goes to the USER, unless the refactoring audit asked for it.

The user's words, 2026-09-13: rule edits should be user approved, but not when the change is in
accordance with the audit command - new wording, a move or a scope change it flagged can be done
automatically. "Its more for weird one off changes that any instance might suggest out of the blue."
New rules and candidate approvals always ask. (knowledge_upkeep PLAN.md section 7, item 19.)

WHAT IT DECIDES
---------------
  NEW RULE          a rules/**/*.rule.md that does not exist yet                   ASK, always
  EDIT A RULE       an existing rule on a fresh audit worklist                     silent
                    any other existing rule                                        ASK
  EDIT rules/INDEX.md   every rule named in the CHANGED lines is on the worklist   silent
                    a changed line names an unflagged rule, or no rule at all      ASK
  rules.py decide <id> approve                                                     ASK, always
  rules.py move <rule> <new>   <rule> on the worklist, or --dry-run                silent
                    otherwise                                                      ASK
  anything else                                                                    silent

"Silent" means no output at all: the hook has no objection and the normal permission mode decides.
It never answers "allow", so it can never widen what the settings permit.

WHAT THE USER IS SHOWN
----------------------
The prompt shows the change itself, not a summary, because the user decides from it in one read:
a one-line headline (NEW RULE / RULE EDIT / INDEX EDIT / RULE MOVE / CANDIDATE APPROVAL, with the
path), the worklist's state, then the change. An edit or a rewrite is a full line diff ("- " removed,
"+ " added, "  " unchanged), a new rule is its full text, a NotebookEdit is the cell being replaced
and its new source, a shell write is the full command and the rule files it names, a move is old and
new name, and an approval is the candidate's id, fact text (read from the master copy
data/<repo>/candidates.jsonl), target rule and any --contradicts/--proof. Only past 6000 characters
is the text cut, and the cut says how much.

The worklist is .claude/skills/rules-system/data/<repo>/audit-worklist.json, written by
`python .claude/skills/rules-system/scripts/audit_worklist.py`. A missing, broken or stale one (over
24 hours) pre-approves nothing, so every existing-rule edit asks until the audit is run again.

EXACT VERSUS HEURISTIC
----------------------
  Write / Edit / NotebookEdit   EXACT. file_path (or notebook_path) is resolved against the payload's
                 cwd and checked against <project>/rules/ and against the disk. For rules/INDEX.md the
                 changed lines are a real diff, widened to whole lines for an Edit: old against new
                 for Edit, the file on disk against the new content for Write, so an unchanged
                 context line naming another rule does not count.
  Bash / PowerShell   HEURISTIC. A command is free text. `rules.py decide ... approve` and
                 `rules.py move` are matched by pattern. A write to a rule or INDEX path is recognised
                 when the path is the target of a redirect, is in the same command segment as tee,
                 sed -i, Set-Content, Add-Content, Out-File, New-Item or truncate, is the last path of a
                 cp/mv/Copy-Item/Move-Item, or appears anywhere in a command that also carries a Python
                 write (write_text, open(..., 'w'), os.replace, shutil.copy ...). A shell write to
                 INDEX.md is keyed on every rule the command names. A pattern path such as
                 rules/**/*.rule.md in a write asks, because its rules cannot be checked. Segments
                 that run rules.py itself are ignored for writes, so text inside `history add --what`
                 is not read as a write. It MISSES a path assembled at run time (root / "rules" / x)
                 and any script file that writes rules internally; it may ASK for a Python command
                 that only reads a rule while writing elsewhere - use the Read tool for the read.
                 Deleting a rule, and moving one away with mv, are not judged.

A SUB-AGENT CANNOT ANSWER AN "ASK". The prompt goes to the user of the main session; inside a
sub-agent it has nobody to answer it and acts as a refusal. A sub-agent that meets one should report
the change it wanted to the main session rather than retry by another route.

Fails OPEN: unreadable input, a missing rules-system skill, or any error in this script exits 0 with
no output.

Tests: python .claude/hooks/test_ask_rule_approval.py
"""

import difflib
import json
import os
import re
import sys
from pathlib import Path

HOOK_REPO = Path(__file__).resolve().parent.parent.parent
SCRIPTS_REL = Path(".claude") / "skills" / "rules-system" / "scripts"
DATA_REL = Path(".claude") / "skills" / "rules-system" / "data"
WORKLIST_CMD = "python .claude/skills/rules-system/scripts/audit_worklist.py"
CAP = 6000

TAIL = ("\n\nChanges the refactoring audit flagged pass without asking; refresh its list with "
        + WORKLIST_CMD + ". (A sub-agent cannot answer this prompt, so there it acts as a refusal: "
        "report the change to the main session instead.)")

DECIDE_RE = re.compile(r"rules\.py[\"']?\s+decide\b(.*)", re.IGNORECASE)
MOVE_RE = re.compile(r"rules\.py[\"']?\s+move\b(.*)", re.IGNORECASE)
RULES_PY_SEGMENT_RE = re.compile(r"rules\.py\b", re.IGNORECASE)
DECIDE_VALUED = ("--repo", "--rule", "--reason", "--why", "--overlap-ok", "--unchecked", "--contradicts",
                 "--proof")

_P = r"[^\s\"'<>|;&(),=`]"
PATH_RE = re.compile(_P + r"*?rules[/\\](?:" + _P + r"*?\.rule\.md|INDEX\.md)(?![\w.-])", re.IGNORECASE)
SEGMENT_WRITE_RE = re.compile(
    r"\b(?:tee|set-content|add-content|out-file|new-item|truncate|patch)\b|\bsed\b[^\n]*?\s-i", re.IGNORECASE)
COPY_VERB_RE = re.compile(r"(?:^|\s)(?:cp|mv|copy|move|rename|copy-item|move-item|rename-item)\b", re.IGNORECASE)
PY_WRITE_RE = re.compile(
    r"write_text|write_bytes|writelines|\.write\(|os\.replace|os\.rename|shutil\.(?:copy\w*|move)"
    r"|[\"'](?:w|a|x|r\+|w\+|a\+)b?[\"']")


def project_dir(payload: dict) -> Path:
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    if env:
        return Path(env)
    if payload.get("cwd"):
        return Path(payload["cwd"])
    return HOOK_REPO


def load_lib(root: Path):
    for base in (root, HOOK_REPO):
        scripts = base / SCRIPTS_REL
        if (scripts / "audit_worklist.py").is_file():
            if str(scripts) not in sys.path:
                sys.path.insert(0, str(scripts))
            try:
                import audit_worklist
                return audit_worklist
            except Exception:
                return None
    return None


def classify(path: str, cwd: str, root: Path):
    """-> ("rule", name, abspath) | ("index", None, abspath) | ("pattern", text, None) | None."""
    if not path:
        return None
    raw = path.strip().strip("\"'")
    full = os.path.abspath(raw if os.path.isabs(raw) else os.path.join(cwd, raw))
    base = os.path.abspath(os.path.join(str(root), "rules"))
    if not os.path.normcase(full).startswith(os.path.normcase(base) + os.sep):
        return None
    sub = full[len(base) + 1:].replace("\\", "/")
    if "*" in sub or "?" in sub:
        return ("pattern", raw, None)
    if sub.lower() == "index.md":
        return ("index", None, full)
    if sub.endswith(".rule.md"):
        return ("rule", sub[:-len(".rule.md")], full)
    return None


def cap(text: str, limit: int = CAP) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "\n... [cut %d of %d characters]" % (len(text) - limit, len(text))


def tokens(text: str):
    return [t[1:-1] if len(t) > 1 and t[0] == t[-1] and t[0] in "\"'" else t
            for t in re.findall(r'"[^"]*"|\'[^\']*\'|\S+', text)]


def changed_lines(old: str, new: str) -> str:
    a, b = (old or "").splitlines(), (new or "").splitlines()
    out = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag != "equal":
            out += a[i1:i2] + b[j1:j2]
    return "\n".join(out)


def line_diff(old: str, new: str, context=None) -> str:
    """Every line prefixed "- " removed, "+ " added, "  " unchanged. `context` keeps only that many
    unchanged lines around each change, for a large file such as rules/INDEX.md."""
    a, b = (old or "").splitlines(), (new or "").splitlines()
    rows = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag == "equal":
            rows += [("  ", l) for l in a[i1:i2]]
        else:
            rows += [("- ", l) for l in a[i1:i2]] + [("+ ", l) for l in b[j1:j2]]
    if context is not None:
        near = set()
        for i, (p, _) in enumerate(rows):
            if p != "  ":
                near.update(range(i - context, i + context + 1))
        kept, gap = [], False
        for i, row in enumerate(rows):
            if i in near:
                kept.append(row)
                gap = False
            elif not gap:
                kept.append(("  ", "..."))
                gap = True
        rows = kept
    if not any(p != "  " for p, _ in rows):
        return "  (no line changes)"
    return "\n".join(p + l for p, l in rows)


def full_lines(current: str, old: str, new: str):
    """Widen an Edit to the whole lines it sits in, when old_string is found in the file."""
    at = current.find(old) if old else -1
    if at < 0:
        return old, new
    start = current.rfind("\n", 0, at) + 1
    end = current.find("\n", at + len(old))
    end = len(current) if end < 0 else end
    return current[start:end], current[start:at] + new + current[at + len(old):end]


def read(path) -> str:
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


class Judge:
    def __init__(self, root: Path, cwd: str, lib):
        self.root, self.cwd, self.lib = root, cwd, lib
        self.flagged, self.note = lib.status(root)
        self._known = None

    @property
    def known(self):
        if self._known is None:
            self._known = self.lib.known_rules(self.root)
        return self._known

    def unflagged(self, name):
        return name not in self.flagged

    def worklist_line(self):
        return "Audit worklist: %s." % self.note

    # ------------------------------------------------------------------------------ file tools
    def file_tool(self, tool, ti):
        path = str(ti.get("file_path") or ti.get("notebook_path") or "")
        c = classify(path, self.cwd, self.root)
        if c is None or c[0] == "pattern":
            return None
        kind, name, full = c
        exists = os.path.isfile(full)
        current = read(full) if exists else ""
        if kind == "rule":
            return self.rule_file(tool, ti, name, exists, current)
        return self.index_file(tool, ti, exists, current)

    def rule_file(self, tool, ti, name, exists, current):
        path = "rules/%s.rule.md" % name
        if tool == "NotebookEdit":
            new = str(ti.get("new_source") or "")
            if not exists:
                return "NEW RULE %s\nNew rules always go to the user.\n\nProposed text (NotebookEdit):\n%s" \
                       % (path, line_diff("", new))
            if not self.unflagged(name):
                return None
            return ("RULE EDIT %s, not on the audit worklist\n%s\n\nNotebookEdit, cell %s, mode %s.\n"
                    "Cell source being replaced:\n%s\n\nNew source:\n%s"
                    % (path, self.worklist_line(), ti.get("cell_id") or "(none given)",
                       ti.get("edit_mode") or "replace", self.cell_source(current, ti.get("cell_id")),
                       new))
        if tool == "Write":
            new = str(ti.get("content") or "")
            if not exists:
                return "NEW RULE %s\nNew rules always go to the user.\n\nProposed text:\n%s" \
                       % (path, line_diff("", new))
            if not self.unflagged(name):
                return None
            return ("RULE EDIT %s, not on the audit worklist\n%s\n\nWrite replaces the whole file. "
                    "Diff against the file on disk:\n%s" % (path, self.worklist_line(), line_diff(current, new)))
        # Edit
        old, new = str(ti.get("old_string") or ""), str(ti.get("new_string") or "")
        if not exists:
            return ("NEW RULE %s\nNew rules always go to the user. (An Edit on a file that does not exist.)"
                    "\n\nProposed text:\n%s" % (path, line_diff("", new)))
        if not self.unflagged(name):
            return None
        how = "Edit with replace_all: EVERY occurrence of the old text is replaced." \
            if ti.get("replace_all") else "Edit."
        return ("RULE EDIT %s, not on the audit worklist\n%s\n\n%s Old text to new text:\n%s"
                % (path, self.worklist_line(), how, line_diff(old, new)))

    @staticmethod
    def cell_source(current, cell_id):
        try:
            cells = json.loads(current).get("cells", [])
            for i, cell in enumerate(cells):
                if cell.get("id") == cell_id or str(i) == str(cell_id):
                    src = cell.get("source", "")
                    return "".join(src) if isinstance(src, list) else str(src)
            return "(no cell %s in the file)" % cell_id
        except (ValueError, AttributeError):
            return "(unavailable: the file is not a notebook, so it has no cells)"

    def index_file(self, tool, ti, exists, current):
        if tool == "Write":
            new = str(ti.get("content") or "")
            return self.index_reason(changed_lines(current, new), "Write replaces the whole file. Changed lines, "
                                     "with two lines of context:\n" + line_diff(current, new, context=2))
        if tool == "Edit":
            old, new = full_lines(current, str(ti.get("old_string") or ""), str(ti.get("new_string") or ""))
            how = "Edit with replace_all: EVERY occurrence of the old text is replaced. " \
                if ti.get("replace_all") else "Edit. "
            return self.index_reason(changed_lines(old, new), how + "Old lines to new lines:\n" + line_diff(old, new))
        new = str(ti.get("new_source") or "")
        return self.index_reason(new, "NotebookEdit, new source:\n" + new)

    def index_reason(self, changed_text, shown):
        names = self.lib.names_in(changed_text, self.known)
        if names and names <= self.flagged:
            return None
        if names:
            head = "INDEX EDIT rules/INDEX.md, names rule(s) not on the audit worklist: %s" \
                   % ", ".join(sorted(names - self.flagged))
        else:
            head = "INDEX EDIT rules/INDEX.md, the changed lines name no rule, so it cannot be matched to the audit"
        named = ", ".join("rules/%s.rule.md" % n for n in sorted(names)) or "none"
        return "%s\n%s\nRules named in the change: %s\n\n%s" % (head, self.worklist_line(), named, shown)

    # ------------------------------------------------------------------------------ shell
    def shell(self, command):
        reasons = []
        segments = split_segments(command)
        for seg in segments:
            m = DECIDE_RE.search(seg)
            if m:
                r = self.decide(m.group(1), command)
                if r:
                    reasons.append(r)
            m = MOVE_RE.search(seg)
            if m:
                r = self.move(m.group(1))
                if r:
                    reasons.append(r)
        r = self.shell_writes(command, segments)
        if r:
            reasons.append(r)
        return "\n\n".join(reasons) or None

    def decide(self, args, command):
        toks = tokens(args)
        values, positional, i = {}, [], 0
        while i < len(toks):
            t = toks[i]
            if t in DECIDE_VALUED:
                values.setdefault(t, []).append(toks[i + 1] if i + 1 < len(toks) else "")
                i += 2
                continue
            if not t.startswith("-"):
                positional.append(t)
            i += 1
        if "approve" not in positional:
            return None
        cid = positional[0] if positional and positional[0] != "approve" else "(no id given)"
        repo = (values.get("--repo") or [self.lib.REPO_NAME])[0]
        target = (values.get("--rule") or [""])[0]
        lines = ["CANDIDATE APPROVAL %s%s" % (cid, " into rules/%s.rule.md" % self.lib.stem(target) if target else
                                             ", no --rule given"),
                 "Approving a candidate writes it into a rule. Candidate approvals always go to the user."]
        if target:
            exists = (self.root / "rules" / (self.lib.stem(target) + ".rule.md")).is_file()
            lines.append("Target rule: rules/%s.rule.md (%s)." % (self.lib.stem(target),
                                                               "exists" if exists else "does not exist yet: a NEW rule"))
        cand = self.candidate(repo, cid)
        if cand is None:
            lines.append("Fact: candidate %s was not found in %s." % (cid, (DATA_REL / repo / "candidates.jsonl").as_posix()))
        else:
            lines.append("Fact: %s" % cand.get("what", "(the candidate has no text)"))
            lines.append("Parked in %s, status %s, title: %s" % (cand.get("folder", "?"), cand.get("status", "?"),
                                                                 cand.get("title", "")))
        for flag in ("--contradicts", "--proof", "--overlap-ok", "--unchecked"):
            for v in values.get(flag, []):
                lines.append("%s %s" % (flag, v))
        if "--agrees" in toks:
            lines.append("--agrees")
        lines.append("\nCommand:\n" + command)
        return "\n".join(lines)

    def candidate(self, repo, cid):
        path = self.root / DATA_REL / repo / "candidates.jsonl"
        found = None
        for line in read(path).splitlines():
            try:
                e = json.loads(line)
            except ValueError:
                continue
            if isinstance(e, dict) and e.get("id") == cid:
                found = e
        return found

    def move(self, args):
        toks = tokens(args)
        if "--dry-run" in toks:
            return None
        toks = [t for t in toks if t and not t.startswith("-")]
        if not toks:
            return None
        name = self.lib.stem(toks[0])
        if "/" not in name:
            hits = [k for k in self.known if k.rsplit("/", 1)[-1] == name]
            name = hits[0] if len(hits) == 1 else name
        if not self.unflagged(name):
            return None
        new = "rules/%s.rule.md" % self.lib.stem(toks[1]) if len(toks) > 1 else "(no new name given)"
        return ("RULE MOVE rules/%s.rule.md, not on the audit worklist\n%s\n\nOld name: rules/%s.rule.md\n"
                "New name: %s" % (name, self.worklist_line(), name, new))

    def shell_writes(self, command, segments):
        kept = [s for s in segments if not RULES_PY_SEGMENT_RE.search(s)]
        text = "\n".join(kept)
        py_write = bool(PY_WRITE_RE.search(text))
        targets = []
        for seg in kept:
            for m in PATH_RE.finditer(seg):
                if (py_write or is_segment_target(seg, m)) and m.group(0) not in targets:
                    targets.append(m.group(0))
        heads, named = [], []
        for t in targets:
            c = classify(t, self.cwd, self.root)
            if c is None:
                continue
            kind, name, full = c
            if kind == "pattern":
                heads.append("RULE WRITE BY SHELL over the pattern %s, so the rules it touches cannot be checked "
                             "against the audit" % name)
                named.append(name)
            elif kind == "rule":
                path = "rules/%s.rule.md" % name
                named.append(path)
                if not os.path.isfile(full):
                    heads.append("NEW RULE %s, written by a shell command. New rules always go to the user." % path)
                elif self.unflagged(name):
                    heads.append("RULE EDIT %s by a shell command, not on the audit worklist" % path)
            else:
                named.append("rules/INDEX.md")
                names = self.lib.names_in(text, self.known)
                if not names:
                    heads.append("INDEX EDIT rules/INDEX.md by a shell command that names no rule, so it cannot be "
                                 "matched to the audit")
                elif not names <= self.flagged:
                    heads.append("INDEX EDIT rules/INDEX.md by a shell command naming rule(s) not on the audit "
                                 "worklist: %s" % ", ".join(sorted(names - self.flagged)))
        if not heads:
            return None
        also = sorted(self.lib.names_in(text, self.known))
        return ("%s\n%s\nRule files it writes: %s\nRules the command names: %s\n\nFull command:\n%s"
                % ("\n".join(heads), self.worklist_line(), ", ".join(dict.fromkeys(named)),
                   ", ".join("rules/%s.rule.md" % n for n in also) or "none", command))


def split_segments(command: str):
    """Split on unquoted ; & | and on every newline. A quote left open resets at the line end."""
    out, cur, quote = [], [], None
    for ch in command:
        if ch == "\n":
            out.append("".join(cur))
            cur, quote = [], None
            continue
        if quote:
            if ch == quote:
                quote = None
            cur.append(ch)
            continue
        if ch in "\"'":
            quote = ch
            cur.append(ch)
        elif ch in ";&|":
            out.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    out.append("".join(cur))
    return [s for s in out if s.strip()]


def is_segment_target(seg: str, m) -> bool:
    before = seg[:m.start()]
    if re.search(r">\s*[\"']?$", before):
        return True
    if SEGMENT_WRITE_RE.search(seg):
        return True
    if COPY_VERB_RE.search(seg):
        paths = [p for p in tokens(seg) if not p.startswith("-")]
        return bool(paths) and paths[-1] == m.group(0)
    return False


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    if not isinstance(payload, dict):
        return 0
    tool = payload.get("tool_name", "")
    ti = payload.get("tool_input") or {}
    if tool not in ("Write", "Edit", "NotebookEdit", "Bash", "PowerShell") or not isinstance(ti, dict):
        return 0
    try:
        root = project_dir(payload)
        lib = load_lib(root)
        if lib is None:
            return 0
        judge = Judge(root, str(payload.get("cwd") or os.getcwd()), lib)
        if tool in ("Bash", "PowerShell"):
            reason = judge.shell(str(ti.get("command") or ""))
        else:
            reason = judge.file_tool(tool, ti)
    except Exception:
        return 0
    if not reason:
        return 0
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                             "permissionDecision": "ask",
                                             "permissionDecisionReason": cap(reason) + TAIL}}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
