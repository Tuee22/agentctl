# Copyright (c) 2026 agentctl contributors.
"""VirtualBox guest capacity wire values retain nonce and resource boundaries."""

from dataclasses import replace

import pytest

from agentctl.check.hyperv_guest import GuestIdentity
from agentctl.check.virtualbox_guest_capacity import (
    Observation,
    Request,
    decode,
    decode_request,
    encode,
    join,
    request_text,
)
from agentctl.check.wsl_guest_sample import GuestReading
from agentctl.foundation import Err, Ok

pytestmark = pytest.mark.evidence("value")
REQUEST = Request("a" * 32, "/home/agentctl/work")
IDENTITY = GuestIdentity(
    "Linux", "6.12", "innotek GmbH", "VirtualBox", "ID=debian\n", "1" * 32, 1000
)
READING = GuestReading((0, 1), 8000, 0, 10000, 6000, 500)


def test_capacity_protocol_refuses_stale_ambiguous_and_invalid_values() -> None:
    """Identity and resource facts must accompany the exact request without extras."""
    request = request_text(REQUEST)
    assert isinstance(request, Ok)
    assert decode_request(request.value) == Ok(REQUEST)
    expected = Observation(REQUEST, IDENTITY, READING)
    response = encode(expected)
    assert isinstance(response, Ok)
    assert decode(response.value, REQUEST) == Ok(expected)
    assert isinstance(decode(response.value, replace(REQUEST, nonce="b" * 32)), Err), (
        "stale guest capacity nonce was accepted"
    )
    assert isinstance(
        decode(response.value, replace(REQUEST, storage="/different")), Err
    )
    assert isinstance(
        decode(
            response.value.replace(
                '"available_memory":8000', '"available_memory":true'
            ),
            REQUEST,
        ),
        Err,
    )
    assert isinstance(
        decode(
            response.value.replace('"volume_free":6000', '"volume_free":10001'), REQUEST
        ),
        Err,
    ), "invalid guest capacity response accepted"
    assert isinstance(
        decode(
            response.value.replace(
                '"available_memory":8000',
                '"available_memory":8000,"available_memory":8000',
            ),
            REQUEST,
        ),
        Err,
    )
    assert isinstance(
        encode(replace(expected, reading=replace(READING, volume_free=10001))), Err
    ), "invalid guest capacity was accepted"
    for storage in (
        "relative",
        "/home/../etc",
        "//home/work",
        "/home/\nwork",
        "/home/\ud800",
        "/home/" + "a" * 4096,
    ):
        assert isinstance(request_text(replace(REQUEST, storage=storage)), Err), (
            "unsafe guest storage path accepted"
        )
    assert isinstance(decode_request('{"nonce":"x","nonce":"y","storage":"/"}'), Err)


def test_capacity_join_rejects_changed_identity() -> None:
    """Resource values are accepted only between matching valid guest identities."""
    expected = Observation(REQUEST, IDENTITY, READING)
    assert join(REQUEST, IDENTITY, READING, IDENTITY) == Ok(expected)
    assert isinstance(
        join(REQUEST, IDENTITY, READING, replace(IDENTITY, uid=1001)), Err
    ), "changed guest identity was accepted"
    assert isinstance(
        join(REQUEST, IDENTITY, replace(READING, volume_free=10001), IDENTITY), Err
    )
