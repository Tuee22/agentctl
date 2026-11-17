# Copyright (c) 2026 agentctl contributors.
"""Read a contained VHD's virtual size without modifying or attaching it."""

import ctypes
import platform
from dataclasses import dataclass
from pathlib import Path

from agentctl.check.wsl_registration import inspect_storage
from agentctl.foundation import Err, Ok, Result

VHDX_DEVICE = 3
OPEN_INFO_VERSION = 2
SIZE_INFO_VERSION = 1
MICROSOFT_VENDOR = (
    0xEC984AEC,
    0xA0F9,
    0x47E9,
    (0x90, 0x1F, 0x71, 0x41, 0x5A, 0x66, 0x34, 0x5B),
)


class _Guid(ctypes.Structure):
    """The native GUID layout in virtdisk.h."""

    _fields_ = [
        ("first", ctypes.c_uint32),
        ("second", ctypes.c_uint16),
        ("third", ctypes.c_uint16),
        ("tail", ctypes.c_ubyte * 8),
    ]


class _Storage(ctypes.Structure):
    """The native virtual storage type."""

    _fields_ = [("device", ctypes.c_uint32), ("vendor", _Guid)]


class _OpenInfo(ctypes.Structure):
    """Version 2 information-only, read-only open parameters."""

    _fields_ = [
        ("version", ctypes.c_uint32),
        ("info_only", ctypes.c_int32),
        ("read_only", ctypes.c_int32),
        ("resiliency", _Guid),
    ]


class _SizeInfo(ctypes.Structure):
    """The size variant of GET_VIRTUAL_DISK_INFO."""

    _fields_ = [
        ("version", ctypes.c_uint32),
        ("virtual", ctypes.c_uint64),
        ("physical", ctypes.c_uint64),
        ("block", ctypes.c_uint32),
        ("sector", ctypes.c_uint32),
    ]
    virtual: int
    physical: int
    block: int
    sector: int


@dataclass(frozen=True, slots=True)
class VhdSize:
    """A native size observation, not authenticated resource evidence."""

    virtual: int
    physical: int
    block: int
    sector: int


def checked_size(
    virtual: int, physical: int, block: int, sector: int
) -> Result[VhdSize, str]:
    """Refuse incomplete or impossible size data before it enters a budget."""
    if (
        any(isinstance(value, bool) for value in (virtual, physical, block, sector))
        or virtual <= 0
        or physical < 0
        or block <= 0
        or sector <= 0
    ):
        return Err("invalid VHD size observation")
    return Ok(VhdSize(virtual, physical, block, sector))


def _query(path: Path) -> Result[VhdSize, str]:
    """Open only for information and close the native handle on every path."""
    try:
        disk = ctypes.WinDLL("virtdisk", use_last_error=True)
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        disk.OpenVirtualDisk.argtypes = (
            ctypes.POINTER(_Storage),
            ctypes.c_wchar_p,
            ctypes.c_uint32,
            ctypes.c_uint32,
            ctypes.POINTER(_OpenInfo),
            ctypes.POINTER(ctypes.c_void_p),
        )
        disk.OpenVirtualDisk.restype = ctypes.c_uint32
        disk.GetVirtualDiskInformation.argtypes = (
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_uint32),
            ctypes.POINTER(_SizeInfo),
            ctypes.c_void_p,
        )
        disk.GetVirtualDiskInformation.restype = ctypes.c_uint32
        kernel.CloseHandle.argtypes = (ctypes.c_void_p,)
        kernel.CloseHandle.restype = ctypes.c_int32
        first, second, third, tail = MICROSOFT_VENDOR
        storage = _Storage(
            VHDX_DEVICE, _Guid(first, second, third, (ctypes.c_ubyte * 8)(*tail))
        )
        parameters = _OpenInfo(OPEN_INFO_VERSION, 1, 1, _Guid())
        handle = ctypes.c_void_p()
        opened = disk.OpenVirtualDisk(
            ctypes.byref(storage),
            str(path),
            0,
            0,
            ctypes.byref(parameters),
            ctypes.byref(handle),
        )
        if opened:
            return Err("VHD information open failed: " + str(opened))
        info = _SizeInfo()
        info.version = SIZE_INFO_VERSION
        size = ctypes.c_uint32(ctypes.sizeof(info))
        try:
            status = disk.GetVirtualDiskInformation(
                handle, ctypes.byref(size), ctypes.byref(info), None
            )
            result = (
                Err("VHD size query failed: " + str(status))
                if status
                else checked_size(info.virtual, info.physical, info.block, info.sector)
            )
        except (OSError, ValueError, AttributeError) as exc:
            result = Err("VHD size query unavailable: " + str(exc))
        try:
            closed = kernel.CloseHandle(handle)
            close_error = "" if closed else "VHD handle close failed"
        except (OSError, ValueError, AttributeError) as exc:
            close_error = "VHD handle close failed: " + str(exc)
        if close_error:
            return Err(
                (result.error + "; " if isinstance(result, Err) else "") + close_error
            )
    except (OSError, ValueError, AttributeError) as exc:
        return Err("VHD information unavailable: " + str(exc))
    else:
        return result


def query_information(path: Path) -> Result[VhdSize, str]:
    """Read VHD information only; callers must independently bracket path identity."""
    if platform.system() != "Windows":
        return Err("VHD size observation requires Windows")
    return _query(path)


def observe(base: Path, owned_root: Path) -> Result[VhdSize, str]:
    """Bracket a Windows VHD size query with the same contained file identity."""
    if platform.system() != "Windows":
        return Err("VHD size observation requires Windows")
    before = inspect_storage(base, owned_root)
    if isinstance(before, Err):
        return before
    result = _query(before.value.vhd)
    after = inspect_storage(base, owned_root)
    if isinstance(after, Err):
        return Err(
            (result.error + "; " if isinstance(result, Err) else "")
            + "VHD identity recheck failed: "
            + after.error
        )
    if (before.value.vhd, before.value.device, before.value.inode) != (
        after.value.vhd,
        after.value.device,
        after.value.inode,
    ):
        return Err(
            (result.error + "; " if isinstance(result, Err) else "")
            + "VHD identity changed during observation"
        )
    return result
