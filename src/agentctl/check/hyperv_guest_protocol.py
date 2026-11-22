# Copyright (c) 2026 agentctl contributors.
"""Bounded nonce exchange for diagnostic Hyper-V guest identity observations."""

import json
import re
import sys
from dataclasses import asdict
from typing import Literal

from agentctl.check import hyperv_guest, virtualbox_guest
from agentctl.check.hyperv_guest import GuestIdentity
from agentctl.foundation import Err, Ok, Result

MAX_RESPONSE = 16384
type GuestFamily = Literal["hyperv", "virtualbox"]


def _problems(identity: GuestIdentity, family: GuestFamily) -> tuple[str, ...]:
    """Select the named guest policy without treating a value as host proof."""
    match family:
        case "hyperv":
            return hyperv_guest.problems(identity)
        case "virtualbox":
            return virtualbox_guest.problems(identity)
        case _:
            return ("invalid guest family",)


def _fields(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """Reject duplicate JSON fields instead of accepting ambiguous values."""
    result = dict(pairs)
    if len(result) != len(pairs):
        message = "duplicate guest identity field"
        raise ValueError(message)
    return result


def encode(
    nonce: str, identity: GuestIdentity, *, guest_family: GuestFamily = "hyperv"
) -> Result[str, str]:
    """Encode a nonce-bound observation without attesting to the peer's identity."""
    if re.fullmatch(r"[0-9a-f]{32}", nonce) is None or _problems(
        identity, guest_family
    ):
        return Err("invalid guest identity or nonce")
    return Ok(
        json.dumps(
            {"nonce": nonce, "identity": asdict(identity)},
            ensure_ascii=True,
            separators=(",", ":"),
        )
    )


def decode(
    text: str, nonce: str, *, guest_family: GuestFamily = "hyperv"
) -> Result[GuestIdentity, str]:
    """Reject stale, oversized, ambiguous or invalid guest identity responses."""
    if len(text) > MAX_RESPONSE or re.fullmatch(r"[0-9a-f]{32}", nonce) is None:
        return Err("invalid guest identity response or nonce")
    try:
        value: object = json.loads(text, object_pairs_hook=_fields)
    except (ValueError, UnicodeError) as exc:
        return Err("cannot decode guest identity: " + str(exc))
    match value:
        case {
            "nonce": str() as received,
            "identity": {
                "family": str() as family,
                "kernel": str() as kernel,
                "vendor": str() as vendor,
                "product": str() as product,
                "release": str() as release,
                "machine_id": str() as machine_id,
                "uid": int() as uid,
                **extra_identity,
            },
            **extra,
        } if (
            not extra
            and not extra_identity
            and received == nonce
            and not isinstance(uid, bool)
        ):
            identity = GuestIdentity(
                family, kernel, vendor, product, release, machine_id, uid
            )
            return (
                Err("invalid guest identity")
                if _problems(identity, guest_family)
                else Ok(identity)
            )
        case _:
            return Err("invalid guest response fields")


def main() -> int:
    """Read one nonce and emit one observation or an explicit refusal."""
    nonce = sys.stdin.read(35)
    if re.fullmatch(r"[0-9a-f]{32}\r?\n", nonce) is None:
        sys.stderr.write("invalid Hyper-V guest nonce\n")
        return 1
    observed = hyperv_guest.observe()
    response = (
        observed
        if isinstance(observed, Err)
        else encode(nonce.rstrip("\r\n"), observed.value)
    )
    if isinstance(response, Err):
        sys.stderr.write(response.error + "\n")
        return 1
    sys.stdout.write(response.value + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
