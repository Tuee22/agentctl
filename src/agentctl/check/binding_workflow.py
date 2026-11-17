# Copyright (c) 2026 agentctl contributors.
"""Advance a pre-gate binding exchange without losing live peer handles."""

import re
import secrets
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from agentctl.check import (
    binding_challenge,
    binding_launcher,
    binding_transaction,
    binding_wsl,
)
from agentctl.foundation import Err, Ok, Result

type Operation = Literal["observe", "absence"]


@dataclass(frozen=True, slots=True)
class Context:
    """Explicit checkout, dedicated state parent and WSL service limits."""

    root: Path
    state_parent: Path
    environment: Mapping[str, str]
    config: binding_wsl.Configuration
    limits: binding_wsl.UnitLimits


@dataclass(frozen=True, slots=True)
class Exchange:
    """The original source challenge and its private workflow directory."""

    context: Context
    pending: binding_transaction.PendingExchange
    directory: Path


@dataclass(frozen=True, slots=True)
class Held:
    """A peer with input held and its owned host handle retained."""

    exchange: Exchange
    started: binding_launcher.Started
    removed: binding_transaction.RemovedExchange | None


@dataclass(frozen=True, slots=True)
class Ready:
    """An independently observed held peer ready for its request."""

    held: Held
    observed: binding_launcher.Observed


@dataclass(frozen=True, slots=True)
class Waiting:
    """A peer whose request was sent exactly once."""

    held: Held
    released: binding_launcher.Released


@dataclass(frozen=True, slots=True)
class AwaitingAbsence:
    """A removed challenge that still needs a separate absence peer."""

    exchange: Exchange
    removed: binding_transaction.RemovedExchange


@dataclass(frozen=True, slots=True)
class Finished:
    """A joined exchange, not an authenticated WSL binding receipt."""

    exchange: Exchange
    result: binding_transaction.BindingExchange


type State = Held | Ready | Waiting | AwaitingAbsence | Finished


def _directory(root: Path, parent: Path) -> Result[Path, str]:
    """Create a fresh external boundary without touching an existing tree."""
    try:
        checkout = root.resolve(strict=True)
        base = parent.resolve(strict=True)
        if (
            parent.is_symlink()
            or not base.is_dir()
            or base == checkout
            or base.is_relative_to(checkout)
        ):
            return Err("invalid binding workflow state parent")
        directory = base / ("abw-" + secrets.token_hex(8))
        directory.mkdir(mode=0o700)
        return Ok(directory)
    except (OSError, RuntimeError, ValueError) as exc:
        return Err("cannot create binding workflow boundary: " + str(exc))


def _start_peer(
    exchange: Exchange,
    operation: Operation,
    removed: binding_transaction.RemovedExchange | None,
) -> Result[Held, str]:
    """Start one service in a fresh attempt directory and retain its handle."""
    context = exchange.context
    unit = binding_wsl.prepare_unit(
        context.config, operation, exchange.pending.request, context.limits
    )
    if isinstance(unit, Err):
        return unit
    try:
        base = context.state_parent.resolve(strict=True)
        directory = exchange.directory.resolve(strict=True)
        if (
            exchange.directory.is_symlink()
            or directory.parent != base
            or re.fullmatch(r"abw-[0-9a-f]{16}", directory.name) is None
        ):
            return Err("binding workflow boundary changed")
        parent = directory / (operation[0] + "-" + secrets.token_hex(8))
        parent.mkdir(mode=0o700)
    except (OSError, RuntimeError) as exc:
        return Err("cannot create binding peer boundary: " + str(exc))
    launcher_context = binding_launcher.LauncherContext(
        context.root, parent / unit.value.unit, context.environment
    )
    started = binding_launcher.start(context.config, unit.value, launcher_context)
    return (
        started
        if isinstance(started, Err)
        else Ok(Held(exchange, started.value, removed))
    )


def begin(
    context: Context, target: binding_transaction.BindingTarget
) -> Result[Held, str]:
    """Create a fresh challenge and start its held-input observation peer.

    An error before a child is started cancels only the new owned challenge;
    any started child remains in the returned state even if registration failed.
    """
    directory = _directory(context.root, context.state_parent)
    if isinstance(directory, Err):
        return directory
    pending = binding_transaction.begin(context.root, target)
    if isinstance(pending, Err):
        return pending
    exchange = Exchange(context, pending.value, directory.value)
    started = _start_peer(exchange, "observe", None)
    if isinstance(started, Err):
        cleaned = binding_challenge.cancel(context.root, pending.value.request.nonce)
        return Err(
            started.error
            + ("; cleanup: " + cleaned.error if isinstance(cleaned, Err) else "")
        )
    return started


def advance(state: State, *, wait_seconds: float) -> Result[State, str]:
    """Advance one bounded step; a wait never starts a replacement process.

    Callers retain the input state on error, including any live process handle.
    This workflow does not establish an authenticated binding or gate receipt.
    """
    match state:
        case Finished():
            return Ok(state)
        case Held(exchange, started, removed):
            observed = binding_launcher.observe(started)
            return (
                observed
                if isinstance(observed, Err)
                else Ok(Ready(Held(exchange, started, removed), observed.value))
            )
        case Ready(held, observed):
            released = binding_launcher.release(observed, wait_seconds)
            return (
                released
                if isinstance(released, Err)
                else Ok(Waiting(held, released.value))
            )
        case Waiting(held, released):
            return _advance_waiting(held, released, wait_seconds)
        case AwaitingAbsence(exchange, removed):
            return _start_peer(exchange, "absence", removed)


def _advance_waiting(
    held: Held, released: binding_launcher.Released, wait_seconds: float
) -> Result[State, str]:
    """Re-poll pending peers or advance a fully reaped peer to its next stage."""
    if isinstance(released.output, Err):
        polled = binding_launcher.wait(released, wait_seconds)
        return polled if isinstance(polled, Err) else Ok(Waiting(held, polled.value))
    if held.removed is not None:
        final = binding_transaction.finish_absence(held.removed, released)
        return (
            final
            if isinstance(final, Err)
            else Ok(Finished(held.exchange, final.value))
        )
    joined = binding_transaction.join_launched(held.exchange.pending, released)
    if isinstance(joined, Err):
        return joined
    removed = binding_transaction.remove_joined(joined.value)
    return (
        removed
        if isinstance(removed, Err)
        else Ok(AwaitingAbsence(held.exchange, removed.value))
    )
