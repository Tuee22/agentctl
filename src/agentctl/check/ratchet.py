# Copyright (c) 2026 agentctl contributors.
"""Append-only governance data compared with the user's read-only HEAD."""

import json
import os
import re
import shutil
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from agentctl.process import Output, run
from agentctl.result import Err, Ok, Result

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
    if set(document) != {key} or not isinstance(values, list) or not values:
        return Err(RatchetError("malformed protected row document"))
    parsed: tuple[RowFact, ...] = ()
    for value in values:
        row = _row(value)
        if isinstance(row, Err):
            return row
        parsed += (row.value,)
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
    for filename in files.value.stdout.split("\0"):
        if filename:
            compared = _compare_file(root, revision.value, filename)
            if isinstance(compared, Err):
                return compared
    return Ok(revision.value)
