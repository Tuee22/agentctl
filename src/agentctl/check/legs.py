# Copyright (c) 2026 agentctl contributors.
"""Pure leg construction and complete-run verdicts."""

from dataclasses import dataclass
from pathlib import Path, PurePath, PurePosixPath

from agentctl.bootstrap.style import StyleTools
from agentctl.result import Err, Ok, Result


@dataclass(frozen=True, slots=True)
class Leg:
    """One introduced tool invocation."""

    name: str
    argv: tuple[str, ...]
    after: tuple[tuple[str, ...], ...] = ()


def targets(root: Path) -> Result[tuple[str, ...], str]:
    """Walk both Python source roots without applying ignore files."""
    files = tuple(
        str(path)
        for directory in ("src", "tests")
        for path in sorted((root / directory).rglob("*.py"))
    )
    return Ok(files) if files else Err("empty Python target set")


def coverage_commands(
    python: str, root: PurePath, run_dir: PurePath
) -> tuple[tuple[str, ...], ...]:
    """Combine only run-owned data and enforce the full branch-coverage floor."""
    common = (
        f"--rcfile={(root / 'pyproject.toml').as_posix()}",
        f"--data-file={(run_dir / 'coverage').as_posix()}",
    )
    return (
        (python, "-m", "coverage", "combine", *common, run_dir.as_posix()),
        (
            python,
            "-m",
            "coverage",
            "report",
            *common,
            "--fail-under=100",
            "--show-missing",
        ),
    )


def python_legs(
    python: str, root: PurePath, files: tuple[str, ...], run_dir: PurePath
) -> tuple[Leg, ...]:
    """Build exactly the Python legs introduced by the package skeleton."""
    root = PurePosixPath(root.as_posix())
    run_dir = PurePosixPath(run_dir.as_posix())
    config = str(root / "pyproject.toml")
    return (
        Leg(
            "ruff-check",
            (
                python,
                "-m",
                "ruff",
                "check",
                "--config",
                config,
                "--no-cache",
                "--no-fix",
                *files,
            ),
        ),
        Leg(
            "ruff-format",
            (
                python,
                "-m",
                "ruff",
                "format",
                "--check",
                "--config",
                config,
                "--no-cache",
                *files,
            ),
        ),
        Leg(
            "ty",
            (
                python,
                "-m",
                "ty",
                "check",
                "--python",
                python,
                "--error-on-warning",
                *files,
            ),
        ),
        Leg(
            "pytest",
            (
                python,
                "-m",
                "coverage",
                "run",
                f"--rcfile={config}",
                f"--data-file={run_dir / 'coverage'}",
                "--branch",
                "--source=agentctl",
                "-m",
                "pytest",
                "-c",
                config,
                f"--rootdir={root}",
                "-p",
                "no:cacheprovider",
                "-p",
                "pytester",
                "-p",
                "agentctl.check.gate_plugin",
                "tests",
            ),
            coverage_commands(python, root, run_dir),
        ),
    )


def cabal_legs(cabal: str, ghc: str, directory: Path) -> tuple[Leg, ...]:
    """Describe the exact Cabal legs independently of when tools are provisioned."""
    common = ("all", "--enable-tests", "-w", ghc, f"--builddir={directory.as_posix()}")
    return (
        Leg("cabal-build", (cabal, "build", *common)),
        Leg("cabal-test", (cabal, "test", *common, "--test-show-details=direct")),
    )


def style_legs(tools: StyleTools, files: tuple[str, ...]) -> tuple[Leg, ...]:
    """Check every discovered source using the absolute pinned tool executables."""
    return (
        Leg("fourmolu", (tools.fourmolu.as_posix(), "--mode", "check", *files)),
        Leg("hlint", (tools.hlint.as_posix(), "app", "src", "test")),
    )


def verdict(expected: tuple[str, ...], outcomes: tuple[tuple[str, int], ...]) -> bool:
    """Require every leg exactly once in order, with a successful status."""
    return tuple(name for name, _code in outcomes) == expected and all(
        code == 0 for _name, code in outcomes
    )
