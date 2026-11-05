# Copyright (c) 2026 agentctl contributors.
"""PEP 610 editable identity's positive and negative boundaries."""

from pathlib import Path

import pytest

from agentctl.check.preconditions import identity, python_floor
from agentctl.check.steps import environment

pytestmark = pytest.mark.evidence("value")


def test_non_editable_refused(tmp_path: Path) -> None:
    """Require editable metadata, rejecting missing and noneditable records."""
    module = tmp_path / "src/agentctl/__init__.py"
    good = {"url": tmp_path.as_uri(), "dir_info": {"editable": True}}
    assert identity(tmp_path, good, module) == ()
    for bad in (None, {}, {"url": tmp_path.as_uri(), "dir_info": {"editable": False}}):
        assert identity(tmp_path, bad, module)[0].startswith("P1:")


def test_other_checkout_refused(tmp_path: Path) -> None:
    """Join distribution URL and loaded module to the same source root."""
    metadata = {"url": tmp_path.as_uri(), "dir_info": {"editable": True}}
    assert identity(tmp_path, metadata, tmp_path / "src/agentctl/cli.py") == ()
    assert identity(tmp_path, metadata, tmp_path / "other/cli.py")
    assert identity(tmp_path / "other", metadata, tmp_path / "src/agentctl/cli.py")


def test_python_floor() -> None:
    """The floor rejects older interpreters and accepts current and future ones."""
    for version in ((2, 7), (3, 11)):
        assert python_floor(version)[0].startswith("P3:")
    for version in ((3, 12), (3, 13), (4, 0)):
        assert python_floor(version) == ()


def test_check_preserves_ghcup_environment(tmp_path: Path) -> None:
    """The check child keeps XDG binary discovery and the empty ghcup XDG switch."""
    overrides = {
        "GHCUP_USE_XDG_DIRS": "",
        "XDG_BIN_HOME": str(tmp_path / "binary"),
        "GHCUP_INSTALL_BASE_PREFIX": str(tmp_path / "prefix"),
    }
    child = environment(overrides, tmp_path / "run", "nonce")
    assert {name: child[name] for name in overrides} == overrides
