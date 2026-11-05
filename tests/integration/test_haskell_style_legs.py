# Copyright (c) 2026 agentctl contributors.
"""Real native style tools with two-sided check-mode and hint-failure controls."""

import json
import os
import shutil
import sys
import tomllib
from dataclasses import replace
from pathlib import Path
from typing import Literal

import pytest

from agentctl.bootstrap import build
from agentctl.bootstrap.style import directory
from agentctl.check import style
from agentctl.check.steps import run_tools
from agentctl.process import run
from agentctl.result import Ok
from tests.harness.bootstrap import pins
from tests.harness.haskell import copy_project
from tests.harness.nonce import fresh

type Event = tuple[tuple[str, ...], bool]


def _step(
    context: build.BuildContext, name: Literal["fourmolu", "hlint"]
) -> style.StyleStep:
    """Use the same supplied pins and project inputs as the actual gate pipeline."""
    return style.StyleStep(name, context.host, context.project, Ok(pins()))


@pytest.mark.evidence("real")
def test_fourmolu_fires(
    root: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The check leg rejects a formatting defect and never rewrites its source."""
    context = copy_project(root, tmp_path)
    step = _step(context, "fourmolu")
    assert run_tools(context.project, tmp_path, "focused", (step,)) == 0
    module = context.project / "src/AgentCtl/Protocol.hs"
    original = module.read_text(encoding="utf-8")
    assert original.count("protocolVersion = 1") == 1
    module.write_text(
        original.replace("protocolVersion = 1", "protocolVersion=1"), encoding="utf-8"
    )
    defective = module.read_bytes()
    assert style.run_step(step) != 0, "fourmolu accepted misformatted source"
    output = capsys.readouterr()
    assert "Protocol.hs" in output.out + output.err
    assert module.read_bytes() == defective, "fourmolu rewrote its check target"


@pytest.mark.evidence("real")
def test_hlint_fires(
    root: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A redundant bracket produces a real hint and nonzero status beside its twin."""
    context = copy_project(root, tmp_path)
    step = _step(context, "hlint")
    assert style.run_step(step) == 0
    module = context.project / "src/AgentCtl/Protocol.hs"
    module.write_text(
        module.read_text(encoding="utf-8").replace(
            "protocolVersion = 1", "protocolVersion = (1)"
        ),
        encoding="utf-8",
    )
    defective = module.read_bytes()
    assert style.run_step(step) != 0, "hlint accepted hinted source"
    output = capsys.readouterr()
    assert "Redundant bracket" in output.out + output.err
    assert "Protocol.hs" in output.out + output.err
    assert module.read_bytes() == defective


@pytest.mark.evidence("real")
def test_style_tools_report_pins(root: Path, haskell_build: build.BuildContext) -> None:
    """Absolute native pins still execute under a constructed PATH with no tools."""
    selected = pins()
    verified = build.verify_style_tools(
        haskell_build, selected, directory(haskell_build.host.cache, selected)
    )
    assert isinstance(verified, Ok), "pinned style tools were not resolved"
    inherited = dict(haskell_build.host.environment)
    inherited["PATH"] = ""
    context = replace(
        haskell_build,
        host=replace(haskell_build.host, environment=tuple(inherited.items())),
    )
    for path, expected in (
        (verified.value.fourmolu, "0.19.0.1"),
        (verified.value.hlint, "3.10"),
    ):
        assert path.is_absolute()
        answer = run(
            [str(path), "--version"],
            cwd=context.project,
            env=build.environment(context),
        )
        assert isinstance(answer, Ok)
        assert answer.value.code == 0
        assert expected in answer.value.stdout, (
            "native style tool answered the wrong pin"
        )
    for name in ("fourmolu", "hlint"):
        assert style.run_step(_step(context, name)) == 0, (
            "style leg resolved its tool from PATH"
        )
    defaults = run(
        [str(verified.value.fourmolu), "--print-defaults"],
        cwd=context.project,
        env=build.environment(context),
    )
    assert isinstance(defaults, Ok)
    assert defaults.value.code == 0
    rows = tomllib.loads(
        (root / "tests/oracles/style_tools.toml").read_text(encoding="utf-8")
    )["case"]
    expected_keys = next(
        row["expected"] for row in rows if row["id"] == "style.config.keys"
    )
    assert set(style.keys(defaults.value.stdout)) == set(expected_keys)


def _actor(
    root: Path, folder: Path, mode: str, native: build.BuildContext
) -> tuple[Event, ...]:
    """Observe genuine version calls while every install candidate remains harmless."""
    harmless = (
        Path(os.environ["SYSTEMROOT"]) / "System32/where.exe"
        if native.host.family == "Windows"
        else Path(shutil.which("false") or "/missing-false")
    )
    assert harmless.is_file()
    nonce = fresh(os.environ.get("AGENTCTL_CHECK_NONCE", "focused"))
    result = run(
        [
            sys.executable,
            str(root / "tests/fixtures/haskell/style_actor.py.txt"),
            mode,
            str(folder),
            str(native.project),
            str(native.host.cache),
            native.tools.ghc,
            str(harmless),
            nonce,
        ],
        cwd=root,
        env=os.environ,
    )
    assert isinstance(result, Ok)
    assert result.value.code == 0, result.value.stderr
    payload: object = json.loads(result.value.stdout)
    assert isinstance(payload, dict)
    assert payload["nonce"] == nonce
    records = payload["events"]
    assert isinstance(records, list)
    events: tuple[Event, ...] = ()
    for item in records:
        assert isinstance(item, dict)
        assert item["nonce"] == nonce
        argv, blocked = item["argv"], item["blocked"]
        assert isinstance(argv, list)
        assert all(isinstance(arg, str) for arg in argv)
        assert isinstance(blocked, bool)
        events += ((tuple(str(arg) for arg in argv), blocked),)
    assert events[0] == ((sys.executable, "-c", "print('observer control')"), False)
    return events[1:]


@pytest.mark.evidence("observer")
def test_tools_idempotent(
    root: Path, tmp_path: Path, haskell_build: build.BuildContext
) -> None:
    """A warm ensure invokes only both version queries and attempts no install."""
    records = _actor(root, tmp_path / "warm", "warm", haskell_build)
    assert tuple(argv[1:] for argv, _blocked in records) == (
        ("--version",),
        ("--version",),
    )
    suffix = ".exe" if haskell_build.host.family == "Windows" else ""
    assert tuple(Path(argv[0]).name for argv, _blocked in records) == (
        "fourmolu" + suffix,
        "hlint" + suffix,
    )
    assert all(
        not blocked
        and Path(argv[0]).is_file()
        and Path(argv[0]).is_relative_to(tmp_path / "warm/cache/tools")
        for argv, blocked in records
    )


@pytest.mark.evidence("observer")
def test_style_installer_and_leg_vetoes(
    root: Path, tmp_path: Path, haskell_build: build.BuildContext
) -> None:
    """A vetoed installer publishes nothing and a vetoed style leg fails the gate."""
    for mode in ("cold", "leg-veto"):
        records = _actor(root, tmp_path / mode, mode, haskell_build)
        assert records
        assert records[-1][1]
        if mode == "cold":
            assert "install" in records[-1][0]
        else:
            assert "--mode" in records[-1][0]
