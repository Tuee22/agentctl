# Copyright (c) 2026 agentctl contributors.
"""Constructed ghcup locations and platform spelling controls."""

import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal

import pytest

from agentctl.bootstrap.pins import Version, load
from agentctl.hostfacts import (
    Distribution,
    Ghcup,
    HostContext,
    architecture,
    discover_ghcup,
    effective_root,
    gather,
    ghcup_destination,
    read_distribution,
    read_record,
    reported_version,
)
from agentctl.process import Output, SpawnError
from agentctl.result import Err, Ok
from tests.harness.oracle import assert_oracle

type TestFamily = Literal["Linux", "Darwin", "Windows"]

pytestmark = pytest.mark.evidence("value")


def _executable(path: Path) -> Path:
    """Create an owned discovery candidate without ever executing its bytes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("owned discovery candidate", encoding="utf-8")
    path.chmod(0o755)
    return path.resolve()


def test_ghcup_discovery_order(tmp_path: Path) -> None:
    """Explicit prefix wins over PATH, which wins over the ordinary home default."""
    families: tuple[TestFamily, ...] = ("Linux", "Darwin", "Windows")
    for family in families:
        home = tmp_path / family / "home"
        prefix = tmp_path / family / "prefix"
        name = "ghcup.exe" if family == "Windows" else "ghcup"
        on_path = _executable(tmp_path / family / "path" / name)
        env = {"PATH": str(on_path.parent), "GHCUP_INSTALL_BASE_PREFIX": str(prefix)}
        configured = _executable(ghcup_destination(family, env, home))
        assert discover_ghcup(family, env, home) == configured, (
            "ghcup prefix was ignored"
        )
        configured.unlink()
        assert discover_ghcup(family, env, home) == on_path
        if family != "Windows":
            default = _executable(home / ".ghcup/bin/ghcup")
            on_path.unlink()
            assert discover_ghcup(family, env, home) == default
            default.unlink()
            assert discover_ghcup(family, env, home) is None
    assert ghcup_destination("Windows", {}, tmp_path) == Path("C:/ghcup/bin/ghcup.exe")
    for flag in ("", "0", "1"):
        env = {
            "GHCUP_USE_XDG_DIRS": flag,
            "GHCUP_INSTALL_BASE_PREFIX": str(tmp_path / "unused"),
            "PATH": "",
        }
        expected = _executable(tmp_path / ".local/bin/ghcup")
        assert ghcup_destination("Darwin", env, tmp_path) == expected
        assert discover_ghcup("Darwin", env, tmp_path) == expected
        expected.unlink()
        env["XDG_BIN_HOME"] = str(tmp_path / "xdg-bin")
        overridden = _executable(tmp_path / "xdg-bin/ghcup")
        assert discover_ghcup("Linux", env, tmp_path) == overridden
        overridden.unlink()


def test_architecture_spellings() -> None:
    """Each platform branch normalises known native spellings and refuses others."""
    families: tuple[TestFamily, ...] = ("Linux", "Darwin", "Windows")
    for family in families:
        for machine in ("AMD64", "x86_64"):
            assert architecture(family, machine) == "x86_64"
        for machine in ("aarch64", "ARM64"):
            assert architecture(family, machine) == (
                "aarch64" if family == "Linux" else "arm64"
            )
        assert architecture(family, "s390x") == "unsupported"


def _context(directory: Path, family: str = "Linux") -> HostContext:
    """Construct all host inputs under owned paths with an empty executable PATH."""
    directory.mkdir(parents=True, exist_ok=True)
    release = directory / "os-release"
    release.write_text('ID=ubuntu\nVERSION_ID="24.04"\n', encoding="utf-8")
    return HostContext(
        family,
        "AMD64",
        directory / "home",
        directory / "cache",
        directory,
        (("PATH", ""),),
        is_root=True,
        interactive=True,
        assume_yes=False,
        os_release=release,
    )


def _record(context: HostContext) -> tuple[str, str]:
    """Write the independently chosen absolute spellings of both recorded pins."""
    ghc, cabal = str(context.home / "tools/ghc"), str(context.home / "tools/cabal")
    context.cache.mkdir(parents=True, exist_ok=True)
    (context.cache / "toolchain-paths.toml").write_text(
        f"ghc = {json.dumps(ghc)}\ncabal = {json.dumps(cabal)}\n", encoding="utf-8"
    )
    return ghc, cabal


def test_gather_warm_host_stops_after_recorded_versions(tmp_path: Path) -> None:
    """Answering paths avoid discovery and an intentionally invalid os-release."""
    pins = load()
    assert isinstance(pins, Ok)
    context = _context(tmp_path)
    ghc, cabal = _record(context)
    context.os_release.write_text('ID="unterminated', encoding="utf-8")
    answers = {ghc: Version((9, 12, 4)), cabal: Version((3, 16, 1, 0))}
    observed: list[str] = []

    def probe(path: str, _context: HostContext) -> Version | None:
        observed.append(path)
        return answers.get(path)

    result = gather(context, pins.value, probe)
    assert isinstance(result, Ok)
    assert observed == [ghc, cabal], (
        "warm discovery performed another version observation"
    )
    assert (result.value.ghc, result.value.cabal) == (ghc, cabal)
    assert result.value.ghcup is None
    assert result.value.distribution is None
    assert result.value.is_root
    assert result.value.interactive
    assert not result.value.assume_yes


def test_gather_cold_and_partial_hosts(tmp_path: Path) -> None:
    """Cold hosts discover ghcup, preserve only answering pins and parse Linux ID."""
    pins = load()
    assert isinstance(pins, Ok)
    families: tuple[TestFamily, ...] = ("Linux", "Darwin", "Windows")
    observed: list[str] = []

    def probe(path: str, _context: HostContext) -> Version | None:
        observed.append(path)
        return Version((0, 1, 50, 2))

    for family in families:
        context = _context(tmp_path / family, family)
        env = {"PATH": "", "GHCUP_INSTALL_BASE_PREFIX": str(context.home / "prefix")}
        candidate = _executable(ghcup_destination(family, env, context.home))
        context = replace(context, environment=tuple(env.items()), assume_yes=True)
        observed.clear()
        result = gather(context, pins.value, probe)
        assert isinstance(result, Ok)
        assert result.value.ghcup == Ghcup(candidate, Version((0, 1, 50, 2)))
        assert observed == [str(candidate)]
        assert result.value.assume_yes
        assert result.value.distribution == (
            Distribution("ubuntu", 24) if family == "Linux" else None
        )
    context = _context(tmp_path / "partial")
    ghc, cabal = _record(context)
    answers = {ghc: Version((9, 12, 4)), cabal: Version((3, 14, 0, 0))}

    def partial_probe(path: str, _context: HostContext) -> Version | None:
        return answers.get(path)

    partial = gather(context, pins.value, partial_probe)
    assert isinstance(partial, Ok)
    assert partial.value.ghc == ghc
    assert partial.value.cabal is None
    assert partial.value.ghcup is None


def test_gather_refuses_invalid_inputs(tmp_path: Path) -> None:
    """Unsupported hosts and corrupt records fail before any version observation."""
    pins = load()
    assert isinstance(pins, Ok)
    context = _context(tmp_path)
    observed: list[str] = []

    def probe(path: str, _context: HostContext) -> Version | None:
        observed.append(path)
        return None

    for invalid in (
        replace(context, family="Other"),
        replace(context, machine="s390x"),
        replace(context, family="Windows", machine="ARM64"),
    ):
        assert isinstance(gather(invalid, pins.value, probe), Err)
    context.cache.mkdir()
    record = context.cache / "toolchain-paths.toml"
    record.write_text("invalid", encoding="utf-8")
    assert isinstance(gather(context, pins.value, probe), Err)
    record.unlink()
    context.os_release.unlink()
    assert isinstance(gather(context, pins.value, probe), Err)
    assert observed == []


def test_record_boundary(tmp_path: Path) -> None:
    """Reject non-absolute, ill-typed, malformed and unreadable cache records."""
    context = _context(tmp_path)
    assert read_record(context.cache) == Ok((None, None))
    paths = _record(context)
    assert read_record(context.cache) == Ok(paths)
    record = context.cache / "toolchain-paths.toml"
    for text in (
        'ghc="relative"\ncabal="relative"',
        "ghc=1\ncabal=2",
        'ghc="/absolute"\ncabal=2',
        'ghc="/absolute"\ncabal="relative"',
        "[extra]",
        "[invalid",
    ):
        record.write_text(text, encoding="utf-8")
        assert isinstance(read_record(context.cache), Err)
    record.write_bytes(b"\xff")
    assert isinstance(read_record(context.cache), Err)
    record.unlink()
    record.mkdir()
    assert isinstance(read_record(context.cache), Err)


def test_distribution_boundary(tmp_path: Path) -> None:
    """Read supported distro identities and reject only malformed input files."""
    release = tmp_path / "os-release"
    for text, expected in (
        (
            'NAME="A descriptive name"\nID="ubuntu"\nVERSION_ID="24.04" # comment',
            Distribution("ubuntu", 24),
        ),
        ("ID='debian'\nVERSION_ID=13", Distribution("debian", 13)),
        ("ID=fedora\nVERSION_ID=43", Distribution("fedora", 43)),
        ("ID=arch", Distribution("arch", None)),
        ("ID=other\nVERSION_ID=rolling", Distribution("other", None)),
        ('ID=ubuntu\nVERSION_ID=""', Distribution("ubuntu", None)),
        ('ID=ubuntu\nVERSION_ID="\uff11"', Distribution("ubuntu", None)),
        ("ID=other\nVERSION_ID=1234567890", Distribution("other", None)),
    ):
        release.write_text(text, encoding="utf-8")
        assert read_distribution(release) == Ok(expected)
    for text in ('ID="unterminated', "ID=", "ID=ubuntu debian", "VERSION_ID=24"):
        release.write_text(text, encoding="utf-8")
        assert isinstance(read_distribution(release), Err)
    release.write_bytes(b"\xff")
    assert isinstance(read_distribution(release), Err)
    release.unlink()
    assert isinstance(read_distribution(release), Err)
    for distribution, manager in (
        (Distribution("ubuntu", 24), "apt"),
        (Distribution("debian", 13), "apt"),
        (Distribution("fedora", 43), "dnf"),
        (Distribution("arch", None), "pacman"),
        (Distribution("other", None), "none"),
    ):
        assert_oracle(lambda value: value.manager, distribution, manager)


@dataclass(frozen=True, slots=True)
class Identity:
    """A constructed native-identity observation for privilege decisions."""

    uid: int

    def geteuid(self) -> int:
        """Supply the explicit uid without touching process privilege."""
        return self.uid


def test_privilege_and_version_values() -> None:
    """No Windows sudo action and no failed or malformed version count as ready."""
    assert effective_root("Linux", Identity(0))
    assert not effective_root("Darwin", Identity(1000))
    assert not effective_root("Windows", Identity(0))
    assert not effective_root("Linux", object())
    for output in (
        Err(SpawnError("not executable")),
        Ok(Output(1, "9.12.4", "failure")),
        Ok(Output(0, "invalid", "")),
    ):
        assert reported_version(output) is None
    assert reported_version(Ok(Output(0, "9.12.4\n", ""))) == Version((9, 12, 4))
