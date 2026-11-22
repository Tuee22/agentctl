# Copyright (c) 2026 agentctl contributors.
"""Read a VM host key through guest control without issuing a binding receipt."""

import os
import re
import secrets
import stat
from dataclasses import dataclass
from pathlib import Path

from agentctl.check import (
    virtualbox_listener,
    virtualbox_observe,
    virtualbox_sessions,
    virtualbox_ssh_key,
)
from agentctl.check.hyperv_observe import ExecutableIdentity, executable_identity
from agentctl.check.virtualbox_listener import ListenerObservation
from agentctl.check.virtualbox_observe import NatRoute
from agentctl.check.virtualbox_ssh_key import PublicKey
from agentctl.foundation import Err, Ok, Result
from agentctl.foundation_process import Child, finish, start, stop
from agentctl.foundation_process_identity import windows_process_image

MAX_PRIVATE_BYTES = 4096
GUEST_TIMEOUT_MS = 10000
HOST_TIMEOUT_SECONDS = 15


@dataclass(frozen=True, slots=True)
class Request:
    """Explicit VM, private files and command inputs for one diagnostic."""

    executable: Path
    identifier: str
    name: str
    route: NatRoute
    user: str
    private_root: Path
    password: Path
    known_hosts: Path
    cwd: Path


@dataclass(frozen=True, slots=True)
class FileFact:
    """An opened file's metadata, without credential contents."""

    device: int
    inode: int
    size: int
    modified: int
    changed: int


@dataclass(frozen=True, slots=True)
class Files:
    """The credential identity and the bounded public known-host record."""

    password: FileFact
    known_hosts: FileFact
    known_text: str


@dataclass(frozen=True, slots=True)
class Observation:
    """A repeated listener and matched key, without provenance attestation."""

    listener: ListenerObservation
    key: PublicKey
    files: Files
    nonce: str


@dataclass(frozen=True, slots=True)
class GuestResponse:
    """Public-key output and the nonce passed to the guest process."""

    text: str
    nonce: str


@dataclass(frozen=True, slots=True)
class _Initial:
    """Facts captured before the guest-control operation."""

    listener: ListenerObservation
    files: Files
    executable: ExecutableIdentity
    nonce: str


@dataclass(frozen=True, slots=True)
class _Results:
    """Independent outcomes collected after starting the operation."""

    guest: Result[str, str]
    files: Result[Files, str]
    listener: Result[ListenerObservation, str]
    executable: Result[ExecutableIdentity, str]


def _fact(value: os.stat_result) -> FileFact:
    """Retain only identity and metadata, never private file contents."""
    return FileFact(
        value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns
    )


def _file(path: Path, root: Path, *, public: bool) -> Result[tuple[FileFact, str], str]:
    """Read only an exact direct-child file and bracket its open-handle identity."""
    try:
        if (
            not root.is_absolute()
            or root.is_symlink()
            or root.is_junction()
            or not root.is_dir()
            or root.resolve(strict=True) != root
            or path.parent != root
            or path.is_symlink()
            or path.is_junction()
        ):
            return Err("private key-file boundary invalid")
        before = path.lstat()
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or before.st_ino <= 0
            or before.st_dev <= 0
            or not 0 < before.st_size <= MAX_PRIVATE_BYTES
        ):
            return Err("private key-file identity invalid")
        with path.open("rb") as stream:
            opened = os.fstat(stream.fileno())
            content = stream.read(virtualbox_ssh_key.MAX_LINE + 1) if public else b""
            closed = os.fstat(stream.fileno())
        after = path.lstat()
        if (
            path.is_symlink()
            or path.is_junction()
            or before.st_nlink != opened.st_nlink
            or opened.st_nlink != closed.st_nlink
            or closed.st_nlink != after.st_nlink
            or _fact(before) != _fact(after)
            or _fact(opened) != _fact(closed)
            or (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
            != (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns)
            or (public and len(content) != before.st_size)
        ):
            return Err("private key file changed during observation")
        text = content.decode("ascii").replace("\r\n", "\n") if public else ""
        return Ok((_fact(after), text))
    except (OSError, RuntimeError, UnicodeError, ValueError):
        return Err("private key file unavailable")


def files(request: Request) -> Result[Files, str]:
    """Inspect both distinct private files without reading the password."""
    if request.password == request.known_hosts:
        return Err("private key files must be distinct")
    match (
        _file(request.password, request.private_root, public=False),
        _file(request.known_hosts, request.private_root, public=True),
    ):
        case (Err() as error, _) | (_, Err() as error):
            return error
        case (Ok((password, _)), Ok((known, text))):
            if (password.device, password.inode) == (known.device, known.inode):
                return Err("private key file identities overlap")
            return Ok(Files(password, known, text))


def argv(request: Request, nonce: str) -> Result[tuple[str, ...], str]:
    """Build a fixed read-only guest-control command with no password value."""
    if (
        re.fullmatch(r"[a-z_][a-z0-9_-]{0,31}", request.user) is None
        or request.user == "root"
        or re.fullmatch(r"[0-9a-f]{32}", nonce) is None
    ):
        return Err("invalid guest-control user")
    return Ok(
        (
            str(request.executable),
            "guestcontrol",
            request.identifier,
            "run",
            "--exe=/usr/bin/head",
            "--arg0=agentctl-key-" + nonce,
            "--username=" + request.user,
            "--passwordfile=" + str(request.password),
            "--timeout=" + str(GUEST_TIMEOUT_MS),
            "--wait-stdout",
            "--wait-stderr",
            "--",
            "-c",
            str(virtualbox_ssh_key.MAX_LINE + 1),
            "/etc/ssh/ssh_host_ed25519_key.pub",
        )
    )


def _stopped(child: Child, primary: str) -> Err[str]:
    """Reap the owned host child while retaining unverified guest termination."""
    match stop(child):
        case Ok():
            return Err(primary + "; guest termination unverified")
        case Err(error):
            return Err(
                primary
                + "; host cleanup: "
                + error.message
                + "; guest termination unverified"
            )


def _wait(child: Child, identity: ExecutableIdentity) -> Result[str, str]:
    """Accept only the expected host process image and successful bounded output."""
    match windows_process_image(child.pid):
        case Err():
            return _stopped(child, "guest-control process image unavailable")
        case Ok(image):
            if not virtualbox_observe.image_matches(identity, image, child.pid):
                return _stopped(child, "guest-control process image differs")
    match finish(child, timeout=HOST_TIMEOUT_SECONDS):
        case Err():
            return _stopped(child, "guest-control host wait failed")
        case Ok(output):
            return (
                Ok(output.stdout)
                if output.code == 0
                and len(output.stdout) <= virtualbox_ssh_key.MAX_LINE
                else Err(
                    "guest-control command failed or output exceeded its bound; "
                    "guest termination unverified"
                )
            )


def _command(
    request: Request, identity: ExecutableIdentity, nonce: str
) -> Result[str, str]:
    """Use one owned native child and never include credential values in errors."""
    match argv(request, nonce):
        case Err() as error:
            return error
        case Ok(arguments):
            match start(list(arguments), cwd=request.cwd, env=os.environ):
                case Err():
                    return Err("cannot start guest-control command")
                case Ok(child):
                    result = _wait(child, identity)
                    session = _session_after(request, identity, child.pid)
                    return combine(result, session)


def combine(result: Result[str, str], session: Result[None, str]) -> Result[str, str]:
    """Keep a session observation failure beside the original command outcome."""
    match (result, session):
        case (Err(primary), Err(followup)):
            return Err(primary + "; " + followup)
        case (Err() as error, _) | (_, Err() as error):
            return error
        case (Ok(text), Ok()):
            return Ok(text)


def _session_after(
    request: Request, identity: ExecutableIdentity, host_pid: int
) -> Result[None, str]:
    """Refuse a visible owned session after the original host process returns."""
    command = [
        str(identity.path),
        "guestcontrol",
        request.identifier,
        "list",
        "sessions",
    ]
    match start(command, cwd=request.cwd, env=os.environ):
        case Err():
            return Err("cannot start guest session listing")
        case Ok(child):
            match _read_session_list(child, identity):
                case Err() as error:
                    return error
                case Ok(sessions):
                    match virtualbox_sessions.owned(
                        sessions, request.identifier, host_pid
                    ):
                        case Err() as error:
                            return error
                        case Ok(None):
                            return Ok(None)
                        case Ok(_):
                            return Err(
                                "owned guest session remains; "
                                "guest termination unverified"
                            )


def _read_session_list(
    child: Child, identity: ExecutableIdentity
) -> Result[tuple[virtualbox_sessions.Session, ...], str]:
    """Read a bounded native session listing through the owned process handle."""
    match windows_process_image(child.pid):
        case Err():
            return _stopped(child, "guest session observer image unavailable")
        case Ok(image):
            if not virtualbox_observe.image_matches(identity, image, child.pid):
                return _stopped(child, "guest session observer image differs")
    match finish(child, timeout=HOST_TIMEOUT_SECONDS):
        case Err():
            return _stopped(child, "guest session observer wait failed")
        case Ok(output):
            if output.code != 0:
                return Err("guest session listing failed")
            return virtualbox_sessions.parse(output.stdout)


def join(
    first: ListenerObservation,
    second: ListenerObservation,
    before: Files,
    after: Files,
    guest: GuestResponse,
) -> Result[Observation, str]:
    """Refuse changed listener or files before comparing the key values."""
    if (
        first != second
        or before != after
        or re.fullmatch(r"[0-9a-f]{32}", guest.nonce) is None
    ):
        return Err("listener or private key files changed")
    match virtualbox_ssh_key.compare(
        guest.text, before.known_text, first.nat.route.host_port
    ):
        case Err() as error:
            return error
        case Ok(key):
            return Ok(Observation(first, key, before, guest.nonce))


def observe(request: Request) -> Result[Observation, str]:
    """Bracket guest-control key reading with local file and listener observations.

    A successful result is not proof of provisioning, guest process containment,
    credential ACLs or continuous SSH peer identity.
    """
    match (executable_identity(request.executable), files(request)):
        case (Err() as error, _) | (_, Err() as error):
            return error
        case (Ok(identity), Ok(before)):
            return _observe(request, identity, before)


def _observe(
    request: Request, identity: ExecutableIdentity, before: Files
) -> Result[Observation, str]:
    """Retain failures while independently rechecking the surrounding observations."""
    match virtualbox_listener.observe(
        request.executable,
        request.identifier,
        request.route,
        name=request.name,
        cwd=request.cwd,
    ):
        case Err() as error:
            return error
        case Ok(first):
            nonce = secrets.token_hex(16)
            guest = _command(request, identity, nonce)
            after = files(request)
            second = virtualbox_listener.observe(
                request.executable,
                request.identifier,
                request.route,
                name=request.name,
                cwd=request.cwd,
            )
            executable = executable_identity(request.executable)
            return _finish(
                _Initial(first, before, identity, nonce),
                _Results(guest, after, second, executable),
            )


def _reason[T](value: Result[T, str]) -> str:
    """Extract a failure message without losing a successful value."""
    match value:
        case Err(error):
            return error
        case Ok():
            return ""


def _executable_reason(
    observed: Result[ExecutableIdentity, str], expected: ExecutableIdentity
) -> str:
    """Reject unavailable or changed executable identity."""
    match observed:
        case Ok(value) if value == expected:
            return ""
        case _:
            return "guest-control executable changed"


def _files_reason(observed: Result[Files, str], expected: Files) -> str:
    """Preserve a file-observation error or a changed file snapshot."""
    match observed:
        case Err(error):
            return error
        case Ok(value):
            return "" if value == expected else "private key files changed"


def _listener_reason(
    observed: Result[ListenerObservation, str], expected: ListenerObservation
) -> str:
    """Preserve a listener error or a changed listener snapshot."""
    match observed:
        case Err(error):
            return error
        case Ok(value):
            return "" if value == expected else "listener changed"


def _finish(initial: _Initial, results: _Results) -> Result[Observation, str]:
    """Keep each independent post-command failure alongside a primary error."""
    problems = tuple(
        text
        for text in (
            _reason(results.guest),
            _files_reason(results.files, initial.files),
            _listener_reason(results.listener, initial.listener),
            _executable_reason(results.executable, initial.executable),
        )
        if text
    )
    if problems:
        return Err("; ".join(problems))
    match (results.guest, results.files, results.listener):
        case (Ok(text), Ok(later_files), Ok(later_listener)):
            return join(
                initial.listener,
                later_listener,
                initial.files,
                later_files,
                GuestResponse(text, initial.nonce),
            )
        case _:
            return Err("incomplete guest-control observation")
