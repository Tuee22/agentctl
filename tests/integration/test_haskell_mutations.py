# Copyright (c) 2026 agentctl contributors.
"""Native mutation selection, compilation failures and actual report boundaries."""

import json
import os
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from agentctl.bootstrap import build
from agentctl.check import haskell_mutants
from agentctl.check.mutants import Mutant, Operator, exercise, scratch
from agentctl.process import Output, run
from agentctl.result import Err, Ok
from tests.harness.bootstrap import context
from tests.harness.nonce import fresh

NODE = "haskell:agentctl-core-test/Handshake/protocol-fields"


@pytest.mark.evidence("observer")
def test_native_edge_vetoes(
    root: Path, tmp_path: Path, haskell_build: build.BuildContext
) -> None:
    """A positive spawn precedes each veto and every native failure remains typed."""
    for mode in ("index-init", "suite-list", "suite-execute", "mutant-execute"):
        nonce = fresh(os.environ.get("AGENTCTL_CHECK_NONCE", "focused"))
        output = run(
            [
                sys.executable,
                str(root / "tests/fixtures/haskell/edge_actor.py.txt"),
                mode,
                str(tmp_path / mode),
                str(haskell_build.project),
                str(haskell_build.directory),
                str(haskell_build.host.cache),
                haskell_build.tools.ghc,
                haskell_build.tools.cabal,
                nonce,
            ],
            cwd=root,
            env=os.environ,
        )
        assert isinstance(output, Ok)
        assert output.value.code == 0, output.value.stderr
        value: object = json.loads(output.value.stdout)
        assert isinstance(value, dict)
        assert value["nonce"] == nonce
        assert value["refused"] is True
        events = value["events"]
        assert isinstance(events, list)
        assert events[0]["argv"] == [sys.executable, "-c", "print('observer control')"]
        assert not events[0]["blocked"]
        assert events[-1]["blocked"]
        assert all(event["nonce"] == nonce for event in events)


@pytest.mark.evidence("real")
def test_native_mutation_failures_never_count_as_kills(
    root: Path, tmp_path: Path, haskell_build: build.BuildContext
) -> None:
    """A passing native baseline accompanies missing-record and bad-build controls."""
    tree = tmp_path / "checkout"
    assert scratch(root, tree) == Ok(tree)
    native = haskell_build.host
    assert haskell_mutants.killer(tree, NODE, native) == Ok(Output(0, "", ""))
    assert isinstance(
        haskell_mutants.killer(tree, NODE, context(tmp_path / "missing-record")), Err
    )
    assert isinstance(
        haskell_mutants.killer(
            tree, "haskell:agentctl-core-test/Handshake/missing", native
        ),
        Err,
    )
    missing = replace(
        haskell_build,
        tools=replace(haskell_build.tools, cabal=str(tmp_path / "missing-cabal")),
    )
    assert isinstance(
        haskell_mutants.selected_case(missing, NODE, tmp_path / "missing.xml"), Err
    )
    target = tree / "src/agentctl/haskell/src/AgentCtl/Protocol.hs"
    original = target.read_bytes()
    record = Mutant(
        "M-build-compile-control",
        Operator.REPLACE_LITERAL,
        "src/agentctl/haskell/src/AgentCtl/Protocol.hs",
        "protocolVersion = 1",
        "protocolVersion = invalid.syntax",
        (NODE,),
        "handshake command list differs",
    )
    rejected = exercise(tree, record)
    assert isinstance(rejected, Err)
    assert rejected.error.stage == "spawn"
    assert target.read_bytes() == original


@pytest.mark.evidence("real")
def test_native_mutation_report_boundaries(tmp_path: Path) -> None:
    """Only the selected case's actual XML failure text becomes a named reason."""
    path = tmp_path / "tasty.xml"
    assert isinstance(haskell_mutants.case_outcomes(path, NODE, 1), Err)
    path.write_text("<invalid", encoding="utf-8")
    assert isinstance(haskell_mutants.case_outcomes(path, NODE, 1), Err)
    xml = (
        '<testsuites tests="1"><testcase classname="agentctl-core-test.Handshake" '
        'name="protocol-fields"><failure>named defect</failure>'
        "</testcase></testsuites>"
    )
    path.write_text(xml, encoding="utf-8")
    assert haskell_mutants.case_outcomes(path, NODE, 1) == Ok(
        Output(1, "E named defect", "")
    )
    assert isinstance(
        haskell_mutants.case_outcomes(
            path, "haskell:agentctl-core-test/Handshake/other", 1
        ),
        Err,
    )
    path.write_bytes(b"\xff")
    assert isinstance(haskell_mutants.case_outcomes(path, NODE, 1), Err)
