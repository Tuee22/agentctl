# Copyright (c) 2026 agentctl contributors.
"""Per-killer record construction from failed and mixed executions."""

import pytest

from agentctl.check import gate_plugin
from agentctl.check.gate_plugin import KillerRecord, MutantRecord
from agentctl.check.mutants import (
    KillerExecution,
    KillerOutcome,
    Mutant,
    MutationError,
    Operator,
)
from agentctl.foundation import Err, Ok

pytestmark = pytest.mark.evidence("value")
NODE = "tests/unit/test_a.py::test_a"


def _mutant(killers: tuple[str, ...]) -> Mutant:
    return Mutant("M-x", Operator.REPLACE_LITERAL, "src/a.py", "1", "2", killers, "r")


def test_failed_execution_keeps_only_its_stage() -> None:
    """An execution that failed before any killer ran carries no killer rows."""
    execution = KillerExecution(_mutant((NODE,)), Err(MutationError("copy", "no")))
    assert gate_plugin.__dict__["_mutant_record"](execution) == MutantRecord(
        "M-x", "copy", ()
    )


def test_killer_statuses_name_each_outcome() -> None:
    """Baseline failures are not run against the mutation and keep their stage."""
    baseline_failure = KillerOutcome(NODE, Err(MutationError("baseline", "x")), None)
    killed = KillerOutcome(NODE, Ok(None), Err(MutationError("mutant", "y")))
    survived = KillerOutcome(NODE, Ok(None), Ok(None))
    expected = (
        (baseline_failure, KillerRecord(NODE, "failed:baseline", "not-run")),
        (killed, KillerRecord(NODE, "passed", "failed:mutant")),
        (survived, KillerRecord(NODE, "passed", "killed")),
    )
    record = gate_plugin.__dict__["_mutant_record"]
    for outcome, row in expected:
        execution = KillerExecution(_mutant((NODE,)), Ok((outcome,)))
        assert record(execution) == MutantRecord("M-x", "", (row,))


def test_inconsistent_executions_are_refused() -> None:
    """Missing declared killers or mismatched node lists yield no record."""
    record = gate_plugin.__dict__["_mutant_record"]
    outcome = KillerOutcome(NODE, Ok(None), Ok(None))
    assert record(KillerExecution(_mutant(()), Ok((outcome,)))) is None
    assert record(KillerExecution(_mutant(("other",)), Ok((outcome,)))) is None
    unrun = KillerOutcome(NODE, Ok(None), None)
    assert record(KillerExecution(_mutant((NODE,)), Ok((unrun,)))) is None
