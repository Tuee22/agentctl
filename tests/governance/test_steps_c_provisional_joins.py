# Copyright (c) 2026 agentctl contributors.
"""Provisional phase joins refuse unavailable, unsealed or disagreeing inputs."""

from collections.abc import Callable
from pathlib import Path

import pytest

from agentctl.check import evidence, steps
from agentctl.check.evidence import Entry, LegEvidence
from agentctl.check.mutants import Mutant
from agentctl.check.steps import CheckRun, ProvisionalCapture, ToolOutcome
from agentctl.result import Err, Ok, Result

pytestmark = pytest.mark.evidence("value")

NONCE = "c" * 32
Verify = Callable[[CheckRun, Path, str], Result[None, str]]


def _finalizers(
    monkeypatch: pytest.MonkeyPatch, *, failing: tuple[str, ...] = ()
) -> None:
    observed = LegEvidence(
        NONCE,
        tuple((name, int(name in failing)) for name in steps.FINALIZER_NAMES[:-1]),
    )
    monkeypatch.setattr(
        steps, "sealed_finalizer_observation", lambda *_args: Ok(observed)
    )


def _values(monkeypatch: pytest.MonkeyPatch, value: object) -> None:
    monkeypatch.setattr(steps, "_provisional_values_for_identity", lambda *_args: value)


def _supporting(monkeypatch: pytest.MonkeyPatch, verdict: Result[None, str]) -> None:
    for name in (
        "verify_python_commands_handoff",
        "verify_tool_results_handoff",
        "verify_provisional_collection",
        "_verify_provisional_census",
    ):
        monkeypatch.setattr(steps, name, lambda *_args, _v=verdict: _v)


def _consumers() -> tuple[tuple[str, Verify], ...]:
    return (
        ("phase static supporting handoff is invalid", steps.verify_provisional_static),
        ("phase source supporting handoff is invalid", steps.verify_provisional_source),
        (
            "phase prerequisite supporting handoff is invalid",
            steps.verify_provisional_prerequisites,
        ),
        (
            "phase validation supporting handoff is invalid",
            steps.verify_provisional_validation,
        ),
    )


def test_provisional_consumers_pass_identity_failures_through(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An unavailable or absent provisional record decides each consumer."""
    context = CheckRun(tmp_path, tmp_path, NONCE, "Linux")
    _finalizers(monkeypatch)
    for _message, verify in _consumers():
        _values(monkeypatch, Err("identity unavailable"))
        assert verify(context, tmp_path, "") == Err("identity unavailable")
        _values(monkeypatch, Ok(None))
        assert verify(context, tmp_path, "") == Ok(None)


def test_provisional_consumers_refuse_invalid_supporting_handoffs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every consumer rejects a failed supporting handoff."""
    context = CheckRun(tmp_path, tmp_path, NONCE, "Linux")
    _finalizers(monkeypatch)
    _values(monkeypatch, Ok(()))
    _supporting(monkeypatch, Err("broken"))
    for message, verify in _consumers():
        assert verify(context, tmp_path, "") == Err(message)


def test_static_inputs_need_a_readable_phase_plan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A census naming an unreadable phase source is not static input."""
    context = CheckRun(tmp_path, tmp_path, NONCE, "Linux")
    broken = Entry("DEVELOPMENT_PLAN/phase-0-x.md", "directory", (b"",))
    monkeypatch.setattr(steps, "_parent_bound_census", lambda *_args: Ok((broken,)))
    sealed = (LegEvidence(NONCE, ()), evidence.ToolSubsteps(NONCE, ()))
    monkeypatch.setattr(steps, "_read_sealed_tool_results", lambda *_args: Ok(sealed))
    result = steps.__dict__["_parent_static_inputs"](context, tmp_path, "")
    assert isinstance(result, Err)
    assert result.error.startswith("census declaration is not a regular file")


def _capture(
    census: Result[tuple[Entry, ...], str],
    claims: tuple[tuple[Mutant, ...], tuple[tuple[str, int], ...]] | None,
) -> ProvisionalCapture:
    tools = ToolOutcome(0, Err("unused"), Err("unused"))
    return ProvisionalCapture(
        census,
        Ok(()),
        tools,
        claims,
        Ok(()),
        NONCE,
        (),
        (),
    )


def test_validation_problems_require_complete_captured_inputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Shared validators need collection inputs, a census and agreeing owners."""
    checkout = tmp_path / "checkout"
    (checkout / "src" / "agentctl").mkdir(parents=True)
    (checkout / "tests").mkdir()
    (checkout / "src" / "agentctl" / "x.py").write_text("", encoding="utf-8")
    context = CheckRun(checkout, tmp_path, NONCE, "Linux")
    problems = steps.__dict__["_parent_validation_problems"]
    monkeypatch.setattr(
        steps, "_parent_collection_capture", lambda *_args: Err("unavailable")
    )
    assert problems(context, tmp_path, "") == Err("phase validation inputs unavailable")
    monkeypatch.setattr(
        steps,
        "_parent_collection_capture",
        lambda *_args: Ok(((), _capture(Err("no census"), ((), ())))),
    )
    assert problems(context, tmp_path, "") == Err(
        "phase validation census or claims unavailable"
    )
    monkeypatch.setattr(
        steps,
        "_parent_collection_capture",
        lambda *_args: Ok(((), _capture(Ok(()), None))),
    )
    assert problems(context, tmp_path, "") == Err(
        "phase validation census or claims unavailable"
    )
    monkeypatch.setattr(
        steps,
        "_parent_collection_capture",
        lambda *_args: Ok(((), _capture(Ok(()), ((), (("missing", 0),))))),
    )
    assert problems(context, tmp_path, "") == Err(
        "phase validation mutant ownership differs"
    )


def test_validation_problems_report_unreadable_closure_inputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A closure input that cannot be read becomes a validator finding."""
    checkout = tmp_path / "checkout"
    (checkout / "src" / "agentctl").mkdir(parents=True)
    (checkout / "tests").mkdir()
    (checkout / "src" / "agentctl" / "x.py").write_text("", encoding="utf-8")
    context = CheckRun(checkout, tmp_path, NONCE, "Linux")
    census = steps.ownership.guarded_census(checkout)
    assert isinstance(census, Ok)
    monkeypatch.setattr(steps, "complete_mutant_owners", lambda *_args: Ok(()))
    capture = _capture(Ok(census.value), ((), ()))
    monkeypatch.setattr(
        steps, "_parent_collection_capture", lambda *_args: Ok(((), capture))
    )
    monkeypatch.setattr(steps, "_parent_bound_census", lambda *_args: Ok(census.value))

    def unreadable(*_args: object, **_kwargs: object) -> tuple[str, ...]:
        message = "closure input is unreadable"
        raise OSError(message)

    monkeypatch.setattr(steps.closure, "static", unreadable)
    result = steps.__dict__["_parent_validation_problems"](context, tmp_path, "")
    assert isinstance(result, Ok)
    assert any("cannot read closure inputs" in item for item in result.value)
