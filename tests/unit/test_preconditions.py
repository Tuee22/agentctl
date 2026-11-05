# Copyright (c) 2026 agentctl contributors.
"""Independent disk, network and bindist readiness decisions."""

from dataclasses import replace
from pathlib import Path

import pytest

from agentctl.bootstrap import prereqs
from agentctl.bootstrap.pins import load
from agentctl.check.preconditions import (
    ToolchainReadiness,
    private_socket_path,
    socket_path_length,
    toolchain_preconditions,
)
from agentctl.check.prerequisites import (
    PrerequisiteReadiness,
    inspect_prerequisites,
    prerequisite_precondition,
)
from agentctl.hostfacts import HostContext, Prerequisite
from agentctl.process import Output, SpawnError
from agentctl.result import Err, Ok, Result
from tests.harness.oracle import Object, Store, Value, assert_oracle, read_homes
from tests.harness.oracle import load as oracle_load

pytestmark = pytest.mark.evidence("value")


def test_socket_path_length(tmp_path: Path) -> None:
    """P6 counts encoded bytes, accepts its bound and excludes Windows sockets."""
    assert socket_path_length(Path("/" + "a" * 99)) == ()
    assert socket_path_length(Path("/" + "a" * 100)), "socket length was not checked"
    assert socket_path_length(Path("/" + "é" * 50)), "socket length was not checked"
    expected = tmp_path / "mux/00000000" / "tmux-1234/default"
    assert private_socket_path(tmp_path, 1234) == expected


def _integer(value: Value) -> int:
    """Require integer capacity data independently of the subject."""
    assert isinstance(value, int)
    assert not isinstance(value, bool)
    return value


def _boolean(value: Value) -> bool:
    """Require explicit readiness observations rather than truthy strings."""
    assert isinstance(value, bool)
    return value


def test_toolchain_preconditions(root: Path) -> None:
    """Compare all readiness outcomes and remedies with independent oracle rows."""
    pins = load()
    assert isinstance(pins, Ok)
    store = oracle_load(
        root / "tests/oracles/toolchain_preconditions.toml", read_homes(root)
    )
    assert isinstance(store, Store)
    assert store.effective
    for row in store.effective:
        assert isinstance(row.inputs, Object)
        fields = dict(row.inputs.items)
        family, machine = fields["family"], fields["architecture"]
        assert isinstance(family, str)
        assert family in {"Linux", "Darwin", "Windows"}
        assert isinstance(machine, str)
        assert machine in {
            "x86_64",
            "aarch64",
            "arm64",
            "unsupported",
        }
        readiness = ToolchainReadiness(
            family,
            machine,
            _integer(fields["ghcup_free"]),
            _integer(fields["cache_free"]),
            _integer(fields["ghcup_required"]),
            _integer(fields["cache_required"]),
            _boolean(fields["pins_ready"]),
            _boolean(fields["downloads_reachable"]),
            _boolean(fields["hackage_reachable"]),
        )
        assert_oracle(
            lambda facts: toolchain_preconditions(facts, pins.value),
            readiness,
            row.expected,
            row_id="toolchain preconditions differ: " + row.identifier,
        )


def test_prerequisite_precondition(root: Path) -> None:
    """P9 needs ready probes or explicit non-interactive install capability."""
    store = oracle_load(root / "tests/oracles/prerequisites.toml", read_homes(root))
    assert isinstance(store, Store)
    compared = 0
    for row in store.effective:
        assert isinstance(row.inputs, Object)
        fields = dict(row.inputs.items)
        if fields["subject"] == "prerequisite-precondition":
            family = fields.get("family", "Linux")
            assert isinstance(family, str)
            assert family in {"Linux", "Darwin", "Windows"}
            readiness = PrerequisiteReadiness(
                ready=_boolean(fields["ready"]),
                assume_yes=_boolean(fields["assume_yes"]),
                is_root=_boolean(fields["is_root"]),
                passwordless=_boolean(fields["passwordless"]),
                family=family,
                verified_packages=_boolean(fields.get("verified_packages", True)),
            )
            assert_oracle(
                lambda facts: not prerequisite_precondition(facts),
                readiness,
                row.expected,
                row_id="prerequisite consent was bypassed: " + row.identifier,
            )
            compared += 1
    assert compared > 0


def _context(directory: Path) -> HostContext:
    """Construct readable distro metadata and keep every probe workspace private."""
    release = directory / "os-release"
    release.write_text('ID=ubuntu\nVERSION_ID="24.04"\n', encoding="utf-8")
    return HostContext(
        "Linux",
        "x86_64",
        directory / "home",
        directory / "cache",
        directory,
        (("PATH", ""),),
        is_root=False,
        interactive=False,
        assume_yes=False,
        os_release=release,
    )


def _observations(*, ready: bool) -> tuple[Prerequisite, ...]:
    """Use the independently fixed Linux probe vocabulary."""
    return (
        Prerequisite("compiler-and-gmp", ready=ready),
        Prerequisite("downloader", ready=True),
        Prerequisite("ca-certificates", ready=True),
        Prerequisite("make", ready=True),
    )


def test_prerequisite_inspection_consent_and_privilege(tmp_path: Path) -> None:
    """The live-edge coordinator only checks sudo -n and prints exact commands."""
    context = _context(tmp_path)
    attempted: list[tuple[str, ...]] = []

    def missing(
        _context: HostContext,
    ) -> Result[tuple[Prerequisite, ...], prereqs.PrerequisiteError]:
        return Ok(_observations(ready=False))

    def ready(
        _context: HostContext,
    ) -> Result[tuple[Prerequisite, ...], prereqs.PrerequisiteError]:
        return Ok(_observations(ready=True))

    def privilege(
        arguments: tuple[str, ...], _context: HostContext
    ) -> Result[Output, SpawnError]:
        attempted.append(arguments)
        return Ok(Output(0, "", ""))

    refused = inspect_prerequisites(context, missing, privilege)
    assert refused
    assert "P9 remedy: sudo apt-get update" in refused
    assert attempted == []
    consented = replace(context, assume_yes=True)
    assert inspect_prerequisites(consented, missing, privilege) == ()
    assert attempted == [("sudo", "-n", "true")]
    attempted.clear()
    assert (
        inspect_prerequisites(replace(consented, is_root=True), missing, privilege)
        == ()
    )
    assert attempted == []

    def unavailable(
        arguments: tuple[str, ...], _context: HostContext
    ) -> Result[Output, SpawnError]:
        attempted.append(arguments)
        return Err(SpawnError("no non-interactive privilege"))

    rejected = inspect_prerequisites(consented, missing, unavailable)
    assert "P9 remedy: sudo -n apt-get update" in rejected
    assert attempted == [("sudo", "-n", "true")]
    attempted.clear()
    context.os_release.unlink()
    assert inspect_prerequisites(context, ready, privilege) == ()
    assert attempted == []


def test_prerequisite_inspection_platforms_and_errors(tmp_path: Path) -> None:
    """Unknown platforms, incomplete probes and unverified sets never install."""
    context = _context(tmp_path)
    attempted: list[tuple[str, ...]] = []

    def missing(
        _context: HostContext,
    ) -> Result[tuple[Prerequisite, ...], prereqs.PrerequisiteError]:
        return Ok(_observations(ready=False))

    def empty(
        _context: HostContext,
    ) -> Result[tuple[Prerequisite, ...], prereqs.PrerequisiteError]:
        return Ok(())

    def broken(
        _context: HostContext,
    ) -> Result[tuple[Prerequisite, ...], prereqs.PrerequisiteError]:
        return Err(
            prereqs.PrerequisiteError("prerequisite-probe-failed", "controlled failure")
        )

    def privilege(
        arguments: tuple[str, ...], _context: HostContext
    ) -> Result[Output, SpawnError]:
        attempted.append(arguments)
        return Ok(Output(0, "", ""))

    assert inspect_prerequisites(
        replace(context, family="Other"), missing, privilege
    ) == ("P9: use Linux, macOS or Windows",)
    assert inspect_prerequisites(context, broken, privilege) == (
        "P9: controlled failure",
    )
    assert inspect_prerequisites(context, empty, privilege) == (
        "P9: the OS prerequisite probe was incomplete",
    )
    assert (
        inspect_prerequisites(replace(context, family="Windows"), empty, privilege)
        == ()
    )

    def xcode(
        _context: HostContext,
    ) -> Result[tuple[Prerequisite, ...], prereqs.PrerequisiteError]:
        return Ok((Prerequisite("xcode-clt", ready=False),))

    mac = inspect_prerequisites(
        replace(context, family="Darwin", assume_yes=True), xcode, privilege
    )
    assert "P9 remedy: xcode-select --install" in mac
    context.os_release.write_text("ID=arch\n", encoding="utf-8")
    arch = inspect_prerequisites(replace(context, assume_yes=True), missing, privilege)
    assert any("No verified package set" in line for line in arch)
    context.os_release.unlink()
    assert any(
        "cannot read os-release" in line
        for line in inspect_prerequisites(context, missing, privilege)
    )
    assert attempted == []
