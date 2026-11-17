# Copyright (c) 2026 agentctl contributors.
"""Read-only Windows capacity samples for a separately controlled WSL workload."""

import json
import os
import platform
import shutil
from dataclasses import dataclass
from pathlib import Path

from agentctl.check.wsl_budget import HostCapacity
from agentctl.foundation import Err, Ok, Result
from agentctl.foundation_process import run

COUNTER_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$samples = (Get-Counter '\Memory\Available Bytes', '\Memory\Committed Bytes',
                        '\Memory\Commit Limit').CounterSamples
$available = @($samples | Where-Object { $_.Path -like '*\memory\available bytes' })
$committed = @($samples | Where-Object { $_.Path -like '*\memory\committed bytes' })
$limit = @($samples | Where-Object { $_.Path -like '*\memory\commit limit' })
if ($available.Count -ne 1 -or $committed.Count -ne 1 -or $limit.Count -ne 1) {
    throw 'incomplete or ambiguous memory counters'
}
[pscustomobject]@{ available = [long]$available[0].CookedValue;
                  committed = [long]$committed[0].CookedValue;
                  limit = [long]$limit[0].CookedValue } | ConvertTo-Json -Compress
"""


@dataclass(frozen=True, slots=True)
class Counters:
    """One native physical-availability and system-commit observation."""

    available: int
    committed: int
    limit: int

    @property
    def headroom(self) -> int:
        """Return the observed difference, without assuming it stays constant."""
        return self.limit - self.committed


@dataclass(frozen=True, slots=True)
class _Volume:
    """Resolved directory identity and current free space on its volume."""

    path: Path
    device: int
    inode: int
    free: int


def _fields(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """Refuse ambiguous counter fields before interpreting them."""
    result = dict(pairs)
    if len(result) != len(pairs):
        message = "duplicate host counter field"
        raise ValueError(message)
    return result


def parse_counters(text: str) -> Result[Counters, str]:
    """Read exact byte counters and refuse impossible or ambiguous values."""
    try:
        value: object = json.loads(text, object_pairs_hook=_fields)
    except (ValueError, UnicodeError) as exc:
        return Err("invalid host counters: " + str(exc))
    match value:
        case {
            "available": int() as available,
            "committed": int() as committed,
            "limit": int() as limit,
            **extra,
        } if (
            not extra
            and all(
                not isinstance(item, bool) for item in (available, committed, limit)
            )
            and available >= 0
            and 0 <= committed <= limit
            and limit > 0
        ):
            return Ok(Counters(available, committed, limit))
        case _:
            return Err("invalid host counter values")


def _volume(path: Path) -> Result[_Volume, str]:
    """Read a real directory's identity and free bytes without changing it."""
    try:
        resolved = path.resolve(strict=True)
        if not resolved.is_dir():
            return Err("host volume path is not a directory")
        facts = resolved.stat()
        if facts.st_dev <= 0 or facts.st_ino <= 0:
            return Err("host volume identity unavailable")
        return Ok(
            _Volume(
                resolved, facts.st_dev, facts.st_ino, shutil.disk_usage(resolved).free
            )
        )
    except (OSError, RuntimeError) as exc:
        return Err("cannot inspect host volume: " + str(exc))


def _same_identity(first: _Volume, second: _Volume) -> bool:
    """Keep the same resolved directory and volume across a counter query."""
    return (first.path, first.device, first.inode) == (
        second.path,
        second.device,
        second.inode,
    )


def shared_volume(first_device: int, second_device: int) -> bool:
    """Classify two already observed native volume identities."""
    return first_device > 0 and second_device > 0 and first_device == second_device


def _counters(root: Path) -> Result[Counters, str]:
    """Query the native host through a fixed read-only PowerShell invocation."""
    windows = os.environ.get("SYSTEMROOT", "")
    executable = Path(windows) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    if not windows or not executable.is_file():
        return Err("Windows PowerShell unavailable")
    observed = run(
        [str(executable), "-NoProfile", "-NonInteractive", "-Command", COUNTER_SCRIPT],
        cwd=root,
        env=os.environ,
        timeout=30,
    )
    if isinstance(observed, Err):
        return Err("cannot observe host counters: " + observed.error.message)
    if observed.value.code != 0:
        return Err("cannot observe host counters: " + observed.value.stderr)
    return parse_counters(observed.value.stdout)


def _volumes(vhd: Path, source: Path) -> Result[tuple[_Volume, _Volume], str]:
    """Preserve the specific volume failure when observing the two paths."""
    first, second = _volume(vhd), _volume(source)
    if isinstance(first, Err):
        return Err("VHD volume: " + first.error)
    if isinstance(second, Err):
        return Err("source volume: " + second.error)
    return Ok((first.value, second.value))


def _observe(
    root: Path, vhd_directory: Path, source_directory: Path
) -> Result[HostCapacity, str]:
    """Join repeated volume identities to one native counter sample."""
    first = _volumes(vhd_directory, source_directory)
    if isinstance(first, Err):
        return first
    counters = _counters(root)
    if isinstance(counters, Err):
        return counters
    second = _volumes(vhd_directory, source_directory)
    if isinstance(second, Err):
        return second
    first_vhd, first_source = first.value
    second_vhd, second_source = second.value
    if not _same_identity(first_vhd, second_vhd) or not _same_identity(
        first_source, second_source
    ):
        return Err("host volume identity changed")
    cpus = os.cpu_count()
    if cpus is None or cpus <= 0:
        return Err("host logical CPU count unavailable")
    return Ok(
        HostCapacity(
            cpus,
            counters.value.available,
            counters.value.headroom,
            min(first_vhd.free, second_vhd.free),
            min(first_source.free, second_source.free),
            shared_volume(first_vhd.device, first_source.device),
        )
    )


def observe(
    root: Path, vhd_directory: Path, source_directory: Path
) -> Result[HostCapacity, str]:
    """Observe real Windows counters and both volumes without asserting readiness."""
    return (
        _observe(root, vhd_directory, source_directory)
        if platform.system() == "Windows"
        else Err("host capacity observation requires Windows")
    )
