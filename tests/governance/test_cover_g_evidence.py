# Copyright (c) 2026 agentctl contributors.
"""Refusal paths of the run-evidence readers and the byte census."""

import json
import os
import stat
from pathlib import Path

import pytest

from agentctl.check import evidence
from agentctl.foundation import Err, Ok

pytestmark = pytest.mark.evidence("value")
NONCE = "nonce-1"


def _write(path: Path, value: object) -> Path:
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def test_tool_substeps_refuse_a_symlink(tmp_path: Path) -> None:
    """A symlinked substep record is never read."""
    real = _write(tmp_path / "real.json", {"nonce": NONCE, "outcomes": []})
    link = tmp_path / "link.json"
    link.symlink_to(real)
    assert evidence.read_tool_substeps(link, NONCE, ()) == Err(
        evidence.EvidenceError("tool substeps are a symlink")
    )


def test_oracle_details_refuse_a_symlink(tmp_path: Path) -> None:
    """A symlinked oracle record is never read."""
    real = _write(tmp_path / "real.json", {"nonce": NONCE, "sources": [], "issues": []})
    link = tmp_path / "link.json"
    link.symlink_to(real)
    assert evidence.read_oracle_details(link, NONCE) == Err(
        evidence.EvidenceError("oracle details are a symlink")
    )


def test_oracle_details_refuse_malformed_fields(tmp_path: Path) -> None:
    """Source lists, duplicates and issue rows are closed schemas."""
    cases = (
        ({"sources": [""], "issues": []}, "invalid oracle source list"),
        ({"sources": ["a", "a"], "issues": []}, "duplicate oracle source"),
        ({"sources": ["a"], "issues": [["b", "m"]]}, "invalid oracle issue"),
    )
    for body, message in cases:
        path = _write(tmp_path / "o.json", {"nonce": NONCE, **body})
        assert evidence.read_oracle_details(path, NONCE) == Err(
            evidence.EvidenceError(message)
        )
    good = _write(
        tmp_path / "g.json",
        {"nonce": NONCE, "sources": ["a"], "issues": [["a", "m"], [None, "n"]]},
    )
    parsed = evidence.read_oracle_details(good, NONCE)
    assert isinstance(parsed, Ok)
    assert parsed.value.issues == (("a", "m"), (None, "n"))


def test_legs_refuse_a_wrong_schedule(tmp_path: Path) -> None:
    """The recorded tool names must equal the expected unique schedule."""
    path = _write(tmp_path / "l.json", {"nonce": NONCE, "outcomes": [["a", 0]]})
    assert evidence.read_legs(path, NONCE, ("a", "b")) == Err(
        evidence.EvidenceError("incomplete or ambiguous tool schedule")
    )
    assert evidence.read_legs(path, NONCE, ("a",)) == Ok(
        evidence.LegEvidence(NONCE, (("a", 0),))
    )
    assert evidence.read_legs(path, NONCE, ()) == Err(
        evidence.EvidenceError("incomplete or ambiguous tool schedule")
    )


def test_census_refuses_a_missing_root(tmp_path: Path) -> None:
    """A file root is not a source census root."""
    assert evidence.source_census(tmp_path / "absent") == Err(
        evidence.EvidenceError("source census root is not a directory")
    )


def test_census_refuses_an_unreadable_directory(tmp_path: Path) -> None:
    """A directory that cannot be listed becomes a typed failure."""
    locked = tmp_path / "locked"
    locked.mkdir()
    locked.chmod(0)
    try:
        readable = os.access(locked, os.R_OK)
        result = evidence.source_census(tmp_path)
    finally:
        locked.chmod(stat.S_IRWXU)
    assert isinstance(result, Ok if readable else Err)
    assert isinstance(evidence.source_census(tmp_path), Ok)


def test_census_refuses_a_special_file(tmp_path: Path) -> None:
    """A FIFO is an unsupported evidence entry."""
    os.mkfifo(tmp_path / "pipe")
    assert evidence.source_census(tmp_path) == Err(
        evidence.EvidenceError("unsupported evidence entry: pipe")
    )


def test_census_refuses_an_escaping_symlink(tmp_path: Path) -> None:
    """A link leaving the source root is refused."""
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("x", encoding="utf-8")
    (root / "link").symlink_to(outside)
    assert evidence.source_census(root) == Err(
        evidence.EvidenceError("evidence symlink escapes source: link")
    )


def test_legs_refuse_unclosed_record_fields(tmp_path: Path) -> None:
    """A record that is not a nonce plus outcome list is invalid."""
    path = _write(tmp_path / "l.json", {"nonce": 1, "outcomes": []})
    assert evidence.read_legs(path, NONCE, ("a",)) == Err(
        evidence.EvidenceError("invalid tool record fields")
    )
