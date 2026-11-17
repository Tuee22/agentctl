# Copyright (c) 2026 agentctl contributors.
"""Independent immutable oracle rows, provenance and pure comparisons."""

import ast
import re
import tomllib
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

type Value = str | bool | int | float | tuple[Value, ...] | Object
TOOL_COLUMNS = 4


@dataclass(frozen=True, slots=True)
class Object:
    """An immutable object at the TOML and JSON comparison boundary."""

    items: tuple[tuple[str, Value], ...]


@dataclass(frozen=True, slots=True)
class Problem:
    """A rejected oracle input with its precise diagnostic."""

    message: str


@dataclass(frozen=True, slots=True)
class TreeIssue:
    """One oracle diagnostic and its source, or shared damage when unknown."""

    source: str | None
    message: str


@dataclass(frozen=True, slots=True)
class Row:
    """One preserved specification case and its source anchor."""

    identifier: str
    requirement: str
    quote: str
    provenance: str
    inputs: Value
    expected: Value
    amends: str = ""


@dataclass(frozen=True, slots=True)
class Store:
    """All rows plus the latest expectation in each amendment chain."""

    rows: tuple[Row, ...]
    effective: tuple[Row, ...]


@dataclass(frozen=True, slots=True)
class Homes:
    """Request quotes, recorded choices and versioned external facts."""

    requirements: tuple[tuple[str, str], ...]
    decisions: frozenset[str]
    tools: tuple[tuple[str, str], ...]


def freeze(value: object) -> Value | Problem:
    """Parse TOML-compatible JSON values into an immutable representation."""
    if isinstance(value, (str, bool, int, float)):
        return value
    if isinstance(value, list):
        values = tuple(freeze(item) for item in value)
        for item in values:
            if isinstance(item, Problem):
                return item
        return tuple(item for item in values if not isinstance(item, Problem))
    if isinstance(value, dict):
        return _object(value)
    return Problem("only TOML-compatible JSON values are accepted")


def _object(value: dict[object, object]) -> Object | Problem:
    """Validate object keys and recursively freeze their values."""
    fields: tuple[tuple[str, Value], ...] = ()
    for key, item in value.items():
        if not isinstance(key, str):
            return Problem("object keys must be strings")
        parsed = freeze(item)
        if isinstance(parsed, Problem):
            return parsed
        fields += ((key, parsed),)
    return Object(tuple(sorted(fields)))


def read_homes(
    root: Path, *, include_decisions: bool = True, include_tools: bool = True
) -> Homes:
    """Read requested anchor families without importing an implementation."""
    overview = (root / "DEVELOPMENT_PLAN/00-overview.md").read_text(encoding="utf-8")
    rationale = (
        (root / "DEVELOPMENT_PLAN/rationale.md").read_text(encoding="utf-8")
        if include_decisions
        else ""
    )
    external = (
        (root / "documents/reference/external_tool_facts.md").read_text(
            encoding="utf-8"
        )
        if include_tools
        else ""
    )
    requirements: tuple[tuple[str, str], ...] = tuple(
        (str(match[1]), str(match[2]))
        for match in re.finditer(
            r"^\| (R\d+(?:\.\d+)?) \|[^\n]+?\| `([^`]+)` \|", overview, re.MULTILINE
        )
    )
    decisions = frozenset(
        str(identifier)
        for identifier in re.findall(r"^\| (D-\d+) \|", rationale, re.MULTILINE)
    )
    tools = tuple(
        (cells[-3].strip(" `"), cells[0].strip())
        for line in external.splitlines()
        if line.startswith("| ")
        for cells in (re.split(r"(?<!\\)\|", line.strip("|")),)
        if len(cells) >= TOOL_COLUMNS
    )
    return Homes(requirements, decisions, tools)


def provenance_resolves(source: str, homes: Homes) -> bool:
    """Resolve only request ids, decision ids or versioned exact tool facts."""
    kind, _separator, reference = source.partition(":")
    match kind:
        case "request":
            return reference in dict(homes.requirements)
        case "decision":
            return reference in homes.decisions
        case "tool":
            version, separator, fact = reference.partition(":")
            return bool(separator and fact) and any(
                version == actual and fact in text for actual, text in homes.tools
            )
    return False


def _row(value: object, homes: Homes) -> Row | Problem:
    """Validate the closed row schema and both provenance anchors."""
    required = frozenset(
        {"id", "requirement", "quote", "provenance", "input", "expected"}
    )
    if (
        not isinstance(value, dict)
        or not required <= value.keys()
        or value.keys() - required - {"amends"}
    ):
        return Problem(
            "row schema requires id, requirement, quote, provenance, input, expected"
        )
    fields = tuple(
        value.get(name, "")
        for name in ("id", "requirement", "quote", "provenance", "amends")
    )
    if not all(isinstance(field, str) for field in fields):
        return Problem("row identity and provenance fields must be strings")
    identifier, requirement, quote, source, amends = (str(field) for field in fields)
    problem = _anchors(identifier, requirement, quote, source, homes)
    if problem is not None:
        return problem
    inputs, expected = freeze(value["input"]), freeze(value["expected"])
    if isinstance(inputs, Problem):
        return inputs
    if isinstance(expected, Problem):
        return expected
    return Row(identifier, requirement, quote, source, inputs, expected, amends)


def _anchors(
    identifier: str, requirement: str, quote: str, source: str, homes: Homes
) -> Problem | None:
    """Resolve a row's stable identity and independent source references."""
    if not re.fullmatch(r"[a-z][a-z0-9_.-]+", identifier):
        return Problem("row id must be stable lower-case text")
    if (
        requirement not in dict(homes.requirements)
        or not quote
        or quote not in dict(homes.requirements)[requirement]
    ):
        return Problem("quote must match its requirement")
    if not provenance_resolves(source, homes):
        return Problem("provenance does not resolve")
    return None


def _amendment(
    row: Row, previous: dict[str, Row], amended: frozenset[str]
) -> Problem | None:
    """Require one acyclic amendment chain per original requirement row."""
    if row.identifier in previous:
        return Problem("duplicate row id")
    if row.amends:
        if row.amends not in previous:
            return Problem("amendment must name a prior row; cycles are forbidden")
        prior = previous[row.amends]
        if prior.requirement != row.requirement or row.amends in amended:
            return Problem("amendment must extend one same-requirement chain")
    return None


def parse(document: object, homes: Homes) -> Store | Problem:
    """Preserve rows, requiring amendments to name an earlier same-id family."""
    if not isinstance(document, dict) or set(document) != {"case"}:
        return Problem("oracle must contain only case rows")
    cases = document["case"]
    if not isinstance(cases, list) or not cases:
        return Problem("empty oracle")
    rows: tuple[Row, ...] = ()
    amended = frozenset[str]()
    for value in cases:
        row = _row(value, homes)
        if isinstance(row, Problem):
            return row
        previous = {item.identifier: item for item in rows}
        problem = _amendment(row, previous, amended)
        if problem is not None:
            return problem
        if row.amends:
            amended = amended | {row.amends}
        rows += (row,)
    return Store(rows, tuple(row for row in rows if row.identifier not in amended))


def load(path: Path, homes: Homes) -> Store | Problem:
    """Parse oracle bytes at the filesystem boundary."""
    try:
        text = path.read_text(encoding="utf-8")
        data = tomllib.loads(text)
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        return Problem(str(exc))
    return parse(data, homes)


def load_scoped(path: Path, root: Path) -> Store | Problem:
    """Validate every row using exactly the anchor families those rows name."""
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        cases = data.get("case")
        if not isinstance(cases, list):
            return Problem("oracle must contain case rows")
        sources = frozenset(
            source.partition(":")[0]
            for case in cases
            if isinstance(case, dict)
            for source in (case.get("provenance"),)
            if isinstance(source, str)
        )
        homes = read_homes(
            root,
            include_decisions="decision" in sources,
            include_tools="tool" in sources,
        )
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        return Problem(str(exc))
    return parse(data, homes)


def imports_subject(source: str) -> bool:
    """Detect direct, aliased, relative and dynamic subject imports."""
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import) and any(
            alias.name.split(".")[0] == "agentctl" for alias in node.names
        ):
            return True
        if isinstance(node, ast.ImportFrom) and (
            node.level or (node.module or "").split(".")[0] == "agentctl"
        ):
            return True
        if isinstance(node, ast.Call) and (
            (isinstance(node.func, ast.Name) and node.func.id == "__import__")
            or (
                isinstance(node.func, ast.Attribute)
                and node.func.attr == "import_module"
            )
        ):
            return True
    return False


def check_tree(root: Path) -> tuple[str, ...]:
    """Apply oracles.independence to every live row and the comparison loader."""
    paths = tuple(sorted((root / "tests/oracles").glob("*.toml")))
    if not paths:
        return ("oracles.independence: empty oracle store",)
    problems: tuple[str, ...] = ()
    identifiers = frozenset[str]()
    for path in paths:
        result = load_scoped(path, root)
        if isinstance(result, Problem):
            problems += (f"oracles.independence: {path.name}: {result.message}",)
        else:
            own = frozenset(row.identifier for row in result.rows)
            if own & identifiers:
                problems += (
                    f"oracles.independence: {path.name}: duplicate row id across files",
                )
            identifiers = identifiers | own
    try:
        source = (root / "tests/harness/oracle.py").read_text(encoding="utf-8")
        if imports_subject(source):
            problems += ("oracles.independence: loader imports subject",)
    except (OSError, UnicodeError, SyntaxError) as exc:
        problems += ("oracles.independence: cannot inspect loader: " + str(exc),)
    return problems


def tree_observations(root: Path) -> tuple[tuple[str, ...], tuple[TreeIssue, ...]]:
    """Identify per-file oracle diagnostics without localizing ambiguous damage.

    The resulting observations do not authenticate the checkout, execution or
    ownership. Duplicate row IDs remain shared because both files are affected.
    """
    paths = tuple(
        sorted(
            path.relative_to(root).as_posix()
            for path in (root / "tests/oracles").glob("*.toml")
        )
    )
    issues: tuple[TreeIssue, ...] = ()
    for message in check_tree(root):
        sources = tuple(
            path
            for path in paths
            if message.startswith("oracles.independence: " + Path(path).name + ": ")
        )
        source = (
            sources[0]
            if len(sources) == 1 and "duplicate row id across files" not in message
            else None
        )
        issues += (TreeIssue(source, message),)
    return paths, issues


def assert_oracle[T, U](
    subject: Callable[[T], U], inputs: T, expected: U, *, row_id: str = "single"
) -> None:
    """Compare the subject's value with an independently supplied expectation."""
    assert subject(inputs) == expected, row_id


def assert_rows(subject: Callable[[Value], Value], store: Store) -> None:
    """Compare every effective row, with its stable id in a failure report."""
    assert store.effective, "empty oracle"
    for row in store.effective:
        assert_oracle(subject, row.inputs, row.expected, row_id=row.identifier)
