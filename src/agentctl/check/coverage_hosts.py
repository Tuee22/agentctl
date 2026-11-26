# Copyright (c) 2026 agentctl contributors.
"""Declared host classes for sources whose execution is confined to one host."""

import json
import re
import tomllib
from dataclasses import dataclass

from agentctl.foundation import Err, Family, Ok, Result

HOSTS = frozenset({"Linux", "Darwin", "Windows", "WSL"})
SOURCE = re.compile(r"src/agentctl/(?:[a-z0-9_]+/)*[a-z0-9_]+\.py")
COVERAGE_JSON_FORMAT = 3


@dataclass(frozen=True, slots=True)
class HostSource:
    """One source file and the host classes that can execute its native paths."""

    path: str
    hosts: frozenset[str]


@dataclass(frozen=True, slots=True)
class CoverageFact:
    """One source's independently reported missing statements and branches."""

    path: str
    missing_statements: int
    missing_branches: int


@dataclass(frozen=True, slots=True)
class CoverageOwner:
    """The phase consumers declared for one present Python source."""

    path: str
    consumers: frozenset[int]


def pinned_version(text: str) -> Result[str, str]:
    """Read exactly one pinned coverage dependency from the captured project file."""
    try:
        document = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return Err("invalid coverage dependency declaration")
    match document:
        case {"project": {"optional-dependencies": {"dev": list() as dependencies}}}:
            pass
        case _:
            return Err("invalid coverage dependency declaration")
    matching = tuple(
        str(item)
        for item in dependencies
        if isinstance(item, str)
        and re.match(r"(?i)^coverage(?:\[|[<=>!~ ;]|$)", item) is not None
    )
    if len(matching) != 1:
        return Err("coverage dependency is missing or ambiguous")
    pinned = re.fullmatch(r"coverage==([0-9]+(?:\.[0-9]+)+)", matching[0])
    return (
        Ok(str(pinned.group(1)))
        if pinned is not None
        else Err("coverage dependency is not exactly pinned")
    )


def _unique_fields(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """Reject duplicate fields at every JSON object depth."""
    values = dict(pairs)
    if len(values) != len(pairs):
        message = "duplicate coverage report field"
        raise ValueError(message)
    return values


def _lines(value: object) -> Result[frozenset[int], str]:
    """Decode a duplicate-free set of positive source line numbers."""
    if not isinstance(value, list):
        return Err("invalid coverage lines")
    if any(
        isinstance(item, bool) or not isinstance(item, int) or item <= 0
        for item in value
    ):
        return Err("invalid coverage lines")
    numbers = tuple(item for item in value if isinstance(item, int))
    return (
        Ok(frozenset(numbers))
        if len(set(numbers)) == len(numbers)
        else Err("duplicate coverage line")
    )


def _branches(value: object) -> Result[frozenset[tuple[int, int]], str]:
    """Decode source-to-target arcs; negative targets are coverage exit arcs."""
    if not isinstance(value, list):
        return Err("invalid coverage branches")
    branches: tuple[tuple[int, int], ...] = ()
    for arc in value:
        match arc:
            case [int() as start, int() as end] if (
                not isinstance(start, bool)
                and not isinstance(end, bool)
                and start > 0
                and end != 0
            ):
                branches += ((start, end),)
            case _:
                return Err("invalid coverage branches")
    return (
        Ok(frozenset(branches))
        if len(set(branches)) == len(branches)
        else Err("duplicate coverage branch")
    )


def _report_file(path: str, value: object) -> Result[CoverageFact, str]:
    """Check per-file line and branch lists against their reported totals."""
    match value:
        case {
            "executed_lines": executed_lines,
            "missing_lines": missing_lines,
            "executed_branches": executed_branches,
            "missing_branches": missing_branches,
            "summary": {
                "num_statements": int() as statements,
                "missing_lines": int() as line_count,
                "num_branches": int() as branch_total,
                "missing_branches": int() as branch_count,
                **_summary_extra,
            },
            **_file_extra,
        } if SOURCE.fullmatch(path) is not None:
            pass
        case _:
            return Err("invalid coverage file record: " + path)
    if any(
        isinstance(count, bool) or count < 0
        for count in (statements, line_count, branch_total, branch_count)
    ):
        return Err("invalid coverage file counts: " + path)
    lines, missed_lines = _lines(executed_lines), _lines(missing_lines)
    branches, missed_branches = (
        _branches(executed_branches),
        _branches(missing_branches),
    )
    match lines, missed_lines, branches, missed_branches:
        case Ok(found), Ok(missed), Ok(arcs), Ok(missed_arcs):
            if (
                found & missed
                or arcs & missed_arcs
                or len(found) + len(missed) != statements
                or len(missed) != line_count
                or len(arcs) + len(missed_arcs) != branch_total
                or len(missed_arcs) != branch_count
            ):
                return Err("inconsistent coverage file observations: " + path)
            return Ok(CoverageFact(path, line_count, branch_count))
        case _:
            return Err("invalid coverage file observations: " + path)


def _summary_counts(
    value: object, *, file_summary: bool
) -> Result[tuple[int, ...], str]:
    """Check the statement and branch totals emitted by coverage's JSON report."""
    if not isinstance(value, dict):
        return Err("invalid coverage summary")
    fields = (
        "num_statements",
        "covered_lines",
        "missing_lines",
        "num_branches",
        "covered_branches",
        "missing_branches",
    )
    counts = tuple(value.get(field) for field in fields)
    if any(
        isinstance(count, bool) or not isinstance(count, int) or count < 0
        for count in counts
    ):
        return Err("invalid coverage summary counts")
    numbers = tuple(count for count in counts if isinstance(count, int))
    if file_summary and (
        numbers[0] != numbers[1] + numbers[2] or numbers[3] != numbers[4] + numbers[5]
    ):
        return Err("inconsistent coverage summary counts")
    return Ok(numbers)


def _report_counts(
    files: tuple[tuple[str, object], ...], totals: object
) -> Result[None, str]:
    """Reconcile every file summary against the aggregate report totals."""
    summaries = tuple(
        _summary_counts(value.get("summary"), file_summary=True)
        if isinstance(value, dict)
        else Err("invalid coverage file")
        for _path, value in files
    )
    aggregate = _summary_counts(totals, file_summary=False)
    if isinstance(aggregate, Err) or any(isinstance(item, Err) for item in summaries):
        return Err("invalid coverage summaries")
    values = tuple(item.value for item in summaries if isinstance(item, Ok))
    return (
        Ok(None)
        if all(
            sum(row[index] for row in values) == aggregate.value[index]
            for index in (0, 1, 3, 4)
        )
        else Err("coverage file and aggregate counts differ")
    )


def parse_report(text: str, version: str) -> Result[tuple[CoverageFact, ...], str]:
    """Decode one branch-enabled coverage JSON report; this does not authenticate it."""
    try:
        value: object = json.loads(text, object_pairs_hook=_unique_fields)
    except (ValueError, UnicodeError, RecursionError):
        return Err("invalid coverage report JSON")
    match value:
        case {
            "meta": {
                "format": int() as format_version,
                "version": str() as actual,
                "branch_coverage": True,
                **_meta_extra,
            },
            "files": dict() as files,
            "totals": dict() as totals,
            **extra,
        } if (
            not extra
            and format_version == COVERAGE_JSON_FORMAT
            and version
            and actual == version
            and files
        ):
            pass
        case _:
            return Err("invalid coverage report metadata")
    paths = tuple(
        (path.replace("\\", "/"), item)
        for path, item in files.items()
        if isinstance(path, str) and not ("\\" in path and "/" in path)
    )
    if len(paths) != len(files) or len({path for path, _item in paths}) != len(paths):
        return Err("invalid or duplicate coverage source paths")
    observations = tuple(_report_file(path, item) for path, item in paths)
    facts = tuple(item.value for item in observations if isinstance(item, Ok))
    if len(facts) != len(files):
        return Err("invalid coverage report files")
    if (
        totals.get("missing_lines") != sum(fact.missing_statements for fact in facts)
        or totals.get("missing_branches")
        != sum(fact.missing_branches for fact in facts)
        or not isinstance(totals.get("missing_lines"), int)
        or not isinstance(totals.get("missing_branches"), int)
        or isinstance(totals.get("missing_lines"), bool)
        or isinstance(totals.get("missing_branches"), bool)
    ):
        return Err("inconsistent coverage report totals")
    reconciled = _report_counts(paths, totals)
    return (
        reconciled
        if isinstance(reconciled, Err)
        else Ok(tuple(sorted(facts, key=lambda fact: fact.path)))
    )


def parse(text: str) -> Result[tuple[HostSource, ...], str]:
    """Parse the closed manifest, refusing unknown hosts, paths and duplicates."""
    try:
        document = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        return Err("invalid coverage host manifest: " + str(exc))
    match document:
        case {"version": int() as version, "source": list() as values, **extra} if (
            not isinstance(version, bool) and version == 1 and not extra
        ):
            pass
        case _:
            return Err("invalid coverage host manifest fields")
    parsed = tuple(_source(value) for value in values)
    sources = tuple(item.value for item in parsed if isinstance(item, Ok))
    paths = tuple(source.path for source in sources)
    if not values or len(sources) != len(values) or len(set(paths)) != len(paths):
        return Err("invalid or duplicate coverage host source")
    return Ok(sources)


def _source(value: object) -> Result[HostSource, str]:
    """Accept one canonical first-party path and a non-empty known host set."""
    match value:
        case {"path": str() as path, "hosts": list() as hosts, **extra} if (
            not extra
            and SOURCE.fullmatch(path) is not None
            and hosts
            and all(isinstance(host, str) and host in HOSTS for host in hosts)
            and len(set(hosts)) == len(hosts)
        ):
            return Ok(HostSource(path, frozenset(str(host) for host in hosts)))
        case _:
            return Err("invalid coverage host source")


def foreign(sources: tuple[HostSource, ...], family: Family) -> tuple[str, ...]:
    """Name declared sources that this host family cannot execute.

    A WSL-only source is foreign to every native family, including ordinary Linux.
    Undeclared sources are measured on every host.
    """
    return tuple(
        sorted(source.path for source in sources if family not in source.hosts)
    )


def missing(
    sources: tuple[HostSource, ...], present: frozenset[str]
) -> tuple[str, ...]:
    """Name declared sources that are absent from the observed source census."""
    return tuple(
        sorted(source.path for source in sources if source.path not in present)
    )


def attribute(
    facts: tuple[CoverageFact, ...],
    owners: tuple[CoverageOwner, ...],
    host_sources: tuple[HostSource, ...],
    family: Family,
    phases: tuple[int, ...],
) -> Result[tuple[tuple[int, frozenset[str]], ...], str]:
    """Join a complete host report to source consumers without issuing a verdict.

    The caller must authenticate the source census, ownership, host, report and
    execution. Missing or duplicate records are never treated as complete coverage.
    """
    phase_set = frozenset(phases)
    paths = tuple(owner.path for owner in owners)
    reported = tuple(fact.path for fact in facts)
    host_paths = tuple(source.path for source in host_sources)
    if (
        not phases
        or phases != tuple(sorted(phase_set))
        or any(isinstance(phase, bool) or phase < 0 for phase in phases)
        or family not in HOSTS
        or not owners
        or len(set(paths)) != len(paths)
        or len(set(reported)) != len(reported)
        or len(set(host_paths)) != len(host_paths)
        or any(SOURCE.fullmatch(path) is None for path in paths)
        or any(
            not owner.consumers
            or not owner.consumers <= phase_set
            or any(isinstance(number, bool) for number in owner.consumers)
            for owner in owners
        )
        or any(
            source.path not in paths or not source.hosts or not source.hosts <= HOSTS
            for source in host_sources
        )
        or any(
            isinstance(number, bool) or number < 0
            for fact in facts
            for number in (fact.missing_statements, fact.missing_branches)
        )
    ):
        return Err("invalid coverage attribution inputs")
    expected = frozenset(paths) - frozenset(foreign(host_sources, family))
    if frozenset(reported) != expected:
        return Err("coverage report differs from the host source census")
    consumers = {owner.path: owner.consumers for owner in owners}
    return Ok(
        tuple(
            (
                phase,
                frozenset(
                    "coverage incomplete: " + fact.path
                    for fact in facts
                    if phase in consumers[fact.path]
                    and (fact.missing_statements or fact.missing_branches)
                ),
            )
            for phase in phases
        )
    )
