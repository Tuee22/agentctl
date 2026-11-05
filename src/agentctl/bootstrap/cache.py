# Copyright (c) 2026 agentctl contributors.
"""Canonical source identities and immutable native-binary cache paths."""

import hashlib
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from agentctl.bootstrap.pins import Pins, asset_for
from agentctl.hostfacts import architecture
from agentctl.result import Err, Ok, Result


@dataclass(frozen=True, slots=True)
class CacheError:
    """An unsupported platform or incomplete, unmodelled source inventory."""

    message: str


@dataclass(frozen=True, slots=True)
class Source:
    """The exact bundled project, raw pin file and bindist platform identity."""

    project: Path
    pins: Path
    triple: str


@dataclass(frozen=True, slots=True)
class Entry:
    """A relative source entry whose kind is observed independently of its bytes."""

    path: str
    kind: Literal["file", "directory", "symlink", "other"]
    body: bytes


@dataclass(frozen=True, slots=True)
class Layout:
    """One source identity, its outside-tree build and immutable published path."""

    digest: str
    directory: Path
    binary: Path


def platform(pins: Pins, family: str, machine: str) -> Result[str, CacheError]:
    """Use exactly the platform prefix that selects the shipped ghcup asset."""
    if family not in {"Linux", "Darwin", "Windows"}:
        return Err(CacheError("Unsupported binary build platform: " + family))
    asset = asset_for(pins, family, architecture(family, machine))
    if asset is None:
        return Err(CacheError("Unsupported binary build architecture: " + machine))
    return Ok(asset.url.rsplit("/", 1)[-1].partition("-ghcup-")[0])


def kind(mode: int) -> Literal["file", "directory", "symlink", "other"]:
    """Keep unsupported entries and links visible instead of silently omitting them."""
    if stat.S_ISREG(mode):
        return "file"
    if stat.S_ISDIR(mode):
        return "directory"
    return "symlink" if stat.S_ISLNK(mode) else "other"


def _walk_failure(error: OSError) -> None:
    """Make incomplete directory traversal a typed digest failure."""
    raise error


def inventory(project: Path) -> tuple[Entry, ...]:
    """Observe every source file and directory without following directory links."""
    paths = (project / "agentctl-core.cabal", project / "cabal.project")
    roots = ("app", "src", "test")
    paths += tuple(project / name for name in roots)
    for current, directories, files in os.walk(project, onerror=_walk_failure):
        if Path(current) == project:
            directories[:] = [name for name in directories if name in roots]
        else:
            paths += tuple(Path(current) / item for item in (*directories, *files))
    entries: tuple[Entry, ...] = ()
    for path in paths:
        entry_kind = kind(path.lstat().st_mode)
        entries += (
            Entry(
                path.relative_to(project).as_posix(),
                entry_kind,
                path.read_bytes() if entry_kind == "file" else b"",
            ),
        )
    return entries


def hash_entries(
    entries: tuple[Entry, ...], pins: bytes, triple: str
) -> Result[str, CacheError]:
    """Hash sorted path/body pairs, raw pins and the triple with eight-byte lengths."""
    files = tuple(entry for entry in entries if entry.kind == "file")
    mandatory = {"agentctl-core.cabal", "cabal.project"}
    if not mandatory <= {entry.path for entry in files} or any(
        entry.kind in {"symlink", "other"} for entry in entries
    ):
        return Err(CacheError("Binary sources require regular files and no symlinks"))
    hashed = hashlib.sha256()
    try:
        fields = (
            *(
                field
                for entry in sorted(files, key=lambda entry: entry.path)
                for field in (entry.path.encode("utf-8"), entry.body)
            ),
            pins,
            triple.encode("ascii"),
        )
    except UnicodeError as exc:
        return Err(CacheError(f"Invalid binary source identity: {exc}"))
    for field in fields:
        hashed.update(len(field).to_bytes(8, "big"))
        hashed.update(field)
    return Ok(hashed.hexdigest())


def digest(source: Source) -> Result[str, CacheError]:
    """Read actual bytes and refuse every unreadable or incomplete source tree."""
    try:
        return hash_entries(
            inventory(source.project), source.pins.read_bytes(), source.triple
        )
    except (OSError, UnicodeError) as exc:
        return Err(CacheError(f"Cannot hash binary sources: {exc}"))


def layout(
    source: Source, cache: Path, data: Path, family: str
) -> Result[Layout, CacheError]:
    """Keep build and executable paths tied to the same current source identity."""
    identity = digest(source)
    if isinstance(identity, Err):
        return identity
    name = "agentctl-core.exe" if family == "Windows" else "agentctl-core"
    return Ok(
        Layout(
            identity.value,
            cache / "build" / identity.value,
            data / "bin" / identity.value / name,
        )
    )
