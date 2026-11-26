# Copyright (c) 2026 agentctl contributors.
"""Refusals of the prepared private Cabal index verifier."""

from pathlib import Path

import pytest

from agentctl.bootstrap import build
from agentctl.bootstrap.toolchain import Toolchain
from agentctl.result import Err, Ok
from tests.harness.bootstrap import context

pytestmark = pytest.mark.evidence("real")
STATE = "2026-01-02T03:04:05Z"


def _prepared(tmp_path: Path, *, project: bool = True) -> build.BuildContext:
    """Create a private cache holding the config and index tarball."""
    host = context(tmp_path / "host")
    source = tmp_path / "project"
    source.mkdir()
    if project:
        (source / "cabal.project").write_text(
            f"index-state: {STATE}\n", encoding="utf-8"
        )
    native = build.BuildContext(
        source, tmp_path / "build", host, Toolchain("/ghc", "/cabal")
    )
    index = native.cabal_directory / "packages/hackage.haskell.org/01-index.tar"
    index.parent.mkdir(parents=True)
    index.write_bytes(b"index")
    (native.cabal_directory / "config").write_text("config", encoding="utf-8")
    return native


def test_unpinned_project_refuses_before_inspection(tmp_path: Path) -> None:
    """A project without its pinned index-state is refused as unreadable."""
    native = _prepared(tmp_path, project=False)
    assert isinstance(build.verify_prepared_index(native), Err)


def test_missing_receipt_is_not_prepared(tmp_path: Path) -> None:
    """An absent receipt is the ordinary not-ready refusal, and a match is ready."""
    native = _prepared(tmp_path)
    missing = build.verify_prepared_index(native)
    assert missing == Err(
        build.BuildError("Prepare the pinned Cabal index before running check")
    )
    (native.cabal_directory / "agentctl-index-state").write_text(
        STATE, encoding="utf-8"
    )
    assert build.verify_prepared_index(native) == Ok(None)


def test_unreadable_receipt_is_an_inspection_failure(tmp_path: Path) -> None:
    """A receipt that cannot be read as a file is not mistaken for absence."""
    native = _prepared(tmp_path)
    (native.cabal_directory / "agentctl-index-state").mkdir()
    refused = build.verify_prepared_index(native)
    assert isinstance(refused, Err)
    assert refused.error.message.startswith("Cannot inspect the private Cabal index")
