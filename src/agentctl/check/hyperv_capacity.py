# Copyright (c) 2026 agentctl contributors.
"""Join host capacity to bracketed Hyper-V observations without issuing receipts."""

from dataclasses import dataclass
from pathlib import Path

from agentctl.check import hyperv_snapshot, hyperv_storage, wsl_host_sample
from agentctl.check.hyperv_snapshot import Snapshot
from agentctl.check.wsl_budget import HostCapacity
from agentctl.check.wsl_vhd import VhdSize, checked_size
from agentctl.foundation import Err, Ok, Result


@dataclass(frozen=True, slots=True)
class CapacityObservation:
    """A point-in-time host sample bracketed by a stable VM and disk identity."""

    snapshot: Snapshot
    host: HostCapacity


def compare_virtual_sizes(
    expected: tuple[int, ...], observed: tuple[VhdSize, ...]
) -> Result[None, str]:
    """Require every native VHD query to match its corresponding VM observation."""
    if not expected or len(expected) != len(observed):
        return Err("incomplete independent VHD size observations")
    for size, value in zip(observed, expected, strict=True):
        checked = checked_size(size.virtual, size.physical, size.block, size.sector)
        if isinstance(checked, Err) or isinstance(value, bool) or value != size.virtual:
            return Err("Hyper-V and native virtual disk sizes disagree")
    return Ok(None)


def join(
    snapshots: tuple[Snapshot, Snapshot],
    host: HostCapacity,
    *,
    name: str,
    identifier: str,
    disk_root: Path,
) -> Result[CapacityObservation, str]:
    """Reject changed VM state and incomplete resource facts, without sizing a run."""
    first, second = snapshots
    joined = hyperv_snapshot.join(
        first, second, name=name, identifier=identifier, disk_root=str(disk_root)
    )
    if isinstance(joined, Err):
        return joined
    values = (
        host.cpus,
        host.available_memory,
        host.commit_headroom,
        host.vhd_free,
        host.source_free,
    )
    if (
        any(isinstance(value, bool) or value <= 0 for value in values)
        or first.vm.processors > host.cpus
    ):
        return Err("incomplete or inconsistent host capacity observation")
    return Ok(CapacityObservation(joined.value, host))


def observe(
    identifier: str, *, name: str, disk_root: Path, source: Path
) -> Result[CapacityObservation, str]:
    """Bracket native host counters with repeated contained-VM snapshots."""
    first = hyperv_snapshot.observe(
        identifier, name=name, disk_root=disk_root, cwd=source
    )
    if isinstance(first, Err):
        return first
    sizes: tuple[VhdSize, ...] = ()
    for disk in first.value.disks:
        size = hyperv_storage.virtual_size(disk.path, root=disk_root)
        if isinstance(size, Err):
            return Err("independent VHD size observation failed: " + size.error)
        sizes += (size.value,)
    agreement = compare_virtual_sizes(first.value.vm.disk_virtual_sizes, sizes)
    if isinstance(agreement, Err):
        return agreement
    host = wsl_host_sample.observe(source, disk_root, source)
    second = hyperv_snapshot.observe(
        identifier, name=name, disk_root=disk_root, cwd=source
    )
    if isinstance(second, Err):
        return Err(
            (host.error + "; " if isinstance(host, Err) else "")
            + "Hyper-V recheck failed: "
            + second.error
        )
    if isinstance(host, Err):
        identity = hyperv_snapshot.join(
            first.value,
            second.value,
            name=name,
            identifier=identifier,
            disk_root=str(disk_root),
        )
        return Err(
            host.error + ("; " + identity.error if isinstance(identity, Err) else "")
        )
    return join(
        (first.value, second.value),
        host.value,
        name=name,
        identifier=identifier,
        disk_root=disk_root,
    )
