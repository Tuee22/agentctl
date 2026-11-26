# Copyright (c) 2026 agentctl contributors.
"""Closed-schema refusals of the retained mutant report decoder."""

import json
from pathlib import Path

import pytest

from agentctl.check import mutant_report
from agentctl.check.mutant_report import MAX_BYTES, decode, read
from agentctl.result import Err

pytestmark = pytest.mark.evidence("value")

NONCE = "nonce"
OVERSIZE = MAX_BYTES + 2


def _killer(**changes: object) -> dict[str, object]:
    return {
        "node": "tests/unit/test_subject.py::test_answer",
        "baseline": "passed",
        "mutation": "killed",
        **changes,
    }


def _record(**changes: object) -> dict[str, object]:
    return {"identifier": "M-a", "error": "", "killers": [_killer()], **changes}


def _encode(*records: object) -> bytes:
    return json.dumps({"nonce": NONCE, "records": list(records)}).encode("utf-8")


def test_decode_refuses_empty_data_and_empty_nonce() -> None:
    """Empty bytes or an empty nonce fail before parsing."""
    expected = Err("invalid mutant report size or nonce")
    assert decode(b"", NONCE) == expected
    assert decode(_encode(_record()), "") == expected


def test_decode_refuses_malformed_killer_rows() -> None:
    """A killer row outside the closed shape is an invalid killer record."""
    result = decode(_encode(_record(killers=[1])), NONCE)
    assert result == Err("invalid mutant report record")
    assert mutant_report.__dict__["_killer"](1) == Err("invalid mutant killer fields")


def test_decode_refuses_malformed_record_rows() -> None:
    """A record row outside the closed shape is refused."""
    assert decode(_encode(1), NONCE) == Err("invalid mutant report record")
    assert mutant_report.__dict__["_record"](1) == Err("invalid mutant record fields")


def test_decode_refuses_invalid_record_values() -> None:
    """An empty identifier or killer-less clean record is refused."""
    assert mutant_report.__dict__["_record"](_record(identifier="")) == Err(
        "invalid mutant record values"
    )
    assert decode(_encode(_record(killers=[])), NONCE) == Err(
        "invalid mutant report record"
    )


def test_decode_refuses_duplicate_records() -> None:
    """Two records with one identifier are refused."""
    assert decode(_encode(_record(), _record()), NONCE) == Err(
        "duplicate mutant report record"
    )


def test_append_ignores_foreign_values() -> None:
    """The accumulator falls through for values outside its two variants."""
    assert mutant_report.__dict__["_append"]("foreign", "foreign") is None


def test_decoders_ignore_foreign_reductions(monkeypatch: pytest.MonkeyPatch) -> None:
    """A reduction yielding no known variant produces no verdict."""
    monkeypatch.setitem(
        mutant_report.__dict__, "_append_killer", lambda *_args: "foreign"
    )
    assert mutant_report.__dict__["_record"](_record()) is None
    monkeypatch.setitem(
        mutant_report.__dict__, "_append_record", lambda *_args: "foreign"
    )
    assert decode(_encode(_record()), NONCE) is None


def test_read_refuses_oversize_report(tmp_path: Path) -> None:
    """A file larger than the bounded read is reported as changed."""
    path = tmp_path / "report.json"
    with path.open("wb") as stream:
        stream.truncate(OVERSIZE)
    assert read(path, NONCE) == Err("mutant report changed during read")
