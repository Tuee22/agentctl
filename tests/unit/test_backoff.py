# Copyright (c) 2026 agentctl contributors.
"""Backoff ranges and notification thresholds come only from frozen data."""

import json
import tomllib
from pathlib import Path

import pytest

from agentctl.bootstrap import build
from agentctl.result import Ok
from tests.harness.oracle import Store, load, read_homes

pytestmark = pytest.mark.evidence("value")
REASON = "backoff delay or escalation differs from oracle"


def test_delays_and_escalations_match_oracle(
    root: Path, haskell_build: build.BuildContext
) -> None:
    """Check every range, explicit level and power-of-two notification decision."""
    path = root / "tests/oracles/backoff.toml"
    store = load(path, read_homes(root))
    assert isinstance(store, Store), store
    effective = {row.identifier for row in store.effective}
    rows = [
        row
        for row in tomllib.loads(path.read_text(encoding="utf-8"))["case"]
        if row["id"] in effective
    ]
    assert rows
    output = build.execute_binary(
        haskell_build,
        build.BinaryCall(
            "exe:agentctl-core-eval",
            input_text="\n".join(json.dumps(row["input"]) for row in rows) + "\n",
        ),
    )
    assert isinstance(output, Ok), output
    assert output.value.code == 0, output.value
    actual = [json.loads(line) for line in output.value.stdout.splitlines()]
    assert len(actual) == len(rows)
    for row, result in zip(rows, actual, strict=True):
        assert isinstance(result, dict), REASON
        assert set(result) == {"delay", "base", "level", "notify", "next_seed"}, REASON
        delay = result["delay"]
        assert isinstance(delay, (int, float)), REASON
        assert not isinstance(delay, bool), REASON
        expected = row["expected"]
        assert expected["minimum"] <= delay <= expected["maximum"], REASON
        for key in ("level", "notify"):
            if key in expected:
                assert result[key] == expected[key], REASON
