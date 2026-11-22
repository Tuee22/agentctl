# Copyright (c) 2026 agentctl contributors.
"""VDI metadata observations reject malformed images and escaped files."""

import struct
from pathlib import Path
from uuid import UUID

import pytest

from agentctl.check.virtualbox_storage import VdiHeader, inspect, parse
from agentctl.foundation import Err, Ok

IMAGE_ID = "20cef611-e035-4fd5-a514-5dcd57efce64"
EXPECTED_FILE_SIZE = 2097152


def _header() -> bytes:
    """Construct a finite 1.1 base-image vector from independently stated offsets."""
    value = bytearray(472)
    struct.pack_into("<IIII", value, 64, 0xBEDA107F, 0x00010001, 400, 1)
    struct.pack_into("<II", value, 340, 1048576, 2097152)
    struct.pack_into("<I", value, 360, 512)
    struct.pack_into("<QIIII", value, 368, 107374182400, 1048576, 0, 102400, 5)
    value[392:408] = UUID(IMAGE_ID).bytes_le
    return bytes(value)


@pytest.mark.evidence("value")
def test_vdi_header_refuses_invalid_identity_and_capacity() -> None:
    """The fixed vector has independent capacity, block and image identity values."""
    good = _header()
    assert parse(good) == Ok(
        VdiHeader(IMAGE_ID, 107374182400, 1048576, 102400, 2097152)
    )
    assert isinstance(parse(good[:471]), Err)
    for offset, replacement in (
        (64, 0),
        (68, 0),
        (72, 0),
        (72, 404),
        (76, 4),
        (340, 0),
        (344, 0),
        (360, 0),
        (376, 0),
        (384, 0),
        (388, 200000),
        (424, 1),
    ):
        changed = bytearray(good)
        struct.pack_into("<I", changed, offset, replacement)
        assert isinstance(parse(bytes(changed)), Err), "invalid VDI header accepted"
    for start, length in ((368, 8), (392, 16)):
        changed = bytearray(good)
        changed[start : start + length] = bytes(length)
        assert isinstance(parse(bytes(changed)), Err), "invalid VDI header accepted"


@pytest.mark.evidence("real")
def test_vdi_file_observation_checks_owned_root(tmp_path: Path) -> None:
    """Real files inside and outside the boundary exercise the read-only adapter."""
    root = tmp_path / "owned"
    root.mkdir()
    image = root / "test.vdi"
    image.write_bytes(_header())
    assert isinstance(inspect(image, root=root), Err)
    with image.open("ab") as stream:
        stream.truncate(2097152)
    result = inspect(image, root=root)
    assert isinstance(result, Ok), result
    assert result.value.header == VdiHeader(
        IMAGE_ID, 107374182400, 1048576, 102400, 2097152
    )
    assert result.value.file_size == EXPECTED_FILE_SIZE
    outside = tmp_path / "outside.vdi"
    outside.write_bytes(_header())
    with outside.open("ab") as stream:
        stream.truncate(EXPECTED_FILE_SIZE)
    assert isinstance(inspect(outside, root=root), Err), "outside storage root accepted"
    assert isinstance(inspect(root / "absent.vdi", root=root), Err)
