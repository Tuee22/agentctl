# Copyright (c) 2026 agentctl contributors.
"""Independent ownership and folder-selection cases through the native evaluator."""

from pathlib import Path

import pytest

from agentctl.bootstrap import build
from tests.harness.evaluate import compare_subject

pytestmark = pytest.mark.evidence("value")


def test_list_rows_match_oracle(root: Path, haskell_build: build.BuildContext) -> None:
    """Only complete, owned identities become rows, with real liveness retained."""
    for subject in ("sessions-list", "sessions-status"):
        compare_subject(
            root,
            haskell_build,
            "session_ownership.toml",
            subject,
            "session rows differ from ownership oracle",
        )


def test_stop_plan_matches_oracle(
    root: Path, haskell_build: build.BuildContext
) -> None:
    """A stop can plan only the exact managed session, never a foreign target."""
    compare_subject(
        root,
        haskell_build,
        "session_ownership.toml",
        "sessions-stop",
        "session stop plan differs from ownership oracle",
    )


def test_attach_plan_matches_oracle(
    root: Path, haskell_build: build.BuildContext
) -> None:
    """Terminal state selects printing, attaching or switching the same target."""
    compare_subject(
        root,
        haskell_build,
        "session_ownership.toml",
        "sessions-attach",
        "session attach selected another target",
    )
