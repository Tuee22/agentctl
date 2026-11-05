# Copyright (c) 2026 agentctl contributors.
"""All frozen control cells and real scheduler deadlines use the same kernel."""

import json
import tomllib
from pathlib import Path

import pytest

from agentctl.bootstrap import build
from agentctl.result import Ok
from tests.harness.evaluate import compare_subject
from tests.harness.oracle import Store, load, read_homes

pytestmark = pytest.mark.evidence("value")
MATRIX_REASON = "recovery transition differs from oracle"
DEADLINE_REASON = "backoff deadline differs from oracle attempt"


def test_every_cell_matches_oracle(
    root: Path, haskell_build: build.BuildContext
) -> None:
    """Require every complete result, including actions and handled identities."""
    compare_subject(
        root,
        haskell_build,
        "recovery_transitions.toml",
        "recovery-transition",
        MATRIX_REASON,
    )


def test_backoff_deadlines_match_oracle(
    root: Path, haskell_build: build.BuildContext
) -> None:
    """Bind scheduled deadlines and subsequent sends to independent delay rows."""
    path = root / "tests/oracles/recovery_transitions.toml"
    store = load(path, read_homes(root))
    assert isinstance(store, Store), store
    effective = {row.identifier for row in store.effective}
    rows = [
        row
        for row in tomllib.loads(path.read_text(encoding="utf-8"))["case"]
        if row["id"] in effective
        and row["input"]["state"] in {"CONFIRM_IDLE", "VERIFY"}
        and row["expected"]["state"] == "BACKOFF"
    ]
    backoff_path = root / "tests/oracles/backoff.toml"
    backoff_store = load(backoff_path, read_homes(root))
    assert isinstance(backoff_store, Store)
    backoff_ids = {row.identifier for row in backoff_store.effective}
    delays = {
        row["input"]["attempt"]: row["expected"]["minimum"]
        for row in tomllib.loads(backoff_path.read_text(encoding="utf-8"))["case"]
        if row["id"] in backoff_ids
        and row["input"]["jitter"] == 0
        and row["expected"]["minimum"] == row["expected"]["maximum"]
    }
    assert rows
    assert delays
    requests = [
        {**row["input"], "subject": "recovery-deadline", "now": 100, "jitter": 0}
        for row in rows
    ]
    requests.extend(
        {
            "subject": "recovery-deadline",
            "state": "BACKOFF",
            "screen": "Overloaded",
            "fingerprint": "f",
            "incident_fingerprint": "f",
            "handled": [],
            "attempt": 1,
            "deadline_reached": due,
            "now": 100 + delays[1] - (0 if due else 0.01),
            "deadline": 100 + delays[1],
            "jitter": 0,
        }
        for due in (False, True)
    )
    output = build.execute_binary(
        haskell_build,
        build.BinaryCall(
            "exe:agentctl-core-eval",
            input_text="\n".join(map(json.dumps, requests)) + "\n",
        ),
    )
    assert isinstance(output, Ok), output
    assert output.value.code == 0, output.value
    actual = [json.loads(line) for line in output.value.stdout.splitlines()]
    assert len(actual) == len(requests)
    for row, result in zip(rows, actual[:-2], strict=True):
        attempt = row["expected"]["attempt"]
        assert result["attempt"] == attempt, DEADLINE_REASON
        assert result["deadline"] == 100 + delays[attempt], DEADLINE_REASON
        assert {key: result[key] for key in row["expected"]} == row["expected"], (
            MATRIX_REASON
        )
        assert result["notices"] == [
            {"level": "info", "attempt": attempt, "delay": delays[attempt]}
        ], "scheduled retry notice was missing or duplicated"
    assert actual[-2]["state"] == "BACKOFF", DEADLINE_REASON
    assert actual[-2]["actions"] == [], DEADLINE_REASON
    assert actual[-1]["state"] == "RECOVERY_SENT", DEADLINE_REASON
    assert actual[-1]["actions"] == ["send"], DEADLINE_REASON
