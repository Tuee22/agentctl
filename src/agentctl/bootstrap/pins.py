# Copyright (c) 2026 agentctl contributors.
"""Typed parsing of the shipped versions and verified download assets."""

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from agentctl.paths import Family
from agentctl.result import Err, Ok, Result

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


@dataclass(frozen=True, slots=True)
class PinError:
    """Package data was unreadable or violated its closed schema."""

    message: str


def version(value: object) -> Version | None:
    """Parse only dotted ASCII numeric versions without suffixes or whitespace."""
    if (
        not isinstance(value, str)
        or re.fullmatch(r"[0-9]{1,9}(?:\.[0-9]{1,9}){1,3}", value) is None
    ):
        return None
    return Version(tuple(int(part) for part in value.split(".")))


def _asset(value: object) -> Asset | None:
    """Reject unknown platforms, extra fields and non-HTTPS download data."""
    if not isinstance(value, dict) or set(value) != {
        "family",
        "architecture",
        "url",
        "sha256",
    }:
        return None
    family, architecture = value["family"], value["architecture"]
    url, digest = value["url"], value["sha256"]
    if (
        not isinstance(family, str)
        or family not in {"Linux", "Darwin", "Windows"}
        or not isinstance(architecture, str)
        or architecture not in {"x86_64", "aarch64", "arm64"}
        or not isinstance(url, str)
        or not url.startswith("https://downloads.haskell.org/~ghcup/")
        or not isinstance(digest, str)
        or re.fullmatch(r"[0-9a-f]{64}", digest) is None
    ):
        return None
    return Asset(family, architecture, url, digest)


def parse(value: object) -> Result[Pins, PinError]:
    """Translate only the complete version and asset schema into domain values."""
    if not isinstance(value, dict) or set(value) != {"versions", "asset"}:
        return Err(PinError("pins require versions and asset tables"))
    versions, assets = value["versions"], value["asset"]
    if not isinstance(versions, dict) or set(versions) != {
        "ghc",
        "cabal",
        "ghcup",
        "ghcup_floor",
        "fourmolu",
        "hlint",
        "ghc_lib_parser",
    }:
        return Err(PinError("pins require the closed toolchain and style version set"))
    parsed = tuple(
        version(versions[name])
        for name in (
            "ghc",
            "cabal",
            "ghcup",
            "ghcup_floor",
            "fourmolu",
            "hlint",
            "ghc_lib_parser",
        )
    )
    if any(item is None for item in parsed):
        return Err(PinError("pins contain a malformed numeric version"))
    if not isinstance(assets, list) or not assets:
        return Err(PinError("pins require a nonempty asset array"))
    return _assets(tuple(item for item in parsed if item is not None), assets)


def _assets(
    versions: tuple[Version, ...], assets: list[object]
) -> Result[Pins, PinError]:
    """Keep asset validation separate from the version-table boundary."""
    valid: tuple[Asset, ...] = ()
    for item in assets:
        parsed = _asset(item)
        if parsed is None:
            return Err(PinError("pins contain a malformed download asset"))
        valid += (parsed,)
    if len({(item.family, item.architecture) for item in valid}) != len(valid):
        return Err(PinError("pins contain a duplicate platform"))
    ghc, cabal, ghcup, floor, fourmolu, hlint, parser = versions
    return Ok(Pins(ghc, cabal, ghcup, floor, valid, fourmolu, hlint, parser))


def load(path: Path | None = None) -> Result[Pins, PinError]:
    """Read packaged pins or an explicitly supplied data file at the I/O edge."""
    try:
        data: object = tomllib.loads(
            (path or Path(__file__).with_name("pins.toml")).read_text(encoding="utf-8")
        )
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        return Err(PinError(str(exc)))
    return parse(data)


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
