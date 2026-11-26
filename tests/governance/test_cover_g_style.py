# Copyright (c) 2026 agentctl contributors.
"""Style preparation refusal when no Haskell source exists."""

import shutil
from pathlib import Path

import pytest

from agentctl.check import style
from agentctl.result import Err, Ok
from tests.harness.bootstrap import context, pins

pytestmark = pytest.mark.evidence("value")


def test_preparation_refuses_empty_target_set(root: Path, tmp_path: Path) -> None:
    """Valid configuration without any Haskell file stops before command setup."""
    project = tmp_path / "project"
    project.mkdir()
    for name in ("fourmolu.yaml", ".hlint.yaml"):
        shutil.copyfile(root / "src/agentctl/haskell" / name, project / name)
    step = style.StyleStep("hlint", context(tmp_path / "host"), project, Ok(pins()))
    refused = style.preparation(step)
    assert isinstance(refused, Err)
    assert refused.error.message == "Empty Haskell style target set"
