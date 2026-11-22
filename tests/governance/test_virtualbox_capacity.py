# Copyright (c) 2026 agentctl contributors.
"""Host capacity joins remain bound to one stable VirtualBox disk inventory."""

from dataclasses import replace
from pathlib import Path

import pytest

from agentctl.check.hyperv_guest import GuestIdentity
from agentctl.check.virtualbox_capacity import (
    CapacityObservation,
    GuestCapacityJoin,
    join,
    join_guest,
)
from agentctl.check.virtualbox_guest_capacity import Observation, Request
from agentctl.check.virtualbox_inventory import InventoryObservation, Slot
from agentctl.check.virtualbox_observe import VmObservation
from agentctl.check.virtualbox_snapshot import Attachment
from agentctl.check.virtualbox_storage import DiskObservation, VdiHeader
from agentctl.check.wsl_budget import HostCapacity
from agentctl.check.wsl_guest_sample import GuestReading
from agentctl.foundation import Err, Ok

pytestmark = pytest.mark.evidence("value")
VM_ID = "9d7dc4eb-c2b5-4044-8bf1-8d8a6c684df8"
DISK_ID = "20cef611-e035-4fd5-a514-5dcd57efce64"


def test_capacity_requires_stable_inventory_and_complete_host_facts(
    tmp_path: Path,
) -> None:
    """Point-in-time free memory already reflects an active VM, not a new allocation."""
    path = tmp_path / "disk.vdi"
    path.write_bytes(b"sample")
    facts = path.stat()
    vm = VmObservation("owned", VM_ID, "config", 12288, 4, 100, "running")
    medium = Attachment(str(path), DISK_ID)
    header = VdiHeader(DISK_ID, 1024, 512, 2, 512)
    disk = DiskObservation(path.resolve(), facts.st_dev, facts.st_ino, 6, header)
    sample = InventoryObservation(vm, (Slot("SATA", 0, medium),), (disk,))
    host = HostCapacity(8, 1, 1, 50000, 50000, shared_volume=True)
    assert join(sample, host, sample, name="owned") == Ok(
        CapacityObservation(sample, host)
    )
    assert isinstance(join(sample, replace(host, cpus=3), sample, name="owned"), Err), (
        "insufficient host CPUs were accepted"
    )
    assert isinstance(
        join(sample, replace(host, available_memory=0), sample, name="owned"), Err
    ), "missing host memory was accepted"
    changed = replace(sample, vm=replace(vm, cpus=5))
    assert isinstance(join(sample, host, changed, name="owned"), Err), (
        "changed VM inventory was accepted"
    )
    for bad in (
        replace(host, cpus=True),
        replace(host, commit_headroom=0),
        replace(host, vhd_free=0),
        replace(host, source_free=0),
    ):
        assert isinstance(join(sample, bad, sample, name="owned"), Err)
    stopped = replace(sample, vm=replace(vm, state="poweroff"))
    assert isinstance(join(stopped, host, stopped, name="owned"), Err)


def test_guest_capacity_join_refuses_mismatched_or_impossible_values(
    tmp_path: Path,
) -> None:
    """Fresh guest values must fit both stable host and configured VM observations."""
    path = tmp_path / "disk.vdi"
    path.write_bytes(b"sample")
    facts = path.stat()
    vm = VmObservation("owned", VM_ID, "config", 4096, 4, 100, "running")
    disk = DiskObservation(
        path.resolve(),
        facts.st_dev,
        facts.st_ino,
        6,
        VdiHeader(DISK_ID, 16384, 512, 32, 512),
    )
    inventory = InventoryObservation(
        vm, (Slot("SATA", 0, Attachment(str(path), DISK_ID)),), (disk,)
    )
    first = CapacityObservation(
        inventory, HostCapacity(8, 100, 100, 50000, 50000, shared_volume=True)
    )
    second = replace(first, host=replace(first.host, available_memory=80))
    request = Request("a" * 32, "/home/agentctl/state")
    identity = GuestIdentity(
        "Linux", "6.12", "innotek GmbH", "VirtualBox", "ID=debian\n", "1" * 32, 1000
    )
    reading = GuestReading((0, 1), 4096, 0, 10000, 6000, 500)
    guest = Observation(request, identity, reading)
    assert join_guest(first, guest, second, request, name="owned") == Ok(
        GuestCapacityJoin(first, guest, second)
    )
    assert isinstance(
        join_guest(
            first, guest, second, replace(request, nonce="b" * 32), name="owned"
        ),
        Err,
    ), "foreign guest request was accepted"
    assert isinstance(
        join_guest(
            first,
            replace(guest, reading=replace(reading, affinity=(0, 1, 2, 3, 4))),
            second,
            request,
            name="owned",
        ),
        Err,
    ), "excess guest CPU affinity was accepted"
    assert isinstance(
        join_guest(
            first,
            replace(
                guest, reading=replace(reading, available_memory=4096 * 1024 * 1024 + 1)
            ),
            second,
            request,
            name="owned",
        ),
        Err,
    ), "excess guest memory was accepted"
    assert isinstance(
        join_guest(
            first,
            replace(guest, reading=replace(reading, volume_size=16385)),
            second,
            request,
            name="owned",
        ),
        Err,
    ), "excess guest filesystem size was accepted"
    assert isinstance(
        join_guest(
            first,
            guest,
            replace(second, host=replace(second.host, cpus=9)),
            request,
            name="owned",
        ),
        Err,
    ), "changed host CPU count was accepted"
