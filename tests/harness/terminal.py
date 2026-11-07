# Copyright (c) 2026 agentctl contributors.
"""Actual private multiplexer panes supply native PTYs to public application callers."""

import sys
import time
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from tests.harness.launch import NativePane, PaneProgram, native_pane
from tests.harness.nonce import fresh
from tests.harness.passthrough import WarmCaller
from tests.harness.tmux import PrivateMux, private_mux

WAIT_SECONDS = 10
CLIENT_FIELDS = 2
CALL = """import os, sys
os.environ.pop('TMUX', None)
os.environ.pop('TMUX_PANE', None)
from agentctl.cli import main
main(sys.argv[1:])
"""
AUDITED_CALL = """import os, sys
from pathlib import Path
os.environ.pop('TMUX', None)
os.environ.pop('TMUX_PANE', None)
from agentctl.check.audit import install
from agentctl.result import Ok
assert install(Path(sys.argv[1]), sys.argv[2]) == Ok(None)
from agentctl.cli import main
main(sys.argv[3:])
"""
ATTACH = """import os, sys
os.environ.pop('TMUX', None)
os.environ.pop('TMUX_PANE', None)
from agentctl.process import foreground
from agentctl.result import Ok
from pathlib import Path
result = foreground(sys.argv[1:], cwd=Path.cwd(), env=os.environ)
assert isinstance(result, Ok), result
raise SystemExit(result.value)
"""
SWITCH = """import sys, time
from pathlib import Path
while not Path(sys.argv[1]).exists():
    time.sleep(0.01)
from agentctl.cli import main
main(sys.argv[2:])
"""


def clients(mux: PrivateMux, session: str | None = None) -> tuple[tuple[int, str], ...]:
    """Read genuine attached client identities and sessions from this owned server."""
    target = ("-t", "=" + session) if session is not None else ()
    output = mux.raw("list-clients", *target, "-F", "#{client_pid}|#{session_name}")
    assert output.code == 0, output.stderr
    rows = []
    for line in output.stdout.splitlines():
        fields = line.split("|")
        assert len(fields) == CLIENT_FIELDS, line
        rows.append((int(fields[0]), fields[1]))
    return tuple(rows)


def await_client(
    mux: PrivateMux,
    driver: NativePane,
    session: str,
    *,
    reason: str = "terminal handover",
) -> tuple[int, str]:
    """Require one actual client on the target before the terminal deadline."""
    deadline = time.monotonic() + WAIT_SECONDS
    present = mux.raw("has-session", "-t", "=" + session)
    while present.code == 1 and time.monotonic() < deadline:
        time.sleep(0.01)
        present = mux.raw("has-session", "-t", "=" + session)
    assert present.code == 0, reason + ": no target session: " + driver.capture()
    observed = clients(mux, session)
    while (
        len(observed) != 1 or observed[0][1] != session
    ) and time.monotonic() < deadline:
        time.sleep(0.01)
        observed = clients(mux, session)
    assert len(observed) == 1, (
        reason + ": did not attach exactly one client: " + driver.capture()
    )
    assert observed[0][1] == session, reason + ": selected another session"
    return observed[0]


def await_exit(pane: NativePane) -> None:
    """Require a terminal driver to finish within the normal native-query deadline."""
    deadline = time.monotonic() + WAIT_SECONDS
    dead = pane.dead()
    while not dead and time.monotonic() < deadline:
        time.sleep(0.01)
        dead = pane.dead()
    assert dead, "terminal driver did not finish: " + pane.capture()


@contextmanager
def terminal(
    caller: WarmCaller,
    arguments: tuple[str, ...],
    *,
    audit: tuple[Path, str] | None = None,
) -> Generator[NativePane]:
    """Run the real public CLI inside a second private server's native terminal."""
    mux = caller.case.mux
    with private_mux(
        mux.context, mux.family, mux.run_directory, fresh(mux.nonce)
    ) as outer:
        program = CALL if audit is None else AUDITED_CALL
        tail = arguments if audit is None else (str(audit[0]), audit[1], *arguments)
        driver = native_pane(
            outer,
            "public-caller",
            PaneProgram(
                (sys.executable, "-c", program, *tail),
                caller.case.folder,
                caller.case.environment,
            ),
            binary=caller.executable,
        )
        try:
            yield driver
        finally:
            caller.case.records()


@contextmanager
def attached_seed(
    caller: WarmCaller, arguments: tuple[str, ...] | None = None
) -> Generator[tuple[NativePane, NativePane]]:
    """Attach one native client to a waiting in-server caller before releasing it."""
    mux = caller.case.mux
    release = caller.case.folder / "launch"
    seed = native_pane(
        mux,
        "seed",
        PaneProgram(
            (
                sys.executable,
                "-c",
                SWITCH,
                str(release),
                *((caller.case.agent,) if arguments is None else arguments),
            ),
            caller.case.folder,
            caller.case.environment,
        ),
        binary=caller.executable,
    )
    prefix = () if mux.family == "Windows" else ("-S", str(mux.endpoint))
    with private_mux(
        mux.context, mux.family, mux.run_directory, fresh(mux.nonce)
    ) as outer:
        driver = native_pane(
            outer,
            "outside-client",
            PaneProgram(
                (
                    sys.executable,
                    "-c",
                    ATTACH,
                    mux.executable,
                    *prefix,
                    "attach-session",
                    "-t",
                    "=seed",
                ),
                caller.case.folder,
                caller.case.environment,
            ),
            binary=caller.executable,
        )
        try:
            yield seed, driver
        finally:
            caller.case.records()
