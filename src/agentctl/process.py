# Copyright (c) 2026 agentctl contributors.
"""The sole Python process creation boundary."""

import ctypes
import os
import subprocess
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

from agentctl.paths import Family
from agentctl.result import Err, Ok, Result

PROCESS_QUERY = 0x1000
INVALID_PID = 87
STILL_ACTIVE = 259


@runtime_checkable
class WindowsErrors(Protocol):
    """The Windows-only ctypes error accessor, checked at the OS boundary."""

    def get_last_error(self) -> int:
        """Read the thread error ctypes saved around its last foreign call."""
        ...


@dataclass(frozen=True, slots=True)
class Output:
    """Decoded output and exit status from one process."""

    code: int
    stdout: str
    stderr: str


@dataclass(frozen=True, slots=True)
class SpawnError:
    """A process could not start or finish within its deadline."""

    message: str


@dataclass(frozen=True, slots=True)
class Child:
    """An owned background process whose handle remains with its creator."""

    handle: subprocess.Popen[str]

    @property
    def pid(self) -> int:
        """Expose the operating-system pid observed after process creation."""
        return self.handle.pid


def run(
    argv: list[str],
    *,
    cwd: Path,
    env: Mapping[str, str],
    timeout: float = 600,
    input_text: str | None = None,
) -> Result[Output, SpawnError]:
    """Run an argv without a shell, decoding both streams as UTF-8."""
    try:
        child = subprocess.run(
            argv,
            cwd=cwd,
            env=env,
            timeout=timeout,
            check=False,
            capture_output=True,
            encoding="utf-8",
            input=input_text,
        )
    except (OSError, subprocess.TimeoutExpired, UnicodeError) as exc:
        return Err(SpawnError(str(exc)))
    return Ok(Output(child.returncode, child.stdout, child.stderr))


def start(
    argv: list[str], *, cwd: Path, env: Mapping[str, str]
) -> Result[Child, SpawnError]:
    """Start an owned observer process for explicit teardown by its caller."""
    try:
        handle = subprocess.Popen(
            argv,
            cwd=cwd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            encoding="utf-8",
        )
    except OSError as exc:
        return Err(SpawnError(str(exc)))
    return Ok(Child(handle))


def stop(child: Child) -> Result[Output, SpawnError]:
    """Terminate an owned child and reap it, bounding both waits."""
    try:
        if child.handle.poll() is None:
            child.handle.terminate()
        try:
            stdout, stderr = child.handle.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            child.handle.kill()
            stdout, stderr = child.handle.communicate(timeout=5)
        code = child.handle.wait(timeout=5)
    except (OSError, subprocess.TimeoutExpired, UnicodeError) as exc:
        return Err(SpawnError(str(exc)))
    return Ok(Output(code, stdout, stderr))


def alive(family: Family, pid: int) -> Result[bool, SpawnError]:
    """Read process liveness without signalling a Windows process."""
    if pid <= 0:
        return Err(SpawnError("observer pid must be positive"))
    probe = {"Windows": _windows_alive, "Linux": _posix_alive, "Darwin": _posix_alive}
    return probe[family](pid)


def _posix_alive(pid: int) -> Result[bool, SpawnError]:  # pragma: no cover
    """Query a POSIX pid without changing its state."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return Ok(value=False)
    except OSError as exc:
        return Err(SpawnError(str(exc)))
    return Ok(value=True)


def _windows_alive(pid: int) -> Result[bool, SpawnError]:  # pragma: no cover
    """Query a Windows handle; signal zero must never be used on Windows."""
    try:
        kernel = ctypes.CDLL("kernel32", use_last_error=True)
    except OSError as exc:
        return Err(SpawnError(str(exc)))
    kernel.OpenProcess.argtypes = (ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32)
    kernel.OpenProcess.restype = ctypes.c_void_p
    kernel.GetExitCodeProcess.argtypes = (
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_uint32),
    )
    kernel.GetExitCodeProcess.restype = ctypes.c_int
    kernel.CloseHandle.argtypes = (ctypes.c_void_p,)
    kernel.CloseHandle.restype = ctypes.c_int
    handle: object = kernel.OpenProcess(PROCESS_QUERY, 0, pid)
    if not isinstance(handle, int):
        if not isinstance(ctypes, WindowsErrors):
            return Err(SpawnError("Windows error accessor is unavailable"))
        error = ctypes.get_last_error()
        return (
            Ok(value=False)
            if error == INVALID_PID
            else Err(SpawnError(f"OpenProcess failed: {error}"))
        )
    status = ctypes.c_uint32()
    try:
        if not kernel.GetExitCodeProcess(handle, ctypes.byref(status)):
            return Err(SpawnError("GetExitCodeProcess failed"))
        return Ok(status.value == STILL_ACTIVE)
    finally:
        kernel.CloseHandle(handle)


def replace(argv: list[str], *, env: Mapping[str, str]) -> Result[int, SpawnError]:
    """Replace this process with inherited terminal handles and literal arguments."""
    try:
        os.execve(argv[0], argv, dict(env))
    except OSError as exc:
        return Err(SpawnError(str(exc)))


def foreground(
    argv: list[str], *, cwd: Path, env: Mapping[str, str]
) -> Result[int, SpawnError]:
    """Inherit the terminal and wait while the child handles console interrupts."""
    try:
        with (
            subprocess.Popen(argv, cwd=cwd, env=env) as child,
            ThreadPoolExecutor(max_workers=1) as waiter,
        ):
            status = waiter.submit(child.wait)
            while True:
                try:
                    return Ok(status.result())
                except KeyboardInterrupt:
                    continue
    except OSError as exc:
        return Err(SpawnError(str(exc)))
