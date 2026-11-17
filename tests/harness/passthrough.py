# Copyright (c) 2026 agentctl contributors.
"""Warm public callers through the application's digest layout and publication."""

from dataclasses import dataclass, replace
from pathlib import Path

from agentctl.paths import Paths
from tests.harness.bootstrap_caller import CallerRequest, publish
from tests.harness.launch import LaunchCase


@dataclass(frozen=True, slots=True)
class WarmCaller:
    """A published native binary and private caller with identical source bytes."""

    case: LaunchCase
    executable: Path
    paths: Paths


def warm(case: LaunchCase) -> WarmCaller:
    """Publish the current native build into this caller's genuine XDG-derived cache."""
    family = case.mux.family
    assert family in {"Linux", "Darwin", "Windows"}
    root = Path(__file__).resolve().parents[2]
    caller = publish(
        CallerRequest(
            root, case.mux.context, family, case.folder, tuple(case.environment.items())
        )
    )
    return WarmCaller(
        replace(case, environment=dict(caller.environment)),
        caller.executable,
        caller.paths,
    )
