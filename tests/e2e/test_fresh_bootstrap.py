# Copyright (c) 2026 agentctl contributors.
"""Bootstrap assertions read the resulting files and run the resolved executables."""

import hashlib
import os
import shutil
from pathlib import Path

import pytest

from agentctl.bootstrap.pins import Version
from agentctl.hostfacts import architecture, numeric_version
from agentctl.process import run
from agentctl.result import Ok
from tests.harness.bootstrap import context, native_tools, observation, pins
from tests.harness.bootstrap_origin import entries

pytestmark = pytest.mark.evidence("real")


def test_ghcup_digest_matches_pin(tmp_path: Path) -> None:
    """Fresh installs match the pin; existing binaries preserve the observed bytes."""
    before = observation(tmp_path / "before")
    selected = pins()
    target = before.found if before.found is not None else before.configured
    assert target.is_file()
    if before.origin == "agentctl-installed" or before.found is None:
        family = before.family
        assert family in {"Linux", "Darwin", "Windows"}
        value = context(tmp_path / "version")
        machine = architecture(family, value.machine)
        expected = next(
            asset.sha256
            for asset in selected.assets
            if asset.family == family and asset.architecture == machine
        )
        assert hashlib.sha256(target.read_bytes()).hexdigest() == expected
    else:
        assert hashlib.sha256(target.read_bytes()).hexdigest() == before.sha256
        value = context(tmp_path / "version")
        copied = value.home / target.name
        shutil.copy2(target, copied)
        reported = numeric_version(str(copied), value)
        assert isinstance(reported, Version)
        assert reported >= Version((0, 1, 50, 2))
        if target != before.configured:
            assert before.configured.exists() == before.configured_existed


def test_no_default_links(tmp_path: Path) -> None:
    """A pristine observed prefix has no default; existing selections remain equal."""
    before = observation(tmp_path / "before")
    native = native_tools()
    assert Path(native.ghc).is_file()
    assert Path(native.cabal).is_file()
    if before.origin == "agentctl-installed":
        assert all(
            not (before.configured.parent / name).exists()
            for name in ("ghc", "cabal", "ghc.exe", "cabal.exe")
        )
    else:
        directories = tuple(
            dict.fromkeys(Path(path).parent for path, _value in before.defaults)
        )
        assert entries(directories) == dict(before.defaults)


def test_whereis_paths_report_pins(tmp_path: Path) -> None:
    """Each recorded resolution exists and answers the independent literal pin."""
    tools = native_tools()
    for executable, expected in ((tools.ghc, "9.12.4"), (tools.cabal, "3.16.1.0")):
        assert Path(executable).is_absolute()
        assert Path(executable).is_file()
        output = run(
            [executable, "--numeric-version"],
            cwd=tmp_path,
            env={**os.environ, "PATH": ""},
        )
        assert isinstance(output, Ok)
        assert output.value.code == 0, output.value.stderr
        assert output.value.stdout.strip() == expected
