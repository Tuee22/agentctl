# Copyright (c) 2026 agentctl contributors.
"""The validator phase of the gate reports closure policy, ownership and read damage."""

from pathlib import Path

import pytest

from agentctl.check import ownership, steps
from agentctl.check.evidence import Entry
from agentctl.check.plan_data import Phase, phase_text
from agentctl.check.validator import closure
from agentctl.result import Err, Ok

pytestmark = pytest.mark.evidence("value")
NONCE = "nonce"
TEST_PATH = "tests/test_early.py"
EMPTY_FINDINGS = ("docs", "plan", "forbidden_surfaces", "configuration")
NO_FINDINGS = (
    "source_ownership_problems",
    "test_consumer_problems",
    "coverage_host_problems",
    "phase0_claim_problems",
    "fragment_claim_problems",
    "source_observations",
)


class _PipelineReachedError(Exception):
    """Raised by the planned-pipeline stand-in once validators have reported."""


def _phase() -> Phase:
    parsed = phase_text(
        Path("phase-0-example.md"),
        f"### Sprint 0.1: Test [Active]\n**Validation tests**: `{TEST_PATH}::case`\n"
        "## Remaining Work\n",
    )
    assert parsed is not None
    return parsed


def _stop(*_args: object, **_kwargs: object) -> tuple[()]:
    raise _PipelineReachedError


def _constant(value: object) -> object:
    return lambda *_args, **_kwargs: value


def _prepare(patch: pytest.MonkeyPatch) -> None:
    entries = (Entry("src", "directory", (b"",)),)
    patch.setattr(steps, "targets", _constant(Ok(("src/x.py",))))
    patch.setattr(ownership, "guarded_census", _constant(Ok(entries)))
    patch.setattr(steps, "census_phases", _constant(Ok((_phase(),))))
    patch.setattr(steps, "python_target_census", _constant(Ok(None)))
    patch.setattr(steps, "report_scoped_source_inputs", _constant(None))
    for name in (*EMPTY_FINDINGS, *NO_FINDINGS):
        patch.setattr(steps, name, _constant(()))
    patch.setattr(steps, "census_corpus", _constant(Ok(())))
    patch.setattr(steps, "_source_guard_observations", _constant(()))
    patch.setattr(steps, "oracle_check", _constant(0))
    patch.setattr(steps, "oracle_observation", _constant(Err("oracle")))
    patch.setattr(steps.evidence, "read_oracle_details", _constant(Err("details")))
    patch.setattr(steps, "report_oracle_diagnostics", _constant(Ok(())))
    patch.setattr(steps, "oracle_details_unchanged", _constant(0))
    patch.setattr(steps, "pipeline", _stop)
    patch.setattr(steps, "complete_mutant_owners", _constant(Ok(())))
    patch.setattr(
        steps, "census_policy", _constant(Ok(closure.CapturedPolicy((), "", "")))
    )
    patch.setattr(closure, "static", _constant(()))
    patch.setattr(closure, "inapplicable", _constant(("subject",)))


def _validate(tmp_path: Path) -> None:
    context = steps.CheckRun(tmp_path, tmp_path, NONCE, "Linux")
    with pytest.raises(_PipelineReachedError):
        steps.__dict__["_validate_and_observe"](context)


def test_clean_validators_report_inapplicable_subjects(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """With no findings, Planned-owner subjects are reported as not applicable."""
    _prepare(monkeypatch)
    _validate(tmp_path)
    captured = capsys.readouterr()
    assert captured.out == "validators: not applicable: subject (owner Planned)\n"
    assert captured.err == ""


def test_scoped_ownership_failures_are_echoed_as_observations(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Incomplete mutant ownership still reports each phase-scoped failure."""
    _prepare(monkeypatch)
    scopes = (ownership.MutantScope(0, ("unowned mutant",)),)
    monkeypatch.setattr(steps, "complete_mutant_owners", _constant(Err("incomplete")))
    monkeypatch.setattr(
        steps, "provisional_or_scoped_mutant_owners", _constant(Err("incomplete"))
    )
    monkeypatch.setattr(steps, "scoped_mutant_ownership", _constant(Ok(scopes)))
    _validate(tmp_path)
    error = capsys.readouterr().err
    assert (
        "ownership-observation phase 0: unowned mutant (not a verdict)"
        in error.splitlines()
    )
    assert "validators: complete mutant ownership: incomplete" in error


def test_unreadable_closure_inputs_are_reported(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """An operating-system failure while reading closure inputs is a finding."""

    def unreadable(*_args: object, **_kwargs: object) -> tuple[str, ...]:
        message = "denied"
        raise OSError(message)

    _prepare(monkeypatch)
    monkeypatch.setattr(closure, "static", unreadable)
    _validate(tmp_path)
    assert (
        "validators: cannot read closure inputs: denied"
        in capsys.readouterr().err.splitlines()
    )
