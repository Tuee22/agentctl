# Copyright (c) 2026 agentctl contributors.
"""Native log selection consumes current private history independently of sessions."""

import json
import os
import tomllib
from pathlib import Path

import pytest

from tests.harness.launch import observe_mux, prepare
from tests.harness.oracle import Store, load, read_homes
from tests.harness.supervisor import (
    log_records,
    observe_polls,
    received_bytes,
    recovery_bytes,
    scripted_target,
    supervisor,
    utc_time,
    wait_backoff,
    wait_observation,
    wait_records,
    wait_transition,
)
from tests.harness.supervisor_barrier import (
    drive_guard,
    guarded_target,
    supervisor_barrier,
)
from tests.harness.supervisor_cases import (
    assert_all_decisions,
    oracle_rows,
    receiving_controls,
    require_receivers,
)
from tests.harness.tmux import PrivateMux, object_value


@pytest.mark.evidence("real")
def test_logs_selects_exact_target(root: Path, mux_server: PrivateMux) -> None:
    """Historical managed and adopted names match exactly and missing names refuse."""
    path = root / "tests/oracles/log_records.toml"
    store = load(path, read_homes(root))
    assert isinstance(store, Store), store
    effective = {row.identifier for row in store.effective}
    row = next(
        row
        for row in tomllib.loads(path.read_text(encoding="utf-8"))["case"]
        if row["id"] == "log.selection.exact-managed" and row["id"] in effective
    )
    case = prepare(mux_server, "claude")
    state = Path(case.environment["AGENTCTL_STATE_DIR"])
    state.mkdir(mode=0o700, exist_ok=True)
    records = [{**record, "run": case.nonce} for record in row["input"]["records"]]
    descriptor = os.open(
        state / "supervisor.jsonl", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
    )
    with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
        stream.write("".join(json.dumps(record) + "\n" for record in records))
    for target in ("api-claude", "api-claude-extra", "%3", "old-session"):
        selected = case.command("logs", (target,))
        assert selected.code == 0, selected
        assert selected.stderr == ""
        actual = [object_value(line) for line in selected.stdout.splitlines()]
        expected = [record for record in records if record["target"] == target]
        assert actual == expected
        assert all(record["run"] == case.nonce for record in actual)
    for target in ("api", "absent", "%30"):
        absent = case.command("logs", (target,))
        assert absent.code == 1, absent
        assert absent.stdout == ""
        assert absent.stderr == f"agentctl: no supervisor records for {target}.\n"


@pytest.mark.evidence("observer")
def test_every_poll_logged(root: Path, mux_server: PrivateMux) -> None:
    """Bind each composite capture's plain and styled views to its log record."""
    targets = [
        scripted_target(mux_server, root, agent, (("IdlePrompt", {"kind": "stay"}),))
        for agent in ("claude", "codex")
    ]
    observer = observe_mux(targets[0].case)
    case = observer.case
    for target in targets:
        assert case.command("watch", (target.target,)).code == 0
    with supervisor(case) as running:
        for target in targets:
            wait_observation(running, target.target, "IdlePrompt")
            observe_polls(running, target.target, 5)
        running.finish()
    arguments = observer.arguments()
    records = log_records(case)
    for target in targets:
        captures = [
            argv
            for argv in arguments
            if argv[:1] == ["capture-pane"] and target.pane in argv
        ]
        observations = [
            row
            for row in records
            if row["target"] == target.target and row["kind"] == "observation"
        ]
        plain = [argv for argv in captures if "-J" in argv]
        styled = [argv for argv in captures if "-e" in argv]
        assert len(plain) == len(styled) == len(observations)
        assert len(captures) == len(plain) + len(styled)
        assert observations
        assert {row["class"] for row in observations} == {"IdlePrompt"}
        assert {row["agent"] for row in observations} == {target.case.agent}
        assert {row["fingerprint"] for row in observations} == {""}
        launch = [row for row in target.case.records() if row["pane"] == target.pane]
        assert len(launch) == 1
        assert launch[0]["nonce"] == target.case.nonce
        frames = target.case.records_directory / "frames.jsonl"
        first = object_value(frames.read_text(encoding="utf-8").splitlines()[0])
        assert first["pid"] == launch[0]["pid"]
        assert first["session"] == target.target
        assert first["pane"] == target.pane


@pytest.mark.evidence("observer")
def test_records_match_schema(root: Path, mux_server: PrivateMux) -> None:
    """One native run emits every kind with sent, aborted and failed attempts."""
    trigger = mux_server.scope / "schema-overload"
    control_trigger = mux_server.scope / "schema-receivers"
    fail_trigger = mux_server.scope / "schema-failure"
    guarded = guarded_target(root, mux_server, "claude", trigger)
    failed = scripted_target(
        mux_server,
        root,
        "codex",
        (
            ("IdlePrompt", {"kind": "file", "path": str(fail_trigger)}),
            ("Overloaded", {"kind": "stay"}),
        ),
    )
    controls = receiving_controls(root, mux_server, control_trigger)
    barrier = supervisor_barrier(guarded.target.case)
    case = barrier.case
    targets = (guarded.target, failed, *controls)
    for target in targets:
        assert case.command("watch", (target.target,)).code == 0
    with supervisor(case) as running:
        for target in targets:
            wait_observation(running, target.target, "IdlePrompt")
        control_trigger.touch()
        for control in controls:
            wait_backoff(running, control.target)
            wait_transition(running, control.target, "RECOVERY_SENT")
            wait_records(running, control.target, "attempt")
        require_receivers(root, controls)
        for control in controls:
            wait_transition(running, control.target, "VERIFY")
            wait_records(running, control.target, "result")
        barrier.arm("guard", guarded.target)
        trigger.touch()
        drive_guard(running, barrier, guarded)
        require_receivers(root, controls)
        for control in controls:
            wait_records(running, control.target, "result")
        barrier.arm("fail", failed, 3)
        fail_trigger.touch()
        wait_backoff(running, failed.target)
        wait_transition(running, failed.target, "RECOVERY_SENT")
        barrier.wait("fail", failed, 3)
        wait_records(running, failed.target, "result")
        running.finish()
    records = log_records(case)
    identities = {target.target: target.case.agent for target in targets}
    _assert_records(root, records, mux_server.family, identities)
    for target in (guarded.target, failed):
        assert received_bytes(target.case.records_directory, target.case.nonce) == b""
    barrier.observer.arguments()
    assert_all_decisions(root, case)


def _assert_records(
    root: Path,
    records: tuple[dict[str, object], ...],
    family: str,
    identities: dict[str, str],
) -> None:
    """Validate every emitted field against the independent closed schema."""
    schemas = [
        row["expected"]
        for row in oracle_rows(root, "log_records.toml")
        if row["id"] == "log.schema"
    ]
    assert len(schemas) == 1
    schema = schemas[0]
    assert isinstance(schema, dict)
    base = schema["base"]
    assert isinstance(base, list)
    assert {row["kind"] for row in records} == set(schema) - {"base"}
    assert len({row["run"] for row in records}) == 1
    for record in records:
        kind = record["kind"]
        assert isinstance(kind, str)
        extra = schema[kind]
        assert isinstance(extra, list)
        assert set(record) == set(base + extra)
        target_name = record["target"]
        assert isinstance(target_name, str)
        assert record["agent"] == identities[target_name]
        utc_time(record["time"])
        if kind == "attempt":
            agent = record["agent"]
            assert isinstance(agent, str)
            text = recovery_bytes(root, family, agent)[:-1].decode()
            assert record["recovery_text"] == text
    attempts = [record for record in records if record["kind"] == "attempt"]
    assert {record["outcome"] for record in attempts} == {"sent", "aborted", "failed"}
