# Copyright (c) 2026 agentctl contributors.
"""VirtualBox host observations reject ambiguous or foreign VM facts."""

import base64
import json
from dataclasses import replace
from ipaddress import IPv4Address
from pathlib import Path

import pytest

from agentctl.check.hyperv_observe import executable_identity
from agentctl.check.virtualbox_key_observe import (
    FileFact,
    Files,
    GuestResponse,
    _finish,
    _Initial,
    _Results,
)
from agentctl.check.virtualbox_key_observe import combine as combine_session
from agentctl.check.virtualbox_key_observe import join as join_key
from agentctl.check.virtualbox_listener import (
    Listener,
    ListenerObservation,
)
from agentctl.check.virtualbox_listener import (
    join as join_listener,
)
from agentctl.check.virtualbox_listener import parse as parse_listener
from agentctl.check.virtualbox_observe import (
    NatObservation,
    NatRoute,
    VmObservation,
    image_matches,
    join_nat,
    nat_route,
    parse,
)
from agentctl.check.virtualbox_sessions import Session
from agentctl.check.virtualbox_sessions import owned as owned_session
from agentctl.check.virtualbox_sessions import parse as parse_sessions
from agentctl.check.virtualbox_ssh_key import PREFIX
from agentctl.foundation import Err, Ok
from agentctl.foundation_process_identity import WindowsProcessImage

pytestmark = pytest.mark.evidence("value")
VM_ID = "9d7dc4eb-c2b5-4044-8bf1-8d8a6c684df8"
ROW = (
    'name="agentctl-test"\n'
    'UUID="9d7dc4eb-c2b5-4044-8bf1-8d8a6c684df8"\n'
    'CfgFile="C:\\\\owned\\\\test.vbox"\n'
    'memory=12288\ncpus=4\ncpuexecutioncap=100\nVMState="running"\n'
    'other="unrelated"\n'
)


def test_machine_observation_rejects_ambiguity_and_wrong_identity() -> None:
    """Require each named field once and bind it to the requested UUID."""
    assert parse(ROW, VM_ID) == Ok(
        VmObservation(
            "agentctl-test", VM_ID, r"C:\owned\test.vbox", 12288, 4, 100, "running"
        )
    )
    assert isinstance(parse(ROW, "bad"), Err)
    assert isinstance(parse(ROW, "00000000-0000-0000-0000-000000000001"), Err), (
        "foreign VirtualBox UUID was accepted"
    )
    assert isinstance(parse(ROW + "memory=12288\n", VM_ID), Err), (
        "duplicate VirtualBox field was accepted"
    )
    for bad in (
        ROW.rstrip("\n"),
        ROW.replace("memory=12288\n", ""),
        ROW.replace("cpus=4", "cpus=true"),
        ROW.replace("memory=12288", "memory=0"),
        ROW.replace("memory=12288", "memory=" + "9" * 19),
        ROW.replace("memory=12288", "memory=" + "9" * 5000),
        ROW.replace("cpuexecutioncap=100", "cpuexecutioncap=101"),
        ROW.replace('VMState="running"', 'VMState=""'),
        ROW.replace('name="agentctl-test"', 'name="invalid\\nname"'),
        ROW.replace('CfgFile="C:\\\\owned\\\\test.vbox"', 'CfgFile="relative"'),
    ):
        assert isinstance(parse(bad, VM_ID), Err), (
            "invalid VirtualBox observation accepted"
        )


def test_process_image_join_rejects_other_files_and_pids(tmp_path: Path) -> None:
    """An actual file identity and child PID must both match the observed image."""
    executable = tmp_path / "expected.exe"
    other = tmp_path / "other.exe"
    executable.write_bytes(b"same bytes")
    other.write_bytes(b"same bytes")
    expected = executable_identity(executable)
    assert isinstance(expected, Ok), expected
    matching = WindowsProcessImage(123, 456, executable)
    assert image_matches(expected.value, matching, 123)
    assert not image_matches(expected.value, matching, 124), (
        "foreign child PID accepted"
    )
    assert not image_matches(
        expected.value, WindowsProcessImage(123, 456, other), 123
    ), "foreign process image accepted"
    assert not image_matches(
        expected.value, WindowsProcessImage(123, 0, executable), 123
    )
    invalid_birth = True
    assert not image_matches(
        expected.value, WindowsProcessImage(123, invalid_birth, executable), 123
    )


def test_nat_route_requires_one_loopback_forward() -> None:
    """A rule is usable only on one connected NAT NIC with no hidden forwards."""
    route = NatRoute("agentctl-ssh", 44223, 22)
    text = (
        'nic1="nat"\ncableconnected1="on"\n'
        + "".join(f'nic{index}="none"\n' for index in range(2, 9))
        + 'Forwarding(0)="agentctl-ssh,tcp,127.0.0.1,44223,,22"\n'
    )
    assert nat_route(text, route) == Ok(route)
    for bad in (
        text.replace('nic1="nat"', 'nic1="bridged"'),
        text.replace('cableconnected1="on"', 'cableconnected1="off"'),
        text.replace('nic2="none"', 'nic2="nat"'),
        text.replace('nic8="none"\n', ""),
        text + 'nic9="nat"\n',
        text + "nic9\n",
        text + 'nic1="nat"\n',
        text + 'Forwarding(1)="other,tcp,127.0.0.1,1234,,22"\n',
        text + "Forwarding(1)\n",
        text.replace("127.0.0.1", str(IPv4Address(0))),
        text.replace(",tcp,", ",udp,"),
        text.replace(",44223,", ",44224,"),
        text.replace(",,22", ",10.0.2.15,22"),
        text.rstrip("\n"),
    ):
        assert isinstance(nat_route(bad, route), Err), "unsafe VirtualBox NAT accepted"
    assert isinstance(nat_route(text, replace(route, host_port=0)), Err)
    assert isinstance(nat_route(text, replace(route, host_port=True)), Err)
    assert isinstance(nat_route(text, replace(route, name="wrong")), Err)


def test_nat_join_refuses_changed_route_or_vm() -> None:
    """Repeated host observations cannot hide VM or route changes."""
    vm = VmObservation(
        "agentctl-test", VM_ID, r"C:\owned\test.vbox", 12288, 4, 100, "running"
    )
    route = NatRoute("agentctl-ssh", 44223, 22)
    sample = NatObservation(vm, route)
    assert join_nat(sample, sample, name="agentctl-test") == Ok(sample)
    assert isinstance(
        join_nat(
            sample,
            replace(sample, route=replace(route, host_port=44224)),
            name="agentctl-test",
        ),
        Err,
    ), "changed NAT route accepted"
    assert isinstance(
        join_nat(sample, replace(sample, vm=replace(vm, cpus=2)), name="agentctl-test"),
        Err,
    ), "changed NAT VM accepted"
    assert isinstance(join_nat(sample, sample, name="wrong"), Err)
    stopped = replace(sample, vm=replace(vm, state="poweroff"))
    assert isinstance(join_nat(stopped, stopped, name="agentctl-test"), Err)


def test_listener_binds_locked_vm_to_loopback_owner() -> None:
    """Reject stale, ambiguous or foreign COM and TCP observations."""
    row = {
        "name": "agentctl-test",
        "identifier": VM_ID,
        "state1": 2,
        "process1": 123,
        "address": "127.0.0.1",
        "port": 44223,
        "owner": 123,
        "state2": 2,
        "process2": 123,
    }
    expected = Listener("agentctl-test", VM_ID, 44223, 123)
    assert parse_listener(json.dumps(row), VM_ID, "agentctl-test", 44223) == Ok(
        expected
    )
    for field, value in (
        ("name", "other"),
        ("identifier", "00000000-0000-0000-0000-000000000001"),
        ("state1", 1),
        ("state2", 1),
        ("process1", 0),
        ("process2", 124),
        ("owner", 124),
        ("address", "127.0.0.2"),
        ("port", 44224),
        ("owner", True),
    ):
        assert isinstance(
            parse_listener(
                json.dumps({**row, field: value}), VM_ID, "agentctl-test", 44223
            ),
            Err,
        ), "invalid VM listener accepted"
    duplicated = json.dumps(row).replace('"owner": 123', '"owner": 123, "owner": 123')
    assert isinstance(parse_listener(duplicated, VM_ID, "agentctl-test", 44223), Err)
    boolean_port = True
    assert isinstance(
        parse_listener(json.dumps(row), VM_ID, "agentctl-test", boolean_port), Err
    )


def test_listener_join_requires_original_process(tmp_path: Path) -> None:
    """Both snapshots and the observed process file and creation identity must match."""
    executable = tmp_path / "VBoxHeadless.exe"
    other = tmp_path / "other.exe"
    executable.write_bytes(b"binary")
    other.write_bytes(b"binary")
    vm = VmObservation(
        "agentctl-test", VM_ID, r"C:\owned\test.vbox", 12288, 4, 100, "running"
    )
    nat = NatObservation(vm, NatRoute("agentctl-ssh", 44223, 22))
    listener = Listener("agentctl-test", VM_ID, 44223, 123)
    sample = ListenerObservation(
        nat, listener, WindowsProcessImage(123, 456, executable)
    )
    assert join_listener(sample, sample, executable) == Ok(sample)
    altered = replace(sample, process=WindowsProcessImage(123, 457, executable))
    assert isinstance(join_listener(sample, altered, executable), Err), (
        "changed listener process accepted"
    )
    invalid = replace(sample, process=WindowsProcessImage(124, 456, executable))
    assert isinstance(join_listener(invalid, invalid, executable), Err), (
        "foreign listener process accepted"
    )
    foreign = replace(sample, process=WindowsProcessImage(123, 456, other))
    assert isinstance(join_listener(foreign, foreign, executable), Err)


def test_guest_control_key_join_retains_independent_failures(tmp_path: Path) -> None:
    """Changed host facts and a primary guest error remain independently visible."""
    executable = tmp_path / "VBoxHeadless.exe"
    executable.write_bytes(b"binary")
    identity = executable_identity(executable)
    assert isinstance(identity, Ok)
    vm = VmObservation(
        "agentctl-test", VM_ID, r"C:\owned\test.vbox", 12288, 4, 100, "running"
    )
    nat = NatObservation(vm, NatRoute("agentctl-ssh", 44223, 22))
    sample = ListenerObservation(
        nat,
        Listener("agentctl-test", VM_ID, 44223, 123),
        WindowsProcessImage(123, 456, executable),
    )
    encoded = base64.b64encode(PREFIX + bytes(range(32))).decode("ascii")
    before = Files(
        FileFact(1, 2, 10, 20, 30),
        FileFact(1, 3, 90, 20, 30),
        "[127.0.0.1]:44223 ssh-ed25519 " + encoded + "\n",
    )
    guest = "ssh-ed25519 " + encoded + " guest\n"
    nonce = "a" * 32
    response = GuestResponse(guest, nonce)
    assert isinstance(join_key(sample, sample, before, before, response), Ok)
    assert isinstance(
        join_key(sample, sample, before, before, replace(response, nonce="invalid")),
        Err,
    ), "invalid guest nonce accepted"
    changed_files = replace(before, known_text="changed")
    changed_listener = replace(
        sample, process=WindowsProcessImage(123, 457, executable)
    )
    assert isinstance(join_key(sample, sample, before, changed_files, response), Err), (
        "changed key files accepted"
    )
    assert isinstance(
        join_key(sample, changed_listener, before, before, response), Err
    ), "changed key listener accepted"
    result = _finish(
        _Initial(sample, before, identity.value, nonce),
        _Results(
            Err("primary guest failure"),
            Ok(changed_files),
            Ok(changed_listener),
            Err("unavailable"),
        ),
    )
    assert isinstance(result, Err)
    for reason in (
        "primary guest failure",
        "private key files changed",
        "listener changed",
        "guest-control executable changed",
    ):
        assert reason in result.error, "guest-control failure was hidden"


def test_guest_control_session_listing_preserves_other_sessions() -> None:
    """A complete census finds an exact owned name without hiding other sessions."""
    name = f"[9308] VBoxManage Guest Control [{VM_ID}] - run"
    text = (
        "Active guest sessions:\n\n"
        f"\tSession #0   ID=1   User=agentctl   Status=[started] Name={name}\n"
        "\tSession #1   ID=7   User=other   Status=[started] Name=other session\n\n"
        "Total guest sessions: 2\n"
    )
    expected = (
        Session(0, 1, "agentctl", "started", name),
        Session(1, 7, "other", "started", "other session"),
    )
    assert parse_sessions(text) == Ok(expected)
    assert owned_session(expected, VM_ID, 9308) == Ok(expected[0])
    assert owned_session(expected, VM_ID, 9999) == Ok(None)
    foreign = replace(
        expected[1],
        name=name.replace(VM_ID, "00000000-0000-0000-0000-000000000001"),
    )
    assert owned_session((foreign,), VM_ID, 9308) == Ok(None), (
        "foreign VM session accepted"
    )
    assert parse_sessions("No active guest sessions found\n") == Ok(())
    for bad in (
        text.replace("Total guest sessions: 2", "Total guest sessions: 1"),
        text.replace("Session #1", "Session #0"),
        text.replace("ID=7", "ID=1"),
        text.replace("Status=[started]", "Status=[started", 1),
        text + "unexpected\n",
        text.rstrip("\n"),
    ):
        assert isinstance(parse_sessions(bad), Err), (
            "invalid guest session census accepted"
        )
    duplicate = (*expected, replace(expected[0], identifier=8))
    assert isinstance(owned_session(duplicate, VM_ID, 9308), Err), (
        "ambiguous owned session accepted"
    )
    assert combine_session(Ok("key"), Ok(None)) == Ok("key")
    assert isinstance(combine_session(Ok("key"), Err("owned session remains")), Err), (
        "remaining session accepted"
    )
    combined = combine_session(Err("primary"), Err("owned session remains"))
    assert isinstance(combined, Err)
    assert "primary" in combined.error
    assert "owned session remains" in combined.error, "session failure hidden"
