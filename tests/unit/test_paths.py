# Copyright (c) 2026 agentctl contributors.
"""Directory policy across every supported operating-system input."""

from pathlib import Path

import pytest

from agentctl.paths import Family, Paths, directories

pytestmark = pytest.mark.evidence("value")


def test_xdg_overrides_on_every_os(tmp_path: Path) -> None:
    """Absolute overrides win; absent and relative overrides use defaults."""
    families: tuple[Family, ...] = ("Linux", "Darwin", "Windows")
    for family in families:
        env = {
            "XDG_CACHE_HOME": str(tmp_path / "c"),
            "XDG_DATA_HOME": str(tmp_path / "d"),
            "XDG_STATE_HOME": str(tmp_path / "s"),
        }
        assert directories(family, env, tmp_path) == Paths(
            tmp_path / "c/agentctl", tmp_path / "d/agentctl", tmp_path / "s/agentctl"
        )
        default = directories(family, {}, tmp_path)
        assert directories(family, dict.fromkeys(env, "relative"), tmp_path) == default
        if family == "Windows":
            assert default.cache == tmp_path / "AppData/Local/agentctl/cache"
            assert (
                directories(
                    family, {"LOCALAPPDATA": str(tmp_path / "local")}, tmp_path
                ).data
                == tmp_path / "local/agentctl/data"
            )
        else:
            assert default == Paths(
                tmp_path / ".cache/agentctl",
                tmp_path / ".local/share/agentctl",
                tmp_path / ".local/state/agentctl",
            )
