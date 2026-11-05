# Copyright (c) 2026 agentctl contributors.
"""Join plan declarations to real paths, current execution and acceptance rows."""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from agentctl.check.evidence import RunEvidence, digest
from agentctl.check.lanes import Declaration, LaneState, parse_lane, refusals
from agentctl.check.mutants import Mutant
from agentctl.check.plan_data import Phase, field, phases, section, table
from agentctl.result import Err, Ok, Result

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


def cited_paths(root: Path, declarations: tuple[Phase, ...]) -> tuple[str, ...]:
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
                    or not (root / path).exists()
                    or not (root / path).resolve().is_relative_to(root.resolve())
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


def _prefixes(root: Path) -> dict[str, tuple[str, ...]]:
    """Read the authoritative phase-to-prefix table rather than a parallel list."""
    text = (root / "DEVELOPMENT_PLAN/development_plan_standards.md").read_text(
        encoding="utf-8"
    )
    return {
        filename: tuple(re.findall(r"`(M-[a-z]+-)`", line))
        for line in text.splitlines()
        if "| `M-" in line
        for filename in re.findall(r"\((phase-\d+-[a-z-]+\.md)\)", line)
    }


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


def gate_integrity(
    root: Path,
    declarations: tuple[Phase, ...],
    records: tuple[Mutant, ...],
    evidence: RunEvidence | None = None,
) -> tuple[str, ...]:
    """Check every declaration and activate executable joins for Done capabilities."""
    prefixes = _prefixes(root)
    requirements = frozenset(
        row[0]
        for row in table(
            section(
                (root / "DEVELOPMENT_PLAN/00-overview.md").read_text(encoding="utf-8"),
                "Requirements",
            )
        )[1:]
    )
    available = {record.identifier: record for record in records}
    rows: tuple[tuple[Phase, IntegrityRow], ...] = ()
    bad = False
    declared: set[str] = set()
    for phase in declarations:
        matrix = table(section(phase.text, "Gate Integrity"))
        if not matrix or matrix[0] != INTEGRITY_COLUMNS or len(matrix) == 1:
            return ("plan.gate-integrity: invalid table",)
        for cells in matrix[1:]:
            parsed = integrity_row(cells)
            if isinstance(parsed, Err):
                return ("plan.gate-integrity: " + parsed.error.message,)
            rows += ((phase, parsed.value),)
            bad = (
                bad
                or parsed.value.requirement not in requirements
                or any(
                    not identifier.startswith(prefixes.get(phase.path.name, ()))
                    for identifier in parsed.value.mutants
                )
            )
        for sprint in phase.sprints:
            identifiers = mutant_ids(field(sprint.text, "Mutants"))
            declared.update(identifiers)
            bad = bad or any(
                not identifier.startswith(prefixes.get(phase.path.name, ()))
                for identifier in identifiers
            )
            if sprint.tag == "Done":
                bad = bad or any(
                    identifier not in available for identifier in identifiers
                )
    bad = bad or not set(available) <= declared or not _owed(declarations, rows)
    for phase, row in rows:
        applicable = field(phase.text, "Status") == "Done" or any(
            identifier in available for identifier in row.mutants
        )
        if not applicable:
            continue
        bad = bad or any(not (root / name).exists() for name in row.oracles)
        bad = bad or any(
            identifier not in available
            or not set(available[identifier].killers) <= set(row.tests)
            for identifier in row.mutants
        )
        if evidence is not None:
            bad = bad or not _executed(row, evidence)
    return ("plan.gate-integrity: declaration or execution join",) if bad else ()


def evidence_rows(root: Path, declarations: tuple[Phase, ...]) -> tuple[str, ...]:
    """Validate terminal rows against the covered tree, lane and literal gate."""
    current = digest(root)
    if isinstance(current, Err):
        return ("plan.evidence-rows: " + current.error.message,)
    problems: tuple[str, ...] = ()
    for phase in declarations:
        if field(phase.text, "Gate kind") != "host-acceptance":
            continue
        row = field(phase.text, "Gate evidence")
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
        return refusals(raw, states)
    return tuple(
        "plan.lanes: " + declaration.name
        for declaration in raw
        if isinstance(parse_lane(declaration.lane), Err)
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


def subjects(root: Path, declarations: tuple[Phase, ...]) -> tuple[Subject, ...]:
    """Discover each introduced class and retain missing future subjects explicitly."""
    owners = {phase.number: field(phase.text, "Status") for phase in declarations}
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


def non_vacuous(root: Path, declarations: tuple[Phase, ...]) -> tuple[str, ...]:
    """Require nonempty owned subject classes, including Haskell when introduced."""
    return tuple(
        "validator.non-vacuous: " + subject.name
        for subject in subjects(root, declarations)
        if isinstance(applicability(subject.owner, subject.paths), Err)
    )


def inapplicable(root: Path, declarations: tuple[Phase, ...]) -> tuple[str, ...]:
    """Name absent Planned inputs without reporting an unimplemented check as passed."""
    return tuple(
        subject.name
        for subject in subjects(root, declarations)
        if applicability(subject.owner, subject.paths) == Ok("not-applicable")
    )


def static(root: Path, records: tuple[Mutant, ...]) -> tuple[str, ...]:
    """Run introduced closure checks that do not depend on this run's outcomes."""
    declarations = phases(root)
    return (
        *cited_paths(root, declarations),
        *gate_integrity(root, declarations, records),
        *evidence_rows(root, declarations),
        *lanes(declarations),
        *non_vacuous(root, declarations),
    )
