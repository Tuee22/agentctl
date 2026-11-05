# Copyright (c) 2026 agentctl contributors.
"""Select an asserted native launch or refusal from existing authentication state."""

from pathlib import Path

import pytest

from tests.harness.live import exercise_live
from tests.harness.tmux import PrivateMux

pytestmark = pytest.mark.evidence("real")


@pytest.mark.parametrize("arguments", [(), ("--",)], ids=["empty", "separator"])
def test_live_launch(
    root: Path, mux_server: PrivateMux, arguments: tuple[str, ...]
) -> None:
    """Preserve launch, argv and refusal checks and classify the current screen."""
    exercise_live(root, mux_server, arguments)
