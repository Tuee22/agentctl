# Copyright (c) 2026 agentctl contributors.
"""Independent selection changes and owned actuation actors."""

import json
import os
import sys
import tomllib
from dataclasses import replace
from pathlib import Path

import pytest

from agentctl.bootstrap import toolchain
from agentctl.bootstrap.pins import Pins
from agentctl.check.audit import Record, read
from agentctl.hostfacts import HostContext, ghcup_destination
from agentctl.process import run
from agentctl.result import Err, Ok, Result
from tests.harness.bootstrap import context, native_tools, pins
from tests.harness.nonce import fresh


def _actor(
    root: Path, directory: Path, mode: str
) -> tuple[tuple[Record, ...], toolchain.Toolchain]:
    """Reap a nonce-bound actor whose installer candidate is a harmless binary."""
    directory.mkdir()
    native = native_tools()

    def spelling(path: str) -> str:
        parent = Path(path).parent
        return str(parent) + "/../" + parent.name + "/" + Path(path).name

    tools = toolchain.Toolchain(spelling(native.ghc), spelling(native.cabal))
    nonce = fresh(os.environ.get("AGENTCTL_CHECK_NONCE", "focused"))
    manifest = os.environ.get("AGENTCTL_CHECK_MANIFEST")
    observers = (
        Path(manifest).parent / "observers"
        if manifest is not None and manifest != ""
        else directory
    )
    log = observers / (nonce + ".jsonl")
    result = run(
        [
            sys.executable,
            str(root / "tests/fixtures/bootstrap/toolchain_actor.py.txt"),
            mode,
            str(directory),
            str(log),
            nonce,
            tools.ghc,
            tools.cabal,
        ],
        cwd=root,
        env=os.environ,
    )
    assert isinstance(result, Ok)
    assert result.value.code == 0, (
        "recorded tool paths were not used verbatim: " + result.value.stderr
    )
    payload: object = json.loads(result.value.stdout)
    assert isinstance(payload, dict)
    if mode in {"warm", "whereis"}:
        assert payload["ghc"] == tools.ghc
        assert payload["cabal"] == tools.cabal
        text = payload["record"]
        assert isinstance(text, str)
        assert tomllib.loads(text) == {"ghc": tools.ghc, "cabal": tools.cabal}
    else:
        assert payload == {"refused": True}
    records = read(log, nonce)
    assert isinstance(records, Ok)
    assert records.value[0].argv == (sys.executable, "-c", "print('observer control')")
    assert not records.value[0].vetoed
    return records.value[1:], tools


@pytest.mark.evidence("observer")
def test_argv_never_sets(root: Path, tmp_path: Path) -> None:
    """The first vetoed install is exact for missing GHC and missing cabal."""
    for mode, expected in (
        ("ghc", ("install", "ghc", "9.12.4")),
        ("cabal", ("install", "cabal", "3.16.1.0", "--no-set")),
    ):
        records, _tools = _actor(root, tmp_path / mode, mode)
        assert len(records) == 1
        assert records[0].argv[1:] == expected, (
            "toolchain install argv changed default selection"
        )
        assert records[0].vetoed


@pytest.mark.evidence("observer")
def test_whereis_paths_used_verbatim(root: Path, tmp_path: Path) -> None:
    """Resolved noncanonical paths are verified and recorded with an empty PATH."""
    records, tools = _actor(root, tmp_path / "whereis", "whereis")
    assert tuple(record.argv for record in records) == (
        (tools.ghc, "--numeric-version"),
        (tools.cabal, "--numeric-version"),
    ), "recorded tool paths were not used verbatim"
    assert all(not record.vetoed for record in records)


@pytest.mark.evidence("observer")
def test_warm_run_spawns_only_version_checks(root: Path, tmp_path: Path) -> None:
    """An already complete toolchain attempts exactly its two recorded executables."""
    records, tools = _actor(root, tmp_path / "warm", "warm")
    assert tuple(record.argv for record in records) == (
        (tools.ghc, "--numeric-version"),
        (tools.cabal, "--numeric-version"),
    ), "warm toolchain called ghcup"
    assert all(not record.vetoed for record in records)


@pytest.mark.evidence("real")
def test_default_links_unchanged_by_step(tmp_path: Path) -> None:
    """A changed target or executable fails after real warm pin verification."""
    value, selected, native = context(tmp_path), pins(), native_tools()
    assert toolchain.record(native, value.cache) == Ok(native)
    family = value.family
    assert family in {"Linux", "Darwin", "Windows"}
    directory = ghcup_destination(family, dict(value.environment), value.home).parent
    directory.mkdir(parents=True)
    default = directory / "ghc"
    default.write_bytes(b"original default")
    assert toolchain.checked(value, selected) == Ok(native)

    def changed(
        ctx: HostContext, pinned: Pins
    ) -> Result[toolchain.Toolchain, toolchain.ToolchainError]:
        default.write_bytes(b"different default")
        return toolchain.ensure(ctx, pinned)

    result = toolchain.checked(value, selected, changed)
    assert isinstance(result, Err), "default selection changes were ignored"
    assert "default ghc or cabal" in result.error.message
    if os.name != "nt":
        default.unlink()
        default.symlink_to("first-target")
        assert toolchain.checked(value, selected) == Ok(native)

        def retarget(
            ctx: HostContext, pinned: Pins
        ) -> Result[toolchain.Toolchain, toolchain.ToolchainError]:
            default.unlink()
            default.symlink_to("second-target")
            return toolchain.ensure(ctx, pinned)

        assert isinstance(toolchain.checked(value, selected, retarget), Err), (
            "default selection changes were ignored"
        )


@pytest.mark.evidence("real")
def test_default_observation_failures(tmp_path: Path) -> None:
    """Unreadable entries and invalid hosts never pass selection preservation."""
    value, selected, native = context(tmp_path), pins(), native_tools()
    assert isinstance(toolchain.defaults(replace(value, family="unsupported")), Err)
    assert isinstance(
        toolchain.checked(replace(value, family="unsupported"), selected), Err
    )
    family = value.family
    assert family in {"Linux", "Darwin", "Windows"}
    bin_dir = ghcup_destination(family, dict(value.environment), value.home).parent
    bin_dir.mkdir(parents=True)
    (bin_dir / "ghc").mkdir()
    assert isinstance(toolchain.defaults(value), Err)
    (bin_dir / "ghc").rmdir()
    assert toolchain.record(native, value.cache) == Ok(native)

    def unreadable(
        ctx: HostContext, pinned: Pins
    ) -> Result[toolchain.Toolchain, toolchain.ToolchainError]:
        (bin_dir / "ghc").mkdir()
        return toolchain.ensure(ctx, pinned)

    assert isinstance(toolchain.checked(value, selected, unreadable), Err)
    (bin_dir / "ghc").rmdir()
    found = tmp_path / "path-bin"
    found.mkdir()
    candidate = found / ("ghcup.exe" if family == "Windows" else "ghcup")
    candidate.write_bytes(b"discovery-only fixture")
    candidate.chmod(0o755)
    alternate = replace(
        value,
        environment=tuple({**dict(value.environment), "PATH": str(found)}.items()),
    )
    entries = toolchain.defaults(alternate)
    assert isinstance(entries, Ok)
    assert {entry.path.parent for entry in entries.value} == {found, bin_dir}
