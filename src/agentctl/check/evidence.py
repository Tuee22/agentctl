# Copyright (c) 2026 agentctl contributors.
"""Fresh execution manifests and canonical byte-level evidence digests."""

import hashlib
import json
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from agentctl.check.writeguard import link_text
from agentctl.result import Err, Ok, Result

type EvidenceClass = Literal["value", "real", "observer"]


@dataclass(frozen=True, slots=True)
class EvidenceError:
    """An untrusted, incomplete or unreadable evidence boundary."""

    message: str


@dataclass(frozen=True, slots=True)
class RunEvidence:
    """Separate observations of collection, execution, outcomes and classes."""

    nonce: str
    collected: frozenset[str]
    executed: frozenset[str]
    passed: frozenset[str]
    forbidden: tuple[str, ...]
    classes: tuple[tuple[str, EvidenceClass], ...]


@dataclass(frozen=True, slots=True, order=True)
class Entry:
    """One canonical relative path, entry kind and literal byte payloads."""

    path: str
    kind: Literal["directory", "file", "symlink"]
    payloads: tuple[bytes, ...]


def classification(value: object) -> Result[EvidenceClass, EvidenceError]:
    """Narrow only the three executable evidence classes."""
    if isinstance(value, str) and value in {"value", "real", "observer"}:
        return Ok(value)
    return Err(EvidenceError("unknown executable evidence class"))


def _ids(value: object) -> Result[frozenset[str], EvidenceError]:
    """Reject duplicates and non-string node ids at the JSON boundary."""
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        return Err(EvidenceError("manifest node ids must be string arrays"))
    parsed = frozenset(str(item) for item in value)
    return (
        Ok(parsed)
        if len(parsed) == len(value)
        else Err(EvidenceError("duplicate manifest node id"))
    )


def parse_manifest(value: object) -> Result[RunEvidence, EvidenceError]:
    """Parse a closed manifest without promoting collection into execution."""
    if not isinstance(value, dict) or set(value) != {
        "nonce",
        "collected",
        "executed",
        "passed",
        "forbidden",
        "classes",
    }:
        return Err(EvidenceError("invalid manifest fields"))
    nonce, forbidden, classes = value["nonce"], value["forbidden"], value["classes"]
    if (
        not isinstance(nonce, str)
        or not isinstance(forbidden, list)
        or not all(isinstance(item, str) for item in forbidden)
        or not isinstance(classes, dict)
    ):
        return Err(EvidenceError("invalid manifest identity or observations"))
    sets = tuple(_ids(value[name]) for name in ("collected", "executed", "passed"))
    for parsed in sets:
        if isinstance(parsed, Err):
            return parsed
    collected, executed, passed = (
        parsed.value for parsed in sets if isinstance(parsed, Ok)
    )
    observed: tuple[tuple[str, EvidenceClass], ...] = ()
    for node, item in classes.items():
        parsed_class = classification(item)
        if isinstance(parsed_class, Err):
            return parsed_class
        observed += ((str(node), parsed_class.value),)
    if frozenset(str(node) for node in classes) != collected:
        return Err(EvidenceError("manifest classes do not match collection"))
    return Ok(
        RunEvidence(
            nonce,
            collected,
            executed,
            passed,
            tuple(str(item) for item in forbidden),
            tuple(sorted(observed)),
        )
    )


def read_manifest(path: Path) -> Result[RunEvidence, EvidenceError]:
    """Read only this run's explicit manifest path."""
    try:
        value: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return Err(EvidenceError(str(exc)))
    return parse_manifest(value)


def verify(
    manifest: RunEvidence, nonce: str, mutants: tuple[str, ...]
) -> Result[None, EvidenceError]:
    """Require fresh complete execution and a passing case for every record."""
    if manifest.nonce != nonce:
        return Err(EvidenceError("manifest nonce mismatch"))
    if (
        manifest.forbidden
        or not manifest.collected
        or manifest.collected != manifest.executed
        or manifest.collected != manifest.passed
    ):
        return Err(EvidenceError("incomplete or forbidden pytest manifest"))
    expected = frozenset(
        "tests/governance/test_mutants.py::test_corpus[" + identifier + "]"
        for identifier in mutants
    )
    if not expected <= manifest.passed:
        return Err(EvidenceError("missing current mutant case"))
    return Ok(None)


def _entry(root: Path, path: Path) -> Result[Entry, EvidenceError]:
    """Read actual bytes, preserving raw link text and rejecting escaping links."""
    label = path.relative_to(root).as_posix()
    try:
        mode = path.lstat().st_mode
        if stat.S_ISLNK(mode):
            target = path.resolve(strict=True)
            if not target.is_relative_to(root.resolve()):
                return Err(EvidenceError("evidence symlink escapes checkout: " + label))
            return Ok(Entry(label, "symlink", (link_text(path), target.read_bytes())))
        if stat.S_ISDIR(mode):
            return Ok(Entry(label, "directory", (b"",)))
        if stat.S_ISREG(mode):
            return Ok(Entry(label, "file", (path.read_bytes(),)))
    except (OSError, UnicodeError, RuntimeError) as exc:
        return Err(EvidenceError(str(exc)))
    return Err(EvidenceError("unsupported evidence entry: " + label))


def _walk_error(error: OSError) -> None:
    """Make an unreadable covered directory a typed digest failure."""
    raise error


def digest(root: Path) -> Result[str, EvidenceError]:
    """Hash sorted entry fields, each prefixed with its eight-byte big-endian size."""
    paths = (root / "src", root / "tests", root / "pyproject.toml")
    try:
        for directory in (root / "src", root / "tests"):
            for current, directories, files in os.walk(directory, onerror=_walk_error):
                paths += tuple(Path(current) / name for name in (*directories, *files))
    except OSError as exc:
        return Err(EvidenceError(str(exc)))
    entries: tuple[Entry, ...] = ()
    for path in paths:
        parsed = _entry(root, path)
        if isinstance(parsed, Err):
            return parsed
        entries += (parsed.value,)
    hashed = hashlib.sha256()
    for entry in sorted(entries):
        for field in (
            entry.path.encode("utf-8"),
            entry.kind.encode("ascii"),
            *entry.payloads,
        ):
            hashed.update(len(field).to_bytes(8, "big"))
            hashed.update(field)
    return Ok(hashed.hexdigest())
