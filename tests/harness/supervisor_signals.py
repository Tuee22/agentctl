# Copyright (c) 2026 agentctl contributors.
"""Native stop requests with an automatic, private Windows console equivalent."""

import time
from collections.abc import Generator
from contextlib import contextmanager

from agentctl.process import Output
from tests.harness.launch import LaunchCase
from tests.harness.supervisor import (
    ConsoleSupervisor,
    Controller,
    RunningSupervisor,
    StopKind,
    console_supervisor,
    supervisor,
)


def wait_stopped(running: Controller) -> Output:
    """Observe exit before cleanup can send a second signal or force termination."""
    deadline = time.monotonic() + 10
    while running.alive() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert not running.alive(), "supervisor ignored its native stop request"
    return running.finish()


@contextmanager
def signal_supervisor(
    case: LaunchCase, kind: StopKind
) -> Generator[RunningSupervisor | ConsoleSupervisor]:
    """Select the host's real stop mechanism and keep native evidence distinct."""
    if case.mux.family != "Windows":
        with supervisor(case) as running:
            yield running
        return
    with console_supervisor(case, kind) as running:
        yield running
