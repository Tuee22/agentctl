# Copyright (c) 2026 agentctl contributors.
"""Constructed host facts exercise every lane and refusal rule."""

import json
from dataclasses import replace
from pathlib import Path

import pytest

from agentctl.check.lanes import (
    LANES,
    Declaration,
    HostFacts,
    architecture,
    evaluate,
    evidence_lines,
    parse_host,
    parse_lane,
    read_host,
    refusals,
)
from agentctl.result import Err, Ok

pytestmark = pytest.mark.evidence("value")


def test_refusal_when_done_lane_unmet() -> None:
    """A Done multiplexer phase requires its actual host qualification."""
    facts = HostFacts(family="Linux", architecture="x86_64", checkout=True, git=True)
    declaration = Declaration("multiplexer", "Done", "self-verifying", "mux-host")
    assert refusals((declaration,), evaluate(replace(facts, mux=True))) == ()
    assert refusals((declaration,), evaluate(facts)) == (
        "plan.lanes: unmet mux-host for multiplexer",
    ), "unmet Done lane was waived"
    assert refusals((replace(declaration, status="Planned"),), evaluate(facts)) == ()


def test_acceptance_lane_not_refused() -> None:
    """An unrelated host reports acceptance lanes without requiring them."""
    facts = HostFacts(family="Linux", architecture="x86_64", checkout=True, git=True)
    assert (
        refusals(
            (Declaration("macOS acceptance", "Done", "host-acceptance", "macos"),),
            evaluate(facts),
        )
        == ()
    )
    assert refusals(
        (Declaration("unknown", "Planned", "host-acceptance", "made-up"),),
        evaluate(facts),
    ) == ("plan.lanes: unknown: unknown host lane: made-up",)


def test_evidence_printed_only_after_full_pass() -> None:
    """Every failure status suppresses rows; a full pass emits only met lanes."""
    states = evaluate(
        HostFacts(family="Linux", architecture="x86_64", checkout=True, git=True)
    )
    expected = (
        "EVIDENCE 2026-11-02 ; any-host ; agentctl check ; pass ; tree "
        + "a" * 64
        + " ; os=Linux,arch=x86_64",
    )
    assert (
        evidence_lines(0, states, "2026-11-02", "a" * 64, "os=Linux,arch=x86_64")
        == expected
    )
    for code in (1, 2, 3, 130):
        assert evidence_lines(code, states, "2026-11-02", "a" * 64, "os=Linux") == (), (
            "EVIDENCE printed after failure"
        )


def test_lane_vocabulary_and_predicates() -> None:
    """The closed table matches independently specified native-host combinations."""
    for name in (
        "any-host",
        "mux-host",
        "agent-host",
        "live-agents",
        "clean-container",
        "macos",
        "windows-psmux",
    ):
        assert parse_lane(name) == Ok(name)
    assert len(LANES) == len(set(LANES))
    assert isinstance(parse_lane("other"), Err)
    assert architecture("Darwin", "aarch64") == "arm64"
    assert architecture("Linux", "ARM64") == "aarch64"
    assert architecture("Windows", "AMD64") == "x86_64"
    for family, arch, expected in (
        (
            "Linux",
            "x86_64",
            {"any-host", "mux-host", "agent-host", "live-agents", "clean-container"},
        ),
        (
            "Darwin",
            "arm64",
            {"any-host", "mux-host", "agent-host", "clean-container", "macos"},
        ),
        (
            "Windows",
            "AMD64",
            {"any-host", "mux-host", "agent-host", "clean-container", "windows-psmux"},
        ),
        ("Windows", "ARM64", set()),
        ("other", "x86_64", set()),
    ):
        facts = HostFacts(
            family=family,
            architecture=arch,
            checkout=True,
            git=True,
            mux=True,
            agents=True,
            authenticated=True,
            clean=True,
            xcode=True,
        )
        assert {state.lane for state in evaluate(facts) if state.met} == expected
        assert not any(state.met for state in evaluate(replace(facts, checkout=False)))
        assert not any(state.met for state in evaluate(replace(facts, git=False)))


def test_host_observation_schema(tmp_path: Path) -> None:
    """Missing, mistyped or stale facts cannot qualify a lane."""
    facts = {
        "family": "Linux",
        "architecture": "x86_64",
        "checkout": True,
        "git": True,
        "mux": False,
        "agents": False,
        "authenticated": False,
        "clean": False,
        "xcode": False,
    }
    value = {"nonce": "current", "facts": facts}
    expected = HostFacts(family="Linux", architecture="x86_64", checkout=True, git=True)
    assert parse_host(value, "current") == Ok(expected)
    for invalid in (
        None,
        {},
        {**value, "nonce": "old"},
        {**value, "facts": []},
        {**value, "facts": {**facts, "mux": "false"}},
        {**value, "facts": {**facts, "family": 1}},
    ):
        assert isinstance(parse_host(invalid, "current"), Err)
    assert isinstance(parse_host(value, ""), Err)
    path = tmp_path / "host.json"
    assert isinstance(read_host(path, "current"), Err)
    path.write_text("bad JSON", encoding="utf-8")
    assert isinstance(read_host(path, "current"), Err)
    path.write_text(json.dumps(value), encoding="utf-8")
    assert read_host(path, "current") == Ok(expected)
