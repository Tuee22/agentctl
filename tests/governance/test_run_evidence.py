# Copyright (c) 2026 agentctl contributors.
"""Independent manifest records and explicit canonical digest byte vectors."""

import ast
import hashlib
import json
import os
import platform
import re
import sys
from collections.abc import Callable
from dataclasses import asdict, replace
from functools import partial
from pathlib import Path
from typing import Literal, Protocol, runtime_checkable

import pytest

from agentctl import foundation_process, process
from agentctl.check import (
    coverage_hosts,
    mutant_report,
    ownership,
    phase_reports,
    steps,
)
from agentctl.check.evidence import (
    Entry,
    LegEvidence,
    RunEvidence,
    ToolSubsteps,
    digest,
    digest_census,
    parse_legs_bytes,
    parse_manifest,
    read_legs,
    read_manifest,
    read_oracle_details,
    read_tool_substeps,
    source_census,
    source_target,
    verify,
)
from agentctl.check.lanes import HostFacts
from agentctl.check.mutants import Mutant, Operator
from agentctl.check.phase_reports import PhaseResult
from agentctl.check.plan_data import Phase, Sprint, phases
from agentctl.check.steps import (
    CheckRun,
    PostRunInputs,
    ToolOutcome,
    _run_tools_observed,
    oracle_details_unchanged,
    oracle_observation,
    oracle_outcomes_unchanged,
    post_run,
    report_pytest_leg,
    summarize,
)
from agentctl.check.validator.closure import CapturedPolicy
from agentctl.check.writeguard import Snapshot
from agentctl.foundation_process_values import (
    Output,
    ProcessImageFile,
    ProcessObservation,
    SpawnError,
)
from agentctl.result import Err, Ok, Result
from tests.harness.git import repository
from tests.harness.oracle import Object, Store, load_scoped

NODE = "tests/unit/test_example.py::test_one"


def _synthetic_gate_output(streams: tuple[str, str]) -> Output:
    """Supply a controlled child observation to unrelated parent-route tests."""
    selected = steps.gate_interpreter_identity(Path(sys.executable))
    assert isinstance(selected, Ok)
    image = ProcessObservation(
        "Linux", os.getpid() + 1, 1, selected.value.path, _image_file(selected.value)
    )
    return Output(0, *streams, observation=Ok(image))


def _image_file(identity: steps.GateInterpreterIdentity) -> ProcessImageFile:
    return ProcessImageFile(
        identity.device,
        identity.inode,
        identity.size,
        identity.modified_ns,
        identity.sha256,
    )


@pytest.mark.evidence("value")
def test_retained_receipt_inputs_join_sealed_observations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Receipt inputs require the same nonce, census and sealed observations."""
    nonce = "current"
    context = CheckRun(tmp_path, tmp_path, nonce, "Linux")
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
    observation = PhaseResult(0, "a" * 64, frozenset({"unverified-run"}))
    manifest = RunEvidence(
        nonce, frozenset({"test"}), frozenset({"test"}), frozenset({"test"}), (), ()
    )
    native = steps.NativeSnapshot(manifest, (), entries)
    killers = mutant_report.Report(nonce, (), "digest")
    tools = ToolOutcome(
        0,
        Err("unused"),
        Err("unused"),
        pytest=Ok(manifest),
        native=Ok(native),
        killers=Ok(killers),
    )
    capture = steps.ProvisionalCapture(
        Ok(entries), Ok(()), tools, ((), ()), Ok(()), nonce, (), ()
    )
    host = HostFacts("Linux", "x86_64", checkout=True, git=True, debian=True)
    facts = (coverage_hosts.CoverageFact("src/agentctl/example.py", 0, 0),)
    snapshot = steps.CoverageSnapshot(
        nonce, facts, b"record", (1, 1), b"report", (1, 2), entries
    )
    coverage = steps.CoverageAttributionInputs(
        entries,
        (phase,),
        nonce,
        "Linux",
        Ok(host),
        Ok(snapshot),
        Ok(ToolSubsteps(nonce, ())),
    )
    owners = (coverage_hosts.CoverageOwner("src/agentctl/example.py", frozenset({0})),)
    finalizers = LegEvidence(
        nonce, tuple((name, 0) for name in steps.FINALIZER_NAMES[:-1])
    )
    monkeypatch.setattr(
        steps, "sealed_finalizer_observation", lambda *_args: Ok(finalizers)
    )
    monkeypatch.setattr(
        steps, "_provisional_values_for_identity", lambda *_args: Ok((observation,))
    )
    monkeypatch.setattr(
        steps, "_parent_collection_capture", lambda *_args: Ok(((), capture))
    )
    monkeypatch.setattr(steps, "_parent_coverage_inputs", lambda *_args: Ok(coverage))
    for name in (
        "verify_provisional_input_identities",
        "verify_provisional_collection",
        "verify_provisional_coverage",
        "verify_host_handoff",
        "verify_native_handoff",
        "collection_capture_sealed",
    ):
        monkeypatch.setattr(steps, name, lambda *_args: Ok(None))
    monkeypatch.setattr(steps, "coverage_inputs_sealed", lambda *_args: True)
    monkeypatch.setattr(steps, "scoped_source_inputs", lambda *_args: Ok(work))
    monkeypatch.setattr(mutant_report, "validate", lambda *_args: Ok(killers))
    monkeypatch.setattr(steps, "_coverage_captured_facts", lambda *_args: Ok(facts))
    monkeypatch.setattr(steps, "_coverage_source_owners", lambda *_args: Ok(owners))
    monkeypatch.setattr(steps, "_coverage_declarations", lambda *_args: Ok(("1", ())))
    monkeypatch.setattr(
        steps, "receipt_native_citations", lambda *_args: Ok(((0, "haskell:declared"),))
    )
    captured = steps.retained_receipt_inputs(context, tmp_path, "sealed")
    assert isinstance(captured, Ok), captured
    assert captured.value.observations == (observation,)
    assert captured.value.python == manifest
    assert captured.value.coverage == facts
    assert captured.value.native_citations == ((0, "haskell:declared"),), (
        "receipt native citations were lost"
    )
    failed_finalizers = replace(
        finalizers,
        outcomes=tuple(
            (name, 1 if name == "write-guard" else code)
            for name, code in finalizers.outcomes
        ),
    )
    monkeypatch.setattr(
        steps, "sealed_finalizer_observation", lambda *_args: Ok(failed_finalizers)
    )
    assert isinstance(
        steps.retained_receipt_inputs(context, tmp_path, "sealed"), Err
    ), "failed receipt integrity was accepted"
    monkeypatch.setattr(
        steps, "sealed_finalizer_observation", lambda *_args: Ok(finalizers)
    )
    monkeypatch.setattr(
        steps,
        "_parent_collection_capture",
        lambda *_args: Ok(((), replace(capture, nonce="stale"))),
    )
    assert isinstance(
        steps.retained_receipt_inputs(context, tmp_path, "sealed"), Err
    ), "stale receipt input nonce was accepted"
    monkeypatch.setattr(
        steps, "_parent_collection_capture", lambda *_args: Ok(((), capture))
    )
    monkeypatch.setattr(
        steps,
        "_parent_coverage_inputs",
        lambda *_args: Ok(replace(coverage, entries=())),
    )
    assert isinstance(
        steps.retained_receipt_inputs(context, tmp_path, "sealed"), Err
    ), "different receipt source census was accepted"
    monkeypatch.setattr(steps, "_parent_coverage_inputs", lambda *_args: Ok(coverage))
    monkeypatch.setattr(steps, "coverage_inputs_sealed", lambda *_args: False)
    assert isinstance(
        steps.retained_receipt_inputs(context, tmp_path, "sealed"), Err
    ), "unsealed receipt coverage was accepted"
    _receipt_native_absence_control(
        context, finalizers, observation, capture, monkeypatch
    )


def _receipt_native_absence_control(
    context: CheckRun,
    finalizers: LegEvidence,
    observation: PhaseResult,
    capture: steps.ProvisionalCapture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Require independent scope and finalizer proofs for a missing native leg."""
    tmp_path = context.directory
    native_failure = replace(
        finalizers,
        outcomes=tuple(
            (name, 1 if name == "native-observation" else code)
            for name, code in finalizers.outcomes
        ),
    )
    missing = replace(
        observation,
        failures=frozenset({"unverified-run", "native observation unavailable"}),
    )
    absent_collection = replace(
        capture, tools=replace(capture.tools, native=Err("absent"))
    )
    scopes = ((0, frozenset({"native observation unavailable"})),)
    native_inputs = steps.ReceiptNativeInputs(
        context, tmp_path, "sealed", native_failure, (missing,), (), absent_collection
    )
    monkeypatch.setattr(
        steps, "_verify_localized_native_finalizers", lambda *_args: Ok(None)
    )
    monkeypatch.setattr(steps, "unavailable_native_scopes", lambda *_args: Ok(scopes))
    assert steps.__dict__["_receipt_native_observation"](native_inputs) == Ok(
        (None, scopes)
    )
    monkeypatch.setattr(
        steps, "sealed_finalizer_observation", lambda *_args: Ok(native_failure)
    )
    monkeypatch.setattr(
        steps, "_provisional_values_for_identity", lambda *_args: Ok((missing,))
    )
    monkeypatch.setattr(
        steps, "_parent_collection_capture", lambda *_args: Ok(((), absent_collection))
    )
    monkeypatch.setattr(steps, "coverage_inputs_sealed", lambda *_args: True)
    absent_capture = steps.retained_receipt_inputs(context, tmp_path, "sealed")
    assert isinstance(absent_capture, Ok), absent_capture
    assert absent_capture.value.native is None
    assert absent_capture.value.native_absence == scopes
    assert isinstance(
        steps.__dict__["_receipt_native_observation"](
            replace(native_inputs, observations=(observation,))
        ),
        Err,
    ), "receipt native absence attribution was omitted"
    monkeypatch.setattr(
        steps, "_verify_localized_native_finalizers", lambda *_args: Err("bad proof")
    )
    assert isinstance(
        steps.__dict__["_receipt_native_observation"](native_inputs), Err
    ), "unproven receipt native absence was accepted"


@pytest.mark.evidence("value")
def test_receipt_native_citations_include_plan_and_mutant_requirements() -> None:
    """Native citations survive even when their cases are not observed."""
    table_text = (
        "## Gate Integrity\n\n| Requirement | Tests |\n| --- | --- |\n"
        "| R1 | `haskell:suite/plan` |\n"
    )
    sprint = Sprint("0.1", "Active", "**Validation tests**: `haskell:suite/sprint`\n")
    phase = Phase(0, Path("phase-0-example.md"), table_text, (sprint,))
    mutant = Mutant(
        "M-example",
        Operator.DELETE,
        "sample.py",
        "old",
        "",
        ("haskell:suite/killer",),
        "reason",
    )
    citations = steps.receipt_native_citations((phase,), (mutant,), (("M-example", 0),))
    assert citations == Ok(
        (
            (0, "haskell:suite/killer"),
            (0, "haskell:suite/plan"),
            (0, "haskell:suite/sprint"),
        )
    ), "native receipt citations were omitted"
    assert isinstance(steps.receipt_native_citations((phase,), (mutant,), ()), Err)
    assert isinstance(
        steps.receipt_native_citations((phase,), (mutant,), (("M-example", True),)), Err
    )


@pytest.mark.evidence("value")
def test_phase_receipt_evidence_scopes_actual_results() -> None:
    """Earlier evidence stays complete while later failures remain on their owner."""
    nonce = "current"
    early = phase_reports.PhaseInputs(
        0, frozenset({"native/early"}), frozenset({"test_early"}), frozenset()
    )
    later = phase_reports.PhaseInputs(
        1, frozenset({"native/later"}), frozenset({"test_later"}), frozenset({0})
    )
    observations = (
        PhaseResult(0, "a" * 64, frozenset({"unverified-run"})),
        PhaseResult(1, "b" * 64, frozenset({"unverified-run"})),
    )
    early_mutant = mutant_report.PREFIX + "M-early]"
    later_mutant = mutant_report.PREFIX + "M-later]"
    collected = frozenset({"test_early", "test_later", early_mutant, later_mutant})
    python = RunEvidence(
        nonce, collected, collected, frozenset({"test_early", early_mutant}), (), ()
    )
    cases = frozenset({"haskell:early", "haskell:later"})
    native_manifest = RunEvidence(
        nonce, cases, cases, frozenset({"haskell:early"}), (), ()
    )
    native = steps.NativeSnapshot(
        native_manifest,
        (("haskell:early", "native/early"), ("haskell:later", "native/later")),
        (),
    )
    killed = mutant_report.Record(
        "M-early", "", (mutant_report.Killer("killer", "passed", "killed"),)
    )
    failed = mutant_report.Record(
        "M-later", "", (mutant_report.Killer("killer", "passed", "failed:mutant"),)
    )
    report = mutant_report.Report(nonce, (killed, failed), "digest")
    coverage = (
        coverage_hosts.CoverageFact("src/agentctl/early.py", 0, 0),
        coverage_hosts.CoverageFact("src/agentctl/later.py", 1, 0),
    )
    owners = (
        coverage_hosts.CoverageOwner("src/agentctl/early.py", frozenset({0, 1})),
        coverage_hosts.CoverageOwner("src/agentctl/later.py", frozenset({1})),
    )
    captured = steps.ReceiptInputs(
        nonce,
        "digest",
        (early, later),
        observations,
        HostFacts("Linux", "x86_64", checkout=True, git=True, debian=True),
        python,
        native,
        report,
        (("M-early", 0), ("M-later", 1)),
        coverage,
        owners,
    )
    scoped = steps.phase_receipt_evidence(captured)
    assert isinstance(scoped, Ok), scoped
    first, second = scoped.value
    assert (
        first.required_tests
        == first.passed_tests
        == frozenset({"test_early", "haskell:early"})
    )
    assert first.required_mutants == first.killed_mutants == frozenset({"M-early"}), (
        "later mutant affected earlier receipt evidence"
    )
    assert (
        first.required_coverage == first.covered == frozenset({"src/agentctl/early.py"})
    )
    assert first.failures == frozenset({"unverified-run"}), (
        "later failure poisoned receipt evidence"
    )
    assert second.prerequisites == ((0, "a" * 64),)
    assert "receipt test missing: test_later" in second.failures
    assert "receipt test missing: haskell:later" in second.failures
    assert "receipt mutant missing: M-later" in second.failures
    assert "receipt coverage missing: src/agentctl/later.py" in second.failures
    with_missing_native = steps.phase_receipt_evidence(
        replace(captured, native_citations=((1, "haskell:missing"),))
    )
    assert isinstance(with_missing_native, Ok)
    assert "haskell:missing" in with_missing_native.value[1].required_tests, (
        "missing native citation was omitted from receipt requirements"
    )
    assert (
        "receipt test missing: haskell:missing" in with_missing_native.value[1].failures
    )
    assert with_missing_native.value[0] == first
    shared_native = steps.phase_receipt_evidence(
        replace(
            captured,
            phases=(
                replace(early, inputs=early.inputs | frozenset({"native/later"})),
                later,
            ),
            native_citations=((1, "haskell:later"),),
        )
    )
    assert isinstance(shared_native, Ok)
    assert shared_native.value[0] == first, (
        "later native citation poisoned earlier receipt evidence"
    )
    absent_scopes = (
        (0, frozenset()),
        (1, frozenset({"native observation unavailable"})),
    )
    absent_observations = (
        observations[0],
        replace(
            observations[1],
            failures=frozenset({"unverified-run", "native observation unavailable"}),
        ),
    )
    absent = replace(
        captured,
        phases=(
            replace(early, inputs=frozenset({"shared/input"})),
            replace(later, inputs=frozenset({"src/agentctl/haskell/test/later.hs"})),
        ),
        observations=absent_observations,
        native=None,
        native_citations=((1, "haskell:later"),),
        native_absence=absent_scopes,
    )
    scoped_absence = steps.phase_receipt_evidence(absent)
    assert isinstance(scoped_absence, Ok), scoped_absence
    assert scoped_absence.value[0].failures == frozenset({"unverified-run"}), (
        "later native absence poisoned earlier receipt evidence"
    )
    assert "native observation unavailable" in scoped_absence.value[1].failures
    assert "receipt test missing: haskell:later" in scoped_absence.value[1].failures
    assert isinstance(
        steps.phase_receipt_evidence(
            replace(absent, native_absence=((0, frozenset()), (1, frozenset())))
        ),
        Err,
    ), "unscoped native absence was accepted"
    assert isinstance(
        steps.phase_receipt_evidence(replace(absent, observations=observations)), Err
    ), "native absence was omitted from receipt evidence"
    assert isinstance(
        steps.phase_receipt_evidence(
            replace(
                absent,
                phases=(
                    replace(
                        early, inputs=frozenset({"src/agentctl/haskell/test/early.hs"})
                    ),
                    absent.phases[1],
                ),
            )
        ),
        Err,
    ), "unattributed native source was accepted"
    _receipt_input_refusal_controls(captured, python, coverage, observations)


def _receipt_input_refusal_controls(
    captured: steps.ReceiptInputs,
    python: RunEvidence,
    coverage: tuple[coverage_hosts.CoverageFact, ...],
    observations: tuple[PhaseResult, ...],
) -> None:
    """Reject stale, incomplete or malformed candidate inputs."""
    assert isinstance(
        steps.phase_receipt_evidence(replace(captured, nonce="stale")), Err
    ), "stale receipt evidence nonce was accepted"
    assert isinstance(
        steps.phase_receipt_evidence(
            replace(captured, python=replace(python, nonce="stale"))
        ),
        Err,
    ), "stale receipt python nonce was accepted"
    assert isinstance(
        steps.phase_receipt_evidence(replace(captured, coverage=coverage[:1])), Err
    ), "missing receipt coverage was accepted"
    assert isinstance(
        steps.phase_receipt_evidence(
            replace(captured, mutant_owners=(("M-early", 0), ("M-later", True)))
        ),
        Err,
    ), "boolean receipt owner was accepted"
    assert isinstance(
        steps.phase_receipt_evidence(
            replace(
                captured,
                observations=(
                    replace(observations[0], identity="invalid"),
                    observations[1],
                ),
            )
        ),
        Err,
    ), "invalid receipt input identity was accepted"
    assert isinstance(
        steps.phase_receipt_evidence(
            replace(
                captured,
                observations=(
                    replace(observations[0], failures=frozenset()),
                    observations[1],
                ),
            )
        ),
        Err,
    ), "unverified receipt marker was omitted"


@pytest.mark.evidence("real")
def test_parent_retains_unverified_phase_candidates(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Retain a provisional record only for the checked source and report."""
    root = tmp_path / "checkout"
    (root / "src").mkdir(parents=True)
    (root / "tests").mkdir()
    (root / "pyproject.toml").write_text("[project]\nname = 'fixture'\n")
    (root / "plan.txt").write_text("original plan\n")
    source = root / "src" / "sample.py"
    source.write_text("value = 1\n")
    census = ownership.guarded_census(root)
    assert isinstance(census, Ok), census
    digest_value = digest_census(census.value)
    assert isinstance(digest_value, Ok)
    nonce = "abc123"
    phase = phase_reports.PhaseInputs(
        0, frozenset({"src/sample.py"}), frozenset({"test"}), frozenset()
    )
    observed = PhaseResult(0, "a" * 64, frozenset({"unverified-run"}))
    python = RunEvidence(
        nonce, frozenset({"test"}), frozenset({"test"}), frozenset({"test"}), (), ()
    )
    empty_native = RunEvidence(nonce, frozenset(), frozenset(), frozenset(), (), ())
    inputs = steps.ReceiptInputs(
        nonce,
        digest_value.value,
        (phase,),
        (observed,),
        HostFacts("Linux", "x86_64", checkout=True, git=True, debian=True),
        python,
        steps.NativeSnapshot(empty_native, (), census.value),
        mutant_report.Report(nonce, (), "digest"),
        (),
        (),
        (),
        entries=census.value,
    )
    candidates = steps.phase_receipt_evidence(inputs)
    interpreter = steps.gate_interpreter_identity(Path(sys.executable))
    assert isinstance(candidates, Ok)
    assert isinstance(interpreter, Ok)
    record = steps.phase_candidate_record(inputs, candidates.value, interpreter.value)
    assert isinstance(record, Ok)
    data = json.loads(record.value)
    assert data["status"] == "unverified", "phase candidates were presented as verified"
    assert data["nonce"] == nonce
    assert data["phases"][0]["failures"] == ["unverified-run"]
    state = tmp_path / "state"
    directory = state / "check-reports" / nonce
    directory.mkdir(parents=True)
    streams = ("original output\n", "primary diagnostic\n")
    (directory / "stdout.txt").write_bytes(streams[0].encode())
    (directory / "stderr.txt").write_bytes(streams[1].encode())
    snapshot = steps.retained_report_snapshot(directory, streams)
    assert isinstance(snapshot, Ok)
    report = steps.RetainedGateReport(directory, snapshot.value, Ok(inputs))
    context = CheckRun(root, tmp_path / "run", nonce, "Linux")
    _candidate_retention_control(context, report, streams, capsys, monkeypatch)


def _candidate_retention_control(
    context: CheckRun,
    report: steps.RetainedGateReport,
    streams: tuple[str, str],
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exercise real retention, tampering refusal and source-census checks."""
    directory = report.directory
    state = directory.parent.parent
    assert isinstance(report.receipt_inputs, Ok)
    candidates = steps.phase_receipt_evidence(report.receipt_inputs.value)
    interpreter = steps.gate_interpreter_identity(Path(sys.executable))
    assert isinstance(candidates, Ok)
    assert isinstance(interpreter, Ok)
    record = steps.phase_candidate_record(
        report.receipt_inputs.value, candidates.value, interpreter.value
    )
    assert isinstance(record, Ok)
    changed_artifact = directory / "unexpected.json"
    changed_artifact.write_bytes(b"unexpected")
    assert isinstance(
        steps.retain_phase_candidates(context, state, report, streams, record.value),
        Err,
    ), "changed candidate input snapshot was accepted"
    assert not (directory / "phase-candidates.json").exists(), (
        "changed candidate input snapshot was accepted"
    )
    changed_artifact.unlink()
    retained = steps.__dict__["_join_candidate_handoff"](
        context, state, Ok(report), streams, interpreter
    )
    assert isinstance(retained, Ok), retained
    assert (directory / "phase-candidates.json").is_file(), (
        "phase candidate record was not retained"
    )
    assert (directory / "phase-candidates.json").read_bytes() == record.value, (
        "phase candidate record was not retained"
    )
    assert steps.retained_report_snapshot(directory, streams) == Ok(
        retained.value.snapshot
    )
    candidate_path = directory / "phase-candidates.json"
    candidate_path.write_bytes(record.value + b" ")
    relay = steps.CheckChildResult(
        0,
        streams,
        Ok(directory),
        trusted=True,
        snapshot=retained.value.snapshot,
        interpreter=interpreter.value,
    )
    assert steps.__dict__["_relay_check_child"](relay, cleaned=True) == 1, (
        "changed phase candidate report was accepted"
    )
    output = capsys.readouterr()
    assert "primary diagnostic" in output.err
    candidate_path.write_bytes(record.value)
    (context.root / "plan.txt").write_text("changed plan\n")
    monkeypatch.setattr(
        steps,
        "retain_phase_candidates",
        lambda _context, _state, candidate_report, _streams, _record: Ok(
            candidate_report
        ),
    )
    refused = steps.__dict__["_join_candidate_handoff"](
        context, state, retained, streams, interpreter
    )
    assert isinstance(refused, Err), "changed candidate source was accepted"
    assert "source or observations changed" in refused.error
    assert (directory / "stderr.txt").read_bytes() == streams[1].encode()


@pytest.mark.evidence("value")
def test_mutant_report_joins_corpus_and_pytest_results() -> None:
    """Exact killer identities and aggregate status must match captured inputs."""
    first = "tests/unit/test_subject.py::test_first"
    second = "tests/unit/test_subject.py::test_second"
    record = Mutant(
        "M-test-one",
        Operator.DELETE,
        "src/sample.py",
        "a",
        "b",
        (first, second),
        "named defect",
    )
    node = mutant_report.PREFIX + record.identifier + "]"
    observation = RunEvidence(
        "current", frozenset({node}), frozenset({node}), frozenset(), (), ()
    )
    payload = {
        "nonce": "current",
        "records": [
            {
                "identifier": record.identifier,
                "error": "",
                "killers": [
                    {
                        "node": first,
                        "baseline": "failed:baseline",
                        "mutation": "not-run",
                    },
                    {"node": second, "baseline": "passed", "mutation": "killed"},
                ],
            }
        ],
    }
    raw = json.dumps(payload).encode()
    result = mutant_report.decode(raw, "current")
    assert isinstance(result, Ok), result
    assert mutant_report.validate(result.value, (record,), observation) == result
    scoped = mutant_report.failure_scopes(
        result.value, (record,), observation, ((record.identifier, 1),), (0, 1)
    )
    assert isinstance(scoped, Ok), scoped
    failures = dict(scoped.value)
    assert not failures[0], "later mutant killer poisoned earlier phase"
    assert any(first in message for message in failures[1]), (
        "failed mutant killer was not attributed"
    )
    assert not any(second in message for message in failures[1]), (
        "successful mutant killer was reported as failed"
    )
    assert isinstance(
        mutant_report.failure_scopes(result.value, (record,), observation, (), (0, 1)),
        Err,
    ), "incomplete killer ownership was accepted"
    assert isinstance(
        mutant_report.validate(
            result.value, (replace(record, killers=(second, first)),), observation
        ),
        Err,
    ), "wrong killer identities accepted"
    assert isinstance(
        mutant_report.validate(
            result.value, (record,), replace(observation, passed=frozenset({node}))
        ),
        Err,
    ), "wrong aggregate mutant status accepted"
    assert isinstance(
        mutant_report.validate(
            result.value, (record,), replace(observation, executed=frozenset())
        ),
        Err,
    ), "unexecuted mutant record accepted"
    assert isinstance(mutant_report.decode(raw, "stale"), Err)
    for bad in (
        raw.replace(b'"nonce": "current"', b'"nonce": "current", "nonce": "current"'),
        raw.replace(b'"failed:baseline"', b'"passed"'),
        raw.replace(b'"not-run"', b'"killed"'),
        raw.replace(b'"killed"', b'"invented"'),
    ):
        assert isinstance(mutant_report.decode(bad, "current"), Err), (
            "invalid mutant report accepted"
        )


@pytest.mark.evidence("value")
def test_mutant_report_scopes_execution_errors() -> None:
    """A failed mutation setup is retained for its owner without inventing kills."""
    killer = "tests/unit/test_subject.py::test_first"
    record = Mutant(
        "M-error", Operator.DELETE, "src/sample.py", "a", "b", (killer,), "x"
    )
    node = mutant_report.PREFIX + record.identifier + "]"
    observation = RunEvidence(
        "current", frozenset({node}), frozenset({node}), frozenset(), (), ()
    )
    payload = json.dumps(
        {
            "nonce": "current",
            "records": [
                {"identifier": record.identifier, "error": "copy", "killers": []}
            ],
        }
    ).encode()
    report = mutant_report.decode(payload, "current")
    assert isinstance(report, Ok), report
    result = mutant_report.failure_scopes(
        report.value, (record,), observation, ((record.identifier, 1),), (0, 1)
    )
    assert isinstance(result, Ok), result
    assert not dict(result.value)[0]
    assert dict(result.value)[1] == frozenset({"M-error: copy"}), (
        "mutation setup failure was lost"
    )


@pytest.mark.evidence("value")
def test_tool_record_identity_and_completeness(tmp_path: Path) -> None:
    """Reject stale, ambiguous or incomplete actual tool outcome records."""
    path = tmp_path / "outcomes.json"
    path.write_text(
        '{"nonce":"current","outcomes":[["one",0],["two",1]]}', encoding="utf-8"
    )
    assert isinstance(read_legs(path, "current", ("one", "two")), Ok)
    assert parse_legs_bytes(path.read_bytes(), "current", ("one", "two")) == Ok(
        LegEvidence("current", (("one", 0), ("two", 1)))
    )
    assert isinstance(read_legs(path, "stale", ("one", "two")), Err)
    assert isinstance(read_legs(path, "current", ("two", "one")), Err)
    assert isinstance(read_legs(path, "current", ("one", "one")), Err)
    for value in (
        '{"nonce":"current","nonce":"current","outcomes":[["one",0]]}',
        '{"nonce":"current","outcomes":[["one",true]]}',
        '{"nonce":"current","outcomes":[["one",0]],"extra":1}',
    ):
        path.write_text(value, encoding="utf-8")
        assert isinstance(read_legs(path, "current", ("one",)), Err)
        assert isinstance(parse_legs_bytes(value.encode(), "current", ("one",)), Err)


@pytest.mark.evidence("value")
def test_deep_evidence_records_fail_closed(tmp_path: Path) -> None:
    """Deep JSON is refused by every reader without escaping the gate."""
    path = tmp_path / "record.json"
    contents = "[" * 50000 + "0" + "]" * 50000
    path.write_text(contents, encoding="utf-8")
    (tmp_path / "finalizer-outcomes.json").write_text(contents, encoding="utf-8")
    readers = (
        ("manifest", partial(read_manifest, path)),
        ("legs", partial(read_legs, path, "current", ("pytest",))),
        ("finalizer", partial(steps.finalizer_observation, tmp_path, "current")),
        ("oracle", partial(read_oracle_details, path, "current")),
        ("substeps", partial(read_tool_substeps, path, "current", (("pytest", 1),))),
    )
    for name, read in readers:
        try:
            result = read()
        except RecursionError:
            pytest.fail("deep " + name + " evidence escaped its reader")
        assert isinstance(result, Err), "deep " + name + " evidence was accepted"


@pytest.mark.evidence("value")
def test_oracle_detail_record_boundaries(tmp_path: Path) -> None:
    """Reject stale, duplicate, malformed and invented oracle detail records."""
    path = tmp_path / "oracle-details.json"
    source = "tests/oracles/example.toml"
    valid = {
        "nonce": "current",
        "sources": [source],
        "issues": [[source, "failure"], [None, "shared"]],
    }
    path.write_text(json.dumps(valid), encoding="utf-8")
    captured = read_oracle_details(path, "current")
    assert isinstance(captured, Ok)
    assert oracle_details_unchanged(tmp_path, "current", captured) == 0
    path.write_text(json.dumps({**valid, "issues": []}), encoding="utf-8")
    assert oracle_details_unchanged(tmp_path, "current", captured) == 1, (
        "changed oracle details were accepted"
    )
    for invalid in (
        {**valid, "nonce": "old"},
        {**valid, "sources": [source, source]},
        {**valid, "issues": [["unknown", "failure"]]},
        {**valid, "issues": [[None, ""]]},
        {**valid, "extra": 1},
    ):
        path.write_text(json.dumps(invalid), encoding="utf-8")
        assert isinstance(read_oracle_details(path, "current"), Err), (
            "invalid oracle detail record was accepted"
        )
    path.write_text(
        json.dumps(valid).replace(
            '"nonce": "current"', '"nonce": "old", "nonce": "current"'
        ),
        encoding="utf-8",
    )
    assert isinstance(read_oracle_details(path, "current"), Err)


@pytest.mark.evidence("value")
def test_tool_substep_record_boundaries(tmp_path: Path) -> None:
    """Ordered, bounded integer subprocess observations must match this run."""
    path = tmp_path / "tool-substeps.json"
    expected = (("pytest", 3),)
    valid = {"nonce": "current", "outcomes": [["pytest", [1, 0, 0]]]}
    path.write_text(json.dumps(valid), encoding="utf-8")
    assert isinstance(read_tool_substeps(path, "current", expected), Ok)
    for invalid in (
        {**valid, "nonce": "old"},
        {**valid, "outcomes": [["pytest", [1, 0, 0, 0]]]},
        {**valid, "outcomes": [["pytest", []]]},
        {**valid, "outcomes": [["pytest", [True]]]},
        {**valid, "outcomes": [["wrong", [0]]]},
        {**valid, "extra": 1},
    ):
        path.write_text(json.dumps(invalid), encoding="utf-8")
        assert isinstance(read_tool_substeps(path, "current", expected), Err), (
            "invalid tool substeps were accepted"
        )


@pytest.mark.evidence("value")
def test_pytest_leg_reports_shared_coverage_damage(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Use the real manifest with separate pytest and coverage statuses."""
    path = tmp_path / "pytest-manifest.json"
    path.write_text(
        json.dumps(_record(passed=[], forbidden=["failed: " + NODE])), encoding="utf-8"
    )
    failed_test = ToolOutcome(
        1,
        Ok(LegEvidence("current", (("pytest", 1),))),
        Ok(ToolSubsteps("current", (("pytest", (1, 0, 0)),))),
    )
    assert report_pytest_leg(tmp_path, failed_test) == 0
    path.write_text(json.dumps(_record()), encoding="utf-8")
    failed_coverage = ToolOutcome(
        1,
        Ok(LegEvidence("current", (("pytest", 2),))),
        Ok(ToolSubsteps("current", (("pytest", (0, 0, 2)),))),
    )
    assert report_pytest_leg(tmp_path, failed_coverage) == 1, (
        "shared coverage damage was accepted"
    )
    assert "coverage report failed" in capsys.readouterr().err


@pytest.mark.evidence("value")
def test_oracle_outcomes_survive_later_tools(tmp_path: Path) -> None:
    """A later tool cannot replace, replay or remove the recorded outcomes."""
    path = tmp_path / "oracle-outcomes.json"
    names = ("oracle-validation", "bootstrap-provenance")
    data = {"nonce": "current", "outcomes": [[names[0], 1], [names[1], 0]]}
    path.write_text(json.dumps(data), encoding="utf-8")
    before = oracle_observation(tmp_path, "current")
    assert isinstance(before, Ok)
    assert oracle_outcomes_unchanged(tmp_path, "current", before) == 0
    path.write_text(
        json.dumps({**data, "outcomes": [[names[0], 0], [names[1], 1]]}),
        encoding="utf-8",
    )
    assert oracle_outcomes_unchanged(tmp_path, "current", before) == 1, (
        "changed oracle outcomes were accepted"
    )
    path.write_text(json.dumps({**data, "nonce": "old"}), encoding="utf-8")
    assert oracle_outcomes_unchanged(tmp_path, "current", before) == 1
    path.unlink()
    assert oracle_outcomes_unchanged(tmp_path, "current", before) == 1
    assert (
        oracle_outcomes_unchanged(
            tmp_path, "current", oracle_observation(tmp_path, "current")
        )
        == 1
    )


def _native_control(tmp_path: Path) -> Result[steps.NativeSnapshot, str]:
    """Create an independently readable native case and source record."""
    node = "haskell:agentctl-core-test/Backoff/grows-to-cap"
    source = "src/agentctl/haskell/test/RecoveryTests.hs"
    other = "src/agentctl/haskell/test/OtherTests.hs"
    (tmp_path / "tasty.xml").write_text(
        '<testsuites tests="1"><testsuite><testcase '
        'classname="agentctl-core-test.Backoff" name="grows-to-cap" />'
        "</testsuite></testsuites>",
        encoding="utf-8",
    )
    (tmp_path / "haskell-manifest.json").write_text(
        json.dumps(
            _record(
                collected=[node],
                executed=[node],
                passed=[node],
                classes={node: "value"},
            )
        ),
        encoding="utf-8",
    )
    (tmp_path / "haskell-sources.json").write_text(
        json.dumps({"nonce": "current", "sources": [[node, source]]}), encoding="utf-8"
    )
    artifacts = tuple(
        (name, (tmp_path / name).resolve().as_posix(), "a" * 64)
        for name in ("ghc", "cabal", "native-test")
    )
    (tmp_path / "native-artifacts.json").write_text(
        json.dumps({"nonce": "current", "artifacts": artifacts}), encoding="utf-8"
    )
    entries = (Entry(source, "file", (b"source",)), Entry(other, "file", (b"other",)))
    return steps.native_snapshot(tmp_path, "current", entries)


@pytest.mark.evidence("value")
def test_native_artifact_record_refuses_invalid_inputs(tmp_path: Path) -> None:
    """The retained artifact record requires its nonce, roles and canonical bytes."""
    assert isinstance(_native_control(tmp_path), Ok)
    path = tmp_path / "native-artifacts.json"
    original = path.read_text(encoding="utf-8")
    assert isinstance(steps.native_artifact_record(tmp_path, "current"), Ok)
    for changed in (
        original.replace('"current"', '"stale"'),
        original.replace('"native-test"', '"ghc"'),
        original.replace("a" * 64, "A" * 64, 1),
        original.replace('"nonce":', '"nonce": "current", "nonce":'),
        " " + original,
    ):
        path.write_text(changed, encoding="utf-8")
        assert isinstance(steps.native_artifact_record(tmp_path, "current"), Err), (
            "invalid native artifact record was accepted"
        )


@pytest.mark.evidence("value")
def test_native_handoff_binds_case_sources_and_checkout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A changed case mapping or native source cannot reuse the captured seal."""
    root = tmp_path / "checkout"
    sources = root / "src/agentctl/haskell/test"
    sources.mkdir(parents=True)
    (sources / "RecoveryTests.hs").write_bytes(b"source")
    (sources / "OtherTests.hs").write_bytes(b"other")
    directory = tmp_path / "run"
    directory.mkdir()
    assert isinstance(_native_control(directory), Ok)
    census = steps.ownership.guarded_census(root)
    assert isinstance(census, Ok)
    captured = steps.native_snapshot(directory, "current", census.value)
    assert isinstance(captured, Ok)
    monkeypatch.setattr(
        steps, "_selected_native_artifacts", lambda *_args: Ok(captured.value.artifacts)
    )
    marker = steps.native_observation_seal("current", captured.value)
    assert isinstance(marker, Ok)
    first, *rest = captured.value.artifacts
    changed_artifacts = ((first[0], first[1], "b" * 64), *rest)
    assert (
        steps.native_observation_seal(
            "current", replace(captured.value, artifacts=changed_artifacts)
        )
        != marker
    ), "altered native artifact identity was accepted"
    failed = {
        "python-commands",
        "tool-outcomes",
        "pytest-manifest",
        "oracle-outcomes",
        "host-observation",
        "ruff-observation",
        "ruff-format-observation",
        "coverage-observation",
        "mutant-killers",
        "ty-observation",
        "coverage-text-observation",
    }
    outcomes = tuple((name, int(name in failed)) for name in steps.FINALIZER_NAMES[:-1])
    assert isinstance(steps.record_finalizers(directory, "current", outcomes), Ok)
    context = CheckRun(root, directory, "current", "Linux")
    finalizer = steps.finalizer_seal(steps.evidence.LegEvidence("current", outcomes))
    output = marker.value + "\nphase\n" + finalizer + "\n"
    assert steps.verify_native_handoff(context, directory, output) == Ok(None)
    monkeypatch.setattr(steps, "_selected_native_artifacts", lambda *_args: Ok(()))
    assert isinstance(steps.verify_native_handoff(context, directory, output), Err), (
        "foreign native artifact selection was accepted"
    )
    monkeypatch.setattr(
        steps, "_selected_native_artifacts", lambda *_args: Ok(captured.value.artifacts)
    )
    assert isinstance(
        steps.verify_native_handoff(
            context, directory, output.replace(marker.value + "\n", "", 1)
        ),
        Err,
    ), "missing native seal was accepted"
    assert isinstance(
        steps.verify_native_handoff(context, directory, marker.value + "\n" + output),
        Err,
    ), "duplicate native seal was accepted"
    artifacts = directory / "native-artifacts.json"
    artifact_bytes = artifacts.read_bytes()
    artifacts.write_bytes(artifact_bytes.replace(b"a" * 64, b"b" * 64, 1))
    assert steps.native_snapshot_unchanged(directory, "current", captured) == 1, (
        "changed native artifact escaped finalizer"
    )
    assert isinstance(steps.verify_native_handoff(context, directory, output), Err), (
        "altered native artifact identity was accepted"
    )
    artifacts.write_bytes(artifact_bytes)
    artifacts.unlink()
    assert isinstance(steps.verify_native_handoff(context, directory, output), Err), (
        "missing native artifact record was accepted"
    )
    artifacts.write_bytes(artifact_bytes)
    mapping = directory / "haskell-sources.json"
    original = mapping.read_text(encoding="utf-8")
    mapping.write_text(
        original.replace("RecoveryTests.hs", "OtherTests.hs"), encoding="utf-8"
    )
    assert isinstance(steps.verify_native_handoff(context, directory, output), Err), (
        "altered native case mapping was accepted"
    )
    mapping.write_text(original, encoding="utf-8")
    (sources / "RecoveryTests.hs").write_bytes(b"changed")
    assert isinstance(steps.verify_native_handoff(context, directory, output), Err), (
        "altered native source was accepted"
    )


@pytest.mark.evidence("value")
def test_native_seal_binds_each_observation(tmp_path: Path) -> None:
    """Each native execution field and every captured source byte affects its seal."""
    captured = _native_control(tmp_path)
    assert isinstance(captured, Ok)
    original = captured.value
    marker = steps.native_observation_seal("current", original)
    assert isinstance(marker, Ok)
    node, source = original.sources[0]
    fields = {
        "collected": frozenset(),
        "executed": frozenset(),
        "passed": frozenset(),
        "forbidden": ("failure",),
        "classes": ((node, "real"),),
    }
    for field, value in fields.items():
        changed = replace(
            original, manifest=replace(original.manifest, **{field: value})
        )
        assert steps.native_observation_seal("current", changed) != marker, (
            "native seal omitted " + field
        )
    changed = replace(original, sources=((node, source.replace("Recovery", "Other")),))
    assert steps.native_observation_seal("current", changed) != marker, (
        "native seal omitted case sources"
    )
    altered = tuple(
        replace(entry, payloads=(b"changed",)) if entry.path == source else entry
        for entry in original.entries
    )
    assert (
        steps.native_observation_seal("current", replace(original, entries=altered))
        != marker
    ), "native seal omitted source bytes"
    assert isinstance(steps.native_observation_seal("other", original), Err), (
        "native seal accepted a foreign nonce"
    )


@pytest.mark.evidence("value")
def test_native_handoff_checks_live_and_retained_reports(
    root: Path, tmp_path: Path
) -> None:
    """A parent refuses changed native evidence before and after report copying."""
    project = tmp_path / "checkout"
    source = project / "src/agentctl/haskell/test"
    source.mkdir(parents=True)
    (source / "RecoveryTests.hs").write_bytes(b"source")
    (source / "OtherTests.hs").write_bytes(b"other")
    observed = tmp_path / "observed"
    observed.mkdir()
    assert isinstance(_native_control(observed), Ok)
    for name in (
        "haskell-manifest.json",
        "haskell-sources.json",
        "native-artifacts.json",
    ):
        record = observed / name
        record.write_text(
            record.read_text(encoding="utf-8").replace('"current"', '"abc123"'),
            encoding="utf-8",
        )
    script = """
import json, sys
from pathlib import Path
from agentctl.check import steps
from agentctl.foundation import Err, Ok
from agentctl.foundation_process_values import Output
root, original, directory, state = map(Path, sys.argv[1:5]); directory.mkdir()
nonce = "abc123"
names = ("haskell-manifest.json", "haskell-sources.json", "tasty.xml",
         "native-artifacts.json")
for name in names:
    (directory / name).write_bytes((original / name).read_bytes())
census = steps.ownership.guarded_census(root)
assert isinstance(census, Ok)
observed = steps.native_snapshot(directory, nonce, census.value)
assert isinstance(observed, Ok)
steps._selected_native_artifacts = lambda *_args: Ok(observed.value.artifacts)
marker = steps.native_observation_seal(nonce, observed.value)
assert isinstance(marker, Ok)
failed = {"python-commands", "tool-outcomes", "pytest-manifest", "oracle-outcomes",
          "host-observation", "ruff-observation", "ruff-format-observation",
          "coverage-observation", "mutant-killers", "ty-observation",
          "coverage-text-observation"}
statuses = tuple((name, int(name in failed)) for name in steps.FINALIZER_NAMES[:-1])
final = steps.record_finalizers(directory, nonce, statuses)
phase = steps.record_provisional_phases(directory, nonce, Err("unavailable"))
assert isinstance(final, Ok) and isinstance(phase, Ok)
output = "\\n".join((marker.value, steps.provisional_seal(nonce, phase.value),
    steps.finalizer_seal(final.value), ""))
context = steps.CheckRun(root, directory, nonce, sys.argv[5])
valid = steps.retain_verified_gate_output(context, state.with_name("state-ok"),
    (output, "primary\\n"), verify_handoff=True)
assert isinstance(valid, Ok), valid
live = directory.parent / "live-run"; live.mkdir()
for name in names:
    (live / name).write_bytes((original / name).read_bytes())
assert isinstance(steps.record_finalizers(live, nonce, statuses), Ok)
assert isinstance(steps.record_provisional_phases(live, nonce, Err("unavailable")), Ok)
mapping = live / "haskell-sources.json"
mapping.write_text(mapping.read_text().replace("RecoveryTests.hs", "OtherTests.hs"))
steps.run_observed = lambda *_args, **_kwargs: Ok(Output(0, output, "primary\\n"))
live_state = state.with_name("state-live")
assert steps._run_check_child(steps.CheckRun(root, live, nonce, sys.argv[5]),
    live_state, assume_yes=False) == 1, "live native check was omitted"
stderr = (live_state / "check-reports" / nonce / "stderr.txt").read_text()
assert "native handoff digest mismatch" in stderr, "live native check was omitted"
assert "primary" in stderr
target = state / "check-reports" / nonce / "haskell-sources.json"
seen = [False]
def audit(event, args):
    if (not seen[0] and event == "open" and str(args[0]) == str(target)
        and "r" in str(args[1]) and target.exists()):
        seen[0] = True
        changed = target.read_text().replace("RecoveryTests.hs", "OtherTests.hs")
        target.write_text(changed)
sys.addaudithook(audit)
answer = steps.retain_verified_gate_output(context, state, (output, "primary\\n"),
    verify_handoff=True)
assert isinstance(answer, Err), "post-copy native tampering was accepted"
assert seen[0]
report = state / "check-reports" / nonce
message = (report / "finalizer-handoff.txt").read_text()
assert "native handoff digest mismatch" in message
assert (report / "stderr.txt").read_text() == "primary\\n"
steps._selected_native_artifacts = lambda *_args: Ok(())
foreign_state = state.with_name("state-foreign-selection")
foreign = steps.retain_verified_gate_output(context, foreign_state,
    (output, "primary\\n"), verify_handoff=True)
assert isinstance(foreign, Err), "retained foreign native selection was accepted"
assert "native artifact selection differs" in foreign.error
"""
    child = process.run(
        [
            sys.executable,
            "-c",
            script,
            str(project),
            str(observed),
            str(tmp_path / "parent-run"),
            str(tmp_path / "state"),
            platform.system(),
        ],
        cwd=root,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    assert isinstance(child, Ok), child
    assert child.value.code == 0, child.value.stderr


@pytest.mark.evidence("value")
def test_native_snapshot_captured_before_later_tools(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A following leg cannot replace a native case's captured source."""
    initial = _native_control(tmp_path)
    assert isinstance(initial, Ok)
    node = "haskell:agentctl-core-test/Backoff/grows-to-cap"
    source = "src/agentctl/haskell/test/OtherTests.hs"

    def native_leg(_step: object, directory: Path, _nonce: str) -> int:
        assert isinstance(_native_control(directory), Ok)
        return 0

    def later_leg(*_args: object) -> steps.LegOutcome:
        (tmp_path / "haskell-sources.json").write_text(
            json.dumps({"nonce": "current", "sources": [[node, source]]}),
            encoding="utf-8",
        )
        return steps.LegOutcome(0, (0,))

    monkeypatch.setattr(steps.haskell, "run_step", native_leg)
    monkeypatch.setattr(steps, "_run_leg_observed", later_leg)
    host = steps.hostfacts.current(tmp_path)
    legs = (
        steps.haskell.HaskellStep("cabal-test", host, tmp_path),
        steps.Leg("later", ("unused",)),
    )
    observed = _run_tools_observed(
        tmp_path, tmp_path, "current", legs, source_entries=initial.value.entries
    )
    assert isinstance(observed.native, Ok), (
        "native evidence was not captured before later tools"
    )
    assert steps.native_snapshot_unchanged(tmp_path, "current", observed.native) == 1, (
        "changed native source evidence was accepted"
    )


@pytest.mark.evidence("value")
def test_native_manifest_rejects_symlinks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A native manifest link cannot masquerade as an owned run artifact."""
    captured = _native_control(tmp_path)
    assert isinstance(captured, Ok)
    target = tmp_path / "haskell-manifest.json"
    with monkeypatch.context() as patch:
        patch.setattr(Path, "is_symlink", lambda subject: subject == target)
        assert isinstance(
            steps.native_snapshot(tmp_path, "current", captured.value.entries), Err
        ), "native manifest symlink was accepted"


def _change_finalizer_ty(
    tmp_path: Path, _context: object, _before: object, code: int
) -> int:
    """Replace the type-checker record during a constructed finalizer."""
    (tmp_path / "ty-observation.json").write_bytes(b"changed")
    return code


def _change_finalizer_native(
    tmp_path: Path, _context: object, _before: object, code: int
) -> int:
    """Replace the native source mapping during a constructed finalizer."""
    node = "haskell:agentctl-core-test/Backoff/grows-to-cap"
    source = "src/agentctl/haskell/test/OtherTests.hs"
    (tmp_path / "haskell-sources.json").write_text(
        json.dumps({"nonce": "current", "sources": [[node, source]]}), encoding="utf-8"
    )
    return code


def _change_finalizer_host(
    tmp_path: Path, _context: object, _before: object, code: int
) -> int:
    """Replace host facts during a constructed finalizer."""
    facts = HostFacts(
        family="Windows", architecture="x86_64", checkout=True, git=True, mux=True
    )
    (tmp_path / "host.json").write_text(
        json.dumps({"nonce": "current", "facts": asdict(facts)}), encoding="utf-8"
    )
    return code


def _plant_finalizer_record(
    tmp_path: Path, _context: object, _before: object, code: int
) -> int:
    """Place an unexpected record at the exclusive finalizer evidence path."""
    (tmp_path / "finalizer-outcomes.json").write_text("foreign", encoding="utf-8")
    return code


def _assert_original_tree(args: tuple[object, ...], kwargs: dict[str, object]) -> None:
    """Ensure the original guard is handed to the validation pipeline."""
    if args:
        assert kwargs.get("original_tree") == (), (
            "original guard was not passed to source census"
        )


def _provisional_validation(
    validate: Callable[..., steps.ValidationOutcome], *args: object, **kwargs: object
) -> steps.ValidationOutcome:
    """Return otherwise passing observations with one unverified phase result."""
    return replace(
        validate(*args, **kwargs),
        phase_observations=Ok(
            (PhaseResult(0, "0" * 64, frozenset({"unverified-run"})),)
        ),
    )


def _initial_details_validation(
    validate: Callable[..., steps.ValidationOutcome], *args: object, **kwargs: object
) -> steps.ValidationOutcome:
    """Return a transient initial integrity failure with otherwise intact records."""
    return replace(validate(*args, **kwargs), initial_oracle_details=1)


def _validation_integrity_control(
    validate: Callable[..., steps.ValidationOutcome], *args: object, **kwargs: object
) -> steps.ValidationOutcome:
    """Model damage observed before otherwise successful finalizers."""
    return replace(validate(*args, **kwargs), validation_integrity=1)


def _failed_primary_validation(
    validate: Callable[..., steps.ValidationOutcome], *args: object, **kwargs: object
) -> steps.ValidationOutcome:
    """Return a prior failure with an otherwise intact provisional observation."""
    return replace(_provisional_validation(validate, *args, **kwargs), code=1)


def _native_absence_validation(
    directory: Path,
    validate: Callable[..., steps.ValidationOutcome],
    *args: object,
    **kwargs: object,
) -> steps.ValidationOutcome:
    """Model one failed native step whose report files are all absent."""
    value = validate(*args, **kwargs)
    for name in steps.NATIVE_REPORT_FILES:
        (directory / name).unlink(missing_ok=True)
    marker = steps.native_absence_observation(directory, "current", 1)
    assert isinstance(marker, Ok)
    outcomes = LegEvidence("current", (("cabal-test", 1),))
    (directory / "tool-outcomes.json").write_text(
        json.dumps({"nonce": "current", "outcomes": outcomes.outcomes}),
        encoding="utf-8",
    )
    return replace(
        value,
        code=1,
        tools=Ok(outcomes),
        native=Err("native report absent"),
        native_absence=marker.value,
        phase_observations=Ok(
            (
                PhaseResult(0, "0" * 64, frozenset({"unverified-run"})),
                PhaseResult(
                    1,
                    "1" * 64,
                    frozenset({"unverified-run", "native observation unavailable"}),
                ),
            )
        ),
    )


def _readiness_validation(
    validate: Callable[..., steps.ValidationOutcome], *args: object, **kwargs: object
) -> steps.ValidationOutcome:
    """Require the captured readiness value at the validation boundary."""
    assert kwargs.get("readiness") == ("later readiness",), (
        "later readiness was not passed to validation"
    )
    return _provisional_validation(validate, *args, **kwargs)


def _set_readiness(monkeypatch: pytest.MonkeyPatch, mode: str) -> None:
    """Select the existing focused readiness observation for one control."""
    value = {"readiness": ("later readiness",)}.get(mode, ())
    monkeypatch.setattr(
        steps, "inspect_later_readiness", lambda *_args, **_kwargs: value
    )


def _controlled_finalization(
    effect: Callable[[object, object, int], int],
    context: object,
    before: object,
    code: int,
) -> steps.Finalization:
    """Keep existing finalizer effect controls while preserving both statuses."""
    return steps.Finalization(effect(context, before, code), code)


def _clear_control_records(tmp_path: Path) -> None:
    """Remove records created by the first isolated control run."""
    for name in (
        "finalizer-outcomes.json",
        "provisional-phases.json",
        "ruff-observation.json",
        "ruff-format-observation.json",
        "ty-observation.json",
        "coverage-text.json",
        "python-commands.json",
    ):
        (tmp_path / name).unlink()


def _plant_provisional_record(
    tmp_path: Path, _context: object, _before: object, code: int
) -> int:
    """Simulate an unexpected pre-existing provisional record."""
    (tmp_path / "provisional-phases.json").write_text("foreign", encoding="utf-8")
    return code


def _killer_control(tmp_path: Path) -> Result[mutant_report.Report, str]:
    """Create and capture the original per-killer file for a finalizer control."""
    path = tmp_path / "mutant-killers.json"
    path.write_text('{"nonce":"current","records":[]}', encoding="utf-8")
    return mutant_report.read(path, "current")


def _change_killer_control(
    tmp_path: Path, _context: object, _before: object, code: int
) -> int:
    """Change report bytes after the original observation."""
    (tmp_path / "mutant-killers.json").write_text(
        '{ "nonce":"current","records":[]}', encoding="utf-8"
    )
    return code


def _coverage_control(tmp_path: Path) -> Result[steps.CoverageSnapshot, str]:
    """Create real files for the finalizer's byte and identity control."""
    record, raw = tmp_path / "coverage-report.json", tmp_path / "coverage-raw.json"
    record.write_bytes(b"captured record")
    raw.write_bytes(b"captured report")
    record_stat, raw_stat = record.stat(), raw.stat()
    return Ok(
        steps.CoverageSnapshot(
            "current",
            (),
            record.read_bytes(),
            (record_stat.st_dev, record_stat.st_ino),
            raw.read_bytes(),
            (raw_stat.st_dev, raw_stat.st_ino),
        )
    )


def _ruff_control(tmp_path: Path) -> Result[steps.RuffSnapshot, str]:
    """Create the original Ruff record for the finalizer controls."""
    return steps.record_ruff_snapshot(
        tmp_path, steps.RuffSnapshot("current", tmp_path, Output(0, "[]", ""), ())
    )


def _commands_control(tmp_path: Path) -> Result[steps.PythonCommandsSnapshot, str]:
    return steps.record_python_commands(
        tmp_path,
        "current",
        tmp_path,
        tuple((name, (("python", name),)) for name in steps.PYTHON_COMMAND_NAMES),
        "0" * 64,
    )


def _change_ruff_control(
    tmp_path: Path, _context: object, _before: object, code: int
) -> int:
    """Change the original Ruff record after its initial capture."""
    path = tmp_path / "ruff-observation.json"
    path.write_bytes(path.read_bytes() + b" ")
    return code


def _change_commands_control(
    tmp_path: Path, _context: object, _before: object, code: int
) -> int:
    path = tmp_path / "python-commands.json"
    path.write_bytes(path.read_bytes() + b" ")
    return code


def _change_ruff_format_control(
    tmp_path: Path, _context: object, _before: object, code: int
) -> int:
    path = tmp_path / "ruff-format-observation.json"
    path.write_bytes(path.read_bytes() + b" ")
    return code


@pytest.mark.evidence("value")
def test_coverage_handoff_seal_follows_finalizer(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Emit the original coverage seal only after its finalizer succeeds."""
    final = steps.record_finalizers(
        tmp_path, "current", tuple((name, 0) for name in steps.FINALIZER_NAMES[:-1])
    )
    phase = steps.record_provisional_phases(tmp_path, "current", Err("unavailable"))
    killers = _killer_control(tmp_path)
    coverage = _coverage_control(tmp_path)
    assert isinstance(final, Ok)
    assert isinstance(phase, Ok)
    assert isinstance(killers, Ok)
    assert isinstance(coverage, Ok)
    marker = steps.coverage_seal(
        "current", coverage.value.record, coverage.value.report
    )
    steps.emit_handoff_seals("current", final, phase, (killers, coverage), (0, 0, 0, 0))
    assert capsys.readouterr().out.splitlines()[0] == marker, (
        "coverage handoff seal was not emitted"
    )
    steps.emit_handoff_seals("current", final, phase, (killers, coverage), (0, 0, 0, 1))
    assert marker not in capsys.readouterr().out, (
        "failed coverage finalizer emitted a seal"
    )


@pytest.mark.evidence("value")
def test_ruff_handoff_seal_follows_finalizer(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Emit the original Ruff seal only after all supporting records survive."""
    final = steps.record_finalizers(
        tmp_path, "current", tuple((name, 0) for name in steps.FINALIZER_NAMES[:-1])
    )
    phase = steps.record_provisional_phases(tmp_path, "current", Err("unavailable"))
    ruff = _ruff_control(tmp_path)
    assert isinstance(final, Ok)
    assert isinstance(phase, Ok)
    assert isinstance(ruff, Ok)
    marker = steps.ruff_seal("current", ruff.value.record)
    steps.emit_ruff_handoff("current", final, phase, ruff, (0, 0, 0))
    assert capsys.readouterr().out.strip() == marker, (
        "Ruff handoff seal was not emitted"
    )
    for codes in ((1, 0, 0), (0, 1, 0), (0, 0, 1)):
        steps.emit_ruff_handoff("current", final, phase, ruff, codes)
        assert marker not in capsys.readouterr().out, (
            "failed Ruff finalizer emitted a seal"
        )


def _oracle_finalizer_control(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    mode: Literal[
        "handoff",
        "initial_details",
        "validation_integrity",
        "oracle",
        "details",
        "tools",
        "substeps",
        "pytest",
        "killers",
        "native",
        "native_absence",
        "host",
        "ruff",
        "ruff_format",
        "ty",
        "python_commands",
        "provisional",
        "primary",
        "record",
        "phase_record",
        "readiness",
    ],
) -> None:
    """Exercise changes at a chosen boundary with real outcome files."""
    path, details_path, tool_path, substeps_path, pytest_path, host_path = (
        tmp_path / name
        for name in (
            "oracle-outcomes.json",
            "oracle-details.json",
            "tool-outcomes.json",
            "tool-substeps.json",
            "pytest-manifest.json",
            "host.json",
        )
    )
    host_facts = HostFacts(
        family="Windows", architecture="x86_64", checkout=True, git=True
    )
    names = ("oracle-validation", "bootstrap-provenance")
    original = {"nonce": "current", "outcomes": [[names[0], 0], [names[1], 0]]}

    def validate(*_args: object, **_kwargs: object) -> steps.ValidationOutcome:
        _assert_original_tree(_args, _kwargs)
        path.write_text(json.dumps(original), encoding="utf-8")
        details_path.write_text(
            json.dumps({"nonce": "current", "sources": [], "issues": []}),
            encoding="utf-8",
        )
        tool_path.write_text(
            json.dumps({"nonce": "current", "outcomes": [["tool", 0]]}),
            encoding="utf-8",
        )
        substeps_path.write_text(
            json.dumps({"nonce": "current", "outcomes": [["tool", [0]]]}),
            encoding="utf-8",
        )
        pytest_path.write_text(json.dumps(_record()), encoding="utf-8")
        host_path.write_text(
            json.dumps({"nonce": "current", "facts": asdict(host_facts)}),
            encoding="utf-8",
        )
        tools = read_legs(tool_path, "current", ("tool",))
        assert isinstance(tools, Ok)
        substeps = read_tool_substeps(substeps_path, "current", (("tool", 1),))
        assert isinstance(substeps, Ok)
        return steps.ValidationOutcome(
            0,
            oracle_observation(tmp_path, "current"),
            read_oracle_details(details_path, "current"),
            Ok(tools.value),
            Ok(substeps.value),
            steps.pytest_observation(tmp_path, "current"),
            _native_control(tmp_path),
            steps.host_observation(tmp_path, "current"),
            killers=_killer_control(tmp_path),
            coverage=_coverage_control(tmp_path),
            ruff=_ruff_control(tmp_path),
            python_commands=_commands_control(tmp_path),
            ruff_format=steps.record_ruff_snapshot(
                tmp_path,
                steps.RuffSnapshot("current", tmp_path, Output(0, "[]", ""), ()),
                filename="ruff-format-observation.json",
            ),
            ty=steps.record_ty_snapshot(
                tmp_path, steps.TySnapshot("current", tmp_path, Output(0, "[]", ""), ())
            ),
            initial_oracle_details=0,
            validation_integrity=0,
            coverage_text=steps.record_coverage_text(
                tmp_path,
                steps.CoverageTextSnapshot(
                    "current",
                    tmp_path,
                    ("py", "-m", "coverage", "report"),
                    Output(0, "TOTAL 1 0 100%\n", ""),
                ),
            ),
        )

    def change(_context: object, _before: object, code: int) -> int:
        path.write_text(
            json.dumps({**original, "outcomes": [[names[0], 1], [names[1], 0]]}),
            encoding="utf-8",
        )
        return code

    def changed_validation(
        *_args: object, **_kwargs: object
    ) -> steps.ValidationOutcome:
        result = validate()
        change(None, None, 0)
        return result

    def change_details(_context: object, _before: object, code: int) -> int:
        details_path.write_text(
            json.dumps(
                {
                    "nonce": "current",
                    "sources": ["tests/oracles/other.toml"],
                    "issues": [],
                }
            ),
            encoding="utf-8",
        )
        return code

    def change_tools(_context: object, _before: object, code: int) -> int:
        tool_path.write_text(
            json.dumps({"nonce": "current", "outcomes": [["tool", 1]]}),
            encoding="utf-8",
        )
        return code

    def change_substeps(_context: object, _before: object, code: int) -> int:
        substeps_path.write_text(
            json.dumps({"nonce": "current", "outcomes": [["tool", [1]]]}),
            encoding="utf-8",
        )
        return code

    def change_pytest(_context: object, _before: object, code: int) -> int:
        pytest_path.write_text(json.dumps(_record(passed=[])), encoding="utf-8")
        return code

    monkeypatch.setattr(steps, "inspect_context", lambda *_args: ())
    monkeypatch.setattr(steps, "inspect_later_readiness", lambda *_args, **_kwargs: ())
    monkeypatch.setattr(
        steps.writeguard, "snapshot", lambda _root: Ok(Snapshot((), (), ()))
    )
    monkeypatch.setattr(steps, "_validate_and_observe", validate)
    monkeypatch.setattr(steps, "verify_baseline", lambda _root, code: code)
    monkeypatch.setattr(steps, "summarize", lambda _context, code, *_args: code)
    monkeypatch.setattr(
        steps,
        "finalize_observed",
        partial(_controlled_finalization, lambda _context, _before, code: code),
    )
    assert steps.execute(tmp_path, tmp_path, "current", "Windows") == 0
    _clear_control_records(tmp_path)
    _set_readiness(monkeypatch, mode)
    if mode == "handoff":
        monkeypatch.setattr(steps, "_validate_and_observe", changed_validation)
    elif mode in {
        "provisional",
        "primary",
        "readiness",
        "initial_details",
        "validation_integrity",
        "native_absence",
    }:
        factory = {
            "validation_integrity": _validation_integrity_control,
            "initial_details": _initial_details_validation,
            "provisional": _provisional_validation,
            "primary": _failed_primary_validation,
            "readiness": _readiness_validation,
            "native_absence": partial(_native_absence_validation, tmp_path),
        }[mode]
        monkeypatch.setattr(steps, "_validate_and_observe", partial(factory, validate))
    else:
        changes = {
            "oracle": change,
            "details": change_details,
            "tools": change_tools,
            "substeps": change_substeps,
            "pytest": change_pytest,
            "killers": partial(_change_killer_control, tmp_path),
            "native": partial(_change_finalizer_native, tmp_path),
            "host": partial(_change_finalizer_host, tmp_path),
            "ruff": partial(_change_ruff_control, tmp_path),
            "ruff_format": partial(_change_ruff_format_control, tmp_path),
            "ty": partial(_change_finalizer_ty, tmp_path),
            "python_commands": partial(_change_commands_control, tmp_path),
            "record": partial(_plant_finalizer_record, tmp_path),
            "phase_record": partial(_plant_provisional_record, tmp_path),
        }
        monkeypatch.setattr(
            steps, "finalize_observed", partial(_controlled_finalization, changes[mode])
        )
    reasons = {
        "validation_integrity": "validation integrity failure was lost",
        "initial_details": "initial oracle integrity failure was lost",
        "handoff": "original oracle observation was lost",
        "oracle": "oracle change during finalizers was accepted",
        "details": "oracle detail change during finalizers was accepted",
        "tools": "tool outcome change during finalizers was accepted",
        "substeps": "tool substep change during finalizers was accepted",
        "pytest": "pytest manifest change during finalizers was accepted",
        "killers": "mutant report change during finalizers was accepted",
        "native": "native evidence change during finalizers was accepted",
        "host": "host observation change during finalizers was accepted",
        "ruff": "Ruff observation change during finalizers was accepted",
        "ruff_format": "Ruff format change during finalizers was accepted",
        "ty": "ty observation change during finalizers was accepted",
        "python_commands": "Python command change during finalizers was accepted",
        "provisional": "unverified phases allowed overall pass",
        "primary": "primary failure was lost",
        "record": "invalid finalizer record allowed overall pass",
        "phase_record": "invalid provisional phase record allowed overall pass",
        "readiness": "later readiness failure was lost",
        "native_absence": "native absence lost the overall failure",
    }
    assert steps.execute(tmp_path, tmp_path, "current", "Windows") == 1, reasons[mode]


@pytest.mark.evidence("value")
def test_execute_localizes_proven_native_absence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The gate preserves the overall failure while localizing native finalization."""
    _oracle_finalizer_control(tmp_path, monkeypatch, mode="native_absence")
    record: object = json.loads((tmp_path / "provisional-phases.json").read_text())
    assert isinstance(record, dict)
    phases = record["phases"]
    assert isinstance(phases, list)
    early, later = phases
    label = "native finalizer failed: native-observation"
    assert label not in early["failures"], "native finalizer poisoned earlier phase"
    assert "shared finalizer failed: native-observation" not in early["failures"], (
        "native finalizer poisoned earlier phase"
    )
    assert label in later["failures"], "native finalizer scope was omitted"


@pytest.mark.evidence("value")
def test_initial_oracle_details_failure_survives_finalizers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A transient initial integrity failure remains in the parent record."""
    _oracle_finalizer_control(tmp_path, monkeypatch, mode="initial_details")
    recorded = steps.finalizer_observation(tmp_path, "current")
    assert isinstance(recorded, Ok)
    assert dict(recorded.value.outcomes)["initial-oracle-details"] == 1, (
        "initial oracle integrity failure was lost"
    )
    phases = Ok((PhaseResult(0, "0" * 64, frozenset({"unverified-run"})),))
    joined = steps.provisional_finalizer_failures(
        phases, (*recorded.value.outcomes, ("finalizer-record", 0))
    )
    assert isinstance(joined, Ok)
    assert "shared finalizer failed: initial-oracle-details" in joined.value[0].failures
    assert isinstance(
        steps.verify_phase_finalizer_failures(recorded.value, joined.value), Ok
    )
    assert isinstance(
        steps.verify_phase_finalizer_failures(recorded.value, phases.value), Err
    )


@pytest.mark.evidence("value")
def test_validation_integrity_failure_survives_finalizers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A transient validation failure remains shared in the parent record."""
    _oracle_finalizer_control(tmp_path, monkeypatch, mode="validation_integrity")
    recorded = steps.finalizer_observation(tmp_path, "current")
    assert isinstance(recorded, Ok)
    assert dict(recorded.value.outcomes)["validation-integrity"] == 1, (
        "validation integrity failure was lost"
    )
    phases = Ok((PhaseResult(0, "0" * 64, frozenset({"unverified-run"})),))
    joined = steps.provisional_finalizer_failures(
        phases, (*recorded.value.outcomes, ("finalizer-record", 0))
    )
    assert isinstance(joined, Ok)
    assert "shared finalizer failed: validation-integrity" in joined.value[0].failures
    assert isinstance(
        steps.verify_phase_finalizer_failures(recorded.value, joined.value), Ok
    )
    assert isinstance(
        steps.verify_phase_finalizer_failures(recorded.value, phases.value), Err
    )


@pytest.mark.evidence("value")
def test_readiness_reaches_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The gate passes captured readiness observations to its validation run."""
    _oracle_finalizer_control(tmp_path, monkeypatch, mode="readiness")
    lines = [
        line
        for line in capsys.readouterr().out.splitlines()
        if line.startswith(steps.READINESS_OBSERVATION + " ")
    ]
    assert len(lines) == len(((), ("later readiness",))), (
        "readiness observation was not emitted"
    )
    assert steps.parse_readiness_observation("current", lines[-1]) == Ok(
        ("later readiness",)
    ), "readiness observation was not emitted"


@pytest.mark.evidence("value")
def test_parent_recovers_exact_readiness_observation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The parent consumes one canonical, nonce-bound child readiness value."""
    marker = steps.readiness_observation("current", ("later readiness",))
    assert isinstance(marker, Ok)
    assert steps.parse_readiness_observation("current", marker.value) == Ok(
        ("later readiness",)
    )
    for invalid in (
        "",
        marker.value + "\n" + marker.value,
        marker.value.replace("current", "other"),
        steps.READINESS_OBSERVATION + ' {"nonce":"current","messages":[]}',
        steps.READINESS_OBSERVATION
        + ' {"messages": [], "nonce": "current", "nonce": "current"}',
    ):
        assert isinstance(steps.parse_readiness_observation("current", invalid), Err), (
            "invalid readiness handoff was accepted"
        )
    context = CheckRun(tmp_path, tmp_path, "current", "Linux")
    tools = ToolOutcome(0, Err("unused"), Err("unused"))
    captured = steps.ProvisionalCapture(
        Err("unused"), Err("unused"), tools, None, Err("unused"), "current", (), ()
    )
    monkeypatch.setattr(
        steps, "_parent_collection_capture", lambda *_args: Ok(((), captured))
    )
    monkeypatch.setattr(steps, "targets", lambda *_args: Ok(()))
    monkeypatch.setattr(steps, "pipeline", lambda *_args, **_kwargs: ())
    monkeypatch.setattr(
        steps,
        "_read_sealed_tool_results",
        lambda *_args: Ok((LegEvidence("current", ()), ToolSubsteps("current", ()))),
    )
    parent = steps.__dict__["_parent_tool_capture"](context, tmp_path, marker.value)
    assert isinstance(parent, Ok), parent
    assert parent.value[1].readiness == ("later readiness",), (
        "parent omitted captured readiness"
    )
    missing = steps.__dict__["_parent_tool_capture"](context, tmp_path, "")
    assert isinstance(missing, Err), "parent accepted missing readiness"


@pytest.mark.evidence("real")
def test_retained_output_refuses_changed_readiness_stream(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The retained child output stays byte-identical through all parent checks."""
    root, run_dir = tmp_path / "checkout", tmp_path / "run"
    root.mkdir()
    run_dir.mkdir()
    context = CheckRun(root, run_dir, "abc123", "Linux")
    marker = steps.readiness_observation("abc123", ("later readiness",))
    assert isinstance(marker, Ok)
    streams = (marker.value + "\n", "primary diagnostic\n")
    names = (
        "verify_finalizer_handoff",
        "verify_provisional_handoff",
        "verify_provisional_finalizers",
        "verify_killer_handoff",
        "verify_coverage_handoff",
        "verify_ruff_handoff",
        "verify_python_commands_handoff",
        "verify_provisional_input_identities",
        "verify_tool_results_handoff",
        "verify_pytest_handoff",
        "verify_oracle_handoff",
        "verify_host_handoff",
        "verify_native_handoff",
        "verify_ty_handoff",
        "verify_coverage_text_handoff",
        "verify_provisional_collection",
        "verify_provisional_oracle",
        "verify_provisional_host",
        "verify_provisional_coverage",
        "verify_provisional_static",
        "verify_provisional_source",
        "verify_provisional_prerequisites",
        "verify_provisional_validation",
        "verify_provisional_tools",
        "verify_ruff_format_handoff",
    )
    for name in names:
        monkeypatch.setattr(steps, name, lambda *_args: Ok(None))
    (run_dir / "native-artifacts.json").write_bytes(b"original native evidence")
    valid = steps.retain_verified_gate_output(
        context, tmp_path / "valid-state", streams, verify_handoff=True
    )
    assert isinstance(valid, Ok), valid
    assert (valid.value / "stdout.txt").read_text(encoding="utf-8") == streams[0]

    for mode in (
        "stdout-contents",
        "stdout-identity",
        "stderr-contents",
        "stderr-identity",
    ):

        def tamper(directory: Path, *_args: object, change: str = mode) -> Ok[None]:
            stream, kind = change.split("-", 1)
            target = directory / (stream + ".txt")
            if kind == "contents":
                target.write_text("changed\n", encoding="utf-8")
            else:
                replacement = directory / "replacement"
                replacement.write_bytes(target.read_bytes())
                replacement.replace(target)
            return Ok(None)

        monkeypatch.setattr(steps, "verify_ruff_format_handoff", tamper)
        state = tmp_path / (mode + "-state")
        changed = steps.retain_verified_gate_output(
            context, state, streams, verify_handoff=True
        )
        assert isinstance(changed, Err), "retained output stream change was accepted"
        assert "retained output streams changed" in changed.error
        report = state / "check-reports" / context.nonce
        if mode.startswith("stdout-"):
            assert (report / "stderr.txt").read_text(encoding="utf-8") == streams[1]
        else:
            assert (report / "stdout.txt").read_text(encoding="utf-8") == streams[0]
        assert "retained output streams changed" in (
            report / "finalizer-handoff.txt"
        ).read_text(encoding="utf-8")
        prior = steps.verify_retained_streams(
            report, streams, Err("lost capture"), Err("primary failure")
        )
        assert prior == Err("primary failure; retained output streams changed")

    _assert_retained_artifact_changes(context, tmp_path, streams, monkeypatch)


def _assert_retained_artifact_changes(
    context: CheckRun,
    tmp_path: Path,
    streams: tuple[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reject late changes after individual retained handoffs have been checked."""
    for mode in ("contents", "identity", "removed", "added"):

        def tamper_artifacts(
            directory: Path, *_args: object, change: str = mode
        ) -> Ok[None]:
            artifact = directory / "native-artifacts.json"
            if change == "contents":
                artifact.write_bytes(b"changed native evidence")
            elif change == "identity":
                replacement = directory / "replacement"
                replacement.write_bytes(artifact.read_bytes())
                replacement.replace(artifact)
            elif change == "removed":
                artifact.unlink()
            else:
                (directory / "unexpected.json").write_bytes(b"added")
            return Ok(None)

        monkeypatch.setattr(steps, "verify_ruff_format_handoff", tamper_artifacts)
        state = tmp_path / ("artifact-" + mode)
        changed = steps.retain_verified_gate_output(
            context, state, streams, verify_handoff=True
        )
        assert isinstance(changed, Err), "retained report artifact change was accepted"
        assert "retained report artifacts changed" in changed.error
        report = state / "check-reports" / context.nonce
        assert (report / "stderr.txt").read_text(encoding="utf-8") == streams[1]
        assert "retained report artifacts changed" in (
            report / "finalizer-handoff.txt"
        ).read_text(encoding="utf-8")
        assert steps.verify_retained_artifacts(
            report, Err("lost capture"), Err("primary failure")
        ) == Err("primary failure; retained report artifacts changed")


@pytest.mark.evidence("real")
def test_parent_keeps_verified_report_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A report changed after its checks cannot become the publication baseline."""
    root, run_dir = tmp_path / "checkout", tmp_path / "run"
    root.mkdir()
    run_dir.mkdir()
    (run_dir / "host.json").write_bytes(b"verified host")
    context = CheckRun(root, run_dir, "abc123", "Linux")
    streams = ("EVIDENCE example\n", "primary diagnostic\n")
    monkeypatch.setattr(
        steps,
        "run_observed",
        lambda *_args, **_kwargs: Ok(_synthetic_gate_output(streams)),
    )
    for name in (
        "verify_finalizer_handoff",
        "verify_provisional_handoff",
        "verify_provisional_finalizers",
        "verify_killer_handoff",
        "verify_coverage_handoff",
        "verify_ruff_handoff",
        "verify_python_handoffs",
        "verify_ruff_format_handoff",
        "verify_python_commands_handoff",
        "verify_provisional_input_identities",
        "verify_tool_results_handoff",
        "verify_pytest_handoff",
        "verify_oracle_handoff",
        "verify_host_handoff",
        "verify_native_handoff",
        "verify_ty_handoff",
        "verify_coverage_text_handoff",
        "verify_provisional_collection",
        "verify_provisional_oracle",
        "verify_provisional_host",
        "verify_provisional_coverage",
        "verify_provisional_static",
        "verify_provisional_source",
        "verify_provisional_prerequisites",
        "verify_provisional_validation",
        "verify_provisional_tools",
    ):
        monkeypatch.setattr(steps, name, lambda *_args: Ok(None))
    monkeypatch.setattr(steps, "_successful_child_finalizers", lambda *_args: True)
    retain = steps.__dict__["_retain_verified_gate_evidence"]

    def change_after_verification(
        observed_context: CheckRun,
        state: Path,
        output: tuple[str, str],
        *,
        verify_handoff: bool,
    ) -> Result[steps.RetainedGateReport, str]:
        result = retain(observed_context, state, output, verify_handoff=verify_handoff)
        assert isinstance(result, Ok)
        report = result.value
        assert isinstance(report, steps.RetainedGateReport)
        (report.directory / "host.json").write_bytes(b"changed host")
        return Ok(report)

    monkeypatch.setattr(
        steps, "_retain_verified_gate_evidence", change_after_verification
    )
    observed = steps.__dict__["_observe_check_child"](
        context, tmp_path / "state", assume_yes=False
    )
    assert isinstance(observed.retained, Ok), (
        "verified gate interpreter record was not retained"
    )
    assert observed.snapshot is not None
    assert steps.retained_report_snapshot(observed.retained.value, streams) != Ok(
        observed.snapshot
    ), "parent discarded the verified report snapshot"
    assert steps.__dict__["_relay_check_child"](observed, cleaned=True) == 1
    output = capsys.readouterr()
    assert "withheld unverified: EVIDENCE example" in output.out
    assert "primary diagnostic" in output.err
    assert "retained report changed after verification" in output.err


@pytest.mark.evidence("real")
def test_gate_interpreter_real_and_changed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Bind a real interpreter run and reject a changed selected file."""
    executable = Path(sys.executable)
    original = steps.gate_interpreter_identity(executable)
    assert isinstance(original, Ok), original
    assert original.value.path == executable.resolve(strict=True)
    assert (
        original.value.sha256 == hashlib.sha256(executable.read_bytes()).hexdigest()
    ), "gate interpreter digest differs from its file bytes"
    child = process.run(
        [str(executable), "-c", "print('gate interpreter control')"],
        cwd=tmp_path,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    assert isinstance(child, Ok)
    assert child.value.code == 0
    assert child.value.stdout.strip() == "gate interpreter control"
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    recorded = steps.record_gate_interpreter(
        runtime_dir, "abc123", executable, original
    )
    assert isinstance(recorded, Ok), recorded
    data = json.loads(recorded.value)
    assert data["nonce"] == "abc123"
    assert data["path"] == str(original.value.path)
    assert data["sha256"] == original.value.sha256
    assert isinstance(
        steps.record_gate_interpreter(runtime_dir, "abc123", executable, original), Err
    ), "existing interpreter record was overwritten"

    candidate = tmp_path / "candidate"
    candidate.write_bytes(b"original interpreter bytes")
    first = steps.gate_interpreter_identity(candidate)
    assert isinstance(first, Ok)
    candidate.write_bytes(b"changed interpreter bytes!")
    changed_dir = tmp_path / "changed-runtime"
    changed_dir.mkdir()
    assert isinstance(
        steps.record_gate_interpreter(changed_dir, "abc123", candidate, first), Err
    ), "changed gate interpreter was accepted"
    assert not (changed_dir / "python-runtime.json").exists()
    _assert_interpreter_change_blocks_publication(
        tmp_path, candidate, monkeypatch, capsys
    )


def _assert_interpreter_change_blocks_publication(
    directory: Path,
    executable: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Keep evidence withheld if the selected interpreter changes after execution."""
    report = directory / "publication-report"
    report.mkdir()
    streams = ("EVIDENCE example\n", "primary diagnostic\n")
    (report / "stdout.txt").write_bytes(streams[0].encode("utf-8"))
    (report / "stderr.txt").write_bytes(streams[1].encode("utf-8"))
    snapshot = steps.retained_report_snapshot(report, streams)
    initial = steps.gate_interpreter_identity(executable)
    assert isinstance(snapshot, Ok)
    assert isinstance(initial, Ok)
    monkeypatch.setattr(sys, "executable", str(executable))
    executable.write_bytes(b"modified after observation")
    result = steps.CheckChildResult(
        0,
        streams,
        Ok(report),
        trusted=True,
        snapshot=snapshot.value,
        interpreter=initial.value,
    )
    assert steps.__dict__["_relay_check_child"](result, cleaned=True) == 1, (
        "changed gate interpreter returned success"
    )
    output = capsys.readouterr()
    assert "withheld unverified: EVIDENCE example" in output.out, (
        "evidence survived changed gate interpreter"
    )
    assert "primary diagnostic" in output.err
    assert "gate interpreter changed after execution" in output.err


@pytest.mark.evidence("value")
def test_gate_interpreter_failure_preserves_primary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A changed interpreter fails the parent without hiding the child failure."""
    root, run_dir = tmp_path / "checkout", tmp_path / "run"
    root.mkdir()
    run_dir.mkdir()
    executable = tmp_path / "interpreter"
    executable.write_bytes(b"original interpreter")
    monkeypatch.setattr(sys, "executable", str(executable))

    def attempted(*_args: object, **_kwargs: object) -> Ok[Output]:
        executable.write_bytes(b"changed interpreter")
        return Ok(Output(1, "EVIDENCE example\n", "primary diagnostic\n"))

    monkeypatch.setattr(steps, "run_observed", attempted)
    monkeypatch.setattr(
        steps, "verify_finalizer_handoff", lambda *_args: Err("original guard failure")
    )
    context = CheckRun(root, run_dir, "abc123", "Linux")
    observed = steps.__dict__["_observe_check_child"](
        context, tmp_path / "state", assume_yes=False
    )
    assert observed.code == 1
    assert not observed.trusted
    assert "primary diagnostic" in observed.streams[1]
    assert "original guard failure" in observed.streams[1]
    assert "gate interpreter identity unavailable or changed" in observed.streams[1], (
        "gate interpreter failure was lost"
    )
    assert isinstance(observed.retained, Ok)
    assert "primary diagnostic" in (observed.retained.value / "stderr.txt").read_text()
    assert steps.__dict__["_relay_check_child"](observed, cleaned=True) == 1
    assert "withheld unverified: EVIDENCE example" in capsys.readouterr().out


@pytest.mark.evidence("value")
def test_parent_rejects_changed_retained_interpreter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The parent joins its runtime record to the retained report snapshot."""
    root, run_dir, state = (tmp_path / name for name in ("checkout", "run", "state"))
    root.mkdir()
    run_dir.mkdir()
    streams = ("EVIDENCE example\n", "primary diagnostic\n")
    monkeypatch.setattr(
        steps,
        "run_observed",
        lambda *_args, **_kwargs: Ok(_synthetic_gate_output(streams)),
    )
    for name in (
        "verify_finalizer_handoff",
        "verify_provisional_handoff",
        "verify_provisional_finalizers",
        "verify_killer_handoff",
        "verify_coverage_handoff",
        "verify_ruff_handoff",
        "verify_python_handoffs",
        "verify_ruff_format_handoff",
    ):
        monkeypatch.setattr(steps, name, lambda *_args: Ok(None))
    monkeypatch.setattr(steps, "_successful_child_finalizers", lambda *_args: True)

    def changed_copy(
        context: CheckRun,
        destination: Path,
        output: tuple[str, str],
        *,
        verify_handoff: bool,
    ) -> Result[steps.RetainedGateReport, str]:
        assert verify_handoff
        assert (context.directory / "python-runtime.json").is_file()
        report = destination / "check-reports" / context.nonce
        report.mkdir(parents=True)
        (report / "stdout.txt").write_bytes(output[0].encode("utf-8"))
        (report / "stderr.txt").write_bytes(output[1].encode("utf-8"))
        (report / "python-runtime.json").write_bytes(b"altered retained record")
        (report / "python-child.json").write_bytes(
            (context.directory / "python-child.json").read_bytes()
        )
        snapshot = steps.retained_report_snapshot(report, output)
        assert isinstance(snapshot, Ok)
        return Ok(steps.RetainedGateReport(report, snapshot.value))

    monkeypatch.setattr(steps, "_retain_verified_gate_evidence", changed_copy)
    context = CheckRun(root, run_dir, "abc123", "Linux")
    observed = steps.__dict__["_observe_check_child"](context, state, assume_yes=False)
    assert isinstance(observed.retained, Err), (
        "changed retained gate interpreter was accepted"
    )
    assert "retained gate interpreter record differs" in observed.retained.error
    report = state / "check-reports" / context.nonce
    assert (
        "retained gate interpreter record differs"
        in (report / "finalizer-handoff.txt").read_text()
    )
    assert (report / "stderr.txt").read_bytes() == streams[1].encode("utf-8")


@pytest.mark.evidence("real")
def test_gate_parent_observes_real_child(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Join a real held Python child to the parent's retained gate report."""
    root, run_dir, state = (tmp_path / name for name in ("checkout", "run", "state"))
    root.mkdir()
    run_dir.mkdir()
    family = platform.system()
    assert family in {"Linux", "Darwin", "Windows"}
    context = CheckRun(root, run_dir, "abc123", family)

    def observed_control(
        argv: list[str],
        *,
        cwd: Path,
        env: dict[str, str],
        request: foundation_process.ObservationRequest,
    ) -> Result[Output, process.SpawnError]:
        assert request.family == family, "gate child process was not observed"
        assert request.input_text == context.nonce + "\n", (
            "gate child nonce was omitted"
        )
        assert "sys.stdin.readline()" in argv[2], "gate child handshake was omitted"
        prelude = ast.unparse(
            ast.Module(body=ast.parse(argv[2]).body[:2], type_ignores=[])
        )
        for supplied, expected in (("incorrect\n", 70), (request.input_text, 0)):
            attempt = process.run(
                [sys.executable, "-c", prelude, *argv[3:]],
                cwd=cwd,
                env=env,
                input_text=supplied,
            )
            assert isinstance(attempt, Ok)
            assert attempt.value.code == expected, "gate child nonce handshake failed"
        program = (
            "import sys; value=sys.stdin.readline(); "
            "value == sys.argv[1] + '\\n' or sys.exit(70); "
            "sys.stdout.write('EVIDENCE example\\n'); "
            "sys.stderr.write('primary diagnostic\\n')"
        )
        return foundation_process.run_observed(
            [sys.executable, "-c", program, context.nonce],
            cwd=cwd,
            env=env,
            request=request,
        )

    monkeypatch.setattr(steps, "run_observed", observed_control)
    for name in (
        "verify_finalizer_handoff",
        "verify_provisional_handoff",
        "verify_provisional_finalizers",
        "verify_killer_handoff",
        "verify_coverage_handoff",
        "verify_ruff_handoff",
        "verify_python_handoffs",
        "verify_ruff_format_handoff",
        "verify_python_commands_handoff",
        "verify_provisional_input_identities",
        "verify_tool_results_handoff",
        "verify_pytest_handoff",
        "verify_oracle_handoff",
        "verify_host_handoff",
        "verify_native_handoff",
        "verify_ty_handoff",
        "verify_coverage_text_handoff",
        "verify_provisional_collection",
        "verify_provisional_oracle",
        "verify_provisional_host",
        "verify_provisional_coverage",
        "verify_provisional_static",
        "verify_provisional_source",
        "verify_provisional_prerequisites",
        "verify_provisional_validation",
        "verify_provisional_tools",
    ):
        monkeypatch.setattr(steps, name, lambda *_args: Ok(None))
    monkeypatch.setattr(steps, "_successful_child_finalizers", lambda *_args: True)
    monkeypatch.setattr(
        steps, "retained_receipt_inputs", lambda *_args: Err("controlled receipt input")
    )
    candidate_join = steps.__dict__["_join_candidate_handoff"]
    candidate_calls: list[str] = []

    def observed_candidate_join(*args: object) -> object:
        candidate_calls.append("called")
        return candidate_join(*args)

    monkeypatch.setattr(steps, "_join_candidate_handoff", observed_candidate_join)
    observed = steps.__dict__["_observe_check_child"](context, state, assume_yes=False)
    assert candidate_calls == ["called"], "phase candidate handoff was omitted"
    if family == "Darwin":
        assert observed.code == 1
        assert not observed.trusted
        assert "native process image unavailable" in observed.streams[1]
    else:
        assert observed.code == 0
        assert observed.trusted, "real gate child observation was not retained"
        assert observed.receipt_inputs == Err("controlled receipt input"), (
            "retained receipt input capture was lost"
        )
        assert observed.receipt_candidates == Err("controlled receipt input"), (
            "receipt candidate failure was lost"
        )
        assert isinstance(observed.retained, Ok)
        record = json.loads(
            (observed.retained.value / "python-child.json").read_bytes()
        )
        assert record["nonce"] == context.nonce
        assert record["family"] == family
        assert record["pid"] != os.getpid()
        assert record["birth"] > 0
        assert Path(record["image"]).is_file()
        assert steps.__dict__["_relay_check_child"](observed, cleaned=True) == 0
        output = capsys.readouterr()
        assert "EVIDENCE example" in output.out
        assert "primary diagnostic" in output.err


@pytest.mark.evidence("value")
def test_gate_child_record_refuses_foreign_observations(tmp_path: Path) -> None:
    """Only a separate child with the selected native image can be recorded."""
    root = tmp_path / "checkout"
    root.mkdir()
    selected = steps.gate_interpreter_identity(Path(sys.executable))
    assert isinstance(selected, Ok)
    child = ProcessObservation(
        "Linux", os.getpid() + 1, 1, selected.value.path, _image_file(selected.value)
    )
    output = Output(0, "", "", observation=Ok(child))
    wrong_parent = replace(output, observation=Ok(replace(child, pid=os.getpid())))
    context = CheckRun(root, tmp_path / "parent", "abc123", "Linux")
    context.directory.mkdir()
    assert isinstance(
        steps.record_gate_child(context, Ok(wrong_parent), selected), Err
    ), "parent PID was accepted as gate child"
    foreign = tmp_path / "foreign-image"
    foreign.write_bytes(b"foreign executable")
    foreign_identity = steps.gate_interpreter_identity(foreign)
    assert isinstance(foreign_identity, Ok)
    for index, observation in enumerate(
        (
            None,
            Err(SpawnError("observer refusal")),
            Ok(replace(child, family="Windows")),
            Ok(replace(child, pid=0)),
            Ok(replace(child, birth=0)),
            Ok(replace(child, image=foreign, file=_image_file(foreign_identity.value))),
            Ok(replace(child, file=None)),
            Ok(
                replace(
                    child, file=replace(_image_file(selected.value), sha256="0" * 64)
                )
            ),
        )
    ):
        directory = tmp_path / ("refused-" + str(index))
        directory.mkdir()
        altered = replace(output, observation=observation)
        assert isinstance(
            steps.record_gate_child(
                replace(context, directory=directory), Ok(altered), selected
            ),
            Err,
        ), "foreign gate child observation was accepted"
        assert not (directory / "python-child.json").exists()
    valid_dir = tmp_path / "valid-child"
    valid_dir.mkdir()
    valid = steps.record_gate_child(
        replace(context, directory=valid_dir), Ok(output), selected
    )
    assert isinstance(valid, Ok), valid
    record = json.loads(valid.value)
    assert record["nonce"] == "abc123"
    assert record["pid"] == child.pid
    assert record["birth"] == child.birth
    assert record["sha256"] == selected.value.sha256


@pytest.mark.evidence("real")
def test_gate_child_observer_failure_preserves_primary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """An observer refusal still runs the child and cannot yield trusted evidence."""
    root, run_dir, state = (tmp_path / name for name in ("checkout", "run", "state"))
    root.mkdir()
    run_dir.mkdir()
    family = platform.system()
    assert family in {"Linux", "Darwin", "Windows"}
    context = CheckRun(root, run_dir, "abc123", family)
    monkeypatch.setattr(
        foundation_process,
        "native_process_image",
        lambda *_args: Err(SpawnError("owned image observer refusal")),
    )

    def child_control(
        _argv: list[str],
        *,
        cwd: Path,
        env: dict[str, str],
        request: foundation_process.ObservationRequest,
    ) -> Result[Output, SpawnError]:
        program = (
            "import sys; sys.stdin.readline(); "
            "sys.stdout.write('EVIDENCE example\\n'); "
            "sys.stderr.write('primary diagnostic\\n')"
        )
        return foundation_process.run_observed(
            [sys.executable, "-c", program], cwd=cwd, env=env, request=request
        )

    monkeypatch.setattr(steps, "run_observed", child_control)
    for name in (
        "verify_finalizer_handoff",
        "verify_provisional_handoff",
        "verify_provisional_finalizers",
        "verify_killer_handoff",
        "verify_coverage_handoff",
        "verify_ruff_handoff",
        "verify_python_handoffs",
        "verify_ruff_format_handoff",
    ):
        monkeypatch.setattr(steps, name, lambda *_args: Ok(None))
    monkeypatch.setattr(steps, "_successful_child_finalizers", lambda *_args: True)
    observed = steps.__dict__["_observe_check_child"](context, state, assume_yes=False)
    assert "owned image observer refusal" in observed.streams[1], (
        "gate child observation failure was lost"
    )
    assert not observed.trusted, "missing gate child observation was accepted"
    assert observed.code == 1
    assert "primary diagnostic" in observed.streams[1]
    assert isinstance(observed.retained, Ok)
    assert "primary diagnostic" in (observed.retained.value / "stderr.txt").read_text()
    assert steps.__dict__["_relay_check_child"](observed, cleaned=True) == 1
    output = capsys.readouterr()
    assert "withheld unverified: EVIDENCE example" in output.out


@pytest.mark.evidence("value")
def test_parent_rejects_changed_retained_child(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The live child-image record must match the retained report snapshot."""
    root, run_dir, state = (tmp_path / name for name in ("checkout", "run", "state"))
    root.mkdir()
    run_dir.mkdir()
    streams = ("EVIDENCE example\n", "primary diagnostic\n")
    monkeypatch.setattr(
        steps,
        "run_observed",
        lambda *_args, **_kwargs: Ok(_synthetic_gate_output(streams)),
    )
    for name in (
        "verify_finalizer_handoff",
        "verify_provisional_handoff",
        "verify_provisional_finalizers",
        "verify_killer_handoff",
        "verify_coverage_handoff",
        "verify_ruff_handoff",
        "verify_python_handoffs",
        "verify_ruff_format_handoff",
    ):
        monkeypatch.setattr(steps, name, lambda *_args: Ok(None))
    monkeypatch.setattr(steps, "_successful_child_finalizers", lambda *_args: True)

    def changed_copy(
        context: CheckRun,
        destination: Path,
        output: tuple[str, str],
        *,
        verify_handoff: bool,
    ) -> Result[steps.RetainedGateReport, str]:
        assert verify_handoff
        report = destination / "check-reports" / context.nonce
        report.mkdir(parents=True)
        (report / "stdout.txt").write_bytes(output[0].encode("utf-8"))
        (report / "stderr.txt").write_bytes(output[1].encode("utf-8"))
        (report / "python-runtime.json").write_bytes(
            (context.directory / "python-runtime.json").read_bytes()
        )
        (report / "python-child.json").write_bytes(b"altered child image")
        snapshot = steps.retained_report_snapshot(report, output)
        assert isinstance(snapshot, Ok)
        return Ok(steps.RetainedGateReport(report, snapshot.value))

    monkeypatch.setattr(steps, "_retain_verified_gate_evidence", changed_copy)
    context = CheckRun(root, run_dir, "abc123", "Linux")
    observed = steps.__dict__["_observe_check_child"](context, state, assume_yes=False)
    assert isinstance(observed.retained, Err), (
        "changed retained gate child was accepted"
    )
    assert "retained gate child image record differs" in observed.retained.error
    report = state / "check-reports" / context.nonce
    assert (
        "retained gate child image record differs"
        in (report / "finalizer-handoff.txt").read_text()
    )
    assert (report / "stderr.txt").read_bytes() == streams[1].encode("utf-8")


@pytest.mark.evidence("value")
def test_ruff_observation_survives_finalizers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A changed Ruff record fails the actual finalizer sequence."""
    _oracle_finalizer_control(tmp_path, monkeypatch, mode="ruff")
    recorded = steps.finalizer_observation(tmp_path, "current")
    assert isinstance(recorded, Ok)
    assert dict(recorded.value.outcomes)["ruff-observation"] == 1, (
        "Ruff finalizer failure was lost"
    )
    markers = [
        line
        for line in capsys.readouterr().out.splitlines()
        if line.startswith(steps.RUFF_SEAL + " ")
    ]
    assert len(markers) == 1, "Ruff handoff was not emitted by gate"


@pytest.mark.evidence("value")
def test_python_commands_survive_finalizers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A changed command record fails the actual finalizer sequence."""
    _oracle_finalizer_control(tmp_path, monkeypatch, mode="python_commands")
    recorded = steps.finalizer_observation(tmp_path, "current")
    assert isinstance(recorded, Ok)
    assert dict(recorded.value.outcomes)["python-commands"] == 1
    markers = [
        line
        for line in capsys.readouterr().out.splitlines()
        if line.startswith(steps.PYTHON_COMMANDS_SEAL + " ")
    ]
    assert len(markers) == 1


@pytest.mark.evidence("value")
def test_ruff_format_survives_finalizers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Reject a changed formatter observation after the containment finalizer."""
    _oracle_finalizer_control(tmp_path, monkeypatch, mode="ruff_format")
    recorded = steps.finalizer_observation(tmp_path, "current")
    assert isinstance(recorded, Ok)
    assert dict(recorded.value.outcomes)["ruff-format-observation"] == 1, (
        "Ruff format finalizer failure was lost"
    )
    markers = [
        line
        for line in capsys.readouterr().out.splitlines()
        if line.startswith(steps.RUFF_FORMAT_SEAL + " ")
    ]
    assert len(markers) == 1, "Ruff format handoff was not emitted by gate"


@pytest.mark.evidence("value")
def test_tool_results_seal_follows_finalizers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Seal original tool results only when both tool finalizers succeed."""
    for mode in ("tools", "substeps"):
        directory = tmp_path / mode
        directory.mkdir()
        with monkeypatch.context() as local:
            _oracle_finalizer_control(directory, local, mode=mode)
        markers = tuple(
            line
            for line in capsys.readouterr().out.splitlines()
            if line.startswith(steps.TOOL_RESULTS_SEAL + " ")
        )
        assert len(markers) == 1, "failed tool results seal was emitted or missing"


@pytest.mark.evidence("value")
def test_pytest_seal_follows_finalizer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Seal the original pytest observation only when its finalizer succeeds."""
    _oracle_finalizer_control(tmp_path, monkeypatch, mode="pytest")
    markers = tuple(
        line
        for line in capsys.readouterr().out.splitlines()
        if line.startswith(steps.PYTEST_OBSERVATION_SEAL + " ")
    )
    assert len(markers) == 1, "failed pytest seal was emitted or missing"


@pytest.mark.evidence("value")
def test_oracle_seal_follows_finalizers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Seal original oracle observations only when both finalizers succeed."""
    for mode in ("oracle", "details"):
        directory = tmp_path / mode
        directory.mkdir()
        with monkeypatch.context() as local:
            _oracle_finalizer_control(directory, local, mode=mode)
        markers = tuple(
            line
            for line in capsys.readouterr().out.splitlines()
            if line.startswith(steps.ORACLE_RESULTS_SEAL + " ")
        )
        assert len(markers) == 1, "failed oracle seal was emitted or missing"


@pytest.mark.evidence("value")
def test_host_seal_follows_finalizer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Seal the original host observation only after its finalizer succeeds."""
    _oracle_finalizer_control(tmp_path, monkeypatch, mode="host")
    markers = tuple(
        line
        for line in capsys.readouterr().out.splitlines()
        if line.startswith(steps.HOST_OBSERVATION_SEAL + " ")
    )
    assert len(markers) == 1, "failed host seal was emitted or missing"


@pytest.mark.evidence("value")
def test_native_seal_follows_finalizer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Seal the original native observation only after its finalizer succeeds."""
    _oracle_finalizer_control(tmp_path, monkeypatch, mode="native")
    markers = tuple(
        line
        for line in capsys.readouterr().out.splitlines()
        if line.startswith(steps.NATIVE_OBSERVATION_SEAL + " ")
    )
    assert len(markers) == 1, "failed native seal was emitted or missing"


@pytest.mark.evidence("value")
def test_ty_seal_follows_finalizer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Only the unchanged type-checker record receives a child seal."""
    _oracle_finalizer_control(tmp_path, monkeypatch, mode="ty")
    markers = tuple(
        line
        for line in capsys.readouterr().out.splitlines()
        if line.startswith(steps.TY_OBSERVATION_SEAL + " ")
    )
    assert len(markers) == 1, "failed ty seal was emitted or missing"
    finalizers = steps.finalizer_observation(tmp_path, "current")
    assert isinstance(finalizers, Ok)
    assert dict(finalizers.value.outcomes)["ty-observation"] == 1, (
        "ty finalizer failure was lost"
    )


@pytest.mark.evidence("value")
def test_primary_failure_does_not_poison_finalizer_observations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """An earlier owned failure must not masquerade as shared integrity damage."""
    _oracle_finalizer_control(tmp_path, monkeypatch, mode="primary")
    assert "(1 failures; not a verdict)" in capsys.readouterr().out, (
        "primary failure poisoned finalizer observations"
    )


@pytest.mark.evidence("value")
def test_invalid_finalizer_record_prevents_overall_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A pre-existing finalizer record cannot be accepted by the gate."""
    _oracle_finalizer_control(tmp_path, monkeypatch, mode="record")


@pytest.mark.evidence("value")
def test_invalid_provisional_record_prevents_overall_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A pre-existing provisional record cannot be accepted by the gate."""
    _oracle_finalizer_control(tmp_path, monkeypatch, mode="phase_record")


@pytest.mark.evidence("value")
def test_provisional_phase_record_is_explicit_and_stable(tmp_path: Path) -> None:
    """Persist complete provisional failures without allowing overwrite or promotion."""
    phase = PhaseResult(0, "a" * 64, frozenset({"unverified-run", "tool failure"}))
    recorded = steps.record_provisional_phases(tmp_path, "current", Ok((phase,)))
    assert isinstance(recorded, Ok)
    path = tmp_path / "provisional-phases.json"
    payload: object = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    assert payload == {
        "nonce": "current",
        "status": "provisional",
        "phases": [
            {
                "number": 0,
                "identity": "a" * 64,
                "failures": ["tool failure", "unverified-run"],
            }
        ],
    }
    assert steps.provisional_phases_unchanged(tmp_path, recorded) == 0
    assert isinstance(
        steps.record_provisional_phases(tmp_path, "current", Ok((phase,))), Err
    ), "provisional phase record was overwritten"
    path.write_bytes(recorded.value + b" ")
    assert steps.provisional_phases_unchanged(tmp_path, recorded) == 1, (
        "provisional phase record change was accepted"
    )
    passing = replace(phase, failures=frozenset())
    assert isinstance(steps.provisional_phase_record("current", Ok((passing,))), Err), (
        "passing provisional phase was recorded"
    )
    unavailable = steps.provisional_phase_record("current", Err("missing census"))
    assert isinstance(unavailable, Ok)
    assert json.loads(unavailable.value) == {
        "nonce": "current",
        "status": "unavailable",
        "reason": "missing census",
    }


@pytest.mark.evidence("value")
def test_provisional_handoff_rejects_invalid_schema(tmp_path: Path) -> None:
    """A matching digest cannot promote malformed or unverified-free records."""
    phase = PhaseResult(0, "a" * 64, frozenset({"unverified-run"}))
    encoded = steps.provisional_phase_record("current", Ok((phase,)))
    assert isinstance(encoded, Ok)
    path = tmp_path / "provisional-phases.json"

    def check(contents: bytes) -> object:
        """Observe the actual parent parser with a matching child digest."""
        path.write_bytes(contents)
        output = steps.provisional_seal("current", contents) + "\nfinalizer\n"
        return steps.verify_provisional_handoff(tmp_path, "current", output)

    assert check(encoded.value) == Ok(None)
    unavailable = steps.provisional_phase_record("current", Err("missing"))
    assert isinstance(unavailable, Ok)
    assert check(unavailable.value) == Ok(None)
    for payload in (
        {"nonce": "current", "status": "passed", "phases": []},
        {"nonce": "other", "status": "unavailable", "reason": "missing"},
        {"nonce": "current", "status": "unavailable", "reason": ""},
        {"nonce": "current", "status": "provisional", "phases": []},
        {
            "nonce": "current",
            "status": "provisional",
            "phases": [{"number": 0, "identity": "a" * 64, "failures": []}],
        },
        {
            "nonce": "current",
            "status": "provisional",
            "phases": [
                {"number": True, "identity": "a" * 64, "failures": ["unverified-run"]}
            ],
        },
    ):
        contents = json.dumps(payload, sort_keys=True).encode("utf-8")
        assert isinstance(check(contents), Err), "invalid provisional schema accepted"
    duplicate = (
        b'{"nonce":"current","nonce":"current",'
        b'"status":"unavailable","reason":"missing"}'
    )
    assert isinstance(check(duplicate), Err), "duplicate provisional fields accepted"


@pytest.mark.evidence("value")
def test_finalizer_record_rejects_replay_and_changes(tmp_path: Path) -> None:
    """A fresh, exclusive finalizer record cannot be replaced or silently changed."""
    statuses = tuple((name, 0) for name in steps.FINALIZER_NAMES[:-1])
    recorded = steps.record_finalizers(tmp_path, "current", statuses)
    assert isinstance(recorded, Ok)
    assert steps.finalizer_outcomes_unchanged(tmp_path, "current", recorded) == 0
    path = tmp_path / "finalizer-outcomes.json"
    original = path.read_bytes()
    assert isinstance(steps.record_finalizers(tmp_path, "current", statuses), Err), (
        "finalizer record was overwritten"
    )
    assert path.read_bytes() == original
    changed = ((statuses[0][0], 1), *statuses[1:])
    path.write_text(
        json.dumps({"nonce": "current", "outcomes": changed}), encoding="utf-8"
    )
    assert steps.finalizer_outcomes_unchanged(tmp_path, "current", recorded) == 1, (
        "finalizer record change was accepted"
    )
    assert isinstance(steps.finalizer_observation(tmp_path, "stale"), Err)
    path.write_text(
        '{"nonce":"current","nonce":"current","outcomes":[]}', encoding="utf-8"
    )
    assert isinstance(steps.finalizer_observation(tmp_path, "current"), Err)


@pytest.mark.evidence("value")
def test_unverified_phase_prevents_overall_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Even otherwise passing gate results cannot promote an unverified phase."""
    _oracle_finalizer_control(tmp_path, monkeypatch, mode="provisional")
    output = capsys.readouterr().out
    assert "agentctl-finalizer-v1 current " in output, "gate omitted finalizer handoff"
    assert "agentctl-provisional-v1 current " in output, (
        "gate omitted provisional handoff"
    )


@pytest.mark.evidence("value")
def test_oracle_outcomes_survive_finalizers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The gate refuses an outcome changed during its integrity finalizers."""
    _oracle_finalizer_control(tmp_path, monkeypatch, mode="oracle")


@pytest.mark.evidence("value")
def test_original_oracle_observation_survives_handoff(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The gate carries the original observation through the validation handoff."""
    _oracle_finalizer_control(tmp_path, monkeypatch, mode="handoff")


@pytest.mark.evidence("value")
def test_oracle_details_survive_finalizers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The gate refuses detail records changed during the finalizers."""
    _oracle_finalizer_control(tmp_path, monkeypatch, mode="details")


@pytest.mark.evidence("value")
def test_tool_outcomes_survive_finalizers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A tool outcome changed during the finalizers cannot produce a pass."""
    _oracle_finalizer_control(tmp_path, monkeypatch, mode="tools")


@pytest.mark.evidence("value")
def test_tool_substeps_survive_finalizers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Changed subprocess results cannot survive the final gate check."""
    _oracle_finalizer_control(tmp_path, monkeypatch, mode="substeps")


@pytest.mark.evidence("value")
def test_pytest_manifest_survives_finalizers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The gate refuses a pytest observation changed during finalizers."""
    _oracle_finalizer_control(tmp_path, monkeypatch, mode="pytest")


@pytest.mark.evidence("value")
def test_mutant_report_survives_finalizers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Changed per-killer evidence cannot survive the final gate check."""
    _oracle_finalizer_control(tmp_path, monkeypatch, mode="killers")


@pytest.mark.evidence("value")
def test_native_evidence_survives_finalizers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Native source identity cannot change during the finalizers."""
    _oracle_finalizer_control(tmp_path, monkeypatch, mode="native")


@pytest.mark.evidence("value")
def test_host_observation_survives_finalizers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Later finalizers cannot alter the host facts used by the lane report."""
    _oracle_finalizer_control(tmp_path, monkeypatch, mode="host")


@runtime_checkable
class FifoOperations(Protocol):
    """The native POSIX FIFO constructor, absent from Windows' os module."""

    def mkfifo(self, path: Path) -> None:
        """Create a filesystem special entry for the digest rejection control."""
        ...


def _record(**changes: object) -> dict[str, object]:
    """Supply an independently authored complete one-case manifest."""
    return {
        "nonce": "current",
        "collected": [NODE],
        "executed": [NODE],
        "passed": [NODE],
        "forbidden": [],
        "classes": {NODE: "value"},
        **changes,
    }


@pytest.mark.evidence("value")
def test_manifest_nonce_required() -> None:
    """An otherwise valid old run cannot qualify as the current execution."""
    manifest = parse_manifest(_record())
    assert isinstance(manifest, Ok)
    assert verify(manifest.value, "current", ()) == Ok(None)
    assert isinstance(verify(manifest.value, "different", ()), Err), (
        "stale manifest nonce was accepted"
    )
    empty = parse_manifest(_record(nonce=""))
    assert isinstance(empty, Ok)
    assert isinstance(verify(empty.value, "", ()), Err), "empty nonce was accepted"


@pytest.mark.evidence("value")
def test_execution_evidence_oracle(root: Path) -> None:
    """Apply independently anchored nonce and mutation-completeness cases."""
    store = load_scoped(root / "tests/oracles/execution_evidence.toml", root)
    assert isinstance(store, Store)
    assert store.effective
    mutant = "M-evidence-control"
    case = "tests/governance/test_mutants.py::test_corpus[" + mutant + "]"
    for row in store.effective:
        assert isinstance(row.inputs, Object)
        values = dict(row.inputs.items)
        nonce, recorded, include = values["nonce"], values["recorded"], values["mutant"]
        assert isinstance(nonce, str)
        assert isinstance(recorded, str)
        assert isinstance(include, bool)
        assert isinstance(row.expected, bool)
        nodes = [NODE, case] if include else [NODE]
        record = _record(
            nonce=recorded,
            collected=nodes,
            executed=nodes,
            passed=nodes,
            classes=dict.fromkeys(nodes, "value"),
        )
        parsed = parse_manifest(record)
        assert isinstance(parsed, Ok)
        assert isinstance(verify(parsed.value, nonce, (mutant,)), Ok) == row.expected


@pytest.mark.evidence("value")
def test_collected_executed_passed_equal() -> None:
    """Each independent observation is required; forbidden outcomes never qualify."""
    for changes in (
        {"executed": []},
        {"passed": []},
        {"forbidden": ["skip"]},
        {"collected": [], "executed": [], "passed": [], "classes": {}},
    ):
        manifest = parse_manifest(_record(**changes))
        assert isinstance(manifest, Ok)
        assert isinstance(verify(manifest.value, "current", ()), Err)


@pytest.mark.evidence("value")
def test_every_mutant_has_current_case() -> None:
    """A complete ordinary run still fails when a corpus case is missing."""
    case = "tests/governance/test_mutants.py::test_corpus[M-evidence-control]"
    manifest = parse_manifest(
        _record(
            collected=[NODE, case],
            executed=[NODE, case],
            passed=[NODE, case],
            classes={NODE: "value", case: "real"},
        )
    )
    assert isinstance(manifest, Ok)
    assert verify(manifest.value, "current", ("M-evidence-control",)) == Ok(None)
    missing = parse_manifest(_record())
    assert isinstance(missing, Ok)
    assert isinstance(verify(missing.value, "current", ("M-evidence-control",)), Err), (
        "missing mutant result was accepted"
    )


@pytest.mark.evidence("value")
def test_manifest_schema_and_read_errors(tmp_path: Path) -> None:
    """Closed fields, node identities and actual JSON reads reject malformed inputs."""
    for value in (
        None,
        {},
        _record(extra=True),
        _record(nonce=1),
        _record(forbidden="skip"),
        _record(classes=[]),
        _record(collected="node"),
        _record(collected=[NODE, NODE]),
        _record(classes={NODE: "owed"}),
        _record(classes={}),
    ):
        assert isinstance(parse_manifest(value), Err)
    path = tmp_path / "manifest.json"
    assert isinstance(read_manifest(path), Err)
    path.write_text("invalid JSON", encoding="utf-8")
    assert isinstance(read_manifest(path), Err)
    path.write_text(json.dumps(_record()), encoding="utf-8")
    assert read_manifest(path) == parse_manifest(_record())


@pytest.mark.evidence("value")
def test_manifest_duplicate_fields_refused(tmp_path: Path) -> None:
    """Duplicate top-level and class keys cannot select a convenient value."""
    path = tmp_path / "manifest.json"
    original = json.dumps(_record())
    path.write_text(original, encoding="utf-8")
    assert isinstance(read_manifest(path), Ok)
    for duplicate in (
        original.replace('"nonce": "current"', '"nonce": "stale", "nonce": "current"'),
        original.replace(
            json.dumps(NODE) + ': "value"',
            json.dumps(NODE) + ': "real", ' + json.dumps(NODE) + ': "value"',
        ),
    ):
        assert duplicate != original
        path.write_text(duplicate, encoding="utf-8")
        assert isinstance(read_manifest(path), Err), "duplicate JSON field was accepted"


def _expected(entries: tuple[tuple[str, str, tuple[bytes, ...]], ...]) -> str:
    """Encode the stated rule directly, without importing the subject's encoder."""
    hashed = hashlib.sha256()
    for path, kind, payloads in sorted(entries):
        for field in (path.encode("utf-8"), kind.encode("ascii"), *payloads):
            hashed.update(len(field).to_bytes(8, "big"))
            hashed.update(field)
    return hashed.hexdigest()


@pytest.mark.evidence("value")
def test_digest_byte_vector_and_currency(tmp_path: Path) -> None:
    """A hand-authored entry vector joins every ignored and untracked byte."""
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "pyproject.toml").write_bytes(b"project = 1\n")
    source = tmp_path / "src/example.py"
    source.write_bytes(b"answer = 42\n")
    (tmp_path / "tests/example.py").write_bytes(b"assert True\n")
    entries = (
        ("src", "directory", (b"",)),
        ("tests", "directory", (b"",)),
        ("pyproject.toml", "file", (b"project = 1\n",)),
        ("src/example.py", "file", (b"answer = 42\n",)),
        ("tests/example.py", "file", (b"assert True\n",)),
    )
    original = digest(tmp_path)
    assert original == Ok(_expected(entries))
    captured = source_census(tmp_path)
    assert isinstance(captured, Ok)
    assert digest_census(captured.value) == original, "captured test source was omitted"
    (tmp_path / "DEVELOPMENT_PLAN").mkdir()
    (tmp_path / "DEVELOPMENT_PLAN/row.md").write_text(
        "recording evidence", encoding="utf-8"
    )
    assert digest(tmp_path) == original
    (tmp_path / "src/.ignored").write_bytes(b"ignored")
    assert digest(tmp_path) == Ok(
        _expected((*entries, ("src/.ignored", "file", (b"ignored",))))
    )
    assert digest(tmp_path) != original
    (tmp_path / "src/.ignored").unlink()
    source.write_bytes(b"answer = 43\n")
    assert digest(tmp_path) != original
    assert digest_census(captured.value) == original


@pytest.mark.evidence("value")
def test_digest_census_rejects_incomplete_entries() -> None:
    """Duplicate, incomplete or malformed captured roots cannot produce a digest."""
    roots = (
        Entry("src", "directory", (b"",)),
        Entry("tests", "directory", (b"",)),
        Entry("pyproject.toml", "file", (b"project",)),
    )
    assert isinstance(digest_census(roots), Ok)
    assert isinstance(digest_census(roots[:-1]), Err)
    assert isinstance(digest_census((*roots, roots[0])), Err)
    assert isinstance(
        digest_census((*roots, Entry("src/../escape", "file", (b"x",)))), Err
    )
    assert isinstance(digest_census((*roots, Entry("src/bad", "file", ()))), Err)
    assert isinstance(
        digest_census((*roots, Entry("src/\udcff", "file", (b"x",)))), Err
    )
    assert isinstance(
        digest_census((*roots, Entry("src/missing/file", "file", (b"x",)))), Err
    )


@pytest.mark.evidence("value")
def test_digest_link_bytes_and_errors(tmp_path: Path) -> None:
    """Literal link text and resolved bytes contribute; unreadable inputs fail."""
    assert source_target(tmp_path, tmp_path / "src/target")
    assert not source_target(tmp_path, tmp_path.parent / "outside")
    assert not source_target(tmp_path, tmp_path / ".git/config"), (
        "source link accepted unguarded Git metadata"
    )
    assert isinstance(digest(tmp_path), Err)
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    assert isinstance(digest(tmp_path), Err)
    (tmp_path / "pyproject.toml").write_bytes(b"project = 1\n")
    target = tmp_path / "src/target"
    target.write_bytes(b"content")
    before = digest(tmp_path)
    assert isinstance(before, Ok)
    link = tmp_path / "src/link"
    if platform.system() == "Windows":
        link.hardlink_to(target)
        assert digest(tmp_path) != before
        target.write_bytes(b"changed")
        assert link.read_bytes() == b"changed"
    else:
        special = tmp_path / "src/unsupported"
        assert isinstance(os, FifoOperations)
        os.mkfifo(special)
        assert isinstance(digest(tmp_path), Err)
        special.unlink()
        link.symlink_to("./target")
        first = digest(tmp_path)
        assert isinstance(first, Ok)
        snapshot = source_census(tmp_path)
        assert isinstance(snapshot, Ok)
        assert digest_census(snapshot.value) == first
        link.unlink()
        link.symlink_to("target")
        assert digest(tmp_path) != first
        link.unlink()
        link.symlink_to(tmp_path.parent)
        assert isinstance(digest(tmp_path), Err)
        assert isinstance(source_census(tmp_path), Err)
        link.unlink()
        link.symlink_to("missing")
        assert isinstance(digest(tmp_path), Err)
        link.unlink()
        (tmp_path / ".git").mkdir()
        (tmp_path / ".git/config").write_bytes(b"unguarded")
        link.symlink_to(tmp_path / ".git/config")
        assert isinstance(source_census(tmp_path), Err)


def _post_tree(root: Path) -> tuple[Mutant, ...]:
    """Supply a minimal valid input for the execution-join component."""
    plan = root / "DEVELOPMENT_PLAN"
    plan.mkdir()
    filename = "phase-0-governance-and-check-skeleton.md"
    (plan / "development_plan_standards.md").write_text(
        "| [Governance](" + filename + ") | `M-legs-` |\n", encoding="utf-8"
    )
    (plan / "00-overview.md").write_text(
        "## Requirements\n\n| ID | Requirement |\n|---|---|\n| R20 | known control |\n",
        encoding="utf-8",
    )
    (plan / filename).write_text(
        "# Phase 0 — Control\n\n**Status**: Done\n**Gate kind**: self-verifying\n"
        "**Host lane**: any-host\n\n## Gate Integrity\n\n"
        "| Requirement | Oracle | Observer | Mutants | Tests |\n|---|---|---|---|---|\n"
        "| R20 — known control | none — explicit minimal input | value: known input | "
        "`M-legs-control` | `" + NODE + "` |\n\n## Sprints\n\n"
        "### Sprint 0.1: Control [Done]\n\n**Implementation**: `src/subject.py`\n"
        "**Validation tests**: `" + NODE + "`\n**Mutants**: `M-legs-control`\n"
        "\n## Remaining Work\n\nNone.\n",
        encoding="utf-8",
    )
    return (
        Mutant(
            "M-legs-control",
            Operator.REPLACE_LITERAL,
            "src/subject.py",
            "return 2",
            "return 3",
            (NODE,),
            "named control",
        ),
    )


def _native_tool_controls(
    tmp_path: Path, records: tuple[Mutant, ...], capsys: pytest.CaptureFixture[str]
) -> None:
    """Reject a native manifest that disagrees with the recorded test command."""
    outcomes = tmp_path / "tool-outcomes.json"
    outcomes.write_text(
        json.dumps({"nonce": "current", "outcomes": [["cabal-test", 1]]}),
        encoding="utf-8",
    )
    assert (
        post_run(
            tmp_path,
            tmp_path,
            "current",
            PostRunInputs(
                records, (("M-legs-control", 0),), tool_schedule=("cabal-test",)
            ),
        )
        == 1
    ), "failed native command was accepted as passing"
    assert "native command status differs" in capsys.readouterr().err, (
        "failed native command was accepted as passing"
    )
    outcomes.write_text(
        json.dumps({"nonce": "current", "outcomes": [["cabal-test", 0]]}),
        encoding="utf-8",
    )
    assert (
        post_run(
            tmp_path,
            tmp_path,
            "current",
            PostRunInputs(
                records,
                (("M-legs-control", 0),),
                tool_schedule=("cabal-test",),
                pending_native=True,
            ),
        )
        == 1
    ), "provisional native ownership passed without source evidence"
    assert (
        post_run(
            tmp_path,
            tmp_path,
            "current",
            PostRunInputs(
                records,
                (("M-legs-control", 0),),
                source_entries=(),
                pending_native=True,
            ),
        )
        == 1
    ), "provisional native ownership passed without a tool schedule"
    assert (
        post_run(
            tmp_path,
            tmp_path,
            "current",
            PostRunInputs(
                records, (("M-legs-control", 0),), tool_schedule=("cabal-test",)
            ),
        )
        == 0
    )


def _isolated_collection_control(
    tmp_path: Path,
    records: tuple[Mutant, ...],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Exercise collection refusal independently of native-source refusal."""
    _native_tool_controls(tmp_path, records, capsys)
    with monkeypatch.context() as patch:
        patch.setattr(steps, "_native_source_join", lambda *_arguments: 0)
        assert (
            post_run(
                tmp_path,
                tmp_path,
                "current",
                PostRunInputs(records, (("M-legs-control", 0),), source_entries=()),
            )
            == 1
        ), "missing captured collection ownership was accepted"


@pytest.mark.evidence("value")
def test_post_run_pipeline_controls(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Actual manifest reads distinguish missing, stale and complete join inputs."""
    records = _post_tree(tmp_path)
    assert post_run(tmp_path, tmp_path, "current", PostRunInputs(records)) == 1
    missing = capsys.readouterr().err
    assert "pytest-manifest.json" in missing
    assert "haskell-manifest.json" in missing, "missing native diagnostic was lost"
    path = tmp_path / "pytest-manifest.json"
    path.write_text(json.dumps(_record(nonce="old")), encoding="utf-8")
    assert post_run(tmp_path, tmp_path, "current", PostRunInputs(records)) == 1
    failures = capsys.readouterr().err
    assert "manifest nonce mismatch" in failures
    assert "haskell-manifest.json" in failures
    case = "tests/governance/test_mutants.py::test_corpus[M-legs-control]"
    complete = _record(
        collected=[NODE, case],
        executed=[NODE, case],
        passed=[NODE, case],
        classes={NODE: "value", case: "real"},
    )
    path.write_text(json.dumps(complete), encoding="utf-8")
    assert post_run(tmp_path, tmp_path, "current", PostRunInputs(records)) == 1
    native = "haskell:agentctl-core-test/Handshake/protocol-fields"
    native_xml = (
        '<testsuites tests="1"><testsuite><testcase '
        'classname="agentctl-core-test.Handshake" name="protocol-fields">'
        "{body}</testcase></testsuite></testsuites>"
    )
    (tmp_path / "tasty.xml").write_text(
        native_xml.format(body="<failure>native failure</failure>"), encoding="utf-8"
    )
    (tmp_path / "haskell-manifest.json").write_text(
        json.dumps(
            _record(
                collected=[native],
                executed=[native],
                passed=[],
                forbidden=["failed: " + native],
                classes={native: "value"},
            )
        ),
        encoding="utf-8",
    )
    assert post_run(tmp_path, tmp_path, "current", PostRunInputs(records)) == 1
    assert "native-observation: failed: " + native in capsys.readouterr().err, (
        "native case failure was hidden"
    )
    (tmp_path / "tasty.xml").write_text(native_xml.format(body=""), encoding="utf-8")
    (tmp_path / "haskell-manifest.json").write_text(
        json.dumps(
            _record(
                collected=[native],
                executed=[native],
                passed=[native],
                classes={native: "value"},
            )
        ),
        encoding="utf-8",
    )
    assert post_run(tmp_path, tmp_path, "current", PostRunInputs(records)) == 1, (
        "post-run accepted missing explicit mutant ownership"
    )
    assert "explicit mutant ownership unavailable" in capsys.readouterr().err
    assert (
        post_run(
            tmp_path,
            tmp_path,
            "current",
            PostRunInputs(records, (("M-legs-control", 0),)),
        )
        == 0
    )
    assert (
        post_run(
            tmp_path,
            tmp_path,
            "current",
            PostRunInputs(records, (("M-legs-control", 0),), source_entries=()),
        )
        == 1
    ), "missing captured collection ownership was accepted"
    captured_errors = capsys.readouterr().err
    assert "collection-observation:" in captured_errors
    assert "native-source-observation:" in captured_errors, (
        "missing native source observation was accepted"
    )
    _isolated_collection_control(tmp_path, records, monkeypatch, capsys)
    captured = phases(tmp_path)
    phase_path = tmp_path / "DEVELOPMENT_PLAN/phase-0-governance-and-check-skeleton.md"
    overview = tmp_path / "DEVELOPMENT_PLAN/00-overview.md"
    standard = tmp_path / "DEVELOPMENT_PLAN/development_plan_standards.md"
    overview_text = overview.read_text(encoding="utf-8")
    policy = CapturedPolicy(
        (("M-legs-control", 0),), standard.read_text(encoding="utf-8"), overview_text
    )
    phase_text = phase_path.read_text(encoding="utf-8")
    phase_path.unlink()
    overview.write_text("## Requirements\n", encoding="utf-8")
    assert (
        post_run(
            tmp_path,
            tmp_path,
            "current",
            PostRunInputs(records, policy, captured),
        )
        == 0
    )
    phase_path.write_text(phase_text, encoding="utf-8")
    overview.write_text(overview_text, encoding="utf-8")
    assert (
        post_run(
            tmp_path,
            tmp_path,
            "current",
            PostRunInputs(records, (("M-legs-control", 1),)),
        )
        == 1
    )
    path.write_text(
        json.dumps(
            _record(
                collected=[case], executed=[case], passed=[case], classes={case: "real"}
            )
        ),
        encoding="utf-8",
    )
    assert post_run(tmp_path, tmp_path, "current", PostRunInputs(records)) == 1
    (tmp_path / "DEVELOPMENT_PLAN/phase-0-governance-and-check-skeleton.md").unlink()
    path.write_text(json.dumps(complete), encoding="utf-8")
    assert post_run(tmp_path, tmp_path, "current", PostRunInputs(records)) == 1


@pytest.mark.evidence("value")
def test_lane_summary_pipeline_controls(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Emit rows for an intact model and suppress them after each failed boundary."""
    root = tmp_path / "subject"
    root.mkdir()
    _post_tree(root)
    (root / "src").mkdir()
    (root / "tests").mkdir()
    (root / "pyproject.toml").write_bytes(b"project = 1\n")
    repository(root)
    context = CheckRun(root, tmp_path, "current", "Linux")
    assert summarize(context, 1) == 1
    assert summarize(context, 0) == 1
    assert "EVIDENCE " not in capsys.readouterr().out
    host = tmp_path / "host.json"
    facts = HostFacts(family="Linux", architecture="x86_64", checkout=True, git=True)
    host.write_text(
        json.dumps({"nonce": "current", "facts": asdict(facts)}), encoding="utf-8"
    )
    original_host = steps.host_observation(tmp_path, "current")
    assert isinstance(original_host, Ok)
    changed_facts = HostFacts(
        family="Linux", architecture="x86_64", checkout=True, git=True, mux=True
    )
    host.write_text(
        json.dumps({"nonce": "current", "facts": asdict(changed_facts)}),
        encoding="utf-8",
    )
    assert summarize(context, 1, original_host) == 1
    assert "lane-observation mux-host: unmet" in capsys.readouterr().out, (
        "lane summary replaced captured host facts"
    )
    host.write_text(
        json.dumps({"nonce": "current", "facts": asdict(facts)}), encoding="utf-8"
    )
    assert summarize(context, 1) == 1
    failed_output = capsys.readouterr().out
    assert "lane-observation " in failed_output
    assert "(not a verdict)" in failed_output
    assert "EVIDENCE " not in failed_output
    assert summarize(context, 0) == 0
    output = capsys.readouterr().out
    rows = tuple(line for line in output.splitlines() if line.startswith("EVIDENCE "))
    assert len(rows) == 1
    assert re.fullmatch(
        (
            r"EVIDENCE \d{4}-\d{2}-\d{2} ; any-host ; agentctl check ; pass ; "
            r"tree [a-f0-9]{64} ; os=Linux,arch=x86_64,baseline=no baseline"
        ),
        rows[0],
    )
    phase = root / "DEVELOPMENT_PLAN/phase-0-governance-and-check-skeleton.md"
    original = phase.read_text(encoding="utf-8")
    phase.write_text(original.replace("any-host", "mux-host"), encoding="utf-8")
    assert summarize(context, 0) == 1
    assert "EVIDENCE " not in capsys.readouterr().out
    phase.write_text(original, encoding="utf-8")
    (root / "pyproject.toml").unlink()
    assert summarize(context, 0) == 1
    assert "EVIDENCE " not in capsys.readouterr().out
    (root / "pyproject.toml").write_bytes(b"project = 1\n")
    (root / ".git/HEAD").write_text("unreadable baseline\n", encoding="utf-8")
    assert summarize(context, 0) == 1
    assert "EVIDENCE " not in capsys.readouterr().out


@pytest.mark.parametrize(
    ("output", "expected"),
    [
        (Output(0, "TOTAL 1 0 100%\n", ""), "complete"),
        (
            Output(
                2,
                "TOTAL 10 1 90%\n"
                "Coverage failure: total of 90 is less than fail-under=100\n",
                "",
            ),
            "floor",
        ),
        (Output(2, "TOTAL 10 1 90%\n", ""), None),
        (Output(1, "TOTAL 10 1 90%\n", ""), None),
        (Output(0, "TOTAL 1 0 100%\n", "diagnostic"), None),
        (Output(0, "TOTAL 1 0 100%\nTOTAL 1 0 100%\n", ""), None),
        (
            Output(
                0,
                "TOTAL 1 0 100%\n"
                "Coverage failure: total of 90 is less than fail-under=100\n",
                "",
            ),
            None,
        ),
    ],
)
@pytest.mark.evidence("value")
def test_coverage_report_floor_requires_an_unambiguous_real_report(
    output: Output, expected: str | None
) -> None:
    """Distinguish a floor failure from malformed or unrelated command failures."""
    observed = steps.coverage_text_floor(output)
    if expected is None:
        assert isinstance(observed, Err)
    else:
        assert observed == Ok(expected)
