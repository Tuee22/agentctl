# Copyright (c) 2026 agentctl contributors.
"""Every fixture is independently expected and has complete, honest provenance."""

import shutil
from pathlib import Path

import pytest

from agentctl.result import Err, Ok
from tests.harness.screens import Captured, read

pytestmark = pytest.mark.evidence("real")


def test_every_fixture_has_provenance(root: Path, tmp_path: Path) -> None:
    """Reject missing, malformed and misleading sidecars beside the actual matrix."""
    directory = root / "tests/fixtures/screens"
    fixtures = read(directory)
    assert isinstance(fixtures, Ok), fixtures
    assert fixtures.value
    copied = tmp_path / "screens"
    shutil.copytree(directory, copied)
    fixture = copied / "claude/IdlePrompt/documented.txt"
    sidecar = fixture.with_suffix(".toml")
    original = sidecar.read_bytes()
    sidecar.unlink()
    missing = read(copied)
    assert isinstance(missing, Err)
    assert "missing provenance sidecar" in missing.error.message
    sidecar.write_bytes(original)
    assert isinstance(read(copied), Ok)
    for replacement, reason in (
        (
            'provenance = "unknown"\nevidence = "Claude Code"\nnote = "control"\n',
            "unknown fixture provenance",
        ),
        (
            'provenance = "documented"\nevidence = "absent span"\nnote = "control"\n',
            "evidence span",
        ),
        (
            original.decode().replace('source = "https:', 'source = "http:'),
            "official HTTPS URL",
        ),
        (original.decode() + 'unexpected = "field"\n', "unknown fields"),
        (
            original.decode().replace('evidence = "Claude Code"', "evidence = 1"),
            "nonempty strings",
        ),
        ("provenance = [", "invalid fixture bytes"),
        (
            'provenance = "captured"\nevidence = "Claude Code"\nnote = "control"\n',
            "version and exact command",
        ),
    ):
        sidecar.write_text(replacement, encoding="utf-8")
        invalid = read(copied)
        assert isinstance(invalid, Err)
        assert reason in invalid.error.message
    sidecar.write_text(
        'provenance = "captured"\nevidence = "Claude Code"\n'
        'note = "parser control only"\nagent_version = "test fixture 1"\n'
        'capture_command = "private fixture capture control"\n',
        encoding="utf-8",
    )
    captured = read(copied)
    assert isinstance(captured, Ok), captured
    assert any(isinstance(item.provenance, Captured) for item in captured.value)
    sidecar.write_bytes(original)
    unknown = copied / "claude/Unknown"
    unknown.rename(copied / "claude/NotAClass")
    invalid = read(copied)
    assert isinstance(invalid, Err)
    assert "unknown screen class" in invalid.error.message
