# Copyright (c) 2026 agentctl contributors.
"""Real logged-out parsers accept final launch argv and reject controlled twins."""

import json
import os
import tomllib
from pathlib import Path

import pytest

from agentctl.bootstrap import build
from agentctl.result import Ok
from tests.harness.agents import AuthProbe, isolated_environment, native_agent, probe
from tests.harness.launch import PaneProgram, native_pane
from tests.harness.tmux import PrivateMux

pytestmark = pytest.mark.evidence("real")
ARGV_REASON = "launched argv differs from required argument assembly"


def _arguments(
    mux: PrivateMux, agent: str, executable: Path, arguments: tuple[str, ...]
) -> tuple[str, ...]:
    """Use the actual publication selector and assembly through the owned evaluator."""
    output = build.execute_binary(
        mux.context,
        build.BinaryCall(
            "exe:agentctl-core-eval",
            input_text=json.dumps(
                {
                    "subject": "launch-final-argv",
                    "family": mux.family,
                    "agent": agent,
                    "executable": str(executable),
                    "args": arguments,
                }
            )
            + "\n",
        ),
    )
    assert isinstance(output, Ok), output
    assert output.value.code == 0, output.value.stderr
    decoded: object = json.loads(output.value.stdout)
    assert isinstance(decoded, list)
    assert all(isinstance(argument, str) for argument in decoded)
    return tuple(str(argument) for argument in decoded)


def _program(
    mux: PrivateMux, agent: str, scope: Path, arguments: tuple[str, ...]
) -> PaneProgram:
    """Give each parser case its own logged-out configuration and runtime state."""
    environment = isolated_environment(scope, os.environ)
    folder = scope / "project"
    folder.mkdir()
    executable = native_agent(agent, mux.family, environment)
    auth = probe(mux.context, AuthProbe(agent, executable, folder), environment)
    assert auth["state"] == "LoggedOut", "isolated agent used credentials"
    return PaneProgram(
        _arguments(mux, agent, executable, arguments), folder, environment
    )


def test_final_argv_accepted_logged_out(root: Path, mux_server: PrivateMux) -> None:
    """Within two seconds valid panes remain alive and invalid subcommands exit."""
    rows = tomllib.loads(
        (root / "tests/oracles/launch_argv.toml").read_text(encoding="utf-8")
    )["case"]
    for agent, rejected_arguments in (
        ("claude", ("auth", "status")),
        ("codex", ("exec",)),
    ):
        scope = mux_server.scope / ("installed-" + agent)
        positive = native_pane(
            mux_server,
            agent + "-accepted",
            _program(mux_server, agent, scope / "accepted", ()),
        )
        dead = positive.observe_startup()
        assert not dead, ARGV_REASON + ": " + positive.capture()
        flags = next(
            row["expected"]["mandatory_flags"]
            for row in rows
            if row["id"] == "agents." + agent
        )
        if mux_server.family == "Linux":
            actual = (Path("/proc") / str(positive.pid) / "cmdline").read_bytes()
            assert actual.split(b"\0")[-len(flags) - 1 : -1] == [
                flag.encode() for flag in flags
            ], ARGV_REASON
        separator = native_pane(
            mux_server,
            agent + "-separator",
            _program(mux_server, agent, scope / "separator", ("--",)),
        )
        separator_dead = separator.observe_startup()
        assert not separator_dead, (
            "real agent rejected a bare separator: " + separator.capture()
        )
        negative = native_pane(
            mux_server,
            agent + "-rejected",
            _program(mux_server, agent, scope / "rejected", rejected_arguments),
        )
        assert negative.observe_startup(), (
            "real agent rejected argv after the startup window: " + negative.capture()
        )
        assert negative.capture().strip(), (
            "real parser rejection produced no diagnostics"
        )
