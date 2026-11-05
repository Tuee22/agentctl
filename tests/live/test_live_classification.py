# Copyright (c) 2026 agentctl contributors.
"""Existing authenticated agents are observed without input or answered dialogs."""

from pathlib import Path

import pytest

from tests.harness.live import exercise_live
from tests.harness.tmux import PrivateMux

pytestmark = pytest.mark.evidence("real")


def test_live_screen_classes(root: Path, mux_server: PrivateMux) -> None:
    """Native launch or refusal and screen classification follow observed auth state."""
    exercise_live(root, mux_server)
