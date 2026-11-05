# Copyright (c) 2026 agentctl contributors.
"""Current-run binary identity as an explicit gate step after Cabal build."""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import click

from agentctl.bootstrap import binary
from agentctl.hostfacts import HostContext
from agentctl.result import Err


@dataclass(frozen=True, slots=True)
class IdentityStep:
    """The bundled source, ensured host and immutable application data destination."""

    host: HostContext
    project: Path
    data: Path
    name: Literal["binary-identity"] = "binary-identity"


def run_step(step: IdentityStep) -> int:
    """Name the actual Cabal and published files only when their byte hashes agree."""
    context = binary.check_context(step.host, step.project)
    if isinstance(context, Err):
        click.echo(context.error.message, err=True)
        return 1
    identity = binary.identify(context.value, step.data)
    if isinstance(identity, Err):
        click.echo(identity.error.message, err=True)
        return 1
    click.echo(
        f"binary-identity: built {identity.value.built}; "
        f"published {identity.value.published}; sha256 {identity.value.sha256}"
    )
    return 0
