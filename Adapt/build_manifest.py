"""Build Adapt/skills.manifest.json: everything each generic skill needs to be installed into a project.

    python Adapt/build_manifest.py          # write the manifest
    python Adapt/build_manifest.py --check  # say whether the manifest still matches this project

What is facts about a skill that no file states (who owns which hook, which rule, what it needs from other
skills, what it needs installed on the machine) is written by hand below, in SKILLS. Everything a file
already states is read from that file, so the manifest cannot drift from the project it describes: hook
entries from .claude/settings.json, gate lines from rules/INDEX.md, the file list from the skill folder.
The installer (the Adapt project's installer task) reads the manifest; the self-tests (Adapt/selftest/) prove the result.
"""

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = HERE / "skills.manifest.json"

# Claude Code matches file deny rules only in the Edit(...) form, which covers every file-editing tool; a
# Write(...) deny is ignored with a warning (seen in a headless session, 2026-09-14).
CLAUDE_MD_DENY = ["Edit(**/CLAUDE.md)", "Edit(**/CLAUDE.local.md)"]

# ---------------------------------------------------------------------------------------------------------
# by hand: what no file states
# ---------------------------------------------------------------------------------------------------------
SKILLS = {
    "rules-system": {
        "summary": "path-gated rules injected by hook; per-project history, tasks and questions; rule candidates; "
                   "the live viewer; the session's rule set (rules.py use)",
        "requires": {"skills": [], "python": ">=3.10", "packages": []},
        "optional": {"vector-search": "the cosine pass for park/decide, rules.py audit and its reports, upkeep's "
                                      "INDEX class; without it they say the pass is unavailable"},
        "hook_files": ["_bootstrap.py", "rule_router.py", "guard_records.py", "guard_docs.py",
                       "ask_rule_approval.py", "post_write_checks.py"],
        "hook_tests": ["test_hooks.py", "test_ask_rule_approval.py"],
        "rules": ["repo/rule-lifecycle", "repo/no-claude-md", "repo/hooks", "repo/automatic-checks",
                  "repo/dependency-direction", "repo/no-silent-changes", "writing/readme-and-rules",
                  "writing/fact-ownership", "writing/history-log", "writing/tasks", "writing/rule-candidates",
                  "lifecycle/archive-folders"],
        "creates": ["rules/INDEX.md (header and the GENERATED readme-triggers markers)",
                    ".claude/skills/rules-system/data/<repo>/ (candidates, accepted findings, audit worklist)",
                    ".claude/rules-firings.jsonl (written by the router)"],
        "settings": {"skillOverrides": {"rules-system": "name-only"},
                     "permissions": {"allow": ["Bash(python *)", "Bash(py *)", "PowerShell(python *)",
                                               "Skill(rules-system)"],
                                     "deny": CLAUDE_MD_DENY}},
        "env": {"CLAUDE_PROJECT_DIR": "set by Claude Code; hooks find the project with it",
                "CLAUDE_CODE_SESSION_ID": "set by Claude Code; keys the session's rule set, focus and once-per-session state",
                "CLAUDE_RULE_STATE_DIR": "optional; where per-session state lives (default: the system temp folder)"},
        "post_install": ["python .claude/skills/rules-system/scripts/rules.py sync",
                         "python .claude/skills/rules-system/scripts/rules.py reconcile",
                         "python .claude/skills/rules-system/scripts/rules.py budget"],
        "tests": ["python .claude/skills/rules-system/scripts/run_tests.py", "python .claude/hooks/test_hooks.py",
                  "python .claude/hooks/test_ask_rule_approval.py"],
        "selftest": "Adapt/selftest/rules-system/test_rules_system.py",
    },
    "vector-search": {
        "summary": "search rules, project history and every skill's docs and code by meaning; the refactoring "
                   "reports rules-system's audit runs",
        "requires": {"skills": ["rules-system"], "python": ">=3.10",
                     "packages": {"numpy": ">=2.0 (tested 2.5.2)", "onnxruntime": ">=1.18 (tested 1.30.0)",
                                  "tokenizers": ">=0.15 (tested 0.23.2)"}},
        "requires_why": {"rules-system": "corpus.py and report.py import rules_lib from .claude/skills/rules-system/scripts "
                                         "to parse rules/INDEX.md and match gates: a known exception to "
                                         "repo/dependency-direction; it also reads rules.py use's session state file"},
        "external": {"model": {
            "name": "voyage-4-nano, ONNX int8 export (Apache 2.0)",
            "source": "https://huggingface.co/onnx-community/voyage-4-nano-ONNX",
            "files": ["config.json", "tokenizer.json", "tokenizer_config.json", "onnx/model_quantized.onnx",
                      "onnx/model_quantized.onnx_data"],
            "size_mb": 431,
            "graph_sha256_16": "e2999ae63b575e34",
            "graph_sha256_16_of": "onnx/model_quantized.onnx (what embed.fingerprint_for hashes)",
            "locate": ["$RULE_SEARCH_MODEL", "C:\\Users\\<user>\\OneDrive\\Desktop\\models\\voyage-4-nano-onnx (embed.DEFAULT_MODEL)"],
            "if_missing": "download the files above into the default path, or into a folder named by RULE_SEARCH_MODEL, "
                          "then check the graph hash"}},
        "hook_files": ["query_log.py", "query_opened.py"],
        "hook_tests": [],
        "rules": ["repo/vector-search", "writing/query-log"],
        "ships_data": ["golden.jsonl (the golden questions, rewritten per project)"],
        "creates": [".claude/skills/vector-search/data/ (indexes, file cache, model hash memo, query logs)"],
        "settings": {"skillOverrides": {"vector-search": "name-only"},
                     "permissions": {"allow": ["Skill(vector-search)"], "deny": []}},
        "env": {"RULE_SEARCH_MODEL": "optional; the model folder", "RULE_SEARCH_THREADS": "optional; default 8"},
        "post_install": ["python .claude/skills/vector-search/scripts/index.py --ns all"],
        "tests": ["python .claude/skills/vector-search/scripts/run_tests.py"],
        "selftest": None,
    },
    "handoff": {
        "summary": "a handoff is written once, read once by the session the user assigns, then retired and reviewed",
        "requires": {"skills": [], "python": ">=3.10", "packages": []},
        "optional": {"rules-system": "the writing doc tells a writer to park rule candidates with rules.py park"},
        "hook_files": ["announce_handoff.py", "gate_handoff_read.py", "block_handoff_write.py", "handoff_skills.py",
                       "handoff_registry.py", "handoff_lib.py"],
        "hook_tests": ["test_block_handoff_write.py"],
        "hook_imports": {"handoff_registry.py": ".claude/skills/handoff/scripts/handoff_data.py",
                         "gate_handoff_read.py": "handoff_lib.py", "handoff_skills.py": "handoff_lib.py (and reads "
                         "skillOverrides in .claude/settings.json)"},
        "rules": ["lifecycle/handoff"],
        "creates": [".claude/skills/handoff/data/ (log.jsonl and one folder per retired handoff)"],
        "settings": {"skillOverrides": {"handoff": "user-invocable-only"},
                     "permissions": {"allow": ["Skill(handoff)"], "deny": []}},
        "env": {"HANDOFF_DATA_DIR": "optional; tests only, redirects the record"},
        "post_install": ["python .claude/skills/handoff/scripts/handoffs.py check"],
        "tests": ["python .claude/skills/handoff/scripts/run_tests.py", "python .claude/hooks/test_block_handoff_write.py"],
        "selftest": "Adapt/selftest/handoff/test_handoff.py",
    },
    "caveman": {
        "summary": "the compressed communication style; ships the project's output style",
        "requires": {"skills": [], "python": None, "packages": []},
        "output_style": {"file": ".claude/output-styles/caveman.md", "level": "ultra",
                         "settings": {"outputStyle": "caveman"}},
        "hook_files": [], "hook_tests": [],
        "rules": ["writing/compressed-register"],
        "settings": {"skillOverrides": {"caveman": "user-invocable-only"},
                     "permissions": {"allow": ["Skill(caveman)"], "deny": []}},
        "post_install": [], "tests": [], "selftest": None,
    },
    "caveman-compress": {
        "summary": "compress a memory or doc file into caveman register, with a backup and a validator",
        "requires": {"skills": ["caveman"], "python": ">=3.10", "packages": []},
        "optional": {"anthropic": "used when ANTHROPIC_API_KEY is set; otherwise it shells out to the claude CLI",
                     "tiktoken": "benchmark.py only"},
        "hook_files": [], "hook_tests": [], "rules": [],
        "settings": {"skillOverrides": {"caveman-compress": "user-invocable-only"},
                     "permissions": {"allow": ["Skill(caveman-compress)"], "deny": []}},
        "env": {"ANTHROPIC_API_KEY": "optional; routes compression through the SDK"},
        "post_install": [], "tests": [], "selftest": None,
    },
    "caveman-help": {
        "summary": "a quick reference card for the caveman skills",
        "requires": {"skills": ["caveman"], "python": None, "packages": []},
        "hook_files": [], "hook_tests": [], "rules": [],
        "settings": {"skillOverrides": {"caveman-help": "user-invocable-only"},
                     "permissions": {"allow": ["Skill(caveman-help)"], "deny": []}},
        "post_install": [], "tests": [], "selftest": None,
    },
}

INSTALL_ORDER = ["rules-system", "vector-search", "handoff", "caveman", "caveman-compress", "caveman-help"]

PROJECT = {
    "claude_md": "forbidden at any path: settings deny it, guard_docs.py refuses it, post_write_checks.py renames one",
    "workspace_trust": "Claude Code ignores a project's permissions.allow until the workspace is trusted: run Claude Code "
                       "in the project once and accept the trust dialog. Hooks run regardless. The installer must say so.",
    "rules_dir": "rules/ at the project root, never .claude/rules/ (auto-loaded like CLAUDE.md)",
    "settings_merge": "merge, never overwrite: hook entries are added to the group with the same event and matcher, "
                      "in the order listed; skillOverrides and permissions are unioned; outputStyle is set only if unset",
    "bundled_skill_overrides": {k: v for k, v in {
        "claude-api": "user-invocable-only", "code-review": "user-invocable-only", "simplify": "user-invocable-only",
        "security-review": "user-invocable-only", "update-config": "user-invocable-only",
        "fewer-permission-prompts": "user-invocable-only", "claude-in-chrome": "user-invocable-only",
        "dataviz": "off", "design": "off", "artifact-design": "off", "artifact-diagramming": "off",
        "artifact-capabilities": "off", "loop": "off", "schedule": "off", "workflow-authoring": "off",
        "run": "off", "init": "off", "keybindings-help": "off"}.items()},
    "python": ">=3.10 (tested 3.12.4)",
}


# ---------------------------------------------------------------------------------------------------------
# read from the project
# ---------------------------------------------------------------------------------------------------------

def skill_files(skill):
    base = ROOT / ".claude" / "skills" / skill
    return sorted(p.relative_to(ROOT).as_posix() for p in base.rglob("*")
                  if p.is_file() and "__pycache__" not in p.parts
                  and not p.relative_to(base).as_posix().startswith("data/"))


def hook_entries(hook_file):
    """The exact settings.json entries that run this hook: event, matcher, position and the entry itself."""
    st = json.loads((ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))
    out = []
    for event, groups in st.get("hooks", {}).items():
        for g in groups:
            for i, h in enumerate(g.get("hooks", [])):
                if re.search(r"[\\/]" + re.escape(hook_file) + r"\"?$", h.get("command", "")):
                    out.append({"event": event, "matcher": g.get("matcher"), "position": i, "entry": h})
    return out


def gate_lines(rule):
    lines = (ROOT / "rules" / "INDEX.md").read_text(encoding="utf-8").splitlines()
    return [l for l in lines if l.startswith("- **%s.rule.md**" % rule)]


def build():
    skills = {}
    for name in INSTALL_ORDER:
        meta = dict(SKILLS[name])
        meta["files"] = skill_files(name)
        meta["hooks"] = [e for h in meta.get("hook_files", []) for e in hook_entries(h)]
        meta["rules"] = [{"rule": "rules/%s.rule.md" % r, "gate": gate_lines(r)} for r in meta.get("rules", [])]
        skills[name] = meta
    return {"schema": 1, "generated_from": ROOT.name, "install_order": INSTALL_ORDER, "project": PROJECT,
            "skills": skills}


def problems(m):
    """What does not match the project: a missing file, a hook that is not registered, a rule without a gate."""
    out = []
    for name, s in m["skills"].items():
        for f in s["files"]:
            if not (ROOT / f).is_file():
                out.append("%s: file missing %s" % (name, f))
        for h in s.get("hook_files", []) + s.get("hook_tests", []):
            if not (ROOT / ".claude" / "hooks" / h).is_file():
                out.append("%s: hook file missing %s" % (name, h))
        registered = {e["entry"]["command"] for e in s["hooks"]}
        for h in s.get("hook_files", []):
            if h not in ("_bootstrap.py", "handoff_lib.py") and not any(h in c for c in registered):
                out.append("%s: %s is not registered in settings.json" % (name, h))
        for r in s["rules"]:
            if not (ROOT / r["rule"]).is_file():
                out.append("%s: rule missing %s" % (name, r["rule"]))
            if len(r["gate"]) != 1:
                out.append("%s: %s has %d gate lines" % (name, r["rule"], len(r["gate"])))
    owned = {r["rule"] for s in m["skills"].values() for r in s["rules"]}
    for p in (ROOT / "rules").rglob("*.rule.md"):
        if p.relative_to(ROOT).as_posix() not in owned:
            out.append("rule owned by no skill: %s" % p.relative_to(ROOT).as_posix())
    hooked = {h for s in m["skills"].values() for h in s.get("hook_files", []) + s.get("hook_tests", [])}
    for p in (ROOT / ".claude" / "hooks").glob("*.py"):
        if p.name not in hooked:
            out.append("hook file owned by no skill: %s" % p.name)
    return out


def main():
    m = build()
    probs = problems(m)
    if "--check" in sys.argv:
        on_disk = json.loads(OUT.read_text(encoding="utf-8")) if OUT.is_file() else None
        stale = on_disk != m
        print("manifest %s; %d problem(s)" % ("is STALE: rebuild it" if stale else "matches the project", len(probs)))
        for p in probs:
            print("  " + p)
        return 1 if stale or probs else 0
    OUT.write_text(json.dumps(m, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    n_files = sum(len(s["files"]) for s in m["skills"].values())
    n_hooks = sum(len(s["hooks"]) for s in m["skills"].values())
    print("wrote %s: %d skills, %d files, %d hook entries, %d rules" % (
        OUT.relative_to(ROOT), len(m["skills"]), n_files, n_hooks, sum(len(s["rules"]) for s in m["skills"].values())))
    for p in probs:
        print("  problem: " + p)
    return 1 if probs else 0


if __name__ == "__main__":
    sys.exit(main())
