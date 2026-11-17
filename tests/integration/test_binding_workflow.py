# Copyright (c) 2026 agentctl contributors.
"""Private source boundaries around pre-gate workflow setup."""

import os
from dataclasses import replace
from pathlib import Path

import pytest

from agentctl.check import binding_transaction, binding_workflow, binding_wsl
from agentctl.check.wsl_registration import Registration
from agentctl.result import Err
from tests.harness.git import repository

pytestmark = pytest.mark.evidence("real")


def test_prelaunch_refusal_removes_only_owned_challenge(tmp_path: Path) -> None:
    """An invalid user fails before spawning and preserves checkout contents."""
    source = tmp_path / "source"
    source.mkdir()
    repository(source, (("untracked", b"content"),))
    registration = Registration(
        "{854ac4df-1457-43ff-905e-2262d4de1f10}", "dedicated", r"C:\owned\debian", 2
    )
    config = binding_wsl.Configuration(
        "wsl.exe",
        "/opt/python",
        registration,
        (registration,),
        r"C:\owned",
        2,
        "root",
        0,
    )
    context = binding_workflow.Context(
        source,
        tmp_path,
        os.environ,
        config,
        binding_wsl.UnitLimits(67108864, 10, 16, 20),
    )
    target = binding_transaction.BindingTarget(
        "dedicated", "/mnt/c/source", "/work/source"
    )
    result = binding_workflow.begin(context, target)
    assert isinstance(result, Err)
    assert "invalid WSL peer invocation" in result.error
    assert not tuple(source.glob(".agentctl-binding-*")), (
        "prelaunch challenge was retained"
    )
    assert (source / "untracked").read_bytes() == b"content"


def test_missing_launcher_keeps_source_intact(tmp_path: Path) -> None:
    """A real spawn failure reaches the launcher and removes its challenge."""
    source = tmp_path / "source"
    source.mkdir()
    repository(source, (("untracked", b"content"),))
    registration = Registration(
        "{854ac4df-1457-43ff-905e-2262d4de1f10}", "dedicated", r"C:\owned\debian", 2
    )
    config = binding_wsl.Configuration(
        "wsl.exe",
        "/opt/python",
        registration,
        (registration,),
        r"C:\owned",
        2,
        "agentctl",
        1000,
    )
    config = replace(config, executable=str(tmp_path / "missing-wsl"))
    context = binding_workflow.Context(
        source,
        tmp_path,
        os.environ,
        config,
        binding_wsl.UnitLimits(67108864, 10, 16, 20),
    )
    result = binding_workflow.begin(
        context,
        binding_transaction.BindingTarget("dedicated", "/mnt/c/source", "/work/source"),
    )
    assert isinstance(result, Err)
    assert "binding host launch failed" in result.error, (
        "private launcher path was unavailable"
    )
    assert not tuple(source.glob(".agentctl-binding-*")), (
        "failed launch retained challenge"
    )
    assert (source / "untracked").read_bytes() == b"content"
