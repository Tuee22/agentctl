# Copyright (c) 2026 agentctl contributors.
"""Shared repository location and explicit fixture-tree construction."""

from pathlib import Path

import pytest

pytest_plugins = ("tests.harness.host", "tests.harness.workspace")


@pytest.fixture(scope="session")
def root() -> Path:
    """Locate the checkout independently of the test's current directory."""
    return Path(__file__).resolve().parents[1]
