# Copyright (c) 2026 agentctl contributors.
"""Provisional, finalizer and killer handoff records refuse altered evidence."""

import json
from pathlib import Path

import pytest

from agentctl.check import steps
from agentctl.foundation import Err, Ok

pytestmark = pytest.mark.evidence("real")

NONCE = "abc123"
PASSING = tuple((name, 0) for name in steps.FINALIZER_NAMES[:-1])


def test_provisional_record_refusals(tmp_path: Path) -> None:
    """Existing, changed, linked or invalid provisional records are refused."""
    assert isinstance(steps.record_provisional_phases(tmp_path, "", None), Err)
    recorded = steps.record_provisional_phases(tmp_path, NONCE, Err("missing"))
    assert isinstance(recorded, Ok), recorded
    again = steps.record_provisional_phases(tmp_path, NONCE, Err("missing"))
    assert isinstance(again, Err)
    assert "cannot record provisional phases" in again.error
    assert steps.provisional_phases_unchanged(tmp_path, recorded) == 0
    assert steps.provisional_phases_unchanged(tmp_path, Err("lost")) == 1
    path = tmp_path / "provisional-phases.json"
    path.write_bytes(recorded.value + b" ")
    assert steps.provisional_phases_unchanged(tmp_path, recorded) == 1
    path.unlink()
    path.mkdir()
    assert steps.provisional_phases_unchanged(tmp_path, recorded) == 1


def test_provisional_record_schema() -> None:
    """Invalid JSON or a foreign nonce never parses as a provisional record."""
    foreign = json.dumps({"nonce": "other"}).encode()
    assert steps.parse_provisional_record(NONCE, b"{") == Err(
        "invalid provisional record JSON"
    )
    for contents in (b"[]", foreign):
        assert steps.parse_provisional_record(NONCE, contents) == Err(
            "invalid provisional record identity"
        )


def test_provisional_record_phase_shapes() -> None:
    """Phase lists must be lists of exactly numbered, identified failures."""
    base = {"nonce": NONCE, "status": "provisional", "phases": "x"}
    assert steps.parse_provisional_record(NONCE, json.dumps(base).encode()) == Err(
        "invalid provisional record phases"
    )
    extra = {**base, "phases": [{"number": 0}]}
    assert isinstance(
        steps.parse_provisional_record(NONCE, json.dumps(extra).encode()), Err
    )


def test_provisional_handoff_refusals(tmp_path: Path) -> None:
    """Missing, malformed, linked or unreadable handoff records fail closed."""
    verify = steps.verify_provisional_handoff
    assert verify(tmp_path, NONCE, "") == Err(
        "missing or ambiguous provisional handoff"
    )
    bad_identity = f"{steps.PROVISIONAL_SEAL} other {'0' * 64}\nfinal\n"
    assert verify(tmp_path, NONCE, bad_identity) == Err(
        "invalid provisional handoff identity"
    )
    sealed = f"{steps.PROVISIONAL_SEAL} {NONCE} {'0' * 64}\nfinal\n"
    missing = verify(tmp_path, NONCE, sealed)
    assert isinstance(missing, Err)
    assert "cannot read provisional handoff" in missing.error
    target = tmp_path / "target.json"
    target.write_text("{}", encoding="utf-8")
    (tmp_path / "provisional-phases.json").symlink_to(target)
    assert verify(tmp_path, NONCE, sealed) == Err(
        "provisional handoff record is a symlink"
    )


def test_finalizer_record_refusals(tmp_path: Path) -> None:
    """Invalid statuses, linked records and missing killer seals are refused."""
    assert steps.record_finalizers(tmp_path, "", PASSING) == Err(
        "invalid finalizer observations"
    )
    assert steps.record_finalizers(tmp_path, NONCE, ()) == Err(
        "invalid finalizer observations"
    )
    target = tmp_path / "target.json"
    target.write_text("{}", encoding="utf-8")
    linked = tmp_path / "linked"
    linked.mkdir()
    (linked / "finalizer-outcomes.json").symlink_to(target)
    assert steps.finalizer_observation(linked, NONCE) == Err(
        "finalizer record is a symlink"
    )
    assert isinstance(steps.finalizer_observation(tmp_path, NONCE), Err)
    assert isinstance(steps.verify_killer_handoff(tmp_path, NONCE, ""), Err)
    recorded = steps.record_finalizers(tmp_path, NONCE, PASSING)
    assert isinstance(recorded, Ok), recorded
    assert steps.verify_killer_handoff(tmp_path, NONCE, "") == Err(
        "missing or ambiguous mutant killer handoff"
    )
    sealed = f"{steps.KILLER_SEAL} {NONCE} {'0' * 64}\nprovisional\nfinal\n"
    unavailable = steps.verify_killer_handoff(tmp_path, NONCE, sealed)
    assert isinstance(unavailable, Err)
    assert "mutant killer handoff record unavailable" in unavailable.error
    failed = tmp_path / "failed"
    failed.mkdir()
    statuses = tuple(
        (name, 1 if name == "mutant-killers" else 0) for name, _ in PASSING
    )
    assert isinstance(steps.record_finalizers(failed, NONCE, statuses), Ok)
    assert steps.verify_killer_handoff(failed, NONCE, "") == Ok(None)


def test_finalizer_handoff_refusals(tmp_path: Path) -> None:
    """The final seal must be last, exact, current and match an unlinked record."""
    verify = steps.verify_finalizer_handoff
    assert verify(tmp_path, NONCE, "") == Err("missing or ambiguous finalizer handoff")
    foreign = f"{steps.FINALIZER_SEAL} other {'0' * 64}"
    assert verify(tmp_path, NONCE, foreign) == Err("invalid finalizer handoff identity")
    sealed = f"{steps.FINALIZER_SEAL} {NONCE} {'0' * 64}"
    unavailable = verify(tmp_path, NONCE, sealed)
    assert isinstance(unavailable, Err)
    assert "finalizer handoff record unavailable" in unavailable.error
    recorded = steps.record_finalizers(tmp_path, NONCE, PASSING)
    assert isinstance(recorded, Ok), recorded
    assert verify(tmp_path, NONCE, sealed) == Err("finalizer handoff digest mismatch")
    assert verify(tmp_path, NONCE, steps.finalizer_seal(recorded.value)) == Ok(None)


def test_native_joins_refuse_missing_observations(tmp_path: Path) -> None:
    """Native joins are skipped only without inputs and fail on missing records."""
    tool_join = steps.__dict__["_native_tool_join"]
    source_join = steps.__dict__["_native_source_join"]
    ownership = steps.__dict__["_native_ownership_observation"]
    assert tool_join(tmp_path, NONCE, None) == 0
    assert source_join(tmp_path, NONCE, None) == 0
    assert tool_join(tmp_path, NONCE, ("cabal-test",)) == 1
    assert source_join(tmp_path, NONCE, ()) == 1
    assert ownership(tmp_path, NONCE, (), (), None) == 1
    (tmp_path / "tool-outcomes.json").write_text(
        json.dumps({"nonce": NONCE, "outcomes": [["cabal-test", 0]]}),
        encoding="utf-8",
    )
    assert tool_join(tmp_path, NONCE, ("cabal-test",)) == 1


def test_report_retention_boundaries(tmp_path: Path) -> None:
    """Reports outside the owned state root, or already present, are refused."""
    root, state = tmp_path / "checkout", tmp_path / "state"
    root.mkdir()
    report = state / "check-reports" / NONCE
    report.mkdir(parents=True)
    (state / "check-reports" / "XYZ").mkdir()
    assert steps.retain_cleanup_failure(root, state, "XYZ", "m") == Err(
        "cleanup report boundary is invalid"
    )
    assert steps.retain_cleanup_failure(root, state, NONCE, "m") == Ok(None)
    retained = steps.retain_cleanup_failure(root, state, NONCE, "again")
    assert isinstance(retained, Err)
    assert "cannot retain cleanup failure" in retained.error
    foreign = tmp_path / "foreign"
    foreign.mkdir()
    assert steps.retain_handoff_failure(root, state, foreign, "m") == Err(
        "finalizer handoff report boundary is invalid"
    )
    assert steps.retain_handoff_failure(root, state, report, "m") == Ok(None)
    repeated = steps.retain_handoff_failure(root, state, report, "m")
    assert isinstance(repeated, Err)


def test_linked_run_artifacts_are_not_retained(tmp_path: Path) -> None:
    """A run artifact replaced by a link stops report retention."""
    root, state, run = tmp_path / "checkout", tmp_path / "state", tmp_path / "run"
    root.mkdir()
    run.mkdir()
    target = tmp_path / "elsewhere.json"
    target.write_text("{}", encoding="utf-8")
    (run / "tool-outcomes.json").symlink_to(target)
    retained = steps.retain_gate_output(root, state, run, NONCE, ("out", "err"))
    assert isinstance(retained, Err)
    assert "run artifact is a symlink: tool-outcomes.json" in retained.error
    assert steps.retain_gate_output(root, state, run, "", ("o", "e")) == Err(
        "invalid report nonce"
    )
