# Copyright (c) 2026 agentctl contributors.
"""The public click application."""

import platform
from collections.abc import Sequence
from dataclasses import dataclass
from typing import override

import click

from agentctl.bootstrap import handoff
from agentctl.check.steps import check
from agentctl.result import Err

PASSTHROUGH = (
    "claude",
    "codex",
    "list",
    "status",
    "attach",
    "stop",
    "adopt",
    "watch",
    "unwatch",
    "pause",
    "resume-watch",
    "logs",
    "supervisor",
)


@dataclass(frozen=True, slots=True)
class CheckRequest:
    """A parsed command whose global options are supplied by the group dispatcher."""

    family: str


@dataclass(frozen=True, slots=True)
class PassRequest:
    """An uninterpreted command tail paired with its observed host family."""

    command: str
    arguments: tuple[str, ...]
    family: str


class RawCommand(click.Command):
    """Let the group parse global options while preserving the entire command tail."""

    def __init__(self, name: str) -> None:
        """Register one real raw transport without introducing a second parser."""
        super().__init__(
            name, help="Pass arguments unchanged to the native application."
        )
        self.command_name = name

    @override
    def parse_args(self, ctx: click.Context, args: list[str]) -> list[str]:
        """Preserve separators, empty strings and help flags before tail parsing."""
        ctx.args = args
        return args

    @override
    def invoke(self, ctx: click.Context) -> PassRequest:
        """Return explicit transport data without parsing agent or binary options."""
        return PassRequest(self.command_name, tuple(ctx.args), platform.system())


@click.group()
@click.option(
    "--assume-yes", is_flag=True, help="Consent to prerequisite installation."
)
def cli(*, assume_yes: bool) -> None:
    """Manage terminal coding agents and validate this checkout."""
    del assume_yes


@cli.command("check")
def check_command() -> CheckRequest:
    """Run every introduced quality check against the editable checkout."""
    return CheckRequest(platform.system())


@cli.result_callback()
def dispatch(request: CheckRequest | PassRequest, *, assume_yes: bool) -> None:
    """Pass the group's explicit consent value without reading Context.obj."""
    if isinstance(request, CheckRequest):
        raise click.exceptions.Exit(check(request.family, assume_yes=assume_yes))
    passed: PassRequest = request
    result = handoff.run(
        passed.family, passed.command, passed.arguments, assume_yes=assume_yes
    )
    if isinstance(result, Err):
        click.echo("agentctl: " + result.error.message, err=True)
        code = 1
    else:
        code = result.value
    raise click.exceptions.Exit(code)


for _command in PASSTHROUGH:
    cli.add_command(RawCommand(_command))


def main(argv: Sequence[str] | None = None) -> None:
    """Run the public application with the given raw arguments."""
    cli.main(args=argv, prog_name="agentctl")
