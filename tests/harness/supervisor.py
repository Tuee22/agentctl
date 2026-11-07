# Copyright (c) 2026 agentctl contributors.
"""Read complete nonce-bound fake-agent events without hiding malformed records."""

import json
import signal
import time
import tomllib
from collections.abc import Generator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal, Protocol

from agentctl.bootstrap import build
from agentctl.process import Child, Output, finish, stop
from agentctl.result import Ok
from tests.harness.launch import (
    LaunchCase,
    NativePane,
    PaneProgram,
    native_pane,
    prepare,
)
from tests.harness.nonce import fresh
from tests.harness.oracle import Store, load, read_homes
from tests.harness.sessions import rows
from tests.harness.terminal import await_exit
from tests.harness.tmux import PrivateMux, object_value, private_mux

BYTE_MAXIMUM = 255
StopKind = Literal["interrupt", "terminate"]


class Controller(Protocol):
    """The observed lifecycle shared by pipe and private-console controllers."""

    case: LaunchCase
    prior_runs: frozenset[str]

    def alive(self) -> bool:
        """Read the owned process or private terminal's native liveness."""
        ...

    def finish(self) -> Output:
        """Reap the owned controller, preserving its actual exit status."""
        ...


@dataclass(frozen=True, slots=True)
class ScriptedTarget:
    """One real managed fake pane with an independent launch and receipt identity."""

    case: LaunchCase
    target: str
    pane: str
    recovery: bytes


def recovery_bytes(root: Path, family: str, agent: str) -> bytes:
    """Read the independent command oracle rather than importing the agent table."""
    path = root / "tests/oracles/forbidden_actions.toml"
    store = load(path, read_homes(root))
    assert isinstance(store, Store), store
    effective = {row.identifier for row in store.effective}
    row = next(
        row
        for row in tomllib.loads(path.read_text(encoding="utf-8"))["case"]
        if row["id"] in effective
        and row["input"]["subject"] == "command-plan"
        and row["input"]["family"] == family
        and row["input"]["agent"] == agent
        and row["input"]["action"] == "send"
    )
    text = row["expected"][0][-1]
    assert isinstance(text, str)
    return text.encode("utf-8") + b"\r"


def scripted_target(
    mux: PrivateMux,
    root: Path,
    agent: str,
    frames: tuple[tuple[str, Mapping[str, object]], ...],
) -> ScriptedTarget:
    """Publish fixture paths and explicit advance directives before a native launch."""
    case = prepare(mux, agent, disposition="scripted")
    script = case.folder.parent / "script.json"
    script.write_text(
        json.dumps(
            {
                "frames": [
                    {
                        "screen": str(
                            root
                            / "tests/fixtures/screens"
                            / agent
                            / (
                                category
                                if category.endswith(".txt")
                                else category + "/documented.txt"
                            )
                        ),
                        "after": after,
                    }
                    for category, after in frames
                ]
            }
        ),
        encoding="utf-8",
    )
    assert case.invoke(("--agentctl-script", str(script))).code == 0
    wait_frames(case.records_directory, case.nonce, 1)
    matches = [
        record
        for record in rows(case.command("list")).values()
        if record["FOLDER"] == str(case.folder.resolve()) and record["AGENT"] == agent
    ]
    assert len(matches) == 1
    target = matches[0]
    launch = [record for record in case.records() if record["pane"] == target["PANE"]]
    assert len(launch) == 1
    assert launch[0]["session"] == target["NAME"]
    return ScriptedTarget(
        case, target["NAME"], target["PANE"], recovery_bytes(root, mux.family, agent)
    )


@dataclass(slots=True)
class RunningSupervisor:
    """An application-owned foreground child with bounded, explicit teardown."""

    child: Child
    case: LaunchCase
    prior_runs: frozenset[str]
    output: Output | None = None

    @property
    def pid(self) -> int:
        """Expose the same owned controller identity observed in its lock."""
        return self.child.pid

    def alive(self) -> bool:
        """Poll the same owned child whose lock and log are observed."""
        return self.child.handle.poll() is None

    def request_stop(self, kind: StopKind) -> None:
        """Send a native POSIX stop request only to this owned live child."""
        assert self.case.mux.family != "Windows"
        assert self.alive()
        self.child.handle.send_signal(
            signal.SIGINT if kind == "interrupt" else signal.SIGTERM
        )

    def finish(self) -> Output:
        """Reap the same owned child once, retaining its actual status and streams."""
        if self.output is None:
            try:
                if self.alive():
                    self.request_stop("terminate")
                result = finish(self.child, timeout=10)
                assert isinstance(result, Ok), result
                self.output = result.value
            finally:
                if self.output is None:
                    assert isinstance(stop(self.child), Ok)
        return self.output


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

    @property
    def pid(self) -> int:
        """Read the fixture's independently observed live controller-lock identity."""
        path = Path(str(self.destination) + ".pid")
        record = object_value(path.read_text(encoding="utf-8"))
        assert set(record) == {"nonce", "pid"}
        assert record["nonce"] == self.case.nonce
        value = record["pid"]
        assert isinstance(value, int)
        assert not isinstance(value, bool)
        assert value > 0
        return value

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
            assert set(record) == {"nonce", "pid", "status", "stdout", "stderr"}
            assert record["nonce"] == self.case.nonce
            pid = record["pid"]
            assert isinstance(pid, int)
            assert not isinstance(pid, bool)
            assert pid > 0
            assert pid == self.pid
            status = record["status"]
            assert isinstance(status, int)
            assert not isinstance(status, bool)
            stdout, stderr = record["stdout"], record["stderr"]
            assert isinstance(stdout, str)
            assert isinstance(stderr, str)
            self.output = Output(status, stdout, stderr)
        return self.output


@contextmanager
def console_supervisor(
    case: LaunchCase,
    kind: StopKind,
    *,
    initial: float = 0.3,
    poll: float = 0.05,
) -> Generator[ConsoleSupervisor]:
    """Own a native console so cleanup requests a graceful controller stop."""
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
                    str(poll),
                    str(initial),
                    str(initial * 4),
                    case.nonce,
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


@contextmanager
def supervisor(
    case: LaunchCase,
    *,
    initial: float = 0.3,
    poll: float = 0.05,
) -> Generator[RunningSupervisor | ConsoleSupervisor]:
    """Use only supported timing flags, and never leave a controller behind."""
    if case.mux.family == "Windows":
        with console_supervisor(
            case, "terminate", initial=initial, poll=poll
        ) as running:
            yield running
        return
    previous = log_records(case)
    prior_runs = frozenset(str(record["run"]) for record in previous)
    started = build.start_binary(
        case.mux.context,
        build.BinaryCall(
            "exe:agentctl-core",
            (
                "supervisor",
                "run",
                "--poll-seconds",
                str(poll),
                "--initial-delay-seconds",
                str(initial),
                "--max-delay-seconds",
                str(initial * 4),
                "--jitter-fraction",
                "0",
            ),
            settings=tuple(case.environment.items()),
        ),
        cwd=case.folder,
    )
    assert isinstance(started, Ok), started
    running = RunningSupervisor(started.value, case, prior_runs)
    try:
        yield running
    finally:
        running.finish()
        assert running.child.handle.poll() is not None
        case.records()


def log_records(case: LaunchCase) -> tuple[dict[str, object], ...]:
    """Read only complete records from this caller's actual handed-off state path."""
    path = Path(case.environment["AGENTCTL_STATE_DIR"]) / "supervisor.jsonl"
    if not path.exists():
        return ()
    return tuple(
        object_value(line)
        for line in path.read_text(encoding="utf-8").splitlines(keepends=True)
        if line.endswith("\n")
    )


def utc_time(value: object) -> datetime:
    """Require a real UTC timestamp from the independent JSON boundary."""
    assert isinstance(value, str)
    parsed = datetime.fromisoformat(value)
    assert parsed.tzinfo is not None
    assert parsed.utcoffset() == timedelta()
    return parsed


def wait_records(
    running: Controller,
    target: str,
    kind: Literal["observation", "decision", "attempt", "result", "notify"],
    count: int = 1,
) -> tuple[dict[str, object], ...]:
    """Require a specified number of actual target records with a live controller."""
    deadline = time.monotonic() + 10
    selected = tuple(
        record
        for record in log_records(running.case)
        if record["kind"] == kind
        and record["target"] == target
        and record["run"] not in running.prior_runs
    )
    while len(selected) < count and time.monotonic() < deadline:
        assert running.alive(), running.finish()
        time.sleep(0.01)
        selected = tuple(
            record
            for record in log_records(running.case)
            if record["kind"] == kind
            and record["target"] == target
            and record["run"] not in running.prior_runs
        )
    assert len(selected) >= count, (
        "controller omitted required target records",
        target,
        kind,
        log_records(running.case)[-20:],
    )
    return selected


def wait_observation(
    running: Controller, target: str, category: str
) -> tuple[dict[str, object], ...]:
    """Require a current target-matched capture while the actual controller lives."""
    deadline = time.monotonic() + 10
    records = tuple(
        record
        for record in log_records(running.case)
        if record["run"] not in running.prior_runs
    )
    while (
        not any(
            record["kind"] == "observation"
            and record["target"] == target
            and record["class"] == category
            for record in records
        )
        and time.monotonic() < deadline
    ):
        assert running.alive(), running.finish()
        time.sleep(0.01)
        records = tuple(
            record
            for record in log_records(running.case)
            if record["run"] not in running.prior_runs
        )
    assert any(
        record["kind"] == "observation"
        and record["target"] == target
        and record["class"] == category
        for record in records
    ), "controller did not observe the scripted target"
    return records


def wait_transition(running: Controller, target: str, mode: str) -> None:
    """Bound each native state advance rather than the whole multi-poll scenario."""
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if any(
            record["kind"] == "decision"
            and record["target"] == target
            and record["run"] not in running.prior_runs
            and record["to"] == mode
            for record in log_records(running.case)
        ):
            return
        assert running.alive(), running.finish()
        time.sleep(0.01)
    details = ("controller did not advance", target, mode)
    raise AssertionError((details, log_records(running.case)[-20:]))


def wait_backoff(running: Controller, target: str) -> None:
    """Require all three pre-send advances, each bounded by a native poll deadline."""
    for mode in ("SUSPECTED_FAILURE", "CONFIRM_IDLE", "BACKOFF"):
        wait_transition(running, target, mode)


def observe_polls(running: Controller, target: str, count: int) -> None:
    """Require each additional native poll within its own observation deadline."""
    previous = len(wait_records(running, target, "observation"))
    for additional in range(1, count + 1):
        wait_records(running, target, "observation", previous + additional)


def timestamp(record: dict[str, object]) -> int:
    """Parse a fake event's native monotonic clock value."""
    value = record["monotonic_ns"]
    assert isinstance(value, int)
    assert not isinstance(value, bool)
    return value


def events(path: Path, nonce: str) -> tuple[dict[str, object], ...]:
    """Ignore only an in-flight unterminated suffix; validate each complete event."""
    if not path.exists():
        return ()
    records = tuple(
        object_value(line)
        for line in path.read_text(encoding="utf-8").splitlines(keepends=True)
        if line.endswith("\n")
    )
    previous = 0
    for record in records:
        assert record["nonce"] == nonce
        pid = record["pid"]
        stamp = timestamp(record)
        assert isinstance(pid, int)
        assert not isinstance(pid, bool)
        assert pid > 0
        assert stamp >= previous
        previous = stamp
    return records


def wait_frames(
    directory: Path, nonce: str, count: int
) -> tuple[dict[str, object], ...]:
    """Require every frame through an index rather than accepting a stale screen."""
    deadline = time.monotonic() + 10
    records = events(directory / "frames.jsonl", nonce)
    while len(records) < count and time.monotonic() < deadline:
        time.sleep(0.01)
        records = events(directory / "frames.jsonl", nonce)
    assert len(records) >= count, "scripted fake agent did not render its frame"
    assert [record["index"] for record in records] == list(range(len(records)))
    return records


def received_bytes(directory: Path, nonce: str) -> bytes:
    """Join every observed byte and check the independently recorded total."""
    values: list[int] = []
    for record in events(directory / "received.jsonl", nonce):
        chunk = record["bytes"]
        assert isinstance(chunk, list)
        for value in chunk:
            assert isinstance(value, int)
            assert not isinstance(value, bool)
            assert 0 <= value <= BYTE_MAXIMUM
            values.append(value)
        assert record["total"] == len(values)
    return bytes(values)


def wait_received(directory: Path, nonce: str, expected: bytes) -> None:
    """Require a partial literal to reach the observer before sending Enter."""
    deadline = time.monotonic() + 10
    actual = received_bytes(directory, nonce)
    while len(actual) < len(expected) and time.monotonic() < deadline:
        time.sleep(0.01)
        actual = received_bytes(directory, nonce)
    assert actual == expected, "scripted fake agent did not record every received byte"
