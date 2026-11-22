# Copyright (c) 2026 agentctl contributors.
"""Validate retained per-killer observations without issuing phase receipts."""

import hashlib
import json
import os
import stat
from dataclasses import dataclass
from functools import reduce
from pathlib import Path

from agentctl.check.evidence import RunEvidence
from agentctl.check.mutants import Mutant
from agentctl.foundation import Err, Ok, Result

type Json = bool | int | float | str | list[Json] | dict[str, Json] | None
MAX_BYTES = 16 * 1024 * 1024
PREFIX = "tests/governance/test_mutants.py::test_corpus["
FAILURES = frozenset({"schema", "copy", "patch", "baseline", "mutant", "spawn"})
BASELINES = frozenset({"passed", "failed:baseline", "failed:spawn"})
MUTATIONS = frozenset({"killed", "not-run", "failed:mutant", "failed:spawn"})


@dataclass(frozen=True, slots=True)
class Killer:
    """The reported status of one exact named killer."""

    node: str
    baseline: str
    mutation: str


@dataclass(frozen=True, slots=True)
class Record:
    """One corpus case and its ordered per-killer statuses."""

    identifier: str
    error: str
    killers: tuple[Killer, ...]


@dataclass(frozen=True, slots=True)
class Report:
    """Decoded values and original bytes' digest for one run."""

    nonce: str
    records: tuple[Record, ...]
    digest: str


def _fields(pairs: list[tuple[str, Json]]) -> dict[str, Json]:
    """Reject duplicate JSON names at every nesting level."""
    values = dict(pairs)
    if len(values) != len(pairs):
        message = "duplicate mutant report field"
        raise ValueError(message)
    return values


def _killer(value: Json) -> Result[Killer, str]:
    """Parse a closed status row without promoting a failed baseline."""
    match value:
        case {
            "node": str() as node,
            "baseline": str() as baseline,
            "mutation": str() as mutation,
            **extra,
        } if not extra:
            if (
                not node
                or baseline not in BASELINES
                or mutation not in MUTATIONS
                or (baseline == "passed") != (mutation != "not-run")
            ):
                return Err("invalid mutant killer status")
            return Ok(Killer(node, baseline, mutation))
        case _:
            return Err("invalid mutant killer fields")


def _record(value: Json) -> Result[Record, str]:
    """Parse a closed record and retain failures without inventing results."""
    match value:
        case {
            "identifier": str() as identifier,
            "error": str() as error,
            "killers": list() as rows,
            **extra,
        } if not extra:
            parsed = tuple(_killer(row) for row in rows)
            initial: Result[tuple[Killer, ...], str] = Ok(())
            match reduce(_append_killer, parsed, initial):
                case Ok(killers):
                    if (
                        not identifier
                        or (error and (error not in FAILURES or killers))
                        or (not error and not killers)
                        or len({item.node for item in killers}) != len(killers)
                    ):
                        return Err("invalid mutant record values")
                    return Ok(Record(identifier, error, killers))
                case Err():
                    return Err("invalid mutant killer record")
        case _:
            return Err("invalid mutant record fields")


def decode(data: bytes, nonce: str) -> Result[Report, str]:
    """Decode bounded original bytes and require the requested run nonce."""
    if not data or len(data) > MAX_BYTES or not nonce:
        return Err("invalid mutant report size or nonce")
    try:
        value = json.loads(data.decode("utf-8"), object_pairs_hook=_fields)
    except (ValueError, UnicodeError, RecursionError):
        return Err("invalid mutant report encoding")
    match value:
        case {"nonce": str() as actual, "records": list() as rows, **extra} if (
            not extra and actual == nonce
        ):
            parsed = tuple(_record(row) for row in rows)
            initial: Result[tuple[Record, ...], str] = Ok(())
            match reduce(_append_record, parsed, initial):
                case Ok(records):
                    if len({item.identifier for item in records}) != len(records):
                        return Err("duplicate mutant report record")
                    return Ok(Report(actual, records, hashlib.sha256(data).hexdigest()))
                case Err():
                    return Err("invalid mutant report record")
        case _:
            return Err("mutant report nonce or fields differ")


def _append[T](
    acc: Result[tuple[T, ...], str], item: Result[T, str]
) -> Result[tuple[T, ...], str]:
    """Retain all decoded rows in their reported order."""
    match (acc, item):
        case (Err() as error, _) | (_, Err() as error):
            return error
        case (Ok(values), Ok(value)):
            return Ok((*values, value))


def _append_killer(
    acc: Result[tuple[Killer, ...], str], item: Result[Killer, str]
) -> Result[tuple[Killer, ...], str]:
    """Accumulate typed killer rows."""
    return _append(acc, item)


def _append_record(
    acc: Result[tuple[Record, ...], str], item: Result[Record, str]
) -> Result[tuple[Record, ...], str]:
    """Accumulate typed corpus records."""
    return _append(acc, item)


def _file_identity(value: os.stat_result) -> tuple[int, int, int, int, int, int]:
    """Exclude access time while retaining identity, size and modification facts."""
    return (
        value.st_dev,
        value.st_ino,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
        value.st_nlink,
    )


def read(path: Path, nonce: str) -> Result[Report, str]:
    """Read a single-link file while checking its opened and path identities."""
    try:
        before = path.lstat()
        if (
            path.is_symlink()
            or path.is_junction()
            or not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or before.st_dev <= 0
            or before.st_ino <= 0
        ):
            return Err("invalid mutant report file")
        with path.open("rb") as stream:
            opened = stream.fileno()
            first = os.fstat(opened)
            data = stream.read(MAX_BYTES + 1)
            last = os.fstat(opened)
        after = path.lstat()
        if (
            path.is_symlink()
            or path.is_junction()
            or _file_identity(before) != _file_identity(after)
            or _file_identity(first) != _file_identity(last)
            or (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
            != (first.st_dev, first.st_ino, first.st_size, first.st_mtime_ns)
            or before.st_nlink != first.st_nlink
            or len(data) != before.st_size
        ):
            return Err("mutant report changed during read")
        return decode(data, nonce)
    except (OSError, ValueError, RuntimeError):
        return Err("mutant report unavailable")


def validate(
    report: Report, records: tuple[Mutant, ...], pytest: RunEvidence
) -> Result[Report, str]:
    """Join statuses to captured corpus, executed cases and aggregate outcomes."""
    expected = {item.identifier: item for item in records}
    observed = {item.identifier: item for item in report.records}
    executed = frozenset(PREFIX + identifier + "]" for identifier in observed)
    actual = frozenset(node for node in pytest.executed if node.startswith(PREFIX))
    if (
        not records
        or not report.nonce
        or len(expected) != len(records)
        or len(observed) != len(report.records)
        or report.nonce != pytest.nonce
        or not pytest.passed <= pytest.executed <= pytest.collected
        or executed != actual
        or not observed.keys() <= expected.keys()
    ):
        return Err("mutant report differs from captured execution")
    if any(
        (
            not item.error
            and tuple(killer.node for killer in item.killers)
            != expected[item.identifier].killers
        )
        or (
            (PREFIX + item.identifier + "]" in pytest.passed)
            != (
                not item.error
                and all(
                    killer.baseline == "passed" and killer.mutation == "killed"
                    for killer in item.killers
                )
            )
        )
        for item in report.records
    ):
        return Err("mutant report differs from captured corpus or pytest outcome")
    return Ok(report)


def failure_scopes(
    report: Report,
    records: tuple[Mutant, ...],
    pytest: RunEvidence,
    owners: tuple[tuple[str, int], ...],
    phases: tuple[int, ...],
) -> Result[tuple[tuple[int, frozenset[str]], ...], str]:
    """Attribute every failed killer to its mutant owner after the evidence join.

    This describes the captured run; it does not authenticate the supplied
    ownership or issue a phase verdict.
    """
    verified = validate(report, records, pytest)
    numbers = frozenset(phases)
    by_id = dict(owners)
    if isinstance(verified, Err):
        return verified
    if (
        not phases
        or len(numbers) != len(phases)
        or len(by_id) != len(owners)
        or by_id.keys() != {item.identifier for item in records}
        or not frozenset(by_id.values()) <= numbers
    ):
        return Err("invalid mutant report ownership")
    return Ok(
        tuple(
            (
                number,
                frozenset(
                    message
                    for item in report.records
                    if by_id[item.identifier] == number
                    for message in (
                        *((item.identifier + ": " + item.error,) if item.error else ()),
                        *(
                            item.identifier
                            + ": "
                            + killer.node
                            + ": "
                            + killer.baseline
                            + ", "
                            + killer.mutation
                            for killer in item.killers
                            if killer.baseline != "passed"
                            or killer.mutation != "killed"
                        ),
                    )
                ),
            )
            for number in phases
        )
    )
