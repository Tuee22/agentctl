# Copyright (c) 2026 agentctl contributors.
"""Shared, read-only native host context observations."""

import os
import platform
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class HostContext:
    """Read-only system inputs captured once before bootstrap observation."""

    family: str
    machine: str
    home: Path
    cache: Path
    cwd: Path
    environment: tuple[tuple[str, str], ...]
    is_root: bool
    interactive: bool
    assume_yes: bool
    os_release: Path = Path("/etc/os-release")


@runtime_checkable
class PosixIdentity(Protocol):
    """The optional standard-library effective-uid observation."""

    def geteuid(self) -> int:
        """Return the effective user id without invoking another process."""
        ...


def effective_root(family: str, identity: object) -> bool:
    """Observe Unix privilege while treating Windows as having no sudo action."""
    return (
        family != "Windows"
        and isinstance(identity, PosixIdentity)
        and identity.geteuid() == 0
    )


def current(cache: Path, *, assume_yes: bool = False) -> HostContext:
    """Capture native identity and terminal facts without spawning uname."""
    family = platform.system()
    return HostContext(
        family,
        platform.machine(),
        Path.home(),
        cache,
        Path.cwd(),
        tuple(os.environ.items()),
        effective_root(family, os),
        sys.stdin.isatty() and sys.stderr.isatty(),
        assume_yes,
    )
