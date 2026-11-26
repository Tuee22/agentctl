# Copyright (c) 2026 agentctl contributors.
"""Constructed proc and cgroup trees exercise the tree observation refusals."""

from collections.abc import Callable
from pathlib import Path

import pytest

from agentctl.check.wsl_tree import observe_native, observe_tree, processes
from agentctl.foundation import Err, Ok

pytestmark = pytest.mark.evidence("value")

ROOT_PID = 301
CHILD_PID = 302
GRAND_PID = 303
START = 4000
CHANGED_START = 9000
SCOPE = "/owned"
OVERSIZED_PID = "99999999999"
MISSING_PID = 999
BAD_MEMBERS = "not-a-pid\n"
FILES = ("cpu.max", "memory.max", "memory.swap.max")


def _stat(pid: int, parent: int, start: int) -> str:
    """Encode the relevant proc stat fields."""
    fields = ("S", str(parent), *("0" for _ in range(17)), str(start))
    return f"{pid} (name) " + " ".join(fields)


def _tree(tmp_path: Path) -> tuple[Path, Path, Path]:
    """Create a private proc table and owned cgroup tree of three processes."""
    proc = tmp_path / "proc"
    proc.mkdir()
    for pid, parent, group in (
        (ROOT_PID, 1, "/owned"),
        (CHILD_PID, ROOT_PID, "/owned/child"),
        (GRAND_PID, CHILD_PID, "/owned/child/grand"),
    ):
        directory = proc / str(pid)
        directory.mkdir()
        (directory / "stat").write_text(_stat(pid, parent, START + pid), "ascii")
        (directory / "status").write_text("Cpus_allowed_list:\t0-1\n", "ascii")
        (directory / "cgroup").write_text("0::" + group + "\n", "ascii")
    cgroup = tmp_path / "cgroup"
    scope = cgroup / "owned"
    grand = scope / "child" / "grand"
    grand.mkdir(parents=True)
    for directory, members in (
        (cgroup, ""),
        (scope, f"{ROOT_PID}\n"),
        (scope / "child", f"{CHILD_PID}\n"),
        (grand, f"{GRAND_PID}\n"),
    ):
        for name, value in zip(FILES, ("100000 100000", "8192", "20"), strict=True):
            (directory / name).write_text(value + "\n", encoding="ascii")
        (directory / "cgroup.procs").write_text(members, encoding="ascii")
    return proc, cgroup, scope


def _rewriting_after(
    original: Callable[..., str], watched: Path, target: Path, replacement: str
) -> Callable[..., str]:
    """Delegate a read of one file, then change another as a concurrent writer."""

    def racing(self: Path, *args: str, **kwargs: str) -> str:
        text = original(self, *args, **kwargs)
        if self == watched:
            target.write_text(replacement, encoding="ascii")
        return text

    return racing


def test_process_table_refuses_bounds_aliases_and_bad_stat(tmp_path: Path) -> None:
    """Oversized ids, linked directories, malformed stat and no proc all refuse."""
    proc, _cgroup, _scope = _tree(tmp_path)
    assert isinstance(processes(proc), Ok)
    (proc / OVERSIZED_PID).mkdir()
    assert processes(proc) == Err("process id exceeds observation bound")
    (proc / OVERSIZED_PID).rmdir()
    (proc / str(MISSING_PID)).symlink_to(proc / str(ROOT_PID), target_is_directory=True)
    assert processes(proc) == Err("process path escaped proc root")
    (proc / str(MISSING_PID)).unlink()
    (proc / str(GRAND_PID) / "stat").write_text("garbled", encoding="ascii")
    assert processes(proc) == Err("invalid process stat identity")
    missing = processes(tmp_path / "missing")
    assert isinstance(missing, Err)
    assert missing.error.startswith("cannot observe process table: ")


def test_observe_tree_refuses_missing_proc_and_root(tmp_path: Path) -> None:
    """A missing proc root or unknown root pid is not an observation."""
    proc, cgroup, _scope = _tree(tmp_path)
    absent = observe_tree(ROOT_PID, tmp_path / "missing", cgroup, SCOPE)
    assert isinstance(absent, Err)
    assert absent.error.startswith("cannot observe cgroup process tree: ")
    assert observe_tree(MISSING_PID, proc, cgroup, SCOPE) == Err(
        "invalid process tree snapshot"
    )


def test_observe_tree_refuses_bad_scopes(tmp_path: Path) -> None:
    """A relative scope or a symlinked scope is not an owned canonical group."""
    proc, cgroup, _scope = _tree(tmp_path)
    assert observe_tree(ROOT_PID, proc, cgroup, "owned") == Err(
        "invalid owned cgroup scope"
    )
    (cgroup / "alias").symlink_to(cgroup / "owned", target_is_directory=True)
    assert observe_tree(ROOT_PID, proc, cgroup, "/alias") == Err(
        "cgroup scope escaped observation root"
    )


def test_observe_tree_refuses_bad_member_lists(tmp_path: Path) -> None:
    """Linked subtrees, missing or malformed member lists refuse observation."""
    proc, cgroup, scope = _tree(tmp_path)
    (scope / "link").symlink_to(scope / "child", target_is_directory=True)
    assert observe_tree(ROOT_PID, proc, cgroup, SCOPE) == Err(
        "cgroup subtree contains a symlink"
    )
    (scope / "link").unlink()
    (scope / "empty").mkdir()
    assert observe_tree(ROOT_PID, proc, cgroup, SCOPE) == Err(
        "cgroup member list unavailable"
    )
    (scope / "empty").rmdir()
    (scope / "child" / "cgroup.procs").write_text(BAD_MEMBERS, encoding="ascii")
    assert observe_tree(ROOT_PID, proc, cgroup, SCOPE) == Err(
        "invalid cgroup member id"
    )


def test_observe_tree_refuses_unreadable_subtree(tmp_path: Path) -> None:
    """A cgroup subtree that cannot be listed fails the whole observation."""
    proc, cgroup, scope = _tree(tmp_path)
    hidden = scope / "child" / "grand"
    hidden.chmod(0)
    try:
        result = observe_tree(ROOT_PID, proc, cgroup, SCOPE)
    finally:
        hidden.chmod(0o700)
    assert isinstance(result, Err)
    assert result.error.startswith("cannot observe cgroup process tree: ")


def test_observe_tree_reports_process_outside_scope(tmp_path: Path) -> None:
    """A member whose own cgroup left the scope names the process in the failure."""
    proc, cgroup, _scope = _tree(tmp_path)
    (proc / str(ROOT_PID) / "cgroup").write_text("0::/foreign\n", encoding="ascii")
    result = observe_tree(ROOT_PID, proc, cgroup, SCOPE)
    assert result == Err(f"process {ROOT_PID}: process escaped owned cgroup")


def test_observe_tree_refuses_identity_changing_after_listing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A start time rewritten after the table read is a changed identity."""
    proc, cgroup, scope = _tree(tmp_path)
    stat = proc / str(ROOT_PID) / "stat"
    changed = _stat(ROOT_PID, 1, CHANGED_START)
    with monkeypatch.context() as patch:
        patch.setattr(
            Path,
            "read_text",
            _rewriting_after(Path.read_text, scope / "cgroup.procs", stat, changed),
        )
        result = observe_tree(ROOT_PID, proc, cgroup, SCOPE)
    assert result == Err(f"process {ROOT_PID}: identity changed")


def test_observe_tree_refuses_membership_changing_during_repeat(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A member list that becomes unreadable after the limits read is refused."""
    proc, cgroup, scope = _tree(tmp_path)
    leaf = scope / "child" / "grand"
    with monkeypatch.context() as patch:
        patch.setattr(
            Path,
            "read_text",
            _rewriting_after(
                Path.read_text,
                leaf / "memory.swap.max",
                scope / "cgroup.procs",
                BAD_MEMBERS,
            ),
        )
        result = observe_tree(ROOT_PID, proc, cgroup, SCOPE)
    assert result == Err("cannot repeat process tree or cgroup observation")


def test_observe_native_refuses_unobserved_or_unrelated_mounts(tmp_path: Path) -> None:
    """A constructed directory is no cgroup2 mount; the real root has no such tree."""
    assert isinstance(observe_native(ROOT_PID, tmp_path, SCOPE), Err)
    real = observe_native(ROOT_PID, Path("/sys/fs/cgroup"), SCOPE)
    assert isinstance(real, Err)
