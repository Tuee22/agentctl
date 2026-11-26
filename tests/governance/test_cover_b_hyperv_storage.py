# Copyright (c) 2026 agentctl contributors.
"""Disk-path, empty-file and identity-race refusals of Hyper-V storage checks."""

from pathlib import Path

import pytest

from agentctl.check import hyperv_storage
from agentctl.check.wsl_vhd import VhdSize
from agentctl.foundation import Err, Result

pytestmark = pytest.mark.evidence("real")


def _root(tmp_path: Path) -> Path:
    """Create an owned storage root."""
    root = tmp_path / "owned"
    root.mkdir()
    return root


def test_relative_and_linked_disks_are_refused(tmp_path: Path) -> None:
    """A relative, parent-reaching or symlinked disk path is invalid."""
    root = _root(tmp_path)
    disk = root / "vm.vhdx"
    disk.write_bytes(b"disk")
    link = root / "link.vhdx"
    link.symlink_to(disk)
    expected = Err("invalid Hyper-V disk path")
    assert hyperv_storage.inspect((Path("vm.vhdx"),), root=root) == expected
    assert hyperv_storage.inspect((link,), root=root) == expected
    assert hyperv_storage.inspect((root / ".." / "owned" / "vm.vhdx",), root=root) == (
        expected
    )


def test_empty_disk_has_unavailable_identity(tmp_path: Path) -> None:
    """A zero-length disk file cannot carry a usable identity."""
    root = _root(tmp_path)
    disk = root / "empty.vhd"
    disk.write_bytes(b"")
    assert hyperv_storage.inspect((disk,), root=root) == Err(
        "Hyper-V disk identity changed or is unavailable"
    )


def test_size_refuses_a_disk_that_vanishes_during_the_query(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failed recheck is joined to the failed query."""
    root = _root(tmp_path)
    disk = root / "vm.vhdx"
    disk.write_bytes(b"disk")

    def query(_path: Path) -> Result[VhdSize, str]:
        """Remove the disk while the native query is pending."""
        disk.unlink()
        return Err("query stopped")

    monkeypatch.setattr(hyperv_storage, "query_information", query)
    result = hyperv_storage.virtual_size(disk, root=root)
    assert isinstance(result, Err)
    assert result.error.startswith("query stopped; Hyper-V disk recheck failed: ")


def test_size_refuses_a_replaced_disk(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A new file at the same path changes the identity bracket."""
    root = _root(tmp_path)
    disk = root / "vm.vhdx"
    disk.write_bytes(b"disk")
    other = root / "other.vhdx"

    def query(_path: Path) -> Result[VhdSize, str]:
        """Replace the disk with a different inode while the query is pending."""
        other.write_bytes(b"disk")
        other.replace(disk)
        return Err("query stopped")

    monkeypatch.setattr(hyperv_storage, "query_information", query)
    assert hyperv_storage.virtual_size(disk, root=root) == Err(
        "query stopped; Hyper-V disk identity changed"
    )
