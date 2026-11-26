# Copyright (c) 2026 agentctl contributors.
"""Append-only governance data compared with the user's read-only HEAD."""

import hashlib
import json
import os
import re
import shutil
import stat
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from agentctl.foundation import Err, Ok, Result
from agentctl.foundation_process import Output, run

type ConfigValue = str | bool | int | float | tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RatchetError:
    """A malformed baseline, edited row or weakened configuration."""

    message: str


@dataclass(frozen=True, slots=True)
class RowFact:
    """A stable row identity and its canonical semantic contents."""

    identifier: str
    contents: str


@dataclass(frozen=True, slots=True)
class RowRelocation:
    """A content-bound proposal to move one protected mutant row."""

    identifier: str
    source: str
    destination: str
    sha256: str
    provenance: str


def relocation_problems(
    before: tuple[tuple[str, RowFact], ...],
    after: tuple[tuple[str, RowFact], ...],
    moves: tuple[RowRelocation, ...],
    rationale: str,
) -> tuple[str, ...]:
    """Check exact cross-file retention; this alone does not change the ratchet.

    The caller must independently establish the complete baseline and current
    file censuses and apply this alongside all other protected-data checks.
    """
    before_ids = tuple(row.identifier for _path, row in before)
    after_ids = tuple(row.identifier for _path, row in after)
    move_ids = tuple(move.identifier for move in moves)
    if (
        len(before_ids) != len(set(before_ids))
        or len(after_ids) != len(set(after_ids))
        or len(move_ids) != len(set(move_ids))
    ):
        return ("ambiguous protected mutant rows or relocations",)
    prior = {row.identifier: (path, row) for path, row in before}
    current = {row.identifier: (path, row) for path, row in after}
    proposed = {move.identifier: move for move in moves}
    problems: tuple[str, ...] = ()
    for identifier, (source, row) in prior.items():
        found = current.get(identifier)
        move = proposed.get(identifier)
        if found == (source, row) and move is None:
            continue
        if move is None or found is None:
            problems += ("missing or unapproved relocation: " + identifier,)
            continue
        destination, observed = found
        valid_paths = all(
            re.fullmatch(r"tests/mutants/[a-z0-9_-]+\.toml", path) is not None
            for path in (source, destination)
        )
        decision = re.fullmatch(r"decision:(D-\d+)", move.provenance)
        anchored = (
            decision is not None
            and re.search(
                r"^\| "
                + re.escape(decision[1])
                + r" \|[^\n]*`"
                + re.escape(_amendment_original(identifier))
                + r"`",
                rationale,
                re.MULTILINE,
            )
            is not None
        )
        if (
            not valid_paths
            or source == destination
            or (move.source, move.destination) != (source, destination)
            or observed != row
            or hashlib.sha256(row.contents.encode("utf-8")).hexdigest() != move.sha256
            or not anchored
        ):
            problems += ("invalid relocation: " + identifier,)
    problems += tuple(
        "unknown relocation: " + identifier
        for identifier in move_ids
        if identifier not in prior
    )
    return problems + _amendment_locations(prior, current)


def _amendment_original(identifier: str) -> str:
    """Recover the mutant identity from a protected amendment revision."""
    return identifier.removeprefix("amendment:").split(":", 1)[0]


def _amendment_locations(
    prior: dict[str, tuple[str, RowFact]], current: dict[str, tuple[str, RowFact]]
) -> tuple[str, ...]:
    """Keep every old and newly added amendment beside its record."""
    problems: tuple[str, ...] = ()
    for identifier in prior:
        if identifier.startswith("amendment:"):
            original = _amendment_original(identifier)
            if (
                original not in prior
                or original not in current
                or identifier not in current
            ):
                problems += ("orphan amendment: " + identifier,)
            elif (
                prior[identifier][0] != prior[original][0]
                or current[identifier][0] != current[original][0]
            ):
                problems += ("separated amendment: " + identifier,)
    for identifier in current:
        if identifier.startswith("amendment:") and identifier not in prior:
            original = _amendment_original(identifier)
            if original not in current:
                problems += ("orphan amendment: " + identifier,)
            elif current[identifier][0] != current[original][0]:
                problems += ("separated amendment: " + identifier,)
    return problems


@dataclass(frozen=True, slots=True)
class MutantAmendment:
    """An explicit binding between two protected mutant record versions."""

    identifier: str
    before_sha256: str
    after_sha256: str


def mutant_amendment_matches(
    before: RowFact, after: RowFact, amendment: MutantAmendment
) -> bool:
    """Check exact record hashes and preserve the defect's protected identity.

    A matching amendment is not a mutation kill or authority to bypass the
    append-only ratchet. The caller must separately validate its provenance and
    execute the named baseline and mutant controls.
    """
    if (
        before.identifier != after.identifier
        or before.identifier != amendment.identifier
        or hashlib.sha256(before.contents.encode("utf-8")).hexdigest()
        != amendment.before_sha256
        or hashlib.sha256(after.contents.encode("utf-8")).hexdigest()
        != amendment.after_sha256
    ):
        return False
    try:
        previous = json.loads(before.contents)
        current = json.loads(after.contents)
    except json.JSONDecodeError:
        return False
    if not isinstance(previous, dict) or not isinstance(current, dict):
        return False
    fields = {"id", "operator", "target", "search", "replace", "killers", "reason"}
    search, replacement = current.get("search"), current.get("replace")
    if (
        not isinstance(search, str)
        or not search
        or not isinstance(replacement, str)
        or not isinstance(previous.get("search"), str)
        or not previous["search"]
        or not isinstance(previous.get("replace"), str)
        or previous["search"] == previous["replace"]
        or not all(
            isinstance(current.get(name), str) and bool(current[name])
            for name in ("id", "operator", "target", "reason")
        )
        or not isinstance(current.get("killers"), list)
        or not current["killers"]
        or not all(isinstance(item, str) and item for item in current["killers"])
    ):
        return False
    return bool(
        set(previous) == fields
        and set(current) == fields
        and previous.get("id") == before.identifier
        and current.get("id") == after.identifier
        and all(
            previous[name] == current[name]
            for name in ("id", "operator", "target", "killers", "reason")
        )
        and search != replacement
    )


@dataclass(frozen=True, slots=True)
class Setting:
    """One typed configuration leaf and its full table path."""

    path: tuple[str, ...]
    value: ConfigValue


def append_only(
    before: tuple[RowFact, ...], after: tuple[RowFact, ...]
) -> tuple[str, ...]:
    """Require every protected identity to retain its original value."""
    current = {row.identifier: row.contents for row in after}
    return tuple(
        row.identifier for row in before if current.get(row.identifier) != row.contents
    )


def rows(
    text: str, kind: Literal["oracle", "mutant", "requirements"]
) -> Result[tuple[RowFact, ...], RatchetError]:
    """Parse protected row semantics at the TOML or Markdown boundary."""
    if kind == "requirements":
        block = re.search(
            r"^## Requirements\n([\s\S]*?)(?=^## |\Z)", text, re.MULTILINE
        )
        if block is None:
            return Err(RatchetError("missing requirements table"))
        found = tuple(
            RowFact(cells[0], json.dumps(cells))
            for line in block[1].splitlines()
            if re.match(r"^\| R\d", line)
            for cells in (tuple(cell.strip() for cell in line.strip("|").split("|")),)
        )
        return _unique(found)
    try:
        document = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        return Err(RatchetError(str(exc)))
    key = "case" if kind == "oracle" else "mutant"
    values = document.get(key)
    allowed = {key, "amendment"} if kind == "mutant" else {key}
    if (
        not {key} <= set(document) <= allowed
        or not isinstance(values, list)
        or not values
    ):
        return Err(RatchetError("malformed protected row document"))
    parsed: tuple[RowFact, ...] = ()
    for value in values:
        row = _row(value)
        if isinstance(row, Err):
            return row
        parsed += (row.value,)
    return _amendment_rows(parsed, document.get("amendment"))


def _amendment_rows(
    parsed: tuple[RowFact, ...], amendments: object
) -> Result[tuple[RowFact, ...], RatchetError]:
    """Include appended amendments in the protected record census."""
    if amendments is None:
        return _unique(parsed)
    if not isinstance(amendments, list) or not amendments:
        return Err(RatchetError("malformed protected amendments"))
    for value in amendments:
        amendment = _row(value)
        if isinstance(amendment, Err):
            return amendment
        identifier = "amendment:" + amendment.value.identifier
        if any(row.identifier == identifier for row in parsed):
            if (
                not isinstance(value, dict)
                or not isinstance(value.get("prior_sha256"), str)
                or re.fullmatch(r"[0-9a-f]{64}", value["prior_sha256"]) is None
            ):
                return Err(RatchetError("invalid amendment revision identity"))
            identifier += ":" + value["prior_sha256"]
        parsed += (RowFact(identifier, amendment.value.contents),)
    return _unique(parsed)


def _row(value: object) -> Result[RowFact, RatchetError]:
    """Convert a parsed record to a stable JSON comparison value."""
    if (
        not isinstance(value, dict)
        or not isinstance(value.get("id"), str)
        or not value["id"]
    ):
        return Err(RatchetError("protected row has no string id"))
    try:
        contents = json.dumps(value, sort_keys=True, ensure_ascii=True, allow_nan=False)
    except (TypeError, ValueError) as exc:
        return Err(RatchetError(str(exc)))
    return Ok(RowFact(str(value["id"]), contents))


def _unique(values: tuple[RowFact, ...]) -> Result[tuple[RowFact, ...], RatchetError]:
    """Reject empty or ambiguous protected row sets."""
    if not values or len({row.identifier for row in values}) != len(values):
        return Err(RatchetError("empty or duplicate protected row ids"))
    return Ok(values)


def _settings(
    value: object, path: tuple[str, ...]
) -> Result[tuple[Setting, ...], RatchetError]:
    """Parse only precise scalar and string-list configuration leaves."""
    if isinstance(value, (str, bool, int, float)):
        return Ok((Setting(path, value),))
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return Ok((Setting(path, tuple(str(item) for item in value)),))
    if not isinstance(value, dict):
        return Err(RatchetError("unsupported configuration value"))
    result: tuple[Setting, ...] = ()
    for key, item in value.items():
        parsed = _settings(item, (*path, str(key)))
        if isinstance(parsed, Err):
            return parsed
        result += parsed.value
    return Ok(result)


def configuration(text: str) -> Result[tuple[Setting, ...], RatchetError]:
    """Read the governed tool tables without including packaging metadata."""
    try:
        document = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        return Err(RatchetError(str(exc)))
    tools = document.get("tool")
    if not isinstance(tools, dict):
        return Err(RatchetError("missing governed configuration"))
    names = frozenset({"ruff", "ty", "pytest", "coverage"})
    if not names <= tools.keys():
        return Err(RatchetError("missing governed configuration tables"))
    return _settings({key: value for key, value in tools.items() if key in names}, ())


def _list_tightens(
    path: tuple[str, ...], before: tuple[str, ...], after: tuple[str, ...]
) -> bool:
    """Permit fewer ignores and a larger selected rule set."""
    if (
        path[-1] in {"ignore", "extend-ignore", "exclude", "extend-exclude"}
        or "per-file-ignores" in path
    ):
        return set(after) <= set(before)
    if path[-1] in {"select", "extend-select"}:
        return set(before) <= set(after)
    return before == after


def _tightens(before: Setting, after: Setting) -> bool:
    """Recognize only documented monotone scalar or rule-set changes."""
    first, second = before.value, after.value
    if type(first) is type(second) and first == second:
        return True
    if isinstance(first, tuple) and isinstance(second, tuple):
        return _list_tightens(before.path, first, second)
    if (
        before.path == ("coverage", "report", "fail_under")
        and isinstance(first, (int, float))
        and isinstance(second, (int, float))
    ):
        return second >= first
    if (
        before.path[:2] == ("ty", "rules")
        and isinstance(first, str)
        and isinstance(second, str)
    ):
        severity = {"ignore": 0, "warn": 1, "error": 2}
        return (
            first in severity
            and second in severity
            and severity[second] >= severity[first]
        )
    flags = {
        ("coverage", "run", "branch"): True,
        ("pytest", "strict"): True,
        ("ty", "terminal", "error-on-warning"): True,
        ("ty", "analysis", "respect-type-ignore-comments"): False,
    }
    return (
        before.path in flags
        and isinstance(first, bool)
        and isinstance(second, bool)
        and second == flags[before.path]
    )


def config_tightens(before: tuple[Setting, ...], after: tuple[Setting, ...]) -> bool:
    """Reject removal, unrecognised additions and every weakening leaf."""
    old = {setting.path: setting for setting in before}
    new = {setting.path: setting for setting in after}
    retained = all(
        path in new and _tightens(setting, new[path]) for path, setting in old.items()
    )
    additions = all(
        path[:2] == ("ty", "rules") and setting.value == "error"
        for path, setting in new.items()
        if path not in old
    )
    return retained and additions


def _git(root: Path, args: tuple[str, ...]) -> Result[Output, RatchetError]:
    """Use only read-only git operations on the requested checkout."""
    executable = shutil.which("git")
    if executable is None:
        return Err(RatchetError("git is required for the ratchet"))
    result = run([executable, *args], cwd=root, env=os.environ)
    return (
        Err(RatchetError(result.error.message)) if isinstance(result, Err) else result
    )


def head(root: Path) -> Result[str | None, RatchetError]:
    """Distinguish an unborn repository from an unreadable committed baseline."""
    revision = _git(root, ("rev-parse", "--verify", "HEAD^{commit}"))
    if isinstance(revision, Err):
        return revision
    if revision.value.code == 0:
        value = revision.value.stdout.strip()
        return (
            Ok(value)
            if re.fullmatch(r"[0-9a-f]{40}(?:[0-9a-f]{24})?", value)
            else Err(RatchetError("malformed HEAD object id"))
        )
    symbolic = _git(root, ("symbolic-ref", "-q", "HEAD"))
    if isinstance(symbolic, Err):
        return symbolic
    reference = symbolic.value.stdout.strip()
    if symbolic.value.code != 0 or not reference.startswith("refs/"):
        return Err(RatchetError("unreadable HEAD baseline"))
    existing = _git(root, ("show-ref", "--verify", "--quiet", reference))
    if isinstance(existing, Err):
        return existing
    return (
        Ok(None)
        if existing.value.code == 1
        else Err(RatchetError("unreadable HEAD baseline"))
    )


def _compare_file(
    root: Path, revision: str, filename: str
) -> Result[None, RatchetError]:
    """Compare one committed protected document to its current semantic rows."""
    original = _git(root, ("show", f"{revision}:{filename}"))
    if isinstance(original, Err):
        return original
    if original.value.code:
        return Err(RatchetError(f"cannot read baseline {filename}"))
    try:
        current = (root / filename).read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        return Err(RatchetError(str(exc)))
    if filename == "pyproject.toml":
        return _compare_config(original.value.stdout, current)
    return _compare_rows(original.value.stdout, current, filename)


def _compare_config(original: str, current: str) -> Result[None, RatchetError]:
    """Apply the monotone configuration comparison to parsed tool tables."""
    first, second = configuration(original), configuration(current)
    if isinstance(first, Err):
        return first
    if isinstance(second, Err):
        return second
    return (
        Ok(None)
        if config_tightens(first.value, second.value)
        else Err(RatchetError("configuration weakened against HEAD"))
    )


def _compare_rows(
    original: str, current: str, filename: str
) -> Result[None, RatchetError]:
    """Require the committed rows of one file to survive unchanged."""
    kind = (
        "requirements"
        if filename.endswith("00-overview.md")
        else ("oracle" if filename.startswith("tests/oracles/") else "mutant")
    )
    prior, live = rows(original, kind), rows(current, kind)
    if isinstance(prior, Err):
        return prior
    if isinstance(live, Err):
        return live
    changed = append_only(prior.value, live.value)
    return (
        Err(
            RatchetError(
                f"protected rows changed or deleted in {filename}: {', '.join(changed)}"
            )
        )
        if changed
        else Ok(None)
    )


def _relocations(root: Path) -> Result[tuple[RowRelocation, ...] | None, RatchetError]:
    """Read explicit relocation proposals without following a symlink."""
    path = root / "tests/mutant_relocations.toml"
    try:
        mode = path.lstat().st_mode
        if not stat.S_ISREG(mode):
            return Err(RatchetError("relocation manifest is not a regular file"))
        document = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return Ok(None)
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        return Err(RatchetError(str(exc)))
    values = document.get("relocation")
    if set(document) != {"relocation"} or not isinstance(values, list) or not values:
        return Err(RatchetError("invalid relocation manifest"))
    records: tuple[RowRelocation, ...] = ()
    for value in values:
        match value:
            case {
                "id": str() as identifier,
                "source": str() as source,
                "destination": str() as destination,
                "sha256": str() as digest,
                "provenance": str() as provenance,
                **extra,
            } if not extra:
                records += (
                    RowRelocation(identifier, source, destination, digest, provenance),
                )
            case _:
                return Err(RatchetError("invalid relocation record"))
    return Ok(records)


def _mutant_rows(
    root: Path, revision: str, filenames: tuple[str, ...]
) -> Result[tuple[tuple[str, RowFact], ...], RatchetError]:
    """Read all protected mutant rows from the selected read-only baseline."""
    result: tuple[tuple[str, RowFact], ...] = ()
    for filename in filenames:
        content = _git(root, ("show", f"{revision}:{filename}"))
        if isinstance(content, Err):
            return content
        if content.value.code:
            return Err(RatchetError("cannot read baseline " + filename))
        parsed = rows(content.value.stdout, "mutant")
        if isinstance(parsed, Err):
            return parsed
        result += tuple((filename, row) for row in parsed.value)
    return Ok(result)


def _current_mutant_rows(
    root: Path,
) -> Result[tuple[tuple[str, RowFact], ...], RatchetError]:
    """Read every live corpus TOML entry without following symlinks."""
    try:
        with os.scandir(root / "tests/mutants") as directory:
            paths = tuple(
                sorted(
                    Path(entry.path)
                    for entry in directory
                    if entry.name.endswith(".toml")
                )
            )
        result: tuple[tuple[str, RowFact], ...] = ()
        for path in paths:
            if not stat.S_ISREG(path.lstat().st_mode):
                return Err(RatchetError("mutant corpus entry is not a regular file"))
            parsed = rows(path.read_text(encoding="utf-8"), "mutant")
            if isinstance(parsed, Err):
                return parsed
            result += tuple(
                (path.relative_to(root).as_posix(), row) for row in parsed.value
            )
        return Ok(result)
    except (OSError, UnicodeError) as exc:
        return Err(RatchetError(str(exc)))


def _compare_relocations(
    root: Path,
    revision: str,
    filenames: tuple[str, ...],
    moves: tuple[RowRelocation, ...],
) -> Result[None, RatchetError]:
    """Compare complete baseline and live corpora with documented exact moves."""
    baseline = _mutant_rows(root, revision, filenames)
    current = _current_mutant_rows(root)
    if isinstance(baseline, Err):
        return baseline
    if isinstance(current, Err):
        return current
    path = root / "DEVELOPMENT_PLAN/rationale.md"
    try:
        if not stat.S_ISREG(path.lstat().st_mode):
            return Err(RatchetError("relocation rationale is not a regular file"))
        rationale = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        return Err(RatchetError(str(exc)))
    problems = relocation_problems(baseline.value, current.value, moves, rationale)
    return Err(RatchetError("; ".join(problems))) if problems else Ok(None)


def _compare_files(
    root: Path, revision: str, names: tuple[str, ...]
) -> Result[None, RatchetError]:
    """Apply relocations and retain all other protected-file comparisons."""
    relocations = _relocations(root)
    if isinstance(relocations, Err):
        return relocations
    mutant_files = tuple(
        filename
        for filename in names
        if filename.startswith("tests/mutants/") and filename.endswith(".toml")
    )
    if relocations.value is not None:
        moved = _compare_relocations(root, revision, mutant_files, relocations.value)
        if isinstance(moved, Err):
            return moved
    for filename in names:
        if relocations.value is not None and filename in mutant_files:
            continue
        compared = _compare_file(root, revision, filename)
        if isinstance(compared, Err):
            return compared
    return Ok(None)


def check(root: Path) -> Result[str, RatchetError]:
    """Ratchet existing governance data against HEAD, reporting its baseline."""
    revision = head(root)
    if isinstance(revision, Err):
        return revision
    if revision.value is None:
        return Ok("no baseline")
    files = _git(
        root,
        (
            "ls-tree",
            "-r",
            "--name-only",
            "-z",
            revision.value,
            "--",
            "tests/oracles",
            "tests/mutants",
            "DEVELOPMENT_PLAN/00-overview.md",
            "pyproject.toml",
        ),
    )
    if isinstance(files, Err):
        return files
    if files.value.code:
        return Err(RatchetError("cannot list baseline files"))
    names = tuple(filename for filename in files.value.stdout.split("\0") if filename)
    compared = _compare_files(root, revision.value, names)
    return compared if isinstance(compared, Err) else Ok(revision.value)
