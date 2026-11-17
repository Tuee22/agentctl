# Copyright (c) 2026 agentctl contributors.
"""Constructed refusal controls for the Linux-side binding observer."""

import pytest

from agentctl.check.binding_peer import (
    ObservationOperations,
    PeerObservation,
    PeerRequest,
    absence_with_identity,
    host_problems,
    observe,
    observe_absence,
    observe_with,
)
from agentctl.check.wsl_guest_sample import GuestReading
from agentctl.result import Err, Ok

pytestmark = pytest.mark.evidence("value")


def test_peer_host_identity_refusals() -> None:
    """Only the requested Debian WSL2 identity passes constructed host facts."""
    family = "Linux"
    kernel = "6.18.58.1-microsoft-standard-WSL2"
    name = "agentctl-debian-validation"
    assert host_problems(family, kernel, name, name, 'ID="debian"\n') == ()
    assert "not Linux WSL2" in host_problems(
        family, "6.1.0-native", name, name, "ID=debian\n"
    ), "non-WSL kernel was accepted"
    assert "distribution identity mismatch" in host_problems(
        family, kernel, "another-distro", name, "ID=debian\n"
    ), "wrong distribution was accepted"
    assert "not Debian" in host_problems(family, kernel, name, name, "ID=ubuntu\n"), (
        "non-Debian peer was accepted"
    )
    assert "not Debian" in host_problems(
        family, kernel, name, name, "ID=debian\nID=ubuntu\n"
    )
    assert "not Linux WSL2" in host_problems(
        "Windows", kernel, name, name, "ID=debian\n"
    )


def test_peer_invalid_request_refused() -> None:
    """Malformed names, aliases and nonces refuse before host inspection."""
    for request in (
        PeerRequest("../other", "/mnt/c/source", "/work/source", "a" * 32),
        PeerRequest("dedicated", "/mnt/c/../other", "/work/source", "a" * 32),
        PeerRequest("dedicated", "/mnt/c/source", "/work/source", "../other"),
        PeerRequest("dedicated", "relative", "/work/source", "a" * 32),
    ):
        outcome = observe(request)
        assert isinstance(outcome, Err)
        assert outcome.error == "invalid binding peer request"
        assert observe_absence(request) == outcome
    unicode_name = observe(
        PeerRequest("Dedicated Débian", "/mnt/c/source", "/work/source", "a" * 32)
    )
    assert isinstance(unicode_name, Err)
    assert unicode_name.error != "invalid binding peer request"


def test_peer_refuses_mount_change_during_exchange() -> None:
    """A changing mapping cannot authenticate a previously read inventory."""
    request = PeerRequest("dedicated", "/mnt/c/source", "/work/source", "a" * 32)
    observation = PeerObservation(
        request,
        "kernel",
        "dedicated",
        "release",
        1000,
        1,
        2,
        "mount",
        "inventory",
        GuestReading((0, 1), 4096, 1024, 8192, 4096, 100),
    )
    samples = iter(("before", "after"))
    operations = ObservationOperations(
        lambda _request: Ok(("kernel", "dedicated", "release", 1000)),
        lambda: next(samples),
        lambda _request, _text: Ok((1, 2)),
        lambda _request, _identity, _text, _mapping: Ok(observation),
    )
    result = observe_with(request, operations)
    assert isinstance(result, Err), "changed peer mount was accepted"
    assert result.error == "binding peer mount changed during exchange"


def test_cleanup_identity_is_bracketed() -> None:
    """A cleanup response cannot mix observations from different identities."""
    request = PeerRequest("dedicated", "/mnt/c/source", "/work/source", "a" * 32)
    identity = ("kernel", "dedicated", "ID=debian", 1000)
    assert absence_with_identity(
        request, lambda _request: Ok(identity), lambda _request: Ok(value=True)
    ) == Ok((True, 1000))
    observed = iter((Ok(identity), Ok((*identity[:3], 1001))))
    result = absence_with_identity(
        request, lambda _request: next(observed), lambda _request: Ok(value=True)
    )
    assert isinstance(result, Err), "changed cleanup identity was accepted"
    assert isinstance(
        absence_with_identity(
            request, lambda _request: Err("identity"), lambda _request: Ok(value=True)
        ),
        Err,
    )
    assert isinstance(
        absence_with_identity(
            request, lambda _request: Ok(identity), lambda _request: Err("absence")
        ),
        Err,
    )
