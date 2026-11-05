# Copyright (c) 2026 agentctl contributors.
"""Warm public callers through the application's digest layout and publication."""

import os
from dataclasses import dataclass, replace
from pathlib import Path

from agentctl.bootstrap import binary, build
from agentctl.bootstrap.pins import load
from agentctl.paths import Paths, directories
from agentctl.result import Ok
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
    paths = directories(family, case.environment, Path(case.environment["HOME"]))
    host = replace(
        case.mux.context.host,
        home=Path(case.environment["HOME"]),
        cache=paths.cache,
        cwd=case.folder,
        environment=tuple(case.environment.items()),
    )
    root = Path(__file__).resolve().parents[2]
    pins = root / "src/agentctl/bootstrap/pins.toml"
    selected = load(pins)
    assert isinstance(selected, Ok), selected
    layout = binary.plan(
        binary.Request(case.mux.context.project, pins, host, paths.data), selected.value
    )
    assert isinstance(layout, Ok), layout
    built = build.binary(case.mux.context, "exe:agentctl-core")
    assert isinstance(built, Ok), built
    published = binary.publish(case.mux.context, built.value, layout.value)
    assert isinstance(published, Ok), published
    environment = {
        **case.environment,
        **{
            key: value
            for key, value in os.environ.items()
            if key.startswith("COVERAGE_") or key == "PYTHONPYCACHEPREFIX"
        },
        "PYTHONPATH": str(root / "src") + os.pathsep + str(root),
    }
    return WarmCaller(replace(case, environment=environment), published.value, paths)
