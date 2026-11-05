# Copyright (c) 2026 agentctl contributors.
"""Real digest builds, immutable publication, identity and observed warm reuse."""

import hashlib
import json
import os
import shutil
import sys
import time
from pathlib import Path

import pytest

from agentctl.bootstrap import binary, build, cache
from agentctl.check import haskell, identity
from agentctl.check.preconditions import exclusive_file
from agentctl.check.steps import run_tools
from agentctl.process import Output, run, start, stop
from agentctl.result import Err, Ok
from tests.harness.binary import request
from tests.harness.bootstrap import native_tools, pins
from tests.harness.nonce import fresh


def _layout(value: binary.Request) -> cache.Layout:
    """Resolve the subject's destination, then inspect its real contents separately."""
    result = binary.plan(value, pins())
    assert isinstance(result, Ok), result
    return result.value


def _context(value: binary.Request) -> build.BuildContext:
    """Use this owned digest build with the genuine recorded compiler and Cabal."""
    return build.BuildContext(
        value.project, _layout(value).directory, value.host, native_tools()
    )


def _snapshot(directory: Path) -> dict[str, bytes]:
    """Read published bytes independently of any cache identity or subject report."""
    return {
        path.relative_to(directory).as_posix(): path.read_bytes()
        for path in directory.rglob("*")
        if path.is_file()
    }


def _actor_arguments(
    root: Path, value: binary.Request, nonce: str, marker: Path | None = None
) -> list[str]:
    """Give an isolated observer only harmless unexpected command candidates."""
    harmless = (
        Path(os.environ["SYSTEMROOT"]) / "System32/where.exe"
        if value.host.family == "Windows"
        else Path(shutil.which("false") or "/missing-false")
    )
    assert harmless.is_file()
    return [
        sys.executable,
        str(root / "tests/fixtures/haskell/cache_actor.py.txt"),
        str(value.project),
        str(value.pins),
        str(value.host.cache),
        str(value.data),
        str(value.host.home),
        native_tools().ghc,
        str(harmless),
        nonce,
        str(marker) if marker is not None else "",
    ]


def _observed(output: Output, nonce: str, expected: Path) -> None:
    """Require the real handoff control and no hidden bootstrap or build spawn."""
    assert output.code == 0, output.stderr
    payload: object = json.loads(output.stdout)
    assert isinstance(payload, dict)
    assert payload["nonce"] == nonce
    assert payload["binary"] == str(expected)
    assert payload["events"] == [
        {"nonce": nonce, "argv": [str(expected), "--handshake"], "blocked": False}
    ], "digest hit rebuilt or probed the toolchain"


@pytest.mark.evidence("observer")
def test_second_run_spawns_nothing(root: Path, tmp_path: Path) -> None:
    """A genuine cold build precedes a warm hit observed beside its handoff control."""
    value = request(root, tmp_path)
    result = binary.ensure(value)
    assert isinstance(result, Ok), result
    before = _snapshot(value.data / "bin")
    nonce = fresh(os.environ.get("AGENTCTL_CHECK_NONCE", "focused"))
    observed = run(_actor_arguments(root, value, nonce), cwd=root, env=os.environ)
    assert isinstance(observed, Ok), observed
    _observed(observed.value, nonce, result.value)
    assert _snapshot(value.data / "bin") == before


@pytest.mark.evidence("real")
def test_failed_build_keeps_previous(root: Path, tmp_path: Path) -> None:
    """A compiler type error leaves the previous publish intact and adds no entry."""
    value = request(root, tmp_path)
    assert isinstance(binary.ensure(value), Ok)
    before = _snapshot(value.data / "bin")
    entries = set((value.data / "bin").iterdir())
    module = value.project / "src/AgentCtl/Protocol.hs"
    module.write_text(
        module.read_text(encoding="utf-8").replace(
            "protocolVersion = 1", 'protocolVersion = "broken"'
        ),
        encoding="utf-8",
    )
    result = binary.ensure(value)
    assert isinstance(result, Err), result
    assert "Protocol.hs" in result.error.message
    assert (
        haskell.run_step(
            haskell.HaskellStep("cabal-build", value.host, value.project),
            tmp_path / "reports",
            "focused",
        )
        == 1
    )
    assert set((value.data / "bin").iterdir()) == entries, (
        "failed build exposed a partial digest"
    )
    assert _snapshot(value.data / "bin") == before


@pytest.mark.evidence("real")
def test_handshake_mismatch_rejected(root: Path, tmp_path: Path) -> None:
    """A compiling wrong-protocol twin publishes nothing beside a genuine publish."""
    value = request(root, tmp_path)
    assert isinstance(binary.ensure(value), Ok)
    before = _snapshot(value.data / "bin")
    module = value.project / "src/AgentCtl/Protocol.hs"
    module.write_text(
        module.read_text(encoding="utf-8").replace(
            "handshake = Handshake protocolVersion commandList",
            "handshake = Handshake 2 commandList",
        ),
        encoding="utf-8",
    )
    result = binary.ensure(value)
    assert isinstance(result, Err), "wrong protocol was published"
    assert "protocol" in result.error.message
    assert not _layout(value).binary.parent.exists(), "wrong protocol was published"
    assert _snapshot(value.data / "bin") == before


@pytest.mark.evidence("real")
def test_identity_step_rejects_foreign_binary(root: Path, tmp_path: Path) -> None:
    """Byte hashing accepts the genuine file and refuses a foreign owned entry."""
    value = request(root, tmp_path)
    published = binary.ensure(value)
    assert isinstance(published, Ok), published
    context = _context(value)
    result = binary.identify(context, value.data, pins_file=value.pins)
    assert isinstance(result, Ok), result
    assert (
        result.value.sha256 == hashlib.sha256(published.value.read_bytes()).hexdigest()
    )
    step = identity.IdentityStep(value.host, value.project, value.data)
    assert run_tools(root, tmp_path / "reports", "focused", (step,)) == 0
    replacement = tmp_path / "foreign"
    replacement.write_bytes(b"owned foreign binary")
    replacement.replace(published.value)
    result = binary.identify(context, value.data, pins_file=value.pins)
    assert isinstance(result, Err), "foreign binary was accepted by identity"
    assert "identity mismatch" in result.error.message
    assert identity.run_step(step) != 0
    assert published.value.read_bytes() == b"owned foreign binary"


@pytest.mark.evidence("observer")
def test_waiter_uses_published_winner(root: Path, tmp_path: Path) -> None:
    """A real lock waiter sees its predecessor's publish without launching Cabal."""
    value = request(root, tmp_path)
    context = _context(value)
    assert isinstance(build.compile_project(context), Ok)
    built = build.binary(context, "exe:agentctl-core")
    assert isinstance(built, Ok)
    layout = _layout(value)
    marker = tmp_path / "lock-attempted"
    nonce = fresh(os.environ.get("AGENTCTL_CHECK_NONCE", "focused"))
    with exclusive_file(layout.directory / "build.lock") as held:
        assert held == Ok(None)
        child = start(
            _actor_arguments(root, value, nonce, marker), cwd=root, env=os.environ
        )
        assert isinstance(child, Ok), child
        try:
            deadline = time.monotonic() + 5
            while not marker.exists() and time.monotonic() < deadline:
                time.sleep(0.01)
            assert marker.is_file(), "waiter never attempted the native lock"
            assert binary.publish(context, built.value, layout) == Ok(layout.binary)
        except BaseException:
            stop(child.value)
            raise
    try:
        deadline = time.monotonic() + 15
        while child.value.handle.poll() is None and time.monotonic() < deadline:
            time.sleep(0.01)
        assert child.value.handle.poll() is not None, "waiter did not finish"
    finally:
        output = stop(child.value)
    assert isinstance(output, Ok), output
    _observed(output.value, nonce, layout.binary)
