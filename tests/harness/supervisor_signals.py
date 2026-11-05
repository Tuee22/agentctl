# Copyright (c) 2026 agentctl contributors.
"""Native stop requests with an automatic, private Windows console equivalent."""

import time
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from agentctl.bootstrap import build
from agentctl.process import Output
from agentctl.result import Ok
from tests.harness.launch import LaunchCase, NativePane, PaneProgram, native_pane
from tests.harness.nonce import fresh
from tests.harness.supervisor import (
    Controller,
    RunningSupervisor,
    StopKind,
    log_records,
    supervisor,
)
from tests.harness.terminal import await_exit
from tests.harness.tmux import object_value, private_mux


@dataclass(slots=True)
class ConsoleSupervisor:
    """One fixture-owned supervisor inside an isolated native Windows console."""

    case: LaunchCase
    prior_runs: frozenset[str]
    driver: NativePane
    kind: StopKind
    trigger: Path
    destination: Path
    output: Output | None = None

    def alive(self) -> bool:
        """Observe the private fixture's real pane without sending any input."""
        return not self.driver.dead()

    def request_stop(self, kind: StopKind) -> None:
        """Release the native fixture's preselected, bounded console event."""
        assert kind == self.kind
        assert self.alive()
        self.trigger.touch()

    def finish(self) -> Output:
        """Require the fixture's independently recorded child exit and identity."""
        if self.output is None:
            if self.alive():
                self.request_stop(self.kind)
            await_exit(self.driver)
            assert self.destination.exists(), self.driver.capture()
            record = object_value(self.destination.read_text(encoding="utf-8"))
            assert set(record) == {"nonce", "pid", "status"}
            assert record["nonce"] == self.case.nonce
            pid = record["pid"]
            assert isinstance(pid, int)
            assert not isinstance(pid, bool)
            assert pid > 0
            status = record["status"]
            assert isinstance(status, int)
            assert not isinstance(status, bool)
            self.output = Output(status, "", self.driver.capture())
        return self.output


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
    mux = case.mux
    fixture = build.binary(mux.context, "test:agentctl-core-test")
    core = build.binary(mux.context, "exe:agentctl-core")
    assert isinstance(fixture, Ok), fixture
    assert isinstance(core, Ok), core
    prior_runs = frozenset(str(record["run"]) for record in log_records(case))
    with private_mux(
        mux.context, mux.family, mux.run_directory, fresh(mux.nonce)
    ) as outer:
        trigger = outer.scope / "request-stop"
        destination = outer.scope / "controller-result.json"
        driver = native_pane(
            outer,
            "console-controller",
            PaneProgram(
                (
                    str(fixture.value),
                    "--console-fixture",
                    str(core.value),
                    kind,
                    str(trigger),
                    str(destination),
                ),
                case.folder,
                case.environment,
            ),
        )
        console = ConsoleSupervisor(
            case, prior_runs, driver, kind, trigger, destination
        )
        try:
            yield console
        finally:
            console.finish()
            case.records()
