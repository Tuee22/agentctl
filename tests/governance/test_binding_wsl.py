# Copyright (c) 2026 agentctl contributors.
"""Constructed Windows-to-WSL invocation and response controls."""

import json
from dataclasses import asdict, replace

import pytest

from agentctl.check import binding_inventory, binding_process, binding_transport
from agentctl.check.binding_peer import PeerObservation, PeerRequest
from agentctl.check.binding_protocol import Request
from agentctl.check.binding_wsl import (
    Configuration,
    Invocation,
    UnitLimits,
    UnitStatus,
    observe_termination_with,
    observe_unit_process_with,
    prepare,
    prepare_unit,
    process_bracket,
    process_query,
    process_response,
    response,
    stopped_query,
    stopped_response,
    uid_is_integer,
    unit_query,
    unit_status,
)
from agentctl.check.evidence import Entry
from agentctl.check.wsl_guest_sample import GuestReading
from agentctl.check.wsl_registration import Registration
from agentctl.process import Output
from agentctl.result import Err, Ok, Result

pytestmark = pytest.mark.evidence("value")

REGISTRATION = Registration(
    "{854ac4df-1457-43ff-905e-2262d4de1f10}",
    "dedicated",
    r"C:\agentctl-validation\debian",
    2,
)
PEER = PeerRequest("dedicated", "/mnt/c/source", "/work/source", "a" * 32)


def test_active_unit_status_binds_identity_and_limits() -> None:
    """A live unit must match its nonce, user, scope and requested limits."""
    config = Configuration(
        "wsl.exe",
        "/opt/agentctl/bin/python",
        REGISTRATION,
        (REGISTRATION,),
        r"C:\agentctl-validation",
        2,
        "agentctl",
        1000,
    )
    prepared = prepare_unit(config, "absence", PEER, UnitLimits(67108864, 10, 16, 20))
    assert isinstance(prepared, Ok)
    unit = prepared.value
    group = "/system.slice/" + unit.unit + ".service"
    fields = {
        "Id": unit.unit + ".service",
        "LoadState": "loaded",
        "ActiveState": "active",
        "SubState": "running",
        "MainPID": "123",
        "ControlGroup": group,
        "InvocationID": "b" * 32,
        "User": "agentctl",
        "MemoryMax": "67108864",
        "MemorySwapMax": "0",
        "CPUQuotaPerSecUSec": "100ms",
        "TasksMax": "16",
        "NoNewPrivileges": "yes",
        "ProtectControlGroups": "yes",
        "Delegate": "no",
        "KillMode": "control-group",
        "RuntimeMaxUSec": "20s",
        "TimeoutStopUSec": "5s",
    }

    def output(values: dict[str, str]) -> Output:
        return Output(
            0, "".join(key + "=" + value + "\n" for key, value in values.items()), ""
        )

    assert isinstance(unit_query(config, unit), Ok)
    assert unit_status(output(fields), config, unit) == Ok(
        UnitStatus(123, "b" * 32, group)
    )
    for changed in (
        {**fields, "Id": "other.service"},
        {**fields, "MainPID": "0"},
        {**fields, "MainPID": "9" * 5000},
        {**fields, "InvocationID": "0" * 32},
        {**fields, "ControlGroup": "/system.slice/other"},
        {**fields, "User": "root"},
        {**fields, "MemoryMax": "67108865"},
        {**fields, "MemorySwapMax": "1"},
        {**fields, "CPUQuotaPerSecUSec": "110ms"},
        {**fields, "TasksMax": "17"},
        {**fields, "KillMode": "process"},
        {**fields, "RuntimeMaxUSec": "infinity"},
        {**fields, "RuntimeMaxUSec": "21s"},
        {**fields, "RuntimeMaxUSec": "1min 20s"},
        {**fields, "TimeoutStopUSec": "6s"},
        {**fields, "Delegate": "yes"},
        {**fields, "NoNewPrivileges": "no"},
        {**fields, "ProtectControlGroups": "no"},
        {**fields, "ActiveState": "inactive"},
        {**fields, "Unexpected": "extra"},
    ):
        assert isinstance(unit_status(output(changed), config, unit), Err), (
            "invalid WSL unit observation was accepted"
        )
    duplicated = output(fields).stdout + "User=agentctl\n"
    assert isinstance(unit_status(Output(0, duplicated, ""), config, unit), Err)
    assert isinstance(
        unit_status(Output(1, output(fields).stdout, "failure"), config, unit), Err
    )
    assert isinstance(unit_query(config, replace(unit, unit="other")), Err)


def test_process_response_is_bound_to_active_unit() -> None:
    """The observer cannot substitute a process, unit, nonce or creation tick."""
    config = Configuration(
        "wsl.exe",
        "/opt/agentctl/bin/python",
        REGISTRATION,
        (REGISTRATION,),
        r"C:\agentctl-validation",
        2,
        "agentctl",
        1000,
    )
    prepared = prepare_unit(config, "absence", PEER, UnitLimits(67108864, 10, 16, 20))
    assert isinstance(prepared, Ok)
    unit = prepared.value
    status = UnitStatus(123, "b" * 32, "/system.slice/" + unit.unit + ".service")
    query = process_query(config, unit, status)
    assert isinstance(query, Ok)
    assert "-B" in query.value.argv, "process observer bytecode suppression was omitted"
    data = {"request": asdict(query.value.request), "starttime": 9876}
    observed = process_response(Output(0, json.dumps(data), ""), query.value)
    assert isinstance(observed, Ok)
    assert observed.value.starttime == data["starttime"]
    assert process_bracket(status, observed.value, status) == observed
    stopped = stopped_query(config, unit, observed.value)
    assert isinstance(stopped, Ok)
    stopped_data = {"process": asdict(observed.value), "stopped": True}
    assert stopped_response(
        Output(0, json.dumps(stopped_data), ""), stopped.value
    ) == Ok(value=True)
    for invalid in (
        {**stopped_data, "stopped": 1},
        {**stopped_data, "process": {**asdict(observed.value), "starttime": 9877}},
    ):
        assert isinstance(
            stopped_response(Output(0, json.dumps(invalid), ""), stopped.value), Err
        )
    assert isinstance(
        process_bracket(
            status, observed.value, replace(status, invocation_id="c" * 32)
        ),
        Err,
    ), "changed WSL unit identity was accepted"
    for changed in (
        {**data, "starttime": 0},
        {**data, "starttime": True},
        {**data, "request": {**data["request"], "pid": 123.0}},
        {**data, "request": {**data["request"], "pid": 124}},
        {**data, "request": {**data["request"], "nonce": "c" * 32}},
        {**data, "extra": 1},
    ):
        assert isinstance(
            process_response(Output(0, json.dumps(changed), ""), query.value), Err
        ), "mismatched process response was accepted"
    assert isinstance(
        process_query(config, unit, replace(status, cgroup="/other")), Err
    )


def test_observation_brackets_native_process() -> None:
    """Observe unit, peer and unit in order, and refuse an intervening restart."""
    config = Configuration(
        "wsl.exe",
        "/opt/agentctl/bin/python",
        REGISTRATION,
        (REGISTRATION,),
        r"C:\agentctl-validation",
        2,
        "agentctl",
        1000,
    )
    prepared = prepare_unit(config, "absence", PEER, UnitLimits(67108864, 10, 16, 20))
    assert isinstance(prepared, Ok)
    unit = prepared.value
    fields = {
        "Id": unit.unit + ".service",
        "LoadState": "loaded",
        "ActiveState": "active",
        "SubState": "running",
        "MainPID": "123",
        "ControlGroup": "/system.slice/" + unit.unit + ".service",
        "InvocationID": "b" * 32,
        "User": "agentctl",
        "MemoryMax": "67108864",
        "MemorySwapMax": "0",
        "CPUQuotaPerSecUSec": "100ms",
        "TasksMax": "16",
        "NoNewPrivileges": "yes",
        "ProtectControlGroups": "yes",
        "Delegate": "no",
        "KillMode": "control-group",
        "RuntimeMaxUSec": "20s",
        "TimeoutStopUSec": "5s",
    }

    def exercise(*, changed: bool) -> tuple[object, list[str]]:
        calls: list[str] = []

        def call(argv: tuple[str, ...], stdin: str | None) -> Result[Output, str]:
            if stdin is None:
                calls.append("unit")
                values = (
                    {**fields, "InvocationID": "c" * 32}
                    if changed and calls == ["unit", "process", "unit"]
                    else fields
                )
                return Ok(
                    Output(
                        0,
                        "".join(
                            key + "=" + value + "\n" for key, value in values.items()
                        ),
                        "",
                    )
                )
            calls.append("process")
            assert argv[-1] == "agentctl.check.binding_process"
            return Ok(
                Output(
                    0, json.dumps({"request": json.loads(stdin), "starttime": 9876}), ""
                )
            )

        return observe_unit_process_with(config, unit, call), calls

    observed, order = exercise(changed=False)
    assert isinstance(observed, Ok), observed
    assert order == ["unit", "process", "unit"], (
        "unit process observation was not bracketed"
    )
    changed, changed_order = exercise(changed=True)
    assert changed_order == order
    assert isinstance(changed, Err), "changed unit observation was accepted"

    def failed(_argv: tuple[str, ...], _stdin: str | None) -> Result[Output, str]:
        return Err("observer unavailable")

    assert observe_unit_process_with(config, unit, failed) == Err(
        "observer unavailable"
    )


def test_termination_brackets_original_unit_and_cgroup() -> None:
    """A live cgroup, changed unit or unobservable process prevents cleanup."""
    config = Configuration(
        "wsl.exe",
        "/opt/agentctl/bin/python",
        REGISTRATION,
        (REGISTRATION,),
        r"C:\agentctl-validation",
        2,
        "agentctl",
        1000,
    )
    prepared = prepare_unit(config, "absence", PEER, UnitLimits(67108864, 10, 16, 20))
    assert isinstance(prepared, Ok)
    unit = prepared.value
    status = UnitStatus(123, "b" * 32, "/system.slice/" + unit.unit + ".service")
    query = process_query(config, unit, status)
    assert isinstance(query, Ok)
    process = binding_process.PeerProcess(query.value.request, 9876)
    fields = {
        "Id": unit.unit + ".service",
        "LoadState": "not-found",
        "ActiveState": "inactive",
        "SubState": "dead",
        "MainPID": "0",
        "ControlGroup": "",
        "InvocationID": "",
    }

    def exercise(
        *, remains: bool, changed: bool
    ) -> tuple[Result[None, str], list[str]]:
        calls: list[str] = []

        def call(_argv: tuple[str, ...], stdin: str | None) -> Result[Output, str]:
            if stdin is None:
                calls.append("unit")
                values = (
                    {**fields, "ActiveState": "active"}
                    if changed and calls == ["unit", "process", "unit"]
                    else fields
                )
                return Ok(
                    Output(
                        0, "".join(k + "=" + v + "\n" for k, v in values.items()), ""
                    )
                )
            calls.append("process")
            return Ok(
                Output(
                    0,
                    json.dumps({"process": json.loads(stdin), "stopped": not remains}),
                    "",
                )
            )

        return observe_termination_with(config, unit, status, process, call), calls

    result, order = exercise(remains=False, changed=False)
    assert result == Ok(None)
    assert order == ["unit", "process", "unit"], (
        "termination observation was not bracketed"
    )
    assert isinstance(exercise(remains=True, changed=False)[0], Err), (
        "live cgroup was accepted"
    )
    assert isinstance(exercise(remains=False, changed=True)[0], Err), (
        "restarted unit was accepted"
    )


def test_unit_invocation_is_bounded_and_nonce_named() -> None:
    """The guest service has explicit limits and preserves the peer request."""
    config = Configuration(
        "wsl.exe",
        "/opt/agentctl/bin/python",
        REGISTRATION,
        (REGISTRATION,),
        r"C:\agentctl-validation",
        2,
        "agentctl",
        1000,
    )
    limits = UnitLimits(64 * 1024 * 1024, 10, 16, 20)
    result = prepare_unit(config, "observe", PEER, limits)
    assert isinstance(result, Ok), result
    assert result.value.unit == "agentctl-binding-" + PEER.nonce
    argv = result.value.invocation.argv
    assert argv[:7] == (
        "wsl.exe",
        "--distribution",
        "dedicated",
        "--user",
        "root",
        "--exec",
        "/usr/bin/systemd-run",
    )
    for required in (
        "--no-ask-password",
        "--wait",
        "--pipe",
        "--service-type=exec",
        "--expand-environment=no",
        "--unit=" + result.value.unit,
        "--uid=agentctl",
        "--setenv=WSL_DISTRO_NAME=dedicated",
        "--property=MemoryMax=67108864",
        "--property=MemorySwapMax=0",
        "--property=CPUQuota=10%",
        "--property=TasksMax=16",
        "--property=RuntimeMaxSec=20s",
        "--property=TimeoutStopSec=5s",
        "--property=NoNewPrivileges=yes",
        "--property=ProtectControlGroups=yes",
        "--property=Delegate=no",
        "--property=KillMode=control-group",
    ):
        assert required in argv, "WSL peer service bound was omitted"
    assert argv[-5:] == (
        "/opt/agentctl/bin/python",
        "-I",
        "-B",
        "-m",
        "agentctl.check.binding_protocol",
    )
    direct = prepare(config, "observe", PEER)
    assert isinstance(direct, Ok)
    assert result.value.invocation.stdin == direct.value.stdin
    assert result.value.invocation.expected_uid == config.uid
    for invalid in (
        replace(limits, memory_bytes=0),
        replace(limits, cpu_percent=101),
        replace(limits, tasks=0),
        replace(limits, runtime_seconds=3601),
        replace(limits, cpu_percent=True),
    ):
        assert isinstance(prepare_unit(config, "observe", PEER, invalid), Err)
    assert isinstance(
        prepare_unit(replace(config, user="root"), "observe", PEER, limits), Err
    )


def test_invocation_binds_registration_and_shell_free_arguments() -> None:
    """A different distro or unsafe interpreter path cannot reach the launcher."""
    config = Configuration(
        "wsl.exe",
        "/opt/agentctl/bin/python",
        REGISTRATION,
        (REGISTRATION,),
        r"C:\agentctl-validation",
        2,
        "agentctl",
        1000,
    )
    invocation = prepare(config, "observe", PEER)
    assert isinstance(invocation, Ok)
    assert "-B" in invocation.value.argv, "WSL peer bytecode suppression was omitted"
    assert invocation.value.argv == (
        "wsl.exe",
        "--distribution",
        "dedicated",
        "--user",
        "agentctl",
        "--exec",
        "/opt/agentctl/bin/python",
        "-I",
        "-B",
        "-m",
        "agentctl.check.binding_protocol",
    ), "dedicated WSL user was omitted"
    assert isinstance(
        prepare(config, "observe", replace(PEER, distribution="other")), Err
    ), "wrong WSL distribution was accepted"
    assert isinstance(
        prepare(replace(config, python="/opt/../bin/python"), "observe", PEER), Err
    )
    assert isinstance(prepare(replace(config, listed=1), "observe", PEER), Err)
    for uid in (0, -1, True):
        assert isinstance(prepare(replace(config, uid=uid), "observe", PEER), Err), (
            "invalid WSL peer uid was accepted"
        )
    for user in ("", "root", "agent ctl", "../root", "-root", "AgentCtl"):
        assert isinstance(prepare(replace(config, user=user), "observe", PEER), Err), (
            "unsafe WSL peer user was accepted"
        )


def test_cleanup_response_is_a_strict_boolean() -> None:
    """Only a matching nonce, UID and real boolean can satisfy cleanup."""
    invocation = Invocation((), "", Request("absence", PEER), 1000)
    data = {"nonce": PEER.nonce, "uid": 1000, "absent": True}
    assert response(Output(0, json.dumps(data), ""), invocation) == Ok(value=True)
    assert response(
        Output(0, json.dumps({**data, "absent": False}), ""), invocation
    ) == Ok(value=False)
    for output in (
        Output(1, json.dumps(data), "failure"),
        Output(0, json.dumps({**data, "absent": 1}), ""),
        Output(0, json.dumps({**data, "absent": "true"}), ""),
        Output(0, json.dumps({**data, "nonce": "b" * 32}), ""),
        Output(0, json.dumps({**data, "uid": 1001}), ""),
        Output(0, json.dumps({**data, "uid": 1000.0}), ""),
        Output(0, json.dumps({**data, "extra": 1}), ""),
        Output(
            0, '{"nonce":"' + PEER.nonce + '","uid":1,"uid":1000,"absent":true}', ""
        ),
        Output(0, "true", ""),
    ):
        assert isinstance(response(output, invocation), Err), (
            "invalid cleanup response was accepted"
        )


def test_observed_peer_uid_matches_invocation() -> None:
    """A valid peer observation must belong to the expected Linux UID."""
    assert uid_is_integer(1000)
    assert not uid_is_integer(1000.0), "non-integer WSL peer uid was accepted"
    inventory = binding_inventory.encode((Entry("entry", "file", (b"x",)),), PEER.nonce)
    assert isinstance(inventory, Ok)
    mountinfo = (
        "10 1 8:1 / / rw - ext4 /dev/root rw\n"
        "20 10 0:40 / /mnt/c rw - 9p C:\\134 rw\n"
        "21 10 0:40 /source /work/source rw - 9p C:\\134 rw\n"
    )
    observed = PeerObservation(
        PEER,
        "6.1-microsoft-standard-WSL2",
        "dedicated",
        "ID=debian\n",
        1000,
        40,
        1234,
        mountinfo,
        inventory.value,
        GuestReading((0, 1), 4096, 1024, 8192, 4096, 100),
    )
    text = binding_transport.encode(observed)
    invocation = Invocation((), "", Request("observe", PEER), 1000)
    assert response(Output(0, text, ""), invocation) == Ok(text)
    assert isinstance(
        response(Output(0, text, ""), replace(invocation, expected_uid=0)), Err
    )
    assert isinstance(
        response(Output(0, text, ""), replace(invocation, expected_uid=1001)), Err
    ), "wrong WSL peer uid was accepted"
