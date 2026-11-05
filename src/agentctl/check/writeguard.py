# Copyright (c) 2026 agentctl contributors.
"""Snapshots of the checkout, refs, installed distributions and owned observers."""

import csv
import hashlib
import importlib.metadata
import json
import os
import shutil
import stat
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from io import StringIO
from pathlib import Path

from agentctl.paths import Family
from agentctl.process import alive, run
from agentctl.result import Err, Ok, Result

RECORD_COLUMNS = 3


@dataclass(frozen=True, slots=True)
class GuardError:
    """An unreadable subject or changed run-integrity boundary."""

    message: str


@dataclass(frozen=True, slots=True, order=True)
class FileFact:
    """Stable entry identity, kind, size, permissions and content digest."""

    path: str
    kind: str
    size: int
    mode: int
    digest: str


@dataclass(frozen=True, slots=True)
class Snapshot:
    """The immutable inputs whose equality a check run preserves."""

    tree: tuple[FileFact, ...]
    refs: tuple[FileFact, ...]
    environment: tuple[FileFact, ...]


def link_text(path: Path) -> bytes:
    """Preserve literal link text at the single approved raw-reader boundary."""
    return os.readlink(path).encode("utf-8")


def _fact(path: Path, label: str) -> FileFact:
    """Read one filesystem entry without following a directory symlink."""
    metadata = path.lstat()
    if path.is_symlink():
        payload = link_text(path)
        kind = "symlink"
    elif path.is_dir():
        payload = b""
        kind = "directory"
    elif stat.S_ISREG(metadata.st_mode):
        payload = path.read_bytes()
        kind = "file"
    else:
        payload = b""
        kind = f"special:{stat.S_IFMT(metadata.st_mode)}"
    return FileFact(
        label,
        kind,
        len(payload),
        stat.S_IMODE(metadata.st_mode),
        hashlib.sha256(payload).hexdigest(),
    )


def tree(root: Path) -> Result[tuple[FileFact, ...], GuardError]:
    """Walk ignored and untracked entries, pruning only the root .git."""
    try:
        facts = (_fact(root, "."),)
        for current, directories, files in os.walk(root, onerror=_walk_error):
            directory = Path(current)
            directories[:] = sorted(
                name for name in directories if directory != root or name != ".git"
            )
            for name in (*directories, *sorted(files)):
                path = directory / name
                if path != root / ".git":
                    facts += (_fact(path, path.relative_to(root).as_posix()),)
    except OSError as exc:
        return Err(GuardError(str(exc)))
    return Ok(tuple(sorted(facts)))


def _walk_error(error: OSError) -> None:
    """Turn an unreadable subtree into the snapshot adapter's typed failure."""
    raise error


def refs(root: Path) -> Result[tuple[FileFact, ...], GuardError]:
    """Observe this checkout's git identity, HEAD, refs and packed refs."""
    git = shutil.which("git")
    if git is None:
        return Err(GuardError("git is required for the ref snapshot"))
    facts: tuple[FileFact, ...] = ()
    for flag in ("--git-dir", "--git-common-dir"):
        result = run([git, "rev-parse", flag], cwd=root, env=os.environ)
        if isinstance(result, Err):
            return Err(GuardError(result.error.message))
        if result.value.code:
            return Err(GuardError(result.value.stderr))
        directory = (root / result.value.stdout.strip()).resolve()
        identity = str(directory).encode("utf-8")
        facts += (
            FileFact(
                flag, "git-dir", len(identity), 0, hashlib.sha256(identity).hexdigest()
            ),
        )
        try:
            paths = (
                directory / "HEAD",
                directory / "packed-refs",
                *sorted((directory / "refs").rglob("*")),
            )
            facts += tuple(
                _fact(path, flag + "/" + path.relative_to(directory).as_posix())
                for path in paths
                if path.is_file()
            )
        except OSError as exc:
            return Err(GuardError(str(exc)))
    return Ok(tuple(sorted(facts)))


def recorded_files(text: str) -> Result[tuple[str, ...], GuardError]:
    """Read raw RECORD rows, including paths importlib would filter as missing."""
    try:
        rows = tuple(csv.reader(StringIO(text), strict=True))
    except csv.Error as exc:
        return Err(GuardError(str(exc)))
    if not rows or any(len(row) != RECORD_COLUMNS or not row[0] for row in rows):
        return Err(GuardError("invalid or empty distribution RECORD"))
    names = tuple(row[0] for row in rows)
    return (
        Ok(names)
        if len(set(names)) == len(names)
        else Err(GuardError("duplicate distribution RECORD path"))
    )


def _distribution(
    distribution: importlib.metadata.Distribution,
) -> Result[tuple[FileFact, ...], GuardError]:
    """Read metadata bytes and every literal recorded file from one distribution."""
    metadata = distribution.metadata
    name: object = metadata.get("Name")
    version: object = metadata.get("Version")
    if not isinstance(name, str) or not isinstance(version, str):
        return Err(GuardError("distribution metadata has no name or version"))
    raw = distribution.read_text("METADATA")
    record = distribution.read_text("RECORD")
    if raw is None or record is None:
        return Err(GuardError(f"distribution {name} has no METADATA or RECORD"))
    parsed = recorded_files(record)
    if isinstance(parsed, Err):
        return parsed
    facts = (
        FileFact(name, "distribution", 0, 0, version),
        *tuple(
            FileFact(
                name + "::" + label,
                "metadata",
                len(value.encode("utf-8")),
                0,
                hashlib.sha256(value.encode("utf-8")).hexdigest(),
            )
            for label, value in (("METADATA", raw), ("RECORD", record))
        ),
    )
    for filename in parsed.value:
        path = distribution.locate_file(filename)
        if not isinstance(path, Path):
            return Err(
                GuardError(f"distribution {name} is not stored as filesystem files")
            )
        facts += (_fact(path, name + "/" + filename),)
    return Ok(facts)


def environment(
    paths: Sequence[str] | None = None,
) -> Result[tuple[FileFact, ...], GuardError]:
    """Hash distribution metadata and every file each RECORD identifies."""
    facts: tuple[FileFact, ...] = ()
    try:
        for distribution in importlib.metadata.distributions(
            path=list(sys.path) if paths is None else list(paths)
        ):
            observed = _distribution(distribution)
            if isinstance(observed, Err):
                return observed
            facts += observed.value
    except (OSError, UnicodeError) as exc:
        return Err(GuardError(str(exc)))
    return (
        Ok(tuple(sorted(facts)))
        if facts
        else Err(GuardError("empty installed environment"))
    )


def snapshot(root: Path) -> Result[Snapshot, GuardError]:
    """Capture all subject boundaries before any validating tool runs."""
    checkout, git, installed = tree(root), refs(root), environment()
    if isinstance(checkout, Err):
        return checkout
    if isinstance(git, Err):
        return git
    if isinstance(installed, Err):
        return installed
    return Ok(Snapshot(checkout.value, git.value, installed.value))


def compare(before: Snapshot, after: Snapshot) -> tuple[str, ...]:
    """Report each changed boundary independently."""
    return tuple(
        name
        for name, first, second in (
            ("tree", before.tree, after.tree),
            ("refs", before.refs, after.refs),
            ("environment", before.environment, after.environment),
        )
        if first != second
    )


def socket_check(modes: tuple[int, ...]) -> Result[None, GuardError]:
    """Classify observed entry modes independently of host socket availability."""
    return (
        Err(GuardError("private server socket is still present"))
        if any(stat.S_ISSOCK(mode) for mode in modes)
        else Ok(None)
    )


def containment(run_dir: Path, nonce: str, family: Family) -> Result[None, GuardError]:
    """Reject a registered live observer or a leftover private server socket."""
    try:
        for path in sorted((run_dir / "observers").glob("*.json")):
            observed = _observer(path, nonce, family)
            if isinstance(observed, Err):
                return observed
        modes = tuple(path.lstat().st_mode for path in run_dir.rglob("*"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return Err(GuardError(str(exc)))
    return socket_check(modes)


def _observer(path: Path, nonce: str, family: Family) -> Result[None, GuardError]:
    """Validate one nonce-bound observer record and query only its pid."""
    data: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return Err(GuardError("observer record must be an object"))
    observed_nonce: object = data.get("nonce")
    if not isinstance(observed_nonce, str) or not (
        observed_nonce == nonce or observed_nonce.startswith(nonce + ".")
    ):
        return Err(GuardError("observer nonce mismatch"))
    pid: object = data.get("pid")
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
        return Err(GuardError("invalid observer pid"))
    state = alive(family, pid)
    if isinstance(state, Err):
        return Err(GuardError(state.error.message))
    return (
        Err(GuardError(f"observer pid {pid} is still alive"))
        if state.value
        else Ok(None)
    )
