# Copyright (c) 2026 agentctl contributors.
"""Request-derived launch actions through the pure native decision kernel."""

from pathlib import Path

import pytest

from agentctl.bootstrap import build
from tests.harness.evaluate import compare_subject

pytestmark = pytest.mark.evidence("value")


def test_launch_plan_matches_oracle(
    root: Path, haskell_build: build.BuildContext
) -> None:
    """Cleanup, refusal statuses, preflight bypass and handover remain explicit."""
    compare_subject(
        root,
        haskell_build,
        "preflight.toml",
        "launch-plan",
        "launch plan differs from oracle",
    )
