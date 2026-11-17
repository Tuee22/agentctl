# Copyright (c) 2026 agentctl contributors.
"""Controls for native process identity joined to the binding peer."""

import json
from dataclasses import asdict, replace

import pytest

from agentctl.check.binding_process import (
    PeerProcess,
    PeerProcessRequest,
    ProcessSample,
    decode,
    validate_sample,
)
from agentctl.result import Err, Ok

pytestmark = pytest.mark.evidence("value")


def test_process_sample_binds_pid_uid_cgroup_and_executable() -> None:
    """Wrong credentials, process reuse or another executable cannot match."""
    request = PeerProcessRequest(
        123,
        1000,
        "/system.slice/agentctl-binding-" + "a" * 32 + ".service",
        "/opt/agentctl/bin/python",
        "a" * 32,
        "b" * 32,
        "dedicated",
    )
    fields = ("S", "1", *("0" for _ in range(17)), "9876")
    sample = ProcessSample(
        "123 (python) " + " ".join(fields),
        "Uid:\t1000\t1000\t1000\t1000\n",
        "0::" + request.group + "\n",
        b"/opt/agentctl/bin/python\0-I\0-B\0-m\0agentctl.check.binding_protocol\0",
        (42, 1234),
        (42, 1234),
    )
    assert validate_sample(request, sample) == Ok(PeerProcess(request, 9876))
    for changed in (
        replace(sample, stat=sample.stat.replace("123 (", "124 (", 1)),
        replace(sample, stat=sample.stat.replace(") S ", ") Z ", 1)),
        replace(sample, status="Uid:\t0\t1000\t1000\t1000\n"),
        replace(sample, status=sample.status + sample.status),
        replace(sample, cgroup="0::/other\n"),
        replace(sample, argv=sample.argv.replace(b"-I\0", b"-X\0")),
        replace(sample, executable=(42, 1235)),
    ):
        assert isinstance(validate_sample(request, changed), Err), (
            "wrong binding peer process was accepted"
        )
    assert isinstance(validate_sample(replace(request, pid=True), sample), Err)
    assert decode(json.dumps(asdict(request))) == Ok(request)
    assert isinstance(decode(json.dumps({**asdict(request), "uid": True})), Err)
    assert isinstance(decode('{"pid":1,"pid":2}'), Err)
