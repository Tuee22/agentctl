# Copyright (c) 2026 agentctl contributors.
"""Verify native proc and complete cgroup v2 mounts before process sampling."""

import platform
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from typing import Protocol, runtime_checkable

from agentctl.check import phase_reports
from agentctl.check.phase_reports import MountFact
from agentctl.foundation import Err, Ok, Result

MIN_MOUNT_FIELDS = 6


@dataclass(frozen=True, slots=True)
class DeviceIdentity:
    """Native filesystem device numbers and directory inode."""

    major: int
    minor: int
    inode: int


@dataclass(frozen=True, slots=True)
class MountObservation:
    """Two kernel mount mappings and the matching directory identities."""

    proc: MountFact
    cgroup: MountFact
    proc_device: DeviceIdentity
    cgroup_device: DeviceIdentity


@runtime_checkable
class _DeviceNumbers(Protocol):
    """The Linux-only native device-number conversion interface."""

    def major(self, device: int) -> int:
        """Return the major device number."""
        ...

    def minor(self, device: int) -> int:
        """Return the minor device number."""
        ...


def _options(text: str, identifier: int) -> Result[frozenset[str], str]:
    """Read per-mount and superblock options for exactly one mount ID."""
    rows = tuple(
        line.split()
        for line in text.splitlines()
        if line.split(maxsplit=1)[:1] == [str(identifier)]
    )
    if len(rows) != 1 or "-" not in rows[0]:
        return Err("mount options unavailable")
    fields = rows[0]
    separator = fields.index("-")
    if len(fields) != separator + 4 or len(fields) < MIN_MOUNT_FIELDS:
        return Err("invalid mount options")
    return Ok(frozenset((*fields[5].split(","), *fields[separator + 3].split(","))))


def _visible(text: str, identifier: int) -> Result[None, str]:
    """Refuse proc mount options that can hide process identities."""
    options = _options(text, identifier)
    if isinstance(options, Err):
        return options
    if any(
        option == "hidepid"
        or (
            option.startswith("hidepid=") and option not in {"hidepid=0", "hidepid=off"}
        )
        for option in options.value
    ):
        return Err("proc mount hides process identities")
    return Ok(None)


def validate(
    text: str,
    cgroup_path: str,
    proc_device: DeviceIdentity,
    cgroup_device: DeviceIdentity,
) -> Result[MountObservation, str]:
    """Join kernel mount records and device facts without attesting their origin."""
    records = phase_reports.parse_mountinfo(text)
    if isinstance(records, Err):
        return Err("invalid mountinfo: " + records.error)
    proc = phase_reports.containing_mount("/proc", records.value)
    cgroup = phase_reports.containing_mount(cgroup_path, records.value)
    if isinstance(proc, Err) or isinstance(cgroup, Err):
        return Err("proc or cgroup mount unavailable")
    if (
        proc.value.mountpoint != "/proc"
        or proc.value.filesystem != "proc"
        or proc.value.root != "/"
        or cgroup.value.mountpoint != cgroup_path
        or cgroup.value.filesystem != "cgroup2"
        or cgroup.value.root != "/"
    ):
        return Err("proc or cgroup mount is not a complete native hierarchy")
    if (
        proc.value.identifier <= 0
        or cgroup.value.identifier <= 0
        or proc_device.inode <= 0
        or cgroup_device.inode <= 0
        or proc.value.device != f"{proc_device.major}:{proc_device.minor}"
        or cgroup.value.device != f"{cgroup_device.major}:{cgroup_device.minor}"
    ):
        return Err("proc or cgroup mount device identity differs")
    visible = _visible(text, proc.value.identifier)
    if isinstance(visible, Err):
        return visible
    return Ok(MountObservation(proc.value, cgroup.value, proc_device, cgroup_device))


def _device(path: Path, interface: _DeviceNumbers) -> DeviceIdentity:
    """Read the device and inode of one actual native directory."""
    facts = path.stat()
    return DeviceIdentity(
        interface.major(facts.st_dev), interface.minor(facts.st_dev), facts.st_ino
    )


def _twice(
    proc: Path, cgroup: Path, interface: _DeviceNumbers
) -> Result[MountObservation, str]:
    """Require two matching native mount and directory observations."""
    before = validate(
        (proc / "self/mountinfo").read_text(encoding="utf-8"),
        cgroup.as_posix(),
        _device(proc, interface),
        _device(cgroup, interface),
    )
    if isinstance(before, Err):
        return before
    after = validate(
        (proc / "self/mountinfo").read_text(encoding="utf-8"),
        cgroup.as_posix(),
        _device(proc, interface),
        _device(cgroup, interface),
    )
    if isinstance(after, Err):
        return after
    return (
        before if before.value == after.value else Err("proc or cgroup mount changed")
    )


def observe(cgroup_root: Path) -> Result[MountObservation, str]:
    """Read and recheck native kernel mount and directory identities on Linux."""
    if platform.system() != "Linux":
        return Err("cgroup mount observation requires Linux")
    interface: object = import_module("os")
    if not isinstance(interface, _DeviceNumbers):
        return Err("Linux device-number interface unavailable")
    try:
        proc = Path("/proc")
        cgroup = cgroup_root.resolve(strict=True)
        if cgroup != cgroup_root or not cgroup.is_dir():
            return Err("cgroup mount path is not canonical")
        return _twice(proc, cgroup, interface)
    except (OSError, UnicodeError, RuntimeError, ValueError) as exc:
        return Err("cannot observe native cgroup mounts: " + str(exc))
