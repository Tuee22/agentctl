# Copyright (c) 2026 agentctl contributors.
"""Constructed receipt joins never constitute a native or historical run."""

from dataclasses import replace

import pytest

from agentctl.check.phase_reports import Receipt, ReceiptRequirement, validate_receipts

pytestmark = pytest.mark.evidence("value")

REQUIREMENT = ReceiptRequirement(
    capability="application",
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
    identity="logical-input",
    native_identity="linux-tools",
    nonce="linux-nonce",
    passed=True,
    tests=frozenset({"test-required"}),
    mutants=frozenset({"mutant-required"}),
    coverage=frozenset({"covered-module"}),
    prerequisites=frozenset({("bootstrap", "bootstrap-input")}),
)
WINDOWS = replace(
    LINUX,
    family="windows",
    host_family="windows",
    native_identity="windows-tools",
    nonce="windows-nonce",
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
