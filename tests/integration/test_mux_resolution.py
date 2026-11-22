# Copyright (c) 2026 agentctl contributors.
"""Native host qualification and an opaque session-name compiler boundary."""

from pathlib import Path

import pytest

from agentctl.bootstrap import build
from agentctl.result import Err, Ok
from tests.harness.haskell import copy_project

pytestmark = pytest.mark.evidence("real")


def test_session_name_constructor_is_private(root: Path, tmp_path: Path) -> None:
    """A checked-name caller compiles; a constructor caller fails as specified."""
    context = copy_project(root, tmp_path)
    cabal = context.project / "agentctl-core.cabal"
    original = cabal.read_text(encoding="utf-8")
    anchor = "exposed-modules: AgentCtl.Protocol, "
    assert original.count(anchor) == 1
    cabal.write_text(
        original.replace(
            anchor, "exposed-modules: AgentCtl.NameWitness, AgentCtl.Protocol, "
        ),
        encoding="utf-8",
    )
    witness = context.project / "src/AgentCtl/NameWitness.hs"
    legal = (
        "module AgentCtl.NameWitness (witness) where\n"
        "import AgentCtl.Session.Name\n"
        "witness :: Either NameError SessionName\n"
        'witness = makeSessionName "good"\n'
    )
    witness.write_text(legal, encoding="utf-8")
    compiled = build.compile_project(context)
    assert isinstance(compiled, Ok), compiled
    witness.write_text(
        legal.replace('makeSessionName "good"', 'Right (SessionName "bad")'),
        encoding="utf-8",
    )
    refused = build.compile_project(context)
    assert isinstance(refused, Err), "SessionName constructor escaped"
    assert "GHC-01928" in refused.error.message, refused.error.message
    assert "Illegal term-level use" in refused.error.message
    assert "SessionName" in refused.error.message
