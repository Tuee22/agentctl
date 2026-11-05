# Copyright (c) 2026 agentctl contributors.
"""Pinned native style legs, complete configuration and nonempty source walks."""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import click

from agentctl.bootstrap import build
from agentctl.bootstrap import style as cache
from agentctl.bootstrap.pins import PinError, Pins
from agentctl.check.legs import style_legs
from agentctl.hostfacts import HostContext
from agentctl.process import run
from agentctl.result import Err, Ok, Result

FOURMOLU_KEYS = frozenset(
    {
        "indentation",
        "column-limit",
        "function-arrows",
        "comma-style",
        "import-export-style",
        "import-grouping",
        "indent-wheres",
        "record-brace-space",
        "newlines-between-decls",
        "haddock-style",
        "haddock-style-module",
        "haddock-location-signature",
        "let-style",
        "in-style",
        "if-style",
        "single-constraint-parens",
        "single-deriving-parens",
        "sort-constraints",
        "sort-derived-classes",
        "sort-deriving-clauses",
        "trailing-section-operators",
        "unicode",
        "respectful",
        "fixities",
        "reexports",
        "local-modules",
    }
)


def keys(text: str) -> tuple[str, ...]:
    """Read unindented configuration keys without interpreting values or comments."""
    return tuple(str(key) for key in re.findall(r"(?m)^([a-z][a-z-]*):", text))


def configuration(project: Path) -> Result[None, build.BuildError]:
    """Require one complete formatter configuration and the default HLint hint set."""
    try:
        files = tuple(
            sorted(
                path.relative_to(project).as_posix()
                for path in project.rglob("*")
                if path.name in {"fourmolu.yaml", ".hlint.yaml"}
            )
        )
        if files != (".hlint.yaml", "fourmolu.yaml"):
            return Err(
                build.BuildError(
                    "Each style tool requires exactly one root configuration"
                )
            )
        text = (project / "fourmolu.yaml").read_text(encoding="utf-8")
        names = keys(text)
        lines = tuple(
            line
            for line in text.splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        )
        if (
            frozenset(names) != FOURMOLU_KEYS
            or len(names) != len(FOURMOLU_KEYS)
            or len(lines) != len(names)
        ):
            return Err(
                build.BuildError(
                    "Fourmolu configuration must specify every setting exactly once"
                )
            )
        if (project / ".hlint.yaml").read_text(encoding="utf-8").strip() != "[]":
            return Err(
                build.BuildError(
                    "HLint configuration must preserve default hints without ignores"
                )
            )
    except (OSError, UnicodeError) as exc:
        return Err(build.BuildError(f"Cannot read style configuration: {exc}"))
    return Ok(None)


def targets(project: Path) -> Result[tuple[str, ...], build.BuildError]:
    """Walk all three Haskell source directories, including ignored source files."""
    files = tuple(
        str(path)
        for directory in ("app", "src", "test")
        for path in sorted((project / directory).rglob("*.hs"))
    )
    return (
        Ok(files) if files else Err(build.BuildError("Empty Haskell style target set"))
    )


@dataclass(frozen=True, slots=True)
class StyleStep:
    """One native style leg whose tools are resolved after toolchain ensure."""

    name: Literal["fourmolu", "hlint"]
    host: HostContext
    project: Path
    pins: Result[Pins, PinError]


def run_step(step: StyleStep) -> int:
    """Validate owned inputs, prepare the pins and propagate the actual tool status."""
    ready = preparation(step)
    if isinstance(ready, Err):
        click.echo(ready.error.message, err=True)
        return 1
    context, tools, files = ready.value
    leg = next(leg for leg in style_legs(tools, files) if leg.name == step.name)
    result = run(list(leg.argv), cwd=step.project, env=build.environment(context))
    if isinstance(result, Err):
        click.echo(result.error.message, err=True)
        return 1
    click.echo(result.value.stdout, nl=False)
    click.echo(result.value.stderr, nl=False, err=True)
    return result.value.code


def preparation(
    step: StyleStep,
) -> Result[
    tuple[build.BuildContext, cache.StyleTools, tuple[str, ...]], build.BuildError
]:
    """Resolve each typed input before any style command can execute."""
    configured = configuration(step.project)
    if isinstance(configured, Err):
        return configured
    files = targets(step.project)
    if isinstance(files, Err):
        return files
    pins = step.pins
    if isinstance(pins, Err):
        return Err(build.BuildError(pins.error.message))
    tools = build.recorded_tools(step.host)
    if isinstance(tools, Err):
        return tools
    context = build.BuildContext(
        step.project, step.host.cache / "build/check", step.host, tools.value
    )
    native = (
        build.ensure_style_tools(context, pins.value)
        if step.name == "fourmolu"
        else build.verify_style_tools(
            context, pins.value, cache.directory(step.host.cache, pins.value)
        )
    )
    return (
        native if isinstance(native, Err) else Ok((context, native.value, files.value))
    )
