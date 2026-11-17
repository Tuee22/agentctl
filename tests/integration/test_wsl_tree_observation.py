# Copyright (c) 2026 agentctl contributors.
"""Constructed proc/cgroup trees exercise actual filesystem observation."""

import os
import sys
from dataclasses import replace
from fractions import Fraction
from pathlib import Path

import pytest

from agentctl.check.wsl_budget import WorkloadBudget
from agentctl.check.wsl_cgroup import ProcessIdentity
from agentctl.check.wsl_tree import descendants, observe_tree, processes, tree_problems
from agentctl.process import run
from agentctl.result import Err, Ok

pytestmark = pytest.mark.evidence("real")

ROOT_PID = 101
CHILD_PID = 102
FOREIGN_PID = 103
GRANDCHILD_PID = 104
START = 1234


def _stat(pid: int, parent: int, start: int) -> str:
    """Encode the relevant proc stat fields with an awkward command name."""
    fields = ("S", str(parent), *("0" for _ in range(17)), str(start))
    return f"{pid} (name)with)paren) " + " ".join(fields)


def _tree(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    """Create a private fixture with a root, child and unrelated process."""
    proc = tmp_path / "proc"
    proc.mkdir()
    for pid, parent, group in (
        (ROOT_PID, 1, "/owned"),
        (CHILD_PID, ROOT_PID, "/owned/child"),
        (FOREIGN_PID, 1, "/foreign"),
        (GRANDCHILD_PID, CHILD_PID, "/owned/child/grand"),
    ):
        directory = proc / str(pid)
        directory.mkdir()
        stat = _stat(pid, parent, START + pid).encode()
        (directory / "stat").write_bytes(
            stat.replace(b"name", b"name\xff") if pid == FOREIGN_PID else stat
        )
        (directory / "status").write_text("Cpus_allowed_list:\t0-1\n", encoding="utf-8")
        (directory / "cgroup").write_text("0::" + group + "\n", encoding="utf-8")
    cgroup = tmp_path / "cgroup"
    scope = cgroup / "owned"
    child = scope / "child"
    grand = child / "grand"
    grand.mkdir(parents=True)
    for directory, cpu, memory, swap, members in (
        (cgroup, "300000 100000", "8192", "20", ""),
        (scope, "200000 100000", "4096", "0", f"{ROOT_PID}\n"),
        (child, "150000 100000", "max", "max", f"{CHILD_PID}\n"),
        (grand, "max 100000", "max", "max", f"{GRANDCHILD_PID}\n"),
    ):
        for name, value in (
            ("cpu.max", cpu),
            ("memory.max", memory),
            ("memory.swap.max", swap),
            ("cgroup.procs", members),
        ):
            (directory / name).write_text(
                value + "\n" if name != "cgroup.procs" else value, encoding="ascii"
            )
    return proc, cgroup, scope, child


def test_tree_observes_all_owned_descendants(tmp_path: Path) -> None:
    """Only the actual descendant closure participates in the private scope."""
    proc, cgroup, _scope, _child = _tree(tmp_path)
    table = processes(proc)
    assert isinstance(table, Ok), f"unrelated process name blocked observation: {table}"
    assert frozenset(item.pid for item in table.value) == frozenset(
        {ROOT_PID, CHILD_PID, FOREIGN_PID, GRANDCHILD_PID}
    )
    observed = observe_tree(ROOT_PID, proc, cgroup, "/owned")
    assert isinstance(observed, Ok), f"grandchild was omitted: {observed}"
    assert tuple(item.pid for item in observed.value) == (
        ROOT_PID,
        CHILD_PID,
        GRANDCHILD_PID,
    )
    budget = WorkloadBudget(
        2, 2000, 5000, 0, 1, 2000, 2000, 2000, 1000, 1000, 1000, 100, 100, 120, 300, 5
    )
    allowed = frozenset({0, 1})
    assert tree_problems(observed.value, budget, allowed) == ()
    changed = (
        observed.value[0],
        replace(observed.value[1], cpu_quota=Fraction(2001, 1000)),
        observed.value[2],
    )
    assert tree_problems(changed, budget, allowed), "child limit was ignored"
    assert tree_problems((observed.value[0], observed.value[0]), budget, allowed) == (
        "invalid observed process set",
    )
    assert tree_problems((replace(observed.value[0], pid=0),), budget, allowed) == (
        "invalid observed process set",
    ), "invalid process identity was accepted"


def test_tree_refuses_missing_and_foreign_members(tmp_path: Path) -> None:
    """A descendant outside the scope or unrelated scope member invalidates it."""
    proc, cgroup, scope, child = _tree(tmp_path)
    (child / "cgroup.procs").write_text("", encoding="ascii")
    assert isinstance(observe_tree(ROOT_PID, proc, cgroup, "/owned"), Err), (
        "escaped descendant was accepted"
    )
    (child / "cgroup.procs").write_text(f"{CHILD_PID}\n", encoding="ascii")
    (scope / "cgroup.procs").write_text(
        f"{ROOT_PID}\n{FOREIGN_PID}\n", encoding="ascii"
    )
    assert isinstance(observe_tree(ROOT_PID, proc, cgroup, "/owned"), Err), (
        "foreign cgroup member was accepted"
    )


def test_tree_refuses_duplicate_cgroup_member(tmp_path: Path) -> None:
    """The same PID appearing twice is a race or corrupt member observation."""
    proc, cgroup, _scope, child = _tree(tmp_path)
    (child / "cgroup.procs").write_text(f"{CHILD_PID}\n{CHILD_PID}\n", encoding="ascii")
    assert isinstance(observe_tree(ROOT_PID, proc, cgroup, "/owned"), Err), (
        "duplicate cgroup member was accepted"
    )


def test_tree_rejects_invalid_process_graph() -> None:
    """Duplicate identities and a cycle containing the root refuse closure."""
    root = ProcessIdentity(ROOT_PID, 1, START)
    child = ProcessIdentity(CHILD_PID, ROOT_PID, START + 1)
    assert descendants(ROOT_PID, (root, child)) == Ok((root, child))
    assert isinstance(descendants(ROOT_PID, (root, root)), Err)
    assert isinstance(
        descendants(ROOT_PID, (replace(root, parent=CHILD_PID), child)), Err
    )


def test_tree_refuses_recycled_pid(root: Path, tmp_path: Path) -> None:
    """An actual audit hook changes a constructed child's final start time."""
    proc, cgroup, _scope, _child = _tree(tmp_path)
    changed = _stat(CHILD_PID, ROOT_PID, START + CHILD_PID + 1)
    program = (
        "import sys\nfrom pathlib import Path\n"
        "sys.path.insert(0, sys.argv[1])\n"
        "from agentctl.check.wsl_tree import observe_tree\n"
        "from agentctl.result import Err\n"
        "target = Path(sys.argv[2]) / sys.argv[4] / 'stat'\n"
        "reads = []\n"
        "def audit(event, args):\n"
        "    if event == 'open' and str(args[0]) == str(target) and args[1] == 'r':\n"
        "        reads.append(1)\n"
        "        if len(reads) == 4: target.write_text(sys.argv[5], encoding='utf-8')\n"
        "sys.addaudithook(audit)\n"
        "result = observe_tree(int(sys.argv[6]), Path(sys.argv[2]), "
        "Path(sys.argv[3]), '/owned')\n"
        "assert isinstance(result, Err), 'recycled process was accepted'\n"
        "assert 'tree or cgroup membership changed' in result.error, result\n"
    )
    observed = run(
        [
            sys.executable,
            "-c",
            program,
            str(root / "src"),
            str(proc),
            str(cgroup),
            str(CHILD_PID),
            changed,
            str(ROOT_PID),
        ],
        cwd=tmp_path,
        env=os.environ,
    )
    assert isinstance(observed, Ok), observed
    assert observed.value.code == 0, observed.value.stderr
