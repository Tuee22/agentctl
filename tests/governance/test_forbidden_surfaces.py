# Copyright (c) 2026 agentctl contributors.
"""The workflow guard rejects runners while admitting ordinary fixture data."""

import tomllib
from pathlib import Path

import pytest

from agentctl.check.validator.source import forbidden_surfaces

pytestmark = pytest.mark.evidence("value")


def test_fixture_and_live_tree(root: Path, tmp_path: Path) -> None:
    """Check actual entry surfaces and a minimal positive/negative tree pair."""
    assert forbidden_surfaces(root) == ()
    (tmp_path / "data.txt").write_text("fixture", encoding="utf-8")
    assert forbidden_surfaces(tmp_path) == ()
    fixture = tmp_path / "tests/fixtures/data/Makefile"
    fixture.parent.mkdir(parents=True)
    fixture.write_text("negative fixture data", encoding="utf-8")
    assert forbidden_surfaces(tmp_path) == ()
    oracle = tomllib.loads(
        (root / "tests/oracles/forbidden_surfaces.toml").read_text(encoding="utf-8")
    )
    names: object = oracle["case"][0]["expected"]
    assert isinstance(names, list)
    for name in names:
        assert isinstance(name, str)
        path = tmp_path / name
        path.write_text("parallel runner", encoding="utf-8")
        assert forbidden_surfaces(tmp_path) == ("tree.forbidden-surfaces: " + name,), (
            "parallel runner was accepted"
        )
        path.unlink()
    for name in ("check.sh", "tasks.py"):
        path = tmp_path / name
        path.write_text("parallel entry", encoding="utf-8")
        assert forbidden_surfaces(tmp_path), "parallel runner was accepted"
        path.unlink()
    metadata = tmp_path / "pyproject.toml"
    metadata.write_text(
        '[project.scripts]\nagentctl = "agentctl.cli:main"\n', encoding="utf-8"
    )
    assert forbidden_surfaces(tmp_path) == ()
    metadata.write_text(
        metadata.read_text(encoding="utf-8") + 'check-other = "other:main"\n',
        encoding="utf-8",
    )
    assert forbidden_surfaces(tmp_path), "parallel runner was accepted"
    metadata.unlink()
    for invalid in ("invalid = [", "project = 1", "[project]\nscripts = 1"):
        metadata.write_text(invalid, encoding="utf-8")
        assert forbidden_surfaces(tmp_path)
    metadata.unlink()
    workflow = tmp_path / ".github/workflows"
    workflow.mkdir(parents=True)
    assert forbidden_surfaces(tmp_path) == (
        "tree.forbidden-surfaces: .github/workflows",
    )
