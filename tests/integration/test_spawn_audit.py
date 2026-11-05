# Copyright (c) 2026 agentctl contributors.
"""Observe real disposable interpreters before their process effects occur."""

import json
import os
import platform
import sys
from pathlib import Path

import pytest

from agentctl.check.audit import (
    Arguments,
    event_arguments,
    forbidden,
    install,
    read,
    windows_arguments,
)
from agentctl.process import run
from agentctl.result import Err, Ok
from tests.harness.nonce import fresh


def _actor(root: Path, directory: Path, mode: str) -> tuple[Path, str, Path]:
    """Launch the same actor with a fresh identity and an owned sentinel."""
    nonce = fresh(os.environ.get("AGENTCTL_CHECK_NONCE", "focused"))
    manifest = os.environ.get("AGENTCTL_CHECK_MANIFEST")
    observers = (
        Path(manifest).parent / "observers"
        if manifest is not None and manifest != ""
        else directory
    )
    log = observers / (nonce + ".jsonl")
    sentinel = directory / (nonce + ".sentinel")
    result = run(
        [
            sys.executable,
            str(root / "tests/fixtures/static_negative/audit/actor.py.txt"),
            mode,
            str(log),
            nonce,
            str(sentinel),
        ],
        cwd=root,
        env=os.environ,
    )
    assert isinstance(result, Ok)
    assert result.value.code == 0, result.value.stderr
    return log, nonce, sentinel


@pytest.mark.evidence("observer")
def test_all_spawn_events_recorded(root: Path, tmp_path: Path) -> None:
    """Independent effects and event names prove the hooks are active."""
    for mode, event in (
        ("subprocess", "subprocess.Popen"),
        ("exec", "os.exec"),
        ("system", "os.system"),
        ("native", "os.spawn" if platform.system() == "Windows" else "os.posix_spawn"),
    ):
        log, nonce, sentinel = _actor(root, tmp_path, mode)
        records = read(log, nonce)
        assert isinstance(records, Ok), "spawn event was not recorded"
        matching = tuple(row for row in records.value if row.event == event)
        assert matching, "spawn event was not recorded"
        assert all(row.nonce == nonce and not row.vetoed for row in matching)
        if mode == "system":
            assert matching[0].argv == ("echo " + nonce,)
            assert matching[0].raw == "echo " + nonce
        else:
            assert matching[0].argv == (
                sys.executable,
                "-c",
                (
                    "from pathlib import Path; import sys; "
                    "Path(sys.argv[1]).write_text('executed')"
                ),
                str(sentinel),
            )
            assert sentinel.read_text(encoding="utf-8") == "executed"


@pytest.mark.evidence("observer")
def test_forbidden_spawn_vetoed(root: Path, tmp_path: Path) -> None:
    """A vetoed argv runs only a harmless Python sentinel if the hook breaks."""
    allowed, allowed_nonce, positive = _actor(root, tmp_path, "subprocess")
    assert positive.exists()
    assert isinstance(read(allowed, allowed_nonce), Ok)
    log, nonce, sentinel = _actor(root, tmp_path, "veto")
    records = read(log, nonce)
    assert isinstance(records, Ok)
    assert records.value[0].vetoed
    assert records.value[0].argv[0] == "sudo"
    assert not sentinel.exists(), "forbidden sentinel executed"


@pytest.mark.evidence("observer")
def test_nonce_replay_rejected(root: Path, tmp_path: Path) -> None:
    """Actual records qualify only under their fresh actor's identity."""
    log, nonce, _sentinel = _actor(root, tmp_path, "subprocess")
    assert isinstance(read(log, nonce), Ok)
    assert isinstance(read(log, fresh("another-run")), Err), "replayed nonce accepted"


@pytest.mark.evidence("value")
def test_windows_command_line_and_veto_policy() -> None:
    """Frozen quoting examples exercise parsing on every host family."""
    for command, expected in (
        (
            '"C:\\Program Files\\Python\\python.exe" -c "a b" ""',
            ("C:\\Program Files\\Python\\python.exe", "-c", "a b", ""),
        ),
        ('program "a\\\\\\"b" c\\\\', ("program", 'a\\"b', "c\\\\")),
        ('program "a""b" plain', ("program", 'a"b', "plain")),
        ("  one\ttwo  ", ("one", "two")),
        ("", ()),
        ('program "tail\\\\"', ("program", "tail\\")),
    ):
        assert windows_arguments(command) == expected
    for name in (
        "apt",
        "apt-get",
        "dnf",
        "pacman",
        "yum",
        "zypper",
        "brew",
        "winget",
        "choco",
        "scoop",
        "sudo",
        "doas",
        "pkexec",
        "C:\\bin\\SUDO.EXE",
    ):
        assert forbidden("subprocess.Popen", Arguments((name, "--version")), "nonce")
    for argv in (
        ("ghcup", "install", "ghc"),
        ("cabal", "install"),
        ("xcode-select", "--install"),
        (),
    ):
        assert forbidden("os.exec", Arguments(argv), "nonce")
    assert not forbidden("os.exec", Arguments(("ghcup", "--version")), "nonce")
    assert not forbidden("os.system", Arguments(("echo nonce",), "echo nonce"), "nonce")
    assert forbidden("os.system", Arguments(("anything",), "anything"), "nonce")


@pytest.mark.evidence("value")
def test_audit_input_boundaries(tmp_path: Path) -> None:
    """Malformed payloads and replay files fail before observations are trusted."""
    assert event_arguments("os.system", (b"echo nonce",)) == Ok(
        Arguments(("echo nonce",), "echo nonce")
    )
    assert event_arguments("subprocess.Popen", ("python", 'python "a b"')) == Ok(
        Arguments(("python", "a b"), 'python "a b"')
    )
    assert event_arguments("os.exec", ("python", b"python")) == Ok(
        Arguments(("python",), "python")
    )
    for event, values in (
        ("os.exec", ()),
        ("os.system", (b"\xff",)),
        ("os.exec", ("python", [1])),
        ("os.exec", ("python", None)),
    ):
        assert isinstance(event_arguments(event, values), Err)
    assert isinstance(install(tmp_path / "log", "invalid nonce"), Err)
    occupied = tmp_path / "occupied"
    occupied.write_text("file", encoding="utf-8")
    assert isinstance(install(occupied / "log", "nonce"), Err)
    path = tmp_path / "records.jsonl"
    assert isinstance(read(path, "nonce"), Err)
    record = {
        "nonce": "nonce",
        "pid": 1,
        "event": "os.exec",
        "argv": ["python"],
        "raw": None,
        "vetoed": False,
    }
    for data in (
        "",
        "not json",
        "[]",
        json.dumps({}),
        json.dumps({**record, "pid": False}),
        json.dumps({**record, "pid": 0}),
        json.dumps({**record, "event": "unknown"}),
        json.dumps({**record, "argv": [1]}),
        json.dumps({**record, "raw": 1}),
        json.dumps({**record, "vetoed": 1}),
    ):
        path.write_text(data, encoding="utf-8")
        assert isinstance(read(path, "nonce"), Err)
    path.write_text(json.dumps(record), encoding="utf-8")
    assert isinstance(read(path, "nonce"), Ok)


@pytest.mark.evidence("observer")
def test_malformed_event_refused(root: Path, tmp_path: Path) -> None:
    """A real audit event with an invalid payload fails beside an observed spawn."""
    log, nonce, sentinel = _actor(root, tmp_path, "malformed")
    assert sentinel.exists()
    assert isinstance(read(log, nonce), Ok)
