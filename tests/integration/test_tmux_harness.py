# Copyright (c) 2026 agentctl contributors.
"""The only kill-server procedure refuses even another disposable test server."""

from pathlib import Path

import pytest

from tests.harness.nonce import fresh
from tests.harness.tmux import PrivateMux, private_mux, server_pid

pytestmark = pytest.mark.evidence("real")
RECORDED_PID = 123


def test_psmux_pid_record_shapes(tmp_path: Path) -> None:
    """Native PID and creation records parse; malformed identities cannot register."""
    path = tmp_path / "server.pid"
    for value in ("123", "123:456\n"):
        path.write_text(value, encoding="utf-8")
        assert server_pid(path) == RECORDED_PID
    for value in ("", "0:456", "-1:456", "123:", "123:bad", "123:456:789"):
        path.write_text(value, encoding="utf-8")
        with pytest.raises(AssertionError):
            server_pid(path)


def test_kill_server_refuses_foreign_socket(mux_server: PrivateMux) -> None:
    """A foreign test-owned endpoint survives refusal beside an owned kill."""
    with private_mux(
        mux_server.context,
        mux_server.family,
        mux_server.run_directory,
        fresh(mux_server.nonce),
    ) as other:
        if other.family == "Windows":
            other.actor("foreign-control").record()
            mux_server.actor("owned-control").record()
        rejected = False
        try:
            mux_server.kill_server(other.endpoint)
        except AssertionError:
            rejected = True
        assert rejected, "foreign socket was not refused"
        if other.server is not None:
            assert other.server.handle.poll() is None
        else:
            assert other.raw("has-session", "-t", "=foreign-control").code == 0
        killed = mux_server.kill_server()
        assert killed.code == 0, killed.stderr
