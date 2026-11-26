# Copyright (c) 2026 agentctl contributors.
"""Report retention, interpreter identity and candidate handoff refusals."""

import hashlib
import os
import sys
import tempfile
from dataclasses import replace
from io import BufferedReader
from pathlib import Path

import pytest

from agentctl.check import lanes, mutant_report, steps
from agentctl.check.evidence import RunEvidence
from agentctl.check.steps import (
    CheckRun,
    GateInterpreterIdentity,
    ReceiptInputs,
    RetainedGateReport,
    RetainedReportSnapshot,
)
from agentctl.foundation_process_values import (
    Output,
    ProcessImageFile,
    ProcessObservation,
)
from agentctl.result import Err, Ok

pytestmark = pytest.mark.evidence("value")

NONCE = "abcdef0123456789abcdef0123456789"
STREAMS = ("out", "err")


def _report_directory(root: Path) -> Path:
    """Create one retained report with its two output streams."""
    directory = root / "check-reports" / NONCE
    directory.mkdir(parents=True)
    (directory / "stdout.txt").write_bytes(STREAMS[0].encode())
    (directory / "stderr.txt").write_bytes(STREAMS[1].encode())
    return directory


def _identity(path: Path) -> GateInterpreterIdentity:
    observed = steps.gate_interpreter_identity(path)
    assert isinstance(observed, Ok)
    return observed.value


def _image(identity: GateInterpreterIdentity) -> ProcessImageFile:
    return ProcessImageFile(
        identity.device,
        identity.inode,
        identity.size,
        identity.modified_ns,
        identity.sha256,
    )


def test_stream_and_artifact_snapshots_refuse_unstable_reports(tmp_path: Path) -> None:
    """Linked streams, non-directories and mutating directories are refused."""
    directory = _report_directory(tmp_path)
    os.link(directory / "stdout.txt", tmp_path / "alias")
    assert steps.retained_stream_snapshot(directory) == Err(
        "retained output streams changed"
    )
    plain = tmp_path / "plain"
    plain.write_bytes(b"x")
    assert steps.retained_artifact_snapshot(plain) == Err(
        "retained report directory unavailable"
    )
    assert steps.retained_artifact_snapshot(tmp_path / "absent") == Err(
        "retained report artifacts unavailable"
    )


def test_artifact_snapshot_refuses_a_directory_that_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A file appearing during the walk invalidates the captured listing."""
    directory = tmp_path / "report"
    directory.mkdir()
    (directory / "one.json").write_bytes(b"{}")
    original = steps.__dict__["_read_provisional_handoff"]

    def growing(path: Path) -> object:
        result = original(path)
        (path.parent / "late.json").write_bytes(b"{}")
        return result

    monkeypatch.setattr(steps, "_read_provisional_handoff", growing)
    assert steps.retained_artifact_snapshot(directory) == Err(
        "retained report directory changed"
    )


def test_interpreter_identity_refuses_unstable_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Directories, absent files and files touched while hashed are refused."""
    assert steps.gate_interpreter_identity(tmp_path) == Err(
        "gate interpreter is not a regular file"
    )
    missing = steps.gate_interpreter_identity(tmp_path / "absent")
    assert isinstance(missing, Err)
    assert missing.error.startswith("cannot observe gate interpreter")
    target = tmp_path / "interpreter"
    target.write_bytes(b"binary")
    original = hashlib.file_digest

    def touching(stream: BufferedReader, algorithm: str) -> object:
        digest = original(stream, algorithm)
        os.utime(target, ns=(1, 1))
        return digest

    monkeypatch.setattr(hashlib, "file_digest", touching)
    assert steps.gate_interpreter_identity(target) == Err(
        "gate interpreter changed during observation"
    )


def test_interpreter_record_detects_tampering(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The runtime record is refused when its stored bytes are altered."""
    selected = Path(sys.executable)
    initial = steps.gate_interpreter_identity(selected)
    original = steps.__dict__["_read_provisional_handoff"]

    def tampered(path: Path) -> object:
        path.write_bytes(b"other")
        return original(path)

    monkeypatch.setattr(steps, "_read_provisional_handoff", tampered)
    assert steps.record_gate_interpreter(tmp_path, NONCE, selected, initial) == Err(
        "gate interpreter record changed"
    )


def test_retained_gate_records_need_a_snapshot() -> None:
    """The retained joins refuse a report without a verified snapshot."""
    report = RetainedGateReport(Path(), None)
    assert steps.retained_gate_interpreter(report, b"x") == Err(
        "retained gate interpreter snapshot unavailable"
    )
    assert steps.retained_gate_child(report, b"x") == Err(
        "retained gate child snapshot unavailable"
    )


def _child_context(tmp_path: Path) -> tuple[CheckRun, GateInterpreterIdentity]:
    root = tmp_path / "checkout"
    root.mkdir()
    run = tmp_path / "run"
    run.mkdir()
    return CheckRun(root, run, "abc123", "Linux"), _identity(Path(sys.executable))


def test_gate_child_record_refuses_unusable_storage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The child record needs a nonce, a comparable image and exclusive storage."""
    context, selected = _child_context(tmp_path)
    image = ProcessObservation(
        "Linux", os.getpid() + 1, 1, selected.path, _image(selected)
    )
    output = Ok(Output(0, "", "", observation=Ok(image)))
    assert steps.record_gate_child(
        replace(context, nonce=""), output, Ok(selected)
    ) == Err("gate child image nonce unavailable")
    vanished = replace(image, image=tmp_path / "vanished")
    assert steps.record_gate_child(
        context, Ok(Output(0, "", "", observation=Ok(vanished))), Ok(selected)
    ) == Err("cannot compare gate child image")
    (context.directory / "python-child.json").write_bytes(b"old")
    exists = steps.record_gate_child(context, output, Ok(selected))
    assert isinstance(exists, Err)
    assert exists.error.startswith("cannot record gate child image")
    (context.directory / "python-child.json").unlink()
    original = steps.__dict__["_read_provisional_handoff"]

    def tampered(path: Path) -> object:
        path.write_bytes(b"other")
        return original(path)

    monkeypatch.setattr(steps, "_read_provisional_handoff", tampered)
    assert steps.record_gate_child(context, output, Ok(selected)) == Err(
        "gate child image record changed"
    )


def _receipt_inputs(nonce: str) -> ReceiptInputs:
    host = lanes.HostFacts("Linux", "x86_64", checkout=True, git=True, debian=True)
    python = RunEvidence(nonce, frozenset(), frozenset(), frozenset(), (), ())
    return ReceiptInputs(
        nonce,
        "0" * 64,
        (),
        (),
        host,
        python,
        None,
        mutant_report.Report(nonce, (), "digest"),
        (),
        (),
        (),
    )


def test_phase_candidates_need_a_nonce() -> None:
    """The provisional candidate record is not encoded without a run nonce."""
    selected = _identity(Path(sys.executable))
    assert steps.phase_candidate_record(_receipt_inputs(""), (), selected) == Err(
        "invalid phase candidate inputs"
    )


def test_phase_candidate_retention_refuses_unstable_reports(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Retaining candidates needs a snapshot and a record that survives rereading."""
    root = tmp_path / "checkout"
    root.mkdir()
    state = tmp_path / "state"
    directory = _report_directory(state)
    context = CheckRun(root, tmp_path, NONCE, "Linux")
    snapshot = steps.retained_report_snapshot(directory, STREAMS)
    assert isinstance(snapshot, Ok)
    report = RetainedGateReport(directory, snapshot.value)
    unavailable = Err("phase candidate snapshot or record unavailable")
    assert (
        steps.retain_phase_candidates(
            context, state, RetainedGateReport(directory, None), STREAMS, b"x"
        )
        == unavailable
    )
    assert (
        steps.retain_phase_candidates(context, state, report, STREAMS, b"")
        == unavailable
    )
    original = steps.__dict__["_read_provisional_handoff"]

    def tampered(path: Path) -> object:
        if path.name == "phase-candidates.json":
            path.write_bytes(b"other")
        return original(path)

    monkeypatch.setattr(steps, "_read_provisional_handoff", tampered)
    assert steps.retain_phase_candidates(context, state, report, STREAMS, b"x") == Err(
        "phase candidate record changed during retention"
    )
    (directory / "phase-candidates.json").unlink()
    monkeypatch.setattr(steps, "_read_provisional_handoff", original)
    stale = RetainedGateReport(
        directory, RetainedReportSnapshot(snapshot.value.streams, (("x", 1, 1, "d"),))
    )
    assert steps.retain_phase_candidates(context, state, stale, STREAMS, b"x") == Err(
        "phase candidate report boundary or snapshot differs"
    )
    (directory / "phase-candidates.json").unlink(missing_ok=True)
    monkeypatch.setattr(
        steps, "retained_report_snapshot", lambda *_args: _first(snapshot)
    )
    result = steps.retain_phase_candidates(context, state, report, STREAMS, b"x")
    assert result == Err("phase candidate report changed during retention")
    (directory / "phase-candidates.json").unlink()
    missing = steps.retain_phase_candidates(
        context, tmp_path / "absent", report, STREAMS, b"x"
    )
    assert isinstance(missing, Err)
    assert missing.error.startswith("cannot retain phase candidates")


def _first(snapshot: Ok[RetainedReportSnapshot]) -> Ok[RetainedReportSnapshot]:
    return snapshot


def test_check_reports_temporary_storage_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """An unusable temporary directory is a refusal before any child starts."""
    private = tmp_path / "home"
    private.mkdir()
    for name in ("HOME", "XDG_STATE_HOME", "XDG_CACHE_HOME", "XDG_CONFIG_HOME"):
        monkeypatch.setenv(name, str(private))
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    monkeypatch.chdir(checkout)
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path / "absent"))
    assert steps.check("Linux") == 1
    assert "temporary storage failure" in capsys.readouterr().err


def test_execute_reports_an_unreadable_write_guard(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A checkout the write guard cannot snapshot stops the run."""
    monkeypatch.setattr(steps, "inspect_context", lambda *_args: ())
    assert steps.execute(tmp_path / "absent", tmp_path, NONCE, "Linux") == 1
    assert capsys.readouterr().err
