# Copyright (c) 2026 agentctl contributors.
"""Coordinate a pre-gate source challenge without issuing an attested receipt."""

import secrets
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from agentctl.check import binding_challenge, binding_launcher, binding_transport
from agentctl.check.binding_peer import PeerObservation, PeerRequest
from agentctl.check.evidence import Entry, source_census
from agentctl.check.writeguard import FileFact, refs
from agentctl.foundation import Err, Ok, Result


@dataclass(frozen=True, slots=True)
class BindingTarget:
    """Peer identity and its source and bind paths before a fresh nonce exists."""

    distribution: str
    source: str
    target: str


@dataclass(frozen=True, slots=True)
class BindingSnapshot:
    """Observed source and Git boundaries around the challenge."""

    entries: tuple[Entry, ...]
    git: tuple[FileFact, ...]


@dataclass(frozen=True, slots=True)
class BindingExchange:
    """A joined exchange, still requiring authenticated host and resource facts."""

    peer: PeerObservation
    before: BindingSnapshot


@dataclass(frozen=True, slots=True)
class PendingExchange:
    """A fresh challenge and the protected checkout state preceding it."""

    root: Path
    request: PeerRequest
    before: BindingSnapshot


@dataclass(frozen=True, slots=True)
class JoinedExchange:
    """A matching observed peer whose challenge still exists."""

    pending: PendingExchange
    released: binding_launcher.Released
    peer: PeerObservation


@dataclass(frozen=True, slots=True)
class RemovedExchange:
    """A locally removed challenge awaiting an observed remote absence."""

    joined: JoinedExchange


type ObservePeer = Callable[[PeerRequest], Result[str, str]]
type ObserveAbsence = Callable[[PeerRequest], Result[bool, str]]
type ObserveStopped = Callable[[PeerRequest], Result[bool, str]]


@dataclass(frozen=True, slots=True)
class PeerOperations:
    """Peer exchange, cleanup observation and independent termination check.

    A production observer must establish termination of the actual guest peer
    and its owned descendants; a callback result alone is not an attestation.
    """

    peer: ObservePeer
    absence: ObserveAbsence
    stopped: ObserveStopped


def _peer_call(peer: ObservePeer, request: PeerRequest) -> Result[str, str]:
    """Translate declared operating-system failures from the peer adapter."""
    try:
        return peer(request)
    except (OSError, RuntimeError) as exc:
        return Err("binding peer failed: " + str(exc))


def _absence_call(absence: ObserveAbsence, request: PeerRequest) -> Result[bool, str]:
    """Translate declared operating-system failures from the cleanup observer."""
    try:
        return absence(request)
    except (OSError, RuntimeError) as exc:
        return Err("binding absence observer failed: " + str(exc))


def _stopped_call(stopped: ObserveStopped, request: PeerRequest) -> Result[bool, str]:
    """Translate failures while checking that the peer no longer runs."""
    try:
        return stopped(request)
    except (OSError, RuntimeError) as exc:
        return Err("binding termination observer failed: " + str(exc))


def _snapshot(root: Path) -> Result[BindingSnapshot, str]:
    """Observe both checkout bytes and the read-only Git identity/index/refs."""
    source = source_census(root)
    if isinstance(source, Err):
        return Err("binding source snapshot: " + source.error.message)
    git = refs(root)
    if isinstance(git, Err):
        return Err("binding Git snapshot: " + git.error.message)
    return Ok(BindingSnapshot(source.value, git.value))


def _after(
    root: Path, before: BindingSnapshot, request: PeerRequest, absence: ObserveAbsence
) -> tuple[str, ...]:
    """Retain remote cleanup and both source and Git comparison failures."""
    remote = _absence_call(absence, request)
    after = _snapshot(root)
    return (
        *(("remote cleanup: " + remote.error,) if isinstance(remote, Err) else ()),
        *(
            ("remote cleanup: sentinel remains",)
            if isinstance(remote, Ok) and remote.value is not True
            else ()
        ),
        *((after.error,) if isinstance(after, Err) else ()),
        *(
            ("binding source changed",)
            if isinstance(after, Ok) and before.entries != after.value.entries
            else ()
        ),
        *(
            ("binding Git identity changed",)
            if isinstance(after, Ok) and before.git != after.value.git
            else ()
        ),
    )


def _abort(
    root: Path,
    before: BindingSnapshot,
    request: PeerRequest,
    absence: ObserveAbsence,
    primary: str,
) -> Result[BindingExchange, str]:
    """Preserve a primary failure with any cleanup and final observation errors."""
    cleaned = binding_challenge.cancel(root, request.nonce)
    problems = (
        primary,
        *(("cleanup: " + cleaned.error,) if isinstance(cleaned, Err) else ()),
        *_after(root, before, request, absence),
    )
    return Err("; ".join(problems))


def _complete(
    root: Path,
    before: BindingSnapshot,
    request: PeerRequest,
    absence: ObserveAbsence,
    observed: Result[str, str],
) -> Result[BindingExchange, str]:
    """Complete or abort only after the termination observer has succeeded."""
    if isinstance(observed, Err):
        return _abort(root, before, request, absence, observed.error)
    joined = binding_transport.join(root, observed.value, request)
    if isinstance(joined, Err):
        return _abort(root, before, request, absence, joined.error)
    finished = binding_challenge.finish(root, request.nonce)
    if isinstance(finished, Err):
        return _abort(root, before, request, absence, finished.error)
    problems = _after(root, before, request, absence)
    return (
        Err("; ".join(problems))
        if problems
        else Ok(BindingExchange(joined.value, before))
    )


def run(
    root: Path, target: BindingTarget, operations: PeerOperations
) -> Result[BindingExchange, str]:
    """Run one fresh exchange and retain source, Git and cleanup observations.

    Callers must independently establish the peer process origin, Windows-to-WSL
    path mapping, dedicated instance identity, limits, and receipt authenticity.
    """
    before = _snapshot(root)
    if isinstance(before, Err):
        return before
    request = PeerRequest(
        target.distribution, target.source, target.target, secrets.token_hex(16)
    )
    created = binding_challenge.begin(root, request.nonce)
    if isinstance(created, Err):
        return created
    observed = _peer_call(operations.peer, request)
    stopped = _stopped_call(operations.stopped, request)
    if isinstance(stopped, Err) or stopped.value is not True:
        primary = (
            observed.error if isinstance(observed, Err) else "peer response received"
        )
        reason = stopped.error if isinstance(stopped, Err) else "peer remains active"
        return Err(primary + "; " + reason + "; challenge retained")
    return _complete(root, before.value, request, operations.absence, observed)


def begin(root: Path, target: BindingTarget) -> Result[PendingExchange, str]:
    """Capture a checkout and create one exclusive challenge before launching."""
    before = _snapshot(root)
    if isinstance(before, Err):
        return before
    request = PeerRequest(
        target.distribution, target.source, target.target, secrets.token_hex(16)
    )
    created = binding_challenge.begin(root, request.nonce)
    return (
        created
        if isinstance(created, Err)
        else Ok(PendingExchange(root, request, before.value))
    )


def finish_launched(
    pending: PendingExchange,
    released: binding_launcher.Released,
    absence: ObserveAbsence,
) -> Result[BindingExchange, str]:
    """Join a terminated launcher to its exact challenge before cleanup.

    Guest containment, provisioning identity and receipt authenticity remain
    separate requirements; an incomplete launcher retains the challenge.
    """
    started = released.observed.started
    try:
        same_root = pending.root.resolve(strict=True) == started.context.root.resolve(
            strict=True
        )
    except (OSError, RuntimeError):
        return Err("binding launcher checkout is unavailable; challenge retained")
    if (
        not same_root
        or started.unit.invocation.request.operation != "observe"
        or started.unit.invocation.request.peer != pending.request
        or released.observed.guest.request.nonce != pending.request.nonce
    ):
        return Err("binding launcher request differs; challenge retained")
    completed = binding_launcher.complete(released)
    if isinstance(completed, Err):
        return Err(completed.error + "; challenge retained")
    result = completed.value.response
    match result:
        case Err(error):
            observed = Err(error)
        case Ok(str() as value):
            observed = Ok(value)
        case _:
            observed = Err("binding launcher returned an invalid observation")
    return _complete(pending.root, pending.before, pending.request, absence, observed)


def _matching_launcher(
    pending: PendingExchange, released: binding_launcher.Released, operation: str
) -> Result[None, str]:
    """Require an exact request and checkout before trusting launcher evidence."""
    started = released.observed.started
    try:
        same_root = pending.root.resolve(strict=True) == started.context.root.resolve(
            strict=True
        )
    except (OSError, RuntimeError):
        return Err("binding launcher checkout is unavailable")
    if (
        not same_root
        or started.unit.invocation.request.operation != operation
        or started.unit.invocation.request.peer != pending.request
        or pending.request.nonce != released.observed.guest.request.nonce
    ):
        return Err("binding launcher request differs")
    return Ok(None)


def join_launched(
    pending: PendingExchange, released: binding_launcher.Released
) -> Result[JoinedExchange, str]:
    """Verify a terminated peer and compare its inventory before any cleanup."""
    matching = _matching_launcher(pending, released, "observe")
    if isinstance(matching, Err):
        return matching
    completed = binding_launcher.complete(released)
    if isinstance(completed, Err):
        return completed
    result = completed.value.response
    if isinstance(result, Err):
        return result
    if not isinstance(result.value, str):
        return Err("binding launcher returned an invalid observation")
    joined = binding_transport.join(pending.root, result.value, pending.request)
    return (
        joined
        if isinstance(joined, Err)
        else Ok(JoinedExchange(pending, released, joined.value))
    )


def remove_joined(joined: JoinedExchange) -> Result[RemovedExchange, str]:
    """Recheck the peer and source before removing exact challenge sentinels."""
    current = join_launched(joined.pending, joined.released)
    if isinstance(current, Err):
        return current
    if current.value.peer != joined.peer:
        return Err("binding peer changed before cleanup")
    removed = binding_challenge.finish(
        joined.pending.root, joined.pending.request.nonce
    )
    return removed if isinstance(removed, Err) else Ok(RemovedExchange(joined))


def finish_absence(
    removed: RemovedExchange, released: binding_launcher.Released
) -> Result[BindingExchange, str]:
    """Require a separate terminated absence peer and unchanged checkout state."""
    joined = removed.joined
    pending = joined.pending
    matching = _matching_launcher(pending, released, "absence")
    if isinstance(matching, Err):
        return _absence_failure(pending, matching.error)
    completed = binding_launcher.complete(released)
    if isinstance(completed, Err):
        return _absence_failure(pending, completed.error)
    observed = completed.value.response
    if isinstance(observed, Err):
        return _absence_failure(pending, observed.error)
    if observed.value is not True:
        return _absence_failure(pending, "binding remote cleanup was not confirmed")
    problems = _after(
        pending.root, pending.before, pending.request, lambda _request: Ok(value=True)
    )
    return (
        Err("; ".join(problems))
        if problems
        else Ok(BindingExchange(joined.peer, pending.before))
    )


def _absence_failure(
    pending: PendingExchange, primary: str
) -> Result[BindingExchange, str]:
    """Keep the primary absence failure with source and Git boundary damage."""
    problems = _after(
        pending.root,
        pending.before,
        pending.request,
        lambda _request: Err("remote absence not established"),
    )
    return Err("; ".join((primary, *problems)))
