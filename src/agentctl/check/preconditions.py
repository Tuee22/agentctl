# Copyright (c) 2026 agentctl contributors.
"""Editable-checkout identity, tool pins and single-run locking."""

import errno
import importlib.metadata
import json
import os
import platform
import shutil
import sys
import time
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from typing import IO, Protocol, runtime_checkable

import agentctl
from agentctl.bootstrap.pins import Architecture, Pins, asset_for
from agentctl.paths import Family
from agentctl.process import run
from agentctl.result import Err, Ok, Result

PINS = (
    ("click", "8.5.0"),
    ("ruff", "0.17.3"),
    ("ty", "0.0.95"),
    ("pytest", "9.2.0"),
    ("coverage", "7.17.0"),
    ("hatchling", "1.33.0"),
)


def identity(root: Path, metadata: object, module: Path) -> tuple[str, ...]:
    """Require a matching PEP 610 editable URL and loaded source location."""
    if not isinstance(metadata, dict):
        return ("P1: missing PEP 610 metadata; reinstall editable '.[dev]'",)
    directory = metadata.get("dir_info")
    if not isinstance(directory, dict) or directory.get("editable") is not True:
        return ("P1: non-editable install; reinstall editable '.[dev]'",)
    if metadata.get(
        "url"
    ) != root.resolve().as_uri() or not module.resolve().is_relative_to(
        root.resolve() / "src/agentctl"
    ):
        return ("P1: another checkout is installed; reinstall editable '.[dev]'",)
    return ()


def python_floor(version: tuple[int, int]) -> tuple[str, ...]:
    """Keep the interpreter-floor decision independent of this host's version."""
    return (
        ()
        if version >= (3, 12)
        else (
            (
                "P3: Python 3.12 or later is required; "
                "reinstall editable '.[dev]' with Python 3.12+"
            ),
        )
    )


def inspect(root: Path) -> tuple[str, ...]:
    """Report all unmet identity, pin, Python and git preconditions."""
    try:
        distribution = importlib.metadata.distribution("agentctl")
        raw = distribution.read_text("direct_url.json")
    except importlib.metadata.PackageNotFoundError:
        raw = None
    try:
        metadata = json.loads(raw) if raw is not None else None
    except json.JSONDecodeError:
        metadata = None
    problems = (
        *identity(root, metadata, Path(str(agentctl.__file__))),
        *python_floor(sys.version_info[:2]),
    )
    for name, pin in PINS:
        try:
            actual = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            actual = "absent"
        if actual != pin:
            problems += (
                f"P2: {name} is {actual}, need {pin}; reinstall editable '.[dev]'",
            )
    git = shutil.which("git")
    if git is None:
        return (*problems, "P4: install git and work from a clone")
    result = run([git, "rev-parse", "--show-toplevel"], cwd=root, env=os.environ)
    if (
        isinstance(result, Err)
        or result.value.code != 0
        or Path(result.value.stdout.strip()).resolve() != root.resolve()
    ):
        problems += ("P4: work from this git checkout",)
    return problems


@runtime_checkable
class PosixLocks(Protocol):
    """The standard-library POSIX advisory lock interface."""

    LOCK_UN: int
    LOCK_EX: int
    LOCK_NB: int

    def flock(self, fd: int, operation: int) -> None:
        """Apply a file lock operation."""
        ...


@runtime_checkable
class WindowsLocks(Protocol):
    """The standard-library Windows byte-range lock interface."""

    LK_UNLCK: int
    LK_NBLCK: int

    def locking(self, fd: int, mode: int, nbytes: int) -> None:
        """Apply a byte-range lock operation."""
        ...


def _file_lock(handle: IO[str], *, unlock: bool) -> None:  # pragma: no cover
    """Take or release a non-blocking operating-system lock."""
    if platform.system() == "Windows":
        backend = import_module("msvcrt")
        if not isinstance(backend, WindowsLocks):
            message = "Windows locking interface is unavailable"
            raise OSError(message)
        handle.seek(0)
        backend.locking(
            handle.fileno(), backend.LK_UNLCK if unlock else backend.LK_NBLCK, 1
        )
    else:
        backend = import_module("fcntl")
        if not isinstance(backend, PosixLocks):
            message = "POSIX locking interface is unavailable"
            raise OSError(message)
        backend.flock(
            handle.fileno(),
            backend.LOCK_UN if unlock else backend.LOCK_EX | backend.LOCK_NB,
        )


@contextmanager
def single_run(state: Path) -> Generator[tuple[str, ...]]:
    """Hold the check lock until scope exit; report an existing holder."""
    lock = state / "locks/check.lock"
    lock.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with lock.open("a+", encoding="utf-8") as handle:
        try:
            _file_lock(handle, unlock=False)
        except OSError:
            handle.seek(0)
            yield (f"P5: check already running, pid {handle.read().strip()}",)
        else:
            handle.seek(0)
            handle.truncate()
            handle.write(str(os.getpid()))
            handle.flush()
            try:
                yield ()
            finally:
                _file_lock(handle, unlock=True)


@dataclass(frozen=True, slots=True)
class LockError:
    """A cache lock could not be opened or acquired before its deadline."""

    message: str


def acquire(handle: IO[str], timeout: float) -> Result[None, LockError]:
    """Wait only on native contention, keeping other kernel failures immediate."""
    deadline = time.monotonic() + timeout
    while True:
        try:
            _file_lock(handle, unlock=False)
        except OSError as exc:
            if exc.errno not in {errno.EACCES, errno.EAGAIN, errno.EDEADLK}:
                return Err(LockError(f"Cannot acquire build lock: {exc}"))
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return Err(LockError("Timed out waiting for the build lock"))
            time.sleep(min(0.05, remaining))
        else:
            return Ok(None)


@contextmanager
def exclusive_file(
    path: Path, *, timeout: float = 1800
) -> Generator[Result[None, LockError]]:
    """Hold one cross-platform advisory file lock, releasing it on every body exit."""
    try:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        handle = path.open("a+", encoding="utf-8")
    except OSError as exc:
        yield Err(LockError(f"Cannot open build lock: {exc}"))
        return
    with handle:
        locked = acquire(handle, timeout)
        if isinstance(locked, Err):
            yield locked
            return
        try:
            yield Ok(None)
        finally:
            _file_lock(handle, unlock=True)


@dataclass(frozen=True, slots=True)
class ToolchainReadiness:
    """Observed capacity and reachability, with budgets for only missing pins."""

    family: Family
    architecture: Architecture
    ghcup_free: int
    cache_free: int
    ghcup_required: int
    cache_required: int
    pins_ready: bool
    downloads_reachable: bool
    hackage_reachable: bool


def toolchain_preconditions(facts: ToolchainReadiness, pins: Pins) -> tuple[str, ...]:
    """Report P7, P8 and P10 independently, without prompting or installing."""
    problems: tuple[str, ...] = ()
    if (
        facts.ghcup_free < facts.ghcup_required
        or facts.cache_free < facts.cache_required
    ):
        problems += (
            (
                "P7: free space in ghcup's directory and agentctl's cache "
                "for missing toolchain pins"
            ),
        )
    if not facts.pins_ready and (
        not facts.downloads_reachable or not facts.hackage_reachable
    ):
        problems += (
            (
                "P8: connect to a network reaching downloads.haskell.org and "
                "hackage.haskell.org; a first run or pin change needs it"
            ),
        )
    if asset_for(pins, facts.family, facts.architecture) is None:
        problems += (
            (
                "P10: no GHC bindist for this platform; use Linux x86_64/aarch64, "
                "macOS x86_64/arm64 or Windows x86_64"
            ),
        )
    return problems


SOCKET_PATH_LIMIT = 100


def socket_path_length(path: Path) -> tuple[str, ...]:
    """Hold every constructed private Unix socket path to the common byte bound."""
    return (
        ()
        if len(str(path).encode("utf-8")) <= SOCKET_PATH_LIMIT
        else ("P6: private tmux socket path exceeds 100 bytes; use a shorter TMPDIR",)
    )


def private_socket_path(run_dir: Path, uid: int) -> Path:
    """Reserve the fixed-width namespace the private multiplexer harness uses."""
    return run_dir / "mux/00000000" / f"tmux-{uid}" / "default"


def inspect_socket(run_dir: Path, family: Family) -> tuple[str, ...]:
    """Read the run directory's owner while keeping Windows free of Unix sockets."""
    if family == "Windows":
        return ()
    try:
        owned = run_dir.resolve(strict=True)
        path = private_socket_path(owned, owned.stat().st_uid)
    except OSError as exc:
        return (f"P6: cannot inspect the private socket directory: {exc}",)
    return socket_path_length(path)
