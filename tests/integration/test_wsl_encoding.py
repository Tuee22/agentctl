# Copyright (c) 2026 agentctl contributors.
"""Actual child environment for native WSL listing output."""

import os
import sys
from pathlib import Path

import pytest

from agentctl.check.wsl_registration import version_environment
from agentctl.process import run, run_bytes
from agentctl.result import Ok

pytestmark = pytest.mark.evidence("real")


def test_wsl_listing_child_requests_utf8(tmp_path: Path) -> None:
    """A real child receives the encoding request without changing its parent."""
    inherited = {**os.environ, "WSL_UTF8": "previous"}
    environment = version_environment(inherited)
    assert inherited["WSL_UTF8"] == "previous"
    program = "import os; print(os.environ.get('WSL_UTF8', 'missing'))"
    observed = run([sys.executable, "-c", program], cwd=tmp_path, env=environment)
    assert isinstance(observed, Ok), observed
    assert observed.value.code == 0
    assert observed.value.stdout.strip() == "1", "WSL UTF-8 request was omitted"


def test_child_preserves_utf16_output_bytes(tmp_path: Path) -> None:
    """A real child can return non-UTF-8 bytes without lossy decoding."""
    program = "import sys; sys.stdout.buffer.write('D\\u00e9bian'.encode('utf-16-le'))"
    observed = run_bytes([sys.executable, "-c", program], cwd=tmp_path, env=os.environ)
    assert isinstance(observed, Ok), observed
    assert observed.value.code == 0
    assert observed.value.stdout == "D\u00e9bian".encode("utf-16-le")
