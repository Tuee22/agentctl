# Copyright (c) 2026 agentctl contributors.
"""Record-shape and guest-key refusals when comparing SSH host keys."""

import base64

import pytest

from agentctl.check import virtualbox_ssh_key
from agentctl.foundation import Err, Ok

pytestmark = pytest.mark.evidence("value")
PORT = 44223
ENCODED = base64.b64encode(virtualbox_ssh_key.PREFIX + bytes(range(32))).decode()


def test_guest_record_needs_algorithm_and_key() -> None:
    """A single token is not a key record."""
    assert virtualbox_ssh_key.guest_key("ssh-ed25519\n") == Err(
        "invalid guest SSH host key record"
    )
    assert isinstance(
        virtualbox_ssh_key.guest_key(f"ssh-ed25519 {ENCODED} comment\n"), Ok
    )


def test_compare_returns_a_guest_key_refusal() -> None:
    """An invalid guest record stops the comparison before the known host."""
    known = f"[127.0.0.1]:{PORT} ssh-ed25519 {ENCODED}\n"
    assert virtualbox_ssh_key.compare("bad", known, PORT) == Err(
        "invalid SSH host key record"
    )
    assert isinstance(
        virtualbox_ssh_key.compare(f"ssh-ed25519 {ENCODED}\n", known, PORT), Ok
    )


def _nothing(*_arguments: object) -> None:
    """Return no result at all, as no member of the closed result union does."""


def test_unclassified_results_produce_no_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Decoding and comparison return nothing for a value outside the result union."""
    with monkeypatch.context() as patch:
        patch.setattr(virtualbox_ssh_key, "_line", _nothing)
        assert virtualbox_ssh_key.guest_key("x\n") is None
        assert virtualbox_ssh_key.known_key("x\n", PORT) is None
    with monkeypatch.context() as patch:
        patch.setattr(virtualbox_ssh_key, "guest_key", _nothing)
        patch.setattr(virtualbox_ssh_key, "known_key", _nothing)
        assert virtualbox_ssh_key.compare("x\n", "y\n", PORT) is None
