# Copyright (c) 2026 agentctl contributors.
"""Plan grammar and exact closure have independently specified negatives."""

import hashlib
import re
from dataclasses import replace
from pathlib import Path

import pytest

from agentctl.check.evidence import RunEvidence
from agentctl.check.lanes import HostFacts, evaluate
from agentctl.check.mutants import Mutant, Operator
from agentctl.check.plan_data import Phase, Sprint
from agentctl.check.validator import closure
from agentctl.check.validator.plan import (
    check,
    field,
    section,
    status_consequences,
    validate,
)
from agentctl.result import Err, Ok
from tests.harness.trees import negative_tree

pytestmark = pytest.mark.evidence("value")
CASE_ID = "tests/unit/test_subject.py::test_subject"
PHASE_FILE = "phase-0-governance-and-check-skeleton.md"
INTEGRITY = (
    "## Gate Integrity\n\n| Requirement | Oracle | Observer | Mutants | Tests |\n"
    "|---|---|---|---|---|\n"
    "| R20 — known control | `tests/oracles/example.toml` | value: pure control | "
    "`M-legs-control` | `tests/unit/test_subject.py::test_subject` |\n"
)


def _controls(root: Path, temporary: Path, rule: str) -> None:
    """Compare the actual plan with its exact named negative transformation."""
    assert check(root, rule) == ()
    tree = negative_tree(root, temporary, "plan_" + rule.replace("-", "_"))
    assert check(tree, rule) == ("plan." + rule + ": DEVELOPMENT_PLAN",), (
        f"plan.{rule} negative was accepted"
    )


def test_plan_fileset(root: Path, tmp_path: Path) -> None:
    """Reject an additional plan file outside the canonical fixed set."""
    _controls(root, tmp_path, "fileset")
    tree = negative_tree(root, tmp_path / "missing", "plan_fileset")
    (tree / "DEVELOPMENT_PLAN/extra.md").unlink()
    (tree / "DEVELOPMENT_PLAN/phase-14-windows-psmux-acceptance.md").unlink()
    assert check(tree, "fileset")
    (tree / "DEVELOPMENT_PLAN/phase-invalid.md").write_text(
        "invalid phase name", encoding="utf-8"
    )
    assert check(tree, "fileset")


def test_plan_header(root: Path, tmp_path: Path) -> None:
    """Reject an otherwise valid phase with an undeclared header field."""
    _controls(root, tmp_path, "header")
    assert field("", "Status") == ""
    assert section("", "Remaining Work") == ""


def test_plan_status_harmony(root: Path, tmp_path: Path) -> None:
    """Validate the roll-up's structure before comparing phase statuses."""
    _controls(root, tmp_path, "status-harmony")
    for number, replacement in enumerate(("Active", "unknown", "Planned | extra")):
        tree = negative_tree(root, tmp_path / str(number), "plan_fileset")
        phase = tree / "DEVELOPMENT_PLAN/phase-14-windows-psmux-acceptance.md"
        phase.write_text(
            re.sub(
                r"(?m)^\*\*Status\*\*: .+$",
                "**Status**: Planned",
                phase.read_text(encoding="utf-8"),
                count=1,
            ),
            encoding="utf-8",
        )
        page = tree / "DEVELOPMENT_PLAN/README.md"
        text = re.sub(
            r"(?m)^(\| 14 \| [^\n]+? \| )[^|]+\|$",
            r"\g<1>Planned |",
            page.read_text(encoding="utf-8"),
        )
        page.write_text(text, encoding="utf-8")
        assert check(tree, "status-harmony") == ()
        row = (
            "| 14 | [Windows and psmux acceptance]"
            "(phase-14-windows-psmux-acceptance.md) | Planned |"
        )
        page.write_text(
            text.replace(row, row.replace("Planned", replacement)), encoding="utf-8"
        )
        assert check(tree, "status-harmony")


def test_plan_sprint_structure(root: Path, tmp_path: Path) -> None:
    """Join sprint heading tags to their closed body fields."""
    _controls(root, tmp_path, "sprint-structure")
    tree = negative_tree(root, tmp_path / "headings", "plan_fileset")
    page = tree / "DEVELOPMENT_PLAN/phase-0-governance-and-check-skeleton.md"
    original = page.read_text(encoding="utf-8")
    for text in (
        original.replace("Sprint 0.1:", "Sprint 0.9:"),
        original + "\n### Sprint invalid\n",
    ):
        page.write_text(text, encoding="utf-8")
        assert check(tree, "sprint-structure")


def test_plan_status_consequences(root: Path, tmp_path: Path) -> None:
    """Reject a Done sprint with unfinished work and unready dependencies."""
    _controls(root, tmp_path, "status-consequences")
    active = Phase(
        1,
        tmp_path / "phase-1-control.md",
        "**Status**: Active\n## Remaining Work\n\nComplete control.\n",
        (Sprint("1.1", "Active", "#### Remaining Work\n\nComplete control.\n"),),
    )
    assert status_consequences(active, (active,))
    assert not status_consequences(
        replace(active, text=active.text.replace("Complete control.", "None.")),
        (active,),
    )
    lower = Phase(0, tmp_path / "phase-0-control.md", "**Status**: Done\n", ())
    dependent = replace(
        active, text="**Depends on**: [Control](phase-0-control.md)\n" + active.text
    )
    assert status_consequences(dependent, (lower, dependent))
    assert not status_consequences(
        dependent, (replace(lower, text="**Status**: Planned\n"), dependent)
    )
    planned = Phase(
        2,
        tmp_path / "phase-2-control.md",
        "**Status**: Planned\n## Remaining Work\n\nThe whole phase: Sprint 2.1.\n",
        (Sprint("2.1", "Planned", "#### Remaining Work\n\nThe whole sprint.\n"),),
    )
    assert status_consequences(planned, (planned,))
    assert not status_consequences(
        replace(
            planned, text=planned.text.replace("The whole phase:", "Incomplete phase:")
        ),
        (planned,),
    )
    assert not status_consequences(
        replace(
            planned,
            sprints=(
                replace(planned.sprints[0], text="#### Remaining Work\n\nNone.\n"),
            ),
        ),
        (planned,),
    )


def test_plan_dependency_direction(root: Path, tmp_path: Path) -> None:
    """Reject a forward phase dependency with a valid lower-phase twin."""
    _controls(root, tmp_path, "dependency-direction")


def test_plan_requirements_table(root: Path, tmp_path: Path) -> None:
    """Require exact quote anchoring and exactly one closure per requirement."""
    _controls(root, tmp_path, "requirements-table")
    malformed = negative_tree(root, tmp_path / "schema", "plan_fileset")
    for name, search, replacement in (
        ("00-overview.md", "| ID | Requirement |", "| Missing | Requirement |"),
        ("phase-0-governance-and-check-skeleton.md", "**Closes**:", "**Not closes**:"),
    ):
        page = malformed / "DEVELOPMENT_PLAN" / name
        original = page.read_text(encoding="utf-8")
        page.write_text(original.replace(search, replacement, 1), encoding="utf-8")
        assert check(malformed, "requirements-table")
        page.write_text(original, encoding="utf-8")
    tree = negative_tree(root, tmp_path / "duplicate", "plan_fileset")
    page = tree / "DEVELOPMENT_PLAN/phase-0-governance-and-check-skeleton.md"
    text = page.read_text(encoding="utf-8")
    page.write_text(
        text.replace("**Closes**: R14.1\n", "**Closes**: R14.1, R2\n"), encoding="utf-8"
    )
    assert check(tree, "requirements-table"), (
        "duplicate requirement closure was accepted"
    )
    page.write_text(
        text.replace("**Closes**: R2\n", "**Closes**: R2, R2\n"),
        encoding="utf-8",
    )
    assert check(tree, "requirements-table"), (
        "duplicate requirement closure was accepted"
    )


def test_plan_legacy_ledger(root: Path, tmp_path: Path) -> None:
    """Reject a ledger entry whose deleting phase does not exist."""
    _controls(root, tmp_path, "legacy-ledger")


def test_plan_disposition_table(root: Path, tmp_path: Path) -> None:
    """Reject an undeclared concept-note disposition without losing its row."""
    _controls(root, tmp_path, "disposition-table")


def test_plan_no_narrative(root: Path, tmp_path: Path) -> None:
    """Reject closure chronicles while retaining source-provenance blocks."""
    _controls(root, tmp_path, "no-narrative")


def test_live_plan_clean(root: Path) -> None:
    """Run every structural plan rule against the complete checkout plan."""
    assert validate(root) == ()


def _declaration(root: Path) -> Phase:
    """Build a minimal component declaration independent of the parser."""
    sprint = Sprint(
        "0.1",
        "Done",
        "**Implementation**: `src/subject.py`\n**Validation tests**: `"
        + CASE_ID
        + "`\n**Mutants**: `M-legs-control`\n",
    )
    return Phase(
        0,
        root / "DEVELOPMENT_PLAN" / PHASE_FILE,
        "**Status**: Done\n**Gate kind**: self-verifying\n**Host lane**: any-host\n"
        + INTEGRITY,
        (sprint,),
    )


def _policy(root: Path) -> None:
    """Write only the independent policy inputs this join reads."""
    directory = root / "DEVELOPMENT_PLAN"
    directory.mkdir()
    (directory / "development_plan_standards.md").write_text(
        "| [Governance](" + PHASE_FILE + ") | `M-legs-` |\n", encoding="utf-8"
    )
    (directory / "00-overview.md").write_text(
        "## Requirements\n\n| ID | Requirement |\n|---|---|\n| R20 | known control |\n",
        encoding="utf-8",
    )
    oracle = root / "tests/oracles/example.toml"
    oracle.parent.mkdir(parents=True)
    oracle.write_text('[[case]]\nid = "control"\nexpected = 2\n', encoding="utf-8")


def _execution() -> RunEvidence:
    """Keep collected, executed and passed values distinct in the control."""
    return RunEvidence(
        "current",
        frozenset({CASE_ID}),
        frozenset({CASE_ID}),
        frozenset({CASE_ID}),
        (),
        ((CASE_ID, "value"),),
    )


def test_plan_gate_integrity(tmp_path: Path) -> None:
    """Schema, executable killers, classes and both owed directions are required."""
    _policy(tmp_path)
    phase = _declaration(tmp_path)
    record = Mutant(
        "M-legs-control",
        Operator.REPLACE_LITERAL,
        "src/subject.py",
        "return 2",
        "return 3",
        (CASE_ID,),
        "named control",
    )
    assert closure.gate_integrity(tmp_path, (phase,), (record,), _execution()) == ()
    assert isinstance(closure.integrity_row(()), Err)
    assert isinstance(
        closure.integrity_row(
            ("R20 — control", "none — input", "value: input", "none — no code", "")
        ),
        Err,
    )
    for declarations, records, evidence in (
        ((phase,), (), _execution()),
        (
            (phase,),
            (replace(record, killers=("tests/live/test_live.py::test_live",)),),
            _execution(),
        ),
        (
            (replace(phase, text=phase.text.replace("value: pure", "cached: pure")),),
            (record,),
            _execution(),
        ),
        ((phase,), (record,), replace(_execution(), classes=((CASE_ID, "real"),))),
        (
            (replace(phase, text=phase.text.replace("R20 —", "R99 —")),),
            (record,),
            _execution(),
        ),
        (
            (
                replace(
                    phase,
                    text=phase.text.replace(
                        "| Requirement | Oracle |", "| Incorrect | Oracle |"
                    ),
                ),
            ),
            (record,),
            _execution(),
        ),
    ):
        assert closure.gate_integrity(tmp_path, declarations, records, evidence)
    source = replace(
        phase,
        text=phase.text.replace(
            "value: pure control", "value: pure control; owed: live-agent-acceptance"
        ),
    )
    acceptance = Phase(
        11,
        tmp_path / "DEVELOPMENT_PLAN/phase-11-live-agent-acceptance.md",
        "**Status**: Planned\n**Gate kind**: host-acceptance\n"
        + INTEGRITY.replace(
            "value: pure control", "owed: live-agent-acceptance"
        ).replace("`M-legs-control`", "none — no code")
        + "\n## Confirms\n\n- R20 — known control (owed by [Governance]("
        + PHASE_FILE
        + ")).\n",
        (),
    )
    assert closure.gate_integrity(tmp_path, (source, acceptance), (record,)) == ()
    assert closure.gate_integrity(tmp_path, (source,), (record,))
    assert closure.gate_integrity(tmp_path, (phase, acceptance), (record,))
    assert closure.gate_integrity(
        tmp_path,
        (source, replace(acceptance, text=acceptance.text.split("## Confirms")[0])),
        (record,),
    )


def test_plan_cited_ids(tmp_path: Path) -> None:
    """A missing current result cannot satisfy a Done citation."""
    phase = _declaration(tmp_path)
    assert closure.cited_ids((phase,), _execution()) == ()
    assert (
        closure.cited_ids(
            (replace(phase, sprints=(replace(phase.sprints[0], tag="Planned"),)),),
            _execution(),
        )
        == ()
    )
    assert closure.cited_ids((phase,), replace(_execution(), passed=frozenset())) == (
        "plan.cited-ids: 0.1",
    ), "missing citation result was accepted"
    parameter = CASE_ID + "[case]"
    current = replace(
        _execution(), collected=frozenset({parameter}), passed=frozenset({parameter})
    )
    assert closure.cited_ids((phase,), current) == ()
    haskell = replace(
        phase,
        sprints=(
            replace(
                phase.sprints[0], text="**Validation tests**: `haskell:suite/case`\n"
            ),
        ),
    )
    assert (
        closure.cited_ids((haskell,), _execution(), frozenset({"haskell:suite/case"}))
        == ()
    )
    assert closure.cited_ids((haskell,), _execution())


def test_plan_cited_paths(tmp_path: Path) -> None:
    """Only existing durable paths qualify; Planned artifacts may be absent."""
    phase = _declaration(tmp_path)
    assert closure.cited_paths(tmp_path, (phase,)) == ("plan.cited-paths: 0.1",), (
        "missing implementation path was accepted"
    )
    (tmp_path / "src").mkdir()
    (tmp_path / "src/subject.py").write_text("value = 1", encoding="utf-8")
    assert closure.cited_paths(tmp_path, (phase,)) == ()
    for path in (".build/output", "logs/run", "result.log", "../outside", "."):
        altered = replace(
            phase,
            sprints=(
                replace(phase.sprints[0], text="**Implementation**: `" + path + "`\n"),
            ),
        )
        assert closure.cited_paths(tmp_path, (altered,))
    assert (
        closure.cited_paths(
            tmp_path,
            (replace(phase, sprints=(replace(phase.sprints[0], tag="Planned"),)),),
        )
        == ()
    )


def _covered_tree(root: Path) -> str:
    """Derive the expected digest from explicit path/kind/byte fields."""
    (root / "src").mkdir()
    (root / "tests").mkdir()
    (root / "pyproject.toml").write_bytes(b"project = 1\n")
    hashed = hashlib.sha256()
    for name, kind, payload in (
        ("pyproject.toml", "file", b"project = 1\n"),
        ("src", "directory", b""),
        ("tests", "directory", b""),
    ):
        for value in (name.encode(), kind.encode(), payload):
            hashed.update(len(value).to_bytes(8, "big"))
            hashed.update(value)
    return hashed.hexdigest()


def test_plan_evidence_rows(tmp_path: Path) -> None:
    """A current exact lane passes; a covered ignored change stales the row."""
    assert closure.evidence_rows(tmp_path, ())
    tree = _covered_tree(tmp_path)
    text = (
        "**Status**: Done\n**Gate kind**: host-acceptance\n**Host lane**: macos\n"
        "**Evidence covers**: `src/` `tests/` `pyproject.toml`\n"
        "**Gate evidence**: 2026-11-02 ; macos ; agentctl check ; pass ; tree "
        + tree
        + " ; os=Darwin\n"
    )
    phase = Phase(13, tmp_path / "phase-13-macos-acceptance.md", text, ())
    assert closure.evidence_rows(tmp_path, (phase,)) == ()
    for altered in (
        text.replace(" ; macos ; ", " ; any-host ; "),
        text.replace("agentctl check ;", "other check ;"),
        text.replace("tree " + tree, "tree " + "0" * 64),
    ):
        assert closure.evidence_rows(tmp_path, (replace(phase, text=altered),)), (
            "evidence row mismatch was accepted"
        )
    (tmp_path / "src/.ignored").write_bytes(b"changed")
    assert closure.evidence_rows(tmp_path, (phase,)), (
        "stale covered digest was accepted"
    )
    reopened = (
        text.replace("**Status**: Done", "**Status**: Active").split(
            "**Gate evidence**:"
        )[0]
        + "**Gate evidence**: none recorded\n"
    )
    assert closure.evidence_rows(tmp_path, (replace(phase, text=reopened),)) == ()


def test_plan_lanes(tmp_path: Path) -> None:
    """Closed header vocabulary and Done requirements use observed lane facts."""
    phase = _declaration(tmp_path)
    facts = HostFacts(family="Linux", architecture="x86_64", checkout=True, git=True)
    assert closure.lanes((phase,)) == ()
    assert closure.lanes((phase,), evaluate(facts)) == ()
    assert closure.lanes(
        (replace(phase, text=phase.text.replace("any-host", "mux-host")),),
        evaluate(facts),
    )
    assert closure.lanes(
        (replace(phase, text=phase.text.replace("any-host", "invented")),)
    )


def test_validator_non_vacuous(tmp_path: Path) -> None:
    """A missing future subject is inapplicable; an introduced empty subject fails."""
    assert closure.applicability("Planned", ()) == Ok("not-applicable")
    assert closure.applicability("Done", ("subject",)) == Ok("applicable")
    for status in ("Active", "Done"):
        assert isinstance(closure.applicability(status, ()), Err), (
            "empty applicable validator target set was accepted"
        )
    future = Phase(3, tmp_path / "phase-3-control.md", "**Status**: Planned\n", ())
    assert closure.inapplicable(tmp_path, (future,)) == ("Haskell source",)
    assert closure.non_vacuous(tmp_path, (future,))
    directory = tmp_path / "src/agentctl/haskell"
    directory.mkdir(parents=True)
    (directory / "Example.hs").write_text("module Example where\n", encoding="utf-8")
    assert closure.inapplicable(tmp_path, (future,)) == ()
