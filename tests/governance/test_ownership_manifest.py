# Copyright (c) 2026 agentctl contributors.
"""Closed ownership declarations require exact, independently observed files."""

import json
import re
import tomllib
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from agentctl.check import coverage_hosts, lanes, mutant_report, steps
from agentctl.check.evidence import (
    Entry,
    LegEvidence,
    OracleDetails,
    RunEvidence,
    ToolSubsteps,
    source_census,
)
from agentctl.check.mutants import Mutant, Operator, corpus
from agentctl.check.ownership import (
    MutantOwnership,
    MutantScope,
    OracleScope,
    OwnershipManifest,
    ScopedPhaseWork,
    attribute_mutant_claims,
    bind_census,
    bind_mutants,
    bind_mutants_observed,
    check_phase_claims,
    collection_scopes,
    oracle_issue_scopes,
    parse_manifest,
    parse_mutant_claims,
    partial_claim_problems,
    phase_work,
    read_manifest,
    scoped_phase_work,
)
from agentctl.check.ownership import test_consumer_problems as consumer_problems
from agentctl.check.phase_reports import (
    ArtifactOwnership,
    CollectionObservation,
    CollectionScope,
    OwnershipPhase,
    PhaseInputs,
    PhaseResult,
    calculate,
    calculate_observed,
    collection_failures,
)
from agentctl.check.plan_data import Phase, field, phase_text, phases
from agentctl.check.steps import (
    CollectionClaims,
    CoverageSnapshot,
    NativeSnapshot,
    ProvisionalCapture,
    RuffSnapshot,
    ToolOutcome,
    _native_ownership_observation,
    _parent_collection_capture,
    _parent_validation_problems,
    captured_phase_observations,
    census_phases,
    census_policy,
    collection_observations,
    complete_mutant_owners,
    fragment_claim_problems,
    native_failure_observations,
    observed_native_mutant_owners,
    ownership_observations,
    phase0_claim_problems,
    provisional_mutant_owners,
    provisional_owned_tool_failures,
    provisional_tool_failures,
    report_provisional_phases,
    scoped_mutant_ownership,
    scoped_source_inputs,
    source_ownership_problems,
)
from agentctl.check.validator.source import SourceIssue
from agentctl.foundation_process_values import Output
from agentctl.result import Err, Ok, Result

MANIFEST = (
    "version = 1\n"
    "[[phases]]\nnumber = 0\nprerequisites = []\n"
    "[[phases]]\nnumber = 1\nprerequisites = [0]\n"
    '[[artifacts]]\npath = "src"\ncapability = "governance"\n'
    "owner = 0\nconsumers = [0, 1]\nrequired = true\n"
    '[[artifacts]]\npath = "src/shared.py"\ncapability = "governance"\n'
    "owner = 0\nconsumers = [0, 1]\nrequired = true\n"
    '[[artifacts]]\npath = "src/future.py"\ncapability = "future"\n'
    "owner = 1\nconsumers = [1]\nrequired = false\n"
)

CLAIMS = (
    'version = 1\n[[claims]]\nidentifier = "M-test-example"\nowner = 0\n'
    'killer_sources = [{node = "tests/test_subject.py::test_control", '
    'path = "tests/test_subject.py"}]\n'
)


def _value[T, E](result: Result[T, E]) -> T:
    match result:
        case Ok(value):
            return value
        case Err(error):
            pytest.fail(str(error))


def _is_error[T, E](result: Result[T, E]) -> bool:
    match result:
        case Err():
            return True
        case Ok():
            return False


@pytest.mark.evidence("value")
def test_ownership_manifest_structure() -> None:
    """Reject ambiguous, malformed and ownership-laundering declarations."""
    parsed = _value(parse_manifest(MANIFEST))
    assert tuple(item.capability for item in parsed.artifacts) == (
        "governance",
        "governance",
        "future",
    )
    for malformed in (
        "",
        "not TOML",
        MANIFEST.replace("version = 1", "version = true"),
        MANIFEST.replace("number = 0", "number = true"),
        MANIFEST.replace("consumers = [0, 1]", "consumers = [0, 0, 1]"),
        MANIFEST.replace("prerequisites = [0]", "prerequisites = [1]"),
        MANIFEST.replace('capability = "future"', 'capability = "governance"'),
        MANIFEST.replace('path = "src/future.py"', 'path = "src/shared.py"'),
        MANIFEST.replace('path = "src/shared.py"', 'path = "../escape.py"'),
        MANIFEST.replace("required = true", "required = 1"),
        MANIFEST + "extra = 1\n",
    ):
        assert _is_error(parse_manifest(malformed))


@pytest.mark.evidence("value")
def test_cited_test_consumers() -> None:
    """A present owner alone cannot omit a phase that cites its test."""
    manifest = OwnershipManifest(
        (OwnershipPhase(0, frozenset()), OwnershipPhase(1, frozenset({0}))),
        (
            ArtifactOwnership(
                "tests/test_shared.py",
                0,
                frozenset({0, 1}),
                required=True,
                capability="shared-tests",
            ),
            ArtifactOwnership(
                "tests/test_early.py",
                0,
                frozenset({0}),
                required=True,
                capability="shared-tests",
            ),
        ),
    )
    assert consumer_problems(manifest, ((1, "tests/test_shared.py::test_ok"),)) == ()
    problems = consumer_problems(
        manifest,
        (
            (1, "tests/test_early.py::test_missing_consumer"),
            (0, "tests/test_unknown.py::test_unowned"),
            (2, "tests/test_shared.py::test_unknown_phase"),
        ),
    )
    expected_problems = 3
    assert len(problems) == expected_problems
    assert any("test_missing_consumer" in problem for problem in problems)
    assert any("test_unowned" in problem for problem in problems)
    assert any("test_unknown_phase" in problem for problem in problems)


@pytest.mark.evidence("value")
def test_collection_scopes_from_manifest() -> None:
    """A shared module affects every declared consumer, not unrelated phases."""
    manifest = OwnershipManifest(
        (OwnershipPhase(0, frozenset()), OwnershipPhase(1, frozenset({0}))),
        (
            ArtifactOwnership(
                "tests/shared.py",
                0,
                frozenset({0, 1}),
                required=True,
                capability="shared",
            ),
            ArtifactOwnership(
                "tests/later.py", 1, frozenset({1}), required=True, capability="later"
            ),
        ),
    )
    early, late = "tests/shared.py::test_early", "tests/later.py::test_late"
    checks = ((0, frozenset({early})), (1, frozenset({late})))
    scopes = _value(collection_scopes(manifest, checks))
    assert scopes[0].modules == frozenset({"tests/shared.py"})
    assert scopes[1].modules == frozenset({"tests/shared.py", "tests/later.py"})
    nodes = frozenset({early, late})
    observation = CollectionObservation(
        nodes,
        nodes,
        frozenset({early}),
        frozenset(),
        nonce_matches=True,
        forbidden=frozenset(),
    )
    failures = _value(collection_failures(scopes, observation))
    assert not failures[0][1]
    assert "failed test: " + late in failures[1][1]
    shared = _value(
        collection_failures(scopes, replace(observation, passed=frozenset({late})))
    )
    assert all("failed test: " + early in failures for _, failures in shared)
    assert _is_error(collection_scopes(manifest, checks[:1]))
    assert _is_error(
        collection_scopes(
            manifest, (checks[0], (1, frozenset({"tests/missing.py::test_x"})))
        )
    )


@pytest.mark.evidence("value")
def test_captured_collection_observations() -> None:
    """Missing tests stay local and stale execution evidence fails all consumers."""
    text = MANIFEST + (
        '[[artifacts]]\npath = "tests/test_early.py"\ncapability = "early-tests"\n'
        "owner = 0\nconsumers = [0]\nrequired = false\n"
        '[[artifacts]]\npath = "tests/test_late.py"\ncapability = "late-tests"\n'
        "owner = 1\nconsumers = [1]\nrequired = false\n"
    )
    entries = (
        Entry("src/agentctl/check/source_ownership.toml", "file", (text.encode(),)),
        Entry("tests/test_early.py", "file", (b"source",)),
    )
    early, late = "tests/test_early.py::test_value", "tests/test_late.py::test_value"
    declarations = tuple(
        phase_text(
            Path(f"phase-{number}-example.md"),
            f"### Sprint {number}.1: Test [Active]\n"
            f"**Validation tests**: `{node}`\n## Remaining Work\n",
        )
        for number, node in ((0, early), (1, late))
    )
    assert all(phase is not None for phase in declarations)
    captured = tuple(phase for phase in declarations if phase is not None)
    observed = RunEvidence(
        "current", frozenset({early}), frozenset({early}), frozenset({early}), (), ()
    )
    result = _value(collection_observations(entries, captured, observed, "current", ()))
    assert not result[0][1]
    assert "missing or failed: " + late in result[1][1]
    stale = _value(collection_observations(entries, captured, observed, "stale", ()))
    assert all("nonce" in failures for _number, failures in stale)
    assert _is_error(
        collection_observations(entries, captured, observed, "current", None)
    )
    assert _is_error(collection_observations((), captured, observed, "current", ()))
    partial_text = text.split('[[artifacts]]\npath = "tests/test_late.py"')[0]
    partial = (
        Entry(
            "src/agentctl/check/source_ownership.toml", "file", (partial_text.encode(),)
        ),
        entries[1],
    )
    local = _value(collection_observations(partial, captured, observed, "current", ()))
    assert not local[0][1], "later missing declaration poisoned earlier observation"
    assert any("unowned or not consumed" in issue for issue in local[1][1])
    nodes = frozenset({early, late})
    unowned = RunEvidence("current", nodes, nodes, nodes, (), ())
    shared = _value(collection_observations(partial, captured, unowned, "current", ()))
    assert all("unowned collector: tests/test_late.py" in row for _, row in shared), (
        "unowned collection did not invalidate every consumer"
    )


@pytest.mark.evidence("value")
def test_oracle_failures_follow_source_consumers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Later oracle failures stay local; shared, missing and forged inputs do not."""
    first, later = "tests/oracles/early.toml", "tests/oracles/later.toml"
    phases = (OwnershipPhase(0, frozenset()), OwnershipPhase(1, frozenset({0})))
    manifest = OwnershipManifest(
        phases,
        (
            ArtifactOwnership(
                first, 0, frozenset({0, 1}), required=True, capability="early"
            ),
            ArtifactOwnership(
                later, 1, frozenset({1}), required=True, capability="later"
            ),
        ),
    )
    entries = (Entry(first, "file", (b"first",)), Entry(later, "file", (b"later",)))
    message = "oracles.independence: later.toml: broken source"
    details = OracleDetails("current", (first, later), ((later, message),))
    assert oracle_issue_scopes(manifest, entries, details, 1) == Ok(
        (OracleScope(0, ()), OracleScope(1, (message,)))
    ), "later oracle failure poisoned earlier phase"
    _assert_parent_oracle_scopes(
        (OracleScope(0, ()), OracleScope(1, (message,))), monkeypatch
    )
    shared = replace(
        details, issues=((None, "oracles.independence: loader unavailable"),)
    )
    result = _value(oracle_issue_scopes(manifest, entries, shared, 1))
    assert all(item.failures for item in result), "shared oracle failure was localized"
    missing = OracleDetails("current", (first,), ())
    result = _value(oracle_issue_scopes(manifest, entries[:1], missing, 0))
    assert result[0] == OracleScope(0, ())
    assert "required oracle missing: " + later in result[1].failures
    assert _is_error(oracle_issue_scopes(manifest, entries, details, 0)), (
        "oracle status disagreement was accepted"
    )
    assert _is_error(oracle_issue_scopes(manifest, entries[:1], details, 1))
    forged = replace(details, issues=((first, message),))
    assert _is_error(oracle_issue_scopes(manifest, entries, forged, 1))
    duplicate = replace(
        details,
        issues=(
            (later, "oracles.independence: later.toml: duplicate row id across files"),
        ),
    )
    assert _is_error(oracle_issue_scopes(manifest, entries, duplicate, 1)), (
        "cross-file oracle failure was localized"
    )


def _assert_parent_oracle_scopes(
    scopes: tuple[OracleScope, ...], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Refuse to hide a later-owned oracle failure in phase observations."""
    results = (
        steps.phase_reports.PhaseResult(0, "a" * 64, frozenset({"unverified-run"})),
        steps.phase_reports.PhaseResult(
            1, "b" * 64, frozenset({"unverified-run", *scopes[1].failures})
        ),
    )
    assert steps.verify_phase_oracle_failures(scopes, results) == Ok(None)
    forged = (results[0], replace(results[1], failures=frozenset({"unverified-run"})))
    assert isinstance(steps.verify_phase_oracle_failures(scopes, forged), Err), (
        "parent accepted hidden oracle failure"
    )
    assert isinstance(steps.verify_phase_oracle_failures(scopes, results[:1]), Err), (
        "parent accepted incomplete oracle phase scopes"
    )
    _assert_parent_oracle_routes(scopes, results, forged, monkeypatch)


def _assert_parent_oracle_routes(
    scopes: tuple[OracleScope, ...],
    results: tuple[steps.phase_reports.PhaseResult, ...],
    forged: tuple[steps.phase_reports.PhaseResult, ...],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify oracle omissions are rejected by live and retained parent routes."""
    nonce = "fresh"
    context = steps.CheckRun(Path("/source"), Path("/run"), nonce, "Linux")
    finalizers = LegEvidence(
        nonce, tuple((name, 0) for name in steps.FINALIZER_NAMES[:-1])
    )
    outcomes = LegEvidence(nonce, ())
    details = OracleDetails(nonce, (), ())
    marker = (
        steps.oracle_results_seal(nonce, outcomes, details)
        + "\n"
        + steps.finalizer_seal(finalizers)
    )
    with monkeypatch.context() as patch:
        patch.setattr(steps, "finalizer_observation", lambda *_args: Ok(finalizers))
        patch.setattr(
            steps, "_provisional_values_for_identity", lambda *_args: Ok(results)
        )
        patch.setattr(steps.ownership, "guarded_census", lambda *_args: Ok(()))
        patch.setattr(steps, "_parent_bound_census", lambda *_args: Ok(()))
        patch.setattr(
            steps,
            "_oracle_handoff_observations",
            lambda *_args: Ok((outcomes, details)),
        )
        patch.setattr(steps, "oracle_diagnostics", lambda *_args: Ok(scopes))
        for name in (
            "verify_python_commands_handoff",
            "verify_oracle_handoff",
            "_verify_provisional_census",
            "verify_python_plan_handoff",
            "verify_provisional_input_identities",
            "verify_tool_results_handoff",
            "verify_pytest_handoff",
            "verify_host_handoff",
            "verify_native_handoff",
            "verify_ty_handoff",
            "verify_coverage_text_handoff",
            "verify_provisional_collection",
            "verify_provisional_host",
            "verify_provisional_coverage",
            "verify_provisional_static",
            "verify_provisional_tools",
            "verify_provisional_validation",
            "verify_provisional_prerequisites",
            "verify_provisional_source",
            "verify_finalizer_handoff",
            "verify_provisional_handoff",
            "verify_provisional_finalizers",
            "verify_killer_handoff",
            "verify_coverage_handoff",
            "verify_ruff_handoff",
            "verify_ruff_format_handoff",
            "retain_handoff_failure",
        ):
            patch.setattr(steps, name, lambda *_args, **_kwargs: Ok(None))
        assert steps.verify_provisional_oracle(
            context, context.directory, marker
        ) == Ok(None)
        patch.setattr(steps.ownership, "guarded_census", lambda *_args: Ok(()))
        patch.setattr(steps, "_parent_bound_census", lambda *_args: Err("changed"))
        assert isinstance(
            steps.verify_provisional_oracle(context, context.directory, marker), Err
        ), "unbound parent oracle census was accepted"
        patch.setattr(steps, "_parent_bound_census", lambda *_args: Ok(()))
        patch.setattr(
            steps, "_provisional_values_for_identity", lambda *_args: Ok(forged)
        )
        assert isinstance(
            steps.verify_provisional_oracle(context, context.directory, marker), Err
        ), "parent accepted hidden oracle failure"
        assert isinstance(steps.verify_python_handoffs(context, marker), Err), (
            "live parent accepted hidden oracle failure"
        )
        patch.setattr(
            steps, "retain_gate_output", lambda *_args, **_kwargs: Ok(context.directory)
        )
        patch.setattr(
            steps,
            "verify_retained_streams",
            lambda _directory, _streams, _observed, prior: prior,
        )
        patch.setattr(
            steps,
            "verify_retained_artifacts",
            lambda _directory, _observed, prior: prior,
        )
        retained = steps.retain_verified_gate_output(
            context, Path("/state"), (marker, ""), verify_handoff=True
        )
        assert isinstance(retained, Err), (
            "retained parent accepted hidden oracle failure"
        )
        clean_scopes = tuple(replace(scope, failures=()) for scope in scopes)
        patch.setattr(steps, "oracle_diagnostics", lambda *_args: Ok(clean_scopes))
        for changed in (
            (replace(outcomes, outcomes=(("oracle", 1),)), details),
            (outcomes, replace(details, issues=((None, "changed"),))),
        ):
            patch.setattr(
                steps,
                "_oracle_handoff_observations",
                lambda *_args, changed=changed: Ok(changed),
            )
            assert isinstance(
                steps.verify_provisional_oracle(context, context.directory, marker), Err
            ), "changed oracle after seal was accepted"
            assert isinstance(steps.verify_python_handoffs(context, marker), Err), (
                "live parent accepted changed oracle after seal"
            )
            retained = steps.retain_verified_gate_output(
                context, Path("/state"), (marker, ""), verify_handoff=True
            )
            assert isinstance(retained, Err), (
                "retained parent accepted changed oracle after seal"
            )


def _assert_captured_coverage_scoping(
    entries: tuple[Entry, ...],
    subject: str,
    captured: ProvisionalCapture,
    tools: ToolOutcome,
) -> None:
    """Join a constructed coverage observation without clearing shared damage."""
    report = json.dumps(
        {
            "meta": {"format": 3, "version": "7.17.0", "branch_coverage": True},
            "files": {
                subject: {
                    "executed_lines": [1],
                    "missing_lines": [2],
                    "executed_branches": [],
                    "missing_branches": [],
                    "summary": {
                        "num_statements": 2,
                        "covered_lines": 1,
                        "missing_lines": 1,
                        "num_branches": 0,
                        "covered_branches": 0,
                        "missing_branches": 0,
                    },
                }
            },
            "totals": {
                "num_statements": 2,
                "covered_lines": 1,
                "missing_lines": 1,
                "num_branches": 0,
                "covered_branches": 0,
                "missing_branches": 0,
            },
        }
    )
    wrapper = json.dumps(
        {"nonce": "current", "version": "7.17.0", "report": report}, sort_keys=True
    ).encode()
    coverage = CoverageSnapshot(
        "current",
        (coverage_hosts.CoverageFact(subject, 1, 0),),
        wrapper,
        (1, 1),
        report.encode(),
        (1, 2),
        entries,
    )
    coverage_tools = replace(
        tools,
        code=1,
        evidence=Ok(LegEvidence("current", (("cabal-test", 0), ("pytest", 2)))),
        substeps=Ok(ToolSubsteps("current", (("pytest", (0, 0, 2)),))),
        host=Ok(
            lanes.HostFacts(
                family="Linux",
                architecture="x86_64",
                checkout=True,
                git=True,
                debian=True,
            )
        ),
    )
    with_coverage = replace(
        captured, tools=coverage_tools, coverage=Ok(coverage), family="Linux"
    )
    attributed = captured_phase_observations(with_coverage)
    assert isinstance(attributed, Ok), attributed
    assert "coverage incomplete: " + subject in attributed.value[0].failures, (
        "captured coverage failure was not scoped"
    )
    assert "coverage report failed" in attributed.value[0].failures, (
        "shared coverage failure was removed prematurely"
    )
    foreign = replace(
        with_coverage,
        tools=replace(
            coverage_tools,
            host=Ok(
                lanes.HostFacts(
                    family="Linux", architecture="x86_64", checkout=True, git=True
                )
            ),
        ),
    )
    foreign_result = captured_phase_observations(foreign)
    assert isinstance(foreign_result, Ok)
    assert "native host lane unmet: linux" in foreign_result.value[0].failures, (
        "phase observations ignored native host eligibility"
    )
    assert isinstance(
        captured_phase_observations(replace(with_coverage, coverage=None)), Err
    ), "missing captured coverage was accepted"


def _assert_phase_host_scoping(
    captured: ProvisionalCapture,
    tools: ToolOutcome,
    phase: Phase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keep missing later host capabilities local to their consumers."""
    late = phase_text(
        Path("phase-1-example.md"),
        "**Host lane**: linux-live-clean\n### Sprint 1.1: Test [Planned]\n",
    )
    assert late is not None
    native_host = lanes.HostFacts(
        family="Linux", architecture="x86_64", checkout=True, git=True, debian=True
    )
    host_capture = replace(
        captured, family="Linux", tools=replace(tools, host=Ok(native_host))
    )
    empty_scopes = steps.ToolFailureAttribution(
        frozenset(), ((0, frozenset()), (1, frozenset()))
    )
    host_scopes = steps.phase_host_attribution(
        host_capture, (phase, late), empty_scopes
    )
    assert isinstance(host_scopes, Ok)
    assert not host_scopes.value.scoped[0][1], "later host lane blocked earlier phase"
    assert (
        "native host lane unmet: linux-live-clean" in host_scopes.value.scoped[1][1]
    ), "unmet native host lane was accepted"
    _assert_parent_host_scopes(
        host_capture, (phase, late), host_scopes.value, monkeypatch
    )
    foreign = replace(
        host_capture, tools=replace(tools, host=Ok(replace(native_host, debian=False)))
    )
    foreign_scopes = steps.phase_host_attribution(foreign, (phase, late), empty_scopes)
    assert isinstance(foreign_scopes, Ok)
    assert "native host lane unmet: linux" in foreign_scopes.value.scoped[0][1], (
        "non-Debian host qualified an earlier phase"
    )
    assert isinstance(
        steps.phase_host_attribution(
            replace(host_capture, tools=replace(tools, host=None)),
            (phase, late),
            empty_scopes,
        ),
        Err,
    ), "missing native host observation was accepted"
    mismatched = replace(
        host_capture,
        tools=replace(tools, host=Ok(replace(native_host, family="Windows"))),
    )
    assert isinstance(
        steps.phase_host_attribution(mismatched, (phase, late), empty_scopes), Err
    ), "foreign native host observation was accepted"


def _assert_parent_host_scopes(
    captured: ProvisionalCapture,
    declarations: tuple[Phase, ...],
    scoped: steps.ToolFailureAttribution,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reject hidden native-host failures on both parent routes."""
    observed = tuple(
        steps.phase_reports.PhaseResult(
            number, str(number + 1) * 64, failures | {"unverified-run"}
        )
        for number, failures in scoped.scoped
    )
    forged = (observed[0], replace(observed[1], failures=frozenset({"unverified-run"})))
    assert steps.verify_phase_host_failures(captured, declarations, observed) == Ok(
        None
    )
    assert isinstance(
        steps.verify_phase_host_failures(captured, declarations, forged), Err
    ), "parent accepted hidden host failure"
    nonce = captured.nonce
    context = steps.CheckRun(Path("/source"), Path("/run"), nonce, "Linux")
    finalizers = LegEvidence(
        nonce, tuple((name, 0) for name in steps.FINALIZER_NAMES[:-1])
    )
    assert isinstance(captured.tools.host, Ok)
    marker = (
        steps.host_observation_seal(nonce, captured.tools.host.value)
        + "\n"
        + steps.finalizer_seal(finalizers)
    )
    with monkeypatch.context() as patch:
        patch.setattr(steps, "finalizer_observation", lambda *_args: Ok(finalizers))
        patch.setattr(
            steps, "_provisional_values_for_identity", lambda *_args: Ok(observed)
        )
        patch.setattr(steps.ownership, "guarded_census", lambda *_args: Ok(()))
        patch.setattr(steps, "_parent_bound_census", lambda *_args: Ok(()))
        patch.setattr(steps, "host_observation", lambda *_args: captured.tools.host)
        patch.setattr(steps, "census_phases", lambda *_args: Ok(declarations))
        for name in (
            "verify_python_commands_handoff",
            "verify_host_handoff",
            "_verify_provisional_census",
            "verify_python_plan_handoff",
            "verify_provisional_input_identities",
            "verify_tool_results_handoff",
            "verify_pytest_handoff",
            "verify_oracle_handoff",
            "verify_native_handoff",
            "verify_ty_handoff",
            "verify_coverage_text_handoff",
            "verify_provisional_collection",
            "verify_provisional_oracle",
            "verify_provisional_coverage",
            "verify_provisional_static",
            "verify_provisional_tools",
            "verify_provisional_validation",
            "verify_provisional_prerequisites",
            "verify_provisional_source",
            "verify_finalizer_handoff",
            "verify_provisional_handoff",
            "verify_provisional_finalizers",
            "verify_killer_handoff",
            "verify_coverage_handoff",
            "verify_ruff_handoff",
            "verify_ruff_format_handoff",
            "retain_handoff_failure",
        ):
            patch.setattr(steps, name, lambda *_args, **_kwargs: Ok(None))
        assert steps.verify_provisional_host(context, context.directory, marker) == Ok(
            None
        )
        patch.setattr(steps.ownership, "guarded_census", lambda *_args: Ok(()))
        patch.setattr(steps, "_parent_bound_census", lambda *_args: Err("changed"))
        assert isinstance(
            steps.verify_provisional_host(context, context.directory, marker), Err
        ), "unbound parent host census was accepted"
        patch.setattr(steps, "_parent_bound_census", lambda *_args: Ok(()))
        patch.setattr(
            steps, "_provisional_values_for_identity", lambda *_args: Ok(forged)
        )
        assert isinstance(
            steps.verify_provisional_host(context, context.directory, marker), Err
        ), "parent accepted hidden host failure"
        changed = replace(
            captured.tools.host.value,
            mux=True,
            agents=True,
            authenticated=True,
            clean=True,
        )
        changed_capture = replace(
            captured, tools=replace(captured.tools, host=Ok(changed))
        )
        assert steps.verify_phase_host_failures(
            changed_capture, declarations, forged
        ) == Ok(None)
        patch.setattr(steps, "host_observation", lambda *_args: Ok(changed))
        assert isinstance(
            steps.verify_provisional_host(context, context.directory, marker), Err
        ), "changed host after seal was accepted"
        patch.setattr(steps, "host_observation", lambda *_args: captured.tools.host)
        assert isinstance(steps.verify_python_handoffs(context, marker), Err), (
            "live parent accepted hidden host failure"
        )
        patch.setattr(
            steps, "retain_gate_output", lambda *_args, **_kwargs: Ok(context.directory)
        )
        patch.setattr(
            steps,
            "verify_retained_streams",
            lambda _directory, _streams, _observed, prior: prior,
        )
        patch.setattr(
            steps,
            "verify_retained_artifacts",
            lambda _directory, _observed, prior: prior,
        )
        retained = steps.retain_verified_gate_output(
            context, Path("/state"), (marker, ""), verify_handoff=True
        )
        assert isinstance(retained, Err), "retained parent accepted hidden host failure"
        patch.setattr(steps, "host_observation", lambda *_args: Ok(changed))
        assert isinstance(steps.verify_python_handoffs(context, marker), Err), (
            "live parent accepted a changed host after seal"
        )
        changed_retained = steps.retain_verified_gate_output(
            context, Path("/state"), (marker, ""), verify_handoff=True
        )
        assert isinstance(changed_retained, Err), (
            "retained parent accepted a changed host after seal"
        )


def _assert_ty_scopes_reach_provisional(
    captured: ProvisionalCapture, tools: ToolOutcome, subject: str
) -> None:
    """Carry a captured source-owned type error into the phase observation."""
    root = Path.cwd().resolve()
    diagnostic = json.dumps(
        [
            {
                "check_name": "invalid-assignment",
                "description": "type mismatch",
                "severity": "major",
                "location": {
                    "path": str(root / subject),
                    "positions": {"begin": {"line": 1}},
                },
            }
        ]
    )
    output = Output(1, diagnostic, "")
    facts = steps.parse_ty_output(root, output)
    assert isinstance(facts, Ok)
    snapshot = steps.TySnapshot("current", root, output, facts.value)
    typed_tools = replace(
        tools,
        code=1,
        evidence=Ok(
            LegEvidence("current", (("cabal-test", 0), ("pytest", 0), ("ty", 1)))
        ),
        substeps=Ok(ToolSubsteps("current", (("pytest", (0, 0, 0)), ("ty", (1,))))),
        ty=Ok(snapshot),
    )
    observed = captured_phase_observations(
        replace(
            captured,
            tools=typed_tools,
            schedule=("cabal-test", "pytest", "ty"),
            substep_schedule=(("pytest", 3), ("ty", 1)),
        )
    )
    assert isinstance(observed, Ok), observed
    assert any(
        "ty invalid-assignment" in value for value in observed.value[0].failures
    ), "type source scope was lost"
    assert "unattributed tool failure: ty" in observed.value[0].failures, (
        "type failure was cleared before authentication"
    )


def _assert_phase_input_identities(
    entries: tuple[Entry, ...],
    phase: Phase,
    result: tuple[steps.phase_reports.PhaseResult, ...],
) -> None:
    """Reject forged, incomplete or stale provisional input identities."""
    assert result[0].failures == frozenset({"unverified-run"})
    assert steps.verify_phase_input_identities(entries, (phase,), result) == Ok(None)
    forged = (replace(result[0], identity="0" * 64),)
    assert isinstance(
        steps.verify_phase_input_identities(entries, (phase,), forged), Err
    ), "foreign phase input identity was accepted"
    changed = tuple(
        replace(entry, payloads=(b"changed source",))
        if entry.path == "src/agentctl/subject.py"
        else entry
        for entry in entries
    )
    assert isinstance(
        steps.verify_phase_input_identities(changed, (phase,), result), Err
    ), "changed phase source identity was accepted"
    assert isinstance(
        steps.verify_phase_input_identities(entries, (phase,), ()), Err
    ), "incomplete phase input identities were accepted"


def _collection_marker_output(captured: ProvisionalCapture) -> str:
    """Construct the child seals for these observed test records."""
    pytest_run, native, killers = (
        captured.tools.pytest,
        captured.tools.native,
        captured.tools.killers,
    )
    assert isinstance(pytest_run, Ok)
    assert isinstance(native, Ok)
    assert isinstance(killers, Ok)
    native_seal = steps.native_observation_seal(captured.nonce, native.value)
    assert isinstance(native_seal, Ok)
    return "\n".join(
        (
            steps.pytest_manifest_seal(captured.nonce, pytest_run.value),
            native_seal.value,
            steps.killer_seal(captured.nonce, killers.value),
        )
    )


def _assert_parent_collection_failures(
    captured: ProvisionalCapture,
    phase: Phase,
    result: tuple[steps.phase_reports.PhaseResult, ...],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Refuse to omit failures independently derived from collection and killers."""
    assert captured.claims is not None
    record = captured.claims[0][0]
    assert any("failed:baseline" in item for item in result[0].failures), (
        "individual mutant killer failure was lost from phase observation"
    )
    assert steps.verify_phase_collection_failures(captured, (phase,), result) == Ok(
        None
    )
    for text in ("failed:baseline", "failed test:"):
        filtered = frozenset(item for item in result[0].failures if text not in item)
        assert filtered != result[0].failures
        forged = (replace(result[0], failures=filtered),)
        assert isinstance(
            steps.verify_phase_collection_failures(captured, (phase,), forged), Err
        ), "phase collection or killer failure was hidden"
    _assert_gate_execution_in_provisional(captured, phase, record.killers[0], record)
    _assert_undeclared_mutant_in_provisional(captured, phase, record)
    context = steps.CheckRun(Path("/source"), Path("/run"), captured.nonce, "Linux")
    output = _collection_marker_output(captured)
    assert steps.collection_capture_sealed(captured, output) == Ok(None)
    assert isinstance(captured.tools.pytest, Ok)
    assert isinstance(captured.tools.native, Ok)
    assert isinstance(captured.tools.killers, Ok)
    python = captured.tools.pytest.value
    native = captured.tools.native.value
    killers = captured.tools.killers.value
    changed = (
        (
            replace(captured.tools, pytest=Ok(replace(python, forbidden=("changed",)))),
            "changed pytest observation after seal was accepted",
        ),
        (
            replace(
                captured.tools,
                native=Ok(
                    replace(
                        native,
                        manifest=replace(native.manifest, forbidden=("changed",)),
                    )
                ),
            ),
            "changed native observation after seal was accepted",
        ),
        (
            replace(captured.tools, killers=Ok(replace(killers, digest="changed"))),
            "changed killer observation after seal was accepted",
        ),
    )
    for changed_tools, reason in changed:
        assert isinstance(
            steps.collection_capture_sealed(
                replace(captured, tools=changed_tools), output
            ),
            Err,
        ), reason
    finalizers = LegEvidence(
        captured.nonce, tuple((name, 0) for name in steps.FINALIZER_NAMES[:-1])
    )
    output += "\n" + steps.finalizer_seal(finalizers)
    with monkeypatch.context() as patch:
        _assert_parent_collection_capture(captured, phase, context, patch)
        patch.setattr(steps, "finalizer_observation", lambda *_args: Ok(finalizers))
        patch.setattr(
            steps, "_provisional_values_for_identity", lambda *_args: Ok(result)
        )
        patch.setattr(
            steps, "_parent_collection_capture", lambda *_args: Ok(((phase,), captured))
        )
        for name in (
            "verify_python_commands_handoff",
            "verify_pytest_handoff",
            "verify_killer_handoff",
            "verify_native_handoff",
            "_verify_provisional_census",
        ):
            patch.setattr(steps, name, lambda *_args: Ok(None))
        assert steps.verify_provisional_collection(
            context, context.directory, output
        ) == Ok(None)
        filtered = frozenset(
            item for item in result[0].failures if "failed:baseline" not in item
        )
        forged = (replace(result[0], failures=filtered),)
        patch.setattr(
            steps, "_provisional_values_for_identity", lambda *_args: Ok(forged)
        )
        assert isinstance(
            steps.verify_provisional_collection(context, context.directory, output), Err
        ), "parent accepted hidden collection or killer failure"
        _assert_collection_parent_routes(context, patch, output)
        _assert_parent_native_routes(captured, phase, result, context, patch)
        patch.setattr(
            steps, "verify_phase_collection_failures", lambda *_args: Ok(None)
        )
        for changed_tools, _reason in changed:
            patch.setattr(
                steps,
                "_parent_collection_capture",
                lambda *_args, changed_tools=changed_tools: Ok(
                    ((phase,), replace(captured, tools=changed_tools))
                ),
            )
            assert isinstance(
                steps.verify_provisional_collection(context, context.directory, output),
                Err,
            ), "parent accepted changed collection after seal"
            assert isinstance(steps.verify_python_handoffs(context, output), Err), (
                "live parent accepted changed collection after seal"
            )
            retained = steps.retain_verified_gate_output(
                context, Path("/state"), (output, ""), verify_handoff=True
            )
            assert isinstance(retained, Err), (
                "retained parent accepted changed collection after seal"
            )


def _assert_parent_native_routes(
    captured: ProvisionalCapture,
    phase: Phase,
    result: tuple[steps.phase_reports.PhaseResult, ...],
    context: steps.CheckRun,
    patch: pytest.MonkeyPatch,
) -> None:
    """Retain a native failure even when collection is intact."""
    native = captured.tools.native
    assert isinstance(native, Ok)
    node = next(iter(native.value.manifest.collected))
    failed_run = replace(
        native.value.manifest, passed=frozenset(), forbidden=("failed: " + node,)
    )
    failed_snapshot = replace(native.value, manifest=failed_run)
    failed = replace(
        captured, tools=replace(captured.tools, native=Ok(failed_snapshot))
    )
    patch.setattr(
        steps, "_parent_collection_capture", lambda *_args: Ok(((phase,), failed))
    )
    patch.setattr(steps, "_provisional_values_for_identity", lambda *_args: Ok(result))
    output = (
        _collection_marker_output(failed)
        + "\n"
        + steps.finalizer_seal(
            LegEvidence(
                context.nonce, tuple((name, 0) for name in steps.FINALIZER_NAMES[:-1])
            )
        )
    )
    assert isinstance(
        steps.verify_provisional_collection(context, context.directory, output), Err
    ), "parent accepted hidden native failure"
    _assert_collection_parent_routes(context, patch, output)


def _assert_parent_collection_capture(
    captured: ProvisionalCapture,
    phase: Phase,
    context: steps.CheckRun,
    patch: pytest.MonkeyPatch,
) -> None:
    """Recover parent inputs while requiring observed native mutant ownership."""
    assert captured.claims is not None
    records, owners = captured.claims
    patch.setattr(steps.ownership, "guarded_census", lambda *_args: captured.census)
    patch.setattr(steps, "_parent_bound_census", lambda *_args: captured.census)
    patch.setattr(steps, "census_phases", lambda *_args: Ok((phase,)))
    patch.setattr(steps, "census_corpus", lambda *_args: Ok(records))
    patch.setattr(steps, "native_snapshot", lambda *_args: captured.tools.native)
    patch.setattr(steps, "pytest_observation", lambda *_args: captured.tools.pytest)
    patch.setattr(steps.mutant_report, "read", lambda *_args: captured.tools.killers)
    patch.setattr(steps, "complete_mutant_owners", lambda *_args: Err("native pending"))
    patch.setattr(steps, "observed_native_mutant_owners", lambda *_args: Ok(owners))
    built = steps.__dict__["_parent_collection_capture"](context, context.directory, "")
    assert isinstance(built, Ok), built
    assert built.value[1].claims == (records, owners), (
        "parent native ownership was not observed"
    )
    assert built.value[1].tools.native == captured.tools.native, (
        "parent native snapshot was not recovered"
    )
    patch.setattr(steps.ownership, "guarded_census", lambda *_args: captured.census)
    patch.setattr(steps, "_parent_bound_census", lambda *_args: Err("changed"))
    assert isinstance(
        steps.__dict__["_parent_collection_capture"](context, context.directory, ""),
        Err,
    ), "unbound parent collection census was accepted"
    patch.setattr(steps, "_parent_bound_census", lambda *_args: captured.census)
    patch.setattr(
        steps, "observed_native_mutant_owners", lambda *_args: Err("foreign native")
    )
    refused = steps.__dict__["_parent_collection_capture"](
        context, context.directory, ""
    )
    assert isinstance(refused, Err), "unverified native mutant ownership was accepted"


def _assert_collection_parent_routes(
    context: steps.CheckRun, patch: pytest.MonkeyPatch, output: str
) -> None:
    """Both live and retained parent paths must invoke the collection recheck."""
    for name in (
        "verify_python_plan_handoff",
        "verify_provisional_input_identities",
        "verify_tool_results_handoff",
        "verify_oracle_handoff",
        "verify_host_handoff",
        "verify_ty_handoff",
        "verify_coverage_text_handoff",
        "verify_provisional_oracle",
        "verify_provisional_host",
        "verify_provisional_coverage",
        "verify_provisional_static",
        "verify_provisional_tools",
        "verify_provisional_validation",
        "verify_provisional_prerequisites",
        "verify_provisional_source",
        "verify_finalizer_handoff",
        "verify_provisional_handoff",
        "verify_provisional_finalizers",
        "verify_coverage_handoff",
        "verify_ruff_handoff",
        "verify_ruff_format_handoff",
        "retain_handoff_failure",
    ):
        patch.setattr(steps, name, lambda *_args, **_kwargs: Ok(None))
    assert isinstance(steps.verify_python_handoffs(context, output), Err), (
        "live parent accepted hidden collection failure"
    )
    patch.setattr(
        steps, "retain_gate_output", lambda *_args, **_kwargs: Ok(context.directory)
    )
    patch.setattr(
        steps,
        "verify_retained_streams",
        lambda _directory, _streams, _observed, prior: prior,
    )
    patch.setattr(
        steps,
        "verify_retained_artifacts",
        lambda _directory, _observed, prior: prior,
    )
    retained = steps.retain_verified_gate_output(
        context, Path("/state"), (output, ""), verify_handoff=True
    )
    assert isinstance(retained, Err), (
        "retained parent accepted hidden collection failure"
    )


def _assert_parent_phase_input_identities(
    entries: tuple[Entry, ...],
    phase: Phase,
    result: tuple[steps.phase_reports.PhaseResult, ...],
    directory: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reject sealed identities that disagree with the parent's guarded census."""
    nonce = "a" * 32
    digest = "a" * 64
    commands = tuple((name, (("python", name),)) for name in steps.PYTHON_COMMAND_NAMES)
    recorded = steps.record_python_commands(
        directory, nonce, directory, commands, digest
    )
    passing = {"python-commands", "write-guard", "containment"}
    finalizers = steps.record_finalizers(
        directory,
        nonce,
        tuple((name, int(name not in passing)) for name in steps.FINALIZER_NAMES[:-1]),
    )
    assert isinstance(recorded, Ok)
    assert isinstance(finalizers, Ok)
    finalized = steps.provisional_finalizer_failures(
        Ok(result), (*finalizers.value.outcomes, ("finalizer-record", 0))
    )
    assert isinstance(finalized, Ok)
    result = finalized.value
    record = steps.record_provisional_phases(directory, nonce, Ok(result))
    assert isinstance(record, Ok)
    output = (
        steps.python_commands_seal(nonce, recorded.value.record)
        + "\n"
        + steps.provisional_seal(nonce, record.value)
        + "\n"
        + steps.finalizer_seal(finalizers.value)
        + "\n"
    )
    context = steps.CheckRun(directory, directory, nonce, "Linux")
    with monkeypatch.context() as patch:
        patch.setattr(steps.ownership, "guarded_census", lambda _root: Ok(entries))
        patch.setattr(steps.evidence, "digest_census", lambda _entries: Ok(digest))
        patch.setattr(steps, "census_phases", lambda _root, _entries: Ok((phase,)))
        assert steps.verify_provisional_input_identities(
            context, directory, output
        ) == Ok(None)
        retained = steps.retain_verified_gate_output(
            context,
            directory.parent / (directory.name + "-phase-ok"),
            (output, "primary\n"),
            verify_handoff=True,
        )
        assert isinstance(retained, Ok), retained
        patch.setattr(steps.evidence, "digest_census", lambda _entries: Ok("b" * 64))
        assert isinstance(
            steps.verify_provisional_input_identities(context, directory, output), Err
        ), "changed phase source census was accepted"
        patch.setattr(steps.evidence, "digest_census", lambda _entries: Ok(digest))
        forged = (replace(result[0], identity="0" * 64),)
        forged_record = steps.provisional_phase_record(nonce, Ok(forged))
        assert isinstance(forged_record, Ok)
        (directory / "provisional-phases.json").write_bytes(forged_record.value)
        forged_output = (
            steps.python_commands_seal(nonce, recorded.value.record)
            + "\n"
            + steps.provisional_seal(nonce, forged_record.value)
            + "\n"
            + steps.finalizer_seal(finalizers.value)
            + "\n"
        )
        assert isinstance(
            steps.verify_provisional_input_identities(
                context, directory, forged_output
            ),
            Err,
        ), "sealed foreign phase input identity was accepted"
        patch.setattr(steps, "verify_python_plan_handoff", lambda *_args: Ok(None))
        patch.setattr(steps, "verify_provisional_source", lambda *_args: Ok(None))
        patch.setattr(
            steps, "verify_provisional_prerequisites", lambda *_args: Ok(None)
        )
        assert isinstance(steps.verify_python_handoffs(context, forged_output), Err), (
            "live foreign phase identity was accepted"
        )
        retained_forgery = steps.retain_verified_gate_output(
            context,
            directory.parent / (directory.name + "-phase-forged"),
            (forged_output, "primary\n"),
            verify_handoff=True,
        )
        assert isinstance(retained_forgery, Err), (
            "retained foreign phase identity was accepted"
        )


@pytest.mark.evidence("real")
def test_parent_verifies_provisional_phase_input_identities(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Check sealed parent and retained identities against independent census values."""
    paths = (
        "src/agentctl/check/source_ownership.toml",
        "tests/test_early.py",
        "src/agentctl/subject.py",
    )
    manifest = "version = 1\n[[phases]]\nnumber = 0\nprerequisites = []\n"
    for path in paths:
        manifest += (
            f'[[artifacts]]\npath = "{path}"\ncapability = "governance"\n'
            "owner = 0\nconsumers = [0]\nrequired = true\n"
        )
    entries = (
        Entry(paths[0], "file", (manifest.encode(),)),
        Entry(paths[1], "file", (b"test",)),
        Entry(paths[2], "file", (b"source",)),
    )
    phase = phase_text(
        Path("phase-0-example.md"),
        "### Sprint 0.1: Test [Active]\n"
        f"**Validation tests**: `{paths[1]}::test_case`\n## Remaining Work\n",
    )
    assert phase is not None
    work = steps.scoped_source_inputs(entries, (phase,))
    assert isinstance(work, Ok)
    calculated = steps.phase_reports.calculate_scoped_inputs(
        work.value.work.phases, work.value.work.sources, frozenset(), frozenset()
    )
    assert isinstance(calculated, Ok)
    result = tuple(
        replace(item, failures=item.failures | {"unverified-run"})
        for item in calculated.value
    )
    _assert_parent_phase_input_identities(entries, phase, result, tmp_path, monkeypatch)


@pytest.mark.evidence("value")
def test_gate_captures_provisional_phase_observations(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Join the actual captured value shapes and reject a foreign native census."""
    paths = (
        "src/agentctl/check/source_ownership.toml",
        "tests/test_early.py",
        "src/agentctl/haskell/native.hs",
        "tests/governance/test_mutants.py",
        "src/agentctl/subject.py",
        "src/agentctl/check/coverage_hosts.toml",
        "pyproject.toml",
    )
    document = "version = 1\n[[phases]]\nnumber = 0\nprerequisites = []\n"
    for path in paths:
        document += (
            f'[[artifacts]]\npath = "{path}"\ncapability = "governance"\n'
            "owner = 0\nconsumers = [0]\nrequired = true\n"
        )
    entries = (
        Entry(paths[0], "file", (document.encode(),)),
        Entry(paths[1], "file", (b"python source",)),
        Entry(paths[2], "file", (b"native source",)),
        Entry(paths[3], "file", (b"mutation source",)),
        Entry(paths[4], "file", (b"python source",)),
        Entry(
            paths[5],
            "file",
            (
                (
                    b"version = 1\n[[source]]\n"
                    b"path = 'src/agentctl/subject.py'\nhosts = ['Linux']\n"
                ),
            ),
        ),
        Entry(
            paths[6],
            "file",
            (b"[project.optional-dependencies]\ndev = ['coverage==7.17.0']\n",),
        ),
    )
    node = paths[1] + "::test_case"
    record = Mutant("M-control", Operator.DELETE, paths[2], "a", "", (node,), "x")
    mutation_node = mutant_report.PREFIX + record.identifier + "]"
    native_node = "haskell:agentctl-core-test/Example/control"
    phase = phase_text(
        Path("phase-0-example.md"),
        "**Host lane**: linux\n"
        "### Sprint 0.1: Test [Active]\n"
        "**Mutants**: `M-control`\n"
        f"**Validation tests**: `{node}`\n## Remaining Work\n",
    )
    assert phase is not None
    python = RunEvidence(
        "current",
        frozenset({node, mutation_node}),
        frozenset({node, mutation_node}),
        frozenset({node, mutation_node}),
        (),
        (),
    )
    native = RunEvidence(
        "current",
        frozenset({native_node}),
        frozenset({native_node}),
        frozenset({native_node}),
        (),
        (),
    )
    snapshot = NativeSnapshot(native, ((native_node, paths[2]),), entries)
    tools = ToolOutcome(
        0,
        Ok(LegEvidence("current", (("cabal-test", 0), ("pytest", 0)))),
        Ok(ToolSubsteps("current", (("pytest", (0, 0, 0)),))),
        Ok(python),
        Ok(snapshot),
        killers=Ok(
            mutant_report.Report(
                "current",
                (
                    mutant_report.Record(
                        record.identifier,
                        "",
                        (mutant_report.Killer(node, "passed", "killed"),),
                    ),
                ),
                "captured",
            )
        ),
    )
    captured = ProvisionalCapture(
        Ok(entries),
        Ok((phase,)),
        tools,
        ((record,), ((record.identifier, 0),)),
        Ok((OracleScope(0, ()),)),
        "current",
        ("cabal-test", "pytest"),
        (("pytest", 3),),
        after_failure=frozenset({"pytest"}),
    )
    failed_tools = replace(
        tools,
        code=1,
        evidence=Ok(
            LegEvidence(
                "current", (("ruff-check", 1), ("cabal-test", 0), ("pytest", 0))
            )
        ),
        substeps=Ok(
            ToolSubsteps("current", (("ruff-check", (1,)), ("pytest", (0, 0, 0))))
        ),
    )
    failed_capture = replace(
        captured,
        tools=failed_tools,
        schedule=("ruff-check", "cabal-test", "pytest"),
        substep_schedule=(("ruff-check", 1), ("pytest", 3)),
    )
    failed_result = captured_phase_observations(failed_capture)
    assert isinstance(failed_result, Ok)
    assert "unattributed tool failure: ruff-check" in failed_result.value[0].failures, (
        "gate lost captured tool failure"
    )
    _assert_phase_host_scoping(captured, tools, phase, monkeypatch)
    result = captured_phase_observations(captured)
    assert isinstance(result, Ok), result
    _assert_phase_input_identities(entries, phase, result.value)
    diagnostic = steps.validation_diagnostics(
        ("source census failed",),
        ("validator could not read claims",),
        (("tool outcomes", 1), ("host observation", 0)),
    )
    assert diagnostic == (
        "source census failed",
        "validator could not read claims",
        "tool outcomes failed",
    ), "pre-finalizer validation diagnostics were lost"
    damaged = captured_phase_observations(replace(captured, validation=diagnostic))
    assert isinstance(damaged, Ok), damaged
    assert {
        "unattributed validation: source census failed",
        "unattributed validation: validator could not read claims",
        "unattributed validation: tool outcomes failed",
    } <= damaged.value[0].failures, "pre-finalizer validation damage was lost"
    assert isinstance(
        captured_phase_observations(replace(captured, validation=("",))), Err
    ), "empty validation diagnostic was accepted"
    _assert_captured_coverage_scoping(entries, paths[4], captured, tools)
    failed_report = mutant_report.Report(
        "current",
        (
            mutant_report.Record(
                record.identifier,
                "",
                (mutant_report.Killer(node, "failed:baseline", "not-run"),),
            ),
        ),
        "failed",
    )
    failed_python = replace(python, passed=frozenset({node}))
    failed_killer = replace(
        captured,
        tools=replace(
            tools,
            code=1,
            evidence=Ok(LegEvidence("current", (("cabal-test", 0), ("pytest", 1)))),
            substeps=Ok(ToolSubsteps("current", (("pytest", (1, 0, 0)),))),
            pytest=Ok(failed_python),
            killers=Ok(failed_report),
        ),
    )
    failed_result = captured_phase_observations(failed_killer)
    assert isinstance(failed_result, Ok), failed_result
    _assert_parent_collection_failures(
        failed_killer, phase, failed_result.value, monkeypatch
    )
    absent_report = replace(
        failed_killer, tools=replace(failed_killer.tools, killers=None)
    )
    assert isinstance(captured_phase_observations(absent_report), Err), (
        "missing mutant killer report was accepted"
    )
    forged_report = replace(failed_report, nonce="stale")
    invalid_report = replace(
        failed_killer, tools=replace(failed_killer.tools, killers=Ok(forged_report))
    )
    assert isinstance(captured_phase_observations(invalid_report), Err), (
        "stale mutant killer report was accepted"
    )
    assert report_provisional_phases(result) == 1, (
        "provisional phase allowed an overall pass"
    )
    assert "not a verdict" in capsys.readouterr().out, (
        "provisional phase was presented as a verdict"
    )
    _assert_ty_scopes_reach_provisional(captured, tools, paths[4])
    foreign = replace(snapshot, entries=entries[:-1])
    invalid = replace(captured, tools=replace(tools, native=Ok(foreign)))
    assert isinstance(captured_phase_observations(invalid), Err), (
        "native observation with a foreign census was accepted"
    )
    assert isinstance(
        captured_phase_observations(replace(captured, nonce="stale")), Err
    )


def _assert_undeclared_mutant_in_provisional(
    captured: ProvisionalCapture, phase: Phase, record: Mutant
) -> None:
    """Keep missing declarations in the child and independently verify them."""
    undeclared_phase = phase_text(
        phase.path, phase.text.replace("**Mutants**: `M-control`\n", "")
    )
    assert undeclared_phase is not None
    undeclared_capture = replace(captured, phases=Ok((undeclared_phase,)))
    undeclared_result = captured_phase_observations(undeclared_capture)
    assert isinstance(undeclared_result, Ok)
    undeclared = "undeclared corpus mutant: " + record.identifier
    assert undeclared in undeclared_result.value[0].failures, (
        "child omitted undeclared mutant ownership failure"
    )
    assert steps.verify_phase_collection_failures(
        undeclared_capture, (undeclared_phase,), undeclared_result.value
    ) == Ok(None)
    forged = (
        replace(
            undeclared_result.value[0],
            failures=undeclared_result.value[0].failures - {undeclared},
        ),
    )
    assert isinstance(
        steps.verify_phase_collection_failures(
            undeclared_capture, (undeclared_phase,), forged
        ),
        Err,
    ), "parent accepted hidden mutant declaration failure"


def _assert_source_validation_scopes(captured: ProvisionalCapture, target: str) -> None:
    local_issue = SourceIssue(target, "src.one-process-module: " + target)
    local = captured_phase_observations(replace(captured, source_issues=(local_issue,)))
    assert isinstance(local, Ok), local
    failure = "source validation: " + local_issue.message
    assert failure not in local.value[0].failures
    assert failure not in local.value[1].failures
    assert failure in local.value[2].failures, "owned source failure was lost"
    shared_issue = SourceIssue("src/unknown.py", "src.parse: src/unknown.py")
    unknown = captured_phase_observations(
        replace(captured, source_issues=(shared_issue,))
    )
    assert isinstance(unknown, Ok), unknown
    assert all(
        "unattributed validation: " + shared_issue.message in item.failures
        for item in unknown.value
    ), "unowned source failure was localized"
    global_issue = SourceIssue(None, "validator.non-vacuous: source missing")
    global_result = captured_phase_observations(
        replace(captured, source_issues=(global_issue,))
    )
    assert isinstance(global_result, Ok), global_result
    assert all(
        "unattributed validation: " + global_issue.message in item.failures
        for item in global_result.value
    )
    shared = SourceIssue("src/shared.py", "src.parse: src/shared.py")
    joint = captured_phase_observations(replace(captured, source_issues=(shared,)))
    assert isinstance(joint, Ok), joint
    shared_failure = "source validation: " + shared.message
    assert shared_failure in joint.value[0].failures
    assert shared_failure not in joint.value[1].failures
    assert shared_failure in joint.value[2].failures, "shared source consumer was lost"
    assert isinstance(captured.census, Ok)
    assert isinstance(captured.phases, Ok)
    work = steps.scoped_source_inputs(captured.census.value, captured.phases.value)
    assert isinstance(work, Ok)
    phases = work.value.work.phases
    entries = captured.census.value
    assert isinstance(
        steps.source_validation_attribution(
            (*entries, entries[1]), phases, (local_issue,)
        ),
        Err,
    ), "duplicate source census was accepted"
    altered = (*phases[:-1], replace(phases[-1], prerequisites=frozenset()))
    assert isinstance(
        steps.source_validation_attribution(entries, altered, (local_issue,)), Err
    ), "foreign phase declarations were accepted"
    unowned = (*entries, Entry(shared_issue.path or "", "file", (b"bad",)))
    fallback = steps.source_validation_attribution(unowned, phases, (shared_issue,))
    assert isinstance(fallback, Ok)
    assert (
        "unattributed validation: " + shared_issue.message in fallback.value.shared
    ), "present unowned source was localized"
    absent = tuple(entry for entry in entries if entry.path != target)
    fallback = steps.source_validation_attribution(absent, phases, (local_issue,))
    assert isinstance(fallback, Ok)
    assert "unattributed validation: " + local_issue.message in fallback.value.shared, (
        "absent source was localized"
    )
    assert isinstance(
        steps.source_validation_attribution(
            entries, phases, (SourceIssue(target, ""),)
        ),
        Err,
    ), "empty source validation message was accepted"


def _assert_ruff_validation_scopes(
    captured: ProvisionalCapture, target: str, root: Path
) -> None:
    output = Output(
        1,
        json.dumps(
            [
                {
                    "filename": str(root / target),
                    "code": "F401",
                    "message": "unused",
                    "location": {"row": 1},
                }
            ]
        ),
        "",
    )
    facts = steps.parse_ruff_output(root, output)
    assert isinstance(facts, Ok)
    tools = replace(
        captured.tools,
        evidence=Ok(
            LegEvidence(
                "current",
                (
                    ("ruff-check", 1),
                    ("toolchain-ensure", 1),
                    ("cabal-test", 0),
                    ("pytest", 0),
                ),
            )
        ),
        substeps=Ok(
            ToolSubsteps("current", (("ruff-check", (1,)), ("pytest", (0, 0, 0))))
        ),
        ruff=Ok(RuffSnapshot("current", root, output, facts.value)),
    )
    updated = replace(
        captured,
        tools=tools,
        schedule=("ruff-check", *captured.schedule),
        substep_schedule=(("ruff-check", 1), *captured.substep_schedule),
    )
    observed = captured_phase_observations(updated)
    assert isinstance(observed, Ok), observed
    failure = "source validation: ruff F401: " + target + ":1: unused"
    assert failure not in observed.value[0].failures
    assert failure in observed.value[2].failures, "Ruff phase scope was lost"
    assert all(
        "unattributed tool failure: ruff-check" in item.failures
        for item in observed.value
    ), "shared Ruff failure was removed prematurely"


def _assert_parent_tool_failures(
    captured: ProvisionalCapture,
    declarations: tuple[Phase, ...],
    result: tuple[steps.phase_reports.PhaseResult, ...],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reject omitted scoped tool failures and unverified coverage handling."""
    assert steps.verify_phase_tool_failures(captured, declarations, result) == Ok(None)
    forged = (
        *result[:2],
        replace(result[2], failures=result[2].failures - {"toolchain-ensure failed"}),
    )
    assert isinstance(
        steps.verify_phase_tool_failures(captured, declarations, forged), Err
    ), "parent accepted hidden owned tool failure"
    readiness = "later readiness: " + captured.readiness[0]
    forged_readiness = (
        *result[:2],
        replace(result[2], failures=result[2].failures - {readiness}),
    )
    assert isinstance(
        steps.verify_phase_tool_failures(captured, declarations, forged_readiness), Err
    ), "parent accepted hidden readiness failure"
    _assert_parent_shared_tool_failure(captured, declarations, result)
    context = steps.CheckRun(Path("/source"), Path("/run"), captured.nonce, "Linux")
    finalizers = LegEvidence(
        captured.nonce, tuple((name, 0) for name in steps.FINALIZER_NAMES[:-1])
    )
    with monkeypatch.context() as patch:
        assert isinstance(captured.tools.evidence, Ok)
        assert isinstance(captured.tools.substeps, Ok)
        outcomes, attempts = (
            captured.tools.evidence.value,
            captured.tools.substeps.value,
        )
        readiness_record = steps.readiness_observation(
            captured.nonce, captured.readiness
        )
        assert isinstance(readiness_record, Ok)
        output = "\n".join(
            (
                readiness_record.value,
                _collection_marker_output(captured),
                steps.tool_results_seal(captured.nonce, outcomes, attempts),
                steps.finalizer_seal(finalizers),
            )
        )
        patch.setattr(
            steps,
            "_parent_collection_capture",
            lambda *_args: Ok((declarations, captured)),
        )
        patch.setattr(steps, "targets", lambda *_args: Ok(("source.py",)))
        patch.setattr(
            steps,
            "_read_sealed_tool_results",
            lambda *_args: Ok((outcomes, attempts)),
        )
        planned = (
            SimpleNamespace(name="toolchain-ensure"),
            SimpleNamespace(name="cabal-test"),
            steps.Leg(
                "pytest", ("python",), (("combine",), ("report",)), after_failure=True
            ),
        )
        patch.setattr(steps, "pipeline", lambda *_args, **_kwargs: planned)
        rebuilt = steps.__dict__["_parent_tool_capture"](
            context, context.directory, output
        )
        assert isinstance(rebuilt, Ok), rebuilt
        assert steps.verify_phase_tool_failures(
            rebuilt.value[1], declarations, result
        ) == Ok(None), "parent did not reconstruct tool schedule"
        patch.setattr(steps, "finalizer_observation", lambda *_args: Ok(finalizers))
        patch.setattr(
            steps, "_provisional_values_for_identity", lambda *_args: Ok(result)
        )
        for name in (
            "verify_python_commands_handoff",
            "verify_tool_results_handoff",
            "verify_pytest_handoff",
            "verify_native_handoff",
            "verify_killer_handoff",
            "verify_provisional_coverage",
            "_verify_provisional_census",
            "verify_python_plan_handoff",
            "verify_provisional_input_identities",
            "verify_oracle_handoff",
            "verify_host_handoff",
            "verify_ty_handoff",
            "verify_coverage_text_handoff",
            "verify_provisional_collection",
            "verify_provisional_oracle",
            "verify_provisional_host",
            "verify_provisional_static",
            "verify_provisional_source",
            "verify_provisional_prerequisites",
            "verify_provisional_validation",
            "verify_finalizer_handoff",
            "verify_provisional_handoff",
            "verify_provisional_finalizers",
            "verify_coverage_handoff",
            "verify_ruff_handoff",
            "verify_ruff_format_handoff",
            "retain_handoff_failure",
        ):
            patch.setattr(steps, name, lambda *_args, **_kwargs: Ok(None))
        assert steps.verify_provisional_tools(context, context.directory, output) == Ok(
            None
        )
        patch.setattr(
            steps, "verify_provisional_coverage", lambda *_args: Err("unverified")
        )
        assert isinstance(
            steps.verify_provisional_tools(context, context.directory, output), Err
        ), "unverified coverage was accepted by tool recheck"
        patch.setattr(steps, "verify_provisional_coverage", lambda *_args: Ok(None))
        patch.setattr(
            steps, "_provisional_values_for_identity", lambda *_args: Ok(forged)
        )
        assert isinstance(
            steps.verify_provisional_tools(context, context.directory, output), Err
        ), "parent accepted hidden owned tool failure"
        assert isinstance(steps.verify_python_handoffs(context, output), Err), (
            "live parent accepted hidden tool failure"
        )
        patch.setattr(
            steps, "retain_gate_output", lambda *_args, **_kwargs: Ok(context.directory)
        )
        patch.setattr(
            steps,
            "retained_stream_snapshot",
            lambda *_args: Ok(((1, 2, output.encode()), (1, 3, b""))),
        )
        patch.setattr(
            steps,
            "verify_retained_artifacts",
            lambda _directory, _observed, prior: prior,
        )
        retained = steps.retain_verified_gate_output(
            context, Path("/state"), (output, ""), verify_handoff=True
        )
        assert isinstance(retained, Err), "retained parent accepted hidden tool failure"
        assert isinstance(captured.tools.pytest, Ok)
        changed_tools = (
            replace(captured.tools, evidence=Ok(replace(outcomes, outcomes=()))),
            replace(captured.tools, substeps=Ok(replace(attempts, outcomes=()))),
            replace(captured.tools, evidence=Ok(replace(outcomes, nonce="stale"))),
            replace(captured.tools, substeps=Ok(replace(attempts, nonce="stale"))),
            replace(
                captured.tools,
                pytest=Ok(replace(captured.tools.pytest.value, forbidden=("changed",))),
            ),
        )
        patch.setattr(steps, "verify_phase_tool_failures", lambda *_args: Ok(None))
        for changed in changed_tools:
            patch.setattr(
                steps,
                "_parent_tool_capture",
                lambda *_args, changed=changed: Ok(
                    (declarations, replace(captured, tools=changed))
                ),
            )
            assert isinstance(
                steps.verify_provisional_tools(context, context.directory, output), Err
            ), "changed tool input after seal was accepted"
            assert isinstance(steps.verify_python_handoffs(context, output), Err), (
                "live parent accepted changed tool input after seal"
            )
            retained = steps.retain_verified_gate_output(
                context, Path("/state"), (output, ""), verify_handoff=True
            )
            assert isinstance(retained, Err), (
                "retained parent accepted changed tool input after seal"
            )


def _assert_parent_shared_tool_failure(
    captured: ProvisionalCapture,
    declarations: tuple[Phase, ...],
    result: tuple[steps.phase_reports.PhaseResult, ...],
) -> None:
    """Keep an unexplained tool failure shared across every phase."""
    assert isinstance(captured.tools.evidence, Ok)
    outcomes = replace(
        captured.tools.evidence.value,
        outcomes=(*captured.tools.evidence.value.outcomes, ("hlint", 1)),
    )
    expanded = replace(
        captured,
        tools=replace(captured.tools, evidence=Ok(outcomes)),
        schedule=(*captured.schedule, "hlint"),
    )
    failure = "unattributed tool failure: hlint"
    observed = tuple(
        replace(item, failures=item.failures | {failure}) for item in result
    )
    assert steps.verify_phase_tool_failures(expanded, declarations, observed) == Ok(
        None
    )
    forged = (
        replace(observed[0], failures=observed[0].failures - {failure}),
        *observed[1:],
    )
    assert isinstance(
        steps.verify_phase_tool_failures(expanded, declarations, forged), Err
    ), "parent accepted hidden shared tool failure"


@pytest.mark.evidence("value")
def test_unavailable_native_scope_follows_declared_consumers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Unavailable native evidence remains local only with complete ownership."""
    manifest_path = "src/agentctl/check/source_ownership.toml"
    native_path = "src/agentctl/haskell/native.hs"
    target = "src/later.py"
    cited_target = "src/cited.py"
    document = "version = 1\n"
    for number in range(4):
        parents = "[]" if number == 0 else f"[{number - 1}]"
        document += f"[[phases]]\nnumber = {number}\nprerequisites = {parents}\n"
    for path, owner in (
        (manifest_path, 0),
        (target, 3),
        (native_path, 2),
        (cited_target, 1),
    ):
        document += (
            f'[[artifacts]]\npath = "{path}"\ncapability = "phase-{owner}"\n'
            f"owner = {owner}\nconsumers = [{owner}]\nrequired = true\n"
        )
    entries = (
        Entry(manifest_path, "file", (document.encode(),)),
        Entry(target, "file", (b"source",)),
        Entry(native_path, "file", (b"native",)),
        Entry(cited_target, "file", (b"source",)),
    )
    nodes = (
        "tests/early.py::test_value",
        "haskell:agentctl-core-test/Later/case",
        "tests/source.py::test_value",
        "tests/mutant.py::test_value",
    )
    parsed = tuple(
        phase_text(
            Path(f"phase-{number}-example.md"),
            f"### Sprint {number}.1: Test [Active]\n"
            f"**Validation tests**: `{nodes[number]}`\n",
        )
        for number in range(4)
    )
    assert all(phase is not None for phase in parsed)
    declarations = tuple(phase for phase in parsed if phase is not None)
    record = Mutant(
        "M-later", Operator.REPLACE_LITERAL, target, "before", "after", (nodes[1],), "x"
    )
    owners = ((record.identifier, 3),)
    observed = steps.unavailable_native_scopes(entries, declarations, (record,), owners)
    assert isinstance(observed, Ok), observed
    scopes = dict(observed.value)
    assert not scopes[0], "unavailable later native evidence poisoned earlier phase"
    assert "native observation unavailable" in scopes[1], (
        "unavailable native citation was omitted"
    )
    assert "native observation unavailable" in scopes[2], (
        "unavailable native source consumer was omitted"
    )
    assert "native observation unavailable" in scopes[3], (
        "unavailable native mutant owner was omitted"
    )
    assert isinstance(
        steps.unavailable_native_scopes(entries, declarations, (record,), ()), Err
    ), "ambiguous native absence ownership was accepted"
    assert isinstance(
        steps.unavailable_native_scopes(
            entries, declarations, (record,), ((record.identifier, 2),)
        ),
        Err,
    ), "ambiguous native absence ownership was accepted"
    assert isinstance(
        steps.unavailable_native_scopes(
            entries,
            declarations,
            (replace(record, target=cited_target),),
            ((record.identifier, True),),
        ),
        Err,
    ), "ambiguous native absence ownership was accepted"
    foreign = (*entries, Entry("src/agentctl/haskell/foreign.hs", "file", (b"x",)))
    assert isinstance(
        steps.unavailable_native_scopes(foreign, declarations, (record,), owners), Err
    ), "ambiguous native absence ownership was accepted"

    monkeypatch.setattr(steps, "native_snapshot", lambda *_args: Err("missing"))
    reported = steps.__dict__["_report_native_attribution"](
        tmp_path,
        "current",
        steps.PostRunInputs((record,), owners, declarations, entries),
        declarations,
        (1, 1, 0),
    )
    output = capsys.readouterr().err
    assert reported == 1, "missing native observation was not reported"
    assert "native-attribution: missing" in output, (
        "native absence primary detail was lost"
    )
    assert "native-attribution phase 0:" not in output
    assert "native-attribution phase 1: native observation unavailable" in output
    assert "native-attribution phase 2: native observation unavailable" in output
    assert "native-attribution phase 3: native observation unavailable" in output
    invalid = steps.__dict__["_report_native_attribution"](
        tmp_path,
        "current",
        steps.PostRunInputs((record,), owners, declarations, foreign),
        declarations,
        (1, 1, 0),
    )
    diagnostics = capsys.readouterr().err
    assert invalid == 1
    assert "native-attribution: missing" in diagnostics, (
        "native absence primary detail was lost"
    )
    assert "native absence ownership is incomplete or ambiguous" in diagnostics
    assert "native-attribution phase " not in diagnostics


@pytest.mark.evidence("value")
def test_gate_scopes_captured_toolchain_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The captured gate join preserves earlier phases when toolchain setup fails."""
    manifest_path = "src/agentctl/check/source_ownership.toml"
    target = "src/agentctl/check/toolchain.py"
    prerequisites = "src/agentctl/check/prerequisites.py"
    native_path = "src/agentctl/haskell/native.hs"
    shared_path = "src/shared.py"
    test_paths = tuple(f"tests/test_phase_{number}.py" for number in range(3))
    document = "version = 1\n"
    for number in range(3):
        parents = "[]" if number == 0 else f"[{number - 1}]"
        document += f"[[phases]]\nnumber = {number}\nprerequisites = {parents}\n"
    artifacts = (
        (manifest_path, 0),
        (native_path, 0),
        (shared_path, 0),
        (target, 2),
        (prerequisites, 2),
        *zip(test_paths, range(3), strict=True),
    )
    for path, owner in artifacts:
        consumers = "[0, 2]" if path == shared_path else f"[{owner}]"
        document += (
            f'[[artifacts]]\npath = "{path}"\ncapability = "scope-{owner}"\n'
            f"owner = {owner}\nconsumers = {consumers}\nrequired = true\n"
        )
    entries = (
        Entry(manifest_path, "file", (document.encode(),)),
        *(Entry(path, "file", (b"source",)) for path, _owner in artifacts[1:]),
    )
    nodes = tuple(path + "::test_case" for path in test_paths)
    declarations = tuple(
        phase_text(
            Path(f"phase-{number}-example.md"),
            f"### Sprint {number}.1: Test [Active]\n"
            f"**Validation tests**: `{node}`\n## Remaining Work\n",
        )
        for number, node in enumerate(nodes)
    )
    assert all(phase is not None for phase in declarations)
    phases = tuple(phase for phase in declarations if phase is not None)
    python = RunEvidence(
        "current", frozenset(nodes), frozenset(nodes), frozenset(nodes), (), ()
    )
    native_node = "haskell:agentctl-core-test/Example/control"
    native = RunEvidence(
        "current",
        frozenset({native_node}),
        frozenset({native_node}),
        frozenset({native_node}),
        (),
        (),
    )
    snapshot = NativeSnapshot(native, ((native_node, native_path),), entries)
    tools = ToolOutcome(
        1,
        Ok(
            LegEvidence(
                "current", (("toolchain-ensure", 1), ("cabal-test", 0), ("pytest", 0))
            )
        ),
        Ok(ToolSubsteps("current", (("pytest", (0, 0, 0)),))),
        Ok(python),
        Ok(snapshot),
        killers=Ok(mutant_report.Report("current", (), "captured")),
    )
    captured = ProvisionalCapture(
        Ok(entries),
        Ok(phases),
        tools,
        ((), ()),
        Ok(tuple(OracleScope(number, ()) for number in range(3))),
        "current",
        ("toolchain-ensure", "cabal-test", "pytest"),
        (("pytest", 3),),
        ("P9: prerequisite unavailable",),
    )
    result = captured_phase_observations(captured)
    assert isinstance(result, Ok), result
    assert "toolchain-ensure failed" not in result.value[0].failures, (
        "later toolchain failure poisoned earlier gate observation"
    )
    assert "toolchain-ensure failed" not in result.value[1].failures
    assert "toolchain-ensure failed" in result.value[2].failures, (
        "owned toolchain failure was lost in gate handoff"
    )
    readiness = "later readiness: P9: prerequisite unavailable"
    assert readiness not in result.value[0].failures, (
        "later readiness poisoned earlier gate observation"
    )
    assert readiness in result.value[2].failures, (
        "owned readiness failure was lost in gate handoff"
    )
    _assert_parent_tool_failures(captured, phases, result.value, monkeypatch)
    damaged = captured_phase_observations(
        replace(captured, validation=("source census mismatch",))
    )
    assert isinstance(damaged, Ok), damaged
    assert all(
        "unattributed validation: source census mismatch" in item.failures
        for item in damaged.value
    ), "unattributed validation damage did not reach all phases"
    ready_tools = replace(
        tools,
        code=0,
        evidence=Ok(
            LegEvidence(
                "current", (("toolchain-ensure", 0), ("cabal-test", 0), ("pytest", 0))
            )
        ),
    )
    readiness_only = captured_phase_observations(replace(captured, tools=ready_tools))
    assert isinstance(readiness_only, Ok), readiness_only
    assert readiness in readiness_only.value[2].failures, (
        "readiness-only failure was lost"
    )
    assert "toolchain-ensure failed" not in readiness_only.value[2].failures
    missing_capture, missing_results = _assert_missing_native_capture(
        captured, tools, entries, document, native_path
    )
    _assert_source_validation_scopes(captured, target)
    _assert_ruff_validation_scopes(captured, target, tmp_path)
    _assert_parent_cited_checks(captured, phases, result.value, nodes[2])
    _assert_localized_native_finalizers(
        missing_capture, phases, missing_results, tmp_path, monkeypatch
    )


def _assert_parent_cited_checks(
    captured: ProvisionalCapture,
    phases: tuple[Phase, ...],
    results: tuple[PhaseResult, ...],
    failed_node: str,
) -> None:
    """Rejoin a cited failure from the same captured source declarations."""
    python = captured.tools.pytest
    assert isinstance(python, Ok)
    failed = replace(python.value, passed=python.value.passed - {failed_node})
    changed = replace(captured, tools=replace(captured.tools, pytest=Ok(failed)))
    retained = (
        *results[:2],
        replace(results[2], failures=results[2].failures | {failed_node}),
    )
    assert steps.verify_captured_cited_checks(
        (phases, changed), "current", retained
    ) == Ok(None)
    assert isinstance(
        steps.verify_captured_cited_checks((phases, changed), "current", results), Err
    ), "parent accepted omitted cited check failure"


def _assert_missing_native_capture(
    captured: ProvisionalCapture,
    tools: ToolOutcome,
    entries: tuple[Entry, ...],
    document: str,
    native_path: str,
) -> tuple[ProvisionalCapture, tuple[PhaseResult, ...]]:
    """Keep an absent failed native run local without manufacturing evidence."""
    old_native = (
        f'path = "{native_path}"\ncapability = "scope-0"\nowner = 0\nconsumers = [0]\n'
    )
    later_native = (
        f'path = "{native_path}"\ncapability = "scope-2"\nowner = 2\nconsumers = [2]\n'
    )
    assert document.count(old_native) == 1
    missing_entries = (
        replace(
            entries[0], payloads=(document.replace(old_native, later_native).encode(),)
        ),
        *entries[1:],
    )
    missing_tools = replace(
        tools,
        evidence=Ok(
            LegEvidence(
                "current", (("toolchain-ensure", 1), ("cabal-test", 1), ("pytest", 0))
            )
        ),
        native=Err("native suite unavailable"),
    )
    missing_capture = replace(captured, census=Ok(missing_entries), tools=missing_tools)
    assert steps.__dict__["_gate_native_manifest"](missing_capture) == Ok(None), (
        "failed later native command suppressed provisional phases"
    )
    partial = captured_phase_observations(missing_capture)
    assert isinstance(partial, Ok), (
        "failed later native command suppressed provisional phases: " + str(partial)
    )
    assert partial.value[0].failures == frozenset({"unverified-run"}), (
        "missing later native evidence poisoned earlier phase"
    )
    assert "native observation unavailable" in partial.value[2].failures, (
        "missing native evidence was not attributed"
    )
    assert all("unverified-run" in item.failures for item in partial.value), (
        "missing native evidence was promoted to a verdict"
    )
    assert isinstance(captured.phases, Ok)
    assert steps.verify_phase_native_failures(
        missing_capture, captured.phases.value, partial.value
    ) == Ok(None)
    assert steps.verify_phase_tool_failures(
        missing_capture, captured.phases.value, partial.value
    ) == Ok(None)
    forged = (
        *partial.value[:2],
        replace(
            partial.value[2],
            failures=partial.value[2].failures - {"native observation unavailable"},
        ),
    )
    assert isinstance(
        steps.verify_phase_native_failures(
            missing_capture, captured.phases.value, forged
        ),
        Err,
    ), "parent accepted omitted native absence"
    fabricated_capture = replace(
        missing_capture, tools=replace(missing_tools, evidence=tools.evidence)
    )
    fabricated = captured_phase_observations(fabricated_capture)
    assert isinstance(fabricated, Err), (
        "successful native command without evidence accepted"
    )
    assert isinstance(captured.tools.pytest, Ok)
    assert isinstance(
        steps.provisional_tool_failures(
            fabricated_capture, captured.tools.pytest.value, None
        ),
        Err,
    ), "successful native tool observation accepted without evidence"
    assert isinstance(
        steps.__dict__["_gate_native_manifest"](fabricated_capture), Err
    ), "successful native collection accepted without evidence"
    return missing_capture, partial.value


def _assert_localized_native_finalizers(
    captured: ProvisionalCapture,
    phases: tuple[Phase, ...],
    observed: tuple[PhaseResult, ...],
    directory: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Check localized finalizer damage against source consumers."""
    statuses = tuple(
        (name, int(name == "native-observation")) for name in steps.FINALIZER_NAMES
    )
    localized = steps.provisional_finalizer_failures(
        Ok(observed), statuses, localized_native=True
    )
    assert isinstance(localized, Ok)
    label = "native finalizer failed: native-observation"
    assert label not in localized.value[0].failures, (
        "native finalizer poisoned earlier phase"
    )
    assert (
        "shared finalizer failed: native-observation" not in localized.value[0].failures
    ), "native finalizer poisoned earlier phase"
    assert label in localized.value[2].failures, "native finalizer scope was omitted"
    assert all("unverified-run" in item.failures for item in localized.value)
    with monkeypatch.context() as patch:
        patch.setattr(
            steps, "_parent_collection_capture", lambda *_args: Ok((phases, captured))
        )
        for name in (
            "verify_python_commands_handoff",
            "verify_pytest_handoff",
            "verify_killer_handoff",
            "collection_capture_sealed",
        ):
            patch.setattr(steps, name, lambda *_args: Ok(None))
        final = steps.record_finalizers(directory, "current", statuses[:-1])
        record = steps.record_provisional_phases(directory, "current", localized)
        assert isinstance(final, Ok)
        assert isinstance(record, Ok)
        output = (
            steps.provisional_seal("current", record.value)
            + "\n"
            + steps.finalizer_seal(final.value)
            + "\n"
        )
        assert steps.verify_provisional_finalizers(directory, "current", output) == Ok(
            None
        )
        forged = (
            *localized.value[:2],
            replace(localized.value[2], failures=localized.value[2].failures - {label}),
        )
        finalizers = LegEvidence("current", statuses[:-1])
        assert isinstance(
            steps.__dict__["_verify_localized_native_finalizers"](
                directory, "current", output, finalizers, forged
            ),
            Err,
        ), "parent accepted missing native finalizer failure"
        _assert_localized_native_refusals(
            directory, output, finalizers, localized.value, forged
        )
        falsely_earlier = (
            replace(localized.value[0], failures=localized.value[0].failures | {label}),
            *localized.value[1:],
        )
        assert isinstance(
            steps.__dict__["_verify_localized_native_finalizers"](
                directory, "current", output, finalizers, falsely_earlier
            ),
            Err,
        ), "parent accepted broadened native finalizer scope"
        damaged = replace(
            finalizers,
            outcomes=tuple(
                (name, 1 if name == "write-guard" else code)
                for name, code in finalizers.outcomes
            ),
        )
        assert isinstance(
            steps.__dict__["_verify_localized_native_finalizers"](
                directory, "current", output, damaged, localized.value
            ),
            Err,
        ), "parent accepted a hidden shared finalizer failure"


def _assert_localized_native_refusals(
    directory: Path,
    output: str,
    finalizers: LegEvidence,
    observed: tuple[PhaseResult, ...],
    forged: tuple[PhaseResult, ...],
) -> None:
    """Refuse missing native evidence through both parent entry points."""
    missing_native = (
        *observed[:2],
        replace(
            observed[2],
            failures=observed[2].failures - {"native observation unavailable"},
        ),
    )
    assert isinstance(
        steps.__dict__["_verify_localized_native_finalizers"](
            directory, "current", output, finalizers, missing_native
        ),
        Err,
    ), "parent accepted missing native absence failure"
    forged_dir = directory / "forged-finalizer"
    forged_dir.mkdir()
    final = steps.record_finalizers(forged_dir, "current", finalizers.outcomes)
    record = steps.record_provisional_phases(forged_dir, "current", Ok(forged))
    assert isinstance(final, Ok)
    assert isinstance(record, Ok)
    forged_output = (
        steps.provisional_seal("current", record.value)
        + "\n"
        + steps.finalizer_seal(final.value)
        + "\n"
    )
    assert isinstance(
        steps.verify_provisional_finalizers(forged_dir, "current", forged_output), Err
    ), "parent accepted missing native finalizer failure"


@pytest.mark.evidence("value")
def test_toolchain_failure_uses_captured_owner() -> None:
    """A later-owned readiness failure stays local while unknown tools remain shared."""
    manifest_path = "src/agentctl/check/source_ownership.toml"
    target = "src/agentctl/check/toolchain.py"
    document = (
        "version = 1\n"
        "[[phases]]\nnumber = 0\nprerequisites = []\n"
        "[[phases]]\nnumber = 1\nprerequisites = [0]\n"
        "[[phases]]\nnumber = 2\nprerequisites = [1]\n"
        f'[[artifacts]]\npath = "{manifest_path}"\ncapability = "governance"\n'
        "owner = 0\nconsumers = [0]\nrequired = true\n"
        f'[[artifacts]]\npath = "{target}"\ncapability = "toolchain"\n'
        "owner = 2\nconsumers = [2]\nrequired = true\n"
    )
    entries = (
        Entry(manifest_path, "file", (document.encode(),)),
        Entry(target, "file", (b"toolchain source",)),
    )
    phases = (
        PhaseInputs(0, frozenset({manifest_path}), frozenset({"a"}), frozenset()),
        PhaseInputs(1, frozenset({manifest_path}), frozenset({"b"}), frozenset({0})),
        PhaseInputs(2, frozenset({target}), frozenset({"c"}), frozenset({1})),
    )
    failures = frozenset(
        {
            "unattributed tool failure: toolchain-ensure",
            "unattributed tool failure: ruff-check",
        }
    )
    result = provisional_owned_tool_failures(entries, phases, failures)
    assert isinstance(result, Ok)
    assert result.value.shared == frozenset(
        {"unattributed tool failure: ruff-check"}
    ), "owned tool failure remained shared"
    assert not result.value.scoped[0][1], "later tool failure poisoned earlier phase"
    assert not result.value.scoped[1][1], "later tool failure poisoned earlier phase"
    assert result.value.scoped[2][1] == frozenset({"toolchain-ensure failed"})
    wrong = document.replace("owner = 2\nconsumers = [2]", "owner = 1\nconsumers = [1]")
    forged = (Entry(manifest_path, "file", (wrong.encode(),)), entries[1])
    assert isinstance(provisional_owned_tool_failures(forged, phases, failures), Err), (
        "reassigned toolchain owner was accepted"
    )
    assert isinstance(
        provisional_owned_tool_failures(entries[:1], phases, failures), Err
    )
    assert isinstance(
        provisional_owned_tool_failures(entries, phases, failures, readiness=("P9",)),
        Err,
    ), "readiness without prerequisite ownership was accepted"


@pytest.mark.evidence("value")
def test_binary_identity_failure_uses_captured_owner() -> None:
    """A later binary check stays local only with complete captured ownership."""
    manifest_path = "src/agentctl/check/source_ownership.toml"
    paths = ("src/agentctl/check/identity.py", "src/agentctl/bootstrap/binary.py")
    document = (
        "version = 1\n"
        "[[phases]]\nnumber = 0\nprerequisites = []\n"
        "[[phases]]\nnumber = 1\nprerequisites = [0]\n"
        "[[phases]]\nnumber = 2\nprerequisites = [1]\n"
        f'[[artifacts]]\npath = "{manifest_path}"\ncapability = "governance"\n'
        "owner = 0\nconsumers = [0]\nrequired = true\n"
        + "".join(
            f'[[artifacts]]\npath = "{path}"\ncapability = "bootstrap"\n'
            "owner = 2\nconsumers = [2]\nrequired = true\n"
            for path in paths
        )
    )
    entries = (
        Entry(manifest_path, "file", (document.encode(),)),
        *(Entry(path, "file", (b"source",)) for path in paths),
    )
    phases = (
        PhaseInputs(0, frozenset({manifest_path}), frozenset({"a"}), frozenset()),
        PhaseInputs(1, frozenset({manifest_path}), frozenset({"b"}), frozenset({0})),
        PhaseInputs(2, frozenset(paths), frozenset({"c"}), frozenset({1})),
    )
    failures = frozenset({steps.IDENTITY_FAILURE, "unrelated shared failure"})
    original = steps.ToolFailureAttribution(
        failures, tuple((phase.number, frozenset()) for phase in phases)
    )
    result = steps.provisional_identity_tool_failures(entries, phases, original)
    assert isinstance(result, Ok)
    assert result.value.shared == frozenset({"unrelated shared failure"}), (
        "binary identity failure remained shared"
    )
    assert not result.value.scoped[0][1], "later binary failure blocked earlier phase"
    assert not result.value.scoped[1][1]
    assert result.value.scoped[2][1] == frozenset({"binary-identity failed"}), (
        "binary identity failure lost its owner"
    )
    forged = document.replace(
        "owner = 2\nconsumers = [2]", "owner = 1\nconsumers = [1]"
    )
    reassigned = (replace(entries[0], payloads=(forged.encode(),)), *entries[1:])
    assert isinstance(
        steps.provisional_identity_tool_failures(reassigned, phases, original), Err
    ), "reassigned binary identity owner was accepted"
    assert isinstance(
        steps.provisional_identity_tool_failures(entries[:-1], phases, original), Err
    ), "missing binary identity source was accepted"
    assert isinstance(
        steps.provisional_identity_tool_failures(
            entries, phases, replace(original, scoped=original.scoped[:-1])
        ),
        Err,
    ), "incomplete binary identity scopes were accepted"
    unrelated = replace(original, shared=frozenset({"unrelated shared failure"}))
    assert steps.provisional_identity_tool_failures((), phases, unrelated) == Ok(
        unrelated
    ), "absent later identity source blocked an unrelated observation"


@pytest.mark.evidence("value")
def test_binary_identity_failure_reaches_provisional_work() -> None:
    """The captured work join applies the later binary ownership observation."""
    manifest_path = "src/agentctl/check/source_ownership.toml"
    subjects = ("src/agentctl/check/identity.py", "src/agentctl/bootstrap/binary.py")
    tests = tuple(f"tests/test_phase_{number}.py" for number in range(3))
    document = "version = 1\n" + "".join(
        f"[[phases]]\nnumber = {number}\n"
        f"prerequisites = {[] if number == 0 else [number - 1]}\n"
        for number in range(3)
    )
    artifacts = (
        (manifest_path, 0),
        *((path, 2) for path in subjects),
        *((path, number) for number, path in enumerate(tests)),
    )
    document += "".join(
        f'[[artifacts]]\npath = "{path}"\ncapability = "phase-{owner}"\n'
        f"owner = {owner}\nconsumers = [{owner}]\nrequired = true\n"
        for path, owner in artifacts
    )
    entries = (
        Entry(manifest_path, "file", (document.encode(),)),
        *(Entry(path, "file", (b"source",)) for path, _owner in artifacts[1:]),
    )
    parsed = tuple(
        phase_text(
            Path(f"phase-{number}-example.md"),
            f"### Sprint {number}.1: Test [Active]\n"
            f"**Validation tests**: `{path}::test_one`\n",
        )
        for number, path in enumerate(tests)
    )
    assert all(phase is not None for phase in parsed)
    declarations = tuple(phase for phase in parsed if phase is not None)
    result = steps.provisional_work_and_tools(
        entries, declarations, frozenset({steps.IDENTITY_FAILURE}), ()
    )
    assert isinstance(result, Ok), result
    attribution = result.value[1]
    assert not attribution.shared, (
        "binary identity failure remained shared in work join"
    )
    assert not attribution.scoped[0][1]
    assert "binary-identity failed" in attribution.scoped[2][1], (
        "binary identity scope was omitted from work join"
    )


@pytest.mark.evidence("value")
def test_provisional_tools_preserve_shared_failures() -> None:
    """Tool, coverage, nonce and native status observations remain visible."""
    node = "tests/test_example.py::test_value"
    test_run = RunEvidence(
        "current", frozenset({node}), frozenset({node}), frozenset({node}), (), ()
    )
    native_node = "haskell:agentctl-core-test/Example/control"
    native_run = RunEvidence(
        "current",
        frozenset({native_node}),
        frozenset({native_node}),
        frozenset({native_node}),
        (),
        (),
    )
    native = NativeSnapshot(native_run, (), ())
    tools = ToolOutcome(
        0,
        Ok(
            LegEvidence(
                "current", (("ruff-check", 0), ("cabal-test", 0), ("pytest", 0))
            )
        ),
        Ok(ToolSubsteps("current", (("ruff-check", (0,)), ("pytest", (0, 0, 0))))),
    )
    captured = ProvisionalCapture(
        Err("not needed"),
        Err("not needed"),
        tools,
        None,
        Err("not needed"),
        "current",
        ("ruff-check", "cabal-test", "pytest"),
        (("ruff-check", 1), ("pytest", 3)),
    )
    assert provisional_tool_failures(captured, test_run, native) == Ok(frozenset())
    incomplete = replace(
        captured,
        substep_schedule=(("ruff-check", 2), ("pytest", 3)),
    )
    assert provisional_tool_failures(incomplete, test_run, native) == Err(
        "captured tool substeps disagree with tool outcomes"
    ), "incomplete successful tool substeps were accepted"
    failed = replace(
        tools,
        code=1,
        evidence=Ok(
            LegEvidence(
                "current", (("ruff-check", 1), ("cabal-test", 0), ("pytest", 0))
            )
        ),
        substeps=Ok(
            ToolSubsteps("current", (("ruff-check", (1,)), ("pytest", (0, 0, 0))))
        ),
    )
    observed = provisional_tool_failures(
        replace(captured, tools=failed), test_run, native
    )
    assert isinstance(observed, Ok)
    assert "unattributed tool failure: ruff-check" in observed.value, (
        "unattributed tool failure was omitted"
    )
    stopped_early = provisional_tool_failures(
        replace(incomplete, tools=failed), test_run, native
    )
    assert isinstance(stopped_early, Ok)
    assert "unattributed tool failure: ruff-check" in stopped_early.value
    interrupted = replace(
        captured,
        tools=replace(
            failed,
            substeps=Ok(
                ToolSubsteps("current", (("ruff-check", (1, 0)), ("pytest", (0, 0, 0))))
            ),
        ),
        substep_schedule=(("ruff-check", 3), ("pytest", 3)),
        after_failure=frozenset({"ruff-check"}),
    )
    assert provisional_tool_failures(interrupted, test_run, native) == Err(
        "captured tool substeps disagree with tool outcomes"
    ), "unfinished successful tool follow-up was accepted"
    completed = replace(
        interrupted,
        tools=replace(
            failed,
            substeps=Ok(
                ToolSubsteps(
                    "current", (("ruff-check", (1, 0, 0)), ("pytest", (0, 0, 0)))
                )
            ),
        ),
    )
    complete_result = provisional_tool_failures(completed, test_run, native)
    assert isinstance(complete_result, Ok)
    assert "unattributed tool failure: ruff-check" in complete_result.value
    assert isinstance(
        provisional_tool_failures(
            replace(completed, after_failure=frozenset()), test_run, native
        ),
        Err,
    ), "tool ran follow-ups after an unpermitted primary failure"
    after_failed_followup = replace(
        captured,
        tools=replace(
            failed,
            substeps=Ok(
                ToolSubsteps(
                    "current", (("ruff-check", (0, 1, 0)), ("pytest", (0, 0, 0)))
                )
            ),
        ),
        substep_schedule=(("ruff-check", 3), ("pytest", 3)),
    )
    assert isinstance(
        provisional_tool_failures(after_failed_followup, test_run, native), Err
    ), "tool ran a command after a failed follow-up"
    assert isinstance(
        provisional_tool_failures(
            replace(captured, after_failure=frozenset({"unknown"})), test_run, native
        ),
        Err,
    )
    coverage = replace(
        tools,
        code=1,
        evidence=Ok(
            LegEvidence(
                "current", (("ruff-check", 0), ("cabal-test", 0), ("pytest", 1))
            )
        ),
        substeps=Ok(
            ToolSubsteps("current", (("ruff-check", (0,)), ("pytest", (0, 0, 1))))
        ),
    )
    observed_coverage = provisional_tool_failures(
        replace(captured, tools=coverage), test_run, native
    )
    assert isinstance(observed_coverage, Ok)
    assert "coverage report failed" in observed_coverage.value, (
        "coverage failure was omitted"
    )
    assert isinstance(
        provisional_tool_failures(replace(captured, nonce="stale"), test_run, native),
        Err,
    )
    assert isinstance(
        provisional_tool_failures(
            replace(captured, schedule=("pytest",)), test_run, native
        ),
        Err,
    )
    invalid_native = replace(
        native, manifest=replace(native_run, forbidden=("native-command-failed",))
    )
    assert isinstance(
        provisional_tool_failures(captured, test_run, invalid_native), Err
    )


@pytest.mark.evidence("value")
def test_captured_shared_case_consumers() -> None:
    """The diagnostic includes mutant killers as well as captured phase citations."""
    module = "tests/test_shared.py"
    mutant_module = "tests/governance/test_mutants.py"
    early, late = module + "::test_early", module + "::test_late"
    mutant_node = mutant_module + "::test_corpus[M-shared]"
    text = MANIFEST + (
        f'[[artifacts]]\npath = "{module}"\ncapability = "shared-tests"\n'
        "owner = 0\nconsumers = [0, 1]\nrequired = true\n"
        f'[[artifacts]]\npath = "{mutant_module}"\ncapability = "mutants"\n'
        "owner = 0\nconsumers = [0]\nrequired = true\n"
    )
    entries = (
        Entry("src/agentctl/check/source_ownership.toml", "file", (text.encode(),)),
        Entry(module, "file", (b"source",)),
        Entry(mutant_module, "file", (b"mutant harness",)),
    )
    declarations = tuple(
        phase_text(
            Path(f"phase-{number}-example.md"),
            f"### Sprint {number}.1: Test [Active]\n"
            f"**Validation tests**: `{node}`\n## Remaining Work\n",
        )
        for number, node in ((0, early), (1, late))
    )
    captured = tuple(phase for phase in declarations if phase is not None)
    nodes = frozenset({early, late, mutant_node})
    observed = RunEvidence("current", nodes, nodes, nodes - {late}, (), ())
    record = Mutant(
        "M-shared", Operator.DELETE, "src/control.py", "x", "", (late,), "x"
    )
    result = _value(
        collection_observations(
            entries,
            captured,
            observed,
            "current",
            CollectionClaims(((record.identifier, 0),), (record,)),
        )
    )
    assert "failed test: " + late in result[0][1], "mutant killer consumer was omitted"
    assert "failed test: " + late in result[1][1]
    local_nodes = frozenset({early, late})
    local_observed = RunEvidence(
        "current", local_nodes, local_nodes, frozenset({early}), (), ()
    )
    local = _value(
        collection_observations(
            entries, captured, local_observed, "current", CollectionClaims((), ())
        )
    )
    assert not local[0][1], "later case failure poisoned earlier phase"


@pytest.mark.evidence("value")
def test_mutant_claim_manifest_structure() -> None:
    """Reject duplicate, malformed and ambiguous ownership records."""
    assert _value(parse_mutant_claims(CLAIMS)) == (
        MutantOwnership(
            "M-test-example",
            0,
            (("tests/test_subject.py::test_control", "tests/test_subject.py"),),
        ),
    )
    for malformed in (
        "",
        CLAIMS.replace("version = 1", "version = true"),
        CLAIMS.replace("owner = 0", "owner = true"),
        CLAIMS.replace("owner = 0", "owner = -1"),
        CLAIMS.replace("M-test-example", "not-a-mutant"),
        CLAIMS.replace('path = "tests/test_subject.py"', 'path = ""'),
        CLAIMS + CLAIMS.split("version = 1\n", 1)[1],
        CLAIMS + "extra = 1\n",
    ):
        assert _is_error(parse_mutant_claims(malformed))


@pytest.mark.evidence("real")
def test_phase0_mutant_claims_match_corpus(root: Path) -> None:
    """The partial declarations name exactly the Phase 0 corpus and killers."""
    claims = _value(
        parse_mutant_claims(
            (root / "src/agentctl/check/phase0_mutant_ownership.toml").read_text(
                encoding="utf-8"
            )
        )
    )
    document = tomllib.loads(
        (root / "tests/mutants/phase.toml").read_text(encoding="utf-8")
    )
    records = document["mutant"]
    expected_legacy = {
        "M-evidence-nonce-unchecked",
        "M-evidence-missing-mutant-allowed",
        "M-evidence-missing-citation-allowed",
        "M-evidence-path-unchecked",
        "M-evidence-digest-unchecked",
        "M-evidence-empty-target-accepted",
        "M-evidence-lane-refusal-off",
        "M-evidence-printed-after-failure",
    }
    assert {claim.identifier for claim in claims} == {
        record["id"] for record in records
    } | expected_legacy
    by_id = {claim.identifier: claim for claim in claims}
    for record in records:
        claim = by_id[record["id"]]
        assert claim.owner == 0
        assert tuple(node for node, _path in claim.killer_sources) == tuple(
            record["killers"]
        )
        assert all(
            node.split("::", 1)[0] == path for node, path in claim.killer_sources
        )
    entries = _value(source_census(root))
    mutants = _value(corpus(root))
    assert phase0_claim_problems(root, entries, mutants) == ()
    assert phase0_claim_problems(root, entries, ())


@pytest.mark.evidence("real")
def test_legacy_mutant_claim_fragments_match_corpus(root: Path) -> None:
    """Explicit capability fragments retain each record and its killer paths."""
    manifest = _value(read_manifest(root / "src/agentctl/check/source_ownership.toml"))
    owners = {item.path: item.owner for item in manifest.artifacts}
    groups = (
        (
            "governance",
            0,
            (
                "gate",
                "integrity",
                "source",
                "governance_identity",
                "governance_native_controls",
                "governance_packaging",
                "governance_preconditions",
                "governance_style",
                "governance_toolchain",
            ),
        ),
        (
            "bootstrap",
            2,
            (
                "ghcup",
                "prerequisites",
                "bootstrap_startup",
                "bootstrap_plan",
                "build_cache",
                "style_legs",
                "toolchain",
                "haskell_build",
                "passthrough",
            ),
        ),
        ("native", 3, ("capture_phase3", "launch_phase3")),
        (
            "linux",
            4,
            ("linux_clean_recipe", "capture_phase4", "mux", "sessions_phase4"),
        ),
        (
            "agent",
            5,
            (
                "argv",
                "auth",
                "preflight",
                "names",
                "launch",
                "mux_phase5",
                "passthrough_phase5",
            ),
        ),
        ("sessions", 6, ("adopt", "classify_status", "sessions")),
        ("observation", 7, ("classify", "observation_status", "capture")),
        ("supervisor", 8, ("supervisor", "backoff", "machine")),
        ("psmux", 10, ("mux_phase10",)),
    )
    for capability, owner, files in groups:
        claim_file = root / f"src/agentctl/check/{capability}_mutant_ownership.toml"
        claims = _value(parse_mutant_claims(claim_file.read_text(encoding="utf-8")))
        records = tuple(
            record
            for name in files
            for record in tomllib.loads(
                (root / f"tests/mutants/{name}.toml").read_text(encoding="utf-8")
            )["mutant"]
        )
        assert {claim.identifier for claim in claims} == {
            record["id"] for record in records
        }
        by_id = {claim.identifier: claim for claim in claims}
        for record in records:
            claim = by_id[record["id"]]
            assert claim.owner == owner == owners[record["target"]]
            assert tuple(node for node, _path in claim.killer_sources) == tuple(
                record["killers"]
            )
            assert all((root / path).is_file() for _node, path in claim.killer_sources)
            assert all(
                node.startswith("haskell:") or node.split("::", 1)[0] == path
                for node, path in claim.killer_sources
            )
    native = frozenset(
        node
        for capability, _owner, _files in groups
        for claim in _value(
            parse_mutant_claims(
                (
                    root / f"src/agentctl/check/{capability}_mutant_ownership.toml"
                ).read_text(encoding="utf-8")
            )
        )
        for node, _path in claim.killer_sources
        if node.startswith("haskell:")
    )
    assert fragment_claim_problems(
        _value(source_census(root)), _value(corpus(root))
    ) == tuple(
        sorted(
            "validators: mutant claims: unverified killer identity: " + node
            for node in native
        )
    )


@pytest.mark.evidence("real")
def test_census_phase_declarations(root: Path, tmp_path: Path) -> None:
    """Captured plan parsing agrees with the live tree and rejects ambiguity."""
    captured = _value(source_census(root))
    assert census_phases(root, captured) == Ok(phases(root))
    path = "DEVELOPMENT_PLAN/phase-0-control.md"
    text = (
        "### Sprint 0.1: Control [Active]\n\n"
        "**Mutants**: `M-control-one`\n\n## Remaining Work\n"
    )
    live = tmp_path / path
    live.parent.mkdir()
    live.write_text(text.replace("[Active]", "[Done]"), encoding="utf-8")
    entry = Entry(path, "file", (text.encode(),))
    first = _value(census_phases(tmp_path, (entry,)))
    assert first[0].sprints[0].tag == "Active", "captured phase declaration was ignored"
    for newline in ("\r\n", "\r"):
        converted = Entry(path, "file", (text.replace("\n", newline).encode(),))
        assert census_phases(tmp_path, (converted,)) == Ok(first)
    altered = Entry(path, "file", (text.replace("[Active]", "[Done]").encode(),))
    assert _value(census_phases(tmp_path, (altered,)))[0].sprints[0].tag == "Done"
    assert isinstance(census_phases(tmp_path, (entry, altered)), Err)
    assert isinstance(census_phases(tmp_path, (Entry(path, "file", (b"\xff",)),)), Err)


@pytest.mark.evidence("value")
def test_native_failure_joins_captured_owners_and_mutants() -> None:
    """Join a later native mutant killer without invalidating the earlier phase."""
    path = "src/agentctl/haskell/test/Later.hs"
    node = "haskell:agentctl-core-test/Later/control"
    document = (
        MANIFEST
        + '[[artifacts]]\npath = "'
        + path
        + '"\ncapability = "governance"\n'
        + "owner = 0\nconsumers = [0, 1]\nrequired = true\n"
    )
    entries = (
        Entry("src/agentctl/check/source_ownership.toml", "file", (document.encode(),)),
        Entry(path, "file", (b"source",)),
    )
    names = frozenset({node})
    run = RunEvidence(
        "fresh", names, names, frozenset(), ("failed: " + node,), ((node, "value"),)
    )
    snapshot = NativeSnapshot(run, ((node, path),), entries)
    declarations = tuple(
        Phase(number, Path(f"phase-{number}-test.md"), "", ()) for number in (0, 1)
    )
    record = Mutant(
        "M-later-control", Operator.DELETE, "src/future.py", "x", "", (node,), "reason"
    )
    result = native_failure_observations(
        snapshot, "fresh", declarations, (record,), ((record.identifier, 1),)
    )
    assert result == Ok(
        ((0, frozenset()), (1, frozenset({"failed native case: " + node})))
    ), "native mutant consumer was lost"
    tools = ToolOutcome(1, Err("unused"), Err("unused"), native=Ok(snapshot))
    captured = ProvisionalCapture(
        Ok(entries),
        Ok(declarations),
        tools,
        ((record,), ((record.identifier, 1),)),
        Err("unused"),
        "fresh",
        (),
        (),
    )
    observations = (
        steps.phase_reports.PhaseResult(0, "a" * 64, frozenset({"unverified-run"})),
        steps.phase_reports.PhaseResult(
            1, "b" * 64, frozenset({"unverified-run", "failed native case: " + node})
        ),
    )
    assert steps.verify_phase_native_failures(
        captured, declarations, observations
    ) == Ok(None)
    forged = (
        observations[0],
        replace(observations[1], failures=frozenset({"unverified-run"})),
    )
    assert isinstance(
        steps.verify_phase_native_failures(captured, declarations, forged), Err
    ), "parent accepted hidden native failure"
    assert isinstance(
        steps.verify_phase_native_failures(
            replace(captured, tools=replace(tools, native=None)),
            declarations,
            observations,
        ),
        Err,
    ), "parent accepted missing native observation"
    assert isinstance(
        native_failure_observations(snapshot, "fresh", declarations, (record,), ()), Err
    )
    assert isinstance(
        native_failure_observations(
            snapshot, "fresh", declarations, (record,), ((record.identifier, 2),)
        ),
        Err,
    )


@pytest.mark.evidence("value")
def test_census_closure_policy() -> None:
    """Closure policy requires both unambiguous captured files."""
    standard = Entry(
        "DEVELOPMENT_PLAN/development_plan_standards.md",
        "file",
        (b"first\r\nsecond\r",),
    )
    overview = Entry("DEVELOPMENT_PLAN/00-overview.md", "file", (b"overview\r\n",))
    result = census_policy((standard, overview), (("M-example-control", 0),))
    assert isinstance(result, Ok)
    assert result.value.standards == "first\nsecond\n"
    assert result.value.overview == "overview\n"
    assert isinstance(census_policy((standard,), None), Err)
    assert isinstance(census_policy((standard, overview, overview), None), Err)


@pytest.mark.evidence("real")
def test_source_manifest_declared_paths_exist(root: Path) -> None:
    """Current required declarations resolve in the real checkout census."""
    manifest = _value(read_manifest(root / "src/agentctl/check/source_ownership.toml"))
    assert manifest.phases[0] == OwnershipPhase(0, frozenset())
    entries = _value(source_census(root))
    present = frozenset(entry.path for entry in entries)
    assert all(item.path in present for item in manifest.artifacts if item.required)
    by_path = {item.path: item for item in manifest.artifacts}
    for phase in phases(root):
        artifact = by_path[phase.path.relative_to(root).as_posix()]
        assert artifact.owner == phase.number
        assert phase.number in artifact.consumers
    for document in (root / "documents").rglob("*.md"):
        owner = re.search(
            r"\(.*?/phase-(\d+)-[^/)]+\.md\)",
            field(document.read_text(encoding="utf-8"), "Owning phase"),
        )
        assert owner is not None
        artifact = by_path[document.relative_to(root).as_posix()]
        assert artifact.owner == int(owner[1])
        assert artifact.owner in artifact.consumers


@pytest.mark.evidence("real")
def test_live_and_release_citation_consumers(root: Path) -> None:
    """Existing live and release citations are inputs to their named phases."""
    manifest = _value(read_manifest(root / "src/agentctl/check/source_ownership.toml"))
    citations = (
        (12, "tests/live/test_live_launch.py::test_live_launch"),
        (12, "tests/live/test_live_classification.py::test_live_screen_classes"),
        (12, "tests/e2e/test_fresh_bootstrap.py::test_ghcup_digest_matches_pin"),
        (
            14,
            "tests/governance/test_release_receipts.py::test_foreign_receipt_input_identity",
        ),
        (1, "tests/integration/test_guard.py::test_containment_detects_owned_leak"),
    )
    assert consumer_problems(manifest, citations) == ()
    module = "tests/live/test_live_supervisor.py"
    node = module + "::test_live_supervisor_never_sends"
    assert consumer_problems(manifest, ((12, node),)) == ()
    artifact = next(item for item in manifest.artifacts if item.path == module)
    supervisor_phase, acceptance_phase = 8, 12
    assert artifact.owner == supervisor_phase
    assert acceptance_phase in artifact.consumers
    empty = CollectionObservation(
        collected=frozenset(),
        executed=frozenset(),
        passed=frozenset(),
        failed_modules=frozenset(),
        nonce_matches=True,
        forbidden=frozenset(),
    )
    failures = _value(
        collection_failures(
            (CollectionScope(12, frozenset({node}), frozenset({module})),), empty
        )
    )
    assert "missing or failed: " + node in failures[0][1]


@pytest.mark.evidence("real")
def test_source_manifest_runtime_owners(root: Path) -> None:
    """Representative runtime paths retain the component inventory's owners."""
    manifest = _value(read_manifest(root / "src/agentctl/check/source_ownership.toml"))
    by_path = {item.path: item.owner for item in manifest.artifacts}
    base = "src/agentctl/haskell/src/AgentCtl/"
    for path, owner in (
        ("src/agentctl/process.py", 1),
        ("src/agentctl/result.py", 1),
        ("src/agentctl/check/preconditions.py", 0),
        ("src/agentctl/check/validator/source.py", 0),
        ("src/agentctl/check/haskell.py", 2),
        ("src/agentctl/bootstrap/build.py", 2),
        ("src/agentctl/cli.py", 2),
        ("src/agentctl/haskell/agentctl-core.cabal", 2),
        ("src/agentctl/haskell/test/MuxTests.hs", 3),
        ("src/agentctl/haskell/test/AgentTests.hs", 5),
        ("tests/live/test_live_launch.py", 5),
        ("tests/live/test_live_classification.py", 7),
        ("tests/live/test_live_supervision.py", 8),
        ("tests/lanes/clean-host.Dockerfile", 4),
        ("tests/e2e/test_fresh_bootstrap.py", 2),
        ("tests/integration/test_haskell_mutations.py", 2),
        ("tests/integration/test_eval_executable.py", 2),
        ("tests/integration/test_python_startup.py", 2),
        ("tests/unit/test_clean_host_recipe.py", 4),
        ("tests/e2e/test_status_screen.py", 6),
        ("tests/e2e/test_scripted_fake.py", 8),
        ("tests/e2e/test_watch_commands.py", 8),
        ("src/agentctl/haskell/app/SupervisorFixture.hs", 8),
        ("src/agentctl/haskell/src/AgentCtl/Mux/Psmux.hs", 10),
        ("src/agentctl/haskell/test/SupervisorTests.hs", 8),
        ("tests/integration/test_static_legs.py", 0),
        ("tests/conftest.py", 0),
        ("tests/harness/host.py", 0),
        ("tests/harness/passthrough.py", 2),
        ("tests/harness/agents.py", 5),
        ("tests/harness/sessions.py", 6),
        ("tests/harness/supervisor.py", 8),
        ("tests/unit/test_lane.py", 0),
        ("tests/unit/test_toolchain.py", 2),
        ("tests/integration/test_fake_agent.py", 4),
        ("tests/integration/test_agent_real.py", 5),
        ("tests/unit/test_sessions_values.py", 4),
        ("tests/fixtures/static_negative/ruff/valid.py.txt", 0),
        ("tests/fixtures/static_negative/ready_constructed.hs.txt", 5),
        ("tests/governance/test_source_guards.py", 0),
        ("tests/integration/test_ghcup.py", 2),
        ("tests/integration/test_mux_real.py", 4),
        ("tests/e2e/test_launch.py", 3),
        ("tests/e2e/test_sessions.py", 4),
        ("tests/integration/test_capture_real.py", 3),
        ("tests/e2e/test_supervisor_run.py", 8),
        ("tests/fixtures/docs_negative/plan_fileset/case.toml", 0),
        ("tests/fixtures/bootstrap/ghcup_actor.py.txt", 2),
        ("tests/fixtures/haskell/cache_actor.py.txt", 2),
        ("tests/fixtures/screens/claude/IdlePrompt/documented.txt", 7),
        ("tests/fixtures/terminal/utf8-and-wrap.txt", 7),
        ("tests/oracles/check_legs.toml", 0),
        ("tests/oracles/execution_evidence.toml", 0),
        ("tests/oracles/forbidden_surfaces.toml", 1),
        ("tests/oracles/bootstrap_plan.toml", 2),
        ("tests/oracles/prerequisites.toml", 2),
        ("tests/oracles/pins.toml", 2),
        ("tests/oracles/mux_commands.toml", 4),
        ("tests/oracles/launch_argv.toml", 5),
        ("tests/oracles/session_ownership.toml", 6),
        ("tests/oracles/recovery_transitions.toml", 7),
        ("tests/oracles/backoff.toml", 8),
        (base + "Protocol.hs", 2),
        (base + "Process.hs", 3),
        (base + "Mux/Tmux.hs", 4),
        (base + "Agent.hs", 5),
        (base + "Launch.hs", 5),
        (base + "Sessions.hs", 6),
        (base + "Observe/Capture.hs", 7),
        (base + "Supervisor/Runtime.hs", 8),
        (base + "Mux/Psmux.hs", 10),
    ):
        assert by_path[path] == owner


@pytest.mark.evidence("real")
def test_single_owner_mutant_files_match_targets(root: Path) -> None:
    """Each declared single-owner corpus file targets that owner's sources."""
    manifest = _value(read_manifest(root / "src/agentctl/check/source_ownership.toml"))
    owners = {item.path: item.owner for item in manifest.artifacts}
    for name in (
        "adopt.toml",
        "argv.toml",
        "auth.toml",
        "backoff.toml",
        "classify.toml",
        "evidence.toml",
        "bootstrap_startup.toml",
        "bootstrap_plan.toml",
        "governance_preconditions.toml",
        "build_cache.toml",
        "governance_identity.toml",
        "governance_native_controls.toml",
        "governance_style.toml",
        "style_legs.toml",
        "toolchain.toml",
        "governance_toolchain.toml",
        "linux_clean_recipe.toml",
        "haskell_build.toml",
        "governance_packaging.toml",
        "classify_status.toml",
        "observation_status.toml",
        "capture.toml",
        "capture_phase3.toml",
        "capture_phase4.toml",
        "launch.toml",
        "launch_phase3.toml",
        "mux.toml",
        "mux_phase5.toml",
        "mux_phase10.toml",
        "passthrough.toml",
        "passthrough_phase5.toml",
        "sessions.toml",
        "sessions_phase4.toml",
        "ghcup.toml",
        "gate.toml",
        "integrity.toml",
        "machine.toml",
        "names.toml",
        "preflight.toml",
        "prerequisites.toml",
        "source.toml",
        "supervisor.toml",
    ):
        path = "tests/mutants/" + name
        records = tomllib.loads((root / path).read_text(encoding="utf-8"))["mutant"]
        assert records
        assert all(owners[record["target"]] == owners[path] for record in records)


@pytest.mark.evidence("real")
def test_source_manifest_reports_unowned_checkout(tmp_path: Path) -> None:
    """An incomplete real checkout reports its unowned and missing paths."""
    manifest = tmp_path / "src/agentctl/check/source_ownership.toml"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(MANIFEST, encoding="utf-8")
    (tmp_path / "extra").write_text("unowned", encoding="utf-8")
    entries = _value(source_census(tmp_path))
    problems = source_ownership_problems(entries)
    assert len(problems) == 1
    assert "unowned source artifact: extra" in problems[0]
    assert "required source artifact missing: src/shared.py" in problems[0]
    manifest.write_text("invalid = [", encoding="utf-8")
    assert source_ownership_problems(entries) == problems
    refreshed = _value(source_census(tmp_path))
    assert source_ownership_problems(refreshed) != problems


@pytest.mark.evidence("real")
def test_ownership_manifest_real_census(tmp_path: Path) -> None:
    """A real new file fails the join until explicitly declared."""
    source = tmp_path / "source"
    (source / "src").mkdir(parents=True)
    (source / "src/shared.py").write_text("shared", encoding="utf-8")
    path = tmp_path / "manifest.toml"
    assert _is_error(read_manifest(path))
    path.write_text(MANIFEST, encoding="utf-8")
    manifest = _value(read_manifest(path))
    first = _value(source_census(source))
    assert not _is_error(bind_census(manifest, first))
    (source / "src/empty").mkdir()
    assert _is_error(bind_census(manifest, _value(source_census(source))))
    (source / "src/empty").rmdir()
    (source / "src/unowned.py").write_text("unowned", encoding="utf-8")
    second = _value(source_census(source))
    assert _is_error(bind_census(manifest, second))


@pytest.mark.evidence("value")
def test_ownership_snapshot_binds_kind_and_payload() -> None:
    """Entry changes affect inputs and malformed or missing entries fail closed."""
    manifest = _value(parse_manifest(MANIFEST))
    directory = Entry("src", "directory", (b"",))
    source = Entry("src/shared.py", "file", (b"content",))
    first = _value(bind_census(manifest, (directory, source)))
    assert first == _value(bind_census(manifest, (source, directory)))
    link = Entry("src/shared.py", "symlink", (b"link", b"content"))
    assert first.sources != _value(bind_census(manifest, (directory, link))).sources
    changed = Entry("src/shared.py", "symlink", (b"other", b"content"))
    assert (
        _value(bind_census(manifest, (directory, link))).sources
        != _value(bind_census(manifest, (directory, changed))).sources
    )
    assert _is_error(bind_census(manifest, (directory,)))
    assert _is_error(bind_census(manifest, (directory, source, source)))
    assert _is_error(bind_census(manifest, (directory, Entry(source.path, "file", ()))))


@pytest.mark.evidence("value")
def test_missing_phase_inputs_remain_scoped() -> None:
    """Absent later inputs fail their consumers without erasing earlier identities."""
    first, later, shared = "src/first.py", "src/later.py", "src/shared.py"
    phases = (OwnershipPhase(0, frozenset()), OwnershipPhase(1, frozenset({0})))
    manifest = OwnershipManifest(
        phases,
        (
            ArtifactOwnership(
                first, 0, frozenset({0}), required=True, capability="early"
            ),
            ArtifactOwnership(
                later, 1, frozenset({1}), required=True, capability="later"
            ),
            ArtifactOwnership(
                shared, 0, frozenset({0, 1}), required=True, capability="shared"
            ),
        ),
    )
    checks = ((0, frozenset({"early"})), (1, frozenset({"late"})))
    entries = tuple(
        Entry(path, "file", (b"content",)) for path in (first, later, shared)
    )
    missing = tuple(entry for entry in entries if entry.path != later)
    complete_work = _value(scoped_phase_work(manifest, entries, checks))
    partial = _value(scoped_phase_work(manifest, missing, checks))
    early, late = "tests/test_early.py::test_case", "tests/test_late.py::test_case"
    scopes = (
        CollectionScope(0, frozenset({early}), frozenset({"tests/test_early.py"})),
        CollectionScope(1, frozenset({late}), frozenset({"tests/test_late.py"})),
    )
    nodes = frozenset({early, late})
    observed = CollectionObservation(
        nodes, nodes, nodes, frozenset(), nonce_matches=True, forbidden=frozenset()
    )

    def results(subject: ScopedPhaseWork) -> tuple[PhaseResult, ...]:
        calculated = calculate_observed(
            subject.work.phases,
            subject.work.sources,
            frozenset({"early", "late"}),
            frozenset(),
            (scopes, observed, (), subject.missing),
        )
        assert isinstance(calculated, Ok)
        return calculated.value

    before, after = results(complete_work), results(partial)
    without_diagnostics = calculate_observed(
        partial.work.phases,
        partial.work.sources,
        frozenset({"early", "late"}),
        frozenset(),
        (scopes, observed),
    )
    assert isinstance(without_diagnostics, Ok)
    assert "missing-input:" + later in without_diagnostics.value[1].failures, (
        "missing input disappeared without diagnostic join"
    )
    assert not before[0].failures
    assert not before[1].failures
    assert after[0].identity == before[0].identity, (
        "later missing input poisoned earlier phase"
    )
    assert not after[0].failures, "later missing input poisoned earlier phase"
    assert after[1].identity != before[1].identity
    empty_file = _value(
        scoped_phase_work(manifest, (*missing, Entry(later, "file", (b"",))), checks)
    )
    assert results(empty_file)[1].identity != after[1].identity, (
        "missing source collided with a present empty file"
    )
    assert "required source artifact missing: " + later in after[1].failures, (
        "missing source was accepted"
    )
    shared_missing = _value(scoped_phase_work(manifest, entries[:2], checks))
    assert all(result.failures for result in results(shared_missing)), (
        "shared missing source was localized"
    )
    assert _is_error(
        scoped_phase_work(
            manifest, (*missing, Entry("src/unknown.py", "file", (b"x",))), checks
        )
    )
    assert _is_error(scoped_phase_work(manifest, (*missing, missing[0]), checks))


@pytest.mark.evidence("value")
def test_captured_scoped_source_inputs() -> None:
    """The gate derives missing input observations from the guarded manifest."""
    manifest_path = "src/agentctl/check/source_ownership.toml"
    manifest = MANIFEST.replace("required = false", "required = true") + (
        f'[[artifacts]]\npath = "{manifest_path}"\ncapability = "governance"\n'
        "owner = 0\nconsumers = [0, 1]\nrequired = true\n"
    )
    entries = (
        Entry(manifest_path, "file", (manifest.encode(),)),
        Entry("src", "directory", (b"",)),
        Entry("src/shared.py", "file", (b"source",)),
    )
    declarations = tuple(
        phase_text(
            Path(f"phase-{number}-example.md"),
            f"### Sprint {number}.1: Test [Active]\n"
            f"**Validation tests**: `tests/test_{number}.py::test_case`\n"
            "## Remaining Work\n",
        )
        for number in (0, 1)
    )
    phases = tuple(phase for phase in declarations if phase is not None)
    observed = _value(scoped_source_inputs(entries, phases))
    assert observed.missing[0] == (0, frozenset())
    assert observed.missing[1] == (
        1,
        frozenset({"required source artifact missing: src/future.py"}),
    ), "captured missing input was not attributed"


@pytest.mark.evidence("value")
def test_phase_work_binds_census_to_current_identity() -> None:
    """Observed changes affect consuming phases and declared prerequisites."""
    manifest = _value(parse_manifest(MANIFEST))
    directory = Entry("src", "directory", (b"",))
    shared = Entry("src/shared.py", "file", (b"shared",))
    future = Entry("src/future.py", "file", (b"before",))
    checks = ((0, frozenset({"early"})), (1, frozenset({"late"})))

    def results(entries: tuple[Entry, ...]) -> tuple[str, ...]:
        work = _value(phase_work(manifest, entries, checks))
        calculated = calculate(
            work.phases, work.sources, frozenset({"early", "late"}), frozenset()
        )
        match calculated:
            case Ok(values):
                return tuple(result.identity for result in values)
            case Err(error):
                pytest.fail(error)

    original = results((directory, shared, future))
    later = results((directory, shared, Entry(future.path, "file", (b"after",))))
    assert original[0] == later[0]
    assert original[1] != later[1]
    changed = results((directory, Entry(shared.path, "file", (b"changed",)), future))
    assert all(a != b for a, b in zip(original, changed, strict=True))
    assert _is_error(phase_work(manifest, (directory, shared), checks[:1]))
    assert _is_error(phase_work(manifest, (directory, shared), (*checks, checks[0])))
    assert _is_error(
        phase_work(manifest, (directory, shared), ((0, frozenset()), checks[1]))
    )


@pytest.mark.evidence("value")
def test_gate_complete_mutant_ownership(tmp_path: Path) -> None:
    """Gate inputs require a complete census and target-bound claims."""
    directory = tmp_path / "src/agentctl/check"
    directory.mkdir(parents=True)
    fragment = "src/agentctl/check/phase0_mutant_ownership.toml"
    target = "src/subject.py"
    test = "tests/test_subject.py"
    node = test + "::test_control"
    manifest_path = "src/agentctl/check/source_ownership.toml"
    paths = (manifest_path, fragment, target, test)
    manifest = "version = 1\n[[phases]]\nnumber = 0\nprerequisites = []\n"
    for path in paths:
        manifest += (
            f'[[artifacts]]\npath = "{path}"\ncapability = "control"\n'
            "owner = 0\nconsumers = [0]\nrequired = true\n"
        )
    (directory / "source_ownership.toml").write_text(manifest, encoding="utf-8")
    claim = (
        'version = 1\n[[claims]]\nidentifier = "M-test-example"\nowner = 0\n'
        f'killer_sources = [{{node = "{node}", path = "{test}"}}]\n'
    )
    (tmp_path / fragment).write_text(claim, encoding="utf-8")
    entries = (
        Entry(manifest_path, "file", (manifest.encode(),)),
        Entry(fragment, "file", (claim.encode(),)),
        Entry(target, "file", (b"source",)),
        Entry(test, "file", (b"test",)),
    )
    mutant = Mutant(
        "M-test-example", Operator.DELETE, target, "x", "", (node,), "reason"
    )
    assert complete_mutant_owners(entries, (mutant,)) == Ok(((mutant.identifier, 0),))
    extra = replace(mutant, identifier="M-test-other")
    assert scoped_mutant_ownership(entries, (mutant, extra)) == Ok(
        (MutantScope(0, ("missing mutant claim: M-test-other",)),)
    )
    assert ownership_observations((MutantScope(0, ("missing claim",)),)) == (
        "ownership-observation phase 0: missing claim (not a verdict)",
    )
    assert ownership_observations((MutantScope(0, ()),)) == ()
    assert isinstance(complete_mutant_owners(entries, (mutant, extra)), Err)
    optional = "src/agentctl/check/future_mutant_ownership.toml"
    optional_row = (
        f'[[artifacts]]\npath = "{optional}"\ncapability = "control"\n'
        "owner = 0\nconsumers = [0]\nrequired = false\n"
    )
    with_optional = (
        Entry(manifest_path, "file", ((manifest + optional_row).encode(),)),
        *entries[1:],
    )
    assert complete_mutant_owners(with_optional, (mutant,)) == Ok(
        ((mutant.identifier, 0),)
    ), "absent optional claim fragment blocked current ownership"
    (directory / "source_ownership.toml").write_text(
        manifest + optional_row, encoding="utf-8"
    )
    assert fragment_claim_problems(with_optional, (mutant,)) == ()
    assert isinstance(
        complete_mutant_owners(
            (*with_optional, Entry(optional, "file", (b"invalid = [",))), (mutant,)
        ),
        Err,
    )
    (tmp_path / optional).write_text("invalid = [", encoding="utf-8")
    assert fragment_claim_problems(
        (*with_optional, Entry(optional, "file", (b"invalid = [",))),
        (mutant,),
    )
    assert isinstance(complete_mutant_owners(entries[:-1], (mutant,)), Err)
    assert isinstance(complete_mutant_owners(entries, (mutant, mutant)), Err)
    (tmp_path / fragment).write_text(
        claim.replace("owner = 0", "owner = 1"), encoding="utf-8"
    )
    assert complete_mutant_owners(entries, (mutant,)) == Ok(((mutant.identifier, 0),))
    assert fragment_claim_problems(entries, (mutant,)) == ()
    altered = (
        entries[0],
        Entry(fragment, "file", (claim.replace("owner = 0", "owner = 1").encode(),)),
        *entries[2:],
    )
    assert isinstance(complete_mutant_owners(altered, (mutant,)), Err)


@pytest.mark.evidence("value")
def test_mutant_ownership_binds_target_and_killer() -> None:
    """Explicit claims cannot reassign a target or omit its killer source."""
    target = "src/subject.py"
    test = "tests/test_subject.py"
    node = test + "::test_control"
    manifest = OwnershipManifest(
        (OwnershipPhase(0, frozenset()), OwnershipPhase(1, frozenset({0}))),
        (
            ArtifactOwnership(
                target, 0, frozenset({0, 1}), required=True, capability="subject"
            ),
            ArtifactOwnership(
                test, 0, frozenset({0, 1}), required=True, capability="tests"
            ),
        ),
    )
    entries = (Entry(target, "file", (b"source",)), Entry(test, "file", (b"test",)))
    mutant = Mutant(
        "M-test-example", Operator.DELETE, target, "x", "", (node,), "reason"
    )
    claim = MutantOwnership(mutant.identifier, 0, ((node, test),))
    assert partial_claim_problems(manifest, entries, (mutant,), (claim,)) == ()
    assert "unowned killer source: " + test in partial_claim_problems(
        replace(manifest, artifacts=manifest.artifacts[:1]),
        entries,
        (mutant,),
        (claim,),
    )
    assert (
        "unverified mutant target owner: " + mutant.identifier
        in partial_claim_problems(
            manifest, entries, (mutant,), (replace(claim, owner=1),)
        )
    ), "partial claim target owner was ignored"
    assert "duplicate mutant claim" in partial_claim_problems(
        manifest, entries, (mutant,), (claim, claim)
    )
    assert bind_mutants(manifest, entries, (mutant,), (claim,)) == Ok(
        ((mutant.identifier, 0),)
    )
    assert check_phase_claims(
        (claim,), (mutant,), frozenset({mutant.identifier}), entries, 0
    ) == Ok(None)
    assert _is_error(
        check_phase_claims(
            (claim,), (mutant,), frozenset({mutant.identifier}), entries, 1
        )
    )
    assert _is_error(check_phase_claims((claim,), (mutant,), frozenset(), entries, 0))
    assert _is_error(
        bind_mutants(manifest, entries, (mutant,), (replace(claim, owner=1),))
    ), "mutant target ownership was reassigned"
    native = "haskell:agentctl-core-test/Example/control"
    assert _is_error(
        bind_mutants(
            manifest,
            entries,
            (replace(mutant, killers=(native,)),),
            (replace(claim, killer_sources=((native, test),)),),
        )
    ), "unverified native killer source was accepted"
    for invalid in (
        (),
        (replace(claim, killer_sources=()),),
        (replace(claim, killer_sources=((node, target),)),),
        (claim, claim),
    ):
        assert _is_error(bind_mutants(manifest, entries, (mutant,), invalid))
    assert _is_error(
        bind_mutants(manifest, entries, (replace(mutant, target="other"),), (claim,))
    )
    assert _is_error(bind_mutants(manifest, entries[:1], (mutant,), (claim,)))
    assert _is_error(
        bind_mutants(
            manifest, entries, (replace(mutant, killers=(node, node)),), (claim,)
        )
    )


@pytest.mark.evidence("value")
def test_captured_native_mutant_ownership(tmp_path: Path) -> None:
    """Captured declarations and observed native locations must agree exactly."""
    manifest_path = "src/agentctl/check/source_ownership.toml"
    fragment = "src/agentctl/check/phase0_mutant_ownership.toml"
    target = "src/subject.py"
    source = "src/agentctl/haskell/test/RecoveryTests.hs"
    node = "haskell:agentctl-core-test/Backoff/grows-to-cap"
    paths = (manifest_path, fragment, target, source)
    text = "version = 1\n[[phases]]\nnumber = 0\nprerequisites = []\n"
    for path in paths:
        text += (
            f'[[artifacts]]\npath = "{path}"\ncapability = "control"\n'
            "owner = 0\nconsumers = [0]\nrequired = true\n"
        )
    claims = (
        'version = 1\n[[claims]]\nidentifier = "M-test-native"\nowner = 0\n'
        f'killer_sources = [{{node = "{node}", path = "{source}"}}]\n'
    )
    entries = (
        Entry(manifest_path, "file", (text.encode(),)),
        Entry(fragment, "file", (claims.encode(),)),
        Entry(target, "file", (b"source",)),
        Entry(source, "file", (b"native",)),
    )
    record = Mutant(
        "M-test-native", Operator.DELETE, target, "x", "", (node,), "reason"
    )
    assert isinstance(complete_mutant_owners(entries, (record,)), Err)
    assert provisional_mutant_owners(entries, (record,)) == Ok(
        ((record.identifier, 0),)
    )
    wrong_source = claims.replace(source, "src/agentctl/haskell/test/Absent.hs")
    invalid_entries = (
        entries[0],
        Entry(fragment, "file", (wrong_source.encode(),)),
        *entries[2:],
    )
    assert isinstance(provisional_mutant_owners(invalid_entries, (record,)), Err), (
        "provisional ownership accepted an absent native source"
    )
    assert observed_native_mutant_owners(entries, (record,), ((node, source),)) == Ok(
        ((record.identifier, 0),)
    )
    assert isinstance(observed_native_mutant_owners(entries, (record,), ()), Err), (
        "missing native source observation was accepted"
    )
    assert isinstance(
        observed_native_mutant_owners(entries[:-1], (record,), ((node, source),)), Err
    )
    (tmp_path / "tasty.xml").write_text(
        '<testsuites tests="1"><testsuite><testcase '
        'classname="agentctl-core-test.Backoff" name="grows-to-cap" />'
        "</testsuite></testsuites>",
        encoding="utf-8",
    )
    (tmp_path / "haskell-manifest.json").write_text(
        json.dumps(
            {
                "nonce": "current",
                "collected": [node],
                "executed": [node],
                "passed": [node],
                "forbidden": [],
                "classes": {node: "value"},
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "haskell-sources.json").write_text(
        json.dumps({"nonce": "current", "sources": [[node, source]]}),
        encoding="utf-8",
    )
    expected = ((record.identifier, 0),)
    assert (
        _native_ownership_observation(tmp_path, "current", entries, (record,), expected)
        == 0
    )
    assert (
        _native_ownership_observation(
            tmp_path, "current", entries, (record,), ((record.identifier, 1),)
        )
        == 1
    ), "different captured owners were accepted"
    assert (
        _native_ownership_observation(tmp_path, "current", entries, (record,), None)
        == 1
    )
    (tmp_path / "haskell-sources.json").unlink()
    assert (
        _native_ownership_observation(tmp_path, "current", entries, (record,), expected)
        == 1
    ), "provisional ownership passed without native observation"


@pytest.mark.evidence("value")
def test_observed_native_mutant_claims_require_exact_source() -> None:
    """Compiled source observations must agree with every native killer claim."""
    target = "src/subject.py"
    python_source = "tests/test_subject.py"
    native_source = "src/agentctl/haskell/test/RecoveryTests.hs"
    other_source = "src/agentctl/haskell/test/OtherTests.hs"
    python_node = python_source + "::test_control"
    native_node = "haskell:agentctl-core-test/Backoff/grows-to-cap"
    artifacts = tuple(
        ArtifactOwnership(path, 0, frozenset({0}), required=True, capability=capability)
        for path, capability in (
            (target, "subject"),
            (python_source, "python-tests"),
            (native_source, "native-tests"),
            (other_source, "native-tests"),
        )
    )
    manifest = OwnershipManifest((OwnershipPhase(0, frozenset()),), artifacts)
    entries = tuple(Entry(item.path, "file", (b"data",)) for item in artifacts)
    record = Mutant(
        "M-test-native",
        Operator.DELETE,
        target,
        "x",
        "",
        (python_node, native_node),
        "reason",
    )
    claim = MutantOwnership(
        record.identifier,
        0,
        ((python_node, python_source), (native_node, native_source)),
    )
    observed = ((native_node, native_source),)
    assert _is_error(bind_mutants(manifest, entries, (record,), (claim,)))
    assert bind_mutants_observed(
        manifest, entries, (record,), (claim,), observed
    ) == Ok(((record.identifier, 0),))
    for invalid in (
        (),
        ((native_node, python_source),),
        ((native_node, other_source),),
        (*observed, *observed),
    ):
        assert _is_error(
            bind_mutants_observed(manifest, entries, (record,), (claim,), invalid)
        ), "unverified native source was accepted"
    assert _is_error(
        bind_mutants_observed(manifest, entries[:-1], (record,), (claim,), observed)
    )
    assert _is_error(
        bind_mutants_observed(
            manifest, entries, (record,), (replace(claim, owner=1),), observed
        )
    )


@pytest.mark.evidence("value")
def test_later_native_mutant_ownership_is_local() -> None:
    """Unverified later native identity cannot invalidate an earlier owner."""
    phases = (OwnershipPhase(0, frozenset()), OwnershipPhase(1, frozenset({0})))
    first, first_test = "src/first.py", "tests/test_first.py"
    later, native_test = "src/later.hs", "src/agentctl/haskell/test/LaterTests.hs"
    artifacts = tuple(
        ArtifactOwnership(
            path, owner, frozenset({owner}), required=True, capability=capability
        )
        for path, owner, capability in (
            (first, 0, "first"),
            (first_test, 0, "first-tests"),
            (later, 1, "later"),
            (native_test, 1, "later-tests"),
        )
    )
    manifest = OwnershipManifest(phases, artifacts)
    entries = tuple(Entry(item.path, "file", (b"content",)) for item in artifacts)
    node = first_test + "::test_first"
    native = "haskell:agentctl-core-test/Later/control"
    records = (
        Mutant("M-first-control", Operator.DELETE, first, "x", "", (node,), "reason"),
        Mutant("M-later-control", Operator.DELETE, later, "x", "", (native,), "reason"),
    )
    claims = (
        MutantOwnership(records[0].identifier, 0, ((node, first_test),)),
        MutantOwnership(records[1].identifier, 1, ((native, native_test),)),
    )
    result = _value(attribute_mutant_claims(manifest, entries, records, claims))
    assert result[0] == MutantScope(0, ()), (
        "later mutant ownership poisoned earlier phase"
    )
    assert result[1].number == 1
    assert result[1].failures
    observed = _value(
        attribute_mutant_claims(
            manifest, entries, records, claims, ((native, native_test),)
        )
    )
    assert observed == (MutantScope(0, ()), MutantScope(1, ())), (
        "observed native source was ignored"
    )
    mismatch = _value(attribute_mutant_claims(manifest, entries, records, claims, ()))
    assert mismatch[0] == MutantScope(0, ())
    assert mismatch[1].failures, "missing native source did not fail its owner"
    assert _is_error(
        attribute_mutant_claims(
            manifest,
            entries,
            records,
            claims,
            ((native, native_test), (native, native_test)),
        )
    ), "ambiguous native source was accepted"
    later_absent = tuple(entry for entry in entries if entry.path != later)
    scoped_absence = _value(
        attribute_mutant_claims(manifest, later_absent, records, claims)
    )
    assert scoped_absence[0] == MutantScope(0, ()), (
        "missing later source poisoned earlier ownership"
    )
    assert "required source artifact missing: " + later in scoped_absence[1].failures
    assert _is_error(bind_mutants(manifest, later_absent, records, claims))
    assert _is_error(
        attribute_mutant_claims(
            manifest,
            (*later_absent, Entry("unknown", "file", (b"x",))),
            records,
            claims,
        )
    )
    missing = _value(attribute_mutant_claims(manifest, entries, records, claims[:1]))
    assert missing[0] == MutantScope(0, ()), (
        "later missing claim poisoned earlier phase"
    )
    assert missing[1] == MutantScope(1, ("missing mutant claim: M-later-control",))
    second_node = "tests/test_second.py::test_second"
    collected = frozenset({node, second_node})
    observation = CollectionObservation(
        collected,
        collected,
        collected,
        frozenset(),
        nonce_matches=True,
        forbidden=frozenset(),
    )
    scopes = (
        CollectionScope(0, frozenset({node}), frozenset({first_test})),
        CollectionScope(
            1, frozenset({second_node}), frozenset({"tests/test_second.py"})
        ),
    )
    phase_inputs = (
        PhaseInputs(0, frozenset({first}), frozenset({"first"}), frozenset()),
        PhaseInputs(1, frozenset({later}), frozenset({"second"}), frozenset({0})),
    )
    assigned = tuple((item.number, frozenset(item.failures)) for item in missing)
    verdicts = _value(
        calculate_observed(
            phase_inputs,
            ((first, b"first"), (later, b"later")),
            frozenset({"first", "second"}),
            frozenset(),
            (scopes, observation, (), assigned),
        )
    )
    assert not verdicts[0].failures
    assert "missing mutant claim: M-later-control" in verdicts[1].failures
    early_missing = _value(
        attribute_mutant_claims(manifest, entries, records, claims[1:])
    )
    assert early_missing[0] == MutantScope(
        0, ("missing mutant claim: M-first-control",)
    )
    assert _is_error(
        attribute_mutant_claims(manifest, entries, records, (*claims, claims[0]))
    )
    assert _is_error(
        attribute_mutant_claims(
            manifest,
            entries,
            (records[0], replace(records[1], target="src/unknown.hs")),
            claims[:1],
        )
    )
    assert _is_error(
        attribute_mutant_claims(
            manifest, entries, records, (claims[0], replace(claims[1], owner=0))
        )
    )


@pytest.mark.evidence("value")
def test_parent_rechecks_source_and_missing_input_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keep later source-policy and missing-input failures on their consumers."""
    manifest_path = "src/agentctl/check/source_ownership.toml"
    late = "src/agentctl/later.py"
    missing = "src/agentctl/missing.py"
    paths = (manifest_path, "tests/test_early.py", "tests/test_late.py", late, missing)
    manifest = (
        "version = 1\n[[phases]]\nnumber = 0\nprerequisites = []\n"
        "[[phases]]\nnumber = 1\nprerequisites = [0]\n"
    )
    for path, owner in zip(paths, (0, 0, 1, 1, 1), strict=True):
        manifest += (
            f'[[artifacts]]\npath = "{path}"\ncapability = "phase-{owner}"\n'
            f"owner = {owner}\nconsumers = [{owner}]\nrequired = true\n"
        )
    entries = (
        Entry(manifest_path, "file", (manifest.encode(),)),
        Entry(paths[1], "file", (b"def test_early(): pass\n",)),
        Entry(paths[2], "file", (b"def test_late(): pass\n",)),
        Entry(late, "file", (b"def broken(:\n",)),
    )
    declarations = tuple(
        phase_text(
            Path(f"phase-{number}-test.md"),
            f"### Sprint {number}.1: Test [Active]\n"
            f"**Validation tests**: `{paths[number + 1]}::test_case`\n"
            "## Remaining Work\n",
        )
        for number in range(2)
    )
    assert all(phase is not None for phase in declarations)
    phases = tuple(phase for phase in declarations if phase is not None)
    failures = frozenset(
        {
            "unverified-run",
            "source validation: src.parse: " + late,
            "required source artifact missing: " + missing,
            "missing-input:" + missing,
        }
    )
    observed = (
        steps.phase_reports.PhaseResult(0, "a" * 64, frozenset({"unverified-run"})),
        steps.phase_reports.PhaseResult(1, "b" * 64, failures),
    )
    source_work = steps.scoped_source_inputs(entries, phases)
    assert isinstance(source_work, Ok), source_work
    assert steps.verify_phase_source_failures(entries, phases, observed) == Ok(None)
    for message in (
        "source validation: src.parse: " + late,
        "required source artifact missing: " + missing,
        "missing-input:" + missing,
    ):
        forged = (observed[0], replace(observed[1], failures=failures - {message}))
        assert isinstance(
            steps.verify_phase_source_failures(entries, phases, forged), Err
        ), "parent accepted hidden source failure"
    _assert_parent_shared_source_failure(entries, phases, observed, late)
    _assert_parent_source_routes(entries, phases, observed, monkeypatch)


def _assert_parent_shared_source_failure(
    entries: tuple[Entry, ...],
    phases: tuple[Phase, ...],
    observed: tuple[steps.phase_reports.PhaseResult, ...],
    late: str,
) -> None:
    """Preserve a census-wide source guard failure on every phase."""
    without_source = tuple(entry for entry in entries if entry.path != late)
    shared = (
        "unattributed validation: validator.non-vacuous: "
        "Python source and tests are required"
    )
    adjusted = (
        replace(observed[0], failures=observed[0].failures | {shared}),
        replace(
            observed[1],
            failures=(observed[1].failures - {"source validation: src.parse: " + late})
            | {
                shared,
                "required source artifact missing: " + late,
                "missing-input:" + late,
            },
        ),
    )
    assert steps.verify_phase_source_failures(without_source, phases, adjusted) == Ok(
        None
    )
    forged = (
        replace(adjusted[0], failures=adjusted[0].failures - {shared}),
        adjusted[1],
    )
    assert isinstance(
        steps.verify_phase_source_failures(without_source, phases, forged), Err
    ), "parent accepted hidden shared source failure"


def _assert_parent_source_routes(
    entries: tuple[Entry, ...],
    declarations: tuple[Phase, ...],
    observed: tuple[steps.phase_reports.PhaseResult, ...],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Require both parent routes to reject omitted source-policy evidence."""
    context = steps.CheckRun(Path("/source"), Path("/run"), "fresh", "Linux")
    finalizers = LegEvidence(
        context.nonce, tuple((name, 0) for name in steps.FINALIZER_NAMES[:-1])
    )
    output = steps.finalizer_seal(finalizers)
    with monkeypatch.context() as patch:
        patch.setattr(steps, "finalizer_observation", lambda *_args: Ok(finalizers))
        patch.setattr(
            steps, "_provisional_values_for_identity", lambda *_args: Ok(observed)
        )
        patch.setattr(steps.ownership, "guarded_census", lambda *_args: Ok(entries))
        patch.setattr(steps, "_parent_bound_census", lambda *_args: Ok(entries))
        patch.setattr(steps, "census_phases", lambda *_args: Ok(declarations))
        for name in (
            "verify_python_commands_handoff",
            "_verify_provisional_census",
            "verify_python_plan_handoff",
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
            "verify_provisional_tools",
            "verify_provisional_validation",
            "verify_provisional_prerequisites",
            "verify_finalizer_handoff",
            "verify_provisional_handoff",
            "verify_provisional_finalizers",
            "verify_killer_handoff",
            "verify_coverage_handoff",
            "verify_ruff_handoff",
            "verify_ruff_format_handoff",
            "retain_handoff_failure",
        ):
            patch.setattr(steps, name, lambda *_args, **_kwargs: Ok(None))
        assert steps.verify_provisional_source(
            context, context.directory, output
        ) == Ok(None)
        patch.setattr(steps, "_parent_bound_census", lambda *_args: Err("changed"))
        assert isinstance(
            steps.verify_provisional_source(context, context.directory, output), Err
        ), "unbound parent source census was accepted"
        patch.setattr(steps, "_parent_bound_census", lambda *_args: Ok(entries))
        forged = (
            observed[0],
            replace(observed[1], failures=frozenset({"unverified-run"})),
        )
        patch.setattr(
            steps, "_provisional_values_for_identity", lambda *_args: Ok(forged)
        )
        assert isinstance(
            steps.verify_provisional_source(context, context.directory, output), Err
        ), "parent accepted hidden source failure"
        assert isinstance(steps.verify_python_handoffs(context, output), Err), (
            "live parent accepted hidden source failure"
        )
        patch.setattr(
            steps, "retain_gate_output", lambda *_args, **_kwargs: Ok(context.directory)
        )
        patch.setattr(
            steps,
            "verify_retained_streams",
            lambda _directory, _streams, _snapshot, prior: prior,
        )
        patch.setattr(
            steps,
            "verify_retained_artifacts",
            lambda _directory, _observed, prior: prior,
        )
        retained = steps.retain_verified_gate_output(
            context, Path("/state"), (output, ""), verify_handoff=True
        )
        assert isinstance(retained, Err), (
            "retained parent accepted hidden source failure"
        )


@pytest.mark.evidence("value")
def test_gate_execution_scopes(tmp_path: Path) -> None:
    """Keep row execution class failures local to their owning phase."""
    case_id = "tests/unit/test_subject.py::test_subject"
    lower = Phase(
        0,
        tmp_path / "phase-0-control.md",
        "**Status**: Done\n## Gate Integrity\n\n"
        "| Requirement | Oracle | Observer | Mutants | Tests |\n"
        "|---|---|---|---|---|\n"
        "| R20 \u2014 known control | `tests/oracles/example.toml` | "
        "value: pure control | "
        "`M-legs-control` | `tests/unit/test_subject.py::test_subject` |\n",
        (),
    )
    upper = replace(
        lower,
        number=1,
        text=lower.text.replace("value: pure control", "observer: independent control"),
    )
    future = replace(
        lower,
        number=2,
        text=lower.text.replace("**Status**: Done", "**Status**: Planned").replace(
            "M-legs-control", "M-legs-future"
        ),
    )
    declarations = (lower, upper, future)
    record = Mutant(
        "M-legs-control",
        Operator.REPLACE_LITERAL,
        "src/subject.py",
        "x",
        "y",
        (case_id,),
        "control",
    )
    python = RunEvidence(
        "current",
        frozenset({case_id}),
        frozenset({case_id}),
        frozenset({case_id}),
        (),
        ((case_id, "value"),),
    )
    native = RunEvidence("current", frozenset(), frozenset(), frozenset(), (), ())
    snapshot = steps.NativeSnapshot(native, (), ())
    captured = steps.ProvisionalCapture(
        Ok(()),
        Ok(declarations),
        steps.ToolOutcome(0, Err("unused"), Err("unused"), native=Ok(snapshot)),
        None,
        Err("unused"),
        "current",
        (),
        (),
    )
    empty = Ok(tuple((phase.number, frozenset()) for phase in declarations))
    expected = (
        (0, frozenset()),
        (1, frozenset({"gate integrity execution: R20"})),
        (2, frozenset()),
    )
    assert (
        steps.closure.execution_scopes(declarations, (record,), python) == expected
    ), "gate row execution was not scoped"
    result = steps.gate_execution_collection(
        empty, captured, declarations, (record,), python
    )
    assert result == Ok(expected), "gate row execution was not joined"
    changed = replace(python, classes=((case_id, "observer"),))
    assert steps.gate_execution_collection(
        empty, captured, declarations, (record,), changed
    ) == Ok(
        (
            (0, frozenset({"gate integrity execution: R20"})),
            (1, frozenset()),
            (2, frozenset()),
        )
    ), "unavailable planned row was applied"
    stale = replace(snapshot, manifest=replace(native, nonce="stale"))
    assert isinstance(
        steps.gate_execution_collection(
            empty,
            replace(captured, tools=replace(captured.tools, native=Ok(stale))),
            declarations,
            (record,),
            python,
        ),
        Err,
    ), "stale gate row execution was accepted"
    overlapping = replace(
        snapshot, manifest=replace(native, collected=frozenset({case_id}))
    )
    assert isinstance(
        steps.gate_execution_collection(
            empty,
            replace(captured, tools=replace(captured.tools, native=Ok(overlapping))),
            declarations,
            (record,),
            python,
        ),
        Err,
    ), "overlapping gate row execution was accepted"


def _assert_gate_execution_in_provisional(
    captured: ProvisionalCapture, phase: Phase, node: str, record: Mutant
) -> None:
    """Carry row failures through the child and independently recheck them."""
    declaration = replace(
        phase,
        text=phase.text + "\n## Gate Integrity\n\n"
        "| Requirement | Oracle | Observer | Mutants | Tests |\n"
        "|---|---|---|---|---|\n"
        "| R20 \u2014 row | `tests/oracles/example.toml` | observer: host | "
        + f"`{record.identifier}` | `{node}` |\n",
    )
    updated = replace(captured, phases=Ok((declaration,)))
    observed = captured_phase_observations(updated)
    assert isinstance(observed, Ok), observed
    failure = "gate integrity execution: R20"
    assert failure in observed.value[0].failures, "child omitted gate execution failure"
    assert steps.verify_phase_collection_failures(
        updated, (declaration,), observed.value
    ) == Ok(None)
    forged = (
        replace(observed.value[0], failures=observed.value[0].failures - {failure}),
    )
    assert isinstance(
        steps.verify_phase_collection_failures(updated, (declaration,), forged), Err
    ), "parent accepted hidden gate execution failure"


@pytest.mark.evidence("value")
def test_integrity_row_variants_remain_scoped(monkeypatch: pytest.MonkeyPatch) -> None:
    """Missing oracle, killer and requirement facts stay on their row owner."""
    captured = _two_phase_undeclared_capture()
    assert isinstance(captured.census, Ok)
    assert isinstance(captured.phases, Ok)
    assert captured.claims is not None
    records, owners = captured.claims
    first, later = captured.phases.value
    policy = census_policy(captured.census.value, owners)
    assert isinstance(policy, Ok)
    applicable = later.text.replace("| none \u2014 planned |", "| `M-later` |", 1)
    variants = (
        (
            applicable.replace(
                "tests/oracles/example.toml", "tests/oracles/missing.toml"
            ),
            "gate integrity missing oracle: tests/oracles/missing.toml",
        ),
        (
            applicable.replace(
                "tests/test_later.py::test_case", "tests/test_other.py::test_case", 1
            ),
            "gate integrity killer citation: M-later",
        ),
        (
            later.text.replace("| R20 \u2014 test |", "| R99 \u2014 test |", 1),
            "gate integrity requirement: R99",
        ),
    )
    for text, failure in variants:
        result = steps.closure.scoped_integrity_failures(
            (first, replace(later, text=text)), records, policy.value
        )
        assert isinstance(result, Ok), result
        assert result.value.phases[0] == (0, frozenset()), (
            "later integrity variant poisoned earlier phase"
        )
        assert failure in result.value.phases[1][1], "integrity row variant was lost"
    sprint = replace(later.sprints[0], tag="Done", text="**Mutants**: `M-missing`\n")
    sprint_result = steps.closure.scoped_integrity_failures(
        (first, replace(later, sprints=(sprint,))), records, policy.value
    )
    assert isinstance(sprint_result, Ok), sprint_result
    assert (
        "gate integrity missing mutant: M-missing" in sprint_result.value.phases[1][1]
    ), "missing completed sprint mutant was lost"
    malformed = replace(later, text=later.text.replace("| Requirement |", "| Bad |", 1))
    assert isinstance(
        steps.closure.scoped_integrity_failures(
            (first, malformed), records, policy.value
        ),
        Err,
    ), "malformed integrity table was scoped"
    with monkeypatch.context() as control:
        control.setattr(
            steps.closure,
            "gate_integrity",
            lambda *_args, **_kwargs: ("plan.gate-integrity: unexplained",),
        )
        unmatched_rejected = isinstance(
            steps.closure.scoped_integrity_failures(
                (first, later), records, policy.value
            ),
            Err,
        )
        assert unmatched_rejected, "unmatched integrity diagnostics were scoped"


@pytest.mark.evidence("value")
def test_later_integrity_row_damage_is_attributed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A later incomplete row does not become an earlier phase failure."""
    captured = _two_phase_undeclared_capture()
    assert isinstance(captured.census, Ok)
    assert isinstance(captured.phases, Ok)
    assert captured.claims is not None
    records, owners = captured.claims
    first, later = captured.phases.value
    changed = replace(
        later,
        text=later.text.replace(
            "| none \u2014 planned |", "| `M-later`, `M-missing` |", 1
        ),
    )
    declarations = (first, changed)
    policy = census_policy(captured.census.value, owners)
    assert isinstance(policy, Ok)
    attributed = steps.closure.scoped_integrity_failures(
        declarations, records, policy.value
    )
    assert isinstance(attributed, Ok), attributed
    assert attributed.value.phases[0] == (0, frozenset()), (
        "later integrity row poisoned earlier phase"
    )
    assert {
        "undeclared corpus mutant: M-later",
        "gate integrity mutant owner: M-missing",
        "gate integrity missing mutant: M-missing",
    } <= attributed.value.phases[1][1], "later integrity row damage was lost"
    assert attributed.value.diagnostics == steps.closure.gate_integrity(
        Path(), declarations, records, mutant_owners=policy.value
    )
    updated = replace(
        captured, phases=Ok(declarations), validation=attributed.value.diagnostics
    )
    observed = captured_phase_observations(updated)
    assert isinstance(observed, Ok), observed
    assert observed.value[0].failures == frozenset({"unverified-run"}), (
        "later integrity diagnostic was globalized"
    )
    missing = "gate integrity missing mutant: M-missing"
    assert missing in observed.value[1].failures, (
        "child omitted scoped integrity damage"
    )
    assert steps.verify_phase_collection_failures(
        updated, declarations, observed.value
    ) == Ok(None)
    forged = (
        observed.value[0],
        replace(observed.value[1], failures=observed.value[1].failures - {missing}),
    )
    assert isinstance(
        steps.verify_phase_collection_failures(updated, declarations, forged), Err
    ), "parent accepted hidden integrity row damage"
    extra = "plan.gate-integrity: unexplained damage"
    damaged = captured_phase_observations(
        replace(updated, validation=(*updated.validation, extra))
    )
    assert isinstance(damaged, Ok)
    assert all(
        "unattributed validation: " + extra in phase.failures for phase in damaged.value
    ), "unexplained integrity diagnostic was localized"
    _assert_parent_scopes_integrity_rows(
        updated, attributed.value.diagnostics, monkeypatch
    )


def _assert_parent_scopes_integrity_rows(
    captured: ProvisionalCapture,
    diagnostics: tuple[str, ...],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Recompute the same scoped static result in the parent validation path."""
    assert isinstance(captured.census, Ok)
    assert isinstance(captured.phases, Ok)
    assert captured.claims is not None
    entries, declarations = captured.census.value, captured.phases.value
    owners = captured.claims[1]
    monkeypatch.setattr(
        steps, "_parent_collection_capture", lambda *_args: Ok((declarations, captured))
    )
    monkeypatch.setattr(steps, "targets", lambda *_args: Ok(("src",)))
    monkeypatch.setattr(steps, "complete_mutant_owners", lambda *_args: Ok(owners))
    monkeypatch.setattr(steps, "python_target_census", lambda *_args: Ok(None))
    for name in (
        "docs",
        "plan",
        "source_ownership_problems",
        "test_consumer_problems",
        "coverage_host_problems",
        "forbidden_surfaces",
        "configuration",
        "phase0_claim_problems",
        "fragment_claim_problems",
    ):
        monkeypatch.setattr(steps, name, lambda *_args: ())
    monkeypatch.setattr(steps.closure, "static", lambda *_args, **_kwargs: diagnostics)
    monkeypatch.setattr(steps, "_parent_bound_census", lambda *_args: Ok(entries))
    context = steps.CheckRun(Path("/source"), Path("/run"), "fresh", "Linux")
    assert _parent_validation_problems(context, context.directory, "") == Ok(()), (
        "parent globalized scoped integrity damage"
    )
    extra = "plan.gate-integrity: unexplained parent damage"
    monkeypatch.setattr(
        steps.closure, "static", lambda *_args, **_kwargs: (*diagnostics, extra)
    )
    shared = _parent_validation_problems(context, context.directory, "")
    assert isinstance(shared, Ok)
    assert extra in shared.value, "parent localized unmatched integrity diagnostics"
    assert all(item in shared.value for item in diagnostics), (
        "parent dropped unmatched integrity diagnostics"
    )


@pytest.mark.evidence("value")
def test_later_undeclared_mutant_does_not_globalize_integrity() -> None:
    """Join a real two-phase capture and independently reject an omitted failure."""
    captured = _two_phase_undeclared_capture()
    observed = captured_phase_observations(captured)
    assert isinstance(observed, Ok), observed
    assert observed.value[0].failures == frozenset({"unverified-run"}), (
        "later undeclared mutant poisoned earlier phase"
    )
    failure = "undeclared corpus mutant: M-later"
    assert failure in observed.value[1].failures
    assert not any(
        item.startswith("unattributed validation: plan.gate-integrity:")
        for phase in observed.value
        for item in phase.failures
    ), "proved undeclared-only aggregate stayed global"
    assert isinstance(captured.phases, Ok)
    assert steps.verify_phase_collection_failures(
        captured, captured.phases.value, observed.value
    ) == Ok(None)
    forged = (
        observed.value[0],
        replace(observed.value[1], failures=observed.value[1].failures - {failure}),
    )
    assert isinstance(
        steps.verify_phase_collection_failures(captured, captured.phases.value, forged),
        Err,
    ), "parent accepted a missing later declaration failure"
    extra = "plan.gate-integrity: unexplained damage"
    damaged = captured_phase_observations(
        replace(captured, validation=(*captured.validation, extra))
    )
    assert isinstance(damaged, Ok)
    assert all(
        "unattributed validation: " + extra in phase.failures for phase in damaged.value
    ), "unexplained integrity damage was hidden"


def _two_phase_undeclared_capture() -> ProvisionalCapture:
    """Build captured source, plan and execution facts for both phase owners."""
    manifest_path = "src/agentctl/check/source_ownership.toml"
    early = "tests/test_early.py::test_case"
    later = "tests/test_later.py::test_case"
    paths = (
        (manifest_path, 0, "[0, 1]"),
        ("DEVELOPMENT_PLAN/development_plan_standards.md", 0, "[0, 1]"),
        ("DEVELOPMENT_PLAN/00-overview.md", 0, "[0, 1]"),
        ("tests/oracles/example.toml", 0, "[0, 1]"),
        ("tests/test_early.py", 0, "[0]"),
        ("tests/test_later.py", 1, "[1]"),
        ("tests/governance/test_mutants.py", 0, "[0, 1]"),
        ("src/native.hs", 0, "[0]"),
        ("src/early.py", 0, "[0]"),
        ("src/later.py", 1, "[1]"),
    )
    manifest = (
        "version = 1\n[[phases]]\nnumber = 0\nprerequisites = []\n"
        "[[phases]]\nnumber = 1\nprerequisites = [0]\n"
        + "".join(
            f'[[artifacts]]\npath = "{path}"\ncapability = "phase-{owner}"\n'
            f"owner = {owner}\nconsumers = {consumers}\nrequired = true\n"
            for path, owner, consumers in paths
        )
    )
    contents = {
        manifest_path: manifest.encode(),
        "DEVELOPMENT_PLAN/development_plan_standards.md": b"standards\n",
        "DEVELOPMENT_PLAN/00-overview.md": (
            b"## Requirements\n\n| ID | Requirement |\n|---|---|\n| R20 | test |\n"
        ),
    }
    entries = tuple(
        Entry(path, "file", (contents.get(path, b"source\n"),))
        for path, _owner, _consumers in paths
    )
    parsed = tuple(
        phase_text(
            Path(f"phase-{number}-example.md"),
            "**Status**: Active\n**Host lane**: linux\n"
            "## Gate Integrity\n\n"
            "| Requirement | Oracle | Observer | Mutants | Tests |\n"
            "|---|---|---|---|---|\n"
            f"| R20 \u2014 test | `tests/oracles/example.toml` | value: case | "
            f"{mutant} | `{node}` |\n\n"
            f"### Sprint {number}.1: Test [Active]\n"
            f"**Mutants**: {mutant}\n**Validation tests**: `{node}`\n"
            "## Remaining Work\n",
        )
        for number, mutant, node in (
            (0, "`M-early`", early),
            (1, "none \u2014 planned", later),
        )
    )
    assert all(phase is not None for phase in parsed)
    declarations = tuple(phase for phase in parsed if phase is not None)
    records = tuple(
        Mutant(identifier, Operator.DELETE, target, "x", "", (node,), "reason")
        for identifier, target, node in (
            ("M-early", "src/early.py", early),
            ("M-later", "src/later.py", later),
        )
    )
    return _two_phase_undeclared_observations(entries, declarations, records)


def _two_phase_undeclared_observations(
    entries: tuple[Entry, ...],
    declarations: tuple[Phase, ...],
    records: tuple[Mutant, ...],
) -> ProvisionalCapture:
    """Bind synthetic execution evidence to the complete captured mutant corpus."""
    owners = (("M-early", 0), ("M-later", 1))
    nodes = frozenset(
        (
            *[record.killers[0] for record in records],
            *[mutant_report.PREFIX + record.identifier + "]" for record in records],
        )
    )
    python = RunEvidence(
        "fresh",
        nodes,
        nodes,
        nodes,
        (),
        tuple((record.killers[0], "value") for record in records),
    )
    native_node = "haskell:agentctl-core-test/Native/case"
    native_nodes = frozenset({native_node})
    native = RunEvidence("fresh", native_nodes, native_nodes, native_nodes, (), ())
    killers = mutant_report.Report(
        "fresh",
        tuple(
            mutant_report.Record(
                record.identifier,
                "",
                (mutant_report.Killer(record.killers[0], "passed", "killed"),),
            )
            for record in records
        ),
        "captured",
    )
    tools = ToolOutcome(
        0,
        Ok(LegEvidence("fresh", (("cabal-test", 0), ("pytest", 0)))),
        Ok(ToolSubsteps("fresh", (("pytest", (0, 0, 0)),))),
        pytest=Ok(python),
        native=Ok(NativeSnapshot(native, ((native_node, "src/native.hs"),), entries)),
        killers=Ok(killers),
    )
    policy = census_policy(entries, owners)
    assert isinstance(policy, Ok)
    validation = steps.closure.gate_integrity(
        Path(), declarations, records, mutant_owners=policy.value
    )
    assert validation == (
        "plan.gate-integrity: undeclared corpus mutant M-later",
        "plan.gate-integrity: declaration or execution join",
    )
    return ProvisionalCapture(
        Ok(entries),
        Ok(declarations),
        tools,
        (records, owners),
        Ok((OracleScope(0, ()), OracleScope(1, ()))),
        "fresh",
        ("cabal-test", "pytest"),
        (("pytest", 3),),
        validation=validation,
    )


@pytest.mark.evidence("value")
def test_undeclared_mutants_remain_on_their_owners() -> None:
    """Later missing declarations do not poison an earlier source owner."""
    parsed = tuple(
        phase_text(
            Path(f"phase-{number}-test.md"),
            f"### Sprint {number}.1: Test [Active]\n"
            + ("**Mutants**: `M-early`\n" if number == 0 else "**Mutants**: none\n")
            + "## Remaining Work\n",
        )
        for number in range(2)
    )
    assert all(phase is not None for phase in parsed)
    declarations = tuple(phase for phase in parsed if phase is not None)
    records = tuple(
        Mutant(identifier, Operator.DELETE, "src/test.py", "x", "", ("case",), "reason")
        for identifier in ("M-early", "M-later")
    )
    owners = (("M-early", 0), ("M-later", 1))
    result = steps.closure.undeclared_mutant_failures(declarations, records, owners)
    assert result == Ok(
        ((0, frozenset()), (1, frozenset({"undeclared corpus mutant: M-later"})))
    ), "later undeclared mutant was not scoped to its owner"
    misplaced = (
        replace(
            declarations[0],
            sprints=(replace(declarations[0].sprints[0], text="**Mutants**: none\n"),),
        ),
        replace(
            declarations[1],
            sprints=(
                replace(declarations[1].sprints[0], text="**Mutants**: `M-early`\n"),
            ),
        ),
    )
    assert steps.closure.undeclared_mutant_failures(misplaced, records, owners) == Ok(
        (
            (0, frozenset({"undeclared corpus mutant: M-early"})),
            (1, frozenset({"undeclared corpus mutant: M-later"})),
        )
    ), "misplaced mutant declaration masked its owner"
    for invalid in (owners[:1], (*owners, owners[0]), (("M-early", 0), ("M-later", 2))):
        assert isinstance(
            steps.closure.undeclared_mutant_failures(declarations, records, invalid),
            Err,
        ), "ambiguous mutant ownership was accepted"


@pytest.mark.evidence("value")
def test_missing_test_consumers_remain_on_their_phases(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Only the exact captured consumer diagnostics may be scoped away."""
    manifest_path = "src/agentctl/check/source_ownership.toml"
    early = "tests/test_early.py::test_case"
    late = "tests/test_later.py::test_case"
    manifest = (
        "version = 1\n[[phases]]\nnumber = 0\nprerequisites = []\n"
        "[[phases]]\nnumber = 1\nprerequisites = [0]\n"
        f'[[artifacts]]\npath = "{manifest_path}"\ncapability = "plan"\n'
        "owner = 0\nconsumers = [0, 1]\nrequired = true\n"
        '[[artifacts]]\npath = "tests/test_early.py"\ncapability = "test"\n'
        "owner = 0\nconsumers = [0]\nrequired = true\n"
        '[[artifacts]]\npath = "src/native.hs"\ncapability = "native-test"\n'
        "owner = 0\nconsumers = [0]\nrequired = true\n"
    )
    entries = (
        Entry(manifest_path, "file", (manifest.encode(),)),
        Entry("tests/test_early.py", "file", (b"def test_case(): pass\n",)),
        Entry("src/native.hs", "file", (b"module Native where\n",)),
    )
    parsed = tuple(
        phase_text(
            Path(f"phase-{number}-test.md"),
            f"### Sprint {number}.1: Test [Active]\n"
            f"**Validation tests**: `{node}`\n## Remaining Work\n",
        )
        for number, node in enumerate((early, late))
    )
    assert all(phase is not None for phase in parsed)
    declarations = tuple(phase for phase in parsed if phase is not None)
    source_manifest = parse_manifest(manifest)
    assert isinstance(source_manifest, Ok)
    scopes = steps.diagnostic_collection_scopes(source_manifest.value, declarations)
    assert isinstance(scopes, Ok)
    assert len(scopes.value[1]) == 1
    assert scopes.value[1][0][0] == 1
    issue = scopes.value[1][0][1]
    diagnostic = "validators: test consumers: " + issue
    problems = (diagnostic, "independent failure")
    assert steps.scoped_ownership_validation(
        problems, Ok(entries), Ok(declarations)
    ) == ("independent failure",), "later test consumer was globalized"
    run = RunEvidence(
        "fresh", frozenset({early}), frozenset({early}), frozenset({early}), (), ()
    )
    observed = collection_observations(entries, declarations, run, "fresh", ())
    assert isinstance(observed, Ok)
    assert issue not in observed.value[0][1]
    assert issue in observed.value[1][1], "missing consumer was hidden from its phase"
    native_case = "haskell:agentctl-core-test/Native/case"
    native_nodes = frozenset({native_case})
    native = RunEvidence("fresh", native_nodes, native_nodes, native_nodes, (), ())
    capture = ProvisionalCapture(
        Ok(entries),
        Ok(declarations),
        ToolOutcome(
            0,
            Err("unused"),
            Err("unused"),
            pytest=Ok(run),
            native=Ok(
                NativeSnapshot(native, ((native_case, "src/native.hs"),), entries)
            ),
        ),
        ((), ()),
        Err("unused"),
        "fresh",
        (),
        (),
    )
    phases = tuple(
        PhaseResult(number, "a" * 64, failures) for number, failures in observed.value
    )
    assert steps.verify_phase_collection_failures(capture, declarations, phases) == Ok(
        None
    )
    forged = (phases[0], replace(phases[1], failures=phases[1].failures - {issue}))
    assert isinstance(
        steps.verify_phase_collection_failures(capture, declarations, forged), Err
    ), "parent accepted hidden test consumer failure"
    for invalid in (
        (diagnostic, diagnostic),
        (diagnostic, "validators: test consumers: unexpected damage"),
        (diagnostic + " changed",),
    ):
        assert (
            steps.scoped_ownership_validation(invalid, Ok(entries), Ok(declarations))
            == invalid
        ), "ambiguous test consumer damage was localized"
    assert (
        steps.scoped_ownership_validation(
            problems, Err("missing census"), Ok(declarations)
        )
        == problems
    )
    captured = ProvisionalCapture(
        Ok(entries),
        Ok(declarations),
        ToolOutcome(0, Err("unused"), Err("unused")),
        ((), ()),
        Err("unused"),
        "fresh",
        (),
        (),
        validation=problems,
    )
    monkeypatch.setattr(
        steps, "_captured_phase_observations", lambda value: Ok(value.validation)
    )
    assert steps.captured_phase_observations(captured) == Ok(("independent failure",))
    monkeypatch.setattr(
        steps, "_parent_collection_capture", lambda *_args: Ok((declarations, captured))
    )
    monkeypatch.setattr(steps, "targets", lambda *_args: Ok(("src",)))
    monkeypatch.setattr(steps, "complete_mutant_owners", lambda *_args: Ok(()))
    monkeypatch.setattr(steps, "census_policy", lambda *_args: Err("policy damage"))
    monkeypatch.setattr(steps, "python_target_census", lambda *_args: Ok(None))
    monkeypatch.setattr(steps, "docs", lambda *_args: ("independent failure",))
    monkeypatch.setattr(steps, "test_consumer_problems", lambda *_args: (diagnostic,))
    for name in (
        "plan",
        "coverage_host_problems",
        "forbidden_surfaces",
        "configuration",
        "phase0_claim_problems",
        "fragment_claim_problems",
    ):
        monkeypatch.setattr(steps, name, lambda *_args: ())
    monkeypatch.setattr(steps.closure, "static", lambda *_args, **_kwargs: ())
    monkeypatch.setattr(steps, "_parent_bound_census", lambda *_args: Ok(entries))
    context = steps.CheckRun(Path("/source"), Path("/run"), "fresh", "Linux")
    assert _parent_validation_problems(context, context.directory, "") == Ok(
        ("independent failure", "validators: closure policy: policy damage")
    ), "parent did not scope test consumer diagnostics"


@pytest.mark.evidence("value")
def test_missing_owned_source_validation_is_scoped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scope missing-only ownership damage while preserving ambiguous damage."""
    manifest_path = "src/agentctl/check/source_ownership.toml"
    paths = (manifest_path, "tests/test_early.py", "tests/test_late.py", "src/later.py")
    manifest = (
        "version = 1\n[[phases]]\nnumber = 0\nprerequisites = []\n"
        "[[phases]]\nnumber = 1\nprerequisites = [0]\n"
    )
    for path, owner in zip(paths, (0, 0, 1, 1), strict=True):
        manifest += (
            f'[[artifacts]]\npath = "{path}"\ncapability = "phase-{owner}"\n'
            f"owner = {owner}\nconsumers = [{owner}]\nrequired = true\n"
        )
    entries = (
        Entry(manifest_path, "file", (manifest.encode(),)),
        Entry(paths[1], "file", (b"def test_case(): pass\n",)),
        Entry(paths[2], "file", (b"def test_case(): pass\n",)),
    )
    parsed = tuple(
        phase_text(
            Path(f"phase-{number}-test.md"),
            f"### Sprint {number}.1: Test [Active]\n"
            f"**Validation tests**: `{paths[number + 1]}::test_case`\n"
            "## Remaining Work\n",
        )
        for number in range(2)
    )
    assert all(phase is not None for phase in parsed)
    declarations = tuple(phase for phase in parsed if phase is not None)
    missing = "required source artifact missing: " + paths[3]
    aggregate = "validators: source ownership: " + missing
    problems = (aggregate, "independent validator failure")
    assert source_ownership_problems(entries) == (aggregate,)
    assert steps.scoped_ownership_validation(
        problems, Ok(entries), Ok(declarations)
    ) == ("independent validator failure",), "owned later source was globalized"
    work = steps.scoped_source_inputs(entries, declarations)
    assert isinstance(work, Ok)
    assert work.value.missing == ((0, frozenset()), (1, frozenset({missing})))
    unknown = (*entries, Entry("src/unowned.py", "file", (b"pass\n",)))
    shared = source_ownership_problems(unknown)
    assert (
        steps.scoped_ownership_validation(shared, Ok(unknown), Ok(declarations))
        == shared
    ), "unowned source was localized"
    assert (
        steps.scoped_ownership_validation(
            problems, Err("unavailable"), Ok(declarations)
        )
        == problems
    )
    duplicate = (aggregate, aggregate)
    assert (
        steps.scoped_ownership_validation(duplicate, Ok(entries), Ok(declarations))
        == duplicate
    ), "ambiguous ownership failure was localized"
    malformed = (aggregate + "; unexpected damage",)
    assert (
        steps.scoped_ownership_validation(malformed, Ok(entries), Ok(declarations))
        == malformed
    )
    captured = ProvisionalCapture(
        Ok(entries),
        Ok(declarations),
        ToolOutcome(0, Err("unused"), Err("unused")),
        None,
        Err("unused"),
        "fresh",
        (),
        (),
        validation=problems,
    )
    monkeypatch.setattr(
        steps, "_captured_phase_observations", lambda value: Ok(value.validation)
    )
    assert steps.captured_phase_observations(captured) == Ok(
        ("independent validator failure",)
    ), "child did not scope missing source validation"
    _assert_parent_scopes_missing_source(entries, declarations, captured, monkeypatch)


def _assert_parent_scopes_missing_source(
    entries: tuple[Entry, ...],
    declarations: tuple[Phase, ...],
    captured: ProvisionalCapture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Recompute the same scoping in the parent without hiding other findings."""
    monkeypatch.setattr(
        steps,
        "_parent_collection_capture",
        lambda *_args: Ok((declarations, replace(captured, claims=((), ())))),
    )
    monkeypatch.setattr(steps, "targets", lambda *_args: Ok(("src",)))
    monkeypatch.setattr(steps, "complete_mutant_owners", lambda *_args: Ok(()))
    monkeypatch.setattr(steps, "census_policy", lambda *_args: Err("policy damage"))
    monkeypatch.setattr(steps, "python_target_census", lambda *_args: Ok(None))
    monkeypatch.setattr(
        steps, "docs", lambda *_args: ("independent validator failure",)
    )
    for name in (
        "plan",
        "test_consumer_problems",
        "coverage_host_problems",
        "forbidden_surfaces",
        "configuration",
        "phase0_claim_problems",
        "fragment_claim_problems",
    ):
        monkeypatch.setattr(steps, name, lambda *_args: ())
    monkeypatch.setattr(steps.closure, "static", lambda *_args, **_kwargs: ())
    monkeypatch.setattr(steps, "_parent_bound_census", lambda *_args: Ok(entries))
    context = steps.CheckRun(Path("/source"), Path("/run"), "fresh", "Linux")
    assert _parent_validation_problems(context, context.directory, "") == Ok(
        ("independent validator failure", "validators: closure policy: policy damage")
    ), "parent did not scope missing source validation"


@pytest.mark.evidence("value")
def test_mutant_ownership_with_later_missing_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify present mutant inputs without inventing a missing later source."""
    manifest_path = "src/agentctl/check/source_ownership.toml"
    fragment = "src/agentctl/check/phase0_mutant_ownership.toml"
    target = "src/subject.py"
    source = "src/agentctl/haskell/test/RecoveryTests.hs"
    missing = "src/later.py"
    node = "haskell:agentctl-core-test/Backoff/grows-to-cap"
    text = (
        "version = 1\n[[phases]]\nnumber = 0\nprerequisites = []\n"
        "[[phases]]\nnumber = 1\nprerequisites = [0]\n"
    )
    for path, owner in (
        (manifest_path, 0),
        (fragment, 0),
        (target, 0),
        (source, 0),
        (missing, 1),
    ):
        text += (
            f'[[artifacts]]\npath = "{path}"\ncapability = "phase-{owner}"\n'
            f"owner = {owner}\nconsumers = [{owner}]\nrequired = true\n"
        )
    claims = (
        'version = 1\n[[claims]]\nidentifier = "M-test-native"\nowner = 0\n'
        f'killer_sources = [{{node = "{node}", path = "{source}"}}]\n'
    )
    entries = (
        Entry(manifest_path, "file", (text.encode(),)),
        Entry(fragment, "file", (claims.encode(),)),
        Entry(target, "file", (b"source",)),
        Entry(source, "file", (b"native",)),
    )
    record = Mutant(
        "M-test-native", Operator.DELETE, target, "x", "", (node,), "reason"
    )
    expected = Ok(((record.identifier, 0),))
    assert isinstance(complete_mutant_owners(entries, (record,)), Err)
    assert provisional_mutant_owners(entries, (record,)) == expected, (
        "missing later source blocked provisional mutant ownership"
    )
    assert (
        observed_native_mutant_owners(entries, (record,), ((node, source),)) == expected
    ), "missing later source blocked observed mutant ownership"
    scopes = scoped_mutant_ownership(entries, (record,), ((node, source),))
    assert isinstance(scopes, Ok)
    assert scopes.value[0].failures == ()
    assert scopes.value[1].failures == ("required source artifact missing: " + missing,)
    assert isinstance(observed_native_mutant_owners(entries, (record,), ()), Err), (
        "missing native source observation was accepted with absent later source"
    )
    assert isinstance(provisional_mutant_owners(entries[:-1], (record,)), Err), (
        "missing native killer source was accepted"
    )
    assert isinstance(
        provisional_mutant_owners((entries[0], entries[1], entries[3]), (record,)), Err
    ), "missing mutant target was accepted"
    unowned = (*entries, Entry("src/unowned.py", "file", (b"x",)))
    assert isinstance(provisional_mutant_owners(unowned, (record,)), Err), (
        "unowned source was accepted during mutant ownership"
    )
    assert isinstance(provisional_mutant_owners(entries, (record, record)), Err), (
        "duplicate mutant ownership was accepted"
    )
    _assert_pure_mutant_ownership_with_missing(entries, record, node, source)
    _assert_parent_mutant_ownership_with_missing(
        entries, record, node, source, monkeypatch
    )


def _assert_pure_mutant_ownership_with_missing(
    entries: tuple[Entry, ...], record: Mutant, native_node: str, native_source: str
) -> None:
    """Apply the same rule when every killer is a present Python test."""
    python_source = "tests/test_subject.py"
    node = python_source + "::test_control"
    revised = (
        replace(
            entries[0],
            payloads=(
                entries[0]
                .payloads[0]
                .replace(native_source.encode(), python_source.encode()),
            ),
        ),
        replace(
            entries[1],
            payloads=(
                entries[1]
                .payloads[0]
                .replace(native_source.encode(), python_source.encode())
                .replace(native_node.encode(), node.encode()),
            ),
        ),
        entries[2],
        Entry(python_source, "file", (b"test",)),
    )
    python_record = replace(record, killers=(node,))
    assert provisional_mutant_owners(revised, (python_record,)) == Ok(
        ((record.identifier, 0),)
    ), "missing later source blocked Python mutant ownership"
    invalid = (*revised[:-1], replace(revised[-1], payloads=()))
    assert isinstance(provisional_mutant_owners(invalid, (python_record,)), Err), (
        "malformed present source was accepted"
    )


def _assert_parent_mutant_ownership_with_missing(
    entries: tuple[Entry, ...],
    record: Mutant,
    node: str,
    source: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Require the parent collection join to use observed native sources."""
    native = RunEvidence(
        "fresh", frozenset({node}), frozenset({node}), frozenset({node}), (), ()
    )
    python = RunEvidence("fresh", frozenset(), frozenset(), frozenset(), (), ())
    snapshot = NativeSnapshot(native, ((node, source),), entries)
    report = mutant_report.Report("fresh", (), "captured")
    monkeypatch.setattr(steps, "_parent_bound_census", lambda *_args: Ok(entries))
    monkeypatch.setattr(steps, "census_phases", lambda *_args: Ok(()))
    monkeypatch.setattr(steps, "census_corpus", lambda *_args: Ok((record,)))
    monkeypatch.setattr(steps, "native_snapshot", lambda *_args: Ok(snapshot))
    monkeypatch.setattr(steps, "pytest_observation", lambda *_args: Ok(python))
    monkeypatch.setattr(steps.mutant_report, "read", lambda *_args: Ok(report))
    context = steps.CheckRun(Path("/source"), Path("/run"), "fresh", "Linux")
    result = _parent_collection_capture(context, context.directory, "")
    assert isinstance(result, Ok), "parent could not bind present mutant inputs"
    assert result.value[1].claims == ((record,), ((record.identifier, 0),))
    monkeypatch.setattr(
        steps, "native_snapshot", lambda *_args: Ok(replace(snapshot, sources=()))
    )
    assert isinstance(
        _parent_collection_capture(context, context.directory, ""), Err
    ), "parent accepted unobserved native mutant ownership"


@pytest.mark.evidence("value")
def test_scoped_mutant_mapping_retains_owned_damage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Owner mapping cannot discard missing claims, targets or native identity."""
    phases = (OwnershipPhase(0, frozenset()), OwnershipPhase(1, frozenset({0})))
    first, test = "src/first.py", "tests/test_first.py"
    later, native_source = "src/later.hs", "src/agentctl/haskell/test/LaterTests.hs"
    artifacts = tuple(
        ArtifactOwnership(
            path, owner, frozenset({owner}), required=True, capability=capability
        )
        for path, owner, capability in (
            (first, 0, "first"),
            (test, 0, "first-tests"),
            (later, 1, "later"),
            (native_source, 1, "later-tests"),
        )
    )
    manifest = OwnershipManifest(phases, artifacts)
    entries = tuple(Entry(item.path, "file", (b"content",)) for item in artifacts)
    node = test + "::test_first"
    native = "haskell:agentctl-core-test/Later/control"
    records = (
        Mutant("M-first-control", Operator.DELETE, first, "x", "", (node,), "reason"),
        Mutant("M-later-control", Operator.DELETE, later, "x", "", (native,), "reason"),
    )
    claims = (
        MutantOwnership(records[0].identifier, 0, ((node, test),)),
        MutantOwnership(records[1].identifier, 1, ((native, native_source),)),
    )
    absent = tuple(entry for entry in entries if entry.path != later)
    result = steps.ownership.scoped_mutant_mapping(
        manifest, absent, records, claims, ((native, native_source),)
    )
    assert isinstance(result, Ok)
    assert result.value.owners == (("M-first-control", 0), ("M-later-control", 1)), (
        "scoped mutant owner mapping was lost"
    )
    assert result.value.scopes[0] == MutantScope(0, ())
    assert (
        "required source artifact missing: " + later in result.value.scopes[1].failures
    ), "missing mutant target failure was lost"
    assert any(
        "mutant target or killer ownership mismatch" in text
        for text in result.value.scopes[1].failures
    )
    missing_claim = steps.ownership.scoped_mutant_mapping(
        manifest, entries, records, claims[:1], ((native, native_source),)
    )
    assert isinstance(missing_claim, Ok)
    assert missing_claim.value.scopes[1] == MutantScope(
        1, ("missing mutant claim: M-later-control",)
    )
    assert missing_claim.value.scopes[0] == MutantScope(0, ())
    unobserved = steps.ownership.scoped_mutant_mapping(
        manifest, entries, records, claims, ()
    )
    assert isinstance(unobserved, Ok)
    assert unobserved.value.scopes[1].failures, "unobserved native killer was accepted"
    assert isinstance(
        steps.ownership.scoped_mutant_mapping(
            manifest, (*absent, Entry("unowned", "file", (b"x",))), records, claims
        ),
        Err,
    ), "unowned mutant census was accepted"
    assert isinstance(
        steps.ownership.scoped_mutant_mapping(
            manifest, entries, records, (claims[0], replace(claims[1], owner=0))
        ),
        Err,
    ), "contradictory mutant owner was accepted"
    assert isinstance(
        steps.ownership.scoped_mutant_mapping(
            manifest,
            entries,
            records,
            claims,
            (("haskell:other/invalid", native_source),),
        ),
        Err,
    ), "invalid native source mapping was accepted"
    _assert_scoped_mutant_gate_join(
        (manifest, absent, records, claims), (native, native_source), monkeypatch
    )


def _assert_scoped_mutant_gate_join(
    inputs: tuple[
        OwnershipManifest,
        tuple[Entry, ...],
        tuple[Mutant, ...],
        tuple[MutantOwnership, ...],
    ],
    native_pair: tuple[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Join a later missing target and reject an omitted parent failure."""
    manifest, entries, records, claims = inputs
    native_node, native_source = native_pair
    monkeypatch.setattr(
        steps, "_census_mutant_declarations", lambda *_args: Ok((manifest, claims))
    )
    owners = ((records[0].identifier, 0), (records[1].identifier, 1))
    native = RunEvidence(
        "fresh",
        frozenset({native_node}),
        frozenset({native_node}),
        frozenset({native_node}),
        (),
        (),
    )
    python = RunEvidence("fresh", frozenset(), frozenset(), frozenset(), (), ())
    tools = ToolOutcome(
        0,
        Err("unused"),
        Err("unused"),
        pytest=Ok(python),
        native=Ok(NativeSnapshot(native, ((native_node, native_source),), entries)),
    )
    captured = ProvisionalCapture(
        Ok(entries),
        Ok(()),
        tools,
        (records, owners),
        Err("unused"),
        "fresh",
        (),
        (),
        scoped_mutants=True,
    )
    collection = Ok(((0, frozenset()), (1, frozenset())))
    _assert_scoped_parent_capture(entries, records, tools.native, owners, monkeypatch)
    assert steps.provisional_or_scoped_mutant_owners(entries, records) == Ok(owners), (
        "child did not select scoped mutant owners"
    )
    joined = steps.scoped_mutant_collection(collection, captured, records)
    assert isinstance(joined, Ok)
    assert joined.value[0] == (0, frozenset())
    required = (
        "mutant ownership: required source artifact missing: " + records[1].target
    )
    assert required in joined.value[1][1], (
        "scoped mutant failure was omitted from child"
    )
    phases = (
        Phase(0, Path("phase-0-test.md"), "", ()),
        Phase(1, Path("phase-1-test.md"), "", ()),
    )
    through_gate = steps.gate_execution_collection(
        collection, captured, phases, records, python
    )
    assert through_gate == joined, "scoped mutant join was omitted from gate execution"
    monkeypatch.setattr(steps, "collection_observations", lambda *_args: collection)
    monkeypatch.setattr(
        steps, "collection_with_killer_failures", lambda *_args: collection
    )
    monkeypatch.setattr(steps, "verify_phase_native_failures", lambda *_args: Ok(None))
    observed = (
        PhaseResult(0, "a" * 64, frozenset()),
        PhaseResult(1, "b" * 64, joined.value[1][1]),
    )
    assert steps.verify_phase_collection_failures(captured, phases, observed) == Ok(
        None
    )
    forged = (
        observed[0],
        replace(observed[1], failures=observed[1].failures - {required}),
    )
    assert isinstance(
        steps.verify_phase_collection_failures(captured, phases, forged), Err
    ), "parent accepted omitted scoped mutant failure"
    wrong = replace(
        captured,
        claims=(records, ((records[0].identifier, 0), (records[1].identifier, 0))),
    )
    assert isinstance(
        steps.scoped_mutant_collection(collection, wrong, records), Err
    ), "scoped mutant owner mismatch was accepted"
    missing_sources = replace(
        captured, tools=replace(tools, native=Ok(NativeSnapshot(native, (), entries)))
    )
    assert isinstance(
        steps.scoped_mutant_collection(collection, missing_sources, records), Err
    ), "scoped mutant accepted an unobserved native source"
    failed_tools = replace(
        tools,
        evidence=Ok(LegEvidence("fresh", (("cabal-test", 1),))),
        substeps=Ok(ToolSubsteps("fresh", ())),
        native=Err("native suite unavailable"),
        killers=Ok(mutant_report.Report("fresh", (), "captured")),
    )
    unavailable = replace(captured, tools=failed_tools)
    partial = steps.scoped_mutant_collection(collection, unavailable, records)
    assert isinstance(partial, Ok), partial
    assert not partial.value[0][1], "unavailable native killer poisoned earlier owner"
    assert required in partial.value[1][1], "missing mutant target failure was lost"
    assert any(
        "native" in failure and "mutant ownership:" in failure
        for failure in partial.value[1][1]
    ), "unobserved native killer was accepted"
    assert (
        steps.gate_execution_collection(
            collection, unavailable, phases, records, python
        )
        == partial
    ), "partial mutant ownership was lost in gate execution"
    passed = replace(
        unavailable,
        tools=replace(
            failed_tools, evidence=Ok(LegEvidence("fresh", (("cabal-test", 0),)))
        ),
    )
    assert isinstance(
        steps.scoped_mutant_collection(collection, passed, records), Err
    ), "successful native command without evidence accepted"
    _assert_parent_missing_native_capture(unavailable, records, monkeypatch)


def _assert_parent_missing_native_capture(
    captured: ProvisionalCapture,
    records: tuple[Mutant, ...],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Require the parent to reconstruct only a sealed failed native command."""
    assert isinstance(captured.tools.evidence, Ok)
    assert isinstance(captured.tools.substeps, Ok)
    assert isinstance(captured.tools.pytest, Ok)
    assert isinstance(captured.tools.killers, Ok)
    outcomes, substeps = captured.tools.evidence.value, captured.tools.substeps.value
    statuses = tuple(
        (name, int(name == "native-observation")) for name in steps.FINALIZER_NAMES[:-1]
    )
    finalizers = LegEvidence("fresh", statuses)
    monkeypatch.setattr(
        steps, "sealed_finalizer_observation", lambda *_args: Ok(finalizers)
    )
    monkeypatch.setattr(
        steps, "_read_sealed_tool_results", lambda *_args: Ok((outcomes, substeps))
    )
    monkeypatch.setattr(steps, "verify_tool_results_handoff", lambda *_args: Ok(None))
    monkeypatch.setattr(steps, "verify_native_absence_handoff", lambda *_args: Ok(None))
    context = steps.CheckRun(Path("/source"), Path("/run"), "fresh", "Linux")
    rebuilt = steps.__dict__["_parent_missing_native_capture"](
        context, context.directory, "", captured, records
    )
    assert isinstance(rebuilt, Ok), rebuilt
    assert rebuilt.value[1].scoped_mutants
    assert rebuilt.value[1].claims == captured.claims
    monkeypatch.setattr(steps, "_parent_bound_census", lambda *_args: captured.census)
    monkeypatch.setattr(steps, "census_phases", lambda *_args: captured.phases)
    monkeypatch.setattr(steps, "census_corpus", lambda *_args: Ok(records))
    monkeypatch.setattr(steps, "native_snapshot", lambda *_args: captured.tools.native)
    monkeypatch.setattr(
        steps, "pytest_observation", lambda *_args: captured.tools.pytest
    )
    monkeypatch.setattr(
        steps.mutant_report, "read", lambda *_args: captured.tools.killers
    )
    outer = steps.__dict__["_parent_collection_capture"](context, context.directory, "")
    assert isinstance(outer, Ok), "parent failed to reconstruct missing native capture"
    assert outer.value[1].claims == captured.claims
    monkeypatch.setattr(
        steps, "verify_tool_results_handoff", lambda *_args: Err("unsealed")
    )
    assert isinstance(
        steps.__dict__["_parent_missing_native_capture"](
            context, context.directory, "", captured, records
        ),
        Err,
    ), "parent accepted an unsealed native command"
    monkeypatch.setattr(steps, "verify_tool_results_handoff", lambda *_args: Ok(None))
    marker = "\n".join(
        (
            steps.pytest_manifest_seal("fresh", captured.tools.pytest.value),
            steps.killer_seal("fresh", captured.tools.killers.value),
            steps.tool_results_seal("fresh", outcomes, substeps),
        )
    )
    assert steps.collection_capture_sealed(rebuilt.value[1], marker) == Ok(None)
    assert isinstance(
        steps.collection_capture_sealed(rebuilt.value[1], marker + "\n" + marker), Err
    ), "ambiguous missing-native supporting seals were accepted"
    foreign_marker = marker + "\n" + steps.TOOL_RESULTS_SEAL + " foreign digest"
    assert isinstance(
        steps.collection_capture_sealed(rebuilt.value[1], foreign_marker), Err
    ), "ambiguous missing-native supporting seals were accepted"
    assert isinstance(steps.collection_capture_sealed(rebuilt.value[1], ""), Err), (
        "missing-native supporting seals were omitted"
    )
    _assert_parent_missing_native_phase_checks(context, rebuilt, marker, monkeypatch)
    passed = replace(outcomes, outcomes=(("cabal-test", 0),))
    monkeypatch.setattr(
        steps, "_read_sealed_tool_results", lambda *_args: Ok((passed, substeps))
    )
    assert isinstance(
        steps.__dict__["_parent_missing_native_capture"](
            context, context.directory, "", captured, records
        ),
        Err,
    ), "parent accepted successful native command without evidence"
    monkeypatch.setattr(
        steps, "_read_sealed_tool_results", lambda *_args: Ok((outcomes, substeps))
    )
    clean = LegEvidence(
        "fresh", tuple((name, 0) for name in steps.FINALIZER_NAMES[:-1])
    )
    monkeypatch.setattr(steps, "sealed_finalizer_observation", lambda *_args: Ok(clean))
    assert isinstance(
        steps.__dict__["_parent_missing_native_capture"](
            context, context.directory, "", captured, records
        ),
        Err,
    ), "parent accepted an unrecorded native absence"


def _assert_parent_missing_native_phase_checks(
    context: steps.CheckRun,
    rebuilt: Ok[tuple[tuple[Phase, ...], ProvisionalCapture]],
    marker: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify missing native evidence does not bypass phase checks."""
    phase_values = (PhaseResult(0, "a" * 64, frozenset({"unverified-run"})),)
    monkeypatch.setattr(
        steps, "_provisional_values_for_identity", lambda *_args: Ok(phase_values)
    )
    for name in (
        "verify_python_commands_handoff",
        "verify_pytest_handoff",
        "verify_killer_handoff",
        "verify_native_handoff",
        "_verify_provisional_census",
    ):
        monkeypatch.setattr(steps, name, lambda *_args: Ok(None))
    monkeypatch.setattr(steps, "_parent_collection_capture", lambda *_args: rebuilt)
    cited: list[bool] = []
    monkeypatch.setattr(
        steps,
        "verify_captured_cited_checks",
        lambda *_args: (cited.append(True), Ok(None))[1],
    )
    called: list[bool] = []
    monkeypatch.setattr(
        steps,
        "verify_phase_collection_failures",
        lambda *_args: (called.append(True), Ok(None))[1],
    )
    assert steps.verify_provisional_collection(
        context, context.directory, marker
    ) == Ok(None)
    assert called == [True], (
        "parent skipped missing-native phase collection verification"
    )
    assert cited == [True], "parent skipped cited check verification"
    monkeypatch.setattr(
        steps,
        "verify_captured_cited_checks",
        lambda *_args: Err("cited failure omitted"),
    )
    assert isinstance(
        steps.verify_provisional_collection(context, context.directory, marker), Err
    ), "parent accepted a failed cited check verification"
    monkeypatch.setattr(steps, "verify_provisional_coverage", lambda *_args: Ok(None))
    monkeypatch.setattr(steps, "_parent_tool_capture", lambda *_args: rebuilt)
    tool_called: list[bool] = []
    monkeypatch.setattr(
        steps,
        "verify_phase_tool_failures",
        lambda *_args: (tool_called.append(True), Ok(None))[1],
    )
    assert steps.verify_provisional_tools(context, context.directory, marker) == Ok(
        None
    )
    assert tool_called == [True], (
        "parent skipped missing-native phase tool verification"
    )
    with monkeypatch.context() as patch:
        patch.setattr(steps, "verify_provisional_collection", lambda *_args: Ok(None))
        called_validation: list[bool] = []
        patch.setattr(
            steps,
            "_parent_validation_problems",
            lambda *_args: (called_validation.append(True), Ok(()))[1],
        )
        assert steps.verify_provisional_validation(
            context, context.directory, marker
        ) == Ok(None)
        assert called_validation == [True], "parent skipped missing-native validation"


def _assert_scoped_parent_capture(
    entries: tuple[Entry, ...],
    records: tuple[Mutant, ...],
    snapshot: Result[NativeSnapshot, str] | None,
    owners: tuple[tuple[str, int], ...],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Derive the parent fallback from the captured native snapshot."""
    assert isinstance(snapshot, Ok)
    native = snapshot.value.manifest
    monkeypatch.setattr(steps, "_parent_bound_census", lambda *_args: Ok(entries))
    monkeypatch.setattr(steps, "census_phases", lambda *_args: Ok(()))
    monkeypatch.setattr(steps, "census_corpus", lambda *_args: Ok(records))
    monkeypatch.setattr(steps, "native_snapshot", lambda *_args: snapshot)
    monkeypatch.setattr(steps, "pytest_observation", lambda *_args: Ok(native))
    monkeypatch.setattr(
        steps.mutant_report,
        "read",
        lambda *_args: Ok(mutant_report.Report("fresh", (), "captured")),
    )
    context = steps.CheckRun(Path("/source"), Path("/run"), "fresh", "Linux")
    result = _parent_collection_capture(context, context.directory, "")
    assert isinstance(result, Ok), "parent did not select scoped mutant owners"
    assert result.value[1].scoped_mutants, "parent omitted scoped ownership marker"
    assert result.value[1].claims == (records, owners)
