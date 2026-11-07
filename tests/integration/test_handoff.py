# Copyright (c) 2026 agentctl contributors.
"""Native inherited-stream children retain the core's actual exit status."""

import _thread
import os
import sys
import threading
import time
from pathlib import Path

import click
import pytest

from agentctl import process
from agentctl.bootstrap import handoff
from agentctl.cli import PassRequest, dispatch
from agentctl.result import Err, Ok
from tests.harness.launch import prepare
from tests.harness.nonce import fresh
from tests.harness.passthrough import warm
from tests.harness.tmux import PrivateMux

EXIT_STATUS = 3


@pytest.mark.evidence("observer")
def test_child_mode_propagates_exit_status(
    mux_server: PrivateMux, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Run the real child transport on every host with a controlled native exit 3."""
    caller = warm(prepare(mux_server, "claude", disposition="3"))
    for key, value in caller.case.environment.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("TMUX", raising=False)
    monkeypatch.delenv("TMUX_PANE", raising=False)
    monkeypatch.chdir(caller.case.folder)
    with pytest.raises(click.exceptions.Exit) as result:
        dispatch(PassRequest("claude", (), "Windows"), assume_yes=False)
    assert result.value.exit_code == EXIT_STATUS, "child handoff changed exit status"
    records = caller.case.records()
    assert any(record["session"] == "api-claude" for record in records)
    assert mux_server.raw("has-session", "-t", "=api-claude").code != 0


@pytest.mark.evidence("real")
def test_handoff_refuses_missing_program_and_unsupported_host(tmp_path: Path) -> None:
    """Return typed errors from real OS spawn and exec refusals."""
    missing = tmp_path / "missing"
    assert isinstance(process.replace([str(missing)], env=os.environ), Err)
    assert isinstance(
        process.foreground([str(missing)], cwd=tmp_path, env=os.environ), Err
    )
    request = handoff.Transfer(
        handoff.Mode.CHILD, missing, (), tmp_path, tuple(os.environ.items())
    )
    assert isinstance(handoff.transfer(request), Err)
    assert isinstance(handoff.run("unsupported", "claude", (), assume_yes=False), Err)


@pytest.mark.evidence("observer")
def test_unreadable_pins_refuse_before_transport(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Observe a genuine file-read veto and preserve the unchanged positive control."""
    for kind in ("CACHE", "DATA", "STATE"):
        monkeypatch.setenv("XDG_" + kind + "_HOME", str(tmp_path / kind.lower()))
    pins = Path(handoff.__file__).with_name("pins.toml")
    original = pins.read_bytes()
    assert original
    nonce = fresh("handoff-pins")
    active = True
    observed = []

    def refuse(event: str, arguments: tuple[object, ...]) -> None:
        """Veto only this read of the real pins file without changing its bytes."""
        if active and event == "open" and arguments[0] == str(pins):
            observed.append((nonce, str(pins)))
            message = "owned pins read veto"
            raise PermissionError(message)

    sys.addaudithook(refuse)
    try:
        result = handoff.run("Linux", "claude", (), assume_yes=False)
    finally:
        active = False
    assert observed == [(nonce, str(pins))]
    assert isinstance(result, Err)
    assert "owned pins read veto" in result.error.message
    assert pins.read_bytes() == original


@pytest.mark.evidence("real")
def test_child_wait_survives_parent_console_interrupt(tmp_path: Path) -> None:
    """Deliver a real parent interrupt while the owned child waits for release."""
    ready = tmp_path / "ready"
    release = tmp_path / "release"
    program = (
        "import sys, time; from pathlib import Path; "
        "Path(sys.argv[1]).write_text('ready'); "
        "\nwhile not Path(sys.argv[2]).exists(): time.sleep(0.01)"
        "\nsys.exit(3)"
    )

    def interrupt() -> None:
        """Wait for the actual child before interrupting and releasing its parent."""
        deadline = time.monotonic() + 10
        while not ready.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert ready.read_text(encoding="utf-8") == "ready"
        time.sleep(0.05)
        _thread.interrupt_main()
        release.write_text("release", encoding="utf-8")

    observer = threading.Thread(target=interrupt)
    observer.start()
    try:
        result = process.foreground(
            [sys.executable, "-c", program, str(ready), str(release)],
            cwd=tmp_path,
            env=os.environ,
        )
        assert result == Ok(EXIT_STATUS), "parent interrupt replaced child exit status"
    finally:
        release.write_text("release", encoding="utf-8")
        observer.join(timeout=10)
        assert not observer.is_alive()


@pytest.mark.evidence("real")
def test_flush_failure_prevents_handoff(tmp_path: Path) -> None:
    """A genuine broken output pipe produces a typed refusal before spawning."""
    program = """import os, sys
from pathlib import Path
from agentctl.bootstrap.handoff import Mode, Transfer, transfer
from agentctl.result import Err
reader, writer = os.pipe()
os.close(reader)
broken = os.fdopen(writer, 'w')
broken.write('buffered')
original = sys.stdout
sys.stdout = broken
try:
    request = Transfer(
        Mode.CHILD, Path(sys.executable), ('-c', 'raise SystemExit(99)'),
        Path.cwd(), tuple(os.environ.items()),
    )
    result = transfer(request)
finally:
    sys.stdout = original
    try:
        broken.close()
    except OSError:
        pass
assert isinstance(result, Err), result
assert 'Cannot flush terminal output' in result.error.message
"""
    result = process.run([sys.executable, "-c", program], cwd=tmp_path, env=os.environ)
    assert isinstance(result, Ok), result
    assert result.value.code == 0, result.value.stderr
