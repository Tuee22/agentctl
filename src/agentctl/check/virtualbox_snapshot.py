# Copyright (c) 2026 agentctl contributors.
"""Join one VirtualBox attachment to a bracketed VDI observation, not a receipt."""

import json
import re
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
from uuid import UUID

from agentctl.check import virtualbox_observe, virtualbox_storage
from agentctl.check.virtualbox_observe import MAX_OUTPUT_CHARS, VmObservation
from agentctl.check.virtualbox_storage import DiskObservation
from agentctl.foundation import Err, Ok, Result

FIRST_PRINTABLE = 32
MAX_PORT = 63
MAX_DEVICE = 7


@dataclass(frozen=True, slots=True)
class Attachment:
    """One explicitly selected controller slot, not a complete storage census."""

    path: str
    identifier: str


@dataclass(frozen=True, slots=True)
class Sample:
    """Separately observed VM, attachment and file facts."""

    vm: VmObservation
    attachment: Attachment
    disk: DiskObservation


@dataclass(frozen=True, slots=True)
class SnapshotRequest:
    """Explicit subject and private storage boundary for a diagnostic sample."""

    executable: Path
    identifier: str
    name: str
    controller: str
    port: int
    device: int
    root: Path
    cwd: Path


def attachment(
    text: str, controller: str, port: int, device: int
) -> Result[Attachment, str]:
    """Decode one named slot and its medium UUID without guessing other slots."""
    if (
        not text.endswith("\n")
        or len(text) > MAX_OUTPUT_CHARS
        or re.fullmatch(r"[A-Za-z0-9 _.\-]{1,64}", controller) is None
        or isinstance(port, bool)
        or isinstance(device, bool)
        or not 0 <= port <= MAX_PORT
        or not 0 <= device <= MAX_DEVICE
    ):
        return Err("invalid VirtualBox attachment query")
    keys = (
        f'"{controller}-{port}-{device}"',
        f'"{controller}-ImageUUID-{port}-{device}"',
    )
    rows = tuple(line.partition("=") for line in text.splitlines())
    selected = tuple((key, value) for key, sep, value in rows if sep and key in keys)
    controllers = tuple(
        (key, value)
        for key, sep, value in rows
        if sep and re.fullmatch(r"storagecontrollername[0-9]+", key)
    )
    if (
        len(selected) != len(keys)
        or frozenset(key for key, _ in selected) != frozenset(keys)
        or len({key for key, _ in controllers}) != len(controllers)
    ):
        return Err("missing or duplicate VirtualBox attachment field")
    try:
        names: tuple[object, ...] = tuple(json.loads(value) for _, value in controllers)
        values = dict(selected)
        path: object = json.loads(values[keys[0]])
        identifier: object = json.loads(values[keys[1]])
        if (
            any(not isinstance(value, str) for value in names)
            or names.count(controller) != 1
            or not isinstance(path, str)
            or not isinstance(identifier, str)
        ):
            return Err("invalid VirtualBox attachment fields")
        parsed = UUID(identifier)
        if (
            str(parsed) != identifier
            or parsed.int == 0
            or not PureWindowsPath(path).is_absolute()
            or ".." in PureWindowsPath(path).parts
            or any(ord(character) < FIRST_PRINTABLE for character in path)
        ):
            return Err("invalid VirtualBox attachment identity")
        return Ok(Attachment(path, identifier))
    except (ValueError, UnicodeError):
        return Err("invalid VirtualBox attachment encoding")


def join(first: Sample, second: Sample, *, name: str) -> Result[Sample, str]:
    """Require a stable VM, slot, VDI identity and exact file for both samples."""
    if (
        not name
        or first.vm.name != name
        or first.vm != second.vm
        or first.attachment != second.attachment
        or first.disk.header != second.disk.header
        or first.disk.header.identifier != first.attachment.identifier
        or (first.disk.device, first.disk.inode)
        != (second.disk.device, second.disk.inode)
        or first.disk.device <= 0
        or first.disk.inode <= 0
        or second.disk.file_size < first.disk.file_size
    ):
        return Err("VirtualBox VM, attachment or disk identity changed")
    try:
        if first.disk.path != Path(first.attachment.path).resolve(strict=True):
            return Err("VirtualBox attachment path does not match VDI file")
        if not first.disk.path.samefile(second.disk.path):
            return Err("VirtualBox disk path changed")
    except OSError as exc:
        return Err("cannot compare VirtualBox disk paths: " + str(exc))
    return Ok(second)


def _disk_samples(
    slot: Attachment, root: Path
) -> Result[tuple[DiskObservation, DiskObservation], str]:
    """Read the same selected image twice between the two VM observations."""
    first = virtualbox_storage.inspect(Path(slot.path), root=root)
    if isinstance(first, Err):
        return first
    second = virtualbox_storage.inspect(Path(slot.path), root=root)
    return second if isinstance(second, Err) else Ok((first.value, second.value))


def observe(request: SnapshotRequest) -> Result[Sample, str]:
    """Bracket VDI file reads with two native observations of the same slot."""
    first = virtualbox_observe.capture(
        request.executable, request.identifier, cwd=request.cwd
    )
    if isinstance(first, Err):
        return first
    slot = attachment(first.value[1], request.controller, request.port, request.device)
    if isinstance(slot, Err):
        return slot
    disks = _disk_samples(slot.value, request.root)
    if isinstance(disks, Err):
        return disks
    second = virtualbox_observe.capture(
        request.executable, request.identifier, cwd=request.cwd
    )
    if isinstance(second, Err):
        return second
    later_slot = attachment(
        second.value[1], request.controller, request.port, request.device
    )
    if isinstance(later_slot, Err):
        return later_slot
    return join(
        Sample(first.value[0], slot.value, disks.value[0]),
        Sample(second.value[0], later_slot.value, disks.value[1]),
        name=request.name,
    )
