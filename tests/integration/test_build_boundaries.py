# Copyright (c) 2026 agentctl contributors.
"""Native Cabal and real filesystem failure boundaries without replacement tools."""

from dataclasses import replace
from pathlib import Path

import pytest

from agentctl.bootstrap import build
from agentctl.check import haskell
from agentctl.result import Err, Ok
from tests.harness.bootstrap import context, native_tools

pytestmark = pytest.mark.evidence("real")


def _owned(directory: Path) -> build.BuildContext:
    """Construct an empty, test-owned index context with the genuine toolchain."""
    host = context(directory)
    project = directory / "project"
    project.mkdir()
    (project / "cabal.project").write_text(
        "index-state: 2026-10-31T00:00:00Z\n", encoding="utf-8"
    )
    return build.BuildContext(project, directory / "build", host, native_tools())


def test_native_command_and_artifact_failures(
    haskell_build: build.BuildContext, tmp_path: Path
) -> None:
    """Missing tools, invalid commands and damaged owned outputs fail closed."""
    missing = replace(
        haskell_build,
        tools=replace(haskell_build.tools, cabal=str(tmp_path / "absent-cabal")),
    )
    assert isinstance(build.invoke(missing, ("--version",)), Err)
    assert isinstance(
        build.invoke(haskell_build, ("unrecognised-agentctl-command",)), Err
    )
    assert isinstance(build.binary(haskell_build, "exe:absent"), Err)
    assert isinstance(
        build.execute_binary(haskell_build, build.BinaryCall("exe:absent")), Err
    )
    located = build.binary(haskell_build, "exe:agentctl-core")
    assert isinstance(located, Ok)
    original = located.value.read_bytes()
    backup = located.value.with_suffix(".owned-backup")
    located.value.rename(backup)
    try:
        assert isinstance(build.binary(haskell_build, "exe:agentctl-core"), Err)
        assert isinstance(haskell.compile_all(haskell_build), Err)
    finally:
        backup.replace(located.value)
    located.value.write_bytes(b"invalid native executable")
    try:
        assert isinstance(
            build.execute_binary(haskell_build, build.BinaryCall("exe:agentctl-core")),
            Err,
        )
    finally:
        located.value.write_bytes(original)
    assert isinstance(
        build.execute_binary(
            haskell_build, build.BinaryCall("exe:agentctl-core", ("--handshake",))
        ),
        Ok,
    )


def test_private_index_receipt_and_failure_boundaries(tmp_path: Path) -> None:
    """Only an existing correctly pinned index is warm; every cold failure is typed."""
    value = _owned(tmp_path / "warm")
    private = value.cabal_directory
    index = private / "packages/hackage.haskell.org/01-index.tar"
    index.parent.mkdir(parents=True)
    index.write_bytes(b"owned index presence control")
    receipt = private / "agentctl-index-state"
    receipt.write_text("2026-10-31T00:00:00Z", encoding="utf-8")
    assert build.ensure_index(value) == Ok(None)
    receipt.write_bytes(b"\xff")
    assert isinstance(build.ensure_index(value), Err)
    receipt.unlink()
    broken = replace(
        value, tools=replace(value.tools, cabal=str(tmp_path / "absent-cabal"))
    )
    assert isinstance(build.ensure_index(broken), Err)
    (private / "config").write_text("active-repositories: :none\n", encoding="utf-8")
    index.unlink()
    assert isinstance(build.ensure_index(broken), Err)
    result = build.ensure_index(value)
    assert isinstance(result, Err), result
    assert "did not produce its private package index" in result.error.message
    assert not receipt.exists()
    assert not (value.project / "dist-newstyle").exists()
    index.write_bytes(b"owned index presence control")
    receipt.write_text("different pin", encoding="utf-8")
    assert build.ensure_index(value) == Ok(None)
    assert receipt.read_text(encoding="utf-8") == "2026-10-31T00:00:00Z"
    blocker = _owned(tmp_path / "blocked")
    blocker.host.cache.write_text("not a directory", encoding="utf-8")
    assert isinstance(build.ensure_index(blocker), Err)
    (blocker.project / "cabal.project").unlink()
    assert isinstance(build.compile_project(blocker), Err)


def test_report_recording_rejects_bad_and_unreadable_input(
    tmp_path: Path, haskell_build: build.BuildContext
) -> None:
    """A current complete report records evidence; malformed and missing ones do not."""
    node = "haskell:agentctl-core-test/Handshake/protocol-fields"
    path = tmp_path / "tasty.xml"
    assert isinstance(haskell.record_report(path, frozenset({node}), "fresh"), Err)
    path.write_text("<broken", encoding="utf-8")
    assert isinstance(haskell.record_report(path, frozenset({node}), "fresh"), Err)
    path.write_text(
        '<testsuites tests="1"><testcase classname="agentctl-core-test.Handshake" '
        'name="protocol-fields"/></testsuites>',
        encoding="utf-8",
    )
    assert isinstance(haskell.record_report(path, frozenset({node}), "fresh"), Ok)
    assert isinstance(haskell.record_report(path, frozenset({"other"}), "fresh"), Err)
    path.write_bytes(b"\xff")
    assert isinstance(haskell.record_report(path, frozenset({node}), "fresh"), Err)
    path.unlink()
    path.mkdir()
    assert isinstance(haskell.record_report(path, frozenset({node}), "fresh"), Err)
    blocked = tmp_path / "blocked"
    blocked.write_text("not a directory", encoding="utf-8")
    assert isinstance(haskell.run_suites(haskell_build, blocked, "fresh"), Err)
