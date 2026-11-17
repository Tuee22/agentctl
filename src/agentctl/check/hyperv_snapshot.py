# Copyright (c) 2026 agentctl contributors.
"""Bracket Hyper-V configuration with contained native disk observations."""

from dataclasses import dataclass
from pathlib import Path, PureWindowsPath

from agentctl.check import hyperv_facts, hyperv_observe, hyperv_storage
from agentctl.check.hyperv_facts import VmFacts
from agentctl.check.hyperv_storage import DiskFile
from agentctl.foundation import Err, Ok, Result


@dataclass(frozen=True, slots=True)
class Snapshot:
    """Two consistent observations, not a provisioning or workload receipt."""

    vm: VmFacts
    disks: tuple[DiskFile, ...]


def join(
    first: Snapshot,
    second: Snapshot,
    *,
    name: str,
    identifier: str,
    disk_root: str,
) -> Result[Snapshot, str]:
    """Refuse mismatched configuration, missing disks and replaced identities."""
    issues = hyperv_facts.problems(
        first.vm, name=name, identifier=identifier, disk_root=disk_root
    )
    if issues:
        return Err("invalid Hyper-V configuration: " + "; ".join(issues))
    if first.vm != second.vm:
        return Err("Hyper-V configuration changed during observation")
    expected = tuple(PureWindowsPath(path) for path in first.vm.disk_paths)
    first_paths = tuple(PureWindowsPath(str(disk.path)) for disk in first.disks)
    second_paths = tuple(PureWindowsPath(str(disk.path)) for disk in second.disks)
    if expected != first_paths or first_paths != second_paths:
        return Err("Hyper-V disk observations do not match the VM")
    before = tuple((disk.device, disk.inode) for disk in first.disks)
    after = tuple((disk.device, disk.inode) for disk in second.disks)
    if (
        not before
        or before != after
        or len(set(before)) != len(before)
        or any(
            isinstance(value, bool) or value <= 0
            for disk in (*first.disks, *second.disks)
            for value in (disk.device, disk.inode, disk.size)
        )
    ):
        return Err("Hyper-V disk identity changed during observation")
    return Ok(second)


def observe(
    identifier: str, *, name: str, disk_root: Path, cwd: Path
) -> Result[Snapshot, str]:
    """Sample VM and storage twice; failures remain diagnostic, never a receipt."""
    first = hyperv_observe.observe(identifier, cwd=cwd)
    if isinstance(first, Err):
        return first
    first_disks = hyperv_storage.inspect(
        tuple(map(Path, first.value.disk_paths)), root=disk_root
    )
    if isinstance(first_disks, Err):
        return first_disks
    second = hyperv_observe.observe(identifier, cwd=cwd)
    if isinstance(second, Err):
        return second
    second_disks = hyperv_storage.inspect(
        tuple(map(Path, second.value.disk_paths)), root=disk_root
    )
    if isinstance(second_disks, Err):
        return second_disks
    return join(
        Snapshot(first.value, first_disks.value),
        Snapshot(second.value, second_disks.value),
        name=name,
        identifier=identifier,
        disk_root=str(disk_root),
    )
