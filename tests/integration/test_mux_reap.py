# Copyright (c) 2026 agentctl contributors.
"""Native child notification is scoped by observed, validated process identity."""

import json
import time

import pytest

from agentctl.bootstrap import build
from agentctl.process import Output, alive
from agentctl.result import Ok
from tests.harness.launch import observe_mux, prepare
from tests.harness.tmux import PrivateMux

pytestmark = pytest.mark.evidence("observer")
WAIT_SECONDS = 10
INVALID_PIDS = ("", "0\n", "-1\n", "abc\n", "1 2\n", "2147483648\n")


def _request(mux: PrivateMux, environment: dict[str, str]) -> Output:
    """Invoke the production request with a controlled native client response."""
    result = build.execute_binary(
        mux.context,
        build.BinaryCall(
            "test:agentctl-core-test",
            ("--mux-fixture",),
            input_text=json.dumps(
                {"operation": "request-reap", "directory": str(mux.scope)}
            ),
            settings=tuple(environment.items()),
        ),
    )
    assert isinstance(result, Ok), result
    return result.value


def test_reap_request_validates_pid_before_notification(mux_server: PrivateMux) -> None:
    """Malformed identities cannot notify; a valid owned pid receives SIGCHLD."""
    actor = mux_server.actor("reap-observer", disposition="observe-reap")
    record = actor.record()
    pid = record["pid"]
    assert isinstance(pid, int)
    observer = observe_mux(prepare(mux_server, "claude"))
    marker = actor.record_directory / "reaped"
    for raw in INVALID_PIDS:
        output = _request(
            mux_server,
            {**observer.case.environment, "AGENTCTL_FAKE_MUX_PID_RESPONSE": raw},
        )
        if mux_server.family == "Windows":
            assert output.code == 0, output
        else:
            assert output.code != 0, "malformed server identity was accepted"
            assert "InvalidServerIdentity" in output.stdout, output
        assert not marker.exists(), "invalid identity sent child notification"
    positive = _request(
        mux_server,
        {**observer.case.environment, "AGENTCTL_FAKE_MUX_PID_RESPONSE": str(pid)},
    )
    assert positive.code == 0, positive
    assert json.loads(positive.stdout) == {"code": 0}
    family = mux_server.family
    assert family in {"Linux", "Darwin", "Windows"}
    assert alive(family, pid) == Ok(value=True)
    if family == "Windows":
        assert not marker.exists(), "psmux sent an unnecessary child notification"
    else:
        deadline = time.monotonic() + WAIT_SECONDS
        while not marker.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert marker.read_text(encoding="utf-8") == actor.nonce, (
            "valid owned pid did not receive child notification"
        )
    invocations = observer.arguments()
    assert ["-V"] in invocations, "native relay observer saw no version probe"
    queries = invocations.count(["list-sessions", "-F", "#{pid}"])
    assert queries == (0 if family == "Windows" else len(INVALID_PIDS) + 1)
