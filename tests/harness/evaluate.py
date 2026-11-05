# Copyright (c) 2026 agentctl contributors.
"""Independent effective oracle cases through the application-owned evaluator."""

import json
import tomllib
from pathlib import Path

from agentctl.bootstrap import build
from agentctl.result import Ok
from tests.harness.oracle import Store, assert_oracle, read_homes
from tests.harness.oracle import load as load_oracle


def compare_subject(
    root: Path,
    context: build.BuildContext,
    filename: str,
    subject: str,
    reason: str,
) -> None:
    """Send only case inputs and compare every result to its declared expectation."""
    path = root / "tests/oracles" / filename
    store = load_oracle(path, read_homes(root))
    assert isinstance(store, Store), store
    effective = {row.identifier for row in store.effective}
    rows = [
        row
        for row in tomllib.loads(path.read_text(encoding="utf-8"))["case"]
        if row["id"] in effective and row["input"]["subject"] == subject
    ]
    assert rows, "oracle subject has no cases"
    request = "\n".join(json.dumps(row["input"]) for row in rows) + "\n"
    result = build.execute_binary(
        context, build.BinaryCall("exe:agentctl-core-eval", input_text=request)
    )
    assert isinstance(result, Ok), result
    assert result.value.code == 0, result.value.stderr
    actual = [json.loads(line) for line in result.value.stdout.splitlines()]
    assert_oracle(
        lambda _: actual,
        None,
        [row["expected"] for row in rows],
        row_id=reason,
    )
