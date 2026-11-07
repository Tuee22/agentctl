# Copyright (c) 2026 agentctl contributors.
"""The foreground interpreter uses native captures, locks and byte receivers."""

import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from tests.harness.supervisor import (
    events,
    log_records,
    received_bytes,
    recovery_bytes,
    scripted_target,
    supervisor,
    utc_time,
    wait_frames,
    wait_observation,
    wait_received,
    wait_records,
)
from tests.harness.tmux import PrivateMux

INITIAL_DELAY = 0.3


@pytest.mark.evidence("observer")
@pytest.mark.parametrize("agent", ["claude", "codex"])
def test_sends_once_after_initial_delay(
    root: Path, mux_server: PrivateMux, agent: str
) -> None:
    """Only the watched post-baseline overload receives one literal and Enter."""
    recovery = recovery_bytes(root, mux_server.family, agent)
    trigger = mux_server.scope / f"overload-{agent}"
    frames = (
        ("IdlePrompt", {"kind": "file", "path": str(trigger)}),
        ("Overloaded", {"kind": "input", "bytes": len(recovery)}),
        ("Working", {"kind": "stay"}),
    )
    watched = scripted_target(mux_server, root, agent, frames)
    unwatched = scripted_target(mux_server, root, agent, frames)
    assert watched.case.command("watch", (watched.target,)).code == 0
    with supervisor(watched.case, initial=INITIAL_DELAY) as running:
        baseline = wait_observation(running, watched.target, "IdlePrompt")
        assert all(record["target"] != unwatched.target for record in baseline)
        assert received_bytes(watched.case.records_directory, watched.case.nonce) == b""
        trigger.touch()
        wait_frames(watched.case.records_directory, watched.case.nonce, 2)
        wait_frames(unwatched.case.records_directory, unwatched.case.nonce, 2)
        wait_observation(running, watched.target, "Overloaded")
        notice = wait_records(running, watched.target, "notify")[0]
        deadline = utc_time(notice["time"]) + timedelta(seconds=INITIAL_DELAY)
        bounded = time.monotonic() + 5
        while datetime.now(UTC) < deadline and time.monotonic() < bounded:
            assert (
                received_bytes(watched.case.records_directory, watched.case.nonce)
                == b""
            )
            time.sleep(0.005)
        wait_received(watched.case.records_directory, watched.case.nonce, recovery)
        receipts = events(
            watched.case.records_directory / "received.jsonl", watched.case.nonce
        )
        assert utc_time(receipts[0]["utc"]) >= deadline
        wait_frames(watched.case.records_directory, watched.case.nonce, 3)
        wait_observation(running, watched.target, "Working")
        assert (
            received_bytes(unwatched.case.records_directory, unwatched.case.nonce)
            == b""
        )
        attempts = [
            record
            for record in log_records(watched.case)
            if record["kind"] == "attempt"
        ]
        assert [record["outcome"] for record in attempts] == ["sent"]
        assert all(record["target"] == watched.target for record in attempts)


@pytest.mark.evidence("real")
def test_second_instance_refused(root: Path, mux_server: PrivateMux) -> None:
    """Contention names the polling holder, and an exited holder permits a fresh run."""
    target = scripted_target(
        mux_server, root, "claude", (("IdlePrompt", {"kind": "stay"}),)
    )
    assert target.case.command("watch", (target.target,)).code == 0
    with supervisor(target.case) as first:
        seen = wait_observation(first, target.target, "IdlePrompt")
        first_runs = {record["run"] for record in seen}
        count = len(wait_records(first, target.target, "observation"))
        second = target.case.command("supervisor", ("run",))
        assert second.code != 0, second
        assert f"by pid {first.pid}" in second.stderr
        assert first.alive()
        wait_records(first, target.target, "observation", count + 1)
        output = first.finish()
        if mux_server.family != "Windows":
            assert output.code == 0, output
    with supervisor(target.case) as third:
        seen = wait_observation(third, target.target, "IdlePrompt")
        assert {record["run"] for record in seen}.isdisjoint(first_runs)
        assert third.alive()


@pytest.mark.evidence("observer")
@pytest.mark.parametrize("agent", ["claude", "codex"])
def test_escalation_notifies(root: Path, mux_server: PrivateMux, agent: str) -> None:
    """A terminal failure reaches both sinks and receives no input beside a receiver."""
    trigger = mux_server.scope / f"terminal-{agent}"
    target = scripted_target(
        mux_server,
        root,
        agent,
        (
            ("IdlePrompt", {"kind": "file", "path": str(trigger)}),
            ("UsageLimit", {"kind": "stay"}),
        ),
    )
    recovery = recovery_bytes(root, mux_server.family, agent)
    control = scripted_target(
        mux_server,
        root,
        agent,
        (
            ("IdlePrompt", {"kind": "file", "path": str(trigger)}),
            ("Overloaded", {"kind": "input", "bytes": len(recovery)}),
            ("Working", {"kind": "stay"}),
        ),
    )
    for name in (target.target, control.target):
        assert target.case.command("watch", (name,)).code == 0
    with supervisor(target.case) as running:
        wait_observation(running, target.target, "IdlePrompt")
        wait_observation(running, control.target, "IdlePrompt")
        trigger.touch()
        wait_observation(running, target.target, "UsageLimit")
        notices = wait_records(running, target.target, "notify")
        assert notices[0]["level"] == "error"
        assert notices[0]["message"] == "requires attention: UsageLimit"
        wait_received(control.case.records_directory, control.case.nonce, recovery)
        assert received_bytes(target.case.records_directory, target.case.nonce) == b""
        output = running.finish()
        assert (
            f"agentctl: {target.target}: requires attention: UsageLimit"
            in output.stderr
        )
