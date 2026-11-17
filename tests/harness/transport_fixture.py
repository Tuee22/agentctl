# Copyright (c) 2026 agentctl contributors.
"""Private multiplexer fixture imported only by tests that require it."""

import os
from collections.abc import Iterator
from importlib import import_module
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from agentctl.bootstrap import build
from agentctl.check.lanes import HostFacts
from tests.harness.nonce import fresh


@pytest.fixture
def mux_server(
    haskell_build: build.BuildContext, record_host: HostFacts
) -> Iterator[object]:
    """Keep focused and gate runs equally private while using the gate registry."""
    manifest = os.environ.get("AGENTCTL_CHECK_MANIFEST")
    nonce = fresh(os.environ.get("AGENTCTL_CHECK_NONCE", "focused"))
    with TemporaryDirectory(prefix="agentctl-mux-") as temporary:
        directory = Path(temporary) if manifest is None else Path(manifest).parent
        with import_module("tests.harness.tmux").private_mux(
            haskell_build, record_host.family, directory, nonce
        ) as mux:
            yield mux
