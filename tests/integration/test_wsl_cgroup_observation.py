# Copyright (c) 2026 agentctl contributors.
"""Actual file reads of constructed cgroup data are not Linux host evidence."""

import os
import sys
from dataclasses import replace
from fractions import Fraction
from pathlib import Path

import pytest

from agentctl.check.wsl_budget import WorkloadBudget
from agentctl.check.wsl_cgroup import cpu_list, limit_problems, observe
from agentctl.process import run
from agentctl.result import Err, Ok

pytestmark = pytest.mark.evidence("real")

PID = 1234
START_TICKS = 9876
PARENT_MEMORY = 4096
LEAF_MEMORY = 2048
ROOT_MEMORY = 8192


def _files(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    """Create a private, constructed proc and cgroup hierarchy."""
    proc = tmp_path / "proc"
    process = proc / str(PID)
    process.mkdir(parents=True)
    fields = ("S", "1", *("0" for _ in range(17)), str(START_TICKS))
    (process / "stat").write_bytes(
        f"{PID} (name)with)paren".encode() + b"\xff) " + " ".join(fields).encode()
    )
    (process / "status").write_bytes(b"Name:\t\xff\nCpus_allowed_list:\t0-1,3\n")
    (process / "cgroup").write_text("0::/owned/child\n", encoding="utf-8")
    root = tmp_path / "cgroup"
    scope = root / "owned"
    leaf = scope / "child"
    leaf.mkdir(parents=True)
    for directory, values in (
        (root, ("300000 100000", str(ROOT_MEMORY), "20")),
        (scope, ("200000 100000", str(PARENT_MEMORY), "0")),
        (leaf, ("150000 100000", "max", "max")),
    ):
        for name, value in zip(
            ("cpu.max", "memory.max", "memory.swap.max"), values, strict=True
        ):
            (directory / name).write_text(value + "\n", encoding="ascii")
    return proc, root, scope, leaf


def test_process_limits_use_every_ancestor(tmp_path: Path) -> None:
    """The tightest ancestor quota, memory and swap values constrain the result."""
    proc, root, scope, leaf = _files(tmp_path)
    observed = observe(PID, proc, root, "/owned")
    assert isinstance(observed, Ok), (
        f"non-UTF8 process name blocked observation: {observed}"
    )
    assert observed.value.starttime == START_TICKS
    assert observed.value.group == "/owned/child"
    assert observed.value.cpus == frozenset({0, 1, 3})
    assert observed.value.cpu_quota == Fraction(3, 2), "tightest CPU quota was ignored"
    assert observed.value.memory_max == PARENT_MEMORY, (
        "ancestor memory limit was ignored"
    )
    assert observed.value.swap_max == 0, "ancestor swap limit was ignored"
    budget = WorkloadBudget(
        2, 2000, 5000, 0, 1, 2000, 2000, 2000, 1000, 1000, 1000, 100, 100, 120, 300, 5
    )
    allowed = frozenset({0, 1, 3})
    assert limit_problems(observed.value, budget, allowed) == ()
    assert "process CPU limit exceeds budget" in limit_problems(
        replace(observed.value, cpu_quota=Fraction(2001, 1000)), budget, allowed
    ), "excess CPU quota was accepted"
    assert "process affinity exceeds budget" in limit_problems(
        observed.value, budget, frozenset({0, 1})
    ), "excess CPU affinity was accepted"
    assert "process swap limit exceeds budget" in limit_problems(
        replace(observed.value, swap_max=1), budget, allowed
    )
    (leaf / "memory.max").write_text(str(LEAF_MEMORY) + "\n", encoding="ascii")
    changed = observe(PID, proc, root, "/owned")
    assert isinstance(changed, Ok)
    assert changed.value.memory_max == LEAF_MEMORY
    (scope / "cpu.max").write_text("max 100000\n", encoding="ascii")
    (leaf / "cpu.max").write_text("max 100000\n", encoding="ascii")
    (root / "cpu.max").write_text("max 100000\n", encoding="ascii")
    assert isinstance(observe(PID, proc, root, "/owned"), Err), (
        "unbounded CPU quota was accepted"
    )


def test_process_limits_refuse_escaped_or_missing_values(tmp_path: Path) -> None:
    """Missing files, escaped membership and invalid scope do not imply limits."""
    proc, root, _scope, leaf = _files(tmp_path)
    (proc / str(PID) / "cgroup").write_text("0::/foreign\n", encoding="utf-8")
    assert isinstance(observe(PID, proc, root, "/owned"), Err), (
        "escaped cgroup was accepted"
    )
    (proc / str(PID) / "cgroup").write_text("0::/owned/child\n", encoding="utf-8")
    (leaf / "memory.max").unlink()
    assert isinstance(observe(PID, proc, root, "/owned"), Err)
    assert isinstance(observe(PID, proc, root, "/"), Err)
    assert isinstance(observe(PID, proc, root, "/owned/../foreign"), Err)


def test_cpu_list_rejects_ambiguous_or_unbounded_input() -> None:
    """Ranges remain exact and reject overlaps, aliases and impractical counts."""
    assert cpu_list("0-2,4") == Ok(frozenset({0, 1, 2, 4}))
    for value in ("", "2-1", "0-2,2", "01", "-1", "0-999999", "9" * 10000):
        assert isinstance(cpu_list(value), Err)


def test_process_limits_refuse_changed_sample(root: Path, tmp_path: Path) -> None:
    """A real audit hook changes an owned ancestor between the two reads."""
    proc, cgroup, scope, _leaf = _files(tmp_path)
    program = (
        "import sys\nfrom pathlib import Path\n"
        "sys.path.insert(0, sys.argv[1])\n"
        "from agentctl.check.wsl_cgroup import observe\n"
        "from agentctl.result import Err\n"
        "target = Path(sys.argv[4]) / 'memory.max'\n"
        "reads = []\n"
        "def audit(event, args):\n"
        "    if event == 'open' and str(args[0]) == str(target) and args[1] == 'r':\n"
        "        reads.append(1)\n"
        "        if len(reads) == 2: target.write_text('8192\\n', encoding='ascii')\n"
        "sys.addaudithook(audit)\n"
        "result = observe(int(sys.argv[5]), Path(sys.argv[2]), "
        "Path(sys.argv[3]), '/owned')\n"
        "assert isinstance(result, Err), 'changed cgroup sample was accepted'\n"
        "assert 'changed during observation' in result.error, result\n"
    )
    observed = run(
        [
            sys.executable,
            "-c",
            program,
            str(root / "src"),
            str(proc),
            str(cgroup),
            str(scope),
            str(PID),
        ],
        cwd=tmp_path,
        env=os.environ,
    )
    assert isinstance(observed, Ok), observed
    assert observed.value.code == 0, observed.value.stderr
