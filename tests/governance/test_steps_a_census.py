# Copyright (c) 2026 agentctl contributors.
"""Census-bound declaration readers refuse missing or inconsistent inputs."""

import json
from pathlib import Path

import pytest

from agentctl.check import evidence, mutant_report, steps
from agentctl.check.evidence import Entry, LegEvidence, RunEvidence, ToolSubsteps
from agentctl.check.mutants import Mutant, Operator
from agentctl.foundation import Err, Ok

pytestmark = pytest.mark.evidence("value")
ROOT = Path(__file__).resolve().parents[2]
MANIFEST = "src/agentctl/check/source_ownership.toml"
PHASE0 = "src/agentctl/check/phase0_mutant_ownership.toml"
LINUX = "src/agentctl/check/linux_mutant_ownership.toml"
PLAN0 = "DEVELOPMENT_PLAN/phase-0-governance-and-phase-evidence.md"
NONCE = "current"
FAILED_STATUS = 1
NODE = "tests/governance/test_mutants.py::test_corpus[M-one]"


def _entry(path: str, payload: bytes | None = None) -> Entry:
    data = (ROOT / path).read_bytes() if payload is None else payload
    return Entry(path, "file", (data,))


def _fragment_paths() -> tuple[str, ...]:
    manifest = steps.ownership.parse_manifest(
        (ROOT / MANIFEST).read_text(encoding="utf-8")
    )
    assert isinstance(manifest, Ok)
    return tuple(
        item.path
        for item in manifest.value.artifacts
        if item.path.startswith("src/agentctl/check/")
        and item.path.endswith("_mutant_ownership.toml")
    )


def _mutant() -> Mutant:
    return Mutant("M-one", Operator.DELETE, "src/x.py", "a", "b", (NODE,), "reason")


def _run_evidence(passed: frozenset[str]) -> RunEvidence:
    return RunEvidence(
        NONCE, frozenset({NODE}), frozenset({NODE}), passed, (), ((NODE, "value"),)
    )


def test_mutant_killers_join_reports_the_evidence_verdict() -> None:
    """A report is accepted only when it matches records and pytest outcomes."""
    killer = mutant_report.Killer(NODE, "passed", "killed")
    record = mutant_report.Record("M-one", "", (killer,))
    report = mutant_report.Report(NONCE, (record,), "digest")
    records = Ok((_mutant(),))
    passing = Ok(_run_evidence(frozenset({NODE})))
    assert steps.mutant_killers_match(Ok(report), records, passing) == 0
    failing = Ok(_run_evidence(frozenset()))
    assert steps.mutant_killers_match(Ok(report), records, failing) == FAILED_STATUS


def test_pytest_leg_reports_inconsistent_shared_evidence(tmp_path: Path) -> None:
    """A manifest from another run than the tool record is refused."""
    manifest = {
        "nonce": NONCE,
        "collected": [NODE],
        "executed": [NODE],
        "passed": [NODE],
        "forbidden": [],
        "classes": {NODE: "value"},
    }
    (tmp_path / "pytest-manifest.json").write_text(json.dumps(manifest), "utf-8")
    tools = steps.ToolOutcome(
        0,
        Ok(LegEvidence("other", (("pytest", 0),))),
        Ok(ToolSubsteps("other", (("pytest", (0, 0, 0)),))),
    )
    assert steps.report_pytest_leg(tmp_path, tools) == FAILED_STATUS


def test_oracle_check_refuses_an_unreadable_outcome_record(tmp_path: Path) -> None:
    """An empty run identity cannot be read back as the oracle record."""
    assert steps.oracle_check(tmp_path, tmp_path, "") == FAILED_STATUS


def test_oracle_diagnostics_need_one_status_for_the_same_run() -> None:
    """Outcomes lacking the oracle leg, or from another run, are inconsistent."""
    entries = (_entry(MANIFEST),)
    details = evidence.OracleDetails(NONCE, (), ())
    message = "oracle details and tool outcomes have inconsistent identity"
    assert steps.oracle_diagnostics(
        entries, details, LegEvidence(NONCE, (("other", 0),))
    ) == Err(message)
    assert steps.oracle_diagnostics(
        entries, details, LegEvidence("other", ((steps.ORACLE_LEGS[0], 0),))
    ) == Err(message)


def test_phase0_claims_refuse_unreadable_fragment_declarations() -> None:
    """A required fragment missing from the census is reported for Phase 0."""
    kept = tuple(_entry(path) for path in _fragment_paths() if path != LINUX)
    entries = (_entry(MANIFEST), _entry(PLAN0), *kept)
    problems = steps.phase0_claim_problems(ROOT, entries, ())
    assert problems == (
        "validators: missing or duplicate census declaration: " + LINUX,
    )


def test_fragment_claims_refuse_owner_mismatch() -> None:
    """A claim fragment whose rows name another owner is a validator problem."""
    changed = (ROOT / PHASE0).read_bytes().replace(b"owner = 0", b"owner = 1")
    entries = (_entry(MANIFEST), _entry(PHASE0, changed))
    problems = steps.fragment_claim_problems(entries, ())
    assert "validators: mutant claim fragment owner mismatch: " + PHASE0 in problems


def test_scoped_mapping_readers_refuse_an_empty_census() -> None:
    """Every scoped mapping reader reports the missing manifest declaration."""
    missing = Err("missing or duplicate census declaration: " + MANIFEST)
    assert steps.scoped_mutant_mapping((), ()) == missing
    assert steps.declared_scoped_mutant_mapping((), ()) == missing
    assert steps.observed_scoped_mutant_mapping((), (), ()) == missing


def test_scoped_consumer_validation_keeps_unattributable_problems() -> None:
    """Without a usable manifest and declarations nothing is attributed away."""
    scoped = ("validators: test consumers: something",)
    validate = steps.__dict__["_scoped_test_consumer_validation"]
    assert validate(scoped, (), ()) == scoped
    assert validate(scoped, (Entry(MANIFEST, "file", (b"= not toml",)),), ()) == scoped
    assert validate(scoped, (_entry(MANIFEST),), ()) == scoped


def test_coverage_declarations_refuse_invalid_and_missing_sources() -> None:
    """Version, host declarations and named sources are all required."""
    read = steps.__dict__["_coverage_declarations"]
    invalid = (
        Entry("pyproject.toml", "file", (b"",)),
        Entry(steps.COVERAGE_HOSTS, "file", (b"",)),
    )
    assert read(invalid, "Linux") == Err("invalid coverage capture declarations")
    sparse = (_entry("pyproject.toml"), _entry(steps.COVERAGE_HOSTS))
    assert read(sparse, "Linux") == Err(
        "coverage host declarations name missing sources"
    )
