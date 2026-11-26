# Copyright (c) 2026 agentctl contributors.
"""Refusals of the parent's recheck functions over captured gate observations."""

import json
from dataclasses import replace
from pathlib import Path

import pytest

from agentctl.check import phase_reports, steps
from agentctl.check.evidence import Entry, LegEvidence, RunEvidence, ToolSubsteps
from agentctl.check.plan_data import Phase, phase_text
from agentctl.check.validator.source import SourceIssue
from agentctl.process import Output
from agentctl.result import Err, Ok

pytestmark = pytest.mark.evidence("value")
MANIFEST = "src/agentctl/check/source_ownership.toml"
TEST_PATH = "tests/test_early.py"
SOURCE_PATH = "src/agentctl/subject.py"
NATIVE_PATH = "src/agentctl/haskell/Core.hs"
NONCE = "nonce"
ABSENT = "missing or duplicate census declaration: " + MANIFEST
EMPTY_RUN = RunEvidence(NONCE, frozenset(), frozenset(), frozenset(), (), ())
IDENTITY = "a" * 64
RUFF_ROW = 3


def _entries() -> tuple[Entry, ...]:
    paths = (MANIFEST, TEST_PATH, SOURCE_PATH, NATIVE_PATH)
    manifest = "version = 1\n[[phases]]\nnumber = 0\nprerequisites = []\n"
    for path in paths:
        manifest += (
            f'[[artifacts]]\npath = "{path}"\ncapability = "governance"\n'
            "owner = 0\nconsumers = [0]\nrequired = true\n"
        )
    return (
        Entry(MANIFEST, "file", (manifest.encode(),)),
        Entry(TEST_PATH, "file", (b"test",)),
        Entry(SOURCE_PATH, "file", (b"source",)),
        Entry(NATIVE_PATH, "file", (b"native",)),
    )


def _phase() -> Phase:
    parsed = phase_text(
        Path("phase-0-example.md"),
        f"### Sprint 0.1: Test [Active]\n**Validation tests**: `{TEST_PATH}::case`\n"
        "## Remaining Work\n",
    )
    assert parsed is not None
    return parsed


def _inputs() -> tuple[phase_reports.PhaseInputs, ...]:
    work = steps.scoped_source_inputs(_entries(), (_phase(),))
    assert isinstance(work, Ok)
    return work.value.work.phases


def _observed(*failures: str) -> tuple[phase_reports.PhaseResult, ...]:
    return (phase_reports.PhaseResult(0, IDENTITY, frozenset(failures)),)


def _capture(
    tools: steps.ToolOutcome,
    census: tuple[Entry, ...] | None = None,
) -> steps.ProvisionalCapture:
    return steps.ProvisionalCapture(
        Err("census") if census is None else Ok(census),
        Ok((_phase(),)),
        tools,
        ((), ()),
        Err("oracle"),
        NONCE,
        (),
        (),
    )


def _bare_tools() -> steps.ToolOutcome:
    return steps.ToolOutcome(0, Err("evidence"), Err("substeps"))


def test_collection_recheck_needs_census_and_claims() -> None:
    """Missing captured inputs or an unreadable census stop the collection join."""
    declarations = (_phase(),)
    bare = _capture(_bare_tools())
    assert steps.verify_phase_collection_failures(bare, declarations, ()) == Err(
        "phase collection inputs unavailable"
    )
    ready = replace(
        _capture(replace(_bare_tools(), pytest=Ok(EMPTY_RUN)), census=()),
        claims=((), ()),
    )
    assert steps.verify_phase_collection_failures(ready, declarations, ()) == Err(
        ABSENT
    )


def test_native_recheck_requires_captured_claims() -> None:
    """The native recheck cannot proceed without a census and mutant claims."""
    declarations = (_phase(),)
    assert steps.verify_phase_native_failures(
        _capture(_bare_tools()), declarations, ()
    ) == Err("phase native evidence unavailable or inconsistent")
    failed = LegEvidence(NONCE, (("cabal-test", 1),))
    tools = replace(_bare_tools(), evidence=Ok(failed))
    assert steps.verify_phase_native_failures(
        _capture(tools, census=()), declarations, ()
    ) == Err(ABSENT)


def test_host_recheck_needs_a_matching_host_observation() -> None:
    """A captured lane family without its host observation is refused."""
    capture = replace(_capture(_bare_tools(), census=()), family="Linux")
    assert steps.verify_phase_host_failures(capture, (_phase(),), ()) == Err(
        "phase native host observation unavailable or inconsistent"
    )


def test_tool_recheck_refuses_each_unavailable_input() -> None:
    """Tool failure recheck covers missing, mismatched and unattributable inputs."""
    declarations = (_phase(),)
    assert steps.verify_phase_tool_failures(
        _capture(_bare_tools()), declarations, ()
    ) == Err("phase tool evidence unavailable")
    snapshot = steps.NativeSnapshot(EMPTY_RUN, (), _entries())
    tools = replace(_bare_tools(), pytest=Ok(EMPTY_RUN), native=Ok(snapshot))
    assert steps.verify_phase_tool_failures(
        _capture(tools, census=()), declarations, ()
    ) == Err("phase tool native census differs")
    unattributed = _capture(replace(_bare_tools(), pytest=Ok(EMPTY_RUN)), census=())
    assert steps.verify_phase_tool_failures(unattributed, declarations, ()) == Err(
        "captured tool observations unavailable"
    )


def test_tool_recheck_refuses_unreadable_ownership(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Valid tool failures still need a readable ownership census."""
    monkeypatch.setattr(
        steps, "provisional_tool_failures", lambda *_args: Ok(frozenset())
    )
    capture = _capture(replace(_bare_tools(), pytest=Ok(EMPTY_RUN)), census=())
    assert steps.verify_phase_tool_failures(capture, (_phase(),), ()) == Err(ABSENT)


def test_coverage_recheck_requires_captured_observations() -> None:
    """A coverage recheck without a host or report observation is refused."""
    inputs = steps.CoverageAttributionInputs(
        (), (), NONCE, "Linux", None, None, Err("substeps")
    )
    assert steps.verify_phase_coverage_failures(inputs, ()) == Err(
        "coverage host or report observation unavailable"
    )


def test_source_recheck_refuses_unreadable_census_and_issues(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Source observations need a parsable census and attributable messages."""
    declarations = (_phase(),)
    assert steps.verify_phase_source_failures((), declarations, ()) == Err(
        "phase source observations unavailable"
    )
    monkeypatch.setattr(
        steps,
        "census_source_observations",
        lambda *_args: Ok((SourceIssue(None, ""),)),
    )
    assert steps.verify_phase_source_failures(_entries(), declarations, ()) == Err(
        "source validation ownership or observations differ"
    )


def test_prerequisite_recheck_refuses_empty_observations() -> None:
    """No declared phases is an invalid prerequisite observation."""
    assert steps.verify_phase_prerequisite_failures((), ()) == Err(
        "invalid prerequisite observations"
    )


def test_validation_recheck_refuses_empty_observations() -> None:
    """Shared validator findings need at least one observed phase."""
    assert steps.verify_phase_validation_failures(("problem",), ()) == Err(
        "invalid phase validation observations"
    )


def _static_inputs(
    tmp_path: Path, tool: str, entries: tuple[Entry, ...], code: int
) -> steps.ParentStaticInputs:
    context = steps.CheckRun(tmp_path, tmp_path, NONCE, "Linux")
    return steps.ParentStaticInputs(
        context,
        tmp_path,
        entries,
        _inputs(),
        LegEvidence(NONCE, ((tool, code),)),
        ToolSubsteps(NONCE, ((tool, (code,)),)),
    )


def _record(code: int, stdout: str) -> bytes:
    return json.dumps({"code": code, "stdout": stdout, "stderr": ""}).encode()


def test_static_recheck_refuses_malformed_records(tmp_path: Path) -> None:
    """The sealed static record must be JSON with exactly typed fields."""
    inputs = _static_inputs(tmp_path, "ruff-check", _entries(), 1)
    expected = (
        (b"{", "static diagnostic record is invalid"),
        (b'{"code": 1}', "static diagnostic fields are invalid"),
        (_record(1, "{"), "static diagnostic output is invalid"),
    )
    for record, message in expected:
        assert steps.verify_static_phase_failures(
            inputs, "ruff-check", record, _observed()
        ) == Err(message)


def test_static_recheck_refuses_unscopable_findings(tmp_path: Path) -> None:
    """A valid finding still needs a readable ownership census to be scoped."""
    row = {
        "filename": (tmp_path / "src" / "x.py").as_posix(),
        "code": "E501",
        "message": "too long",
        "location": {"row": RUFF_ROW, "column": 1},
    }
    inputs = _static_inputs(tmp_path, "ruff-check", (), 1)
    record = _record(1, json.dumps([row]))
    assert steps.verify_static_phase_failures(
        inputs, "ruff-check", record, _observed()
    ) == Err(ABSENT)
    parsed = steps.parse_ruff_output(tmp_path, Output(1, json.dumps([row]), ""))
    assert isinstance(parsed, Ok)
    assert parsed.value[0].code == "E501"


def test_static_recheck_requires_format_findings_to_be_unformatted(
    tmp_path: Path,
) -> None:
    """The formatter record may only contain unformatted-file findings."""
    row = {
        "filename": (tmp_path / "src" / "x.py").as_posix(),
        "code": "E501",
        "message": "too long",
        "location": {"row": RUFF_ROW, "column": 1},
    }
    inputs = _static_inputs(tmp_path, "ruff-format", _entries(), 1)
    record = _record(1, json.dumps([row]))
    assert steps.verify_static_phase_failures(
        inputs, "ruff-format", record, _observed()
    ) == Err("static diagnostic output is invalid")
