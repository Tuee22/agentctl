# Copyright (c) 2026 agentctl contributors.
"""Provisional, finalizer and killer handoff records refuse altered evidence."""

import json
import os
import sys
from pathlib import Path

import pytest

from agentctl.check import steps
from agentctl.foundation import Err, Ok
from agentctl.foundation_process_values import Output
from agentctl.process import run
from tests.harness.workspace import _cleanup_path, cleanup_workspace

pytestmark = pytest.mark.evidence("real")

NONCE = "abc123"
PASSING = tuple((name, 0) for name in steps.FINALIZER_NAMES[:-1])


def test_native_workspace_cleanup_handles_long_paths_and_boundaries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Delete only the owned root, including native paths beyond Windows MAX_PATH."""
    root = (tmp_path / "b-owned").resolve()
    root.mkdir()
    original = root.lstat()
    identity = (original.st_dev, original.st_ino)
    other = tmp_path / "other"
    other.mkdir()
    assert _cleanup_path(root, windows=True).startswith("\\\\?\\"), (
        "long native cleanup path was not extended"
    )
    assert _cleanup_path(Path(r"\\server\share\owned"), windows=True) == (
        r"\\?\UNC\server\share\owned"
    ), "UNC native cleanup path was not extended"
    with monkeypatch.context() as control:
        removed: list[str] = []
        control.setattr("tests.harness.workspace.shutil.rmtree", removed.append)
        other_stat = other.lstat()
        for target, parent, token in (
            (root, other, identity),
            (root, tmp_path, (identity[0], identity[1] + 1)),
            (other, tmp_path, (other_stat.st_dev, other_stat.st_ino)),
        ):
            try:
                cleanup_workspace(target, parent, token)
            except OSError:
                pass
            else:
                pytest.fail("foreign workspace boundary was accepted")
        assert not removed, "foreign workspace was removed"
    nested = root.joinpath(
        *("native-build-" + str(number) + "x" * 48 for number in range(6))
    )
    Path(_cleanup_path(nested, windows=os.name == "nt")).mkdir(parents=True)
    Path(_cleanup_path(nested / "artifact.o", windows=os.name == "nt")).write_bytes(
        b"owned native output"
    )
    cleanup_workspace(root, tmp_path.resolve(), identity)
    assert not root.exists(), "long-path workspace cleanup was incomplete"


def test_ty_diagnostics_refuse_incomplete_or_foreign_values(tmp_path: Path) -> None:
    """Only complete current-checkout type diagnostics can be attributed."""
    source = tmp_path / "src/subject.py"
    row = {
        "check_name": "invalid-assignment",
        "description": "incompatible value",
        "severity": "major",
        "location": {"path": str(source), "positions": {"begin": {"line": 1}}},
    }
    encoded = json.dumps([row])
    assert isinstance(steps.parse_ty_output(tmp_path, Output(1, encoded, "")), Ok)
    relative = {**row, "location": {**row["location"], "path": "src/subject.py"}}
    assert isinstance(
        steps.parse_ty_output(tmp_path, Output(1, json.dumps([relative]), "")), Ok
    )
    assert steps.parse_ty_output(tmp_path, Output(0, "[]", "")) == Ok(())
    for output in (
        Output(0, encoded, ""),
        Output(1, "[]", ""),
        Output(2, encoded, ""),
        Output(1, encoded, "unexplained error"),
        Output(1, "not-json", ""),
        Output(1, json.dumps([{**row, "severity": []}]), ""),
        Output(1, json.dumps([{**row, "location": {"path": "relative.py"}}]), ""),
        Output(
            1,
            json.dumps(
                [
                    {
                        **relative,
                        "location": {**relative["location"], "path": "../foreign.py"},
                    }
                ]
            ),
            "",
        ),
        Output(
            1, encoded.replace('"severity":', '"severity": "major", "severity":'), ""
        ),
    ):
        assert isinstance(steps.parse_ty_output(tmp_path, output), Err), (
            "invalid type diagnostic was accepted"
        )


def test_parent_evidence_requires_verified_retention_and_cleanup(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Publish aggregate evidence only after successful parent finalizers."""
    streams = ("diagnostic\nEVIDENCE example\nPHASE example\n", "primary\n")
    (tmp_path / "stdout.txt").write_bytes(streams[0].encode("utf-8"))
    (tmp_path / "stderr.txt").write_bytes(streams[1].encode("utf-8"))
    snapshot = steps.retained_report_snapshot(tmp_path, streams)
    assert isinstance(snapshot, Ok)
    interpreter = steps.gate_interpreter_identity(Path(sys.executable))
    assert isinstance(interpreter, Ok)
    for trusted, cleaned, code, retained in (
        (True, True, 0, Ok(tmp_path)),
        (False, True, 0, Ok(tmp_path)),
        (True, False, 0, Ok(tmp_path)),
        (True, True, 1, Ok(tmp_path)),
        (False, True, 0, Err("retention failed")),
        (True, True, 0, Err("retention failed")),
    ):
        result = steps.CheckChildResult(
            code, streams, retained, trusted, snapshot.value, interpreter.value
        )
        status = steps.__dict__["_relay_check_child"](result, cleaned=cleaned)
        captured = capsys.readouterr()
        lines = captured.out.splitlines()
        assert "diagnostic" in lines
        assert "primary" in captured.err
        assert not any(line.startswith("PHASE ") for line in lines), (
            "unverified phase evidence was published"
        )
        expected = trusted and cleaned and code == 0 and isinstance(retained, Ok)
        assert ("EVIDENCE example" in lines) == expected, (
            "aggregate evidence bypassed parent finalizers"
        )
        assert status == (1 if isinstance(retained, Err) else code)

    missing = steps.CheckChildResult(
        0, streams, Ok(tmp_path), trusted=True, interpreter=interpreter.value
    )
    assert steps.__dict__["_relay_check_child"](missing, cleaned=True) == 1
    captured = capsys.readouterr()
    assert "withheld unverified: EVIDENCE example" in captured.out
    assert "retained report changed after verification" in captured.err


def test_context_keeps_binding_refusal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A binding observer refusal reaches the shared gate precondition."""
    monkeypatch.setattr(
        steps.virtualbox_binding,
        "check_shared_checkout",
        lambda *_args: Err("binding unavailable"),
    )
    issues = steps.inspect_context(tmp_path, tmp_path, "Linux")
    assert "VirtualBox binding: binding unavailable" in issues, (
        "gate ignored binding observer refusal"
    )


def test_provisional_record_refusals(tmp_path: Path) -> None:
    """Existing, changed, linked or invalid provisional records are refused."""
    assert isinstance(steps.record_provisional_phases(tmp_path, "", None), Err)
    recorded = steps.record_provisional_phases(tmp_path, NONCE, Err("missing"))
    assert isinstance(recorded, Ok), recorded
    again = steps.record_provisional_phases(tmp_path, NONCE, Err("missing"))
    assert isinstance(again, Err)
    assert "cannot record provisional phases" in again.error
    assert steps.provisional_phases_unchanged(tmp_path, recorded) == 0
    assert steps.provisional_phases_unchanged(tmp_path, Err("lost")) == 1
    path = tmp_path / "provisional-phases.json"
    path.write_bytes(recorded.value + b" ")
    assert steps.provisional_phases_unchanged(tmp_path, recorded) == 1
    path.unlink()
    path.mkdir()
    assert steps.provisional_phases_unchanged(tmp_path, recorded) == 1


def test_provisional_record_schema() -> None:
    """Invalid JSON or a foreign nonce never parses as a provisional record."""
    foreign = json.dumps({"nonce": "other"}).encode()
    assert steps.parse_provisional_record(NONCE, b"{") == Err(
        "invalid provisional record JSON"
    )
    for contents in (b"[]", foreign):
        assert steps.parse_provisional_record(NONCE, contents) == Err(
            "invalid provisional record identity"
        )


def test_deep_provisional_handoff_is_refused(tmp_path: Path) -> None:
    """Deeply nested retained JSON produces a refusal rather than a crash."""
    contents = b"[" * 50000 + b"0" + b"]" * 50000
    (tmp_path / "provisional-phases.json").write_bytes(contents)
    output = steps.provisional_seal(NONCE, contents) + "\nfinalizer\n"
    try:
        result = steps.verify_provisional_handoff(tmp_path, NONCE, output)
    except RecursionError:
        pytest.fail("deep provisional handoff escaped its parser")
    assert isinstance(result, Err), "deep provisional handoff was accepted"


def test_deep_coverage_handoff_is_refused(tmp_path: Path) -> None:
    """A sealed but deeply nested wrapper cannot crash the coverage handoff."""
    contents = b"[" * 50000 + b"0" + b"]" * 50000
    raw = b"coverage report"
    final = steps.record_finalizers(tmp_path, NONCE, PASSING)
    assert isinstance(final, Ok)
    (tmp_path / "coverage-report.json").write_bytes(contents)
    (tmp_path / "coverage-raw.json").write_bytes(raw)
    output = "\n".join(
        (
            steps.coverage_seal(NONCE, contents, raw),
            "a",
            "b",
            steps.finalizer_seal(final.value),
            "",
        )
    )
    try:
        result = steps.verify_coverage_handoff(tmp_path, NONCE, output)
    except RecursionError:
        pytest.fail("deep coverage handoff escaped its parser")
    assert isinstance(result, Err), "deep coverage handoff was accepted"


def test_coverage_handoff_refuses_special_and_replaced_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Coverage files must be private regular files throughout both reads."""
    special = tmp_path / "special"
    special.mkdir()
    report = special / "coverage-report.json"
    if hasattr(os, "mkfifo"):
        os.mkfifo(report)
    else:
        report.mkdir()
    (special / "coverage-raw.json").write_bytes(b"raw")
    program = (
        "from pathlib import Path; import sys; "
        "from agentctl.check.steps import _coverage_handoff_files; "
        "from agentctl.foundation import Err; "
        "print('refused' if isinstance(_coverage_handoff_files(Path(sys.argv[1]), "
        "'abc123'), Err) else 'accepted')"
    )
    observed = run(
        [sys.executable, "-c", program, str(special)],
        cwd=Path.cwd(),
        env=os.environ,
        timeout=5,
    )
    assert isinstance(observed, Ok), (
        "coverage handoff special file blocked or was accepted"
    )
    assert observed.value.code == 0, observed.value.stderr
    assert observed.value.stdout.strip() == "refused", (
        "coverage handoff special file blocked or was accepted"
    )

    directory = tmp_path / "regular"
    directory.mkdir()
    summary = {
        "num_statements": 1,
        "covered_lines": 1,
        "missing_lines": 0,
        "num_branches": 0,
        "covered_branches": 0,
        "missing_branches": 0,
    }
    raw = json.dumps(
        {
            "meta": {"format": 3, "version": "7.17.0", "branch_coverage": True},
            "files": {
                "src/agentctl/a.py": {
                    "executed_lines": [1],
                    "missing_lines": [],
                    "executed_branches": [],
                    "missing_branches": [],
                    "summary": summary,
                }
            },
            "totals": summary,
        }
    ).encode()
    contents = json.dumps(
        {"nonce": NONCE, "version": "7.17.0", "report": raw.decode()}, sort_keys=True
    ).encode()
    path = directory / "coverage-report.json"
    path.write_bytes(contents)
    (directory / "coverage-raw.json").write_bytes(raw)
    read_pair = steps.__dict__["_coverage_handoff_files"]
    reader = steps.__dict__["_read_provisional_handoff"]
    assert read_pair(directory, NONCE) == Ok((contents, raw))
    calls = 0
    replacement_read = 3

    def replaced(target: Path) -> object:
        nonlocal calls
        calls += 1
        if calls == replacement_read:
            replacement = target.with_name("replacement")
            replacement.write_bytes(target.read_bytes())
            replacement.replace(target)
        return reader(target)

    monkeypatch.setattr(steps, "_read_provisional_handoff", replaced)
    assert read_pair(directory, NONCE) == Err(
        "coverage handoff changed during inspection"
    ), "coverage handoff file replacement was accepted"


def test_provisional_record_phase_shapes() -> None:
    """Phase lists must be lists of exactly numbered, identified failures."""
    base = {"nonce": NONCE, "status": "provisional", "phases": "x"}
    assert steps.parse_provisional_record(NONCE, json.dumps(base).encode()) == Err(
        "invalid provisional record phases"
    )
    extra = {**base, "phases": [{"number": 0}]}
    assert isinstance(
        steps.parse_provisional_record(NONCE, json.dumps(extra).encode()), Err
    )


def test_provisional_handoff_refusals(tmp_path: Path) -> None:
    """Missing, malformed, linked or unreadable handoff records fail closed."""
    verify = steps.verify_provisional_handoff
    assert verify(tmp_path, NONCE, "") == Err(
        "missing or ambiguous provisional handoff"
    )
    bad_identity = f"{steps.PROVISIONAL_SEAL} other {'0' * 64}\nfinal\n"
    assert verify(tmp_path, NONCE, bad_identity) == Err(
        "invalid provisional handoff identity"
    )
    sealed = f"{steps.PROVISIONAL_SEAL} {NONCE} {'0' * 64}\nfinal\n"
    missing = verify(tmp_path, NONCE, sealed)
    assert isinstance(missing, Err)
    assert "cannot read provisional handoff" in missing.error
    target = tmp_path / "target.json"
    target.write_text("{}", encoding="utf-8")
    (tmp_path / "provisional-phases.json").symlink_to(target)
    assert verify(tmp_path, NONCE, sealed) == Err(
        "provisional handoff record is a symlink"
    )


def test_finalizer_record_refusals(tmp_path: Path) -> None:
    """Invalid statuses, linked records and missing killer seals are refused."""
    assert steps.record_finalizers(tmp_path, "", PASSING) == Err(
        "invalid finalizer observations"
    )
    assert steps.record_finalizers(tmp_path, NONCE, ()) == Err(
        "invalid finalizer observations"
    )
    target = tmp_path / "target.json"
    target.write_text("{}", encoding="utf-8")
    linked = tmp_path / "linked"
    linked.mkdir()
    (linked / "finalizer-outcomes.json").symlink_to(target)
    assert steps.finalizer_observation(linked, NONCE) == Err(
        "finalizer record is a symlink"
    )
    assert isinstance(steps.finalizer_observation(tmp_path, NONCE), Err)
    assert isinstance(steps.verify_killer_handoff(tmp_path, NONCE, ""), Err)
    recorded = steps.record_finalizers(tmp_path, NONCE, PASSING)
    assert isinstance(recorded, Ok), recorded
    assert steps.verify_killer_handoff(
        tmp_path, NONCE, steps.finalizer_seal(recorded.value)
    ) == Err("missing or ambiguous mutant killer handoff")
    sealed = (
        f"{steps.KILLER_SEAL} {NONCE} {'0' * 64}\nprovisional\n"
        + steps.finalizer_seal(recorded.value)
        + "\n"
    )
    unavailable = steps.verify_killer_handoff(tmp_path, NONCE, sealed)
    assert isinstance(unavailable, Err)
    assert "mutant killer handoff record unavailable" in unavailable.error
    failed = tmp_path / "failed"
    failed.mkdir()
    statuses = tuple(
        (name, 1 if name == "mutant-killers" else 0) for name, _ in PASSING
    )
    assert isinstance(steps.record_finalizers(failed, NONCE, statuses), Ok)
    assert steps.verify_killer_handoff(failed, NONCE, _finalizer_marker(failed)) == Ok(
        None
    )


def test_provisional_handoff_rejects_hardlinks(tmp_path: Path) -> None:
    """Even matching sealed bytes cannot be shared through a second path."""
    recorded = steps.record_provisional_phases(tmp_path, NONCE, Err("missing"))
    assert isinstance(recorded, Ok)
    output = steps.provisional_seal(NONCE, recorded.value) + "\nfinalizer\n"
    original = tmp_path / "provisional-phases.json"
    alias = tmp_path / "alias.json"
    os.link(original, alias)
    assert isinstance(steps.verify_provisional_handoff(tmp_path, NONCE, output), Err), (
        "hardlinked provisional handoff was accepted"
    )
    alias.unlink()
    assert steps.verify_provisional_handoff(tmp_path, NONCE, output) == Ok(None)


def test_provisional_handoff_opens_nonblocking(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Request nonblocking open even if a FIFO replaces the checked path."""
    recorded = steps.record_provisional_phases(tmp_path, NONCE, Err("missing"))
    assert isinstance(recorded, Ok)
    target = tmp_path / "provisional-phases.json"
    output = steps.provisional_seal(NONCE, recorded.value) + "\nfinalizer\n"
    flag = getattr(os, "O_NONBLOCK", 1 << 28)
    nofollow = getattr(os, "O_NOFOLLOW", 1 << 29)
    actual_open = os.open
    seen: list[int] = []

    def capture(path: str, flags: int, mode: int = 0o777) -> int:
        if Path(path) == target:
            seen.append(flags)
            return actual_open(path, flags & ~(flag | nofollow), mode)
        return actual_open(path, flags, mode)

    monkeypatch.setattr(os, "O_NONBLOCK", flag, raising=False)
    monkeypatch.setattr(os, "O_NOFOLLOW", nofollow, raising=False)
    monkeypatch.setattr(os, "open", capture)
    assert steps.verify_provisional_handoff(tmp_path, NONCE, output) == Ok(None)
    assert seen
    assert all(flags & flag for flags in seen), (
        "provisional handoff did not request nonblocking open"
    )
    assert all(flags & nofollow for flags in seen), (
        "provisional handoff did not request no-follow open"
    )


def test_finalizer_observation_rejects_special_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Refuse a FIFO or directory before a potentially blocking record read."""
    path = tmp_path / "finalizer-outcomes.json"
    if hasattr(os, "mkfifo"):
        os.mkfifo(path)
    else:
        path.mkdir()

    def refuse_read(*_args: object) -> None:
        pytest.fail("nonregular finalizer was read")

    monkeypatch.setattr(steps, "_read_finalizer_handoff", refuse_read)
    assert isinstance(steps.finalizer_observation(tmp_path, NONCE), Err)


def test_finalizer_handoff_rejects_hardlinks(tmp_path: Path) -> None:
    """A finalizer record must be private even when its digest is correct."""
    recorded = steps.record_finalizers(tmp_path, NONCE, PASSING)
    assert isinstance(recorded, Ok)
    output = steps.finalizer_seal(recorded.value)
    original = tmp_path / "finalizer-outcomes.json"
    alias = tmp_path / "alias.json"
    os.link(original, alias)
    assert isinstance(steps.verify_finalizer_handoff(tmp_path, NONCE, output), Err), (
        "hardlinked finalizer handoff was accepted"
    )
    alias.unlink()
    assert steps.verify_finalizer_handoff(tmp_path, NONCE, output) == Ok(None)


def test_finalizer_handoff_opens_nonblocking(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Both finalizer reads request a nonblocking, no-follow open."""
    recorded = steps.record_finalizers(tmp_path, NONCE, PASSING)
    assert isinstance(recorded, Ok)
    target = tmp_path / "finalizer-outcomes.json"
    output = steps.finalizer_seal(recorded.value)
    nonblocking = getattr(os, "O_NONBLOCK", 1 << 28)
    nofollow = getattr(os, "O_NOFOLLOW", 1 << 29)
    actual_open = os.open
    seen: list[int] = []

    def capture(path: str, flags: int, mode: int = 0o777) -> int:
        if Path(path) == target:
            seen.append(flags)
            return actual_open(path, flags & ~(nonblocking | nofollow), mode)
        return actual_open(path, flags, mode)

    monkeypatch.setattr(os, "O_NONBLOCK", nonblocking, raising=False)
    monkeypatch.setattr(os, "O_NOFOLLOW", nofollow, raising=False)
    monkeypatch.setattr(os, "open", capture)
    assert steps.verify_finalizer_handoff(tmp_path, NONCE, output) == Ok(None)
    expected_reads = 2
    assert len(seen) >= expected_reads, "finalizer handoff did not use safe open flags"
    assert all(flags & nonblocking and flags & nofollow for flags in seen), (
        "finalizer handoff did not use safe open flags"
    )


def test_finalizer_handoff_refusals(tmp_path: Path) -> None:
    """The final seal must be last, exact, current and match an unlinked record."""
    verify = steps.verify_finalizer_handoff
    assert verify(tmp_path, NONCE, "") == Err("missing or ambiguous finalizer handoff")
    foreign = f"{steps.FINALIZER_SEAL} other {'0' * 64}"
    assert verify(tmp_path, NONCE, foreign) == Err("invalid finalizer handoff identity")
    sealed = f"{steps.FINALIZER_SEAL} {NONCE} {'0' * 64}"
    unavailable = verify(tmp_path, NONCE, sealed)
    assert isinstance(unavailable, Err)
    assert "finalizer handoff record unavailable" in unavailable.error
    recorded = steps.record_finalizers(tmp_path, NONCE, PASSING)
    assert isinstance(recorded, Ok), recorded
    assert verify(tmp_path, NONCE, sealed) == Err("finalizer handoff digest mismatch")
    assert verify(tmp_path, NONCE, steps.finalizer_seal(recorded.value)) == Ok(None)


def _finalizer_marker(directory: Path) -> str:
    """Use the actual finalizer seal while testing a missing tool seal."""
    recorded = steps.finalizer_observation(directory, NONCE)
    assert isinstance(recorded, Ok)
    return steps.finalizer_seal(recorded.value)


def test_failed_coverage_finalizer_retains_partial_handoff(tmp_path: Path) -> None:
    """A failed coverage finalizer requires no fabricated successful seal."""
    passing = tmp_path / "passing"
    failing = tmp_path / "failing"
    passing.mkdir()
    failing.mkdir()
    assert isinstance(steps.record_finalizers(passing, NONCE, PASSING), Ok)
    assert isinstance(
        steps.verify_coverage_handoff(passing, NONCE, _finalizer_marker(passing)), Err
    ), "missing coverage handoff was accepted"
    failed = tuple(
        (name, int(name == "coverage-observation")) for name, _code in PASSING
    )
    assert isinstance(steps.record_finalizers(failing, NONCE, failed), Ok)
    assert steps.verify_coverage_handoff(
        failing, NONCE, _finalizer_marker(failing)
    ) == Ok(None)


def test_failed_ruff_finalizer_retains_partial_handoff(tmp_path: Path) -> None:
    """A failed Ruff finalizer does not fabricate a successful handoff."""
    passing, failing = tmp_path / "passing", tmp_path / "failing"
    passing.mkdir()
    failing.mkdir()
    assert isinstance(steps.record_finalizers(passing, NONCE, PASSING), Ok)
    assert isinstance(
        steps.verify_ruff_handoff(passing, NONCE, _finalizer_marker(passing), tmp_path),
        Err,
    ), "missing Ruff handoff was accepted"
    failed = tuple((name, int(name == "ruff-observation")) for name, _code in PASSING)
    assert isinstance(steps.record_finalizers(failing, NONCE, failed), Ok)
    assert steps.verify_ruff_handoff(
        failing, NONCE, _finalizer_marker(failing), tmp_path
    ) == Ok(None)


def test_failed_python_commands_finalizer_retains_partial_handoff(
    tmp_path: Path,
) -> None:
    """A failed command finalizer does not claim a successful handoff."""
    passing, failing = tmp_path / "passing", tmp_path / "failing"
    passing.mkdir()
    failing.mkdir()
    assert isinstance(steps.record_finalizers(passing, NONCE, PASSING), Ok)
    assert isinstance(
        steps.verify_python_commands_handoff(
            passing, NONCE, _finalizer_marker(passing), tmp_path
        ),
        Err,
    )
    failed = tuple((name, int(name == "python-commands")) for name, _ in PASSING)
    assert isinstance(steps.record_finalizers(failing, NONCE, failed), Ok)
    assert steps.verify_python_commands_handoff(
        failing, NONCE, _finalizer_marker(failing), tmp_path
    ) == Ok(None)


def test_python_command_record_refuses_replacement(tmp_path: Path) -> None:
    """The original command record must retain its identity and exact bytes."""
    commands = tuple((name, (("python", name),)) for name in steps.PYTHON_COMMAND_NAMES)
    captured = steps.record_python_commands(
        tmp_path, NONCE, tmp_path, commands, "0" * 64
    )
    assert isinstance(captured, Ok)
    assert steps.python_commands_unchanged(tmp_path, NONCE, tmp_path, captured) == 0
    assert (
        steps.python_commands_unchanged(tmp_path, "foreign", tmp_path, captured) == 1
    ), "foreign command nonce was accepted"
    assert (
        steps.python_commands_unchanged(tmp_path, NONCE, tmp_path.parent, captured) == 1
    ), "foreign command root was accepted"
    path = tmp_path / "python-commands.json"
    path.write_bytes(captured.value.record + b" ")
    assert steps.python_commands_unchanged(tmp_path, NONCE, tmp_path, captured) == 1, (
        "changed command bytes were accepted"
    )
    path.rename(tmp_path / "original-commands.json")
    path.write_bytes(captured.value.record)
    assert steps.python_commands_unchanged(tmp_path, NONCE, tmp_path, captured) == 1, (
        "replaced command record was accepted"
    )


def test_python_command_seal_follows_finalizer(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A seal is emitted only for a command record whose finalizers succeeded."""
    final = steps.record_finalizers(tmp_path, NONCE, PASSING)
    phase = steps.record_provisional_phases(tmp_path, NONCE, Err("unavailable"))
    commands = tuple((name, (("python", name),)) for name in steps.PYTHON_COMMAND_NAMES)
    captured = steps.record_python_commands(
        tmp_path, NONCE, tmp_path, commands, "0" * 64
    )
    assert isinstance(final, Ok)
    assert isinstance(phase, Ok)
    assert isinstance(captured, Ok)
    marker = steps.python_commands_seal(NONCE, captured.value.record)
    steps.emit_python_commands_handoff(NONCE, final, phase, captured, (0, 0, 0))
    assert capsys.readouterr().out.strip() == marker, "command seal was not emitted"
    for codes in ((1, 0, 0), (0, 1, 0), (0, 0, 1)):
        steps.emit_python_commands_handoff(NONCE, final, phase, captured, codes)
        assert marker not in capsys.readouterr().out, "failed command seal was emitted"


def test_failed_tool_finalizer_retains_partial_handoff(tmp_path: Path) -> None:
    """A failed tool finalizer does not require a fabricated successful seal."""
    passing = tmp_path / "passing"
    passing.mkdir()
    assert isinstance(steps.record_finalizers(passing, NONCE, PASSING), Ok)
    assert isinstance(
        steps.verify_tool_results_handoff(passing, NONCE, _finalizer_marker(passing)),
        Err,
    ), "missing tool results seal was accepted"
    for name in ("tool-outcomes", "tool-substeps"):
        directory = tmp_path / name
        directory.mkdir()
        failed = tuple((item, int(item == name)) for item, _ in PASSING)
        assert isinstance(steps.record_finalizers(directory, NONCE, failed), Ok)
        assert steps.verify_tool_results_handoff(
            directory, NONCE, _finalizer_marker(directory)
        ) == Ok(None), "failed tool finalizer required a fabricated seal"


def test_failed_pytest_finalizer_retains_partial_handoff(tmp_path: Path) -> None:
    """A failed pytest finalizer does not fabricate a successful seal."""
    passing, failing = tmp_path / "passing", tmp_path / "failing"
    passing.mkdir()
    failing.mkdir()
    assert isinstance(steps.record_finalizers(passing, NONCE, PASSING), Ok)
    assert isinstance(
        steps.verify_pytest_handoff(passing, NONCE, _finalizer_marker(passing)), Err
    ), "missing pytest seal was accepted"
    failed = tuple((name, int(name == "pytest-manifest")) for name, _ in PASSING)
    assert isinstance(steps.record_finalizers(failing, NONCE, failed), Ok)
    assert steps.verify_pytest_handoff(
        failing, NONCE, _finalizer_marker(failing)
    ) == Ok(None), "failed pytest finalizer required a fabricated seal"


def test_failed_oracle_finalizer_retains_partial_handoff(tmp_path: Path) -> None:
    """A failed oracle finalizer does not require a fabricated successful seal."""
    passing = tmp_path / "passing"
    passing.mkdir()
    assert isinstance(steps.record_finalizers(passing, NONCE, PASSING), Ok)
    assert isinstance(
        steps.verify_oracle_handoff(passing, NONCE, _finalizer_marker(passing)), Err
    ), "missing oracle seal was accepted"
    for name in ("oracle-outcomes", "oracle-details"):
        directory = tmp_path / name
        directory.mkdir()
        failed = tuple((item, int(item == name)) for item, _ in PASSING)
        assert isinstance(steps.record_finalizers(directory, NONCE, failed), Ok)
        assert steps.verify_oracle_handoff(
            directory, NONCE, _finalizer_marker(directory)
        ) == Ok(None), "failed oracle finalizer required a fabricated seal"


def test_failed_host_finalizer_retains_partial_handoff(tmp_path: Path) -> None:
    """A failed host finalizer does not fabricate a successful seal."""
    passing, failing = tmp_path / "passing", tmp_path / "failing"
    passing.mkdir()
    failing.mkdir()
    assert isinstance(steps.record_finalizers(passing, NONCE, PASSING), Ok)
    assert isinstance(
        steps.verify_host_handoff(passing, NONCE, _finalizer_marker(passing)), Err
    ), "missing host seal was accepted"
    failed = tuple((name, int(name == "host-observation")) for name, _ in PASSING)
    assert isinstance(steps.record_finalizers(failing, NONCE, failed), Ok)
    assert steps.verify_host_handoff(failing, NONCE, _finalizer_marker(failing)) == Ok(
        None
    ), "failed host finalizer required a fabricated seal"


def test_failed_native_finalizer_retains_partial_handoff(tmp_path: Path) -> None:
    """Native evidence needs a seal and a trustworthy shared guard."""
    for failure in (None, "native-observation", "write-guard", "containment"):
        directory = tmp_path / str(failure)
        directory.mkdir()
        outcomes = tuple((name, int(name == failure)) for name, _ in PASSING)
        assert isinstance(steps.record_finalizers(directory, NONCE, outcomes), Ok)
        context = steps.CheckRun(tmp_path, directory, NONCE, "Linux")
        result = steps.verify_native_handoff(
            context, directory, _finalizer_marker(directory)
        )
        if failure == "native-observation":
            assert result == Ok(None), "failed native finalizer required a seal"
        elif failure in {"write-guard", "containment"}:
            assert result == Err("native handoff lacks a trustworthy checkout guard"), (
                "native handoff accepted a failed " + failure
            )
        else:
            assert isinstance(result, Err), "untrusted native handoff was accepted"


def test_failed_ty_finalizer_retains_partial_handoff(tmp_path: Path) -> None:
    """A failed type observation does not require a fabricated successful seal."""
    passing, failing = tmp_path / "passing", tmp_path / "failing"
    passing.mkdir()
    failing.mkdir()
    assert isinstance(steps.record_finalizers(passing, NONCE, PASSING), Ok)
    assert isinstance(
        steps.verify_ty_handoff(passing, NONCE, _finalizer_marker(passing), tmp_path),
        Err,
    ), "missing ty seal was accepted"
    failed = tuple((name, int(name == "ty-observation")) for name, _ in PASSING)
    assert isinstance(steps.record_finalizers(failing, NONCE, failed), Ok)
    assert steps.verify_ty_handoff(
        failing, NONCE, _finalizer_marker(failing), tmp_path
    ) == Ok(None), "failed ty finalizer required a fabricated seal"


def test_ty_record_refuses_replacement_and_stale_identity(tmp_path: Path) -> None:
    """Keep one exclusive observation bound to the original file and nonce."""
    captured = steps.record_ty_snapshot(
        tmp_path, steps.TySnapshot(NONCE, tmp_path, Output(0, "[]", ""), ())
    )
    assert isinstance(captured, Ok)
    assert steps.ty_snapshot_unchanged(tmp_path, NONCE, captured) == 0
    assert isinstance(steps.record_ty_snapshot(tmp_path, captured.value), Err), (
        "ty record was overwritten"
    )
    assert steps.ty_snapshot_unchanged(tmp_path, "stale", captured) == 1, (
        "stale ty record was accepted"
    )
    path = tmp_path / "ty-observation.json"
    path.write_bytes(path.read_bytes() + b" ")
    assert steps.ty_snapshot_unchanged(tmp_path, NONCE, captured) == 1, (
        "changed ty record was accepted"
    )


def test_native_joins_refuse_missing_observations(tmp_path: Path) -> None:
    """Native joins are skipped only without inputs and fail on missing records."""
    tool_join = steps.__dict__["_native_tool_join"]
    source_join = steps.__dict__["_native_source_join"]
    ownership = steps.__dict__["_native_ownership_observation"]
    assert tool_join(tmp_path, NONCE, None) == 0
    assert source_join(tmp_path, NONCE, None) == 0
    assert tool_join(tmp_path, NONCE, ("cabal-test",)) == 1
    assert source_join(tmp_path, NONCE, ()) == 1
    assert ownership(tmp_path, NONCE, (), (), None) == 1
    (tmp_path / "tool-outcomes.json").write_text(
        json.dumps({"nonce": NONCE, "outcomes": [["cabal-test", 0]]}),
        encoding="utf-8",
    )
    assert tool_join(tmp_path, NONCE, ("cabal-test",)) == 1


def test_report_retention_boundaries(tmp_path: Path) -> None:
    """Reports outside the owned state root, or already present, are refused."""
    root, state = tmp_path / "checkout", tmp_path / "state"
    root.mkdir()
    report = state / "check-reports" / NONCE
    report.mkdir(parents=True)
    (state / "check-reports" / "XYZ").mkdir()
    assert steps.retain_cleanup_failure(root, state, "XYZ", "m") == Err(
        "cleanup report boundary is invalid"
    )
    assert steps.retain_cleanup_failure(root, state, NONCE, "m") == Ok(None)
    retained = steps.retain_cleanup_failure(root, state, NONCE, "again")
    assert isinstance(retained, Err)
    assert "cannot retain cleanup failure" in retained.error
    foreign = tmp_path / "foreign"
    foreign.mkdir()
    assert steps.retain_handoff_failure(root, state, foreign, "m") == Err(
        "finalizer handoff report boundary is invalid"
    )
    assert steps.retain_handoff_failure(root, state, report, "m") == Ok(None)
    repeated = steps.retain_handoff_failure(root, state, report, "m")
    assert isinstance(repeated, Err)


def test_linked_run_artifacts_are_not_retained(tmp_path: Path) -> None:
    """A run artifact replaced by a link stops report retention."""
    root, state, run = tmp_path / "checkout", tmp_path / "state", tmp_path / "run"
    root.mkdir()
    run.mkdir()
    target = tmp_path / "elsewhere.json"
    target.write_text("{}", encoding="utf-8")
    (run / "tool-outcomes.json").symlink_to(target)
    retained = steps.retain_gate_output(root, state, run, NONCE, ("out", "err"))
    assert isinstance(retained, Err)
    assert "run artifact is a symlink: tool-outcomes.json" in retained.error
    assert steps.retain_gate_output(root, state, run, "", ("o", "e")) == Err(
        "invalid report nonce"
    )
