# Copyright (c) 2026 agentctl contributors.
"""Constructed samples exercise the monitor's start refusals."""

from dataclasses import replace
from fractions import Fraction

import pytest

from agentctl.check.wsl_budget import GuestCapacity, HostCapacity, WorkloadBudget
from agentctl.check.wsl_cgroup import ProcessIdentity, ProcessLimits
from agentctl.check.wsl_monitor import MonitorSample, begin
from agentctl.foundation import Err

pytestmark = pytest.mark.evidence("value")

NONCE = "c" * 32
FIRST_NS = 1_000_000_000
ROOT = ProcessIdentity(201, 1, 3001)
ROOT_LIMIT = ProcessLimits(201, 3001, "/owned", frozenset({0, 1}), Fraction(2), 4096, 0)
HOST = HostCapacity(8, 16000, 16000, 50000, 50000, shared_volume=True)
GUEST = GuestCapacity((0, 1, 2, 3), 12000, 1000, 100000, 40000, 5000, 120000)
BUDGET = WorkloadBudget(
    2, 2000, 5000, 0, 1, 2000, 2000, 2000, 1000, 1000, 1000, 100, 100, 120, 300, 5
)
ALLOWED = frozenset({0, 1})
SAMPLE = MonitorSample(NONCE, FIRST_NS, (ROOT,), (ROOT_LIMIT,), HOST, GUEST)


def test_begin_refuses_bad_nonce_and_time() -> None:
    """A nonce that is not 32 hex digits or a non-positive time cannot start."""
    assert begin(replace(SAMPLE, nonce="short"), ROOT.pid, BUDGET, ALLOWED) == Err(
        "invalid monitor nonce or time"
    )
    assert isinstance(
        begin(replace(SAMPLE, monotonic_ns=0), ROOT.pid, BUDGET, ALLOWED), Err
    )


def test_begin_refuses_unknown_root_and_incomplete_samples() -> None:
    """An absent root or a zero capacity value is a refusal, not a state."""
    missing_root = begin(SAMPLE, ROOT.pid + 1, BUDGET, ALLOWED)
    assert missing_root == Err("invalid process tree snapshot")
    incomplete = begin(
        replace(SAMPLE, host=replace(HOST, available_memory=0)),
        ROOT.pid,
        BUDGET,
        ALLOWED,
    )
    assert incomplete == Err("resource sample incomplete")


def test_begin_refuses_tree_problems_and_reserve_breaches() -> None:
    """Over-budget members and breached reserves stop the first sample."""
    wide = replace(ROOT_LIMIT, cpu_quota=Fraction(3))
    result = begin(replace(SAMPLE, scope=(wide,)), ROOT.pid, BUDGET, ALLOWED)
    assert result == Err("process 201: process CPU limit exceeds budget")
    breached = replace(SAMPLE, host=replace(HOST, commit_headroom=1))
    assert begin(breached, ROOT.pid, BUDGET, ALLOWED) == Err(
        "host commit reserve breached"
    )
