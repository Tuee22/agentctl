# Copyright (c) 2026 agentctl contributors.
"""Closed stdin protocol for one independently launched binding peer."""

import json
import sys
from dataclasses import dataclass
from typing import Literal

from agentctl.check import binding_peer, binding_transport
from agentctl.check.binding_peer import PeerRequest
from agentctl.foundation import Err, Ok, Result

MAX_REQUEST = 16384
type Operation = Literal["observe", "absence"]


@dataclass(frozen=True, slots=True)
class Request:
    """One operation and its nonce-bound source mapping."""

    operation: Operation
    peer: PeerRequest


def _fields(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """Refuse duplicate JSON keys at every level."""
    value = dict(pairs)
    if len(value) != len(pairs):
        message = "duplicate protocol field"
        raise ValueError(message)
    return value


def encode(request: Request) -> str:
    """Serialize a request with no shell interpretation."""
    return json.dumps(
        {
            "operation": request.operation,
            "distribution": request.peer.distribution,
            "source": request.peer.source,
            "target": request.peer.target,
            "nonce": request.peer.nonce,
        },
        ensure_ascii=True,
        separators=(",", ":"),
    )


def decode(text: str) -> Result[Request, str]:
    """Refuse oversized, malformed, duplicate or unrecognized requests."""
    if len(text) > MAX_REQUEST:
        return Err("binding request too large")
    try:
        data: object = json.loads(text, object_pairs_hook=_fields)
    except (ValueError, UnicodeError) as exc:
        return Err("invalid binding request: " + str(exc))
    match data:
        case {
            "operation": str() as raw_operation,
            "distribution": str() as distribution,
            "source": str() as source,
            "target": str() as target,
            "nonce": str() as nonce,
            **extra,
        } if not extra and raw_operation in {"observe", "absence"}:
            operation: Operation = (
                "observe" if raw_operation == "observe" else "absence"
            )
            return Ok(
                Request(operation, PeerRequest(distribution, source, target, nonce))
            )
        case _:
            return Err("invalid binding request fields")


def dispatch(request: Request) -> Result[str, str]:
    """Perform one Linux observation; returned values are not a receipt."""
    if request.operation == "observe":
        observed = binding_peer.observe(request.peer)
        return (
            observed
            if isinstance(observed, Err)
            else Ok(binding_transport.encode(observed.value))
        )
    absent = binding_peer.observe_absence_identity(request.peer)
    return (
        absent
        if isinstance(absent, Err)
        else Ok(
            json.dumps(
                {
                    "nonce": request.peer.nonce,
                    "uid": absent.value[1],
                    "absent": absent.value[0],
                }
            )
        )
    )


def main() -> int:
    """Read one bounded request and emit a value or a nonzero error."""
    request = decode(sys.stdin.read(MAX_REQUEST + 1))
    result = request if isinstance(request, Err) else dispatch(request.value)
    if isinstance(result, Err):
        sys.stderr.write(result.error + "\n")
        return 1
    sys.stdout.write(result.value + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
