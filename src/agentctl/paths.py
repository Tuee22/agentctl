# Copyright (c) 2026 agentctl contributors.
"""Pure per-user directory policy, shared by all command paths."""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

type Family = Literal["Linux", "Darwin", "Windows"]


@dataclass(frozen=True, slots=True)
class Paths:
    """The three directories agentctl owns for one user."""

    cache: Path
    data: Path
    state: Path


def directories(family: Family, env: Mapping[str, str], home: Path) -> Paths:
    """Honour absolute XDG overrides on every supported OS family."""
    local = Path(env.get("LOCALAPPDATA", str(home / "AppData" / "Local")))
    defaults = (
        (
            local / "agentctl" / "cache",
            local / "agentctl" / "data",
            local / "agentctl" / "state",
        )
        if family == "Windows"
        else (
            home / ".cache" / "agentctl",
            home / ".local/share" / "agentctl",
            home / ".local/state" / "agentctl",
        )
    )
    resolved = tuple(
        Path(env[key]) / "agentctl"
        if key in env and Path(env[key]).is_absolute()
        else default
        for key, default in zip(
            ("XDG_CACHE_HOME", "XDG_DATA_HOME", "XDG_STATE_HOME"), defaults, strict=True
        )
    )
    cache, data, state = resolved
    return Paths(cache, data, state)
