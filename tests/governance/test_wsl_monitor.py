# Copyright (c) 2026 agentctl contributors.
"""Constructed samples exercise monitor transitions without attesting a run."""

from dataclasses import replace
from fractions import Fraction

import pytest

from agentctl.check.wsl_budget import GuestCapacity, HostCapacity, WorkloadBudget
from agentctl.check.wsl_cgroup import ProcessIdentity, ProcessLimits
from agentctl.check.wsl_monitor import MonitorSample, advance, begin
from agentctl.result import Err, Ok

pytestmark = pytest.mark.evidence("value")

NONCE = "a" * 32
ROOT = ProcessIdentity(101, 1, 1001)
CHILD = ProcessIdentity(102, 101, 1002)
ROOT_LIMIT = ProcessLimits(101, 1001, "/owned", frozenset({0, 1}), Fraction(2), 4096, 0)
CHILD_LIMIT = ProcessLimits(
    102, 1002, "/owned/child", frozenset({0, 1}), Fraction(1), 4096, 0
)
HOST = HostCapacity(8, 16000, 16000, 50000, 50000, shared_volume=True)
GUEST = GuestCapacity((0, 1, 2, 3), 12000, 1000, 100000, 40000, 5000, 120000)
BUDGET = WorkloadBudget(
    2, 2000, 5000, 0, 1, 2000, 2000, 2000, 1000, 1000, 1000, 100, 100, 120, 300, 5
)
ALLOWED = frozenset({0, 1})
FIRST = MonitorSample(
    NONCE, 1_000_000_000, (ROOT, CHILD), (ROOT_LIMIT, CHILD_LIMIT), HOST, GUEST
)


def test_monitor_detects_reparented_live_child() -> None:
    """A previously observed PID that remains alive outside scope is an escape."""
    started = begin(FIRST, ROOT.pid, BUDGET, ALLOWED)
    assert isinstance(started, Ok)
    escaped = replace(
        FIRST,
        monotonic_ns=2_000_000_000,
        processes=(ROOT, replace(CHILD, parent=1)),
        scope=(ROOT_LIMIT,),
    )
    result = advance(started.value, escaped, BUDGET, ALLOWED)
    assert isinstance(result, Err), "live escaped process was accepted"
    assert "observed process escaped cgroup" in result.error
    exited = replace(escaped, processes=(ROOT,))
    assert isinstance(advance(started.value, exited, BUDGET, ALLOWED), Ok)
    reused = replace(
        escaped, processes=(ROOT, replace(CHILD, parent=1, starttime=2002))
    )
    assert isinstance(advance(started.value, reused, BUDGET, ALLOWED), Ok), (
        "PID reuse was mistaken for escape"
    )


def test_monitor_rejects_stale_time_and_unobserved_members() -> None:
    """Nonce, sample cadence and process-to-scope identity must remain current."""
    started = begin(FIRST, ROOT.pid, BUDGET, ALLOWED)
    assert isinstance(started, Ok)
    late = replace(FIRST, monotonic_ns=7_000_000_000)
    assert isinstance(advance(started.value, late, BUDGET, ALLOWED), Err), (
        "missed monitor interval was accepted"
    )
    wrong_nonce = replace(FIRST, monotonic_ns=2_000_000_000, nonce="b" * 32)
    assert isinstance(advance(started.value, wrong_nonce, BUDGET, ALLOWED), Err)
    missing = replace(FIRST, monotonic_ns=2_000_000_000, scope=(ROOT_LIMIT,))
    assert isinstance(advance(started.value, missing, BUDGET, ALLOWED), Err), (
        "unobserved descendant was accepted"
    )
    assert isinstance(begin(missing, ROOT.pid, BUDGET, ALLOWED), Err), (
        "unobserved descendant was accepted"
    )
    replaced_root = replace(
        FIRST,
        monotonic_ns=2_000_000_000,
        processes=(replace(ROOT, starttime=2001), CHILD),
        scope=(replace(ROOT_LIMIT, starttime=2001), CHILD_LIMIT),
    )
    assert isinstance(advance(started.value, replaced_root, BUDGET, ALLOWED), Err), (
        "recycled monitor root was accepted"
    )
    current = replace(FIRST, monotonic_ns=2_000_000_000)
    assert isinstance(
        advance(started.value, current, replace(BUDGET, reserve_commit=1), ALLOWED), Err
    ), "changed monitor budget was accepted"
    assert isinstance(
        advance(started.value, current, BUDGET, frozenset({0, 1, 2})), Err
    ), "changed monitor affinity was accepted"


def test_monitor_reports_live_resource_pressure() -> None:
    """Changing capacity is checked against explicit host and guest reserves."""
    started = begin(FIRST, ROOT.pid, BUDGET, ALLOWED)
    assert isinstance(started, Ok)
    pressured = replace(
        FIRST,
        monotonic_ns=2_000_000_000,
        host=replace(HOST, commit_headroom=1999, available_memory=1999),
        guest=replace(GUEST, available_memory=1999, free_inodes=99),
    )
    result = advance(started.value, pressured, BUDGET, ALLOWED)
    assert isinstance(result, Err)
    assert "host commit reserve breached" in result.error, (
        "host commit pressure was ignored"
    )
    assert "host memory reserve breached" in result.error
    assert "guest memory reserve breached" in result.error
    assert "guest storage reserve breached" in result.error
