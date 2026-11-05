# Copyright (c) 2026 agentctl contributors.
"""Every document rule sees its negative tree and a passing live twin."""

from pathlib import Path

import pytest

from agentctl.check.validator.docs import check, validate
from tests.harness.trees import negative_tree

pytestmark = pytest.mark.evidence("value")


def _controls(root: Path, temporary: Path, rule: str) -> None:
    """Require exactly the named diagnostic in the rule's negative tree."""
    assert check(root, rule) == ()
    tree = negative_tree(root, temporary, "docs_" + rule.replace("-", "_"))
    result = check(tree, rule)
    assert len(result) == 1, f"docs.{rule} negative was accepted"
    assert result[0].startswith("docs." + rule + ":")


def test_docs_metadata(root: Path, tmp_path: Path) -> None:
    """Reject the closed metadata grammar's invalid status."""
    _controls(root, tmp_path, "metadata")


def test_docs_structure(root: Path, tmp_path: Path) -> None:
    """Require architecture's summary section and the final Related section."""
    _controls(root, tmp_path, "structure")


def test_docs_taxonomy(root: Path, tmp_path: Path) -> None:
    """Reject unregistered documentation roots and categories."""
    _controls(root, tmp_path, "taxonomy")
    tree = negative_tree(root, tmp_path / "alternate-root", "plan_fileset")
    (tree / "docs").mkdir()
    assert "docs.taxonomy: docs/" in check(tree, "taxonomy")


def test_docs_links(root: Path, tmp_path: Path) -> None:
    """Resolve anchors while ignoring nested fenced link examples."""
    _controls(root, tmp_path, "links")
    tree = negative_tree(root, tmp_path / "fenced", "docs_links")
    page = tree / "documents/operations/installation.md"
    text = page.read_text(encoding="utf-8")
    page.write_text(
        text.replace(
            "[negative](#missing-anchor)",
            "````text\n```text\n[negative](#missing-anchor)\n```\n````",
        ),
        encoding="utf-8",
    )
    assert check(tree, "links") == ()
    for target in ("https://example.com", "mailto:user@example.com", "missing.md"):
        page.write_text(text.replace("#missing-anchor", target), encoding="utf-8")
        assert check(tree, "links")


def test_docs_owning_phase(root: Path, tmp_path: Path) -> None:
    """Join a page's owning-phase title to its actual target."""
    _controls(root, tmp_path, "owning-phase")
    tree = negative_tree(root, tmp_path / "missing", "plan_fileset")
    page = tree / "documents/operations/installation.md"
    original = (root / page.relative_to(tree)).read_text(encoding="utf-8")
    for text in (
        "\n".join(
            line
            for line in original.splitlines()
            if not line.startswith("**Owning phase**:")
        ),
        original.replace("phase-6-launch-and-passthrough.md", "missing.md"),
    ):
        page.write_text(text, encoding="utf-8")
        assert check(tree, "owning-phase") == (
            "docs.owning-phase: documents/operations/installation.md",
        )


def test_docs_no_status(root: Path, tmp_path: Path) -> None:
    """Keep phase completion claims in the plan's status table."""
    _controls(root, tmp_path, "no-status")


def test_docs_phase_citation(root: Path, tmp_path: Path) -> None:
    """Reject phase ordinals outside fenced examples."""
    _controls(root, tmp_path, "phase-citation")


def test_docs_binary_unnamed(root: Path, tmp_path: Path) -> None:
    """Read fenced content too when checking user-facing binary vocabulary."""
    _controls(root, tmp_path, "binary-unnamed")


def test_docs_enforcement_cited(root: Path, tmp_path: Path) -> None:
    """Require a test citation adjacent to an enforcement claim."""
    _controls(root, tmp_path, "enforcement-cited")


def test_docs_root_entry(root: Path, tmp_path: Path) -> None:
    """Reject policy duplication, missing root files and absent index links."""
    _controls(root, tmp_path, "root-entry")
    for name in ("README.md", "AGENTS.md", "CLAUDE.md"):
        tree = negative_tree(root, tmp_path / name, "docs_root_entry")
        (tree / name).unlink()
        assert check(tree, "root-entry")
    for number, index in enumerate(
        ("DEVELOPMENT_PLAN/README.md", "documents/README.md")
    ):
        tree = negative_tree(root, tmp_path / str(number), "docs_root_entry")
        (tree / "CLAUDE.md").write_text(
            (root / "CLAUDE.md").read_text(encoding="utf-8"), encoding="utf-8"
        )
        page = tree / "README.md"
        page.write_text(
            page.read_text(encoding="utf-8").replace(index, "AGENTS.md"),
            encoding="utf-8",
        )
        assert check(tree, "root-entry"), "missing root index link was accepted"
    tree = negative_tree(root, tmp_path / "status", "docs_root_entry")
    (tree / "CLAUDE.md").write_bytes((root / "CLAUDE.md").read_bytes())
    page = tree / "README.md"
    page.write_text(
        page.read_text(encoding="utf-8").replace(
            "Reference only", "Authoritative source"
        ),
        encoding="utf-8",
    )
    assert check(tree, "root-entry")


def test_live_docs_clean(root: Path) -> None:
    """Run the full documentation registry over the actual governed tree."""
    assert validate(root) == ()
