# Copyright (c) 2026 agentctl contributors.
"""Native Hyper-V observation failures do not manufacture a VM result."""

import base64
import hashlib
import os
import platform
import sys
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import pytest

from agentctl.check.hyperv_observe import (
    executable_identity,
    observe,
    system_powershell,
)
from agentctl.check.hyperv_ssh import ED25519_PREFIX, Connection, prepare
from agentctl.foundation import Err, Ok
from agentctl.process import run

pytestmark = pytest.mark.evidence("real")


def test_ssh_preparation_binds_real_files_and_pin(tmp_path: Path) -> None:
    """Preflight detects changed host keys and credentials outside its boundary."""
    source = tmp_path / "source"
    private = tmp_path / "private"
    source.mkdir()
    private.mkdir()
    key = private / "key"
    hosts = private / "known_hosts"
    key.write_text("placeholder", encoding="utf-8")
    blob = ED25519_PREFIX + bytes(range(32))
    fingerprint = "SHA256:" + base64.b64encode(
        hashlib.sha256(blob).digest()
    ).decode().rstrip("=")
    hosts.write_text(
        "192.168.12.9 ssh-ed25519 " + base64.b64encode(blob).decode() + "\n",
        encoding="utf-8",
    )
    powershell = system_powershell()
    executable = (
        powershell.value.parents[2] / "OpenSSH" / "ssh.exe"
        if isinstance(powershell, Ok)
        else tmp_path / "ssh.exe"
    )
    connection = Connection(
        executable,
        key,
        hosts,
        "192.168.12.9",
        22,
        "agentctl",
        "/usr/bin/python3",
        fingerprint,
    )
    result = prepare(connection, source_root=source, private_root=private)
    if isinstance(powershell, Err):
        assert isinstance(result, Err)
        return
    assert isinstance(result, Ok), result
    for changed in (
        replace(connection, known_hosts=Path("known_hosts")),
        replace(connection, private_key=private / ".." / "private" / "key"),
    ):
        assert isinstance(
            prepare(changed, source_root=source, private_root=private), Err
        )
    assert isinstance(
        prepare(connection, source_root=Path("source"), private_root=private), Err
    )
    hosts.write_text("changed", encoding="utf-8")
    assert isinstance(
        prepare(connection, source_root=source, private_root=private), Err
    )
    assert executable_identity(hosts) != Ok(result.value.known_hosts)
    assert isinstance(
        prepare(connection, source_root=source, private_root=tmp_path), Err
    )


def test_unregistered_vm_is_not_observed(tmp_path: Path) -> None:
    """A fresh VM UUID cannot return another VM, on Windows or another host."""
    result = observe(str(uuid4()), cwd=tmp_path)
    assert isinstance(result, Err), result


def test_executable_identity_detects_same_size_content_change(tmp_path: Path) -> None:
    """File metadata alone cannot hide a same-size executable replacement."""
    executable = tmp_path / "observer.exe"
    executable.write_bytes(b"first")
    first = executable_identity(executable)
    assert isinstance(first, Ok), first
    executable.write_bytes(b"other")
    second = executable_identity(executable)
    assert isinstance(second, Ok), second
    assert first.value.digest != second.value.digest
    assert isinstance(executable_identity(tmp_path / "missing.exe"), Err)


def test_guest_protocol_accepts_both_line_endings_and_refuses_extra_input(
    tmp_path: Path,
) -> None:
    """A real protocol process distinguishes a valid nonce from extra input."""
    args = [sys.executable, "-m", "agentctl.check.hyperv_guest_protocol"]
    environment = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    for request in ("1" * 32 + "\n", "1" * 32 + "\r\n"):
        result = run(args, cwd=tmp_path, env=environment, input_text=request)
        assert isinstance(result, Ok), result
        assert "invalid Hyper-V guest nonce" not in result.value.stderr
    invalid = run(args, cwd=tmp_path, env=environment, input_text="1" * 32 + "\nextra")
    assert isinstance(invalid, Ok), invalid
    assert invalid.value.code != 0
    assert "invalid Hyper-V guest nonce" in invalid.value.stderr


def test_system_powershell_is_required(tmp_path: Path) -> None:
    """A fresh child cannot redirect system PowerShell through its environment."""
    script = (
        "import os, sys\n"
        "from pathlib import Path\n"
        "from agentctl.check.hyperv_observe import system_powershell\n"
        "from agentctl.foundation import Err, Ok\n"
        "before = system_powershell()\n"
        "os.environ['SYSTEMROOT'] = sys.argv[1]\n"
        "os.environ['PATH'] = sys.argv[1]\n"
        "after = system_powershell()\n"
        "assert before == after\n"
        "if sys.argv[2] == 'Windows':\n"
        "    assert isinstance(after, Ok), after\n"
        "    assert not after.value.is_relative_to(Path(sys.argv[1]))\n"
        "else:\n"
        "    assert isinstance(after, Err), after\n"
    )
    result = run(
        [sys.executable, "-c", script, str(tmp_path), platform.system()],
        cwd=tmp_path,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    assert isinstance(result, Ok), result
    assert result.value.code == 0, result.value.stderr
