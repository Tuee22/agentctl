# Copyright (c) 2026 agentctl contributors.
"""Relocation manifests, live corpora and rationale reads fail closed."""

import hashlib
import shutil
from pathlib import Path

import pytest

from agentctl.check.ratchet import check, rows
from agentctl.result import Err, Ok
from tests.harness.git import repository

pytestmark = pytest.mark.evidence("value")

SOURCE = "tests/mutants/mixed.toml"
DESTINATION = "tests/mutants/later.toml"
FIRST = '[[mutant]]\nid = "M-example-first"\nsearch = "a"\n'
SECOND = '[[mutant]]\nid = "M-example-second"\nsearch = "b"\n'


def _moved(tmp_path: Path) -> tuple[Path, str]:
    """Commit two rows in one file, then move the first to another file."""
    root = tmp_path / "subject"
    revision = repository(root, ((SOURCE, (FIRST + SECOND).encode()),), with_head=True)
    (root / SOURCE).write_text(SECOND, encoding="utf-8")
    (root / DESTINATION).write_text(FIRST, encoding="utf-8")
    original = rows(FIRST, "mutant")
    assert isinstance(original, Ok)
    proposal = "".join(
        f'[[relocation]]\nid = "{row.identifier}"\n'
        f'source = "{SOURCE}"\ndestination = "{DESTINATION}"\n'
        f'sha256 = "{hashlib.sha256(row.contents.encode()).hexdigest()}"\n'
        'provenance = "decision:D-93"\n'
        for row in original.value
    )
    (root / "tests/mutant_relocations.toml").write_text(proposal, encoding="utf-8")
    rationale = root / "DEVELOPMENT_PLAN/rationale.md"
    rationale.parent.mkdir()
    rationale.write_text(
        "| D-93 | Move `M-example-first` unchanged. |\n", encoding="utf-8"
    )
    assert check(root) == Ok(revision)
    return root, proposal


def _refused(root: Path, fragment: str) -> None:
    """Require the ratchet to fail with a diagnostic naming the cause."""
    result = check(root)
    assert isinstance(result, Err), "ratchet accepted " + fragment
    assert fragment in result.error.message, result.error.message


def test_relocation_manifest_shapes_are_refused(tmp_path: Path) -> None:
    """Directories, invalid TOML, empty lists and extra fields are refused."""
    root, proposal = _moved(tmp_path)
    manifest = root / "tests/mutant_relocations.toml"
    manifest.unlink()
    manifest.mkdir()
    _refused(root, "relocation manifest is not a regular file")
    manifest.rmdir()
    manifest.write_text("relocation = [", encoding="utf-8")
    assert isinstance(check(root), Err), "invalid relocation TOML accepted"
    manifest.write_text("relocation = []\n", encoding="utf-8")
    _refused(root, "invalid relocation manifest")
    manifest.write_text(proposal + 'extra = "x"\n', encoding="utf-8")
    _refused(root, "invalid relocation record")


def test_live_corpus_and_rationale_reads_fail_closed(tmp_path: Path) -> None:
    """Unreadable live corpora and rationale files never authorize a move."""
    root, _proposal = _moved(tmp_path)
    linked = root / "tests/mutants/linked.toml"
    linked.symlink_to(root / DESTINATION)
    _refused(root, "mutant corpus entry is not a regular file")
    linked.unlink()
    broken = root / "tests/mutants/broken.toml"
    broken.write_text("[[mutant]]\nid = 1\n", encoding="utf-8")
    assert isinstance(check(root), Err)
    broken.unlink()
    rationale = root / "DEVELOPMENT_PLAN/rationale.md"
    text = rationale.read_text(encoding="utf-8")
    rationale.unlink()
    rationale.mkdir()
    _refused(root, "relocation rationale is not a regular file")
    rationale.rmdir()
    _refused(root, "rationale.md")
    rationale.write_text(text, encoding="utf-8")
    assert isinstance(check(root), Ok)
    shutil.rmtree(root / "tests/mutants")
    assert isinstance(check(root), Err)
