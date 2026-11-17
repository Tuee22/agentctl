# Copyright (c) 2026 agentctl contributors.
"""Linux-side observations for a pre-gate WSL source-binding exchange."""

import os
import platform
import re
import stat
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from agentctl.check import (
    binding_challenge,
    binding_inventory,
    phase_reports,
    wsl_guest_sample,
)
from agentctl.check.evidence import FIRST_SURROGATE, LAST_SURROGATE
from agentctl.foundation import Err, Ok, Result


@dataclass(frozen=True, slots=True)
class PeerRequest:
    """Expected Linux source mapping and nonce supplied by the initiating host."""

    distribution: str
    source: str
    target: str
    nonce: str


@dataclass(frozen=True, slots=True)
class PeerObservation:
    """Direct peer observations, not an authenticated binding receipt."""

    request: PeerRequest
    kernel: str
    distribution: str
    release: str
    uid: int
    device: int
    inode: int
    mountinfo: str
    inventory: str
    guest: wsl_guest_sample.GuestReading


def host_problems(
    family: str, kernel: str, distribution: str, requested: str, release: str
) -> tuple[str, ...]:
    """Refuse observations outside the requested Debian WSL2 environment."""
    ids = re.findall(r'(?m)^ID=(?:"([^"\n]+)"|([^\s"\n]+))$', release)
    observed = tuple(quoted or unquoted for quoted, unquoted in ids)
    return (
        *(
            ("not Linux WSL2",)
            if family != "Linux" or "microsoft-standard-wsl2" not in kernel.lower()
            else ()
        ),
        *(
            ("distribution identity mismatch",)
            if not requested or distribution != requested
            else ()
        ),
        *(("not Debian",) if observed != ("debian",) else ()),
    )


def valid_request(request: PeerRequest) -> bool:
    """Refuse aliases and ambiguous distribution and nonce values."""
    return not (
        not request.distribution.strip()
        or any(
            ord(character) < phase_reports.FIRST_PRINTABLE_ASCII
            or FIRST_SURROGATE <= ord(character) <= LAST_SURROGATE
            or character in "/\\"
            for character in request.distribution
        )
        or re.fullmatch(r"[0-9a-f]{32}", request.nonce) is None
        or any(
            not PurePosixPath(path).is_absolute()
            or PurePosixPath(path).as_posix() != path
            or ".." in PurePosixPath(path).parts
            for path in (request.source, request.target)
        )
    )


def _mount(request: PeerRequest, mountinfo: str) -> Result[tuple[int, int], str]:
    """Join kernel mapping to canonical directory and inode observations."""
    mounts = phase_reports.parse_mountinfo(mountinfo)
    if isinstance(mounts, Err):
        return Err("binding peer mountinfo: " + mounts.error)
    mapping = phase_reports.same_bind_source(
        request.source, request.target, mounts.value
    )
    if isinstance(mapping, Err):
        return Err("binding peer mount: " + mapping.error)
    source, target = Path(request.source), Path(request.target)
    if source.resolve(strict=True) != source or target.resolve(strict=True) != target:
        return Err("binding peer paths are not canonical")
    original, bound = source.stat(), target.stat()
    if (
        not stat.S_ISDIR(original.st_mode)
        or not stat.S_ISDIR(bound.st_mode)
        or (original.st_dev, original.st_ino) != (bound.st_dev, bound.st_ino)
    ):
        return Err("binding peer source identities differ")
    return Ok((original.st_dev, original.st_ino))


def _exchange(
    request: PeerRequest,
    identity: tuple[str, str, str, int],
    mountinfo: str,
    source_id: tuple[int, int],
) -> Result[PeerObservation, str]:
    """Answer only after host and mount checks, then observe the live tree."""
    target = Path(request.target)
    answered = binding_challenge.answer(target, request.nonce)
    if isinstance(answered, Err):
        return Err("binding peer challenge: " + answered.error)
    inventory = binding_inventory.observe(target, request.nonce)
    if isinstance(inventory, Err):
        return Err("binding peer inventory: " + inventory.error)
    guest = wsl_guest_sample.observe(Path("/"))
    if isinstance(guest, Err):
        return Err("binding peer guest capacity: " + guest.error)
    return Ok(
        PeerObservation(
            request,
            identity[0],
            identity[1],
            identity[2],
            identity[3],
            source_id[0],
            source_id[1],
            mountinfo,
            inventory.value,
            guest.value,
        )
    )


def _identity(request: PeerRequest) -> Result[tuple[str, str, str, int], str]:
    """Observe actual Linux distribution, kernel and effective user identity."""
    if platform.system() != "Linux":
        return Err("binding peer requires Linux")
    release = Path("/etc/os-release").read_text(encoding="utf-8")
    kernel = platform.release()
    distribution = os.environ.get("WSL_DISTRO_NAME", "")
    problems = host_problems(
        platform.system(),
        kernel,
        distribution,
        request.distribution,
        release,
    )
    if problems:
        return Err("binding peer host: " + "; ".join(problems))
    status = Path("/proc/self/status").read_text(encoding="utf-8")
    uid = re.search(r"(?m)^Uid:\s+\d+\s+(\d+)\s+\d+\s+\d+\s*$", status)
    if uid is None or int(uid.group(1)) == 0:
        return Err("binding peer effective uid unavailable")
    return Ok((kernel, distribution, release, int(uid.group(1))))


@dataclass(frozen=True, slots=True)
class ObservationOperations:
    """Explicit effect boundary for observing one peer exchange."""

    identity: Callable[[PeerRequest], Result[tuple[str, str, str, int], str]]
    mountinfo: Callable[[], str]
    mount: Callable[[PeerRequest, str], Result[tuple[int, int], str]]
    exchange: Callable[
        [PeerRequest, tuple[str, str, str, int], str, tuple[int, int]],
        Result[PeerObservation, str],
    ]


def observe_with(
    request: PeerRequest, operations: ObservationOperations
) -> Result[PeerObservation, str]:
    """Bracket the exchange and inventory with native mount observations."""
    identity = operations.identity(request)
    if isinstance(identity, Err):
        return identity
    mountinfo = operations.mountinfo()
    mapping = operations.mount(request, mountinfo)
    if isinstance(mapping, Err):
        return mapping
    observed = operations.exchange(request, identity.value, mountinfo, mapping.value)
    if isinstance(observed, Err):
        return observed
    final_mountinfo = operations.mountinfo()
    final_mapping = operations.mount(request, final_mountinfo)
    if isinstance(final_mapping, Err):
        return final_mapping
    if final_mountinfo != mountinfo or final_mapping.value != mapping.value:
        return Err("binding peer mount changed during exchange")
    return observed


def observe(request: PeerRequest) -> Result[PeerObservation, str]:
    """Read kernel mount identity, answer the nonce and inventory live bytes.

    This operation alone does not prove Windows-side origin, distro version,
    resource limits, cleanup, or the integrity of an enclosing gate run.
    """
    if not valid_request(request):
        return Err("invalid binding peer request")
    try:
        return observe_with(
            request,
            ObservationOperations(
                _identity,
                lambda: Path("/proc/self/mountinfo").read_text(encoding="utf-8"),
                _mount,
                _exchange,
            ),
        )
    except (OSError, UnicodeError, RuntimeError) as exc:
        return Err("cannot observe binding peer: " + str(exc))


def sentinel_absent(root: Path, nonce: str) -> Result[bool, str]:
    """Observe absence without following a dangling sentinel symlink."""
    directory = binding_challenge.challenge_directory(root, nonce)
    if isinstance(directory, Err):
        return directory
    try:
        directory.value.lstat()
        return Ok(value=False)
    except FileNotFoundError:
        return Ok(value=True)
    except OSError as exc:
        return Err("cannot observe binding cleanup: " + str(exc))


def _observe_absence(request: PeerRequest) -> Result[bool, str]:
    """Take the underlying host, mount and absence observations."""
    identity = _identity(request)
    if isinstance(identity, Err):
        return identity
    first_info = Path("/proc/self/mountinfo").read_text(encoding="utf-8")
    first = _mount(request, first_info)
    if isinstance(first, Err):
        return first
    absent = sentinel_absent(Path(request.target), request.nonce)
    second_info = Path("/proc/self/mountinfo").read_text(encoding="utf-8")
    second = _mount(request, second_info)
    if isinstance(second, Err):
        return second
    if first_info != second_info or first.value != second.value:
        return Err("binding peer mount changed during cleanup observation")
    return absent


def observe_absence(request: PeerRequest) -> Result[bool, str]:
    """Recheck host and mount identity around the peer's cleanup observation."""
    if not valid_request(request):
        return Err("invalid binding peer request")
    try:
        return _observe_absence(request)
    except (OSError, UnicodeError, RuntimeError) as exc:
        return Err("cannot observe binding peer cleanup: " + str(exc))


def absence_with_identity(
    request: PeerRequest,
    identity: Callable[[PeerRequest], Result[tuple[str, str, str, int], str]],
    observe: Callable[[PeerRequest], Result[bool, str]],
) -> Result[tuple[bool, int], str]:
    """Bracket cleanup observation with the same independently observed identity."""
    before = identity(request)
    if isinstance(before, Err):
        return before
    absent = observe(request)
    if isinstance(absent, Err):
        return absent
    after = identity(request)
    if isinstance(after, Err):
        return after
    if before.value != after.value:
        return Err("binding peer identity changed during cleanup")
    return Ok((absent.value, before.value[3]))


def observe_absence_identity(request: PeerRequest) -> Result[tuple[bool, int], str]:
    """Observe cleanup and UID without claiming the launch is authenticated."""
    if not valid_request(request):
        return Err("invalid binding peer request")
    try:
        return absence_with_identity(request, _identity, _observe_absence)
    except (OSError, UnicodeError, RuntimeError) as exc:
        return Err("cannot observe binding peer cleanup: " + str(exc))
