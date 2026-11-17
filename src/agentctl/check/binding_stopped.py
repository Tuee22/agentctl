# Copyright (c) 2026 agentctl contributors.
"""Observe termination of one nonce-bound guest peer and its cgroup."""

import json
import os
import platform
import re
import sys
from dataclasses import asdict
from pathlib import Path, PurePosixPath

from agentctl.check import binding_peer, binding_process, wsl_mount
from agentctl.check.wsl_cgroup import process_identity
from agentctl.foundation import Err, Ok, Result

MAX_REQUEST = 16384
MAX_STARTTIME = 2**64 - 1


def _unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """Refuse duplicate JSON fields at every level."""
    result = dict(pairs)
    if len(result) != len(pairs):
        message = "duplicate stopped request field"
        raise ValueError(message)
    return result


def decode(text: str) -> Result[binding_process.PeerProcess, str]:
    """Parse a closed, bounded previously observed process identity."""
    if len(text) > MAX_REQUEST:
        return Err("stopped request too large")
    try:
        value: object = json.loads(text, object_pairs_hook=_unique)
    except (ValueError, UnicodeError):
        return Err("invalid stopped request")
    match value:
        case {"request": dict() as request, "starttime": int() as start, **extra} if (
            not extra and not isinstance(start, bool) and 0 < start <= MAX_STARTTIME
        ):
            parsed = binding_process.decode(json.dumps(request))
            return (
                parsed
                if isinstance(parsed, Err)
                else Ok(binding_process.PeerProcess(parsed.value, start))
            )
        case _:
            return Err("invalid stopped request")


def _gone(process: binding_process.PeerProcess, proc: Path) -> Result[bool, str]:
    """Distinguish an absent or recycled PID from the original process."""
    request = process.request
    try:
        stat = (proc / str(request.pid) / "stat").read_text(
            encoding="utf-8", errors="surrogateescape"
        )
    except FileNotFoundError:
        return Ok(value=True)
    identity = process_identity(stat, request.pid)
    return (
        identity
        if isinstance(identity, Err)
        else Ok(identity.value.starttime != process.starttime)
    )


def _empty(group: Path) -> Result[bool, str]:
    """Use cgroup v2's recursive populated flag without following aliases."""
    if group.resolve(strict=False) != group or group.is_symlink():
        return Err("stopped cgroup path differs")
    try:
        group.lstat()
    except FileNotFoundError:
        return Ok(value=True)
    events_path = group / "cgroup.events"
    if events_path.is_symlink():
        return Err("stopped cgroup events is a symlink")
    populated = tuple(
        str(match[1])
        for match in re.finditer(
            r"(?m)^populated ([01])$", events_path.read_text(encoding="ascii")
        )
    )
    if len(populated) != 1:
        return Err("invalid stopped cgroup events")
    return Ok(populated[0] == "0")


def sample(
    process: binding_process.PeerProcess, proc: Path, cgroup: Path
) -> Result[tuple[bool, bool], str]:
    """Read the original PID identity and recursively populated cgroup state."""
    request = process.request
    if (
        not binding_process.valid_request(request)
        or isinstance(process.starttime, bool)
        or not 0 < process.starttime <= MAX_STARTTIME
    ):
        return Err("invalid stopped process identity")
    group = cgroup / PurePosixPath(request.group).relative_to("/")
    try:
        gone, empty = _gone(process, proc), _empty(group)
    except (OSError, UnicodeError, RuntimeError, ValueError) as exc:
        return Err("cannot observe stopped process: " + str(exc))
    match gone, empty:
        case (Err(error), _) | (_, Err(error)):
            return Err(error)
        case Ok(gone_value), Ok(empty_value):
            return Ok((gone_value, empty_value))


def observe(process: binding_process.PeerProcess) -> Result[bool, str]:
    """Bracket two native termination samples with verified kernel mounts.

    This does not prove earlier cgroup containment, the systemd unit lifecycle,
    or that a delayed launcher cannot create a new peer under the same name.
    """
    if platform.system() != "Linux" or not binding_process.valid_request(
        process.request
    ):
        return Err("invalid Linux stopped observation")
    try:
        release = Path("/etc/os-release").read_text(encoding="utf-8")
        host = binding_peer.host_problems(
            platform.system(),
            platform.release(),
            os.environ.get("WSL_DISTRO_NAME", ""),
            process.request.distribution,
            release,
        )
        status = Path("/proc/self/status").read_text(encoding="utf-8")
        if host or re.search(r"(?m)^Uid:\s+0\s+0\s+0\s+0\s*$", status) is None:
            return Err("stopped process observer host differs")
        root = Path("/sys/fs/cgroup")
        before_mount = wsl_mount.observe(root)
        if isinstance(before_mount, Err):
            return before_mount
        first = sample(process, Path("/proc"), root)
        second = sample(process, Path("/proc"), root)
        after_mount = wsl_mount.observe(root)
        if (
            isinstance(first, Err)
            or isinstance(second, Err)
            or isinstance(after_mount, Err)
            or first.value != second.value
            or before_mount.value != after_mount.value
        ):
            return Err("stopped process observation changed or failed")
        return Ok(first.value == (True, True))
    except (OSError, UnicodeError, RuntimeError, ValueError) as exc:
        return Err("cannot observe stopped process: " + str(exc))


def main() -> int:
    """Read a process identity and emit its bounded termination observation."""
    parsed = decode(sys.stdin.read(MAX_REQUEST + 1))
    result = parsed if isinstance(parsed, Err) else observe(parsed.value)
    if isinstance(result, Err):
        sys.stderr.write(result.error + "\n")
        return 1
    if isinstance(parsed, Err):
        return 1
    sys.stdout.write(
        json.dumps({"process": asdict(parsed.value), "stopped": result.value}) + "\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
