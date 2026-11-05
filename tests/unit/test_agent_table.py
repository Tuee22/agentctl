# Copyright (c) 2026 agentctl contributors.
"""Independent closed agent entries, including every OS-specific spelling."""

from pathlib import Path

import pytest

from agentctl.bootstrap import build
from tests.harness.evaluate import compare_subject

pytestmark = pytest.mark.evidence("value")


def test_agent_table_matches_oracle(
    root: Path, haskell_build: build.BuildContext
) -> None:
    """Both agents' executables, flags, remedies and recovery text match the data."""
    for subject in ("agent-table", "agent-details"):
        compare_subject(
            root,
            haskell_build,
            "launch_argv.toml",
            subject,
            "agent table differs from oracle",
        )
