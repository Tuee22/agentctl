# Copyright (c) 2026 agentctl contributors.
"""Entry-point refusal when the VirtualBox guest cannot be observed."""

import io

import pytest

from agentctl.check import virtualbox_guest, virtualbox_guest_protocol
from agentctl.foundation import Err

pytestmark = pytest.mark.evidence("value")
NONCE = "1" * 32
FAILURE = "guest is not a VirtualBox virtual machine"


def test_main_reports_a_failed_observation(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A refused observation writes only its reason to standard error."""
    monkeypatch.setattr(virtualbox_guest, "observe", lambda: Err(FAILURE))
    monkeypatch.setattr("sys.stdin", io.StringIO(NONCE + "\n"))
    assert virtualbox_guest_protocol.main() == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == FAILURE + "\n"
