# Copyright (c) 2026 agentctl contributors.
"""Refusal of unusable peer mount facts and undecodable peer messages."""

from dataclasses import replace
from pathlib import Path

import pytest

from agentctl.check import binding_inventory, binding_transport
from agentctl.check.binding_peer import PeerObservation, PeerRequest
from agentctl.check.evidence import Entry
from agentctl.check.wsl_guest_sample import GuestReading
from agentctl.foundation import Err, Ok

pytestmark = pytest.mark.evidence("value")
REQUEST = PeerRequest(
    "dedicated", "/mnt/c/Users/name/agentctl", "/work/agentctl", "a" * 32
)
MOUNTINFO = (
    "10 1 8:1 / / rw - ext4 /dev/root rw\n"
    "20 10 0:40 / /mnt/c rw - 9p C:\\134 rw\n"
    "21 10 0:40 /Users/name/agentctl /work/agentctl rw - 9p C:\\134 rw\n"
)


def _observation(mountinfo: str) -> PeerObservation:
    """Build a peer observation around the supplied mount table."""
    inventory = binding_inventory.encode(
        (Entry("entry", "file", (b"bytes",)),), REQUEST.nonce
    )
    assert isinstance(inventory, Ok)
    return PeerObservation(
        REQUEST,
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


def test_unparseable_mount_table_is_refused() -> None:
    """A peer whose mountinfo cannot be parsed never joins."""
    text = binding_transport.encode(_observation("not a mount table\n"))
    refused = binding_transport.decode(text, REQUEST)
    assert isinstance(refused, Err)
    assert refused.error.startswith("binding peer mountinfo invalid: ")
    assert binding_transport.decode(
        binding_transport.encode(_observation(MOUNTINFO)), REQUEST
    ) == Ok(_observation(MOUNTINFO))


def test_join_returns_the_decoding_failure(tmp_path: Path) -> None:
    """Join reports an undecodable message before reading any local bytes."""
    refused = binding_transport.join(tmp_path, "{", REQUEST)
    assert isinstance(refused, Err)
    assert refused.error.startswith("cannot decode binding peer: ")
    stale = binding_transport.encode(
        replace(_observation(MOUNTINFO), request=replace(REQUEST, nonce="b" * 32))
    )
    assert isinstance(binding_transport.join(tmp_path, stale, REQUEST), Err)
