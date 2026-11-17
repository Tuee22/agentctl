# Copyright (c) 2026 agentctl contributors.
"""Prepare and interpret a dedicated WSL binding-peer invocation."""

import json
import re
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath

from agentctl.check import (
    binding_peer,
    binding_process,
    binding_protocol,
    binding_stopped,
    binding_transport,
)
from agentctl.check.binding_peer import PeerRequest
from agentctl.check.binding_protocol import Operation, Request
from agentctl.check.wsl_registration import Registration, select
from agentctl.foundation import Err, Ok, Result
from agentctl.foundation_process import Output, run

FIRST_PRINTABLE_ASCII = 32
MAX_PEER_CPU_PERCENT = 100
MAX_PEER_TASKS = 1024
MAX_PEER_SECONDS = 3600
OBSERVATION_TIMEOUT_SECONDS = 5
MICROSECONDS_PER_SECOND = 1000000
STOP_TIMEOUT_SECONDS = 5
PYTHON_NO_BYTECODE = "-B"


def uid_is_integer(value: object) -> bool:
    """Reject non-integer UID claims before any numeric comparison."""
    return isinstance(value, int)


@dataclass(frozen=True, slots=True)
class Configuration:
    """Supplied executable and registration facts, pending native authentication."""

    executable: str
    python: str
    expected: Registration
    rows: tuple[Registration, ...]
    owned_root: str
    listed: int
    user: str
    uid: int


@dataclass(frozen=True, slots=True)
class Invocation:
    """Exact argv and stdin for a peer, before process ownership is established."""

    argv: tuple[str, ...]
    stdin: str
    request: Request
    expected_uid: int


@dataclass(frozen=True, slots=True)
class UnitLimits:
    """Explicit bounds for the short-lived binding peer service."""

    memory_bytes: int
    cpu_percent: int
    tasks: int
    runtime_seconds: int


@dataclass(frozen=True, slots=True)
class UnitInvocation:
    """One named transient service and its bounded peer request."""

    unit: str
    invocation: Invocation
    limits: UnitLimits


@dataclass(frozen=True, slots=True)
class UnitStatus:
    """One observed active service identity, pending process verification."""

    pid: int
    invocation_id: str
    cgroup: str


@dataclass(frozen=True, slots=True)
class ProcessInvocation:
    """A read-only guest process query and its expected identity."""

    argv: tuple[str, ...]
    stdin: str
    request: binding_process.PeerProcessRequest


@dataclass(frozen=True, slots=True)
class StoppedInvocation:
    """A guest termination query tied to a previously observed process."""

    argv: tuple[str, ...]
    stdin: str
    process: binding_process.PeerProcess


@dataclass(frozen=True, slots=True)
class TerminalUnit:
    """A terminal systemd state observed after an active unit."""

    load: str
    active: str
    substate: str
    invocation_id: str


def prepare(
    config: Configuration,
    operation: Operation,
    request: PeerRequest,
) -> Result[Invocation, str]:
    """Build shell-free argv only for a matching WSL2 registration and request.

    These supplied values are consistency checks, not authenticated ownership.
    The caller must observe them natively and enforce peer process containment.
    """
    registration = select(
        config.rows, config.expected, config.owned_root, config.listed
    )
    if isinstance(registration, Err):
        return registration
    path = PurePosixPath(config.python)
    if (
        not config.executable
        or re.fullmatch(r"[a-z_][a-z0-9_-]{0,31}", config.user) is None
        or config.user == "root"
        or not uid_is_integer(config.uid)
        or isinstance(config.uid, bool)
        or config.uid <= 0
        or not path.is_absolute()
        or path.as_posix() != config.python
        or ".." in path.parts
        or any(ord(character) < FIRST_PRINTABLE_ASCII for character in config.python)
        or request.distribution != registration.value.name
        or not binding_peer.valid_request(request)
        or operation not in {"observe", "absence"}
    ):
        return Err("invalid WSL peer invocation")
    message = Request(operation, request)
    return Ok(
        Invocation(
            (
                config.executable,
                "--distribution",
                registration.value.name,
                "--user",
                config.user,
                "--exec",
                config.python,
                "-I",
                "-B",
                "-m",
                "agentctl.check.binding_protocol",
            ),
            binding_protocol.encode(message),
            message,
            config.uid,
        )
    )


def prepare_unit(
    config: Configuration,
    operation: Operation,
    request: PeerRequest,
    limits: UnitLimits,
) -> Result[UnitInvocation, str]:
    """Prepare a dedicated systemd service without claiming process ownership.

    The launcher must authenticate the observed unit and guest process, enforce
    the deadline and prove that the service and descendants have terminated.
    """
    direct = prepare(config, operation, request)
    if isinstance(direct, Err):
        return direct
    values = (
        limits.memory_bytes,
        limits.cpu_percent,
        limits.tasks,
        limits.runtime_seconds,
    )
    if (
        any(
            not uid_is_integer(value) or isinstance(value, bool) or value <= 0
            for value in values
        )
        or limits.cpu_percent > MAX_PEER_CPU_PERCENT
        or limits.tasks > MAX_PEER_TASKS
        or limits.runtime_seconds > MAX_PEER_SECONDS
    ):
        return Err("invalid WSL peer service limits")
    unit = "agentctl-binding-" + request.nonce
    argv = (
        config.executable,
        "--distribution",
        request.distribution,
        "--user",
        "root",
        "--exec",
        "/usr/bin/systemd-run",
        "--quiet",
        "--no-ask-password",
        "--wait",
        "--pipe",
        "--service-type=exec",
        "--expand-environment=no",
        "--unit=" + unit,
        "--uid=" + config.user,
        "--setenv=WSL_DISTRO_NAME=" + request.distribution,
        "--property=MemoryMax=" + str(limits.memory_bytes),
        "--property=MemorySwapMax=0",
        "--property=CPUQuota=" + str(limits.cpu_percent) + "%",
        "--property=TasksMax=" + str(limits.tasks),
        "--property=RuntimeMaxSec=" + str(limits.runtime_seconds) + "s",
        "--property=TimeoutStopSec=" + str(STOP_TIMEOUT_SECONDS) + "s",
        "--property=NoNewPrivileges=yes",
        "--property=ProtectControlGroups=yes",
        "--property=Delegate=no",
        "--property=KillMode=control-group",
        "--",
        *direct.value.argv[6:],
    )
    return Ok(
        UnitInvocation(
            unit,
            Invocation(argv, direct.value.stdin, direct.value.request, config.uid),
            limits,
        )
    )


def unit_query(
    config: Configuration, unit: UnitInvocation
) -> Result[tuple[str, ...], str]:
    """Prepare a read-only systemd query bound to the original peer request."""
    expected = prepare_unit(
        config,
        unit.invocation.request.operation,
        unit.invocation.request.peer,
        unit.limits,
    )
    if isinstance(expected, Err) or expected.value != unit:
        return Err("WSL unit invocation differs")
    return Ok(
        (
            config.executable,
            "--distribution",
            config.expected.name,
            "--user",
            "root",
            "--exec",
            "/usr/bin/systemctl",
            "show",
            unit.unit + ".service",
            "--property=Id,LoadState,ActiveState,SubState,MainPID,ControlGroup,InvocationID,User,MemoryMax,MemorySwapMax,CPUQuotaPerSecUSec,TasksMax,NoNewPrivileges,ProtectControlGroups,Delegate,KillMode,RuntimeMaxUSec,TimeoutStopUSec",
        )
    )


def _quota(value: str) -> Result[int, str]:
    """Convert systemd's integral seconds or milliseconds into microseconds."""
    match = re.fullmatch(r"([0-9]{1,7})(us|ms|s)", value)
    if match is None:
        return Err("invalid WSL unit CPU quota")
    scale = {"us": 1, "ms": 1000, "s": 1000000}[match[2]]
    return Ok(int(match[1]) * scale)


def _duration(value: str) -> Result[int, str]:
    """Parse systemd's integral hour, minute and second duration display."""
    parts = value.split(" ")
    parsed = tuple(re.fullmatch(r"([0-9]{1,4})(h|min|s)", item) for item in parts)
    if not parts or any(item is None for item in parsed):
        return Err("invalid WSL unit duration")
    pairs = tuple((int(item[1]), item[2]) for item in parsed if item is not None)
    order = {"h": 0, "min": 1, "s": 2}
    indices = tuple(order[unit] for _number, unit in pairs)
    if indices != tuple(sorted(set(indices))) or any(
        number > MAX_PEER_SECONDS for number, _unit in pairs
    ):
        return Err("invalid WSL unit duration")
    seconds = sum(
        number * {"h": 3600, "min": 60, "s": 1}[unit] for number, unit in pairs
    )
    return Ok(seconds * MICROSECONDS_PER_SECOND)


def unit_status(
    output: Output, config: Configuration, unit: UnitInvocation
) -> Result[UnitStatus, str]:
    """Validate a systemd observation without treating it as a receipt."""
    query = unit_query(config, unit)
    if isinstance(query, Err) or output.code != 0:
        return Err("WSL unit query failed or differs")
    rows = tuple(line.partition("=") for line in output.stdout.splitlines())
    fields = {name: value for name, _separator, value in rows}
    names = {
        "Id",
        "LoadState",
        "ActiveState",
        "SubState",
        "MainPID",
        "ControlGroup",
        "InvocationID",
        "User",
        "MemoryMax",
        "MemorySwapMax",
        "CPUQuotaPerSecUSec",
        "TasksMax",
        "NoNewPrivileges",
        "ProtectControlGroups",
        "Delegate",
        "KillMode",
        "RuntimeMaxUSec",
        "TimeoutStopUSec",
    }
    if (
        len(rows) != len(fields)
        or set(fields) != names
        or any(sep != "=" for _, sep, _ in rows)
    ):
        return Err("invalid WSL unit fields")
    quota = _quota(fields["CPUQuotaPerSecUSec"])
    runtime = _duration(fields["RuntimeMaxUSec"])
    stop_timeout = _duration(fields["TimeoutStopUSec"])
    expected = {
        "Id": unit.unit + ".service",
        "LoadState": "loaded",
        "ActiveState": "active",
        "SubState": "running",
        "ControlGroup": "/system.slice/" + unit.unit + ".service",
        "User": config.user,
        "MemoryMax": str(unit.limits.memory_bytes),
        "MemorySwapMax": "0",
        "TasksMax": str(unit.limits.tasks),
        "NoNewPrivileges": "yes",
        "ProtectControlGroups": "yes",
        "Delegate": "no",
        "KillMode": "control-group",
    }
    pid = fields["MainPID"]
    identity = fields["InvocationID"]
    if (
        any(fields[name] != value for name, value in expected.items())
        or re.fullmatch(r"[1-9][0-9]*", pid) is None
        or len(pid) > len(str(2**31 - 1))
        or int(pid) > 2**31 - 1
        or re.fullmatch(r"[0-9a-f]{32}", identity) is None
        or identity == "0" * 32
        or isinstance(quota, Err)
        or quota.value != unit.limits.cpu_percent * 10000
        or isinstance(runtime, Err)
        or runtime.value != unit.limits.runtime_seconds * MICROSECONDS_PER_SECOND
        or isinstance(stop_timeout, Err)
        or stop_timeout.value != STOP_TIMEOUT_SECONDS * MICROSECONDS_PER_SECOND
    ):
        return Err("WSL unit identity or limits differ")
    return Ok(UnitStatus(int(pid), identity, fields["ControlGroup"]))


def _observed_response(output: Output, request: Request, uid: int) -> Result[str, str]:
    """Join the peer's declared UID to the prepared invocation."""
    decoded = binding_transport.decode(output.stdout, request.peer)
    if isinstance(decoded, Err):
        return decoded
    return (
        Ok(output.stdout)
        if decoded.value.uid == uid
        else Err("WSL binding peer uid differs")
    )


def _unique_response_fields(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """Refuse ambiguous cleanup response fields."""
    values = dict(pairs)
    if len(values) != len(pairs):
        message = "duplicate cleanup response field"
        raise ValueError(message)
    return values


def process_query(
    config: Configuration, unit: UnitInvocation, status: UnitStatus
) -> Result[ProcessInvocation, str]:
    """Prepare an independent root observer for a previously observed unit PID."""
    checked = unit_query(config, unit)
    request = binding_process.PeerProcessRequest(
        status.pid,
        config.uid,
        status.cgroup,
        config.python,
        unit.invocation.request.peer.nonce,
        status.invocation_id,
        config.expected.name,
    )
    if isinstance(checked, Err) or not binding_process.valid_request(request):
        return Err("invalid WSL peer process query")
    return Ok(
        ProcessInvocation(
            (
                config.executable,
                "--distribution",
                config.expected.name,
                "--user",
                "root",
                "--exec",
                config.python,
                "-I",
                PYTHON_NO_BYTECODE,
                "-m",
                "agentctl.check.binding_process",
            ),
            json.dumps(asdict(request)),
            request,
        )
    )


def process_response(
    output: Output, query: ProcessInvocation
) -> Result[binding_process.PeerProcess, str]:
    """Bind the returned process identity to its complete original query."""
    if output.code != 0:
        return Err("WSL peer process observer failed: " + output.stderr)
    try:
        value: object = json.loads(
            output.stdout, object_pairs_hook=_unique_response_fields
        )
    except (ValueError, UnicodeError):
        return Err("invalid WSL peer process response")
    match value:
        case {
            "request": dict() as request,
            "starttime": int() as starttime,
            **extra,
        } if (
            not extra
            and binding_process.decode(json.dumps(request)) == Ok(query.request)
            and not isinstance(starttime, bool)
            and starttime > 0
        ):
            return Ok(binding_process.PeerProcess(query.request, starttime))
        case _:
            return Err("WSL peer process response differs")


def process_bracket(
    before: UnitStatus, process: binding_process.PeerProcess, after: UnitStatus
) -> Result[binding_process.PeerProcess, str]:
    """Require the same active systemd unit on both sides of process sampling."""
    request = process.request
    if (
        before != after
        or request.pid != before.pid
        or request.group != before.cgroup
        or request.invocation_id != before.invocation_id
        or process.starttime <= 0
    ):
        return Err("WSL unit changed around peer process observation")
    return Ok(process)


def stopped_query(
    config: Configuration, unit: UnitInvocation, process: binding_process.PeerProcess
) -> Result[StoppedInvocation, str]:
    """Prepare a guest termination observation for this exact unit and process."""
    status = UnitStatus(
        process.request.pid, process.request.invocation_id, process.request.group
    )
    original = process_query(config, unit, status)
    if (
        isinstance(original, Err)
        or original.value.request != process.request
        or isinstance(process.starttime, bool)
        or not 0 < process.starttime <= binding_stopped.MAX_STARTTIME
    ):
        return Err("invalid WSL stopped process query")
    argv = (*original.value.argv[:-1], "agentctl.check.binding_stopped")
    return Ok(StoppedInvocation(argv, json.dumps(asdict(process)), process))


def stopped_response(output: Output, query: StoppedInvocation) -> Result[bool, str]:
    """Reject stale, malformed or non-boolean termination observations."""
    if output.code != 0:
        return Err("WSL stopped observer failed: " + output.stderr)
    try:
        value: object = json.loads(
            output.stdout, object_pairs_hook=_unique_response_fields
        )
    except (ValueError, UnicodeError):
        return Err("invalid WSL stopped response")
    match value:
        case {"process": dict() as process, "stopped": bool() as stopped, **extra} if (
            not extra
            and binding_stopped.decode(json.dumps(process)) == Ok(query.process)
        ):
            return Ok(stopped)
        case _:
            return Err("WSL stopped response differs")


def terminal_query(
    config: Configuration, unit: UnitInvocation
) -> Result[tuple[str, ...], str]:
    """Query only the selected unit's terminal state and identity."""
    active = unit_query(config, unit)
    if isinstance(active, Err):
        return active
    return Ok(
        (
            *active.value[:-1],
            "--property=Id,LoadState,ActiveState,SubState,MainPID,ControlGroup,InvocationID",
        )
    )


def terminal_status(
    output: Output, config: Configuration, unit: UnitInvocation, previous: UnitStatus
) -> Result[TerminalUnit, str]:
    """Refuse live, transitioning, foreign or ambiguously encoded units."""
    if isinstance(terminal_query(config, unit), Err) or output.code != 0:
        return Err("WSL terminal unit query failed")
    rows = tuple(line.partition("=") for line in output.stdout.splitlines())
    fields = {name: value for name, _separator, value in rows}
    names = {
        "Id",
        "LoadState",
        "ActiveState",
        "SubState",
        "MainPID",
        "ControlGroup",
        "InvocationID",
    }
    if (
        len(rows) != len(fields)
        or set(fields) != names
        or any(sep != "=" for _, sep, _ in rows)
    ):
        return Err("invalid WSL terminal unit fields")
    load, active, substate, identity = (
        fields["LoadState"],
        fields["ActiveState"],
        fields["SubState"],
        fields["InvocationID"],
    )
    if (
        fields["Id"] != unit.unit + ".service"
        or fields["MainPID"] != "0"
        or fields["ControlGroup"] != ""
        or (load, active, substate)
        not in {
            ("not-found", "inactive", "dead"),
            ("loaded", "inactive", "dead"),
            ("loaded", "failed", "failed"),
        }
        or (identity != previous.invocation_id if load == "loaded" else identity != "")
    ):
        return Err("WSL unit is active, changed or not yet terminal")
    return Ok(TerminalUnit(load, active, substate, identity))


type ObservationCall = Callable[[tuple[str, ...], str | None], Result[Output, str]]


def _observe_unit(
    config: Configuration, unit: UnitInvocation, call: ObservationCall
) -> Result[UnitStatus, str]:
    query = unit_query(config, unit)
    if isinstance(query, Err):
        return query
    output = call(query.value, None)
    return (
        output if isinstance(output, Err) else unit_status(output.value, config, unit)
    )


def _observe_process(
    config: Configuration,
    unit: UnitInvocation,
    status: UnitStatus,
    call: ObservationCall,
) -> Result[binding_process.PeerProcess, str]:
    query = process_query(config, unit, status)
    if isinstance(query, Err):
        return query
    output = call(query.value.argv, query.value.stdin)
    return (
        output
        if isinstance(output, Err)
        else process_response(output.value, query.value)
    )


def observe_unit_process_with(
    config: Configuration, unit: UnitInvocation, call: ObservationCall
) -> Result[binding_process.PeerProcess, str]:
    """Join unit, native process and repeated unit observations in order.

    This is not a receipt: the caller must authenticate the invocation origin,
    preserve the held input, and verify later guest termination.
    """
    before = _observe_unit(config, unit, call)
    if isinstance(before, Err):
        return before
    process = _observe_process(config, unit, before.value, call)
    if isinstance(process, Err):
        return process
    after = _observe_unit(config, unit, call)
    return (
        after
        if isinstance(after, Err)
        else process_bracket(before.value, process.value, after.value)
    )


def observe_unit_process(
    config: Configuration,
    unit: UnitInvocation,
    root: Path,
    environment: Mapping[str, str],
) -> Result[binding_process.PeerProcess, str]:
    """Run the three bounded, shell-free observations against the selected WSL."""

    def call(argv: tuple[str, ...], stdin: str | None) -> Result[Output, str]:
        observed = run(
            list(argv),
            cwd=root,
            env=environment,
            input_text=stdin,
            timeout=OBSERVATION_TIMEOUT_SECONDS,
        )
        return Err(observed.error.message) if isinstance(observed, Err) else observed

    return observe_unit_process_with(config, unit, call)


def _terminal_unit(
    config: Configuration,
    unit: UnitInvocation,
    previous: UnitStatus,
    call: ObservationCall,
) -> Result[TerminalUnit, str]:
    """Read and validate one terminal systemd observation."""
    query = terminal_query(config, unit)
    if isinstance(query, Err):
        return query
    output = call(query.value, None)
    return (
        output
        if isinstance(output, Err)
        else terminal_status(output.value, config, unit, previous)
    )


def _stopped_peer(peer: StoppedInvocation, call: ObservationCall) -> Result[None, str]:
    """Read the original guest identity and reject a live or unknown group."""
    observed = call(peer.argv, peer.stdin)
    if isinstance(observed, Err):
        return observed
    stopped = stopped_response(observed.value, peer)
    if isinstance(stopped, Err):
        return stopped
    return (
        Ok(None)
        if stopped.value is True
        else Err("WSL peer or cgroup remains active or unobservable")
    )


def observe_termination_with(
    config: Configuration,
    unit: UnitInvocation,
    previous: UnitStatus,
    process: binding_process.PeerProcess,
    call: ObservationCall,
) -> Result[None, str]:
    """Bracket the original process/cgroup termination with terminal unit checks.

    The caller must retain and reap the actual host launcher and establish that
    no delayed launcher can create another service before using this observation.
    """
    peer = stopped_query(config, unit, process)
    if isinstance(peer, Err):
        return Err("invalid WSL termination query")
    if isinstance(process_bracket(previous, process, previous), Err):
        return Err("WSL termination process identity differs")
    before = _terminal_unit(config, unit, previous, call)
    if isinstance(before, Err):
        return before
    stopped = _stopped_peer(peer.value, call)
    if isinstance(stopped, Err):
        return stopped
    after = _terminal_unit(config, unit, previous, call)
    if isinstance(after, Err) or before.value != after.value:
        return Err("WSL terminal unit changed during observation")
    return Ok(None)


def observe_termination(
    config: Configuration,
    unit: UnitInvocation,
    process: binding_process.PeerProcess,
    root: Path,
    environment: Mapping[str, str],
) -> Result[None, str]:
    """Observe terminal unit and process states with bounded WSL calls."""

    def call(argv: tuple[str, ...], stdin: str | None) -> Result[Output, str]:
        result = run(
            list(argv),
            cwd=root,
            env=environment,
            input_text=stdin,
            timeout=OBSERVATION_TIMEOUT_SECONDS,
        )
        return Err(result.error.message) if isinstance(result, Err) else result

    previous = UnitStatus(
        process.request.pid, process.request.invocation_id, process.request.group
    )
    return observe_termination_with(config, unit, previous, process, call)


def _cleanup_response(output: Output, invocation: Invocation) -> Result[bool, str]:
    """Validate a cleanup observation's nonce, UID and boolean result."""
    try:
        decoded: object = json.loads(
            output.stdout, object_pairs_hook=_unique_response_fields
        )
    except (ValueError, UnicodeError) as exc:
        return Err("invalid WSL cleanup response: " + str(exc))
    if (
        not isinstance(decoded, dict)
        or set(decoded) != {"nonce", "uid", "absent"}
        or decoded.get("nonce") != invocation.request.peer.nonce
        or not isinstance(decoded.get("uid"), int)
        or isinstance(decoded.get("uid"), bool)
        or decoded.get("uid") != invocation.expected_uid
    ):
        return Err("WSL cleanup identity differs")
    value: object = decoded["absent"]
    if not isinstance(value, bool):
        return Err("invalid WSL cleanup response")
    return Ok(value)


def response(output: Output, invocation: Invocation) -> Result[str | bool, str]:
    """Bind peer output to its request and the expected non-root UID."""
    request = invocation.request
    if (
        not uid_is_integer(invocation.expected_uid)
        or isinstance(invocation.expected_uid, bool)
        or invocation.expected_uid <= 0
    ):
        return Err("invalid expected WSL peer uid")
    if output.code != 0:
        return Err("WSL binding peer failed: " + output.stderr)
    if request.operation == "observe":
        return _observed_response(output, request, invocation.expected_uid)
    return _cleanup_response(output, invocation)
