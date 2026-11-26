# Copyright (c) 2026 agentctl contributors.
"""Constructed proc and cgroup files exercise the cgroup observation refusals."""

from collections.abc import Callable
from pathlib import Path

import pytest

from agentctl.check.wsl_cgroup import cpu_list, observe, process_identity
from agentctl.foundation import Err, Ok

pytestmark = pytest.mark.evidence("value")

PID = 4321
START_TICKS = 5555
PARENT = 77
SCOPE = "/owned"
MEMORY = "8192"
INVALID_SAMPLE = "invalid process identity, cgroup or affinity"
DUPLICATE_MEMBERSHIP = "0::/owned/x\n0::/owned/y\n"
FILES = ("cpu.max", "memory.max", "memory.swap.max")


def _stat(pid: int, parent: str, start: str) -> str:
    """Encode the native stat fields around a command name."""
    fields = ("S", parent, *("0" for _ in range(17)), start)
    return f"{pid} (name) " + " ".join(fields)


def _limits(directory: Path, values: tuple[str, str, str]) -> None:
    """Write one directory's three limit files."""
    for name, value in zip(FILES, values, strict=True):
        (directory / name).write_text(value + "\n", encoding="ascii")


def _fixture(tmp_path: Path) -> tuple[Path, Path, Path]:
    """Create a private proc and cgroup hierarchy with an owned child group."""
    proc = tmp_path / "proc"
    process = proc / str(PID)
    process.mkdir(parents=True)
    (process / "stat").write_text(
        _stat(PID, str(PARENT), str(START_TICKS)), encoding="ascii"
    )
    (process / "status").write_text("Cpus_allowed_list:\t0-1\n", encoding="ascii")
    (process / "cgroup").write_text("0::/owned/child\n", encoding="ascii")
    root = tmp_path / "cgroup"
    leaf = root / "owned" / "child"
    leaf.mkdir(parents=True)
    _limits(root, ("300000 100000", MEMORY, "20"))
    _limits(root / "owned", ("200000 100000", MEMORY, "10"))
    _limits(leaf, ("100000 100000", "max", "max"))
    return proc, root, leaf


def _rewriting_after(
    original: Callable[..., str], watched: Path, replacement: str
) -> Callable[..., str]:
    """Delegate a read, then change the watched file as a concurrent writer would."""

    def racing(self: Path, *args: str, **kwargs: str) -> str:
        text = original(self, *args, **kwargs)
        if self == watched.resolve():
            watched.write_text(replacement, encoding="ascii")
        return text

    return racing


@pytest.mark.parametrize(
    ("name", "content"),
    [
        ("cgroup", "0::/owned/child\n0::/owned/child\n"),
        ("cgroup", "1:name:/owned/child\n"),
        ("cgroup", "0::/owned/../child\n"),
        ("cgroup", "0::relative\n"),
        ("stat", f"{PID} (name) S 1"),
        ("stat", "not a stat record"),
        ("status", "Name:\tx\n"),
    ],
)
def test_malformed_process_files_refuse_observation(
    tmp_path: Path, name: str, content: str
) -> None:
    """Duplicate, absent or aliased membership and short stat or status refuse."""
    proc, root, _leaf = _fixture(tmp_path)
    (proc / str(PID) / name).write_text(content, encoding="ascii")
    assert observe(PID, proc, root, SCOPE) == Err(INVALID_SAMPLE)


def test_process_identity_and_cpu_list_bounds() -> None:
    """Pids, parents and CPU lists beyond the kernel bounds are refused."""
    good = _stat(PID, str(PARENT), str(START_TICKS))
    assert isinstance(process_identity(good, PID), Ok)
    assert process_identity(good, 0) == Err("invalid process identity")
    assert process_identity(good, pid=True) == Err("invalid process identity")
    bad_parent = _stat(PID, "x", str(START_TICKS))
    assert process_identity(bad_parent, PID) == Err("invalid parent process identity")
    assert cpu_list("0-65536") == Err("CPU list exceeds observation bound")


def test_process_directory_alias_refuses_observation(tmp_path: Path) -> None:
    """A process directory that is a symlink does not escape through proc."""
    proc, root, _leaf = _fixture(tmp_path)
    real = proc / str(PID)
    moved = proc / "moved"
    real.rename(moved)
    real.symlink_to(moved, target_is_directory=True)
    assert observe(PID, proc, root, SCOPE) == Err(
        "process observation escapes proc root"
    )


def test_cgroup_directory_alias_refuses_observation(tmp_path: Path) -> None:
    """A symlinked leaf group is a filesystem alias, not an owned cgroup."""
    proc, root, leaf = _fixture(tmp_path)
    real = leaf.with_name("real")
    leaf.rename(real)
    leaf.symlink_to(real, target_is_directory=True)
    assert observe(PID, proc, root, SCOPE) == Err(
        "cgroup path contains a filesystem alias"
    )


@pytest.mark.parametrize(
    ("name", "values", "message"),
    [
        ("memory.max", "abc", "invalid cgroup limit"),
        ("memory.max", "9" * 20, "invalid cgroup limit"),
        ("cpu.max", "100000", "invalid cgroup CPU quota"),
        ("cpu.max", "0 100000", "invalid cgroup CPU quota"),
    ],
)
def test_malformed_limit_files_refuse_observation(
    tmp_path: Path, name: str, values: str, message: str
) -> None:
    """Non-numeric, oversized, short or zero limits are refused with a reason."""
    proc, root, leaf = _fixture(tmp_path)
    (leaf / name).write_text(values + "\n", encoding="ascii")
    assert observe(PID, proc, root, SCOPE) == Err(message)


def test_limits_changing_between_samples_refuse_observation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A limit rewritten after the first sample makes the two samples differ."""
    proc, root, leaf = _fixture(tmp_path)
    watched = leaf / "memory.swap.max"
    with monkeypatch.context() as patch:
        patch.setattr(
            Path, "read_text", _rewriting_after(Path.read_text, watched, "7\n")
        )
        result = observe(PID, proc, root, SCOPE)
    assert result == Err("process or cgroup changed during observation")


def test_membership_changing_between_samples_refuses_observation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A membership record that turns invalid after the first sample is refused."""
    proc, root, _leaf = _fixture(tmp_path)
    watched = proc / str(PID) / "cgroup"
    with monkeypatch.context() as patch:
        patch.setattr(
            Path,
            "read_text",
            _rewriting_after(Path.read_text, watched, DUPLICATE_MEMBERSHIP),
        )
        result = observe(PID, proc, root, SCOPE)
    assert result == Err(INVALID_SAMPLE)
