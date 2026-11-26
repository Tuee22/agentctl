# Copyright (c) 2026 agentctl contributors.
"""Parent handoff rechecks refuse each unavailable, forged or inconsistent input."""

from dataclasses import replace
from pathlib import Path

import pytest

from agentctl import foundation_host
from agentctl.check import lanes, mutant_report, phase_reports, steps
from agentctl.check.evidence import Entry, LegEvidence, RunEvidence, ToolSubsteps
from agentctl.check.plan_data import Phase, phase_text
from agentctl.result import Err, Ok, Result

pytestmark = pytest.mark.evidence("value")
MANIFEST = "src/agentctl/check/source_ownership.toml"
TEST_PATH = "tests/test_early.py"
SOURCE_PATH = "src/agentctl/subject.py"
NONCE = "nonce"
ABSENT = "missing or duplicate census declaration: " + MANIFEST
EMPTY_RUN = RunEvidence(NONCE, frozenset(), frozenset(), frozenset(), (), ())
IDENTITY = "a" * 64
FINALIZERS = LegEvidence(NONCE, tuple((name, 0) for name in steps.FINALIZER_NAMES[:-1]))
NATIVE_FAILED = replace(
    FINALIZERS,
    outcomes=tuple(
        (name, 1 if name == "native-observation" else code)
        for name, code in FINALIZERS.outcomes
    ),
)


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


def _phase(tests: str = f"`{TEST_PATH}::case`") -> Phase:
    parsed = phase_text(
        Path("phase-0-example.md"),
        f"### Sprint 0.1: Test [Active]\n**Validation tests**: {tests}\n"
        "## Remaining Work\n",
    )
    assert parsed is not None
    return parsed


def _observed() -> tuple[phase_reports.PhaseResult, ...]:
    return (phase_reports.PhaseResult(0, IDENTITY, frozenset({"unverified-run"})),)


def _context(tmp_path: Path) -> steps.CheckRun:
    return steps.CheckRun(tmp_path, tmp_path, NONCE, "Linux")


def _tools() -> steps.ToolOutcome:
    return steps.ToolOutcome(0, Err("evidence"), Err("substeps"))


def _capture(
    tools: steps.ToolOutcome | None = None,
    census: tuple[Entry, ...] | None = None,
) -> steps.ProvisionalCapture:
    return steps.ProvisionalCapture(
        Err("census") if census is None else Ok(census),
        Ok((_phase(),)),
        _tools() if tools is None else tools,
        ((), ()),
        Err("oracle"),
        NONCE,
        (),
        (),
    )


def _ok(value: object) -> object:
    return lambda *_args, **_kwargs: Ok(value)


def _err(message: str) -> object:
    return lambda *_args, **_kwargs: Err(message)


def test_finalizer_failures_need_a_nonce_and_observations() -> None:
    """Finalizer rechecks reject an unidentified or empty observation."""
    assert steps.verify_phase_finalizer_failures(
        replace(FINALIZERS, nonce=""), _observed()
    ) == Err("invalid phase finalizer observations")


def test_provisional_finalizers_need_both_handoffs(tmp_path: Path) -> None:
    """Missing retained finalizer or provisional handoffs are structured refusals."""
    assert steps.verify_provisional_finalizers(tmp_path, NONCE, "") == Err(
        "phase finalizer handoff unavailable"
    )


def test_localized_native_finalizers_refuse_unavailable_hosts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An unknown host family cannot reproduce a localized native absence."""
    unknown = lanes.HostFacts("Plan9", "x86_64", checkout=True, git=True, debian=True)
    monkeypatch.setattr(foundation_host, "current", lambda *_args: unknown)
    assert steps.__dict__["_verify_localized_native_finalizers"](
        tmp_path, NONCE, "", NATIVE_FAILED, _observed()
    ) == Err("native finalizer host unavailable")


def test_localized_native_finalizers_need_ownership_and_scopes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Missing ownership or unreadable native scopes cannot localize an absence."""
    function = steps.__dict__["_verify_localized_native_finalizers"]
    declarations = (_phase(),)
    unowned = _capture()
    monkeypatch.setattr(
        steps, "_parent_collection_capture", _ok((declarations, unowned))
    )
    assert function(tmp_path, NONCE, "", NATIVE_FAILED, _observed()) == Err(
        "native finalizer ownership unavailable"
    )
    owned = _capture(census=())
    monkeypatch.setattr(steps, "_parent_collection_capture", _ok((declarations, owned)))
    for name in (
        "verify_python_commands_handoff",
        "verify_pytest_handoff",
        "verify_killer_handoff",
        "collection_capture_sealed",
        "verify_phase_native_failures",
    ):
        monkeypatch.setattr(steps, name, _ok(None))
    assert function(tmp_path, NONCE, "", NATIVE_FAILED, _observed()) == Err(ABSENT)


def test_input_identities_refuse_unreadable_and_uncalculable_census(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Identity recalculation needs a manifest and a calculable phase closure."""
    assert steps.verify_phase_input_identities((), (_phase(),), ()) == Err(ABSENT)
    monkeypatch.setattr(phase_reports, "calculate_scoped_inputs", _err("uncalculable"))
    assert steps.verify_phase_input_identities(
        _entries(), (_phase(),), _observed()
    ) == Err("uncalculable")


def test_identity_values_need_sealed_provisional_records(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A provisional record must be sealed and readable before it is decoded."""
    function = steps.__dict__["_provisional_values_for_identity"]
    monkeypatch.setattr(steps, "sealed_finalizer_observation", _ok(FINALIZERS))
    monkeypatch.setattr(steps, "verify_provisional_handoff", _err("unsealed"))
    assert function(_context(tmp_path), tmp_path, "") == Err(
        "phase input identity handoff unavailable"
    )
    monkeypatch.setattr(steps, "verify_provisional_handoff", _ok(None))
    assert function(_context(tmp_path), tmp_path, "") == Err(
        "phase input identity record unavailable"
    )


def test_identity_decoder_refuses_changed_records(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The decoder requires JSON, the canonical schema and the child's seal."""
    decode = steps.__dict__["_decode_provisional_for_identity"]
    assert decode(NONCE, b"{", "") == Err("phase input identity record unavailable")
    assert decode(NONCE, b"{}", "") == Err("phase input identity record changed")
    record = b'{"status": "other"}'
    monkeypatch.setattr(steps, "parse_provisional_record", _ok(None))
    sealed = steps.provisional_seal(NONCE, record)
    assert decode(NONCE, record, sealed) == Err(
        "phase input identity record is invalid"
    )


def test_bound_census_refuses_unparseable_command_records(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The captured command record must decode before its digest is compared."""
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    record = b"{"
    monkeypatch.setattr(steps, "_python_commands_handoff_record", _ok(record))
    output = steps.python_commands_seal(NONCE, record)
    bound = steps.__dict__["_parent_bound_census"](_context(tmp_path), tmp_path, output)
    assert bound == Err("phase input command record unavailable")


def test_missing_native_capture_requires_guarded_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A missing native leg needs sealed finalizers, results and a valid mapping."""
    function = steps.__dict__["_parent_missing_native_capture"]
    context = _context(tmp_path)
    assert function(context, tmp_path, "", _capture(), ()) == Err(
        "missing native parent evidence unavailable"
    )
    results = (LegEvidence(NONCE, (("cabal-test", 1),)), ToolSubsteps(NONCE, ()))
    monkeypatch.setattr(steps, "sealed_finalizer_observation", _ok(NATIVE_FAILED))
    monkeypatch.setattr(steps, "_read_sealed_tool_results", _ok(results))
    monkeypatch.setattr(steps, "verify_tool_results_handoff", _ok(None))
    monkeypatch.setattr(steps, "verify_native_absence_handoff", _ok(None))
    assert function(context, tmp_path, "", _capture(census=()), ()) == Err(ABSENT)


def test_collection_capture_needs_decodable_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Collection capture refuses missing declarations, pytest or killer records."""
    function = steps.__dict__["_parent_collection_capture"]
    context = _context(tmp_path)
    monkeypatch.setattr(steps, "_parent_bound_census", _ok(()))
    assert function(context, tmp_path, "") == Err(
        "phase collection evidence unavailable"
    )
    snapshot = steps.NativeSnapshot(EMPTY_RUN, (), ())
    monkeypatch.setattr(steps, "native_snapshot", _ok(snapshot))
    assert function(context, tmp_path, "") == Err(
        "phase collection evidence unavailable"
    )


def test_collection_capture_binds_complete_owner_claims(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Complete mutant owners are used without consulting native case sources."""
    function = steps.__dict__["_parent_collection_capture"]
    snapshot = steps.NativeSnapshot(EMPTY_RUN, (), ())
    report = mutant_report.Report(NONCE, (), "digest")
    monkeypatch.setattr(steps, "_parent_bound_census", _ok(()))
    monkeypatch.setattr(steps, "census_phases", _ok((_phase(),)))
    monkeypatch.setattr(steps, "census_corpus", _ok(()))
    monkeypatch.setattr(steps, "native_snapshot", _ok(snapshot))
    monkeypatch.setattr(steps, "pytest_observation", _ok(EMPTY_RUN))
    monkeypatch.setattr(mutant_report, "read", _ok(report))
    monkeypatch.setattr(steps, "complete_mutant_owners", _ok(()))
    captured = function(_context(tmp_path), tmp_path, "")
    assert isinstance(captured, Ok)
    assert captured.value[1].claims == ((), ())
    assert not captured.value[1].scoped_mutants


def test_missing_native_collection_seal_requires_every_observation() -> None:
    """A failed native leg still needs pytest, killers and tool results sealed."""
    function = steps.__dict__["_missing_collection_capture_sealed"]
    assert function(_capture(), "") == Err("phase collection observations unavailable")


def test_collection_capture_seal_refuses_unsealed_native_evidence() -> None:
    """Native, pytest and killer observations must be present and consistent."""
    snapshot = steps.NativeSnapshot(EMPTY_RUN, (), ())
    pytest_missing = replace(_tools(), native=Ok(snapshot))
    assert steps.collection_capture_sealed(_capture(pytest_missing), "") == Err(
        "phase collection observations unavailable"
    )
    stale = steps.NativeSnapshot(replace(EMPTY_RUN, nonce="stale"), (), ())
    killers = mutant_report.Report(NONCE, (), "digest")
    tools = replace(
        _tools(), native=Ok(stale), pytest=Ok(EMPTY_RUN), killers=Ok(killers)
    )
    assert isinstance(steps.collection_capture_sealed(_capture(tools), ""), Err)


def _patch_sealed(patch: pytest.MonkeyPatch, values: Result[object, str]) -> None:
    patch.setattr(steps, "sealed_finalizer_observation", _ok(FINALIZERS))
    patch.setattr(steps, "_provisional_values_for_identity", lambda *_args: values)


def test_provisional_rechecks_pass_through_unavailable_values(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Collection, oracle, host, tool and coverage rechecks relay unavailable values."""
    context = _context(tmp_path)
    rechecks = (
        steps.verify_provisional_collection,
        steps.verify_provisional_oracle,
        steps.verify_provisional_host,
        steps.verify_provisional_tools,
        steps.verify_provisional_coverage,
    )
    for values in (Ok(None), Err("unavailable")):
        _patch_sealed(monkeypatch, values)
        for recheck in rechecks:
            assert recheck(context, tmp_path, "") == values


def test_provisional_rechecks_refuse_invalid_supporting_handoffs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Each recheck names its own failed supporting handoff."""
    context = _context(tmp_path)
    _patch_sealed(monkeypatch, Ok(_observed()))
    expected = (
        (steps.verify_provisional_collection, "phase collection supporting"),
        (steps.verify_provisional_oracle, "phase oracle supporting"),
        (steps.verify_provisional_host, "phase host supporting"),
        (steps.verify_provisional_tools, "phase tool supporting"),
        (steps.verify_provisional_coverage, "phase coverage supporting"),
    )
    for recheck, prefix in expected:
        result = recheck(context, tmp_path, "")
        assert isinstance(result, Err)
        assert result.error.startswith(prefix)


def test_cited_checks_need_a_census_and_pytest_run() -> None:
    """Cited checks cannot be derived without the captured census and pytest run."""
    assert steps.verify_captured_cited_checks(
        ((_phase(),), _capture()), NONCE, _observed()
    ) == Err("phase cited check observations unavailable")
    tools = replace(_tools(), pytest=Ok(EMPTY_RUN))
    assert steps.verify_captured_cited_checks(
        ((_phase(),), _capture(tools, census=())), NONCE, _observed()
    ) == Err(ABSENT)
