# Copyright (c) 2026 agentctl contributors.
"""Combine native host and VHD observations without issuing a receipt."""

from dataclasses import dataclass, replace
from pathlib import Path

from agentctl.check import wsl_host_sample, wsl_vhd
from agentctl.check.wsl_budget import HostCapacity
from agentctl.check.wsl_registration import StorageObservation, inspect_storage
from agentctl.foundation import Err, Ok, Result


@dataclass(frozen=True, slots=True)
class HostVhdObservation:
    """A bracketed host sample and size, not authenticated provisioning evidence."""

    before: StorageObservation
    size: wsl_vhd.VhdSize
    host: HostCapacity
    after: StorageObservation


def join(
    before: StorageObservation,
    size: wsl_vhd.VhdSize,
    host: HostCapacity,
    after: StorageObservation,
) -> Result[HostVhdObservation, str]:
    """Require the same file identity and retain the lowest observed free space."""
    if (
        (before.base, before.vhd, before.device, before.inode)
        != (after.base, after.vhd, after.device, after.inode)
        or before.device <= 0
        or before.inode <= 0
    ):
        return Err("VHD identity changed during host observation")
    checked = wsl_vhd.checked_size(size.virtual, size.physical, size.block, size.sector)
    if isinstance(checked, Err):
        return checked
    if any(
        isinstance(value, bool) or value <= 0
        for value in (
            before.free_bytes,
            after.free_bytes,
            host.cpus,
            host.available_memory,
            host.commit_headroom,
            host.vhd_free,
            host.source_free,
        )
    ) or any(
        isinstance(value, bool) or value < 0
        for value in (before.file_bytes, after.file_bytes)
    ):
        return Err("incomplete host or storage observation")
    vhd_free = min(before.free_bytes, host.vhd_free, after.free_bytes)
    source_free = (
        min(host.source_free, vhd_free) if host.shared_volume else host.source_free
    )
    return Ok(
        HostVhdObservation(
            before,
            checked.value,
            replace(host, vhd_free=vhd_free, source_free=source_free),
            after,
        )
    )


def observe(
    root: Path, base: Path, owned_root: Path
) -> Result[HostVhdObservation, str]:
    """Observe one owned VHD around the native host capacity sample."""
    before = inspect_storage(base, owned_root)
    if isinstance(before, Err):
        return before
    size = wsl_vhd.observe(base, owned_root)
    if isinstance(size, Err):
        return size
    host = wsl_host_sample.observe(root, base, root)
    after = inspect_storage(base, owned_root)
    if isinstance(after, Err):
        return Err(
            (host.error + "; " if isinstance(host, Err) else "")
            + "VHD identity recheck failed: "
            + after.error
        )
    if isinstance(host, Err):
        identity = (
            before.value.base,
            before.value.vhd,
            before.value.device,
            before.value.inode,
        )
        final = (
            after.value.base,
            after.value.vhd,
            after.value.device,
            after.value.inode,
        )
        return Err(host.error + ("; VHD identity changed" if identity != final else ""))
    return join(before.value, size.value, host.value, after.value)
