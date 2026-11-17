# Copyright (c) 2026 agentctl contributors.
"""Existing authenticated agents are observed without input or answered dialogs."""

from pathlib import Path

import pytest

from tests.harness.haskell_fixtures import haskell_build as _haskell_build_fixture
from tests.harness.live import exercise_live
from tests.harness.tmux import PrivateMux
from tests.harness.tmux_fixtures import mux_server as _mux_server_fixture

haskell_build = _haskell_build_fixture
mux_server = _mux_server_fixture

pytestmark = pytest.mark.evidence("real")


def test_live_screen_classes(root: Path, mux_server: PrivateMux) -> None:
    """Native launch or refusal and screen classification follow observed auth state."""
    exercise_live(root, mux_server)
