# Copyright (c) 2026 agentctl contributors.
"""Private live launches and unattended native screen classification."""

import json
import os
import time
import tomllib
from pathlib import Path

from agentctl.bootstrap import build
from agentctl.process import Output, run
from agentctl.result import Ok
from tests.harness.agents import native_agent
from tests.harness.host import live_folder
from tests.harness.launch import LaunchCase
from tests.harness.nonce import fresh
from tests.harness.oracle import Store, assert_oracle, freeze, read_homes
from tests.harness.oracle import load as load_oracle
from tests.harness.sessions import rows
from tests.harness.tmux import PrivateMux

AUTH_FAILURE_EXIT = 8
PANE_FIELDS = 2
VISUAL_FIELDS = 4


def caller(mux: PrivateMux, agent: str) -> LaunchCase:
    """Keep user agent settings in place and give all multiplexer state to this test."""
    scope = mux.scope / agent
    scope.mkdir(mode=0o700)
    records = scope / "records"
    records.mkdir(mode=0o700)
    return LaunchCase(
        mux,
        agent,
        live_folder(mux.family, os.environ),
        records,
        fresh(mux.nonce),
        {
            **{
                key: value
                for key, value in os.environ.items()
                if key not in {"TMUX", "TMUX_PANE", "NO_COLOR"}
            },
            "TMUX_TMPDIR": str(mux.scope),
            "PSMUX_DATA_DIR": str(mux.endpoint),
            "PSMUX_NO_WARM": "1",
            "DISABLE_AUTOUPDATER": "1",
            "AGENTCTL_CACHE_DIR": str(scope / "cache"),
            "AGENTCTL_DATA_DIR": str(scope / "data"),
            "AGENTCTL_STATE_DIR": str(scope / "state"),
            "AGENTCTL_DISTRIBUTION": "ubuntu",
        },
    )


def refusal(root: Path, case: LaunchCase, status: int, output: Output) -> None:
    """Compare logged-out warnings to their oracle and distinguish probe failures."""
    if status == 1:
        store = load_oracle(root / "tests/oracles/auth_status.toml", read_homes(root))
        assert isinstance(store, Store), store
        expected = next(
            row.expected
            for row in store.effective
            if row.identifier == "auth.warning." + case.agent + ".logged-out"
        )
        actual = freeze({"exit": output.code, "lines": output.stderr.splitlines()})
        assert_oracle(
            lambda _: actual,
            None,
            expected,
            row_id="live launch refusal differs from oracle",
        )
    else:
        assert output.code == AUTH_FAILURE_EXIT, output
        assert "could not tell whether " + case.agent + " is logged in" in output.stderr
        assert "no session was started" in output.stderr
    name = "live-acceptance-" + case.agent
    assert case.mux.raw("has-session", "-t", "=" + name).code != 0
    positive = case.mux.actor("absence-control-" + case.agent)
    positive.record()
    assert case.mux.raw("has-session", "-t", "=" + positive.session).code == 0


def running(
    root: Path, case: LaunchCase, output: Output, arguments: tuple[str, ...]
) -> None:
    """Read native liveness and, on Linux, the actual launched process argv tail."""
    assert output.code == 0, output
    name = "live-acceptance-" + case.agent
    assert case.mux.raw("has-session", "-t", "=" + name).code == 0
    observed = case.mux.raw(
        "list-panes", "-t", "=" + name, "-F", "#{pane_pid}|#{pane_dead}"
    )
    assert observed.code == 0, observed.stderr
    fields = observed.stdout.strip().split("|")
    assert len(fields) == PANE_FIELDS
    pid = int(fields[0])
    case.mux.register_observer(pid)
    assert fields[1] == "0", "logged-in launch died during startup"
    if case.mux.family == "Linux":
        rows = tomllib.loads(
            (root / "tests/oracles/launch_argv.toml").read_text(encoding="utf-8")
        )["case"]
        identifier = (
            "argv." + case.agent + ".0"
            if not arguments
            else "through." + case.agent + ".separator"
        )
        expected = next(row["expected"][1:] for row in rows if row["id"] == identifier)
        actual = (Path("/proc") / str(pid) / "cmdline").read_bytes().split(b"\0")
        assert actual[-len(expected) - 1 : -1] == [
            argument.encode() for argument in expected
        ], "live argv differs from oracle"


def assert_live_class(case: LaunchCase) -> None:
    """Classify an independent native capture and the current status without input."""
    allowed = {"TrustDialog", "BypassWarning", "IdlePrompt"}
    deadline = time.monotonic() + 10
    name = "live-acceptance-" + case.agent
    displayed, independent, frame = _classes(case, name)
    while (
        displayed not in allowed or independent not in allowed
    ) and time.monotonic() < deadline:
        time.sleep(0.05)
        displayed, independent, frame = _classes(case, name)
    assert displayed in allowed, (
        "unexpected live status screen: " + case.agent + " " + displayed + "\n" + frame
    )
    assert independent in allowed, (
        "unexpected independent live screen: "
        + case.agent
        + " "
        + independent
        + "\n"
        + frame
    )


def _classes(case: LaunchCase, name: str) -> tuple[str, str, str]:
    """Keep actual terminal observations separate from status's captured value."""
    observed = rows(case.command("status", (name,)))[name]
    pane = observed["PANE"]
    displayed = observed["SCREEN"]
    fields = "#{cursor_x}|#{cursor_y}|#{pane_width}|#{pane_height}"
    before = case.mux.raw("display-message", "-p", "-t", pane, fields)
    captured = case.mux.raw("capture-pane", "-p", "-J", "-S", "-100", "-t", pane)
    styled = case.mux.raw("capture-pane", "-p", "-e", "-S", "0", "-t", pane)
    after = case.mux.raw("display-message", "-p", "-t", pane, fields)
    assert before.code == captured.code == styled.code == after.code == 0
    coordinates = tuple(int(value) for value in after.stdout.strip().split("|"))
    assert len(coordinates) == VISUAL_FIELDS
    visual = (
        None
        if before.stdout != after.stdout
        else {
            "x": coordinates[0],
            "y": coordinates[1],
            "width": coordinates[2],
            "height": coordinates[3],
            "styled": styled.stdout,
        }
    )
    output = build.execute_binary(
        case.mux.context,
        build.BinaryCall(
            "exe:agentctl-core-eval",
            input_text=json.dumps(
                {
                    "subject": "classify-" + case.agent,
                    "text": captured.stdout,
                    "dead": False,
                    "visual": visual,
                }
            )
            + "\n",
        ),
    )
    assert isinstance(output, Ok), output
    assert output.value.code == 0, output.value
    independent: object = json.loads(output.value.stdout)
    assert isinstance(independent, str)
    frame = (
        captured.stdout[-4000:]
        + "\nCURSOR "
        + after.stdout
        + "\nSTYLED "
        + repr(styled.stdout)
    )
    return displayed, independent, frame


def exercise_live(root: Path, mux: PrivateMux, arguments: tuple[str, ...] = ()) -> None:
    """Observe existing authentication and verify the corresponding complete branch."""
    for agent, status_arguments in (
        ("claude", ["auth", "status"]),
        ("codex", ["login", "status"]),
    ):
        case = caller(mux, agent)
        executable = native_agent(agent, mux.family, case.environment)
        status = run(
            [str(executable), *status_arguments],
            cwd=case.folder,
            env=case.environment,
            timeout=10,
        )
        assert isinstance(status, Ok), status
        output = case.invoke(arguments)
        if status.value.code == 0:
            running(root, case, output, arguments)
            assert_live_class(case)
        else:
            refusal(root, case, status.value.code, output)
