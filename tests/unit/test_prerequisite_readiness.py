# Copyright (c) 2026 agentctl contributors.
"""Bootstrap prerequisite inspection uses explicit, non-interactive probes."""

from dataclasses import replace
from pathlib import Path

import pytest

from agentctl.bootstrap import prereqs
from agentctl.check.prerequisites import inspect_prerequisites
from agentctl.hostfacts import HostContext, Prerequisite
from agentctl.process import Output, SpawnError
from agentctl.result import Err, Ok, Result

pytestmark = pytest.mark.evidence("value")


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
