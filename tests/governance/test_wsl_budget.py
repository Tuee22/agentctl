# Copyright (c) 2026 agentctl contributors.
"""Constructed budgets are consistency controls, not host observations."""

from dataclasses import replace

import pytest

from agentctl.check.wsl_budget import (
    GuestCapacity,
    HostCapacity,
    MeasuredPeaks,
    WorkloadBudget,
    problems,
)

pytestmark = pytest.mark.evidence("value")

HOST = HostCapacity(8, 16000, 16000, 50000, 50000, shared_volume=True)
GUEST = GuestCapacity((0, 1, 2, 3), 12000, 1000, 100000, 40000, 5000, 120000)
PEAKS = MeasuredPeaks(3000, 1000, 500, 4000, 2000, 1000, 300, 30, 20)
BUDGET = WorkloadBudget(
    2, 2000, 4000, 0, 1, 2000, 2000, 2000, 1000, 1000, 1000, 100, 100, 120, 300, 5
)


def test_budget_refuses_capacity_and_peak_gaps() -> None:
    """Measured aggregate peaks and explicit host and guest reserves all matter."""
    assert problems(HOST, GUEST, PEAKS, BUDGET) == ()
    assert "CPU budget exceeds observed capacity" in problems(
        replace(HOST, cpus=2), GUEST, PEAKS, BUDGET
    ), "CPU reserve was ignored"
    assert "memory budget lacks measured headroom" in problems(
        HOST, GUEST, PEAKS, replace(BUDGET, workers=4)
    ), "parallel memory peak was ignored"
    assert "memory budget lacks measured headroom" in problems(
        HOST, replace(GUEST, available_memory=5999), PEAKS, BUDGET
    ), "guest memory reserve was ignored"
    assert "commit or swap reserve is insufficient" in problems(
        replace(HOST, commit_headroom=5999), GUEST, PEAKS, BUDGET
    ), "commit reserve was ignored"
    assert "guest storage or inode reserve is insufficient" in problems(
        HOST, replace(GUEST, free_inodes=399), PEAKS, BUDGET
    ), "inode reserve was ignored"
    assert "guest storage or inode reserve is insufficient" in problems(
        HOST, replace(GUEST, vhd_maximum=99999), PEAKS, BUDGET
    )
    assert "monitoring deadlines are insufficient" in problems(
        HOST, GUEST, PEAKS, replace(BUDGET, sample_seconds=120)
    ), "monitor interval was ignored"
    assert "monitoring deadlines are insufficient" in problems(
        HOST, GUEST, PEAKS, replace(BUDGET, step_seconds=30, run_seconds=49)
    ), "whole-run deadline was ignored"


def test_budget_combines_shared_volume_demands() -> None:
    """Shared source and VHD writes consume the same host free-space reserve."""
    constrained = replace(HOST, vhd_free=6050, source_free=6050)
    assert "host storage reserve is insufficient" in problems(
        constrained, GUEST, PEAKS, BUDGET
    ), "shared volume demand was ignored"
    separate = replace(constrained, shared_volume=False, source_free=1100)
    assert problems(separate, GUEST, PEAKS, BUDGET) == ()


def test_budget_rejects_missing_or_invalid_observations() -> None:
    """Unknown peaks, absent affinity and zero headroom do not establish readiness."""
    assert problems(HOST, GUEST, replace(PEAKS, worker_memory=0), BUDGET) == (
        "resource observation or budget is incomplete",
    )
    assert problems(HOST, replace(GUEST, affinity=()), PEAKS, BUDGET) == (
        "resource observation or budget is incomplete",
    )
    assert problems(HOST, GUEST, PEAKS, replace(BUDGET, reserve_commit=0)) == (
        "resource observation or budget is incomplete",
    )
