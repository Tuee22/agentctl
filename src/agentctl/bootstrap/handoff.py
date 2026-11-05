# Copyright (c) 2026 agentctl contributors.
"""Raw command transport after the application-owned digest and build boundary."""

import os
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from agentctl import hostfacts, process
from agentctl.bootstrap import binary, build
from agentctl.paths import Family, directories
from agentctl.result import Err, Ok, Result


class Mode(Enum):
    """The native process-lifetime contract selected by the host OS."""

    EXECVE = "execve"
    CHILD = "child"


@dataclass(frozen=True, slots=True)
class HandoffError:
    """A bootstrap or native transport refusal reported by the Python application."""

    message: str


@dataclass(frozen=True, slots=True)
class Transfer:
    """A verified executable and literal tail with private environment values."""

    mode: Mode
    executable: Path
    arguments: tuple[str, ...]
    directory: Path
    environment: tuple[tuple[str, str], ...] = field(repr=False)


def mode(family: Family) -> Mode:
    """Select replacement on POSIX and an inherited-stream child on Windows."""
    return Mode.CHILD if family == "Windows" else Mode.EXECVE


def transfer(request: Transfer) -> Result[int, HandoffError]:
    """Flush Python's streams and transport the command without parsing its tail."""
    try:
        sys.stdout.flush()
        sys.stderr.flush()
    except OSError as exc:
        return Err(HandoffError(f"Cannot flush terminal output: {exc}"))
    argv = [str(request.executable), *request.arguments]
    environment = dict(request.environment)
    if request.mode is Mode.EXECVE:
        result = process.replace(argv, env=environment)
    else:
        result = process.foreground(argv, cwd=request.directory, env=environment)
    return (
        Err(HandoffError(result.error.message)) if isinstance(result, Err) else result
    )


def run(
    family: str, command: str, arguments: tuple[str, ...], *, assume_yes: bool
) -> Result[int, HandoffError]:
    """Ensure the current binary and supply only the directory and protocol contract."""
    if family not in {"Linux", "Darwin", "Windows"}:
        return Err(HandoffError("Unsupported host: " + family))
    paths = directories(family, os.environ, Path.home())
    host = hostfacts.current(paths.cache, assume_yes=assume_yes)
    executable = binary.ensure(
        binary.Request(
            build.bundled_project(),
            Path(__file__).with_name("pins.toml"),
            host,
            paths.data,
        )
    )
    if isinstance(executable, Err):
        return Err(HandoffError(executable.error.message))
    distribution = (
        hostfacts.read_distribution(host.os_release) if family == "Linux" else None
    )
    name = distribution.value.name if isinstance(distribution, Ok) else "other"
    environment = {
        **os.environ,
        "AGENTCTL_PROTOCOL_VERSION": "1",
        "AGENTCTL_CACHE_DIR": str(paths.cache),
        "AGENTCTL_DATA_DIR": str(paths.data),
        "AGENTCTL_STATE_DIR": str(paths.state),
        "AGENTCTL_DISTRIBUTION": name,
    }
    return transfer(
        Transfer(
            mode(family),
            executable.value,
            (command, *arguments),
            host.cwd,
            tuple(environment.items()),
        )
    )
