# Copyright (c) 2026 agentctl contributors.
"""Remaining receipt-decoding and scoped-input refusals of the phase reports."""

import json
from dataclasses import replace

import pytest

from agentctl.check.lanes import HostFacts
from agentctl.check.phase_reports import (
    PhaseInputs,
    Receipt,
    aggregate_receipt_records,
    calculate_scoped_inputs,
    parse_receipt,
    receipt_bytes,
)
from agentctl.foundation import Err, Ok

pytestmark = pytest.mark.evidence("value")

LINUX = Receipt(
    capability="application",
    family="linux",
    host_family="linux",
    host_facts=HostFacts("Linux", "x86_64", checkout=True, git=True, debian=True),
    identity="logical-input",
    native_identity="linux-tools",
    nonce="linux-nonce",
    passed=True,
    tests=frozenset({"test-required"}),
    mutants=frozenset({"mutant-required"}),
    coverage=frozenset({"covered-module"}),
    prerequisites=frozenset({("bootstrap", "bootstrap-input")}),
    diagnostics=(),
)
MACOS = replace(
    LINUX,
    family="macos",
    host_family="macos",
    host_facts=HostFacts("Darwin", "arm64", checkout=True, git=True, xcode=True),
    native_identity="macos-tools",
    nonce="macos-nonce",
)


def _raw(receipt: Receipt) -> dict[str, object]:
    encoded = receipt_bytes(receipt)
    assert isinstance(encoded, Ok)
    decoded = json.loads(encoded.value)
    assert isinstance(decoded, dict)
    return {str(name): item for name, item in decoded.items()}


def _encode(value: dict[str, object]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def test_macos_receipt_round_trips() -> None:
    """The macOS family decodes to its own native family value."""
    encoded = receipt_bytes(MACOS)
    assert isinstance(encoded, Ok)
    assert parse_receipt(encoded.value) == Ok(MACOS)


def test_malformed_prerequisite_pairs_are_refused() -> None:
    """Prerequisite entries must be pairs of nonempty identifiers."""
    for invalid in (["lonely"], "not-a-list", [["a", ""]], [["a", "b", "c"]]):
        contents = _encode({**_raw(LINUX), "prerequisites": invalid})
        assert isinstance(parse_receipt(contents), Err), str(invalid)


def test_receipt_field_set_must_be_exact() -> None:
    """A missing, extra or non-object receipt record is refused."""
    base = _raw(LINUX)
    missing = {name: item for name, item in base.items() if name != "tests"}
    assert parse_receipt(_encode(missing)) == Err("invalid receipt fields")
    assert parse_receipt(_encode({**base, "extra": 1})) == Err("invalid receipt fields")
    assert parse_receipt(b"[]") == Err("invalid receipt fields")


def test_record_aggregation_refuses_empty_groups() -> None:
    """Undeclared receipt groups propagate the aggregate refusal."""
    assert aggregate_receipt_records(()) == Err("invalid receipt group declarations")


def test_scoped_inputs_refuse_empty_declarations() -> None:
    """The base calculation's refusal is returned unchanged."""
    result = calculate_scoped_inputs((), (), frozenset(), frozenset())
    assert result == Err("invalid phase declarations or source census")
    phase = PhaseInputs(0, frozenset({"a"}), frozenset({"c"}), frozenset())
    assert isinstance(
        calculate_scoped_inputs((phase,), (("a", b""),), frozenset(), frozenset()), Ok
    )
