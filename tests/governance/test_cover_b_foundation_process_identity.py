# Copyright (c) 2026 agentctl contributors.
"""Process identity refusals with real Linux children and constructed OS facts."""

import os
import shutil
import time
from collections.abc import Callable, Generator
from contextlib import contextmanager
from pathlib import Path

import pytest

from agentctl import foundation_process_identity as identity
from agentctl.foundation import Err, Ok
from agentctl.foundation_process_identity import (
    WindowsProcessImage,
    _process_image_file,
    linux_birth,
    native_process_image,
    process_birth,
    registered_alive,
    windows_birth,
    windows_process_image,
)
from agentctl.foundation_process_values import SpawnError
from agentctl.process import Child, start, stop

pytestmark = pytest.mark.evidence("value")

DEAD_PID = 2**31 - 1
WINDOWS_PID = 4242
BIRTH = 77
CHANGED_BIRTH = 78
HANDLE = 5
INVALID_PID_ERROR = 87
DENIED_ERROR = 5
EXECUTABLE = 0o755
SLEEP_SECONDS = "30"
EXEC_SECONDS = 5.0
POLL_SECONDS = 0.01
FAILED = Err(SpawnError("injected failure"))


class _Function:
    """A foreign function stand-in that accepts prototypes and returns one value."""

    def __init__(self, result: object) -> None:
        """Retain the constructed result and the assignable prototype fields."""
        self.result = result
        self.argtypes: object = None
        self.restype: object = None

    def __call__(self, *_args: object) -> object:
        """Return the constructed foreign result."""
        return self.result


class _Kernel:
    """A constructed library exposing only the calls the observation makes."""

    def __init__(self, handle: object, query: int, times: int, code: int) -> None:
        """Choose the handle and each call's native success value."""
        self.OpenProcess = _Function(handle)
        self.QueryFullProcessImageNameW = _Function(query)
        self.GetProcessTimes = _Function(times)
        self.GetExitCodeProcess = _Function(code)
        self.WaitForSingleObject = _Function(0)
        self.CloseHandle = _Function(1)


def _library(kernel: _Kernel) -> Callable[..., _Kernel]:
    """Return a loader that serves the constructed library."""

    def load(*_args: object, **_kwargs: object) -> _Kernel:
        return kernel

    return load


def _last_error(code: int) -> Callable[[], int]:
    """Return a Windows-style last-error accessor."""

    def read() -> int:
        return code

    return read


def _after_file(
    patch: pytest.MonkeyPatch, name: str, replacement: object
) -> Callable[[Path, Path], object]:
    """Observe the real image file, then change a later observation."""

    def wrapper(image: Path, executable: Path) -> object:
        observed = _process_image_file(image, executable)
        patch.setattr(identity, name, replacement)
        return observed

    return wrapper


def _copy_of_sleep(tmp_path: Path, name: str, mode: int) -> Path:
    """Copy a native executable into private storage with the chosen mode."""
    source = shutil.which("sleep")
    assert source is not None
    target = tmp_path / name
    shutil.copy2(source, target)
    target.chmod(mode)
    return target


def _await_exec(pid: int, program: Path) -> None:
    """Wait until the child's native image is the requested program."""
    deadline = time.monotonic() + EXEC_SECONDS
    link = Path("/proc") / str(pid) / "exe"
    while time.monotonic() < deadline and link.resolve() != program.resolve():
        time.sleep(POLL_SECONDS)
    assert link.resolve() == program.resolve()


@contextmanager
def _running(program: Path, cwd: Path) -> Generator[Child]:
    """Run one owned child and always stop it."""
    launched = start([str(program), SLEEP_SECONDS], cwd=cwd, env=os.environ)
    assert isinstance(launched, Ok)
    try:
        _await_exec(launched.value.pid, program)
        yield launched.value
    finally:
        assert isinstance(stop(launched.value), Ok)


def test_linux_image_observes_an_exact_child_and_refuses_unreadable_ones(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A readable image is bound to its child; failed reads or deletion refuse."""
    readable = _copy_of_sleep(tmp_path, "readable", EXECUTABLE)
    with _running(readable, tmp_path) as child:
        observed = native_process_image("Linux", child.pid)
        assert isinstance(observed, Ok)
        assert observed.value.image == readable.resolve()
    with _running(readable, tmp_path) as child, monkeypatch.context() as patch:
        patch.setattr(identity, "_process_image_file", lambda *_args: FAILED)
        assert native_process_image("Linux", child.pid) == FAILED
    gone = _copy_of_sleep(tmp_path, "gone", EXECUTABLE)
    with _running(gone, tmp_path) as child:
        gone.unlink()
        vanished = native_process_image("Linux", child.pid)
        assert isinstance(vanished, Err)
        assert vanished.error.message.startswith("cannot observe Linux process image: ")


def test_linux_image_refuses_dead_and_invalid_processes() -> None:
    """Exited, non-positive and foreign-family processes have no image."""
    assert native_process_image("Linux", DEAD_PID) == Err(
        SpawnError("process image is no longer live")
    )
    assert native_process_image("Linux", 0) == Err(
        SpawnError("process image requires a positive PID")
    )
    assert native_process_image("Linux", pid=True) == Err(
        SpawnError("process image requires a positive PID")
    )
    assert native_process_image("Windows", 1) == Err(
        SpawnError("native process image unavailable on this host")
    )


def test_linux_image_refuses_birth_failures_and_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A birth read that fails or changes after the file read is refused."""
    program = _copy_of_sleep(tmp_path, "racing", EXECUTABLE)
    with _running(program, tmp_path) as child:
        with monkeypatch.context() as patch:
            patch.setattr(
                identity,
                "_process_image_file",
                _after_file(patch, "linux_birth", lambda _pid: FAILED),
            )
            assert native_process_image("Linux", child.pid) == FAILED
        with monkeypatch.context() as patch:
            patch.setattr(
                identity,
                "_process_image_file",
                _after_file(patch, "linux_birth", lambda _pid: Ok(BIRTH)),
            )
            assert native_process_image("Linux", child.pid) == Err(
                SpawnError("Linux process changed during image observation")
            )


def test_linux_birth_refusals(monkeypatch: pytest.MonkeyPatch) -> None:
    """Invalid pids, unreadable stat and liveness failures are structured."""
    assert isinstance(linux_birth(0), Err)
    with monkeypatch.context() as patch:
        patch.setattr(identity, "alive", lambda *_args: FAILED)
        assert linux_birth(DEAD_PID) == FAILED
    with monkeypatch.context() as patch:
        patch.setattr(identity, "alive", lambda *_args: Ok(value=True))
        assert linux_birth(DEAD_PID) == Err(
            SpawnError("live Linux process has no visible stat")
        )
    target = Path("/proc") / str(os.getpid()) / "stat"
    original = Path.read_bytes

    def denied(self: Path) -> bytes:
        if self == target:
            message = "denied"
            raise PermissionError(message)
        return original(self)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "read_bytes", denied)
        assert linux_birth(os.getpid()) == Err(SpawnError("denied"))


def test_linux_image_propagates_initial_birth_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed first birth read is returned before any image is read."""
    with monkeypatch.context() as patch:
        patch.setattr(identity, "linux_birth", lambda _pid: FAILED)
        assert native_process_image("Linux", os.getpid()) == FAILED


def test_registered_identity_distinguishes_reused_pids() -> None:
    """A matching birth is alive; a different birth is a reused pid."""
    current = process_birth("Linux", os.getpid())
    assert isinstance(current, Ok)
    assert current.value is not None
    assert registered_alive("Linux", os.getpid(), current.value) == Ok(value=True)
    assert registered_alive("Linux", os.getpid(), current.value + 1) == Ok(value=False)
    assert registered_alive("Linux", os.getpid(), 0) == Err(
        SpawnError("invalid registered process identity")
    )


def test_foreign_family_identity_is_unavailable() -> None:
    """Another family has no creation identity and a registered one cannot match."""
    unavailable = Err(SpawnError("process creation identity unavailable on this host"))
    assert process_birth("Darwin", 1) == unavailable
    assert registered_alive("Darwin", 1, BIRTH) == unavailable


def test_windows_birth_refusals_over_a_constructed_library(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Handle, error and time results map to structured values."""
    assert isinstance(windows_birth(WINDOWS_PID), Err)
    assert isinstance(windows_birth(0), Err)
    with monkeypatch.context() as patch:
        patch.setattr(identity.sys, "platform", "win32")
        assert isinstance(windows_birth(WINDOWS_PID), Err)
        patch.setattr(identity.ctypes, "CDLL", _library(_Kernel(None, 1, 1, 1)))
        assert windows_birth(WINDOWS_PID) == Err(
            SpawnError("Windows error accessor is unavailable")
        )
        patch.setattr(
            identity.ctypes,
            "get_last_error",
            _last_error(INVALID_PID_ERROR),
            raising=False,
        )
        assert windows_birth(WINDOWS_PID) == Ok(None)
        patch.setattr(
            identity.ctypes, "get_last_error", _last_error(DENIED_ERROR), raising=False
        )
        assert windows_birth(WINDOWS_PID) == Err(
            SpawnError(f"OpenProcess failed: {DENIED_ERROR}")
        )
        patch.setattr(identity.ctypes, "CDLL", _library(_Kernel(HANDLE, 1, 0, 1)))
        assert windows_birth(WINDOWS_PID) == Err(SpawnError("GetProcessTimes failed"))
        patch.setattr(identity.ctypes, "CDLL", _library(_Kernel(HANDLE, 1, 1, 1)))
        assert windows_birth(WINDOWS_PID) == Ok(0)


def test_windows_image_refusals_over_a_constructed_library(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Library, handle and each native query failure are structured refusals."""
    assert isinstance(windows_process_image(WINDOWS_PID), Err)
    with monkeypatch.context() as patch:
        patch.setattr(identity.sys, "platform", "win32")
        assert isinstance(windows_process_image(WINDOWS_PID), Err)
        patch.setattr(identity.ctypes, "CDLL", _library(_Kernel(None, 1, 1, 1)))
        assert windows_process_image(WINDOWS_PID) == Err(
            SpawnError("cannot open process image handle")
        )
        for query, times, code, message in (
            (0, 1, 1, "cannot query process image path"),
            (1, 0, 1, "cannot query process image creation time"),
            (1, 1, 0, "cannot query process image liveness"),
            (1, 1, 1, "process image is not live or has invalid identity"),
        ):
            kernel = _Kernel(HANDLE, query, times, code)
            patch.setattr(identity.ctypes, "CDLL", _library(kernel))
            assert windows_process_image(WINDOWS_PID) == Err(SpawnError(message))


def test_windows_image_observation_over_constructed_images(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Each stage of the Windows image join refuses without a Windows kernel."""
    image = tmp_path / "image.exe"
    image.write_bytes(b"image")
    live = WindowsProcessImage(WINDOWS_PID, BIRTH, image)

    def observed(value: WindowsProcessImage) -> Callable[[int], object]:
        return lambda _pid: Ok(value)

    with monkeypatch.context() as patch:
        patch.setattr(identity.sys, "platform", "win32")
        patch.setattr(identity, "windows_process_image", lambda _pid: FAILED)
        assert native_process_image("Windows", WINDOWS_PID) == FAILED
        patch.setattr(
            identity,
            "windows_process_image",
            observed(WindowsProcessImage(WINDOWS_PID, BIRTH, tmp_path / "missing")),
        )
        missing = native_process_image("Windows", WINDOWS_PID)
        assert isinstance(missing, Err)
        assert missing.error.message.startswith("cannot resolve Windows process image")
        patch.setattr(
            identity,
            "windows_process_image",
            observed(WindowsProcessImage(WINDOWS_PID, BIRTH, tmp_path)),
        )
        directory = native_process_image("Windows", WINDOWS_PID)
        assert directory == Err(
            SpawnError("process image file does not match live image")
        )
        patch.setattr(identity, "windows_process_image", observed(live))
        stable = native_process_image("Windows", WINDOWS_PID)
        assert isinstance(stable, Ok)
        assert stable.value.birth == BIRTH

        patch.setattr(identity, "windows_process_image", observed(live))
        patch.setattr(
            identity,
            "_process_image_file",
            _after_file(patch, "windows_process_image", lambda _pid: FAILED),
        )
        assert native_process_image("Windows", WINDOWS_PID) == FAILED
        changed = WindowsProcessImage(WINDOWS_PID, CHANGED_BIRTH, image)
        patch.setattr(identity, "windows_process_image", observed(live))
        patch.setattr(
            identity,
            "_process_image_file",
            _after_file(patch, "windows_process_image", observed(changed)),
        )
        assert native_process_image("Windows", WINDOWS_PID) == Err(
            SpawnError("Windows process changed during image observation")
        )
