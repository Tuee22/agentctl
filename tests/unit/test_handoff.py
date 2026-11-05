# Copyright (c) 2026 agentctl contributors.
"""Process lifetime is selected from OS values rather than the test runner's OS."""

import tomllib
from pathlib import Path

import pytest

from agentctl.bootstrap.handoff import Mode, mode
from tests.harness.oracle import assert_oracle

pytestmark = pytest.mark.evidence("value")


def test_handoff_mode_by_os_family(root: Path) -> None:
    """Replace the POSIX process and inherit a Windows child with its status."""
    rows = tomllib.loads(
        (root / "tests/oracles/command_surface.toml").read_text(encoding="utf-8")
    )["case"]
    selected = [row for row in rows if row["input"]["subject"] == "handoff-mode"]
    assert {member.value for member in Mode} == {row["expected"] for row in selected}
    assert {row["input"]["family"] for row in selected} == {
        "Linux",
        "Darwin",
        "Windows",
    }
    for row in selected:
        family = row["input"]["family"]
        assert family in {"Linux", "Darwin", "Windows"}
        assert_oracle(
            lambda selected: mode(selected).value,
            family,
            row["expected"],
            row_id="handoff mode differs from host contract",
        )
