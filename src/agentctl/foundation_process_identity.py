# Copyright (c) 2026 agentctl contributors.
"""Native process identity observations shared by governance and runtime."""

import ctypes
import hashlib
import os
import stat
import sys
from pathlib import Path
from typing import NamedTuple, Protocol, runtime_checkable

from agentctl.check.process_identity import linux_birth_stat
from agentctl.foundation import Err, Family, Ok, Result
from agentctl.foundation_process_values import (
    ProcessImageFile,
    ProcessObservation,
    SpawnError,
)

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


WAIT_TIMEOUT = 258
SYNCHRONIZE = 0x00100000
WINDOWS_PATH_LIMIT = 32768


class WindowsProcessImage(NamedTuple):
    """One live Windows process's observed creation time and image path."""

    pid: int
    birth: int
    image: Path


def windows_process_image(pid: int) -> Result[WindowsProcessImage, SpawnError]:
    """Read a live process image and creation time through the same query handle.

    This is an observation of one handle, not proof that the path's current bytes
    are those mapped into the process or that the process remains live afterward.
    """
    if isinstance(pid, bool) or pid <= 0 or sys.platform != "win32":
        return Err(SpawnError("process image requires a positive Windows PID"))
    try:
        kernel = ctypes.CDLL("kernel32", use_last_error=True)
    except OSError as exc:
        return Err(SpawnError(str(exc)))
    kernel.OpenProcess.argtypes = (ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32)
    kernel.OpenProcess.restype = ctypes.c_void_p
    kernel.QueryFullProcessImageNameW.argtypes = (
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.POINTER(ctypes.c_wchar),
        ctypes.POINTER(ctypes.c_uint32),
    )
    kernel.QueryFullProcessImageNameW.restype = ctypes.c_int
    kernel.GetProcessTimes.argtypes = (
        ctypes.c_void_p,
        ctypes.POINTER(_FileTime),
        ctypes.POINTER(_FileTime),
        ctypes.POINTER(_FileTime),
        ctypes.POINTER(_FileTime),
    )
    kernel.GetProcessTimes.restype = ctypes.c_int
    kernel.GetExitCodeProcess.argtypes = (
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_uint32),
    )
    kernel.GetExitCodeProcess.restype = ctypes.c_int
    kernel.WaitForSingleObject.argtypes = (ctypes.c_void_p, ctypes.c_uint32)
    kernel.WaitForSingleObject.restype = ctypes.c_uint32
    kernel.CloseHandle.argtypes = (ctypes.c_void_p,)
    kernel.CloseHandle.restype = ctypes.c_int
    handle: object = kernel.OpenProcess(PROCESS_QUERY | SYNCHRONIZE, 0, pid)
    if not isinstance(handle, int):
        return Err(SpawnError("cannot open process image handle"))
    try:
        return _image_from_handle(kernel, handle, pid)
    finally:
        kernel.CloseHandle(handle)


def _image_from_handle(
    kernel: ctypes.CDLL, handle: int, pid: int
) -> Result[WindowsProcessImage, SpawnError]:
    """Read the path, creation time and liveness from one already-open handle."""
    creation, exit_time, kernel_time, user_time = (_FileTime() for _ in range(4))
    buffer = ctypes.create_unicode_buffer(WINDOWS_PATH_LIMIT)
    length = ctypes.c_uint32(len(buffer))
    status = ctypes.c_uint32()
    if not kernel.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(length)):
        return Err(SpawnError("cannot query process image path"))
    if not kernel.GetProcessTimes(
        handle,
        ctypes.byref(creation),
        ctypes.byref(exit_time),
        ctypes.byref(kernel_time),
        ctypes.byref(user_time),
    ):
        return Err(SpawnError("cannot query process image creation time"))
    if not kernel.GetExitCodeProcess(handle, ctypes.byref(status)):
        return Err(SpawnError("cannot query process image liveness"))
    birth = (creation.high << 32) | creation.low
    image = Path(buffer.value)
    wait = kernel.WaitForSingleObject(handle, 0)
    return checked_windows_image(pid, birth, image, status.value, wait)


def checked_windows_image(
    pid: int, birth: int, image: Path, status: int, wait: int
) -> Result[WindowsProcessImage, SpawnError]:
    """Validate supplied process-image facts without asserting their provenance."""
    if (
        isinstance(pid, bool)
        or isinstance(birth, bool)
        or isinstance(status, bool)
        or isinstance(wait, bool)
        or pid <= 0
        or status != STILL_ACTIVE
        or wait != WAIT_TIMEOUT
        or birth <= 0
        or not image.is_absolute()
    ):
        return Err(SpawnError("process image is not live or has invalid identity"))
    return Ok(WindowsProcessImage(pid, birth, image))


def linux_birth(pid: int) -> Result[int | None, SpawnError]:
    """Read a Linux process's native start ticks, or None after it has exited."""
    if pid <= 0 or sys.platform != "linux":
        return Err(SpawnError("Linux process identity requires a positive Linux PID"))
    try:
        data = (Path("/proc") / str(pid) / "stat").read_bytes()
    except (FileNotFoundError, ProcessLookupError):
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


def native_process_image(
    family: Family, pid: int
) -> Result[ProcessObservation, SpawnError]:
    """Observe one live process image and retain its native creation identity."""
    if isinstance(pid, bool) or pid <= 0:
        return Err(SpawnError("process image requires a positive PID"))
    if family == "Linux" and sys.platform == "linux":
        return _linux_process_image(pid)
    if family == "Windows" and sys.platform == "win32":
        return _windows_process_image(pid)
    return Err(SpawnError("native process image unavailable on this host"))


def _linux_process_image(pid: int) -> Result[ProcessObservation, SpawnError]:
    before = linux_birth(pid)
    if isinstance(before, Err):
        return before
    if before.value is None:
        return Err(SpawnError("process image is no longer live"))
    try:
        executable = Path("/proc") / str(pid) / "exe"
        image = executable.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        return Err(SpawnError("cannot observe Linux process image: " + str(exc)))
    observed = _process_image_file(image, executable)
    if isinstance(observed, Err):
        return observed
    after = linux_birth(pid)
    if isinstance(after, Err):
        return after
    return (
        Ok(ProcessObservation("Linux", pid, before.value, image, observed.value))
        if after == before
        else Err(SpawnError("Linux process changed during image observation"))
    )


def _windows_process_image(pid: int) -> Result[ProcessObservation, SpawnError]:
    before = windows_process_image(pid)
    if isinstance(before, Err):
        return before
    try:
        image = before.value.image.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        return Err(SpawnError("cannot resolve Windows process image: " + str(exc)))
    observed = _process_image_file(image, image)
    if isinstance(observed, Err):
        return observed
    after = windows_process_image(pid)
    if isinstance(after, Err):
        return after
    return (
        Ok(
            ProcessObservation(
                "Windows", pid, before.value.birth, image, observed.value
            )
        )
        if after == before
        else Err(SpawnError("Windows process changed during image observation"))
    )


def _process_file_facts(info: os.stat_result) -> tuple[int, int, int, int]:
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)


def _process_image_file(
    image: Path, executable: Path
) -> Result[ProcessImageFile, SpawnError]:
    """Bind stable file bytes to the live image path while the child is held."""
    try:
        before = image.stat()
        if not stat.S_ISREG(before.st_mode) or not image.samefile(executable):
            return Err(SpawnError("process image file does not match live image"))
        with image.open("rb") as stream:
            opened = os.fstat(stream.fileno())
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
            stream.seek(0)
            repeated = hashlib.file_digest(stream, "sha256").hexdigest()
            closed = os.fstat(stream.fileno())
        after = image.stat()
        if (
            digest != repeated
            or before.st_ctime_ns != after.st_ctime_ns
            or opened.st_ctime_ns != closed.st_ctime_ns
            or any(
                _process_file_facts(item) != _process_file_facts(before)
                for item in (opened, closed, after)
            )
            or not image.samefile(executable)
        ):
            return Err(SpawnError("process image file changed during observation"))
    except (OSError, RuntimeError, ValueError) as exc:
        return Err(SpawnError("cannot observe process image file: " + str(exc)))
    return Ok(ProcessImageFile(*_process_file_facts(before), digest))


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
