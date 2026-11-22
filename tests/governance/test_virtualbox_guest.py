# Copyright (c) 2026 agentctl contributors.
"""VirtualBox guest values refuse foreign, malformed and privileged observations."""

import base64
from dataclasses import replace

import pytest

from agentctl.check.hyperv_guest import GuestIdentity
from agentctl.check.virtualbox_guest import problems
from agentctl.check.virtualbox_guest_protocol import decode, encode
from agentctl.check.virtualbox_ssh_key import (
    PREFIX,
    PublicKey,
    compare,
    guest_key,
    known_key,
)
from agentctl.foundation import Err, Ok

pytestmark = pytest.mark.evidence("value")
GUEST = GuestIdentity(
    "Linux", "6.12", "innotek GmbH", "VirtualBox", "ID=debian\n", "1" * 32, 1000
)


def test_guest_identity_rejects_foreign_and_ambiguous_values() -> None:
    """Matching DMI values alone do not waive the other guest requirements."""
    assert problems(GUEST) == ()
    for bad in (
        replace(GUEST, family="Windows"),
        replace(GUEST, vendor="Microsoft Corporation"),
        replace(GUEST, product="other"),
        replace(GUEST, kernel=""),
        replace(GUEST, kernel="6.6.0-microsoft-standard-WSL2"),
        replace(GUEST, release="ID=debian\nID=ubuntu\n"),
        replace(GUEST, machine_id="0" * 32),
        replace(GUEST, uid=0),
        replace(GUEST, uid=True),
    ):
        assert problems(bad), "invalid VirtualBox guest facts were accepted"


def test_guest_protocol_rejects_stale_foreign_and_ambiguous_values() -> None:
    """The nonce and strict schema bind values but do not authenticate their origin."""
    nonce = "a" * 32
    result = encode(nonce, GUEST)
    assert isinstance(result, Ok), "VirtualBox protocol rejected valid guest facts"
    assert decode(result.value, nonce) == Ok(GUEST), (
        "VirtualBox protocol failed to decode valid guest facts"
    )
    assert isinstance(decode(result.value, "b" * 32), Err)
    assert isinstance(
        decode(result.value.replace('"uid":1000', '"uid":true'), nonce), Err
    )
    assert isinstance(
        decode(result.value.replace('"uid":1000', '"uid":1000,"uid":1000'), nonce),
        Err,
    )
    assert isinstance(
        encode(nonce, replace(GUEST, vendor="Microsoft Corporation")), Err
    )
    assert isinstance(encode("bad", GUEST), Err)


def test_guest_host_key_comparison_refuses_foreign_or_malformed_keys() -> None:
    """Join exact loopback and Ed25519 bytes without attesting their source."""
    blob = PREFIX + bytes(range(32))
    encoded = base64.b64encode(blob).decode("ascii")
    guest = "ssh-ed25519 " + encoded + " guest comment\n"
    known = "[127.0.0.1]:44223 ssh-ed25519 " + encoded + "\n"
    assert guest_key(guest) == Ok(PublicKey(blob))
    assert known_key(known, 44223) == Ok(PublicKey(blob))
    assert compare(guest, known, 44223) == Ok(PublicKey(blob))
    other = base64.b64encode(PREFIX + bytes(reversed(range(32)))).decode("ascii")
    assert isinstance(compare(guest, known.replace(encoded, other), 44223), Err), (
        "foreign SSH host key accepted"
    )
    for bad in (
        known.replace("[127.0.0.1]:44223", "[127.0.0.1]:44224"),
        known.replace("[127.0.0.1]:44223", "*"),
        known + known,
        known.rstrip("\n"),
        known.replace("ssh-ed25519", "ssh-rsa"),
        known.replace(encoded, base64.b64encode(blob[:-1]).decode("ascii")),
        known.replace(encoded, base64.b64encode(b"x" + blob[1:]).decode("ascii")),
        known.replace(encoded, encoded[:-1] + "!"),
    ):
        assert isinstance(known_key(bad, 44223), Err), "malformed SSH host key accepted"
    assert isinstance(guest_key(guest + "unexpected\n"), Err)
    assert isinstance(known_key(known, 0), Err)
    boolean_port = True
    assert isinstance(known_key(known, boolean_port), Err)
