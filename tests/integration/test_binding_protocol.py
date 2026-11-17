# Copyright (c) 2026 agentctl contributors.
"""The peer protocol refuses malformed requests across a process boundary."""

import json
import os
import sys
from pathlib import Path

import pytest

from agentctl.check import binding_peer
from agentctl.check.binding_peer import PeerRequest
from agentctl.check.binding_protocol import (
    MAX_REQUEST,
    Request,
    decode,
    dispatch,
    encode,
)
from agentctl.process import run
from agentctl.result import Err, Ok

pytestmark = pytest.mark.evidence("real")


def test_cleanup_response_carries_nonce_and_uid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The cleanup protocol carries the observed identity and exact request nonce."""
    peer = PeerRequest("dedicated", "/mnt/c/source", "/work/source", "a" * 32)
    monkeypatch.setattr(
        binding_peer, "observe_absence_identity", lambda _request: Ok((True, 1000))
    )
    result = dispatch(Request("absence", peer))
    assert isinstance(result, Ok)
    assert json.loads(result.value) == {
        "nonce": peer.nonce,
        "uid": 1000,
        "absent": True,
    }, "cleanup identity was not transported"


def test_protocol_rejects_unrecognized_or_ambiguous_input(root: Path) -> None:
    """A separate interpreter refuses duplicates, extras and invalid operations."""
    peer = PeerRequest("dedicated", "/mnt/c/source", "/work/source", "a" * 32)
    request = Request("observe", peer)
    assert decode(encode(request)) == Ok(request)
    for text in (
        '{"operation":"observe","operation":"absence","distribution":"d","source":"/s","target":"/t","nonce":"a"}',
        '{"operation":"other","distribution":"d","source":"/s","target":"/t","nonce":"a"}',
        '{"operation":"observe","distribution":"d","source":"/s","target":"/t","nonce":"a","extra":1}',
        "x" * (MAX_REQUEST + 1),
    ):
        assert isinstance(decode(text), Err), "invalid peer request was accepted"
        child = run(
            [sys.executable, "-m", "agentctl.check.binding_protocol"],
            cwd=root,
            env=os.environ,
            input_text=text,
        )
        assert isinstance(child, Ok)
        assert child.value.code != 0, "invalid peer request was accepted"
        assert not child.value.stdout
