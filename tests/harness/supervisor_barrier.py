# Copyright (c) 2026 agentctl contributors.
"""Hold a real guard capture or refuse a literal at the controlled mux boundary."""

import json
import os
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal

from tests.harness.launch import LaunchCase, MuxObserver, observe_mux
from tests.harness.screens import normalized
from tests.harness.supervisor import (
    Controller,
    ScriptedTarget,
    log_records,
    received_bytes,
    scripted_target,
    wait_backoff,
    wait_frames,
    wait_records,
    wait_transition,
)
from tests.harness.tmux import PrivateMux, object_value

type BarrierMode = Literal["guard", "fail"]


@dataclass(frozen=True, slots=True)
class SupervisorBarrier:
    """A nonce-bound compiled relay which still forwards genuine native queries."""

    observer: MuxObserver
    directory: Path

    @property
    def case(self) -> LaunchCase:
        """Return the same actual caller with only its controlled relay configured."""
        return self.observer.case

    def arm(
        self, mode: BarrierMode, target: ScriptedTarget, generation: int = 0
    ) -> None:
        """Match only send proposals flushed after this explicit arming point."""
        log = Path(self.case.environment["AGENTCTL_STATE_DIR"]) / "supervisor.jsonl"
        descriptor = {
            "mode": mode,
            "target": target.target,
            "pane": target.pane,
            "offset": log.stat().st_size,
            "generation": generation,
        }
        pending = self.directory / "pending.json"
        handle = os.open(pending, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(descriptor, stream)
        pending.replace(self.directory / "arm.json")

    def wait(
        self, mode: BarrierMode, target: ScriptedTarget, generation: int = 0
    ) -> dict[str, object]:
        """Require the real client's identity and target before changing its pane."""
        path = self.directory / f"blocked-{generation}.json"
        deadline = time.monotonic() + 10
        while not path.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert path.exists(), (
            "native client never reached its send boundary",
            mode,
            generation,
            log_records(self.case)[-8:],
        )
        record = object_value(path.read_text(encoding="utf-8"))
        assert set(record) == {"nonce", "pid", "pane", "target", "mode"}
        assert record["nonce"] == self.case.nonce
        assert record["pane"] == target.pane
        assert record["target"] == target.target
        assert record["mode"] == mode
        pid = record["pid"]
        assert isinstance(pid, int)
        assert not isinstance(pid, bool)
        assert pid > 0
        self.case.mux.register_observer(pid)
        return record

    def release(self, generation: int) -> None:
        """Release only the selected owned native client's bounded hold."""
        (self.directory / f"release-{generation}").write_text(
            self.case.nonce, encoding="utf-8"
        )


def supervisor_barrier(case: LaunchCase) -> SupervisorBarrier:
    """Install the existing compiled fake relay into a disposable caller PATH."""
    observer = observe_mux(case)
    directory = observer.directory / "supervisor-barrier"
    directory.mkdir(mode=0o700)
    configured = replace(
        observer.case,
        environment={
            **observer.case.environment,
            "AGENTCTL_FAKE_SUPERVISOR_BARRIER": str(directory / "arm.json"),
        },
    )
    return SupervisorBarrier(replace(observer, case=configured), directory)


def wait_native_screen(target: ScriptedTarget, marker: str) -> str:
    """Require the real mux to have rendered a changed frame before guard release."""
    deadline = time.monotonic() + 10
    screen = ""
    while marker not in screen and time.monotonic() < deadline:
        captured = target.case.mux.raw("capture-pane", "-p", "-t", target.pane)
        assert captured.code == 0, captured
        screen = captured.stdout
        if marker not in screen:
            time.sleep(0.01)
    assert marker in screen, "native pane did not render its changed screen"
    return screen


@dataclass(frozen=True, slots=True)
class GuardedTarget:
    """Two text changes preserving the error, then an unsafe input prompt."""

    target: ScriptedTarget
    advances: tuple[Path, ...]
    markers: tuple[str, ...]


def guarded_target(
    root: Path, mux: PrivateMux, agent: str, trigger: Path
) -> GuardedTarget:
    """Derive controlled header changes from documented fixtures, never core output."""
    source = root / "tests/fixtures/screens" / agent
    overloaded = (source / "Overloaded/documented.txt").read_text(encoding="utf-8")
    advances = tuple(mux.scope / f"advance-{agent}-{index}" for index in range(3))
    markers = ("guard frame one", "guard frame two", "inspect src/")
    variants = []
    for marker in markers[:2]:
        path = mux.scope / (agent + "-" + marker.replace(" ", "-") + ".txt")
        path.write_text(marker + "\n" + overloaded, encoding="utf-8")
        variants.append(str(path))
    target = scripted_target(
        mux,
        root,
        agent,
        (
            ("IdlePrompt", {"kind": "file", "path": str(trigger)}),
            ("Overloaded", {"kind": "file", "path": str(advances[0])}),
            (variants[0], {"kind": "file", "path": str(advances[1])}),
            (variants[1], {"kind": "file", "path": str(advances[2])}),
            ("PartialInput", {"kind": "stay"}),
        ),
    )
    return GuardedTarget(target, advances, markers)


def drive_guard(
    running: Controller, barrier: SupervisorBarrier, guarded: GuardedTarget
) -> None:
    """Hold each native guard until its next frame is independently visible."""
    target = guarded.target
    previous = ""
    try:
        wait_backoff(running, target.target)
        wait_transition(running, target.target, "RECOVERY_SENT")
        for generation, (advance, marker) in enumerate(
            zip(guarded.advances, guarded.markers, strict=True)
        ):
            barrier.wait("guard", target, generation)
            if generation == 0:
                previous = wait_native_screen(target, "overloaded")
            advance.touch()
            wait_frames(
                target.case.records_directory, target.case.nonce, generation + 3
            )
            fresh = wait_native_screen(target, marker)
            assert normalized(fresh) != normalized(previous)
            assert (
                received_bytes(target.case.records_directory, target.case.nonce) == b""
            )
            barrier.release(generation)
            attempts = wait_records(running, target.target, "attempt", generation + 1)
            assert attempts[generation]["outcome"] == "aborted"
            if generation < len(guarded.advances) - 1:
                assert attempts[generation]["pre_send_class"] == "Overloaded"
                captured = [
                    row
                    for row in log_records(running.case)
                    if row["target"] == target.target
                    and row["kind"] == "observation"
                    and row["class"] == "Overloaded"
                ]
                assert captured
                assert {row["fingerprint"] for row in captured} == {
                    attempts[generation]["pre_send_fingerprint"]
                }
            previous = fresh
    finally:
        for generation in range(len(guarded.advances)):
            barrier.release(generation)
        barrier.observer.arguments()
