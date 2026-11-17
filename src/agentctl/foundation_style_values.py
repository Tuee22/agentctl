# Copyright (c) 2026 agentctl contributors.
"""Immutable style-tool paths shared by governance and bootstrap."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class StyleTools:
    """The verified native tools in one atomically published cache directory."""

    fourmolu: Path
    hlint: Path
