# Copyright (c) 2026 agentctl contributors.
"""Captured-census joins, coverage reconstruction and receipt inputs refuse damage."""

from dataclasses import replace
from pathlib import Path

import pytest

from agentctl.check import (
    coverage_hosts,
    mutant_report,
    ownership,
    phase_reports,
    steps,
)
from agentctl.check.evidence import Entry, LegEvidence, RunEvidence, ToolSubsteps
from agentctl.check.lanes import HostFacts
from agentctl.check.mutants import Mutant, Operator
from agentctl.check.plan_data import Phase, phase_text
from agentctl.result import Err, Ok

pytestmark = pytest.mark.evidence("value")
MANIFEST = "src/agentctl/check/source_ownership.toml"
TEST_PATH = "tests/test_early.py"
SOURCE_PATH = "src/agentctl/subject.py"
NONCE = "nonce"
ABSENT = "missing or duplicate census declaration: " + MANIFEST
EMPTY_RUN = RunEvidence(NONCE, frozenset(), frozenset(), frozenset(), (), ())
IDENTITY = "a" * 64
UNAVAILABLE = "gate execution native observation unavailable"
FINALIZERS = LegEvidence(NONCE, tuple((name, 0) for name in steps.FINALIZER_NAMES[:-1]))
HOST = HostFacts("Linux", "x86_64", checkout=True, git=True, debian=True)


def _entries() -> tuple[Entry, ...]:
    manifest = "version = 1\n[[phases]]\nnumber = 0\nprerequisites = []\n"
    for path in (MANIFEST, TEST_PATH, SOURCE_PATH):
        manifest += (
            f'[[artifacts]]\npath = "{path}"\ncapability = "governance"\n'
            "owner = 0\nconsumers = [0]\nrequired = true\n"
        )
    return (
        Entry(MANIFEST, "file", (manifest.encode(),)),
        Entry(TEST_PATH, "file", (b"test",)),
        Entry(SOURCE_PATH, "file", (b"source",)),
    )


def _phase() -> Phase:
    parsed = phase_text(
        Path("phase-0-example.md"),
        f"### Sprint 0.1: Test [Active]\n**Validation tests**: `{TEST_PATH}::case`\n"
        "## Remaining Work\n",
    )
    assert parsed is not None
    return parsed


def _observed() -> tuple[phase_reports.PhaseResult, ...]:
    return (phase_reports.PhaseResult(0, IDENTITY, frozenset({"unverified-run"})),)


def _bare_tools() -> steps.ToolOutcome:
    return steps.ToolOutcome(0, Err("evidence"), Err("substeps"))


def _capture(
    tools: steps.ToolOutcome,
    census: tuple[Entry, ...] | None,
    claims: tuple[tuple[Mutant, ...], tuple[tuple[str, int], ...]] | None = ((), ()),
) -> steps.ProvisionalCapture:
    return steps.ProvisionalCapture(
        Err("census") if census is None else Ok(census),
        Ok((_phase(),)),
        tools,
        claims,
        Err("oracle"),
        NONCE,
        (),
        (),
    )


def _ok(value: object) -> object:
    return lambda *_args, **_kwargs: Ok(value)


def _err(message: str) -> object:
    return lambda *_args, **_kwargs: Err(message)


def test_source_guard_observations_report_an_invalid_census() -> None:
    """Duplicate census paths become a shared validator source issue."""
    duplicate = (Entry("src/a.py", "file", (b"",)),) * 2
    observed = steps.__dict__["_source_guard_observations"](Ok(duplicate), ())
    assert [issue.message for issue in observed] == [
        "validator source census: invalid or duplicate source census paths"
    ]


def test_collection_refuses_inconsistent_observations() -> None:
    """Passed cases that were never executed invalidate the collection join."""
    observed = RunEvidence(
        NONCE, frozenset(), frozenset(), frozenset({"tests/test_x.py::case"}), (), ()
    )
    result = steps.collection_observations(_entries(), (_phase(),), observed, NONCE, ())
    assert result == Err("invalid collection declarations or observations")


def test_scoped_capture_mapping_requires_current_native_census() -> None:
    """Scoped mutant mapping needs claims and a native snapshot of the same census."""
    function = steps.__dict__["_scoped_capture_mapping"]
    assert function(_capture(_bare_tools(), None), ()) == Err(
        "scoped mutant observations unavailable"
    )
    stale = steps.NativeSnapshot(EMPTY_RUN, (), _entries())
    tools = replace(_bare_tools(), native=Ok(stale))
    assert function(_capture(tools, ()), ()) == Err(
        "scoped mutant observations unavailable"
    )


def test_gate_execution_collection_refuses_unavailable_native_and_mapping() -> None:
    """Native absence needs a failed command, and scoped mutants need a mapping."""
    collection = Ok(((0, frozenset()),))
    declarations = (_phase(),)
    assert steps.gate_execution_collection(
        collection, _capture(_bare_tools(), ()), declarations, (), EMPTY_RUN
    ) == Err(UNAVAILABLE)
    snapshot = steps.NativeSnapshot(EMPTY_RUN, (), ())
    scoped = replace(
        _capture(replace(_bare_tools(), native=Ok(snapshot)), (), claims=None),
        scoped_mutants=True,
    )
    assert steps.gate_execution_collection(
        collection, scoped, declarations, (), EMPTY_RUN
    ) == Err("scoped mutant observations unavailable")


def _mutant() -> Mutant:
    return Mutant("mutant-one", Operator.DELETE, SOURCE_PATH, "a", "b", (), "reason")


def test_captured_observations_retain_unscoped_native_claims(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Mutant claims without native evidence mark the capture scoped, then join."""
    pytest_tools = replace(_bare_tools(), pytest=Ok(EMPTY_RUN))
    capture = _capture(pytest_tools, (), claims=((_mutant(),), (("mutant-one", 0),)))
    function = steps.__dict__["_captured_phase_observations"]
    assert function(capture) == Err("captured tool observations unavailable")
    monkeypatch.setattr(steps, "provisional_tool_failures", _ok(frozenset()))
    assert function(capture) == Err(ABSENT)


def _coverage_patches(patch: pytest.MonkeyPatch, report: bytes) -> None:
    patch.setattr(steps, "_parent_bound_census", _ok(_entries()))
    patch.setattr(steps, "_coverage_handoff_files", _ok((b"{}", report)))
    tools = (LegEvidence(NONCE, ()), ToolSubsteps(NONCE, ()))
    patch.setattr(steps, "_read_sealed_tool_results", _ok(tools))
    patch.setattr(steps, "host_observation", _ok(HOST))
    patch.setattr(steps, "census_phases", _ok((_phase(),)))
    patch.setattr(steps, "_coverage_declarations", _ok(("1", ())))


def test_parent_coverage_inputs_refuse_each_unreadable_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Coverage reconstruction names undeclared phases and malformed reports."""
    function = steps.__dict__["_parent_coverage_inputs"]
    context = steps.CheckRun(tmp_path, tmp_path, NONCE, "Linux")
    _coverage_patches(monkeypatch, b"{")
    assert isinstance(function(context, tmp_path, ""), Err)
    expected = (
        (b"\xff", "phase coverage report is not UTF-8"),
        (b"{", "phase coverage inputs are invalid"),
    )
    for report, message in expected:
        _coverage_patches(monkeypatch, report)
        assert function(context, tmp_path, "") == Err(message)
    monkeypatch.setattr(steps, "census_phases", _err("no phases"))
    assert function(context, tmp_path, "") == Err(
        "phase coverage declarations unavailable"
    )


def _sealed_inputs(report: bytes, nonce: str) -> steps.CoverageAttributionInputs:
    snapshot = steps.CoverageSnapshot(NONCE, (), b"{}", (0, 0), report, (0, 0), ())
    return steps.CoverageAttributionInputs(
        (),
        (),
        nonce,
        "Linux",
        Ok(HOST),
        Ok(snapshot),
        Ok(ToolSubsteps(NONCE, ())),
        Ok(LegEvidence(NONCE, ())),
    )


def test_coverage_inputs_seal_refuses_unreadable_reports() -> None:
    """The coverage seal is false for a missing nonce, bad bytes or declarations."""
    assert not steps.coverage_inputs_sealed(_sealed_inputs(b"{}", ""), "")
    assert not steps.coverage_inputs_sealed(_sealed_inputs(b"\xff", NONCE), "")
    assert not steps.coverage_inputs_sealed(_sealed_inputs(b"{}", NONCE), "")


def test_receipt_native_observation_refuses_unreadable_scopes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A localized native absence needs readable native scopes to be proven."""
    failed = replace(
        FINALIZERS,
        outcomes=tuple(
            (name, 1 if name == "native-observation" else code)
            for name, code in FINALIZERS.outcomes
        ),
    )
    collection = _capture(replace(_bare_tools(), native=Err("absent")), ())
    context = steps.CheckRun(tmp_path, tmp_path, NONCE, "Linux")
    inputs = steps.ReceiptNativeInputs(
        context, tmp_path, "", failed, _observed(), (_phase(),), collection
    )
    monkeypatch.setattr(steps, "_verify_localized_native_finalizers", _ok(None))
    assert steps.__dict__["_receipt_native_observation"](inputs) == Err(ABSENT)


def _receipt_patches(patch: pytest.MonkeyPatch) -> steps.CheckRun:
    nonce = NONCE
    entries = (
        Entry("pyproject.toml", "file", (b"config",)),
        Entry("src", "directory", (b"",)),
        Entry("src/source", "file", (b"bytes",)),
        Entry("tests", "directory", (b"",)),
    )
    phase = phase_reports.PhaseInputs(
        0, frozenset({"source"}), frozenset({"test"}), frozenset()
    )
    work = ownership.ScopedPhaseWork(
        ownership.PhaseWork((phase,), (("source", b"bytes"),)), ((0, frozenset()),)
    )
    manifest = RunEvidence(
        nonce, frozenset({"test"}), frozenset({"test"}), frozenset({"test"}), (), ()
    )
    killers = mutant_report.Report(nonce, (), "digest")
    tools = replace(
        _bare_tools(),
        pytest=Ok(manifest),
        native=Ok(steps.NativeSnapshot(manifest, (), entries)),
        killers=Ok(killers),
    )
    capture = steps.ProvisionalCapture(
        Ok(entries), Ok(()), tools, ((), ()), Ok(()), nonce, (), ()
    )
    facts = (coverage_hosts.CoverageFact("src/agentctl/example.py", 0, 0),)
    snapshot = steps.CoverageSnapshot(nonce, facts, b"r", (1, 1), b"p", (1, 2), entries)
    coverage = steps.CoverageAttributionInputs(
        entries,
        (phase,),
        nonce,
        "Linux",
        Ok(HOST),
        Ok(snapshot),
        Ok(ToolSubsteps(nonce, ())),
    )
    owners = (coverage_hosts.CoverageOwner("src/agentctl/example.py", frozenset({0})),)
    patch.setattr(steps, "sealed_finalizer_observation", _ok(FINALIZERS))
    patch.setattr(steps, "_provisional_values_for_identity", _ok(_observed()))
    patch.setattr(steps, "_parent_collection_capture", _ok(((), capture)))
    patch.setattr(steps, "_parent_coverage_inputs", _ok(coverage))
    for name in (
        "verify_provisional_input_identities",
        "verify_provisional_collection",
        "verify_provisional_coverage",
        "verify_host_handoff",
        "verify_native_handoff",
        "collection_capture_sealed",
    ):
        patch.setattr(steps, name, _ok(None))
    patch.setattr(steps, "coverage_inputs_sealed", lambda *_args: True)
    patch.setattr(steps, "scoped_source_inputs", _ok(work))
    patch.setattr(mutant_report, "validate", _ok(killers))
    patch.setattr(steps, "_coverage_captured_facts", _ok(facts))
    patch.setattr(steps, "_coverage_source_owners", _ok(owners))
    patch.setattr(steps, "_coverage_declarations", _ok(("1", ())))
    patch.setattr(steps, "receipt_native_citations", _ok(((0, "haskell:declared"),)))
    return steps.CheckRun(Path.cwd(), Path.cwd(), nonce, "Linux")


def test_receipt_inputs_refuse_each_late_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unavailable observations, killers and native citations block receipt inputs."""
    context = _receipt_patches(monkeypatch)
    assert isinstance(steps.retained_receipt_inputs(context, Path.cwd(), ""), Ok)
    monkeypatch.setattr(steps, "receipt_native_citations", _err("citations"))
    assert steps.retained_receipt_inputs(context, Path.cwd(), "") == Err(
        "receipt input declarations unavailable"
    )
    monkeypatch.setattr(mutant_report, "validate", _err("killers"))
    assert steps.retained_receipt_inputs(context, Path.cwd(), "") == Err(
        "receipt input observations are invalid"
    )
    monkeypatch.setattr(steps, "_provisional_values_for_identity", _err("values"))
    assert steps.retained_receipt_inputs(context, Path.cwd(), "") == Err(
        "receipt input evidence unavailable"
    )
