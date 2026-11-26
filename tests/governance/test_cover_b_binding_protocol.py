# Copyright (c) 2026 agentctl contributors.
"""Dispatch and entry-point behavior of the closed binding stdin protocol."""

import io
import sys

import pytest

from agentctl.check import binding_peer, binding_protocol
from agentctl.check.binding_peer import PeerRequest
from agentctl.foundation import Err, Ok, Result

pytestmark = pytest.mark.evidence("value")
NONCE = "a" * 32
UID = 1000
SUCCESS = 0
INVALID = PeerRequest("dedicated", "relative", "/work/agentctl", NONCE)
VALID = PeerRequest("dedicated", "/mnt/c/agentctl", "/work/agentctl", NONCE)


def _absent(_request: PeerRequest) -> Result[tuple[bool, int], str]:
    """Report one confirmed cleanup for the native-only absence observation."""
    return Ok((True, UID))


def test_observation_refuses_invalid_request_before_any_host_read() -> None:
    """An invalid mapping is a structured failure from the observe operation."""
    result = binding_protocol.dispatch(binding_protocol.Request("observe", INVALID))
    assert result == Err("invalid binding peer request")


def test_main_writes_the_dispatched_value(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A decoded absence request prints the nonce-bound observation and exits zero."""
    text = binding_protocol.encode(binding_protocol.Request("absence", VALID))
    with monkeypatch.context() as patch:
        patch.setattr(sys, "stdin", io.StringIO(text))
        patch.setattr(binding_peer, "observe_absence_identity", _absent)
        code = binding_protocol.main()
    assert code == SUCCESS
    assert capsys.readouterr().out == (
        '{"nonce": "' + NONCE + '", "uid": 1000, "absent": true}\n'
    )
