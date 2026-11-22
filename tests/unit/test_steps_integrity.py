# Copyright (c) 2026 agentctl contributors.
"""Gate run-record refusals for unavailable, linked, stale or changed records."""

import json
import sys
from pathlib import Path

import pytest

from agentctl.check import steps
from agentctl.check.evidence import Entry
from agentctl.check.legs import Leg
from agentctl.check.mutants import MutationError
from agentctl.foundation import Err

pytestmark = pytest.mark.evidence("real")

PASS = (sys.executable, "-c", "pass")


def test_unwritable_run_records_fail_closed(tmp_path: Path) -> None:
    """A run directory that cannot hold the tool record makes the run fail."""
    occupied = tmp_path / "occupied"
    occupied.write_text("not a directory", encoding="utf-8")
    outcome = steps.__dict__["_run_tools_observed"](
        tmp_path, occupied, "fresh", (Leg("probe", PASS),)
    )
    assert outcome.code == 1
    assert isinstance(outcome.evidence, Err)
    assert isinstance(outcome.substeps, Err)


def test_unavailable_original_records_fail(tmp_path: Path) -> None:
    """Without an original observation, later integrity checks cannot pass."""
    unavailable = Err("unavailable")
    assert steps.tool_outcomes_unchanged(tmp_path, "fresh", unavailable) == 1
    assert steps.tool_substeps_unchanged(tmp_path, "fresh", unavailable) == 1
    assert steps.oracle_outcomes_unchanged(tmp_path, "fresh", unavailable) == 1
    assert (
        steps.mutant_killers_match(None, Err(MutationError("schema", "x")), None) == 1
    )
    assert (
        steps.report_pytest_leg(
            tmp_path, steps.ToolOutcome(0, unavailable, unavailable)
        )
        == 1
    )


def test_linked_and_stale_manifests_are_refused(tmp_path: Path) -> None:
    """Symlinked records and foreign nonces never become current observations."""
    target = tmp_path / "target.json"
    target.write_text(json.dumps({"nonce": "other"}), encoding="utf-8")
    (tmp_path / "pytest-manifest.json").symlink_to(target)
    (tmp_path / "oracle-outcomes.json").symlink_to(target)
    assert steps.pytest_observation(tmp_path, "fresh") == Err(
        "pytest manifest is a symlink"
    )
    assert steps.oracle_observation(tmp_path, "fresh") == Err(
        "oracle outcome record is a symlink"
    )
    plain = tmp_path / "plain"
    plain.mkdir()
    manifest = {
        "nonce": "other",
        "collected": [],
        "executed": [],
        "passed": [],
        "forbidden": [],
        "classes": {},
    }
    (plain / "pytest-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    observed = steps.pytest_observation(plain, "fresh")
    assert isinstance(observed, Err)


def test_oracle_diagnostics_require_declared_ownership() -> None:
    """Oracle diagnostics refuse a census without one parsable ownership manifest."""
    details = steps.evidence.OracleDetails("fresh", (), ())
    outcomes = steps.evidence.LegEvidence("fresh", (("oracle-validation", 0),))
    missing = steps.oracle_diagnostics((), details, outcomes)
    assert isinstance(missing, Err)
    assert "missing or duplicate census declaration" in missing.error
    broken = (Entry("src/agentctl/check/source_ownership.toml", "file", (b"not = [",)),)
    assert isinstance(steps.oracle_diagnostics(broken, details, outcomes), Err)
