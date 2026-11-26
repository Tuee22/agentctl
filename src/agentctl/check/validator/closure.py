# Copyright (c) 2026 agentctl contributors.
"""Join plan declarations to real paths, current execution and acceptance rows."""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Literal

from agentctl.check.evidence import EvidenceError, RunEvidence, digest
from agentctl.check.lanes import Declaration, LaneState, parse_phase_lane, refusals
from agentctl.check.mutants import Mutant
from agentctl.check.plan_data import Phase, field, phases, section, table
from agentctl.foundation import Err, Ok, Result

INTEGRITY_COLUMNS = ("Requirement", "Oracle", "Observer", "Mutants", "Tests")
OBSERVATION_FIELDS = 2
EVIDENCE_FIELDS = 6


@dataclass(frozen=True, slots=True)
class ClosureError:
    """A completion claim has no qualifying current subject or observation."""

    message: str


@dataclass(frozen=True, slots=True)
class IntegrityRow:
    """One structurally valid, independently declared integrity claim."""

    requirement: str
    oracles: tuple[str, ...]
    observations: tuple[tuple[str, str], ...]
    mutants: tuple[str, ...]
    tests: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Subject:
    """A validator's discovered inputs and the status of their owning capability."""

    name: str
    owner: str
    paths: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class MutantOwnerPolicy:
    """Legacy prefix rules or complete explicit source-derived ownership."""

    prefixes: tuple[tuple[str, tuple[str, ...]], ...]
    owners: tuple[tuple[str, int], ...] | None


@dataclass(frozen=True, slots=True)
class CapturedPolicy:
    """Guarded plan policy texts and their independently joined mutant owners."""

    owners: tuple[tuple[str, int], ...] | None
    standards: str
    overview: str
    regular_files: frozenset[str] | None = None
    symlinks: frozenset[str] = frozenset()
    directories: frozenset[str] = frozenset()
    covered_digest: Result[str, EvidenceError] | None = None


@dataclass(frozen=True, slots=True)
class IntegrityAttribution:
    """Complete static diagnostics and their independently derived phase failures."""

    diagnostics: tuple[str, ...]
    phases: tuple[tuple[int, frozenset[str]], ...]


@dataclass(frozen=True, slots=True)
class _IntegrityContext:
    """Captured inputs shared by every independently attributed row."""

    requirements: frozenset[str]
    policy: MutantOwnerPolicy
    available: Mapping[str, Mutant]
    captured: CapturedPolicy


def tokens(value: str) -> tuple[str, ...]:
    """Read explicit backtick citations without interpreting prose as artifacts."""
    return tuple(str(token) for token in re.findall(r"`([^`]+)`", value))


def test_ids(value: str) -> tuple[str, ...]:
    """Select pytest and Haskell case citations from a declaration."""
    return tuple(
        token
        for token in tokens(value)
        if token.startswith("haskell:")
        or (token.startswith("tests/") and "::" in token)
    )


def mutant_ids(value: str) -> tuple[str, ...]:
    """Read the closed mutation-id spelling from fields and table cells."""
    return tuple(str(token) for token in re.findall(r"`(M-[a-z0-9-]+)`", value))


def integrity_row(cells: tuple[str, ...]) -> Result[IntegrityRow, ClosureError]:
    """Validate row width, requirement identity, citations and evidence classes."""
    if len(cells) != len(INTEGRITY_COLUMNS):
        return Err(ClosureError("integrity row has invalid columns"))
    requirement = re.match(r"(R\d+(?:\.\d+)?) — \S", cells[0])
    observations = tuple(
        tuple(part.strip().split(":", 1)) for part in cells[2].split(";")
    )
    if (
        requirement is None
        or not observations
        or any(
            len(item) != OBSERVATION_FIELDS
            or item[0] not in {"value", "real", "observer", "owed"}
            or not item[1].strip()
            for item in observations
        )
    ):
        return Err(
            ClosureError("integrity row has invalid requirement or evidence class")
        )
    tests = test_ids(cells[4])
    oracles = tokens(cells[1])
    mutants = mutant_ids(cells[3])
    if (
        not tests
        or (not oracles and not cells[1].startswith("none — "))
        or (not mutants and not cells[3].startswith("none — "))
    ):
        return Err(ClosureError("integrity row has missing citations"))
    return Ok(
        IntegrityRow(
            requirement[1],
            oracles,
            tuple((item[0], item[1].strip()) for item in observations),
            mutants,
            tests,
        )
    )


def _captured_path_present(
    root: Path, path: Path, captured: CapturedPolicy | None
) -> bool:
    """Check a captured source entry or independently resolve a live path."""
    if captured is not None and captured.regular_files is not None:
        return (
            path.as_posix()
            in captured.regular_files | captured.symlinks | captured.directories
        )
    return (root / path).exists() and (root / path).resolve().is_relative_to(
        root.resolve()
    )


def cited_paths(
    root: Path,
    declarations: tuple[Phase, ...],
    *,
    captured: CapturedPolicy | None = None,
) -> tuple[str, ...]:
    """Require every Done sprint's implementation to resolve to a durable artifact."""
    problems: tuple[str, ...] = ()
    for phase in declarations:
        for sprint in phase.sprints:
            if sprint.tag != "Done":
                continue
            implementation = field(sprint.text, "Implementation")
            paths = tokens(implementation)
            invalid = not paths and not implementation.startswith("none — ")
            for name in paths:
                path = Path(name)
                invalid = (
                    invalid
                    or path.is_absolute()
                    or not path.parts
                    or ".." in path.parts
                    or ".build" in path.parts
                    or path.parts[0] == "logs"
                    or path.suffix == ".log"
                    or not _captured_path_present(root, path, captured)
                )
            if invalid:
                problems += ("plan.cited-paths: " + sprint.identifier,)
    return problems


def matching(citation: str, observed: frozenset[str]) -> frozenset[str]:
    """Expand a cited parametrized method only to its actually collected cases."""
    return frozenset(
        node for node in observed if node == citation or node.startswith(citation + "[")
    )


def cited_ids(
    declarations: tuple[Phase, ...],
    evidence: RunEvidence,
    haskell: frozenset[str] = frozenset(),
) -> tuple[str, ...]:
    """Join Done citations to this run, including every collected parameter case."""
    problems: tuple[str, ...] = ()
    for phase in declarations:
        for sprint in phase.sprints:
            if sprint.tag != "Done":
                continue
            citations = test_ids(field(sprint.text, "Validation tests"))
            invalid = not citations
            for citation in citations:
                cases = matching(citation, evidence.collected | haskell)
                invalid = invalid or not cases or not cases <= evidence.passed | haskell
            if invalid:
                problems += ("plan.cited-ids: " + sprint.identifier,)
    return problems


def _prefixes_from_text(text: str) -> dict[str, tuple[str, ...]]:
    """Parse the authoritative phase-to-prefix table from supplied text."""
    return {
        filename: tuple(re.findall(r"`(M-[a-z]+-)`", line))
        for line in text.splitlines()
        if "| `M-" in line
        for filename in re.findall(r"\((phase-\d+-[a-z-]+\.md)\)", line)
    }


def _prefixes(root: Path) -> dict[str, tuple[str, ...]]:
    """Read the authoritative phase-to-prefix table rather than a parallel list."""
    return _prefixes_from_text(
        (root / "DEVELOPMENT_PLAN/development_plan_standards.md").read_text(
            encoding="utf-8"
        )
    )


def _owed(
    declarations: tuple[Phase, ...], rows: tuple[tuple[Phase, IntegrityRow], ...]
) -> bool:
    """Require both directions of every source-phase/acceptance confirmation."""
    owed: set[tuple[str, str, str]] = set()
    confirmed: set[tuple[str, str, str]] = set()
    for phase, row in rows:
        if field(phase.text, "Gate kind") == "self-verifying":
            for kind, target in row.observations:
                if kind == "owed":
                    destinations = tuple(
                        candidate
                        for candidate in declarations
                        if candidate.path.name.endswith("-" + target + ".md")
                        and field(candidate.text, "Gate kind") == "host-acceptance"
                    )
                    if len(destinations) != 1:
                        return False
                    owed.add(
                        (row.requirement, phase.path.name, destinations[0].path.name)
                    )
    for phase in declarations:
        for line in section(phase.text, "Confirms").splitlines():
            identifier = re.match(r"- (R\d+(?:\.\d+)?) — ", line)
            if identifier:
                confirmed.update(
                    (identifier[1], source, phase.path.name)
                    for source in re.findall(r"\((phase-\d+-[a-z-]+\.md)\)", line)
                )
    return owed == confirmed


def _executed(row: IntegrityRow, evidence: RunEvidence) -> bool:
    """Join each cited case and its actual evidence class to one claim."""
    cases = tuple(matching(citation, evidence.collected) for citation in row.tests)
    selected = frozenset(node for nodes in cases for node in nodes)
    classes = dict(evidence.classes)
    observed = frozenset(classes[node] for node in selected if node in classes)
    expected = frozenset(kind for kind, _detail in row.observations if kind != "owed")
    return (
        all(cases)
        and selected <= evidence.passed
        and selected <= classes.keys()
        and (not expected or observed == expected)
    )


def execution_scopes(
    declarations: tuple[Phase, ...], records: tuple[Mutant, ...], observed: RunEvidence
) -> tuple[tuple[int, frozenset[str]], ...]:
    """Attribute failed applicable execution rows to their owning phase."""
    available = frozenset(record.identifier for record in records)
    return tuple(
        (
            phase.number,
            frozenset(
                "gate integrity execution: " + row.value.requirement
                for cells in table(section(phase.text, "Gate Integrity"))[1:]
                for row in (integrity_row(cells),)
                if isinstance(row, Ok)
                and (
                    field(phase.text, "Status") == "Done"
                    or any(identifier in available for identifier in row.value.mutants)
                )
                and not _executed(row.value, observed)
            ),
        )
        for phase in declarations
    )


def _canonical_oracle(name: str) -> bool:
    """Reject aliases and paths outside the checkout on every host."""
    path = PurePosixPath(name)
    return bool(
        name
        and path.parts
        and not path.is_absolute()
        and path.as_posix() == name
        and all(part not in {".", ".."} for part in path.parts)
        and "\\" not in name
        and ":" not in name
    )


def _oracle_present(root: Path, name: str) -> bool:
    """Require a canonical checkout-local file, including after symlink resolution."""
    if not _canonical_oracle(name):
        return False
    try:
        candidate = (root / name).resolve(strict=True)
        return (
            candidate.is_relative_to(root.resolve(strict=True)) and candidate.is_file()
        )
    except (OSError, RuntimeError):
        return False


def _captured_oracle_present(root: Path, name: str, policy: CapturedPolicy) -> bool:
    """Use census files and links whose containment was checked during capture."""
    if policy.regular_files is None:
        return _oracle_present(root, name)
    return _canonical_oracle(name) and (
        name in policy.regular_files or name in policy.symlinks
    )


def _row_diagnostics(
    phase: Phase,
    row: IntegrityRow,
    requirements: frozenset[str],
    policy: MutantOwnerPolicy,
) -> tuple[str, ...]:
    """Name unresolved requirement and mutant ownership for one row."""
    missing = (
        (
            "plan.gate-integrity: "
            + phase.path.name
            + ": undeclared requirement "
            + row.requirement,
        )
        if row.requirement not in requirements
        else ()
    )
    return (
        *missing,
        *(
            "plan.gate-integrity: "
            + phase.path.name
            + (
                ": no authorized prefix for "
                if policy.owners is None
                else ": no matching source owner for "
            )
            + identifier
            for identifier in row.mutants
            if not _mutant_owned(phase, identifier, policy)
        ),
    )


def _mutant_owned(phase: Phase, identifier: str, policy: MutantOwnerPolicy) -> bool:
    """Require an exact owner when supplied; never fall back for missing claims."""
    if policy.owners is None:
        return identifier.startswith(dict(policy.prefixes).get(phase.path.name, ()))
    return (identifier, phase.number) in policy.owners


def _incomplete_owners(
    owners: tuple[tuple[str, int], ...] | None, available: dict[str, Mutant]
) -> bool:
    """Refuse duplicate, omitted or invented source ownership claims."""
    if owners is None:
        return False
    identifiers = tuple(identifier for identifier, _owner in owners)
    return len(set(identifiers)) != len(identifiers) or frozenset(
        identifiers
    ) != frozenset(available)


def _owner_diagnostics(
    owners: tuple[tuple[str, int], ...] | None, available: dict[str, Mutant]
) -> tuple[str, ...]:
    return (
        ("plan.gate-integrity: incomplete or duplicate source mutant owners",)
        if _incomplete_owners(owners, available)
        else ()
    )


def _join_diagnostics(
    available: dict[str, Mutant],
    declared: set[str],
    declarations: tuple[Phase, ...],
    rows: tuple[tuple[Phase, IntegrityRow], ...],
) -> tuple[str, ...]:
    """Report missing corpus ownership and inconsistent owed confirmations."""
    return (
        *(
            "plan.gate-integrity: undeclared corpus mutant " + identifier
            for identifier in sorted(set(available) - declared)
        ),
        *(
            ("plan.gate-integrity: owed evidence confirmation mismatch",)
            if not _owed(declarations, rows)
            else ()
        ),
    )


def undeclared_mutant_failures(
    declarations: tuple[Phase, ...],
    records: tuple[Mutant, ...],
    owners: tuple[tuple[str, int], ...],
) -> Result[tuple[tuple[int, frozenset[str]], ...], str]:
    """Attribute omitted corpus declarations only with complete source owners."""
    numbers = tuple(phase.number for phase in declarations)
    identifiers = tuple(record.identifier for record in records)
    owner_map = dict(owners)
    if (
        not numbers
        or len(set(numbers)) != len(numbers)
        or len(set(identifiers)) != len(identifiers)
        or len(owner_map) != len(owners)
        or frozenset(owner_map) != frozenset(identifiers)
        or any(owner not in numbers for owner in owner_map.values())
    ):
        return Err("invalid mutant declarations or source owners")
    declared = frozenset(
        (identifier, phase.number)
        for phase in declarations
        for sprint in phase.sprints
        for identifier in mutant_ids(field(sprint.text, "Mutants"))
    )
    return Ok(
        tuple(
            (
                number,
                frozenset(
                    "undeclared corpus mutant: " + identifier
                    for identifier in identifiers
                    if (identifier, owner_map[identifier]) not in declared
                    and owner_map[identifier] == number
                ),
            )
            for number in numbers
        )
    )


def gate_integrity(
    root: Path,
    declarations: tuple[Phase, ...],
    records: tuple[Mutant, ...],
    evidence: RunEvidence | None = None,
    *,
    mutant_owners: tuple[tuple[str, int], ...] | CapturedPolicy | None = None,
) -> tuple[str, ...]:
    """Check declarations; callers must independently establish explicit owners."""
    owners = (
        mutant_owners.owners
        if isinstance(mutant_owners, CapturedPolicy)
        else mutant_owners
    )
    prefixes = (
        _prefixes_from_text(mutant_owners.standards)
        if isinstance(mutant_owners, CapturedPolicy)
        else _prefixes(root)
    )
    overview = (
        mutant_owners.overview
        if isinstance(mutant_owners, CapturedPolicy)
        else (root / "DEVELOPMENT_PLAN/00-overview.md").read_text(encoding="utf-8")
    )
    policy = MutantOwnerPolicy(tuple(sorted(prefixes.items())), owners)
    requirements = frozenset(
        row[0]
        for row in table(
            section(
                overview,
                "Requirements",
            )
        )[1:]
    )
    available = {record.identifier: record for record in records}
    rows: tuple[tuple[Phase, IntegrityRow], ...] = ()
    problems = _owner_diagnostics(owners, available)
    bad = bool(problems)
    declared: set[str] = set()
    for phase in declarations:
        matrix = table(section(phase.text, "Gate Integrity"))
        if not matrix or matrix[0] != INTEGRITY_COLUMNS or len(matrix) == 1:
            problems += ("plan.gate-integrity: " + phase.path.name + ": invalid table",)
            continue
        for cells in matrix[1:]:
            parsed = integrity_row(cells)
            if isinstance(parsed, Err):
                label = cells[0] if cells else "empty row"
                problems += (
                    "plan.gate-integrity: "
                    + phase.path.name
                    + ": "
                    + label
                    + ": "
                    + parsed.error.message,
                )
                continue
            rows += ((phase, parsed.value),)
            problems += _row_diagnostics(phase, parsed.value, requirements, policy)
            bad = (
                bad
                or parsed.value.requirement not in requirements
                or any(
                    not _mutant_owned(phase, identifier, policy)
                    for identifier in parsed.value.mutants
                )
            )
        for sprint in phase.sprints:
            identifiers = mutant_ids(field(sprint.text, "Mutants"))
            declared.update(identifiers)
            bad = bad or any(
                not _mutant_owned(phase, identifier, policy)
                for identifier in identifiers
            )
            if sprint.tag == "Done":
                bad = bad or any(
                    identifier not in available for identifier in identifiers
                )
    problems += _join_diagnostics(available, declared, declarations, rows)
    bad = bad or not set(available) <= declared or not _owed(declarations, rows)
    for phase, row in rows:
        applicable = field(phase.text, "Status") == "Done" or any(
            identifier in available for identifier in row.mutants
        )
        if not applicable:
            continue
        bad = bad or any(
            not (
                _captured_oracle_present(root, name, mutant_owners)
                if isinstance(mutant_owners, CapturedPolicy)
                else _oracle_present(root, name)
            )
            for name in row.oracles
        )
        bad = bad or any(
            identifier not in available
            or not set(available[identifier].killers) <= set(row.tests)
            for identifier in row.mutants
        )
        if evidence is not None:
            bad = bad or not _executed(row, evidence)
    return (
        *problems,
        *(("plan.gate-integrity: declaration or execution join",) if bad else ()),
    )


def undeclared_only_integrity(
    declarations: tuple[Phase, ...],
    records: tuple[Mutant, ...],
    captured: CapturedPolicy,
) -> Result[tuple[str, ...], str]:
    """Prove the complete static integrity failure consists only of omissions.

    The actual corpus and declarations remain intact. This observation does not
    authenticate the census or owner mapping and does not issue a phase verdict.
    """
    owners = captured.owners
    if owners is None or captured.regular_files is None:
        return Err("captured integrity policy unavailable")
    scoped = undeclared_mutant_failures(declarations, records, owners)
    if isinstance(scoped, Err):
        return scoped
    missing = frozenset(
        failure.removeprefix("undeclared corpus mutant: ")
        for _number, failures in scoped.value
        for failure in failures
    )
    if not missing:
        return Err("no undeclared corpus mutants")
    parsed_rows = tuple(
        (phase, tuple(integrity_row(cells) for cells in matrix[1:]))
        for phase in declarations
        for matrix in (table(section(phase.text, "Gate Integrity")),)
        if matrix and matrix[0] == INTEGRITY_COLUMNS and len(matrix) > 1
    )
    if len(parsed_rows) != len(declarations) or any(
        isinstance(row, Err) for _phase, rows in parsed_rows for row in rows
    ):
        return Err("invalid integrity tables")
    rows = tuple(
        (phase, row.value)
        for phase, values in parsed_rows
        for row in values
        if isinstance(row, Ok)
    )
    requirements = frozenset(
        row[0] for row in table(section(captured.overview, "Requirements"))[1:]
    )
    policy = MutantOwnerPolicy((), owners)
    available = {record.identifier: record for record in records}
    sprint_valid = all(
        all(_mutant_owned(phase, identifier, policy) for identifier in identifiers)
        and (sprint.tag != "Done" or all(item in available for item in identifiers))
        for phase in declarations
        for sprint in phase.sprints
        for identifiers in (mutant_ids(field(sprint.text, "Mutants")),)
    )
    rows_valid = all(
        row.requirement in requirements
        and all(_mutant_owned(phase, identifier, policy) for identifier in row.mutants)
        and (
            not (
                field(phase.text, "Status") == "Done"
                or any(identifier in available for identifier in row.mutants)
            )
            or (
                all(
                    _captured_oracle_present(Path(), name, captured)
                    for name in row.oracles
                )
                and all(
                    identifier in available
                    and set(available[identifier].killers) <= set(row.tests)
                    for identifier in row.mutants
                )
            )
        )
        for phase, row in rows
    )
    expected = (
        *(
            "plan.gate-integrity: undeclared corpus mutant " + identifier
            for identifier in sorted(missing)
        ),
        "plan.gate-integrity: declaration or execution join",
    )
    actual = gate_integrity(Path(), declarations, records, mutant_owners=captured)
    return (
        Ok(expected)
        if sprint_valid
        and rows_valid
        and _owed(declarations, rows)
        and actual == expected
        else Err("integrity failure has additional or ambiguous causes")
    )


def _row_integrity_failures(
    phase: Phase,
    row: IntegrityRow,
    context: _IntegrityContext,
) -> frozenset[str]:
    """Retain every static defect owned by one valid integrity row."""
    requirements, policy, available, captured = (
        context.requirements,
        context.policy,
        context.available,
        context.captured,
    )
    applicable = field(phase.text, "Status") == "Done" or any(
        identifier in available for identifier in row.mutants
    )
    return frozenset(
        (
            *(
                ("gate integrity requirement: " + row.requirement,)
                if row.requirement not in requirements
                else ()
            ),
            *(
                "gate integrity mutant owner: " + identifier
                for identifier in row.mutants
                if not _mutant_owned(phase, identifier, policy)
            ),
            *(
                "gate integrity missing oracle: " + name
                for name in row.oracles
                if applicable and not _captured_oracle_present(Path(), name, captured)
            ),
            *(
                "gate integrity missing mutant: " + identifier
                for identifier in row.mutants
                if applicable and identifier not in available
            ),
            *(
                "gate integrity killer citation: " + identifier
                for identifier in row.mutants
                if applicable
                and identifier in available
                and not set(available[identifier].killers) <= set(row.tests)
            ),
        )
    )


def _phase_integrity_failures(
    phase: Phase,
    rows: tuple[IntegrityRow, ...],
    context: _IntegrityContext,
) -> frozenset[str]:
    """Join row and sprint declarations without discarding individual defects."""
    row_failures = frozenset(
        failure
        for row in rows
        for failure in _row_integrity_failures(phase, row, context)
    )
    sprint_failures = frozenset(
        failure
        for sprint in phase.sprints
        for identifier in mutant_ids(field(sprint.text, "Mutants"))
        for failure in (
            *(
                ("gate integrity mutant owner: " + identifier,)
                if not _mutant_owned(phase, identifier, context.policy)
                else ()
            ),
            *(
                ("gate integrity missing mutant: " + identifier,)
                if sprint.tag == "Done" and identifier not in context.available
                else ()
            ),
        )
    )
    return row_failures | sprint_failures


def scoped_integrity_failures(
    declarations: tuple[Phase, ...],
    records: tuple[Mutant, ...],
    captured: CapturedPolicy,
) -> Result[IntegrityAttribution, str]:
    """Attribute a complete static integrity result without changing the corpus.

    Malformed tables, uncertain ownership or cross-phase owed evidence remain
    shared. The caller must authenticate the captured inputs and execution.
    """
    owners = captured.owners
    if owners is None or captured.regular_files is None:
        return Err("captured integrity policy unavailable")
    missing = undeclared_mutant_failures(declarations, records, owners)
    if (
        isinstance(missing, Err)
        or any(isinstance(phase.number, bool) for phase in declarations)
        or any(isinstance(owner, bool) for _identifier, owner in owners)
    ):
        return Err("invalid integrity ownership")
    parsed = tuple(
        (phase, tuple(integrity_row(cells) for cells in matrix[1:]))
        for phase in declarations
        for matrix in (table(section(phase.text, "Gate Integrity")),)
        if matrix and matrix[0] == INTEGRITY_COLUMNS and len(matrix) > 1
    )
    if len(parsed) != len(declarations) or any(
        isinstance(row, Err) for _phase, rows in parsed for row in rows
    ):
        return Err("invalid integrity tables")
    rows = tuple(
        (phase, row.value)
        for phase, values in parsed
        for row in values
        if isinstance(row, Ok)
    )
    if not _owed(declarations, rows):
        return Err("integrity owed evidence is ambiguous")
    requirements = frozenset(
        row[0] for row in table(section(captured.overview, "Requirements"))[1:]
    )
    policy = MutantOwnerPolicy((), owners)
    available = {record.identifier: record for record in records}
    context = _IntegrityContext(requirements, policy, available, captured)
    omitted = dict(missing.value)
    scoped = tuple(
        (
            phase.number,
            omitted[phase.number]
            | _phase_integrity_failures(
                phase,
                tuple(row for owner, row in rows if owner == phase),
                context,
            ),
        )
        for phase in declarations
    )
    declared = {
        identifier
        for phase in declarations
        for sprint in phase.sprints
        for identifier in mutant_ids(field(sprint.text, "Mutants"))
    }
    expected = (
        *(
            problem
            for phase, row in rows
            for problem in _row_diagnostics(phase, row, requirements, policy)
        ),
        *_join_diagnostics(available, declared, declarations, rows),
        *(
            ("plan.gate-integrity: declaration or execution join",)
            if any(failures for _number, failures in scoped)
            else ()
        ),
    )
    actual = gate_integrity(Path(), declarations, records, mutant_owners=captured)
    return (
        Ok(IntegrityAttribution(expected, scoped))
        if actual == expected
        else Err("integrity diagnostics and attribution differ")
    )


def evidence_rows(
    root: Path,
    declarations: tuple[Phase, ...],
    *,
    observed_digest: Result[str, EvidenceError] | None = None,
) -> tuple[str, ...]:
    """Validate terminal rows against the covered tree, lane and literal gate."""
    current = digest(root) if observed_digest is None else observed_digest
    if isinstance(current, Err):
        return ("plan.evidence-rows: " + current.error.message,)
    problems: tuple[str, ...] = ()
    for phase in declarations:
        if field(phase.text, "Gate kind") != "host-acceptance":
            continue
        row = field(phase.text, "Gate evidence")
        covers = field(phase.text, "Evidence covers")
        if covers == "phase input closure and verified prerequisite receipts":
            if row != "none recorded" or field(phase.text, "Status") not in {
                "Planned",
                "Active",
            }:
                problems += ("plan.evidence-rows: " + phase.path.name,)
            continue
        fields = tuple(part.strip() for part in row.split(" ; "))
        valid = row == "none recorded" and field(phase.text, "Status") != "Done"
        if len(fields) == EVIDENCE_FIELDS:
            valid = (
                field(phase.text, "Status") == "Done"
                and re.fullmatch(r"\d{4}-\d{2}-\d{2}", fields[0]) is not None
                and fields[1] == field(phase.text, "Host lane")
                and fields[2:4] == ("agentctl check", "pass")
                and fields[4] == "tree " + current.value
                and bool(fields[5])
            )
        if (
            field(phase.text, "Evidence covers") != "`src/` `tests/` `pyproject.toml`"
            or not valid
        ):
            problems += ("plan.evidence-rows: " + phase.path.name,)
    return problems


def lane_declarations(declarations: tuple[Phase, ...]) -> tuple[Declaration, ...]:
    """Project the exact header fields used by the lane evaluator."""
    return tuple(
        Declaration(
            phase.path.name,
            field(phase.text, "Status"),
            field(phase.text, "Gate kind"),
            field(phase.text, "Host lane"),
        )
        for phase in declarations
    )


def lanes(
    declarations: tuple[Phase, ...], states: tuple[LaneState, ...] | None = None
) -> tuple[str, ...]:
    """Validate vocabulary before execution, then enforce current Done lanes."""
    raw = lane_declarations(declarations)
    if states is not None:
        current = tuple(
            declaration
            for declaration in raw
            if not isinstance(parse_phase_lane(declaration.lane), Err)
        )
        legacy = tuple(declaration for declaration in raw if declaration not in current)
        return (
            *(
                "plan.lanes: current phase receipts unavailable for " + declaration.name
                for declaration in current
                if declaration.status == "Done"
            ),
            *refusals(legacy, states),
        )
    return tuple(
        "plan.lanes: " + declaration.name
        for declaration in raw
        if isinstance(parse_phase_lane(declaration.lane), Err)
    )


def applicability(
    owner: str, targets: tuple[str, ...]
) -> Result[Literal["applicable", "not-applicable"], ClosureError]:
    """Allow an absent owned subject only while its owner remains Planned."""
    if targets:
        return Ok("applicable")
    return (
        Ok("not-applicable")
        if owner == "Planned"
        else Err(ClosureError("empty applicable validator target set"))
    )


def _captured_subject_paths(
    root: Path, policy: CapturedPolicy, base: str, suffix: str, *, recursive: bool
) -> tuple[str, ...]:
    """Select observed files without rereading or traversing the checkout."""
    if policy.regular_files is None:
        return ()
    directory = PurePosixPath(base)
    return tuple(
        str(root / name)
        for name in sorted(policy.regular_files | policy.symlinks)
        if (path := PurePosixPath(name)).suffix == suffix
        and path.is_relative_to(directory)
        and (recursive or path.parent == directory)
        and (base != "DEVELOPMENT_PLAN" or path.name.startswith("phase-"))
    )


def subjects(
    root: Path,
    declarations: tuple[Phase, ...],
    *,
    captured: CapturedPolicy | None = None,
) -> tuple[Subject, ...]:
    """Discover each introduced class and retain missing future subjects explicitly."""
    owners = {phase.number: field(phase.text, "Status") for phase in declarations}
    captured_groups = (
        ("documentation", 0, "documents", ".md", True),
        ("plan", 0, "DEVELOPMENT_PLAN", ".md", False),
        ("oracles", 0, "tests/oracles", ".toml", False),
        ("mutants", 1, "tests/mutants", ".toml", False),
        ("Haskell source", 3, "src/agentctl/haskell", ".hs", True),
    )
    if captured is not None and captured.regular_files is not None:
        return tuple(
            Subject(
                name,
                owners.get(owner, "unknown"),
                _captured_subject_paths(
                    root, captured, base, suffix, recursive=recursive
                ),
            )
            for name, owner, base, suffix, recursive in captured_groups
        )
    groups = (
        ("documentation", 0, tuple((root / "documents").rglob("*.md"))),
        ("plan", 0, tuple((root / "DEVELOPMENT_PLAN").glob("phase-*.md"))),
        ("oracles", 0, tuple((root / "tests/oracles").glob("*.toml"))),
        ("mutants", 1, tuple((root / "tests/mutants").glob("*.toml"))),
        ("Haskell source", 3, tuple((root / "src/agentctl/haskell").rglob("*.hs"))),
    )
    return tuple(
        Subject(name, owners.get(owner, "unknown"), tuple(str(path) for path in paths))
        for name, owner, paths in groups
    )


def non_vacuous(
    root: Path,
    declarations: tuple[Phase, ...],
    *,
    captured: CapturedPolicy | None = None,
) -> tuple[str, ...]:
    """Require nonempty owned subject classes, including Haskell when introduced."""
    return tuple(
        "validator.non-vacuous: " + subject.name
        for subject in subjects(root, declarations, captured=captured)
        if isinstance(applicability(subject.owner, subject.paths), Err)
    )


def inapplicable(
    root: Path,
    declarations: tuple[Phase, ...],
    *,
    captured: CapturedPolicy | None = None,
) -> tuple[str, ...]:
    """Name absent Planned inputs without reporting an unimplemented check as passed."""
    return tuple(
        subject.name
        for subject in subjects(root, declarations, captured=captured)
        if applicability(subject.owner, subject.paths) == Ok("not-applicable")
    )


def static(
    root: Path,
    records: tuple[Mutant, ...],
    *,
    mutant_owners: tuple[tuple[str, int], ...] | CapturedPolicy | None = None,
    observed_phases: tuple[Phase, ...] | None = None,
) -> tuple[str, ...]:
    """Run introduced closure checks that do not depend on this run's outcomes."""
    declarations = phases(root) if observed_phases is None else observed_phases
    return (
        *cited_paths(
            root,
            declarations,
            captured=mutant_owners
            if isinstance(mutant_owners, CapturedPolicy)
            else None,
        ),
        *gate_integrity(root, declarations, records, mutant_owners=mutant_owners),
        *evidence_rows(
            root,
            declarations,
            observed_digest=mutant_owners.covered_digest
            if isinstance(mutant_owners, CapturedPolicy)
            else None,
        ),
        *lanes(declarations),
        *non_vacuous(
            root,
            declarations,
            captured=mutant_owners
            if isinstance(mutant_owners, CapturedPolicy)
            else None,
        ),
    )
