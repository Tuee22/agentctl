# Copyright (c) 2026 agentctl contributors.
"""Watch intent changes owned state while native sessions retain their identity."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from tests.harness.launch import LaunchCase, prepare
from tests.harness.sessions import rows
from tests.harness.tmux import PrivateMux, object_value, pane_identifier

pytestmark = pytest.mark.evidence("real")
PANE_FACTS = 3


def watch_path(case: LaunchCase) -> Path:
    """Inspect the actual state path handed to this caller."""
    return Path(case.environment["AGENTCTL_STATE_DIR"]) / "watch.json"


def registry(case: LaunchCase) -> tuple[int, dict[str, dict[str, object]]]:
    """Parse revisions and entries independently of the native store."""
    document = object_value(watch_path(case).read_text(encoding="utf-8"))
    assert set(document) == {"revision", "watched"}
    revision = document["revision"]
    assert isinstance(revision, int)
    assert not isinstance(revision, bool)
    assert revision >= 0
    watched = document["watched"]
    assert isinstance(watched, dict)
    entries: dict[str, dict[str, object]] = {}
    for key, value in watched.items():
        assert isinstance(key, str)
        assert isinstance(value, dict)
        entry: dict[str, object] = {str(name): field for name, field in value.items()}
        assert set(entry) == {"paused", "revision"}
        assert isinstance(entry["paused"], bool)
        entry_revision = entry["revision"]
        assert isinstance(entry_revision, int)
        assert not isinstance(entry_revision, bool)
        assert 0 < entry_revision <= revision
        entries[key] = entry
    return revision, entries


def pane_pid(mux: PrivateMux, pane: str) -> int:
    """Use the genuine backend to require the same live pane process."""
    output = mux.raw(
        "display-message", "-p", "-t", pane, "#{pane_id}|#{pane_pid}|#{pane_dead}"
    )
    assert output.code == 0, output
    fields = output.stdout.strip().split("|")
    assert len(fields) == PANE_FACTS
    assert fields[0] == pane_identifier(pane)
    assert fields[2] == "0"
    return int(fields[1])


def test_concurrent_watch_updates_preserve_entries(mux_server: PrivateMux) -> None:
    """Independent commands serialize their complete registry read and write."""
    case = prepare(mux_server, "claude")
    other = prepare(mux_server, "codex")
    assert case.invoke().code == 0
    assert other.invoke().code == 0
    adopted = tuple(mux_server.actor(f"concurrent-{index}") for index in range(2))
    for actor in adopted:
        assert actor.record()["nonce"] == actor.nonce
        assert case.command("adopt", (actor.pane, "--agent", "claude")).code == 0
    targets = ("api-claude", "api-codex", *(actor.pane for actor in adopted))
    for operation in ("watch", "pause", "resume-watch"):
        with ThreadPoolExecutor(max_workers=len(targets)) as executor:
            futures = tuple(
                executor.submit(case.command, operation, (target,))
                for target in targets
            )
            outputs = tuple(future.result() for future in futures)
        for output in outputs:
            assert output.code == 0, output
        revision, entries = registry(case)
        assert set(entries) == set(targets), "concurrent update lost watch intent"
        expected_revision = (
            len(targets) * {"watch": 1, "pause": 2, "resume-watch": 3}[operation]
        )
        assert revision == expected_revision
        assert {entry["revision"] for entry in entries.values()} == set(
            range(revision - len(targets) + 1, revision + 1)
        )
        assert all(
            entry["paused"] == (operation == "pause") for entry in entries.values()
        )


def test_list_and_status_show_watch_state(mux_server: PrivateMux) -> None:
    """A watched managed pane, paused adopted pane and unwatched pane differ."""
    case = prepare(mux_server, "claude")
    other = prepare(mux_server, "codex")
    assert case.invoke().code == 0
    assert other.invoke().code == 0
    adopted = mux_server.actor("watch-adopted")
    assert adopted.record()["nonce"] == adopted.nonce
    assert case.command("adopt", (adopted.pane, "--agent", "claude")).code == 0
    assert case.command("watch", ("api-claude",)).code == 0
    assert case.command("watch", (adopted.pane,)).code == 0
    assert case.command("pause", (adopted.pane,)).code == 0
    listed = rows(case.command("list"))
    assert set(listed) == {"api-claude", "api-codex", adopted.pane}
    expected = {
        "api-claude": ("yes", "no"),
        "api-codex": ("no", "no"),
        adopted.pane: ("yes", "yes"),
    }
    for target, flags in expected.items():
        assert (listed[target]["WATCHED"], listed[target]["PAUSED"]) == flags
        current = rows(case.command("status", (target,)))[target]
        assert (current["WATCHED"], current["PAUSED"]) == flags
    before, entries = registry(case)
    original = entries["api-claude"]["revision"]
    assert case.command("pause", ("api-claude",)).code == 0
    assert case.command("resume-watch", ("api-claude",)).code == 0
    after, entries = registry(case)
    assert after == before + 2
    assert entries["api-claude"] == {"paused": False, "revision": after}
    assert entries["api-claude"]["revision"] != original
    unchanged = watch_path(case).read_bytes()
    assert case.command("watch", (adopted.pane,)).code == 0
    assert watch_path(case).read_bytes() == unchanged
    assert (
        rows(case.command("status", (adopted.pane,)))[adopted.pane]["PAUSED"] == "yes"
    )


def test_unwatch_never_touches_session(mux_server: PrivateMux) -> None:
    """Native pids survive pause and unwatch beside nonce-bound watch controls."""
    case = prepare(mux_server, "claude")
    assert case.invoke().code == 0
    managed = rows(case.command("list"))["api-claude"]
    launched = [
        record for record in case.records() if record["session"] == "api-claude"
    ]
    assert len(launched) == 1
    assert launched[0]["nonce"] == case.nonce
    assert launched[0]["pane"] == managed["PANE"]
    adopted = mux_server.actor("watch-kept")
    assert adopted.record()["nonce"] == adopted.nonce
    assert case.command("adopt", (adopted.pane, "--agent", "claude")).code == 0
    targets = {"api-claude": managed["PANE"], adopted.pane: adopted.pane}
    original = {target: pane_pid(mux_server, pane) for target, pane in targets.items()}
    for target in targets:
        assert case.command("watch", (target,)).code == 0
        assert rows(case.command("status", (target,)))[target]["WATCHED"] == "yes"
        assert case.command("pause", (target,)).code == 0
        assert case.command("unwatch", (target,)).code == 0
    for target, pane in targets.items():
        assert pane_pid(mux_server, pane) == original[target]
        assert rows(case.command("status", (target,)))[target]["WATCHED"] == "no"
    for session in ("api-claude", "watch-kept"):
        assert mux_server.raw("has-session", "-t", "=" + session).code == 0


def test_watch_refuses_foreign_target(mux_server: PrivateMux) -> None:
    """Refusals preserve exact state bytes, while a stale opt-out still works."""
    case = prepare(mux_server, "claude")
    assert case.invoke().code == 0
    assert case.command("watch", ("api-claude",)).code == 0
    before = watch_path(case).read_bytes()
    foreign = mux_server.actor("watch-foreign")
    assert foreign.record()["nonce"] == foreign.nonce
    for target in ("watch-foreign", "missing"):
        assert case.command("watch", (target,)).code == 1
        assert watch_path(case).read_bytes() == before
        assert case.command("resume-watch", (target,)).code == 1
        assert watch_path(case).read_bytes() == before
    assert mux_server.raw("has-session", "-t", "=watch-foreign").code == 0
    assert mux_server.raw("kill-session", "-t", "=api-claude").code == 0
    assert case.command("pause", ("api-claude",)).code == 0
    assert case.command("unwatch", ("api-claude",)).code == 0
    assert registry(case)[1] == {}
