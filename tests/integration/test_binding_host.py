# Copyright (c) 2026 agentctl contributors.
"""Local source comparisons against constructed peer transport messages."""

import secrets
from pathlib import Path

import pytest

from agentctl.check import binding_inventory, binding_transport
from agentctl.check.binding_peer import PeerObservation, PeerRequest
from agentctl.check.wsl_guest_sample import GuestReading
from agentctl.result import Err, Ok

pytestmark = pytest.mark.evidence("real")


def test_join_observes_current_local_bytes(tmp_path: Path) -> None:
    """An actual local inventory must equal every byte in the peer message.

    The peer host and mount values are constructed; this is not WSL evidence.
    """
    (tmp_path / ".gitignore").write_text("ignored\n", encoding="utf-8")
    (tmp_path / "ignored").write_bytes(b"before")
    (tmp_path / "untracked").write_bytes(b"current")
    nonce = secrets.token_hex(16)
    request = PeerRequest(
        "dedicated", "/mnt/c/Users/name/agentctl", "/work/agentctl", nonce
    )
    inventory = binding_inventory.observe(tmp_path, nonce)
    assert isinstance(inventory, Ok)
    mountinfo = (
        "10 1 8:1 / / rw - ext4 /dev/root rw\n"
        "20 10 0:40 / /mnt/c rw - 9p C:\\134 rw\n"
        "21 10 0:40 /Users/name/agentctl /work/agentctl rw - 9p C:\\134 rw\n"
    )
    peer = PeerObservation(
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
    message = binding_transport.encode(peer)
    assert binding_transport.join(tmp_path, message, request) == Ok(peer)
    (tmp_path / "ignored").write_bytes(b"after")
    assert isinstance(binding_transport.join(tmp_path, message, request), Err), (
        "different local inventory was accepted"
    )
    (tmp_path / "ignored").write_bytes(b"before")
    (tmp_path / "another-untracked").write_bytes(b"new")
    assert isinstance(binding_transport.join(tmp_path, message, request), Err), (
        "different local inventory was accepted"
    )
