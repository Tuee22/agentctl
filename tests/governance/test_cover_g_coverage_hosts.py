# Copyright (c) 2026 agentctl contributors.
"""Closed decoding of the coverage dependency pin and report observations."""

import pytest

from agentctl.check import coverage_hosts
from agentctl.foundation import Err, Ok

pytestmark = pytest.mark.evidence("value")
LINE_ONE = 1
LINE_TWO = 2


def test_pin_refuses_a_document_without_development_dependencies() -> None:
    """The dependency list must be a dev optional-dependency array."""
    refusal = Err("invalid coverage dependency declaration")
    assert coverage_hosts.pinned_version("[project]\nname = 'x'\n") == refusal
    assert (
        coverage_hosts.pinned_version(
            "[project.optional-dependencies]\ndev = 'coverage==1.0'\n"
        )
        == refusal
    )
    assert coverage_hosts.pinned_version("not toml [") == refusal


def test_lines_must_be_a_list_of_positive_integers() -> None:
    """Non-lists and non-positive or boolean entries are refused."""
    decode = coverage_hosts.__dict__["_lines"]
    refusal = Err("invalid coverage lines")
    assert decode("1") == refusal
    assert decode([0]) == refusal
    assert decode([True]) == refusal
    assert decode([LINE_ONE, LINE_ONE]) == Err("duplicate coverage line")
    assert decode([LINE_ONE, LINE_TWO]) == Ok(frozenset({LINE_ONE, LINE_TWO}))


def test_branches_must_be_a_list_of_arcs() -> None:
    """Non-lists and malformed arcs are refused; exit arcs may be negative."""
    decode = coverage_hosts.__dict__["_branches"]
    refusal = Err("invalid coverage branches")
    assert decode({}) == refusal
    assert decode([[0, 1]]) == refusal
    assert decode([[LINE_ONE, 0]]) == refusal
    assert decode([[LINE_ONE, -LINE_TWO]]) == Ok(frozenset({(LINE_ONE, -LINE_TWO)}))
    assert decode([[LINE_ONE, LINE_TWO]] * 2) == Err("duplicate coverage branch")


def test_summary_must_be_an_object() -> None:
    """A non-object summary is refused before its counts are read."""
    counts = coverage_hosts.__dict__["_summary_counts"]
    assert counts([], file_summary=True) == Err("invalid coverage summary")
