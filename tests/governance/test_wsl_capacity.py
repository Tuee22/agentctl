# Copyright (c) 2026 agentctl contributors.
"""Host/VHD joins are consistency checks, never workload receipts."""

from dataclasses import replace
from pathlib import Path

import pytest

from agentctl.check.wsl_budget import HostCapacity
from agentctl.check.wsl_capacity import join, observe
from agentctl.check.wsl_registration import StorageObservation
from agentctl.check.wsl_vhd import VhdSize
from agentctl.foundation import Err, Ok


@pytest.mark.evidence("value")
def test_host_vhd_join_requires_stable_identity_and_conservative_space() -> None:
    """File replacement and optimistic free space cannot enter the joined sample."""
    before = StorageObservation(
        Path("/owned/base"), Path("/owned/base/ext4.vhdx"), 8, 9, 100, 1000
    )
    after = replace(before, file_bytes=120, free_bytes=800)
    size = VhdSize(4096, 120, 1024, 512)
    host = HostCapacity(8, 5000, 4000, 900, 950, shared_volume=True)
    result = join(before, size, host, after)
    assert isinstance(result, Ok)
    assert result.value.host.vhd_free == after.free_bytes
    assert result.value.host.source_free == after.free_bytes, (
        "shared volume reserve was overstated"
    )
    assert isinstance(join(before, size, host, replace(after, inode=10)), Err), (
        "changed VHD identity was accepted"
    )
    assert isinstance(join(before, replace(size, virtual=0), host, after), Err), (
        "invalid VHD size was joined"
    )
    assert isinstance(join(before, size, replace(host, commit_headroom=0), after), Err)
    separate = join(before, size, replace(host, shared_volume=False), after)
    assert isinstance(separate, Ok)
    assert separate.value.host.source_free == host.source_free


@pytest.mark.evidence("real")
def test_host_vhd_observation_refuses_outside_storage(tmp_path: Path) -> None:
    """A real outside VHD path is refused before any host capacity is joined."""
    owned, outside = tmp_path / "owned", tmp_path / "outside"
    owned.mkdir()
    outside.mkdir()
    (outside / "ext4.vhdx").write_bytes(b"not a VHD")
    result = observe(tmp_path, outside, owned)
    assert isinstance(result, Err), "outside VHD was accepted"
    assert "escapes owned boundary" in result.error
