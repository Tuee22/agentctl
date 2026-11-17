# Copyright (c) 2026 agentctl contributors.
"""Constructed peer messages never constitute authenticated WSL evidence."""

import json
from dataclasses import replace

import pytest

from agentctl.check import binding_inventory, binding_transport
from agentctl.check.binding_peer import PeerObservation, PeerRequest
from agentctl.check.evidence import Entry
from agentctl.check.wsl_guest_sample import GuestReading
from agentctl.result import Err, Ok

pytestmark = pytest.mark.evidence("value")


def test_peer_message_identity_and_evidence() -> None:
    """Only exact request, host, mount and nonce-bound inventory values join."""
    request = PeerRequest(
        "dedicated", "/mnt/c/Users/name/agentctl", "/work/agentctl", "a" * 32
    )
    inventory = binding_inventory.encode(
        (Entry("entry", "file", (b"bytes",)),), request.nonce
    )
    assert isinstance(inventory, Ok)
    mountinfo = (
        "10 1 8:1 / / rw - ext4 /dev/root rw\n"
        "20 10 0:40 / /mnt/c rw - 9p C:\\134 rw\n"
        "21 10 0:40 /Users/name/agentctl /work/agentctl rw - 9p C:\\134 rw\n"
    )
    observation = PeerObservation(
        request,
        "6.1-microsoft-standard-WSL2",
        "dedicated",
        "ID=debian\n",
        1000,
        40,
        1234,
        mountinfo,
        inventory.value,
        GuestReading((0, 1), 4096, 1024, 8192, 4096, 100),
    )
    text = binding_transport.encode(observation)
    assert binding_transport.decode(text, request) == Ok(observation), (
        "guest capacity not carried in peer"
    )
    assert isinstance(
        binding_transport.decode(text, replace(request, nonce="b" * 32)), Err
    ), "stale peer message was accepted"
    altered_nonce = json.loads(text)
    altered_nonce["nonce"] = "b" * 32
    assert isinstance(
        binding_transport.decode(json.dumps(altered_nonce), request), Err
    ), "stale peer message was accepted"
    changed = replace(
        observation, mountinfo=mountinfo.replace("0:40 /Users", "0:41 /Users")
    )
    assert isinstance(
        binding_transport.decode(binding_transport.encode(changed), request), Err
    ), "wrong peer mount was accepted"
    changed = replace(observation, release="ID=ubuntu\n")
    assert isinstance(
        binding_transport.decode(binding_transport.encode(changed), request), Err
    ), "wrong peer host was accepted"
    changed = replace(
        observation, inventory=inventory.value.replace(request.nonce, "b" * 32)
    )
    assert isinstance(
        binding_transport.decode(binding_transport.encode(changed), request), Err
    ), "stale peer inventory was accepted"
    changed = replace(observation, uid=0)
    assert isinstance(
        binding_transport.decode(binding_transport.encode(changed), request), Err
    )
    fields = json.loads(text)
    fields["uid"] = True
    assert isinstance(binding_transport.decode(json.dumps(fields), request), Err)
    for guest in (
        replace(observation.guest, available_memory=0),
        replace(observation.guest, affinity=()),
        replace(observation.guest, volume_free=observation.guest.volume_size + 1),
    ):
        changed = binding_transport.encode(replace(observation, guest=guest))
        assert isinstance(binding_transport.decode(changed, request), Err), (
            "invalid guest capacity was accepted"
        )
    fields = json.loads(text)
    fields["guest"]["available_memory"] = True
    assert isinstance(binding_transport.decode(json.dumps(fields), request), Err)
    fields = json.loads(text)
    fields["guest"]["extra"] = 1
    assert isinstance(binding_transport.decode(json.dumps(fields), request), Err)
    fields = json.loads(text)
    del fields["guest"]
    assert isinstance(binding_transport.decode(json.dumps(fields), request), Err), (
        "missing guest capacity was accepted"
    )


def test_peer_message_rejects_malformed_fields() -> None:
    """Duplicate keys, unknown fields and boolean identities are not observations."""
    request = PeerRequest("dedicated", "/mnt/c/source", "/work/source", "a" * 32)
    assert isinstance(
        binding_transport.decode('{"nonce":"x","nonce":"y"}', request), Err
    )
    assert isinstance(binding_transport.decode(json.dumps({"extra": 1}), request), Err)
    assert isinstance(binding_transport.decode("not json", request), Err)
