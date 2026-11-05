# Copyright (c) 2026 agentctl contributors.
"""Actual agent CLIs in empty, private configuration and credential directories."""

import os
import tomllib
from pathlib import Path

import pytest

from agentctl.bootstrap import build
from agentctl.check.lanes import HostFacts
from agentctl.process import run
from agentctl.result import Ok
from tests.harness.agents import AuthProbe, isolated_environment, native_agent, probe
from tests.harness.nonce import fresh

pytestmark = pytest.mark.evidence("real")
UNKNOWN_FLAG_EXIT = 2


def test_logged_out_by_construction(
    root: Path,
    haskell_build: build.BuildContext,
    tmp_path: Path,
    record_host: HostFacts,
) -> None:
    """Both real status commands exit one without reading a user's credentials."""
    rows = tomllib.loads(
        (root / "tests/oracles/auth_status.toml").read_text(encoding="utf-8")
    )["case"]
    for agent, arguments in (
        ("claude", ("auth", "status")),
        ("codex", ("login", "status")),
    ):
        environment = isolated_environment(tmp_path / agent, os.environ)
        executable = native_agent(agent, record_host.family, environment)
        observed = run(
            [str(executable), *arguments], cwd=tmp_path, env=environment, timeout=10
        )
        assert isinstance(observed, Ok), observed
        assert observed.value.code == 1, "isolated agent used credentials"
        answer = probe(
            haskell_build, AuthProbe(agent, executable, tmp_path), environment
        )
        assert answer["state"] == "LoggedOut"
        expected = next(
            row["expected"]
            for row in rows
            if row["id"] == "auth.warning." + agent + ".logged-out"
        )
        assert answer["warning"] == expected
        assert not (Path(environment["CODEX_HOME"]) / "auth.json").exists()
        assert not (
            Path(environment["CLAUDE_CONFIG_DIR"]) / ".credentials.json"
        ).exists()


def test_help_canaries_list_mandatory_flags(
    root: Path, tmp_path: Path, record_host: HostFacts
) -> None:
    """Real parsers recognise mandatory flags and see a fresh bogus-flag control."""
    rows = tomllib.loads(
        (root / "tests/oracles/launch_argv.toml").read_text(encoding="utf-8")
    )["case"]
    nonce = fresh("help-canary")
    bogus = "--agentctl-unknown-" + nonce
    for agent in ("claude", "codex"):
        environment = isolated_environment(tmp_path / agent, os.environ)
        executable = native_agent(agent, record_host.family, environment)
        flags = next(
            row["expected"]["mandatory_flags"]
            for row in rows
            if row["id"] == "agents." + agent
        )
        help_output = run(
            [str(executable), "--help"], cwd=tmp_path, env=environment, timeout=10
        )
        assert isinstance(help_output, Ok), help_output
        assert help_output.value.code == 0
        for flag in flags:
            assert flag in help_output.value.stdout, "mandatory flag absent from help"
            if agent == "codex":
                accepted = run(
                    [str(executable), flag, "--help"],
                    cwd=tmp_path,
                    env=environment,
                    timeout=10,
                )
                assert isinstance(accepted, Ok), accepted
                assert accepted.value.code == 0, "mandatory flag rejected by CLI"
        rejected = run(
            [str(executable), bogus, "--help"],
            cwd=tmp_path,
            env=environment,
            timeout=10,
        )
        assert isinstance(rejected, Ok), rejected
        if agent == "codex":
            assert rejected.value.code == UNKNOWN_FLAG_EXIT
            assert bogus in rejected.value.stderr
        else:
            assert rejected.value.code == 0
            assert bogus not in rejected.value.stdout
