# Copyright (c) 2026 agentctl contributors.
"""Strict nonce-bound diagnostic guest identity transport."""

from dataclasses import replace

import pytest

from agentctl.check.hyperv_guest import GuestIdentity
from agentctl.check.hyperv_guest_protocol import decode, encode
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


def test_guest_response_rejects_stale_ambiguous_and_invalid_values() -> None:
    """A matching nonce is necessary but never authenticates the peer by itself."""
    encoded = encode(NONCE, GUEST)
    assert isinstance(encoded, Ok)
    assert decode(encoded.value, NONCE) == Ok(GUEST)
    assert isinstance(decode(encoded.value, "2" * 32), Err)
    assert isinstance(
        decode(encoded.value.replace('"uid":1000', '"uid":true'), NONCE), Err
    )
    assert isinstance(
        decode(encoded.value.replace('"uid":1000', '"uid":1000,"uid":1000'), NONCE), Err
    )
    assert isinstance(encode(NONCE, replace(GUEST, uid=0)), Err)
    assert isinstance(encode("bad", GUEST), Err)
