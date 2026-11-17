# Copyright (c) 2026 agentctl contributors.
"""Observe a live Linux binding peer against a systemd service identity."""

import json
import os
import platform
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath

from agentctl.check import binding_peer, wsl_mount
from agentctl.check.wsl_cgroup import process_identity
from agentctl.foundation import Err, Ok, Result

MAX_REQUEST = 16384
FIRST_PRINTABLE_ASCII = 32
FIRST_SURROGATE = 0xD800
LAST_SURROGATE = 0xDFFF


@dataclass(frozen=True, slots=True)
class PeerProcessRequest:
    """An expected guest process and its nonce-bound service identity."""

    pid: int
    uid: int
    group: str
    python: str
    nonce: str
    invocation_id: str
    distribution: str


@dataclass(frozen=True, slots=True)
class PeerProcess:
    """A live PID and creation tick tied to one requested service."""

    request: PeerProcessRequest
    starttime: int


@dataclass(frozen=True, slots=True)
class ProcessSample:
    """Raw process facts read from one native proc hierarchy."""

    stat: str
    status: str
    cgroup: str
    argv: bytes
    executable: tuple[int, int]
    interpreter: tuple[int, int]


def valid_request(request: PeerProcessRequest) -> bool:
    """Reject aliases, unsafe identities and noncanonical process paths."""
    path = PurePosixPath(request.python)
    return (
        not isinstance(request.pid, bool)
        and 0 < request.pid < 2**31
        and not isinstance(request.uid, bool)
        and request.uid > 0
        and re.fullmatch(r"[0-9a-f]{32}", request.nonce) is not None
        and re.fullmatch(r"[0-9a-f]{32}", request.invocation_id) is not None
        and request.invocation_id != "0" * 32
        and request.group
        == "/system.slice/agentctl-binding-" + request.nonce + ".service"
        and path.is_absolute()
        and path.as_posix() == request.python
        and ".." not in path.parts
        and all(
            ord(character) >= FIRST_PRINTABLE_ASCII
            and not FIRST_SURROGATE <= ord(character) <= LAST_SURROGATE
            for character in request.python
        )
        and binding_peer.valid_request(
            binding_peer.PeerRequest(
                request.distribution, "/source", "/target", request.nonce
            )
        )
    )


def validate_sample(
    request: PeerProcessRequest, sample: ProcessSample
) -> Result[PeerProcess, str]:
    """Join process creation, credentials, argv and executable file identity."""
    if not valid_request(request):
        return Err("invalid peer process request")
    identity = process_identity(sample.stat, request.pid)
    matches = re.findall(
        r"(?m)^Uid:[ \t]+(\d+)[ \t]+(\d+)[ \t]+(\d+)[ \t]+(\d+)[ \t]*$", sample.status
    )
    expected = (request.python, "-I", "-B", "-m", "agentctl.check.binding_protocol")
    if (
        isinstance(identity, Err)
        or re.search(r"\) [ZX] ", sample.stat) is not None
        or len(matches) != 1
        or any(int(value) != request.uid for match in matches for value in match)
        or sample.cgroup != "0::" + request.group + "\n"
        or sample.argv != b"\0".join(item.encode("utf-8") for item in expected) + b"\0"
        or sample.executable != sample.interpreter
        or any(value <= 0 for value in sample.executable)
    ):
        return Err("peer process identity differs")
    return Ok(PeerProcess(request, identity.value.starttime))


def _sample(request: PeerProcessRequest) -> ProcessSample:
    """Read the requested live process and resolved interpreter file identities."""
    proc = Path("/proc") / str(request.pid)
    actual = (proc / "exe").stat()
    expected = Path(request.python).stat()
    return ProcessSample(
        (proc / "stat").read_text(encoding="utf-8", errors="surrogateescape"),
        (proc / "status").read_text(encoding="utf-8"),
        (proc / "cgroup").read_text(encoding="utf-8"),
        (proc / "cmdline").read_bytes(),
        (actual.st_dev, actual.st_ino),
        (expected.st_dev, expected.st_ino),
    )


def _observe(request: PeerProcessRequest) -> Result[PeerProcess, str]:
    """Read Linux host, mount and process facts in their observation order."""
    release = Path("/etc/os-release").read_text(encoding="utf-8")
    host = binding_peer.host_problems(
        platform.system(),
        platform.release(),
        os.environ.get("WSL_DISTRO_NAME", ""),
        request.distribution,
        release,
    )
    if host:
        return Err("peer process host: " + "; ".join(host))
    self_status = Path("/proc/self/status").read_text(encoding="utf-8")
    if re.search(r"(?m)^Uid:\s+0\s+0\s+0\s+0\s*$", self_status) is None:
        return Err("peer process observer is not root")
    before_mount = wsl_mount.observe(Path("/sys/fs/cgroup"))
    if isinstance(before_mount, Err):
        return before_mount
    before = _sample(request)
    after = _sample(request)
    after_mount = wsl_mount.observe(Path("/sys/fs/cgroup"))
    first, second = (
        validate_sample(request, before),
        validate_sample(request, after),
    )
    if (
        isinstance(after_mount, Err)
        or isinstance(first, Err)
        or isinstance(second, Err)
        or before_mount.value != after_mount.value
        or first.value != second.value
        or before.argv != after.argv
        or before.cgroup != after.cgroup
        or before.executable != after.executable
        or before.interpreter != after.interpreter
    ):
        return Err("peer process changed during observation")
    return first


def observe(request: PeerProcessRequest) -> Result[PeerProcess, str]:
    """Bracket process observations with native proc and cgroup mounts.

    The caller must separately authenticate systemd, the launcher and the WSL
    registration. A point-in-time process observation is not a receipt.
    """
    if not valid_request(request) or platform.system() != "Linux":
        return Err("invalid Linux peer process observation")
    try:
        return _observe(request)
    except (OSError, UnicodeError, RuntimeError, ValueError) as exc:
        return Err("cannot observe peer process: " + str(exc))


def _unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """Reject duplicate request keys."""
    result = dict(pairs)
    if len(result) != len(pairs):
        message = "duplicate process request field"
        raise ValueError(message)
    return result


def decode(text: str) -> Result[PeerProcessRequest, str]:
    """Parse a bounded, closed process observation request."""
    if len(text) > MAX_REQUEST:
        return Err("process request too large")
    try:
        data: object = json.loads(text, object_pairs_hook=_unique)
    except (ValueError, UnicodeError):
        return Err("invalid process request")
    match data:
        case {
            "pid": int() as pid,
            "uid": int() as uid,
            "group": str() as group,
            "python": str() as python,
            "nonce": str() as nonce,
            "invocation_id": str() as invocation_id,
            "distribution": str() as distribution,
            **extra,
        } if not extra:
            request = PeerProcessRequest(
                pid, uid, group, python, nonce, invocation_id, distribution
            )
            return (
                Ok(request)
                if valid_request(request)
                else Err("invalid process request")
            )
        case _:
            return Err("invalid process request")


def main() -> int:
    """Read one request and emit the observed process identity as JSON."""
    request = decode(sys.stdin.read(MAX_REQUEST + 1))
    result = request if isinstance(request, Err) else observe(request.value)
    if isinstance(result, Err):
        sys.stderr.write(result.error + "\n")
        return 1
    sys.stdout.write(json.dumps(asdict(result.value)) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
