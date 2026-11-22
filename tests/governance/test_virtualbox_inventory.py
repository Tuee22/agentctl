# Copyright (c) 2026 agentctl contributors.
"""VirtualBox AHCI inventories retain all hard-disk slots."""

import json
from dataclasses import replace
from pathlib import Path

import pytest

from agentctl.check.virtualbox_inventory import (
    InventoryObservation,
    Slot,
    inventory,
    join,
)
from agentctl.check.virtualbox_observe import VmObservation
from agentctl.check.virtualbox_snapshot import Attachment
from agentctl.check.virtualbox_storage import DiskObservation, VdiHeader
from agentctl.foundation import Err, Ok

pytestmark = pytest.mark.evidence("value")
FIRST = "20cef611-e035-4fd5-a514-5dcd57efce64"
SECOND = "8316a61e-f498-46bd-a48a-e5a90e7eb927"


def test_inventory_includes_all_disks_and_refuses_ambiguous_slots() -> None:
    """Two disks, an optical drive and an empty port remain distinguishable."""
    path1, path2, optical = r"C:\vm\one.vdi", r"C:\vm\two.vdi", r"C:\vm\disc.iso"
    text = (
        'storagecontrollername0="SATA"\n'
        'storagecontrollertype0="IntelAhci"\n'
        'storagecontrollerportcount0="4"\n'
        f'"SATA-0-0"={json.dumps(path1)}\n'
        f'"SATA-ImageUUID-0-0"="{FIRST}"\n'
        f'"SATA-1-0"={json.dumps(optical)}\n'
        '"SATA-IsEjected-1-0"="off"\n'
        '"SATA-tempeject-1-0"="off"\n'
        f'"SATA-2-0"={json.dumps(path2)}\n'
        f'"SATA-ImageUUID-2-0"="{SECOND}"\n'
        '"SATA-3-0"="none"\n'
        " rec_screen0\n"
    )
    assert inventory(text) == Ok(
        (
            Slot("SATA", 0, Attachment(path1, FIRST)),
            Slot("SATA", 2, Attachment(path2, SECOND)),
        )
    ), "VirtualBox disk inventory omitted a slot"
    for bad in (
        text.replace('"SATA-3-0"="none"\n', ""),
        text + '"SATA-4-0"="none"\n',
        text + '"SATA-0-0"="none"\n',
        text + '"HIDDEN-0-0"="none"\n',
        text + '"SATA-ImageUUID-9-0"="00000000-0000-0000-0000-000000000000"\n',
        text + 'storagecontrollertype1="IntelAhci"\n',
        text + 'storagecontrollername00="HIDDEN"\n',
        text + " rec_screen0\n",
        text + "=invalid\n",
        text.replace(
            'storagecontrollertype0="IntelAhci"', 'storagecontrollertype0="Other"'
        ),
        text.replace(SECOND, FIRST),
        text.replace(json.dumps(optical), json.dumps(path2)),
        text.replace('"SATA-tempeject-1-0"="off"\n', ""),
    ):
        assert isinstance(inventory(bad), Err), "invalid VirtualBox inventory accepted"


def test_inventory_join_rejects_changed_or_missing_disks(tmp_path: Path) -> None:
    """Both VM samples must describe the same ordered complete disk inventory."""
    paths = (tmp_path / "one.vdi", tmp_path / "two.vdi")
    for path in paths:
        path.write_bytes(b"sample")
    ids = (FIRST, SECOND)
    slots = tuple(
        Slot("SATA", number, Attachment(str(path), identifier))
        for number, (path, identifier) in enumerate(zip(paths, ids, strict=True))
    )
    disks = tuple(
        DiskObservation(
            path.resolve(),
            path.stat().st_dev,
            path.stat().st_ino,
            6,
            VdiHeader(identifier, 1024, 512, 2, 512),
        )
        for path, identifier in zip(paths, ids, strict=True)
    )
    vm = VmObservation("owned", FIRST, "config", 4096, 2, 100, "running")
    sample = InventoryObservation(vm, slots, disks)
    assert join(sample, sample, "owned") == Ok(sample)
    changed = replace(sample, slots=(replace(slots[0], port=9), slots[1]))
    assert isinstance(join(sample, changed, "owned"), Err), "changed disk slot accepted"
    assert isinstance(join(sample, replace(sample, disks=disks[:1]), "owned"), Err)
    assert isinstance(
        join(
            replace(sample, slots=(), disks=()),
            replace(sample, slots=(), disks=()),
            "owned",
        ),
        Err,
    )
