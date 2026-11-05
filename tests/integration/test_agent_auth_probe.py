# Copyright (c) 2026 agentctl contributors.
"""Native auth probes observed by a fresh nonce-bound fake agent."""

import os
import shutil
import tomllib
from pathlib import Path

import pytest

from agentctl.bootstrap import build
from agentctl.check.lanes import HostFacts
from agentctl.result import Ok
from tests.harness.agents import (
    AuthProbe,
    isolated_environment,
    preflight,
    preflight_scope,
    probe,
)
from tests.harness.nonce import fresh
from tests.harness.tmux import object_value, validate_record

pytestmark = pytest.mark.evidence("observer")


def test_probe_sees_caller_environment(
    haskell_build: build.BuildContext,
    tmp_path: Path,
    record_host: HostFacts,
) -> None:
    """The real caller environment reaches both exact status argv and the observer."""
    located = build.binary(haskell_build, "exe:agentctl-fake-agent")
    assert isinstance(located, Ok), located
    for agent, arguments in (
        ("claude", ["auth", "status"]),
        ("codex", ["login", "status"]),
    ):
        scope = tmp_path / agent
        environment = isolated_environment(scope, os.environ)
        nonce = fresh("auth-probe")
        records = scope / "records"
        records.mkdir(mode=0o700)
        environment.update(
            {
                "AGENTCTL_FAKE_NONCE": nonce,
                "AGENTCTL_FAKE_RECORD_DIR": str(records),
                "AGENTCTL_FAKE_EXIT": "1",
                "PROBE_ONLY": "private-probe-value",
            }
        )
        binaries = scope / "bin with spaces"
        binaries.mkdir()
        executable = binaries / (
            agent + (".exe" if record_host.family == "Windows" else "")
        )
        shutil.copy2(located.value, executable)
        answer = probe(haskell_build, AuthProbe(agent, executable, scope), environment)
        assert answer["state"] == "LoggedOut", answer
        files = tuple(records.glob("*.json"))
        assert len(files) == 1, "auth probe dropped caller environment"
        raw = files[0].read_text(encoding="utf-8")
        record = object_value(raw)
        validate_record(record, nonce)
        assert record["argv"] == arguments, "auth probe ran an unexpected command"
        assert Path(str(record["cwd"])).resolve() == scope.resolve()
        keys = record["env_keys"]
        assert isinstance(keys, list)
        assert {"PROBE_ONLY", "CLAUDE_CONFIG_DIR", "CODEX_HOME"} <= set(keys), (
            "auth probe dropped caller environment"
        )
        assert "private-probe-value" not in raw
        assert record["pane"] is None
        assert record["session"] is None


def test_preflight_never_runs_login(
    root: Path,
    haskell_build: build.BuildContext,
    tmp_path: Path,
    record_host: HostFacts,
) -> None:
    """A real preflight invokes only status and prints the logged-out remedy."""
    rows = tomllib.loads(
        (root / "tests/oracles/auth_status.toml").read_text(encoding="utf-8")
    )["case"]
    for agent, arguments in (
        ("claude", ["auth", "status"]),
        ("codex", ["login", "status"]),
    ):
        scope = preflight_scope(
            haskell_build, tmp_path / agent, record_host.family, agent, status="1"
        )
        scope.add_multiplexer(record_host.family)
        answer = preflight(haskell_build, agent, scope.directory, scope.environment)
        expected = next(
            row["expected"]
            for row in rows
            if row["id"] == "auth.warning." + agent + ".logged-out"
        )
        assert answer.code == expected["exit"]
        assert answer.stderr.splitlines() == expected["lines"]
        assert (
            scope.record("preflight did not run its status probe")["argv"] == arguments
        )
        assert not list(scope.directory.rglob("*.status.json"))
