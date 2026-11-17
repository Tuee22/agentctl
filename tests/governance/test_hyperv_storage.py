# Copyright (c) 2026 agentctl contributors.
"""Real filesystem containment controls for observed virtual disks."""

import os
from pathlib import Path

import pytest

from agentctl.check.hyperv_storage import inspect, virtual_size
from agentctl.foundation import Err, Ok

pytestmark = pytest.mark.evidence("real")


def test_storage_refuses_unowned_or_duplicate_disk_files(tmp_path: Path) -> None:
    """Actual files must remain beneath the owned root and have distinct identities."""
    root = tmp_path / "owned"
    root.mkdir()
    disk = root / "vm.vhdx"
    disk.write_bytes(b"disk")
    alias = root / "alias.vhdx"
    os.link(disk, alias)
    outside = tmp_path / "other.vhdx"
    outside.write_bytes(b"other")
    assert isinstance(inspect((disk,), root=root), Ok)
    assert isinstance(inspect((outside,), root=root), Err)
    assert isinstance(inspect((disk, disk), root=root), Err)
    assert isinstance(inspect((disk, alias), root=root), Err)
    assert isinstance(virtual_size(disk, root=root), Err)
    assert isinstance(virtual_size(outside, root=root), Err)
    assert isinstance(inspect((), root=root), Err)
    assert isinstance(inspect((root / "missing.vhdx",), root=root), Err)
