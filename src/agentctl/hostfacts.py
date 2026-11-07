# Copyright (c) 2026 agentctl contributors.
"""Immutable host observations and environment-aware ghcup discovery."""

import os
import platform
import shlex
import sys
import tomllib
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal, Protocol, runtime_checkable

from agentctl.bootstrap.pins import Architecture, Pins, Version, asset_for, version
from agentctl.paths import Family
from agentctl.process import Output, SpawnError, run
from agentctl.result import Err, Ok, Result

MAX_RELEASE_DIGITS = 9

type DistributionName = Literal["ubuntu", "debian", "fedora", "arch", "other"]
type PackageManager = Literal["apt", "dnf", "pacman", "none"]
type PrerequisiteName = Literal[
    "compiler-and-gmp", "downloader", "ca-certificates", "make", "xcode-clt"
]


@dataclass(frozen=True, slots=True)
class Prerequisite:
    """One named prerequisite observation, never inferred from distro alone."""

    name: PrerequisiteName
    ready: bool


def expected_probes(family: Family) -> tuple[PrerequisiteName, ...]:
    """Return the required observation vocabulary for each supported OS."""
    names: dict[Family, tuple[PrerequisiteName, ...]] = {
        "Linux": ("compiler-and-gmp", "downloader", "ca-certificates", "make"),
        "Darwin": ("xcode-clt",),
        "Windows": (),
    }
    return names[family]


@dataclass(frozen=True, slots=True)
class Distribution:
    """A parsed Linux distribution and its numeric major release, when present."""

    name: DistributionName
    major: int | None

    @property
    def manager(self) -> PackageManager:
        """Name the distro's manager without assuming it has verified packages."""
        managers: dict[DistributionName, PackageManager] = {
            "ubuntu": "apt",
            "debian": "apt",
            "fedora": "dnf",
            "arch": "pacman",
            "other": "none",
        }
        return managers[self.name]


@dataclass(frozen=True, slots=True)
class HostContext:
    """Read-only system inputs captured once before bootstrap observation."""

    family: str
    machine: str
    home: Path
    cache: Path
    cwd: Path
    environment: tuple[tuple[str, str], ...]
    is_root: bool
    interactive: bool
    assume_yes: bool
    os_release: Path = Path("/etc/os-release")


@dataclass(frozen=True, slots=True)
class FactsError:
    """A malformed record or unsupported host with an actionable diagnosis."""

    message: str


@runtime_checkable
class PosixIdentity(Protocol):
    """The optional standard-library effective-uid observation."""

    def geteuid(self) -> int:
        """Return the effective user id without invoking another process."""
        ...


def effective_root(family: str, identity: object) -> bool:
    """Observe Unix privilege while treating Windows as having no sudo action."""
    return (
        family != "Windows"
        and isinstance(identity, PosixIdentity)
        and identity.geteuid() == 0
    )


def current(cache: Path, *, assume_yes: bool = False) -> HostContext:
    """Capture native identity and terminal facts without spawning uname."""
    family = platform.system()
    return HostContext(
        family,
        platform.machine(),
        Path.home(),
        cache,
        Path.cwd(),
        tuple(os.environ.items()),
        effective_root(family, os),
        sys.stdin.isatty() and sys.stderr.isatty(),
        assume_yes,
    )


@dataclass(frozen=True, slots=True)
class Ghcup:
    """An existing executable and its answering version, or an unanswering one."""

    path: Path
    version: Version | None


@dataclass(frozen=True, slots=True)
class HostFacts:
    """The observations needed for an ordered, effect-free bootstrap decision."""

    family: Family
    architecture: Architecture
    ghcup_destination: Path
    ghcup: Ghcup | None
    ghc: str | None
    cabal: str | None
    distribution: Distribution | None = None
    is_root: bool = False
    interactive: bool = False
    assume_yes: bool = False
    prerequisites: tuple[Prerequisite, ...] | None = None


def architecture(family: Family, machine: str) -> Architecture:
    """Normalise native machine spellings to the platform table's vocabulary."""
    if machine.casefold() in {"amd64", "x86_64"}:
        return "x86_64"
    if machine.casefold() in {"aarch64", "arm64"}:
        return "aarch64" if family == "Linux" else "arm64"
    return "unsupported"


def ghcup_destination(family: Family, env: Mapping[str, str], home: Path) -> Path:
    """Apply ghcup's prefix and XDG locations before the platform default."""
    if family == "Windows":
        return Path(env.get("GHCUP_INSTALL_BASE_PREFIX", "C:/")) / "ghcup/bin/ghcup.exe"
    if "GHCUP_USE_XDG_DIRS" in env:
        return Path(env.get("XDG_BIN_HOME", str(home / ".local/bin"))) / "ghcup"
    return Path(env.get("GHCUP_INSTALL_BASE_PREFIX", str(home))) / ".ghcup/bin/ghcup"


def discover_ghcup(family: Family, env: Mapping[str, str], home: Path) -> Path | None:
    """Prefer an explicit environment location, then PATH, then the default."""
    destination = ghcup_destination(family, env, home)
    explicit = "GHCUP_INSTALL_BASE_PREFIX" in env or (
        family != "Windows" and "GHCUP_USE_XDG_DIRS" in env
    )
    if explicit and destination.is_file():
        return destination.resolve()
    name = "ghcup.exe" if family == "Windows" else "ghcup"
    found = next(
        (
            candidate
            for directory in env.get("PATH", "").split(os.pathsep)
            if directory
            for candidate in (Path(directory) / name,)
            if candidate.is_file() and os.access(candidate, os.X_OK)
        ),
        None,
    )
    if found is not None:
        return found.resolve()
    default = ghcup_destination(family, {}, home)
    return default.resolve() if default.is_file() else None


def read_record(cache: Path) -> Result[tuple[str | None, str | None], FactsError]:
    """Read both absolute tool paths, preserving their original spelling."""
    try:
        data = tomllib.loads(
            (cache / "toolchain-paths.toml").read_text(encoding="utf-8")
        )
    except FileNotFoundError:
        return Ok((None, None))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        return Err(FactsError(f"cannot read toolchain path record: {exc}"))
    if set(data) != {"ghc", "cabal"}:
        return Err(
            FactsError(
                "toolchain path record requires ghc and cabal; "
                "remove the invalid cache record"
            )
        )
    ghc, cabal = data["ghc"], data["cabal"]
    if (
        not isinstance(ghc, str)
        or not isinstance(cabal, str)
        or not Path(ghc).is_absolute()
        or not Path(cabal).is_absolute()
    ):
        return Err(
            FactsError(
                "toolchain paths must be absolute; remove the invalid cache record"
            )
        )
    return Ok((ghc, cabal))


def read_distribution(path: Path) -> Result[Distribution, FactsError]:
    """Read only os-release identity fields with their specified shell quoting."""
    try:
        fields: dict[str, str] = {}
        for line in path.read_text(encoding="utf-8").splitlines():
            key, separator, raw = line.partition("=")
            if separator and key in {"ID", "VERSION_ID"}:
                tokens = shlex.split(raw, comments=True)
                if len(tokens) != 1:
                    return Err(FactsError("invalid os-release identity field"))
                fields[key] = tokens[0]
    except (OSError, UnicodeError, ValueError) as exc:
        return Err(FactsError(f"cannot read os-release: {exc}"))
    if "ID" not in fields:
        return Err(FactsError("os-release has no ID"))
    name = fields["ID"]
    major = fields.get("VERSION_ID", "").partition(".")[0]
    number = (
        int(major)
        if major.isascii() and major.isdecimal() and len(major) <= MAX_RELEASE_DIGITS
        else None
    )
    return Ok(
        Distribution(
            name if name in {"ubuntu", "debian", "fedora", "arch"} else "other", number
        )
    )


def reported_version(result: Result[Output, SpawnError]) -> Version | None:
    """Treat a failed process or non-numeric answer as an unanswering tool."""
    if isinstance(result, Err) or result.value.code != 0:
        return None
    return version(result.value.stdout.strip())


def numeric_version(executable: str, context: HostContext) -> Version | None:
    """Run the absolute executable read-only with updating disabled and a deadline."""
    return reported_version(
        run(
            [executable, "--numeric-version"],
            cwd=context.cwd,
            env={**dict(context.environment), "GHCUP_SKIP_UPDATE_CHECK": "1"},
            timeout=10,
        )
    )


type VersionProbe = Callable[[str, HostContext], Version | None]


def _answering(
    path: str | None, pin: Version, context: HostContext, probe: VersionProbe
) -> str | None:
    """Keep a recorded path only when that exact executable answers at its pin."""
    return path if path is not None and probe(path, context) == pin else None


def gather(
    context: HostContext, pins: Pins, probe: VersionProbe = numeric_version
) -> Result[HostFacts, FactsError]:
    """Observe cached pins first and stop before ghcup or OS probes on warm hosts."""
    family = context.family
    if family not in {"Linux", "Darwin", "Windows"}:
        return Err(FactsError(f"unsupported OS {family}; use Linux, macOS or Windows"))
    machine = architecture(family, context.machine)
    if asset_for(pins, family, machine) is None:
        return Err(
            FactsError(
                "P10: no GHC bindist for this platform; "
                "use a supported OS and architecture"
            )
        )
    recorded = read_record(context.cache)
    if isinstance(recorded, Err):
        return recorded
    ghc = _answering(recorded.value[0], pins.ghc, context, probe)
    cabal = _answering(recorded.value[1], pins.cabal, context, probe)
    env = dict(context.environment)
    facts = HostFacts(
        family,
        machine,
        ghcup_destination(family, env, context.home).absolute(),
        None,
        ghc,
        cabal,
        is_root=context.is_root,
        interactive=context.interactive,
        assume_yes=context.assume_yes,
    )
    if ghc is not None and cabal is not None:
        return Ok(facts)
    if family == "Linux":
        distribution = read_distribution(context.os_release)
        if isinstance(distribution, Err):
            return distribution
        facts = replace(facts, distribution=distribution.value)
    found = discover_ghcup(family, env, context.home)
    return Ok(
        replace(
            facts,
            ghcup=None if found is None else Ghcup(found, probe(str(found), context)),
        )
    )
