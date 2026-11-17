# Copyright (c) 2026 agentctl contributors.
"""Native build fixture imported only by tests that require it."""

import os
from dataclasses import replace
from pathlib import Path

import pytest

from agentctl.bootstrap import build
from agentctl.result import Ok
from tests.harness.haskell import native_context

CONTEXT = pytest.StashKey[build.BuildContext]()


@pytest.fixture(scope="session")
def haskell_build(
    root: Path, tmp_path_factory: pytest.TempPathFactory, request: pytest.FixtureRequest
) -> build.BuildContext:
    """Build the real bundled project through the application's shared path."""
    if CONTEXT in request.session.stash:
        return request.session.stash[CONTEXT]
    context = native_context(
        root / "src/agentctl/haskell", tmp_path_factory.mktemp("native-haskell")
    )
    mutant_directory = os.environ.get("AGENTCTL_MUTANT_BUILD")
    if mutant_directory is not None:
        context = replace(context, directory=Path(mutant_directory), options=("-O0",))
    compiled = build.compile_project(context)
    assert isinstance(compiled, Ok), compiled
    request.session.stash[CONTEXT] = context
    return context
