# Copyright (c) 2026 agentctl contributors.
"""Owned bootstrap contexts and independently read native path records."""

import json
import os
import platform
import tomllib
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal

from agentctl.bootstrap.pins import Pins, load
from agentctl.bootstrap.toolchain import Toolchain
from agentctl.hostfacts import HostContext, current
from agentctl.paths import directories
from agentctl.result import Ok
from tests.harness.bootstrap_origin import capture


@dataclass(frozen=True, slots=True)
class Observation:
    """Parsed independent facts recorded before the real provisioning step."""

    origin: Literal["agentctl-installed", "user"]
    family: str
    configured: Path
    configured_existed: bool
    found: Path | None
    sha256: str | None
    defaults: tuple[tuple[str, str], ...]


def observation(directory: Path) -> Observation:
    """Use this run's nonce-bound observer; focused runs make a fresh observation."""
    manifest = os.environ.get("AGENTCTL_CHECK_MANIFEST")
    nonce = os.environ.get("AGENTCTL_CHECK_NONCE", "focused")
    if manifest is None:
        capture(directory, nonce, platform.system(), os.environ, Path.home())
        source = directory / "bootstrap-host.json"
    else:
        source = Path(manifest).parent / "bootstrap-host.json"
    value: object = json.loads(source.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    assert value["nonce"] == nonce
    origin, family, configured, occupied, previous, digest, defaults = (
        value[name]
        for name in (
            "origin",
            "family",
            "configured",
            "configured_existed",
            "found",
            "sha256",
            "defaults",
        )
    )
    assert origin in {"agentctl-installed", "user"}
    assert isinstance(family, str)
    assert isinstance(configured, str)
    assert isinstance(occupied, bool)
    assert previous is None or isinstance(previous, str)
    assert digest is None or isinstance(digest, str)
    assert isinstance(defaults, dict)
    assert all(
        isinstance(key, str) and isinstance(item, str) for key, item in defaults.items()
    )
    return Observation(
        origin,
        family,
        Path(configured),
        occupied,
        Path(previous) if previous is not None else None,
        digest,
        tuple((str(key), str(item)) for key, item in defaults.items()),
    )


def native_tools() -> Toolchain:
    """Read the record the real gate prepared before the pytest leg begins."""
    family = platform.system()
    assert family in {"Linux", "Darwin", "Windows"}
    cache = directories(family, os.environ, Path.home()).cache
    fields = tomllib.loads((cache / "toolchain-paths.toml").read_text(encoding="utf-8"))
    ghc, cabal = fields["ghc"], fields["cabal"]
    assert isinstance(ghc, str)
    assert isinstance(cabal, str)
    assert Path(ghc).is_absolute()
    assert Path(cabal).is_absolute()
    return Toolchain(ghc, cabal)


def pins() -> Pins:
    """Load the package data, independently held to literal oracle pins."""
    result = load()
    assert isinstance(result, Ok)
    return result.value


def context(directory: Path) -> HostContext:
    """Keep home, prefix, cache and the working directory inside owned storage."""
    directory.mkdir(parents=True, exist_ok=True)
    home = directory / "home"
    home.mkdir()
    roaming = home / "AppData/Roaming"
    local = home / "AppData/Local"
    roaming.mkdir(parents=True)
    local.mkdir(parents=True)
    value = current(directory / "cache")
    env = {
        key: item
        for key, item in value.environment
        if key not in {"GHCUP_USE_XDG_DIRS", "XDG_BIN_HOME"}
    }
    env.update(
        {
            "HOME": str(home),
            "USERPROFILE": str(home),
            "GHCUP_INSTALL_BASE_PREFIX": str(home),
            "PATH": "",
            "APPDATA": str(roaming),
            "LOCALAPPDATA": str(local),
            **{
                f"XDG_{kind}_HOME": str(directory / kind.lower())
                for kind in ("CACHE", "CONFIG", "DATA", "STATE")
            },
        }
    )
    return replace(
        value,
        home=home,
        cwd=directory,
        environment=tuple(env.items()),
        interactive=False,
        assume_yes=False,
    )
