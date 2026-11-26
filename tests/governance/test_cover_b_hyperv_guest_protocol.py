# Copyright (c) 2026 agentctl contributors.
"""Remaining family, size and entry-point paths of the Hyper-V guest protocol."""

import io
import json

import pytest

from agentctl.check import hyperv_guest, hyperv_guest_protocol
from agentctl.check.hyperv_guest import GuestIdentity
from agentctl.foundation import Err, Ok

pytestmark = pytest.mark.evidence("value")
NONCE = "1" * 32
GUEST = GuestIdentity(
    "Linux",
    "6.12",
    "Microsoft Corporation",
    "Virtual Machine",
    "ID=debian\n",
    "123456789abcdef0123456789abcdef0",
    1000,
)


def test_unknown_family_is_refused() -> None:
    """A family outside the closed set never validates an identity."""
    unknown = json.loads('"other"')
    assert hyperv_guest_protocol.encode(NONCE, GUEST, guest_family=unknown) == Err(
        "invalid guest identity or nonce"
    )


def test_oversized_response_and_bad_nonce_are_refused() -> None:
    """Bounded input and a canonical nonce precede any decoding."""
    assert hyperv_guest_protocol.decode(
        " " * (hyperv_guest_protocol.MAX_RESPONSE + 1), NONCE
    ) == Err("invalid guest identity response or nonce")


def test_main_emits_one_observation(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A valid nonce and an observed identity produce one decodable line."""
    monkeypatch.setattr(hyperv_guest, "observe", lambda: Ok(GUEST))
    monkeypatch.setattr("sys.stdin", io.StringIO(NONCE + "\n"))
    assert hyperv_guest_protocol.main() == 0
    out = capsys.readouterr().out
    assert hyperv_guest_protocol.decode(out.strip(), NONCE) == Ok(GUEST)
