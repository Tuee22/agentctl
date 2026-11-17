# Copyright (c) 2026 agentctl contributors.
"""Constructed proc and cgroup boundaries for termination observations."""

import json
from dataclasses import asdict, replace
from pathlib import Path

import pytest

from agentctl.check.binding_process import PeerProcess, PeerProcessRequest
from agentctl.check.binding_stopped import decode, sample
from agentctl.result import Err, Ok

pytestmark = pytest.mark.evidence("real")


def test_stopped_requires_original_pid_and_cgroup_gone(tmp_path: Path) -> None:
    """A live identity or a populated descendant group prevents cleanup."""
    request = PeerProcessRequest(
        123,
        1000,
        "/system.slice/agentctl-binding-" + "a" * 32 + ".service",
        "/opt/agentctl/bin/python",
        "a" * 32,
        "b" * 32,
        "dedicated",
    )
    process = PeerProcess(request, 9876)
    proc = tmp_path / "proc"
    pid = proc / "123"
    pid.mkdir(parents=True)
    cgroup = tmp_path / "cgroup"
    group = cgroup / request.group.lstrip("/")
    group.mkdir(parents=True)
    fields = ("S", "1", *("0" for _ in range(17)), "9876")
    stat = pid / "stat"
    stat.write_text("123 (python) " + " ".join(fields), encoding="utf-8")
    events = group / "cgroup.events"
    events.write_text("populated 1\nfrozen 0\n", encoding="ascii")
    assert sample(process, proc, cgroup) == Ok((False, False)), (
        "populated cgroup was accepted"
    )
    stat.unlink()
    assert sample(process, proc, cgroup) == Ok((True, False)), (
        "populated cgroup was accepted"
    )
    events.write_text("populated 0\nfrozen 0\n", encoding="ascii")
    assert sample(process, proc, cgroup) == Ok((True, True))
    stat.write_text(
        "123 (python) " + " ".join((*fields[:-1], "9877")), encoding="utf-8"
    )
    assert sample(process, proc, cgroup) == Ok((True, True))
    events.write_text("populated 0\npopulated 0\n", encoding="ascii")
    assert isinstance(sample(process, proc, cgroup), Err)
    assert isinstance(sample(replace(process, starttime=True), proc, cgroup), Err)
    assert decode(json.dumps(asdict(process))) == Ok(process)
    assert isinstance(decode(json.dumps({**asdict(process), "starttime": True})), Err)
