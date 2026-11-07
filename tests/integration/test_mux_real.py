# Copyright (c) 2026 agentctl contributors.
"""Typed native commands against private servers and real nonce-bound observers."""

import base64
import shlex
import sys
import time
from dataclasses import replace
from pathlib import Path

import pytest

from agentctl.check.writeguard import containment
from agentctl.process import alive
from agentctl.result import Err, Ok
from tests.harness.launch import observe_mux, prepare
from tests.harness.tmux import Actor, PrivateMux, pane_identifier

WAIT_SECONDS = 10
EXIT_STATUS = 3
RELEASE_POLL = 2
EXACT_TARGET_CALLS = 3
FORWARDED = ("x;", "#{pane_id}", "#(id)", "$(id)", "--", "", "one\ntwo", "λ日")


def _capture(mux: PrivateMux, actor: Actor, expected: str) -> str:
    """Wait for the real terminal to contain the controlled actor's output."""
    deadline = time.monotonic() + WAIT_SECONDS
    result = mux.command("capture", pane=actor.pane, lines=100)
    text = str(result["stdout"])
    while expected not in text and time.monotonic() < deadline:
        time.sleep(0.01)
        result = mux.command("capture", pane=actor.pane, lines=100)
        text = str(result["stdout"])
    assert result["code"] == 0, result
    assert expected in text, "native capture lost fake-agent output"
    return text


@pytest.mark.evidence("observer")
def test_private_server_roundtrip(mux_server: PrivateMux) -> None:
    """The trampoline preserves caller data and the vocabulary targets its pane."""
    actor = mux_server.actor("roundtrip", arguments=FORWARDED)
    record = actor.record()
    assert record["argv"] == list(actor.arguments)
    assert Path(str(record["cwd"])).resolve() == actor.folder.resolve()
    assert record["session"] == actor.session
    assert record["pane"] == actor.pane
    keys = record["env_keys"]
    assert isinstance(keys, list)
    assert set(keys) == set(actor.environment) | {"TERM", "TMUX", "TMUX_PANE"}
    assert "CALLER_ONLY" in keys
    assert "SERVER_ONLY" not in keys
    assert not actor.spec.exists()
    raw_pid = mux_server.raw("display-message", "-p", "-t", actor.pane, "#{pane_pid}")
    assert raw_pid.code == 0, raw_pid.stderr
    if mux_server.family == "Windows":
        assert record["pid"] != int(raw_pid.stdout.strip())
    else:
        assert record["pid"] == int(raw_pid.stdout.strip())
    assert mux_server.command("has-session", session=actor.session)["code"] == 0
    listed = mux_server.command("list-sessions", format="#{session_name}")
    assert listed["stdout"] == actor.session + "\n"
    panes = mux_server.command("list-panes", session=actor.session, format="#{pane_id}")
    assert panes["stdout"] == pane_identifier(actor.pane) + "\n"
    encoded = base64.urlsafe_b64encode(str(actor.folder).encode()).decode().rstrip("=")
    for key, value in (
        ("owner", "agentctl"),
        ("agent", "claude"),
        ("folder", encoded),
        ("pane", pane_identifier(actor.pane)),
    ):
        response = mux_server.command(
            "set-identity", session=actor.session, key=key, value=value
        )
        assert response["code"] == 0, response
    target = "=" + actor.session + ":"
    raw_options = mux_server.raw("show-options", "-t", target)
    shown = mux_server.command("show-options", session=actor.session)
    assert shown["stdout"] == raw_options.stdout
    identity = [
        shlex.split(line)
        for line in raw_options.stdout.splitlines()
        if line.startswith("@")
    ]
    assert ["@agentctl_owner", "agentctl"] in identity
    assert ["@agentctl_folder", encoded] in identity
    state = mux_server.command("pane-state", pane=actor.pane)
    assert int(str(state["stdout"]).split()[0]) == int(raw_pid.stdout.strip())
    _capture(mux_server, actor, "ready:" + actor.nonce)
    literal = "resume literal " + actor.nonce
    assert (
        mux_server.command("send-literal", pane=actor.pane, text=literal)["code"] == 0
    )
    before = mux_server.command("capture", pane=actor.pane, lines=100)
    assert "echo:" + literal not in str(before["stdout"])
    assert mux_server.command("send-enter", pane=actor.pane)["code"] == 0
    _capture(mux_server, actor, "echo:" + literal)
    assert (
        mux_server.command(
            "remain-on-exit", session=actor.session, pane=actor.pane, enabled=False
        )["code"]
        == 0
    )


@pytest.mark.evidence("real")
def test_instant_exit_status(mux_server: PrivateMux) -> None:
    """Remain-on-exit holds a genuine exit 3 beside a genuinely running actor."""
    live = mux_server.actor("live-control")
    live.record()
    assert (
        mux_server.raw(
            "display-message", "-p", "-t", live.pane, "#{pane_dead}"
        ).stdout.strip()
        == "0"
    )
    dead = mux_server.actor("instant-exit", disposition="3")
    dead.record()
    assert mux_server.exit_status(dead) == EXIT_STATUS


@pytest.mark.evidence("observer")
def test_pane_targets_distinguish_servers(mux_server: PrivateMux) -> None:
    """Two genuine native panes retain separate process, capture and input identity."""
    left = mux_server.actor("left")
    right = mux_server.actor("right")
    left_record, right_record = left.record(), right.record()
    assert left_record["pid"] != right_record["pid"]
    left_state = mux_server.command("pane-state", pane=left.pane)
    right_state = mux_server.command("pane-state", pane=right.pane)
    assert str(left_state["stdout"]).split()[0] != str(right_state["stdout"]).split()[0]
    _capture(mux_server, left, "ready:" + left.nonce)
    _capture(mux_server, right, "ready:" + right.nonce)
    literal = "left only " + left.nonce
    assert mux_server.command("send-literal", pane=left.pane, text=literal)["code"] == 0
    assert mux_server.command("send-enter", pane=left.pane)["code"] == 0
    _capture(mux_server, left, "echo:" + literal)
    captured = mux_server.command("capture", pane=right.pane, lines=100)
    assert captured["code"] == 0
    assert literal not in str(captured["stdout"])


@pytest.mark.evidence("observer")
def test_closed_terminal_does_not_publish_exit_status(mux_server: PrivateMux) -> None:
    """Closed streams precede a genuine child exit; only a later poll releases it."""
    actor = mux_server.actor("closed-streams", disposition="closed-streams")
    record = actor.record()
    pid = record["pid"]
    assert isinstance(pid, int)
    deadline = time.monotonic() + WAIT_SECONDS
    if mux_server.family == "Windows":
        state = mux_server.raw(
            "display-message", "-p", "-t", actor.pane, "#{pane_dead}"
        )
        assert state.code == 0, state.stderr
        assert state.stdout.strip() == "0"
        assert not actor.status.exists()
    else:
        state = mux_server.raw(
            "display-message",
            "-p",
            "-t",
            actor.pane,
            "#{pane_dead}|#{pane_dead_status}|#{pane_dead_signal}",
        )
        while state.stdout.strip() != "1||" and time.monotonic() < deadline:
            time.sleep(0.01)
            state = mux_server.raw(
                "display-message",
                "-p",
                "-t",
                actor.pane,
                "#{pane_dead}|#{pane_dead_status}|#{pane_dead_signal}",
            )
        assert state.code == 0, state.stderr
        assert state.stdout.strip() == "1||", state.stdout
    family = mux_server.family
    assert family in {"Linux", "Darwin", "Windows"}
    assert alive(family, pid) == Ok(value=True), (
        "controlled child exited before status observation"
    )
    active = True
    polls = 0
    wanted = (
        "#{pane_dead}"
        if mux_server.family == "Windows"
        else "#{pane_dead}|#{pane_dead_status}|#{pane_dead_signal}"
    )
    stop = actor.record_directory / "stop"

    def release_on_second_poll(event: str, arguments: tuple[object, ...]) -> None:
        """Observe actual query spawns before letting the owned child exit."""
        nonlocal polls
        if active and event == "subprocess.Popen":
            argv = arguments[1]
            if isinstance(argv, str):
                argv = [word.strip('"') for word in shlex.split(argv, posix=False)]
            if (
                isinstance(argv, list)
                and argv
                and argv[0] == mux_server.executable
                and actor.pane in argv
                and argv[-1] == wanted
            ):
                polls += 1
                if polls == RELEASE_POLL:
                    stop.write_text("release", encoding="utf-8")

    sys.addaudithook(release_on_second_poll)
    try:
        observed = mux_server.exit_status(actor)
    finally:
        active = False
        stop.write_text("release", encoding="utf-8")
    assert polls >= RELEASE_POLL, "exit status was accepted before a later observation"
    assert observed == EXIT_STATUS
    assert alive(family, pid) == Ok(value=False), "exited observer was not reaped"


@pytest.mark.evidence("observer")
def test_exact_target_spares_prefix_sibling(mux_server: PrivateMux) -> None:
    """Ending ab leaves ab-c running on the same private native server."""
    target = mux_server.actor("ab")
    sibling = mux_server.actor("ab-c")
    target.record()
    sibling.record()
    observer = observe_mux(prepare(mux_server, "claude"))
    observed = replace(mux_server, environment=observer.case.environment)
    assert mux_server.raw("has-session", "-t", "=ab").code == 0
    assert observed.command("kill", session="ab")["code"] == 0
    assert mux_server.raw("has-session", "-t", "=ab").code != 0
    assert observed.command("has-session", session="ab")["code"] != 0, (
        "prefix sibling was targeted as absent session"
    )
    assert observed.command("kill", session="ab")["code"] != 0
    calls = [
        argv
        for argv in observer.arguments()
        if argv[:1] in (["has-session"], ["kill-session"])
    ]
    assert len(calls) == EXACT_TARGET_CALLS
    assert all(argv[-2:] == ["-t", "=ab"] for argv in calls), (
        "prefix sibling was targeted as absent session"
    )
    assert mux_server.raw("has-session", "-t", "=ab-c").code == 0
    assert (
        mux_server.raw(
            "display-message", "-p", "-t", sibling.pane, "#{pane_dead}"
        ).stdout.strip()
        == "0"
    )


@pytest.mark.evidence("real")
def test_containment_sees_leftover_server(mux_server: PrivateMux) -> None:
    """The gate sees a live private server and accepts its reaped control."""
    if mux_server.family == "Windows":
        mux_server.actor("containment").record()
    family = mux_server.family
    assert family in {"Linux", "Darwin", "Windows"}
    assert isinstance(
        containment(mux_server.run_directory, mux_server.nonce.split(".")[0], family),
        Err,
    )
    mux_server.close()
    assert containment(
        mux_server.run_directory, mux_server.nonce.split(".")[0], family
    ) == Ok(None)
