# Copyright (c) 2026 agentctl contributors.
"""Process image values retain their liveness and identity prerequisites."""

import hashlib
import os
import sys
from io import BufferedReader
from pathlib import Path

import pytest

from agentctl import foundation_process_identity as identity
from agentctl.foundation import Err, Ok
from agentctl.foundation_process_identity import (
    WindowsProcessImage,
    _process_image_file,
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


def test_process_image_file_rejects_foreign_and_replaced_mapping(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The file read must be the image mapping before and after hashing."""
    image = tmp_path / "image"
    image.write_bytes(b"owned image")
    foreign = tmp_path / "foreign"
    foreign.write_bytes(b"other image")
    observed = _process_image_file(image, image)
    assert isinstance(observed, Ok)

    def refuse_foreign_read(*_args: object, **_kwargs: object) -> None:
        pytest.fail("foreign process mapping was accepted")

    with monkeypatch.context() as early:
        early.setattr(Path, "open", refuse_foreign_read)
        assert isinstance(_process_image_file(image, foreign), Err), (
            "foreign process mapping was accepted"
        )
    samefile = Path.samefile
    calls = 0

    def changed_mapping(path: Path, other: Path) -> bool:
        nonlocal calls
        calls += 1
        return calls == 1 and samefile(path, other)

    monkeypatch.setattr(Path, "samefile", changed_mapping)
    assert isinstance(_process_image_file(image, image), Err), (
        "replaced process mapping was accepted"
    )


def test_process_image_file_refuses_missing_and_changed_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Missing, non-file and changing image bytes never produce a file sample."""
    missing = tmp_path / "missing"
    assert isinstance(_process_image_file(missing, missing), Err)
    assert isinstance(_process_image_file(tmp_path, tmp_path), Err)
    image = tmp_path / "image"
    image.write_bytes(b"original")
    digest = hashlib.file_digest
    calls = 0

    def change_after_first_read(stream: BufferedReader, name: str) -> object:
        nonlocal calls
        result = digest(stream, name)
        calls += 1
        if calls == 1:
            image.write_bytes(b"modified")
        return result

    monkeypatch.setattr(hashlib, "file_digest", change_after_first_read)
    assert isinstance(_process_image_file(image, image), Err), (
        "changed process image bytes were accepted"
    )


def test_process_image_refuses_changed_birth(monkeypatch: pytest.MonkeyPatch) -> None:
    """A process identity sampled across PID reuse cannot qualify its image."""
    if sys.platform == "linux":
        linux_values = iter((Ok(11), Ok(12)))
        monkeypatch.setattr(identity, "linux_birth", lambda _pid: next(linux_values))
        result = identity.__dict__["_linux_process_image"](os.getpid())
    else:
        image = Path(sys.executable).resolve(strict=True)
        windows_values = iter(
            (
                Ok(WindowsProcessImage(os.getpid(), 11, image)),
                Ok(WindowsProcessImage(os.getpid(), 12, image)),
            )
        )
        monkeypatch.setattr(
            identity, "windows_process_image", lambda _pid: next(windows_values)
        )
        result = identity.__dict__["_windows_process_image"](os.getpid())
    assert isinstance(result, Err), "changed process birth was accepted"


def test_process_image_file_rejects_inconsistent_reads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Different file-read digests cannot become an accepted observation."""
    image = tmp_path / "image"
    image.write_bytes(b"original")
    original = hashlib.file_digest
    calls = 0

    def inconsistent(stream: BufferedReader, name: str) -> object:
        nonlocal calls
        calls += 1
        return original(stream, name) if calls == 1 else hashlib.sha256(b"different")

    monkeypatch.setattr(hashlib, "file_digest", inconsistent)
    assert isinstance(_process_image_file(image, image), Err), (
        "inconsistent process image reads were accepted"
    )
