# Copyright (c) 2026 agentctl contributors.
"""Verified prerequisite package proposals and explicit consent decisions."""

import os
import shlex
import shutil
import ssl
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal

import click

from agentctl.hostfacts import (
    Distribution,
    HostContext,
    HostFacts,
    Prerequisite,
    PrerequisiteName,
    expected_probes,
)
from agentctl.paths import Family
from agentctl.process import Output, SpawnError, run
from agentctl.result import Err, Ok, Result

APT_PACKAGES = (
    "build-essential",
    "curl",
    "libgmp-dev",
    "libgmp10",
    "libncurses-dev",
    "pkg-config",
)
FEDORA_PACKAGES = (
    "gcc",
    "gcc-c++",
    "gmp",
    "gmp-devel",
    "make",
    "ncurses",
    "ncurses-compat-libs",
    "xz",
    "perl",
)
GENERIC_DEPENDENCIES = (
    "curl",
    "g++",
    "gcc",
    "gmp",
    "make",
    "ncurses",
    "realpath",
    "xz-utils",
    "pkg-config",
)
UBUNTU_MINIMUM_MAJOR = 23
DEBIAN_MINIMUM_MAJOR = 13
C_SOURCE = "int main(void) { return 0; }\n"


@dataclass(frozen=True, slots=True)
class PackageInstall:
    """One verified package set and its ordered, shell-free command vectors."""

    packages: tuple[str, ...]
    commands: tuple[tuple[str, ...], ...]


@dataclass(frozen=True, slots=True)
class XcodeInstall:
    """A request to start Apple's Command Line Tools installer."""

    command: tuple[str, ...] = ("xcode-select", "--install")


type PrerequisiteAction = PackageInstall | XcodeInstall


@dataclass(frozen=True, slots=True)
class PackageHost:
    """Only the platform and privilege inputs needed to propose OS commands."""

    family: Family
    distribution: Distribution | None
    is_root: bool
    assume_yes: bool


@dataclass(frozen=True, slots=True)
class PrerequisiteError:
    """A refused or incomplete prerequisite step with a concrete remedy."""

    reason: Literal[
        "prerequisites-unverified",
        "prerequisites-unobserved",
        "prerequisite-consent-required",
        "prerequisite-declined",
        "prerequisite-install-failed",
        "prerequisite-still-missing",
        "prerequisite-probe-failed",
        "xcode-pending",
    ]
    remedy: str


def consented(*, assume_yes: bool, accepted: bool) -> bool:
    """Keep an explicit flag or affirmative prompt answer as the only consent."""
    return assume_yes or accepted


def affirmative(value: object) -> bool:
    """Treat every response except y or yes as a decline, without a retry prompt."""
    return isinstance(value, str) and value.strip().casefold() in {"y", "yes"}


def packages(
    distribution: Distribution | None,
) -> Result[tuple[str, ...], PrerequisiteError]:
    """Select only the package sets verified for this GHC version."""
    if distribution is not None:
        if (
            distribution.name == "ubuntu"
            and distribution.major is not None
            and distribution.major >= UBUNTU_MINIMUM_MAJOR
        ):
            return Ok(APT_PACKAGES)
        if (
            distribution.name == "debian"
            and distribution.major is not None
            and distribution.major >= DEBIAN_MINIMUM_MAJOR
        ):
            return Ok((*APT_PACKAGES, "libncurses6", "libtinfo6"))
        if distribution.name == "fedora":
            return Ok(FEDORA_PACKAGES)
    return Err(
        PrerequisiteError(
            "prerequisites-unverified",
            "No verified package set exists for this host; GHC needs "
            + ", ".join(GENERIC_DEPENDENCIES),
        )
    )


def proposal(
    facts: HostFacts | PackageHost,
) -> Result[tuple[PrerequisiteAction, ...], PrerequisiteError]:
    """Render a verified OS action while keeping consent separate from planning."""
    if facts.family == "Windows":
        return Ok(())
    if facts.family == "Darwin":
        return Ok((XcodeInstall(),))
    selected = packages(facts.distribution)
    if isinstance(selected, Err):
        return selected
    privilege = (
        () if facts.is_root else (("sudo", "-n") if facts.assume_yes else ("sudo",))
    )
    commands = (
        (
            (*privilege, "apt-get", "update"),
            (*privilege, "apt-get", "install", "-y", *selected.value),
        )
        if facts.distribution is not None and facts.distribution.manager == "apt"
        else ((*privilege, "dnf", "install", "-y", *selected.value),)
    )
    return Ok((PackageInstall(selected.value, commands),))


def commands_of(action: PrerequisiteAction) -> tuple[tuple[str, ...], ...]:
    """Expose each concrete argv for display and the single-command adapter."""
    if isinstance(action, PackageInstall):
        return action.commands
    return (action.command,)


def command_lines(action: PrerequisiteAction) -> tuple[str, ...]:
    """Format fixed argv for display while keeping execution shell-free."""
    return tuple(shlex.join(command) for command in commands_of(action))


def describe_missing(
    family: Family, observations: tuple[Prerequisite, ...] | None
) -> str:
    """Describe only failed observations, using names meaningful to a user."""
    names = (
        expected_probes(family)
        if observations is None
        else tuple(item.name for item in observations if not item.ready)
    )
    labels: dict[PrerequisiteName, str] = {
        "compiler-and-gmp": "the C compiler and linker with GMP",
        "downloader": "curl or wget",
        "ca-certificates": "CA certificates",
        "make": "make",
        "xcode-clt": "the Xcode Command Line Tools",
    }
    return ", ".join(labels[name] for name in names)


def complete(family: str, observations: tuple[Prerequisite, ...]) -> bool:
    """Reject missing, duplicate or reordered probe results at the boundary."""
    if family not in {"Linux", "Darwin", "Windows"}:
        return False
    return tuple(item.name for item in observations) == expected_probes(family)


def plan_actions(
    facts: HostFacts,
) -> Result[tuple[PrerequisiteAction, ...], PrerequisiteError]:
    """Require complete probes and consent eligibility before planning installation."""
    expected = expected_probes(facts.family)
    if not expected:
        return Ok(())
    if facts.prerequisites is None or not complete(facts.family, facts.prerequisites):
        return Err(
            PrerequisiteError(
                "prerequisites-unobserved",
                "Probe the OS prerequisites before provisioning",
            )
        )
    if all(probe.ready for probe in facts.prerequisites):
        return Ok(())
    selected = proposal(facts)
    if isinstance(selected, Err):
        return Err(
            PrerequisiteError(
                selected.error.reason,
                "GHC needs "
                + describe_missing(facts.family, facts.prerequisites)
                + "; "
                + selected.error.remedy,
            )
        )
    if (
        not consented(assume_yes=facts.assume_yes, accepted=False)
        and not facts.interactive
    ):
        commands = tuple(
            command for action in selected.value for command in commands_of(action)
        )
        return Err(
            PrerequisiteError(
                "prerequisite-consent-required",
                "GHC needs "
                + describe_missing(facts.family, facts.prerequisites)
                + "; run "
                + "; ".join(shlex.join(command) for command in commands)
                + "; or use agentctl --assume-yes",
            )
        )
    return selected


type Invoke = Callable[[tuple[str, ...], HostContext], Result[Output, SpawnError]]


def invoke(
    arguments: tuple[str, ...], context: HostContext
) -> Result[Output, SpawnError]:
    """Use the sole process boundary with bounded, UTF-8, shell-free execution."""
    return run(
        list(arguments), cwd=context.cwd, env=dict(context.environment), timeout=10
    )


def successful(result: Result[Output, SpawnError]) -> bool:
    """Interpret only a successfully launched, zero-exit command as a ready probe."""
    return isinstance(result, Ok) and result.value.code == 0


def _private_file(path: Path, contents: str) -> None:
    """Create a probe input or output with its final private mode."""
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        stream.write(contents)


def link_gmp(
    compiler: str, context: HostContext, execute: Invoke = invoke
) -> Result[bool, PrerequisiteError]:
    """Link an owned one-line program against GMP, then remove every artifact."""
    try:
        context.cache.mkdir(mode=0o700, parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix="prerequisite-", dir=context.cache
        ) as temporary:
            directory = Path(temporary)
            source, output = directory / "probe.c", directory / "probe-output"
            _private_file(source, C_SOURCE)
            _private_file(output, "")
            result = execute(
                (compiler, str(source), "-lgmp", "-o", str(output)), context
            )
    except OSError as exc:
        return Err(
            PrerequisiteError(
                "prerequisite-probe-failed",
                f"Cannot create the private compiler probe: {exc}",
            )
        )
    return Ok(successful(result))


def certificate_store(paths: tuple[str | None, str | None]) -> bool:
    """Require the CA file or directory reported by the SSL configuration to exist."""
    file, directory = paths
    return (file is not None and Path(file).is_file()) or (
        directory is not None and Path(directory).is_dir()
    )


def probe(
    context: HostContext,
    execute: Invoke = invoke,
    certificates: tuple[str | None, str | None] | None = None,
) -> Result[tuple[Prerequisite, ...], PrerequisiteError]:
    """Measure the OS-specific requirements without invoking any installer."""
    family = context.family
    if family not in {"Linux", "Darwin", "Windows"}:
        return Err(
            PrerequisiteError("prerequisites-unverified", "Use Linux, macOS or Windows")
        )
    if family == "Windows":
        return Ok(())
    env = dict(context.environment)
    search = env.get("PATH", "")
    if family == "Darwin":
        xcode = shutil.which("xcode-select", path=search)
        ready = xcode is not None and successful(execute((xcode, "-p"), context))
        return Ok((Prerequisite("xcode-clt", ready),))
    compiler = shutil.which("cc", path=search)
    compiled = (
        Ok(value=False) if compiler is None else link_gmp(compiler, context, execute)
    )
    if isinstance(compiled, Err):
        return compiled
    default = ssl.get_default_verify_paths()
    paths = (default.cafile, default.capath) if certificates is None else certificates
    return Ok(
        (
            Prerequisite("compiler-and-gmp", compiled.value),
            Prerequisite(
                "downloader",
                shutil.which("curl", path=search) is not None
                or shutil.which("wget", path=search) is not None,
            ),
            Prerequisite("ca-certificates", certificate_store(paths)),
            Prerequisite("make", shutil.which("make", path=search) is not None),
        )
    )


@dataclass(frozen=True, slots=True)
class GrantedPrerequisites:
    """A fixed prerequisite action after explicit consent has been obtained."""

    action: PrerequisiteAction


def authorize(
    action: PrerequisiteAction, facts: HostFacts
) -> Result[GrantedPrerequisites, PrerequisiteError]:
    """Display exact commands and ask only when both input and stderr are terminals."""
    click.echo(
        "agentctl: GHC needs build tools this host lacks: "
        + describe_missing(facts.family, facts.prerequisites)
        + ".",
        err=True,
    )
    click.echo("agentctl: with your consent agentctl runs:", err=True)
    for command in command_lines(action):
        click.echo("agentctl:   " + command, err=True)
    if not facts.interactive and not facts.assume_yes:
        return Err(
            PrerequisiteError(
                "prerequisite-consent-required",
                "Non-interactive installation needs --assume-yes; "
                "run the commands above yourself, then retry",
            )
        )
    accepted = (
        False
        if facts.assume_yes
        else affirmative(
            click.prompt(
                "agentctl: run them now? [y/N]",
                default="",
                show_default=False,
                prompt_suffix=" ",
                err=True,
            )
        )
    )
    if not consented(assume_yes=facts.assume_yes, accepted=accepted):
        return Err(
            PrerequisiteError(
                "prerequisite-declined",
                "nothing was installed; run the commands above yourself, "
                "then run agentctl again",
            )
        )
    return Ok(GrantedPrerequisites(action))


def install_command(
    arguments: tuple[str, ...], context: HostContext
) -> Result[Output, SpawnError]:
    """Run one approved command with an installation deadline, never through a shell."""
    return run(
        list(arguments), cwd=context.cwd, env=dict(context.environment), timeout=600
    )


type Examine = Callable[
    [HostContext], Result[tuple[Prerequisite, ...], PrerequisiteError]
]


def apply(
    granted: GrantedPrerequisites,
    context: HostContext,
    examine: Examine = probe,
    attempt: Invoke = install_command,
) -> Result[tuple[Prerequisite, ...], PrerequisiteError]:
    """Stop at the first failed command, then re-probe once rather than reinstalling."""
    for command in commands_of(granted.action):
        if not successful(attempt(command, context)):
            return Err(
                PrerequisiteError(
                    "prerequisite-install-failed",
                    "The prerequisite command failed; "
                    "run the printed commands yourself, then retry",
                )
            )
    if isinstance(granted.action, XcodeInstall):
        return Err(
            PrerequisiteError(
                "xcode-pending",
                "Finish the Xcode Command Line Tools dialog, then run agentctl again",
            )
        )
    observed = examine(context)
    if isinstance(observed, Err):
        return observed
    if not complete(context.family, observed.value):
        return Err(
            PrerequisiteError(
                "prerequisite-probe-failed",
                "The post-install prerequisite probe was incomplete",
            )
        )
    failed = tuple(item.name for item in observed.value if not item.ready)
    if failed:
        return Err(
            PrerequisiteError(
                "prerequisite-still-missing",
                "Prerequisites still fail after installation: " + ", ".join(failed),
            )
        )
    return observed


def ensure(
    action: PrerequisiteAction, facts: HostFacts, context: HostContext
) -> Result[tuple[Prerequisite, ...], PrerequisiteError]:
    """Compose consent and application without a test-specific execution path."""
    granted = authorize(action, facts)
    return granted if isinstance(granted, Err) else apply(granted.value, context)


def observe(
    facts: HostFacts, context: HostContext, examine: Examine = probe
) -> Result[HostFacts, PrerequisiteError]:
    """Complete a cold host's frozen observations while leaving warm pins alone."""
    if facts.ghc is not None and facts.cabal is not None:
        return Ok(facts)
    measured = examine(context)
    if isinstance(measured, Err):
        return measured
    if not complete(facts.family, measured.value):
        return Err(
            PrerequisiteError(
                "prerequisite-probe-failed", "The OS prerequisite probe was incomplete"
            )
        )
    return Ok(replace(facts, prerequisites=measured.value))
