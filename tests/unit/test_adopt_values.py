# Copyright (c) 2026 agentctl contributors.
"""Adoption never creates ownership and every use checks its recorded identity."""

from pathlib import Path

import pytest

from agentctl.bootstrap import build
from tests.harness.evaluate import compare_subject

pytestmark = pytest.mark.evidence("value")


def test_adopt_rows_match_oracle(root: Path, haskell_build: build.BuildContext) -> None:
    """Registration, three-part revalidation and forgetting match independent rows."""
    for subject in (
        "adopt-decision",
        "adopt-revalidate",
        "adopt-stop",
        "adopt-endpoint",
    ):
        compare_subject(
            root,
            haskell_build,
            "session_ownership.toml",
            subject,
            "adopted pane policy differs from ownership oracle",
        )
