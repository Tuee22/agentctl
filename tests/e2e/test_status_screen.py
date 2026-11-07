# Copyright (c) 2026 agentctl contributors.
"""Status observes changed real panes and chooses each registered agent's classifier."""

import json
import time
from pathlib import Path

import pytest

from agentctl.bootstrap import build
from agentctl.result import Ok
from tests.harness.launch import LaunchCase, prepare
from tests.harness.screens import ScreenClass, normalized, read
from tests.harness.sessions import rows
from tests.harness.tmux import PrivateMux

pytestmark = pytest.mark.evidence("observer")
REASON = "status screen differs from current fixture"
AGENT_REASON = "status selected another agent's classifier"


def publish(path: Path, text: str) -> None:
    """Publish test-owned frames and render triggers atomically."""
    temporary = path.with_suffix(path.suffix + ".pending")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def await_frame(mux: PrivateMux, pane: str, text: str) -> None:
    """Observe the actual native terminal before asking status to classify it."""
    deadline = time.monotonic() + 10
    captured = mux.raw("capture-pane", "-p", "-J", "-t", pane, "-S", "-100")
    while (
        normalized(captured.stdout) != normalized(text) and time.monotonic() < deadline
    ):
        time.sleep(0.01)
        captured = mux.raw("capture-pane", "-p", "-J", "-t", pane, "-S", "-100")
    assert captured.code == 0
    assert normalized(captured.stdout) == normalized(text), "fixture did not reach pane"


def launch(case: LaunchCase, path: Path, text: str) -> str:
    """Start a nonce-bound fake waiting for explicit fixture playback."""
    publish(path, text)
    output = case.invoke(("--agentctl-screen-fixture", str(path)))
    assert output.code == 0, output
    actual = rows(case.command("list"))["api-" + case.agent]
    launched = [record for record in case.records() if record["pane"] == actual["PANE"]]
    assert len(launched) == 1
    assert launched[0]["nonce"] == case.nonce
    publish(case.records_directory / "render", "initial")
    await_frame(case.mux, actual["PANE"], text)
    return actual["PANE"]


def test_screen_column_shows_fixture_class(root: Path, mux_server: PrivateMux) -> None:
    """The same managed pane changes class, then reports its real retained death."""
    loaded = read(root / "tests/fixtures/screens")
    assert isinstance(loaded, Ok), loaded
    for agent in ("claude", "codex"):
        case = prepare(mux_server, agent, disposition="fixture")
        path = case.folder / "screen.txt"
        fixtures = {
            fixture.kind: fixture
            for fixture in loaded.value
            if fixture.agent == agent and fixture.path.stem == "documented"
        }
        pane = launch(case, path, fixtures[ScreenClass.IDLE].text)
        name = "api-" + agent
        for kind in ScreenClass:
            if kind is not ScreenClass.EXITED:
                publish(path, fixtures[kind].text)
                publish(case.records_directory / "render", kind.value)
                await_frame(mux_server, pane, fixtures[kind].text)
                observed = rows(case.command("status", (name,)))[name]
                assert observed["SCREEN"] == kind.value, REASON
        target = mux_server.pane_option_target(name, pane)
        assert (
            mux_server.raw(
                "set-option", "-p", "-t", target, "remain-on-exit", "on"
            ).code
            == 0
        )
        publish(case.records_directory / "stop", "exit")
        deadline = time.monotonic() + 10
        dead = mux_server.raw("display-message", "-p", "-t", pane, "#{pane_dead}")
        while dead.stdout.strip() != "1" and time.monotonic() < deadline:
            time.sleep(0.01)
            dead = mux_server.raw("display-message", "-p", "-t", pane, "#{pane_dead}")
        assert dead.code == 0
        assert dead.stdout.strip() == "1"
        observed = rows(case.command("status", (name,)))[name]
        assert observed["SCREEN"] == ScreenClass.EXITED.value, REASON


def test_screen_column_uses_the_agents_classifier(
    root: Path, mux_server: PrivateMux
) -> None:
    """Select by managed identity or the adopted pane's recorded agent."""
    fixture = root / "tests/fixtures/screens/codex/Overloaded/documented.txt"
    text = fixture.read_text(encoding="utf-8")
    case = prepare(mux_server, "codex", disposition="fixture")
    pane = launch(case, case.folder / "screen.txt", text)
    opposite = build.execute_binary(
        mux_server.context,
        build.BinaryCall(
            "exe:agentctl-core-eval",
            input_text=json.dumps(
                {"subject": "classify-claude", "text": text, "dead": False}
            )
            + "\n",
        ),
    )
    assert isinstance(opposite, Ok), opposite
    assert opposite.value.code == 0
    assert json.loads(opposite.value.stdout) == ScreenClass.UNKNOWN.value
    observed = rows(case.command("status", ("api-codex",)))["api-codex"]
    assert observed["PANE"] == pane
    assert observed["SCREEN"] == ScreenClass.OVERLOADED.value, AGENT_REASON
    foreign = mux_server.actor(
        "adopted-screen",
        disposition="fixture",
        arguments=("--agentctl-screen-fixture", str(fixture)),
    )
    assert foreign.record()["nonce"] == foreign.nonce
    publish(foreign.record_directory / "render", "render")
    await_frame(mux_server, foreign.pane, text)
    assert case.command("adopt", (foreign.pane, "--agent", "claude")).code == 0
    observed = rows(case.command("status", (foreign.pane,)))[foreign.pane]
    assert observed["SCREEN"] == ScreenClass.UNKNOWN.value, AGENT_REASON
    assert observed["KIND"] == "adopted"
