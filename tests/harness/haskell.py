# Copyright (c) 2026 agentctl contributors.
"""Native Cabal contexts with disposable source, output and user-home fixtures."""

import os
import shutil
from dataclasses import replace
from pathlib import Path

from agentctl.bootstrap import build
from agentctl.hostfacts import current
from agentctl.paths import directories
from tests.harness.bootstrap import native_tools


def native_context(project: Path, directory: Path) -> build.BuildContext:
    """Share only agentctl's dependency cache and never touch the user's Cabal home."""
    paths = directories(
        "Windows" if os.name == "nt" else "Linux", os.environ, Path.home()
    )
    host = current(paths.cache)
    home = directory / "home"
    home.mkdir(parents=True, exist_ok=True)
    roaming = home / "AppData/Roaming"
    local = home / "AppData/Local"
    roaming.mkdir(parents=True, exist_ok=True)
    local.mkdir(parents=True, exist_ok=True)
    env = dict(host.environment)
    env.update(
        {
            "HOME": str(home),
            "USERPROFILE": str(home),
            "APPDATA": str(roaming),
            "LOCALAPPDATA": str(local),
            **{
                f"XDG_{kind}_HOME": str(directory / kind.lower())
                for kind in ("CACHE", "CONFIG", "DATA", "STATE")
            },
        }
    )
    return build.BuildContext(
        project,
        directory / "build",
        replace(host, home=home, environment=tuple(env.items())),
        native_tools(),
    )


def copy_project(root: Path, directory: Path) -> build.BuildContext:
    """Copy actual checkout sources, including edits and newly introduced files."""
    project = directory / "project"
    shutil.copytree(root / "src/agentctl/haskell", project)
    return native_context(project, directory)
