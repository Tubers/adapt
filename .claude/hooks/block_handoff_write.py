#!/usr/bin/env python3
"""PreToolUse hook: a handoff is WRITTEN ONCE, READ ONCE, then RETIRED TO THE ARCHIVE.

A handoff is a message from one session to exactly one other session. It is never rewritten and
never maintained, and it never stays at the live path once it has been read. What makes it worth
reading is that it was true when it was written, so an edited handoff is a document nobody can
date; and a handoff that outlives its reading in place is the exact failure this repo has already
paid for - a fresh session picking up a finished thing as if it were pending.

It is kept, though. Retired handoffs go to the handoff skill's data folder rather than the
bin, because this repo has no version control and a spent message is cheap to keep. That folder's
README says, in its first line, that nothing in it needs reading.

    written once   by /handoff, at the end of a session
    read once      by the next session, at its start
    retired        by that same session, moved to archive/handoffs/ once it has read it

THE RULE THIS ENFORCES IS "CREATE YES, MODIFY NO"
-------------------------------------------------
  CREATE   allowed. `/handoff` writes the next handoff only after the session that read the last
           one retired it, so at that moment the name is free. Blocking creation would make the
           lifecycle unenforceable by the very hook meant to protect it.
  MODIFY   refused. Any edit to a handoff that already exists on disk.
  MOVE     allowed when the DESTINATION is not an existing handoff. Retiring one to
           archive/handoffs/ is the sanctioned end of its life, so `mv`/`Move-Item` must pass;
           `mv new.md <existing handoff>` is an overwrite wearing a different verb and does not.
  DELETE   allowed - `rm`, `del`, `Remove-Item`, `os.remove` and `Path.unlink` all pass. The
           convention is to archive rather than delete, but the guard does not force that: it
           protects a handoff's CONTENT, and it is not this script's business to stop someone
           throwing away their own spent message.
  READ     never blocked, by any route.

WHAT THIS BLOCKS, AND HOW RELIABLY
----------------------------------
Two arms, and they are not equally strong. Say so rather than implying one guarantee:

  Write / Edit / NotebookEdit   EXACT. The tool hands over `tool_input.file_path`, so the name and
                 its existence on disk are both checked directly.

  Bash / PowerShell   HEURISTIC. A shell command is arbitrary text; there is no file_path field to
                 read. This denies a command that names a handoff AND carries a mutation token
                 (a redirect, `tee`, `sed -i`, an editor, a copy/move, or a Python write mode)
                 when that handoff exists. It will occasionally refuse a command that only meant
                 to read - the deny message says how to proceed. That trade is deliberate: the
                 in-place edits that made this rule necessary went through `python - <<EOF` in
                 Bash, not through Edit, so a Write|Edit-only hook would have caught none of them.
                 When a command mutates a handoff but no path can be parsed out of it, this FAILS
                 CLOSED - an unparseable mutation is the dangerous case, not the safe one.
                 "Names a handoff" means a FILE whose name starts with handoff, or a variable
                 naming one. A folder or file that only contains the word, such as
                 `value_handoff_to_xs/`, is not a handoff and is never refused on that account.

Dated variants (`HANDOFF-2026-09-05.md`) are protected on the same terms, so choosing a dated name
is not a way around this.

Tests: python .claude/hooks/test_block_handoff_write.py
"""

import json
import os
import re
import sys

PROTECTED_BASENAME = "handoff.md"

# Tokens that mean a shell command is going to CHANGE something rather than read it. Kept
# deliberately short: every entry is a way a file gets written, and a longer list would refuse more
# reads without catching more writes.
#
# DELETION IS NOT ON THIS LIST, AND NEITHER ARE MOVE AND COPY - both deliberate, both for the same
# reason, and both were on it once. See the module docstring for delete, and MOVE_VERB_RE below for
# move/copy: those verbs are judged by their DESTINATION instead of banned outright, because
# retiring a handoff to the archive is a routine operation on it.
MUTATION_TOKENS = (
    "tee", "sed -i", "truncate", "dd ", "patch ",
    "vim", "nvim", "nano", "emacs",
    "'w'", '"w"', "'a'", '"a"', "write_text", "writelines", "os.replace",
    "set-content", "add-content", "out-file",
)

# Move and copy are NOT flat mutation tokens, because relocating a handoff is now the sanctioned
# end of its life - it is archived rather than deleted, so `mv` is a routine operation on it. What
# must still be refused is a move or copy whose DESTINATION is a handoff that already exists, which
# is a content rewrite wearing a different verb. So these verbs are judged by where they point.
#
# This is the same lesson `rm` taught: a blanket token on the verb blocks the sanctioned operation
# in order to catch an exotic one, which is the wrong trade.
# Matched on WORD BOUNDARIES, not as substrings. `Remove-Item` - the sanctioned PowerShell delete -
# contains the literal "move-item", so a substring test refused the very deletion this design
# depends on. Caught by the suite, not by reading.
MOVE_VERB_RE = re.compile(
    r"\b(?:mv|move|rename|cp|copy|copy-item|move-item)\b|shutil\.", re.IGNORECASE)

# A BARE `>` IS NOT A MUTATION TOKEN, and that is a fix rather than an omission. It was one until
# 2026-09-05, which meant any command containing `2>&1` - a stream redirect, not a file write - was
# refused if the word "handoff" appeared anywhere else in it. That fires constantly: it blocked a
# `python tests.py 2>&1 | tail` run inside this very hook's own test loop. A redirect only counts
# when it points AT something handoff-shaped, which is what this pattern requires.
#
# SCOPED TO HANDOFF FILES, 2026-09-12. "Handoff-shaped" used to mean any token CONTAINING the word,
# so a write to rules/INDEX.md was refused because the same command named the measurement folder
# `value_handoff_to_xs/`. A folder that merely contains the word is not a handoff. A target now has
# to be what a handoff actually is: a file whose NAME starts with handoff, or a variable naming one.
_REDIRECT_AT_HANDOFF_RE = re.compile(
    r">>?\s*[\"']?(?:[^\s\"'>]*[/\\])?(?:handoff|\$\{?(?:env:)?\w*handoff)", re.IGNORECASE)

# Paths that end in a markdown file with the word in it, so existence can be checked. Filtered again
# by is_handoff_name(), because `notes_on_handoff.md` matches here and is not a handoff.
_HANDOFF_PATH_RE = re.compile(r"[A-Za-z0-9_./\\:~+-]*handoff[A-Za-z0-9_.-]*\.md", re.IGNORECASE)

# A shell or PowerShell VARIABLE naming a handoff: `$HANDOFF_FILE`, `${handoff}`, `$env:HANDOFF`.
# The one shape where a write is aimed at a handoff and no path can be read out of the text, so the
# only one that fails closed.
_HANDOFF_VAR_RE = re.compile(r"\$\{?(?:env:)?\w*handoff\w*", re.IGNORECASE)

DENY_MESSAGE = (
    "A handoff is WRITTEN ONCE, READ ONCE, then RETIRED. This one already exists, so it may not "
    "be changed.\n\n"
    "Reading it is fine and is not blocked. So is RETIRING it, which is the intended end of its "
    "life: `python .claude/skills/handoff/scripts/handoffs.py retire <path>` files it under "
    ".claude/skills/handoff/data/<date>-<scope>/.\n\n"
    "It is a snapshot of what one session knew: what makes it worth reading is that it was true "
    "when it was written, and it carries no accuracy obligation afterwards. So if something in it "
    "is now wrong, that is EXPECTED - do not correct it here. Put the current fact in the document "
    "that OWNS it (the folder's HISTORY.jsonl, or the rule that owns the "
    "convention) and let this file retire on schedule: read it, move anything durable to its "
    "owner, then retire it with the script. If what you have to say is about the handoff ITSELF - "
    "it was wrong, thin or ambiguous - that is a REVIEW, not an edit: `handoffs.py draft "
    "<occasion>` opens one beside it. A fresh handoff is written by /handoff at the END of a "
    "session."
)

SHELL_ARM_NOTE = (
    "\n\n(Refused by the shell arm of this hook, which matches on command text and is therefore "
    "approximate. If this command only READS a handoff, re-run it without a redirect or a write "
    "mode in the same command - or use the Read tool.)"
)


def is_handoff_name(path: str) -> bool:
    """`HANDOFF.md`, and dated variants like `HANDOFF-2026-09-05.md`.

    The dated forms are covered because a session may still choose one, and leaving them
    unprotected would be a hole the moment anybody did.
    """
    if not path:
        return False
    base = os.path.basename(path.replace("\\", "/")).lower()
    # rules/lifecycle/handoff.rule.md is the rule ABOUT handoffs, not a handoff. Rule files are
    # explicitly editable at any time, and without this exclusion the guard made that one rule the
    # only permanently uneditable file in the repo - found by it refusing an edit to itself.
    if base.endswith(".rule.md"):
        return False
    return base == PROTECTED_BASENAME or (base.startswith("handoff") and base.endswith(".md"))


def _last_path_argument(command: str):
    """The destination of a move/copy: the last path-like token on the (first) command line.

    Deliberately simple. It handles the shapes an archive move actually takes - `mv A B`,
    `Move-Item A B`, a quoted path with spaces - and gives up rather than guessing on anything
    exotic. Giving up returns None, which leaves the decision to the general mutation check below
    rather than silently allowing.
    """
    line = command.strip().splitlines()[0] if command.strip() else ""
    line = line.split("&&")[0].split("|")[0].split(";")[0]
    tokens = re.findall(r'"[^"]+"|\'[^\']+\'|\S+', line)
    for token in reversed(tokens):
        cleaned = token.strip("\"'")
        if cleaned.startswith("-") or not cleaned:
            continue                      # a flag, not a path
        if cleaned.lower() in ("mv", "cp", "move", "copy", "rename",
                               "move-item", "copy-item"):
            return None                   # ran out of arguments before finding a path
        return cleaned
    return None


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        # A hook that cannot parse its input must not block real work. Fail open, but loudly enough
        # to be visible in the transcript rather than silently disabled.
        print(json.dumps({"systemMessage": "block_handoff_write.py: unreadable hook input"}))
        return 0

    tool = payload.get("tool_name", "")
    tool_input = payload.get("tool_input") or {}
    cwd = payload.get("cwd") or os.getcwd()

    def exists(path: str) -> bool:
        return os.path.isfile(path if os.path.isabs(path) else os.path.join(cwd, path))

    reason = None

    if tool in ("Write", "NotebookEdit"):
        path = str(tool_input.get("file_path", ""))
        if is_handoff_name(path) and exists(path):
            reason = DENY_MESSAGE

    elif tool == "Edit":
        # Edit only ever targets an existing file, so there is no create case to allow.
        if is_handoff_name(str(tool_input.get("file_path", ""))):
            reason = DENY_MESSAGE

    elif tool in ("Bash", "PowerShell"):
        command = str(tool_input.get("command", ""))
        lowered = command.lower()
        if "handoff" not in lowered:
            return 0

        candidates = [c for c in _HANDOFF_PATH_RE.findall(command) if is_handoff_name(c)]

        if MOVE_VERB_RE.search(command):
            # Judged by DESTINATION, which for every one of these verbs is the last path argument.
            # `mv <handoff> archive/...` relocates it and is allowed - that is how a handoff is
            # retired. `mv new.md <existing handoff>` overwrites it and is refused.
            dest = _last_path_argument(command)
            if dest and is_handoff_name(dest) and exists(dest):
                reason = DENY_MESSAGE + SHELL_ARM_NOTE

        if reason is None:
            mutates = (any(t in lowered for t in MUTATION_TOKENS)
                       or bool(_REDIRECT_AT_HANDOFF_RE.search(command)))
            if mutates:
                if candidates:
                    # Deny only if one of them is really there. Every named handoff being absent
                    # means this is CREATION, which is how the next handoff gets written.
                    if any(exists(c) for c in candidates):
                        reason = DENY_MESSAGE + SHELL_ARM_NOTE
                elif _HANDOFF_VAR_RE.search(command):
                    # A mutation aimed at a VARIABLE naming a handoff, whose path cannot be
                    # resolved - `cat x > $HANDOFF_FILE`. Fail CLOSED: an unparseable mutation is
                    # the dangerous case, not the safe one. A word inside a folder name is not
                    # this case, and no longer fails closed.
                    reason = DENY_MESSAGE + SHELL_ARM_NOTE

    if reason is None:
        return 0

    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
