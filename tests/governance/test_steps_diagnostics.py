# Copyright (c) 2026 agentctl contributors.
"""Independent expected values for the Ruff and type-checker diagnostic decoders."""

import json
from pathlib import Path

import pytest

from agentctl.check import steps
from agentctl.check.steps import TySnapshot
from agentctl.process import Output
from agentctl.result import Err, Ok

pytestmark = pytest.mark.evidence("value")
RUFF_ROW = 3
TY_LINE = 7


def _ruff_row(filename: str) -> dict[str, object]:
    return {
        "filename": filename,
        "code": "E501",
        "message": "too long",
        "location": {"row": RUFF_ROW, "column": 1},
    }


def _ty_row(path: str) -> dict[str, object]:
    return {
        "check_name": "invalid-assignment",
        "description": "bad",
        "severity": "major",
        "location": {"path": path, "positions": {"begin": {"line": TY_LINE}}},
    }


def test_ruff_paths_must_name_python_targets(tmp_path: Path) -> None:
    """Only absolute in-checkout Python sources under src or tests are findings."""
    root = tmp_path.resolve()
    outside = (root.parent / "elsewhere" / "x.py").as_posix()
    outside_targets = "Ruff diagnostic is outside Python targets"
    cases = (
        (outside, "Ruff diagnostic is outside checkout"),
        ((root / "docs" / "x.py").as_posix(), outside_targets),
        ((root / "src" / "x.txt").as_posix(), outside_targets),
    )
    for filename, message in cases:
        output = Output(1, json.dumps([_ruff_row(filename)]), "")
        assert steps.parse_ruff_output(root, output) == Err(
            "Ruff diagnostics disagree with the subprocess status"
        ), message
        assert steps.__dict__["_ruff_fact"](root, _ruff_row(filename)) == Err(message)
    accepted = (root / "src" / "x.py").as_posix()
    parsed = steps.parse_ruff_output(
        root, Output(1, json.dumps([_ruff_row(accepted)]), "")
    )
    assert isinstance(parsed, Ok)
    assert parsed.value[0].path == "src/x.py"
    assert parsed.value[0].row == RUFF_ROW


def test_ruff_output_refuses_malformed_json_and_rows(tmp_path: Path) -> None:
    """Malformed documents and non-list roots are structured refusals."""
    root = tmp_path.resolve()
    assert steps.parse_ruff_output(root, Output(1, "{", "")) == Err("invalid Ruff JSON")
    assert steps.parse_ruff_output(root, Output(1, "{}", "")) == Err(
        "invalid Ruff JSON rows"
    )
    assert steps.parse_ruff_output(root, Output(1, "[1]", "")) == Err(
        "Ruff diagnostics disagree with the subprocess status"
    )
    assert steps.parse_ruff_output(root, Output(2, "[]", "")) == Err(
        "Ruff diagnostic status or context is unavailable"
    )


def test_ty_output_refuses_malformed_documents_and_paths(tmp_path: Path) -> None:
    """The type-checker decoder checks syntax, shape, status and relative paths."""
    root = tmp_path.resolve()
    assert steps.parse_ty_output(root, Output(1, "{", "")) == Err("invalid ty JSON")
    assert steps.parse_ty_output(root, Output(1, "{}", "")) == Err(
        "invalid ty JSON rows"
    )
    assert steps.parse_ty_output(root, Output(2, "[]", "")) == Err(
        "ty diagnostic status or context is unavailable"
    )
    assert steps.parse_ty_output(root, Output(1, "[]", "")) == Err(
        "ty diagnostics disagree with the subprocess status"
    )
    for path in ("", "../outside.py"):
        assert steps.__dict__["_ty_fact"](root, _ty_row(path)) == Err(
            "invalid ty diagnostic path"
        )
    assert steps.__dict__["_ty_fact"](root, {"check_name": 1}) == Err(
        "invalid ty diagnostic"
    )
    relative = steps.parse_ty_output(
        root, Output(1, json.dumps([_ty_row("src/a.py")]), "")
    )
    assert isinstance(relative, Ok)
    assert relative.value[0].path == "src/a.py"
    assert relative.value[0].row == TY_LINE


def test_ty_snapshot_recording_is_exclusive_and_checked(tmp_path: Path) -> None:
    """An invalid snapshot, or an existing record, is refused without overwriting."""
    root = tmp_path.resolve()
    output = Output(0, "[]", "")
    snapshot = TySnapshot("nonce", root, output, ())
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    assert steps.record_ty_snapshot(run_dir, TySnapshot("", root, output, ())) == Err(
        "invalid ty snapshot"
    )
    recorded = steps.record_ty_snapshot(run_dir, snapshot)
    assert isinstance(recorded, Ok)
    assert json.loads(recorded.value.record)["nonce"] == "nonce"
    again = steps.record_ty_snapshot(run_dir, snapshot)
    assert isinstance(again, Err)
    assert again.error.startswith("cannot record ty observation: ")
    assert (run_dir / "ty-observation.json").read_bytes() == recorded.value.record
