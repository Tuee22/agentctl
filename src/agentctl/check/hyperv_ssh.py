# Copyright (c) 2026 agentctl contributors.
"""Construct a narrowly configured SSH guest observer without launching it."""

import base64
import binascii
import hashlib
import ipaddress
import re
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from agentctl.check.hyperv_observe import (
    ExecutableIdentity,
    executable_identity,
    system_powershell,
)
from agentctl.foundation import Err, Ok, Result

ED25519_PREFIX = b"\x00\x00\x00\x0bssh-ed25519\x00\x00\x00\x20"
ED25519_BYTES = 32
HOST_KEY_FIELDS = 3
MAX_PORT = 65535
DEFAULT_PORT = 22


@dataclass(frozen=True, slots=True)
class Connection:
    """Provisioned connection inputs; construction does not establish their trust."""

    executable: Path
    private_key: Path
    known_hosts: Path
    address: str
    port: int
    user: str
    guest_python: str
    host_fingerprint: str


@dataclass(frozen=True, slots=True)
class Prepared:
    """Preflight arguments and file identities, not an authenticated guest session."""

    argv: tuple[str, ...]
    ssh: ExecutableIdentity
    known_hosts: ExecutableIdentity
    private_key: ExecutableIdentity = field(repr=False)


def prepare(
    connection: Connection, *, source_root: Path, private_root: Path
) -> Result[Prepared, str]:
    """Bind a pinned host key to contained files and the Windows system SSH path.

    The caller must recheck these identities around process execution and observe
    the VM network mapping, peer lifecycle and credential permissions separately.
    """
    powershell = system_powershell()
    if isinstance(powershell, Err):
        return powershell
    supplied_paths = (
        source_root,
        private_root,
        connection.executable,
        connection.private_key,
        connection.known_hosts,
    )
    if any(not path.is_absolute() or ".." in path.parts for path in supplied_paths):
        return Err("SSH observer paths must be absolute and unambiguous")
    try:
        source = source_root.resolve(strict=True)
        private = private_root.resolve(strict=True)
        if (
            source_root.is_symlink()
            or private_root.is_symlink()
            or not source.is_dir()
            or not private.is_dir()
            or private == source
            or private.is_relative_to(source)
            or source.is_relative_to(private)
        ):
            return Err("invalid private SSH storage boundary")
        expected_ssh = powershell.value.parents[2] / "OpenSSH" / "ssh.exe"
        actual_ssh = connection.executable.resolve(strict=True)
        key = connection.private_key.resolve(strict=True)
        hosts = connection.known_hosts.resolve(strict=True)
        if (
            actual_ssh != expected_ssh.resolve(strict=True)
            or connection.executable.is_symlink()
            or connection.private_key.is_symlink()
            or connection.known_hosts.is_symlink()
            or not key.is_relative_to(private)
            or not hosts.is_relative_to(private)
            or key == hosts
        ):
            return Err("SSH executable or credentials escape their owned boundary")
        return _prepare_files(connection, source, actual_ssh, key, hosts)
    except (OSError, UnicodeError, RuntimeError, ValueError) as exc:
        return Err("cannot prepare Hyper-V SSH observer: " + str(exc))


def _prepare_files(
    connection: Connection, source: Path, actual_ssh: Path, key: Path, hosts: Path
) -> Result[Prepared, str]:
    """Read and reobserve the canonical files during preflight."""
    observed_ssh = executable_identity(actual_ssh)
    observed_key = executable_identity(key)
    observed_hosts = executable_identity(hosts)
    if (
        not isinstance(observed_ssh, Ok)
        or not isinstance(observed_key, Ok)
        or not isinstance(observed_hosts, Ok)
    ):
        return Err("SSH observer file identity unavailable")
    raw_hosts = hosts.read_bytes()
    if hashlib.sha256(raw_hosts).hexdigest() != observed_hosts.value.digest:
        return Err("known-hosts file changed during preparation")
    text = raw_hosts.decode("utf-8")
    canonical = Connection(
        actual_ssh,
        key,
        hosts,
        connection.address,
        connection.port,
        connection.user,
        connection.guest_python,
        connection.host_fingerprint,
    )
    argv = arguments(canonical, source_root=source, known_hosts_text=text)
    if isinstance(argv, Err):
        return argv
    if (
        executable_identity(actual_ssh) != observed_ssh
        or executable_identity(key) != observed_key
        or executable_identity(hosts) != observed_hosts
    ):
        return Err("SSH observer files changed during preparation")
    return Ok(
        Prepared(
            argv.value, observed_ssh.value, observed_hosts.value, observed_key.value
        )
    )


def host_key_problem(text: str, address: str, fingerprint: str) -> str | None:
    """Match exactly one unhashed, pinned Ed25519 key to the VM's IP address."""
    lines = text.splitlines()
    if len(lines) != 1:
        return "known-hosts file must contain exactly one key"
    fields = lines[0].split()
    if (
        len(fields) != HOST_KEY_FIELDS
        or fields[0] != address
        or fields[1] != "ssh-ed25519"
    ):
        return "known-hosts key does not match the VM address"
    try:
        key = base64.b64decode(fields[2], validate=True)
    except (ValueError, binascii.Error):
        return "invalid known-hosts key encoding"
    if (
        not key.startswith(ED25519_PREFIX)
        or len(key) != len(ED25519_PREFIX) + ED25519_BYTES
    ):
        return "invalid Ed25519 host key"
    digest = base64.b64encode(hashlib.sha256(key).digest()).decode("ascii").rstrip("=")
    return (
        None if fingerprint == "SHA256:" + digest else "host key fingerprint mismatch"
    )


def arguments(
    connection: Connection, *, source_root: Path, known_hosts_text: str
) -> Result[tuple[str, ...], str]:
    """Build shell-free local argv with a fixed, safely constrained guest command.

    The caller must inspect and bracket the actual files, VM network identity,
    process lifetime and peer. This calculation does not launch or authenticate one.
    """
    paths = (connection.executable, connection.private_key, connection.known_hosts)
    if (
        not source_root.is_absolute()
        or ".." in source_root.parts
        or any(not path.is_absolute() or ".." in path.parts for path in paths)
        or any(path.is_relative_to(source_root) for path in paths)
        or len(set(paths)) != len(paths)
    ):
        return Err("invalid SSH observer file boundary")
    try:
        address = ipaddress.IPv4Address(connection.address)
    except ipaddress.AddressValueError:
        return Err("invalid Hyper-V guest address")
    if (
        str(address) != connection.address
        or address.is_unspecified
        or address.is_multicast
        or isinstance(connection.port, bool)
        or not 1 <= connection.port <= MAX_PORT
        or re.fullmatch(r"[a-z_][a-z0-9_-]{0,31}", connection.user) is None
        or re.fullmatch(r"/[A-Za-z0-9_./-]+", connection.guest_python) is None
        or ".." in PurePosixPath(connection.guest_python).parts
        or PurePosixPath(connection.guest_python).as_posix() != connection.guest_python
    ):
        return Err("invalid Hyper-V SSH connection")
    host_label = (
        connection.address
        if connection.port == DEFAULT_PORT
        else f"[{connection.address}]:{connection.port}"
    )
    key_problem = host_key_problem(
        known_hosts_text, host_label, connection.host_fingerprint
    )
    if key_problem is not None:
        return Err(key_problem)
    remote = (
        "env PYTHONDONTWRITEBYTECODE=1 "
        + connection.guest_python
        + " -m agentctl.check.hyperv_guest_protocol"
    )
    return Ok(
        (
            str(connection.executable),
            "-F",
            "NUL",
            "-T",
            "-i",
            str(connection.private_key),
            "-p",
            str(connection.port),
            "-o",
            "BatchMode=yes",
            "-o",
            "IdentitiesOnly=yes",
            "-o",
            "StrictHostKeyChecking=yes",
            "-o",
            "UpdateHostKeys=no",
            "-o",
            "ClearAllForwardings=yes",
            "-o",
            "GlobalKnownHostsFile=NUL",
            "-o",
            "UserKnownHostsFile=" + str(connection.known_hosts),
            connection.user + "@" + connection.address,
            remote,
        )
    )
