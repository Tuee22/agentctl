# Copyright (c) 2026 agentctl contributors.
"""Independent literal-tail rows cross the public CLI, native mux and actual pane."""

import time
import tomllib
from pathlib import Path

import pytest

from tests.harness.launch import MuxObserver, observe_mux, prepare
from tests.harness.passthrough import WarmCaller, warm
from tests.harness.terminal import await_client, terminal
from tests.harness.tmux import PrivateMux

pytestmark = pytest.mark.evidence("observer")
WAIT_SECONDS = 10


def _creation(observer: MuxObserver, caller: WarmCaller) -> None:
    """Observe the actual create argv before a malformed invocation can fail later."""
    deadline = time.monotonic() + WAIT_SECONDS
    creates = observer.creates()
    while not creates and time.monotonic() < deadline:
        time.sleep(0.01)
        creates = observer.creates()
    assert len(creates) == 1, "multiplexer observer saw no create invocation"
    expected = [
        "new-session",
        "-d",
        "-s",
        "api-" + caller.case.agent,
        "-P",
        "-F",
        "#{pane_id}",
        "--",
        str(caller.executable),
        "pane-exec",
    ]
    assert creates[0][:-1] == expected, "agent argv reached multiplexer command line"
    assert Path(creates[0][-1]).is_absolute(), (
        "agent argv reached multiplexer command line"
    )
    assert Path(creates[0][-1]).name == "spec.json", (
        "agent argv reached multiplexer command line"
    )


@pytest.mark.parametrize("agent", ["claude", "codex"])
def test_through_stack_rows(root: Path, mux_server: PrivateMux, agent: str) -> None:
    """Keep every request-derived tail literal under a genuine native terminal."""
    rows = [
        row
        for row in tomllib.loads(
            (root / "tests/oracles/launch_argv.toml").read_text(encoding="utf-8")
        )["case"]
        if row["id"].startswith("through.")
    ]
    assert rows, "through-stack oracle has no rows"
    assert {row["input"]["agent"] for row in rows} == {"claude", "codex"}
    selected = [row for row in rows if row["input"]["agent"] == agent]
    assert selected, "agent has no through-stack oracle rows"
    for row in selected:
        observer = observe_mux(prepare(mux_server, agent))
        caller = warm(observer.case)
        arguments = tuple(row["input"]["args"])
        session = "api-" + agent
        with terminal(caller, (agent, *arguments)) as driver:
            _creation(observer, caller)
            await_client(mux_server, driver, session)
            records = caller.case.records()
            launched = [record for record in records if record["session"] == session]
            assert len(launched) == 1
            assert launched[0]["argv"] == row["expected"][1:], (
                "raw tail was parsed or changed"
            )
        ended = mux_server.raw("kill-session", "-t", "=" + session)
        assert ended.code == 0, ended.stderr
