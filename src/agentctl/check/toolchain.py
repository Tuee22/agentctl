# Copyright (c) 2026 agentctl contributors.
"""Native toolchain readiness observations and the selection-preserving gate step."""

import shutil
import socket
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import click

from agentctl.bootstrap import toolchain
from agentctl.bootstrap.pins import PinError, Pins
from agentctl.check.preconditions import ToolchainReadiness, toolchain_preconditions
from agentctl.hostfacts import HostContext, HostFacts, gather
from agentctl.result import Err, Result

GIB = 1024**3
GHC_BUDGET = 10 * GIB
CABAL_BUDGET = GIB
CACHE_BUDGET = 4 * GIB


def reachable(host: str, port: int) -> bool:
    """Observe a bounded TCP connection and close it without sending input."""
    try:
        with socket.create_connection((host, port), timeout=3):
            return True
    except OSError:
        return False


def existing_ancestor(path: Path) -> Path:
    """Find the existing ancestor whose filesystem receives a future directory."""
    return next(item for item in (path, *path.parents) if item.exists())


def budgets(*, ghc_ready: bool, cabal_ready: bool, shared: bool) -> tuple[int, int]:
    """Reserve only missing pins, combining simultaneous needs on a shared volume."""
    tools = (0 if ghc_ready else GHC_BUDGET) + (0 if cabal_ready else CABAL_BUDGET)
    cache = 0 if ghc_ready and cabal_ready else CACHE_BUDGET
    return (tools + cache, 0) if shared else (tools, cache)


type Reach = Callable[[str, int], bool]


def readiness(
    facts: HostFacts, context: HostContext, connect: Reach = reachable
) -> ToolchainReadiness:
    """Observe native storage and cold-only endpoint reachability for P7/P8/P10."""
    ghcup = existing_ancestor(facts.ghcup_destination.parent)
    cache = existing_ancestor(context.cache)
    ghcup_required, cache_required = budgets(
        ghc_ready=facts.ghc is not None,
        cabal_ready=facts.cabal is not None,
        shared=ghcup.stat().st_dev == cache.stat().st_dev,
    )
    ready = facts.ghc is not None and facts.cabal is not None
    return ToolchainReadiness(
        facts.family,
        facts.architecture,
        shutil.disk_usage(ghcup).free,
        shutil.disk_usage(cache).free,
        ghcup_required,
        cache_required,
        ready,
        ready or connect("downloads.haskell.org", 443),
        ready or connect("hackage.haskell.org", 443),
    )


type Observe = Callable[[HostFacts, HostContext], ToolchainReadiness]


def inspect_toolchain(
    context: HostContext,
    pins: Result[Pins, PinError],
    observe: Observe = readiness,
) -> tuple[str, ...]:
    """Translate native observation failures before any provisioning action occurs."""
    if isinstance(pins, Err):
        return (pins.error.message,)
    facts = gather(context, pins.value)
    if isinstance(facts, Err):
        return (facts.error.message,)
    try:
        observed = observe(facts.value, context)
    except OSError as exc:
        return (f"P7: cannot inspect toolchain storage: {exc}",)
    return toolchain_preconditions(observed, pins.value)


@dataclass(frozen=True, slots=True)
class EnsureStep:
    """The introduced non-tool step between Python checks and Haskell legs."""

    context: HostContext
    pins: Result[Pins, PinError]
    name: Literal["toolchain-ensure"] = "toolchain-ensure"


def run_step(step: EnsureStep) -> int:
    """Run the same guarded provisioning code that first-use commands call."""
    pins = step.pins
    if isinstance(pins, Err):
        click.echo(pins.error.message, err=True)
        return 1
    result = toolchain.checked(step.context, pins.value)
    if isinstance(result, Err):
        click.echo(result.error.message, err=True)
        return 1
    return 0
