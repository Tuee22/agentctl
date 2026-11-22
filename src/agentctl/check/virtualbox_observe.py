# Copyright (c) 2026 agentctl contributors.
"""Read a VirtualBox VM configuration without asserting its provenance."""

import json
import os
import platform
import re
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
from uuid import UUID

from agentctl.check.hyperv_observe import ExecutableIdentity, executable_identity
from agentctl.foundation import Err, Ok, Result
from agentctl.foundation_process import Child, Output, finish, start, stop
from agentctl.foundation_process_identity import (
    WindowsProcessImage,
    windows_process_image,
)

FIELDS = frozenset(
    {"name", "UUID", "CfgFile", "memory", "cpus", "cpuexecutioncap", "VMState"}
)
MAX_CPU_CAP = 100
MAX_OUTPUT_CHARS = 1_048_576
MAX_COUNT_DIGITS = 18
FIRST_PRINTABLE = 32
MAX_PORT = 65535
NAT_NICS = 8


@dataclass(frozen=True, slots=True)
class VmObservation:
    """Reported host configuration, not proof of provisioning or resource isolation."""

    name: str
    identifier: str
    configuration: str
    memory_mib: int
    cpus: int
    cpu_cap: int
    state: str


@dataclass(frozen=True, slots=True)
class NatRoute:
    """One loopback-only SSH forward on a single active NAT adapter."""

    name: str
    host_port: int
    guest_port: int


@dataclass(frozen=True, slots=True)
class NatObservation:
    """Repeated host-reported VM and route facts, not peer authentication."""

    vm: VmObservation
    route: NatRoute


def nat_route(text: str, expected: NatRoute) -> Result[NatRoute, str]:
    """Require one complete supported NIC layout and exactly the requested rule."""
    match (expected.host_port, expected.guest_port):
        case (bool(), _) | (_, bool()):
            return Err("invalid VirtualBox NAT route request")
    if (
        not text.endswith("\n")
        or len(text) > MAX_OUTPUT_CHARS
        or re.fullmatch(r"[A-Za-z0-9_-]{1,64}", expected.name) is None
        or not 1 <= expected.host_port <= MAX_PORT
        or not 1 <= expected.guest_port <= MAX_PORT
    ):
        return Err("invalid VirtualBox NAT route request")
    rows = tuple(line.partition("=") for line in text.splitlines())
    selected = tuple(
        (key, separator, value)
        for key, separator, value in rows
        if (
            re.fullmatch(r"nic[0-9]+", key) is not None
            or key.casefold().startswith("forwarding")
            or key == "cableconnected1"
        )
    )
    required = frozenset(
        (
            *("nic" + str(index) for index in range(1, NAT_NICS + 1)),
            "cableconnected1",
            "Forwarding(0)",
        )
    )
    if (
        len(selected) != len(required)
        or any(not separator for _, separator, _ in selected)
        or frozenset(key for key, _, _ in selected) != required
    ):
        return Err("VirtualBox NAT configuration is incomplete or ambiguous")
    fields = {key: value for key, _, value in selected}
    try:
        adapter = json.loads(fields["nic1"])
        cable = json.loads(fields["cableconnected1"])
        others = tuple(
            json.loads(fields["nic" + str(index)]) for index in range(2, NAT_NICS + 1)
        )
        forwarding = json.loads(fields["Forwarding(0)"])
    except (ValueError, UnicodeError):
        return Err("invalid VirtualBox NAT configuration encoding")
    rule = f"{expected.name},tcp,127.0.0.1,{expected.host_port},,{expected.guest_port}"
    if (
        adapter != "nat"
        or cable != "on"
        or any(value != "none" for value in others)
        or forwarding != rule
    ):
        return Err("VirtualBox NAT route does not match request")
    return Ok(expected)


def join_nat(
    first: NatObservation, second: NatObservation, *, name: str
) -> Result[NatObservation, str]:
    """Require the same running named VM and route around an observation."""
    if (
        not name
        or first != second
        or first.vm.name != name
        or first.vm.state != "running"
    ):
        return Err("VirtualBox NAT route or VM changed")
    return Ok(second)


def observe_nat(
    executable: Path, identifier: str, expected: NatRoute, *, name: str, cwd: Path
) -> Result[NatObservation, str]:
    """Capture VM and route twice without claiming SSH endpoint provenance."""
    match _nat_sample(executable, identifier, expected, cwd):
        case Err() as error:
            return error
        case Ok(first):
            match _nat_sample(executable, identifier, expected, cwd):
                case Err() as error:
                    return error
                case Ok(second):
                    return join_nat(first, second, name=name)


def _nat_sample(
    executable: Path, identifier: str, expected: NatRoute, cwd: Path
) -> Result[NatObservation, str]:
    """Join a captured VM to its route without authenticating the output."""
    match capture(executable, identifier, cwd=cwd):
        case Err() as error:
            return error
        case Ok((vm, raw)):
            match nat_route(raw, expected):
                case Err() as error:
                    return error
                case Ok(route):
                    return Ok(NatObservation(vm, route))


def parse(text: str, identifier: str) -> Result[VmObservation, str]:
    """Decode required machine-readable fields, rejecting ambiguity and bad identity."""
    try:
        expected = str(UUID(identifier))
    except (ValueError, AttributeError, TypeError):
        return Err("invalid VirtualBox VM identifier")
    return _parse_fields(text, expected)


def _strings(values: dict[str, str]) -> Result[tuple[str, str, str, str], str]:
    """Decode only the expected string fields from an already checked field set."""
    try:
        decoded: tuple[object, ...] = tuple(
            json.loads(values[key]) for key in ("name", "UUID", "CfgFile", "VMState")
        )
    except (ValueError, UnicodeError):
        return Err("invalid VirtualBox observation string")
    match decoded:
        case (str() as name, str() as observed, str() as configuration, str() as state):
            return Ok((name, observed, configuration, state))
        case _:
            return Err("invalid VirtualBox observation string")


def _parse_fields(text: str, expected: str) -> Result[VmObservation, str]:
    """Join complete fields to the already normalized requested identity."""
    if not text or len(text) > MAX_OUTPUT_CHARS or not text.endswith("\n"):
        return Err("incomplete VirtualBox observation")
    rows = tuple(line.partition("=") for line in text.splitlines())
    selected = tuple(
        (key, value) for key, separator, value in rows if separator and key in FIELDS
    )
    if len(selected) != len(FIELDS) or frozenset(key for key, _ in selected) != FIELDS:
        return Err("missing or duplicate VirtualBox observation field")
    values = dict(selected)
    decoded = _strings(values)
    if isinstance(decoded, Err):
        return decoded
    name, observed, configuration, state = decoded.value
    counts = tuple(values[key] for key in ("memory", "cpus", "cpuexecutioncap"))
    if (
        not name
        or observed != expected
        or re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", state) is None
        or any(ord(character) < FIRST_PRINTABLE for character in name + configuration)
        or not all(
            len(value) <= MAX_COUNT_DIGITS and re.fullmatch(r"[0-9]+", value)
            for value in counts
        )
    ):
        return Err("invalid VirtualBox observation fields")
    path = PureWindowsPath(configuration)
    memory, cpus, cap = map(int, counts)
    if (
        not path.is_absolute()
        or ".." in path.parts
        or memory <= 0
        or cpus <= 0
        or not 1 <= cap <= MAX_CPU_CAP
    ):
        return Err("invalid VirtualBox configuration or allocation")
    return Ok(VmObservation(name, observed, configuration, memory, cpus, cap, state))


def observe(
    executable: Path, identifier: str, *, cwd: Path
) -> Result[VmObservation, str]:
    """Read the typed VM configuration without claiming a VM binding receipt."""
    captured = capture(executable, identifier, cwd=cwd)
    return captured if isinstance(captured, Err) else Ok(captured.value[0])


def capture(
    executable: Path, identifier: str, *, cwd: Path
) -> Result[tuple[VmObservation, str], str]:
    """Retain the original machine-readable output with its typed VM observation."""
    if platform.system() != "Windows":
        return Err("VirtualBox host observation requires Windows")
    try:
        normalized = str(UUID(identifier))
    except (ValueError, AttributeError, TypeError):
        return Err("invalid VirtualBox VM identifier")
    return _invoke(executable, normalized, cwd)


def _invoke(
    executable: Path, normalized: str, cwd: Path
) -> Result[tuple[VmObservation, str], str]:
    """Preserve the primary command error if the executable changes as well."""
    before = executable_identity(executable)
    if isinstance(before, Err):
        return before
    outcome = _query(executable, normalized, cwd, before.value)
    after = executable_identity(executable)
    if isinstance(after, Err) or after.value != before.value:
        primary = (
            outcome.error
            if isinstance(outcome, Err)
            else "exit " + str(outcome.value.code) + ": " + outcome.value.stderr
            if outcome.value.code
            else ""
        )
        return Err(
            ("VirtualBox observation failed: " + primary + "; " if primary else "")
            + "VirtualBox observer executable changed during execution"
        )
    if isinstance(outcome, Err):
        return Err("VirtualBox observation failed: " + outcome.error)
    if outcome.value.code != 0:
        return Err("VirtualBox observation failed: " + outcome.value.stderr)
    parsed = parse(outcome.value.stdout, normalized)
    return (
        parsed if isinstance(parsed, Err) else Ok((parsed.value, outcome.value.stdout))
    )


def image_matches(
    expected: ExecutableIdentity, observed: WindowsProcessImage, pid: int
) -> bool:
    """Join an observed child to the previously inspected executable file."""
    if (
        isinstance(pid, bool)
        or isinstance(observed.pid, bool)
        or isinstance(observed.birth, bool)
        or pid <= 0
        or observed.pid != pid
        or observed.birth <= 0
    ):
        return False
    try:
        return observed.image.samefile(expected.path)
    except OSError:
        return False


def _cleanup_failure(child: Child, primary: str) -> Err[str]:
    """Stop only the owned child and retain any cleanup failure beside the primary."""
    cleanup = stop(child)
    suffix = "; cleanup: " + cleanup.error.message if isinstance(cleanup, Err) else ""
    return Err(primary + suffix)


def _query(
    executable: Path, identifier: str, cwd: Path, expected: ExecutableIdentity
) -> Result[Output, str]:
    """Observe the owned child's image before accepting its command output."""
    child = start(
        [str(executable), "showvminfo", identifier, "--machinereadable"],
        cwd=cwd,
        env=dict(os.environ),
    )
    if isinstance(child, Err):
        return Err(child.error.message)
    image = windows_process_image(child.value.pid)
    if isinstance(image, Err):
        return _cleanup_failure(child.value, "process image: " + image.error.message)
    if not image_matches(expected, image.value, child.value.pid):
        return _cleanup_failure(child.value, "process image does not match executable")
    result = finish(child.value, timeout=30)
    if isinstance(result, Err):
        return _cleanup_failure(child.value, result.error.message)
    return result
