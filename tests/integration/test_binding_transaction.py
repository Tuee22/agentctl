# Copyright (c) 2026 agentctl contributors.
"""Real local transaction boundaries with explicitly constructed peer facts."""

import json
import os
import platform
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from agentctl.check import (
    binding_challenge,
    binding_launcher,
    binding_process,
    binding_transaction,
    binding_wsl,
)
from agentctl.check.binding_peer import PeerObservation, PeerRequest
from agentctl.check.wsl_guest_sample import GuestReading
from agentctl.check.wsl_registration import Registration
from agentctl.process import Output, process_birth, run, start_protocol, stop
from agentctl.result import Err, Ok, Result
from tests.harness.git import repository

pytestmark = pytest.mark.evidence("real")

TARGET = binding_transaction.BindingTarget(
    "dedicated", "/mnt/c/Users/name/agentctl", "/work/agentctl"
)
PEER = (
    "import sys\nfrom pathlib import Path\n"
    "sys.path.insert(0, sys.argv[1])\n"
    "from agentctl.check import binding_challenge, "
    "binding_inventory, binding_transport\n"
    "from agentctl.check.binding_peer import PeerObservation, PeerRequest\n"
    "from agentctl.check.wsl_guest_sample import GuestReading\n"
    "from agentctl.result import Ok\n"
    "root = Path(sys.argv[2])\n"
    "request = PeerRequest(*sys.argv[3:7])\n"
    "assert binding_challenge.answer(root, request.nonce) == Ok(None)\n"
    "inventory = binding_inventory.observe(root, request.nonce)\n"
    "assert isinstance(inventory, Ok), inventory\n"
    "mounts = ('10 1 8:1 / / rw - ext4 /dev/root rw\\n'\n"
    "          '20 10 0:40 / /mnt/c rw - 9p C:\\\\134 rw\\n'\n"
    "          '21 10 0:40 /Users/name/agentctl /work/agentctl "
    "rw - 9p C:\\\\134 rw\\n')\n"
    "observation = PeerObservation(request, '6.1-microsoft-standard-WSL2',\n"
    "    request.distribution, 'ID=debian\\n', 1000, 40, 1234, "
    "mounts, inventory.value, GuestReading((0, 1), 4096, 1024, 8192, 4096, 100))\n"
    "print(binding_transport.encode(observation))\n"
)


def _peer(project: Path, source: Path, request: PeerRequest) -> Result[str, str]:
    """Run a separate interpreter with real files and constructed mount facts."""
    outcome = run(
        [
            sys.executable,
            "-c",
            PEER,
            str(project / "src"),
            str(source),
            request.distribution,
            request.source,
            request.target,
            request.nonce,
        ],
        cwd=source,
        env=os.environ,
    )
    if isinstance(outcome, Err):
        return Err(outcome.error.message)
    return (
        Ok(outcome.value.stdout)
        if outcome.value.code == 0
        else Err(outcome.value.stderr)
    )


def _absence(source: Path, request: PeerRequest) -> Result[bool, str]:
    """Observe the test's local peer path after the host removes its sentinel."""
    return Ok(not (source / (".agentctl-binding-" + request.nonce)).exists())


def _stopped(_request: PeerRequest) -> Result[bool, str]:
    """Confirm the synchronous local test peer returned or never started."""
    return Ok(value=True)


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


def test_launched_transaction_retains_live_or_mismatched_peer(tmp_path: Path) -> None:
    """A mismatched request or live host cannot trigger challenge cleanup."""
    source = tmp_path / "source"
    source.mkdir()
    repository(source, (("untracked", b"content"),))
    pending = binding_transaction.begin(source, TARGET)
    assert isinstance(pending, Ok)
    request = pending.value.request
    config = _configuration()
    unit = binding_wsl.prepare_unit(
        config, "observe", request, binding_wsl.UnitLimits(67108864, 10, 16, 20)
    )
    assert isinstance(unit, Ok)
    child = start_protocol(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        cwd=tmp_path,
        env=os.environ,
    )
    assert isinstance(child, Ok)
    directory = source / (".agentctl-binding-" + request.nonce)
    try:
        family = platform.system()
        assert family in {"Linux", "Darwin", "Windows"}
        birth = (
            Ok(None) if family == "Darwin" else process_birth(family, child.value.pid)
        )
        assert isinstance(birth, Ok)
        (tmp_path / "observer.json").write_text(
            json.dumps(
                {"nonce": request.nonce, "pid": child.value.pid, "birth": birth.value}
            ),
            encoding="utf-8",
        )
        context = binding_launcher.LauncherContext(
            source, tmp_path / unit.value.unit, os.environ
        )
        started = binding_launcher.Started(
            config, unit.value, context, child.value, Err("not attested")
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
        released = binding_launcher.Released(
            binding_launcher.Observed(started, guest), Ok(Output(0, "invented", "")), ()
        )
        mismatch = replace(pending.value, request=replace(request, nonce="a" * 32))
        refused = binding_transaction.finish_launched(
            mismatch, released, lambda _request: Ok(value=True)
        )
        assert isinstance(refused, Err)
        assert "request differs" in refused.error
        wrong_guest = replace(guest, request=replace(guest.request, nonce="a" * 32))
        wrong_released = replace(
            released, observed=replace(released.observed, guest=wrong_guest)
        )
        wrong = binding_transaction.finish_launched(
            pending.value, wrong_released, lambda _request: Ok(value=True)
        )
        assert isinstance(wrong, Err)
        assert "request differs" in wrong.error, "wrong guest nonce was accepted"
        live = binding_transaction.finish_launched(
            pending.value, released, lambda _request: Ok(value=True)
        )
        assert isinstance(live, Err)
        assert "host child remains active" in live.error
        assert isinstance(
            binding_transaction.join_launched(pending.value, released), Err
        )
        assert binding_challenge.answer(source, request.nonce) == Ok(None)
        invented = PeerObservation(
            request,
            "kernel",
            "dedicated",
            "release",
            1000,
            1,
            1,
            "mounts",
            "inventory",
            GuestReading((0, 1), 4096, 1024, 8192, 4096, 100),
        )
        forged = binding_transaction.JoinedExchange(pending.value, released, invented)
        assert isinstance(binding_transaction.remove_joined(forged), Err), (
            "live joined peer authorized cleanup"
        )
        missing_absence = binding_transaction.finish_absence(
            binding_transaction.RemovedExchange(forged), released
        )
        assert isinstance(missing_absence, Err), (
            "unverified remote absence was accepted"
        )
        assert "request differs" in missing_absence.error
        assert "binding source changed" in missing_absence.error, (
            "absence failure hid checkout damage"
        )
        assert directory.exists(), "live launched challenge was removed"
    finally:
        assert isinstance(stop(child.value), Ok)
        if directory.exists():
            assert binding_challenge.cancel(source, request.nonce) == Ok(None)


def test_transaction_joins_and_cleans(root: Path, tmp_path: Path) -> None:
    """A separate process participates; constructed mount facts are not WSL proof."""
    repository(tmp_path, ((".gitignore", b"ignored\n"), ("ignored", b"uncommitted")))
    (tmp_path / "untracked").write_bytes(b"present")

    def peer(request: PeerRequest) -> Result[str, str]:
        return _peer(root, tmp_path, request)

    def absence(request: PeerRequest) -> Result[bool, str]:
        return _absence(tmp_path, request)

    result = binding_transaction.run(
        tmp_path, TARGET, binding_transaction.PeerOperations(peer, absence, _stopped)
    )
    assert isinstance(result, Ok), result
    assert not (
        tmp_path / (".agentctl-binding-" + result.value.peer.request.nonce)
    ).exists()
    assert (tmp_path / "ignored").read_bytes() == b"uncommitted"
    assert (tmp_path / "untracked").read_bytes() == b"present"


def test_transaction_refuses_changed_git(root: Path, tmp_path: Path) -> None:
    """A changed test-owned Git HEAD invalidates an otherwise matching exchange."""
    repository(tmp_path, (("untracked", b"content"),))

    def peer(request: PeerRequest) -> Result[str, str]:
        result = _peer(root, tmp_path, request)
        (tmp_path / ".git/HEAD").write_text("ref: refs/heads/other\n", encoding="utf-8")
        return result

    def absence(request: PeerRequest) -> Result[bool, str]:
        return _absence(tmp_path, request)

    result = binding_transaction.run(
        tmp_path, TARGET, binding_transaction.PeerOperations(peer, absence, _stopped)
    )
    assert isinstance(result, Err), "changed Git identity was accepted"
    assert "binding Git identity changed" in result.error
    assert not tuple(tmp_path.glob(".agentctl-binding-*"))


def test_transaction_preserves_source_damage(root: Path, tmp_path: Path) -> None:
    """A post-peer local change is reported alongside the inventory mismatch."""
    repository(tmp_path, (("untracked", b"before"),))

    def peer(request: PeerRequest) -> Result[str, str]:
        result = _peer(root, tmp_path, request)
        (tmp_path / "untracked").write_bytes(b"after")
        return result

    def absence(request: PeerRequest) -> Result[bool, str]:
        return _absence(tmp_path, request)

    result = binding_transaction.run(
        tmp_path, TARGET, binding_transaction.PeerOperations(peer, absence, _stopped)
    )
    assert isinstance(result, Err)
    assert "binding peer comparison" in result.error
    assert "binding source changed" in result.error, "source boundary damage was lost"
    assert not tuple(tmp_path.glob(".agentctl-binding-*"))


def test_transaction_preserves_failure_and_cleanup(tmp_path: Path) -> None:
    """A refused peer keeps its error and reports an unremovable foreign entry."""
    repository(tmp_path, (("untracked", b"content"),))

    def peer(request: PeerRequest) -> Result[str, str]:
        directory = tmp_path / (".agentctl-binding-" + request.nonce)
        (directory / "foreign").write_bytes(b"not owned")
        return Err("peer refusal")

    def absence(request: PeerRequest) -> Result[bool, str]:
        return _absence(tmp_path, request)

    result = binding_transaction.run(
        tmp_path, TARGET, binding_transaction.PeerOperations(peer, absence, _stopped)
    )
    assert isinstance(result, Err)
    assert "peer refusal" in result.error
    assert "cleanup: binding directory contains unexpected entries" in result.error, (
        "cleanup failure was lost"
    )
    assert "binding source changed" in result.error
    directory = next(tmp_path.glob(".agentctl-binding-*"))
    assert (directory / "foreign").read_bytes() == b"not owned"


def test_transaction_cleans_after_peer_os_error(tmp_path: Path) -> None:
    """A native peer-start failure does not leave an owned challenge behind."""
    repository(tmp_path, (("untracked", b"content"),))

    def peer(_request: PeerRequest) -> Result[str, str]:
        message = "peer unavailable"
        raise OSError(message)

    def absence(request: PeerRequest) -> Result[bool, str]:
        return _absence(tmp_path, request)

    result = binding_transaction.run(
        tmp_path, TARGET, binding_transaction.PeerOperations(peer, absence, _stopped)
    )
    assert isinstance(result, Err)
    assert "peer unavailable" in result.error
    assert not tuple(tmp_path.glob(".agentctl-binding-*"))


def test_transaction_requires_remote_cleanup(root: Path, tmp_path: Path) -> None:
    """A successful local cleanup is not a remote absence observation."""
    repository(tmp_path, (("untracked", b"content"),))

    def peer(request: PeerRequest) -> Result[str, str]:
        return _peer(root, tmp_path, request)

    def absence(_request: PeerRequest) -> Result[bool, str]:
        remote_absent = False
        return Ok(remote_absent)

    result = binding_transaction.run(
        tmp_path, TARGET, binding_transaction.PeerOperations(peer, absence, _stopped)
    )
    assert isinstance(result, Err), "missing remote cleanup was accepted"
    assert "remote cleanup: sentinel remains" in result.error
    assert not tuple(tmp_path.glob(".agentctl-binding-*"))


def test_transaction_retains_challenge_until_peer_stops(tmp_path: Path) -> None:
    """Neither a failed exchange nor a response proves peer termination."""
    for peer_failed in (True, False):
        case = tmp_path / str(peer_failed)
        case.mkdir()
        _transaction_retains_until_peer_stops(case, peer_failed=peer_failed)


def _transaction_retains_until_peer_stops(tmp_path: Path, *, peer_failed: bool) -> None:
    """Run one retention case in its own owned repository."""
    repository(tmp_path, (("untracked", b"content"),))
    requests: list[PeerRequest] = []
    absence_calls: list[PeerRequest] = []

    def peer(request: PeerRequest) -> Result[str, str]:
        requests.append(request)
        return Err("peer timed out") if peer_failed else Ok("response")

    def absence(request: PeerRequest) -> Result[bool, str]:
        absence_calls.append(request)
        return Ok(value=True)

    def stopped(_request: PeerRequest) -> Result[bool, str]:
        return Ok(value=False)

    result = binding_transaction.run(
        tmp_path, TARGET, binding_transaction.PeerOperations(peer, absence, stopped)
    )
    assert len(requests) == 1
    directory = tmp_path / (".agentctl-binding-" + requests[0].nonce)
    try:
        assert directory.exists(), "live peer challenge was removed"
        assert isinstance(result, Err)
        assert "peer remains active; challenge retained" in result.error
        assert not absence_calls
    finally:
        if directory.exists():
            assert binding_challenge.cancel(tmp_path, requests[0].nonce) == Ok(None)


def test_transaction_retains_challenge_on_termination_error(tmp_path: Path) -> None:
    """Keep the primary failure when the termination observer also fails."""
    repository(tmp_path, (("untracked", b"content"),))
    requests: list[PeerRequest] = []

    def peer(request: PeerRequest) -> Result[str, str]:
        requests.append(request)
        return Err("peer timed out")

    def stopped(_request: PeerRequest) -> Result[bool, str]:
        message = "observer unavailable"
        raise OSError(message)

    result = binding_transaction.run(
        tmp_path, TARGET, binding_transaction.PeerOperations(peer, _stopped, stopped)
    )
    assert len(requests) == 1
    directory = tmp_path / (".agentctl-binding-" + requests[0].nonce)
    try:
        assert directory.exists(), "uncertain peer challenge was removed"
        assert isinstance(result, Err)
        assert "peer timed out" in result.error
        assert "observer unavailable" in result.error
    finally:
        if directory.exists():
            assert binding_challenge.cancel(tmp_path, requests[0].nonce) == Ok(None)
