# Copyright (c) 2026 agentctl contributors.
"""Defensive refusals of the recorded snapshots, absence and artifact readers."""

import os
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import override

import pytest

from agentctl.check import evidence, steps
from agentctl.check.legs import Leg
from agentctl.foundation import Err, Ok
from agentctl.foundation_process_values import Output

pytestmark = pytest.mark.evidence("value")
NONCE = "abc123"
FAILED_STATUS = 1
SHA256 = "0" * 64
SUFFIX = ".racer"


def _linking_open(real: Callable[..., int], victim: Path) -> Callable[..., int]:
    """Delegate to the real open, then add a second link to the victim record."""

    def racing(path: str | Path, flags: int, *args: int, **kwargs: int) -> int:
        descriptor = real(path, flags, *args, **kwargs)
        if Path(path) == victim:
            os.link(victim, victim.with_name(victim.name + SUFFIX))
        return descriptor

    return racing


def _commands() -> tuple[tuple[str, tuple[tuple[str, ...], ...]], ...]:
    return tuple((name, (("python", name),)) for name in steps.PYTHON_COMMAND_NAMES)


def test_coverage_text_recording_refuses_races_and_existing_records(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A record that gains a link or already exists is a structured refusal."""
    snapshot = steps.CoverageTextSnapshot(
        NONCE,
        tmp_path,
        ("coverage", "report"),
        Output(
            0,
            "Name   Stmts\nTOTAL   1   0   100%\n",
            "",
        ),
    )
    target = tmp_path / "coverage-text.json"
    with monkeypatch.context() as patch:
        patch.setattr(steps.os, "open", _linking_open(os.open, target))
        raced = steps.record_coverage_text(tmp_path, snapshot)
    assert raced == Err("coverage text changed during recording")
    existing = steps.record_coverage_text(tmp_path, snapshot)
    assert isinstance(existing, Err)
    assert existing.error.startswith("cannot record coverage text: ")


def test_ruff_recording_refuses_names_snapshots_races_and_existing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ruff records need a known name, a valid snapshot and an exclusive file."""
    snapshot = steps.RuffSnapshot(NONCE, tmp_path, Output(0, "[]", ""), ())
    assert steps.record_ruff_snapshot(tmp_path, snapshot, filename="other.json") == Err(
        "invalid Ruff record name"
    )
    assert steps.record_ruff_snapshot(
        tmp_path, steps.RuffSnapshot("", tmp_path, Output(0, "[]", ""), ())
    ) == Err("invalid Ruff snapshot")
    target = tmp_path / "ruff-observation.json"
    with monkeypatch.context() as patch:
        patch.setattr(steps.os, "open", _linking_open(os.open, target))
        raced = steps.record_ruff_snapshot(tmp_path, snapshot)
    assert raced == Err("Ruff observation changed during recording")


def test_python_command_recording_refuses_identity_races(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Command records refuse invalid identity and a record that gains a link."""
    assert steps.record_python_commands(
        tmp_path, "", tmp_path, _commands(), SHA256
    ) == Err("invalid Python command observation")
    target = tmp_path / "python-commands.json"
    with monkeypatch.context() as patch:
        patch.setattr(steps.os, "open", _linking_open(os.open, target))
        raced = steps.record_python_commands(
            tmp_path, NONCE, tmp_path, _commands(), SHA256
        )
    assert raced == Err("Python command observation changed during recording")
    existing = steps.record_python_commands(
        tmp_path, NONCE, tmp_path, _commands(), SHA256
    )
    assert isinstance(existing, Err)
    assert existing.error.startswith("cannot record Python commands: ")


def test_unchanged_checks_refuse_records_that_vanish(tmp_path: Path) -> None:
    """A recorded file that disappears is reported as a changed capture."""
    text = steps.record_coverage_text(
        tmp_path,
        steps.CoverageTextSnapshot(
            NONCE, tmp_path, ("coverage",), Output(0, "TOTAL   1   0   100%\n", "")
        ),
    )
    ty = steps.record_ty_snapshot(
        tmp_path, steps.TySnapshot(NONCE, tmp_path, Output(0, "[]", ""), ())
    )
    ruff = steps.record_ruff_snapshot(
        tmp_path, steps.RuffSnapshot(NONCE, tmp_path, Output(0, "[]", ""), ())
    )
    commands = steps.record_python_commands(
        tmp_path, NONCE, tmp_path, _commands(), SHA256
    )
    assert isinstance(text, Ok)
    assert isinstance(ty, Ok)
    assert isinstance(ruff, Ok)
    assert isinstance(commands, Ok)
    for name in (
        "coverage-text.json",
        "ty-observation.json",
        "ruff-observation.json",
        "python-commands.json",
    ):
        (tmp_path / name).unlink()
    assert steps.coverage_text_unchanged(tmp_path, NONCE, text) == FAILED_STATUS
    assert steps.ty_snapshot_unchanged(tmp_path, NONCE, ty) == FAILED_STATUS
    assert steps.ruff_snapshot_unchanged(tmp_path, NONCE, ruff) == FAILED_STATUS
    assert (
        steps.python_commands_unchanged(tmp_path, NONCE, tmp_path, commands)
        == FAILED_STATUS
    )


def test_python_command_capture_needs_a_source_census(tmp_path: Path) -> None:
    """A failed source census prevents binding commands to source bytes."""
    context = steps.CheckRun(tmp_path, tmp_path, NONCE, "Linux")
    assert steps.__dict__["_capture_python_commands"](
        context, Err("no census"), _commands()
    ) == Err("Python command source census unavailable")
    duplicated = (
        evidence.Entry("src", "directory", ()),
        evidence.Entry("src", "directory", ()),
    )
    assert steps.__dict__["_capture_python_commands"](
        context, Ok(duplicated), _commands()
    ) == Err("Python command source digest unavailable")


def test_failed_native_step_with_a_report_records_no_absence(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """An existing report keeps a failed native step from being called absent."""
    root, run_dir = tmp_path / "checkout", tmp_path / "run"
    root.mkdir()
    run_dir.mkdir()
    (run_dir / "tasty.xml").write_text("partial", encoding="utf-8")
    host = steps.hostfacts.current(tmp_path / "empty-cache")
    leg = steps.haskell.HaskellStep("cabal-test", host, root / "missing-project")
    code, marker = steps.__dict__["_run_native_step_with_absence"](leg, run_dir, NONCE)
    assert code == FAILED_STATUS
    assert marker is None
    assert steps.NATIVE_ABSENCE_OBSERVATION not in capsys.readouterr().out


def test_tool_substep_record_must_match_the_legs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A leg reporting more subprocess statuses than scheduled is refused."""

    def short_leg(*_args: object) -> steps.LegOutcome:
        return steps.LegOutcome(0, (0, 0))

    monkeypatch.setattr(steps, "_run_leg_observed", short_leg)
    leg = Leg("later", ("unused",))
    observed = steps.__dict__["_run_tools_observed"](tmp_path, tmp_path, NONCE, (leg,))
    assert observed.code == FAILED_STATUS
    assert observed.substeps == Err("tool substep record changed")
    assert isinstance(observed.evidence, Ok)


def _swapping(victim: Path) -> tuple[str, ...]:
    """Names whose iteration replaces the observed directory."""

    class Swapping(tuple[str, ...]):
        __slots__ = ()

        @override
        def __iter__(self) -> Iterator[str]:
            victim.rename(victim.with_name(victim.name + ".old"))
            victim.mkdir()
            return iter(())

    return Swapping(("tasty.xml",))


def test_native_absence_refuses_unusable_directories(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Missing, non-directory and replaced run directories are not absence."""
    absent = steps.native_absence_observation
    assert absent(tmp_path / "missing", NONCE, FAILED_STATUS) == Err(
        "native absence cannot be observed"
    )
    plain = tmp_path / "plain"
    plain.write_text("x", encoding="utf-8")
    assert absent(plain, NONCE, FAILED_STATUS) == Err(
        "native absence directory unavailable"
    )
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    monkeypatch.setattr(steps, "NATIVE_REPORT_FILES", _swapping(run_dir))
    assert absent(run_dir, NONCE, FAILED_STATUS) == Err(
        "native absence directory changed"
    )


def test_native_artifact_record_refusals(tmp_path: Path) -> None:
    """An absent record is empty, but a linked record or bad rows are refused."""
    reader = steps.native_artifact_record
    assert reader(tmp_path, NONCE) == Ok(())
    target = tmp_path / "elsewhere.json"
    target.write_text("{}", encoding="utf-8")
    (tmp_path / "native-artifacts.json").symlink_to(target)
    assert reader(tmp_path, NONCE) == Err("native artifact record unavailable")
    rows = steps.__dict__["_parse_native_artifact_rows"]
    assert rows("not rows") == Err("invalid native artifact observations")
