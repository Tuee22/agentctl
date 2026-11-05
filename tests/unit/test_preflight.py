# Copyright (c) 2026 agentctl contributors.
"""Independent preflight decisions and every warning class."""

from pathlib import Path

import pytest

from agentctl.bootstrap import build
from tests.harness.evaluate import compare_subject

pytestmark = pytest.mark.evidence("value")


def test_failure_warnings_match_oracle(
    root: Path, haskell_build: build.BuildContext
) -> None:
    """The first failed check determines its warning and nonzero exit status."""
    for subject in ("preflight-order", "preflight-warning"):
        compare_subject(
            root,
            haskell_build,
            "preflight.toml",
            subject,
            "preflight decision differs from oracle",
        )
