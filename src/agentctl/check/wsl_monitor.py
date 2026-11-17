# Copyright (c) 2026 agentctl contributors.
"""Pure transition checks for independently observed WSL workload samples."""

import re
from dataclasses import dataclass

from agentctl.check.wsl_budget import (
    MILLIS_PER_CPU,
    GuestCapacity,
    HostCapacity,
    WorkloadBudget,
)
from agentctl.check.wsl_cgroup import ProcessIdentity, ProcessLimits
from agentctl.check.wsl_tree import descendants, tree_problems
from agentctl.foundation import Err, Ok, Result

NANOSECONDS_PER_SECOND = 1_000_000_000


@dataclass(frozen=True, slots=True)
class MonitorSample:
    """One independently collected sample, not an authenticated monitor record."""

    nonce: str
    monotonic_ns: int
    processes: tuple[ProcessIdentity, ...]
    scope: tuple[ProcessLimits, ...]
    host: HostCapacity
    guest: GuestCapacity


@dataclass(frozen=True, slots=True)
class MonitorState:
    """Previously seen owned identities and the bounded run's time boundary."""

    nonce: str
    root_pid: int
    root_start: int
    started_ns: int
    last_ns: int
    budget: WorkloadBudget
    allowed_cpus: frozenset[int]
    seen: frozenset[tuple[int, int]]


def _pressure(
    sample: MonitorSample, budget: WorkloadBudget, allowed_cpus: frozenset[int]
) -> tuple[str, ...]:
    """Compare current free resources with the chosen nonzero reserves."""
    host, guest = sample.host, sample.guest
    values = (
        host.cpus,
        host.available_memory,
        host.commit_headroom,
        host.vhd_free,
        host.source_free,
        guest.available_memory,
        guest.volume_size,
        guest.volume_free,
        guest.free_inodes,
        guest.vhd_maximum,
        budget.workers,
        budget.cpu_millis,
        budget.memory,
        budget.reserve_cpus,
        budget.reserve_memory,
        budget.reserve_guest_memory,
        budget.reserve_commit,
        budget.reserve_vhd,
        budget.reserve_source,
        budget.reserve_guest,
        budget.reserve_inodes,
        budget.source_writes,
        budget.step_seconds,
        budget.run_seconds,
        budget.sample_seconds,
    )
    if (
        any(isinstance(value, bool) or value <= 0 for value in values)
        or any(
            isinstance(value, bool) or value < 0
            for value in (guest.available_swap, budget.swap)
        )
        or not budget.sample_seconds < budget.step_seconds <= budget.run_seconds
    ):
        return ("resource sample incomplete",)
    return (
        *(
            ("host memory reserve breached",)
            if host.available_memory < budget.reserve_memory
            else ()
        ),
        *(
            ("host commit reserve breached",)
            if host.commit_headroom < budget.reserve_commit
            else ()
        ),
        *(
            ("guest memory reserve breached",)
            if guest.available_memory < budget.reserve_guest_memory
            else ()
        ),
        *(
            ("host storage reserve breached",)
            if host.vhd_free < budget.reserve_vhd
            or host.source_free < budget.reserve_source
            else ()
        ),
        *(
            ("guest storage reserve breached",)
            if guest.volume_free > guest.volume_size
            or guest.volume_size > guest.vhd_maximum
            or guest.volume_free < budget.reserve_guest
            or guest.free_inodes < budget.reserve_inodes
            else ()
        ),
        *(
            ("CPU capacity changed",)
            if budget.reserve_cpus >= host.cpus
            or not guest.affinity
            or len(set(guest.affinity)) != len(guest.affinity)
            or not allowed_cpus
            or not allowed_cpus <= frozenset(guest.affinity)
            or budget.cpu_millis > (host.cpus - budget.reserve_cpus) * MILLIS_PER_CPU
            or budget.cpu_millis > len(guest.affinity) * MILLIS_PER_CPU
            else ()
        ),
    )


def _identities(
    sample: MonitorSample, root_pid: int
) -> Result[frozenset[tuple[int, int]], str]:
    """Require every current descendant to match one bounded scope observation."""
    tree = descendants(root_pid, sample.processes)
    if isinstance(tree, Err):
        return tree
    expected = frozenset((item.pid, item.starttime) for item in tree.value)
    observed = frozenset((item.pid, item.starttime) for item in sample.scope)
    if len(observed) != len(sample.scope) or expected != observed:
        return Err("scope identities differ from process descendants")
    return Ok(observed)


def begin(
    sample: MonitorSample,
    root_pid: int,
    budget: WorkloadBudget,
    allowed_cpus: frozenset[int],
) -> Result[MonitorState, str]:
    """Start a monitor trace only from a complete, bounded first sample."""
    if (
        re.fullmatch(r"[0-9a-f]{32}", sample.nonce) is None
        or isinstance(sample.monotonic_ns, bool)
        or sample.monotonic_ns <= 0
    ):
        return Err("invalid monitor nonce or time")
    owned = _identities(sample, root_pid)
    if isinstance(owned, Err):
        return owned
    failures = (
        *_pressure(sample, budget, allowed_cpus),
        *tree_problems(sample.scope, budget, allowed_cpus),
    )
    if failures:
        return Err("; ".join(failures))
    root = next(item for item in sample.processes if item.pid == root_pid)
    return Ok(
        MonitorState(
            sample.nonce,
            root_pid,
            root.starttime,
            sample.monotonic_ns,
            sample.monotonic_ns,
            budget,
            allowed_cpus,
            owned.value,
        )
    )


def advance(
    state: MonitorState,
    sample: MonitorSample,
    budget: WorkloadBudget,
    allowed_cpus: frozenset[int],
) -> Result[MonitorState, str]:
    """Detect missed samples, pressure and previously observed live escapes.

    This calculation cannot detect an unobserved short-lived escape or attest
    either sample's origin. The caller must continuously observe and stop only
    owned work when a failure occurs.
    """
    if (
        re.fullmatch(r"[0-9a-f]{32}", state.nonce) is None
        or sample.nonce != state.nonce
        or isinstance(sample.monotonic_ns, bool)
        or state.started_ns <= 0
        or state.last_ns < state.started_ns
        or (state.root_pid, state.root_start) not in state.seen
        or budget != state.budget
        or allowed_cpus != state.allowed_cpus
        or sample.monotonic_ns <= state.last_ns
        or sample.monotonic_ns - state.last_ns
        > budget.sample_seconds * NANOSECONDS_PER_SECOND
        or sample.monotonic_ns - state.started_ns
        > budget.run_seconds * NANOSECONDS_PER_SECOND
    ):
        return Err("monitor identity or timing invalid")
    owned = _identities(sample, state.root_pid)
    if isinstance(owned, Err):
        return owned
    if (state.root_pid, state.root_start) not in owned.value:
        return Err("monitor root identity changed")
    live = frozenset((item.pid, item.starttime) for item in sample.processes)
    if (state.seen & live) - owned.value:
        return Err("observed process escaped cgroup")
    failures = (
        *_pressure(sample, budget, allowed_cpus),
        *tree_problems(sample.scope, budget, allowed_cpus),
    )
    if failures:
        return Err("; ".join(failures))
    return Ok(
        MonitorState(
            state.nonce,
            state.root_pid,
            state.root_start,
            state.started_ns,
            sample.monotonic_ns,
            state.budget,
            state.allowed_cpus,
            state.seen | owned.value,
        )
    )
