# Copyright (c) 2026 agentctl contributors.
"""The peer cleanup observation checks an actual nonce-named entry."""

from pathlib import Path

import pytest

from agentctl.check.binding_peer import sentinel_absent
from agentctl.result import Err, Ok

pytestmark = pytest.mark.evidence("real")


def test_peer_cleanup_observes_nonce_entry(tmp_path: Path) -> None:
    """Both a file and a directory count as a remaining sentinel."""
    nonce = "a" * 32
    entry = tmp_path / (".agentctl-binding-" + nonce)
    assert sentinel_absent(tmp_path, nonce) == Ok(value=True)
    entry.write_bytes(b"unexpected")
    assert sentinel_absent(tmp_path, nonce) == Ok(value=False), (
        "remaining file was ignored"
    )
    entry.unlink()
    entry.mkdir()
    assert sentinel_absent(tmp_path, nonce) == Ok(value=False), (
        "remaining directory was ignored"
    )
    assert isinstance(sentinel_absent(tmp_path, "../other"), Err)
