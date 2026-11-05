# Copyright (c) 2026 agentctl contributors.
"""The test runs the native resolved tools and reads their own pinned answers."""

import os
from pathlib import Path

import pytest

from agentctl.process import run
from agentctl.result import Ok
from tests.harness.bootstrap import native_tools

pytestmark = pytest.mark.evidence("real")


def test_resolved_ghc_reports_pin(tmp_path: Path) -> None:
    """Both actual recorded executables answer independently of bootstrap's report."""
    tools = native_tools()
    for executable, expected in ((tools.ghc, "9.12.4"), (tools.cabal, "3.16.1.0")):
        result = run(
            [executable, "--numeric-version"],
            cwd=tmp_path,
            env={**os.environ, "PATH": ""},
        )
        assert isinstance(result, Ok)
        assert result.value.code == 0, result.value.stderr
        assert result.value.stdout.strip() == expected
