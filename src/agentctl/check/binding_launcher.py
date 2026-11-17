# Copyright (c) 2026 agentctl contributors.
"""Keep a WSL peer's owned host handle through observation and timeout."""

import json
import os
import stat
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from agentctl.check import binding_process, binding_wsl
from agentctl.foundation import Err, Ok, Result
from agentctl.foundation_process import Child, Output, finish, start_protocol
from agentctl.foundation_process_identity import process_birth

MAX_WAIT_SECONDS = 30
OBSERVATION_WAIT_SECONDS = 5


@dataclass(frozen=True, slots=True)
class LauncherContext:
    """A checkout and fresh pre-gate resource boundary for one launcher."""

    root: Path
    directory: Path
    environment: Mapping[str, str]


@dataclass(frozen=True, slots=True)
class HostRegistration:
    """The exact observer file and native host-process identity at creation."""

    path: Path
    nonce: str
    pid: int
    birth: int
    device: int
    inode: int


@dataclass(frozen=True, slots=True)
class Started:
    """The actual owned host child and its durable registration result."""

    config: binding_wsl.Configuration
    unit: binding_wsl.UnitInvocation
    context: LauncherContext
    child: Child
    registration: Result[HostRegistration, str]


@dataclass(frozen=True, slots=True)
class Observed:
    """A held-input host child and the bracketed guest process observation."""

    started: Started
    guest: binding_process.PeerProcess


@dataclass(frozen=True, slots=True)
class Released:
    """A request sent once, with its host handle retained across wait failures."""

    observed: Observed
    output: Result[Output, str]
    failures: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Completed:
    """A reaped host child and terminal guest observation, not a receipt."""

    released: Released
    response: Result[str | bool, str]


@dataclass(frozen=True, slots=True)
class Reservation:
    """An exclusively opened observer file held across process creation."""

    path: Path
    descriptor: int
    device: int
    inode: int


def _registry(
    context: LauncherContext, unit: binding_wsl.UnitInvocation
) -> Result[Reservation, str]:
    """Create a fresh nonce-named boundary and reserve its observer record."""
    try:
        root = context.root.resolve(strict=True)
        parent = context.directory.parent.resolve(strict=True)
        if (
            context.directory.name != unit.unit
            or not parent.is_dir()
            or parent == root
            or parent.is_relative_to(root)
        ):
            return Err("invalid binding launcher boundary")
        directory = parent / unit.unit
        directory.mkdir(mode=0o700)
        observers = directory / "observers"
        observers.mkdir(mode=0o700)
        if observers.is_symlink() or observers.resolve(strict=True).parent != directory:
            return Err("invalid binding observer directory")
        path = observers / (unit.unit + ".json")
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            facts = os.fstat(descriptor)
        except OSError:
            os.close(descriptor)
            raise
        return Ok(Reservation(path, descriptor, facts.st_dev, facts.st_ino))
    except (OSError, RuntimeError, ValueError) as exc:
        return Err("cannot reserve binding observer: " + str(exc))


def _register(
    reservation: Reservation, unit: binding_wsl.UnitInvocation, child: Child
) -> Result[HostRegistration, str]:
    """Record the Windows creation identity without overwriting foreign files."""
    try:
        with os.fdopen(
            reservation.descriptor, "w", encoding="utf-8", newline=""
        ) as stream:
            birth = process_birth("Windows", child.pid)
            if isinstance(birth, Err):
                return Err("binding host process identity: " + birth.error.message)
            if birth.value is None:
                return Err("binding host process identity unavailable")
            facts = reservation.path.lstat()
            if (
                reservation.path.is_symlink()
                or (facts.st_dev, facts.st_ino)
                != (reservation.device, reservation.inode)
                or facts.st_size != 0
            ):
                return Err("binding observer reservation changed")
            json.dump(
                {
                    "nonce": unit.invocation.request.peer.nonce,
                    "pid": child.pid,
                    "birth": birth.value,
                },
                stream,
            )
        return Ok(
            HostRegistration(
                reservation.path,
                unit.invocation.request.peer.nonce,
                child.pid,
                birth.value,
                reservation.device,
                reservation.inode,
            )
        )
    except (OSError, UnicodeError) as exc:
        return Err("cannot record binding host process: " + str(exc))


def _discard(reservation: Reservation) -> Result[None, str]:
    """Remove an unchanged empty reservation when process creation failed."""
    try:
        os.close(reservation.descriptor)
        facts = reservation.path.lstat()
        if (
            reservation.path.is_symlink()
            or (facts.st_dev, facts.st_ino) != (reservation.device, reservation.inode)
            or facts.st_size != 0
        ):
            return Err("binding observer reservation changed")
        reservation.path.unlink()
        return Ok(None)
    except (OSError, RuntimeError) as exc:
        return Err("cannot remove binding observer reservation: " + str(exc))


def start(
    config: binding_wsl.Configuration,
    unit: binding_wsl.UnitInvocation,
    context: LauncherContext,
) -> Result[Started, str]:
    """Start the exact prepared service with input held and a reserved record.

    If registration fails after spawning, the returned Started still owns the
    child and must be reaped; the empty record prevents claiming containment.
    """
    checked = binding_wsl.unit_query(config, unit)
    if isinstance(checked, Err):
        return checked
    registry = _registry(context, unit)
    if isinstance(registry, Err):
        return registry
    child = start_protocol(
        list(unit.invocation.argv), cwd=context.root, env=context.environment
    )
    if isinstance(child, Err):
        removed = _discard(registry.value)
        return Err(
            "binding host launch failed: "
            + child.error.message
            + ("; cleanup: " + removed.error if isinstance(removed, Err) else "")
        )
    return Ok(
        Started(
            config,
            unit,
            context,
            child.value,
            _register(registry.value, unit, child.value),
        )
    )


def verify_registration(started: Started, *, live: bool) -> Result[None, str]:
    """Recheck the original file identity, exact bytes and owned child handle."""
    registration = started.registration
    if isinstance(registration, Err):
        return registration
    record = registration.value
    expected = json.dumps(
        {"nonce": record.nonce, "pid": record.pid, "birth": record.birth}
    ).encode("utf-8")
    try:
        before = record.path.lstat()
        if not stat.S_ISREG(before.st_mode) or before.st_size != len(expected):
            return Err("binding host registration is not the expected file")
        data = record.path.read_bytes()
        after = record.path.lstat()
        if (
            record.path.is_symlink()
            or record.path.resolve(strict=True).parent
            != (started.context.directory / "observers").resolve(strict=True)
            or record.path.name != started.unit.unit + ".json"
            or (before.st_dev, before.st_ino) != (record.device, record.inode)
            or (after.st_dev, after.st_ino) != (record.device, record.inode)
            or data != expected
            or record.nonce != started.unit.invocation.request.peer.nonce
            or record.pid != started.child.pid
            or record.birth <= 0
            or (live and started.child.handle.poll() is not None)
        ):
            return Err("binding host registration changed or child exited")
        return Ok(None)
    except (OSError, RuntimeError, ValueError) as exc:
        return Err("cannot verify binding host registration: " + str(exc))


def observe(started: Started) -> Result[Observed, str]:
    """Observe the held guest only after the host child is registered."""
    checked = verify_registration(started, live=True)
    if isinstance(checked, Err):
        return checked
    guest = binding_wsl.observe_unit_process(
        started.config, started.unit, started.context.root, started.context.environment
    )
    if isinstance(guest, Err):
        return guest
    final = verify_registration(started, live=True)
    return final if isinstance(final, Err) else Ok(Observed(started, guest.value))


def abort(started: Started, timeout: float) -> Result[Output, str]:
    """Close held input without a request and wait for the same host child."""
    if not 0 < timeout <= MAX_WAIT_SECONDS:
        return Err("invalid binding host wait")
    result = finish(started.child, timeout=timeout, input_text="")
    return Err(result.error.message) if isinstance(result, Err) else result


def abort_wait(started: Started, timeout: float) -> Result[Output, str]:
    """Continue waiting on the same child after an abort wait timed out."""
    if not 0 < timeout <= MAX_WAIT_SECONDS:
        return Err("invalid binding host wait")
    result = finish(started.child, timeout=timeout)
    return Err(result.error.message) if isinstance(result, Err) else result


def release(observed: Observed, timeout: float) -> Result[Released, str]:
    """Send the request once; a timeout retains the same child and primary error."""
    if not 0 < timeout <= MAX_WAIT_SECONDS:
        return Err("invalid binding host wait")
    checked = verify_registration(observed.started, live=True)
    if isinstance(checked, Err):
        return checked
    result = finish(
        observed.started.child,
        timeout=timeout,
        input_text=observed.started.unit.invocation.stdin,
    )
    output = Err(result.error.message) if isinstance(result, Err) else result
    failures = (output.error,) if isinstance(output, Err) else ()
    return Ok(Released(observed, output, failures))


def wait(released: Released, timeout: float) -> Result[Released, str]:
    """Re-poll the same child without sending a second request."""
    if not 0 < timeout <= MAX_WAIT_SECONDS:
        return Err("invalid binding host wait")
    if isinstance(released.output, Ok):
        return Ok(released)
    result = finish(released.observed.started.child, timeout=timeout)
    output = Err(result.error.message) if isinstance(result, Err) else result
    failures = (
        (*released.failures, output.error)
        if isinstance(output, Err)
        else released.failures
    )
    return Ok(Released(released.observed, output, failures))


def conclude(released: Released, terminal: Result[None, str]) -> Result[Completed, str]:
    """Preserve failures without authenticating supplied observations."""
    if isinstance(released.output, Err):
        return Err("binding host child has not completed: " + released.output.error)
    started = released.observed.started
    response = binding_wsl.response(released.output.value, started.unit.invocation)
    if isinstance(terminal, Err):
        failures = (
            *released.failures,
            *((response.error,) if isinstance(response, Err) else ()),
            "termination: " + terminal.error,
        )
        return Err("; ".join(failures))
    failures = (
        *released.failures,
        *((response.error,) if isinstance(response, Err) else ()),
    )
    return Ok(
        Completed(
            released,
            Err("; ".join(failures)) if failures else response,
        )
    )


def complete(released: Released) -> Result[Completed, str]:
    """Require the host wait and guest termination before exposing a response."""
    if isinstance(released.output, Err):
        return Err("binding host child has not completed: " + released.output.error)
    started = released.observed.started
    if started.child.handle.poll() is None:
        return Err("; ".join((*released.failures, "binding host child remains active")))
    actual = finish(started.child, timeout=OBSERVATION_WAIT_SECONDS)
    if isinstance(actual, Err) or actual.value != released.output.value:
        detail = actual.error.message if isinstance(actual, Err) else "output differs"
        return Err("; ".join((*released.failures, "binding host output: " + detail)))
    terminal = binding_wsl.observe_termination(
        started.config,
        started.unit,
        released.observed.guest,
        started.context.root,
        started.context.environment,
    )
    registration = verify_registration(started, live=False)
    if isinstance(registration, Err):
        terminal = (
            Err(terminal.error + "; " + registration.error)
            if isinstance(terminal, Err)
            else registration
        )
    return conclude(released, terminal)
