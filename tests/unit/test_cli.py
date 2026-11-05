# Copyright (c) 2026 agentctl contributors.
"""Public click command grammar, independently of effect execution."""

import click
import pytest
from click.testing import CliRunner

from agentctl.cli import RawCommand, cli

pytestmark = pytest.mark.evidence("real")


def test_cli_is_click_group() -> None:
    """Expose a real click group and parse check without extra arguments."""
    assert isinstance(cli, click.Group)
    assert tuple(
        name
        for name, command in cli.commands.items()
        if not isinstance(command, RawCommand)
    ) == ("check",)
    result = CliRunner().invoke(cli, ["check", "--help"])
    assert result.exit_code == 0
    assert "Run every introduced quality check" in result.output


def test_check_rejects_arguments() -> None:
    """Reject selectors and arbitrary trailing arguments at the public parser."""
    for tail in (["test_x.py"], ["-k", "test_x"], ["--", "anything"]):
        result = CliRunner().invoke(cli, ["check", *tail])
        assert result.exit_code == click.UsageError.exit_code
    assert CliRunner().invoke(cli, ["--assume-yes", "check", "--help"]).exit_code == 0
