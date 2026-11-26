# Copyright (c) 2026 agentctl contributors.
"""Failure and completion paths of the pre-gate binding transaction."""

import os
import sys
from collections.abc import Callable, Iterator
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
    binding_wsl,
)
from agentctl.check.binding_peer import PeerObservation, PeerRequest
from agentctl.check.wsl_guest_sample import GuestReading
from agentctl.check.wsl_registration import Registration
from agentctl.foundation import Err, Ok, Result
from agentctl.process import Child, Output, start_protocol, stop
from tests.harness.git import repository

pytestmark = pytest.mark.evidence("value")
NONCE = "a" * 32
BLOCKED = "blocked"
TARGET = binding_transaction.BindingTarget(
    "dedicated", "/mnt/c/Users/name/agentctl", "/work/agentctl"
)
MOUNTINFO = (
    "10 1 8:1 / / rw - ext4 /dev/root rw\n"
    "20 10 0:40 / /mnt/c rw - 9p C:\\134 rw\n"
    "21 10 0:40 /Users/name/agentctl /work/agentctl rw - 9p C:\\134 rw\n"
)
LIMITS = binding_wsl.UnitLimits(67108864, 10, 16, 20)
type Completion = Result[binding_launcher.Completed, str]


@pytest.fixture
def child(tmp_path: Path) -> Iterator[Child]:
    """Own one quiet host child for a constructed launcher state."""
    started = start_protocol(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        cwd=tmp_path,
        env=os.environ,
    )
    assert isinstance(started, Ok)
    yield started.value
    assert isinstance(stop(started.value), Ok)


def _configuration() -> binding_wsl.Configuration:
    """Construct a WSL configuration without claiming a native observation."""
    registration = Registration(
        "{854ac4df-1457-43ff-905e-2262d4de1f10}", "dedicated", r"C:\owned\debian", 2
    )
    return binding_wsl.Configuration(
        "wsl.exe",
        "/opt/python",
        registration,
        (registration,),
        r"C:\owned",
        2,
        "agentctl",
        1000,
    )


def _source(tmp_path: Path) -> Path:
    """Create an owned checkout with one untracked file."""
    source = tmp_path / "source"
    source.mkdir(parents=True)
    repository(source, (("untracked", b"content"),))
    return source


def _released(
    pending: binding_transaction.PendingExchange,
    child: Child,
    operation: binding_wsl.Operation,
) -> binding_launcher.Released:
    """Construct an unattested launcher state for the pending request."""
    request = pending.request
    config = _configuration()
    unit = binding_wsl.prepare_unit(config, operation, request, LIMITS)
    assert isinstance(unit, Ok)
    context = binding_launcher.LauncherContext(
        pending.root, pending.root.parent / unit.value.unit, os.environ
    )
    started = binding_launcher.Started(
        config, unit.value, context, child, Err("not attested")
    )
    guest = binding_process.PeerProcess(
        binding_process.PeerProcessRequest(
            123,
            1000,
            "/system.slice/" + unit.value.unit + ".service",
            "/opt/python",
            request.nonce,
            "b" * 32,
            "dedicated",
        ),
        9876,
    )
    return binding_launcher.Released(
        binding_launcher.Observed(started, guest), Ok(Output(0, "invented", "")), ()
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


def _completing(
    released: binding_launcher.Released, response: Result[str | bool, str]
) -> Callable[[binding_launcher.Released], Completion]:
    """Return the launcher completion that the native WSL observer would."""

    def complete(_released: binding_launcher.Released) -> Completion:
        return Ok(binding_launcher.Completed(released, response))

    return complete


def _present(_request: PeerRequest) -> Result[bool, str]:
    """Report the remote sentinel as absent."""
    return Ok(value=True)


def _stopped(_request: PeerRequest) -> Result[bool, str]:
    """Report the synchronous peer as terminated."""
    return Ok(value=True)


def _no_peer(_request: PeerRequest) -> Result[str, str]:
    """Refuse to be consulted."""
    return Err("not consulted")


def test_snapshot_failures_precede_any_challenge(tmp_path: Path) -> None:
    """An unreadable checkout or missing Git identity stops both entry points."""
    operations = binding_transaction.PeerOperations(_no_peer, _present, _stopped)
    missing = tmp_path / "missing"
    bare = tmp_path / "bare"
    bare.mkdir()
    for refused, prefix in (
        (binding_transaction.run(missing, TARGET, operations), "binding source"),
        (binding_transaction.begin(missing, TARGET), "binding source"),
        (binding_transaction.run(bare, TARGET, operations), "binding Git"),
        (binding_transaction.begin(bare, TARGET), "binding Git"),
    ):
        assert isinstance(refused, Err)
        assert refused.error.startswith(prefix + " snapshot: ")
    assert not tuple(bare.glob(".agentctl-binding-*"))


def test_run_refuses_a_challenge_that_cannot_be_created(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A pre-existing challenge directory prevents the peer from being consulted."""
    source = _source(tmp_path)
    (source / (".agentctl-binding-" + NONCE)).mkdir()
    with monkeypatch.context() as patch:
        patch.setattr(binding_transaction.secrets, "token_hex", lambda _size: NONCE)
        refused = binding_transaction.run(
            source,
            TARGET,
            binding_transaction.PeerOperations(_no_peer, _present, _stopped),
        )
    assert isinstance(refused, Err)
    assert refused.error.startswith("cannot create binding directory: ")


def test_run_preserves_absence_observer_and_sentinel_failures(tmp_path: Path) -> None:
    """A raising cleanup observer is reported after the exchange itself passes."""
    source = _source(tmp_path)

    def peer(request: PeerRequest) -> Result[str, str]:
        return Ok(_peer_text(source, request))

    def absence(_request: PeerRequest) -> Result[bool, str]:
        raise OSError(BLOCKED)

    result = binding_transaction.run(
        source, TARGET, binding_transaction.PeerOperations(peer, absence, _stopped)
    )
    assert isinstance(result, Err)
    assert "remote cleanup: binding absence observer failed: " + BLOCKED in result.error


def test_run_reports_sentinel_that_cannot_be_finished(tmp_path: Path) -> None:
    """A sentinel linked outside the challenge cannot be removed as owned."""
    source = _source(tmp_path / "case")
    outside = tmp_path / "outside"

    def peer(request: PeerRequest) -> Result[str, str]:
        text = _peer_text(source, request)
        reply = source / (".agentctl-binding-" + request.nonce) / "linux"
        os.link(reply, outside)
        return Ok(text)

    result = binding_transaction.run(
        source, TARGET, binding_transaction.PeerOperations(peer, _present, _stopped)
    )
    assert isinstance(result, Err)
    assert "binding sentinel is not a regular file" in result.error
    assert "; cleanup: binding sentinel is not a regular file" in result.error
    outside.unlink()
    (directory,) = tuple((tmp_path / "case" / "source").glob(".agentctl-binding-*"))
    nonce = directory.name.removeprefix(".agentctl-binding-")
    assert binding_challenge.cancel(source, nonce) == Ok(None)


def test_launched_exchange_refuses_an_unavailable_checkout(
    tmp_path: Path, child: Child
) -> None:
    """A vanished checkout retains the challenge and refuses every launched step."""
    source = _source(tmp_path)
    pending = binding_transaction.begin(source, TARGET)
    assert isinstance(pending, Ok)
    released = _released(pending.value, child, "observe")
    gone = replace(pending.value, root=tmp_path / "gone")
    finished = binding_transaction.finish_launched(gone, released, _present)
    assert finished == Err(
        "binding launcher checkout is unavailable; challenge retained"
    )
    joined = binding_transaction.join_launched(gone, released)
    assert joined == Err("binding launcher checkout is unavailable")
    other = replace(
        pending.value, request=replace(pending.value.request, nonce="c" * 32)
    )
    assert binding_transaction.join_launched(other, released) == Err(
        "binding launcher request differs"
    )
    assert binding_challenge.cancel(source, pending.value.request.nonce) == Ok(None)


def test_finish_launched_translates_each_response_shape(
    tmp_path: Path, child: Child, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Failed, malformed, wrongly typed and valid launcher responses are joined."""
    shapes: tuple[tuple[str, str], ...] = (
        ("failed", "peer failed"),
        ("garbage", "cannot decode binding peer"),
        ("boolean", "binding launcher returned an invalid observation"),
        ("valid", ""),
    )
    for label, expected in shapes:
        source = _source(tmp_path / label)
        pending = binding_transaction.begin(source, TARGET)
        assert isinstance(pending, Ok)
        released = _released(pending.value, child, "observe")
        response: Result[str | bool, str] = {
            "failed": Err("peer failed"),
            "garbage": Ok("{"),
            "boolean": Ok(value=True),
            "valid": Ok(_peer_text(source, pending.value.request)),
        }[label]
        with monkeypatch.context() as patch:
            patch.setattr(binding_launcher, "complete", _completing(released, response))
            result = binding_transaction.finish_launched(
                pending.value, released, _present
            )
        if label == "valid":
            assert isinstance(result, Ok)
        else:
            assert isinstance(result, Err)
            assert expected in result.error
        assert not tuple(source.glob(".agentctl-binding-*"))


def test_joined_exchange_is_rechecked_removed_and_confirmed_absent(
    tmp_path: Path, child: Child, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The observe peer, cleanup and absence peer complete one exchange in order."""
    source = _source(tmp_path)
    pending = binding_transaction.begin(source, TARGET)
    assert isinstance(pending, Ok)
    request = pending.value.request
    released = _released(pending.value, child, "observe")
    absent = _released(pending.value, child, "absence")
    text = _peer_text(source, request)
    with monkeypatch.context() as patch:
        patch.setattr(
            binding_launcher, "complete", _completing(released, Err("peer failed"))
        )
        assert binding_transaction.join_launched(pending.value, released) == Err(
            "peer failed"
        )
    with monkeypatch.context() as patch:
        patch.setattr(
            binding_launcher, "complete", _completing(released, Ok(value=True))
        )
        invalid = binding_transaction.join_launched(pending.value, released)
        assert invalid == Err("binding launcher returned an invalid observation")
    with monkeypatch.context() as patch:
        patch.setattr(binding_launcher, "complete", _completing(released, Ok("{")))
        garbage = binding_transaction.join_launched(pending.value, released)
        assert isinstance(garbage, Err)
    with monkeypatch.context() as patch:
        patch.setattr(binding_launcher, "complete", _completing(released, Ok(text)))
        joined = binding_transaction.join_launched(pending.value, released)
        assert isinstance(joined, Ok)
        changed = replace(
            joined.value, peer=replace(joined.value.peer, kernel="other-kernel")
        )
        assert binding_transaction.remove_joined(changed) == Err(
            "binding peer changed before cleanup"
        )
        removed = binding_transaction.remove_joined(joined.value)
        assert isinstance(removed, Ok)
    assert not tuple(source.glob(".agentctl-binding-*"))
    failures: tuple[tuple[Completion, str], ...] = (
        (Err("host failed"), "host failed"),
        (Ok(binding_launcher.Completed(absent, Err("absent failed"))), "absent failed"),
        (
            Ok(binding_launcher.Completed(absent, Ok(value=False))),
            "binding remote cleanup was not confirmed",
        ),
    )
    for completion, expected in failures:
        with monkeypatch.context() as patch:
            patch.setattr(
                binding_launcher, "complete", lambda _released, fixed=completion: fixed
            )
            refused = binding_transaction.finish_absence(removed.value, absent)
        assert isinstance(refused, Err)
        assert refused.error.startswith(expected)
        assert "remote cleanup: remote absence not established" in refused.error
    with monkeypatch.context() as patch:
        patch.setattr(binding_launcher, "complete", _completing(absent, Ok(value=True)))
        final = binding_transaction.finish_absence(removed.value, absent)
        assert isinstance(final, Ok)
        (source / "untracked").write_bytes(b"damaged")
        damaged = binding_transaction.finish_absence(removed.value, absent)
        assert isinstance(damaged, Err)
        assert "binding source changed" in damaged.error
