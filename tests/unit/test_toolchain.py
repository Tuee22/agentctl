# Copyright (c) 2026 agentctl contributors.
"""Typed actuation, complete path records and cold/warm error boundaries."""

import os
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from agentctl.bootstrap import toolchain
from agentctl.bootstrap.pins import Asset, Version
from agentctl.bootstrap.plan import DownloadGhcup, GhcupCommand, Refusal
from agentctl.bootstrap.prereqs import (
    PackageInstall,
    PrerequisiteAction,
    PrerequisiteError,
)
from agentctl.hostfacts import (
    Distribution,
    Ghcup,
    HostContext,
    HostFacts,
    Prerequisite,
    read_record,
)
from agentctl.result import Err, Ok, Result
from tests.harness.bootstrap import context, native_tools, pins
from tests.harness.http import Body, serve

pytestmark = pytest.mark.evidence("value")
PRIVATE_MODE = 0o600


def _facts(value: HostContext) -> HostFacts:
    """Describe a contrived Linux host with an existing floor-version ghcup."""
    return HostFacts(
        "Linux",
        "x86_64",
        value.home / ".ghcup/bin/ghcup",
        Ghcup(value.home / ".ghcup/bin/ghcup", Version((0, 1, 50, 2))),
        None,
        None,
        distribution=Distribution("ubuntu", 24),
    )


def test_apply_sequence_and_verified_record(tmp_path: Path) -> None:
    """Only complete verified resolutions are recorded after the ordered commands."""
    value, selected, native = context(tmp_path), pins(), native_tools()
    facts = _facts(value)
    actions = tuple(
        GhcupCommand(facts.ghcup_destination, args)
        for args in (
            ("install", "ghc", "9.12.4"),
            ("install", "cabal", "3.16.1.0", "--no-set"),
            ("whereis", "ghc", "9.12.4"),
            ("whereis", "cabal", "3.16.1.0"),
        )
    )
    observed: list[tuple[str, ...]] = []

    def invoke(
        action: GhcupCommand, _context: HostContext
    ) -> Result[str, toolchain.ToolchainError]:
        observed.append(action.arguments)
        return Ok(
            (native.ghc if action.arguments[1] == "ghc" else native.cabal)
            if action.arguments[0] == "whereis"
            else "informational output"
        )

    assert toolchain.apply(
        facts, selected, value, actions, toolchain.Actuation(invoke=invoke)
    ) == Ok(native)
    assert tuple(observed) == tuple(action.arguments for action in actions)
    assert read_record(value.cache) == Ok((native.ghc, native.cabal))
    if os.name != "nt":
        assert (
            value.cache / "toolchain-paths.toml"
        ).stat().st_mode & 0o777 == PRIVATE_MODE
    assert tuple(value.cache.iterdir()) == (value.cache / "toolchain-paths.toml",)


def test_apply_refuses_partial_or_failed_resolution(tmp_path: Path) -> None:
    """A command, invalid path or wrong version cannot leave a new record."""
    value, selected = context(tmp_path), pins()
    facts = _facts(value)
    action = GhcupCommand(facts.ghcup_destination, ("whereis", "ghc", "9.12.4"))

    def failed(
        _action: GhcupCommand, _context: HostContext
    ) -> Result[str, toolchain.ToolchainError]:
        return Err(toolchain.ToolchainError("controlled command failure"))

    def relative(
        _action: GhcupCommand, _context: HostContext
    ) -> Result[str, toolchain.ToolchainError]:
        return Ok("relative/ghc")

    for result in (
        toolchain.apply(
            facts, selected, value, (action,), toolchain.Actuation(invoke=failed)
        ),
        toolchain.apply(
            facts, selected, value, (action,), toolchain.Actuation(invoke=relative)
        ),
        toolchain.apply(facts, selected, value, ()),
        toolchain.resolved("relative/ghc", selected.ghc, value),
        toolchain.resolved(sys.executable, selected.ghc, value),
    ):
        assert isinstance(result, Err)
    assert not value.cache.exists()
    package = PackageInstall(("fixture-only",), (("unreachable-installer",),))
    assert isinstance(toolchain.apply(facts, selected, value, (package,)), Err)
    assert not value.cache.exists()

    def prepared(
        _action: PrerequisiteAction, _facts: HostFacts, _context: HostContext
    ) -> Result[tuple[Prerequisite, ...], PrerequisiteError]:
        return Ok(
            tuple(
                Prerequisite(name, ready=True)
                for name in (
                    "compiler-and-gmp",
                    "downloader",
                    "ca-certificates",
                    "make",
                )
            )
        )

    native = native_tools()
    assert toolchain.apply(
        replace(facts, ghc=native.ghc, cabal=native.cabal),
        selected,
        value,
        (package,),
        toolchain.Actuation(prepare=prepared),
    ) == Ok(native)


def test_download_action_and_failure(tmp_path: Path) -> None:
    """Download actuation shares the verified provider and stops at its first error."""
    value, selected = context(tmp_path), pins()
    facts = replace(_facts(value), ghcup=None)
    asset = Asset("Linux", "x86_64", "file:///unreachable", "0" * 64)
    local = replace(selected, assets=(asset,))
    assert isinstance(
        toolchain.apply(
            facts, local, value, (DownloadGhcup(asset, facts.ghcup_destination),)
        ),
        Err,
    )
    native = native_tools()
    with serve(tmp_path / "server", (Body("/empty", b"", "0"),)) as server:
        asset = replace(
            asset,
            url=server.url + "/empty",
            sha256="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        )
        complete = replace(facts, ghc=native.ghc, cabal=native.cabal)
        assert toolchain.apply(
            complete,
            replace(selected, assets=(asset,)),
            value,
            (DownloadGhcup(asset, facts.ghcup_destination),),
        ) == Ok(native)


def test_command_outputs_and_environment(tmp_path: Path) -> None:
    """The real bounded process adapter preserves output and reports failed spawns."""
    value = context(tmp_path)
    before = value.environment
    changed = toolchain.ghcup_context(value)
    assert value.environment == before
    assert dict(changed.environment)["GHCUP_SKIP_UPDATE_CHECK"] == "1"
    successful = GhcupCommand(Path(sys.executable), ("-c", "print('exact output')"))
    assert toolchain.command(successful, value) == Ok("exact output")
    assert isinstance(
        toolchain.command(
            replace(successful, arguments=("-c", "raise SystemExit(3)")), value
        ),
        Err,
    )
    assert isinstance(
        toolchain.command(replace(successful, executable=tmp_path / "missing"), value),
        Err,
    )


def test_record_atomicity_and_storage_failure(tmp_path: Path) -> None:
    """Quoted paths round-trip, and failed storage preserves the prior file bytes."""
    native = native_tools()
    cache = tmp_path / "cache"
    tools = toolchain.Toolchain(
        str(tmp_path / 'GHC "quoted"/ghc'), str(tmp_path / "cabal\\path")
    )
    assert toolchain.record(tools, cache) == Ok(tools)
    assert read_record(cache) == Ok((tools.ghc, tools.cabal))
    occupied = tmp_path / "occupied"
    occupied.write_bytes(b"preserve")
    assert isinstance(toolchain.record(native, occupied), Err)
    assert occupied.read_bytes() == b"preserve"


def test_ensure_warm_and_cold_failures(tmp_path: Path) -> None:
    """Warm paths answer their pins; invalid or incomplete cold inputs refuse."""
    value, selected, native = context(tmp_path), pins(), native_tools()
    assert toolchain.record(native, value.cache) == Ok(native)
    assert toolchain.ensure(value, selected) == Ok(native)
    assert isinstance(
        toolchain.ensure(replace(value, family="unsupported"), selected), Err
    )
    (value.cache / "toolchain-paths.toml").write_text("invalid = [", encoding="utf-8")
    assert isinstance(toolchain.ensure(value, selected), Err)
    (value.cache / "toolchain-paths.toml").unlink()

    def broken(
        _context: HostContext,
    ) -> Result[tuple[Prerequisite, ...], PrerequisiteError]:
        return Err(
            PrerequisiteError("prerequisite-probe-failed", "controlled probe failure")
        )

    assert toolchain.ensure(value, selected, broken) == Err(
        toolchain.ToolchainError("controlled probe failure")
    )
    release = tmp_path / "os-release"
    release.write_text('ID=arch\nVERSION_ID="1"\n', encoding="utf-8")
    linux = replace(value, family="Linux", os_release=release)

    def missing(
        _context: HostContext,
    ) -> Result[tuple[Prerequisite, ...], PrerequisiteError]:
        return Ok(
            tuple(
                Prerequisite(name, ready=False)
                for name in (
                    "compiler-and-gmp",
                    "downloader",
                    "ca-certificates",
                    "make",
                )
            )
        )

    refused = toolchain.ensure(linux, selected, missing)
    assert isinstance(refused, Err)
    assert "verified package set" in refused.error.message
    assert not (value.cache / "toolchain-paths.toml").exists()
    candidate = _facts(linux).ghcup_destination
    candidate.parent.mkdir(parents=True)
    candidate.write_bytes(b"discovery-only fixture, never executed")
    for reported in (None, Version((0, 1, 50, 1))):

        def inspected(
            _path: str, _context: HostContext, answer: Version | None = reported
        ) -> Version | None:
            return answer

        rejected = toolchain.ensure(
            linux, selected, missing, inspect_versions=inspected
        )
        assert isinstance(rejected, Err)
        assert str(candidate) in rejected.error.message
        assert "0.1.50.2" in rejected.error.message
        assert "ghcup upgrade" in rejected.error.message
        expected = (
            "did not answer --numeric-version" if reported is None else "0.1.50.1"
        )
        assert expected in rejected.error.message
    absent = toolchain.planning_failure(
        Refusal("unsupported-platform", ""),
        replace(_facts(linux), ghcup=None),
        selected,
    )
    assert "unsupported-platform" in absent.message
    assert "ghcup absent" in absent.message
