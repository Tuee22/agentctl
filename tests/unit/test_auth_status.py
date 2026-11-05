# Copyright (c) 2026 agentctl contributors.
"""Independent auth outcomes, warning remedies and refused login shapes."""

from pathlib import Path

import pytest

from agentctl.bootstrap import build
from tests.harness.evaluate import compare_subject

pytestmark = pytest.mark.evidence("value")


def test_classify_auth_matches_oracle(
    root: Path, haskell_build: build.BuildContext
) -> None:
    """Only exits zero and one denote login state; every other outcome fails."""
    compare_subject(
        root,
        haskell_build,
        "auth_status.toml",
        "auth-classify",
        "auth classification differs from oracle",
    )


def test_remedy_names_the_command_to_type(
    root: Path, haskell_build: build.BuildContext
) -> None:
    """A failed probe has a distinct warning and never recommends a fresh login."""
    for subject in ("login-remedy", "auth-warning"):
        compare_subject(
            root,
            haskell_build,
            "auth_status.toml",
            subject,
            "auth remedy differs from oracle",
        )


def test_login_shaped_args_refused(
    root: Path, haskell_build: build.BuildContext
) -> None:
    """Forbidden shapes fail beside ordinary prompts and status subcommands."""
    for subject in ("login-shaped", "login-refusal-warning"):
        compare_subject(
            root,
            haskell_build,
            "auth_status.toml",
            subject,
            "login refusal differs from oracle",
        )
