# Copyright (c) 2026 agentctl contributors.
"""Select an asserted native launch or refusal from existing authentication state."""

from pathlib import Path

import pytest

from tests.harness.haskell_fixtures import haskell_build as _haskell_build_fixture
from tests.harness.live import exercise_live
from tests.harness.tmux import PrivateMux
from tests.harness.tmux_fixtures import mux_server as _mux_server_fixture

haskell_build = _haskell_build_fixture
mux_server = _mux_server_fixture

pytestmark = pytest.mark.evidence("real")


@pytest.mark.parametrize("arguments", [(), ("--",)], ids=["empty", "separator"])
def test_live_launch(
    root: Path, mux_server: PrivateMux, arguments: tuple[str, ...]
) -> None:
    """Preserve launch, argv and refusal checks and classify the current screen."""
    exercise_live(root, mux_server, arguments)
