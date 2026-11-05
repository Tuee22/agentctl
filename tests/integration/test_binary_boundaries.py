# Copyright (c) 2026 agentctl contributors.
"""Native filesystem, lock and wire failures preserve owned published entries."""

import json
import os
import shutil
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from agentctl.bootstrap import binary, build
from agentctl.check import identity
from agentctl.check.preconditions import exclusive_file
from agentctl.process import run
from agentctl.result import Err, Ok
from tests.harness.binary import request
from tests.harness.bootstrap import context, native_tools, pins
from tests.harness.nonce import fresh


def _prepared(value: binary.Request) -> build.BuildContext:
    """Read the native context with the same explicit source and pins as the request."""
    result = binary.check_context(value.host, value.project, value.pins)
    assert isinstance(result, Ok), result
    return result.value


def _fail_while_locked(path: Path) -> None:
    """Expose exceptional scope exit using a real native lock."""
    with exclusive_file(path) as held:
        assert held == Ok(None)
        message = "owned body failure"
        raise ValueError(message)


@pytest.mark.evidence("real")
def test_source_pin_and_toolchain_failures(root: Path, tmp_path: Path) -> None:
    """Missing inputs and a corrupt owned tool record refuse before a build."""
    value = request(root, tmp_path / "subject")
    missing = tmp_path / "missing-pins"
    assert isinstance(binary.ensure(replace(value, pins=missing)), Err)
    assert isinstance(binary.check_context(value.host, value.project, missing), Err)
    prepared = _prepared(value)
    assert isinstance(binary.identify(prepared, value.data, pins_file=missing), Err)
    unsupported = replace(value, host=replace(value.host, family="Other"))
    assert isinstance(binary.ensure(unsupported), Err)
    absent = replace(value, project=tmp_path / "absent-project")
    assert isinstance(binary.ensure(absent), Err)
    assert isinstance(binary.check_context(value.host, absent.project, value.pins), Err)
    assert isinstance(
        binary.identify(replace(prepared, project=absent.project), value.data), Err
    )
    empty = context(tmp_path / "empty")
    assert isinstance(binary.check_context(empty, value.project), Err)
    assert (
        identity.run_step(identity.IdentityStep(empty, value.project, value.data)) == 1
    )
    (value.host.cache / "toolchain-paths.toml").write_bytes(b"\xff")
    result = binary.ensure(value)
    assert isinstance(result, Err), result
    assert "toolchain" in result.error.message


@pytest.mark.evidence("real")
def test_publication_failures_never_replace_existing(
    root: Path, tmp_path: Path
) -> None:
    """Incomplete winners, blocked locks and missing outputs remain typed errors."""
    value = request(root, tmp_path)
    prepared = _prepared(value)
    layout = binary.plan(value, pins())
    assert isinstance(layout, Ok)
    layout.value.binary.parent.mkdir(parents=True)
    marker = layout.value.binary.parent / "winner"
    marker.write_bytes(b"keep existing directory")
    result = binary.publish(prepared, tmp_path / "absent-built", layout.value)
    assert isinstance(result, Err)
    assert "Incomplete" in result.error.message
    assert marker.read_bytes() == b"keep existing directory"
    other = replace(layout.value, binary=value.data / "bin/other/agentctl-core")
    result = binary.publish(prepared, tmp_path / "absent-built", other)
    assert isinstance(result, Err)
    assert "Cannot publish" in result.error.message
    assert not other.binary.parent.exists()
    assert not tuple((value.data / "bin").glob(".binary-*"))
    blocked = tmp_path / "blocked-data"
    blocked.mkdir()
    (blocked / "locks").write_bytes(b"not a directory")
    result = binary.publish(
        prepared,
        tmp_path / "absent-built",
        replace(layout.value, binary=blocked / "bin/other/agentctl-core"),
    )
    assert isinstance(result, Err)
    assert "Cannot open build lock" in result.error.message


@pytest.mark.evidence("real")
def test_native_lock_contention_timeout_and_exception_release(tmp_path: Path) -> None:
    """A contending lock times out and works again after either scope exit."""
    path = tmp_path / "build.lock"
    with exclusive_file(path) as held:
        assert held == Ok(None)
        with exclusive_file(path, timeout=0.06) as refused:
            assert isinstance(refused, Err)
            assert "Timed out" in refused.error.message
    with pytest.raises(ValueError, match="owned body failure"):
        _fail_while_locked(path)
    with exclusive_file(path) as held:
        assert held == Ok(None)
    blocker = tmp_path / "parent-file"
    blocker.write_bytes(b"not a directory")
    with exclusive_file(blocker / "build.lock") as refused:
        assert isinstance(refused, Err)


@pytest.mark.evidence("real")
def test_request_and_identity_lock_failures(root: Path, tmp_path: Path) -> None:
    """The public operations preserve typed errors for blocked and contended locks."""
    value = request(root, tmp_path)
    prepared = _prepared(value)
    prepared.directory.parent.mkdir(parents=True)
    prepared.directory.write_bytes(b"not a directory")
    assert isinstance(binary.ensure(value), Err)
    assert isinstance(binary.identify(prepared, value.data, pins_file=value.pins), Err)
    assert isinstance(build.compile_project(prepared), Err)
    prepared.directory.unlink()
    with exclusive_file(prepared.directory / "build.lock") as held:
        assert held == Ok(None)
        assert isinstance(binary.ensure(value, lock_timeout=0), Err)
        assert isinstance(
            binary.identify(prepared, value.data, pins_file=value.pins, lock_timeout=0),
            Err,
        )
        assert isinstance(build.compile_project(prepared, lock_timeout=0), Err)


@pytest.mark.evidence("real")
def test_handshake_checks_native_output_and_status(root: Path, tmp_path: Path) -> None:
    """Real malformed-JSON and nonzero-exit builds refuse beside a working core."""
    value = request(root, tmp_path)
    prepared = _prepared(value)
    assert isinstance(build.compile_project(prepared), Ok)
    located = build.binary(prepared, "exe:agentctl-core")
    assert isinstance(located, Ok)
    assert binary.verify_handshake(prepared, located.value) == Ok(None)
    assert isinstance(binary.verify_handshake(prepared, tmp_path / "absent"), Err)
    module = value.project / "app/Core.hs"
    original = module.read_text(encoding="utf-8")
    for answer, diagnostic in (
        ('Bytes.putStrLn (encode handshake <> "invalid")', "Invalid core handshake"),
        ("Bytes.putStrLn (encode handshake) >> exitFailure", "does not match"),
    ):
        module.write_text(
            original.replace("Bytes.putStrLn (encode handshake)", answer),
            encoding="utf-8",
        )
        assert isinstance(build.compile_project(prepared), Ok)
        result = binary.verify_handshake(prepared, located.value)
        assert isinstance(result, Err)
        assert diagnostic in result.error.message


@pytest.mark.evidence("real")
def test_identity_refuses_missing_output_incomplete_publish_and_path(
    root: Path, tmp_path: Path
) -> None:
    """Identity checks Cabal, entry completeness and a private executable path."""
    value = request(root, tmp_path)
    prepared = _prepared(value)
    assert isinstance(binary.identify(prepared, value.data, pins_file=value.pins), Err)
    assert isinstance(build.compile_project(prepared), Ok)
    layout = binary.plan(value, pins())
    assert isinstance(layout, Ok)
    layout.value.binary.parent.mkdir(parents=True)
    assert isinstance(binary.identify(prepared, value.data, pins_file=value.pins), Err)
    layout.value.binary.parent.rmdir()
    genuine = binary.identify(prepared, value.data, pins_file=value.pins)
    assert isinstance(genuine, Ok), genuine
    owned_bin = tmp_path / "path"
    owned_bin.mkdir()
    shutil.copy2(genuine.value.published, owned_bin / genuine.value.published.name)
    inherited = dict(prepared.host.environment)
    inherited["PATH"] = str(owned_bin)
    forbidden = replace(
        prepared, host=replace(prepared.host, environment=tuple(inherited.items()))
    )
    refused = binary.identify(forbidden, value.data, pins_file=value.pins)
    assert isinstance(refused, Err)
    assert "must not be on PATH" in refused.error.message


@pytest.mark.evidence("observer")
def test_native_lock_spawn_hash_and_publication_race_controls(
    root: Path, tmp_path: Path
) -> None:
    """Native vetoes and a real racing publisher produce nonce-bound evidence."""
    value = request(root, tmp_path)
    prepared = _prepared(value)
    assert isinstance(build.compile_project(prepared), Ok)
    built = build.binary(prepared, "exe:agentctl-core")
    assert isinstance(built, Ok)
    tools = native_tools()
    for mode in (
        "lock-io",
        "build-unlock",
        "ensure-locate",
        "identify-locate",
        "ensure-unlock",
        "identify-unlock",
        "hash-read",
        "publish-race",
    ):
        nonce = fresh(os.environ.get("AGENTCTL_CHECK_NONCE", "focused"))
        data = tmp_path / mode
        result = run(
            [
                sys.executable,
                str(root / "tests/fixtures/haskell/cache_boundary_actor.py.txt"),
                mode,
                str(value.project),
                str(value.host.cache),
                str(data),
                str(value.host.home),
                str(value.pins),
                tools.ghc,
                tools.cabal,
                str(built.value),
                nonce,
            ],
            cwd=root,
            env=os.environ,
        )
        assert isinstance(result, Ok), result
        assert result.value.code == 0, (mode, result.value.stderr)
        payload: object = json.loads(result.value.stdout)
        assert isinstance(payload, dict)
        assert payload["nonce"] == nonce
        events = payload["events"]
        assert isinstance(events, list)
        assert events[0] == {
            "nonce": nonce,
            "argv": [sys.executable, "-c", "print('observer control')"],
            "blocked": False,
        }
        assert all(
            isinstance(event, dict) and event["nonce"] == nonce for event in events
        )
        if mode == "publish-race":
            assert events[-1]["argv"][1:] == ["--handshake"]
        else:
            assert any(event.get("blocked") or "veto" in event for event in events)
