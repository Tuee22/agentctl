# Copyright (c) 2026 agentctl contributors.
"""Actual filesystem operations for the pre-gate binding challenge."""

import os
import platform
import re
import secrets
import sys
from pathlib import Path

import pytest

from agentctl.check.binding_challenge import answer, begin, cancel, exchange, finish
from agentctl.process import Child, process_birth, run, start, stop
from agentctl.result import Err, Ok, Result

pytestmark = pytest.mark.evidence("real")


def _stopped(_nonce: str) -> Result[bool, str]:
    """Confirm the synchronous test peer returned or never started."""
    return Ok(value=True)


def test_challenge_roundtrip_and_collision(tmp_path: Path) -> None:
    """Two independent calls exchange exact bytes and remove their own directory."""
    nonce = secrets.token_hex(16)
    directory = tmp_path / (".agentctl-binding-" + nonce)
    assert begin(tmp_path, nonce) == Ok(None)
    assert (directory / "windows").read_bytes() == ("windows:" + nonce).encode()
    assert isinstance(begin(tmp_path, nonce), Err)
    assert answer(tmp_path, nonce) == Ok(None)
    assert (directory / "linux").read_bytes() == ("linux:" + nonce).encode()
    assert isinstance(answer(tmp_path, nonce), Err)
    assert finish(tmp_path, nonce) == Ok(None)
    assert not directory.exists()
    assert isinstance(finish(tmp_path, nonce), Err)
    assert isinstance(begin(tmp_path, "../outside"), Err)


def test_challenge_refuses_changed_bytes(tmp_path: Path) -> None:
    """Changed first or second side bytes cannot be accepted or deleted."""
    nonce = secrets.token_hex(16)
    directory = tmp_path / (".agentctl-binding-" + nonce)
    assert begin(tmp_path, nonce) == Ok(None)
    first = directory / "windows"
    first.write_bytes(b"altered")
    assert isinstance(answer(tmp_path, nonce), Err), "changed challenge accepted"
    first.write_bytes(("windows:" + nonce).encode())
    assert answer(tmp_path, nonce) == Ok(None)
    second = directory / "linux"
    second.write_bytes(b"altered")
    assert isinstance(finish(tmp_path, nonce), Err), "changed response accepted"
    assert first.exists()
    assert second.read_bytes() == b"altered"


def test_challenge_preserves_unexpected_entries(tmp_path: Path) -> None:
    """An unexpected file prevents cleanup and is never treated as owned."""
    nonce = secrets.token_hex(16)
    directory = tmp_path / (".agentctl-binding-" + nonce)
    assert begin(tmp_path, nonce) == Ok(None)
    assert answer(tmp_path, nonce) == Ok(None)
    extra = directory / "other"
    extra.write_bytes(b"not owned")
    assert isinstance(finish(tmp_path, nonce), Err), "foreign entry was accepted"
    assert extra.read_bytes() == b"not owned"
    assert (directory / "windows").is_file(), "foreign entry was accepted"
    assert (directory / "linux").is_file(), "foreign entry was accepted"


def test_exchange_uses_separate_process(root: Path, tmp_path: Path) -> None:
    """An independent interpreter reads and answers the first process's bytes."""
    program = (
        "import sys\nfrom pathlib import Path\n"
        "sys.path.insert(0, sys.argv[1])\n"
        "from agentctl.check.binding_challenge import answer\n"
        "from agentctl.result import Ok\n"
        "assert answer(Path(sys.argv[2]), sys.argv[3]) == Ok(None)\n"
    )

    def peer(nonce: str) -> Result[None, str]:
        observed = run(
            [sys.executable, "-c", program, str(root / "src"), str(tmp_path), nonce],
            cwd=tmp_path,
            env=os.environ,
        )
        if isinstance(observed, Err):
            return Err(observed.error.message)
        if observed.value.code != 0:
            return Err(observed.value.stderr)
        return Ok(None)

    result = exchange(tmp_path, peer, _stopped)
    assert isinstance(result, Ok), result
    assert re.fullmatch(r"[0-9a-f]{32}", result.value)
    assert not (tmp_path / (".agentctl-binding-" + result.value)).exists()


def test_exchange_retains_failure_and_cleans_owned_files(tmp_path: Path) -> None:
    """A refused peer leaves no owned sentinel and retains its primary error."""

    def peer(_nonce: str) -> Result[None, str]:
        return Err("independent peer refusal")

    result = exchange(tmp_path, peer, _stopped)
    assert isinstance(result, Err)
    assert "independent peer refusal" in result.error
    assert not tuple(tmp_path.iterdir()), "failed exchange retained owned challenge"

    def unavailable(_nonce: str) -> Result[None, str]:
        message = "peer unavailable"
        raise OSError(message)

    refused = exchange(tmp_path, unavailable, _stopped)
    assert isinstance(refused, Err)
    assert "peer unavailable" in refused.error
    assert not tuple(tmp_path.iterdir()), "failed exchange retained owned challenge"


def test_exchange_refuses_peer_without_reply(tmp_path: Path) -> None:
    """A peer's successful exit cannot stand in for a returned sentinel."""

    def peer(_nonce: str) -> Result[None, str]:
        return Ok(None)

    result = exchange(tmp_path, peer, _stopped)
    assert isinstance(result, Err), "missing peer response accepted"
    assert "binding directory contains unexpected entries" in result.error
    assert not tuple(tmp_path.iterdir()), "failed exchange retained owned challenge"


def test_exchange_preserves_cleanup_refusal(tmp_path: Path) -> None:
    """Unknown files prevent cleanup without hiding the peer's original failure."""

    def peer(nonce: str) -> Result[None, str]:
        directory = tmp_path / (".agentctl-binding-" + nonce)
        (directory / "foreign").write_bytes(b"not owned")
        return Err("independent peer refusal")

    result = exchange(tmp_path, peer, _stopped)
    assert isinstance(result, Err)
    assert "independent peer refusal" in result.error
    assert "cleanup: binding directory contains unexpected entries" in result.error, (
        "cleanup failure was hidden"
    )
    directory = next(tmp_path.iterdir())
    assert (directory / "windows").is_file(), "unverified cleanup removed sentinel"
    assert (directory / "foreign").read_bytes() == b"not owned"


@pytest.mark.parametrize("peer_failed", [True, False])
def test_exchange_retains_challenge_until_peer_stops(
    tmp_path: Path, *, peer_failed: bool
) -> None:
    """A timeout or response is insufficient evidence to remove the challenge."""
    nonces: list[str] = []

    def peer(nonce: str) -> Result[None, str]:
        nonces.append(nonce)
        return Err("peer timed out") if peer_failed else Ok(None)

    def stopped(_nonce: str) -> Result[bool, str]:
        return Ok(value=False)

    result = exchange(tmp_path, peer, stopped)
    assert len(nonces) == 1
    directory = tmp_path / (".agentctl-binding-" + nonces[0])
    try:
        assert directory.is_dir(), "active challenge was removed"
        assert isinstance(result, Err)
        assert "peer remains active; challenge retained" in result.error
        if peer_failed:
            assert "peer timed out" in result.error
    finally:
        if directory.exists():
            assert cancel(tmp_path, nonces[0]) == Ok(None)


def test_exchange_retains_challenge_for_owned_live_child(tmp_path: Path) -> None:
    """A real registered child must exit before its challenge can be removed."""
    children: list[Child] = []
    nonces: list[str] = []
    registry = tmp_path / "owned-peer.txt"

    def peer(nonce: str) -> Result[None, str]:
        nonces.append(nonce)
        launched = start(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            cwd=tmp_path,
            env=os.environ,
        )
        assert isinstance(launched, Ok), launched
        children.append(launched.value)
        family = platform.system()
        assert family in {"Linux", "Darwin", "Windows"}
        birth = (
            Ok(None)
            if family == "Darwin"
            else process_birth(family, launched.value.pid)
        )
        assert isinstance(birth, Ok), birth
        registry.write_text(
            f"{nonce} {launched.value.pid} {birth.value}\n", encoding="utf-8"
        )
        return Err("peer timed out")

    def stopped(_nonce: str) -> Result[bool, str]:
        return Ok(children[0].handle.poll() is not None)

    try:
        result = exchange(tmp_path, peer, stopped)
        assert isinstance(result, Err)
        assert "peer timed out" in result.error
        assert "challenge retained" in result.error
        assert (tmp_path / (".agentctl-binding-" + nonces[0])).is_dir(), (
            "live child's challenge was removed"
        )
    finally:
        for child in children:
            assert isinstance(stop(child), Ok)
        for nonce in nonces:
            directory = tmp_path / (".agentctl-binding-" + nonce)
            if directory.exists():
                assert cancel(tmp_path, nonce) == Ok(None)
        registry.unlink(missing_ok=True)


def test_exchange_retains_challenge_on_termination_error(tmp_path: Path) -> None:
    """Preserve both the peer failure and the termination-observer failure."""
    nonces: list[str] = []

    def peer(nonce: str) -> Result[None, str]:
        nonces.append(nonce)
        return Err("peer timed out")

    def stopped(_nonce: str) -> Result[bool, str]:
        message = "observer unavailable"
        raise OSError(message)

    result = exchange(tmp_path, peer, stopped)
    assert len(nonces) == 1
    directory = tmp_path / (".agentctl-binding-" + nonces[0])
    try:
        assert directory.is_dir()
        assert isinstance(result, Err)
        assert "peer timed out" in result.error
        assert "observer unavailable" in result.error
    finally:
        if directory.exists():
            assert cancel(tmp_path, nonces[0]) == Ok(None)
