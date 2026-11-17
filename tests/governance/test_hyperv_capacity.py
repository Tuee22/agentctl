# Copyright (c) 2026 agentctl contributors.
"""Host capacity must be joined to the same Hyper-V VM and disks."""

from dataclasses import replace
from pathlib import Path

import pytest

from agentctl.check.hyperv_capacity import compare_virtual_sizes, join
from agentctl.check.hyperv_facts import VmFacts
from agentctl.check.hyperv_snapshot import Snapshot
from agentctl.check.hyperv_storage import DiskFile
from agentctl.check.wsl_budget import HostCapacity
from agentctl.check.wsl_vhd import VhdSize
from agentctl.foundation import Err, Ok

pytestmark = pytest.mark.evidence("value")
VM_ID = "4ba0db52-1f0c-498b-85e3-98f6c0cf0c39"
ROOT = Path(r"C:\owned")
DISK = ROOT / "vm.vhdx"
VM = VmFacts(
    "agentctl",
    VM_ID,
    "Running",
    2,
    4,
    8192,
    dynamic_memory=False,
    disk_paths=(str(DISK),),
    processor_limit=100,
    processor_reserve=0,
    disk_virtual_sizes=(100000,),
)
SNAPSHOT = Snapshot(VM, (DiskFile(DISK, 1, 2, 100),))
HOST = HostCapacity(8, 16000, 16000, 50000, 50000, shared_volume=True)


def test_capacity_refuses_mismatched_or_incomplete_native_disk_sizes() -> None:
    """A PowerShell size alone cannot substitute for an independent VHD query."""
    size = VhdSize(100000, 5000, 4096, 512)
    assert isinstance(compare_virtual_sizes((100000,), (size,)), Ok)
    assert isinstance(compare_virtual_sizes((100001,), (size,)), Err)
    assert isinstance(compare_virtual_sizes((100000,), ()), Err)
    assert isinstance(compare_virtual_sizes((100000,), (replace(size, sector=0),)), Err)


def test_capacity_requires_consistent_vm_and_complete_host_facts() -> None:
    """A host sample cannot authorize a different VM or unknown headroom."""

    def check(host: HostCapacity, second: Snapshot) -> object:
        return join(
            (SNAPSHOT, second), host, name="agentctl", identifier=VM_ID, disk_root=ROOT
        )

    assert isinstance(check(HOST, SNAPSHOT), Ok)
    assert isinstance(check(replace(HOST, commit_headroom=0), SNAPSHOT), Err)
    assert isinstance(check(replace(HOST, cpus=3), SNAPSHOT), Err)
    assert isinstance(check(HOST, replace(SNAPSHOT, vm=replace(VM, processors=5))), Err)
    assert isinstance(check(HOST, replace(SNAPSHOT, disks=())), Err)
