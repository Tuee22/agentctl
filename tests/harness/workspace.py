# Copyright (c) 2026 agentctl contributors.
"""Run-owned temporary workspace shared independently of native fixture imports."""

import os
import shutil
import stat
from collections.abc import Iterator
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest


class WorkspaceBoundaryError(OSError):
    """The native workspace no longer matches its recorded owned boundary."""


def _cleanup_path(path: Path, *, windows: bool) -> str:
    """Allow Windows to remove native build paths longer than MAX_PATH."""
    text = str(path)
    if not windows:
        return text
    if text.startswith("\\\\"):
        return "\\\\?\\UNC\\" + text[2:]
    return "\\\\?\\" + text


def cleanup_workspace(path: Path, parent: Path, identity: tuple[int, int]) -> None:
    """Remove only the originally created private root and surface cleanup errors."""
    before = path.lstat()
    resolved = path.resolve(strict=True)
    if (
        path.is_symlink()
        or path.is_junction()
        or not stat.S_ISDIR(before.st_mode)
        or (before.st_dev, before.st_ino) != identity
        or resolved != path
        or resolved.parent != parent.resolve(strict=True)
        or not path.name.startswith("b-")
    ):
        raise WorkspaceBoundaryError
    shutil.rmtree(_cleanup_path(resolved, windows=os.name == "nt"))


@pytest.fixture(scope="session", autouse=True)
def native_workspace() -> Iterator[None]:
    """Keep native build paths within run-owned storage."""
    with (
        TemporaryDirectory(prefix="b-", delete=False) as temporary,
        pytest.MonkeyPatch.context() as patch,
    ):
        path = Path(temporary).resolve(strict=True)
        original = path.lstat()
        patch.setenv("AGENTCTL_TEST_NATIVE_ROOT", temporary)
        try:
            yield
        finally:
            cleanup_workspace(path, path.parent, (original.st_dev, original.st_ino))
