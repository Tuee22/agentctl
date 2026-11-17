# Copyright (c) 2026 agentctl contributors.
"""Private socket readiness remains independently observable at collection."""

from pathlib import Path

import pytest

from agentctl.check.preconditions import inspect_socket, socket_path_length

pytestmark = pytest.mark.evidence("real")


def test_socket_directory_inspection(tmp_path: Path) -> None:
    """Native ownership determines the Unix path; unreadable directories refuse."""
    assert inspect_socket(tmp_path, "Windows") == ()
    path = (
        tmp_path.resolve() / "mux/00000000" / f"tmux-{tmp_path.stat().st_uid}/default"
    )
    nested = tmp_path / "nested"
    nested.mkdir()
    for family in ("Linux", "Darwin"):
        assert inspect_socket(tmp_path, family) == socket_path_length(path)
        assert inspect_socket(nested / "..", family) == socket_path_length(path)
        assert inspect_socket(tmp_path / "absent", family)[0].startswith("P6:")
