# Copyright (c) 2026 agentctl contributors.
"""Real read-only VHD refusal and owned-storage boundary controls."""

import platform
from pathlib import Path

import pytest

from agentctl.check.wsl_vhd import VhdSize, checked_size, observe
from agentctl.foundation import Err, Ok


@pytest.mark.evidence("value")
def test_vhd_size_requires_complete_values() -> None:
    """A size cannot be manufactured from empty native capacity fields."""
    assert checked_size(4096, 1024, 1024, 512) == Ok(VhdSize(4096, 1024, 1024, 512))
    assert isinstance(checked_size(0, 1024, 1024, 512), Err), (
        "zero VHD virtual size was accepted"
    )
    for values in ((4096, -1, 1024, 512), (4096, 1024, 0, 512), (4096, 1024, 1024, 0)):
        assert isinstance(checked_size(*values), Err)


@pytest.mark.evidence("real")
def test_vhd_observer_refuses_invalid_and_unowned_paths(tmp_path: Path) -> None:
    """An ordinary file and an outside directory never become VHD evidence."""
    owned = tmp_path / "owned"
    base = owned / "instance"
    outside = tmp_path / "outside"
    base.mkdir(parents=True)
    outside.mkdir()
    (base / "ext4.vhdx").write_bytes(b"not a virtual disk")
    (outside / "ext4.vhdx").write_bytes(b"not a virtual disk")
    invalid = observe(base, owned)
    escaped = observe(outside, owned)
    assert isinstance(invalid, Err), "invalid VHD produced a size observation"
    assert isinstance(escaped, Err), "outside VHD produced a size observation"
    if platform.system() == "Windows":
        assert "VHD information open failed" in invalid.error, (
            "invalid VHD open failure was lost"
        )
        assert "escapes owned boundary" in escaped.error, (
            "outside VHD boundary was ignored"
        )
    else:
        assert "requires Windows" in invalid.error
        assert "requires Windows" in escaped.error
