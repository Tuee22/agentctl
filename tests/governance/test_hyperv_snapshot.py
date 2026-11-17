# Copyright (c) 2026 agentctl contributors.
"""Independent checks for repeated Hyper-V and disk observations."""

from dataclasses import replace
from pathlib import Path

import pytest

from agentctl.check.hyperv_facts import VmFacts
from agentctl.check.hyperv_snapshot import Snapshot, join
from agentctl.check.hyperv_storage import DiskFile
from agentctl.foundation import Err, Ok

pytestmark = pytest.mark.evidence("value")
ID = "4ba0db52-1f0c-498b-85e3-98f6c0cf0c39"
ROOT = r"C:\owned"
PATH = ROOT + r"\vm.vhdx"
VM = VmFacts(
    "agentctl",
    ID,
    "Running",
    2,
    4,
    8192,
    dynamic_memory=False,
    disk_paths=(PATH,),
    processor_limit=100,
    processor_reserve=0,
    disk_virtual_sizes=(100000,),
)
DISK = DiskFile(Path(PATH), 42, 43, 100)


def test_join_rejects_changed_vm_or_disk_identity() -> None:
    """Disk growth is allowed; replacement, omission and changed configuration fail."""

    def check(second: VmFacts, disks: tuple[DiskFile, ...]) -> object:
        return join(
            Snapshot(VM, (DISK,)),
            Snapshot(second, disks),
            name="agentctl",
            identifier=ID,
            disk_root=ROOT,
        )

    assert isinstance(check(VM, (replace(DISK, size=200),)), Ok)
    assert isinstance(check(replace(VM, processors=8), (DISK,)), Err)
    assert isinstance(check(VM, (replace(DISK, inode=44),)), Err)
    assert isinstance(check(VM, (replace(DISK, size=0),)), Err)
    assert isinstance(check(VM, (replace(DISK, size=True),)), Err)
    assert isinstance(check(VM, ()), Err)
    assert isinstance(
        check(VM, (replace(DISK, path=Path(ROOT + r"\other.vhdx")),)), Err
    )
