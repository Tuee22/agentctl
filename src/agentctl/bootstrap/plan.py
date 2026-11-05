# Copyright (c) 2026 agentctl contributors.
"""Pure, ordered provisioning actions from immutable host observations."""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from agentctl.bootstrap.pins import Asset, Pins, asset_for
from agentctl.bootstrap.prereqs import (
    PackageInstall,
    PrerequisiteError,
    XcodeInstall,
    plan_actions,
)
from agentctl.hostfacts import HostFacts
from agentctl.result import Err, Ok, Result


@dataclass(frozen=True, slots=True)
class DownloadGhcup:
    """Fetch and verify the selected asset into an absent destination."""

    asset: Asset
    destination: Path


@dataclass(frozen=True, slots=True)
class GhcupCommand:
    """An absolute ghcup invocation whose arguments never select defaults."""

    executable: Path
    arguments: tuple[str, ...]


type Action = DownloadGhcup | GhcupCommand | PackageInstall | XcodeInstall


@dataclass(frozen=True, slots=True)
class Refusal:
    """A complete refusal with no partially executable provisioning plan."""

    reason: Literal["unsupported-platform", "ghcup-below-floor", "ghcup-unanswering"]
    remedy: str


def provision(
    facts: HostFacts, pins: Pins
) -> Result[tuple[Action, ...], Refusal | PrerequisiteError]:
    """Reuse answering pins and acceptable ghcup, installing only missing pins."""
    asset = asset_for(pins, facts.family, facts.architecture)
    if asset is None:
        return Err(Refusal("unsupported-platform", ""))
    if facts.ghc is not None and facts.cabal is not None:
        return Ok(())
    actions: tuple[Action, ...] = ()
    if facts.ghcup is None:
        executable = facts.ghcup_destination
        actions = (DownloadGhcup(asset, executable),)
    else:
        executable = facts.ghcup.path
        if facts.ghcup.version is None:
            return Err(Refusal("ghcup-unanswering", "ghcup upgrade"))
        if facts.ghcup.version < pins.ghcup_floor:
            return Err(Refusal("ghcup-below-floor", "ghcup upgrade"))
    prerequisites = plan_actions(facts)
    if isinstance(prerequisites, Err):
        return prerequisites
    actions = (*prerequisites.value, *actions)
    if facts.ghc is None:
        actions += (GhcupCommand(executable, ("install", "ghc", pins.ghc.text)),)
    if facts.cabal is None:
        actions += (
            GhcupCommand(executable, ("install", "cabal", pins.cabal.text, "--no-set")),
        )
    return Ok(
        (
            *actions,
            GhcupCommand(executable, ("whereis", "ghc", pins.ghc.text)),
            GhcupCommand(executable, ("whereis", "cabal", pins.cabal.text)),
        )
    )
