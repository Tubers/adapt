"""Copy rules-system and vector-search from this repository into Adapt's workspace template.

    python Adapt/build/scripts/vendor.py          copy, then report
    python Adapt/build/scripts/vendor.py --check  report drift only; exit 1 if the copies differ

Adapt ships its own copies of these two skills. The originals live in this repository's
.claude/skills/ and keep evolving; the copies in adapt/workspace/.claude/skills/ must be re-synced
on purpose, never edited in place. VENDORED.json beside the copies records the source commit and a
hash of every file, so drift in either direction shows up.

Not copied: machine and repository data (data/), compiled files, and vector-search's golden.jsonl,
whose questions are about this repository's own rules and mean nothing in a workspace.
"""

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
SOURCE = REPO / ".claude" / "skills"
TARGET = REPO / "Adapt" / "build" / "adapt" / "workspace" / ".claude" / "skills"
SKILLS = ("rules-system", "vector-search")
EXCLUDED_DIRS = {"data", "__pycache__"}
EXCLUDED_FILES = {"golden.jsonl"}
EXCLUDED_SUFFIXES = {".pyc"}
MANIFEST = TARGET / "VENDORED.json"


def wanted(rel: Path) -> bool:
    if any(part in EXCLUDED_DIRS for part in rel.parts[:-1]):
        return False
    return rel.name not in EXCLUDED_FILES and rel.suffix not in EXCLUDED_SUFFIXES


def files_of(root: Path) -> dict:
    out = {}
    if not root.is_dir():
        return out
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root)
        if path.is_file() and wanted(rel):
            out[rel.as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()[:16]
    return out


def source_commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True,
                              text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def drift() -> dict:
    report = {}
    for skill in SKILLS:
        src, dst = files_of(SOURCE / skill), files_of(TARGET / skill)
        changed = sorted(k for k in src.keys() & dst.keys() if src[k] != dst[k])
        missing = sorted(src.keys() - dst.keys())
        extra = sorted(dst.keys() - src.keys())
        if changed or missing or extra:
            report[skill] = {"changed": changed, "missing": missing, "extra": extra}
    return report


def copy() -> None:
    TARGET.mkdir(parents=True, exist_ok=True)
    manifest = {"source": ".claude/skills", "commit": source_commit(), "skills": {}}
    for skill in SKILLS:
        dst = TARGET / skill
        if dst.exists():
            shutil.rmtree(dst)
        for rel in files_of(SOURCE / skill):
            (dst / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(SOURCE / skill / rel, dst / rel)
        manifest["skills"][skill] = files_of(dst)
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="report drift only")
    args = parser.parse_args(argv)
    if not args.check:
        copy()
    report = drift()
    if not report:
        print("vendored copies match the originals: %s" % ", ".join(SKILLS))
        return 0
    for skill, kinds in report.items():
        for kind, names in kinds.items():
            for name in names:
                print("%s  %-8s %s" % (skill, kind, name))
    return 1


if __name__ == "__main__":
    sys.exit(main())
