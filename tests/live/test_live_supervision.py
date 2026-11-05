# Copyright (c) 2026 agentctl contributors.
"""Supervise existing authenticated agents without typing or answering a dialog."""

from pathlib import Path

import pytest

from agentctl.process import run
from agentctl.result import Ok
from tests.e2e.test_adopt import pane_facts
from tests.harness.agents import native_agent
from tests.harness.live import assert_live_class, caller, refusal, running
from tests.harness.sessions import rows
from tests.harness.supervisor import (
    log_records,
    observe_polls,
    recovery_bytes,
    supervisor,
    wait_records,
)
from tests.harness.tmux import PrivateMux

pytestmark = pytest.mark.evidence("real")


def test_live_watch_sends_nothing(root: Path, mux_server: PrivateMux) -> None:
    """Each auth branch is automatic, and every actual live poll remains read-only."""
    for agent, arguments in (
        ("claude", ["auth", "status"]),
        ("codex", ["login", "status"]),
    ):
        case = caller(mux_server, agent)
        executable = native_agent(agent, mux_server.family, case.environment)
        status = run(
            [str(executable), *arguments],
            cwd=case.folder,
            env=case.environment,
            timeout=10,
        )
        assert isinstance(status, Ok), status
        output = case.invoke()
        if status.value.code != 0:
            refusal(root, case, status.value.code, output)
            continue
        running(root, case, output, ())
        assert_live_class(case)
        name = "live-acceptance-" + agent
        pane = rows(case.command("status", (name,)))[name]["PANE"]
        identity = pane_facts(mux_server, pane)
        assert case.command("watch", (name,)).code == 0
        with supervisor(case) as controller:
            wait_records(controller, name, "observation")
            observe_polls(controller, name, 3)
            assert_live_class(case)
            controller.finish()
        records = log_records(case)
        observations = [row for row in records if row["kind"] == "observation"]
        assert observations
        assert {row["target"] for row in observations} == {name}
        assert {row["agent"] for row in observations} == {agent}
        assert {row["class"] for row in observations} <= {
            "TrustDialog",
            "BypassWarning",
            "IdlePrompt",
        }
        assert not any(row["kind"] == "attempt" for row in records)
        captured = mux_server.raw("capture-pane", "-p", "-J", "-t", pane)
        assert captured.code == 0, captured
        recovery = recovery_bytes(root, mux_server.family, agent)[:-1].decode()
        assert recovery not in captured.stdout
        assert pane_facts(mux_server, pane) == identity
