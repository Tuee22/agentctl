# Copyright (c) 2026 agentctl contributors.
"""Immutable pin values shared by governance and bootstrap policy."""

from dataclasses import dataclass
from typing import Literal

from agentctl.foundation import Family

type Architecture = Literal["x86_64", "aarch64", "arm64", "unsupported"]


@dataclass(frozen=True, slots=True, order=True)
class Version:
    """A numeric version compared by components rather than string order."""

    parts: tuple[int, ...]

    @property
    def text(self) -> str:
        """Render the numeric version for an executable argument."""
        return ".".join(str(part) for part in self.parts)


@dataclass(frozen=True, slots=True)
class Asset:
    """One supported platform's fixed URL and expected SHA-256."""

    family: Family
    architecture: Architecture
    url: str
    sha256: str


@dataclass(frozen=True, slots=True)
class Pins:
    """The immutable package-data contract used by all bootstrap decisions."""

    ghc: Version
    cabal: Version
    ghcup: Version
    ghcup_floor: Version
    assets: tuple[Asset, ...]
    fourmolu: Version
    hlint: Version
    ghc_lib_parser: Version


def asset_for(pins: Pins, family: Family, architecture: Architecture) -> Asset | None:
    """Select a bindist only for an explicitly supported OS and architecture."""
    return next(
        (
            asset
            for asset in pins.assets
            if (asset.family, asset.architecture) == (family, architecture)
        ),
        None,
    )
