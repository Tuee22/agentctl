# Copyright (c) 2026 agentctl contributors.
"""Exact-once scratch mutations killed only by their named failure reason."""

import os
import re
import shutil
import sys
import tempfile
import tomllib
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Literal

from agentctl.check.haskell_mutants import killer as haskell_killer
from agentctl.hostfacts import current
from agentctl.paths import directories
from agentctl.process import Output, run
from agentctl.result import Err, Ok, Result


class Operator(Enum):
    """The closed vocabulary of deliberate defect transformations."""

    DELETE = "delete"
    NEGATE = "negate"
    REPLACE_LITERAL = "replace-literal"
    REORDER = "reorder"
    WIDEN = "widen"
    SHORT_CIRCUIT = "short-circuit"


@dataclass(frozen=True, slots=True)
class MutationError:
    """A rejected record, patch, baseline or defective execution."""

    stage: Literal["schema", "copy", "patch", "baseline", "mutant", "spawn"]
    message: str


@dataclass(frozen=True, slots=True)
class Mutant:
    """One exact source transformation and the tests responsible for it."""

    identifier: str
    operator: Operator
    target: str
    search: str
    replacement: str
    killers: tuple[str, ...]
    reason: str


@dataclass(frozen=True, slots=True)
class Patch:
    """Original and defective bytes for exactly one contained scratch target."""

    target: Path
    original: bytes
    changed: bytes


def operator(value: str) -> Result[Operator, MutationError]:
    """Parse the operator rather than guessing an unknown transformation."""
    for member in Operator:
        if value == member.value:
            return Ok(member)
    return Err(MutationError("schema", "unknown operator"))


def parse(value: object) -> Result[Mutant, MutationError]:
    """Validate record shape, containment and nonrecursive killer identities."""
    fields = ("id", "operator", "target", "search", "replace", "killers", "reason")
    if not isinstance(value, dict) or set(value) != set(fields):
        return Err(MutationError("schema", "closed mutant record fields required"))
    text = tuple(value[name] for name in fields if name != "killers")
    if not all(isinstance(item, str) for item in text):
        return Err(MutationError("schema", "mutant fields must be strings"))
    identifier, operation, target, search, replacement, reason = (
        str(item) for item in text
    )
    parsed = operator(operation)
    if isinstance(parsed, Err):
        return parsed
    killers = value["killers"]
    if (
        not isinstance(killers, list)
        or not killers
        or not all(isinstance(item, str) for item in killers)
    ):
        return Err(MutationError("schema", "nonempty killer node ids required"))
    nodes = tuple(str(item) for item in killers)
    problem = _identity(identifier, target, search, reason, nodes)
    return (
        problem
        if problem is not None
        else Ok(
            Mutant(identifier, parsed.value, target, search, replacement, nodes, reason)
        )
    )


def _identity(
    identifier: str, target: str, search: str, reason: str, killers: tuple[str, ...]
) -> Err[MutationError] | None:
    """Check record identities and paths without accessing the filesystem."""
    if not re.fullmatch(r"M-[a-z]+-[a-z0-9-]+", identifier) or not search or not reason:
        return Err(
            MutationError("schema", "id, exact search and named reason required")
        )
    path = Path(target)
    if path.is_absolute() or ".." in path.parts or not path.parts or "\\" in target:
        return Err(MutationError("schema", "target escapes scratch tree"))
    if any(
        not re.fullmatch(
            r"tests/(?:unit|integration|e2e|governance)/test_\w+\.py::test_\w+(?:\[[A-Za-z0-9_.-]+\])?|haskell:agentctl-core-test/[A-Za-z0-9_-]+/[A-Za-z0-9_-]+",
            node,
        )
        or "::test_corpus" in node
        for node in killers
    ):
        return Err(
            MutationError(
                "schema", "killer must be an ordinary nonlive noncorpus pytest node"
            )
        )
    return None


def corpus(root: Path) -> Result[tuple[Mutant, ...], MutationError]:
    """Load every executable record, rejecting empty or duplicate corpora."""
    records: tuple[Mutant, ...] = ()
    for path in sorted((root / "tests/mutants").glob("*.toml")):
        try:
            document = tomllib.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
            return Err(MutationError("schema", str(exc)))
        values = document.get("mutant")
        if set(document) != {"mutant"} or not isinstance(values, list) or not values:
            return Err(MutationError("schema", "nonempty mutant rows required"))
        for value in values:
            record = parse(value)
            if isinstance(record, Err):
                return record
            if any(
                previous.identifier == record.value.identifier for previous in records
            ):
                return Err(MutationError("schema", "duplicate mutant id"))
            records += (record.value,)
    return Ok(records) if records else Err(MutationError("schema", "empty corpus"))


def scratch(root: Path, destination: Path) -> Result[Path, MutationError]:
    """Copy the checkout once, excluding only its repository metadata."""
    if destination.resolve().is_relative_to(root.resolve()):
        return Err(MutationError("copy", "scratch tree must be outside checkout"))

    def ignore(directory: str, _names: list[str]) -> frozenset[str]:
        return frozenset({".git"}) if Path(directory) == root else frozenset[str]()

    try:
        shutil.copytree(root, destination, ignore=ignore, symlinks=True)
    except OSError as exc:
        return Err(MutationError("copy", str(exc)))
    return Ok(destination)


def patch(
    original: bytes, search: bytes, replacement: bytes
) -> Result[bytes, MutationError]:
    """Require exactly one occurrence before changing the scratch bytes."""
    if not search or original.count(search) != 1:
        return Err(MutationError("patch", "search must match exactly once"))
    return Ok(original.replace(search, replacement, 1))


def baseline(output: Output, reason: str) -> Result[None, MutationError]:
    """Require the unmodified killer to pass without the defect's reason."""
    if output.code != 0 or reason in output.stdout + output.stderr:
        return Err(
            MutationError("baseline", "baseline must pass without the named reason")
        )
    return Ok(None)


def killed(output: Output, reason: str) -> Result[None, MutationError]:
    """Count only test failure with the named reason, never unrelated breakage."""
    if output.code != 1:
        return Err(MutationError("mutant", "survivor or non-test failure"))
    combined = output.stdout + output.stderr
    if any(
        token in combined
        for token in (
            "ImportError",
            "ModuleNotFoundError",
            "SyntaxError",
            "INTERNALERROR",
        )
    ):
        return Err(MutationError("mutant", "unrelated interpreter or import failure"))
    detail = "\n".join(line for line in combined.splitlines() if line.startswith("E "))
    if reason not in detail:
        return Err(MutationError("mutant", "wrong failure reason"))
    return Ok(None)


def _killer(tree: Path, node: str, timeout: float) -> Result[Output, MutationError]:
    """Run a named child outside the gate session with fresh bytecode storage."""
    if node.startswith("haskell:"):
        paths = directories(
            "Windows" if os.name == "nt" else "Linux", os.environ, Path.home()
        )
        output = haskell_killer(tree, node, current(paths.cache))
        return (
            Err(MutationError("spawn", output.error.message))
            if isinstance(output, Err)
            else output
        )
    with tempfile.TemporaryDirectory(prefix="agentctl-killer-") as temporary:
        env = {
            key: value
            for key, value in os.environ.items()
            if key
            not in {
                "AGENTCTL_CHECK_NONCE",
                "AGENTCTL_CHECK_MANIFEST",
                "PYTEST_ADDOPTS",
                "PYTEST_PLUGINS",
                "PYTHONPATH",
            }
            and not key.startswith("COVERAGE_")
        }
        env.update(
            {
                "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
                "PYTHONPYCACHEPREFIX": str(Path(temporary) / "bytecode"),
                "PYTHONPATH": os.pathsep.join((str(tree / "src"), str(tree))),
                "AGENTCTL_MUTANT_BUILD": str(tree.parent / "haskell-mutants"),
            }
        )
        program = (
            "import sys; sys.path.insert(0, sys.argv.pop(1)); "
            "import pytest; sys.exit(pytest.main(sys.argv[1:]))"
        )
        result = run(
            [
                sys.executable,
                "-c",
                program,
                str(tree / "src"),
                "-q",
                "--tb=short",
                "-p",
                "no:cacheprovider",
                "-p",
                "pytester",
                node,
            ],
            cwd=tree,
            env=env,
            timeout=timeout,
        )
    return (
        Err(MutationError("spawn", result.error.message))
        if isinstance(result, Err)
        else result
    )


def exercise(
    tree: Path, record: Mutant, *, timeout: float = 120
) -> Result[None, MutationError]:
    """Baseline every killer, apply one defect and restore on every exit path."""
    target = tree / record.target
    if not target.resolve().is_relative_to(tree.resolve()):
        return Err(MutationError("patch", "target escapes scratch tree"))
    try:
        original = target.read_bytes()
        changed = patch(
            original, record.search.encode("utf-8"), record.replacement.encode("utf-8")
        )
        if isinstance(changed, Err):
            return changed
        return _exercise(tree, Patch(target, original, changed.value), record, timeout)
    except OSError as exc:
        return Err(MutationError("patch", str(exc)))


def _exercise(
    tree: Path, prepared: Patch, record: Mutant, timeout: float
) -> Result[None, MutationError]:
    """Keep the restoration finalizer around baseline and defective invocations."""
    try:
        for node in record.killers:
            output = _killer(tree, node, timeout)
            if isinstance(output, Err):
                return output
            verdict = baseline(output.value, record.reason)
            if isinstance(verdict, Err):
                return Err(
                    MutationError(
                        verdict.error.stage,
                        f"{record.identifier}: {node}: {verdict.error.message}\n"
                        f"{output.value.stdout}\n{output.value.stderr}",
                    )
                )
        prepared.target.write_bytes(prepared.changed)
        for node in record.killers:
            output = _killer(tree, node, timeout)
            if isinstance(output, Err):
                return output
            verdict = killed(output.value, record.reason)
            if isinstance(verdict, Err):
                return Err(
                    MutationError(
                        verdict.error.stage,
                        f"{record.identifier}: {node}: {verdict.error.message}\n"
                        f"{output.value.stdout}\n{output.value.stderr}",
                    )
                )
        return Ok(None)
    finally:
        prepared.target.write_bytes(prepared.original)
