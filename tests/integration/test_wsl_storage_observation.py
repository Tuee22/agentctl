# Copyright (c) 2026 agentctl contributors.
"""Native storage observations do not claim a configured VHD capacity."""

from pathlib import Path

import pytest

from agentctl.check.wsl_registration import inspect_storage
from agentctl.result import Err, Ok

pytestmark = pytest.mark.evidence("real")


def test_storage_observation_requires_contained_vhd(tmp_path: Path) -> None:
    """Observe an actual owned file and refuse an equally real foreign file."""
    owned = tmp_path / "owned"
    base = owned / "debian"
    base.mkdir(parents=True)
    vhd = base / "ext4.vhdx"
    vhd.write_bytes(b"owned-vhd")
    observed = inspect_storage(base, owned)
    assert isinstance(observed, Ok), observed
    assert observed.value.vhd == vhd.resolve()
    assert observed.value.file_bytes == len(b"owned-vhd")
    assert observed.value.inode == vhd.stat().st_ino
    assert observed.value.free_bytes > 0
    foreign = tmp_path / "foreign"
    foreign.mkdir()
    (foreign / "ext4.vhdx").write_bytes(b"foreign-vhd")
    assert isinstance(inspect_storage(foreign, owned), Err), "foreign VHD was accepted"
    assert isinstance(inspect_storage(owned, owned), Err)
    assert (foreign / "ext4.vhdx").read_bytes() == b"foreign-vhd"
