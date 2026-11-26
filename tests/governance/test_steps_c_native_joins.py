# Copyright (c) 2026 agentctl contributors.
"""Native source and ownership joins over real private observation files."""

import json
from dataclasses import replace
from pathlib import Path

import pytest

from agentctl.check import steps
from agentctl.check.evidence import Entry, RunEvidence
from agentctl.check.mutants import Mutant, Operator
from agentctl.check.plan_data import Phase, phase_text
from agentctl.check.steps import NativeSnapshot, PostRunInputs
from agentctl.result import Err, Ok

pytestmark = pytest.mark.evidence("value")

NONCE = "current"
MANIFEST = "src/agentctl/check/source_ownership.toml"
FRAGMENT = "src/agentctl/check/phase0_mutant_ownership.toml"
TARGET = "src/subject.py"
SOURCE = "src/agentctl/haskell/test/RecoveryTests.hs"
NODE = "haskell:agentctl-core-test/Backoff/grows-to-cap"
RECORD = Mutant("M-test-native", Operator.DELETE, TARGET, "x", "", (NODE,), "reason")
OWNERS = ((RECORD.identifier, 0),)


OTHER = "src/agentctl/haskell/test/Other.hs"


def _entries(*, with_other: bool = False) -> tuple[Entry, ...]:
    extra = (OTHER,) if with_other else ()
    text = "version = 1\n[[phases]]\nnumber = 0\nprerequisites = []\n"
    for path in (MANIFEST, FRAGMENT, TARGET, SOURCE, *extra):
        text += (
            f'[[artifacts]]\npath = "{path}"\ncapability = "control"\n'
            "owner = 0\nconsumers = [0]\nrequired = true\n"
        )
    claims = (
        'version = 1\n[[claims]]\nidentifier = "M-test-native"\nowner = 0\n'
        f'killer_sources = [{{node = "{NODE}", path = "{SOURCE}"}}]\n'
    )
    return (
        Entry(MANIFEST, "file", (text.encode(),)),
        Entry(FRAGMENT, "file", (claims.encode(),)),
        Entry(TARGET, "file", (b"source",)),
        Entry(SOURCE, "file", (b"native",)),
        *(Entry(path, "file", (b"other",)) for path in extra),
    )


def _write_native(directory: Path) -> None:
    """Write one passing native case with its source observation."""
    (directory / "tasty.xml").write_text(
        '<testsuites tests="1"><testsuite><testcase '
        'classname="agentctl-core-test.Backoff" name="grows-to-cap" />'
        "</testsuite></testsuites>",
        encoding="utf-8",
    )
    (directory / "haskell-manifest.json").write_text(
        json.dumps(
            {
                "nonce": NONCE,
                "collected": [NODE],
                "executed": [NODE],
                "passed": [NODE],
                "forbidden": [],
                "classes": {NODE: "value"},
            }
        ),
        encoding="utf-8",
    )
    (directory / "haskell-sources.json").write_text(
        json.dumps({"nonce": NONCE, "sources": [[NODE, SOURCE]]}), encoding="utf-8"
    )


def _declarations() -> tuple[Phase, ...]:
    phase = phase_text(
        Path("phase-0-example.md"),
        f"### Sprint 0.1: Test [Active]\n**Validation tests**: `{NODE}`\n",
    )
    assert phase is not None
    return (phase,)


def test_native_source_join_accepts_observed_sources(tmp_path: Path) -> None:
    """Observed native case sources joined to the census are accepted."""
    _write_native(tmp_path)
    join = steps.__dict__["_native_source_join"]
    assert join(tmp_path, NONCE, _entries()) == 0
    assert join(tmp_path, NONCE, ()) == 1


def test_native_ownership_reports_each_disagreement(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Scoped failures, fallback mappings and absent owners are all observed."""
    _write_native(tmp_path)
    observe = steps.__dict__["_native_ownership_observation"]
    entries = _entries()
    assert observe(tmp_path, NONCE, entries[3:], (RECORD,), None) == 1
    assert "census declaration" in capsys.readouterr().err
    changed = replace(RECORD, killers=("tests/x.py::t",))
    assert observe(tmp_path, NONCE, entries, (changed,), OWNERS) == 0
    assert "ownership-observation phase 0" in capsys.readouterr().err
    other = replace(RECORD, identifier="M-other")
    assert observe(tmp_path, NONCE, entries, (RECORD, other), OWNERS) == 1
    assert "captured owners differ" in capsys.readouterr().err
    assert observe(tmp_path, NONCE, entries, (other,), OWNERS) == 1
    assert "incomplete or ambiguous" in capsys.readouterr().err
    (tmp_path / "haskell-sources.json").write_text(
        json.dumps({"nonce": NONCE, "sources": [[NODE, OTHER]]}), encoding="utf-8"
    )
    assert observe(tmp_path, NONCE, _entries(with_other=True), (RECORD,), OWNERS) == 1
    assert "lacks its observed source" in capsys.readouterr().err


def test_native_attribution_reports_observed_phase_failures(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A readable native snapshot is attributed unless a guard already failed."""
    _write_native(tmp_path)
    declarations = _declarations()
    inputs = PostRunInputs((RECORD,), OWNERS, declarations, _entries())
    report = steps.__dict__["_report_native_attribution"]
    assert report(tmp_path, NONCE, inputs, declarations, (0, 0, 0)) == 0
    capsys.readouterr()
    assert report(tmp_path, NONCE, inputs, declarations, (1, 0, 0)) == 0
    assert capsys.readouterr().err == ""
    unowned = PostRunInputs((RECORD,), None, declarations, _entries())
    assert report(tmp_path, NONCE, unowned, declarations, (0, 0, 0)) == 0


def test_post_run_without_a_pytest_manifest_still_inspects_native_evidence(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A missing pytest manifest is reported even when native evidence is present."""
    _write_native(tmp_path)
    inputs = PostRunInputs((RECORD,), OWNERS)
    assert steps.post_run(tmp_path, tmp_path, NONCE, inputs) == 1
    assert "post-run-verifier:" in capsys.readouterr().err


def test_native_handoff_is_not_sealed_without_native_sources(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """No seal is emitted when the native source census cannot be digested."""
    manifest = RunEvidence(NONCE, frozenset(), frozenset(), frozenset(), (), ())
    snapshot = NativeSnapshot(manifest, (), ())
    steps.emit_native_handoff(
        NONCE,
        Ok(steps.evidence.LegEvidence(NONCE, ())),
        Ok(b"x"),
        Ok(snapshot),
        (0, 0, 0),
    )
    assert capsys.readouterr().out == ""
    assert isinstance(steps.native_observation_seal(NONCE, snapshot), Err)
