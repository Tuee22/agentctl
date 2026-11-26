# Copyright (c) 2026 agentctl contributors.
"""Corpus, amendment and restoration refusals for the mutation executor."""

from pathlib import Path

import pytest

from agentctl.check import mutants
from agentctl.check.evidence import Entry
from agentctl.check.mutants import (
    Mutant,
    MutationError,
    Operator,
    Patch,
    amend_records,
    corpus,
)
from agentctl.process import Output
from agentctl.result import Err, Ok

pytestmark = pytest.mark.evidence("value")
KILLER = "haskell:agentctl-core-test/Group/case-one"
TIMEOUT = 30


def _row(**changes: object) -> dict[str, object]:
    return {
        "id": "M-cover",
        "operator": "replace-literal",
        "target": "src/sample.py",
        "search": "return 2",
        "replace": "return 3",
        "killers": ["tests/unit/test_subject.py::test_answer"],
        "reason": "named answer defect",
        **changes,
    }


def _amendment(**changes: str) -> dict[str, object]:
    return {
        "id": "M-cover",
        "prior_sha256": "a",
        "revised_sha256": "b",
        "search": "x",
        "replace": "y",
        "provenance": "decision:D-1",
        **changes,
    }


def _root_with_rationale(directory: Path) -> Path:
    (directory / "DEVELOPMENT_PLAN").mkdir(parents=True)
    (directory / "DEVELOPMENT_PLAN/rationale.md").write_text(
        "| D-1 | text | `M-cover` |\n", encoding="utf-8"
    )
    return directory


def _mutant() -> Mutant:
    return Mutant(
        "M-cover",
        Operator.REPLACE_LITERAL,
        "src/sample.py",
        "return 2",
        "return 3",
        (KILLER,),
        "named answer defect",
    )


def _vanish_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove the working directory so host capture fails with a primary error."""
    gone = tmp_path / "gone"
    gone.mkdir()
    monkeypatch.chdir(gone)
    gone.rmdir()


def test_corpus_refuses_symlinked_entries(tmp_path: Path) -> None:
    """A symlinked corpus file or rationale is refused before reading."""
    directory = tmp_path / "tests/mutants"
    directory.mkdir(parents=True)
    real = tmp_path / "real.toml"
    real.write_text("", encoding="utf-8")
    (directory / "link.toml").symlink_to(real)
    assert corpus(tmp_path) == Err(
        MutationError("schema", "mutant corpus entry is a symlink")
    )
    (directory / "link.toml").unlink()
    (tmp_path / "DEVELOPMENT_PLAN").mkdir()
    (tmp_path / "DEVELOPMENT_PLAN/rationale.md").symlink_to(real)
    assert corpus(tmp_path) == Err(
        MutationError("schema", "amendment rationale is a symlink")
    )


def test_census_entry_refuses_undecodable_bytes() -> None:
    """Non-UTF-8 census bytes are a schema error."""
    entry = Entry("tests/mutants/a.toml", "file", (b"\xff",))
    result = mutants.__dict__["_census_entry_text"](entry)
    assert isinstance(result, Err)
    assert result.error.stage == "schema"


def test_amend_records_refuses_non_array_and_accepts_empty(tmp_path: Path) -> None:
    """Amendments must be an array; an empty array leaves rows unchanged."""
    assert amend_records([], "not-a-list", tmp_path) == Err(
        MutationError("schema", "amendments must be an array")
    )
    rows: list[object] = [_row()]
    assert amend_records(rows, [], tmp_path) == Ok(tuple(rows))


def test_amendment_must_name_one_original(tmp_path: Path) -> None:
    """An amendment for an absent mutant is refused."""
    root = _root_with_rationale(tmp_path)
    result = amend_records([_row(id="M-other")], [_amendment()], root)
    assert result == Err(
        MutationError("schema", "amendment must name exactly one original mutant")
    )


def test_amendment_requires_valid_original(tmp_path: Path) -> None:
    """The original row is schema-validated before an amendment applies."""
    root = _root_with_rationale(tmp_path)
    result = amend_records([{"id": "M-cover"}], [_amendment()], root)
    assert isinstance(result, Err)
    assert result.error.stage == "schema"


def test_verdict_and_helpers_accept_foreign_values() -> None:
    """Helper matches fall through for values outside their declared variants."""
    record = _mutant()
    assert mutants.__dict__["killer_verdict"](record, "foreign") is None
    assert mutants.__dict__["_failure"]("foreign") is None
    assert mutants.__dict__["_passed"]("foreign") is None


def test_exercise_restores_target_after_primary_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An interrupted run restores the target and re-raises the primary failure."""
    _vanish_cwd(tmp_path, monkeypatch)
    target = tmp_path / "sample.py"
    target.write_bytes(b"changed")
    prepared = Patch(target, b"original", b"changed")
    with pytest.raises(FileNotFoundError):
        mutants.__dict__["_exercise_killers"](tmp_path, prepared, _mutant(), TIMEOUT)
    assert target.read_bytes() == b"original"


def test_exercise_groups_primary_and_restoration_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failed restoration after a primary failure raises both together."""
    _vanish_cwd(tmp_path, monkeypatch)
    directory = tmp_path / "target-directory"
    directory.mkdir()
    prepared = Patch(directory, b"original", b"changed")
    with pytest.raises(BaseExceptionGroup) as raised:
        mutants.__dict__["_exercise_killers"](tmp_path, prepared, _mutant(), TIMEOUT)
    assert len(raised.value.exceptions) == len(("primary", "cleanup"))


def test_census_entry_refuses_non_regular_entry() -> None:
    """A directory or multi-payload entry is not decoded as a corpus file."""
    entry = Entry("tests/mutants/a.toml", "directory", ())
    assert mutants.__dict__["_census_entry_text"](entry) == Err(
        MutationError("schema", "census entry is not a regular file")
    )


def test_observed_killer_ignores_foreign_results(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The observer returns nothing when a collaborator yields no known variant."""
    observe = mutants.__dict__["_observed_killer"]
    monkeypatch.setitem(mutants.__dict__, "_killer", lambda *_args: "foreign")
    assert observe(tmp_path, "node", _mutant(), TIMEOUT, mutated=True) is None
    monkeypatch.setitem(
        mutants.__dict__, "_killer", lambda *_args: Ok(Output(1, "", ""))
    )
    monkeypatch.setitem(mutants.__dict__, "killed", lambda *_args: "foreign")
    assert observe(tmp_path, "node", _mutant(), TIMEOUT, mutated=True) is None
