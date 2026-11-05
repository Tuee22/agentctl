# Copyright (c) 2026 agentctl contributors.
"""Reproducible negative trees derived from committed fixture instructions."""

import shutil
import tomllib
from pathlib import Path


def negative_tree(root: Path, temporary: Path, name: str) -> Path:
    """Copy governed files and apply one provenance-labelled negative edit."""
    tree = temporary / "subject"
    tree.mkdir(parents=True)
    for directory in ("documents", "DEVELOPMENT_PLAN"):
        shutil.copytree(root / directory, tree / directory)
    for filename in ("README.md", "AGENTS.md", "CLAUDE.md"):
        if (root / filename).is_file():
            shutil.copyfile(root / filename, tree / filename)
    case = tomllib.loads(
        (root / "tests/fixtures/docs_negative" / name / "case.toml").read_text(
            encoding="utf-8"
        )
    )
    filename: object = case["path"]
    search: object = case["search"]
    replacement: object = case["replace"]
    assert isinstance(filename, str)
    assert isinstance(search, str)
    assert isinstance(replacement, str)
    path = tree / filename
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    assert not search or text.count(search) == 1
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        text.replace(search, replacement, 1) if search else text + replacement,
        encoding="utf-8",
    )
    return tree
