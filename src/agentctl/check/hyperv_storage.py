# Copyright (c) 2026 agentctl contributors.
"""Observe contained VHD files without treating their paths as resource receipts."""

from dataclasses import dataclass
from pathlib import Path

from agentctl.check.wsl_vhd import VhdSize, query_information
from agentctl.foundation import Err, Ok, Result


@dataclass(frozen=True, slots=True)
class DiskFile:
    """One independently inspected regular file and its current filesystem identity."""

    path: Path
    device: int
    inode: int
    size: int


def _disk(path: Path, boundary: Path) -> Result[DiskFile, str]:
    """Inspect one path before it is joined to the complete chain."""
    if not path.is_absolute() or ".." in path.parts or path.is_symlink():
        return Err("invalid Hyper-V disk path")
    before = path.stat()
    resolved = path.resolve(strict=True)
    if (
        resolved == boundary
        or not resolved.is_relative_to(boundary)
        or not resolved.is_file()
        or resolved.suffix.lower() not in {".vhd", ".vhdx", ".avhdx"}
    ):
        return Err("Hyper-V disk escapes storage boundary")
    after = path.stat()
    if (
        before.st_dev != after.st_dev
        or before.st_ino != after.st_ino
        or before.st_size != after.st_size
        or after.st_ino <= 0
        or after.st_size <= 0
    ):
        return Err("Hyper-V disk identity changed or is unavailable")
    return Ok(DiskFile(resolved, after.st_dev, after.st_ino, after.st_size))


def inspect(
    paths: tuple[Path, ...], *, root: Path
) -> Result[tuple[DiskFile, ...], str]:
    """Check resolved ancestry and bracket file identity; never open or modify a VHD.

    This does not prove virtual size, link-free future state or observation provenance.
    """
    try:
        if not paths or root.is_symlink() or not root.is_dir():
            return Err("invalid Hyper-V storage root or empty disk chain")
        boundary = root.resolve(strict=True)
        found: tuple[DiskFile, ...] = ()
        for path in paths:
            result = _disk(path, boundary)
            if isinstance(result, Err):
                return result
            found += (result.value,)
        if len({(disk.device, disk.inode) for disk in found}) != len(found):
            return Err("duplicate Hyper-V disk identity")
        return Ok(found)
    except (OSError, RuntimeError, ValueError) as exc:
        return Err("cannot inspect Hyper-V storage: " + str(exc))


def virtual_size(path: Path, *, root: Path) -> Result[VhdSize, str]:
    """Bracket the native VHD information query with contained file identities."""
    before = inspect((path,), root=root)
    if isinstance(before, Err):
        return before
    size = query_information(before.value[0].path)
    after = inspect((path,), root=root)
    if isinstance(after, Err):
        return Err(
            (size.error + "; " if isinstance(size, Err) else "")
            + "Hyper-V disk recheck failed: "
            + after.error
        )
    first, second = before.value[0], after.value[0]
    if (first.path, first.device, first.inode) != (
        second.path,
        second.device,
        second.inode,
    ):
        return Err(
            (size.error + "; " if isinstance(size, Err) else "")
            + "Hyper-V disk identity changed"
        )
    return size
