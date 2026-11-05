# Copyright (c) 2026 agentctl contributors.
"""The real public parser preserves tails up to a nonce-bound, vetoed native spawn."""

import sys
import tomllib
from collections.abc import Sequence
from pathlib import Path

import pytest
from click.testing import CliRunner

from agentctl.check.audit import EVENTS, event_arguments
from agentctl.cli import PASSTHROUGH, cli
from agentctl.result import Ok
from tests.harness.launch import prepare
from tests.harness.oracle import assert_oracle
from tests.harness.passthrough import WarmCaller, warm
from tests.harness.tmux import PrivateMux


def _commands(root: Path) -> list[str]:
    """Read the complete request-derived surface independently of the live table."""
    rows = tomllib.loads(
        (root / "tests/oracles/command_surface.toml").read_text(encoding="utf-8")
    )["case"]
    expected: object = next(
        row["expected"]["commands"] for row in rows if row["id"] == "surface.complete"
    )
    assert isinstance(expected, list)
    assert all(isinstance(command, str) for command in expected)
    return [str(command) for command in expected]


def _vetoed(
    caller: WarmCaller, argv: Sequence[str], monkeypatch: pytest.MonkeyPatch
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    """Record every actual spawn boundary and veto it before any child runs."""
    for key, value in caller.case.environment.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("TMUX", raising=False)
    monkeypatch.delenv("TMUX_PANE", raising=False)
    monkeypatch.chdir(caller.case.folder)
    active = True
    observed: list[tuple[str, tuple[str, ...]]] = []

    def observe(event: str, arguments: tuple[object, ...]) -> None:
        """Keep this observer scoped to its own parser call and fresh nonce."""
        if active and event in EVENTS:
            decoded = event_arguments(event, arguments)
            assert isinstance(decoded, Ok), decoded
            observed.append((caller.case.nonce, decoded.value.argv))
            message = "owned native handoff veto"
            raise PermissionError(message)

    sys.addaudithook(observe)
    try:
        CliRunner().invoke(cli, list(argv))
    finally:
        active = False
    return tuple(observed)


@pytest.mark.evidence("value")
def test_passthrough_table_matches_oracle(root: Path) -> None:
    """Join the complete transport vocabulary to its independent request-derived row."""
    assert_oracle(
        lambda _: ["check", *PASSTHROUGH],
        None,
        _commands(root),
        row_id="passthrough command table differs",
    )


@pytest.mark.evidence("observer")
def test_every_command_but_check_passes_through(
    root: Path, mux_server: PrivateMux, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every declared command reaches a real warm handoff without another spawn."""
    caller = warm(prepare(mux_server, "claude"))
    assert ["check", *PASSTHROUGH] == _commands(root), (
        "passthrough command table differs"
    )
    for command in _commands(root)[1:]:
        arguments = (command, "literal", "--unknown", caller.case.nonce)
        observed = _vetoed(caller, arguments, monkeypatch)
        assert observed == (
            (caller.case.nonce, (str(caller.executable), *arguments)),
        ), "command did not pass through raw"


@pytest.mark.evidence("observer")
def test_raw_tail_keeps_dashdash_and_help(
    mux_server: PrivateMux, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Preserve separators, empty elements and help tokens through the public parser."""
    caller = warm(prepare(mux_server, "claude"))
    for arguments in (
        ("claude", "--", "--yolo"),
        ("codex", "--help"),
        ("claude", "-h"),
        ("claude", ""),
        ("claude", "x;", "#{pane_id}", "$(id)", "one\ntwo"),
    ):
        observed = _vetoed(caller, arguments, monkeypatch)
        assert observed == (
            (caller.case.nonce, (str(caller.executable), *arguments)),
        ), "raw tail was parsed or changed"
