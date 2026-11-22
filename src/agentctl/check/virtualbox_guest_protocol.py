# Copyright (c) 2026 agentctl contributors.
"""Bounded nonce exchange for diagnostic VirtualBox guest observations."""

import re
import sys

from agentctl.check import virtualbox_guest
from agentctl.check.hyperv_guest import GuestIdentity
from agentctl.check.hyperv_guest_protocol import decode as decode_guest
from agentctl.check.hyperv_guest_protocol import encode as encode_guest
from agentctl.foundation import Err, Result


def encode(nonce: str, identity: GuestIdentity) -> Result[str, str]:
    """Encode facts and nonce without attesting to their host provenance."""
    return encode_guest(nonce, identity, guest_family="virtualbox")


def decode(text: str, nonce: str) -> Result[GuestIdentity, str]:
    """Reject malformed, stale and foreign diagnostic guest responses."""
    return decode_guest(text, nonce, guest_family="virtualbox")


def main() -> int:
    """Read one nonce and emit one observation or an explicit refusal."""
    nonce = sys.stdin.read(35)
    if re.fullmatch(r"[0-9a-f]{32}\r?\n", nonce) is None:
        sys.stderr.write("invalid VirtualBox guest nonce\n")
        return 1
    observed = virtualbox_guest.observe()
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
