# Copyright (c) 2026 agentctl contributors.
"""Pure style-tool identity, cache paths and compiler-pinned install arguments."""

import hashlib
from dataclasses import dataclass
from pathlib import Path

from agentctl.bootstrap.pins import Pins


@dataclass(frozen=True, slots=True)
class StyleTools:
    """The verified native tools in one atomically published cache directory."""

    fourmolu: Path
    hlint: Path


def digest(pins: Pins) -> str:
    """Hash ordered name/version fields with eight-byte big-endian lengths."""
    hashed = hashlib.sha256()
    for name, version in (
        ("ghc", pins.ghc),
        ("fourmolu", pins.fourmolu),
        ("hlint", pins.hlint),
        ("ghc_lib_parser", pins.ghc_lib_parser),
    ):
        for value in (name, version.text):
            field = value.encode("ascii")
            hashed.update(len(field).to_bytes(8, "big"))
            hashed.update(field)
    return hashed.hexdigest()


def directory(cache: Path, pins: Pins) -> Path:
    """Keep compiler or style-pin changes in separate cache directories."""
    return cache / "tools" / digest(pins)


def paths(directory: Path, family: str) -> StyleTools:
    """Use native executable suffixes without resolving either tool on PATH."""
    suffix = ".exe" if family == "Windows" else ""
    return StyleTools(directory / ("fourmolu" + suffix), directory / ("hlint" + suffix))


def install_arguments(
    pins: Pins, ghc: str, staged: Path, build: Path, index_state: str
) -> tuple[str, ...]:
    """Build both exact versions against one supported parser in the private store."""
    return (
        "install",
        f"fourmolu-{pins.fourmolu.text}",
        f"hlint-{pins.hlint.text}",
        "--ignore-project",
        "--install-method=copy",
        "--overwrite-policy=never",
        f"--installdir={staged}",
        "-w",
        ghc,
        f"--builddir={build}",
        f"--index-state={index_state}",
        f"--constraint=ghc-lib-parser=={pins.ghc_lib_parser.text}",
        "--jobs=2",
    )
