# Copyright (c) 2026 agentctl contributors.
"""VM attachment observations must match a stable independent disk sample."""

import json
from dataclasses import replace
from pathlib import Path

import pytest

from agentctl.check.virtualbox_observe import VmObservation
from agentctl.check.virtualbox_snapshot import Attachment, Sample, attachment, join
from agentctl.check.virtualbox_storage import DiskObservation, VdiHeader
from agentctl.foundation import Err, Ok

pytestmark = pytest.mark.evidence("value")
VM_ID = "9d7dc4eb-c2b5-4044-8bf1-8d8a6c684df8"
DISK_ID = "20cef611-e035-4fd5-a514-5dcd57efce64"
FILE = r"C:\owned\disk.vdi"


def test_attachment_refuses_ambiguous_and_invalid_slots() -> None:
    """A named controller and both exact slot fields are needed for an attachment."""
    text = (
        'storagecontrollername0="SATA"\n'
        f'"SATA-0-0"={json.dumps(FILE)}\n'
        f'"SATA-ImageUUID-0-0"="{DISK_ID}"\n'
    )
    assert attachment(text, "SATA", 0, 0) == Ok(Attachment(FILE, DISK_ID))
    for bad in (
        text + f'"SATA-0-0"={json.dumps(FILE)}\n',
        text + 'storagecontrollername0="OTHER"\n',
        text.replace(DISK_ID, "00000000-0000-0000-0000-000000000000"),
        text.replace(json.dumps(FILE), '"relative.vdi"'),
        text.replace('storagecontrollername0="SATA"\n', ""),
    ):
        assert isinstance(attachment(bad, "SATA", 0, 0), Err), (
            "ambiguous VirtualBox attachment accepted"
        )
    assert isinstance(attachment(text, "SATA", -1, 0), Err)


def test_snapshot_join_refuses_changed_vm_and_foreign_disk(tmp_path: Path) -> None:
    """Equal bytes are insufficient when VM, medium or file identity differs."""
    disk = tmp_path / "disk.vdi"
    other = tmp_path / "other.vdi"
    disk.write_bytes(b"same")
    other.write_bytes(b"same")
    facts = disk.stat()
    vm = VmObservation("owned", VM_ID, "config", 4096, 2, 100, "running")
    header = VdiHeader(DISK_ID, 1024, 512, 2, 512)
    sample = Sample(
        vm,
        Attachment(str(disk), DISK_ID),
        DiskObservation(disk.resolve(), facts.st_dev, facts.st_ino, 4, header),
    )
    assert join(sample, sample, name="owned") == Ok(sample)
    assert isinstance(
        join(sample, replace(sample, vm=replace(vm, cpus=3)), name="owned"), Err
    ), "changed VirtualBox VM accepted"
    foreign = replace(sample, attachment=Attachment(str(other), DISK_ID))
    assert isinstance(join(foreign, foreign, name="owned"), Err), (
        "foreign VirtualBox attachment accepted"
    )
    wrong_id = replace(sample, attachment=Attachment(str(disk), VM_ID))
    assert isinstance(join(wrong_id, wrong_id, name="owned"), Err), (
        "foreign VDI UUID accepted"
    )
    changed = replace(sample, disk=replace(sample.disk, inode=sample.disk.inode + 1))
    assert isinstance(join(sample, changed, name="owned"), Err)
