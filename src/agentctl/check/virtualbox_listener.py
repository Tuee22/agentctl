# Copyright (c) 2026 agentctl contributors.
"""Observe a VirtualBox NAT listener without authenticating its guest peer."""

import json
import os
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from agentctl.check import virtualbox_observe
from agentctl.check.hyperv_observe import (
    ExecutableIdentity,
    executable_identity,
    system_powershell,
)
from agentctl.check.virtualbox_observe import NatObservation, NatRoute
from agentctl.foundation import Err, Ok, Result
from agentctl.foundation_process import Child, Output, finish, start, stop
from agentctl.foundation_process_identity import (
    WindowsProcessImage,
    windows_process_image,
)

SCRIPT = r"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$vbox = New-Object -ComObject VirtualBox.VirtualBox
$machine = $vbox.FindMachine($env:AGENTCTL_VBOX_LISTENER_ID)
$state1 = [int]$machine.SessionState
$process1 = [int]$machine.SessionPID
$port = [int]$env:AGENTCTL_VBOX_LISTENER_PORT
$listeners = @(Get-NetTCPConnection -State Listen -LocalPort $port)
if ($listeners.Count -ne 1) { throw 'ambiguous listener count' }
$state2 = [int]$machine.SessionState
$process2 = [int]$machine.SessionPID
[ordered]@{ name = [string]$machine.Name; identifier = [string]$machine.Id;
    state1 = $state1; process1 = $process1;
    address = [string]$listeners[0].LocalAddress;
    port = [int]$listeners[0].LocalPort; owner = [int]$listeners[0].OwningProcess;
    state2 = $state2; process2 = $process2 } | ConvertTo-Json -Compress
"""
MAX_RESPONSE = 8192
LOCKED = 2


@dataclass(frozen=True, slots=True)
class Listener:
    """One reported VM session PID and its loopback listener."""

    name: str
    identifier: str
    port: int
    pid: int


@dataclass(frozen=True, slots=True)
class ListenerObservation:
    """Stable host configuration, listener and live process-image facts."""

    nat: NatObservation
    listener: Listener
    process: WindowsProcessImage


@dataclass(frozen=True, slots=True)
class _Request:
    """Immutable host inputs used throughout one observation."""

    executable: Path
    identifier: str
    route: NatRoute
    name: str
    cwd: Path


def parse(text: str, identifier: str, name: str, port: int) -> Result[Listener, str]:
    """Require exact ordered fields, a locked VM session and matching listener PID."""
    try:
        expected = str(UUID(identifier))
        value = (
            json.loads(text, object_pairs_hook=tuple)
            if len(text) <= MAX_RESPONSE
            else None
        )
    except (ValueError, UnicodeError, TypeError, AttributeError):
        return Err("invalid VirtualBox listener observation")
    match value:
        case (
            ("name", str() as observed_name),
            ("identifier", str() as observed_id),
            ("state1", int() as state1),
            ("process1", int() as process1),
            ("address", str() as address),
            ("port", int() as observed_port),
            ("owner", int() as owner),
            ("state2", int() as state2),
            ("process2", int() as process2),
        ):
            match (port, state1, process1, observed_port, owner, state2, process2):
                case (
                    (bool(), *_)
                    | (_, bool(), *_)
                    | (_, _, bool(), *_)
                    | (_, _, _, bool(), *_)
                    | (_, _, _, _, bool(), *_)
                    | (_, _, _, _, _, bool(), *_)
                    | (_, _, _, _, _, _, bool())
                ):
                    return Err("invalid VirtualBox listener values")
            if (
                not name
                or observed_name != name
                or observed_id != expected
                or not 1 <= port <= virtualbox_observe.MAX_PORT
                or observed_port != port
                or address != "127.0.0.1"
                or state1 != LOCKED
                or state2 != LOCKED
                or process1 <= 0
                or process1 != process2
                or process1 != owner
            ):
                return Err("VirtualBox session and listener do not match")
            return Ok(Listener(name, expected, port, process1))
        case _:
            return Err("invalid VirtualBox listener fields")


def join(
    first: ListenerObservation, second: ListenerObservation, expected: Path
) -> Result[ListenerObservation, str]:
    """Require stable VM, listener and original live process identity."""
    if (
        first != second
        or first.listener.name != first.nat.vm.name
        or first.listener.identifier != first.nat.vm.identifier
        or first.listener.port != first.nat.route.host_port
        or first.process.pid != first.listener.pid
        or first.process.birth <= 0
    ):
        return Err("VirtualBox listener observation changed or differs")
    try:
        return (
            Ok(second)
            if first.process.image.samefile(expected)
            else Err("VirtualBox listener image differs")
        )
    except OSError as exc:
        return Err("cannot compare VirtualBox listener image: " + str(exc))


def _stop_with_failure(child: Child, primary: str) -> Err[str]:
    """Retain the primary failure alongside an owned-child cleanup failure."""
    match stop(child):
        case Ok():
            return Err(primary)
        case Err(error):
            return Err(primary + "; cleanup: " + error.message)


def _wait_child(child: Child, identity: ExecutableIdentity) -> Result[Output, str]:
    """Observe the actual child image before accepting its output."""
    match windows_process_image(child.pid):
        case Err(error):
            return _stop_with_failure(child, "shell process image: " + error.message)
        case Ok(image):
            if not virtualbox_observe.image_matches(identity, image, child.pid):
                return _stop_with_failure(
                    child, "VirtualBox listener shell image differs"
                )
    match finish(child, timeout=30):
        case Err(error):
            return _stop_with_failure(child, error.message)
        case Ok(output):
            return Ok(output)


def _shell_output(
    identity: ExecutableIdentity, identifier: str, port: int, cwd: Path
) -> Result[Output, str]:
    """Use only the selected native system shell and a private child handle."""
    environment = {
        **os.environ,
        "AGENTCTL_VBOX_LISTENER_ID": identifier,
        "AGENTCTL_VBOX_LISTENER_PORT": str(port),
    }
    match start(
        [str(identity.path), "-NoProfile", "-NonInteractive", "-Command", SCRIPT],
        cwd=cwd,
        env=environment,
    ):
        case Err(error):
            return Err(error.message)
        case Ok(child):
            return _wait_child(child, identity)


def _checked_shell(
    identity: ExecutableIdentity, identifier: str, port: int, name: str, cwd: Path
) -> Result[Listener, str]:
    """Retain any primary failure when the selected shell also changes."""
    match _shell_output(identity, identifier, port, cwd):
        case Err() as error:
            result = error
        case Ok(value):
            result = (
                Err("VirtualBox listener query failed: " + value.stderr)
                if value.code
                else Ok(value.stdout)
            )
    match (result, executable_identity(identity.path)):
        case (Err(primary), Err()):
            return Err(primary + "; VirtualBox listener shell changed")
        case (Err(primary), Ok(after)) if after != identity:
            return Err(primary + "; VirtualBox listener shell changed")
        case (Err() as error, _):
            return error
        case (Ok(text), Ok(after)) if after == identity:
            return parse(text, identifier, name, port)
        case _:
            return Err("VirtualBox listener shell changed during observation")


def _query(identifier: str, port: int, name: str, cwd: Path) -> Result[Listener, str]:
    """Read COM session and TCP owner through an identity-checked system shell."""
    match system_powershell():
        case Err() as error:
            return error
        case Ok(shell):
            match executable_identity(shell):
                case Err() as error:
                    return error
                case Ok(identity):
                    return _checked_shell(identity, identifier, port, name, cwd)


def _sample(request: _Request) -> Result[ListenerObservation, str]:
    """Join one host configuration, listener and process sample."""
    match virtualbox_observe.observe_nat(
        request.executable,
        request.identifier,
        request.route,
        name=request.name,
        cwd=request.cwd,
    ):
        case Err() as error:
            return error
        case Ok(nat):
            match _query(
                request.identifier, request.route.host_port, request.name, request.cwd
            ):
                case Err() as error:
                    return error
                case Ok(listener):
                    match windows_process_image(listener.pid):
                        case Err(error):
                            return Err(error.message)
                        case Ok(process):
                            return Ok(ListenerObservation(nat, listener, process))


def _complete(
    request: _Request,
    identity: ExecutableIdentity,
    first: ListenerObservation,
    second: ListenerObservation,
) -> Result[ListenerObservation, str]:
    """Recheck the VM configuration and executable after both process samples."""
    match (
        virtualbox_observe.observe_nat(
            request.executable,
            request.identifier,
            request.route,
            name=request.name,
            cwd=request.cwd,
        ),
        executable_identity(identity.path),
    ):
        case (Err() as error, _):
            return error
        case (Ok(nat), Ok(after)) if nat == second.nat and identity == after:
            return join(first, second, identity.path)
        case _:
            return Err("VirtualBox configuration or headless executable changed")


def observe(
    executable: Path, identifier: str, route: NatRoute, *, name: str, cwd: Path
) -> Result[ListenerObservation, str]:
    """Bracket the listener and session with VM configuration and process samples."""
    request = _Request(executable, identifier, route, name, cwd)
    match executable_identity(executable.parent / "VBoxHeadless.exe"):
        case Err() as error:
            return error
        case Ok(identity):
            match _sample(request):
                case Err() as error:
                    return error
                case Ok(first):
                    match _sample(request):
                        case Err() as error:
                            return error
                        case Ok(second):
                            return _complete(request, identity, first, second)
