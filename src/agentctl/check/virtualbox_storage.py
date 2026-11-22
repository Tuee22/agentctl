# Copyright (c) 2026 agentctl contributors.
"""Read bounded VDI metadata without claiming VM attachment or containment proof."""

import os
import struct
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from agentctl.foundation import Err, Ok, Result

HEADER_BYTES = 472
SIGNATURE = 0xBEDA107F
VERSION = 0x00010001
HEADER_SIZE = 400
PREHEADER_SIZE = 72
SECTOR_SIZE = 512
BASE_DYNAMIC = 1
UUID_BYTES = 16


@dataclass(frozen=True, slots=True)
class VdiHeader:
    """Stable VDI identity and virtual allocation, not current storage consumption."""

    identifier: str
    capacity: int
    block_size: int
    blocks: int
    data_offset: int


@dataclass(frozen=True, slots=True)
class DiskObservation:
    """A file-handle sample, not proof that a VM uses this image."""

    path: Path
    device: int
    inode: int
    file_size: int
    header: VdiHeader


def parse(data: bytes) -> Result[VdiHeader, str]:
    """Decode supported base dynamic VDI 1.1 metadata and reject ambiguity."""
    if len(data) < HEADER_BYTES:
        return Err("incomplete VDI header")
    signature, version, header_size, kind = struct.unpack_from("<IIII", data, 64)
    blocks_offset, data_offset = struct.unpack_from("<II", data, 340)
    sector = struct.unpack_from("<I", data, 360)[0]
    capacity, block_size, extra, blocks, allocated = struct.unpack_from(
        "<QIIII", data, 368
    )
    identifier = UUID(bytes_le=data[392 : 392 + UUID_BYTES])
    parent = UUID(bytes_le=data[424 : 424 + UUID_BYTES])
    if (
        signature != SIGNATURE
        or version != VERSION
        or header_size != HEADER_SIZE
        or kind != BASE_DYNAMIC
        or sector != SECTOR_SIZE
        or capacity <= 0
        or capacity % SECTOR_SIZE
        or block_size < SECTOR_SIZE
        or block_size & (block_size - 1)
        or extra != 0
        or blocks != (capacity + block_size - 1) // block_size
        or allocated > blocks
        or blocks_offset < PREHEADER_SIZE + header_size
        or data_offset < blocks_offset + blocks * 4
        or blocks_offset % SECTOR_SIZE
        or data_offset % SECTOR_SIZE
        or identifier.int == 0
        or parent.int != 0
    ):
        return Err("unsupported or invalid VDI header")
    return Ok(VdiHeader(str(identifier), capacity, block_size, blocks, data_offset))


def inspect(path: Path, *, root: Path) -> Result[DiskObservation, str]:
    """Bracket a read with file identity checks inside a supplied storage root.

    This does not establish VM attachment, race-free containment or filesystem
    physical allocation; file_size is the observed logical file length.
    """
    try:
        if (
            not root.is_absolute()
            or not path.is_absolute()
            or ".." in root.parts
            or ".." in path.parts
            or root.is_symlink()
            or path.is_symlink()
        ):
            return Err("invalid VDI storage path")
        boundary = root.resolve(strict=True)
        resolved = path.resolve(strict=True)
        if (
            not boundary.is_dir()
            or resolved == boundary
            or not resolved.is_relative_to(boundary)
            or resolved.suffix.lower() != ".vdi"
            or not resolved.is_file()
        ):
            return Err("VDI escapes storage root or is not a regular image")
        with resolved.open("rb") as stream:
            first = os.fstat(stream.fileno())
            initial = parse(stream.read(HEADER_BYTES))
            stream.seek(0)
            final = parse(stream.read(HEADER_BYTES))
            last = os.fstat(stream.fileno())
        current = path.stat()
        if isinstance(initial, Err) or isinstance(final, Err):
            return Err("cannot decode VDI header")
        if (
            path.is_symlink()
            or initial != final
            or first.st_ino <= 0
            or (first.st_dev, first.st_ino) != (last.st_dev, last.st_ino)
            or (last.st_dev, last.st_ino) != (current.st_dev, current.st_ino)
            or first.st_size < initial.value.data_offset
            or last.st_size < first.st_size
            or current.st_size < first.st_size
        ):
            return Err("VDI identity or stable metadata changed during observation")
        return Ok(
            DiskObservation(
                resolved, first.st_dev, first.st_ino, first.st_size, initial.value
            )
        )
    except (OSError, RuntimeError, ValueError) as exc:
        return Err("cannot inspect VDI: " + str(exc))
