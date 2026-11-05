# Copyright (c) 2026 agentctl contributors.
"""Apply the provisioning plan without changing the user's default selections."""

import hashlib
import json
import os
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal

from agentctl import hostfacts
from agentctl.bootstrap import ghcup, prereqs
from agentctl.bootstrap.pins import Pins, Version
from agentctl.bootstrap.plan import (
    Action,
    DownloadGhcup,
    GhcupCommand,
    Refusal,
    provision,
)
from agentctl.hostfacts import HostContext, HostFacts, numeric_version
from agentctl.result import Err, Ok, Result


@dataclass(frozen=True, slots=True)
class Toolchain:
    """Verified absolute executable strings, preserved exactly as resolved."""

    ghc: str
    cabal: str


@dataclass(frozen=True, slots=True)
class ToolchainError:
    """A provisioning or selection-preservation failure with its concrete remedy."""

    message: str


def command(action: GhcupCommand, context: HostContext) -> Result[str, ToolchainError]:
    """Execute the planned argv through the sole process adapter."""
    result = prereqs.install_command(
        (str(action.executable), *action.arguments),
        ghcup_context(context),
    )
    if isinstance(result, Err):
        return Err(ToolchainError(result.error.message))
    if result.value.code:
        return Err(
            ToolchainError(
                f"ghcup {' '.join(action.arguments)} failed ({result.value.code}): "
                + result.value.stderr
            )
        )
    return Ok(result.value.stdout.rstrip("\r\n"))


def ghcup_context(context: HostContext) -> HostContext:
    """Set the required update-check opt-out without changing inherited inputs."""
    return replace(
        context,
        environment=tuple(
            {**dict(context.environment), "GHCUP_SKIP_UPDATE_CHECK": "1"}.items()
        ),
    )


type Invoke = Callable[[GhcupCommand, HostContext], Result[str, ToolchainError]]
type Prepare = Callable[
    [prereqs.PrerequisiteAction, HostFacts, HostContext],
    Result[tuple[hostfacts.Prerequisite, ...], prereqs.PrerequisiteError],
]


@dataclass(frozen=True, slots=True)
class Actuation:
    """Explicit command and prerequisite adapters for the plan interpreter."""

    invoke: Invoke = command
    prepare: Prepare = prereqs.ensure


DEFAULT_ACTUATION = Actuation()


def resolved(
    path: str, pin: Version, context: HostContext
) -> Result[str, ToolchainError]:
    """Verify the absolute printed path without normalising its spelling."""
    if not Path(path).is_absolute():
        return Err(ToolchainError("ghcup whereis did not return an absolute path"))
    if numeric_version(path, context) != pin:
        return Err(
            ToolchainError(f"{path} must answer --numeric-version with {pin.text}")
        )
    return Ok(path)


def record(tools: Toolchain, cache: Path) -> Result[Toolchain, ToolchainError]:
    """Atomically publish a private path record only after both pins are verified."""
    try:
        cache.mkdir(mode=0o700, parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".toolchain-", dir=cache) as temporary:
            staged = Path(temporary) / "paths.toml"
            descriptor = os.open(staged, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                for name, path in (("ghc", tools.ghc), ("cabal", tools.cabal)):
                    stream.write(
                        name + " = " + json.dumps(path, ensure_ascii=False) + "\n"
                    )
            staged.replace(cache / "toolchain-paths.toml")
    except OSError as exc:
        return Err(ToolchainError(f"Cannot record verified toolchain paths: {exc}"))
    return Ok(tools)


def apply_command(
    action: GhcupCommand,
    pins: Pins,
    context: HostContext,
    paths: tuple[str | None, str | None],
    invoke: Invoke,
) -> Result[tuple[str | None, str | None], ToolchainError]:
    """Resolve and verify whereis output while keeping install output informational."""
    answer = invoke(action, context)
    if isinstance(answer, Err):
        return answer
    if action.arguments[0] != "whereis":
        return Ok(paths)
    ghc = action.arguments[1] == "ghc"
    verified = resolved(answer.value, pins.ghc if ghc else pins.cabal, context)
    if isinstance(verified, Err):
        return verified
    return Ok((verified.value, paths[1]) if ghc else (paths[0], verified.value))


def apply(
    facts: HostFacts,
    pins: Pins,
    context: HostContext,
    actions: tuple[Action, ...],
    edge: Actuation = DEFAULT_ACTUATION,
) -> Result[Toolchain, ToolchainError]:
    """Apply each action once, stop on failure and record only a complete toolchain."""
    paths = (facts.ghc, facts.cabal)
    for action in actions:
        if isinstance(action, DownloadGhcup):
            downloaded = ghcup.provide(facts, pins)
            if isinstance(downloaded, Err):
                return Err(ToolchainError(downloaded.error.message))
        elif isinstance(action, (prereqs.PackageInstall, prereqs.XcodeInstall)):
            installed = edge.prepare(action, facts, context)
            if isinstance(installed, Err):
                return Err(ToolchainError(installed.error.remedy))
        else:
            answered = apply_command(action, pins, context, paths, edge.invoke)
            if isinstance(answered, Err):
                return answered
            paths = answered.value
    ghc_path, cabal_path = paths
    if ghc_path is None or cabal_path is None:
        return Err(
            ToolchainError("The provisioning plan did not resolve both pinned tools")
        )
    return record(Toolchain(ghc_path, cabal_path), context.cache)


def planning_failure(
    error: Refusal | prereqs.PrerequisiteError, facts: HostFacts, pins: Pins
) -> ToolchainError:
    """Retain the observed executable and version when presenting a refusal."""
    if isinstance(error, prereqs.PrerequisiteError):
        return ToolchainError(error.remedy)
    existing = facts.ghcup
    detail = (
        "absent"
        if existing is None
        else f"{existing.path} reports {existing.version.text}"
        if existing.version is not None
        else f"{existing.path} did not answer --numeric-version"
    )
    return ToolchainError(
        f"Cannot provision {facts.family}/{facts.architecture}: {error.reason}; "
        f"ghcup {detail}; reuse floor {pins.ghcup_floor.text}; {error.remedy}"
    )


def ensure(
    context: HostContext,
    pins: Pins,
    examine: prereqs.Examine = prereqs.probe,
    *,
    inspect_versions: hostfacts.VersionProbe = numeric_version,
) -> Result[Toolchain, ToolchainError]:
    """Gather once, plan once and leave a warm run at exactly its two version checks."""
    gathered = hostfacts.gather(context, pins, inspect_versions)
    if isinstance(gathered, Err):
        return Err(ToolchainError(gathered.error.message))
    facts = gathered.value
    if facts.ghc is not None and facts.cabal is not None:
        return Ok(Toolchain(facts.ghc, facts.cabal))
    observed = prereqs.observe(facts, context, examine)
    if isinstance(observed, Err):
        return Err(ToolchainError(observed.error.remedy))
    planned = provision(observed.value, pins)
    if isinstance(planned, Err):
        return Err(planning_failure(planned.error, observed.value, pins))
    return apply(observed.value, pins, context, planned.value)


@dataclass(frozen=True, slots=True)
class Default:
    """One unversioned entry's link target, file digest or absence."""

    path: Path
    kind: Literal["link", "file", "absent"]
    value: str


def defaults(context: HostContext) -> Result[tuple[Default, ...], ToolchainError]:
    """Read the configured and discovered ghcup binary directories without spawns."""
    family = context.family
    if family not in {"Linux", "Darwin", "Windows"}:
        return Err(ToolchainError("Use Linux, macOS or Windows"))
    env = dict(context.environment)
    configured = hostfacts.ghcup_destination(family, env, context.home).parent
    found = hostfacts.discover_ghcup(family, env, context.home)
    directories = (
        (configured,)
        if found is None or found.parent == configured
        else (configured, found.parent)
    )
    values: tuple[Default, ...] = ()
    try:
        for directory in directories:
            for name in ("ghc", "cabal", "ghc.exe", "cabal.exe"):
                path = directory / name
                if path.is_symlink():
                    value = Default(path, "link", str(path.readlink()))
                elif path.exists():
                    value = Default(
                        path, "file", hashlib.sha256(path.read_bytes()).hexdigest()
                    )
                else:
                    value = Default(path, "absent", "")
                values += (value,)
    except OSError as exc:
        return Err(ToolchainError(f"Cannot inspect the user's ghcup selection: {exc}"))
    return Ok(values)


type Ensure = Callable[[HostContext, Pins], Result[Toolchain, ToolchainError]]


def checked(
    context: HostContext, pins: Pins, operation: Ensure = ensure
) -> Result[Toolchain, ToolchainError]:
    """Compare the user's default entries even after a typed provisioning failure."""
    before = defaults(context)
    if isinstance(before, Err):
        return before
    result = operation(context, pins)
    after = defaults(context)
    if isinstance(after, Err):
        return after
    if before.value != after.value:
        return Err(
            ToolchainError("toolchain-ensure changed the user's default ghc or cabal")
        )
    return result
