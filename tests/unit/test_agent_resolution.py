# Copyright (c) 2026 agentctl contributors.
"""Pure PATH, executable-bit and Windows PATHEXT resolution cases."""

from pathlib import Path

import pytest

from agentctl.bootstrap import build
from tests.harness.evaluate import compare_subject
from tests.harness.haskell_fixtures import haskell_build as _haskell_build_fixture

haskell_build = _haskell_build_fixture

pytestmark = pytest.mark.evidence("value")


def test_resolution_matches_oracle(
    root: Path, haskell_build: build.BuildContext
) -> None:
    """Resolution returns the first absolute executable match and refuses shims."""
    compare_subject(
        root,
        haskell_build,
        "preflight.toml",
        "agent-resolution",
        "agent resolution differs from oracle",
    )
