# Copyright (c) 2026 agentctl contributors.
"""Publish a native bootstrap caller without an agent or multiplexer fixture."""

import os
from dataclasses import dataclass, replace
from pathlib import Path

from agentctl.bootstrap import binary, build
from agentctl.bootstrap.pins import load
from agentctl.foundation import Family, Ok
from agentctl.foundation_paths import Paths, directories


@dataclass(frozen=True, slots=True)
class CallerRequest:
    """Explicit inputs for publishing one private, warmed caller."""

    root: Path
    context: build.BuildContext
    family: Family
    folder: Path
    environment: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class PublishedCaller:
    """The published binary and exact private caller environment."""

    executable: Path
    paths: Paths
    environment: tuple[tuple[str, str], ...]


def publish(request: CallerRequest) -> PublishedCaller:
    """Build and publish through the application-owned bootstrap interfaces."""
    inherited = dict(request.environment)
    home = Path(inherited["HOME"])
    paths = directories(request.family, inherited, home)
    host = replace(
        request.context.host,
        home=home,
        cache=paths.cache,
        cwd=request.folder,
        environment=request.environment,
    )
    pins = request.root / "src/agentctl/bootstrap/pins.toml"
    selected = load(pins)
    assert isinstance(selected, Ok), selected
    layout = binary.plan(
        binary.Request(request.context.project, pins, host, paths.data), selected.value
    )
    assert isinstance(layout, Ok), layout
    built = build.binary(request.context, "exe:agentctl-core")
    assert isinstance(built, Ok), built
    published = binary.publish(request.context, built.value, layout.value)
    assert isinstance(published, Ok), published
    environment = {
        **inherited,
        **{
            key: value
            for key, value in os.environ.items()
            if key.startswith("COVERAGE_") or key == "PYTHONPYCACHEPREFIX"
        },
        "PYTHONPATH": str(request.root / "src") + os.pathsep + str(request.root),
    }
    return PublishedCaller(published.value, paths, tuple(environment.items()))
