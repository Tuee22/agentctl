# Copyright (c) 2026 agentctl contributors.
"""Read-only Windows registration observations for a dedicated WSL instance."""

import json
import ntpath
import os
import platform
import re
import shutil
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from agentctl.foundation import Err, Ok, Result
from agentctl.foundation_process import ByteOutput, Output, run, run_bytes

WSL2_VERSION = 2
FIRST_PRINTABLE_ASCII = 32

REGISTRY_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$items = @(Get-ChildItem 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Lxss' |
    ForEach-Object {
        $item = Get-ItemProperty -LiteralPath $_.PSPath
        [pscustomobject]@{ identifier = $_.PSChildName; name = $item.DistributionName;
                          base = $item.BasePath; version = $item.Version }
    })
ConvertTo-Json -InputObject $items -Compress
"""


@dataclass(frozen=True, slots=True)
class Registration:
    """One named registration and its native Windows storage location."""

    identifier: str
    name: str
    base: str
    version: int


@dataclass(frozen=True, slots=True)
class StorageObservation:
    """Current resolved VHD identity, file length and host-volume free bytes."""

    base: Path
    vhd: Path
    device: int
    inode: int
    file_bytes: int
    free_bytes: int


def inspect_storage(base: Path, owned_root: Path) -> Result[StorageObservation, str]:
    """Inspect a VHD only within the resolved, explicitly owned storage boundary.

    The VHD file length is not its configured maximum or a workload budget.
    This observation alone does not establish provisioning ownership.
    """
    try:
        root = owned_root.resolve(strict=True)
        directory = base.resolve(strict=True)
        if (
            base.is_symlink()
            or owned_root.is_symlink()
            or not root.is_dir()
            or not directory.is_dir()
            or directory == root
        ):
            return Err("invalid WSL storage boundary")
        if not directory.is_relative_to(root):
            return Err("WSL storage escapes owned boundary")
        vhd = directory / "ext4.vhdx"
        if (
            vhd.is_symlink()
            or not vhd.is_file()
            or vhd.resolve(strict=True).parent != directory
        ):
            return Err("WSL VHD is not a contained regular file")
        facts = vhd.stat()
        if facts.st_ino <= 0 or facts.st_size < 0:
            return Err("WSL VHD identity unavailable")
        return Ok(
            StorageObservation(
                directory,
                vhd,
                facts.st_dev,
                facts.st_ino,
                facts.st_size,
                shutil.disk_usage(directory).free,
            )
        )
    except (OSError, RuntimeError) as exc:
        return Err("cannot inspect WSL storage: " + str(exc))


def _windows_path(value: str) -> bool:
    """Accept only an absolute, normalized Windows path without parent aliases."""
    return bool(
        value
        and ntpath.isabs(value)
        and ntpath.normpath(value) == value
        and ".." not in value.replace("/", "\\").split("\\")
    )


def _valid_row(row: Registration) -> bool:
    """Check identity syntax without assigning ownership to any registration."""
    return bool(
        re.fullmatch(
            r"\{[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}\}",
            row.identifier,
        )
        and row.name
        and all(ord(character) >= FIRST_PRINTABLE_ASCII for character in row.name)
        and _windows_path(row.base)
        and not isinstance(row.version, bool)
        and row.version in {1, WSL2_VERSION}
    )


def _fields(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """Reject duplicate registry-observation fields."""
    values = dict(pairs)
    if len(values) != len(pairs):
        message = "duplicate WSL registration field"
        raise ValueError(message)
    return values


def parse(text: str) -> Result[tuple[Registration, ...], str]:
    """Decode closed registration rows without trusting their names as ownership."""
    try:
        value: object = json.loads(text, object_pairs_hook=_fields)
    except (ValueError, UnicodeError) as exc:
        return Err("invalid WSL registration data: " + str(exc))
    if not isinstance(value, list):
        return Err("WSL registration list required")
    rows: tuple[Registration, ...] = ()
    for item in value:
        match item:
            case {
                "identifier": str() as identifier,
                "name": str() as name,
                "base": str() as base,
                "version": int() as version,
                **extra,
            } if not extra and not isinstance(version, bool):
                row = Registration(identifier.lower(), name, base, version)
                if not _valid_row(row):
                    return Err("invalid WSL registration row")
                rows += (row,)
            case _:
                return Err("invalid WSL registration row")
    if len({row.identifier for row in rows}) != len(rows) or len(
        {row.name.casefold() for row in rows}
    ) != len(rows):
        return Err("ambiguous WSL registration list")
    return Ok(rows)


def select(
    rows: tuple[Registration, ...], expected: Registration, owned_root: str, listed: int
) -> Result[Registration, str]:
    """Match a retained provisioning identity and a distinct owned storage root.

    This is a consistency check; the caller must authenticate the provisioning
    identity and independently inspect the registered VHD and workload limits.
    """
    if (
        not _windows_path(owned_root)
        or not _valid_row(expected)
        or any(not _valid_row(row) for row in rows)
        or len({row.identifier.lower() for row in rows}) != len(rows)
        or len({row.name.casefold() for row in rows}) != len(rows)
    ):
        return Err("invalid owned WSL storage boundary")
    try:
        root = ntpath.normcase(owned_root)
        base = ntpath.normcase(expected.base)
        if root == base or ntpath.commonpath((root, base)) != root:
            return Err("WSL storage is outside the owned boundary")
    except ValueError:
        return Err("WSL storage is outside the owned boundary")
    matching = tuple(
        row for row in rows if row.name.casefold() == expected.name.casefold()
    )
    if len(matching) != 1:
        return Err("dedicated WSL registration unavailable or ambiguous")
    actual = matching[0]
    if (
        actual.version != WSL2_VERSION
        or expected.version != WSL2_VERSION
        or isinstance(listed, bool)
        or listed != WSL2_VERSION
        or actual.identifier != expected.identifier.lower()
        or ntpath.normcase(actual.base) != base
    ):
        return Err("dedicated WSL registration identity mismatch")
    return Ok(actual)


def listed_version(text: str, name: str) -> Result[int, str]:
    """Read one exact named row from the native WSL verbose listing."""
    if not name.strip() or any(
        ord(character) < FIRST_PRINTABLE_ASCII for character in name
    ):
        return Err("invalid WSL distribution name")
    lines = text.replace("\x00", "").splitlines()
    pattern = r"^\s*\*?\s*" + re.escape(name) + r"\s+.+?\s+([12])\s*$"
    matches = tuple(
        value
        for line in lines
        for value in re.findall(pattern, line, flags=re.IGNORECASE)
    )
    if len(matches) != 1:
        return Err("WSL version listing is missing or ambiguous")
    return Ok(int(matches[0]))


def version_environment(inherited: Mapping[str, str]) -> dict[str, str]:
    """Request UTF-8 only for the child WSL listing process."""
    return {**inherited, "WSL_UTF8": "1"}


def version_result(output: Output, name: str) -> Result[int, str]:
    """Refuse failed or non-UTF-8-shaped output before parsing a version."""
    if output.code != 0:
        return Err("cannot observe WSL version: " + output.stderr)
    if "\x00" in output.stdout:
        return Err("WSL listing did not use the requested UTF-8 encoding")
    return listed_version(output.stdout, name)


def version_bytes_result(output: ByteOutput, name: str) -> Result[int, str]:
    """Decode the requested UTF-8 or a native UTF-16LE WSL listing strictly."""
    if output.code != 0:
        return Err("cannot observe WSL version: " + repr(output.stderr))
    data = output.stdout
    encoding = (
        "utf-16"
        if data.startswith(b"\xff\xfe")
        else ("utf-16-le" if b"\x00" in data else "utf-8-sig")
    )
    try:
        decoded = data.decode(encoding)
    except UnicodeError as exc:
        return Err("cannot decode WSL version listing: " + str(exc))
    return version_result(Output(output.code, decoded, ""), name)


def wsl_executable() -> Result[Path, str]:
    """Locate the native Windows WSL interface without searching user PATH."""
    if platform.system() != "Windows":
        return Err("WSL version observation requires Windows")
    windows = os.environ.get("SYSTEMROOT", "")
    if not windows:
        return Err("Windows system directory unavailable")
    executable = Path(windows) / "System32/wsl.exe"
    if not executable.is_file():
        return Err("Windows WSL interface unavailable")
    return Ok(executable)


def observe_version(root: Path, name: str) -> Result[int, str]:
    """Read the current native WSL version without starting a distribution."""
    executable = wsl_executable()
    if isinstance(executable, Err):
        return executable
    observed = run_bytes(
        [str(executable.value), "--list", "--verbose"],
        cwd=root,
        env=version_environment(os.environ),
        timeout=30,
    )
    if isinstance(observed, Err):
        return Err("cannot observe WSL version: " + observed.error.message)
    return version_bytes_result(observed.value, name)


def observe(root: Path) -> Result[tuple[Registration, ...], str]:
    """Read the current user's native WSL registrations without changing them."""
    if platform.system() != "Windows":
        return Err("WSL registration observation requires Windows")
    windows = os.environ.get("SYSTEMROOT", "")
    if not windows:
        return Err("Windows system directory unavailable")
    executable = Path(windows) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    if not executable.is_file():
        return Err("Windows PowerShell unavailable")
    observed = run(
        [str(executable), "-NoProfile", "-NonInteractive", "-Command", REGISTRY_SCRIPT],
        cwd=root,
        env=os.environ,
        timeout=30,
    )
    if isinstance(observed, Err):
        return Err("cannot observe WSL registration: " + observed.error.message)
    if observed.value.code != 0:
        return Err("cannot observe WSL registration: " + observed.value.stderr)
    return parse(observed.value.stdout)
