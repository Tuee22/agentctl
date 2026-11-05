# Copyright (c) 2026 agentctl contributors.
"""Atomic native tool publication and refusing corrupted or incomplete cache inputs."""

import shutil
from dataclasses import replace
from pathlib import Path

import pytest

from agentctl.bootstrap import build, style, toolchain
from agentctl.bootstrap.pins import PinError, Version
from agentctl.check.style import StyleStep, preparation, run_step
from agentctl.process import Output
from agentctl.result import Err, Ok
from tests.harness.bootstrap import context, pins
from tests.harness.haskell import copy_project

pytestmark = pytest.mark.evidence("real")


def _copy_tools(native: build.BuildContext, directory: Path) -> style.StyleTools:
    """Use genuine built tools as publication inputs without invoking an installer."""
    selected = pins()
    tools = style.paths(
        style.directory(native.host.cache, selected), native.host.family
    )
    directory.mkdir(parents=True)
    copied = style.paths(directory, native.host.family)
    for source, target in (
        (tools.fourmolu, copied.fourmolu),
        (tools.hlint, copied.hlint),
    ):
        shutil.copy2(source, target)
    return copied


def test_tools_publish_together_and_keep_existing(
    haskell_build: build.BuildContext, tmp_path: Path
) -> None:
    """Only verified completed inputs publish, and an existing winner stays intact."""
    selected = pins()
    staged, destination = tmp_path / "staged", tmp_path / "published"
    copied = _copy_tools(haskell_build, staged)
    assert build.verify_style_tools(haskell_build, selected, staged) == Ok(copied)
    failed = Err(build.BuildError("owned installer failure"))
    assert (
        build.publish_style_tools(haskell_build, selected, staged, destination, failed)
        == failed
    )
    assert staged.is_dir()
    assert not destination.exists()
    assert build.publish_style_tools(
        haskell_build, selected, staged, destination, Ok(Output(0, "", ""))
    ) == Ok(style.paths(destination, haskell_build.host.family))
    assert not staged.exists()
    assert all(
        path.is_file()
        for path in (
            destination / copied.fourmolu.name,
            destination / copied.hlint.name,
        )
    )
    marker = destination / "winner"
    marker.write_text("original", encoding="utf-8")
    _copy_tools(haskell_build, staged)
    (staged / "winner").write_text("replacement", encoding="utf-8")
    assert isinstance(
        build.publish_style_tools(
            haskell_build, selected, staged, destination, Ok(Output(0, "", ""))
        ),
        Ok,
    )
    assert marker.read_text(encoding="utf-8") == "original"
    assert (staged / "winner").read_text(encoding="utf-8") == "replacement"
    assert isinstance(
        build.publish_style_tools(
            haskell_build,
            selected,
            staged,
            tmp_path / "absent-parent/tools",
            Ok(Output(0, "", "")),
        ),
        Err,
    )
    assert staged.is_dir()


def test_incomplete_or_wrong_version_tools_refused(
    haskell_build: build.BuildContext, tmp_path: Path
) -> None:
    """Real version answers are required; missing, damaged and mismatched tools fail."""
    selected = pins()
    staged = tmp_path / "staged"
    _copy_tools(haskell_build, staged)
    assert isinstance(
        build.verify_style_tools(haskell_build, selected, Path("relative")), Err
    )
    assert isinstance(
        build.verify_style_tools(
            haskell_build, replace(selected, fourmolu=Version((99, 1))), staged
        ),
        Err,
    )
    damaged = tmp_path / "damaged"
    damaged.mkdir()
    broken = style.paths(damaged, haskell_build.host.family)
    broken.fourmolu.write_bytes(b"invalid native executable")
    assert isinstance(build.verify_style_tools(haskell_build, selected, damaged), Err)
    assert isinstance(
        build.publish_style_tools(
            haskell_build,
            selected,
            damaged,
            tmp_path / "published",
            Ok(Output(0, "", "")),
        ),
        Err,
    )
    broken.fourmolu.unlink()
    assert isinstance(build.verify_style_tools(haskell_build, selected, damaged), Err)
    assert not (tmp_path / "published").exists()


def test_style_preparation_and_staging_failures(
    root: Path, tmp_path: Path, haskell_build: build.BuildContext
) -> None:
    """Every missing configuration, target, pin, record or staging directory refuses."""
    selected = pins()
    project = copy_project(root, tmp_path / "project")
    invalid = StyleStep("hlint", project.host, tmp_path / "missing", Ok(selected))
    assert isinstance(preparation(invalid), Err)
    assert run_step(invalid) == 1
    assert isinstance(
        preparation(
            StyleStep(
                "hlint",
                project.host,
                project.project,
                Err(PinError("owned pin refusal")),
            )
        ),
        Err,
    )
    host = context(tmp_path / "owned")
    assert isinstance(
        preparation(StyleStep("hlint", host, project.project, Ok(selected))), Err
    )
    assert toolchain.record(haskell_build.tools, host.cache) == Ok(haskell_build.tools)
    assert isinstance(
        preparation(StyleStep("hlint", host, project.project, Ok(selected))), Err
    )
    for directory in ("app", "src", "test"):
        shutil.rmtree(project.project / directory)
    assert isinstance(
        preparation(StyleStep("hlint", host, project.project, Ok(selected))), Err
    )
    missing = replace(haskell_build, project=tmp_path / "missing-project", host=host)
    assert isinstance(build.ensure_style_tools(missing, selected), Err)
    # An unavailable executable makes every potential installer harmless.
    cold = replace(
        haskell_build,
        host=host,
        tools=replace(haskell_build.tools, cabal=str(tmp_path / "absent-cabal")),
    )
    assert isinstance(build.ensure_style_tools(cold, selected), Err)
    index = host.cache / "cabal/packages/hackage.haskell.org/01-index.tar"
    index.parent.mkdir(parents=True, exist_ok=True)
    index.touch()
    (host.cache / "cabal/agentctl-index-state").write_text(
        "2026-10-31T00:00:00Z", encoding="utf-8"
    )
    (host.cache / "tools").write_text("not a directory", encoding="utf-8")
    assert isinstance(build.ensure_style_tools(cold, selected), Err)
