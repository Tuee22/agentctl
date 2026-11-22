# Copyright (c) 2026 agentctl contributors.
"""Read Hyper-V configuration without asserting its provenance or readiness."""

import ctypes
import hashlib
import json
import os
import platform
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from agentctl.check.hyperv_facts import VmFacts
from agentctl.foundation import Err, Ok, Result
from agentctl.foundation_process import run

SCRIPT = r"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$vm = Get-VM -Id ([guid]$env:AGENTCTL_HYPERV_OBSERVE_ID)
$processor = Get-VMProcessor -VM $vm
if ($processor.Count -ne $vm.ProcessorCount) { throw 'VM processor count changed' }
$disks = @()
$sizes = @()
$seen = [System.Collections.Generic.HashSet[string]]::new(
    [StringComparer]::OrdinalIgnoreCase)
foreach ($attachment in @(Get-VMHardDiskDrive -VM $vm)) {
    $path = $attachment.Path
    $depth = 0
    while ($path) {
        $depth++
        if ($depth -gt 32 -or -not $seen.Add($path)) {
            throw 'Invalid or repeated VHD ancestry'
        }
        $disk = Get-VHD -Path $path
        if ($disk.Path -ne $path) { throw 'VHD path changed during observation' }
        $disks += $disk.Path
        $sizes += $disk.Size
        if ($disk.VhdType.ToString() -eq 'Differencing') {
            if (-not $disk.ParentPath) { throw 'Differencing VHD has no parent' }
            $path = $disk.ParentPath
        } else {
            if ($disk.ParentPath) { throw 'Unexpected VHD parent' }
            $path = $null
        }
    }
}
$row = [pscustomobject]@{ name = $vm.Name; identifier = $vm.Id.ToString();
    state = $vm.State.ToString(); generation = $vm.Generation;
    processors = $vm.ProcessorCount; startup_memory = $vm.MemoryStartup;
    dynamic_memory = $vm.DynamicMemoryEnabled; disk_paths = $disks;
    processor_limit = $processor.Maximum; processor_reserve = $processor.Reserve;
    disk_virtual_sizes = $sizes }
ConvertTo-Json -InputObject $row -Compress
"""
WINDOWS_PATH_LIMIT = 32768


@dataclass(frozen=True, slots=True)
class ExecutableIdentity:
    """One resolved executable's file identity and content digest."""

    path: Path
    device: int
    inode: int
    digest: str


def executable_identity(path: Path) -> Result[ExecutableIdentity, str]:
    """Observe bytes between file-identity checks without accepting a symlink."""
    try:
        if not path.is_absolute() or path.is_symlink() or not path.is_file():
            return Err("invalid Hyper-V observer executable")
        before = path.stat()
        resolved = path.resolve(strict=True)
        contents = path.read_bytes()
        after = path.stat()
        if (
            path.is_symlink()
            or before.st_dev != after.st_dev
            or before.st_ino != after.st_ino
            or before.st_size != after.st_size
            or after.st_ino <= 0
            or len(contents) != after.st_size
        ):
            return Err("Hyper-V observer executable changed during inspection")
        return Ok(
            ExecutableIdentity(
                resolved,
                after.st_dev,
                after.st_ino,
                hashlib.sha256(contents).hexdigest(),
            )
        )
    except (OSError, RuntimeError, ValueError) as exc:
        return Err("cannot inspect Hyper-V observer executable: " + str(exc))


def system_powershell() -> Result[Path, str]:
    """Resolve system PowerShell from the native Windows directory API, not PATH."""
    if platform.system() != "Windows":
        return Err("Hyper-V observation requires Windows")
    try:
        kernel = ctypes.CDLL("kernel32", use_last_error=True)
        function = kernel.GetSystemDirectoryW
        function.argtypes = (ctypes.POINTER(ctypes.c_wchar), ctypes.c_uint32)
        function.restype = ctypes.c_uint32
        buffer = ctypes.create_unicode_buffer(WINDOWS_PATH_LIMIT)
        length = function(buffer, len(buffer))
        if not length or length >= len(buffer):
            return Err("Windows system directory is unavailable")
        directory = Path(buffer.value)
        executable = directory / "WindowsPowerShell/v1.0/powershell.exe"
        if not directory.is_absolute() or not executable.is_file():
            return Err("Windows system PowerShell is unavailable")
        return Ok(executable)
    except (OSError, ValueError, AttributeError) as exc:
        return Err("Windows system PowerShell is unavailable: " + str(exc))


def _fields(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """Reject duplicate keys rather than silently accepting an ambiguous observation."""
    values = dict(pairs)
    if len(values) != len(pairs):
        message = "duplicate Hyper-V observation field"
        raise ValueError(message)
    return values


def parse(text: str) -> Result[VmFacts, str]:
    """Decode exactly one complete, typed VM configuration observation."""
    try:
        row: object = json.loads(text, object_pairs_hook=_fields)
    except (ValueError, UnicodeError) as exc:
        return Err("invalid Hyper-V observation: " + str(exc))
    match row:
        case {
            "name": str() as name,
            "identifier": str() as identifier,
            "state": str() as state,
            "generation": int() as generation,
            "processors": int() as processors,
            "startup_memory": int() as memory,
            "dynamic_memory": bool() as dynamic,
            "disk_paths": list() as paths,
            "processor_limit": int() as limit,
            "processor_reserve": int() as reserve,
            "disk_virtual_sizes": list() as sizes,
            **extra,
        } if (
            not extra
            and all(
                not isinstance(value, bool)
                for value in (generation, processors, memory, limit, reserve)
            )
            and all(isinstance(path, str) for path in paths)
            and all(
                isinstance(size, int) and not isinstance(size, bool) for size in sizes
            )
        ):
            return Ok(
                VmFacts(
                    name,
                    identifier,
                    state,
                    generation,
                    processors,
                    memory,
                    dynamic,
                    tuple(paths),
                    limit,
                    reserve,
                    tuple(sizes),
                )
            )
        case _:
            return Err("invalid Hyper-V observation fields")


def _invoke(executable: Path, identifier: str, cwd: Path) -> Result[VmFacts, str]:
    """Bracket one process execution with its executable's observed identity."""
    before = executable_identity(executable)
    if isinstance(before, Err):
        return before
    environment = {**os.environ, "AGENTCTL_HYPERV_OBSERVE_ID": identifier}
    outcome = run(
        [str(executable), "-NoProfile", "-NonInteractive", "-Command", SCRIPT],
        cwd=cwd,
        env=environment,
        timeout=30,
    )
    after = executable_identity(executable)
    if isinstance(after, Err) or after.value != before.value:
        primary = (
            outcome.error.message
            if isinstance(outcome, Err)
            else "exit " + str(outcome.value.code) + ": " + outcome.value.stderr
            if outcome.value.code
            else ""
        )
        return Err(
            ("Hyper-V observation failed: " + primary + "; " if primary else "")
            + "Hyper-V observer executable changed during execution"
        )
    if isinstance(outcome, Err):
        return Err("Hyper-V observation failed: " + outcome.error.message)
    if outcome.value.code != 0:
        return Err("Hyper-V observation failed: " + outcome.value.stderr)
    return parse(outcome.value.stdout)


def observe(identifier: str, *, cwd: Path) -> Result[VmFacts, str]:
    """Read one VM by UUID through the host's PowerShell Hyper-V interface."""
    if platform.system() != "Windows":
        return Err("Hyper-V observation requires Windows")
    try:
        normalized = str(UUID(identifier))
    except (ValueError, AttributeError, TypeError):
        return Err("invalid Hyper-V VM identifier")
    executable = system_powershell()
    return (
        executable
        if isinstance(executable, Err)
        else _invoke(executable.value, normalized, cwd)
    )
