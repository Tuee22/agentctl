# Copyright (c) 2026 agentctl contributors.
"""Ensure step refusal when recorded tools meet an unsupported host."""

from dataclasses import replace
from pathlib import Path

import pytest

from agentctl.bootstrap.toolchain import Toolchain, record
from agentctl.check import toolchain
from agentctl.result import Ok
from tests.harness.bootstrap import context, pins

pytestmark = pytest.mark.evidence("value")


def test_ensure_reports_host_fact_failure(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A recorded toolchain cannot override an unsupported platform architecture."""
    host = replace(context(tmp_path), machine="s390x")
    assert isinstance(record(Toolchain("/ghc", "/cabal"), host.cache), Ok)
    assert toolchain.run_step(toolchain.EnsureStep(host, Ok(pins()))) == 1
    assert "P10" in capsys.readouterr().err
