# Copyright (c) 2026 agentctl contributors.
"""Independent watch intent transitions include repeats and stale opt-out."""

from pathlib import Path

import pytest

from agentctl.bootstrap import build
from tests.harness.evaluate import compare_subject

pytestmark = pytest.mark.evidence("value")


def test_watch_transitions_oracle(
    root: Path, haskell_build: build.BuildContext
) -> None:
    """Compare every state, revision, result and planned native command."""
    compare_subject(
        root,
        haskell_build,
        "command_surface.toml",
        "watch-transition",
        "watch transition differs from oracle",
    )
