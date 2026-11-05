# Copyright (c) 2026 agentctl contributors.
"""The complete gate table, including the executable binary-identity step."""

import tomllib
from pathlib import Path

import pytest

from agentctl.check.steps import pipeline, step_table
from tests.harness.oracle import assert_oracle

pytestmark = pytest.mark.evidence("value")


def test_step_table_equals_oracle(root: Path, tmp_path: Path) -> None:
    """Every step, including identity between build and test, equals the frozen row."""
    rows = tomllib.loads(
        (root / "tests/oracles/check_steps.toml").read_text(encoding="utf-8")
    )["case"]
    expected = next(
        row["expected"] for row in rows if row["id"] == "steps.complete-order"
    )
    steps = pipeline(root, tmp_path, ("source.py",), "Linux", assume_yes=False)
    assert_oracle(
        lambda _: list(step_table(steps)),
        None,
        expected,
        row_id="gate step table differs from oracle",
    )
