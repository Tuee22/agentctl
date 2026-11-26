# Copyright (c) 2026 agentctl contributors.
"""Linux guest observation refusals when its kernel facts are absent or change."""

import os
from collections.abc import Callable
from pathlib import Path

import pytest

from agentctl.check import wsl_guest_sample
from agentctl.check.wsl_guest_sample import memory, observe
from agentctl.foundation import Err, Ok

pytestmark = pytest.mark.evidence("value")

MEMINFO = Path("/proc/meminfo")
STATUS = Path("/proc/self/status")
JUNK_MEMINFO = "MemTotal: 1 kB\n"
JUNK_STATUS = b"Name:\tx\n"
CHANGED_STATUS = b"Cpus_allowed_list:\t60000\n"
FRSIZE = 4096
BLOCKS = 100
AVAILABLE = 50
FILES = 10
NAMEMAX = 255


def _statvfs(inodes: int) -> os.statvfs_result:
    """Construct a native filesystem result with the chosen free inode count."""
    return os.statvfs_result(
        (
            FRSIZE,
            FRSIZE,
            BLOCKS,
            AVAILABLE,
            AVAILABLE,
            FILES,
            inodes,
            inodes,
            0,
            NAMEMAX,
        )
    )


def _text_for(
    original: Callable[..., str], target: Path, text: str
) -> Callable[..., str]:
    """Return a text reader that serves one path from a constructed record."""

    def read(self: Path, *args: str, **kwargs: str) -> str:
        return text if self == target else original(self, *args, **kwargs)

    return read


def _bytes_for(
    original: Callable[..., bytes], target: Path, data: bytes
) -> Callable[..., bytes]:
    """Return a byte reader that serves one path from a constructed record."""

    def read(self: Path, *args: str, **kwargs: str) -> bytes:
        return data if self == target else original(self, *args, **kwargs)

    return read


def test_memory_requires_swap_counter() -> None:
    """A meminfo record without SwapFree is refused by the swap counter."""
    result = memory("MemAvailable: 64 kB\n")
    assert result == Err("missing or ambiguous Linux memory counter: SwapFree")


def test_observe_refuses_non_directory_storage(tmp_path: Path) -> None:
    """A regular file is not workload storage."""
    storage = tmp_path / "file"
    storage.write_text("x", encoding="ascii")
    assert observe(storage) == Err("Linux workload storage is not a directory")


def test_observe_reports_initial_memory_and_affinity_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An unreadable first memory or affinity record fails the initial sample."""
    with monkeypatch.context() as patch:
        patch.setattr(
            Path, "read_text", _text_for(Path.read_text, MEMINFO, JUNK_MEMINFO)
        )
        memory_failure = observe(tmp_path)
    assert isinstance(memory_failure, Err)
    assert memory_failure.error.startswith("initial Linux observation: ")
    with monkeypatch.context() as patch:
        patch.setattr(
            Path, "read_bytes", _bytes_for(Path.read_bytes, STATUS, JUNK_STATUS)
        )
        affinity_failure = observe(tmp_path)
    assert isinstance(affinity_failure, Err)
    assert affinity_failure.error.startswith("initial Linux observation: ")


def test_observe_reports_final_observation_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Memory that becomes unreadable after the filesystem read is refused."""
    real = os.statvfs

    def statvfs_then_break(path: str | Path) -> os.statvfs_result:
        result = real(path)
        monkeypatch.setattr(
            Path, "read_text", _text_for(Path.read_text, MEMINFO, JUNK_MEMINFO)
        )
        return result

    with monkeypatch.context() as patch:
        patch.setattr(os, "statvfs", statvfs_then_break)
        failure = observe(tmp_path)
    assert isinstance(failure, Err)
    assert failure.error.startswith("final Linux observation: ")


def test_observe_refuses_changed_affinity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An affinity that changes between the two samples is refused."""
    real = os.statvfs

    def statvfs_then_change(path: str | Path) -> os.statvfs_result:
        result = real(path)
        monkeypatch.setattr(
            Path, "read_bytes", _bytes_for(Path.read_bytes, STATUS, CHANGED_STATUS)
        )
        return result

    with monkeypatch.context() as patch:
        patch.setattr(os, "statvfs", statvfs_then_change)
        failure = observe(tmp_path)
    assert failure == Err("Linux affinity or storage identity changed")


def test_observe_refuses_unavailable_filesystem_capacity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A filesystem with no free inodes is not usable capacity."""
    with monkeypatch.context() as patch:
        patch.setattr(os, "statvfs", lambda _path: _statvfs(0))
        failure = observe(tmp_path)
    assert failure == Err("Linux filesystem capacity is unavailable")
    with monkeypatch.context() as patch:
        patch.setattr(os, "statvfs", lambda _path: _statvfs(FILES))
        assert isinstance(observe(tmp_path), Ok)


def test_observe_requires_linux_and_statvfs_interface(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A foreign platform or a module without statvfs is refused."""
    with monkeypatch.context() as patch:
        patch.setattr(wsl_guest_sample.platform, "system", lambda: "Windows")
        assert observe(tmp_path) == Err("guest capacity observation requires Linux")
    with monkeypatch.context() as patch:
        patch.setattr(wsl_guest_sample, "import_module", lambda _name: object())
        assert observe(tmp_path) == Err("Linux statvfs interface unavailable")
