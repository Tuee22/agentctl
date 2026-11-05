# Copyright (c) 2026 agentctl contributors.
"""Scripted native panes provide byte-complete receiving controls for supervision."""

import json
import time
from pathlib import Path

import pytest

from tests.harness.launch import prepare
from tests.harness.sessions import rows
from tests.harness.supervisor import (
    events,
    received_bytes,
    timestamp,
    wait_frames,
    wait_received,
)
from tests.harness.tmux import PrivateMux

pytestmark = pytest.mark.evidence("observer")
INPUT_FRAME_COUNT = 2
FRAME_DELAY_NANOSECONDS = 50000000


@pytest.mark.parametrize("agent", ["claude", "codex"])
def test_scripted_agent_records_every_byte(
    root: Path, mux_server: PrivateMux, agent: str
) -> None:
    """File, input and timed advances retain exact bytes, target and fresh nonce."""
    case = prepare(mux_server, agent, disposition="scripted")
    trigger = case.records_directory / "advance"
    script = case.folder.parent / "script.json"
    screens = root / "tests/fixtures/screens" / agent
    first = "partial"
    second = " literal"
    literal = first + second
    script.write_text(
        json.dumps(
            {
                "frames": [
                    {
                        "screen": str(screens / "IdlePrompt/documented.txt"),
                        "after": {"kind": "file", "path": str(trigger)},
                    },
                    {
                        "screen": str(screens / "Overloaded/documented.txt"),
                        "after": {"kind": "input", "bytes": len(literal) + 1},
                    },
                    {
                        "screen": str(screens / "Working/documented.txt"),
                        "after": {"kind": "delay", "seconds": 0.05},
                    },
                    {
                        "screen": str(screens / "IdlePrompt/documented.txt"),
                        "after": {"kind": "stay"},
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    assert case.invoke(("--agentctl-script", str(script))).code == 0
    initial = wait_frames(case.records_directory, case.nonce, 1)
    target = rows(case.command("list"))[f"api-{agent}"]
    pane = target["PANE"]
    launch = [record for record in case.records() if record["pane"] == pane]
    assert len(launch) == 1
    assert received_bytes(case.records_directory, case.nonce) == b""
    assert len(initial) == 1
    trigger.touch()
    wait_frames(case.records_directory, case.nonce, 2)
    output = mux_server.raw("send-keys", "-l", "-t", pane, "--", first)
    assert output.code == 0, output
    wait_received(case.records_directory, case.nonce, first.encode())
    assert (
        len(events(case.records_directory / "frames.jsonl", case.nonce))
        == INPUT_FRAME_COUNT
    )
    output = mux_server.raw("send-keys", "-l", "-t", pane, "--", second)
    assert output.code == 0, output
    wait_received(case.records_directory, case.nonce, literal.encode())
    output = mux_server.raw("send-keys", "-t", pane, "Enter")
    assert output.code == 0, output
    wait_received(case.records_directory, case.nonce, literal.encode() + b"\r")
    frames = wait_frames(case.records_directory, case.nonce, 4)
    for record in (
        *frames,
        *events(case.records_directory / "received.jsonl", case.nonce),
    ):
        assert record["pid"] == launch[0]["pid"]
        assert record["pane"] == pane
        assert record["session"] == f"api-{agent}"
    receipts = events(case.records_directory / "received.jsonl", case.nonce)
    assert timestamp(receipts[0]) >= timestamp(frames[1])
    assert timestamp(frames[3]) - timestamp(frames[2]) >= FRAME_DELAY_NANOSECONDS
    retained = mux_server.raw("set-option", "-p", "-t", pane, "remain-on-exit", "on")
    assert retained.code == 0, retained
    (case.records_directory / "stop").touch()
    deadline = time.monotonic() + 10
    current = rows(case.command("list"))[f"api-{agent}"]
    while current["STATE"] != "dead" and time.monotonic() < deadline:
        time.sleep(0.01)
        current = rows(case.command("list"))[f"api-{agent}"]
    assert current["STATE"] == "dead"
    assert current["EXIT"] == "0"
