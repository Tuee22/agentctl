# Copyright (c) 2026 agentctl contributors.
"""Structural development-plan checks independent of product availability."""

import re
from collections import Counter
from pathlib import Path

from agentctl.check.plan_data import Phase, field, phases, section
from agentctl.check.plan_data import table as _rows
from agentctl.check.validator.docs import unfenced

REQUIREMENT_COLUMNS = 7
STATUS_COLUMNS = 3
LEDGER_COLUMNS = 4
DISPOSITION_COLUMNS = 6
MINIMUM_TABLE_ROWS = 2
README_LINE_LIMIT = 200
RULES = (
    "fileset",
    "header",
    "status-harmony",
    "sprint-structure",
    "status-consequences",
    "dependency-direction",
    "requirements-table",
    "legacy-ledger",
    "disposition-table",
    "no-narrative",
)
COMPANIONS = frozenset(
    {
        "README.md",
        "development_plan_standards.md",
        "00-overview.md",
        "system-components.md",
        "rationale.md",
        "legacy_tracking_for_deletion.md",
    }
)
STATUSES = frozenset({"Planned", "Active", "Done"})
PHASE_SECTIONS = (
    "Phase Objective",
    "Gate Integrity",
    "Not Proven By This Gate",
    "Sprints",
    "Remaining Work",
    "Documentation Requirements",
)
SPRINT_FIELDS = (
    "Status",
    "Implementation",
    "Validation tests",
    "Mutants",
    "Closes",
    "Docs to update",
)
DOC_LABELS = (
    "Architecture docs to create/update:",
    "Engineering docs to create/update:",
    "Operations and reference docs to create/update:",
    "Cross-references to add:",
)


def _ids(value: str) -> tuple[str, ...]:
    """Parse the closed comma-separated requirement-id grammar."""
    return () if value == "none" else tuple(value.split(", "))


def _header(phase: Phase) -> bool:
    """Require the closed phase header and canonical section sequence."""
    header = phase.text.split("> **Purpose**:", 1)[0]
    fields = tuple(re.findall(r"^\*\*([^*]+)\*\*:", header, re.MULTILINE))
    expected = ("Status", "Depends on", "Host lane", "Gate", "Gate kind", "Closes")
    acceptance = field(header, "Gate kind") == "host-acceptance"
    if acceptance:
        expected += ("Gate evidence", "Evidence covers")
    sections = tuple(re.findall(r"^## (.+)$", unfenced(phase.text), re.MULTILINE))
    wanted = (
        (*PHASE_SECTIONS[:3], "Confirms", *PHASE_SECTIONS[3:])
        if acceptance
        else PHASE_SECTIONS
    )
    labels = tuple(
        re.findall(
            r"^\*\*([^*]+:)\*\*$",
            section(phase.text, "Documentation Requirements"),
            re.MULTILINE,
        )
    )
    return (
        fields == expected
        and field(header, "Status") in STATUSES
        and field(header, "Gate") == "`agentctl check`"
        and field(header, "Gate kind") in {"self-verifying", "host-acceptance"}
        and re.match(r"# Phase " + str(phase.number) + r" — [^\n]+\n", phase.text)
        is not None
        and sections == wanted
        and labels == DOC_LABELS
    )


def _sprints(phase: Phase) -> bool:
    """Require contiguous sprint ids, closed fields and section headings."""
    identifiers = tuple(sprint.identifier for sprint in phase.sprints)
    if not identifiers or identifiers != tuple(
        f"{phase.number}.{number}" for number in range(1, len(identifiers) + 1)
    ):
        return False
    if len(re.findall(r"^### Sprint ", phase.text, re.MULTILINE)) != len(identifiers):
        return False
    for sprint in phase.sprints:
        fields = tuple(re.findall(r"^\*\*([^*]+)\*\*:", sprint.text, re.MULTILINE))
        headings = tuple(re.findall(r"^#### (.+)$", sprint.text, re.MULTILINE))
        if (
            fields != SPRINT_FIELDS
            or sprint.tag not in STATUSES
            or field(sprint.text, "Status") != sprint.tag
            or headings != ("Objective", "Deliverables", "Validation", "Remaining Work")
        ):
            return False
    return True


def status_consequences(phase: Phase, all_phases: tuple[Phase, ...]) -> bool:
    """Check completion consequences and lower-phase readiness."""
    status = field(phase.text, "Status")
    remaining = section(phase.text, "Remaining Work")
    if status == "Done" and (
        remaining != "None." or any(sprint.tag != "Done" for sprint in phase.sprints)
    ):
        return False
    planned_remainder = (
        f"The whole phase: Sprint {phase.number}.1."
        if len(phase.sprints) == 1
        else (
            f"The whole phase: Sprints {phase.number}.1"
            f"\u2013{phase.number}.{len(phase.sprints)}."
        )
    )
    if status == "Planned" and (
        remaining != planned_remainder
        or any(sprint.tag != "Planned" for sprint in phase.sprints)
    ):
        return False
    if status == "Active" and (not remaining or remaining == "None."):
        return False
    dependencies = tuple(
        int(number)
        for number in re.findall(r"\(phase-(\d+)-", field(phase.text, "Depends on"))
    )
    if status != "Planned" and any(
        not any(
            lower.number == dependency and field(lower.text, "Status") == "Done"
            for lower in all_phases
        )
        for dependency in dependencies
    ):
        return False
    for sprint in phase.sprints:
        remainder = section(sprint.text, "Remaining Work", level=4)
        if (
            (sprint.tag == "Done" and remainder != "None.")
            or (sprint.tag == "Planned" and remainder != "The whole sprint.")
            or (sprint.tag == "Active" and (not remainder or remainder == "None."))
        ):
            return False
    return True


def _requirements(root: Path, all_phases: tuple[Phase, ...]) -> bool:
    """Join request quotes, requirement rows and exactly one closing sprint."""
    overview = (root / "DEVELOPMENT_PLAN/00-overview.md").read_text(encoding="utf-8")
    rationale = (root / "DEVELOPMENT_PLAN/rationale.md").read_text(encoding="utf-8")
    request = section(rationale, "Originating Request")
    rows = _rows(section(overview, "Requirements"))
    if not rows or rows[0] != (
        "ID",
        "Requirement",
        "Quote",
        "Closing sprint",
        "Evidence classes",
        "Prose home",
        "Data home",
    ):
        return False
    requirements = rows[1:]
    closures: Counter[str] = Counter()
    closing: dict[str, str] = {}
    for phase in all_phases:
        own = tuple(
            identifier
            for sprint in phase.sprints
            for identifier in _ids(field(sprint.text, "Closes"))
        )
        if set(own) != set(_ids(field(phase.text, "Closes"))):
            return False
        closures.update(own)
        for sprint in phase.sprints:
            for identifier in _ids(field(sprint.text, "Closes")):
                closing[identifier] = sprint.identifier
    if (
        not requirements
        or len({row[0] for row in requirements}) != len(requirements)
        or closures != Counter({row[0]: 1 for row in requirements})
    ):
        return False
    for row in requirements:
        if (
            len(row) != REQUIREMENT_COLUMNS
            or not re.fullmatch(r"R\d+(?:\.\d+)?", row[0])
            or not row[2].startswith("`")
            or not row[2].endswith("`")
            or row[2][1:-1] not in request
            or not row[3].startswith(f"[Sprint {closing[row[0]]}]")
        ):
            return False
    return True


def _invalid_fileset(all_phases: tuple[Phase, ...], plan: Path, readme: str) -> bool:
    """Detect violations of plan.fileset."""
    wanted = COMPANIONS | set(
        re.findall(
            r"\((phase-\d+-[a-z-]+\.md)\)", section(readme, "Current Phase Status")
        )
    )
    numbers = tuple(phase.number for phase in all_phases)
    return (
        {path.name for path in plan.iterdir()} != wanted
        or numbers != tuple(range(len(numbers)))
        or not numbers
    )


def _invalid_header(all_phases: tuple[Phase, ...], plan: Path) -> bool:
    """Detect violations of plan.header."""
    bad = False
    bad = any(not _header(phase) for phase in all_phases)
    for filename in COMPANIONS:
        text = (plan / filename).read_text(encoding="utf-8")
        bad = (
            bad
            or not text.startswith("# ")
            or not field(text, "Status")
            or not field(text, "Supersedes")
            or "> **Purpose**:" not in text
            or "## Related" not in text
        )
    return bad


def _invalid_status_harmony(
    all_phases: tuple[Phase, ...], rows: tuple[tuple[str, ...], ...]
) -> bool:
    """Detect violations of plan.status-harmony."""
    expected = tuple(
        (str(phase.number), phase.path.name, field(phase.text, "Status"))
        for phase in all_phases
    )
    actual = tuple(
        (row[0], re.sub(r".*\(([^)]+)\).*", r"\1", row[1]), row[2])
        for row in rows[1:]
        if len(row) == STATUS_COLUMNS
    )
    return (
        not rows
        or rows[0] != ("#", "Phase", "Status")
        or len(actual) != len(rows) - 1
        or actual != expected
    )


def _invalid_sprint_structure(all_phases: tuple[Phase, ...]) -> bool:
    """Detect violations of plan.sprint-structure."""
    return any(not _sprints(phase) for phase in all_phases)


def _invalid_status_consequences(all_phases: tuple[Phase, ...]) -> bool:
    """Detect violations of plan.status-consequences."""
    return any(not status_consequences(phase, all_phases) for phase in all_phases)


def _invalid_dependency_direction(all_phases: tuple[Phase, ...]) -> bool:
    """Detect violations of plan.dependency-direction."""
    bad = False
    for phase in all_phases:
        dependencies = tuple(
            int(number)
            for number in re.findall(r"\(phase-(\d+)-", field(phase.text, "Depends on"))
        )
        bad = (
            bad
            or (
                field(phase.text, "Depends on") != "nothing"
                if phase.number == 0
                else not dependencies
            )
            or any(
                number >= phase.number
                or not any(
                    candidate.number == number
                    and field(candidate.text, "Gate kind") == "self-verifying"
                    for candidate in all_phases
                )
                for number in dependencies
            )
        )
        remainders = (
            section(phase.text, "Remaining Work"),
            *(
                section(sprint.text, "Remaining Work", level=4)
                for sprint in phase.sprints
            ),
        )
        bad = bad or any(
            int(number) > phase.number
            for text in remainders
            for number in re.findall(r"\bPhase (\d+)", text)
        )
    return bad


def _invalid_requirements_table(root: Path, all_phases: tuple[Phase, ...]) -> bool:
    """Detect violations of plan.requirements-table."""
    return not _requirements(root, all_phases)


def _invalid_legacy_ledger(all_phases: tuple[Phase, ...], plan: Path) -> bool:
    """Detect violations of plan.legacy-ledger."""
    bad = False
    ledger = (plan / "legacy_tracking_for_deletion.md").read_text(encoding="utf-8")
    ledger_rows = _rows(ledger)
    bad = not ledger_rows or ledger_rows[0] != (
        "Shape",
        "Location",
        "Why it must go",
        "Deleted by",
    )
    for row in ledger_rows[1:]:
        bad = (
            bad
            or len(row) != LEDGER_COLUMNS
            or not any(
                phase.path.name in row[-1] and field(phase.text, "Status") != "Done"
                for phase in all_phases
            )
        )
    return bad


def _invalid_disposition_table(plan: Path) -> bool:
    """Detect violations of plan.disposition-table."""
    bad = False
    rationale = (plan / "rationale.md").read_text(encoding="utf-8")
    dispositions = _rows(section(rationale, "Concept-Note Disposition"))
    bad = len(dispositions) < MINIMUM_TABLE_ROWS
    for row in dispositions[1:]:
        bad = (
            bad
            or len(row) != DISPOSITION_COLUMNS
            or row[3] not in {"adopted", "adapted", "rejected", "deferred-to-phase"}
            or not row[4]
        )
    return bad


def _invalid_no_narrative(all_phases: tuple[Phase, ...], readme: str) -> bool:
    """Detect violations of plan.no-narrative."""
    bad = False
    for phase in all_phases:
        prose = unfenced(phase.text)
        bad = (
            bad
            or re.search(
                r"^#{1,3} .*\b(?:Historical|Superseded|Corrected|Deprecated|Legacy)\b",
                prose,
                re.MULTILINE,
            )
            is not None
            or re.search(r"\b\d+ (?:tests?|test passes|mutants? killed)\b", prose)
            is not None
            or re.search(
                r"(?<!evidence\*\*: )\b20\d\d-\d\d-\d\d\b",
                re.sub(r"^\*\*Gate evidence\*\*:.*$", "", prose, flags=re.MULTILINE),
            )
            is not None
        )
    return bad or len(readme.splitlines()) > README_LINE_LIMIT


def _invalid(root: Path, rule: str) -> bool:
    """Evaluate one registered structural plan rule."""
    all_phases = phases(root)
    plan = root / "DEVELOPMENT_PLAN"
    readme = (plan / "README.md").read_text(encoding="utf-8")
    rows = _rows(section(readme, "Current Phase Status"))
    checks = {
        "fileset": lambda: _invalid_fileset(all_phases, plan, readme),
        "header": lambda: _invalid_header(all_phases, plan),
        "status-harmony": lambda: _invalid_status_harmony(all_phases, rows),
        "sprint-structure": lambda: _invalid_sprint_structure(all_phases),
        "status-consequences": lambda: _invalid_status_consequences(all_phases),
        "dependency-direction": lambda: _invalid_dependency_direction(all_phases),
        "requirements-table": lambda: _invalid_requirements_table(root, all_phases),
        "legacy-ledger": lambda: _invalid_legacy_ledger(all_phases, plan),
        "disposition-table": lambda: _invalid_disposition_table(plan),
        "no-narrative": lambda: _invalid_no_narrative(all_phases, readme),
    }
    return checks[rule]()


def check(root: Path, rule: str) -> tuple[str, ...]:
    """Reject unreadable owned inputs as well as invalid plan declarations."""
    try:
        invalid = _invalid(root, rule)
    except (OSError, UnicodeError):
        invalid = True
    return (f"plan.{rule}: DEVELOPMENT_PLAN",) if invalid else ()


def validate(root: Path) -> tuple[str, ...]:
    """Run every plan rule available at the governance boundary."""
    return tuple(problem for rule in RULES for problem in check(root, rule))
