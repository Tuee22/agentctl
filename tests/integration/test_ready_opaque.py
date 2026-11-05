# Copyright (c) 2026 agentctl contributors.
"""The pinned compiler refuses the actual private capability constructor."""

from pathlib import Path

import pytest

from agentctl.bootstrap import build
from agentctl.result import Err, Ok
from tests.harness.haskell import copy_project

pytestmark = pytest.mark.evidence("real")


def test_ready_constructor_is_not_exported(root: Path, tmp_path: Path) -> None:
    """The real preflight caller compiles while direct construction fails by name."""
    context = copy_project(root, tmp_path)
    cabal = context.project / "agentctl-core.cabal"
    cabal.write_text(
        cabal.read_text(encoding="utf-8").replace(
            "exposed-modules: ", "exposed-modules: AgentCtl.ReadyWitness, ", 1
        ),
        encoding="utf-8",
    )
    witness = context.project / "src/AgentCtl/ReadyWitness.hs"
    fixtures = root / "tests/fixtures/static_negative"
    witness.write_bytes((fixtures / "ready_from_preflight.hs.txt").read_bytes())
    compiled = build.compile_project(context)
    assert isinstance(compiled, Ok), compiled
    witness.write_bytes((fixtures / "ready_constructed.hs.txt").read_bytes())
    refused = build.compile_project(context)
    assert isinstance(refused, Err), "Ready constructor escaped"
    assert "GHC-88464" in refused.error.message, refused.error.message
    assert "VerifiedReady" in refused.error.message
