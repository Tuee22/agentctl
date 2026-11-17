# Copyright (c) 2026 agentctl contributors.
"""Read one Linux process's effective hierarchical cgroup v2 limits."""

import re
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path, PurePosixPath

from agentctl.check.wsl_budget import MILLIS_PER_CPU, WorkloadBudget
from agentctl.foundation import Err, Ok, Result

MAX_CPUS = 65536
STAT_STARTTIME_INDEX = 19
MAX_KERNEL_NUMBER_DIGITS = 20
MAX_KERNEL_NUMBER = 2**64 - 1
RANGE_FIELDS = 2
QUOTA_FIELDS = 2
STAT_PARENT_INDEX = 1


@dataclass(frozen=True, slots=True)
class ProcessIdentity:
    """A kernel PID, parent PID and start time, before cgroup attribution."""

    pid: int
    parent: int
    starttime: int


@dataclass(frozen=True, slots=True)
class ProcessLimits:
    """Stable observations for one PID, not proof of a complete process tree."""

    pid: int
    starttime: int
    group: str
    cpus: frozenset[int]
    cpu_quota: Fraction
    memory_max: int
    swap_max: int


@dataclass(frozen=True, slots=True)
class _Raw:
    """One complete sample of identity, membership, affinity and ancestor files."""

    starttime: int
    group: str
    cpus: frozenset[int]
    limits: tuple[tuple[str, str, str], ...]


def limit_problems(
    observed: ProcessLimits, budget: WorkloadBudget, allowed_cpus: frozenset[int]
) -> tuple[str, ...]:
    """Compare one observed process to selected upper bounds and CPU affinity."""
    return (
        *(
            ("process CPU limit exceeds budget",)
            if observed.cpu_quota <= 0
            or observed.cpu_quota > Fraction(budget.cpu_millis, MILLIS_PER_CPU)
            else ()
        ),
        *(
            ("process affinity exceeds budget",)
            if not allowed_cpus
            or not observed.cpus
            or not observed.cpus <= allowed_cpus
            else ()
        ),
        *(
            ("process memory limit exceeds budget",)
            if observed.memory_max <= 0 or observed.memory_max > budget.memory
            else ()
        ),
        *(
            ("process swap limit exceeds budget",)
            if observed.swap_max < 0 or observed.swap_max > budget.swap
            else ()
        ),
    )


def cpu_list(text: str) -> Result[frozenset[int], str]:
    """Parse bounded Linux CPU lists without accepting duplicates or aliases."""
    fields = text.strip().split(",")
    if not fields or any(
        re.fullmatch(r"(?:0|[1-9][0-9]*)(?:-(?:0|[1-9][0-9]*))?", item) is None
        for item in fields
    ):
        return Err("invalid CPU list")
    if any(
        len(value) > len(str(MAX_CPUS)) for item in fields for value in item.split("-")
    ):
        return Err("CPU list exceeds observation bound")
    ranges = tuple(tuple(int(value) for value in item.split("-")) for item in fields)
    if any(len(item) == RANGE_FIELDS and item[0] > item[1] for item in ranges):
        return Err("invalid CPU range")
    size = sum((item[-1] - item[0] + 1) for item in ranges)
    if size > MAX_CPUS or any(item[-1] >= MAX_CPUS for item in ranges):
        return Err("CPU list exceeds observation bound")
    cpus = frozenset(value for item in ranges for value in range(item[0], item[-1] + 1))
    return Ok(cpus) if len(cpus) == size and cpus else Err("duplicate CPU list entry")


def _group(text: str) -> Result[str, str]:
    """Accept exactly one canonical unified-hierarchy membership line."""
    values = tuple(line[3:] for line in text.splitlines() if line.startswith("0::"))
    if len(values) != 1:
        return Err("unified cgroup membership unavailable")
    value = values[0]
    path = PurePosixPath(value)
    if not path.is_absolute() or path.as_posix() != value or ".." in path.parts:
        return Err("invalid cgroup membership")
    return Ok(value)


def _starttime(text: str, pid: int) -> Result[int, str]:
    """Read kernel start ticks without assuming the command has no parentheses."""
    closing = text.rfind(")")
    if not text.startswith(str(pid) + " (") or closing < 0:
        return Err("invalid process stat identity")
    fields = text[closing + 1 :].split()
    if (
        len(fields) <= STAT_STARTTIME_INDEX
        or len(fields[STAT_STARTTIME_INDEX]) > MAX_KERNEL_NUMBER_DIGITS
        or re.fullmatch(r"[0-9]+", fields[STAT_STARTTIME_INDEX]) is None
    ):
        return Err("invalid process starttime")
    start = int(fields[STAT_STARTTIME_INDEX])
    return (
        Ok(start)
        if 0 < start <= MAX_KERNEL_NUMBER
        else Err("invalid process starttime")
    )


def process_identity(text: str, pid: int) -> Result[ProcessIdentity, str]:
    """Join a process's parent and start ticks from one native stat record."""
    if isinstance(pid, bool) or pid <= 0:
        return Err("invalid process identity")
    start = _starttime(text, pid)
    if isinstance(start, Err):
        return start
    fields = text[text.rfind(")") + 1 :].split()
    parent = fields[STAT_PARENT_INDEX]
    if (
        len(parent) > MAX_KERNEL_NUMBER_DIGITS
        or re.fullmatch(r"[0-9]+", parent) is None
        or int(parent) > MAX_KERNEL_NUMBER
    ):
        return Err("invalid parent process identity")
    return Ok(ProcessIdentity(pid, int(parent), start.value))


def _affinity(text: str) -> Result[frozenset[int], str]:
    """Read exactly one effective CPU list from process status."""
    values = tuple(
        line.partition(":")[2].strip()
        for line in text.splitlines()
        if line.startswith("Cpus_allowed_list:")
    )
    return (
        cpu_list(values[0]) if len(values) == 1 else Err("process affinity unavailable")
    )


def status_affinity(data: bytes) -> Result[frozenset[int], str]:
    """Decode only ASCII affinity rows, not unrelated process-name bytes."""
    try:
        rows = tuple(
            line.decode("ascii")
            for line in data.splitlines()
            if line.startswith(b"Cpus_allowed_list:")
        )
    except UnicodeError as exc:
        return Err("invalid Linux affinity bytes: " + str(exc))
    return _affinity("\n".join(rows))


def _sample(
    pid: int, proc: Path, root: Path, scope: PurePosixPath
) -> Result[_Raw, str]:
    """Read one PID and every cgroup ancestor within the supplied mount."""
    directory = proc / str(pid)
    if directory.is_symlink() or not directory.resolve(strict=True).is_relative_to(
        proc
    ):
        return Err("process observation escapes proc root")
    start = _starttime(
        (directory / "stat").read_text(encoding="utf-8", errors="surrogateescape"), pid
    )
    group = _group((directory / "cgroup").read_text(encoding="utf-8"))
    cpus = status_affinity((directory / "status").read_bytes())
    if isinstance(start, Err) or isinstance(group, Err) or isinstance(cpus, Err):
        return Err("invalid process identity, cgroup or affinity")
    member = PurePosixPath(group.value)
    if not member.is_relative_to(scope):
        return Err("process escaped owned cgroup")
    leaf_path = root / member.relative_to("/")
    boundary_path = root / scope.relative_to("/")
    leaf = leaf_path.resolve(strict=True)
    boundary = boundary_path.resolve(strict=True)
    if leaf != leaf_path or boundary != boundary_path:
        return Err("cgroup path contains a filesystem alias")
    if not leaf.is_relative_to(boundary) or not boundary.is_relative_to(root):
        return Err("cgroup path escaped observation root")
    limits = tuple(
        (
            (directory / "cpu.max").read_text(encoding="ascii").strip(),
            (directory / "memory.max").read_text(encoding="ascii").strip(),
            (directory / "memory.swap.max").read_text(encoding="ascii").strip(),
        )
        for directory in (leaf, *leaf.parents)
        if directory.is_relative_to(root)
    )
    return Ok(_Raw(start.value, group.value, cpus.value, limits))


def _scalar(text: str) -> Result[int | None, str]:
    """Parse an unsigned kernel cgroup value or the explicit unlimited marker."""
    if text == "max":
        return Ok(None)
    if len(text) > MAX_KERNEL_NUMBER_DIGITS or re.fullmatch(r"[0-9]+", text) is None:
        return Err("invalid cgroup limit")
    number = int(text)
    return Ok(number) if number <= MAX_KERNEL_NUMBER else Err("invalid cgroup limit")


def _effective(raw: _Raw, pid: int) -> Result[ProcessLimits, str]:
    """Use the tightest finite limit in every observed ancestor hierarchy."""
    cpu: tuple[Fraction, ...] = ()
    memory: tuple[int, ...] = ()
    swap: tuple[int, ...] = ()
    for quota, mem, swp in raw.limits:
        parts = quota.split()
        if (
            len(parts) != QUOTA_FIELDS
            or len(parts[1]) > MAX_KERNEL_NUMBER_DIGITS
            or re.fullmatch(r"[0-9]+", parts[1]) is None
            or not 0 < int(parts[1]) <= MAX_KERNEL_NUMBER
        ):
            return Err("invalid cgroup CPU quota")
        parsed_cpu, parsed_memory, parsed_swap = (
            _scalar(parts[0]),
            _scalar(mem),
            _scalar(swp),
        )
        if (
            isinstance(parsed_cpu, Err)
            or isinstance(parsed_memory, Err)
            or isinstance(parsed_swap, Err)
        ):
            return Err("invalid cgroup limit")
        if parsed_cpu.value is not None:
            if parsed_cpu.value <= 0:
                return Err("invalid cgroup CPU quota")
            cpu += (Fraction(parsed_cpu.value, int(parts[1])),)
        if parsed_memory.value is not None:
            memory += (parsed_memory.value,)
        if parsed_swap.value is not None:
            swap += (parsed_swap.value,)
    if not cpu or not memory or not swap:
        return Err("effective cgroup limit is unbounded")
    return Ok(
        ProcessLimits(
            pid, raw.starttime, raw.group, raw.cpus, min(cpu), min(memory), min(swap)
        )
    )


def observe(
    pid: int, proc_root: Path, cgroup_root: Path, scope: str
) -> Result[ProcessLimits, str]:
    """Read a stable, bounded process sample; callers must establish mount origin."""
    path = PurePosixPath(scope)
    if (
        isinstance(pid, bool)
        or pid <= 0
        or not path.is_absolute()
        or path.as_posix() != scope
        or scope == "/"
        or ".." in path.parts
    ):
        return Err("invalid process or owned cgroup scope")
    try:
        proc = proc_root.resolve(strict=True)
        root = cgroup_root.resolve(strict=True)
        first = _sample(pid, proc, root, path)
        if isinstance(first, Err):
            return first
        second = _sample(pid, proc, root, path)
        if isinstance(second, Err):
            return second
        if first.value != second.value:
            return Err("process or cgroup changed during observation")
        return _effective(first.value, pid)
    except (OSError, UnicodeError, RuntimeError, ValueError) as exc:
        return Err("cannot observe process cgroup: " + str(exc))
