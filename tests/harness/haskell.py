# Copyright (c) 2026 agentctl contributors.
"""Native Cabal contexts with disposable source, output and user-home fixtures."""

import os
import shutil
from dataclasses import replace
from pathlib import Path

import pytest

from agentctl.bootstrap import build
from agentctl.hostfacts import current
from agentctl.paths import directories
from agentctl.result import Ok
from tests.harness.bootstrap import native_tools


def native_context(project: Path, directory: Path) -> build.BuildContext:
    """Share only agentctl's dependency cache and never touch the user's Cabal home."""
    paths = directories(
        "Windows" if os.name == "nt" else "Linux", os.environ, Path.home()
    )
    host = current(paths.cache)
    home = directory / "home"
    home.mkdir(parents=True, exist_ok=True)
    env = dict(host.environment)
    env.update(
        {
            "HOME": str(home),
            "USERPROFILE": str(home),
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


@pytest.fixture(scope="session")
def haskell_build(
    root: Path, tmp_path_factory: pytest.TempPathFactory
) -> build.BuildContext:
    """Build the real bundled project once, through the application's shared path."""
    context = native_context(
        root / "src/agentctl/haskell", tmp_path_factory.mktemp("native-haskell")
    )
    mutant_directory = os.environ.get("AGENTCTL_MUTANT_BUILD")
    if mutant_directory is not None:
        context = replace(context, directory=Path(mutant_directory), options=("-O0",))
    compiled = build.compile_project(context)
    assert isinstance(compiled, Ok), compiled
    return context
