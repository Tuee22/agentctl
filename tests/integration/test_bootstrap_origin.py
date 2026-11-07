# Copyright (c) 2026 agentctl contributors.
"""Independent pre-bootstrap records distinguish absence from existing tools."""

import hashlib
import json
import os
from dataclasses import replace
from pathlib import Path

import pytest

from tests.harness.bootstrap import context
from tests.harness.bootstrap_origin import capture, location, state_directory
from tests.harness.nonce import fresh

pytestmark = pytest.mark.evidence("real")


def test_absence_record_precedes_first_file(tmp_path: Path) -> None:
    """A clean observed prefix gains one private witness which is never rewritten."""
    value = replace(context(tmp_path), family="Linux")
    env = dict(value.environment)
    nonce = fresh(os.environ.get("AGENTCTL_CHECK_NONCE", "focused"))
    initial = capture(tmp_path / "first", nonce, value.family, env, value.home)
    assert initial["nonce"] == nonce
    assert initial["origin"] == "agentctl-installed"
    assert initial["found"] is None
    assert initial["configured_existed"] is False
    witness = state_directory(value.family, env, value.home) / "pre-bootstrap.json"
    assert witness.is_relative_to(tmp_path)
    before = witness.read_bytes()
    data: object = json.loads(before)
    assert isinstance(data, dict)
    assert data["before"] == {"ghcup": False, "ghc": False, "cabal": False}
    binary = location(value.family, env, value.home)
    binary.parent.mkdir(parents=True)
    binary.write_bytes(b"owned fixture, never executed")
    later = capture(tmp_path / "later", fresh(nonce), value.family, env, value.home)
    assert later["origin"] == "agentctl-installed"
    assert later["found"] == str(binary.resolve())
    assert later["sha256"] == hashlib.sha256(binary.read_bytes()).hexdigest()
    assert witness.read_bytes() == before


def test_existing_tool_and_mismatched_witness(tmp_path: Path) -> None:
    """An existing binary is user provenance and an invalid witness cannot qualify."""
    value = context(tmp_path)
    env = dict(value.environment)
    binary = location(value.family, env, value.home)
    binary.parent.mkdir(parents=True)
    binary.write_bytes(b"existing fixture")
    nonce = fresh(os.environ.get("AGENTCTL_CHECK_NONCE", "focused"))
    initial = capture(tmp_path / "before", nonce, value.family, env, value.home)
    assert initial["origin"] == "user"
    witness = state_directory(value.family, env, value.home) / "pre-bootstrap.json"
    assert not witness.exists()
    witness.parent.mkdir(parents=True)
    witness.write_text(
        json.dumps(
            {
                "family": value.family,
                "configured": "wrong-prefix",
                "before": {"ghcup": False, "ghc": False, "cabal": False},
                "nonce": "0" * 32,
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(AssertionError):
        capture(tmp_path / "invalid", fresh(nonce), value.family, env, value.home)
