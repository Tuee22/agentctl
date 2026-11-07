# Copyright (c) 2026 agentctl contributors.
"""Real core launches with disposable agents and an already owned native server."""

import json
import os
import shutil
import time
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path

from agentctl.bootstrap import build
from agentctl.process import Output, finish, stop
from agentctl.result import Ok
from tests.harness.agents import isolated_environment
from tests.harness.nonce import fresh
from tests.harness.tmux import PrivateMux, object_value, server_pid, validate_record

STARTUP_SECONDS = 2


@dataclass(frozen=True, slots=True)
class NativePane:
    """A real trampoline pane whose process and publication are independently owned."""

    mux: PrivateMux
    pane: str
    pid: int
    spec: Path
    published: float

    def dead(self) -> bool:
        """Read actual pane liveness through a native client on the private server."""
        output = self.mux.raw("display-message", "-p", "-t", self.pane, "#{pane_dead}")
        assert output.code == 0, output.stderr
        assert output.stdout.strip() in {"0", "1"}, output.stdout
        return output.stdout.strip() == "1"

    def observe_startup(self) -> bool:
        """Observe the same fixed window from the spec's atomic publication."""
        dead = self.dead()
        while not dead and time.monotonic() < self.published + STARTUP_SECONDS:
            time.sleep(0.01)
            dead = self.dead()
        assert not self.spec.exists(), "native pane did not consume the launch spec"
        return dead

    def capture(self) -> str:
        """Retain actual startup diagnostics without sending any pane input."""
        output = self.mux.raw("capture-pane", "-p", "-t", self.pane, "-S", "-100")
        assert output.code == 0, output.stderr
        return output.stdout


@dataclass(frozen=True, slots=True)
class PaneProgram:
    """Literal arguments and caller state for a native terminal fixture."""

    arguments: tuple[str, ...]
    folder: Path
    environment: Mapping[str, str] = field(repr=False)


def native_pane(
    mux: PrivateMux,
    session: str,
    program: PaneProgram,
    *,
    binary: Path | None = None,
) -> NativePane:
    """Start a waiting trampoline and publish only the test's supplied private spec."""
    owned = mux.scope / ("pane-" + fresh(mux.nonce).rsplit(".", maxsplit=1)[-1])
    owned.mkdir(mode=0o700)
    spec = owned / "spec.json"
    core = (
        build.binary(mux.context, "exe:agentctl-core") if binary is None else Ok(binary)
    )
    assert isinstance(core, Ok), core
    result = mux.raw(
        "new-session",
        "-d",
        "-s",
        session,
        "-P",
        "-F",
        "#{pane_id}",
        "--",
        str(core.value),
        "pane-exec",
        str(spec),
    )
    assert result.code == 0, result
    pane = result.stdout.strip()
    deadline = time.monotonic() + 10
    ready = mux.raw("has-session", "-t", "=" + session)
    while ready.code == 1 and time.monotonic() < deadline:
        time.sleep(0.01)
        ready = mux.raw("has-session", "-t", "=" + session)
    assert ready.code == 0, ready.stderr
    target = mux.pane_option_target(session, pane)
    pane = mux.pane_target(session, pane)
    held = mux.raw("set-option", "-p", "-t", target, "remain-on-exit", "on")
    assert held.code == 0, held.stderr
    identity = mux.raw("display-message", "-p", "-t", pane, "#{pane_pid}")
    assert identity.code == 0, identity.stderr
    pid = int(identity.stdout.strip())
    mux.register_observer(pid)
    if mux.family == "Windows":
        for path in mux.endpoint.glob("*.pid"):
            mux.register_observer(server_pid(path))
    pending = owned / "pending.json"
    descriptor = os.open(pending, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        json.dump(
            {
                "argv": program.arguments,
                "cwd": str(program.folder.resolve()),
                "env": dict(program.environment),
                "status": str(owned / "status.json"),
            },
            stream,
            ensure_ascii=False,
        )
    pending.rename(spec)
    return NativePane(mux, pane, pid, spec, time.monotonic())


@dataclass(frozen=True, slots=True)
class LaunchCase:
    """One caller environment and its independently written observer records."""

    mux: PrivateMux
    agent: str
    folder: Path
    records_directory: Path
    nonce: str
    environment: dict[str, str] = field(repr=False)

    def records(self) -> list[dict[str, object]]:
        """Validate every actual child record and register it for owned teardown."""
        observed = []
        for path in sorted(self.records_directory.glob("*.json")):
            record = object_value(path.read_text(encoding="utf-8"))
            validate_record(record, self.nonce)
            pid = record["pid"]
            assert isinstance(pid, int)
            self.mux.register_observer(pid, self.records_directory / "stop")
            observed.append(record)
        if self.mux.family == "Windows":
            for path in self.mux.endpoint.glob("*.pid"):
                self.mux.register_observer(server_pid(path))
        return observed

    def invoke(
        self,
        arguments: tuple[str, ...] = (),
        *,
        folder: Path | None = None,
        changes: Mapping[str, str] | None = None,
    ) -> Output:
        """Call the application-owned core boundary and reap its real process."""
        return self.command(self.agent, arguments, folder=folder, changes=changes)

    def command(
        self,
        command: str,
        arguments: tuple[str, ...] = (),
        *,
        folder: Path | None = None,
        changes: Mapping[str, str] | None = None,
    ) -> Output:
        """Run one real native handler against this case's private server and state."""
        child = build.start_binary(
            self.mux.context,
            build.BinaryCall(
                "exe:agentctl-core",
                (command, *arguments),
                settings=tuple({**self.environment, **(changes or {})}.items()),
            ),
            cwd=self.folder if folder is None else folder,
        )
        assert isinstance(child, Ok), child
        try:
            completed = finish(child.value, timeout=30)
            assert isinstance(completed, Ok), completed
            return completed.value
        finally:
            assert isinstance(stop(child.value), Ok)
            self.records()


@dataclass(frozen=True, slots=True)
class MuxObserver:
    """The compiled observer records a client invocation before forwarding it."""

    case: LaunchCase
    directory: Path

    def arguments(self) -> list[list[str]]:
        """Validate and register every client's nonce-bound native invocation."""
        invocations = []
        for path in sorted(self.directory.glob("*.json")):
            record = object_value(path.read_text(encoding="utf-8"))
            validate_record(record, self.case.nonce)
            pid = record["pid"]
            assert isinstance(pid, int)
            self.case.mux.register_observer(pid)
            arguments = record["argv"]
            assert isinstance(arguments, list)
            assert all(isinstance(argument, str) for argument in arguments)
            invocations.append([str(argument) for argument in arguments])
        return invocations

    def creates(self) -> list[list[str]]:
        """Select genuine create calls from the complete invocation records."""
        return [argv for argv in self.arguments() if argv[:1] == ["new-session"]]


def observe_mux(case: LaunchCase) -> MuxObserver:
    """Relay the controlled caller's clients to a copied genuine native backend."""
    binaries = Path(case.environment["PATH"])
    directory = binaries.parent / "mux-records"
    directory.mkdir(mode=0o700)
    backend = binaries.parent / "backend"
    backend.mkdir(mode=0o700)
    name = "psmux.exe" if case.mux.family == "Windows" else "tmux"
    relay_bin = binaries.parent / "relay-bin"
    relay_bin.mkdir(mode=0o700)
    for path in binaries.iterdir():
        if path.name != name:
            shutil.copy2(path, relay_bin / path.name)
    real = backend / name
    shutil.copy2(case.mux.executable, real)
    fake = build.binary(case.mux.context, "exe:agentctl-fake-agent")
    assert isinstance(fake, Ok), fake
    pending = directory / ("observer-" + name)
    shutil.copy2(fake.value, pending)
    pending.replace(relay_bin / name)
    environment = {
        **case.environment,
        "PATH": str(relay_bin),
        "AGENTCTL_FAKE_MUX_EXECUTABLE": str(real),
        "AGENTCTL_FAKE_MUX_RECORD_DIR": str(directory),
    }
    return MuxObserver(replace(case, environment=environment), directory)


def prepare(mux: PrivateMux, agent: str, *, disposition: str = "stay") -> LaunchCase:
    """Use copied native executables so PATH contains only these controlled tools."""
    nonce = fresh(mux.nonce)
    directory = mux.scope / ("launch-" + nonce.rsplit(".", maxsplit=1)[-1])
    directory.mkdir(mode=0o700)
    binaries = directory / "bin"
    binaries.mkdir(mode=0o700)
    records = directory / "records"
    records.mkdir(mode=0o700)
    folder = directory / "api"
    folder.mkdir()
    fake = build.binary(mux.context, "exe:agentctl-fake-agent")
    assert isinstance(fake, Ok), fake
    suffix = ".exe" if mux.family == "Windows" else ""
    shutil.copy2(fake.value, binaries / (agent + suffix))
    shutil.copy2(mux.executable, binaries / ("psmux.exe" if suffix else "tmux"))
    environment = {
        **isolated_environment(directory / "isolation", mux.environment),
        "PATH": str(binaries),
        "TMUX_TMPDIR": str(mux.scope),
        "PSMUX_DATA_DIR": str(mux.endpoint),
        "AGENTCTL_CACHE_DIR": str(directory / "cache"),
        "AGENTCTL_DATA_DIR": str(directory / "data"),
        "AGENTCTL_STATE_DIR": str(directory / "state"),
        "AGENTCTL_DISTRIBUTION": "ubuntu",
        "AGENTCTL_FAKE_NONCE": nonce,
        "AGENTCTL_FAKE_RECORD_DIR": str(records),
        "AGENTCTL_FAKE_AUTH_EXIT": "0",
        "AGENTCTL_FAKE_EXIT": disposition,
        "CALLER_ONLY": "caller-literal",
        "PATHEXT": os.pathsep.join((".EXE", ".CMD", ".BAT")),
    }
    return LaunchCase(mux, agent, folder, records, nonce, environment)
