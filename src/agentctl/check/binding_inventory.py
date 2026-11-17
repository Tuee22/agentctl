# Copyright (c) 2026 agentctl contributors.
"""Nonce-bound transport of complete observed source entries for binding checks."""

import base64
import binascii
import json
import re
from pathlib import Path, PurePosixPath

from agentctl.check.evidence import (
    FIRST_SURROGATE,
    LAST_SURROGATE,
    SYMLINK_PAYLOADS,
    Entry,
    source_census,
)
from agentctl.foundation import Err, Ok, Result

FIRST_PRINTABLE_ASCII = 32


def _valid(entries: tuple[Entry, ...]) -> bool:
    """Reject aliases, malformed payloads, absent parents and duplicate entries."""
    names = tuple(entry.path for entry in entries)
    kinds = {entry.path: entry.kind for entry in entries}
    return bool(
        entries
        and names == tuple(sorted(set(names)))
        and all(
            entry.path
            and bool(PurePosixPath(entry.path).parts)
            and PurePosixPath(entry.path).as_posix() == entry.path
            and not PurePosixPath(entry.path).is_absolute()
            and all(part not in {".", ".."} for part in PurePosixPath(entry.path).parts)
            and PurePosixPath(entry.path).parts[0] != ".git"
            and "\\" not in entry.path
            and ":" not in entry.path
            and not any(
                ord(character) < FIRST_PRINTABLE_ASCII
                or FIRST_SURROGATE <= ord(character) <= LAST_SURROGATE
                for character in entry.path
            )
            and (
                PurePosixPath(entry.path).parent.as_posix() == "."
                or kinds.get(PurePosixPath(entry.path).parent.as_posix()) == "directory"
            )
            and (
                (entry.kind == "directory" and entry.payloads == (b"",))
                or (entry.kind == "file" and len(entry.payloads) == 1)
                or (entry.kind == "symlink" and len(entry.payloads) == SYMLINK_PAYLOADS)
            )
            for entry in entries
        )
    )


def encode(entries: tuple[Entry, ...], nonce: str) -> Result[str, str]:
    """Encode observed relative paths, kinds and exact bytes with a fresh nonce."""
    if re.fullmatch(r"[0-9a-f]{32}", nonce) is None or not _valid(entries):
        return Err("invalid binding inventory or nonce")
    value = {
        "nonce": nonce,
        "entries": [
            [
                entry.path,
                entry.kind,
                [base64.b64encode(item).decode("ascii") for item in entry.payloads],
            ]
            for entry in entries
        ],
    }
    return Ok(json.dumps(value, ensure_ascii=True, separators=(",", ":")))


def observe(root: Path, nonce: str) -> Result[str, str]:
    """Independently read the live source tree before serializing its inventory."""
    entries = source_census(root)
    if isinstance(entries, Err):
        return Err("binding source census: " + entries.error.message)
    return encode(entries.value, nonce)


def _fields(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """Reject ambiguous JSON names at every object boundary."""
    value = dict(pairs)
    if len(value) != len(pairs):
        message = "duplicate binding inventory field"
        raise ValueError(message)
    return value


def decode(text: str, nonce: str) -> Result[tuple[Entry, ...], str]:
    """Read a complete peer inventory without accepting malformed or stale data."""
    if re.fullmatch(r"[0-9a-f]{32}", nonce) is None:
        return Err("invalid binding inventory nonce")
    try:
        value: object = json.loads(text, object_pairs_hook=_fields)
        if not isinstance(value, dict) or set(value) != {"nonce", "entries"}:
            return Err("invalid binding inventory fields")
        if value["nonce"] != nonce or not isinstance(value["entries"], list):
            return Err("binding inventory nonce or entries mismatch")
        result: tuple[Entry, ...] = ()
        for row in value["entries"]:
            match row:
                case [
                    str() as path,
                    ("file" | "directory" | "symlink") as kind,
                    list() as payloads,
                ] if all(isinstance(item, str) for item in payloads):
                    result += (
                        Entry(
                            path,
                            kind,
                            tuple(
                                base64.b64decode(item, validate=True)
                                for item in payloads
                            ),
                        ),
                    )
                case _:
                    return Err("invalid binding inventory entry")
        return Ok(result) if _valid(result) else Err("invalid binding inventory census")
    except (ValueError, UnicodeError, binascii.Error) as exc:
        return Err("cannot decode binding inventory: " + str(exc))


def compare(root: Path, nonce: str, remote: str) -> Result[None, str]:
    """Compare independent complete entries, not just declared or tracked paths."""
    local = source_census(root)
    if isinstance(local, Err):
        return Err("binding source census: " + local.error.message)
    other = decode(remote, nonce)
    if isinstance(other, Err):
        return other
    if not _valid(local.value) or local.value != other.value:
        return Err("binding source inventories differ")
    return Ok(None)
