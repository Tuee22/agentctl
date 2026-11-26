# Copyright (c) 2026 agentctl contributors.
"""Fresh execution manifests and canonical byte-level evidence digests."""

import hashlib
import json
import os
import stat
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Literal

from agentctl.check.writeguard import link_text
from agentctl.foundation import Err, Ok, Result

type EvidenceClass = Literal["value", "real", "observer"]
SYMLINK_PAYLOADS = 2
FIRST_SURROGATE = 0xD800
LAST_SURROGATE = 0xDFFF


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


@dataclass(frozen=True, slots=True)
class LegEvidence:
    """One run's ordered tool results, before any phase attribution."""

    nonce: str
    outcomes: tuple[tuple[str, int], ...]


@dataclass(frozen=True, slots=True)
class OracleDetails:
    """Run-specific oracle sources and attributable or shared diagnostics."""

    nonce: str
    sources: tuple[str, ...]
    issues: tuple[tuple[str | None, str], ...]


@dataclass(frozen=True, slots=True)
class ToolSubsteps:
    """Actual command statuses within each subprocess-backed tool leg."""

    nonce: str
    outcomes: tuple[tuple[str, tuple[int, ...]], ...]


def read_tool_substeps(
    path: Path, nonce: str, expected: tuple[tuple[str, int], ...]
) -> Result[ToolSubsteps, EvidenceError]:
    """Read ordered subprocess statuses, refusing ambiguous or invented commands."""
    try:
        if path.is_symlink():
            return Err(EvidenceError("tool substeps are a symlink"))
        decoder = json.JSONDecoder(object_pairs_hook=_unique_fields)
        value: object = decoder.decode(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError, RecursionError) as exc:
        return Err(EvidenceError(str(exc)))
    match value:
        case {"nonce": str() as observed, "outcomes": list() as rows, **extra} if (
            not extra and nonce and observed == nonce
        ):
            outcomes: tuple[tuple[str, tuple[int, ...]], ...] = ()
            for row in rows:
                match row:
                    case [str() as name, list() as codes] if (
                        name
                        and codes
                        and all(
                            isinstance(code, int) and not isinstance(code, bool)
                            for code in codes
                        )
                    ):
                        outcomes += ((name, tuple(int(code) for code in codes)),)
                    case _:
                        return Err(EvidenceError("invalid tool substep record"))
            if (
                len({name for name, _limit in expected}) != len(expected)
                or tuple(name for name, _codes in outcomes)
                != tuple(name for name, _limit in expected)
                or any(
                    limit < 1 or len(codes) > limit
                    for (_name, codes), (_expected, limit) in zip(
                        outcomes, expected, strict=True
                    )
                )
            ):
                return Err(EvidenceError("incomplete or ambiguous tool substeps"))
            return Ok(ToolSubsteps(observed, outcomes))
        case _:
            return Err(EvidenceError("invalid tool substep identity"))


def read_oracle_details(path: Path, nonce: str) -> Result[OracleDetails, EvidenceError]:
    """Read a closed, unambiguous oracle observation for this run."""
    try:
        if path.is_symlink():
            return Err(EvidenceError("oracle details are a symlink"))
        decoder = json.JSONDecoder(object_pairs_hook=_unique_fields)
        value: object = decoder.decode(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError, RecursionError) as exc:
        return Err(EvidenceError(str(exc)))
    return _parse_oracle_details(value, nonce)


def _parse_oracle_details(
    value: object, nonce: str
) -> Result[OracleDetails, EvidenceError]:
    """Validate the decoded closed oracle observation."""
    match value:
        case {
            "nonce": str() as observed,
            "sources": list() as paths,
            "issues": list() as rows,
            **extra,
        } if not extra and nonce and observed == nonce:
            if not all(isinstance(item, str) and item for item in paths):
                return Err(EvidenceError("invalid oracle source list"))
            sources = tuple(str(item) for item in paths)
            if len(sources) != len(set(sources)):
                return Err(EvidenceError("duplicate oracle source"))
            issues: tuple[tuple[str | None, str], ...] = ()
            for row in rows:
                match row:
                    case [str() as source, str() as message] if (
                        source in sources and message
                    ):
                        issues += ((source, message),)
                    case [None, str() as message] if message:
                        issues += ((None, message),)
                    case _:
                        return Err(EvidenceError("invalid oracle issue"))
            return Ok(OracleDetails(observed, sources, issues))
        case _:
            return Err(EvidenceError("invalid oracle observation identity"))


def read_legs(
    path: Path, nonce: str, expected: tuple[str, ...]
) -> Result[LegEvidence, EvidenceError]:
    """Read a complete ordered tool record for this exact run and schedule."""
    try:
        decoder = json.JSONDecoder(object_pairs_hook=_unique_fields)
        value: object = decoder.decode(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError, RecursionError) as exc:
        return Err(EvidenceError(str(exc)))
    return _legs_from_value(value, nonce, expected)


def parse_legs_bytes(
    data: bytes, nonce: str, expected: tuple[str, ...]
) -> Result[LegEvidence, EvidenceError]:
    """Decode already captured bytes with the same closed tool-record schema."""
    try:
        decoder = json.JSONDecoder(object_pairs_hook=_unique_fields)
        value: object = decoder.decode(data.decode("utf-8"))
    except (UnicodeError, ValueError, RecursionError) as exc:
        return Err(EvidenceError(str(exc)))
    return _legs_from_value(value, nonce, expected)


def _legs_from_value(
    value: object, nonce: str, expected: tuple[str, ...]
) -> Result[LegEvidence, EvidenceError]:
    """Validate an ordered result independently of how its bytes were read."""
    match value:
        case {"nonce": str() as observed, "outcomes": list() as rows, **extra}:
            if extra or not nonce or observed != nonce:
                return Err(EvidenceError("tool record identity mismatch"))
            outcomes: tuple[tuple[str, int], ...] = ()
            for row in rows:
                match row:
                    case [str() as name, int() as code] if name and not isinstance(
                        code, bool
                    ):
                        outcomes += ((name, code),)
                    case _:
                        return Err(EvidenceError("invalid tool outcome"))
            names = tuple(name for name, _code in outcomes)
            if not expected or len(set(expected)) != len(expected) or names != expected:
                return Err(EvidenceError("incomplete or ambiguous tool schedule"))
            return Ok(LegEvidence(observed, outcomes))
        case _:
            return Err(EvidenceError("invalid tool record fields"))


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


def _unique_fields(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """Refuse ambiguous JSON objects at every nesting level."""
    result = dict(pairs)
    if len(result) != len(pairs):
        message = "duplicate JSON object field"
        raise ValueError(message)
    return result


def read_manifest(path: Path) -> Result[RunEvidence, EvidenceError]:
    """Read only this run's explicit manifest path."""
    try:
        value: object = json.loads(
            path.read_text(encoding="utf-8"), object_pairs_hook=_unique_fields
        )
    except (OSError, UnicodeError, ValueError, RecursionError) as exc:
        return Err(EvidenceError(str(exc)))
    return parse_manifest(value)


def verify(
    manifest: RunEvidence, nonce: str, mutants: tuple[str, ...]
) -> Result[None, EvidenceError]:
    """Require fresh complete execution and a passing case for every record."""
    if not nonce or manifest.nonce != nonce:
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


def source_target(root: Path, target: Path) -> bool:
    """Accept only targets covered by the source tree's guard snapshot."""
    return target.is_relative_to(root) and target.relative_to(root).parts[:1] != (
        ".git",
    )


def _entry(root: Path, path: Path) -> Result[Entry, EvidenceError]:
    """Read actual bytes, preserving raw link text and rejecting escaping links."""
    label = path.relative_to(root).as_posix()
    try:
        mode = path.lstat().st_mode
        if stat.S_ISLNK(mode):
            target = path.resolve(strict=True)
            if not source_target(root.resolve(), target):
                return Err(EvidenceError("evidence symlink escapes source: " + label))
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


def source_census(root: Path) -> Result[tuple[Entry, ...], EvidenceError]:
    """Read checkout entries, including ignored files, without following links.

    Root Git metadata is handled by the separate read-only baseline observer.
    This census does not establish ownership or protect against concurrent edits;
    callers must join its paths to ownership and the write guard.
    """
    if not root.is_dir():
        return Err(EvidenceError("source census root is not a directory"))
    paths: tuple[Path, ...] = ()
    try:
        for current, directories, files in os.walk(
            root, onerror=_walk_error, followlinks=False
        ):
            directory = Path(current)
            if directory == root and ".git" in directories:
                directories.remove(".git")
            paths += tuple(
                directory / name
                for name in files
                if not (directory == root and name == ".git")
            )
            paths += tuple(directory / name for name in directories)
    except OSError as exc:
        return Err(EvidenceError(str(exc)))
    entries: tuple[Entry, ...] = ()
    for path in paths:
        parsed = _entry(root, path)
        if isinstance(parsed, Err):
            return parsed
        entries += (parsed.value,)
    return Ok(tuple(sorted(entries)))


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


def digest_census(entries: tuple[Entry, ...]) -> Result[str, EvidenceError]:
    """Hash the digest-covered subset of a complete independently guarded census."""
    names = tuple(entry.path for entry in entries)
    if len(names) != len(set(names)):
        return Err(EvidenceError("duplicate census entry"))
    selected = tuple(
        entry
        for entry in entries
        if entry.path in {"src", "tests", "pyproject.toml"}
        or entry.path.startswith(("src/", "tests/"))
    )
    roots = {
        entry.path: entry.kind
        for entry in selected
        if entry.path in {"src", "tests", "pyproject.toml"}
    }
    if roots != {"src": "directory", "tests": "directory", "pyproject.toml": "file"}:
        return Err(EvidenceError("missing or invalid digest roots"))
    if any(
        entry.kind not in {"directory", "file", "symlink"}
        or PurePosixPath(entry.path).as_posix() != entry.path
        or ".." in PurePosixPath(entry.path).parts
        or "\\" in entry.path
        or ":" in entry.path
        or any(
            FIRST_SURROGATE <= ord(character) <= LAST_SURROGATE
            for character in entry.path
        )
        or (entry.kind == "directory" and entry.payloads != (b"",))
        or (entry.kind == "file" and len(entry.payloads) != 1)
        or (entry.kind == "symlink" and len(entry.payloads) != SYMLINK_PAYLOADS)
        for entry in selected
    ):
        return Err(EvidenceError("invalid digest census entry"))
    kinds = {entry.path: entry.kind for entry in selected}
    if any(
        PurePosixPath(entry.path).parent.as_posix() != "."
        and kinds.get(PurePosixPath(entry.path).parent.as_posix()) != "directory"
        for entry in selected
    ):
        return Err(EvidenceError("digest census parent missing or not a directory"))
    hashed = hashlib.sha256()
    for entry in sorted(selected):
        for field in (
            entry.path.encode("utf-8"),
            entry.kind.encode("ascii"),
            *entry.payloads,
        ):
            hashed.update(len(field).to_bytes(8, "big"))
            hashed.update(field)
    return Ok(hashed.hexdigest())
