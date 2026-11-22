# Copyright (c) 2026 agentctl contributors.
"""Join VirtualBox configuration and host capacity without issuing a receipt."""

from dataclasses import dataclass

from agentctl.check import (
    virtualbox_guest_capacity,
    virtualbox_inventory,
    wsl_host_sample,
)
from agentctl.check.virtualbox_inventory import InventoryObservation, InventoryRequest
from agentctl.check.wsl_budget import HostCapacity
from agentctl.foundation import Err, Ok, Result

MIB = 1024 * 1024


@dataclass(frozen=True, slots=True)
class CapacityObservation:
    """A point-in-time host sample bracketed by one VM and disk inventory."""

    inventory: InventoryObservation
    host: HostCapacity


@dataclass(frozen=True, slots=True)
class GuestCapacityJoin:
    """Numerically consistent samples, not proof of peer or storage provenance."""

    first: CapacityObservation
    guest: virtualbox_guest_capacity.Observation
    second: CapacityObservation


def join_guest(
    first: CapacityObservation,
    guest: virtualbox_guest_capacity.Observation,
    second: CapacityObservation,
    request: virtualbox_guest_capacity.Request,
    *,
    name: str,
) -> Result[GuestCapacityJoin, str]:
    """Compare bracketed host facts and guest values without authenticating either."""
    before = join(first.inventory, first.host, second.inventory, name=name)
    after = join(first.inventory, second.host, second.inventory, name=name)
    if isinstance(before, Err) or isinstance(after, Err):
        return Err("invalid or changed host capacity observations")
    checked = virtualbox_guest_capacity.join(
        request, guest.identity, guest.reading, guest.identity
    )
    if isinstance(checked, Err) or guest.request != request:
        return Err("invalid or mismatched guest capacity observation")
    capacities = tuple(disk.header.capacity for disk in first.inventory.disks)
    if (
        first.host.cpus != second.host.cpus
        or first.host.shared_volume != second.host.shared_volume
        or not capacities
        or any(isinstance(value, bool) or value <= 0 for value in capacities)
        or len(guest.reading.affinity) > first.inventory.vm.cpus
        or guest.reading.available_memory > first.inventory.vm.memory_mib * MIB
        or guest.reading.volume_size > sum(capacities)
    ):
        return Err("guest capacity is inconsistent with VM or host observations")
    return Ok(GuestCapacityJoin(first, guest, second))


def join(
    first: InventoryObservation,
    host: HostCapacity,
    second: InventoryObservation,
    *,
    name: str,
) -> Result[CapacityObservation, str]:
    """Refuse changed VM/disk facts and incomplete or inconsistent host facts."""
    stable = virtualbox_inventory.join(first, second, name)
    if isinstance(stable, Err):
        return stable
    values = (
        host.cpus,
        host.available_memory,
        host.commit_headroom,
        host.vhd_free,
        host.source_free,
    )
    if (
        any(isinstance(value, bool) or value <= 0 for value in values)
        or first.vm.cpus > host.cpus
        or first.vm.state != "running"
    ):
        return Err("incomplete or inconsistent VirtualBox host capacity")
    return Ok(CapacityObservation(stable.value, host))


def observe(request: InventoryRequest) -> Result[CapacityObservation, str]:
    """Bracket native host counters and free-space samples with VM observations."""
    first = virtualbox_inventory.observe(request)
    if isinstance(first, Err):
        return first
    host = wsl_host_sample.observe(request.cwd, request.root, request.cwd)
    second = virtualbox_inventory.observe(request)
    if isinstance(second, Err):
        return Err(
            (host.error + "; " if isinstance(host, Err) else "")
            + "VirtualBox inventory recheck failed: "
            + second.error
        )
    if isinstance(host, Err):
        stable = virtualbox_inventory.join(first.value, second.value, request.name)
        return Err(
            host.error + ("; " + stable.error if isinstance(stable, Err) else "")
        )
    return join(first.value, host.value, second.value, name=request.name)
