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

from agentctl.foundation import Err, Family, Ok, Result
from agentctl.foundation_process import run
from agentctl.foundation_process_identity import alive, process_birth

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
    """Observe this checkout's Git identity, index, HEAD and refs."""
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
    index_facts = _index(root, git)
    if isinstance(index_facts, Err):
        return index_facts
    return Ok(tuple(sorted((*facts, *index_facts.value))))


def _index(root: Path, git: str) -> Result[tuple[FileFact, ...], GuardError]:
    """Observe the path Git actually uses, including an absent index."""
    index_result = run(
        [git, "rev-parse", "--git-path", "index"], cwd=root, env=os.environ
    )
    if isinstance(index_result, Err):
        return Err(GuardError(index_result.error.message))
    if index_result.value.code:
        return Err(GuardError(index_result.value.stderr))
    index_name = index_result.value.stdout.strip()
    if not index_name:
        return Err(GuardError("git returned an empty index path"))
    try:
        index_path = (root / index_name).resolve()
        identity = str(index_path).encode("utf-8")
        facts = (
            FileFact(
                "--index-path",
                "git-index-path",
                len(identity),
                0,
                hashlib.sha256(identity).hexdigest(),
            ),
        )
    except (OSError, RuntimeError) as exc:
        return Err(GuardError(str(exc)))
    contents = _index_entry(index_path)
    if isinstance(contents, Err):
        return contents
    return Ok(tuple(sorted((*facts, *contents.value))))


def _index_entry(index_path: Path) -> Result[tuple[FileFact, ...], GuardError]:
    """Only a missing path is absence; unreadable or nonregular indexes fail."""
    facts: tuple[FileFact, ...] = ()
    try:
        metadata = index_path.stat()
    except FileNotFoundError:
        return Ok(facts)
    except OSError as exc:
        return Err(GuardError(str(exc)))
    try:
        if stat.S_ISREG(metadata.st_mode):
            facts += (_fact(index_path, "--index"),)
        else:
            return Err(GuardError("git index is not a regular file"))
    except OSError as exc:
        return Err(GuardError(str(exc)))
    return Ok(facts)


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


def filesystem_path(run_dir: Path) -> Path:
    """Use Windows extended paths so deep owned entries remain observable."""
    if os.name != "nt":
        return run_dir
    absolute = str(run_dir.resolve())
    if absolute.startswith("\\\\?\\"):
        return Path(absolute)
    if absolute.startswith("\\\\"):
        return Path("\\\\?\\UNC\\" + absolute[2:])
    return Path("\\\\?\\" + absolute)


def containment(run_dir: Path, nonce: str, family: Family) -> Result[None, GuardError]:
    """Reject a registered live observer or a leftover private server socket."""
    try:
        root = filesystem_path(run_dir)
        modes: tuple[int, ...] = ()
        for current, directories, files in os.walk(root, onerror=_walk_error):
            directory = Path(current)
            modes += tuple(
                (directory / name).lstat().st_mode for name in (*directories, *files)
            )
            if directory == root and "observers" in files:
                return Err(GuardError("observer directory is not a directory"))
            if (
                directory == root
                and "observers" in directories
                and (root / "observers").is_symlink()
            ):
                return Err(GuardError("observer directory is a symlink"))
            if directory == root / "observers":
                for name in sorted(name for name in files if name.endswith(".json")):
                    observed = _observer(directory / name, nonce, family)
                    if isinstance(observed, Err):
                        return observed
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return Err(GuardError(str(exc)))
    return socket_check(modes)


def same_process_birth(recorded: int, actual: int | None) -> bool:
    """Compare a captured process birth with a current native observation."""
    return recorded == actual


def _observer_identity(
    data: dict[object, object], pid: int, family: Family
) -> Result[bool, GuardError]:
    """Compare a registered native process birth when the record contains one."""
    if "birth" not in data:
        return Ok(value=True)
    birth: object = data["birth"]
    if (
        family not in {"Windows", "Linux"}
        or not isinstance(birth, int)
        or isinstance(birth, bool)
        or birth <= 0
    ):
        return Err(GuardError("invalid observer process identity"))
    actual = process_birth(family, pid)
    if isinstance(actual, Err):
        return Err(GuardError(actual.error.message))
    return Ok(same_process_birth(birth, actual.value))


def _observer_liveness(
    data: dict[object, object], pid: int, family: Family
) -> Result[None, GuardError]:
    """Reject a still-live process only when its registered identity matches."""
    identity = _observer_identity(data, pid, family)
    if isinstance(identity, Err):
        return identity
    if not identity.value:
        return Ok(None)
    state = alive(family, pid)
    if isinstance(state, Err):
        return Err(GuardError(state.error.message))
    return (
        Err(GuardError(f"observer pid {pid} is still alive"))
        if state.value
        else Ok(None)
    )


def _observer(path: Path, nonce: str, family: Family) -> Result[None, GuardError]:
    """Validate one nonce-bound observer record and query its native identity."""
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
    return _observer_liveness(data, pid, family)
