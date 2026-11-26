# Copyright (c) 2026 agentctl contributors.
"""Closure refusals for live oracles, omitted-only integrity and owed evidence."""

from pathlib import Path

import pytest

from agentctl.check.mutants import Mutant, Operator
from agentctl.check.plan_data import Phase, Sprint
from agentctl.check.validator import closure
from agentctl.foundation import Err, Ok

pytestmark = pytest.mark.evidence("value")
CASE_ID = "tests/unit/test_subject.py::test_subject"
IDENTIFIER = "M-legs-control"
DASH = "—"
HEADER = (
    "## Gate Integrity\n\n| Requirement | Oracle | Observer | Mutants | Tests |\n"
    "|---|---|---|---|---|\n"
)


def _text(observer: str) -> str:
    return (
        "**Status**: Done\n**Gate kind**: self-verifying\n**Host lane**: any-host\n"
        + HEADER
        + f"| R20 {DASH} control | `tests/oracles/example.toml` | {observer} | "
        + f"`{IDENTIFIER}` | `{CASE_ID}` |\n"
    )


def _phase(root: Path, observer: str = "value: pure control") -> Phase:
    sprint = Sprint("0.1", "Done", f"**Mutants**: `{IDENTIFIER}`\n")
    return Phase(
        0, root / "DEVELOPMENT_PLAN/phase-0-governance.md", _text(observer), (sprint,)
    )


def _record() -> Mutant:
    return Mutant(
        IDENTIFIER,
        Operator.REPLACE_LITERAL,
        "src/subject.py",
        "x",
        "y",
        (CASE_ID,),
        "c",
    )


def _captured(owners: tuple[tuple[str, int], ...] | None) -> closure.CapturedPolicy:
    overview = "## Requirements\n\n| ID | Requirement |\n|---|---|\n| R20 | known |\n"
    return closure.CapturedPolicy(
        owners, "", overview, frozenset({"tests/oracles/example.toml"})
    )


def test_missing_oracle_is_not_present(tmp_path: Path) -> None:
    """A canonical name without a file is absent, with or without a census."""
    present = closure.__dict__["_oracle_present"]
    assert not present(tmp_path, "tests/oracles/absent.toml")
    uncensused = closure.CapturedPolicy(None, "", "", None)
    captured = closure.__dict__["_captured_oracle_present"]
    assert not captured(tmp_path, "tests/oracles/absent.toml", uncensused)
    (tmp_path / "x.toml").write_text("", encoding="utf-8")
    assert captured(tmp_path, "x.toml", uncensused)


def test_uncensused_policy_selects_no_subject_paths(tmp_path: Path) -> None:
    """Without a captured file census no subject path is observed."""
    select = closure.__dict__["_captured_subject_paths"]
    uncensused = closure.CapturedPolicy(None, "", "", None)
    assert select(tmp_path, uncensused, "src", ".py", recursive=True) == ()


def test_undeclared_only_integrity_needs_valid_declarations(tmp_path: Path) -> None:
    """Invalid declaration sets and fully declared corpora are not omissions."""
    owners = ((IDENTIFIER, 0),)
    captured = _captured(owners)
    assert isinstance(
        closure.undeclared_only_integrity((), (_record(),), captured), Err
    )
    assert closure.undeclared_only_integrity(
        (_phase(tmp_path),), (_record(),), captured
    ) == Err("no undeclared corpus mutants")


def test_scoped_integrity_refuses_foreign_owners_and_owed_evidence(
    tmp_path: Path,
) -> None:
    """Unknown owners and unmatched owed observations stay shared failures."""
    owners = ((IDENTIFIER, 0),)
    refused = closure.scoped_integrity_failures(
        (_phase(tmp_path),), (_record(),), _captured(((IDENTIFIER, 7),))
    )
    assert refused == Err("invalid integrity ownership")
    owed = closure.scoped_integrity_failures(
        (_phase(tmp_path, "owed: phase-missing"),), (_record(),), _captured(owners)
    )
    assert owed == Err("integrity owed evidence is ambiguous")
    accepted = closure.scoped_integrity_failures(
        (_phase(tmp_path),), (_record(),), _captured(owners)
    )
    assert isinstance(accepted, Ok)
