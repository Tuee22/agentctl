# Copyright (c) 2026 agentctl contributors.
"""Mount observation refusals and the twice-read join over a constructed proc."""

import os
from collections.abc import Callable
from pathlib import Path

import pytest

from agentctl.check import wsl_mount
from agentctl.check.wsl_mount import (
    DeviceIdentity,
    _options,
    _twice,
    _visible,
    observe,
    validate,
)
from agentctl.foundation import Err, Ok

pytestmark = pytest.mark.evidence("value")

PROC_ID = 2
CHANGED_PROC_ID = 9
CGROUP_ID = 3
PATH = "/sys/fs/cgroup"
DEVICE = DeviceIdentity(0, 29, 22)
NO_PROC = "3 1 0:29 / /sys/fs/cgroup rw - cgroup2 cgroup rw\n"
SHORT_OPTIONS = "2 1 0:5 / /proc rw - proc proc\n"


class _Numbers:
    """The native device-number interface backed by the operating system."""

    def major(self, device: int) -> int:
        """Return the major device number."""
        return os.major(device)

    def minor(self, device: int) -> int:
        """Return the minor device number."""
        return os.minor(device)


def _mountinfo(directory: Path, cgroup: Path, proc_id: int, hidepid: str) -> str:
    """Describe a constructed proc and cgroup mount with the directory's device."""
    device = f"{os.major(directory.stat().st_dev)}:{os.minor(directory.stat().st_dev)}"
    return (
        f"{proc_id} 1 {device} / /proc rw - proc proc rw,hidepid={hidepid}\n"
        f"{CGROUP_ID} 1 {device} / {cgroup.as_posix()} rw - cgroup2 cgroup rw\n"
    )


def _rewriting_after(
    original: Callable[..., str], watched: Path, replacement: str
) -> Callable[..., str]:
    """Delegate a read, then change the watched file as a concurrent writer would."""

    def racing(self: Path, *args: str, **kwargs: str) -> str:
        text = original(self, *args, **kwargs)
        if self == watched:
            watched.write_text(replacement, encoding="utf-8")
        return text

    return racing


def _constructed(tmp_path: Path) -> tuple[Path, Path, Path]:
    """Create a constructed proc root, cgroup directory and mountinfo record."""
    proc = tmp_path / "proc"
    (proc / "self").mkdir(parents=True)
    cgroup = tmp_path / "cgroup"
    cgroup.mkdir()
    record = proc / "self" / "mountinfo"
    record.write_text(_mountinfo(proc, cgroup, PROC_ID, "0"), encoding="utf-8")
    return proc, cgroup, record


def test_options_and_visibility_refusals() -> None:
    """Missing or short option rows cannot establish proc visibility."""
    assert _options("", PROC_ID) == Err("mount options unavailable")
    assert _options(SHORT_OPTIONS, PROC_ID) == Err("invalid mount options")
    assert _visible("", PROC_ID) == Err("mount options unavailable")


def test_validate_refuses_absent_proc_mount() -> None:
    """A mountinfo without any mount containing /proc is unavailable."""
    assert validate(NO_PROC, PATH, DEVICE, DEVICE) == Err(
        "proc or cgroup mount unavailable"
    )


def test_twice_accepts_a_stable_constructed_proc(tmp_path: Path) -> None:
    """Two matching reads of constructed mount records join into one value."""
    proc, cgroup, _record = _constructed(tmp_path)
    result = _twice(proc, cgroup, _Numbers())
    assert isinstance(result, Ok)
    assert result.value.proc.identifier == PROC_ID
    assert result.value.cgroup.mountpoint == cgroup.as_posix()


def test_twice_refuses_unmounted_first_read(tmp_path: Path) -> None:
    """The first read must itself describe native mounts."""
    proc, cgroup, record = _constructed(tmp_path)
    record.write_text(NO_PROC, encoding="utf-8")
    assert _twice(proc, cgroup, _Numbers()) == Err("proc or cgroup mount unavailable")


def test_twice_refuses_a_second_read_that_hides_processes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A mount that starts hiding processes after the first read is refused."""
    proc, cgroup, record = _constructed(tmp_path)
    hidden = _mountinfo(proc, cgroup, PROC_ID, "2")
    with monkeypatch.context() as patch:
        patch.setattr(
            Path, "read_text", _rewriting_after(Path.read_text, record, hidden)
        )
        result = _twice(proc, cgroup, _Numbers())
    assert result == Err("proc mount hides process identities")


def test_twice_refuses_a_changed_mount_identifier(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A different mount identifier between reads is a changed mount."""
    proc, cgroup, record = _constructed(tmp_path)
    changed = _mountinfo(proc, cgroup, CHANGED_PROC_ID, "0")
    with monkeypatch.context() as patch:
        patch.setattr(
            Path, "read_text", _rewriting_after(Path.read_text, record, changed)
        )
        result = _twice(proc, cgroup, _Numbers())
    assert result == Err("proc or cgroup mount changed")


def test_observe_refuses_foreign_and_unmounted_roots(tmp_path: Path) -> None:
    """A plain directory is not a cgroup2 mount; a missing or linked root fails."""
    plain = observe(tmp_path.resolve())
    assert isinstance(plain, Err)
    missing = observe(tmp_path / "missing")
    assert isinstance(missing, Err)
    assert missing.error.startswith("cannot observe native cgroup mounts: ")
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)
    assert observe(link) == Err("cgroup mount path is not canonical")


def test_observe_requires_linux_and_device_interface(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A foreign platform or a module without device numbers is refused."""
    with monkeypatch.context() as patch:
        patch.setattr(wsl_mount.platform, "system", lambda: "Windows")
        assert observe(tmp_path) == Err("cgroup mount observation requires Linux")
    with monkeypatch.context() as patch:
        patch.setattr(wsl_mount, "import_module", lambda _name: object())
        assert observe(tmp_path) == Err("Linux device-number interface unavailable")
