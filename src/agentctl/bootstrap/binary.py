# Copyright (c) 2026 agentctl contributors.
"""Digest hits, locked native builds and immutable, handshake-checked publication."""

import hashlib
import json
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from agentctl.bootstrap import build, cache, toolchain
from agentctl.bootstrap.pins import Pins, load
from agentctl.check.preconditions import exclusive_file
from agentctl.hostfacts import HostContext
from agentctl.process import run
from agentctl.result import Err, Ok, Result


@dataclass(frozen=True, slots=True)
class Request:
    """Explicit source, pins and per-user destinations captured by the application."""

    project: Path
    pins: Path
    host: HostContext
    data: Path


@dataclass(frozen=True, slots=True)
class Identity:
    """Observed compiler output and published file with their matching byte hash."""

    built: Path
    published: Path
    sha256: str


def plan(request: Request, pins: Pins) -> Result[cache.Layout, build.BuildError]:
    """Identify the current sources without probing or spawning any executable."""
    triple = cache.platform(pins, request.host.family, request.host.machine)
    if isinstance(triple, Err):
        return Err(build.BuildError(triple.error.message))
    result = cache.layout(
        cache.Source(request.project, request.pins, triple.value),
        request.host.cache,
        request.data,
        request.host.family,
    )
    return (
        Err(build.BuildError(result.error.message))
        if isinstance(result, Err)
        else result
    )


def check_context(
    host: HostContext, project: Path, pins_file: Path | None = None
) -> Result[build.BuildContext, build.BuildError]:
    """Resolve the ensured toolchain and the current digest's exact build directory."""
    tools = build.recorded_tools(host)
    if isinstance(tools, Err):
        return tools
    path = pins_file or Path(__file__).with_name("pins.toml")
    selected = load(path)
    if isinstance(selected, Err):
        return Err(build.BuildError(selected.error.message))
    layout = plan(Request(project, path, host, host.cache), selected.value)
    return (
        layout
        if isinstance(layout, Err)
        else Ok(build.BuildContext(project, layout.value.directory, host, tools.value))
    )


def handshake(value: object) -> bool:
    """Accept only the current wire version and a nonempty, unique command list."""
    if not isinstance(value, dict) or set(value) != {"protocol", "commands"}:
        return False
    protocol, commands = value["protocol"], value["commands"]
    return (
        type(protocol) is int
        and protocol == 1
        and isinstance(commands, list)
        and bool(commands)
        and all(isinstance(command, str) and bool(command) for command in commands)
        and len(set(commands)) == len(commands)
    )


def verify_handshake(
    context: build.BuildContext, binary: Path
) -> Result[None, build.BuildError]:
    """Ask the staged native file for the protocol before any final path appears."""
    result = run(
        [str(binary), "--handshake"],
        cwd=context.project,
        env={**build.environment(context), "AGENTCTL_PROTOCOL_VERSION": "1"},
        timeout=10,
    )
    if isinstance(result, Err):
        return Err(build.BuildError(result.error.message))
    try:
        answer: object = json.loads(result.value.stdout)
    except json.JSONDecodeError as exc:
        return Err(build.BuildError(f"Invalid core handshake: {exc}"))
    if result.value.code or not handshake(answer):
        return Err(build.BuildError("Core handshake does not match protocol 1"))
    return Ok(None)


def _existing(path: Path) -> Result[Path, build.BuildError]:
    """Refuse incomplete entries without overwriting or deleting their contents."""
    return (
        Ok(path)
        if path.is_file()
        else Err(
            build.BuildError(f"Incomplete published binary directory: {path.parent}")
        )
    )


def _cached(layout: cache.Layout) -> bool:
    """Observe the published executable before any provisioning or build work."""
    return layout.binary.is_file()


def publish(
    context: build.BuildContext, built: Path, layout: cache.Layout
) -> Result[Path, build.BuildError]:
    """Serialise publication outside bin, preserving every existing digest directory."""
    destination = layout.binary
    root = destination.parent.parent.parent
    try:
        with exclusive_file(
            root / "locks" / (layout.digest + ".publish.lock")
        ) as locked:
            if isinstance(locked, Err):
                return Err(build.BuildError(locked.error.message))
            if destination.parent.exists():
                return _existing(destination)
            return _publish(context, built, destination)
    except OSError as exc:
        return Err(build.BuildError(f"Cannot publish core binary: {exc}"))


def _publish(
    context: build.BuildContext, built: Path, destination: Path
) -> Result[Path, build.BuildError]:
    """Copy and validate in an owned sibling directory before one atomic rename."""
    destination.parent.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=".binary-", dir=destination.parent.parent
    ) as temporary:
        staged = Path(temporary) / "entry"
        staged.mkdir(mode=0o700)
        candidate = staged / destination.name
        shutil.copy2(built, candidate)
        accepted = verify_handshake(context, candidate)
        if isinstance(accepted, Err):
            return accepted
        if destination.parent.exists():
            return _existing(destination)
        staged.rename(destination.parent)
    return Ok(destination)


def ensure(
    request: Request, *, lock_timeout: float = 1800
) -> Result[Path, build.BuildError]:
    """Return a digest hit before toolchain probes, otherwise build under its lock."""
    pins = load(request.pins)
    if isinstance(pins, Err):
        return Err(build.BuildError(pins.error.message))
    layout = plan(request, pins.value)
    if isinstance(layout, Err):
        return layout
    if _cached(layout.value):
        return Ok(layout.value.binary)
    try:
        with exclusive_file(
            layout.value.directory / "build.lock", timeout=lock_timeout
        ) as locked:
            if isinstance(locked, Err):
                return Err(build.BuildError(locked.error.message))
            return _ensure_locked(request, pins.value, layout.value)
    except OSError as exc:
        return Err(build.BuildError(f"Cannot complete binary build: {exc}"))


def _ensure_locked(
    request: Request, pins: Pins, layout: cache.Layout
) -> Result[Path, build.BuildError]:
    """Look again after acquiring the lock before provisioning or compilation."""
    if _cached(layout):
        return Ok(layout.binary)
    tools = toolchain.checked(request.host, pins)
    if isinstance(tools, Err):
        return Err(build.BuildError(tools.error.message))
    context = build.BuildContext(
        request.project, layout.directory, request.host, tools.value
    )
    compiled = build.compile_target(context, "exe:agentctl-core")
    if isinstance(compiled, Err):
        return compiled
    located = build.binary(context, "exe:agentctl-core")
    return (
        located if isinstance(located, Err) else publish(context, located.value, layout)
    )


def file_hash(path: Path) -> str:
    """Hash actual file bytes, independent of the binary's handshake or path name."""
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def identify(
    context: build.BuildContext,
    data: Path,
    *,
    pins_file: Path | None = None,
    lock_timeout: float = 1800,
) -> Result[Identity, build.BuildError]:
    """Compare this run's Cabal output with the immutable file the application uses."""
    path = pins_file or Path(__file__).with_name("pins.toml")
    selected = load(path)
    if isinstance(selected, Err):
        return Err(build.BuildError(selected.error.message))
    layout = plan(
        Request(context.project, path, context.host, data),
        selected.value,
    )
    if isinstance(layout, Err):
        return layout
    try:
        with exclusive_file(
            context.directory / "build.lock", timeout=lock_timeout
        ) as locked:
            if isinstance(locked, Err):
                return Err(build.BuildError(locked.error.message))
            return _identify_locked(context, layout.value)
    except OSError as exc:
        return Err(build.BuildError(f"Cannot inspect binary identity: {exc}"))


def _identify_locked(
    context: build.BuildContext, layout: cache.Layout
) -> Result[Identity, build.BuildError]:
    """Locate the built file through Cabal before publishing and hashing it."""
    located = build.binary(context, "exe:agentctl-core")
    if isinstance(located, Err):
        return located
    published = publish(context, located.value, layout)
    if isinstance(published, Err):
        return published
    inherited = dict(context.host.environment)
    if shutil.which("agentctl-core", path=inherited.get("PATH", "")) is not None:
        return Err(build.BuildError("The core binary must not be on PATH"))
    built_hash, published_hash = file_hash(located.value), file_hash(published.value)
    if built_hash != published_hash:
        return Err(
            build.BuildError(
                f"Binary identity mismatch: built {built_hash}, "
                f"published {published_hash}; "
                f"remove {published.value.parent}"
            )
        )
    return Ok(Identity(located.value, published.value, built_hash))
