# Copyright (c) 2026 agentctl contributors.
"""Remaining request, response and observation refusals for guest capacity."""

import io
import json
from collections.abc import Callable, Iterator
from dataclasses import replace
from pathlib import Path

import pytest

from agentctl.check import virtualbox_guest, virtualbox_guest_capacity
from agentctl.check.hyperv_guest import GuestIdentity
from agentctl.check.virtualbox_guest_capacity import (
    Observation,
    Request,
    decode,
    decode_request,
    encode,
    observe,
)
from agentctl.check.wsl_guest_sample import GuestReading
from agentctl.foundation import Err, Ok, Result

pytestmark = pytest.mark.evidence("value")
NONCE = "a" * 32
IDENTITY = GuestIdentity(
    "Linux", "6.12", "innotek GmbH", "VirtualBox", "ID=debian\n", "1" * 32, 1000
)
READING = GuestReading((0, 1), 8000, 0, 10000, 6000, 500)
HUGE_DIGITS = 5000
OVERSIZED = virtualbox_guest_capacity.MAX_RESPONSE + 1


def _sequence(
    *results: Result[GuestIdentity, str],
) -> Callable[[], Result[GuestIdentity, str]]:
    """Return a stand-in observer that yields each result in order."""
    remaining: Iterator[Result[GuestIdentity, str]] = iter(results)
    return lambda: next(remaining)


def test_request_decoding_refuses_size_and_shape() -> None:
    """An oversized or extra-field request is refused before use."""
    assert decode_request(" " * (virtualbox_guest_capacity.MAX_REQUEST + 1)) == Err(
        "VirtualBox guest capacity request too large"
    )
    assert decode_request('{"nonce":"x"}') == Err(
        "invalid guest capacity request fields"
    )


def test_encoding_refuses_foreign_identity_and_unencodable_values() -> None:
    """A foreign identity and an integer too large for JSON are refused."""
    request = Request(NONCE, "/home/agentctl/work")
    foreign = replace(IDENTITY, vendor="Other")
    assert isinstance(encode(Observation(request, foreign, READING)), Err)
    huge = 10**HUGE_DIGITS
    big = replace(READING, available_memory=huge, volume_size=huge, volume_free=huge)
    assert encode(Observation(request, IDENTITY, big)) == Err(
        "cannot encode guest capacity observation"
    )


def test_decoding_refuses_oversize_and_foreign_identity() -> None:
    """Oversized text and an invalid embedded identity are refused."""
    request = Request(NONCE, "/home/agentctl/work")
    assert decode(" " * OVERSIZED, request) == Err(
        "invalid guest capacity response or request"
    )
    text = json.dumps(
        {
            "nonce": NONCE,
            "storage": request.storage,
            "identity": "not an identity",
            "reading": {},
        }
    )
    assert isinstance(decode(text, request), Err)


def test_observation_refusals_and_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Each bracketing observation failure is returned and a stable pair joins."""
    request = Request(NONCE, tmp_path.as_posix())
    assert observe(replace(request, storage="relative")) == Err(
        "invalid guest capacity request"
    )
    failure = Err("first failed")
    monkeypatch.setattr(virtualbox_guest, "observe", _sequence(failure))
    assert observe(request) == failure
    second = Err("second failed")
    monkeypatch.setattr(virtualbox_guest, "observe", _sequence(Ok(IDENTITY), second))
    assert observe(request) == second
    monkeypatch.setattr(
        virtualbox_guest, "observe", _sequence(Ok(IDENTITY), Ok(IDENTITY))
    )
    observed = observe(request)
    assert isinstance(observed, Ok)
    assert observed.value.identity == IDENTITY


def test_main_refuses_bad_requests_and_emits_observations(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The entry point refuses a bad request and writes one valid response."""
    monkeypatch.setattr("sys.stdin", io.StringIO("{"))
    assert virtualbox_guest_capacity.main() == 1
    assert capsys.readouterr().err
    request = Request(NONCE, tmp_path.as_posix())
    monkeypatch.setattr(
        virtualbox_guest, "observe", _sequence(Ok(IDENTITY), Ok(IDENTITY))
    )
    monkeypatch.setattr(
        "sys.stdin",
        io.StringIO(json.dumps({"nonce": request.nonce, "storage": request.storage})),
    )
    assert virtualbox_guest_capacity.main() == 0
    decoded = decode(capsys.readouterr().out.strip(), request)
    assert isinstance(decoded, Ok)
    monkeypatch.setattr(virtualbox_guest, "observe", _sequence(Err("no guest")))
    monkeypatch.setattr(
        "sys.stdin",
        io.StringIO(json.dumps({"nonce": request.nonce, "storage": request.storage})),
    )
    assert virtualbox_guest_capacity.main() == 1
    assert capsys.readouterr().err == "no guest\n"
