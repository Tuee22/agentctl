# Copyright (c) 2026 agentctl contributors.
"""Boundary refusals and stage advancement of the pre-gate binding workflow."""

import os
import sys
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

import pytest

from agentctl.check import (
    binding_challenge,
    binding_inventory,
    binding_launcher,
    binding_process,
    binding_transaction,
    binding_transport,
    binding_workflow,
    binding_wsl,
)
from agentctl.check.binding_peer import PeerObservation, PeerRequest
from agentctl.check.wsl_guest_sample import GuestReading
from agentctl.check.wsl_registration import Registration
from agentctl.foundation import Err, Ok, Result
from agentctl.process import Output, stop
from tests.harness.git import repository

pytestmark = pytest.mark.evidence("value")
NONCE = "a" * 32
TARGET = binding_transaction.BindingTarget(
    "dedicated", "/mnt/c/Users/name/agentctl", "/work/agentctl"
)
MOUNTINFO = (
    "10 1 8:1 / / rw - ext4 /dev/root rw\n"
    "20 10 0:40 / /mnt/c rw - 9p C:\\134 rw\n"
    "21 10 0:40 /Users/name/agentctl /work/agentctl rw - 9p C:\\134 rw\n"
)
LIMITS = binding_wsl.UnitLimits(67108864, 10, 16, 20)
WAIT_SECONDS = 5
type Completion = Result[binding_launcher.Completed, str]


def _context(tmp_path: Path, executable: str) -> binding_workflow.Context:
    """Create a checkout, a state parent and a context using the given launcher."""
    source = tmp_path / "source"
    source.mkdir(parents=True)
    repository(source, (("untracked", b"content"),))
    (tmp_path / "state").mkdir()
    registration = Registration(
        "{854ac4df-1457-43ff-905e-2262d4de1f10}", "dedicated", r"C:\owned\debian", 2
    )
    config = binding_wsl.Configuration(
        executable,
        "/opt/python",
        registration,
        (registration,),
        r"C:\owned",
        2,
        "agentctl",
        1000,
    )
    return binding_workflow.Context(
        source, tmp_path / "state", os.environ, config, LIMITS
    )


def _peer_text(source: Path, request: PeerRequest) -> str:
    """Answer the challenge in-process and encode a consistent peer message."""
    assert binding_challenge.answer(source, request.nonce) == Ok(None)
    inventory = binding_inventory.observe(source, request.nonce)
    assert isinstance(inventory, Ok)
    return binding_transport.encode(
        PeerObservation(
            request,
            "6.1-microsoft-standard-WSL2",
            request.distribution,
            "ID=debian\n",
            1000,
            40,
            1234,
            MOUNTINFO,
            inventory.value,
            GuestReading((0, 1), 4096, 1024, 8192, 4096, 100),
        )
    )


def _released(
    held: binding_workflow.Held, output: Result[Output, str]
) -> binding_launcher.Released:
    """Construct an unattested released state around the held host child."""
    started = held.started
    guest = binding_process.PeerProcess(
        binding_process.PeerProcessRequest(
            123,
            1000,
            "/system.slice/" + started.unit.unit + ".service",
            "/opt/python",
            held.exchange.pending.request.nonce,
            "b" * 32,
            "dedicated",
        ),
        9876,
    )
    failures = (output.error,) if isinstance(output, Err) else ()
    return binding_launcher.Released(
        binding_launcher.Observed(started, guest), output, failures
    )


def _completing(
    released: binding_launcher.Released, response: Result[str | bool, str]
) -> Callable[[binding_launcher.Released], Completion]:
    """Return the launcher completion the native WSL observer would produce."""

    def complete(_released: binding_launcher.Released) -> Completion:
        return Ok(binding_launcher.Completed(released, response))

    return complete


def test_state_parent_refusals(tmp_path: Path) -> None:
    """A missing, enclosed or checkout-equal state parent cannot hold a workflow."""
    context = _context(tmp_path, "wsl.exe")
    inside = context.root / "inside"
    inside.mkdir()
    for parent in (context.root, inside):
        refused = binding_workflow.begin(replace(context, state_parent=parent), TARGET)
        assert refused == Err("invalid binding workflow state parent")
    missing = binding_workflow.begin(
        replace(context, state_parent=tmp_path / "missing"), TARGET
    )
    assert isinstance(missing, Err)
    assert missing.error.startswith("cannot create binding workflow boundary: ")
    assert not tuple(context.root.glob(".agentctl-binding-*"))


def test_begin_refuses_a_challenge_that_cannot_be_created(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An existing challenge directory prevents any peer from being started."""
    context = _context(tmp_path, "wsl.exe")
    (context.root / (".agentctl-binding-" + NONCE)).mkdir()
    with monkeypatch.context() as patch:
        patch.setattr(binding_transaction.secrets, "token_hex", lambda _size: NONCE)
        refused = binding_workflow.begin(context, TARGET)
    assert isinstance(refused, Err)
    assert refused.error.startswith("cannot create binding directory: ")


def _decoded(text: str, request: PeerRequest) -> PeerObservation:
    """Decode a constructed peer message that this module just encoded."""
    decoded = binding_transport.decode(text, request)
    assert isinstance(decoded, Ok)
    return decoded.value


def test_absence_stage_refuses_a_changed_or_missing_boundary(tmp_path: Path) -> None:
    """The absence peer needs the original private workflow directory."""
    context = _context(tmp_path, sys.executable)
    started = binding_workflow.begin(context, TARGET)
    assert isinstance(started, Ok)
    held = started.value
    request = held.exchange.pending.request
    assert isinstance(stop(held.started.child), Ok)
    joined = binding_transaction.JoinedExchange(
        held.exchange.pending,
        _released(held, Ok(Output(0, "", ""))),
        _decoded(_peer_text(context.root, request), request),
    )
    awaiting = binding_workflow.AwaitingAbsence(
        held.exchange, binding_transaction.RemovedExchange(joined)
    )
    moved = replace(held.exchange, directory=tmp_path / "state")
    changed = binding_workflow.advance(
        replace(awaiting, exchange=moved), wait_seconds=WAIT_SECONDS
    )
    assert changed == Err("binding workflow boundary changed")
    vanished = replace(
        held.exchange, context=replace(context, state_parent=tmp_path / "missing")
    )
    refused = binding_workflow.advance(
        replace(awaiting, exchange=vanished), wait_seconds=WAIT_SECONDS
    )
    assert isinstance(refused, Err)
    assert refused.error.startswith("cannot create binding peer boundary: ")
    assert binding_challenge.cancel(context.root, request.nonce) == Ok(None)


def test_unattested_hosts_cannot_be_observed_or_released(tmp_path: Path) -> None:
    """Without a host registration neither observation nor release proceeds."""
    context = _context(tmp_path, sys.executable)
    started = binding_workflow.begin(context, TARGET)
    assert isinstance(started, Ok)
    held = started.value
    assert isinstance(stop(held.started.child), Ok)
    observed = binding_workflow.advance(held, wait_seconds=WAIT_SECONDS)
    assert isinstance(observed, Err)
    released = _released(held, Ok(Output(0, "", "")))
    ready = binding_workflow.Ready(held, released.observed)
    refused = binding_workflow.advance(ready, wait_seconds=WAIT_SECONDS)
    assert isinstance(refused, Err)
    assert binding_challenge.cancel(
        context.root, held.exchange.pending.request.nonce
    ) == Ok(None)


def test_waiting_peers_advance_to_a_finished_exchange(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pending, observed and absence peers advance in order to a finished exchange."""
    context = _context(tmp_path, sys.executable)
    started = binding_workflow.begin(context, TARGET)
    assert isinstance(started, Ok)
    held = started.value
    request = held.exchange.pending.request
    pending = _released(held, Err("timed out"))
    polled = binding_workflow.advance(
        binding_workflow.Waiting(held, pending), wait_seconds=WAIT_SECONDS
    )
    assert isinstance(polled, Ok)
    assert isinstance(polled.value, binding_workflow.Waiting)
    done = _released(held, Ok(Output(0, "", "")))
    with monkeypatch.context() as patch:
        patch.setattr(binding_launcher, "complete", _completing(done, Ok("{")))
        garbage = binding_workflow.advance(
            binding_workflow.Waiting(held, done), wait_seconds=WAIT_SECONDS
        )
    assert isinstance(garbage, Err)
    text = _peer_text(context.root, request)
    with monkeypatch.context() as patch:
        patch.setattr(binding_launcher, "complete", _completing(done, Ok(text)))
        awaiting = binding_workflow.advance(
            binding_workflow.Waiting(held, done), wait_seconds=WAIT_SECONDS
        )
    assert isinstance(awaiting, Ok)
    assert isinstance(awaiting.value, binding_workflow.AwaitingAbsence)
    second = binding_workflow.advance(awaiting.value, wait_seconds=WAIT_SECONDS)
    assert isinstance(second, Ok)
    assert isinstance(second.value, binding_workflow.Held)
    assert second.value.removed is not None
    absent = _released(second.value, Ok(Output(0, "", "")))
    with monkeypatch.context() as patch:
        patch.setattr(binding_launcher, "complete", _completing(absent, Ok(value=True)))
        finished = binding_workflow.advance(
            binding_workflow.Waiting(second.value, absent), wait_seconds=WAIT_SECONDS
        )
    assert isinstance(finished, Ok)
    assert isinstance(finished.value, binding_workflow.Finished)
    assert binding_workflow.advance(finished.value, wait_seconds=WAIT_SECONDS) == Ok(
        finished.value
    )
    for child in (held.started.child, second.value.started.child):
        assert isinstance(stop(child), Ok)
    assert not tuple(context.root.glob(".agentctl-binding-*"))
