# Copyright (c) 2026 agentctl contributors.
"""Private process environments shared by independent host observers."""

from collections.abc import Mapping
from pathlib import Path

SYSTEM_KEYS = frozenset(
    {
        "PATH",
        "PATHEXT",
        "SYSTEMROOT",
        "SystemRoot",
        "WINDIR",
        "COMSPEC",
        "TEMP",
        "TMP",
        "TMPDIR",
        "LD_LIBRARY_PATH",
        "DYLD_LIBRARY_PATH",
    }
)


def state_directory(family: str, env: Mapping[str, str], home: Path) -> Path:
    """Read the documented state location without calling application policy."""
    override = env.get("XDG_STATE_HOME")
    if override is not None and Path(override).is_absolute():
        return Path(override) / "agentctl"
    if family == "Windows":
        return (
            Path(env.get("LOCALAPPDATA", str(home / "AppData/Local")))
            / "agentctl/state"
        )
    return home / ".local/state/agentctl"


def isolated_environment(
    directory: Path, original: Mapping[str, str]
) -> dict[str, str]:
    """Expose no auth variables, project settings, user files or OS credential store."""
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    home = directory / "home"
    home.mkdir(mode=0o700)
    claude = directory / "claude"
    claude.mkdir(mode=0o700)
    codex = directory / "codex"
    codex.mkdir(mode=0o700)
    (codex / "config.toml").write_text(
        'cli_auth_credentials_store = "file"\ncheck_for_update_on_startup = false\n',
        encoding="utf-8",
    )
    return {
        **{key: value for key, value in original.items() if key in SYSTEM_KEYS},
        "HOME": str(home),
        "USERPROFILE": str(home),
        "APPDATA": str(directory / "appdata"),
        "LOCALAPPDATA": str(directory / "localappdata"),
        "CLAUDE_CONFIG_DIR": str(claude),
        "CODEX_HOME": str(codex),
        "DISABLE_AUTOUPDATER": "1",
        "PSMUX_DATA_DIR": str(directory / "psmux"),
        "PSMUX_NO_WARM": "1",
        "TMUX_TMPDIR": str(directory),
        **{
            f"XDG_{kind}_HOME": str(directory / kind.lower())
            for kind in ("CACHE", "CONFIG", "DATA", "STATE")
        },
    }
