# Copyright (c) 2026 agentctl contributors.
"""Closed transport for Linux peer observations before Windows-side joining."""

import json
from dataclasses import asdict
from pathlib import Path

from agentctl.check import binding_inventory, phase_reports, wsl_guest_sample
from agentctl.check.binding_peer import PeerObservation, PeerRequest, host_problems
from agentctl.foundation import Err, Ok, Result


def encode(observation: PeerObservation) -> str:
    """Serialize observed values without claiming their provenance is verified."""
    request = observation.request
    return json.dumps(
        {
            "distribution": observation.distribution,
            "source": request.source,
            "target": request.target,
            "nonce": request.nonce,
            "kernel": observation.kernel,
            "release": observation.release,
            "uid": observation.uid,
            "device": observation.device,
            "inode": observation.inode,
            "mountinfo": observation.mountinfo,
            "inventory": observation.inventory,
            "guest": asdict(observation.guest),
        },
        ensure_ascii=True,
        separators=(",", ":"),
    )


def _fields(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """Reject duplicated JSON names before interpreting an observation."""
    values = dict(pairs)
    if len(values) != len(pairs):
        message = "duplicate binding peer field"
        raise ValueError(message)
    return values


def _validate(observation: PeerObservation) -> Result[PeerObservation, str]:
    """Join host claims, mount mapping and inventory identity without attestation."""
    request = observation.request
    if (
        observation.uid <= 0
        or observation.device < 0
        or observation.inode <= 0
        or host_problems(
            "Linux",
            observation.kernel,
            observation.distribution,
            request.distribution,
            observation.release,
        )
    ):
        return Err("binding peer host identity invalid")
    mounts = phase_reports.parse_mountinfo(observation.mountinfo)
    if isinstance(mounts, Err):
        return Err("binding peer mountinfo invalid: " + mounts.error)
    mapping = phase_reports.same_bind_source(
        request.source, request.target, mounts.value
    )
    if isinstance(mapping, Err):
        return Err("binding peer mount invalid: " + mapping.error)
    inventory = binding_inventory.decode(observation.inventory, request.nonce)
    if isinstance(inventory, Err):
        return Err("binding peer inventory invalid: " + inventory.error)
    if not wsl_guest_sample.valid_reading(observation.guest):
        return Err("binding peer guest capacity invalid")
    return Ok(observation)


def _guest(value: object) -> Result[wsl_guest_sample.GuestReading, str]:
    """Decode exact integer guest fields before their consistency check."""
    match value:
        case {
            "affinity": list() as affinity,
            "available_memory": int() as memory,
            "available_swap": int() as swap,
            "volume_size": int() as size,
            "volume_free": int() as free,
            "free_inodes": int() as inodes,
            **extra,
        } if (
            not extra
            and all(
                isinstance(cpu, int) and not isinstance(cpu, bool) for cpu in affinity
            )
            and all(
                not isinstance(item, bool)
                for item in (memory, swap, size, free, inodes)
            )
        ):
            return Ok(
                wsl_guest_sample.GuestReading(
                    tuple(affinity), memory, swap, size, free, inodes
                )
            )
        case _:
            return Err("invalid binding peer guest fields")


def decode_guest_reading(value: object) -> Result[wsl_guest_sample.GuestReading, str]:
    """Decode the shared Linux guest-capacity wire value without attesting it."""
    return _guest(value)


def decode(text: str, request: PeerRequest) -> Result[PeerObservation, str]:
    """Reject stale, malformed or inconsistent peer messages for this request."""
    try:
        value: object = json.loads(text, object_pairs_hook=_fields)
    except (ValueError, UnicodeError) as exc:
        return Err("cannot decode binding peer: " + str(exc))
    match value:
        case {
            "distribution": str() as distribution,
            "source": str() as source,
            "target": str() as target,
            "nonce": str() as nonce,
            "kernel": str() as kernel,
            "release": str() as release,
            "uid": int() as uid,
            "device": int() as device,
            "inode": int() as inode,
            "mountinfo": str() as mountinfo,
            "inventory": str() as inventory,
            "guest": guest,
            **extra,
        } if not extra and all(
            not isinstance(number, bool) for number in (uid, device, inode)
        ):
            if (distribution, source, target, nonce) != (
                request.distribution,
                request.source,
                request.target,
                request.nonce,
            ):
                return Err("binding peer request identity mismatch")
            reading = _guest(guest)
            if isinstance(reading, Err):
                return reading
            return _validate(
                PeerObservation(
                    request,
                    kernel,
                    distribution,
                    release,
                    uid,
                    device,
                    inode,
                    mountinfo,
                    inventory,
                    reading.value,
                )
            )
        case _:
            return Err("invalid binding peer fields")


def join(root: Path, text: str, request: PeerRequest) -> Result[PeerObservation, str]:
    """Compare the peer message to current local bytes without issuing a receipt."""
    remote = decode(text, request)
    if isinstance(remote, Err):
        return remote
    comparison = binding_inventory.compare(root, request.nonce, remote.value.inventory)
    if isinstance(comparison, Err):
        return Err("binding peer comparison: " + comparison.error)
    return remote
