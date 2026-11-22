# Copyright (c) 2026 agentctl contributors.
"""Independent manifest records and explicit canonical digest byte vectors."""

import hashlib
import json
import os
import platform
import re
from collections.abc import Callable
from dataclasses import asdict, replace
from functools import partial
from pathlib import Path
from typing import Literal, Protocol, runtime_checkable

import pytest

from agentctl.check import mutant_report, steps
from agentctl.check.evidence import (
    Entry,
    LegEvidence,
    RunEvidence,
    ToolSubsteps,
    digest,
    digest_census,
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
from agentctl.check.plan_data import phases
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
from agentctl.result import Err, Ok, Result
from tests.harness.git import repository
from tests.harness.oracle import Object, Store, load_scoped

pytestmark = pytest.mark.evidence("value")
NODE = "tests/unit/test_example.py::test_one"


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


def test_tool_record_identity_and_completeness(tmp_path: Path) -> None:
    """Reject stale, ambiguous or incomplete actual tool outcome records."""
    path = tmp_path / "outcomes.json"
    path.write_text(
        '{"nonce":"current","outcomes":[["one",0],["two",1]]}', encoding="utf-8"
    )
    assert isinstance(read_legs(path, "current", ("one", "two")), Ok)
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
    entries = (Entry(source, "file", (b"source",)), Entry(other, "file", (b"other",)))
    return steps.native_snapshot(tmp_path, "current", entries)


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


def _failed_primary_validation(
    validate: Callable[..., steps.ValidationOutcome], *args: object, **kwargs: object
) -> steps.ValidationOutcome:
    """Return a prior failure with an otherwise intact provisional observation."""
    return replace(_provisional_validation(validate, *args, **kwargs), code=1)


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
    for name in ("finalizer-outcomes.json", "provisional-phases.json"):
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


def _oracle_finalizer_control(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    mode: Literal[
        "handoff",
        "oracle",
        "details",
        "tools",
        "substeps",
        "pytest",
        "killers",
        "native",
        "host",
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
    elif mode in {"provisional", "primary", "readiness"}:
        factory = {
            "provisional": _provisional_validation,
            "primary": _failed_primary_validation,
            "readiness": _readiness_validation,
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
            "record": partial(_plant_finalizer_record, tmp_path),
            "phase_record": partial(_plant_provisional_record, tmp_path),
        }
        monkeypatch.setattr(
            steps, "finalize_observed", partial(_controlled_finalization, changes[mode])
        )
    reasons = {
        "handoff": "original oracle observation was lost",
        "oracle": "oracle change during finalizers was accepted",
        "details": "oracle detail change during finalizers was accepted",
        "tools": "tool outcome change during finalizers was accepted",
        "substeps": "tool substep change during finalizers was accepted",
        "pytest": "pytest manifest change during finalizers was accepted",
        "killers": "mutant report change during finalizers was accepted",
        "native": "native evidence change during finalizers was accepted",
        "host": "host observation change during finalizers was accepted",
        "provisional": "unverified phases allowed overall pass",
        "primary": "primary failure was lost",
        "record": "invalid finalizer record allowed overall pass",
        "phase_record": "invalid provisional phase record allowed overall pass",
        "readiness": "later readiness failure was lost",
    }
    assert steps.execute(tmp_path, tmp_path, "current", "Windows") == 1, reasons[mode]


def test_readiness_reaches_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The gate passes captured readiness observations to its validation run."""
    _oracle_finalizer_control(tmp_path, monkeypatch, mode="readiness")


def test_primary_failure_does_not_poison_finalizer_observations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """An earlier owned failure must not masquerade as shared integrity damage."""
    _oracle_finalizer_control(tmp_path, monkeypatch, mode="primary")
    assert "(1 failures; not a verdict)" in capsys.readouterr().out, (
        "primary failure poisoned finalizer observations"
    )


def test_invalid_finalizer_record_prevents_overall_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A pre-existing finalizer record cannot be accepted by the gate."""
    _oracle_finalizer_control(tmp_path, monkeypatch, mode="record")


def test_invalid_provisional_record_prevents_overall_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A pre-existing provisional record cannot be accepted by the gate."""
    _oracle_finalizer_control(tmp_path, monkeypatch, mode="phase_record")


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


def test_oracle_outcomes_survive_finalizers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The gate refuses an outcome changed during its integrity finalizers."""
    _oracle_finalizer_control(tmp_path, monkeypatch, mode="oracle")


def test_original_oracle_observation_survives_handoff(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The gate carries the original observation through the validation handoff."""
    _oracle_finalizer_control(tmp_path, monkeypatch, mode="handoff")


def test_oracle_details_survive_finalizers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The gate refuses detail records changed during the finalizers."""
    _oracle_finalizer_control(tmp_path, monkeypatch, mode="details")


def test_tool_outcomes_survive_finalizers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A tool outcome changed during the finalizers cannot produce a pass."""
    _oracle_finalizer_control(tmp_path, monkeypatch, mode="tools")


def test_tool_substeps_survive_finalizers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Changed subprocess results cannot survive the final gate check."""
    _oracle_finalizer_control(tmp_path, monkeypatch, mode="substeps")


def test_pytest_manifest_survives_finalizers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The gate refuses a pytest observation changed during finalizers."""
    _oracle_finalizer_control(tmp_path, monkeypatch, mode="pytest")


def test_mutant_report_survives_finalizers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Changed per-killer evidence cannot survive the final gate check."""
    _oracle_finalizer_control(tmp_path, monkeypatch, mode="killers")


def test_native_evidence_survives_finalizers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Native source identity cannot change during the finalizers."""
    _oracle_finalizer_control(tmp_path, monkeypatch, mode="native")


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
