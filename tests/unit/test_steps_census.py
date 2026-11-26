# Copyright (c) 2026 agentctl contributors.
"""Census-derived validator inputs refuse absent, invalid or ambiguous entries."""

import json
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from agentctl.check import steps
from agentctl.check.evidence import Entry, LegEvidence, ToolSubsteps, source_census
from agentctl.check.legs import Leg, python_legs, targets
from agentctl.check.mutants import census_corpus
from agentctl.foundation import Err, Ok

pytestmark = pytest.mark.evidence("value")

MANIFEST = "src/agentctl/check/source_ownership.toml"
PHASE0 = "src/agentctl/check/phase0_mutant_ownership.toml"
FRAGMENT = "src/agentctl/check/governance_mutant_ownership.toml"
STANDARDS = "DEVELOPMENT_PLAN/development_plan_standards.md"
OVERVIEW = "DEVELOPMENT_PLAN/00-overview.md"


def test_command_capture_uses_guarded_source_census(tmp_path: Path) -> None:
    """Command evidence binds the captured bytes, not a fabricated source identity."""
    root, run_dir = tmp_path / "root", tmp_path / "run"
    (root / "src").mkdir(parents=True)
    (root / "tests").mkdir()
    (root / "pyproject.toml").write_text("[project]\nname = 'test'\n", encoding="utf-8")
    (root / "src/subject.py").write_text("value = 1\n", encoding="utf-8")
    run_dir.mkdir()
    census = steps.ownership.guarded_census(root)
    assert isinstance(census, Ok)
    digest = steps.evidence.digest_census(census.value)
    assert isinstance(digest, Ok)
    commands = tuple((name, (("python", name),)) for name in steps.PYTHON_COMMAND_NAMES)
    captured = steps.__dict__["_capture_python_commands"](
        steps.CheckRun(root, run_dir, "current", "Linux"), census, commands
    )
    assert isinstance(captured, Ok)
    assert json.loads(captured.value.record)["source_digest"] == digest.value, (
        "command source digest was not captured"
    )


def test_python_tool_targets_match_guarded_census(tmp_path: Path) -> None:
    """The real target walk must cover exactly the captured Python source set."""
    source, tests = tmp_path / "src", tmp_path / "tests"
    source.mkdir()
    tests.mkdir()
    (source / "first.py").write_text("pass\n", encoding="utf-8")
    (tests / "test_first.py").write_text("pass\n", encoding="utf-8")
    directory = source / "package.py"
    directory.mkdir()
    (directory / "inside.py").write_text("pass\n", encoding="utf-8")
    found = targets(tmp_path)
    entries = source_census(tmp_path)
    assert isinstance(found, Ok)
    assert isinstance(entries, Ok)
    assert steps.python_target_census(tmp_path, found.value, entries.value) == Ok(None)
    assert isinstance(
        steps.python_target_census(tmp_path, found.value[:-1], entries.value), Err
    ), "missing Python tool target was accepted"
    assert isinstance(
        steps.python_target_census(
            tmp_path, (*found.value, found.value[0]), entries.value
        ),
        Err,
    ), "duplicate Python tool target was accepted"
    assert isinstance(
        steps.python_target_census(
            tmp_path, tuple(reversed(found.value)), entries.value
        ),
        Err,
    ), "reordered Python tool targets were accepted"
    assert isinstance(
        steps.python_target_census(
            tmp_path, found.value, (*entries.value, entries.value[0])
        ),
        Err,
    ), "duplicate Python source census was accepted"
    escaped = (*entries.value, Entry("src/../foreign.txt", "file", (b"data",)))
    assert isinstance(
        steps.python_target_census(tmp_path, found.value, escaped), Err
    ), "noncanonical Python source census was accepted"
    without_root = tuple(entry for entry in entries.value if entry.path != "tests")
    assert isinstance(
        steps.python_target_census(tmp_path, found.value, without_root), Err
    ), "missing Python source root was accepted"
    empty = (Entry("src", "directory", (b"",)), Entry("tests", "directory", (b"",)))
    assert isinstance(steps.python_target_census(tmp_path, (), empty), Err), (
        "empty Python tool targets were accepted"
    )
    (tests / "test_new.py").write_text("pass\n", encoding="utf-8")
    changed = source_census(tmp_path)
    assert isinstance(changed, Ok)
    assert isinstance(
        steps.python_target_census(tmp_path, found.value, changed.value), Err
    ), "new Python source was omitted from tool targets"


def test_python_invocations_join_census_and_attempted_commands(tmp_path: Path) -> None:
    """The exact planned commands and actual attempted prefixes must agree."""
    root, run_dir = tmp_path / "checkout", tmp_path / "run"
    source, tests = root / "src/agentctl", root / "tests"
    (source / "check").mkdir(parents=True)
    tests.mkdir()
    run_dir.mkdir()
    (source / "subject.py").write_text("pass\n", encoding="utf-8")
    (tests / "test_subject.py").write_text("pass\n", encoding="utf-8")
    (root / "pyproject.toml").write_text(
        "[project.optional-dependencies]\ndev = ['coverage==7.17.0']\n",
        encoding="utf-8",
    )
    (source / "check/coverage_hosts.toml").write_text(
        "version = 1\n[[source]]\n"
        "path = 'src/agentctl/subject.py'\nhosts = ['Linux']\n",
        encoding="utf-8",
    )
    found, census = targets(root), source_census(root)
    assert isinstance(found, Ok)
    assert isinstance(census, Ok)
    context = steps.CheckRun(root, run_dir, "fresh", "Linux")
    legs = python_legs(sys.executable, root, found.value, run_dir)
    commands = tuple((leg.name, (leg.argv, *leg.after)) for leg in legs)
    substeps = tuple((leg.name, (0,) * (1 + len(leg.after))) for leg in legs)
    tools = steps.ToolOutcome(
        0,
        Ok(LegEvidence("fresh", tuple((leg.name, 0) for leg in legs))),
        Ok(ToolSubsteps("fresh", substeps)),
        commands=commands,
    )
    observe = steps.python_invocation_observation
    assert observe(context, found.value, census.value, legs, tools) == Ok(None)
    later = Leg("later-owned", (sys.executable, "-c", "raise SystemExit(1)"))
    extended = replace(
        tools,
        code=1,
        evidence=Ok(
            LegEvidence(
                "fresh", (*tuple((leg.name, 0) for leg in legs), (later.name, 1))
            )
        ),
        substeps=Ok(ToolSubsteps("fresh", (*substeps, (later.name, (1,))))),
        commands=(*commands, (later.name, (later.argv,))),
    )
    assert observe(context, found.value, census.value, (*legs, later), extended) == Ok(
        None
    ), "later owned tool poisoned Python invocation observation"
    altered_leg = replace(legs[0], argv=legs[0].argv[:-1])
    assert isinstance(
        observe(context, found.value, census.value, (altered_leg, *legs[1:]), tools),
        Err,
    ), "changed Python invocation plan was accepted"
    altered_commands = ((commands[0][0], (commands[0][1][0][:-1],)), *commands[1:])
    assert isinstance(
        observe(
            context,
            found.value,
            census.value,
            legs,
            replace(tools, commands=altered_commands),
        ),
        Err,
    ), "changed attempted Python command was accepted"
    assert isinstance(
        observe(
            replace(context, nonce="stale"), found.value, census.value, legs, tools
        ),
        Err,
    ), "stale Python invocation was accepted"
    stale_outcomes = replace(
        tools,
        evidence=Ok(LegEvidence("stale", tuple((leg.name, 0) for leg in legs))),
    )
    assert isinstance(
        observe(context, found.value, census.value, legs, stale_outcomes), Err
    ), "stale Python outcome nonce was accepted"
    stale_steps = replace(tools, substeps=Ok(ToolSubsteps("stale", substeps)))
    assert isinstance(
        observe(context, found.value, census.value, legs, stale_steps), Err
    ), "stale Python substep nonce was accepted"
    assert isinstance(
        observe(
            context,
            found.value,
            census.value,
            legs,
            replace(tools, commands=commands[:-1]),
        ),
        Err,
    ), "missing Python invocation was accepted"
    wrong_outcomes = tuple((leg.name, int(leg.name == "pytest")) for leg in legs)
    assert isinstance(
        observe(
            context,
            found.value,
            census.value,
            legs,
            replace(tools, evidence=Ok(LegEvidence("fresh", wrong_outcomes))),
        ),
        Err,
    ), "Python invocation outcome mismatch was accepted"
    pytest_commands = (*commands[:-1], ("pytest", commands[-1][1][:2]))
    stopped_steps = (*substeps[:-1], ("pytest", (1, 1)))
    stopped = replace(
        tools,
        code=1,
        evidence=Ok(LegEvidence("fresh", wrong_outcomes)),
        substeps=Ok(ToolSubsteps("fresh", stopped_steps)),
        commands=pytest_commands,
    )
    assert observe(context, found.value, census.value, legs, stopped) == Ok(None)
    too_few = replace(
        stopped, commands=(*commands[:-1], ("pytest", commands[-1][1][:1]))
    )
    assert isinstance(
        observe(context, found.value, census.value, legs, too_few), Err
    ), "Python command and status counts disagreed"
    truncated = replace(
        stopped,
        substeps=Ok(ToolSubsteps("fresh", (*substeps[:-1], ("pytest", (1, 0))))),
    )
    assert isinstance(
        observe(context, found.value, census.value, legs, truncated), Err
    ), "truncated successful Python followup was accepted"


def _census(root: Path) -> tuple[Entry, ...]:
    """Observe the live checkout once for a calculation."""
    entries = source_census(root)
    assert isinstance(entries, Ok), entries
    return entries.value


def _without(entries: tuple[Entry, ...], *paths: str) -> tuple[Entry, ...]:
    """Remove the named entries."""
    return tuple(entry for entry in entries if entry.path not in paths)


def _replaced(
    entries: tuple[Entry, ...], path: str, payload: bytes
) -> tuple[Entry, ...]:
    """Replace one regular file's bytes."""
    return tuple(
        Entry(entry.path, entry.kind, (payload,)) if entry.path == path else entry
        for entry in entries
    )


def _without_phases(entries: tuple[Entry, ...]) -> tuple[Entry, ...]:
    """Remove every phase document from the census."""
    return tuple(
        entry
        for entry in entries
        if not entry.path.startswith("DEVELOPMENT_PLAN/phase-")
    )


def test_census_text_requires_one_utf8_regular_file() -> None:
    """Missing, duplicate, non-file and non-UTF-8 declarations are refused."""
    text = steps.__dict__["_census_text"]
    file = Entry("a.toml", "file", (b"ok",))
    assert text((file,), "a.toml") == Ok("ok")
    assert isinstance(text((), "a.toml"), Err)
    assert isinstance(text((file, file), "a.toml"), Err)
    assert isinstance(text((Entry("a.toml", "directory", ()),), "a.toml"), Err)
    assert isinstance(text((Entry("a.toml", "file", (b"\xff",)),), "a.toml"), Err)


def test_phase_declarations_require_phase_documents(root: Path) -> None:
    """Missing or non-phase plan documents yield no phase declarations."""
    entries = _census(root)
    assert isinstance(steps.census_phases(root, entries), Ok)
    assert isinstance(steps.census_phases(root, _without_phases(entries)), Err)
    unparsable = (Entry("DEVELOPMENT_PLAN/phase-x.md", "file", (b"no header",)),)
    assert isinstance(steps.census_phases(root, unparsable), Err)
    linked = (Entry("DEVELOPMENT_PLAN/phase-x.md", "symlink", (b"target",)),)
    assert isinstance(steps.census_phases(root, linked), Err)


def test_claim_and_consumer_validators_report_unreadable_inputs(root: Path) -> None:
    """Each validator names its unreadable or invalid source declaration."""
    entries = _census(root)
    records = census_corpus(entries)
    assert isinstance(records, Ok), records
    assert steps.phase0_claim_problems(root, _without(entries, PHASE0), ()) != ()
    assert steps.phase0_claim_problems(root, _without_phases(entries), ()) != ()
    assert (
        steps.phase0_claim_problems(root, _replaced(entries, PHASE0, b"x = ["), ())
        != ()
    )
    phase0 = "DEVELOPMENT_PLAN/phase-0-governance-and-phase-evidence.md"
    assert steps.phase0_claim_problems(root, _without(entries, phase0), ()) == (
        "validators: missing or duplicate Phase 0 declaration",
    )
    for broken in (_without(entries, MANIFEST), _replaced(entries, MANIFEST, b"x")):
        assert steps.test_consumer_problems(root, broken) != ()
        assert steps.fragment_claim_problems(broken, records.value) != ()
        assert isinstance(steps.complete_mutant_owners(broken, records.value), Err)
        assert isinstance(steps.scoped_source_inputs(broken, ()), Err)
    assert steps.test_consumer_problems(root, _without_phases(entries)) != ()
    for fragment in (_without(entries, FRAGMENT), _replaced(entries, FRAGMENT, b"[")):
        assert steps.fragment_claim_problems(fragment, records.value) != ()
        assert isinstance(steps.provisional_mutant_owners(fragment, records.value), Err)
        assert isinstance(
            steps.observed_native_mutant_owners(fragment, records.value, ()), Err
        )
        assert isinstance(steps.scoped_mutant_ownership(fragment, records.value), Err)


def test_policy_and_collection_scopes_refuse_invalid_inputs(root: Path) -> None:
    """Closure policy and collection scopes need complete, unique inputs."""
    entries = _census(root)
    assert isinstance(steps.census_policy(_without(entries, STANDARDS), None), Err)
    assert isinstance(steps.census_policy(_without(entries, OVERVIEW), None), Err)
    phases = steps.census_phases(root, entries)
    assert isinstance(phases, Ok), phases
    manifest_text = steps.__dict__["_census_text"](entries, MANIFEST)
    assert isinstance(manifest_text, Ok)
    manifest = steps.ownership.parse_manifest(manifest_text.value)
    assert isinstance(manifest, Ok)
    duplicated = (*phases.value, phases.value[0])
    assert steps.diagnostic_collection_scopes(manifest.value, duplicated) == Err(
        "invalid collection phase declarations"
    )
    assert isinstance(steps.scoped_source_inputs(entries, duplicated), Err)


def test_provisional_observation_refusals(root: Path) -> None:
    """Provisional joins refuse missing ownership, owners, nonces and readiness."""
    entries = _census(root)
    phases = steps.census_phases(root, entries)
    assert isinstance(phases, Ok), phases
    run = steps.evidence.RunEvidence(
        "fresh", frozenset(), frozenset(), frozenset(), (), ()
    )
    broken = _without(entries, MANIFEST)
    assert isinstance(
        steps.collection_observations(broken, phases.value, run, "fresh", None), Err
    )
    unowned = steps.collection_observations(entries, phases.value, run, "fresh", None)
    assert unowned == Err("complete mutation ownership unavailable")
    duplicated = (*phases.value, phases.value[0])
    assert isinstance(
        steps.collection_observations(entries, duplicated, run, "fresh", None), Err
    )
    assert steps.report_collection(Err("unavailable")) == 1
    snapshot = steps.NativeSnapshot(run, (), broken)
    assert isinstance(
        steps.native_failure_observations(snapshot, "fresh", phases.value, (), ()), Err
    )
    wrong = steps.NativeSnapshot(run, (), entries)
    assert steps.native_failure_observations(wrong, "fresh", (), (), ()) == Err(
        "native phase declarations differ from ownership"
    )
    owned = steps.provisional_owned_tool_failures
    assert isinstance(owned(entries, (), frozenset(), readiness=("",)), Err)
    assert isinstance(owned(broken, (), frozenset(), readiness=("later",)), Err)
    assert isinstance(
        owned(_replaced(entries, MANIFEST, b"x"), (), frozenset(), readiness=("l",)),
        Err,
    )
    assert isinstance(
        steps.provisional_work_and_tools(broken, phases.value, frozenset(), ()), Err
    )
    assert steps.report_provisional_phases(Err("missing")) == 1
    assert steps.provisional_phase_record("", None) == Err(
        "invalid provisional phase nonce"
    )
    assert steps.provisional_phase_record("fresh", Err("")) == Err(
        "empty provisional phase failure"
    )
    assert steps.provisional_finalizer_failures(Ok(()), ()) == Err(
        "incomplete or ambiguous finalizer observations"
    )


def test_parent_rechecks_shared_validation_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keep recomputed shared validator failures on every phase and parent path."""
    problems = ("docs: broken", "plan: broken")
    required = frozenset("unattributed validation: " + item for item in problems)
    observed = (
        steps.phase_reports.PhaseResult(0, "a" * 64, required | {"unverified-run"}),
        steps.phase_reports.PhaseResult(1, "b" * 64, required | {"unverified-run"}),
    )
    assert steps.verify_phase_validation_failures(problems, observed) == Ok(None)
    forged = (
        replace(
            observed[0],
            failures=observed[0].failures - {"unattributed validation: docs: broken"},
        ),
        observed[1],
    )
    assert isinstance(steps.verify_phase_validation_failures(problems, forged), Err), (
        "parent accepted hidden validator failure"
    )
    context = steps.CheckRun(Path("/source"), Path("/run"), "fresh", "Linux")
    final = LegEvidence(
        context.nonce, tuple((name, 0) for name in steps.FINALIZER_NAMES[:-1])
    )
    output = steps.finalizer_seal(final)
    with monkeypatch.context() as patch:
        _assert_parent_validation_problems(context, patch)
        patch.setattr(steps, "finalizer_observation", lambda *_args: Ok(final))
        patch.setattr(
            steps, "_provisional_values_for_identity", lambda *_args: Ok(observed)
        )
        patch.setattr(steps, "_parent_validation_problems", lambda *_args: Ok(problems))
        for name in (
            "verify_provisional_collection",
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
            "verify_provisional_oracle",
            "verify_provisional_host",
            "verify_provisional_coverage",
            "verify_provisional_static",
            "verify_provisional_source",
            "verify_provisional_prerequisites",
            "verify_provisional_tools",
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
        assert steps.verify_provisional_validation(
            context, context.directory, output
        ) == Ok(None)
        patch.setattr(
            steps, "_provisional_values_for_identity", lambda *_args: Ok(forged)
        )
        assert isinstance(
            steps.verify_provisional_validation(context, context.directory, output), Err
        ), "parent accepted hidden validator failure"
        assert isinstance(steps.verify_python_handoffs(context, output), Err), (
            "live parent accepted hidden validator failure"
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
            "retained parent accepted hidden validator failure"
        )


def _assert_parent_validation_problems(
    context: steps.CheckRun, patch: pytest.MonkeyPatch
) -> None:
    """Recompute each validator and reject a changed census around the join."""
    entries = (Entry("src/example.py", "file", (b"pass\n",)),)
    tools = steps.ToolOutcome(0, Err("unused"), Err("unused"))
    capture = steps.ProvisionalCapture(
        Ok(entries), Ok(()), tools, ((), ()), Err("unused"), context.nonce, (), ()
    )
    patch.setattr(steps, "_parent_collection_capture", lambda *_args: Ok(((), capture)))
    patch.setattr(steps, "targets", lambda *_args: Ok(("src/example.py",)))
    patch.setattr(steps, "complete_mutant_owners", lambda *_args: Ok(()))
    patch.setattr(
        steps,
        "census_policy",
        lambda *_args: Ok(steps.closure.CapturedPolicy((), "standards", "overview")),
    )
    patch.setattr(steps, "python_target_census", lambda *_args: Err("target mismatch"))
    validators = (
        "source_ownership_problems",
        "docs",
        "plan",
        "test_consumer_problems",
        "coverage_host_problems",
        "forbidden_surfaces",
        "configuration",
        "phase0_claim_problems",
        "fragment_claim_problems",
    )
    for name in validators:
        patch.setattr(steps, name, lambda *_args, _name=name, **_kwargs: (_name,))
    patch.setattr(
        steps.closure, "static", lambda *_args, **_kwargs: ("closure.static",)
    )
    patch.setattr(steps, "_parent_bound_census", lambda *_args: Ok(entries))
    recomputed = steps.__dict__["_parent_validation_problems"](
        context, context.directory, ""
    )
    assert isinstance(recomputed, Ok), recomputed
    assert set(recomputed.value) == set(validators) | {
        "validators: Python targets: target mismatch",
        "closure.static",
    }, "parent validator census omitted a finding"
    patch.setattr(steps, "_parent_bound_census", lambda *_args: Ok(()))
    assert isinstance(
        steps.__dict__["_parent_validation_problems"](context, context.directory, ""),
        Err,
    ), "parent accepted changed validator census"
