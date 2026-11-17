# Copyright (c) 2026 agentctl contributors.
"""Constructed Linux capacity values are not native WSL evidence."""

from dataclasses import replace

import pytest

from agentctl.check.wsl_guest_sample import (
    GuestReading,
    MemoryReading,
    affinity,
    affinity_bytes,
    capacity,
    memory,
)
from agentctl.result import Err, Ok

pytestmark = pytest.mark.evidence("value")


def test_guest_memory_and_affinity_refusals() -> None:
    """Only the exact available-memory and unique affinity counters count."""
    text = "MemFree: 12 kB\nMemAvailable: 64 kB\nSwapFree: 8 kB\n"
    assert memory(text) == Ok(MemoryReading(64 * 1024, 8 * 1024)), (
        "wrong Linux available memory was accepted"
    )
    assert isinstance(memory(text + "MemAvailable: 65 kB\n"), Err)
    assert isinstance(memory("MemAvailable: 0 kB\nSwapFree: 0 kB\n"), Err)
    assert isinstance(memory("MemAvailable:\n64 kB\nSwapFree: 8 kB\n"), Err)
    assert isinstance(
        memory("MemAvailable: " + "9" * 100 + " kB\nSwapFree: 0 kB\n"), Err
    )
    assert affinity("Cpus_allowed_list:\t0-2,4\n") == Ok((0, 1, 2, 4))
    assert isinstance(affinity("Cpus_allowed_list: 0-2,2\n"), Err)
    assert isinstance(affinity("Cpus_allowed_list: 0\nCpus_allowed_list: 1\n"), Err)
    assert affinity_bytes(b"Name:\t\xff\nCpus_allowed_list:\t0-1\n") == Ok((0, 1)), (
        "unrelated process-name bytes blocked affinity"
    )
    assert isinstance(affinity_bytes(b"Cpus_allowed_list:\t\xff\n"), Err)


def test_guest_capacity_requires_consistent_vhd_maximum() -> None:
    """A smaller VHD maximum or invalid local observation refuses the join."""
    reading = GuestReading((0, 1), 8000, 0, 10000, 6000, 500)
    assert isinstance(capacity(reading, 12000), Ok)
    assert isinstance(capacity(reading, 9999), Err), "undersized VHD was accepted"
    assert isinstance(capacity(replace(reading, volume_free=10001), 12000), Err)
    assert isinstance(capacity(replace(reading, affinity=()), 12000), Err)
    assert isinstance(capacity(reading, 0), Err)
