# Copyright (c) 2026 agentctl contributors.
"""Actual native preflight dependencies and two-sided failure observations."""

import json
import os
import tomllib
from pathlib import Path

import pytest

from agentctl.bootstrap import build
from agentctl.check.lanes import HostFacts
from tests.harness.agents import preflight, preflight_scope
from tests.harness.host import observe_agents
from tests.harness.nonce import fresh
from tests.harness.tmux import object_value


@pytest.mark.evidence("observer")
def test_order_mux_then_agent_then_auth(
    haskell_build: build.BuildContext,
    tmp_path: Path,
    record_host: HostFacts,
) -> None:
    """No mux prevents auth; adding that mux starts exactly one real observer."""
    scope = preflight_scope(haskell_build, tmp_path, record_host.family, "claude")
    before = {path for path in tmp_path.rglob("*") if path.is_file()}
    absent = preflight(haskell_build, scope.agent, tmp_path, scope.environment)
    assert absent.code != 0
    assert not tuple(scope.records.glob("*.json")), "auth ran before multiplexer"
    assert {path for path in tmp_path.rglob("*") if path.is_file()} == before
    scope.add_multiplexer(record_host.family)
    ready = preflight(haskell_build, scope.agent, tmp_path, scope.environment)
    assert ready.code == 0, ready.stderr
    value = object_value(ready.stdout)
    assert value["state"] == "Ready"
    assert value["auth"] == "LoggedIn"
    assert Path(str(value["executable"])).resolve() == scope.executable.resolve()
    record = scope.record("preflight skipped auth status")
    assert record["argv"] == ["auth", "status"]
    assert Path(str(record["cwd"])).resolve() == tmp_path.resolve()
    after = {path for path in tmp_path.rglob("*") if path.is_file()}
    assert after - before == {
        scope.binaries / ("psmux.exe" if record_host.family == "Windows" else "tmux"),
        *scope.records.glob("*.json"),
    }


@pytest.mark.evidence("real")
def test_missing_agent_names_install_hint(
    root: Path,
    haskell_build: build.BuildContext,
    tmp_path: Path,
    record_host: HostFacts,
) -> None:
    """A missing executable prints its OS remedy beside a found-agent control."""
    scope = preflight_scope(haskell_build, tmp_path, record_host.family, "codex")
    scope.add_multiplexer(record_host.family)
    hidden = tmp_path / "hidden-agent"
    scope.executable.rename(hidden)
    answer = preflight(haskell_build, scope.agent, tmp_path, scope.environment)
    rows = tomllib.loads(
        (root / "tests/oracles/preflight.toml").read_text(encoding="utf-8")
    )["case"]
    expected = next(
        row["expected"]
        for row in rows
        if row["id"]
        == "preflight.warning." + record_host.family.lower() + ".codex.missing"
    )
    assert answer.code == expected["exit"]
    assert answer.stderr.splitlines() == expected["lines"]
    assert not tuple(scope.records.glob("*.json"))
    hidden.rename(scope.executable)
    found = preflight(haskell_build, scope.agent, tmp_path, scope.environment)
    assert found.code == 0, found.stderr
    assert scope.record("found agent was not probed")["argv"] == ["login", "status"]


@pytest.mark.evidence("real")
def test_agents_host_observes_native_tools(
    tmp_path: Path, record_host: HostFacts
) -> None:
    """An empty PATH is unmet while the real version probes carry this nonce."""
    nonce = fresh("agent-host")
    absent = tmp_path / "absent"
    assert not observe_agents(
        record_host.family, absent, nonce, {**os.environ, "PATH": ""}
    )
    negative: object = json.loads(
        (absent / "agents-host.json").read_text(encoding="utf-8")
    )
    assert isinstance(negative, dict)
    assert negative["nonce"] == nonce
    assert negative["met"] is False
    present = tmp_path / "present"
    assert observe_agents(record_host.family, present, nonce, os.environ)
    positive: object = json.loads(
        (present / "agents-host.json").read_text(encoding="utf-8")
    )
    assert isinstance(positive, dict)
    assert positive["nonce"] == nonce
    assert positive["met"] is True
    tools = positive["tools"]
    assert isinstance(tools, list)
    expected_agents = {"claude", "codex"}
    assert len(tools) == len(expected_agents)
    names: set[str] = set()
    for tool in tools:
        assert isinstance(tool, dict)
        agent = tool["agent"]
        assert isinstance(agent, str)
        names.add(agent)
        assert tool["met"] is True
        assert Path(tool["executable"]).is_absolute()
        assert tool["version"]
    assert names == expected_agents
