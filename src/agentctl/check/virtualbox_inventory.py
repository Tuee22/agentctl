# Copyright (c) 2026 agentctl contributors.
"""Inventory supported VirtualBox storage slots without claiming a receipt."""

import json
import re
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath

from agentctl.check import virtualbox_observe, virtualbox_snapshot, virtualbox_storage
from agentctl.check.virtualbox_observe import MAX_OUTPUT_CHARS, VmObservation
from agentctl.check.virtualbox_snapshot import Attachment, Sample
from agentctl.check.virtualbox_storage import DiskObservation
from agentctl.foundation import Err, Ok, Result

MAX_PORTS = 64
CONTROLLER_PREFIXES = (
    "storagecontrollername",
    "storagecontrollertype",
    "storagecontrollerportcount",
)
SLOT_SUFFIXES = (
    "",
    "-ImageUUID",
    "-IsEjected",
    "-tempeject",
    "-hot-pluggable",
    "-nonrotational",
    "-discard",
)


@dataclass(frozen=True, slots=True)
class Slot:
    """One supported hard-disk attachment and its controller location."""

    controller: str
    port: int
    medium: Attachment


@dataclass(frozen=True, slots=True)
class InventoryRequest:
    """VM and storage-root inputs for a diagnostic inventory."""

    executable: Path
    identifier: str
    name: str
    root: Path
    cwd: Path


@dataclass(frozen=True, slots=True)
class InventoryObservation:
    """Stable supported slots and VDI samples, not an authenticated receipt."""

    vm: VmObservation
    slots: tuple[Slot, ...]
    disks: tuple[DiskObservation, ...]


def _fields(text: str) -> Result[dict[str, str], str]:
    """Require complete lines and reject duplicate keys across the native output."""
    if not text or not text.endswith("\n") or len(text) > MAX_OUTPUT_CHARS:
        return Err("incomplete VirtualBox inventory")
    lines = tuple(text.splitlines())
    headings = tuple(
        line for line in lines if re.fullmatch(r" rec_screen(?:0|[1-9][0-9]*)", line)
    )
    if len(set(headings)) != len(headings):
        return Err("duplicate VirtualBox recording section")
    rows = tuple(line.partition("=") for line in lines if line not in headings)
    if any(not key or not separator for key, separator, _ in rows):
        return Err("malformed VirtualBox inventory line")
    fields = {key: value for key, _, value in rows}
    return (
        Ok(fields)
        if len(fields) == len(rows)
        else Err("duplicate VirtualBox inventory field")
    )


def _controller(fields: dict[str, str], index: str) -> Result[tuple[str, int], str]:
    """Accept the explicit AHCI controller layout currently observed by this adapter."""
    try:
        name: object = json.loads(fields["storagecontrollername" + index])
        kind: object = json.loads(fields["storagecontrollertype" + index])
        count: object = json.loads(fields["storagecontrollerportcount" + index])
        if (
            not isinstance(name, str)
            or re.fullmatch(r"[A-Za-z0-9 _.\-]{1,64}", name) is None
            or kind != "IntelAhci"
            or not isinstance(count, str)
            or re.fullmatch(r"[1-9][0-9]?", count) is None
            or int(count) > MAX_PORTS
        ):
            return Err("unsupported VirtualBox storage controller")
        return Ok((name, int(count)))
    except (KeyError, ValueError, UnicodeError):
        return Err("missing or malformed VirtualBox storage controller")


def _port(
    text: str, fields: dict[str, str], name: str, port: int
) -> Result[Slot | None, str]:
    """Decode one port or refuse an unclassified medium."""
    try:
        medium: object = json.loads(fields[f'"{name}-{port}-0"'])
        if not isinstance(medium, str):
            return Err("invalid VirtualBox medium field")
        optical = fields.get(f'"{name}-IsEjected-{port}-0"')
        if optical is not None:
            eject = json.loads(optical)
            temporary = json.loads(fields[f'"{name}-tempeject-{port}-0"'])
            optical_path = PureWindowsPath(medium)
            invalid = (
                eject not in ("on", "off")
                or temporary not in ("on", "off")
                or (
                    medium not in {"none", "emptydrive"}
                    and (
                        not optical_path.is_absolute()
                        or optical_path.suffix.lower() != ".iso"
                    )
                )
            )
            return Err("invalid VirtualBox optical state") if invalid else Ok(None)
        if medium not in {"none", "emptydrive"}:
            disk = virtualbox_snapshot.attachment(text, name, port, 0)
            return disk if isinstance(disk, Err) else Ok(Slot(name, port, disk.value))
        if medium == "emptydrive" or f'"{name}-ImageUUID-{port}-0"' in fields:
            return Err("unclassified VirtualBox empty drive")
        return Ok(None)
    except (KeyError, ValueError, UnicodeError, TypeError):
        return Err("incomplete VirtualBox controller slot")


def _slots(
    text: str, fields: dict[str, str], name: str, count: int
) -> Result[tuple[Slot, ...], str]:
    """Read every AHCI port; distinguish explicitly reported optical drives."""
    represented = frozenset(
        key
        for key in fields
        if re.fullmatch(r'"' + re.escape(name) + r'-[0-9]+-[0-9]+"', key)
    )
    expected = frozenset(f'"{name}-{port}-0"' for port in range(count))
    if represented != expected:
        return Err("missing or unexpected VirtualBox controller slot")
    observed = tuple(_port(text, fields, name, port) for port in range(count))
    errors = tuple(value.error for value in observed if isinstance(value, Err))
    if errors:
        return Err("; ".join(errors))
    return Ok(
        tuple(
            value.value
            for value in observed
            if isinstance(value, Ok) and value.value is not None
        )
    )


def inventory(text: str) -> Result[tuple[Slot, ...], str]:
    """Inventory all reported AHCI ports and refuse unsupported controller kinds."""
    parsed = _fields(text)
    if isinstance(parsed, Err):
        return parsed
    return _inventory_fields(text, parsed.value)


def _indices(fields: dict[str, str]) -> Result[tuple[str, ...], str]:
    """Refuse orphaned, noncanonical or incomplete controller field groups."""
    groups = tuple(
        tuple(key.removeprefix(prefix) for key in fields if key.startswith(prefix))
        for prefix in CONTROLLER_PREFIXES
    )
    if (
        not groups[0]
        or any(
            re.fullmatch(r"0|[1-9][0-9]*", value) is None
            for group in groups
            for value in group
        )
        or any(frozenset(group) != frozenset(groups[0]) for group in groups[1:])
    ):
        return Err("VirtualBox controller fields are incomplete or ambiguous")
    return Ok(groups[0])


def _recognized_slots(
    fields: dict[str, str], controllers: tuple[tuple[str, int], ...]
) -> bool:
    """Reject slot-shaped fields that do not belong to a known controller layout."""
    pairs = tuple(
        (name + suffix, count)
        for name, count in controllers
        for suffix in SLOT_SUFFIXES
    )
    allowed = dict(pairs)
    if len(allowed) != len(pairs):
        return False
    return all(
        match.group(1) in allowed
        and re.fullmatch(r"0|[1-9][0-9]?", match.group(2)) is not None
        and int(match.group(2)) < allowed[match.group(1)]
        and match.group(3) == "0"
        for key in fields
        if (match := re.fullmatch(r'"(.+)-([0-9]+)-([0-9]+)"', key)) is not None
    )


def _inventory_fields(
    text: str, fields: dict[str, str]
) -> Result[tuple[Slot, ...], str]:
    """Join all typed controller and port observations."""
    indices = _indices(fields)
    if isinstance(indices, Err):
        return indices
    controllers = tuple(_controller(fields, index) for index in indices.value)
    controller_errors = tuple(
        value.error for value in controllers if isinstance(value, Err)
    )
    if controller_errors:
        return Err("VirtualBox storage controllers: " + "; ".join(controller_errors))
    values = tuple(value.value for value in controllers if isinstance(value, Ok))
    if len({name.casefold() for name, _ in values}) != len(
        values
    ) or not _recognized_slots(fields, values):
        return Err("duplicate VirtualBox controller name")
    observed = tuple(_slots(text, fields, name, count) for name, count in values)
    slot_errors = tuple(value.error for value in observed if isinstance(value, Err))
    if slot_errors:
        return Err("VirtualBox storage slots: " + "; ".join(slot_errors))
    slots = tuple(
        slot for value in observed if isinstance(value, Ok) for slot in value.value
    )
    if not slots or len({slot.medium.identifier for slot in slots}) != len(slots):
        return Err("empty or duplicate VirtualBox disk inventory")
    return Ok(slots)


def _disks(
    slots: tuple[Slot, ...], root: Path
) -> Result[tuple[DiskObservation, ...], str]:
    """Inspect every enumerated disk without hiding unsupported image formats."""
    observed = tuple(
        virtualbox_storage.inspect(Path(slot.medium.path), root=root) for slot in slots
    )
    errors = tuple(value.error for value in observed if isinstance(value, Err))
    if errors:
        return Err("VirtualBox VDI inventory observation failed: " + "; ".join(errors))
    disks = tuple(value.value for value in observed if isinstance(value, Ok))
    if len({(disk.device, disk.inode) for disk in disks}) != len(disks):
        return Err("duplicate VirtualBox disk file identity")
    return Ok(disks)


def join(
    first: InventoryObservation, second: InventoryObservation, name: str
) -> Result[InventoryObservation, str]:
    """Join equal slot censuses and each corresponding independent VDI sample."""
    if (
        not first.slots
        or first.slots != second.slots
        or len(first.slots) != len(first.disks)
        or len(second.slots) != len(second.disks)
    ):
        return Err("VirtualBox storage inventory changed")
    results = tuple(
        virtualbox_snapshot.join(
            Sample(first.vm, slot.medium, disk),
            Sample(second.vm, slot.medium, later_disk),
            name=name,
        )
        for slot, disk, later_disk in zip(
            first.slots, first.disks, second.disks, strict=True
        )
    )
    errors = tuple(value.error for value in results if isinstance(value, Err))
    return (
        Err("VirtualBox storage inventory join failed: " + "; ".join(errors))
        if errors
        else Ok(second)
    )


def observe(request: InventoryRequest) -> Result[InventoryObservation, str]:
    """Bracket two complete supported disk reads with native VM inventories."""
    first = virtualbox_observe.capture(
        request.executable, request.identifier, cwd=request.cwd
    )
    if isinstance(first, Err):
        return first
    slots = inventory(first.value[1])
    if isinstance(slots, Err):
        return slots
    disks = _disk_pair(slots.value, request.root)
    if isinstance(disks, Err):
        return disks
    second = virtualbox_observe.capture(
        request.executable, request.identifier, cwd=request.cwd
    )
    if isinstance(second, Err):
        return second
    later_slots = inventory(second.value[1])
    if isinstance(later_slots, Err):
        return later_slots
    return join(
        InventoryObservation(first.value[0], slots.value, disks.value[0]),
        InventoryObservation(second.value[0], later_slots.value, disks.value[1]),
        request.name,
    )


def _disk_pair(
    slots: tuple[Slot, ...], root: Path
) -> Result[tuple[tuple[DiskObservation, ...], tuple[DiskObservation, ...]], str]:
    """Observe every enumerated disk twice between the VM queries."""
    first = _disks(slots, root)
    if isinstance(first, Err):
        return first
    second = _disks(slots, root)
    return second if isinstance(second, Err) else Ok((first.value, second.value))
