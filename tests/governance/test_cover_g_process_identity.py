# Copyright (c) 2026 agentctl contributors.
"""Boundary values for the Linux process start-time field decoder."""

import pytest

from agentctl.check.process_identity import linux_birth_stat
from agentctl.result import Err, Ok

pytestmark = pytest.mark.evidence("value")
PID = 7
START_INDEX = 19
FIELD_PADDING = b"S " * START_INDEX
MAX_START = 2**64 - 1


def _stat(start: bytes) -> bytes:
    """Build a proc stat line whose twentieth post-name field is the given start."""
    return b"7 (name) " + FIELD_PADDING + start + b"\n"


def test_start_time_must_be_positive_and_fit_unsigned_64_bits() -> None:
    """Zero and an in-width value beyond the unsigned 64-bit range are refused."""
    assert linux_birth_stat(_stat(b"5"), PID) == Ok(5)
    assert linux_birth_stat(_stat(b"0"), PID) == Err("invalid Linux process start time")
    beyond = str(MAX_START + 1).encode("ascii")
    assert linux_birth_stat(_stat(beyond), PID) == Err(
        "invalid Linux process start time"
    )
    assert linux_birth_stat(_stat(str(MAX_START).encode("ascii")), PID) == Ok(MAX_START)
