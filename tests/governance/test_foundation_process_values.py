# Copyright (c) 2026 agentctl contributors.
"""Governance-owned process outcomes are independently usable."""

import pytest

from agentctl.foundation_process_values import ByteOutput, Output, SpawnError

pytestmark = pytest.mark.evidence("value")


def test_process_outcomes_preserve_values() -> None:
    """The shared result shapes preserve bytes, text, status and failure details."""
    text = Output(3, "output", "error")
    raw = ByteOutput(4, b"\xff", b"error")
    failure = SpawnError("unavailable")
    assert (text.code, text.stdout, text.stderr) == (3, "output", "error")
    assert (raw.code, raw.stdout, raw.stderr) == (4, b"\xff", b"error")
    assert failure.message == "unavailable"
