# Copyright (c) 2026 agentctl contributors.
"""Nonce-bound VirtualBox guest capacity observations, not authenticated receipts."""

import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath

from agentctl.check import (
    binding_transport,
    virtualbox_guest,
    virtualbox_guest_protocol,
)
from agentctl.check import wsl_guest_sample as guest_sample
from agentctl.check.hyperv_guest import GuestIdentity
from agentctl.foundation import Err, Ok, Result

MAX_REQUEST = 4096
MAX_RESPONSE = 16384
FIRST_PRINTABLE = 32
FIRST_SURROGATE = 0xD800
LAST_SURROGATE = 0xDFFF


@dataclass(frozen=True, slots=True)
class Request:
    """A fresh nonce and the guest's intended private workload storage path."""

    nonce: str
    storage: str


@dataclass(frozen=True, slots=True)
class Observation:
    """Guest-supplied identity and resource facts, not proof of their origin."""

    request: Request
    identity: GuestIdentity
    reading: guest_sample.GuestReading


def valid_request(request: Request) -> bool:
    """Refuse stale-shaped nonces and noncanonical Linux storage paths."""
    path = PurePosixPath(request.storage)
    return (
        re.fullmatch(r"[0-9a-f]{32}", request.nonce) is not None
        and path.is_absolute()
        and path.as_posix() == request.storage
        and not request.storage.startswith("//")
        and ".." not in path.parts
        and all(
            ord(character) >= FIRST_PRINTABLE
            and not FIRST_SURROGATE <= ord(character) <= LAST_SURROGATE
            for character in request.storage
        )
    )


def _fields(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """Reject duplicate JSON keys at every nesting level."""
    values = dict(pairs)
    if len(values) != len(pairs):
        message = "duplicate guest capacity field"
        raise ValueError(message)
    return values


def request_text(request: Request) -> Result[str, str]:
    """Serialize only a valid request."""
    if not valid_request(request):
        return Err("invalid VirtualBox guest capacity request")
    text = json.dumps(asdict(request), ensure_ascii=True, separators=(",", ":"))
    return (
        Ok(text)
        if len(text) <= MAX_REQUEST
        else Err("guest capacity request too large")
    )


def decode_request(text: str) -> Result[Request, str]:
    """Decode one bounded request with no extra or duplicate fields."""
    if len(text) > MAX_REQUEST:
        return Err("VirtualBox guest capacity request too large")
    try:
        value: object = json.loads(text, object_pairs_hook=_fields)
    except (ValueError, UnicodeError):
        return Err("invalid VirtualBox guest capacity request")
    match value:
        case {"nonce": str() as nonce, "storage": str() as storage, **extra} if (
            not extra
        ):
            request = Request(nonce, storage)
            return (
                Ok(request)
                if valid_request(request)
                else Err("invalid guest capacity request values")
            )
        case _:
            return Err("invalid guest capacity request fields")


def encode(observation: Observation) -> Result[str, str]:
    """Encode complete values without asserting a trusted transport or peer."""
    if not valid_request(observation.request) or not guest_sample.valid_reading(
        observation.reading
    ):
        return Err("invalid guest capacity observation")
    identity = virtualbox_guest_protocol.encode(
        observation.request.nonce, observation.identity
    )
    if isinstance(identity, Err):
        return identity
    try:
        text = json.dumps(
            {
                "nonce": observation.request.nonce,
                "storage": observation.request.storage,
                "identity": identity.value,
                "reading": asdict(observation.reading),
            },
            ensure_ascii=True,
            separators=(",", ":"),
        )
    except (ValueError, UnicodeError):
        return Err("cannot encode guest capacity observation")
    return (
        Ok(text)
        if len(text) <= MAX_RESPONSE
        else Err("guest capacity response too large")
    )


def decode(text: str, request: Request) -> Result[Observation, str]:
    """Require the original request and strict typed identity and capacity values."""
    if len(text) > MAX_RESPONSE or not valid_request(request):
        return Err("invalid guest capacity response or request")
    try:
        value: object = json.loads(text, object_pairs_hook=_fields)
    except (ValueError, UnicodeError):
        return Err("invalid guest capacity response")
    match value:
        case {
            "nonce": str() as nonce,
            "storage": str() as storage,
            "identity": str() as raw_identity,
            "reading": reading,
            **extra,
        } if not extra and (nonce, storage) == (request.nonce, request.storage):
            identity = virtualbox_guest_protocol.decode(raw_identity, nonce)
            guest = binding_transport.decode_guest_reading(reading)
            if isinstance(identity, Err):
                return identity
            if isinstance(guest, Err) or not guest_sample.valid_reading(guest.value):
                return Err("invalid guest capacity values")
            return Ok(Observation(request, identity.value, guest.value))
        case _:
            return Err("guest capacity response does not match request")


def observe(request: Request) -> Result[Observation, str]:
    """Bracket local resource readings with matching guest identity observations."""
    if not valid_request(request):
        return Err("invalid guest capacity request")
    first = virtualbox_guest.observe()
    if isinstance(first, Err):
        return first
    reading = guest_sample.observe(Path(request.storage))
    if isinstance(reading, Err):
        return reading
    second = virtualbox_guest.observe()
    if isinstance(second, Err):
        return second
    return join(request, first.value, reading.value, second.value)


def join(
    request: Request,
    first: GuestIdentity,
    reading: guest_sample.GuestReading,
    second: GuestIdentity,
) -> Result[Observation, str]:
    """Join complete local values without attesting their collection or origin."""
    if (
        not valid_request(request)
        or virtualbox_guest.problems(first)
        or not guest_sample.valid_reading(reading)
        or first != second
    ):
        return Err("guest identity or capacity observation is invalid or changed")
    return Ok(Observation(request, first, reading))


def main() -> int:
    """Read a bounded request and emit one response or a noninteractive refusal."""
    request = decode_request(sys.stdin.read(MAX_REQUEST + 1))
    if isinstance(request, Err):
        sys.stderr.write(request.error + "\n")
        return 1
    observed = observe(request.value)
    response = observed if isinstance(observed, Err) else encode(observed.value)
    if isinstance(response, Err):
        sys.stderr.write(response.error + "\n")
        return 1
    sys.stdout.write(response.value + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
