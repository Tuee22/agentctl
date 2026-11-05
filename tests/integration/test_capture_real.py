# Copyright (c) 2026 agentctl contributors.
"""Capture actual terminal wraps and UTF-8 through the production observer."""

import json
import time
from collections.abc import Mapping
from pathlib import Path

import pytest

from agentctl.bootstrap import build
from agentctl.result import Ok
from tests.harness.launch import observe_mux, prepare
from tests.harness.screens import normalized
from tests.harness.tmux import PrivateMux, object_value

REASON = "native capture differs from independently normalized fixture"
WAIT_SECONDS = 10
CHANGED_CURSOR_X = 3
RETRIED_FACT_QUERIES = 4


def capture(
    mux: PrivateMux, pane: str, *, changes: Mapping[str, str] | None = None
) -> dict[str, object]:
    """Reach the production capture edge through the application-owned native test."""
    output = build.execute_binary(
        mux.context,
        build.BinaryCall(
            "test:agentctl-core-test",
            ("--mux-fixture",),
            input_text=json.dumps(
                {"operation": "capture", "directory": str(mux.scope), "pane": pane}
            ),
            settings=tuple(
                {**mux.environment, **(changes or {}), "LC_ALL": "C"}.items()
            ),
        ),
    )
    assert isinstance(output, Ok), output
    assert output.value.code == 0, output.value
    value = object_value(output.value.stdout)
    assert set(value) == {"text", "dead", "visual"}
    assert isinstance(value["text"], str)
    assert isinstance(value["dead"], bool)
    visual = value["visual"]
    assert isinstance(visual, dict)
    assert set(visual) == {"x", "y", "width", "height", "styled"}
    for field in ("x", "y", "width", "height"):
        assert isinstance(visual[field], int)
        assert not isinstance(visual[field], bool)
    assert isinstance(visual["styled"], str)
    return value


@pytest.mark.evidence("observer")
def test_capture_roundtrip_on_private_server(
    root: Path, mux_server: PrivateMux
) -> None:
    """Round-trip fixtures at a narrow width and independently observe pane death."""
    fixtures = (
        root / "tests/fixtures/terminal/utf8-and-wrap.txt",
        *sorted((root / "tests/fixtures/screens").glob("*/*/*.txt")),
    )
    for index, fixture in enumerate(fixtures):
        text = fixture.read_text(encoding="utf-8")
        expected = normalized(text)
        longest = max(map(len, text.splitlines()))
        width = max(4, min(24, longest - 1))
        assert width < longest
        actor = mux_server.actor(
            "capture-" + str(index),
            disposition="fixture",
            arguments=("--agentctl-screen-fixture", str(fixture)),
        )
        assert actor.record()["nonce"] == actor.nonce
        resized = mux_server.raw(
            "resize-window", "-t", actor.pane, "-x", str(width), "-y", "40"
        )
        assert resized.code == 0, resized
        dimensions = mux_server.raw(
            "display-message", "-p", "-t", actor.pane, "#{pane_width}"
        )
        assert dimensions.code == 0
        assert int(dimensions.stdout.strip()) == width
        (actor.record_directory / "render").write_text("render", encoding="utf-8")
        deadline = time.monotonic() + WAIT_SECONDS
        raw = mux_server.raw("capture-pane", "-p", "-J", "-S", "-100", "-t", actor.pane)
        while normalized(raw.stdout) != expected and time.monotonic() < deadline:
            time.sleep(0.01)
            raw = mux_server.raw(
                "capture-pane", "-p", "-J", "-S", "-100", "-t", actor.pane
            )
        assert raw.code == 0, raw
        assert normalized(raw.stdout) == expected, (
            "fixture never reached native terminal"
        )
        observed = capture(mux_server, actor.pane)
        assert observed["text"] == expected, REASON
        assert observed["dead"] is False, REASON
        (actor.record_directory / "stop").write_text("exit", encoding="utf-8")
        deadline = time.monotonic() + WAIT_SECONDS
        state = mux_server.raw(
            "display-message", "-p", "-t", actor.pane, "#{pane_dead}"
        )
        while state.stdout.strip() != "1" and time.monotonic() < deadline:
            time.sleep(0.01)
            state = mux_server.raw(
                "display-message", "-p", "-t", actor.pane, "#{pane_dead}"
            )
        assert state.code == 0
        assert state.stdout.strip() == "1"
        assert capture(mux_server, actor.pane)["dead"] is True


@pytest.mark.evidence("observer")
def test_capture_keeps_prompt_visuals(mux_server: PrivateMux) -> None:
    """Native faint text and cursor facts distinguish a hint from a draft at Home."""
    marker = "\u276f"
    text = marker + " Try inspect parser"
    path = mux_server.scope / "visual.txt"
    path.write_text(text, encoding="utf-8")
    actor = mux_server.actor(
        "visual",
        disposition="fixture",
        arguments=("--agentctl-screen-fixture", str(path)),
    )
    assert actor.record()["nonce"] == actor.nonce
    assert (
        mux_server.raw("resize-window", "-t", actor.pane, "-x", "40", "-y", "8").code
        == 0
    )
    for index, (prefix, expected) in enumerate(
        (("\x1b[2m", "IdlePrompt"), ("", "PartialInput"))
    ):
        payload = marker + " " + prefix + "Try inspect parser\x1b[0m\x1b[1;3H"
        pending = path.with_suffix(".pending")
        pending.write_text(payload, encoding="utf-8")
        pending.replace(path)
        trigger = actor.record_directory / "render"
        pending = trigger.with_suffix(".pending")
        pending.write_text(str(index), encoding="utf-8")
        pending.replace(trigger)
        deadline = time.monotonic() + WAIT_SECONDS
        raw = mux_server.raw("capture-pane", "-p", "-e", "-S", "0", "-t", actor.pane)
        while (
            ("\x1b[2m" in raw.stdout) != bool(prefix)
            or normalized(
                mux_server.raw("capture-pane", "-p", "-J", "-t", actor.pane).stdout
            )
            != text
        ) and time.monotonic() < deadline:
            time.sleep(0.01)
            raw = mux_server.raw(
                "capture-pane", "-p", "-e", "-S", "0", "-t", actor.pane
            )
        assert raw.code == 0
        assert ("\x1b[2m" in raw.stdout) == bool(prefix)
        observed = capture(mux_server, actor.pane)
        assert observed["text"] == text
        visual = observed["visual"]
        assert isinstance(visual, dict)
        assert visual["styled"] == raw.stdout
        assert {key: visual[key] for key in ("x", "y", "width", "height")} == {
            "x": 2,
            "y": 0,
            "width": 40,
            "height": 8,
        }
        output = build.execute_binary(
            mux_server.context,
            build.BinaryCall(
                "exe:agentctl-core-eval",
                input_text=json.dumps({"subject": "classify-claude", **observed})
                + "\n",
            ),
        )
        assert isinstance(output, Ok), output
        assert output.value.code == 0, output.value
        assert json.loads(output.value.stdout) == expected, (
            "native composer evidence misclassified"
        )


@pytest.mark.evidence("observer")
def test_capture_retries_changed_cursor(mux_server: PrivateMux) -> None:
    """Change a native pane after its first facts query, before capture completes."""
    path = mux_server.scope / "changing.txt"
    frame = "\u276f \x1b[2mTry inspect parser\x1b[0m\x1b[1;3H"
    path.write_text(frame, encoding="utf-8")
    actor = mux_server.actor(
        "changing",
        disposition="fixture",
        arguments=("--agentctl-screen-fixture", str(path)),
    )
    assert actor.record()["nonce"] == actor.nonce
    trigger = actor.record_directory / "render"
    trigger.write_text("initial", encoding="utf-8")
    deadline = time.monotonic() + WAIT_SECONDS
    state = mux_server.raw("display-message", "-p", "-t", actor.pane, "#{cursor_x}")
    while state.stdout.strip() != "2" and time.monotonic() < deadline:
        time.sleep(0.01)
        state = mux_server.raw("display-message", "-p", "-t", actor.pane, "#{cursor_x}")
    assert state.code == 0
    assert state.stdout.strip() == "2"
    pending = path.with_suffix(".pending")
    pending.write_text(frame.replace("[1;3H", "[1;4H"), encoding="utf-8")
    pending.replace(path)
    release = actor.record_directory / "capture-release"
    release.write_text("release after first native facts", encoding="utf-8")
    observer = observe_mux(prepare(mux_server, "claude"))
    observed = capture(
        mux_server,
        actor.pane,
        changes={
            **observer.case.environment,
            "AGENTCTL_FAKE_CAPTURE_RELEASE": str(release),
        },
    )
    visual = observed["visual"]
    assert isinstance(visual, dict)
    assert visual["x"] == CHANGED_CURSOR_X
    native = mux_server.raw("display-message", "-p", "-t", actor.pane, "#{cursor_x}")
    assert native.code == 0
    assert native.stdout.strip() == "3"
    facts = [
        argv
        for argv in observer.arguments()
        if argv[-1:]
        == ["#{pane_dead}|#{cursor_x}|#{cursor_y}|#{pane_width}|#{pane_height}"]
    ]
    assert len(facts) >= RETRIED_FACT_QUERIES, (
        "capture accepted changed native cursor snapshots"
    )
