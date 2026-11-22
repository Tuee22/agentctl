# Copyright (c) 2026 agentctl contributors.
"""Closed ownership declarations require exact, independently observed files."""

import json
import re
import tomllib
from dataclasses import replace
from pathlib import Path

import pytest

from agentctl.check import mutant_report
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
    NativeSnapshot,
    ProvisionalCapture,
    ToolOutcome,
    _native_ownership_observation,
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
def test_oracle_failures_follow_source_consumers() -> None:
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


@pytest.mark.evidence("value")
def test_gate_captures_provisional_phase_observations(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Join the actual captured value shapes and reject a foreign native census."""
    paths = (
        "src/agentctl/check/source_ownership.toml",
        "tests/test_early.py",
        "src/native.hs",
        "tests/governance/test_mutants.py",
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
    )
    node = paths[1] + "::test_case"
    record = Mutant(
        "M-control", Operator.DELETE, "src/native.hs", "a", "", (node,), "x"
    )
    mutation_node = mutant_report.PREFIX + record.identifier + "]"
    native_node = "haskell:agentctl-core-test/Example/control"
    phase = phase_text(
        Path("phase-0-example.md"),
        "### Sprint 0.1: Test [Active]\n"
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
    )
    result = captured_phase_observations(captured)
    assert isinstance(result, Ok), result
    assert result.value[0].failures == frozenset({"unverified-run"})
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
    assert any("failed:baseline" in item for item in failed_result.value[0].failures), (
        "individual mutant killer failure was lost from phase observation"
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
    foreign = replace(snapshot, entries=entries[:-1])
    invalid = replace(captured, tools=replace(tools, native=Ok(foreign)))
    assert isinstance(captured_phase_observations(invalid), Err), (
        "native observation with a foreign census was accepted"
    )
    assert isinstance(
        captured_phase_observations(replace(captured, nonce="stale")), Err
    )


@pytest.mark.evidence("value")
def test_gate_scopes_captured_toolchain_failure() -> None:
    """The captured gate join preserves earlier phases when toolchain setup fails."""
    manifest_path = "src/agentctl/check/source_ownership.toml"
    target = "src/agentctl/check/toolchain.py"
    prerequisites = "src/agentctl/check/prerequisites.py"
    native_path = "src/native.hs"
    test_paths = tuple(f"tests/test_phase_{number}.py" for number in range(3))
    document = "version = 1\n"
    for number in range(3):
        parents = "[]" if number == 0 else f"[{number - 1}]"
        document += f"[[phases]]\nnumber = {number}\nprerequisites = {parents}\n"
    artifacts = (
        (manifest_path, 0),
        (native_path, 0),
        (target, 2),
        (prerequisites, 2),
        *zip(test_paths, range(3), strict=True),
    )
    for path, owner in artifacts:
        document += (
            f'[[artifacts]]\npath = "{path}"\ncapability = "scope-{owner}"\n'
            f"owner = {owner}\nconsumers = [{owner}]\nrequired = true\n"
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
