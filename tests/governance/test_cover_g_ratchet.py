# Copyright (c) 2026 agentctl contributors.
"""Refusals of amendment matching, amendment rows and baseline mutant readers."""

import hashlib
from pathlib import Path

import pytest

from agentctl.check import ratchet
from agentctl.check.ratchet import RatchetError, RowFact
from agentctl.foundation import Err, Ok
from tests.harness.git import repository

pytestmark = pytest.mark.evidence("value")
MUTANT = '[[mutant]]\nid = "a"\n'


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _amend(before: str, after: str) -> bool:
    amendment = ratchet.MutantAmendment("m", _sha(before), _sha(after))
    return ratchet.mutant_amendment_matches(
        RowFact("m", before), RowFact("m", after), amendment
    )


def test_amendment_needs_parseable_object_records() -> None:
    """Hash-matching but non-JSON or non-object contents never match."""
    assert not _amend("{", "{")
    assert not _amend("[]", "{}")
    assert not _amend("{}", "[]")


def test_amendment_rows_refuse_malformed_amendments() -> None:
    """Amendments must be a non-empty list of identified rows."""
    cases = (
        ("amendment = []\n" + MUTANT, "malformed protected amendments"),
        (MUTANT + '[[amendment]]\nname = "x"\n', "protected row has no string id"),
        (
            MUTANT + '[[amendment]]\nid = "a"\n[[amendment]]\nid = "a"\n',
            "invalid amendment revision identity",
        ),
    )
    for text, message in cases:
        assert ratchet.rows(text, "mutant") == Err(RatchetError(message))


def test_amendment_rows_keep_revisions_of_one_identity() -> None:
    """A repeated amendment identity is kept when it names its prior digest."""
    prior = "0" * 64
    text = (
        MUTANT
        + '[[amendment]]\nid = "a"\n'
        + f'[[amendment]]\nid = "a"\nprior_sha256 = "{prior}"\n'
    )
    parsed = ratchet.rows(text, "mutant")
    assert isinstance(parsed, Ok)
    identifiers = tuple(row.identifier for row in parsed.value)
    assert identifiers == ("a", "amendment:a", "amendment:a:" + prior)


def test_baseline_mutant_rows_refuse_unreadable_records(tmp_path: Path) -> None:
    """A missing, malformed or git-less baseline is a typed failure."""
    revision = repository(
        tmp_path, (("tests/mutants/bad.toml", b"not = [toml"),), with_head=True
    )
    reader = ratchet.__dict__["_mutant_rows"]
    assert isinstance(reader(tmp_path, revision, ("tests/mutants/absent.toml",)), Err)
    assert isinstance(reader(tmp_path, revision, ("tests/mutants/bad.toml",)), Err)
    relocation = ratchet.__dict__["_compare_relocations"]
    assert isinstance(
        relocation(tmp_path, revision, ("tests/mutants/absent.toml",), ()), Err
    )


def test_baseline_mutant_rows_need_git(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without Git on the search path the baseline cannot be read."""
    monkeypatch.setenv("PATH", str(tmp_path))
    outcome = ratchet.__dict__["_mutant_rows"](tmp_path, "HEAD", ("x.toml",))
    assert outcome == Err(RatchetError("git is required for the ratchet"))
