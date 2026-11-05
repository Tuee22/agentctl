# Copyright (c) 2026 agentctl contributors.
"""Supervisor kernels obey independent command, guard and poll expectations."""

import tomllib
from pathlib import Path

import pytest

from agentctl.bootstrap import build
from tests.harness.evaluate import compare_subject
from tests.harness.oracle import Store, load, read_homes

pytestmark = pytest.mark.evidence("value")


def test_command_plan_oracle(root: Path, haskell_build: build.BuildContext) -> None:
    """Exact native argv equality also excludes every forbidden effect and token."""
    compare_subject(
        root,
        haskell_build,
        "forbidden_actions.toml",
        "command-plan",
        "supervisor command plan differs from oracle",
    )
    path = root / "tests/oracles/forbidden_actions.toml"
    store = load(path, read_homes(root))
    assert isinstance(store, Store), store
    effective = {row.identifier for row in store.effective}
    rows = [
        row
        for row in tomllib.loads(path.read_text(encoding="utf-8"))["case"]
        if row["id"] in effective
    ]
    policies = [
        row["expected"] for row in rows if row["input"]["subject"] == "forbidden-policy"
    ]
    assert len(policies) == 1
    policy = policies[0]
    commands = [row for row in rows if row["input"]["subject"] == "command-plan"]
    assert {row["input"]["family"] for row in commands} == {
        "Linux",
        "Darwin",
        "Windows",
    }
    assert {row["input"]["agent"] for row in commands} == {"claude", "codex"}
    for row in commands:
        for argv in row["expected"]:
            assert argv
            assert argv[0] not in policy["verbs"]
            assert not any(token in " ".join(argv) for token in policy["tokens"])


def test_send_guard_oracle(root: Path, haskell_build: build.BuildContext) -> None:
    """Only an identical normalized overload with the same fingerprint proceeds."""
    compare_subject(
        root,
        haskell_build,
        "forbidden_actions.toml",
        "send-guard",
        "supervisor send guard differs from oracle",
    )


def test_poll_step_oracle(root: Path, haskell_build: build.BuildContext) -> None:
    """Capture requests, memory, effects, notices and incident results all agree."""
    compare_subject(
        root,
        haskell_build,
        "forbidden_actions.toml",
        "poll-step",
        "supervisor poll step differs from oracle",
    )


def test_run_flag_defaults_oracle(
    root: Path, haskell_build: build.BuildContext
) -> None:
    """The actual option parser keeps defaults and refuses invalid policies."""
    compare_subject(
        root,
        haskell_build,
        "command_surface.toml",
        "run-flag-defaults",
        "supervisor timing flags differ from oracle",
    )


def test_poll_records_oracle(root: Path, haskell_build: build.BuildContext) -> None:
    """Every capture, proposal, attempt, notification and closure has exact fields."""
    compare_subject(
        root,
        haskell_build,
        "log_records.toml",
        "record-function",
        "supervisor log records differ from oracle",
    )
    path = root / "tests/oracles/log_records.toml"
    store = load(path, read_homes(root))
    assert isinstance(store, Store), store
    effective = {row.identifier for row in store.effective}
    rows = [
        row
        for row in tomllib.loads(path.read_text(encoding="utf-8"))["case"]
        if row["id"] in effective
    ]
    schemas = [
        row["expected"] for row in rows if row["input"]["subject"] == "log-schema"
    ]
    assert len(schemas) == 1
    schema = schemas[0]
    for row in rows:
        if row["input"]["subject"] == "record-function":
            for record in row["expected"]:
                assert set(record) == set(schema["base"]) | set(schema[record["kind"]])


def test_logs_selection_oracle(root: Path, haskell_build: build.BuildContext) -> None:
    """Exact names retain run order without including a longer target's prefix."""
    compare_subject(
        root,
        haskell_build,
        "log_records.toml",
        "log-selection",
        "supervisor log selection differs from oracle",
    )


def test_log_decoding_oracle(root: Path, haskell_build: build.BuildContext) -> None:
    """Only an active writer permits an unfinished suffix; complete errors fail."""
    compare_subject(
        root,
        haskell_build,
        "log_records.toml",
        "log-decoding",
        "supervisor log decoding differs from oracle",
    )


def test_delivery_commit_oracle(root: Path, haskell_build: build.BuildContext) -> None:
    """Delivery commits only sent input and never re-enters a send in one poll."""
    compare_subject(
        root,
        haskell_build,
        "forbidden_actions.toml",
        "delivery-completion",
        "supervisor delivery completion differs from oracle",
    )
