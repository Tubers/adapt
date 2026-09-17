"""Where a project's three record files live: <project>/.rs/.

A project is a folder with a .rs folder holding any of HISTORY.jsonl, TASKS.md and QUESTIONS.jsonl.
Keeping the three together in one hidden folder (the user, 2026-09-17) keeps a project's own files
uncluttered and gives every tool one place to look. Every module finds the files through here and
never joins the names onto a project folder itself.

Records still sitting directly in a project folder are the old layout: `rules.py migrate` moves them.
"""

from __future__ import annotations

from pathlib import Path

RECORDS_DIR = ".rs"
HISTORY = "HISTORY.jsonl"
TASKS = "TASKS.md"
QUESTIONS = "QUESTIONS.jsonl"
NAMES = (HISTORY, TASKS, QUESTIONS)


def folder(project_dir) -> Path:
    """The .rs folder of a project folder."""
    return Path(project_dir) / RECORDS_DIR


def path(project_dir, name: str) -> Path:
    """One record file of a project folder."""
    return folder(project_dir) / name


def present(project_dir) -> set:
    """The record file names a project folder holds."""
    d = folder(project_dir)
    return {n for n in NAMES if (d / n).is_file()}


def is_project(project_dir) -> bool:
    return bool(present(project_dir))


def project_of_file(file_path) -> Path | None:
    """The project folder a record file belongs to, or None when the path is not a record file."""
    p = Path(file_path)
    if p.name in NAMES and p.parent.name == RECORDS_DIR:
        return p.parent.parent
    return None


def legacy(project_dir) -> list:
    """Record files still in the old place, directly in the project folder."""
    d = Path(project_dir)
    return [d / n for n in NAMES if (d / n).is_file()]
