# Copyright (c) 2026 agentctl contributors.
"""Native context capture and an actual bounded version-probe failure."""

import platform
import sys
from pathlib import Path

import pytest

from agentctl.hostfacts import current, numeric_version

pytestmark = pytest.mark.evidence("real")


def test_native_context_and_numeric_failure(tmp_path: Path) -> None:
    """Capture this host without uname and reject real failed version invocations."""
    context = current(tmp_path / "cache", assume_yes=True)
    assert context.family == platform.system()
    assert context.machine == platform.machine()
    assert context.cache == tmp_path / "cache"
    assert context.home == Path.home()
    assert context.cwd == Path.cwd()
    assert context.assume_yes
    assert context.interactive == (sys.stdin.isatty() and sys.stderr.isatty())
    assert numeric_version(sys.executable, context) is None
    assert numeric_version(str(tmp_path / "absent-executable"), context) is None
