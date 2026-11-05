# Copyright (c) 2026 agentctl contributors.
"""Independent multiplexer and session-name cases through the native evaluator."""

import json
import tomllib
from pathlib import Path

import pytest

from agentctl.bootstrap import build
from agentctl.result import Ok
from tests.harness.oracle import Store, assert_oracle, read_homes
from tests.harness.oracle import load as oracle_load

pytestmark = pytest.mark.evidence("value")


def _compare(
    root: Path, context: build.BuildContext, subject: str, filename: str, reason: str
) -> None:
    """Send only independent fixture inputs and compare every ordered native answer."""
    store = oracle_load(root / "tests/oracles" / filename, read_homes(root))
    assert isinstance(store, Store)
    effective = {row.identifier for row in store.effective}
    rows = tomllib.loads(
        (root / "tests/oracles" / filename).read_text(encoding="utf-8")
    )["case"]
    selected = [
        row
        for row in rows
        if row["id"] in effective and row["input"]["subject"] == subject
    ]
    assert selected
    request = "\n".join(json.dumps(row["input"]) for row in selected) + "\n"
    result = build.execute_binary(
        context, build.BinaryCall("exe:agentctl-core-eval", input_text=request)
    )
    assert isinstance(result, Ok), result
    assert result.value.code == 0, result.value.stderr
    actual = [json.loads(line) for line in result.value.stdout.splitlines()]
    assert_oracle(
        lambda _: actual, None, [row["expected"] for row in selected], row_id=reason
    )


def test_version_floor_oracle(root: Path, haskell_build: build.BuildContext) -> None:
    """The tmux letter suffix and both native floors match independent cases."""
    _compare(
        root,
        haskell_build,
        "mux-version",
        "mux_commands.toml",
        "multiplexer version differs from oracle",
    )


def test_resolution_candidates_oracle(
    root: Path, haskell_build: build.BuildContext
) -> None:
    """Windows admits only the psmux executable; other hosts select tmux."""
    _compare(
        root,
        haskell_build,
        "mux-candidates",
        "mux_commands.toml",
        "multiplexer candidates differ from oracle",
    )


def test_remedy_oracle(root: Path, haskell_build: build.BuildContext) -> None:
    """Each OS and Linux distribution receives its recorded install remedy."""
    _compare(
        root,
        haskell_build,
        "mux-remedy",
        "mux_commands.toml",
        "multiplexer remedy differs from oracle",
    )


def test_session_name_oracle(root: Path, haskell_build: build.BuildContext) -> None:
    """Only nonempty safe ASCII names without a leading dash or separator pass."""
    _compare(
        root,
        haskell_build,
        "session-name-valid",
        "session_names.toml",
        "session name acceptance differs from oracle",
    )


def test_render_oracle(root: Path, haskell_build: build.BuildContext) -> None:
    """Each allowed action preserves its independent executable and argv row."""
    _compare(
        root,
        haskell_build,
        "mux-render",
        "mux_commands.toml",
        "multiplexer command differs from oracle",
    )


def test_dead_status_rule_oracle(root: Path, haskell_build: build.BuildContext) -> None:
    """Native pane status and signals differ from psmux's status file."""
    _compare(
        root,
        haskell_build,
        "mux-dead-status",
        "mux_commands.toml",
        "multiplexer dead status differs from oracle",
    )


def test_spec_acceptance_oracle(root: Path, haskell_build: build.BuildContext) -> None:
    """Native file facts meet every independent owner, kind and mode case."""
    _compare(
        root,
        haskell_build,
        "mux-spec-acceptance",
        "mux_commands.toml",
        "spec access differs from oracle",
    )


def test_reap_policy_oracle(root: Path, haskell_build: build.BuildContext) -> None:
    """Only a dead tmux pane without a published status needs a reap request."""
    _compare(
        root,
        haskell_build,
        "mux-reap-policy",
        "mux_commands.toml",
        "multiplexer reap policy differs from oracle",
    )


def test_invocation_cwd_stays_off_argv(
    root: Path, haskell_build: build.BuildContext
) -> None:
    """The production invocation carries the caller directory outside mux parsing."""
    _compare(
        root,
        haskell_build,
        "mux-invocation",
        "mux_commands.toml",
        "native invocation moved caller data onto mux argv",
    )
