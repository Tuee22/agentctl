# Copyright (c) 2026 agentctl contributors.
"""Native guest-capacity adapter; a non-Linux host explicitly refuses it."""

import platform
from pathlib import Path

import pytest

from agentctl.check.wsl_guest_sample import observe
from agentctl.result import Err, Ok

pytestmark = pytest.mark.evidence("real")


def test_guest_sample_reads_native_filesystem(tmp_path: Path) -> None:
    """Linux reads actual proc and statvfs facts without invoking a package tool."""
    observed = observe(tmp_path)
    if platform.system() != "Linux":
        assert isinstance(observed, Err)
        assert "requires Linux" in observed.error
    else:
        assert isinstance(observed, Ok), observed
        assert observed.value.affinity
        assert observed.value.available_memory > 0
        assert observed.value.volume_size >= observed.value.volume_free
        assert observed.value.free_inodes > 0
