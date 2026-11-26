# Copyright (c) 2026 agentctl contributors.
"""Refusals of the source challenge at filesystem and observer boundaries."""

import os
from collections.abc import Callable
from pathlib import Path

import pytest

from agentctl.check import binding_challenge
from agentctl.foundation import Err, Ok, Result

pytestmark = pytest.mark.evidence("value")
NONCE = "a" * 32
OWNED = ".agentctl-binding-" + NONCE
BLOCKED = "blocked"
REAL_OPEN = os.open


def _stopped(_nonce: str) -> Result[bool, str]:
    """Report the synchronous peer as terminated."""
    return Ok(value=True)


def _challenge(root: Path) -> Path:
    """Begin a challenge and return its directory."""
    assert binding_challenge.begin(root, NONCE) == Ok(None)
    return root / OWNED


def _failing_rmdir(_path: Path) -> None:
    """Refuse directory removal as a failing native filesystem would."""
    raise OSError(BLOCKED)


def _failing_open(_path: Path, _flags: int, _mode: int = 0) -> int:
    """Refuse sentinel creation."""
    raise OSError(BLOCKED)


def _littering_open(path: Path, flags: int, mode: int = 0) -> int:
    """Leave a foreign file beside the sentinel, then refuse its creation."""
    os.close(REAL_OPEN(Path(path).parent / "foreign", flags, mode))
    raise OSError(BLOCKED)


def _resolving(
    real: Callable[..., Path], victim: str, *, fail: bool
) -> Callable[..., Path]:
    """Fault the strict resolution of only the challenge directory."""

    def resolve(path: Path, *, strict: bool = False) -> Path:
        if path.name == victim:
            if fail:
                raise OSError(BLOCKED)
            return path.parent / "elsewhere"
        return real(path, strict=strict)

    return resolve


def test_source_root_must_exist_and_be_a_directory(tmp_path: Path) -> None:
    """A regular file or missing path cannot host a challenge."""
    regular = tmp_path / "file"
    regular.write_bytes(b"")
    refused = binding_challenge.challenge_directory(regular, NONCE)
    assert refused == Err("binding source is not a directory")
    missing = binding_challenge.challenge_directory(tmp_path / "missing", NONCE)
    assert isinstance(missing, Err)
    assert missing.error.startswith("cannot resolve binding source: ")


def test_existing_boundary_refuses_bad_nonce_and_absent_directory(
    tmp_path: Path,
) -> None:
    """Answering, cancelling and finishing need a valid, existing challenge."""
    for operation in (
        binding_challenge.answer,
        binding_challenge.finish,
        binding_challenge.cancel,
    ):
        assert operation(tmp_path, "bad") == Err("invalid binding nonce")
        assert operation(tmp_path, NONCE) == Err(
            "binding challenge directory unavailable"
        )


def test_existing_boundary_refuses_escape_and_inspection_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A challenge whose strict resolution differs or fails is refused."""
    directory = _challenge(tmp_path)
    with monkeypatch.context() as patch:
        patch.setattr(Path, "resolve", _resolving(Path.resolve, OWNED, fail=False))
        escaped = binding_challenge.answer(tmp_path, NONCE)
    assert escaped == Err("binding challenge directory escaped source")
    with monkeypatch.context() as patch:
        patch.setattr(Path, "resolve", _resolving(Path.resolve, OWNED, fail=True))
        failed = binding_challenge.answer(tmp_path, NONCE)
    assert failed == Err("cannot inspect binding directory: " + BLOCKED)
    assert binding_challenge.cancel(tmp_path, NONCE) == Ok(None)
    assert not directory.exists()


def test_begin_reports_write_failure_with_and_without_cleanup_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failed sentinel write removes the empty directory or reports why not."""
    with monkeypatch.context() as patch:
        patch.setattr(binding_challenge.os, "open", _failing_open)
        failed = binding_challenge.begin(tmp_path, NONCE)
    assert failed == Err("cannot write binding challenge: " + BLOCKED)
    assert not (tmp_path / OWNED).exists()
    with monkeypatch.context() as patch:
        patch.setattr(binding_challenge.os, "open", _littering_open)
        stuck = binding_challenge.begin(tmp_path, NONCE)
    assert isinstance(stuck, Err)
    assert stuck.error.startswith("cannot write binding challenge: " + BLOCKED)
    assert "; cleanup: " in stuck.error
    (tmp_path / OWNED / "foreign").unlink()
    (tmp_path / OWNED).rmdir()


def test_finish_and_cancel_report_removal_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A directory that cannot be removed is a structured failure."""
    directory = _challenge(tmp_path)
    assert binding_challenge.answer(tmp_path, NONCE) == Ok(None)
    with monkeypatch.context() as patch:
        patch.setattr(Path, "rmdir", _failing_rmdir)
        finished = binding_challenge.finish(tmp_path, NONCE)
    assert finished == Err("cannot finish binding challenge: " + BLOCKED)
    directory.rmdir()
    _challenge(tmp_path)
    with monkeypatch.context() as patch:
        patch.setattr(Path, "rmdir", _failing_rmdir)
        cancelled = binding_challenge.cancel(tmp_path, NONCE)
    assert cancelled == Err("cannot clean binding challenge: " + BLOCKED)
    directory.rmdir()


def test_cancel_refuses_changed_sentinel_bytes(tmp_path: Path) -> None:
    """A sentinel with foreign bytes is neither accepted nor removed."""
    directory = _challenge(tmp_path)
    (directory / "windows").write_bytes(b"altered")
    assert binding_challenge.cancel(tmp_path, NONCE) == Err(
        "binding sentinel bytes differ"
    )
    assert (directory / "windows").read_bytes() == b"altered"


def test_exchange_reports_failure_to_begin(tmp_path: Path) -> None:
    """No peer is consulted when the challenge cannot be created."""
    refused = binding_challenge.exchange(
        tmp_path / "missing", lambda _nonce: Ok(None), _stopped
    )
    assert isinstance(refused, Err)
    assert refused.error.startswith("cannot resolve binding source: ")
