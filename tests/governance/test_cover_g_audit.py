# Copyright (c) 2026 agentctl contributors.
"""Observer registration refusals for unavailable and unsupported identities."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from agentctl.check import audit

pytestmark = pytest.mark.evidence("real")
NONCE = "nonce"
UNSUPPORTED_PID = 4321


def _register(path: Path, pid: int) -> None:
    audit.__dict__["_register"](path, NONCE, pid)


def _finished_pid() -> int:
    """Return the pid of a child that has exited and been reaped."""
    child = subprocess.Popen([sys.executable, "-c", "pass"])
    child.wait()
    return child.pid


def test_register_refuses_absent_linux_process(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A pid with no live process cannot be bound to an observer record."""
    monkeypatch.setattr(audit.sys, "platform", "linux")
    with pytest.raises(OSError, match="identity unavailable"):
        _register(tmp_path / "log.jsonl", _finished_pid())


def test_register_refuses_foreign_windows_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Windows identity lookup fails off Windows and its refusal is raised."""
    monkeypatch.setattr(audit.sys, "platform", "win32")
    with pytest.raises(OSError, match=r"kernel32|process identity"):
        _register(tmp_path / "log.jsonl", UNSUPPORTED_PID)


def test_register_accepts_unmodelled_platform_without_birth(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Other hosts register nonce and pid with no creation identity."""
    monkeypatch.setattr(audit.sys, "platform", "darwin")
    _register(tmp_path / "log.jsonl", UNSUPPORTED_PID)
    stored = json.loads(
        (tmp_path / f"log.{UNSUPPORTED_PID}.json").read_text(encoding="utf-8")
    )
    assert stored == {"nonce": NONCE, "pid": UNSUPPORTED_PID}
