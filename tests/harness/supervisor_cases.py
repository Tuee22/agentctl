# Copyright (c) 2026 agentctl contributors.
"""Independent scenario expectations and shared receiving controls for native tests."""

import tomllib
from pathlib import Path

from tests.harness.launch import LaunchCase
from tests.harness.oracle import Store, load, read_homes
from tests.harness.supervisor import (
    ScriptedTarget,
    log_records,
    scripted_target,
    wait_received,
)
from tests.harness.tmux import PrivateMux

RULE_PARTS = 4


def oracle_rows(root: Path, filename: str) -> list[dict[str, object]]:
    """Keep independent input and expected values joined to effective frozen rows."""
    path = root / "tests/oracles" / filename
    store = load(path, read_homes(root))
    assert isinstance(store, Store), store
    effective = {row.identifier for row in store.effective}
    return [
        {str(key): value for key, value in row.items()}
        for row in tomllib.loads(path.read_text(encoding="utf-8"))["case"]
        if row["id"] in effective
    ]


def scenario(root: Path, name: str, agent: str) -> dict[str, object]:
    """Read a single scenario expectation without consulting controller output."""
    identifier = "scenario." + name + "." + agent
    matching = [
        row
        for row in oracle_rows(root, "forbidden_actions.toml")
        if row["id"] == identifier
    ]
    assert len(matching) == 1
    expected = matching[0]["expected"]
    assert isinstance(expected, dict)
    return {str(key): value for key, value in expected.items()}


def receiving_controls(
    root: Path, mux: PrivateMux, trigger: Path
) -> tuple[ScriptedTarget, ...]:
    """Each agent gets its own overload receiver beside all no-input targets."""
    result: list[ScriptedTarget] = []
    for agent in ("claude", "codex"):
        expected = scenario(root, "recovery-working", agent)
        text = expected["received"]
        assert isinstance(text, str)
        result.append(
            scripted_target(
                mux,
                root,
                agent,
                (
                    ("IdlePrompt", {"kind": "file", "path": str(trigger)}),
                    ("Overloaded", {"kind": "input", "bytes": len(text.encode())}),
                    ("Working", {"kind": "stay"}),
                ),
            )
        )
    return tuple(result)


def require_receivers(root: Path, controls: tuple[ScriptedTarget, ...]) -> None:
    """Require exact literal and Enter receipts for both independent controls."""
    assert {control.case.agent for control in controls} == {"claude", "codex"}
    for control in controls:
        text = scenario(root, "recovery-working", control.case.agent)["received"]
        assert isinstance(text, str)
        wait_received(
            control.case.records_directory, control.case.nonce, text.encode("utf-8")
        )


def assert_decisions(
    root: Path, target: ScriptedTarget | str, source: LaunchCase | None = None
) -> None:
    """Every logged step has exactly its independently declared transition result."""
    transitions = oracle_rows(root, "recovery_transitions.toml")
    case = target.case if isinstance(target, ScriptedTarget) else source
    assert case is not None
    name = target.target if isinstance(target, ScriptedTarget) else target
    decisions = [
        record
        for record in log_records(case if source is None else source)
        if record["kind"] == "decision" and record["target"] == name
    ]
    assert decisions
    for decision in decisions:
        rule = decision["rule"]
        assert isinstance(rule, str)
        if rule in {"baseline", "paused", "unwatched"}:
            assert decision["to"] == "MONITORING"
            assert decision["actions"] == []
            continue
        if rule in {"send-failed", "identity-changed"}:
            _assert_delivery_decision(root, decision)
            continue
        parts = rule.split("/")
        assert len(parts) == RULE_PARTS, decision
        prefix, before, category, event = parts
        assert prefix == "step"
        assert before == decision["from"]
        matching = []
        for row in transitions:
            request = row["input"]
            expected = row["expected"]
            assert isinstance(request, dict)
            assert isinstance(expected, dict)
            if request["state"] == before and request["screen"] == category:
                matching.append(expected)
        assert any(
            row["state"] == decision["to"]
            and row["actions"] == decision["actions"]
            and row["incident"] == event
            for row in matching
        ), decision


def _assert_delivery_decision(root: Path, decision: dict[str, object]) -> None:
    """Join effect completion to its separate independent delivery rows."""
    candidates = []
    for row in oracle_rows(root, "forbidden_actions.toml"):
        request, expected = row["input"], row["expected"]
        assert isinstance(request, dict)
        if request["subject"] != "delivery-completion":
            continue
        assert isinstance(expected, dict)
        poll = request["poll"]
        completed = expected["decision"]
        assert isinstance(poll, dict)
        assert isinstance(completed, dict)
        if not completed:
            continue
        candidates.append(
            {
                "from": poll["state"],
                "to": completed["state"],
                "rule": completed["rule"],
                "actions": completed["actions"],
            }
        )
    projected = {key: decision[key] for key in ("from", "to", "rule", "actions")}
    assert projected in candidates, decision


def assert_all_decisions(root: Path, case: LaunchCase) -> None:
    """Include every control pane and every effect completion in the oracle join."""
    names = {row["target"] for row in log_records(case) if row["kind"] == "decision"}
    assert names
    for name in names:
        assert isinstance(name, str)
        assert_decisions(root, name, case)
