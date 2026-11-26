# Copyright (c) 2026 agentctl contributors.
"""Defensive refusals of the tool attribution and provisional joins in the gate."""

from dataclasses import replace
from pathlib import Path

import pytest

from agentctl.check import ownership, phase_reports, steps
from agentctl.check.evidence import Entry, RunEvidence
from agentctl.check.plan_data import Phase
from agentctl.process import Output
from agentctl.result import Err, Ok

pytestmark = pytest.mark.evidence("value")
MANIFEST = "src/agentctl/check/source_ownership.toml"
NONCE = "nonce"
BROKEN = Entry(MANIFEST, "file", (b"not valid = [toml",))
ABSENT_TEXT = "missing or duplicate census declaration: " + MANIFEST
EMPTY_RUN = RunEvidence(NONCE, frozenset(), frozenset(), frozenset(), (), ())


def _capture(tools: steps.ToolOutcome) -> steps.ProvisionalCapture:
    return steps.ProvisionalCapture(
        Err("census"), Err("phases"), tools, None, Err("oracle"), NONCE, (), ()
    )


def _unavailable_tools() -> steps.ToolOutcome:
    return steps.ToolOutcome(0, Err("evidence"), Err("substeps"))


def _failing() -> Output:
    return Output(0, "[]", "")


def test_ruff_family_attribution_requires_tool_status(tmp_path: Path) -> None:
    """A captured diagnostic without sealed tool status is a structured refusal."""
    snapshot = steps.RuffSnapshot(NONCE, tmp_path, _failing(), ())
    ty_snapshot = steps.TySnapshot(NONCE, tmp_path, _failing(), ())
    tools = _unavailable_tools()
    ruff = _capture(replace(tools, ruff=Ok(snapshot)))
    formatted = _capture(replace(tools, ruff_format=Ok(snapshot)))
    typed = _capture(replace(tools, ty=Ok(ty_snapshot)))
    assert steps.ruff_validation_attribution(ruff, (), ()) == Err(
        "Ruff tool status unavailable"
    )
    assert steps.ruff_format_validation_attribution(formatted, (), ()) == Err(
        "Ruff format tool status unavailable"
    )
    assert steps.ty_validation_attribution(typed, (), ()) == Err(
        "ty tool status unavailable"
    )


def test_ruff_format_and_ty_return_their_captured_failures() -> None:
    """A snapshot that is itself an Err is returned unchanged."""
    tools = _unavailable_tools()
    formatted = _capture(replace(tools, ruff_format=Err("format failed")))
    typed = _capture(replace(tools, ty=Err("ty failed")))
    assert steps.ruff_format_validation_attribution(formatted, (), ()) == Err(
        "format failed"
    )
    assert steps.ty_validation_attribution(typed, (), ()) == Err("ty failed")


def test_provisional_join_refuses_empty_phase_inputs() -> None:
    """An empty phase set cannot be hashed into scoped identities."""
    work = ownership.ScopedPhaseWork(ownership.PhaseWork((), ()), ())
    inputs = steps.ProvisionalPhaseInputs(
        work, EMPTY_RUN, NONCE, Ok(()), Ok(()), Ok(())
    )
    assert steps.provisional_phase_observations(inputs) == Err(
        "invalid phase declarations or source census"
    )


def _phase_text(number: int) -> Phase:
    return Phase(number, Path("phase.md"), "text", ())


def test_manifest_readers_refuse_absent_and_unparseable_declarations() -> None:
    """Each census consumer reports its absent or malformed ownership manifest."""
    phases = (_phase_text(0),)
    for entries, message in (((), ABSENT_TEXT), ((BROKEN,), None)):
        results = (
            steps.collection_observations(entries, phases, EMPTY_RUN, NONCE, None),
            steps.unavailable_native_scopes(entries, phases, (), ()),
            steps.native_failure_observations(
                steps.NativeSnapshot(EMPTY_RUN, (), entries), NONCE, phases, (), ()
            ),
        )
        for result in results:
            assert isinstance(result, Err)
            assert message is None or result.error == message


def test_provisional_tool_failures_need_captured_observations() -> None:
    """Missing sealed outcomes or substeps leave no tool failures to join."""
    capture = _capture(_unavailable_tools())
    assert steps.provisional_tool_failures(capture, EMPTY_RUN, None) == Err(
        "captured tool observations unavailable"
    )


def test_identity_attribution_refuses_unreadable_manifests() -> None:
    """A failed binary identity needs a readable ownership manifest to be scoped."""
    attribution = steps.ToolFailureAttribution(frozenset({steps.IDENTITY_FAILURE}), ())
    assert steps.provisional_identity_tool_failures((), (), attribution) == Err(
        ABSENT_TEXT
    )
    assert isinstance(
        steps.provisional_identity_tool_failures((BROKEN,), (), attribution), Err
    )


def test_finalizer_localization_requires_an_unavailable_native_observation() -> None:
    """A localized native finalizer must have been the sole unavailable evidence."""
    observed = (phase_reports.PhaseResult(0, "a" * 64, frozenset({"unverified-run"})),)
    statuses = tuple((name, 0) for name in steps.FINALIZER_NAMES)
    assert steps.provisional_finalizer_failures(
        Ok(observed), statuses, localized_native=True
    ) == Err("invalid localized native finalizer")


def test_collection_reports_each_failure_without_a_verdict(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Collection failures are echoed per phase and counted for the exit status."""
    result = Ok(((0, frozenset({"b", "a"})), (1, frozenset())))
    assert steps.report_collection(result) == 1
    lines = capsys.readouterr().err.splitlines()
    assert lines == [
        "collection-observation phase 0: a (not a verdict)",
        "collection-observation phase 0: b (not a verdict)",
    ]
    assert steps.report_collection(Ok(((0, frozenset()),))) == 0
