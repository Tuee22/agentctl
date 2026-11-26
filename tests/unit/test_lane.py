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
    debian_release,
    evaluate,
    evidence_lines,
    parse_host,
    parse_lane,
    parse_phase_lane,
    phase_lane_host,
    read_host,
    refusals,
)
from agentctl.result import Err, Ok
from tests.harness.oracle import Object, Store, load_scoped

pytestmark = pytest.mark.evidence("value")


def test_phase_lane_qualifies_native_family_without_later_capabilities() -> None:
    """Require Debian or the specified foreign host and only the lane's base facts."""
    linux = HostFacts("Linux", "x86_64", checkout=True, git=True, debian=True)
    assert phase_lane_host("linux", linux), "Debian phase lane was rejected"
    assert phase_lane_host("linux-windows", linux)
    assert phase_lane_host("linux-macos", linux)
    assert not phase_lane_host("linux", replace(linux, debian=False)), (
        "non-Debian Linux qualified for a phase"
    )
    assert not phase_lane_host("linux", replace(linux, checkout=False))
    assert not phase_lane_host("linux", replace(linux, git=False))
    assert not phase_lane_host("linux", replace(linux, architecture="unknown"))
    assert not phase_lane_host("linux-live-clean", linux)
    live = replace(linux, mux=True, agents=True, authenticated=True, clean=True)
    assert phase_lane_host("linux-live-clean", live)
    for name in ("mux", "agents", "authenticated", "clean"):
        assert not phase_lane_host(
            "linux-live-clean", replace(live, **{name: False})
        ), "live lane ignored " + name
    windows = HostFacts("Windows", "AMD64", checkout=True, git=True)
    assert phase_lane_host("linux-windows", windows), (
        "foreign phase lane required later capabilities"
    )
    assert not phase_lane_host("linux", windows), "foreign family qualified Linux lane"
    assert not phase_lane_host("linux-macos", windows)
    assert not phase_lane_host("linux-windows", replace(windows, architecture="ARM64"))
    mac = HostFacts("Darwin", "arm64", checkout=True, git=True)
    assert phase_lane_host("linux-macos", mac)
    assert not phase_lane_host("linux-windows", mac)


def test_host_lane_oracle(root: Path) -> None:
    """Use independent cases for native family and lane qualification."""
    store = load_scoped(root / "tests/oracles/host_lanes.toml", root)
    assert isinstance(store, Store)
    assert store.effective
    for row in store.effective:
        assert isinstance(row.inputs, Object)
        values = dict(row.inputs.items)
        assert isinstance(row.expected, bool)
        lane = values["lane"]
        family = values["family"]
        machine = values["architecture"]
        assert isinstance(lane, str)
        assert isinstance(family, str)
        assert isinstance(machine, str)
        parsed = parse_phase_lane(lane)
        assert isinstance(parsed, Ok)
        flags = tuple(
            values[name]
            for name in (
                "checkout",
                "git",
                "debian",
                "mux",
                "agents",
                "authenticated",
                "clean",
            )
        )
        assert all(isinstance(value, bool) for value in flags)
        facts = HostFacts(
            family,
            machine,
            checkout=flags[0] is True,
            git=flags[1] is True,
            debian=flags[2] is True,
            mux=flags[3] is True,
            agents=flags[4] is True,
            authenticated=flags[5] is True,
            clean=flags[6] is True,
        )
        assert phase_lane_host(parsed.value, facts) == row.expected, row.identifier


def test_debian_release_requires_exact_unambiguous_identity() -> None:
    """Reject derivatives, missing IDs and duplicate distribution identities."""
    assert debian_release('NAME="Debian"\nID=debian\n')
    assert debian_release('ID="debian"\n')
    for invalid in (
        "",
        "ID=ubuntu\n",
        "ID_LIKE=debian\n",
        "ID=debian\nID=debian\n",
        'ID=debian\nID="bad value"\n',
        "ID=debian\nID=\n",
        "ID=debian\n ID =other\n",
    ):
        assert not debian_release(invalid), "foreign Linux qualified as Debian"


def test_lane_evidence_oracle(root: Path) -> None:
    """Independent cases govern lane refusal and emission after failure."""
    store = load_scoped(root / "tests/oracles/lane_evidence.toml", root)
    assert isinstance(store, Store)
    assert store.effective
    base = HostFacts(family="Linux", architecture="x86_64", checkout=True, git=True)
    for row in store.effective:
        assert isinstance(row.inputs, Object)
        values = dict(row.inputs.items)
        assert isinstance(row.expected, bool)
        if values["subject"] == "refusal":
            status, mux = values["status"], values["mux"]
            assert isinstance(status, str)
            assert isinstance(mux, bool)
            declaration = Declaration("mux", status, "self-verifying", "mux-host")
            result = bool(refusals((declaration,), evaluate(replace(base, mux=mux))))
        else:
            assert values["subject"] == "evidence"
            code = values["code"]
            assert isinstance(code, int)
            assert not isinstance(code, bool)
            result = bool(
                evidence_lines(code, evaluate(base), "2026-11-02", "a" * 64, "host")
            )
        assert result == row.expected


def test_phase_lane_vocabulary() -> None:
    """Plan lanes require Linux and cannot combine both foreign families."""
    for name in ("linux", "linux-windows", "linux-macos", "linux-live-clean"):
        assert parse_phase_lane(name) == Ok(name)
    for name in ("any-host", "windows", "linux-windows-macos", "", "Linux"):
        assert isinstance(parse_phase_lane(name), Err)


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


def test_host_observation_schema(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
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
        "debian": False,
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
        {**value, "facts": {**facts, "debian": "true"}},
        {
            **value,
            "facts": {key: value for key, value in facts.items() if key != "debian"},
        },
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
    path.write_text(
        json.dumps(value).replace(
            '"nonce": "current"', '"nonce": "old", "nonce": "current"'
        ),
        encoding="utf-8",
    )
    assert isinstance(read_host(path, "current"), Err), (
        "duplicate host nonce was accepted"
    )
    path.write_text(
        json.dumps(value).replace('"mux": false', '"mux": true, "mux": false'),
        encoding="utf-8",
    )
    assert isinstance(read_host(path, "current"), Err), (
        "duplicate host fact was accepted"
    )
    path.write_text(json.dumps(value), encoding="utf-8")
    with monkeypatch.context() as patch:
        patch.setattr(Path, "is_symlink", lambda subject: subject == path)
        assert isinstance(read_host(path, "current"), Err), "host symlink was accepted"
