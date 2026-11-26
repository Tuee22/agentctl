# Copyright (c) 2026 agentctl contributors.
"""Console interrupt, input and cleanup-failure paths of owned child handling."""

import _thread
import sys
import threading
from pathlib import Path

import pytest

from agentctl import foundation_process
from agentctl.foundation_process import ObservationRequest
from agentctl.result import Err, Ok

pytestmark = pytest.mark.evidence("real")
CHILD_SECONDS = 2
INTERRUPT_DELAY = 0.4
OBSERVED_TIMEOUT = 0.5
INVALID_BYTE = 255


def test_foreground_survives_console_interrupts(tmp_path: Path) -> None:
    """An interrupt delivered while waiting does not abandon the running child."""
    timer = threading.Timer(INTERRUPT_DELAY, _thread.interrupt_main)
    timer.start()
    result = foundation_process.foreground(
        [sys.executable, "-c", f"import time; time.sleep({CHILD_SECONDS})"],
        cwd=tmp_path,
        env={},
    )
    timer.join()
    assert result == Ok(0)


def test_observed_child_requires_explicit_input(tmp_path: Path) -> None:
    """An empty release input is refused before any child is started."""
    result = foundation_process.run_observed(
        [sys.executable, "-c", "pass"],
        cwd=tmp_path,
        env={},
        request=ObservationRequest("Linux", ""),
    )
    assert result == Err(
        foundation_process.SpawnError("observed child requires explicit input")
    )


def test_observed_timeout_reports_failed_cleanup(tmp_path: Path) -> None:
    """A timed-out child whose partial output is not UTF-8 reports both failures."""
    program = "; ".join(
        (
            "import sys, time",
            f"sys.stdout.buffer.write(bytes([{INVALID_BYTE}]))",
            "sys.stdout.buffer.flush()",
            f"time.sleep({CHILD_SECONDS})",
        )
    )
    result = foundation_process.run_observed(
        [sys.executable, "-c", program],
        cwd=tmp_path,
        env={},
        request=ObservationRequest("Linux", "go", OBSERVED_TIMEOUT),
    )
    assert isinstance(result, Err)
    assert "; cleanup: " in result.error.message
