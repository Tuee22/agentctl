# Copyright (c) 2026 agentctl contributors.
"""Native process identity observations shared by governance and runtime."""

import ctypes
import os
import sys
from pathlib import Path
from typing import Protocol, runtime_checkable

from agentctl.check.process_identity import linux_birth_stat
from agentctl.foundation import Err, Family, Ok, Result
from agentctl.foundation_process_values import SpawnError

PROCESS_QUERY = 0x1000
INVALID_PID = 87
STILL_ACTIVE = 259


class _FileTime(ctypes.Structure):
    """Windows FILETIME, expressed in native 32-bit halves."""

    _fields_ = [("low", ctypes.c_uint32), ("high", ctypes.c_uint32)]
    low: int
    high: int


@runtime_checkable
class WindowsErrors(Protocol):
    """The Windows-only ctypes error accessor, checked at the OS boundary."""

    def get_last_error(self) -> int:
        """Read the thread error ctypes saved around its last foreign call."""
        ...


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


def windows_birth(pid: int) -> Result[int | None, SpawnError]:
    """Read Windows process creation identity, or None when the PID is absent."""
    if pid <= 0 or sys.platform != "win32":
        return Err(
            SpawnError("Windows process identity requires a positive Windows PID")
        )
    try:
        kernel = ctypes.CDLL("kernel32", use_last_error=True)
    except OSError as exc:
        return Err(SpawnError(str(exc)))
    kernel.OpenProcess.argtypes = (ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32)
    kernel.OpenProcess.restype = ctypes.c_void_p
    kernel.GetProcessTimes.argtypes = (
        ctypes.c_void_p,
        ctypes.POINTER(_FileTime),
        ctypes.POINTER(_FileTime),
        ctypes.POINTER(_FileTime),
        ctypes.POINTER(_FileTime),
    )
    kernel.GetProcessTimes.restype = ctypes.c_int
    kernel.CloseHandle.argtypes = (ctypes.c_void_p,)
    kernel.CloseHandle.restype = ctypes.c_int
    handle: object = kernel.OpenProcess(PROCESS_QUERY, 0, pid)
    if not isinstance(handle, int):
        if not isinstance(ctypes, WindowsErrors):
            return Err(SpawnError("Windows error accessor is unavailable"))
        error = ctypes.get_last_error()
        return (
            Ok(None)
            if error == INVALID_PID
            else Err(SpawnError(f"OpenProcess failed: {error}"))
        )
    creation, exit_time, kernel_time, user_time = (_FileTime() for _ in range(4))
    try:
        if not kernel.GetProcessTimes(
            handle,
            ctypes.byref(creation),
            ctypes.byref(exit_time),
            ctypes.byref(kernel_time),
            ctypes.byref(user_time),
        ):
            return Err(SpawnError("GetProcessTimes failed"))
        return Ok((creation.high << 32) | creation.low)
    finally:
        kernel.CloseHandle(handle)


def linux_birth(pid: int) -> Result[int | None, SpawnError]:
    """Read a Linux process's native start ticks, or None after it has exited."""
    if pid <= 0 or sys.platform != "linux":
        return Err(SpawnError("Linux process identity requires a positive Linux PID"))
    try:
        data = (Path("/proc") / str(pid) / "stat").read_bytes()
    except FileNotFoundError:
        state = alive("Linux", pid)
        if isinstance(state, Err):
            return state
        return (
            Err(SpawnError("live Linux process has no visible stat"))
            if state.value
            else Ok(None)
        )
    except OSError as exc:
        return Err(SpawnError(str(exc)))
    parsed = linux_birth_stat(data, pid)
    return (
        Err(SpawnError(parsed.error)) if isinstance(parsed, Err) else Ok(parsed.value)
    )


def process_birth(family: Family, pid: int) -> Result[int | None, SpawnError]:
    """Read native creation identity on supported hosts, never a foreign kernel."""
    if family == "Windows":
        return windows_birth(pid)
    if family == "Linux":
        return linux_birth(pid)
    return Err(SpawnError("process creation identity unavailable on this host"))


def registered_alive(
    family: Family, pid: int, birth: int | None
) -> Result[bool, SpawnError]:
    """Check a registered process without confusing a reused PID for its owner."""
    if birth is None:
        return alive(family, pid)
    if birth <= 0:
        return Err(SpawnError("invalid registered process identity"))
    current = process_birth(family, pid)
    if isinstance(current, Err):
        return current
    return alive(family, pid) if current.value == birth else Ok(value=False)
