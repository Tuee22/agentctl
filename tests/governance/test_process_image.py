# Copyright (c) 2026 agentctl contributors.
"""Process image values retain their liveness and identity prerequisites."""

from pathlib import Path

import pytest

from agentctl.foundation import Err, Ok
from agentctl.foundation_process_identity import (
    WindowsProcessImage,
    checked_windows_image,
)

pytestmark = pytest.mark.evidence("value")


def test_checked_image_refuses_dead_or_ambiguous_values() -> None:
    """Only live positive identities and absolute image paths produce a value."""
    path = Path.cwd() / "observer.exe"
    assert checked_windows_image(7, 8, path, 259, 258) == Ok(
        WindowsProcessImage(7, 8, path)
    )
    assert isinstance(checked_windows_image(7, 8, path, 0, 258), Err), (
        "terminated process image was accepted"
    )
    assert isinstance(checked_windows_image(7, 8, path, 259, 0), Err), (
        "signaled process image was accepted"
    )
    for pid, birth, image, status in (
        (0, 8, path, 259),
        (7, 0, path, 259),
        (7, 8, Path("relative"), 259),
        (True, 8, path, 259),
        (7, True, path, 259),
        (7, 8, path, True),
    ):
        assert isinstance(checked_windows_image(pid, birth, image, status, 258), Err)
