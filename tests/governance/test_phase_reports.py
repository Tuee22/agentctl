# Copyright (c) 2026 agentctl contributors.
"""Independent controls for the phase report calculation."""

import json
from dataclasses import replace
from pathlib import Path

import pytest

from agentctl.check import steps
from agentctl.check.evidence import Entry, LegEvidence, RunEvidence, ToolSubsteps
from agentctl.check.mutants import Mutant, Operator
from agentctl.check.ownership import (
    MutantOwnership,
    OracleScope,
    OwnershipManifest,
    PhaseWork,
    ScopedPhaseWork,
    bind_mutants,
    case_consumers,
)
from agentctl.check.phase_reports import (
    AdditionalFailures,
    ArtifactOwnership,
    BindingObservation,
    CollectionObservation,
    CollectionScope,
    NativeAttribution,
    NativeFamily,
    OwnershipPhase,
    PhaseInputs,
    PhaseResult,
    binding_problems,
    calculate,
    calculate_observed,
    calculate_scoped_inputs,
    collection_failures,
    containing_mount,
    hardware_budget,
    join_additional_failures,
    native_case_failures,
    observe_collection,
    ownership_inputs,
    parse_mountinfo,
    pytest_leg_failures,
    same_bind_source,
)
from agentctl.check.steps import (
    FINALIZER_NAMES,
    ProvisionalPhaseInputs,
    join_captured_phase_failures,
    provisional_finalizer_failures,
    provisional_phase_observations,
    verify_phase_prerequisite_failures,
)
from agentctl.result import Err, Ok
from tests.harness.oracle import Object, Store, load_scoped

pytestmark = pytest.mark.evidence("value")
PHASES = (
    PhaseInputs(0, frozenset({"shared"}), frozenset({"early"}), frozenset()),
    PhaseInputs(1, frozenset({"later"}), frozenset({"late"}), frozenset({0})),
)
SOURCES = (("shared", b"original"), ("later", b"original"))


def test_parent_rechecks_cited_test_outcomes() -> None:
    """A later failed parameter cannot disappear from its owning phase result."""
    early = "tests/test_early.py::test_case"
    later = "tests/test_later.py::test_case"
    phases = (
        PhaseInputs(0, frozenset({"a"}), frozenset({early}), frozenset()),
        PhaseInputs(1, frozenset({"b"}), frozenset({later}), frozenset({0})),
    )
    nodes = frozenset({early, later + "[good]", later + "[bad]"})
    evidence = RunEvidence("fresh", nodes, nodes, nodes - {later + "[bad]"}, (), ())
    results = (
        PhaseResult(0, "a" * 64, frozenset()),
        PhaseResult(1, "b" * 64, frozenset({later})),
    )
    assert steps.verify_phase_cited_checks(phases, evidence, "fresh", results) == Ok(
        None
    )
    forged = (results[0], replace(results[1], failures=frozenset()))
    assert isinstance(
        steps.verify_phase_cited_checks(phases, evidence, "fresh", forged), Err
    ), "parent accepted omitted cited check failure"
    assert isinstance(
        steps.verify_phase_cited_checks(phases, evidence, "stale", results), Err
    ), "stale cited check nonce accepted"


EARLY = "tests/test_early.py::test_control"
LATE = "tests/test_later.py::test_control"
SCOPES = (
    CollectionScope(0, frozenset({EARLY}), frozenset({"tests/test_early.py"})),
    CollectionScope(1, frozenset({LATE}), frozenset({"tests/test_later.py"})),
)


def test_native_case_failures_follow_declared_consumers() -> None:
    """Later failures stay local; missing and ambiguous evidence fail closed."""
    early = "haskell:agentctl-core-test/Core/early"
    late = "haskell:agentctl-core-test/Mux/late"
    source = "src/agentctl/haskell/test/MuxTests.hs"
    nodes = frozenset({early, late})
    observed = RunEvidence(
        "fresh",
        nodes,
        nodes,
        frozenset({early}),
        ("failed: " + late, "native-command-failed"),
        ((early, "value"), (late, "value")),
    )
    sources = ((early, source), (late, source))
    consumers = ((source, frozenset({0, 1})),)
    citations = ((0, early), (1, late))
    result = native_case_failures(
        observed, "fresh", NativeAttribution((0, 1), sources, consumers, citations)
    )
    assert isinstance(result, Ok), result
    assert result.value[0] == (0, frozenset()), (
        "later native failure poisoned earlier phase"
    )
    assert result.value[1] == (1, frozenset({"failed native case: " + late})), (
        "later native failure was lost"
    )
    missing = native_case_failures(
        observed,
        "fresh",
        NativeAttribution(
            (0, 1),
            sources,
            consumers,
            (*citations, (0, "haskell:agentctl-core-test/Core/missing")),
        ),
    )
    assert isinstance(missing, Ok)
    assert (
        "missing native case: haskell:agentctl-core-test/Core/missing"
        in missing.value[0][1]
    )
    shared = native_case_failures(
        observed, "fresh", NativeAttribution((0, 1), sources, consumers, ((0, early),))
    )
    assert isinstance(shared, Ok)
    assert all(
        "failed native case: " + late in failures for _, failures in shared.value
    ), "unclaimed native failure was hidden from source consumers"
    for changed, mapping, ownership in (
        (replace(observed, nonce="stale"), sources, consumers),
        (observed, sources[:-1], consumers),
        (observed, sources, ((source, frozenset({0})),)),
        (replace(observed, forbidden=()), sources, consumers),
    ):
        assert isinstance(
            native_case_failures(
                changed,
                "fresh",
                NativeAttribution((0, 1), mapping, ownership, citations),
            ),
            Err,
        ), "invalid native evidence was accepted"


def test_unexplained_native_failure_follows_all_consumers() -> None:
    """A native command failure reaches every native consumer and no unrelated phase."""
    node = "haskell:agentctl-core-test/Mux/late"
    missing = "haskell:agentctl-core-test/Mux/missing"
    source = "src/agentctl/haskell/test/MuxTests.hs"
    observed = RunEvidence(
        "fresh",
        frozenset({node}),
        frozenset({node}),
        frozenset({node}),
        ("native-command-failed",),
        ((node, "value"),),
    )
    attribution = NativeAttribution(
        (0, 1, 2, 3),
        ((node, source),),
        ((source, frozenset({1, 2})),),
        ((1, node), (3, missing)),
    )
    result = native_case_failures(observed, "fresh", attribution)
    assert isinstance(result, Ok), result
    failures = dict(result.value)
    assert not failures[0], "later native command failure poisoned unrelated phase"
    assert "unexplained native command failure" in failures[1]
    assert "unexplained native command failure" in failures[2], (
        "native command failure omitted source consumer"
    )
    assert "unexplained native command failure" in failures[3], (
        "native command failure omitted cited consumer"
    )
    assert "missing native case: " + missing in failures[3]
    assert isinstance(
        native_case_failures(replace(observed, nonce="stale"), "fresh", attribution),
        Err,
    ), "stale native command observation was accepted"


def test_mountinfo_paths_and_ambiguity() -> None:
    """Kernel escapes and longest-prefix selection cannot hide a bind mount."""
    root_mount_id, source_mount_id = 10, 20
    data = (
        "10 1 8:1 / / rw - ext4 /dev/root rw\n"
        "20 10 0:40 /Users/name/source\\040tree /work/source\\040tree "
        "rw shared:5 - 9p C:\\134 rw\n"
    )
    parsed = parse_mountinfo(data)
    assert isinstance(parsed, Ok)
    selected = containing_mount("/work/source tree/src", parsed.value)
    assert isinstance(selected, Ok)
    assert selected.value.identifier == source_mount_id
    assert selected.value.root == "/Users/name/source tree"
    assert selected.value.source == "C:\\"
    assert selected.value.filesystem == "9p"
    sibling = containing_mount("/work/source tree-other", parsed.value)
    assert isinstance(sibling, Ok)
    assert sibling.value.identifier == root_mount_id
    assert isinstance(containing_mount("/work/../outside", parsed.value), Err)
    assert isinstance(containing_mount("/outside", (selected.value,)), Err)
    stacked = data + "21 10 0:40 /other /work/source\\040tree rw - 9p C:\\134 rw\n"
    ambiguous = parse_mountinfo(stacked)
    assert isinstance(ambiguous, Ok)
    assert isinstance(containing_mount("/work/source tree/src", ambiguous.value), Err)
    for invalid in (
        "",
        data.rstrip("\n"),
        data + "20 1 0:1 / /other rw - ext4 /dev/other rw\n",
        data.replace("source\\040tree", "source\\999tree"),
        "10 1 bad / / rw - ext4 /dev/root rw\n",
        "10 1 8:1 / / rw ext4 /dev/root rw\n",
        "10 1 8:1 relative / rw - ext4 /dev/root rw\n",
        "10 1 8:1 / relative rw - ext4 /dev/root rw\n",
    ):
        assert isinstance(parse_mountinfo(invalid), Err)


def test_bind_mount_mapping() -> None:
    """A mount must map the same device and filesystem root, not a copy."""
    mountinfo = (
        "10 1 8:1 / / rw - ext4 /dev/root rw\n"
        "20 10 0:40 / /mnt/c rw - 9p C:\\134 rw\n"
        "21 10 0:40 /Users/name/agentctl /work/agentctl rw - 9p C:\\134 rw\n"
    )
    records = parse_mountinfo(mountinfo)
    assert isinstance(records, Ok)
    source, target = "/mnt/c/Users/name/agentctl", "/work/agentctl"
    assert same_bind_source(source, target, records.value) == Ok(None)
    for changed in (
        mountinfo.replace("0:40 /Users", "0:41 /Users"),
        mountinfo.replace("/Users/name/agentctl /work", "/Users/name/copy /work"),
        mountinfo.replace("- 9p C:\\134 rw\n", "- 9p D:\\134 rw\n", 1),
    ):
        alternate = parse_mountinfo(changed)
        assert isinstance(alternate, Ok)
        assert isinstance(same_bind_source(source, target, alternate.value), Err), (
            "different mount mapping was accepted"
        )
    assert isinstance(same_bind_source(source, source, records.value), Err)
    assert isinstance(same_bind_source(source, target + "/src", records.value), Err)
    assert isinstance(same_bind_source("/mnt/c/../other", target, records.value), Err)


def test_binding_observation_join() -> None:
    """Each independently observed part of a live binding must agree."""
    mounts = parse_mountinfo(
        "10 1 8:1 / / rw - ext4 /dev/root rw\n"
        "20 10 0:40 / /mnt/c rw - 9p C:\\134 rw\n"
        "21 10 0:40 /Users/name/agentctl /work/agentctl rw - 9p C:\\134 rw\n"
    )
    assert isinstance(mounts, Ok)
    inventory = (("modified.py", b"changed"), ("untracked.py", b"new"))
    observation = BindingObservation(
        nonce="fresh",
        windows_write=b"windows:fresh",
        linux_read=b"windows:fresh",
        linux_write=b"linux:fresh",
        windows_read=b"linux:fresh",
        windows_inventory=inventory,
        linux_inventory=inventory,
        git_before=b"HEAD-index-refs",
        git_after=b"HEAD-index-refs",
        windows_clean=True,
        linux_clean=True,
    )
    source, target = "/mnt/c/Users/name/agentctl", "/work/agentctl"
    assert binding_problems(source, target, mounts.value, observation) == ()
    for changed, expected in (
        (replace(observation, linux_read=b"windows:stale"), "bidirectional nonce"),
        (replace(observation, windows_read=b"linux:stale"), "bidirectional nonce"),
        (replace(observation, nonce=""), "bidirectional nonce"),
        (replace(observation, linux_inventory=inventory[:1]), "source inventory"),
        (
            replace(observation, windows_inventory=(*inventory, inventory[0])),
            "source inventory",
        ),
        (replace(observation, git_after=b"changed"), "git baseline"),
        (replace(observation, linux_clean=False), "sentinel cleanup"),
        (replace(observation, windows_clean=False), "sentinel cleanup"),
    ):
        assert expected in binding_problems(source, target, mounts.value, changed)
    assert "mount mapping" in binding_problems(
        source, source, mounts.value, observation
    )


def test_ownership_rejects_boolean_indices() -> None:
    """Booleans cannot alias phase numbers, dependencies or artifact owners."""
    false = json.loads("false")
    phases = (OwnershipPhase(0, frozenset()), OwnershipPhase(1, frozenset({0})))
    artifact = ArtifactOwnership(
        "src/shared.py", 0, frozenset({0, 1}), required=True, capability="shared"
    )
    assert isinstance(ownership_inputs(phases, (artifact,), (artifact.path,)), Ok)
    for changed_phases, changed_artifact in (
        ((replace(phases[0], number=false), phases[1]), artifact),
        ((phases[0], replace(phases[1], prerequisites=frozenset({false}))), artifact),
        (phases, replace(artifact, owner=false)),
        (phases, replace(artifact, consumers=frozenset({false, 1}))),
    ):
        assert isinstance(
            ownership_inputs(changed_phases, (changed_artifact,), (artifact.path,)), Err
        ), "boolean ownership index was accepted"


def test_phase_calculation_rejects_boolean_indices() -> None:
    """A Boolean cannot stand for a phase identity or prerequisite."""
    false = json.loads("false")
    invalid = (
        (replace(PHASES[0], number=false), PHASES[1]),
        (PHASES[0], replace(PHASES[1], prerequisites=frozenset({false}))),
    )
    for phases in invalid:
        assert isinstance(
            calculate(phases, SOURCES, frozenset({"early", "late"}), frozenset()), Err
        ), "boolean phase index was accepted"


def test_native_attribution_rejects_boolean_indices() -> None:
    """Native observations cannot alias phase numbers through Boolean values."""
    false = json.loads("false")
    node = "haskell:agentctl-core-test/Native/case"
    source = "src/agentctl/haskell/test/Native.hs"
    nodes = frozenset({node})
    observed = RunEvidence("fresh", nodes, nodes, nodes, (), ())
    base = NativeAttribution(
        (0, 1), ((node, source),), ((source, frozenset({0, 1})),), ((0, node),)
    )
    assert isinstance(native_case_failures(observed, "fresh", base), Ok)
    for invalid in (
        replace(base, numbers=(false, 1)),
        replace(base, consumers=((source, frozenset({false, 1})),)),
        replace(base, citations=((false, node),)),
    ):
        assert isinstance(native_case_failures(observed, "fresh", invalid), Err), (
            "boolean native attribution index was accepted"
        )


def test_collection_rejects_boolean_indices() -> None:
    """Collection scopes and explicit owners require integer phase numbers."""
    false = json.loads("false")
    nodes = frozenset({EARLY, LATE})
    observed = CollectionObservation(
        nodes, nodes, nodes, frozenset(), nonce_matches=True, forbidden=frozenset()
    )
    assert isinstance(collection_failures(SCOPES, observed), Ok)
    assert isinstance(
        collection_failures((replace(SCOPES[0], number=false), SCOPES[1]), observed),
        Err,
    ), "boolean collection scope was accepted"
    consumers = ((EARLY, frozenset({false})), (LATE, frozenset({1})))
    assert isinstance(
        collection_failures(SCOPES, observed, case_consumers=consumers), Err
    ), "boolean case consumer was accepted"
    first = replace(
        SCOPES[0], modules=SCOPES[0].modules | {"tests/governance/test_mutants.py"}
    )
    assert isinstance(
        collection_failures(
            (first, SCOPES[1]), observed, mutation_owners=(("M-test", false),)
        ),
        Err,
    ), "boolean mutant owner was accepted"


def test_additional_failures_reject_boolean_indices() -> None:
    """A malformed phase or observer owner cannot alias an integer phase."""
    false = json.loads("false")
    calculated = calculate(PHASES, SOURCES, frozenset({"early", "late"}), frozenset())
    assert isinstance(calculated, Ok)
    empty = ((0, frozenset[str]()), (1, frozenset[str]()))
    observations = AdditionalFailures(empty, empty)
    assert isinstance(
        join_additional_failures(PHASES, calculated.value, observations), Ok
    )
    for phases, results, facts in (
        ((replace(PHASES[0], number=false), PHASES[1]), calculated.value, observations),
        (
            (PHASES[0], replace(PHASES[1], prerequisites=frozenset({false}))),
            calculated.value,
            observations,
        ),
        (
            PHASES,
            (replace(calculated.value[0], number=false), calculated.value[1]),
            observations,
        ),
        (
            PHASES,
            calculated.value,
            AdditionalFailures(((false, frozenset()), empty[1]), empty),
        ),
        (
            PHASES,
            calculated.value,
            AdditionalFailures(empty, ((false, frozenset()), empty[1])),
        ),
    ):
        assert isinstance(join_additional_failures(phases, results, facts), Err), (
            "boolean additional-failure index was accepted"
        )
    nodes = frozenset({EARLY, LATE})
    observed = CollectionObservation(
        nodes, nodes, nodes, frozenset(), nonce_matches=True, forbidden=frozenset()
    )
    assert isinstance(
        calculate_observed(
            PHASES,
            SOURCES,
            frozenset({"early", "late"}),
            frozenset(),
            (SCOPES, observed, (), ((false, frozenset()), empty[1])),
        ),
        Err,
    ), "boolean scoped ownership failure was accepted"


def test_ownership_census_and_prerequisites() -> None:
    """Every observed path has one owner and every consumer inherits that owner."""
    phases = (
        OwnershipPhase(0, frozenset()),
        OwnershipPhase(1, frozenset({0})),
        OwnershipPhase(2, frozenset({1})),
    )
    artifacts = (
        ArtifactOwnership(
            "src/shared.py", 0, frozenset({0, 2}), required=True, capability="shared"
        ),
        ArtifactOwnership(
            "src/future.py", 2, frozenset({2}), required=False, capability="future"
        ),
    )
    actual = ownership_inputs(phases, artifacts, ("src/shared.py",))
    assert actual == Ok(
        (
            (0, frozenset({"src/shared.py"})),
            (1, frozenset()),
            (2, frozenset({"src/shared.py"})),
        )
    )
    assert isinstance(
        ownership_inputs(phases, artifacts, ("src/shared.py", "src/untracked.py")), Err
    )
    assert isinstance(ownership_inputs(phases, artifacts, ()), Err)
    assert isinstance(
        ownership_inputs(phases, (*artifacts, artifacts[0]), ("src/shared.py",)), Err
    )
    assert isinstance(
        ownership_inputs(
            phases,
            (artifacts[0], replace(artifacts[1], capability="shared")),
            ("src/shared.py",),
        ),
        Err,
    )
    assert isinstance(
        ownership_inputs(
            phases,
            (replace(artifacts[0], capability="Invalid Label"),),
            ("src/shared.py",),
        ),
        Err,
    )
    assert isinstance(
        ownership_inputs(phases, artifacts, ("src/shared.py", "src/shared.py")), Err
    )
    for invalid in (
        ".",
        "../escape",
        "/absolute",
        "src//shared.py",
        "src\\shared.py",
        "C:/shared.py",
        "src/invalid\x00.py",
    ):
        assert isinstance(
            ownership_inputs(
                phases, (replace(artifacts[0], path=invalid),), (invalid,)
            ),
            Err,
        )
    unrelated = (phases[0], OwnershipPhase(1, frozenset()), phases[2])
    assert isinstance(ownership_inputs(unrelated, artifacts, ("src/shared.py",)), Err)
    assert isinstance(
        ownership_inputs(
            (phases[0], OwnershipPhase(2, frozenset({0}))),
            (artifacts[0],),
            ("src/shared.py",),
        ),
        Err,
    )
    assert isinstance(
        ownership_inputs(
            phases,
            (replace(artifacts[0], consumers=frozenset({2})),),
            ("src/shared.py",),
        ),
        Err,
    )


def test_ownership_gaps_report_all_paths() -> None:
    """Unowned and absent required paths are both identified in one result."""
    phases = (OwnershipPhase(0, frozenset()),)
    artifacts = (
        ArtifactOwnership(
            "src/needed", 0, frozenset({0}), required=True, capability="source"
        ),
    )
    gaps = ownership_inputs(phases, artifacts, ("src/untracked",))
    assert isinstance(gaps, Err)
    assert "unowned source artifact: src/untracked" in gaps.error, (
        "unowned source artifact was omitted"
    )
    assert "required source artifact missing: src/needed" in gaps.error


def test_manifest_observations_preserve_failures() -> None:
    """Only exact attributable records leave the shared-integrity failure set."""
    manifest = RunEvidence(
        "fresh",
        frozenset({EARLY, LATE}),
        frozenset({EARLY, LATE}),
        frozenset({EARLY, LATE}),
        ("failed: " + LATE, "collection failed: tests/test_later.py"),
        ((EARLY, "value"), (LATE, "value")),
    )
    observed = observe_collection(manifest, "fresh")
    assert observed.passed == frozenset({EARLY})
    assert observed.failed_modules == frozenset({"tests/test_later.py"})
    result = collection_failures(SCOPES, observed)
    assert isinstance(result, Ok)
    assert not result.value[0][1]
    assert "failed test: " + LATE in result.value[1][1]
    hostile = replace(
        manifest,
        nonce="",
        forbidden=("failed: invented", "collection failed: tests/conftest.py::hook"),
    )
    observed_hostile = observe_collection(hostile, "")
    assert not observed_hostile.nonce_matches
    assert observed_hostile.forbidden == frozenset(hostile.forbidden)


def test_owned_collection_error_is_local() -> None:
    """A known later broken module does not invalidate early execution."""
    result = collection_failures(
        SCOPES,
        CollectionObservation(
            frozenset({EARLY}),
            frozenset({EARLY}),
            frozenset({EARLY}),
            frozenset({"tests/test_later.py"}),
            nonce_matches=True,
            forbidden=frozenset(),
        ),
    )
    assert isinstance(result, Ok)
    assert not result.value[0][1]
    assert "collection failed: tests/test_later.py" in result.value[1][1]
    unknown = collection_failures(
        SCOPES,
        CollectionObservation(
            frozenset({EARLY}),
            frozenset({EARLY}),
            frozenset({EARLY}),
            frozenset({"tests/conftest.py"}),
            nonce_matches=True,
            forbidden=frozenset(),
        ),
    )
    assert isinstance(unknown, Ok)
    assert all(
        "unowned collector: tests/conftest.py" in failures
        for _, failures in unknown.value
    )


def test_shared_module_case_consumers() -> None:
    """Citations and mutant killers count; unknown cases and collection stay shared."""
    module = "tests/test_shared.py"
    early = module + "::test_early"
    late = module + "::test_late"
    other = module + "::test_other"
    scopes = (
        CollectionScope(0, frozenset({early}), frozenset({module})),
        CollectionScope(1, frozenset({late}), frozenset({module})),
    )
    record = Mutant(
        "M-shared", Operator.DELETE, "src/control.py", "x", "", (late,), "x"
    )
    mapping = case_consumers(scopes, (record,), ((record.identifier, 0),))
    assert isinstance(mapping, Ok)
    assert dict(mapping.value)[late] == frozenset({0, 1}), (
        "mutant killer consumer was omitted"
    )
    assert isinstance(case_consumers(scopes, (record,), ()), Err)
    nodes = frozenset({early, late + "[case]", other})
    observed = CollectionObservation(
        nodes,
        nodes,
        frozenset({early, other}),
        frozenset(),
        nonce_matches=True,
        forbidden=frozenset(),
    )
    shared_killer = collection_failures(scopes, observed, case_consumers=mapping.value)
    assert isinstance(shared_killer, Ok)
    assert all(
        "failed test: " + late + "[case]" in failures
        for _, failures in shared_killer.value
    )
    only_citations = case_consumers(scopes, (), ())
    assert isinstance(only_citations, Ok)
    local = collection_failures(scopes, observed, case_consumers=only_citations.value)
    assert isinstance(local, Ok)
    assert not local.value[0][1], "later case failure poisoned earlier phase"
    assert "failed test: " + late + "[case]" in local.value[1][1]
    uncited = collection_failures(
        scopes,
        replace(observed, passed=frozenset({early, late + "[case]"})),
        case_consumers=only_citations.value,
    )
    assert isinstance(uncited, Ok)
    assert all("failed test: " + other in failures for _, failures in uncited.value)
    broken = collection_failures(
        scopes,
        replace(observed, failed_modules=frozenset({module})),
        case_consumers=only_citations.value,
    )
    assert isinstance(broken, Ok)
    assert all(
        "collection failed: " + module in failures for _, failures in broken.value
    )
    assert isinstance(collection_failures(scopes, observed, case_consumers=()), Err)


def test_pytest_substeps_separate_test_and_coverage_failures() -> None:
    """Test failures stay attributable; coverage and inconsistent records do not."""
    nodes = frozenset({EARLY, LATE})
    passing = RunEvidence("current", nodes, nodes, nodes, (), ())
    tools = LegEvidence("current", (("pytest", 0),))
    substeps = ToolSubsteps("current", (("pytest", (0, 0, 0)),))
    assert pytest_leg_failures(passing, tools, substeps) == Ok(frozenset())
    failed = replace(passing, passed=frozenset({EARLY}), forbidden=("failed: " + LATE,))
    test_tools = replace(tools, outcomes=(("pytest", 1),))
    test_steps = replace(substeps, outcomes=(("pytest", (1, 0, 0)),))
    assert pytest_leg_failures(failed, test_tools, test_steps) == Ok(frozenset()), (
        "attributable test failure was treated as shared tool damage"
    )
    coverage = pytest_leg_failures(
        passing,
        replace(tools, outcomes=(("pytest", 2),)),
        replace(substeps, outcomes=(("pytest", (0, 2)),)),
    )
    assert coverage == Ok(
        frozenset({"coverage combine failed", "coverage report not executed"})
    ), "coverage failure was not shared"
    report = pytest_leg_failures(
        failed,
        test_tools,
        replace(substeps, outcomes=(("pytest", (1, 0, 2)),)),
    )
    assert report == Ok(frozenset({"coverage report failed"})), (
        "coverage failure was not shared"
    )
    for invalid in (
        (passing, tools, replace(substeps, nonce="old")),
        (failed, tools, substeps),
        (passing, tools, replace(substeps, outcomes=(("pytest", (0, 0)),))),
        (passing, tools, replace(substeps, outcomes=(("pytest", (0, 1, 0)),))),
        (passing, replace(tools, outcomes=(("pytest", 1),)), substeps),
    ):
        assert isinstance(pytest_leg_failures(*invalid), Err), (
            "inconsistent pytest execution was accepted"
        )


def test_mutation_collection_uses_verified_target_owners() -> None:
    """Shared harness failures propagate; named mutant failures follow owners."""
    module = "tests/governance/test_mutants.py"
    prefix = module + "::test_corpus["
    early, late = prefix + "M-early]", prefix + "M-later]"
    shared = module + "::test_harness_control"
    scopes = (
        CollectionScope(0, frozenset({early}), frozenset({module})),
        CollectionScope(1, frozenset({late}), frozenset({module})),
    )
    nodes = frozenset({early, late, shared})
    observed = CollectionObservation(
        nodes,
        nodes,
        frozenset({early, shared}),
        frozenset(),
        nonce_matches=True,
        forbidden=frozenset(),
    )
    owners = (("M-early", 0), ("M-later", 1))
    result = collection_failures(scopes, observed, mutation_owners=owners)
    assert isinstance(result, Ok)
    assert not result.value[0][1]
    assert "failed test: " + late in result.value[1][1]
    shared_failure = collection_failures(
        scopes,
        replace(observed, passed=frozenset({early, late})),
        mutation_owners=owners,
    )
    assert isinstance(shared_failure, Ok)
    assert all(
        "failed test: " + shared in failures for _, failures in shared_failure.value
    )
    incomplete = collection_failures(scopes, observed, mutation_owners=owners[:1])
    assert isinstance(incomplete, Err)
    without_claims = collection_failures(scopes, observed)
    assert isinstance(without_claims, Err)
    shared_scopes = tuple(
        replace(scope, required=frozenset({shared})) for scope in scopes
    )
    unknown = collection_failures(shared_scopes, observed, mutation_owners=owners[:1])
    assert isinstance(unknown, Ok)
    assert all("unowned mutation: " + late in failures for _, failures in unknown.value)
    malformed = prefix[:-1]
    malformed_observation = replace(
        observed,
        collected=nodes | {malformed},
        executed=nodes | {malformed},
        passed=observed.passed | {malformed},
    )
    malformed_result = collection_failures(
        shared_scopes, malformed_observation, mutation_owners=owners
    )
    assert isinstance(malformed_result, Ok)
    assert all(
        "unowned mutation: " + malformed in failures
        for _, failures in malformed_result.value
    )
    assert isinstance(
        collection_failures(scopes, observed, mutation_owners=(*owners, owners[0])), Err
    )
    assert isinstance(
        collection_failures(
            scopes, observed, mutation_owners=(("M-early", 1), ("M-later", 1))
        ),
        Err,
    )
    missing = collection_failures(
        scopes,
        replace(observed, collected=nodes - {late}, executed=nodes - {late}),
        mutation_owners=owners,
    )
    assert isinstance(missing, Ok)
    assert not missing.value[0][1]
    assert "missing mutation: " + late in missing.value[1][1]


def test_collection_failures_reach_phase_verdicts() -> None:
    """Later damage remains local; prerequisite and shared damage propagate."""
    nodes = frozenset({EARLY, LATE})
    observation = CollectionObservation(
        nodes,
        nodes,
        frozenset({EARLY}),
        frozenset(),
        nonce_matches=True,
        forbidden=frozenset(),
    )
    later = calculate_observed(
        PHASES,
        SOURCES,
        frozenset({"early", "late"}),
        frozenset(),
        (SCOPES, observation),
    )
    assert isinstance(later, Ok)
    assert not later.value[0].failures
    assert "failed test: " + LATE in later.value[1].failures, (
        "collection failure was omitted from verdict"
    )
    missing = calculate_observed(
        PHASES,
        SOURCES[:1],
        frozenset({"early", "late"}),
        frozenset(),
        (SCOPES, replace(observation, passed=nodes)),
    )
    assert isinstance(missing, Ok), "missing input globalized phase verdicts"
    assert missing.value[0] == later.value[0]
    assert "missing-input:later" in missing.value[1].failures
    earlier = calculate_observed(
        PHASES,
        SOURCES,
        frozenset({"early", "late"}),
        frozenset(),
        (SCOPES, replace(observation, passed=frozenset({LATE}))),
    )
    assert isinstance(earlier, Ok)
    assert "failed test: " + EARLY in earlier.value[0].failures
    assert "prerequisite:0" in earlier.value[1].failures
    shared = calculate_observed(
        PHASES,
        SOURCES,
        frozenset({"early", "late"}),
        frozenset(),
        (SCOPES, replace(observation, nonce_matches=False)),
    )
    assert isinstance(shared, Ok)
    assert all("nonce" in result.failures for result in shared.value)
    assert isinstance(
        calculate_observed(
            PHASES, SOURCES, frozenset(), frozenset(), (SCOPES[:1], observation)
        ),
        Err,
    )


def test_provisional_finalizers_retain_shared_damage() -> None:
    """A shared finalizer failure reaches every provisional consumer."""
    calculated = calculate_scoped_inputs(
        PHASES, SOURCES, frozenset({"early", "late"}), frozenset({"unverified-run"})
    )
    assert isinstance(calculated, Ok)
    clean = tuple((name, 0) for name in FINALIZER_NAMES)
    assert provisional_finalizer_failures(calculated, clean) == calculated
    damaged = tuple(
        (name, int(name in {"ratchet", "containment", "write-guard"}))
        for name in FINALIZER_NAMES
    )
    result = provisional_finalizer_failures(calculated, damaged)
    assert isinstance(result, Ok)
    assert all(
        {
            "shared finalizer failed: ratchet",
            "shared finalizer failed: containment",
            "shared finalizer failed: write-guard",
        }
        <= item.failures
        for item in result.value
    ), "shared finalizer failure was omitted"
    assert isinstance(provisional_finalizer_failures(calculated, clean[:-1]), Err), (
        "incomplete finalizer observations were accepted"
    )
    assert isinstance(
        provisional_finalizer_failures(
            calculated, (*clean[:-1], (FINALIZER_NAMES[-1], True))
        ),
        Err,
    )
    assert provisional_finalizer_failures(Err("missing"), clean) == Err("missing")


def test_provisional_observations_join_captured_evidence() -> None:
    """The provisional join retains failures and never supplies a passing receipt."""
    nodes = frozenset({"early", "late"})
    empty = ((0, frozenset[str]()), (1, frozenset[str]()))
    captured = ProvisionalPhaseInputs(
        ScopedPhaseWork(PhaseWork(PHASES, SOURCES), empty),
        RunEvidence("current", nodes, nodes, nodes, (), ()),
        "current",
        Ok(((0, frozenset[str]()), (1, frozenset({"collection failure"})))),
        Ok(((0, frozenset({"native failure"})), (1, frozenset[str]()))),
        Ok((OracleScope(0, ()), OracleScope(1, ("oracle failure",)))),
    )
    result = provisional_phase_observations(captured)
    assert isinstance(result, Ok)
    assert all("unverified-run" in item.failures for item in result.value), (
        "provisional observation became a passing receipt"
    )
    assert "native failure" in result.value[0].failures
    assert {"collection failure", "oracle failure", "prerequisite:0"} <= (
        result.value[1].failures
    ), "captured collection failure was omitted"
    with_shared = provisional_phase_observations(
        replace(captured, shared=frozenset({"tool failure"}))
    )
    assert isinstance(with_shared, Ok)
    assert all("tool failure" in item.failures for item in with_shared.value), (
        "captured shared tool failure was omitted"
    )
    with_owned = provisional_phase_observations(
        replace(
            captured,
            scoped_tools=(
                (0, frozenset()),
                (1, frozenset({"toolchain-ensure failed"})),
            ),
        )
    )
    assert isinstance(with_owned, Ok)
    assert "toolchain-ensure failed" not in with_owned.value[0].failures
    assert "toolchain-ensure failed" in with_owned.value[1].failures, (
        "captured owned tool failure was omitted"
    )
    assert isinstance(
        provisional_phase_observations(replace(captured, nonce="stale")), Err
    ), "stale phase observation was accepted"
    assert isinstance(
        provisional_phase_observations(replace(captured, collection=Err("missing"))),
        Err,
    ), "missing collection attribution was accepted"
    duplicate = Ok((*empty, empty[0]))
    assert isinstance(
        provisional_phase_observations(replace(captured, collection=duplicate)), Err
    )


def test_unverified_marker_does_not_invent_prerequisite_failures() -> None:
    """Only observed lower-phase failures propagate to dependent phases."""
    nodes = frozenset({"early", "late"})
    empty = ((0, frozenset[str]()), (1, frozenset[str]()))
    captured = ProvisionalPhaseInputs(
        ScopedPhaseWork(PhaseWork(PHASES, SOURCES), empty),
        RunEvidence("current", nodes, nodes, nodes, (), ()),
        "current",
        Ok(empty),
        Ok(empty),
        Ok((OracleScope(0, ()), OracleScope(1, ()))),
    )
    clean = provisional_phase_observations(captured)
    assert isinstance(clean, Ok)
    assert all(
        item.failures == frozenset({"unverified-run"}) for item in clean.value
    ), "unverified marker invented a prerequisite failure"
    later = provisional_phase_observations(
        replace(
            captured, scoped_tools=((0, frozenset()), (1, frozenset({"later failure"})))
        )
    )
    assert isinstance(later, Ok)
    assert later.value[0].failures == frozenset({"unverified-run"}), (
        "later owned failure blocked earlier phase"
    )
    assert later.value[1].failures == frozenset({"unverified-run", "later failure"})
    earlier = provisional_phase_observations(
        replace(
            captured,
            scoped_tools=((0, frozenset({"earlier failure"})), (1, frozenset())),
        )
    )
    assert isinstance(earlier, Ok)
    assert "prerequisite:0" in earlier.value[1].failures, (
        "observed prerequisite failure was not propagated"
    )
    _assert_parent_prerequisite_failures(clean.value, later.value, earlier.value)


def _assert_parent_prerequisite_failures(
    clean: tuple[PhaseResult, ...],
    later: tuple[PhaseResult, ...],
    earlier: tuple[PhaseResult, ...],
) -> None:
    """Refuse missing or invented prerequisite failures without promoting markers."""
    clean_phases, later_phases, earlier_phases = clean, later, earlier
    assert verify_phase_prerequisite_failures(PHASES, clean_phases) == Ok(None), (
        "parent treated provisional marker as failure"
    )
    assert verify_phase_prerequisite_failures(PHASES, later_phases) == Ok(None)
    assert verify_phase_prerequisite_failures(PHASES, earlier_phases) == Ok(None)
    omitted = (
        earlier_phases[0],
        replace(
            earlier_phases[1], failures=earlier_phases[1].failures - {"prerequisite:0"}
        ),
    )
    assert isinstance(verify_phase_prerequisite_failures(PHASES, omitted), Err), (
        "parent accepted missing prerequisite failure"
    )
    invented = (
        clean_phases[0],
        replace(
            clean_phases[1], failures=clean_phases[1].failures | {"prerequisite:0"}
        ),
    )
    assert isinstance(verify_phase_prerequisite_failures(PHASES, invented), Err), (
        "parent accepted invented prerequisite failure"
    )
    finalized = tuple(
        replace(item, failures=item.failures | {"shared finalizer failed: ratchet"})
        for item in clean_phases
    )
    assert verify_phase_prerequisite_failures(PHASES, finalized) == Ok(None), (
        "shared finalizer invented a prerequisite failure"
    )


def test_provisional_parametrized_citation_requires_every_case() -> None:
    """A cited test passes only when all its collected variants pass completely."""
    cited = "tests/test_early.py::test_control"
    cases = frozenset({cited + "[first]", cited + "[second]"})
    phases = (replace(PHASES[0], checks=frozenset({cited})), PHASES[1])
    nodes = cases | {"late"}
    empty = ((0, frozenset[str]()), (1, frozenset[str]()))
    captured = ProvisionalPhaseInputs(
        ScopedPhaseWork(PhaseWork(phases, SOURCES), empty),
        RunEvidence("current", nodes, nodes, nodes, (), ()),
        "current",
        Ok(empty),
        Ok(empty),
        Ok((OracleScope(0, ()), OracleScope(1, ()))),
    )
    complete = provisional_phase_observations(captured)
    assert isinstance(complete, Ok)
    assert cited not in complete.value[0].failures, "passing parameter cases were lost"
    assert "unverified-run" in complete.value[0].failures
    for manifest in (
        replace(captured.manifest, passed=nodes - {cited + "[second]"}),
        replace(captured.manifest, forbidden=("failed: " + cited + "[second]",)),
        replace(
            captured.manifest,
            collected=frozenset({"late"}),
            executed=frozenset({"late"}),
            passed=frozenset({"late"}),
        ),
        replace(
            captured.manifest,
            collected=frozenset({"late", cited + "_other[first]"}),
            executed=frozenset({"late", cited + "_other[first]"}),
            passed=frozenset({"late", cited + "_other[first]"}),
        ),
        replace(
            captured.manifest,
            collected=nodes | {cited},
            executed=nodes | {cited},
            passed=(nodes | {cited}) - {cited + "[second]"},
        ),
    ):
        observed = provisional_phase_observations(replace(captured, manifest=manifest))
        assert isinstance(observed, Ok)
        assert cited in observed.value[0].failures, "incomplete parameter cases passed"


def test_captured_phase_failures_require_both_observers() -> None:
    """The captured join refuses unavailable sources instead of inventing passes."""
    base = calculate_scoped_inputs(
        PHASES, SOURCES, frozenset({"early", "late"}), frozenset()
    )
    assert isinstance(base, Ok)
    native = Ok(((0, frozenset[str]()), (1, frozenset({"later native"}))))
    oracle = Ok((OracleScope(0, ("early oracle",)), OracleScope(1, ())))
    result = join_captured_phase_failures(PHASES, base.value, native, oracle)
    assert isinstance(result, Ok)
    assert "early oracle" in result.value[0].failures
    assert {"later native", "prerequisite:0"} <= result.value[1].failures
    assert isinstance(
        join_captured_phase_failures(PHASES, base.value, Err("missing"), oracle), Err
    ), "missing native attribution was accepted"
    assert isinstance(
        join_captured_phase_failures(PHASES, base.value, native, Err("missing")), Err
    ), "missing oracle attribution was accepted"
    duplicate = Ok((OracleScope(0, ("same", "same")), OracleScope(1, ())))
    assert isinstance(
        join_captured_phase_failures(PHASES, base.value, native, duplicate), Err
    )


def test_native_and_oracle_failures_join_phase_results() -> None:
    """Complete attributed failures stay local and propagate to dependents."""
    base = calculate_scoped_inputs(
        PHASES, SOURCES, frozenset({"early", "late"}), frozenset()
    )
    assert isinstance(base, Ok)
    empty = ((0, frozenset[str]()), (1, frozenset[str]()))
    later = ((0, frozenset[str]()), (1, frozenset({"late native"})))
    earlier = ((0, frozenset({"early oracle"})), (1, frozenset[str]()))
    local = join_additional_failures(
        PHASES, base.value, AdditionalFailures(later, empty)
    )
    assert isinstance(local, Ok)
    assert not local.value[0].failures
    assert "late native" in local.value[1].failures, "native failure was omitted"
    propagated = join_additional_failures(
        PHASES, base.value, AdditionalFailures(empty, earlier)
    )
    assert isinstance(propagated, Ok)
    assert "early oracle" in propagated.value[0].failures, "oracle failure was omitted"
    assert "prerequisite:0" in propagated.value[1].failures
    assert isinstance(
        join_additional_failures(
            PHASES, base.value, AdditionalFailures(empty[:1], empty)
        ),
        Err,
    ), "incomplete native attribution was accepted"
    assert isinstance(
        join_additional_failures(
            PHASES, base.value, AdditionalFailures(empty, (*empty, empty[0]))
        ),
        Err,
    )


def test_scoped_ownership_failures_reach_phase_verdicts() -> None:
    """Known later failures stay local; earlier failures reach prerequisites."""
    nodes = frozenset({EARLY, LATE})
    observation = CollectionObservation(
        nodes, nodes, nodes, frozenset(), nonce_matches=True, forbidden=frozenset()
    )
    passed = frozenset({"early", "late"})
    later = ((0, frozenset[str]()), (1, frozenset({"missing later claim"})))
    result = calculate_observed(
        PHASES, SOURCES, passed, frozenset(), (SCOPES, observation, (), later)
    )
    assert isinstance(result, Ok)
    assert not result.value[0].failures
    assert "missing later claim" in result.value[1].failures, (
        "scoped ownership failure was omitted from verdict"
    )
    earlier = ((0, frozenset({"missing early claim"})), (1, frozenset[str]()))
    result = calculate_observed(
        PHASES, SOURCES, passed, frozenset(), (SCOPES, observation, (), earlier)
    )
    assert isinstance(result, Ok)
    assert "missing early claim" in result.value[0].failures
    assert "prerequisite:0" in result.value[1].failures
    assert isinstance(
        calculate_observed(
            PHASES, SOURCES, passed, frozenset(), (SCOPES, observation, (), later[:1])
        ),
        Err,
    )
    for malformed in (
        (later[0], later[0]),
        ((0, frozenset({""})), later[1]),
        ((0, frozenset[str]()), (2, frozenset[str]())),
    ):
        assert isinstance(
            calculate_observed(
                PHASES,
                SOURCES,
                passed,
                frozenset(),
                (SCOPES, observation, (), malformed),
            ),
            Err,
        ), "malformed scoped ownership failures were accepted"


def test_mutation_ownership_reaches_phase_verdicts() -> None:
    """A later mutant failure stays local and an unknown owner remains shared."""
    module = "tests/governance/test_mutants.py"
    early = module + "::test_corpus[M-early]"
    late = module + "::test_corpus[M-later]"
    scopes = (
        CollectionScope(0, frozenset({early}), frozenset({module})),
        CollectionScope(1, frozenset({late}), frozenset({module})),
    )
    nodes = frozenset({early, late})
    observation = CollectionObservation(
        nodes,
        nodes,
        frozenset({early}),
        frozenset(),
        nonce_matches=True,
        forbidden=frozenset(),
    )
    targets = ("src/early.py", "src/later.py")
    killer = "tests/test_killers.py"
    killer_node = killer + "::test_control"
    manifest = OwnershipManifest(
        (OwnershipPhase(0, frozenset()), OwnershipPhase(1, frozenset({0}))),
        (
            ArtifactOwnership(
                targets[0], 0, frozenset({0}), required=True, capability="early"
            ),
            ArtifactOwnership(
                targets[1], 1, frozenset({1}), required=True, capability="later"
            ),
            ArtifactOwnership(
                killer, 0, frozenset({0, 1}), required=True, capability="killers"
            ),
        ),
    )
    entries = tuple(Entry(path, "file", (b"content",)) for path in (*targets, killer))
    mutants = tuple(
        Mutant(identifier, Operator.DELETE, target, "x", "", (killer_node,), "reason")
        for identifier, target in zip(("M-early", "M-later"), targets, strict=True)
    )
    claims = tuple(
        MutantOwnership(mutant.identifier, owner, ((killer_node, killer),))
        for owner, mutant in enumerate(mutants)
    )
    bound = bind_mutants(manifest, entries, mutants, claims)
    assert isinstance(bound, Ok)
    owners = bound.value
    result = calculate_observed(
        PHASES,
        SOURCES,
        frozenset({"early", "late"}),
        frozenset(),
        (scopes, observation, owners),
    )
    assert isinstance(result, Ok), "mutation ownership was omitted from verdict"
    assert not result.value[0].failures
    assert "failed test: " + late in result.value[1].failures
    assert isinstance(
        calculate_observed(
            PHASES,
            SOURCES,
            frozenset({"early", "late"}),
            frozenset(),
            (scopes, observation, owners[:1]),
        ),
        Err,
    )


def test_complete_collection_without_selection() -> None:
    """Execution gaps, forbidden selection and stale nonces invalidate all scopes."""
    nodes = frozenset({EARLY, LATE})
    clean = collection_failures(
        SCOPES,
        CollectionObservation(
            nodes,
            nodes,
            nodes,
            frozenset(),
            nonce_matches=True,
            forbidden=frozenset(),
        ),
    )
    assert isinstance(clean, Ok)
    assert all(not failures for _, failures in clean.value)
    damaged = collection_failures(
        SCOPES,
        CollectionObservation(
            nodes,
            frozenset({EARLY}),
            frozenset({EARLY}),
            frozenset(),
            nonce_matches=False,
            forbidden=frozenset({"deselected"}),
        ),
    )
    assert isinstance(damaged, Ok)
    assert all(
        {"nonce", "deselected", "incomplete execution"} <= failures
        for _, failures in damaged.value
    ), "incomplete execution was accepted"


def test_future_missing_ids_are_owned() -> None:
    """An absent future case fails its owner; parameter cases must all pass."""
    parameter = EARLY + "[one]"
    result = collection_failures(
        SCOPES,
        CollectionObservation(
            frozenset({parameter}),
            frozenset({parameter}),
            frozenset({parameter}),
            frozenset(),
            nonce_matches=True,
            forbidden=frozenset(),
        ),
    )
    assert isinstance(result, Ok)
    assert not result.value[0][1], "future missing test poisoned earlier phase"
    assert "missing or failed: " + LATE in result.value[1][1]
    failed = collection_failures(
        SCOPES,
        CollectionObservation(
            frozenset({parameter, EARLY + "[two]"}),
            frozenset({parameter, EARLY + "[two]"}),
            frozenset({parameter}),
            frozenset(),
            nonce_matches=True,
            forbidden=frozenset(),
        ),
    )
    assert isinstance(failed, Ok)
    assert "missing or failed: " + EARLY in failed.value[0][1]


def test_hardware_budget() -> None:
    """A phase requires Linux and can add at most one foreign family."""
    assert hardware_budget(frozenset({"linux"}))
    assert hardware_budget(frozenset({"linux", "windows"}))
    assert hardware_budget(frozenset({"linux", "macos"}))
    assert not hardware_budget(frozenset({"linux", "windows", "macos"})), (
        "combined foreign families were accepted"
    )
    assert not hardware_budget(frozenset({"windows"}))
    assert not hardware_budget(frozenset())


def test_hardware_budget_oracle(root: Path) -> None:
    """Compare the phase family budget with independent, anchored expectations."""
    store = load_scoped(root / "tests/oracles/phase_ownership.toml", root)
    assert isinstance(store, Store)
    rows = store.effective
    assert rows
    for row in rows:
        assert isinstance(row.inputs, Object)
        value = dict(row.inputs.items)
        assert value["subject"] == "hardware-budget"
        linux, windows, macos = value["linux"], value["windows"], value["macos"]
        assert isinstance(linux, bool)
        assert isinstance(windows, bool)
        assert isinstance(macos, bool)
        assert isinstance(row.expected, bool)
        choices: tuple[tuple[NativeFamily, bool], ...] = (
            ("linux", linux),
            ("windows", windows),
            ("macos", macos),
        )
        assert (
            hardware_budget(frozenset(name for name, selected in choices if selected))
            == row.expected
        )


def test_later_failure_preserves_earlier_verdict() -> None:
    """An owned later failure does not poison a complete prerequisite."""
    result = calculate(PHASES, SOURCES, frozenset({"early"}), frozenset())
    assert isinstance(result, Ok)
    assert result.value[0].failures == frozenset(), (
        "later failure poisoned earlier phase"
    )
    assert result.value[1].failures == frozenset({"late"})
    failed_early = calculate(PHASES, SOURCES, frozenset({"late"}), frozenset())
    assert isinstance(failed_early, Ok)
    assert "prerequisite:0" in failed_early.value[1].failures


def test_shared_failure_invalidates_dependents() -> None:
    """A shared integrity failure remains visible in every consuming verdict."""
    result = calculate(
        PHASES, SOURCES, frozenset({"early", "late"}), frozenset({"nonce"})
    )
    assert isinstance(result, Ok)
    assert all("nonce" in phase.failures for phase in result.value), (
        "shared failure was ignored"
    )


def test_scoped_missing_inputs_preserve_earlier_identity() -> None:
    """Missing owned inputs fail their consumers and their dependents only."""
    passed = frozenset({"early", "late"})
    complete = calculate_scoped_inputs(PHASES, SOURCES, passed, frozenset())
    missing_later = calculate_scoped_inputs(PHASES, SOURCES[:1], passed, frozenset())
    missing_shared = calculate_scoped_inputs(PHASES, SOURCES[1:], passed, frozenset())
    assert isinstance(complete, Ok)
    assert isinstance(missing_later, Ok)
    assert isinstance(missing_shared, Ok)
    assert missing_later.value[0] == complete.value[0]
    assert missing_later.value[1].failures == frozenset({"missing-input:later"}), (
        "missing input was accepted"
    )
    assert missing_shared.value[0].failures == frozenset({"missing-input:shared"})
    assert "prerequisite:0" in missing_shared.value[1].failures
    sentinel = calculate_scoped_inputs(
        PHASES, (("shared", b"original"), ("later", b"\x01")), passed, frozenset()
    )
    assert isinstance(sentinel, Ok)
    assert sentinel.value[1].identity != missing_later.value[1].identity
    assert isinstance(
        calculate_scoped_inputs(PHASES, (*SOURCES, SOURCES[0]), passed, frozenset()),
        Err,
    )


def test_receipt_input_closure() -> None:
    """Later-only bytes preserve the earlier digest; shared bytes invalidate both."""
    baseline = calculate(PHASES, SOURCES, frozenset({"early", "late"}), frozenset())
    later = calculate(
        PHASES,
        (("shared", b"original"), ("later", b"changed")),
        frozenset(),
        frozenset(),
    )
    shared = calculate(
        PHASES,
        (("shared", b"changed"), ("later", b"original")),
        frozenset(),
        frozenset(),
    )
    assert isinstance(baseline, Ok)
    assert isinstance(later, Ok)
    assert isinstance(shared, Ok)
    assert baseline.value[0].identity == later.value[0].identity
    assert baseline.value[1].identity != later.value[1].identity
    assert all(
        a.identity != b.identity
        for a, b in zip(baseline.value, shared.value, strict=True)
    ), "prerequisite identity was omitted"
    revised = calculate(
        (replace(PHASES[0], checks=frozenset({"additional"})), PHASES[1]),
        SOURCES,
        frozenset(),
        frozenset(),
    )
    assert isinstance(revised, Ok)
    assert all(
        a.identity != b.identity
        for a, b in zip(baseline.value, revised.value, strict=True)
    )
    assert isinstance(calculate(PHASES, SOURCES[:1], frozenset(), frozenset()), Err)
    assert isinstance(
        calculate(
            (PHASES[0], replace(PHASES[1], prerequisites=frozenset({1}))),
            SOURCES,
            frozenset(),
            frozenset(),
        ),
        Err,
    )
    assert isinstance(
        calculate(PHASES, (*SOURCES, SOURCES[0]), frozenset(), frozenset()), Err
    )


def test_parent_rechecks_prerequisite_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    """Require both parent paths to preserve actual prerequisite failures."""
    nonce = "fresh"
    context = steps.CheckRun(Path("/source"), Path("/run"), nonce, "Linux")
    final = LegEvidence(nonce, tuple((name, 0) for name in FINALIZER_NAMES[:-1]))
    work = ScopedPhaseWork(
        PhaseWork(PHASES, SOURCES), ((0, frozenset()), (1, frozenset()))
    )
    observed = (
        PhaseResult(0, "a" * 64, frozenset({"unverified-run", "earlier failure"})),
        PhaseResult(1, "b" * 64, frozenset({"unverified-run", "prerequisite:0"})),
    )
    forged = (observed[0], replace(observed[1], failures=frozenset({"unverified-run"})))
    output = steps.finalizer_seal(final)
    with monkeypatch.context() as patch:
        patch.setattr(steps, "finalizer_observation", lambda *_args: Ok(final))
        patch.setattr(
            steps, "_provisional_values_for_identity", lambda *_args: Ok(observed)
        )
        patch.setattr(steps, "_parent_bound_census", lambda *_args: Ok(()))
        patch.setattr(steps.ownership, "guarded_census", lambda *_args: Ok(()))
        patch.setattr(steps, "census_phases", lambda *_args: Ok(()))
        patch.setattr(steps, "scoped_source_inputs", lambda *_args: Ok(work))
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
            "verify_provisional_source",
            "verify_provisional_tools",
            "verify_provisional_validation",
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
        assert steps.verify_provisional_prerequisites(
            context, context.directory, output
        ) == Ok(None)
        patch.setattr(steps, "_parent_bound_census", lambda *_args: Err("changed"))
        assert isinstance(
            steps.verify_provisional_prerequisites(context, context.directory, output),
            Err,
        ), "unbound parent prerequisite census was accepted"
        patch.setattr(steps, "_parent_bound_census", lambda *_args: Ok(()))
        patch.setattr(
            steps, "_provisional_values_for_identity", lambda *_args: Ok(forged)
        )
        assert isinstance(
            steps.verify_provisional_prerequisites(context, context.directory, output),
            Err,
        ), "parent accepted missing prerequisite failure"
        assert isinstance(steps.verify_python_handoffs(context, output), Err), (
            "live parent accepted missing prerequisite failure"
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
            "retained parent accepted missing prerequisite failure"
        )
