# Copyright (c) 2026 agentctl contributors.
"""External spawn observations with nonce binding and pre-execution vetoes."""

import json
import os
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import ClassVar

from agentctl.result import Err, Ok, Result

EVENTS = frozenset(
    {"subprocess.Popen", "os.exec", "os.system", "os.posix_spawn", "os.spawn"}
)
MANAGERS = frozenset(
    {
        "apt",
        "apt-get",
        "dnf",
        "pacman",
        "yum",
        "zypper",
        "brew",
        "winget",
        "choco",
        "scoop",
        "sudo",
        "doas",
        "pkexec",
    }
)


@dataclass(frozen=True, slots=True)
class AuditError:
    """An invalid observation, replay or unavailable output boundary."""

    message: str


@dataclass(frozen=True, slots=True)
class Arguments:
    """The observed argument vector and any original command-line string."""

    argv: tuple[str, ...]
    raw: str | None = None


@dataclass(frozen=True, slots=True)
class Record:
    """One event recorded independently before it can take effect."""

    nonce: str
    pid: int
    event: str
    argv: tuple[str, ...]
    raw: str | None
    vetoed: bool


def windows_arguments(command: str) -> tuple[str, ...]:
    """Decode the CRT quoting produced by Python's Windows argv conversion."""
    arguments: list[str] = []
    current: list[str] = []
    quoted = False
    started = False
    index = 0
    while index < len(command):
        character = command[index]
        if character in " \t" and not quoted:
            if started:
                arguments.append("".join(current))
                current = []
                started = False
            index += 1
        elif character in {"\\", '"'}:
            count = 0
            while index < len(command) and command[index] == "\\":
                count += 1
                index += 1
            if index < len(command) and command[index] == '"':
                current.extend("\\" * (count // 2))
                if count % 2:
                    current.append('"')
                elif quoted and index + 1 < len(command) and command[index + 1] == '"':
                    current.append('"')
                    index += 1
                else:
                    quoted = not quoted
                index += 1
            else:
                current.extend("\\" * count)
            started = True
        else:
            current.append(character)
            started = True
            index += 1
    if started:
        arguments.append("".join(current))
    return tuple(arguments)


def forbidden(event: str, arguments: Arguments, nonce: str) -> bool:
    """Refuse installers and arbitrary shell strings before execution."""
    if event == "os.system":
        return arguments.raw != "echo " + nonce
    if not arguments.argv:
        return True
    name = (
        arguments.argv[0]
        .replace("\\", "/")
        .rsplit("/", 1)[-1]
        .lower()
        .removesuffix(".exe")
    )
    return (
        name in MANAGERS
        or (name in {"ghcup", "cabal"} and "install" in arguments.argv[1:])
        or (name == "xcode-select" and "--install" in arguments.argv[1:])
    )


def event_arguments(
    event: str, values: tuple[object, ...]
) -> Result[Arguments, AuditError]:
    """Parse documented audit-event payloads without recording environment values."""
    offset = 0 if event == "os.system" else (2 if event == "os.spawn" else 1)
    if len(values) <= offset:
        return Err(AuditError("incomplete audit event"))
    value = values[offset]
    if isinstance(value, bytes):
        try:
            value = value.decode("utf-8")
        except UnicodeError as exc:
            return Err(AuditError(str(exc)))
    if isinstance(value, str):
        return Ok(
            Arguments(
                (value,) if event == "os.system" else windows_arguments(value), value
            )
        )
    if isinstance(value, (list, tuple)) and all(
        isinstance(item, str) for item in value
    ):
        return Ok(Arguments(tuple(str(item) for item in value)))
    return Err(AuditError("invalid audit argument vector"))


def _append(path: Path, value: str) -> None:
    """Append one private, flushed observation before the observed effect."""
    descriptor = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    with os.fdopen(descriptor, "a", encoding="utf-8") as stream:
        stream.write(value + "\n")


def _register(path: Path, nonce: str, pid: int) -> None:
    """Register each actor pid once, including exec actors created by a fork."""
    registry = path.with_name(path.stem + f".{pid}.json")
    if not registry.exists():
        descriptor = os.open(registry, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump({"nonce": nonce, "pid": pid}, stream)


@dataclass(frozen=True, slots=True)
class Observer:
    """An immutable hook whose effects remain visible to Python tracing tools."""

    path: Path
    nonce: str
    __cantrace__: ClassVar[bool] = True

    def __call__(self, event: str, values: tuple[object, ...]) -> None:
        """Record a recognized boundary and veto an unsafe operation."""
        if event in EVENTS:
            parsed = event_arguments(event, values)
            if isinstance(parsed, Err):
                message = "audit rejected an unparseable event: " + parsed.error.message
                raise OSError(message)
            denied = forbidden(event, parsed.value, self.nonce)
            record = Record(
                self.nonce,
                os.getpid(),
                event,
                parsed.value.argv,
                parsed.value.raw,
                denied,
            )
            _register(self.path, self.nonce, record.pid)
            _append(self.path, json.dumps(asdict(record), ensure_ascii=True))
            if denied:
                message = "audit veto: installation or unsafe system command"
                raise PermissionError(message)


def install(path: Path, nonce: str) -> Result[None, AuditError]:
    """Install an observer in a disposable subject interpreter."""
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", nonce):
        return Err(AuditError("invalid observer nonce"))
    try:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        _register(path, nonce, os.getpid())
    except OSError as exc:
        return Err(AuditError(str(exc)))
    sys.addaudithook(Observer(path, nonce))
    return Ok(None)


def _record(value: object, nonce: str) -> Result[Record, AuditError]:
    """Parse an observation into a precise type and reject replayed records."""
    if not isinstance(value, dict) or set(value) != {
        "nonce",
        "pid",
        "event",
        "argv",
        "raw",
        "vetoed",
    }:
        return Err(AuditError("invalid observer record fields"))
    if value.get("nonce") != nonce:
        return Err(AuditError("observer nonce mismatch"))
    pid, event, argv, raw, vetoed = (
        value[name] for name in ("pid", "event", "argv", "raw", "vetoed")
    )
    if (
        not isinstance(pid, int)
        or isinstance(pid, bool)
        or pid <= 0
        or not isinstance(event, str)
        or event not in EVENTS
    ):
        return Err(AuditError("invalid observer identity"))
    if (
        not isinstance(argv, list)
        or not all(isinstance(item, str) for item in argv)
        or not isinstance(vetoed, bool)
        or (raw is not None and not isinstance(raw, str))
    ):
        return Err(AuditError("invalid observer payload"))
    return Ok(Record(nonce, pid, event, tuple(str(item) for item in argv), raw, vetoed))


def read(path: Path, nonce: str) -> Result[tuple[Record, ...], AuditError]:
    """Read nonempty, nonce-bound observations from a private actor log."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        return Err(AuditError(str(exc)))
    if not lines:
        return Err(AuditError("empty observer log"))
    records: tuple[Record, ...] = ()
    for line in lines:
        try:
            value: object = json.loads(line)
        except json.JSONDecodeError as exc:
            return Err(AuditError(str(exc)))
        parsed = _record(value, nonce)
        if isinstance(parsed, Err):
            return parsed
        records += (parsed.value,)
    return Ok(records)
