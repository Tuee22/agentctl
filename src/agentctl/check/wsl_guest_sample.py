# Copyright (c) 2026 agentctl contributors.
"""Read Linux memory, affinity and storage without claiming WSL provenance."""

import platform
import re
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from typing import Protocol, runtime_checkable

from agentctl.check.wsl_budget import GuestCapacity
from agentctl.check.wsl_cgroup import cpu_list, status_affinity
from agentctl.foundation import Err, Ok, Result

KIBIBYTE = 1024
MAX_COUNTER_DIGITS = 20
MAX_COUNTER = (2**64 - 1) // KIBIBYTE


@dataclass(frozen=True, slots=True)
class MemoryReading:
    """Available RAM and swap read directly from one Linux meminfo record."""

    available: int
    swap_free: int


@dataclass(frozen=True, slots=True)
class GuestReading:
    """A local Linux observation before any independent VHD-capacity join."""

    affinity: tuple[int, ...]
    available_memory: int
    available_swap: int
    volume_size: int
    volume_free: int
    free_inodes: int


class _Stat(Protocol):
    """The finite filesystem fields returned by Linux statvfs."""

    f_frsize: int
    f_blocks: int
    f_bavail: int
    f_favail: int


@runtime_checkable
class _Statvfs(Protocol):
    """The Linux-only filesystem capacity adapter."""

    def statvfs(self, path: Path) -> _Stat:
        """Read native filesystem allocation facts."""
        ...


def _field(text: str, name: str) -> Result[int, str]:
    """Parse one bounded, uniquely present Linux memory counter."""
    values = re.findall(
        r"(?m)^" + re.escape(name) + r":[ \t]*([0-9]+)[ \t]+kB[ \t]*$", text
    )
    if len(values) != 1 or len(values[0]) > MAX_COUNTER_DIGITS:
        return Err("missing or ambiguous Linux memory counter: " + name)
    amount = int(values[0])
    return (
        Ok(amount * KIBIBYTE)
        if amount <= MAX_COUNTER
        else Err("Linux memory counter overflow: " + name)
    )


def memory(text: str) -> Result[MemoryReading, str]:
    """Read exact Linux meminfo keys, reject duplicates and convert KiB to bytes."""
    available, swap = _field(text, "MemAvailable"), _field(text, "SwapFree")
    if isinstance(available, Err):
        return available
    if isinstance(swap, Err):
        return swap
    if available.value <= 0:
        return Err("Linux available memory is zero")
    return Ok(MemoryReading(available.value, swap.value))


def affinity(text: str) -> Result[tuple[int, ...], str]:
    """Read exactly one effective CPU list from Linux process status."""
    values = tuple(
        line.partition(":")[2].strip()
        for line in text.splitlines()
        if line.startswith("Cpus_allowed_list:")
    )
    if len(values) != 1:
        return Err("Linux process affinity unavailable")
    parsed = cpu_list(values[0])
    return parsed if isinstance(parsed, Err) else Ok(tuple(sorted(parsed.value)))


def affinity_bytes(data: bytes) -> Result[tuple[int, ...], str]:
    """Decode only the ASCII affinity rows, not unrelated process-name bytes."""
    parsed = status_affinity(data)
    return parsed if isinstance(parsed, Err) else Ok(tuple(sorted(parsed.value)))


def valid_reading(reading: GuestReading) -> bool:
    """Require complete guest facts without inventing a VHD maximum."""
    return not (
        not reading.affinity
        or len(set(reading.affinity)) != len(reading.affinity)
        or any(isinstance(cpu, bool) or cpu < 0 for cpu in reading.affinity)
        or reading.available_memory <= 0
        or reading.available_swap < 0
        or reading.volume_size <= 0
        or not 0 <= reading.volume_free <= reading.volume_size
        or reading.free_inodes <= 0
        or any(
            isinstance(value, bool)
            for value in (
                reading.available_memory,
                reading.available_swap,
                reading.volume_size,
                reading.volume_free,
                reading.free_inodes,
            )
        )
    )


def capacity(reading: GuestReading, vhd_maximum: int) -> Result[GuestCapacity, str]:
    """Join an independently observed VHD maximum without authenticating it."""
    if (
        isinstance(vhd_maximum, bool)
        or vhd_maximum <= 0
        or not valid_reading(reading)
        or reading.volume_size > vhd_maximum
    ):
        return Err("invalid guest or VHD capacity")
    return Ok(
        GuestCapacity(
            reading.affinity,
            reading.available_memory,
            reading.available_swap,
            reading.volume_size,
            reading.volume_free,
            reading.free_inodes,
            vhd_maximum,
        )
    )


def _inputs() -> Result[tuple[MemoryReading, tuple[int, ...]], str]:
    """Preserve the specific failure of either process or memory observation."""
    observed_memory = memory(Path("/proc/meminfo").read_text(encoding="ascii"))
    if isinstance(observed_memory, Err):
        return observed_memory
    observed_affinity = affinity_bytes(Path("/proc/self/status").read_bytes())
    if isinstance(observed_affinity, Err):
        return observed_affinity
    return Ok((observed_memory.value, observed_affinity.value))


def _reading(storage: Path, interface: _Statvfs) -> Result[GuestReading, str]:
    """Read memory, affinity and storage twice, retaining conservative free values."""
    before = _inputs()
    if isinstance(before, Err):
        return Err("initial Linux observation: " + before.error)
    directory = storage.resolve(strict=True)
    if not directory.is_dir():
        return Err("Linux workload storage is not a directory")
    identity = directory.stat()
    filesystem = interface.statvfs(directory)
    after = _inputs()
    if isinstance(after, Err):
        return Err("final Linux observation: " + after.error)
    final_filesystem = interface.statvfs(directory)
    final_identity = directory.stat()
    if (
        before.value[1] != after.value[1]
        or identity.st_ino <= 0
        or (identity.st_dev, identity.st_ino)
        != (final_identity.st_dev, final_identity.st_ino)
    ):
        return Err("Linux affinity or storage identity changed")
    if (
        filesystem.f_frsize <= 0
        or filesystem.f_blocks <= 0
        or filesystem.f_bavail < 0
        or filesystem.f_bavail > filesystem.f_blocks
        or filesystem.f_favail <= 0
        or final_filesystem.f_bavail < 0
        or final_filesystem.f_bavail > final_filesystem.f_blocks
        or final_filesystem.f_favail <= 0
        or (filesystem.f_frsize, filesystem.f_blocks)
        != (final_filesystem.f_frsize, final_filesystem.f_blocks)
    ):
        return Err("Linux filesystem capacity is unavailable")
    total = filesystem.f_blocks * filesystem.f_frsize
    free = min(filesystem.f_bavail, final_filesystem.f_bavail) * filesystem.f_frsize
    return Ok(
        GuestReading(
            before.value[1],
            min(before.value[0].available, after.value[0].available),
            min(before.value[0].swap_free, after.value[0].swap_free),
            total,
            free,
            min(filesystem.f_favail, final_filesystem.f_favail),
        )
    )


def observe(storage: Path) -> Result[GuestReading, str]:
    """Read actual Linux facts; caller authenticates host and storage provenance."""
    if platform.system() != "Linux":
        return Err("guest capacity observation requires Linux")
    interface: object = import_module("os")
    if not isinstance(interface, _Statvfs):
        return Err("Linux statvfs interface unavailable")
    try:
        return _reading(storage, interface)
    except (OSError, UnicodeError, RuntimeError, ValueError) as exc:
        return Err("cannot observe guest capacity: " + str(exc))
