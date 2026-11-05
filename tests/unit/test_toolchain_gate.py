# Copyright (c) 2026 agentctl contributors.
"""Native readiness boundaries, budget values and the introduced gate-step order."""

import shutil
from dataclasses import replace
from pathlib import Path
from typing import Never

import pytest

from agentctl.bootstrap.pins import PinError
from agentctl.bootstrap.toolchain import record
from agentctl.check.steps import pipeline, run_tools
from agentctl.check.toolchain import (
    EnsureStep,
    budgets,
    inspect_toolchain,
    reachable,
    readiness,
    run_step,
)
from agentctl.hostfacts import HostContext, HostFacts
from agentctl.result import Err, Ok
from tests.harness.bootstrap import context, native_tools, pins
from tests.harness.http import serve
from tests.harness.oracle import Object, Store, assert_oracle, read_homes
from tests.harness.oracle import load as oracle_load

CAPACITY_TOLERANCE = 64 * 1024 * 1024


@pytest.mark.evidence("value")
def test_storage_budget_values(root: Path) -> None:
    """Missing tools reserve independent literal budgets, combined on one volume."""
    store = oracle_load(root / "tests/oracles/toolchain_storage.toml", read_homes(root))
    assert isinstance(store, Store)
    seen: set[tuple[bool, bool, bool]] = set()
    for row in store.effective:
        assert isinstance(row.inputs, Object)
        fields = dict(row.inputs.items)
        ghc, cabal, shared = (
            fields[name] for name in ("ghc_ready", "cabal_ready", "shared")
        )
        assert isinstance(ghc, bool)
        assert isinstance(cabal, bool)
        assert isinstance(shared, bool)
        inputs = (ghc, cabal, shared)
        assert_oracle(
            lambda values: budgets(
                ghc_ready=values[0], cabal_ready=values[1], shared=values[2]
            ),
            inputs,
            row.expected,
            row_id="toolchain storage budget differs: " + row.identifier,
        )
        seen.add(inputs)
    assert seen == {
        (ghc, cabal, shared)
        for ghc in (False, True)
        for cabal in (False, True)
        for shared in (False, True)
    }


@pytest.mark.evidence("value")
def test_native_readiness_and_warm_network_absence(tmp_path: Path) -> None:
    """Capacity agrees with the filesystem and a warm host attempts no connection."""
    value = context(tmp_path)
    facts = HostFacts(
        "Linux", "x86_64", value.home / ".ghcup/bin/ghcup", None, None, None
    )
    calls: list[tuple[str, int]] = []

    def connect(host: str, port: int) -> bool:
        calls.append((host, port))
        return host == "downloads.haskell.org"

    cold = readiness(facts, value, connect)
    assert abs(cold.ghcup_free - shutil.disk_usage(tmp_path).free) < CAPACITY_TOLERANCE
    assert abs(cold.cache_free - shutil.disk_usage(tmp_path).free) < CAPACITY_TOLERANCE
    assert calls == [("downloads.haskell.org", 443), ("hackage.haskell.org", 443)]
    assert cold.downloads_reachable
    assert not cold.hackage_reachable
    calls.clear()
    native = native_tools()
    warm = readiness(replace(facts, ghc=native.ghc, cabal=native.cabal), value, connect)
    assert warm.ghcup_required == warm.cache_required == 0
    assert warm.downloads_reachable
    assert warm.hackage_reachable
    assert calls == []


@pytest.mark.evidence("value")
def test_readiness_failures_and_gate_step(tmp_path: Path) -> None:
    """Pin, host, storage and provisioning failures remain concrete failed steps."""
    value, selected, native = context(tmp_path), pins(), native_tools()
    invalid = Err(PinError("invalid pin fixture"))
    assert inspect_toolchain(value, invalid) == ("invalid pin fixture",)
    assert run_step(EnsureStep(value, invalid)) == 1
    assert (
        run_tools(tmp_path, tmp_path, "focused", (EnsureStep(value, invalid),)) == 1
    ), "toolchain-ensure was bypassed"
    unsupported = replace(value, family="unsupported")
    assert inspect_toolchain(unsupported, Ok(selected))
    assert run_step(EnsureStep(unsupported, Ok(selected))) == 1
    assert record(native, value.cache) == Ok(native)

    def unreadable(_facts: HostFacts, _context: HostContext) -> Never:
        message = "controlled storage read failure"
        raise OSError(message)

    assert inspect_toolchain(value, Ok(selected), unreadable) == (
        "P7: cannot inspect toolchain storage: controlled storage read failure",
    )
    assert inspect_toolchain(value, Ok(selected)) == ()
    assert run_step(EnsureStep(value, Ok(selected))) == 0
    assert (
        run_tools(tmp_path, tmp_path, "focused", (EnsureStep(value, Ok(selected)),))
        == 0
    )


@pytest.mark.evidence("value")
def test_pipeline_retains_python_legs_and_inserts_provisioning(tmp_path: Path) -> None:
    """Provisioning stays after ty and before the introduced pytest leg."""
    for family in ("Linux", "Darwin", "Windows"):
        steps = pipeline(tmp_path, tmp_path, ("file.py",), family, assume_yes=True)
        assert tuple(step.name for step in steps) == (
            "ruff-check",
            "ruff-format",
            "ty",
            "toolchain-ensure",
            "fourmolu",
            "hlint",
            "cabal-build",
            "binary-identity",
            "cabal-test",
            "pytest",
        )
        provision = steps[3]
        assert isinstance(provision, EnsureStep)
        assert provision.context.assume_yes
        assert not provision.context.interactive


@pytest.mark.evidence("real")
def test_reachability_opens_and_closes_owned_endpoints(tmp_path: Path) -> None:
    """An owned listener accepts a TCP probe; the closed endpoint refuses it."""
    with serve(tmp_path / "server", ()) as server:
        port = int(server.url.rsplit(":", 1)[1])
        assert reachable("127.0.0.1", port)
        assert server.requests == ()
    assert not reachable("127.0.0.1", port)
