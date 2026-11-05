# Copyright (c) 2026 agentctl contributors.
"""Real multiplexer servers, endpoints and fake-agent actors owned by one scope."""

import json
import os
import secrets
import shutil
import time
from collections.abc import Generator, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from agentctl.bootstrap import build
from agentctl.check.lanes import HostFacts
from agentctl.process import Child, Output, alive, run, start, stop
from agentctl.result import Ok
from tests.harness.nonce import fresh

WAIT_SECONDS = 10
POLL_SECONDS = 0.01
SOCKET_BYTES = 100
EXIT_FIELDS = 3


def object_value(text: str) -> dict[str, object]:
    """Require a real JSON object rather than treating malformed output as absent."""
    value: object = json.loads(text)
    assert isinstance(value, dict), text
    return {str(key): item for key, item in value.items()}


def validate_record(value: dict[str, object], nonce: str) -> None:
    """Reject missing or replayed observer identity beside a positive pid."""
    assert value.get("nonce") == nonce, "fake record dropped nonce"
    pid = value.get("pid")
    assert isinstance(pid, int)
    assert not isinstance(pid, bool)
    assert pid > 0
    assert isinstance(value.get("argv"), list)
    assert isinstance(value.get("env_keys"), list)


@dataclass(frozen=True, slots=True)
class Actor:
    """Paths and native target of one controlled fake agent."""

    session: str
    pane: str
    nonce: str
    record_directory: Path
    spec: Path
    status: Path
    folder: Path
    arguments: tuple[str, ...]
    environment: dict[str, str]

    def record(self) -> dict[str, object]:
        """Wait for the atomic observer file and validate its fresh identity."""
        deadline = time.monotonic() + WAIT_SECONDS
        files = tuple(self.record_directory.glob("*.json"))
        while not files and time.monotonic() < deadline:
            time.sleep(POLL_SECONDS)
            files = tuple(self.record_directory.glob("*.json"))
        assert len(files) == 1, "fake agent did not produce exactly one record"
        value = object_value(files[0].read_text(encoding="utf-8"))
        validate_record(value, self.nonce)
        return value


@dataclass(slots=True)
class PrivateMux:
    """One native backend with no route to a user's endpoint or configuration."""

    context: build.BuildContext
    family: str
    run_directory: Path
    nonce: str
    scope: Path
    environment: dict[str, str]
    executable: str
    endpoint: Path
    server: Child | None = None
    actors: list[Actor] = field(default_factory=list)
    registered: set[int] = field(default_factory=set)
    releases: dict[int, Path] = field(default_factory=dict)

    def open(self) -> None:
        """Own a foreground tmux server; psmux creates its per-session servers."""
        if self.family == "Windows":
            self.endpoint.mkdir(mode=0o700, exist_ok=True)
        else:
            assert len(str(self.endpoint).encode("utf-8")) <= SOCKET_BYTES
            created = start(
                [self.executable, "-D", "-f", os.devnull],
                cwd=self.scope,
                env=self.environment,
            )
            assert isinstance(created, Ok), created
            self.server = created.value
            self._register(self.server.pid)
            deadline = time.monotonic() + WAIT_SECONDS
            while not self.endpoint.is_socket() and time.monotonic() < deadline:
                assert self.server.handle.poll() is None, "private server exited"
                time.sleep(POLL_SECONDS)
            assert self.endpoint.is_socket(), "private server never became ready"

    def _register(self, pid: int) -> None:
        """Put native server identity in the gate's own observer registry."""
        observers = self.run_directory / "observers"
        observers.mkdir(exist_ok=True)
        (observers / f"{self.nonce}.{pid}.json").write_text(
            json.dumps({"nonce": self.nonce, "pid": pid}), encoding="utf-8"
        )
        self.registered.add(pid)

    def register_observer(self, pid: int, release: Path | None = None) -> None:
        """Own an independently observed native pid until this server is reaped."""
        self._register(pid)
        if release is not None:
            assert release.resolve().is_relative_to(self.scope.resolve())
            self.releases[pid] = release

    def raw(self, *arguments: str, endpoint: Path | None = None) -> Output:
        """Use an independent native client only against the specified test scope."""
        selected = self.endpoint if endpoint is None else endpoint
        if "kill-server" in arguments:
            assert selected.resolve().is_relative_to(self.scope.resolve()), (
                "foreign server endpoint refused"
            )
        environment = dict(self.environment)
        prefix = []
        if self.family == "Windows":
            environment["PSMUX_DATA_DIR"] = str(selected)
        else:
            prefix = ["-S", str(selected)]
        result = run(
            [self.executable, *prefix, *arguments],
            cwd=self.scope,
            env=environment,
            timeout=WAIT_SECONDS,
        )
        assert isinstance(result, Ok), result
        return result.value

    def command(
        self, action: str, *, directory: Path | None = None, **fields: object
    ) -> dict[str, object]:
        """Exercise both the value renderer and the actual Haskell interpreter."""
        request = {"family": self.family, "action": action, **fields}
        rendered = build.execute_binary(
            self.context,
            build.BinaryCall(
                "exe:agentctl-core-eval",
                input_text=json.dumps({"subject": "mux-render", **request}) + "\n",
            ),
        )
        assert isinstance(rendered, Ok), rendered
        assert rendered.value.code == 0, rendered.value.stderr
        value = object_value(rendered.value.stdout)
        assert value.get("executable") == (
            "psmux.exe" if self.family == "Windows" else "tmux"
        )
        assert isinstance(value.get("argv"), list)
        result = build.execute_binary(
            self.context,
            build.BinaryCall(
                "test:agentctl-core-test",
                ("--mux-fixture",),
                input_text=json.dumps(
                    {
                        "operation": "command",
                        "directory": str(
                            self.scope if directory is None else directory
                        ),
                        **request,
                    }
                ),
                protocol=None,
                settings=tuple(self.environment.items()),
            ),
        )
        assert isinstance(result, Ok), result
        assert result.value.code == 0, result.value.stdout + result.value.stderr
        return object_value(result.value.stdout)

    def actor(
        self,
        session: str,
        *,
        disposition: str = "stay",
        arguments: tuple[str, ...] = (),
    ) -> Actor:
        """Start the trampoline, hold its pane, then publish an independent spec."""
        nonce = fresh(self.nonce)
        directory = self.scope / ("actor-" + secrets.token_hex(4))
        directory.mkdir(mode=0o700)
        records = directory / "records"
        records.mkdir(mode=0o700)
        folder = directory / "folder with spaces #literal"
        folder.mkdir()
        binary_directory = directory / "binary with spaces #literal"
        binary_directory.mkdir()
        core = build.binary(self.context, "exe:agentctl-core")
        fake = build.binary(self.context, "exe:agentctl-fake-agent")
        assert isinstance(core, Ok), core
        assert isinstance(fake, Ok), fake
        suffix = ".exe" if self.family == "Windows" else ""
        published = binary_directory / ("agentctl-core" + suffix)
        agent = binary_directory / ("claude" + suffix)
        shutil.copy2(core.value, published)
        shutil.copy2(fake.value, agent)
        spec = directory / "launch.json"
        status = directory / "status.json"
        environment = {
            **{
                key: value
                for key, value in self.environment.items()
                if key != "SERVER_ONLY"
            },
            "CALLER_ONLY": "caller-literal",
            "AGENTCTL_FAKE_RECORD_DIR": str(records),
            "AGENTCTL_FAKE_EXIT": disposition,
        }
        forwarded = (*arguments, "--agentctl-observer-nonce", nonce)
        result = self.command(
            "create",
            session=session,
            binary=str(published),
            spec=str(spec),
            directory=folder,
        )
        assert result["code"] == 0, result
        pane = str(result["stdout"]).strip()
        assert pane.startswith("%")
        assert pane[1:].isascii()
        assert pane[1:].isdigit()
        actor = Actor(
            session, pane, nonce, records, spec, status, folder, forwarded, environment
        )
        self.actors.append(actor)
        held = self.command("remain-on-exit", pane=pane, enabled=True)
        assert held["code"] == 0, held
        payload = {
            "argv": [str(agent), *forwarded],
            "cwd": str(folder),
            "env": environment,
            "status": str(status),
        }
        pending = directory / "pending.json"
        descriptor = os.open(pending, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False)
        pending.rename(spec)
        if self.family == "Windows":
            for pid_file in self.endpoint.glob("*.pid"):
                self._register(int(pid_file.read_text(encoding="utf-8").strip()))
        observed = actor.record()
        pid = observed["pid"]
        assert isinstance(pid, int)
        self._register(pid)
        return actor

    def exit_status(self, actor: Actor) -> int:
        """Wait for terminal closure and the backend's published exit status."""
        deadline = time.monotonic() + WAIT_SECONDS
        while time.monotonic() < deadline:
            state = self.raw(
                "display-message",
                "-p",
                "-t",
                actor.pane,
                "#{pane_dead}"
                if self.family == "Windows"
                else "#{pane_dead}|#{pane_dead_status}|#{pane_dead_signal}",
            )
            assert state.code == 0, state.stderr
            if self.family == "Windows":
                if state.stdout.strip() == "1" and actor.status.exists():
                    result = build.execute_binary(
                        self.context,
                        build.BinaryCall(
                            "test:agentctl-core-test",
                            ("--mux-fixture",),
                            input_text=json.dumps(
                                {"operation": "status", "path": str(actor.status)}
                            ),
                            settings=tuple(self.environment.items()),
                        ),
                    )
                    assert isinstance(result, Ok), result
                    assert result.value.code == 0, result.value.stderr
                    value: object = json.loads(result.value.stdout)
                    assert isinstance(value, int)
                    assert not isinstance(value, bool)
                    return value
            else:
                fields = state.stdout.rstrip("\r\n").split("|")
                assert len(fields) == EXIT_FIELDS, state.stdout
                if fields[0] == "1" and (fields[1] or fields[2]):
                    assert not fields[2], (
                        "controlled actor terminated by signal: " + fields[2]
                    )
                    assert fields[1].isascii(), state.stdout
                    assert fields[1].isdigit(), (
                        "terminal closed before exit status was published"
                    )
                    return int(fields[1])
                if fields[0] == "1":
                    self.request_reap()
            time.sleep(POLL_SECONDS)
        message = "dead pane did not publish its exit status within the deadline"
        raise AssertionError(message)

    def request_reap(self) -> None:
        """Use the real runner to refresh only this backend's child accounting."""
        result = build.execute_binary(
            self.context,
            build.BinaryCall(
                "test:agentctl-core-test",
                ("--mux-fixture",),
                input_text=json.dumps(
                    {"operation": "request-reap", "directory": str(self.scope)}
                ),
                settings=tuple(self.environment.items()),
            ),
        )
        assert isinstance(result, Ok), result
        assert result.value.code == 0, result.value.stdout + result.value.stderr
        assert object_value(result.value.stdout) == {"code": 0}

    def kill_server(self, endpoint: Path | None = None) -> Output:
        """Refuse an endpoint outside this owned scope before issuing kill-server."""
        selected = self.endpoint if endpoint is None else endpoint
        return self.raw("kill-server", endpoint=selected)

    def restart(self) -> None:
        """Reap this private server before reopening the same owned endpoint."""
        assert self.endpoint.resolve().is_relative_to(self.run_directory.resolve())
        self.close()
        self.open()

    def _release_observers(self) -> None:
        """Let recorded fake actors finish before ending their private server."""
        family = self.family
        assert family in {"Linux", "Darwin", "Windows"}
        for release in self.releases.values():
            release.write_text("stop", encoding="utf-8")
        for pid in self.releases:
            deadline = time.monotonic() + WAIT_SECONDS
            state = alive(family, pid)
            while state == Ok(value=True) and time.monotonic() < deadline:
                time.sleep(POLL_SECONDS)
                state = alive(family, pid)

    def close(self) -> None:
        """Stop fake actors before ending and reaping the owned server."""
        try:
            self._release_observers()
            for actor in self.actors:
                (actor.record_directory / "stop").write_text("stop", encoding="utf-8")
            for actor in self.actors:
                deadline = time.monotonic() + WAIT_SECONDS
                result = self.raw(
                    "display-message", "-p", "-t", actor.pane, "#{pane_dead}"
                )
                while (
                    result.code == 0
                    and result.stdout.strip() != "1"
                    and time.monotonic() < deadline
                ):
                    time.sleep(POLL_SECONDS)
                    result = self.raw(
                        "display-message", "-p", "-t", actor.pane, "#{pane_dead}"
                    )
            self.kill_server()
        finally:
            if self.server is not None:
                assert isinstance(stop(self.server), Ok)
            family = self.family
            assert family in {"Linux", "Darwin", "Windows"}
            for pid in self.registered:
                deadline = time.monotonic() + WAIT_SECONDS
                state = alive(family, pid)
                while state == Ok(value=True) and time.monotonic() < deadline:
                    time.sleep(POLL_SECONDS)
                    state = alive(family, pid)
                assert state == Ok(value=False), (
                    "owned observer survived server teardown"
                )
                (self.run_directory / "observers" / f"{self.nonce}.{pid}.json").unlink()
            self.registered.clear()
            self.releases.clear()
            if self.family != "Windows":
                assert self.endpoint.resolve().is_relative_to(self.scope.resolve())
                if self.endpoint.is_socket():
                    self.endpoint.unlink()


@contextmanager
def private_mux(
    context: build.BuildContext, family: str, run_directory: Path, nonce: str
) -> Generator[PrivateMux]:
    """Create a short endpoint and private homes beneath the owning run."""
    scope = run_directory / "mux" / secrets.token_hex(4)
    scope.mkdir(parents=True, mode=0o700)
    home = scope / "home"
    home.mkdir(mode=0o700)
    environment = {
        **{
            key: value
            for key, value in build.environment(context).items()
            if key not in {"TMUX", "TMUX_PANE"}
        },
        "HOME": str(home),
        "USERPROFILE": str(home),
        "TMUX_TMPDIR": str(scope),
        "PSMUX_DATA_DIR": str(scope / "psmux"),
        "PSMUX_NO_WARM": "1",
        "SERVER_ONLY": "server-literal",
    }
    for kind in ("CACHE", "CONFIG", "DATA", "STATE"):
        path = scope / kind.lower()
        path.mkdir(mode=0o700)
        environment[f"XDG_{kind}_HOME"] = str(path)
    executable = shutil.which(
        "psmux.exe" if family == "Windows" else "tmux", path=environment.get("PATH", "")
    )
    assert executable is not None, "native backend is absent"
    endpoint = (
        scope / "psmux"
        if family == "Windows"
        else scope / f"tmux-{os.getuid()}/default"
    )
    mux = PrivateMux(
        context, family, run_directory, nonce, scope, environment, executable, endpoint
    )
    try:
        mux.open()
        yield mux
    finally:
        mux.close()


@pytest.fixture
def mux_server(
    haskell_build: build.BuildContext, record_host: HostFacts
) -> Iterator[PrivateMux]:
    """Keep focused and gate runs equally private while using the gate registry."""
    manifest = os.environ.get("AGENTCTL_CHECK_MANIFEST")
    nonce = fresh(os.environ.get("AGENTCTL_CHECK_NONCE", "focused"))
    with TemporaryDirectory(prefix="agentctl-mux-") as temporary:
        directory = Path(temporary) if manifest is None else Path(manifest).parent
        with private_mux(haskell_build, record_host.family, directory, nonce) as mux:
            yield mux
