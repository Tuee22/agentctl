# Copyright (c) 2026 agentctl contributors.
"""Pure numerical checks for a separately observed WSL workload budget."""

from dataclasses import dataclass

MILLIS_PER_CPU = 1000


@dataclass(frozen=True, slots=True)
class HostCapacity:
    """One host observation, not a guarantee about future resource pressure."""

    cpus: int
    available_memory: int
    commit_headroom: int
    vhd_free: int
    source_free: int
    shared_volume: bool


@dataclass(frozen=True, slots=True)
class GuestCapacity:
    """Observed guest capacity and affinity; VHD maximum is independently queried."""

    affinity: tuple[int, ...]
    available_memory: int
    available_swap: int
    volume_size: int
    volume_free: int
    free_inodes: int
    vhd_maximum: int


@dataclass(frozen=True, slots=True)
class MeasuredPeaks:
    """Retained single-build and single-test-worker calibration observations."""

    build_memory: int
    worker_memory: int
    fixed_memory: int
    build_storage: int
    worker_storage: int
    fixed_storage: int
    workload_inodes: int
    build_seconds: int
    test_seconds: int


@dataclass(frozen=True, slots=True)
class WorkloadBudget:
    """Chosen limits, explicit reserves and monitoring deadlines."""

    workers: int
    cpu_millis: int
    memory: int
    swap: int
    reserve_cpus: int
    reserve_memory: int
    reserve_guest_memory: int
    reserve_commit: int
    reserve_vhd: int
    reserve_source: int
    reserve_guest: int
    reserve_inodes: int
    source_writes: int
    step_seconds: int
    run_seconds: int
    sample_seconds: int


def _positive(values: tuple[int, ...]) -> bool:
    """Refuse unknown, boolean and nonpositive required observations."""
    return all(
        isinstance(value, int) and not isinstance(value, bool) and value > 0
        for value in values
    )


def _nonnegative(values: tuple[int, ...]) -> bool:
    """Permit zero only for explicitly optional swap and reserve quantities."""
    return all(
        isinstance(value, int) and not isinstance(value, bool) and value >= 0
        for value in values
    )


def problems(
    host: HostCapacity,
    guest: GuestCapacity,
    peaks: MeasuredPeaks,
    budget: WorkloadBudget,
) -> tuple[str, ...]:
    """Check measured peaks and explicit headroom without asserting real provenance."""
    required = (
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
        peaks.build_memory,
        peaks.worker_memory,
        peaks.fixed_memory,
        peaks.build_storage,
        peaks.worker_storage,
        peaks.fixed_storage,
        peaks.workload_inodes,
        peaks.build_seconds,
        peaks.test_seconds,
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
    optional = (guest.available_swap, budget.swap)
    if (
        not _positive(required)
        or not _nonnegative(optional)
        or not guest.affinity
        or len(set(guest.affinity)) != len(guest.affinity)
        or not _nonnegative(guest.affinity)
    ):
        return ("resource observation or budget is incomplete",)
    memory_peak = max(
        peaks.build_memory, peaks.fixed_memory + budget.workers * peaks.worker_memory
    )
    storage_peak = max(
        peaks.build_storage, peaks.fixed_storage + budget.workers * peaks.worker_storage
    )
    shared_free = min(host.vhd_free, host.source_free)
    shared_required = (
        storage_peak
        + budget.source_writes
        + max(budget.reserve_vhd, budget.reserve_source)
    )
    return (
        *(
            ("CPU budget exceeds observed capacity",)
            if budget.reserve_cpus >= host.cpus
            or budget.workers > len(guest.affinity)
            or budget.cpu_millis > (host.cpus - budget.reserve_cpus) * MILLIS_PER_CPU
            or budget.cpu_millis > len(guest.affinity) * MILLIS_PER_CPU
            else ()
        ),
        *(
            ("memory budget lacks measured headroom",)
            if budget.memory < memory_peak
            or host.available_memory < budget.memory + budget.reserve_memory
            or guest.available_memory < budget.memory + budget.reserve_guest_memory
            else ()
        ),
        *(
            ("commit or swap reserve is insufficient",)
            if guest.available_swap < budget.swap
            or host.commit_headroom
            < budget.memory + budget.swap + budget.reserve_commit
            else ()
        ),
        *(
            ("guest storage or inode reserve is insufficient",)
            if guest.volume_free > guest.volume_size
            or guest.volume_size > guest.vhd_maximum
            or guest.volume_free < storage_peak + budget.reserve_guest
            or guest.free_inodes < peaks.workload_inodes + budget.reserve_inodes
            else ()
        ),
        *(
            ("host storage reserve is insufficient",)
            if (host.shared_volume and shared_free < shared_required)
            or (
                not host.shared_volume
                and (
                    host.vhd_free < storage_peak + budget.reserve_vhd
                    or host.source_free < budget.source_writes + budget.reserve_source
                )
            )
            else ()
        ),
        *(
            ("monitoring deadlines are insufficient",)
            if not budget.sample_seconds < budget.step_seconds <= budget.run_seconds
            or budget.step_seconds < max(peaks.build_seconds, peaks.test_seconds)
            or budget.run_seconds < peaks.build_seconds + peaks.test_seconds
            else ()
        ),
    )
