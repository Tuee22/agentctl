# Copyright (c) 2026 agentctl contributors.
"""Folder names, independent hashes and ownership decisions through native values."""

import hashlib
import tomllib
from pathlib import Path

import pytest

from agentctl.bootstrap import build
from tests.harness.evaluate import compare_subject

pytestmark = pytest.mark.evidence("value")


def test_session_names_match_oracle(
    root: Path, haskell_build: build.BuildContext
) -> None:
    """Both name forms match the independent rows and standard-library hashes."""
    compare_subject(
        root,
        haskell_build,
        "session_names.toml",
        "session-names",
        "session names differ from oracle",
    )
    rows = tomllib.loads(
        (root / "tests/oracles/session_names.toml").read_text(encoding="utf-8")
    )["case"]
    for row in rows:
        inputs = row["input"]
        if inputs["subject"] == "session-names":
            canonical = inputs["canonical"]
            windows = inputs["windows"]
            assert isinstance(canonical, str)
            assert isinstance(windows, bool)
            identity = canonical.casefold() if windows else canonical
            digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:8]
            expected = row["expected"]
            assert expected["hashed"] == (
                expected["base"] + "-" + digest + "-" + inputs["agent"]
            ), "oracle hash differs from hashlib"


def test_decision_rows_match_oracle(
    root: Path, haskell_build: build.BuildContext
) -> None:
    """A foreign or unidentified session never becomes an attachment target."""
    for subject in ("session-decision", "session-selection"):
        compare_subject(
            root,
            haskell_build,
            "session_names.toml",
            subject,
            "session decision differs from oracle",
        )
