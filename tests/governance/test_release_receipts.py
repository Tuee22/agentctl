# Copyright (c) 2026 agentctl contributors.
"""Constructed receipt joins never constitute a native or historical run."""

import json
from dataclasses import replace
from pathlib import Path

import pytest

from agentctl.check.lanes import HostFacts
from agentctl.check.phase_reports import (
    Receipt,
    ReceiptGroup,
    ReceiptRecordGroup,
    ReceiptRequirement,
    aggregate_receipt_records,
    aggregate_receipts,
    parse_receipt,
    receipt_bytes,
    validate_receipts,
)
from agentctl.foundation import Err, Ok
from tests.harness.oracle import Object, Store, load_scoped

pytestmark = pytest.mark.evidence("value")

REQUIREMENT = ReceiptRequirement(
    capability="application",
    lane="linux-windows",
    identity="logical-input",
    families=frozenset({"linux", "windows"}),
    native_identities=frozenset(
        {("linux", "linux-tools"), ("windows", "windows-tools")}
    ),
    run_nonces=frozenset({("linux", "linux-nonce"), ("windows", "windows-nonce")}),
    tests=frozenset({"test-required"}),
    mutants=frozenset({"mutant-required"}),
    coverage=frozenset({"covered-module"}),
    prerequisites=frozenset({("bootstrap", "bootstrap-input")}),
)
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
WINDOWS = replace(
    LINUX,
    family="windows",
    host_family="windows",
    host_facts=HostFacts("Windows", "x86_64", checkout=True, git=True),
    native_identity="windows-tools",
    nonce="windows-nonce",
)


def test_receipt_canonical_round_trip() -> None:
    """Every lane and evidence field survives a canonical retained record."""
    for receipt in (LINUX, WINDOWS, replace(LINUX, passed=False)):
        encoded = receipt_bytes(receipt)
        assert isinstance(encoded, Ok)
        assert parse_receipt(encoded.value) == Ok(receipt)
    linux = receipt_bytes(LINUX)
    windows = receipt_bytes(WINDOWS)
    assert isinstance(linux, Ok)
    assert isinstance(windows, Ok)
    decoded = (parse_receipt(linux.value), parse_receipt(windows.value))
    assert all(isinstance(item, Ok) for item in decoded)
    records = tuple(item.value for item in decoded if isinstance(item, Ok))
    assert validate_receipts(REQUIREMENT, records) == ()
    assert validate_receipts(replace(REQUIREMENT, identity="changed"), records), (
        "stale decoded receipts were accepted"
    )


def test_receipt_record_refuses_ambiguous_or_noncanonical_values() -> None:
    """Wire records cannot hide aliases, duplicates or malformed identities."""
    encoded = receipt_bytes(LINUX)
    assert isinstance(encoded, Ok)
    raw = json.loads(encoded.value)
    assert isinstance(raw, dict)
    for field, invalid in (
        ("version", True),
        ("nonce", ""),
        ("family", "other"),
        ("host_family", "windows"),
        ("passed", 1),
        ("tests", ["test-required", "test-required"]),
        ("mutants", [["unhashable"]]),
        ("coverage", [""]),
        (
            "prerequisites",
            [["bootstrap", "bootstrap-input"], ["bootstrap", "bootstrap-input"]],
        ),
        ("diagnostics", [""]),
    ):
        value = {**raw, field: invalid}
        contents = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
        assert isinstance(parse_receipt(contents), Err), f"invalid {field} accepted"
    assert isinstance(parse_receipt(b'{"version":1,"version":1}'), Err)
    assert isinstance(parse_receipt(encoded.value + b" "), Err), (
        "noncanonical receipt was accepted"
    )
    assert isinstance(parse_receipt(b"\xff"), Err)
    assert isinstance(receipt_bytes(replace(LINUX, nonce="")), Err)


def test_receipt_record_aggregation_preserves_scoped_failures() -> None:
    """A damaged lane fails its owner and dependents without poisoning earlier work."""
    lower_requirement = replace(
        REQUIREMENT,
        capability="bootstrap",
        lane="linux",
        identity="bootstrap-input",
        families=frozenset({"linux"}),
        native_identities=frozenset({("linux", "linux-tools")}),
        run_nonces=frozenset({("linux", "linux-nonce")}),
        prerequisites=frozenset(),
    )
    lower_receipt = replace(
        LINUX,
        capability="bootstrap",
        identity="bootstrap-input",
        prerequisites=frozenset(),
    )
    lower_bytes, linux_bytes, windows_bytes = (
        receipt_bytes(lower_receipt),
        receipt_bytes(LINUX),
        receipt_bytes(WINDOWS),
    )
    assert isinstance(lower_bytes, Ok)
    assert isinstance(linux_bytes, Ok)
    assert isinstance(windows_bytes, Ok)
    lower = ReceiptRecordGroup(0, lower_requirement, (lower_bytes.value,))
    later = ReceiptRecordGroup(1, REQUIREMENT, (linux_bytes.value, windows_bytes.value))
    success = aggregate_receipt_records((lower, later))
    assert isinstance(success, Ok)
    assert all(not item.failures for item in success.value)
    damaged_later = aggregate_receipt_records(
        (lower, replace(later, records=(linux_bytes.value, windows_bytes.value + b" ")))
    )
    assert isinstance(damaged_later, Ok)
    assert not damaged_later.value[0].failures, "later receipt poisoned earlier phase"
    assert "invalid receipt record" in damaged_later.value[1].failures
    damaged_lower = aggregate_receipt_records(
        (replace(lower, records=(lower_bytes.value, lower_bytes.value + b" ")), later)
    )
    assert isinstance(damaged_lower, Ok)
    assert "invalid receipt record" in damaged_lower.value[0].failures
    assert "invalid prerequisite: bootstrap" in damaged_lower.value[1].failures, (
        "damaged prerequisite receipt was accepted"
    )
    duplicate = aggregate_receipt_records(
        (lower, replace(later, records=(linux_bytes.value,) * 2))
    )
    assert isinstance(duplicate, Ok)
    assert duplicate.value[1].failures, "duplicate receipt family was accepted"


def test_requirement_receipt_oracle(root: Path) -> None:
    """Compare receipt qualification to independent current-evidence cases."""
    store = load_scoped(root / "tests/oracles/requirements.toml", root)
    assert isinstance(store, Store)
    assert store.effective
    requirement = replace(
        REQUIREMENT,
        lane="linux",
        families=frozenset({"linux"}),
        native_identities=frozenset({("linux", "linux-tools")}),
        run_nonces=frozenset({("linux", "linux-nonce")}),
    )
    for row in store.effective:
        assert isinstance(row.inputs, Object)
        values = dict(row.inputs.items)
        assert isinstance(row.expected, bool)
        for name in (
            "family",
            "host_family",
            "identity",
            "native_identity",
            "nonce",
            "prerequisite",
        ):
            assert isinstance(values[name], str)
        for name in ("passed", "test", "mutant", "coverage", "debian", "checkout"):
            assert isinstance(values[name], bool)
        receipt = replace(
            LINUX,
            family=values["family"],
            host_family=values["host_family"],
            host_facts=replace(
                LINUX.host_facts,
                debian=values["debian"],
                checkout=values["checkout"],
            ),
            identity=values["identity"],
            native_identity=values["native_identity"],
            nonce=values["nonce"],
            passed=values["passed"],
            tests=LINUX.tests if values["test"] else frozenset(),
            mutants=LINUX.mutants if values["mutant"] else frozenset(),
            coverage=LINUX.coverage if values["coverage"] else frozenset(),
            prerequisites=frozenset({("bootstrap", values["prerequisite"])}),
        )
        assert (not validate_receipts(requirement, (receipt,))) == row.expected, (
            row.identifier
        )


def test_complete_current_requirement_receipts() -> None:
    """All required lanes and evidence must be current, complete and passing."""
    assert validate_receipts(REQUIREMENT, (LINUX, WINDOWS)) == ()
    for receipts in ((LINUX,), (LINUX, LINUX, WINDOWS), ()):
        assert validate_receipts(REQUIREMENT, receipts)
    for invalid in (
        replace(REQUIREMENT, capability=""),
        replace(REQUIREMENT, identity=""),
        replace(REQUIREMENT, tests=frozenset()),
        replace(REQUIREMENT, families=frozenset({"windows"})),
        replace(REQUIREMENT, native_identities=frozenset({("linux", "linux-tools")})),
        replace(REQUIREMENT, run_nonces=frozenset({("linux", "linux-nonce")})),
        replace(REQUIREMENT, run_nonces=frozenset({("linux", ""), ("windows", "w")})),
        replace(
            REQUIREMENT,
            run_nonces=frozenset(
                {("linux", "one"), ("linux", "two"), ("windows", "w")}
            ),
        ),
        replace(REQUIREMENT, prerequisites=frozenset({("bootstrap", "")})),
        replace(
            REQUIREMENT,
            prerequisites=frozenset({("bootstrap", "one"), ("bootstrap", "two")}),
        ),
    ):
        assert validate_receipts(invalid, (LINUX, WINDOWS)) == ("invalid requirement",)
    for changed in (
        replace(LINUX, passed=False),
        replace(LINUX, nonce=""),
        replace(LINUX, nonce="wrong-nonce"),
        replace(LINUX, nonce="windows-nonce"),
        replace(LINUX, tests=frozenset()),
        replace(LINUX, mutants=frozenset()),
        replace(LINUX, coverage=frozenset()),
        replace(LINUX, prerequisites=frozenset()),
        replace(LINUX, capability="other"),
    ):
        assert validate_receipts(REQUIREMENT, (changed, WINDOWS))


def test_receipt_pass_is_a_boolean() -> None:
    """A truthy non-Boolean value cannot attest a passing native run."""
    for value in (json.loads("1"), json.loads('"false"')):
        changed = replace(LINUX, passed=value)
        assert validate_receipts(REQUIREMENT, (changed, WINDOWS)) == (
            "invalid receipt: linux",
        ), "non-Boolean passing receipt was accepted"


def test_receipt_requirement_rejects_malformed_identifiers() -> None:
    """Numeric and empty identifiers cannot define required evidence."""
    number = json.loads("1")
    for invalid in (
        replace(REQUIREMENT, capability=number),
        replace(REQUIREMENT, identity=number),
        replace(REQUIREMENT, tests=frozenset({number})),
        replace(REQUIREMENT, mutants=frozenset({""})),
        replace(REQUIREMENT, coverage=frozenset({number})),
    ):
        assert validate_receipts(invalid, (LINUX, WINDOWS)) == (
            "invalid requirement",
        ), "malformed receipt requirement was not rejected"


def test_receipt_requirement_rejects_malformed_pairs() -> None:
    """Malformed identities, nonces and prerequisites fail without an exception."""
    number = json.loads("1")
    singleton = tuple(json.loads('["linux"]'))
    for invalid in (
        replace(REQUIREMENT, native_identities=frozenset({singleton})),
        replace(
            REQUIREMENT,
            native_identities=frozenset({("linux", number), ("windows", "w")}),
        ),
        replace(REQUIREMENT, run_nonces=frozenset({singleton})),
        replace(REQUIREMENT, prerequisites=frozenset({singleton})),
    ):
        try:
            result = validate_receipts(invalid, (LINUX, WINDOWS))
        except (TypeError, ValueError):
            pytest.fail("malformed receipt pair escaped validation")
        assert result == ("invalid requirement",), "malformed receipt pair was accepted"


def test_receipt_rejects_malformed_evidence() -> None:
    """A receipt cannot add non-string or mutable evidence values."""
    number = json.loads("1")
    mutable = json.loads('["test-required"]')
    for changed in (
        replace(LINUX, tests=mutable),
        replace(LINUX, tests=LINUX.tests | {number}),
        replace(LINUX, mutants=LINUX.mutants | {""}),
        replace(LINUX, coverage=LINUX.coverage | {number}),
        replace(LINUX, prerequisites=LINUX.prerequisites | {(number, "value")}),
    ):
        try:
            result = validate_receipts(REQUIREMENT, (changed, WINDOWS))
        except (TypeError, ValueError):
            pytest.fail("malformed receipt evidence escaped validation")
        assert result == ("invalid receipt: linux",), (
            "malformed receipt evidence was accepted"
        )


def test_receipt_rejects_malformed_identity() -> None:
    """Unhashable or non-string identifiers cannot crash or satisfy the join."""
    invalid = json.loads("[]")
    for changed in (
        replace(LINUX, capability=invalid),
        replace(LINUX, host_family=invalid),
        replace(LINUX, identity=invalid),
        replace(LINUX, native_identity=invalid),
        replace(LINUX, nonce=invalid),
    ):
        try:
            result = validate_receipts(REQUIREMENT, (changed, WINDOWS))
        except (TypeError, ValueError):
            pytest.fail("malformed receipt identity escaped validation")
        assert result == ("invalid receipt: linux",), (
            "malformed receipt identity was accepted"
        )
    try:
        family = validate_receipts(
            REQUIREMENT, (replace(LINUX, family=invalid), WINDOWS)
        )
    except (TypeError, ValueError):
        pytest.fail("malformed receipt family escaped validation")
    assert family == ("missing, duplicate or unexpected family",)


def test_receipt_requires_qualified_host_and_retained_diagnostics() -> None:
    """The declared lane, native host and diagnostic values must agree."""
    for invalid in (
        replace(REQUIREMENT, lane="linux"),
        replace(REQUIREMENT, lane="unknown"),
    ):
        assert validate_receipts(invalid, (LINUX, WINDOWS)) == (
            "invalid requirement",
        ), "receipt accepted inconsistent lane families"
    for changed in (
        replace(LINUX, host_facts=replace(LINUX.host_facts, debian=False)),
        replace(LINUX, host_facts=replace(LINUX.host_facts, checkout=False)),
        replace(LINUX, host_facts=replace(LINUX.host_facts, family="Windows")),
        replace(
            LINUX, host_facts=replace(LINUX.host_facts, checkout=json.loads('"yes"'))
        ),
        replace(LINUX, diagnostics=("",)),
        replace(LINUX, diagnostics=json.loads('["diagnostic"]')),
    ):
        assert validate_receipts(REQUIREMENT, (changed, WINDOWS)) == (
            "invalid receipt: linux",
        ), "receipt accepted invalid host facts or diagnostics"
    live = replace(
        REQUIREMENT,
        lane="linux-live-clean",
        families=frozenset({"linux"}),
        native_identities=frozenset({("linux", "linux-tools")}),
        run_nonces=frozenset({("linux", "linux-nonce")}),
    )
    ready = replace(
        LINUX,
        host_facts=replace(
            LINUX.host_facts, mux=True, agents=True, authenticated=True, clean=True
        ),
        diagnostics=("retained observation",),
    )
    assert validate_receipts(live, (ready,)) == ()
    assert validate_receipts(live, (LINUX,)) == ("invalid receipt: linux",), (
        "incomplete live host qualified its receipt"
    )


def test_foreign_receipt_input_identity() -> None:
    """Logical identity matches across hosts; native tool identities are separate."""
    assert validate_receipts(REQUIREMENT, (LINUX, WINDOWS)) == ()
    for changed in (
        replace(WINDOWS, identity="stale"),
        replace(WINDOWS, native_identity="linux-tools"),
        replace(WINDOWS, host_family="linux"),
        replace(WINDOWS, nonce="linux-nonce"),
        replace(WINDOWS, prerequisites=frozenset({("bootstrap", "stale")})),
    ):
        assert validate_receipts(REQUIREMENT, (LINUX, changed))


def test_aggregate_receipts_respects_lower_host_acceptance() -> None:
    """Only complete, current lower receipts can satisfy explicit dependencies."""
    lower_requirement = replace(
        REQUIREMENT,
        capability="bootstrap",
        lane="linux",
        identity="bootstrap-input",
        families=frozenset({"linux"}),
        native_identities=frozenset({("linux", "linux-tools")}),
        run_nonces=frozenset({("linux", "linux-nonce")}),
        prerequisites=frozenset(),
    )
    lower_receipt = replace(
        LINUX,
        capability="bootstrap",
        identity="bootstrap-input",
        prerequisites=frozenset(),
    )
    lower = ReceiptGroup(0, lower_requirement, (lower_receipt,))
    later = ReceiptGroup(1, REQUIREMENT, (LINUX, WINDOWS))
    baseline = aggregate_receipts((lower, later))
    assert isinstance(baseline, Ok)
    assert all(not result.failures for result in baseline.value)
    broken_lower = aggregate_receipts((replace(lower, receipts=()), later))
    assert isinstance(broken_lower, Ok)
    assert broken_lower.value[0].failures, "missing lower receipt was accepted"
    assert "invalid prerequisite: bootstrap" in broken_lower.value[1].failures, (
        "failed lower receipt did not invalidate its consumer"
    )
    broken_later = aggregate_receipts((lower, replace(later, receipts=(LINUX,))))
    assert isinstance(broken_later, Ok)
    assert not broken_later.value[0].failures, (
        "later receipt failure poisoned lower phase"
    )
    assert broken_later.value[1].failures
    for prerequisite in (
        frozenset({("bootstrap", "stale")}),
        frozenset({("application", "logical-input")}),
        frozenset({("unknown", "identity")}),
    ):
        changed = replace(REQUIREMENT, prerequisites=prerequisite)
        matching = tuple(
            replace(receipt, prerequisites=prerequisite) for receipt in (LINUX, WINDOWS)
        )
        result = aggregate_receipts((lower, ReceiptGroup(1, changed, matching)))
        assert isinstance(result, Ok)
        assert not result.value[0].failures
        assert result.value[1].failures, "invalid prerequisite was accepted"
    higher_dependency = frozenset({("application", "logical-input")})
    higher = replace(
        lower,
        requirement=replace(lower_requirement, prerequisites=higher_dependency),
        receipts=(replace(lower_receipt, prerequisites=higher_dependency),),
    )
    result = aggregate_receipts((higher, later))
    assert isinstance(result, Ok)
    assert result.value[0].failures, "higher prerequisite was accepted"
    assert result.value[1].failures
    assert isinstance(aggregate_receipts((lower, lower)), Err)
    duplicate = replace(later, requirement=replace(REQUIREMENT, capability="bootstrap"))
    assert isinstance(aggregate_receipts((lower, duplicate)), Err), (
        "duplicate capability was accepted"
    )
    assert isinstance(
        aggregate_receipts((replace(lower, number=True), replace(later, number=2))), Err
    ), "boolean receipt phase was accepted"
