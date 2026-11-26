# Copyright (c) 2026 agentctl contributors.
"""Refusal paths of the write guard's index, observer and extended-path readers."""

import os
import shutil
import stat
import sys
from pathlib import Path, PosixPath, PureWindowsPath
from typing import Self, override

import pytest

from agentctl.check import writeguard
from agentctl.foundation import Err, Ok

pytestmark = pytest.mark.evidence("value")
PID_ONE = 1
BIRTH = 5
BACKSLASH = chr(92)
EXTENDED_PREFIX = BACKSLASH * 2 + "?" + BACKSLASH


def _git() -> str:
    found = shutil.which("git")
    assert found is not None
    return found


def _script(path: Path, body: str) -> str:
    path.write_text("#!/bin/sh\n" + body + "\n", encoding="utf-8")
    path.chmod(stat.S_IRWXU)
    return str(path)


def _index(root: Path, git: str) -> object:
    return writeguard.__dict__["_index"](root, git)


def test_index_refuses_an_unlaunchable_git(tmp_path: Path) -> None:
    """A missing Git executable is a typed observation failure."""
    assert isinstance(_index(tmp_path, str(tmp_path / "absent-git")), Err)


def test_index_refuses_a_failing_git(tmp_path: Path) -> None:
    """Git run outside a repository reports its refusal."""
    outcome = _index(tmp_path, _git())
    assert isinstance(outcome, Err)
    assert outcome.error.message


def test_index_refuses_an_empty_index_path(tmp_path: Path) -> None:
    """Git output without a path cannot identify the index."""
    git = _script(tmp_path / "git", "echo")
    assert _index(tmp_path, git) == Err(
        writeguard.GuardError("git returned an empty index path")
    )


def test_index_refuses_a_path_below_a_file(tmp_path: Path) -> None:
    """A stat failure other than absence is not treated as an absent index."""
    (tmp_path / "plain").write_text("x", encoding="utf-8")
    git = _script(tmp_path / "git", "echo plain/index")
    outcome = _index(tmp_path, git)
    assert isinstance(outcome, Err)


def test_index_refuses_an_unreadable_index(tmp_path: Path) -> None:
    """A regular index whose bytes cannot be read fails the observation."""
    index = tmp_path / "index"
    index.write_bytes(b"data")
    index.chmod(0)
    git = _script(tmp_path / "git", "echo index")
    try:
        readable = os.access(index, os.R_OK)
        outcome = _index(tmp_path, git)
    finally:
        index.chmod(stat.S_IRWXU)
    assert isinstance(outcome, Ok if readable else Err)


def test_extended_paths_use_the_native_prefix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Windows extended spellings are chosen from the resolved path text."""
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    with monkeypatch.context() as scope:
        scope.setattr(os, "name", "nt")
        plain = writeguard.filesystem_path(run_dir)
    assert str(plain).startswith(EXTENDED_PREFIX)


def test_containment_refuses_a_symlinked_observer_directory(tmp_path: Path) -> None:
    """The observers directory must be owned, not a link elsewhere."""
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "observers").symlink_to(elsewhere)
    assert writeguard.containment(run_dir, "nonce", "Linux") == Err(
        writeguard.GuardError("observer directory is a symlink")
    )


def test_observer_identity_reports_an_unobservable_birth() -> None:
    """A foreign-family birth cannot be observed on this host."""
    identity = writeguard.__dict__["_observer_identity"](
        {"birth": BIRTH}, PID_ONE, "Windows" if sys.platform != "win32" else "Linux"
    )
    assert isinstance(identity, Err)


class _Spelled(PosixPath):
    """A run directory whose native resolution is a fixed Windows spelling."""

    spelling = ""

    @override
    def resolve(self, strict: bool = False) -> Self:
        """Report the fixed spelling a Windows host would produce."""
        del strict
        return self.with_segments(self.spelling)


class _Extended(_Spelled):
    """An already extended Windows spelling."""

    spelling = EXTENDED_PREFIX + "C:" + BACKSLASH + "run"


class _Unc(_Spelled):
    """A network share spelling."""

    spelling = BACKSLASH * 2 + "host" + BACKSLASH + "share"


def test_extended_path_spellings_keep_existing_prefixes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Extended spellings stay and share spellings gain the UNC extension."""
    cases = (
        (_Extended("run"), _Extended.spelling),
        (
            _Unc("run"),
            EXTENDED_PREFIX + "UNC" + BACKSLASH + "host" + BACKSLASH + "share",
        ),
    )
    for run_dir, expected in cases:
        with monkeypatch.context() as scope:
            scope.setattr(os, "name", "nt")
            observed = writeguard.filesystem_path(run_dir)
        assert str(observed) == str(PureWindowsPath(expected))
