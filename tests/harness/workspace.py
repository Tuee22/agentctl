# Copyright (c) 2026 agentctl contributors.
"""Run-owned temporary workspace shared independently of native fixture imports."""

from collections.abc import Iterator
from tempfile import TemporaryDirectory

import pytest


@pytest.fixture(scope="session", autouse=True)
def native_workspace() -> Iterator[None]:
    """Keep native build paths within run-owned storage."""
    with (
        TemporaryDirectory(prefix="b-") as temporary,
        pytest.MonkeyPatch.context() as patch,
    ):
        patch.setenv("AGENTCTL_TEST_NATIVE_ROOT", temporary)
        yield
