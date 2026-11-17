# Copyright (c) 2026 agentctl contributors.
"""Actual local host sampling, with no Linux workload or WSL invocation."""

import os
import platform
from pathlib import Path

import pytest

from agentctl.check.wsl_host_sample import observe
from agentctl.result import Err, Ok

pytestmark = pytest.mark.evidence("real")


def test_host_sample_uses_native_counters(tmp_path: Path) -> None:
    """Windows reads native counters; other hosts explicitly refuse this adapter."""
    result = observe(tmp_path, tmp_path, tmp_path)
    if platform.system() != "Windows":
        assert isinstance(result, Err)
        assert "requires Windows" in result.error
    else:
        assert isinstance(result, Ok), result
        assert result.value.cpus == os.cpu_count()
        assert result.value.available_memory > 0
        assert result.value.commit_headroom >= 0
        assert result.value.vhd_free > 0
        assert result.value.source_free > 0
        assert result.value.shared_volume
