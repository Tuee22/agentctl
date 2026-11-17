# Copyright (c) 2026 agentctl contributors.
"""Compare live process descendants with one private cgroup's members."""

import os
import re
from itertools import accumulate, pairwise
from pathlib import Path, PurePosixPath

from agentctl.check.wsl_budget import WorkloadBudget
from agentctl.check.wsl_cgroup import (
    ProcessIdentity,
    ProcessLimits,
    limit_problems,
    observe,
    process_identity,
)
from agentctl.check.wsl_mount import observe as observe_mount
from agentctl.foundation import Err, Ok, Result

MAX_PID = 2**31 - 1


def _walk_error(error: OSError) -> None:
    """Preserve an unreadable cgroup subtree as a failed observation."""
    raise error


def descendants(
    root: int, rows: tuple[ProcessIdentity, ...]
) -> Result[tuple[ProcessIdentity, ...], str]:
    """Compute a bounded immutable parent closure from one process snapshot."""
    identifiers = tuple(row.pid for row in rows)
    if (
        isinstance(root, bool)
        or root <= 0
        or root not in identifiers
        or len(set(identifiers)) != len(identifiers)
        or any(row.pid <= 0 or row.parent < 0 or row.starttime <= 0 for row in rows)
    ):
        return Err("invalid process tree snapshot")
    states = accumulate(
        rows,
        lambda parents, _row: (
            parents | frozenset(row.pid for row in rows if row.parent in parents)
        ),
        initial=frozenset({root}),
    )
    included = next(
        (after for before, after in pairwise(states) if before == after), frozenset()
    )
    if not included:
        return Err("process closure did not converge")
    selected = tuple(
        sorted((row for row in rows if row.pid in included), key=lambda row: row.pid)
    )
    root_row = next(row for row in selected if row.pid == root)
    if root_row.parent in included:
        return Err("cyclic process tree snapshot")
    return Ok(selected)


def _processes(proc: Path) -> Result[tuple[ProcessIdentity, ...], str]:
    """Read every process identity; unreadable or disappearing stat is a failure."""
    rows: tuple[ProcessIdentity, ...] = ()
    for directory in sorted(proc.iterdir()):
        if re.fullmatch(r"[1-9][0-9]*", directory.name) is None:
            continue
        if len(directory.name) > len(str(MAX_PID)) or int(directory.name) > MAX_PID:
            return Err("process id exceeds observation bound")
        if directory.is_symlink() or not directory.resolve(strict=True).is_relative_to(
            proc
        ):
            return Err("process path escaped proc root")
        identity = process_identity(
            (directory / "stat").read_text(encoding="utf-8", errors="surrogateescape"),
            int(directory.name),
        )
        if isinstance(identity, Err):
            return identity
        rows += (identity.value,)
    return Ok(rows)


def processes(proc_root: Path) -> Result[tuple[ProcessIdentity, ...], str]:
    """Observe a process table without claiming its mount origin is authentic."""
    try:
        return _processes(proc_root.resolve(strict=True))
    except (OSError, UnicodeError, RuntimeError, ValueError) as exc:
        return Err("cannot observe process table: " + str(exc))


def _tree(proc: Path, root: int) -> Result[tuple[ProcessIdentity, ...], str]:
    """Derive the root's descendant closure from a complete process table."""
    rows = _processes(proc)
    return rows if isinstance(rows, Err) else descendants(root, rows.value)


def _scope(cgroup: Path, scope: str) -> Result[Path, str]:
    """Resolve a non-root scope without accepting path or filesystem aliases."""
    path = PurePosixPath(scope)
    if (
        not path.is_absolute()
        or path.as_posix() != scope
        or scope == "/"
        or ".." in path.parts
    ):
        return Err("invalid owned cgroup scope")
    unresolved = cgroup / path.relative_to("/")
    boundary = unresolved.resolve(strict=True)
    if (
        boundary != unresolved
        or not boundary.is_relative_to(cgroup)
        or not boundary.is_dir()
    ):
        return Err("cgroup scope escaped observation root")
    return Ok(boundary)


def _members(cgroup: Path, scope: str) -> Result[frozenset[int], str]:
    """Read every cgroup.procs file under a canonical owned scope, without links."""
    selected = _scope(cgroup, scope)
    if isinstance(selected, Err):
        return selected
    identifiers: tuple[int, ...] = ()
    for current, directories, _files in os.walk(
        selected.value, onerror=_walk_error, followlinks=False
    ):
        directory = Path(current)
        if any((directory / name).is_symlink() for name in directories):
            return Err("cgroup subtree contains a symlink")
        procs = directory / "cgroup.procs"
        if procs.is_symlink() or not procs.is_file():
            return Err("cgroup member list unavailable")
        lines = procs.read_text(encoding="ascii").splitlines()
        if any(
            re.fullmatch(r"[1-9][0-9]*", line) is None
            or len(line) > len(str(MAX_PID))
            or int(line) > MAX_PID
            for line in lines
        ):
            return Err("invalid cgroup member id")
        identifiers += tuple(int(line) for line in lines)
    if len(set(identifiers)) != len(identifiers):
        return Err("duplicate cgroup member id")
    return Ok(frozenset(identifiers))


def _limits(
    rows: tuple[ProcessIdentity, ...], proc: Path, cgroup: Path, scope: str
) -> Result[tuple[ProcessLimits, ...], str]:
    """Observe every selected PID and require its original start identity."""
    results: tuple[ProcessLimits, ...] = ()
    for row in rows:
        sample = observe(row.pid, proc, cgroup, scope)
        if isinstance(sample, Err):
            return Err(f"process {row.pid}: " + sample.error)
        if sample.value.starttime != row.starttime:
            return Err(f"process {row.pid}: identity changed")
        results += (sample.value,)
    return Ok(results)


def _repeat(
    proc: Path,
    cgroup: Path,
    scope: str,
    root_pid: int,
    before: tuple[tuple[ProcessIdentity, ...], frozenset[int]],
) -> Result[None, str]:
    """Refuse changed process identities or changed cgroup membership."""
    after_members = _members(cgroup, scope)
    after_tree = _tree(proc, root_pid)
    if isinstance(after_members, Err) or isinstance(after_tree, Err):
        return Err("cannot repeat process tree or cgroup observation")
    if before[0] != after_tree.value or before[1] != after_members.value:
        return Err("process tree or cgroup membership changed")
    return Ok(None)


def _observe_tree(
    root_pid: int, proc: Path, cgroup: Path, scope: str
) -> Result[tuple[ProcessLimits, ...], str]:
    """Join each member's stable limits to repeated tree and cgroup observations."""
    first = _tree(proc, root_pid)
    if isinstance(first, Err):
        return first
    members = _members(cgroup, scope)
    if isinstance(members, Err):
        return members
    if members.value != frozenset(row.pid for row in first.value):
        return Err("cgroup members differ from process descendants")
    limits = _limits(first.value, proc, cgroup, scope)
    if isinstance(limits, Err):
        return limits
    repeated = _repeat(proc, cgroup, scope, root_pid, (first.value, members.value))
    return repeated if isinstance(repeated, Err) else limits


def observe_tree(
    root_pid: int, proc_root: Path, cgroup_root: Path, scope: str
) -> Result[tuple[ProcessLimits, ...], str]:
    """Compare two process snapshots, two cgroup listings and all member limits.

    This is a point-in-time observation, not proof of mount provenance or of
    processes which escaped before or between samples; a live watcher is required.
    """
    try:
        proc, cgroup = proc_root.resolve(strict=True), cgroup_root.resolve(strict=True)
        result = _observe_tree(root_pid, proc, cgroup, scope)
    except (OSError, UnicodeError, RuntimeError, ValueError) as exc:
        return Err("cannot observe cgroup process tree: " + str(exc))
    else:
        return result


def observe_native(
    root_pid: int, cgroup_root: Path, scope: str
) -> Result[tuple[ProcessLimits, ...], str]:
    """Bracket tree observation with native proc and cgroup mount identity.

    The caller still must establish root PID ownership, continuous process
    coverage and the resource budget before treating this as run evidence.
    """
    before = observe_mount(cgroup_root)
    if isinstance(before, Err):
        return before
    sampled = observe_tree(root_pid, Path("/proc"), cgroup_root, scope)
    after = observe_mount(cgroup_root)
    failures = (
        *(("process tree: " + sampled.error,) if isinstance(sampled, Err) else ()),
        *(("mount reobservation: " + after.error,) if isinstance(after, Err) else ()),
        *(
            ("proc or cgroup mount changed",)
            if isinstance(after, Ok) and before.value != after.value
            else ()
        ),
    )
    if failures:
        return Err("; ".join(failures))
    return sampled


def tree_problems(
    observed: tuple[ProcessLimits, ...],
    budget: WorkloadBudget,
    allowed_cpus: frozenset[int],
) -> tuple[str, ...]:
    """Check every observed member against the selected limits and affinity."""
    if (
        not observed
        or len({item.pid for item in observed}) != len(observed)
        or any(
            isinstance(item.pid, bool)
            or isinstance(item.starttime, bool)
            or item.pid <= 0
            or item.starttime <= 0
            for item in observed
        )
    ):
        return ("invalid observed process set",)
    return tuple(
        f"process {item.pid}: {problem}"
        for item in observed
        for problem in limit_problems(item, budget, allowed_cpus)
    )
