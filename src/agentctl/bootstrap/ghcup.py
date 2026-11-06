# Copyright (c) 2026 agentctl contributors.
"""Reuse the user's ghcup or publish only a verified pinned download."""

import hashlib
import os
import tempfile
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from http.client import HTTPException, HTTPResponse
from pathlib import Path
from typing import BinaryIO
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import build_opener

from agentctl.bootstrap.pins import Asset, Pins, asset_for
from agentctl.hostfacts import HostFacts
from agentctl.result import Err, Ok, Result

CHUNK_BYTES = 64 * 1024


@dataclass(frozen=True, slots=True)
class GhcupError:
    """A refused reuse or unsuccessful download, without a partial installation."""

    message: str


def transfer(response: HTTPResponse, stream: BinaryIO) -> tuple[str, int]:
    """Hash the bytes actually written, keeping the memory bound to one chunk."""
    digest = hashlib.sha256()
    count = 0
    while block := response.read(CHUNK_BYTES):
        stream.write(block)
        digest.update(block)
        count += len(block)
    return digest.hexdigest(), count


@contextmanager
def connection(url: str) -> Generator[HTTPResponse]:
    """Narrow urllib's response at the I/O boundary and always close it."""
    try:
        with build_opener().open(url, timeout=30) as response:
            if not isinstance(response, HTTPResponse):
                message = "ghcup download requires an HTTP response"
                raise TypeError(message)
            yield response
    except HTTPError as exc:
        exc.close()
        raise


def fetch(asset: Asset, staged: Path) -> Result[None, GhcupError]:
    """Require the advertised length and pinned digest before publication."""
    descriptor = os.open(staged, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as stream, connection(asset.url) as response:
        expected = response.getheader("Content-Length")
        digest, count = transfer(response, stream)
    if expected is not None and count != int(expected):
        return Err(GhcupError("ghcup download was truncated"))
    if digest != asset.sha256:
        return Err(GhcupError("ghcup download SHA-256 does not match its pin"))
    return Ok(None)


def download(asset: Asset, destination: Path) -> Result[Path, GhcupError]:
    """Download into a private sibling and rename after length and digest checks."""
    if urlsplit(asset.url).scheme not in {"http", "https"}:
        return Err(GhcupError("ghcup download requires an HTTP or HTTPS URL"))
    try:
        if destination.exists() or destination.is_symlink():
            return Err(
                GhcupError("ghcup destination is occupied; gather host facts again")
            )
        destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix=".ghcup-", dir=destination.parent
        ) as temporary:
            staged = Path(temporary) / "download"
            verified = fetch(asset, staged)
            if isinstance(verified, Err):
                return verified
            if asset.family != "Windows":
                staged.chmod(0o755)
            if destination.exists() or destination.is_symlink():
                return Err(
                    GhcupError("ghcup destination changed during download; retry")
                )
            staged.replace(destination)
        return Ok(destination)
    except (OSError, URLError, HTTPException, ValueError, TypeError) as exc:
        return Err(GhcupError(f"Cannot download verified ghcup: {exc}"))


def provide(facts: HostFacts, pins: Pins) -> Result[Path, GhcupError]:
    """Respect a found executable and its floor before considering any download."""
    asset = asset_for(pins, facts.family, facts.architecture)
    if asset is None:
        return Err(GhcupError("No ghcup asset for this platform"))
    if facts.ghcup is not None:
        if facts.ghcup.version is None or facts.ghcup.version < pins.ghcup_floor:
            return Err(GhcupError(f"Use {facts.ghcup.path} upgrade, then retry"))
        return Ok(facts.ghcup.path)
    return download(asset, facts.ghcup_destination)
