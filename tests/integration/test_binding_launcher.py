# Copyright (c) 2026 agentctl contributors.
"""Owned host-child lifecycle controls for the pre-gate WSL launcher."""

import json
import os
import platform
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from agentctl.check import (
    binding_launcher,
    binding_process,
    binding_transaction,
    binding_workflow,
    binding_wsl,
)
from agentctl.check.binding_peer import PeerRequest
from agentctl.check.wsl_registration import Registration
from agentctl.process import Output, process_birth, start_protocol, stop
from agentctl.result import Err, Ok

pytestmark = pytest.mark.evidence("real")


def _fixture_unit() -> tuple[
    binding_wsl.Configuration, PeerRequest, binding_wsl.UnitInvocation
]:
    """Construct a service request without claiming WSL evidence."""
    registration = Registration(
        "{854ac4df-1457-43ff-905e-2262d4de1f10}", "dedicated", r"C:\owned\debian", 2
    )
    config = binding_wsl.Configuration(
        "wsl.exe",
        "/opt/python",
        registration,
        (registration,),
        r"C:\owned",
        2,
        "agentctl",
        1000,
    )
    peer = PeerRequest("dedicated", "/mnt/c/source", "/work/source", "a" * 32)
    unit = binding_wsl.prepare_unit(
        config, "absence", peer, binding_wsl.UnitLimits(67108864, 10, 16, 20)
    )
    assert isinstance(unit, Ok)
    return config, peer, unit.value


def _workflow_wait(
    tmp_path: Path,
    config: binding_wsl.Configuration,
    peer: PeerRequest,
    unit: binding_wsl.UnitInvocation,
    released: binding_launcher.Released,
) -> binding_launcher.Released:
    """Advance a constructed workflow around an actual owned child."""
    context = binding_workflow.Context(
        tmp_path, tmp_path, os.environ, config, unit.limits
    )
    pending = binding_transaction.PendingExchange(
        tmp_path, peer, binding_transaction.BindingSnapshot((), ())
    )
    exchange = binding_workflow.Exchange(context, pending, tmp_path)
    held = binding_workflow.Held(exchange, released.observed.started, None)
    advanced = binding_workflow.advance(
        binding_workflow.Waiting(held, released), wait_seconds=5
    )
    assert isinstance(advanced, Ok)
    assert isinstance(advanced.value, binding_workflow.Waiting)
    return advanced.value.released


def test_timeout_reuses_owned_child_and_preserves_failure(tmp_path: Path) -> None:
    """A timed-out input exchange is resumed on its original registered handle."""
    config, peer, unit = _fixture_unit()
    script = "import sys,time; data=sys.stdin.read(); time.sleep(0.3); print(data)"
    child = start_protocol([sys.executable, "-c", script], cwd=tmp_path, env=os.environ)
    assert isinstance(child, Ok)
    try:
        family = platform.system()
        assert family in {"Linux", "Darwin", "Windows"}
        birth = (
            Ok(None) if family == "Darwin" else process_birth(family, child.value.pid)
        )
        assert isinstance(birth, Ok)
        context = binding_launcher.LauncherContext(
            tmp_path, tmp_path / unit.unit, os.environ
        )
        observers = context.directory / "observers"
        observers.mkdir(parents=True)
        path = observers / (unit.unit + ".json")
        identity = birth.value if birth.value is not None else 1
        path.write_text(
            json.dumps(
                {"nonce": peer.nonce, "pid": child.value.pid, "birth": identity}
            ),
            encoding="utf-8",
        )
        facts = path.stat()
        record = binding_launcher.HostRegistration(
            path, peer.nonce, child.value.pid, identity, facts.st_dev, facts.st_ino
        )
        started = binding_launcher.Started(
            config, unit, context, child.value, Ok(record)
        )
        guest = binding_process.PeerProcess(
            binding_process.PeerProcessRequest(
                123,
                1000,
                "/system.slice/" + unit.unit + ".service",
                "/opt/python",
                peer.nonce,
                "b" * 32,
                "dedicated",
            ),
            9876,
        )
        observed = binding_launcher.Observed(started, guest)
        assert binding_launcher.verify_registration(started, live=True) == Ok(None)
        original = path.read_bytes()
        path.write_bytes(original + b" ")
        assert isinstance(binding_launcher.release(observed, 1), Err), (
            "changed host registration was accepted"
        )
        path.write_bytes(original)
        released = binding_launcher.release(observed, 0.001)
        assert isinstance(released, Ok)
        assert isinstance(released.value.output, Err)
        forged = replace(released.value, output=Ok(Output(0, "invented", "")))
        refused = binding_launcher.complete(forged)
        assert isinstance(refused, Err)
        assert "host child remains active" in refused.error, (
            "live host child was accepted"
        )
        assert isinstance(binding_launcher.complete(released.value), Err), (
            "unfinished host child was accepted"
        )
        waited = _workflow_wait(tmp_path, config, peer, unit, released.value)
        assert isinstance(waited.output, Ok), "workflow did not poll timed-out child"
        assert waited.output.value.stdout.strip() == unit.invocation.stdin
        assert waited.observed.started.child.pid == child.value.pid, (
            "workflow replaced the timed-out child"
        )
        assert waited.failures, "original timeout was lost"
        assert waited.failures == released.value.failures, "original timeout was lost"
        failed = binding_launcher.conclude(waited, Err("unit remains active"))
        assert isinstance(failed, Err)
        assert waited.failures[0] in failed.error, "original timeout was lost"
        assert "unit remains active" in failed.error, "termination failure was lost"
    finally:
        assert isinstance(stop(child.value), Ok)
