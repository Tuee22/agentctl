# Copyright (c) 2026 agentctl contributors.
"""Malformed listings and invalid ownership inputs for guest-control sessions."""

import pytest

from agentctl.check import virtualbox_sessions
from agentctl.foundation import Err, Ok

pytestmark = pytest.mark.evidence("value")
VM = "9d7dc4eb-c2b5-4044-8bf1-8d8a6c684df8"
HOST_PID = 4242
OUT_OF_RANGE = 0


def _listing(*rows: str, total: str = "1") -> str:
    """Build a complete native listing around the given rows."""
    return (
        "Active guest sessions:\n"
        + "".join(row + "\n" for row in rows)
        + f"Total guest sessions: {total}\n"
    )


def test_session_values_listing_and_count_refusals() -> None:
    """Out-of-range identifiers, short listings and bad counts are refused."""
    zero_id = "Session #0 ID=0 User=u Status=[Started] Name=n"
    assert virtualbox_sessions.parse(_listing(zero_id)) == Err(
        "malformed VirtualBox guest session listing"
    )
    assert virtualbox_sessions.parse("Active guest sessions:\n\n") == Err(
        "invalid VirtualBox guest session listing"
    )
    row = "Session #0 ID=1 User=u Status=[Started] Name=n"
    assert virtualbox_sessions.parse(_listing(row, total="0")) == Err(
        "invalid VirtualBox guest session count"
    )
    assert isinstance(virtualbox_sessions.parse(_listing(row)), Ok)


def test_owner_lookup_refuses_invalid_inputs() -> None:
    """A bool or out-of-range PID and a malformed VM identifier are refused."""
    assert virtualbox_sessions.owned((), VM, host_pid=True) == Err(
        "invalid guest-control host PID"
    )
    assert virtualbox_sessions.owned((), "not-a-uuid", HOST_PID) == Err(
        "invalid VirtualBox VM identifier"
    )
    assert virtualbox_sessions.owned((), VM, OUT_OF_RANGE) == Err(
        "invalid guest-control host PID"
    )


def _nothing(*_arguments: object) -> None:
    """Return no result at all, as no member of the closed result union does."""


def test_unclassified_results_produce_no_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Folding and counting return nothing for a value outside the result union."""
    append = virtualbox_sessions.__dict__["_append"]
    assert append(Ok(()), None) is None
    counted = virtualbox_sessions.__dict__["_counted"]
    row = "Session #0 ID=1 User=u Status=[Started] Name=n"
    lines = ("Active guest sessions:", row, "Total guest sessions: 1")
    monkeypatch.setattr(virtualbox_sessions, "reduce", _nothing)
    assert counted(lines) is None
