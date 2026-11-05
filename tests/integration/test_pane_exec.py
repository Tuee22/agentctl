# Copyright (c) 2026 agentctl contributors.
"""Native trampoline execution, private-spec refusal and owned child controls."""

import json
import os
import sys
import time
from pathlib import Path

import pytest

from agentctl.bootstrap import build
from agentctl.check.lanes import HostFacts
from agentctl.process import run, stop
from agentctl.result import Err, Ok

pytestmark = pytest.mark.evidence("real")
EXIT_STATUS = 3
SPEC_WAIT_SECONDS = 30
SPEC_WAIT_TOLERANCE = 1
SPEC_WAIT_TIMEOUT = 45
FORWARDED = ["x;", "#{pane_id}", "#(id)", "$(id)", "--", "", "one\ntwo", "λ日"]
WITNESS = """import json, os, sys
from pathlib import Path
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')
Path(sys.argv[1]).write_text(json.dumps({
    'argv': sys.argv[3:], 'nonce': sys.argv[2], 'cwd': os.getcwd(),
    'pid': os.getpid(), 'ppid': os.getppid(),
    'forwarded_value': os.environ.get('PANE_VALUE'),
    'pane': [os.environ.get(k) for k in ('TERM', 'TMUX', 'TMUX_PANE')],
    'server_only': os.environ.get('SERVER_ONLY')
}, ensure_ascii=False), encoding='utf-8')
print('out-é')
sys.stderr.write('err-é\\n')
sys.exit(3)
"""


def _spec(
    context: build.BuildContext, directory: Path, nonce: str
) -> tuple[Path, Path, Path]:
    """Publish a private literal spec and return its independent witness paths."""
    launch = directory / "launch"
    launch.mkdir(parents=True, mode=0o700)
    folder = directory / "folder with spaces #literal"
    folder.mkdir()
    record = directory / "record.json"
    status = launch / "case.status.json"
    spec = launch / "case.json"
    environment = {
        **build.environment(context),
        "PANE_VALUE": "λ日\n$(id)=value",
        "PYTHONIOENCODING": "utf-8",
        "TERM": "caller-term",
        "TMUX": "caller-server",
        "TMUX_PANE": "%0",
    }
    payload = {
        "argv": [sys.executable, "-I", "-c", WITNESS, str(record), nonce, *FORWARDED],
        "cwd": str(folder.resolve()),
        "env": environment,
        "status": str(status),
    }
    descriptor = os.open(spec, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False)
    return spec, record, status


def _call(spec: Path) -> build.BinaryCall:
    """Keep pane identity separate from the caller environment in the spec."""
    return build.BinaryCall(
        "exe:agentctl-core",
        ("pane-exec", str(spec)),
        protocol=None,
        settings=(
            ("TERM", "pane-term"),
            ("TMUX", "owned-pane-server"),
            ("TMUX_PANE", "%12"),
            ("SERVER_ONLY", "excluded"),
        ),
    )


def test_spec_deleted_and_status_propagated(
    haskell_build: build.BuildContext, tmp_path: Path, record_host: HostFacts
) -> None:
    """Actual exec preserves the POSIX pid; Windows waits and publishes status."""
    nonce = "pane-native-witness"
    spec, record, status = _spec(haskell_build, tmp_path, nonce)
    assert spec.is_file()
    child = build.start_binary(haskell_build, _call(spec))
    assert isinstance(child, Ok), child
    try:
        stdout, stderr = child.value.handle.communicate(timeout=15)
        assert child.value.handle.returncode == EXIT_STATUS, stderr
        assert stdout == "out-é\n"
        assert stderr == "err-é\n"
        assert not spec.exists()
        observed = json.loads(record.read_text(encoding="utf-8"))
        assert observed["nonce"] == nonce
        assert observed["argv"] == FORWARDED
        assert (
            Path(observed["cwd"]).resolve()
            == (tmp_path / "folder with spaces #literal").resolve()
        )
        assert observed["forwarded_value"] == "λ日\n$(id)=value", (
            "pane environment differs from spec"
        )
        assert observed["pane"] == ["pane-term", "owned-pane-server", "%12"]
        assert observed["server_only"] is None
        if record_host.family == "Windows":
            assert observed["ppid"] == child.value.pid
            assert observed["pid"] != child.value.pid
            assert json.loads(status.read_text(encoding="utf-8")) == EXIT_STATUS
        else:
            assert observed["pid"] == child.value.pid
            assert observed["ppid"] == os.getpid()
            assert not status.exists()
    finally:
        assert isinstance(stop(child.value), Ok)


def _grant_read(context: build.BuildContext, path: Path, *, directory: bool) -> None:
    """Use the native ACL utility only on the test's own Windows path."""
    utility = Path(os.environ["SYSTEMROOT"]) / "System32/icacls.exe"
    result = run(
        [
            str(utility),
            str(path),
            "/grant",
            "*S-1-1-0:RX" if directory else "*S-1-1-0:R",
        ],
        cwd=path.parent,
        env=build.environment(context),
    )
    assert isinstance(result, Ok), result
    assert result.value.code == 0, result.value.stderr


def test_unsafe_spec_refused(
    haskell_build: build.BuildContext, tmp_path: Path, record_host: HostFacts
) -> None:
    """Unsafe file or parent access prevents execution beside a private control."""
    for kind in ("file", "directory"):
        spec, record, status = _spec(haskell_build, tmp_path / kind, kind)
        original = spec.read_bytes()
        if record_host.family == "Windows":
            _grant_read(
                haskell_build,
                spec if kind == "file" else spec.parent,
                directory=kind == "directory",
            )
        else:
            (spec if kind == "file" else spec.parent).chmod(
                0o644 if kind == "file" else 0o755
            )
        result = build.execute_binary(haskell_build, _call(spec))
        assert isinstance(result, Ok), result
        assert result.value.code != 0
        assert "UnsafeSpec" in result.value.stderr, "unsafe spec was not refused"
        assert not record.exists(), "unsafe spec ran its program"
        assert not status.exists()
        assert spec.read_bytes() == original
    spec, record, _status = _spec(haskell_build, tmp_path / "private", "control")
    result = build.execute_binary(haskell_build, _call(spec))
    assert isinstance(result, Ok), result
    assert result.value.code == EXIT_STATUS
    assert record.is_file()
    assert not spec.exists()


def test_background_binary_errors(
    haskell_build: build.BuildContext, tmp_path: Path
) -> None:
    """Background calls refuse input, absent targets and an unavailable cwd."""
    assert isinstance(
        build.start_binary(
            haskell_build, build.BinaryCall("exe:agentctl-core", input_text="unused")
        ),
        Err,
    )

    child = build.start_binary(
        haskell_build,
        build.BinaryCall("exe:agentctl-core", ("--handshake",)),
        cwd=tmp_path,
    )
    assert isinstance(child, Ok), child
    try:
        stdout, stderr = child.value.handle.communicate(timeout=10)
        assert child.value.handle.returncode == 0, stderr
        assert json.loads(stdout)["protocol"] == 1
        assert not stderr
    finally:
        assert isinstance(stop(child.value), Ok)
    assert isinstance(
        build.start_binary(haskell_build, build.BinaryCall("exe:missing-component")),
        Err,
    )
    assert isinstance(
        build.start_binary(
            haskell_build,
            build.BinaryCall("exe:agentctl-core"),
            cwd=tmp_path / "missing",
        ),
        Err,
    )


def test_malformed_spec_preserved(
    haskell_build: build.BuildContext, tmp_path: Path
) -> None:
    """Invalid contents or paths fail before deleting or executing a spec."""
    changes: tuple[tuple[str, object], ...] = (
        ("argv", []),
        ("argv", ["relative-executable"]),
        ("cwd", "relative-folder"),
        ("env", {"BAD=KEY": "literal"}),
        ("env", {"KEY": "embedded\0nul"}),
        ("status", "relative-status"),
        ("status", str(tmp_path / "outside.status.json")),
    )
    for index, (key, value) in enumerate(changes):
        spec, record, status = _spec(haskell_build, tmp_path / str(index), str(index))
        payload = json.loads(spec.read_text(encoding="utf-8"))
        payload[key] = value
        spec.write_text(json.dumps(payload), encoding="utf-8")
        original = spec.read_bytes()
        result = build.execute_binary(haskell_build, _call(spec))
        assert isinstance(result, Ok), result
        assert result.value.code != 0
        assert result.value.stderr
        assert not record.exists()
        assert not status.exists()
        assert spec.read_bytes() == original
    spec, record, _status = _spec(haskell_build, tmp_path / "alias", "alias")
    payload = json.loads(spec.read_text(encoding="utf-8"))
    payload["status"] = str(spec.parent) + "/./" + spec.name
    spec.write_text(json.dumps(payload), encoding="utf-8")
    result = build.execute_binary(haskell_build, _call(spec))
    assert isinstance(result, Ok), result
    assert result.value.code != 0
    assert "InvalidSpec" in result.value.stderr
    assert not record.exists()
    assert spec.exists()
    spec, record, _status = _spec(haskell_build, tmp_path / "json", "json")
    spec.write_bytes(b"not json")
    result = build.execute_binary(haskell_build, _call(spec))
    assert isinstance(result, Ok), result
    assert result.value.code != 0
    assert "InvalidSpec" in result.value.stderr
    assert not record.exists()
    assert spec.read_bytes() == b"not json"


def test_exec_failure_is_visible(
    haskell_build: build.BuildContext, tmp_path: Path, record_host: HostFacts
) -> None:
    """A failed native exec prints a typed failure after consuming a valid spec."""
    spec, record, status = _spec(haskell_build, tmp_path, "exec-failure")
    payload = json.loads(spec.read_text(encoding="utf-8"))
    payload["argv"] = [str(tmp_path / "missing-executable")]
    spec.write_text(json.dumps(payload), encoding="utf-8")
    result = build.execute_binary(haskell_build, _call(spec))
    assert isinstance(result, Ok), result
    assert result.value.code != 0
    assert "ProgramFailed" in result.value.stderr
    assert not spec.exists()
    assert not record.exists()
    if record_host.family == "Windows":
        assert json.loads(status.read_text(encoding="utf-8")) == 1
    else:
        assert "ExecFailed" in result.value.stderr
        assert not status.exists()


def test_delayed_spec_published_atomically(
    haskell_build: build.BuildContext, tmp_path: Path
) -> None:
    """The trampoline waits for an atomic publication before running the program."""
    spec, record, _status = _spec(haskell_build, tmp_path, "delayed")
    pending = spec.with_suffix(".pending")
    spec.rename(pending)
    child = build.start_binary(haskell_build, _call(spec))
    assert isinstance(child, Ok), child
    try:
        time.sleep(0.1)
        assert child.value.handle.poll() is None
        assert not record.exists()
        pending.rename(spec)
        _stdout, stderr = child.value.handle.communicate(timeout=15)
        assert child.value.handle.returncode == EXIT_STATUS, stderr
        assert json.loads(record.read_text(encoding="utf-8"))["nonce"] == "delayed"
        assert not spec.exists()
        assert not pending.exists()
    finally:
        assert isinstance(stop(child.value), Ok)


def test_missing_spec_times_out(
    haskell_build: build.BuildContext, tmp_path: Path
) -> None:
    """The real thirty-second wait ends with a visible typed timeout."""
    launch = tmp_path / "launch"
    launch.mkdir(mode=0o700)
    spec = launch / "missing.json"
    child = build.start_binary(haskell_build, _call(spec))
    assert isinstance(child, Ok), child
    began = time.monotonic()
    try:
        stdout, stderr = child.value.handle.communicate(timeout=SPEC_WAIT_TIMEOUT)
        elapsed = time.monotonic() - began
        assert SPEC_WAIT_SECONDS - SPEC_WAIT_TOLERANCE <= elapsed < SPEC_WAIT_TIMEOUT
        assert child.value.handle.returncode != 0
        assert not stdout
        assert "SpecTimedOut" in stderr
        assert not spec.exists()
    finally:
        assert isinstance(stop(child.value), Ok)
