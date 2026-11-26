# Copyright (c) 2026 agentctl contributors.
"""Real-file races and process failures at the last measured defensive branches."""

import hashlib
import os
import signal
import sys
from pathlib import Path
from typing import BinaryIO, Self

import pytest

from agentctl.bootstrap import build
from agentctl.check import haskell, steps
from agentctl.check.phase_reports import join_results
from agentctl.check.steps import TySnapshot
from agentctl.foundation_process import foreground, replace
from agentctl.process import Output
from agentctl.result import Err, Ok
from tests.governance.test_cover_g_haskell import _fixture

pytestmark = pytest.mark.evidence("value")
APPENDED = b"changed"
CHILD_SECONDS = 0.5


class _Replacing:
    """A real stream whose owner swaps the file for a link when it closes."""

    def __init__(self, stream: BinaryIO, path: Path, target: Path) -> None:
        self.stream = stream
        self.path = path
        self.target = target

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.stream.close()
        self.path.unlink()
        self.path.symlink_to(self.target)

    def write(self, data: bytes) -> int:
        return self.stream.write(data)


def test_native_artifact_changing_during_inspection_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A tool whose bytes change between the stat and digest reads is refused."""
    fixture = _fixture(tmp_path)

    def altering(stream: BinaryIO, algorithm: str) -> object:
        digest = hashlib.new(algorithm, stream.read())
        with Path(stream.name).open("ab") as handle:
            handle.write(APPENDED)
        return digest

    with monkeypatch.context() as scope:
        scope.setattr(haskell.hashlib, "file_digest", altering)
        result = haskell.native_artifact_facts(fixture.context)
    assert result == Err(build.BuildError("Native artifact changed during inspection"))


def test_foreground_refuses_an_unlaunchable_child(tmp_path: Path) -> None:
    """A child that cannot start is a typed failure."""
    result = foreground(["agentctl-absent-executable"], cwd=tmp_path, env={})
    assert isinstance(result, Err)


def test_readiness_observation_refuses_invalid_messages(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """An empty nonce is refused and reported on the error stream."""
    assert steps.readiness_observation("", ("message",)) == Err(
        "invalid readiness observation"
    )
    assert steps.emit_readiness_observation("", ("message",), 0) == 1
    assert "invalid readiness observation" in capsys.readouterr().err


def test_ty_record_replaced_after_writing_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A second hard link added during recording changes the record identity."""
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    real = os.open

    def linking(path: Path, flags: int, mode: int = 0o777) -> int:
        descriptor = real(path, flags, mode)
        os.link(path, run_dir / "alias")
        return descriptor

    snapshot = TySnapshot("nonce", tmp_path.resolve(), Output(0, "[]", ""), ())
    with monkeypatch.context() as scope:
        scope.setattr(steps.os, "open", linking)
        result = steps.record_ty_snapshot(run_dir, snapshot)
    assert result == Err("ty observation changed during recording")


def test_provisional_record_replaced_after_writing_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A record replaced by a link while closing is not accepted."""
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    elsewhere = tmp_path / "elsewhere"
    elsewhere.write_bytes(b"other")
    real = os.fdopen

    def replacing(descriptor: int, mode: str) -> _Replacing:
        assert mode == "wb"
        return _Replacing(
            real(descriptor, "wb"), run_dir / "provisional-phases.json", elsewhere
        )

    with monkeypatch.context() as scope:
        scope.setattr(steps.os, "fdopen", replacing)
        result = steps.record_provisional_phases(run_dir, "nonce", Err("unavailable"))
    assert result == Err("provisional phase record changed during recording")


def test_join_results_keeps_the_first_error() -> None:
    """Two successes pair their values; otherwise the first error wins."""
    assert join_results(Ok(1), Ok("two")) == Ok((1, "two"))
    assert join_results(Err("first"), Err("second")) == Err("first")
    assert join_results(Ok(1), Err("second")) == Err("second")


def test_foreground_survives_an_interrupt_while_waiting(tmp_path: Path) -> None:
    """A console interrupt delivered once the child runs does not abandon it."""
    program = "; ".join(
        (
            "import os, signal, time",
            "os.kill(os.getppid(), signal.SIGINT)",
            f"time.sleep({CHILD_SECONDS})",
        )
    )
    previous = signal.signal(signal.SIGINT, signal.default_int_handler)
    try:
        result = foreground(
            [sys.executable, "-c", program], cwd=tmp_path, env=os.environ
        )
    finally:
        signal.signal(signal.SIGINT, previous)
    assert result == Ok(0)


def test_replace_refuses_an_unlaunchable_program() -> None:
    """A failed exec returns a typed error instead of replacing the process."""
    result = replace(["/agentctl-absent-program"], env={})
    assert isinstance(result, Err)
