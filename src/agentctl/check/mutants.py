# Copyright (c) 2026 agentctl contributors.
"""Exact-once scratch mutations killed only by their named failure reason."""

import json
import os
import re
import shutil
import sys
import tempfile
import tomllib
from dataclasses import dataclass
from enum import Enum
from importlib import import_module
from pathlib import Path, PurePosixPath
from typing import Literal

from agentctl.check.evidence import Entry
from agentctl.check.ratchet import MutantAmendment, RowFact, mutant_amendment_matches
from agentctl.foundation import Err, Ok, Result
from agentctl.foundation_host import current
from agentctl.foundation_paths import directories
from agentctl.foundation_process import Output, run


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


@dataclass(frozen=True, slots=True)
class KillerOutcome:
    """One named baseline and its mutation result, when the baseline passed."""

    node: str
    baseline: Result[None, MutationError]
    mutation: Result[None, MutationError] | None


@dataclass(frozen=True, slots=True)
class KillerExecution:
    """The declared mutant and its restored, per-killer execution outcome."""

    record: Mutant
    outcomes: Result[tuple[KillerOutcome, ...], MutationError]


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
        or len(killers) != len(set(killers))
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
    if path.anchor or ".." in path.parts or not path.parts or "\\" in target:
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
    try:
        with os.scandir(root / "tests/mutants") as directory:
            paths = tuple(
                sorted(
                    Path(entry.path)
                    for entry in directory
                    if entry.name.endswith(".toml")
                )
            )
        if any(path.is_symlink() for path in paths):
            return Err(MutationError("schema", "mutant corpus entry is a symlink"))
        entries = tuple(
            Entry(path.relative_to(root).as_posix(), "file", (path.read_bytes(),))
            for path in paths
        )
        rationale = root / "DEVELOPMENT_PLAN/rationale.md"
        if rationale.is_symlink():
            return Err(MutationError("schema", "amendment rationale is a symlink"))
        if rationale.exists():
            entries += (
                Entry(
                    "DEVELOPMENT_PLAN/rationale.md", "file", (rationale.read_bytes(),)
                ),
            )
    except OSError as exc:
        return Err(MutationError("schema", str(exc)))
    return census_corpus(entries)


def _census_entry_text(entry: Entry) -> Result[str, MutationError]:
    """Decode one regular census file without consulting the live tree."""
    match entry.kind, entry.payloads:
        case "file", (bytes() as payload,):
            try:
                return Ok(payload.decode("utf-8"))
            except UnicodeError as exc:
                return Err(MutationError("schema", str(exc)))
        case _:
            return Err(MutationError("schema", "census entry is not a regular file"))


def _census_rows(
    entry: Entry, rationale_entries: tuple[Entry, ...]
) -> Result[tuple[object, ...], MutationError]:
    """Parse one observed corpus document and apply its observed amendments."""
    content = _census_entry_text(entry)
    if isinstance(content, Err):
        return content
    try:
        document = tomllib.loads(content.value)
    except tomllib.TOMLDecodeError as exc:
        return Err(MutationError("schema", str(exc)))
    values = document.get("mutant")
    amendments = document.get("amendment", [])
    if (
        not {"mutant"} <= set(document) <= {"mutant", "amendment"}
        or not isinstance(values, list)
        or not values
        or not isinstance(amendments, list)
    ):
        message = (
            "nonempty mutant rows required"
            if not isinstance(values, list) or not values
            else "invalid corpus rows"
        )
        return Err(MutationError("schema", message))
    if not amendments:
        return Ok(tuple(values))
    if len(rationale_entries) != 1:
        return Err(MutationError("schema", "missing amendment rationale"))
    rationale = _census_entry_text(rationale_entries[0])
    return (
        _amend_all(tuple(values), amendments, rationale.value)
        if isinstance(rationale, Ok)
        else rationale
    )


def census_corpus(
    entries: tuple[Entry, ...],
) -> Result[tuple[Mutant, ...], MutationError]:
    """Parse corpus records and amendment provenance from one guarded census."""
    paths = tuple(entry.path for entry in entries)
    if len(paths) != len(set(paths)):
        return Err(MutationError("schema", "duplicate census path"))
    candidates = tuple(
        entry
        for entry in entries
        if PurePosixPath(entry.path).parent == PurePosixPath("tests/mutants")
        and entry.path.endswith(".toml")
    )
    rationale_entries = tuple(
        entry for entry in entries if entry.path == "DEVELOPMENT_PLAN/rationale.md"
    )
    records: tuple[Mutant, ...] = ()
    for entry in sorted(candidates):
        revised = _census_rows(entry, rationale_entries)
        if isinstance(revised, Err):
            return revised
        for value in revised.value:
            record = parse(value)
            if isinstance(record, Err):
                return record
            if any(
                previous.identifier == record.value.identifier for previous in records
            ):
                return Err(MutationError("schema", "duplicate mutant id"))
            records += (record.value,)
    return Ok(records) if records else Err(MutationError("schema", "empty corpus"))


def amend_records(
    values: list[object], amendments: object, root: Path
) -> Result[tuple[object, ...], MutationError]:
    """Apply content-bound amendments without changing protected original rows."""
    if not isinstance(amendments, list):
        return Err(MutationError("schema", "amendments must be an array"))
    result: tuple[object, ...] = tuple(values)
    if not amendments:
        return Ok(result)
    try:
        rationale = (root / "DEVELOPMENT_PLAN/rationale.md").read_text(encoding="utf-8")
    except OSError as exc:
        return Err(MutationError("schema", str(exc)))
    return _amend_all(result, amendments, rationale)


def _amend_all(
    result: tuple[object, ...], amendments: list[object], rationale: str
) -> Result[tuple[object, ...], MutationError]:
    """Apply a documented, content-bound sequence without changing old rows."""
    used = frozenset[tuple[str, str]]()
    for amendment in amendments:
        if (
            not isinstance(amendment, dict)
            or set(amendment)
            != {
                "id",
                "prior_sha256",
                "revised_sha256",
                "search",
                "replace",
                "provenance",
            }
            or not all(isinstance(value, str) for value in amendment.values())
        ):
            return Err(MutationError("schema", "invalid mutant amendment fields"))
        identifier = str(amendment["id"])
        provenance = str(amendment["provenance"])
        prior = str(amendment["prior_sha256"])
        if (
            (identifier, prior) in used
            or not re.fullmatch(r"decision:D-\d+", provenance)
            or not re.search(
                r"^\| "
                + re.escape(provenance.removeprefix("decision:"))
                + r" \|[^\n]*`"
                + re.escape(identifier)
                + r"`",
                rationale,
                re.MULTILINE,
            )
        ):
            return Err(
                MutationError("schema", "duplicate amendment or invalid provenance")
            )
        matches = tuple(
            value
            for value in result
            if isinstance(value, dict) and value.get("id") == identifier
        )
        if len(matches) != 1:
            return Err(
                MutationError(
                    "schema", "amendment must name exactly one original mutant"
                )
            )
        original = matches[0]
        validated = parse(original)
        if isinstance(validated, Err):
            return validated
        updated = {
            **original,
            "search": amendment["search"],
            "replace": amendment["replace"],
        }
        before = RowFact(
            identifier,
            json.dumps(original, sort_keys=True, ensure_ascii=True, allow_nan=False),
        )
        after = RowFact(
            identifier,
            json.dumps(updated, sort_keys=True, ensure_ascii=True, allow_nan=False),
        )
        binding = MutantAmendment(
            identifier, amendment["prior_sha256"], amendment["revised_sha256"]
        )
        if before.contents == after.contents or not mutant_amendment_matches(
            before, after, binding
        ):
            return Err(
                MutationError("schema", "mutant amendment content binding mismatch")
            )
        result = tuple(updated if value is original else value for value in result)
        used = used | {(identifier, prior)}
    return Ok(result)


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
        output = import_module("agentctl.check.haskell_mutants").killer(
            tree, node, current(paths.cache)
        )
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
    """Run every named killer and retain the complete record's verdict."""
    return killer_verdict(record, exercise_observed(tree, record, timeout=timeout))


def exercise_observed(
    tree: Path, record: Mutant, *, timeout: float = 120
) -> Result[tuple[KillerOutcome, ...], MutationError]:
    """Run named killers and expose their outcomes after scratch restoration."""
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
        return _exercise_killers(
            tree, Patch(target, original, changed.value), record, timeout
        )
    except OSError as exc:
        return Err(MutationError("patch", str(exc)))


def killer_verdict(
    record: Mutant,
    observed: Result[tuple[KillerOutcome, ...], MutationError],
) -> Result[None, MutationError]:
    """Fail the complete record if any named killer lacks a valid result."""
    match observed:
        case Err() as error:
            return error
        case Ok(detailed):
            if (
                not record.killers
                or tuple(item.node for item in detailed) != record.killers
                or any(
                    _passed(item.baseline) != (item.mutation is not None)
                    for item in detailed
                )
            ):
                return Err(
                    MutationError(
                        "schema", "incomplete or inconsistent killer outcomes"
                    )
                )
            failures = _outcome_failures(detailed)
            if not failures:
                return Ok(None)
            return Err(
                MutationError(
                    failures[0].stage, "\n".join(item.message for item in failures)
                )
            )


def _outcome_failures(outcomes: tuple[KillerOutcome, ...]) -> tuple[MutationError, ...]:
    """Keep failures in original killer and execution order."""
    return tuple(
        error
        for outcome in outcomes
        for value in (outcome.baseline, outcome.mutation)
        for error in _failure(value)
    )


def _failure(value: Result[None, MutationError] | None) -> tuple[MutationError, ...]:
    """Extract an actual failure without promoting an unrun mutation."""
    match value:
        case Err(error):
            return (error,)
        case Ok() | None:
            return ()


def _observed_killer(
    tree: Path, node: str, record: Mutant, timeout: float, *, mutated: bool
) -> Result[None, MutationError]:
    """Retain the named process, phase and output for one baseline or mutation."""
    match _killer(tree, node, timeout):
        case Err(error):
            return Err(
                MutationError(
                    error.stage, f"{record.identifier}: {node}: {error.message}"
                )
            )
        case Ok(output):
            verdict = (
                killed(output, record.reason)
                if mutated
                else baseline(output, record.reason)
            )
            match verdict:
                case Err(error):
                    return Err(
                        MutationError(
                            error.stage,
                            f"{record.identifier}: {node}: {error.message}\n"
                            f"{output.stdout}\n{output.stderr}",
                        )
                    )
                case Ok():
                    return Ok(None)


def _passed(value: Result[None, MutationError]) -> bool:
    """Only a passing baseline authorizes its corresponding mutant attempt."""
    match value:
        case Ok():
            return True
        case Err():
            return False


def _exercise_killers(
    tree: Path, prepared: Patch, record: Mutant, timeout: float
) -> Result[tuple[KillerOutcome, ...], MutationError]:
    """Observe every baseline and mutate only those whose own baseline passed.

    These values are local diagnostic outcomes, not authenticated phase receipts.
    Restoration is attempted in the original owned scratch tree on every exit.
    """
    try:
        outcomes = _run_killers(tree, prepared, record, timeout)
    except BaseException as primary:
        try:
            prepared.target.write_bytes(prepared.original)
        except OSError as cleanup:
            message = "mutation execution and restoration failed"
            raise BaseExceptionGroup(message, (primary, cleanup)) from None
        raise
    try:
        prepared.target.write_bytes(prepared.original)
    except OSError as cleanup:
        failures = _outcome_failures(outcomes)
        primary = "\n".join(item.message for item in failures)
        return Err(
            MutationError(
                failures[0].stage if failures else "patch",
                ("primary: " + primary + "; " if primary else "")
                + "mutation restoration: "
                + str(cleanup),
            )
        )
    return Ok(outcomes)


def _run_killers(
    tree: Path, prepared: Patch, record: Mutant, timeout: float
) -> tuple[KillerOutcome, ...]:
    """Observe every baseline before attempting its eligible mutation."""
    baselines = tuple(
        _observed_killer(tree, node, record, timeout, mutated=False)
        for node in record.killers
    )
    if any(_passed(value) for value in baselines):
        prepared.target.write_bytes(prepared.changed)
    return tuple(
        KillerOutcome(
            node,
            control,
            _observed_killer(tree, node, record, timeout, mutated=True)
            if _passed(control)
            else None,
        )
        for node, control in zip(record.killers, baselines, strict=True)
    )
