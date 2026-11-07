# Copyright (c) 2026 agentctl contributors.
"""Adoption observes real pane identities and never takes multiplexer ownership."""

import json
import stat
from pathlib import Path

import pytest

from tests.harness.launch import LaunchCase, prepare
from tests.harness.sessions import rows
from tests.harness.tmux import PrivateMux, object_value, pane_identifier

REASON = "adopted pane policy differs from ownership oracle"
PANE_FIELDS = 5
PRIVATE_FILE = 0o600
PRIVATE_DIRECTORY = 0o700


def registry(case: LaunchCase) -> Path:
    """Use the caller's actual handed state directory."""
    return Path(case.environment["AGENTCTL_STATE_DIR"]) / "adopted.json"


def entries(path: Path) -> list[dict[str, object]]:
    """Read the public registry with a separate standard-library parser."""
    document = object_value(path.read_text(encoding="utf-8"))
    assert set(document) == {"panes"}
    panes = document["panes"]
    assert isinstance(panes, list)
    result: list[dict[str, object]] = []
    for item in panes:
        assert isinstance(item, dict)
        value: dict[str, object] = {str(key): field for key, field in item.items()}
        assert set(value) == {"socket", "pane", "pid", "agent"}
        result.append(value)
    return result


def pane_facts(mux: PrivateMux, pane: str) -> tuple[int, str, str]:
    """Read identity directly from the native backend, independently of agentctl."""
    output = mux.raw(
        "display-message",
        "-p",
        "-t",
        pane,
        "#{pane_id}|#{pane_pid}|#{pane_dead}|#{socket_path}|#{session_id}",
    )
    assert output.code == 0, output
    fields = output.stdout.rstrip("\r\n").split("|")
    assert len(fields) == PANE_FIELDS
    assert fields[0] == pane_identifier(pane)
    assert fields[2] == "0", REASON
    return int(fields[1]), fields[3], fields[4]


def no_options(mux: PrivateMux, session: str) -> None:
    """Require no agentctl option on a foreign session before or after adoption."""
    target = "=" + session + ":"
    output = mux.raw("show-options", "-t", target)
    assert output.code == 0
    assert "@agentctl_" not in output.stdout, REASON


@pytest.mark.evidence("observer")
def test_adopt_does_not_take_ownership(mux_server: PrivateMux) -> None:
    """Preserve a nonce-bound foreign process and options through adoption and stop."""
    case = prepare(mux_server, "claude")
    assert case.invoke().code == 0
    managed = rows(case.command("list"))["api-claude"]
    foreign = mux_server.actor("foreign")
    record = foreign.record()
    assert record["nonce"] == foreign.nonce
    pid, namespace, session = pane_facts(mux_server, foreign.pane)
    no_options(mux_server, "foreign")
    registered = case.command("adopt", (foreign.pane, "--agent", "claude"))
    assert registered.code == 0, registered
    path = registry(case)
    expected_endpoint = (
        namespace
        if mux_server.family != "Windows"
        else json.dumps(
            ["psmux", namespace, session], ensure_ascii=False, separators=(",", ":")
        )
    )
    expected = {
        "socket": expected_endpoint,
        "pane": foreign.pane,
        "pid": pid,
        "agent": "claude",
    }
    assert entries(path) == [expected], REASON
    if mux_server.family != "Windows":
        assert stat.S_IMODE(path.stat().st_mode) == PRIVATE_FILE
        assert stat.S_IMODE(path.parent.stat().st_mode) == PRIVATE_DIRECTORY
    observed = rows(case.command("list"))[foreign.pane]
    assert observed["KIND"] == "adopted", REASON
    assert observed["STATE"] == "alive", REASON
    assert int(observed["PID"]) == pid
    assert observed["SESSION"] == "foreign"
    hint = mux_server.raw(
        "display-message", "-p", "-t", foreign.pane, "#{pane_current_command}"
    )
    assert hint.code == 0
    assert observed["COMMAND"] == hint.stdout.rstrip("\r\n")
    no_options(mux_server, "foreign")
    original = path.read_bytes()
    for pane in (foreign.pane, managed["PANE"], "%999999"):
        assert case.command("adopt", (pane, "--agent", "codex")).code != 0
        assert path.read_bytes() == original
    assert case.command("attach", (foreign.pane,)).code != 0
    path.write_text(
        json.dumps(
            {"panes": [{**expected, "socket": expected_endpoint + "-different"}]}
        ),
        encoding="utf-8",
    )
    assert (
        rows(case.command("status", (foreign.pane,)))[foreign.pane]["STATE"] == "stale"
    ), REASON
    path.write_bytes(original)
    assert (
        rows(case.command("status", (foreign.pane,)))[foreign.pane]["STATE"] == "alive"
    ), REASON
    stopped = case.command("stop", (foreign.pane,))
    assert stopped.code == 0, REASON
    assert "is adopted, not owned" in stopped.stdout, REASON
    assert entries(path) == [], REASON
    assert pane_facts(mux_server, foreign.pane)[0] == pid, REASON
    no_options(mux_server, "foreign")


@pytest.mark.evidence("real")
def test_stale_entry_after_server_restart(mux_server: PrivateMux) -> None:
    """Reject changed pids, including a real restart at the same endpoint."""
    case = prepare(mux_server, "claude")
    foreign = mux_server.actor("foreign")
    other = mux_server.actor("other")
    pid, _, _ = pane_facts(mux_server, foreign.pane)
    other_pid, _, _ = pane_facts(mux_server, other.pane)
    assert pid != other_pid
    if mux_server.family == "Windows":
        assert pane_identifier(foreign.pane) == pane_identifier(other.pane)
        refused = case.command(
            "adopt", (pane_identifier(foreign.pane), "--agent", "claude")
        )
        assert refused.code != 0
        assert "ambiguous pane id" in refused.stderr
        assert not registry(case).exists()
    assert case.command("adopt", (foreign.pane, "--agent", "claude")).code == 0
    path = registry(case)
    original = path.read_bytes()
    recorded = entries(path)[0]
    path.write_text(
        json.dumps({"panes": [{**recorded, "pid": other_pid}]}), encoding="utf-8"
    )
    assert rows(case.command("list"))[foreign.pane]["STATE"] == "stale", REASON
    path.write_bytes(original)
    assert (
        rows(case.command("status", (foreign.pane,)))[foreign.pane]["STATE"] == "alive"
    )
    mux_server.restart()
    replacement = mux_server.actor("replacement")
    replacement_pid, _, _ = pane_facts(mux_server, replacement.pane)
    assert replacement_pid != pid
    if mux_server.family != "Windows":
        assert replacement.pane == foreign.pane
    assert rows(case.command("list"))[foreign.pane]["STATE"] == "stale", REASON
    assert case.command("stop", (foreign.pane,)).code == 0
    assert entries(path) == []
    assert pane_facts(mux_server, replacement.pane)[0] == replacement_pid, REASON


@pytest.mark.evidence("real")
def test_registry_rejects_invalid_state(mux_server: PrivateMux) -> None:
    """Malformed or unsafe files refuse without rewriting data or touching the pane."""
    case = prepare(mux_server, "claude")
    foreign = mux_server.actor("foreign")
    pid, _, _ = pane_facts(mux_server, foreign.pane)
    assert case.command("adopt", (foreign.pane, "--agent", "claude")).code == 0
    path = registry(case)
    original = path.read_bytes()
    entry = entries(path)[0]
    malformed = [
        "not-json",
        "{}",
        json.dumps({"panes": [entry], "unexpected": True}),
        json.dumps({"panes": [{**entry, "owner": "agentctl"}]}),
        json.dumps({"panes": [entry, entry]}),
        *[
            json.dumps({"panes": [{**entry, key: value}]})
            for key, value in (
                ("pid", 0),
                ("pid", True),
                ("pane", "invalid"),
                ("socket", ""),
                ("agent", "unknown"),
            )
        ],
    ]
    for text in malformed:
        path.write_text(text, encoding="utf-8")
        refused = case.command("list")
        assert refused.code != 0
        assert "registry" in refused.stderr.casefold()
        assert path.read_text(encoding="utf-8") == text
    path.write_bytes(original)
    backup = path.with_suffix(".saved")
    path.rename(backup)
    path.mkdir()
    assert case.command("list").code != 0
    path.rmdir()
    backup.rename(path)
    assert rows(case.command("list"))[foreign.pane]["STATE"] == "alive"
    assert pane_facts(mux_server, foreign.pane)[0] == pid
