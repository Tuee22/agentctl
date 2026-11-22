# Copyright (c) 2026 agentctl contributors.
"""Real process controls for the VirtualBox guest diagnostic protocol."""

import base64
import os
import platform
import secrets
import sys
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import pytest

from agentctl.check.virtualbox_guest_capacity import Request, request_text
from agentctl.check.virtualbox_key_observe import Request as KeyRequest
from agentctl.check.virtualbox_key_observe import argv as key_argv
from agentctl.check.virtualbox_key_observe import files as key_files
from agentctl.check.virtualbox_listener import observe as observe_listener
from agentctl.check.virtualbox_observe import NatRoute, observe, observe_nat
from agentctl.check.virtualbox_ssh_key import PREFIX
from agentctl.foundation_process_identity import windows_birth, windows_process_image
from agentctl.process import finish, run, start, start_protocol, stop
from agentctl.result import Err, Ok

pytestmark = pytest.mark.evidence("real")
EXIT_STILL_ACTIVE = 259


def test_current_process_image_has_native_creation_identity() -> None:
    """Observe this process through the real native handle on Windows only."""
    assert isinstance(windows_process_image(0), Err)
    invalid_pid = True
    assert isinstance(windows_process_image(invalid_pid), Err)
    observed = windows_process_image(os.getpid())
    if platform.system() != "Windows":
        assert isinstance(observed, Err)
    else:
        assert isinstance(observed, Ok), observed
        creation = windows_birth(os.getpid())
        assert isinstance(creation, Ok), creation
        assert observed.value.pid == os.getpid()
        assert observed.value.birth == creation.value
        assert observed.value.birth > 0
        expected = (Path(sys.executable), Path(sys.base_prefix) / "python.exe")
        assert any(observed.value.image.samefile(path) for path in expected)


def test_exited_process_image_is_refused(tmp_path: Path) -> None:
    """An exited Windows child with exit code STILL_ACTIVE is not a live image."""
    if platform.system() != "Windows":
        assert isinstance(windows_process_image(os.getpid()), Err)
    else:
        child = start(
            [sys.executable, "-c", "raise SystemExit(259)"],
            cwd=tmp_path,
            env=os.environ,
        )
        assert isinstance(child, Ok), child
        try:
            result = finish(child.value, timeout=10)
            assert isinstance(result, Ok), result
            assert result.value.code == EXIT_STILL_ACTIVE
            assert isinstance(windows_process_image(child.value.pid), Err), (
                "exited Windows process image was accepted"
            )
        finally:
            assert isinstance(stop(child.value), Ok)


def test_owned_child_image_is_observed_before_release(tmp_path: Path) -> None:
    """Query an independently spawned child while its owned input remains held."""
    if platform.system() != "Windows":
        assert isinstance(windows_process_image(os.getpid()), Err)
    else:
        child = start_protocol(
            [sys.executable, "-c", "import sys; sys.stdin.read()"],
            cwd=tmp_path,
            env=os.environ,
        )
        assert isinstance(child, Ok), child
        try:
            observed = windows_process_image(child.value.pid)
            assert isinstance(observed, Ok), observed
            birth = windows_birth(child.value.pid)
            assert isinstance(birth, Ok), birth
            assert observed.value.birth == birth.value
            expected = (Path(sys.executable), Path(sys.base_prefix) / "python.exe")
            assert any(observed.value.image.samefile(path) for path in expected)
            result = finish(child.value, timeout=10, input_text="release")
            assert isinstance(result, Ok), result
            assert result.value.code == 0
        finally:
            assert isinstance(stop(child.value), Ok)


def test_host_observer_refuses_missing_executable(tmp_path: Path) -> None:
    """No missing observer executable can produce a VM configuration."""
    result = observe(tmp_path / "absent.exe", str(uuid4()), cwd=tmp_path)
    assert isinstance(result, Err), result
    nat = observe_nat(
        tmp_path / "absent.exe",
        str(uuid4()),
        NatRoute("agentctl-ssh", 44223, 22),
        name="dedicated",
        cwd=tmp_path,
    )
    assert isinstance(nat, Err), nat
    listener = observe_listener(
        tmp_path / "absent.exe",
        str(uuid4()),
        NatRoute("agentctl-ssh", 44223, 22),
        name="dedicated",
        cwd=tmp_path,
    )
    assert isinstance(listener, Err), listener


def test_guest_control_key_files_are_bounded_and_contained(tmp_path: Path) -> None:
    """Real owned files refuse hard links, aliases and paths outside their root."""
    root = tmp_path.resolve()
    private = root / "private"
    private.mkdir()
    password = private / "password"
    known = private / "known_hosts"
    password.write_bytes(b"private test credential")
    encoded = base64.b64encode(PREFIX + bytes(range(32))).decode("ascii")
    known.write_text(
        "[127.0.0.1]:44223 ssh-ed25519 " + encoded + "\n", encoding="ascii"
    )
    request = KeyRequest(
        root / "VBoxManage.exe",
        str(uuid4()),
        "dedicated",
        NatRoute("agentctl-ssh", 44223, 22),
        "agentctl",
        private,
        password,
        known,
        root,
    )
    original = key_files(request)
    assert isinstance(original, Ok), original
    assert original.value.known_text == known.read_text(encoding="ascii")
    nonce = secrets.token_hex(16)
    command = key_argv(request, nonce)
    assert isinstance(command, Ok)
    assert b"private test credential" not in " ".join(command.value).encode()
    assert "--wait-stdout" in command.value, "guest stdout wait omitted"
    assert "--wait-stderr" in command.value, "guest stderr wait omitted"
    assert "--arg0=agentctl-key-" + nonce in command.value, "guest nonce omitted"
    assert isinstance(key_argv(request, "../foreign"), Err)
    alias = root / "outside-link"
    os.link(password, alias)
    try:
        assert isinstance(key_files(request), Err), "hardlinked password accepted"
        assert alias.read_bytes() == b"private test credential"
    finally:
        alias.unlink()
    outside = root / "outside"
    outside.write_bytes(b"outside")
    assert isinstance(key_files(replace(request, password=outside)), Err), (
        "outside password accepted"
    )
    assert isinstance(key_files(replace(request, password=known)), Err)
    known.write_text("changed\n", encoding="ascii")
    changed = key_files(request)
    assert isinstance(changed, Ok)
    assert changed.value != original.value


def test_guest_protocol_input_is_bounded(tmp_path: Path) -> None:
    """Accept both request line endings and refuse trailing input before observing."""
    args = [sys.executable, "-m", "agentctl.check.virtualbox_guest_protocol"]
    environment = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    for request in ("1" * 32 + "\n", "1" * 32 + "\r\n"):
        result = run(args, cwd=tmp_path, env=environment, input_text=request)
        assert isinstance(result, Ok), result
        assert "invalid VirtualBox guest nonce" not in result.value.stderr
    invalid = run(args, cwd=tmp_path, env=environment, input_text="1" * 32 + "\nextra")
    assert isinstance(invalid, Ok), invalid
    assert invalid.value.code != 0
    assert "invalid VirtualBox guest nonce" in invalid.value.stderr


def test_guest_capacity_protocol_refuses_ambiguous_input(tmp_path: Path) -> None:
    """A real protocol process rejects duplicate requests before guest sampling."""
    request = request_text(Request(secrets.token_hex(16), "/home/agentctl/state"))
    assert isinstance(request, Ok), request
    args = [sys.executable, "-m", "agentctl.check.virtualbox_guest_capacity"]
    environment = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    valid = run(args, cwd=tmp_path, env=environment, input_text=request.value)
    assert isinstance(valid, Ok), valid
    assert "request" not in valid.value.stderr
    invalid = run(
        args, cwd=tmp_path, env=environment, input_text='{"nonce":"a","nonce":"b"}'
    )
    assert isinstance(invalid, Ok), invalid
    assert invalid.value.code != 0
    assert "request" in invalid.value.stderr
