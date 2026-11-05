# Copyright (c) 2026 agentctl contributors.
"""Independent argument-assembly cases through the native pure subject."""

from pathlib import Path

import pytest

from agentctl.bootstrap import build
from tests.harness.evaluate import compare_subject

pytestmark = pytest.mark.evidence("value")


def test_launch_argv_matches_oracle(
    root: Path, haskell_build: build.BuildContext
) -> None:
    """Flags occur before the first separator and positional text stays literal."""
    compare_subject(
        root,
        haskell_build,
        "launch_argv.toml",
        "launch-argv",
        "launch argv differs from oracle",
    )
