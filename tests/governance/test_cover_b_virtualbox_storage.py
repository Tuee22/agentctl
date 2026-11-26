# Copyright (c) 2026 agentctl contributors.
"""Path and header refusals of VDI observation."""

from pathlib import Path

import pytest

from agentctl.check import virtualbox_storage
from agentctl.foundation import Err

pytestmark = pytest.mark.evidence("real")


def test_relative_paths_are_invalid_storage_paths(tmp_path: Path) -> None:
    """A relative image path is not accepted against an absolute root."""
    assert virtualbox_storage.inspect(Path("disk.vdi"), root=tmp_path) == Err(
        "invalid VDI storage path"
    )


def test_undecodable_header_is_refused(tmp_path: Path) -> None:
    """A contained image whose header is not VDI cannot be decoded."""
    image = tmp_path / "disk.vdi"
    image.write_bytes(bytes(virtualbox_storage.HEADER_BYTES))
    assert virtualbox_storage.inspect(image, root=tmp_path) == Err(
        "cannot decode VDI header"
    )
