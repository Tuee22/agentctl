# Copyright (c) 2026 agentctl contributors.
"""Hyper-V guest identity facts have strict positive and refusal controls."""

from dataclasses import replace

import pytest

from agentctl.check.hyperv_guest import GuestIdentity, effective_uid, problems
from agentctl.foundation import Err, Ok

pytestmark = pytest.mark.evidence("value")
IDENTITY = GuestIdentity(
    "Linux",
    "6.12.1",
    "Microsoft Corporation",
    "Virtual Machine",
    "ID=debian\n",
    "123456789abcdef0123456789abcdef0",
    1000,
)


def test_guest_identity_refuses_foreign_and_ambiguous_hosts() -> None:
    """Names alone cannot establish a Debian non-root Hyper-V guest."""
    assert problems(IDENTITY) == ()
    for bad in (
        replace(IDENTITY, family="Windows"),
        replace(IDENTITY, vendor="other"),
        replace(IDENTITY, kernel="6.6.0-microsoft-standard-WSL2"),
        replace(IDENTITY, release="ID=debian\nID=ubuntu\n"),
        replace(IDENTITY, machine_id="0" * 32),
        replace(IDENTITY, uid=0),
    ):
        assert problems(bad)
    assert effective_uid("Uid:\t1000\t1001\t1000\t1000\n") == Ok(1001)
    assert isinstance(effective_uid("Uid:\t1000\n"), Err)
    assert isinstance(effective_uid("Uid: 1 1 1 1\nUid: 2 2 2 2\n"), Err)
    assert isinstance(effective_uid("Uid: 1 1 1 1\nUid: invalid\n"), Err), (
        "malformed duplicate guest UID was accepted"
    )
