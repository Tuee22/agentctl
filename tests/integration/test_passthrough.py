# Copyright (c) 2026 agentctl contributors.
"""The native protocol and public transport share one declared command vocabulary."""

import json
import time
from pathlib import Path

import pytest

from agentctl.bootstrap import build
from agentctl.check.audit import read
from agentctl.cli import PASSTHROUGH
from agentctl.result import Ok
from tests.harness.launch import prepare
from tests.harness.passthrough import warm
from tests.harness.terminal import await_client, terminal
from tests.harness.tmux import PrivateMux


@pytest.mark.evidence("real")
def test_passthrough_table_equals_binary_commands(
    haskell_build: build.BuildContext,
) -> None:
    """Compare the actual handshake with Python's complete transport registry."""
    output = build.execute_binary(
        haskell_build, build.BinaryCall("exe:agentctl-core", ("--handshake",))
    )
    assert isinstance(output, Ok), output
    assert output.value.code == 0, output.value.stderr
    assert json.loads(output.value.stdout)["commands"] == list(PASSTHROUGH), (
        "passthrough command table differs"
    )


@pytest.mark.evidence("real")
def test_binary_refuses_direct_run(haskell_build: build.BuildContext) -> None:
    """Reject an absent handoff before dispatch beside the same authorized request."""
    refused = build.execute_binary(
        haskell_build,
        build.BinaryCall("exe:agentctl-core", ("--handshake",), protocol=None),
    )
    assert isinstance(refused, Ok), refused
    assert refused.value.code != 0, "binary ran without its handoff protocol"
    assert "Run agentctl" in refused.value.stderr
    assert "agentctl-core" not in refused.value.stderr
    positive = build.execute_binary(
        haskell_build, build.BinaryCall("exe:agentctl-core", ("--handshake",))
    )
    assert isinstance(positive, Ok), positive
    assert positive.value.code == 0
    assert json.loads(positive.value.stdout)["protocol"] == 1


@pytest.mark.evidence("real")
def test_usage_text_names_agentctl(haskell_build: build.BuildContext) -> None:
    """Require the real option parser to name only the public application."""
    output = build.execute_binary(
        haskell_build, build.BinaryCall("exe:agentctl-core", ("--unknown-option",))
    )
    assert isinstance(output, Ok), output
    assert output.value.code != 0
    assert "Usage: agentctl" in output.value.stderr, (
        "native usage did not name agentctl"
    )
    assert "agentctl-core" not in output.value.stderr, (
        "native usage did not name agentctl"
    )


@pytest.mark.evidence("observer")
def test_warm_passthrough_spawns_only_the_binary(
    mux_server: PrivateMux, tmp_path: Path
) -> None:
    """Observe the public handoff beside the absence of any Python build spawn."""
    caller = warm(prepare(mux_server, "claude"))
    log = tmp_path / "handoff.jsonl"
    reason = "warm handoff did not execute only its cached binary"
    with terminal(caller, ("claude",), audit=(log, caller.case.nonce)) as driver:
        deadline = time.monotonic() + 10
        while (
            (not log.exists() or log.stat().st_size == 0)
            and not driver.dead()
            and time.monotonic() < deadline
        ):
            time.sleep(0.01)
        assert log.is_file(), reason
        records = read(log, caller.case.nonce)
        assert isinstance(records, Ok), records
        assert len(records.value) == 1, reason
        observed = records.value[0]
        mux_server.register_observer(observed.pid)
        event = "subprocess.Popen" if mux_server.family == "Windows" else "os.exec"
        assert observed.event == event
        assert observed.argv == (str(caller.executable), "claude"), reason
        assert not observed.vetoed
        await_client(mux_server, driver, "api-claude")
        assert read(log, caller.case.nonce) == records, reason
