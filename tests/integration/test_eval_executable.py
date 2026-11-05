# Copyright (c) 2026 agentctl contributors.
"""Independent JSONL expectations applied to the native pure-kernel evaluator."""

import json
import tomllib
from pathlib import Path

import pytest

from agentctl.bootstrap import build
from agentctl.result import Ok
from tests.harness.oracle import assert_oracle

pytestmark = pytest.mark.evidence("value")


def test_every_case_answered(haskell_build: build.BuildContext, root: Path) -> None:
    """Each input line, including malformed input, has one corresponding result."""
    rows = tomllib.loads(
        (root / "tests/oracles/protocol.toml").read_text(encoding="utf-8")
    )["case"]
    inputs = [row["input"]["line"] for row in rows]
    expected = [row["expected"] for row in rows]
    result = build.execute_binary(
        haskell_build,
        build.BinaryCall("exe:agentctl-core-eval", input_text="\n".join(inputs) + "\n"),
    )
    assert isinstance(result, Ok), result
    assert result.value.code == 0
    actual: list[object] = [
        json.loads(line) for line in result.value.stdout.splitlines()
    ]
    assert_oracle(
        lambda _: actual, None, expected, row_id="eval skipped or reordered a case"
    )
