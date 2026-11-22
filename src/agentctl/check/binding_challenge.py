# Copyright (c) 2026 agentctl contributors.
"""Exclusive nonce challenges for a separately observed shared source mount."""

import os
import re
import secrets
import stat
from collections.abc import Callable
from pathlib import Path

from agentctl.foundation import Err, Ok, Result


def challenge_directory(root: Path, nonce: str) -> Result[Path, str]:
    """Resolve only the nonce-named direct child of an existing source root."""
    if re.fullmatch(r"[0-9a-f]{32}", nonce) is None:
        return Err("invalid binding nonce")
    try:
        if root.is_symlink() or root.is_junction():
            return Err("binding source is a link or junction")
        source = root.resolve(strict=True)
        if not source.is_dir():
            return Err("binding source is not a directory")
        return Ok(source / (".agentctl-binding-" + nonce))
    except (OSError, RuntimeError) as exc:
        return Err("cannot resolve binding source: " + str(exc))


def _write(path: Path, content: bytes) -> None:
    """Create a new sentinel without replacing an existing file or link."""
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(content)


def _private_sentinel(path: Path) -> bool:
    """Refuse links and regular files with another name outside the challenge."""
    observed = path.lstat()
    return stat.S_ISREG(observed.st_mode) and observed.st_nlink == 1


def _existing(root: Path, nonce: str) -> Result[Path, str]:
    """Refuse links and non-directories at an existing challenge boundary."""
    result = challenge_directory(root, nonce)
    if isinstance(result, Err):
        return result
    directory = result.value
    try:
        if directory.is_symlink() or directory.is_junction() or not directory.is_dir():
            return Err("binding challenge directory unavailable")
        if directory.resolve(strict=True) != directory:
            return Err("binding challenge directory escaped source")
        return Ok(directory)
    except (OSError, RuntimeError) as exc:
        return Err("cannot inspect binding directory: " + str(exc))


def begin(root: Path, nonce: str) -> Result[None, str]:
    """Create the first side's challenge in a new, nonce-owned directory."""
    result = challenge_directory(root, nonce)
    if isinstance(result, Err):
        return result
    directory = result.value
    try:
        directory.mkdir(mode=0o700)
    except OSError as exc:
        return Err("cannot create binding directory: " + str(exc))
    try:
        _write(directory / "windows", ("windows:" + nonce).encode())
        return Ok(None)
    except OSError as exc:
        try:
            directory.rmdir()
            return Err("cannot write binding challenge: " + str(exc))
        except OSError as cleanup:
            return Err(
                "cannot write binding challenge: "
                + str(exc)
                + "; cleanup: "
                + str(cleanup)
            )


def answer(root: Path, nonce: str) -> Result[None, str]:
    """Read the first side's bytes and create a distinct second-side reply."""
    result = _existing(root, nonce)
    if isinstance(result, Err):
        return result
    directory = result.value
    challenge = directory / "windows"
    try:
        if not _private_sentinel(challenge):
            return Err("binding challenge unavailable")
        if challenge.read_bytes() != ("windows:" + nonce).encode():
            return Err("binding challenge differs")
        _write(directory / "linux", ("linux:" + nonce).encode())
        return Ok(None)
    except OSError as exc:
        return Err("cannot answer binding challenge: " + str(exc))


def finish(root: Path, nonce: str) -> Result[None, str]:
    """Verify both sentinels and remove only the exact owned files and directory."""
    result = _existing(root, nonce)
    if isinstance(result, Err):
        return result
    directory = result.value
    first, second = directory / "windows", directory / "linux"
    try:
        if {entry.name for entry in directory.iterdir()} != {"windows", "linux"}:
            return Err("binding directory contains unexpected entries")
        if any(not _private_sentinel(path) for path in (first, second)):
            return Err("binding sentinel is not a regular file")
        if (
            first.read_bytes() != ("windows:" + nonce).encode()
            or second.read_bytes() != ("linux:" + nonce).encode()
        ):
            return Err("binding sentinel bytes differ")
        first.unlink()
        second.unlink()
        directory.rmdir()
        return Ok(None)
    except OSError as exc:
        return Err("cannot finish binding challenge: " + str(exc))


def cancel(root: Path, nonce: str) -> Result[None, str]:
    """Remove only an incomplete challenge whose remaining files match the nonce."""
    result = _existing(root, nonce)
    if isinstance(result, Err):
        return result
    directory = result.value
    try:
        names = frozenset(entry.name for entry in directory.iterdir())
        if not names <= {"windows", "linux"}:
            return Err("binding directory contains unexpected entries")
        entries = tuple(
            (directory / name, (name + ":" + nonce).encode()) for name in sorted(names)
        )
        if any(not _private_sentinel(path) for path, _ in entries):
            return Err("binding sentinel is not a regular file")
        if any(path.read_bytes() != content for path, content in entries):
            return Err("binding sentinel bytes differ")
        for path, _content in entries:
            path.unlink()
        directory.rmdir()
        return Ok(None)
    except OSError as exc:
        return Err("cannot clean binding challenge: " + str(exc))


type Peer = Callable[[str], Result[None, str]]
type ObserveStopped = Callable[[str], Result[bool, str]]


def _respond(peer: Peer, nonce: str) -> Result[None, str]:
    """Convert the peer adapter's declared operating-system failures."""
    try:
        return peer(nonce)
    except (OSError, RuntimeError) as exc:
        return Err("binding peer failed: " + str(exc))


def exchange(root: Path, peer: Peer, stopped: ObserveStopped) -> Result[str, str]:
    """Run a fresh challenge and retain primary and cleanup failures separately.

    A successful exchange proves only the observed bytes, not host identity,
    mount identity, inventory equality or resource readiness. The caller must
    independently verify termination of the actual peer and its descendants.
    """
    nonce = secrets.token_hex(16)
    created = begin(root, nonce)
    if isinstance(created, Err):
        return created
    response = _respond(peer, nonce)
    try:
        termination = stopped(nonce)
    except (OSError, RuntimeError) as exc:
        termination = Err("binding termination observer failed: " + str(exc))
    if isinstance(termination, Err) or termination.value is not True:
        primary = (
            response.error if isinstance(response, Err) else "peer response received"
        )
        reason = (
            termination.error if isinstance(termination, Err) else "peer remains active"
        )
        return Err(primary + "; " + reason + "; challenge retained")
    if isinstance(response, Err):
        cleaned = cancel(root, nonce)
        return Err(
            response.error
            + ("; cleanup: " + cleaned.error if isinstance(cleaned, Err) else "")
        )
    completed = finish(root, nonce)
    if isinstance(completed, Err):
        cleaned = cancel(root, nonce)
        return Err(
            completed.error
            + ("; cleanup: " + cleaned.error if isinstance(cleaned, Err) else "")
        )
    return Ok(nonce)
