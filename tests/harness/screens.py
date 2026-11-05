# Copyright (c) 2026 agentctl contributors.
"""Independent screen expectations and their documented or captured provenance."""

import tomllib
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from agentctl.result import Err, Ok, Result

type AgentName = Literal["claude", "codex"]
PATH_PARTS = 3
TAIL_LINES = 100


def normalized(text: str) -> str:
    """Apply the documented text contract independently in Python."""
    lines = [
        line.rstrip(" \t")
        for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    ]
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines[-TAIL_LINES:])


class ScreenClass(StrEnum):
    """The requirement's closed vocabulary, independent of native implementation."""

    IDLE = "IdlePrompt"
    WORKING = "Working"
    APPROVAL = "ApprovalDialog"
    PARTIAL = "PartialInput"
    TRUST = "TrustDialog"
    BYPASS = "BypassWarning"
    LOGIN = "LoginScreen"
    OVERLOADED = "Overloaded"
    USAGE = "UsageLimit"
    AUTH = "AuthError"
    CONTEXT = "ContextExhausted"
    EXITED = "Exited"
    UNKNOWN = "Unknown"


@dataclass(frozen=True, slots=True)
class Documented:
    """A source URL with a declared limitation, never live-screen evidence."""

    source: str


@dataclass(frozen=True, slots=True)
class Captured:
    """An exact optional capture operation and the agent version it observed."""

    agent_version: str
    capture_command: str


@dataclass(frozen=True, slots=True)
class Fixture:
    """The directory supplies the expectation; no subject supplies its own oracle."""

    path: Path
    agent: AgentName
    kind: ScreenClass
    text: str
    provenance: Documented | Captured
    evidence: str
    note: str
    baseline: Path | None


@dataclass(frozen=True, slots=True)
class FixtureError:
    """A specific invalid fixture or incomplete class matrix."""

    message: str


def read(directory: Path) -> Result[tuple[Fixture, ...], FixtureError]:
    """Require paired files and the whole per-agent vocabulary."""
    paths = tuple(sorted(directory.rglob("*.txt")))
    fixtures: tuple[Fixture, ...] = ()
    for path in paths:
        result = _fixture(directory, path)
        if isinstance(result, Err):
            return result
        fixtures += (result.value,)
    for sidecar in directory.rglob("*.toml"):
        if sidecar.with_suffix(".txt") not in paths:
            return Err(FixtureError("orphan provenance sidecar: " + str(sidecar)))
    for agent in ("claude", "codex"):
        classes = {fixture.kind for fixture in fixtures if fixture.agent == agent}
        if classes != set(ScreenClass):
            return Err(FixtureError("incomplete screen-class matrix for " + agent))
    return Ok(fixtures)


def _fixture(directory: Path, path: Path) -> Result[Fixture, FixtureError]:
    """Join independently parsed identity, contents and provenance."""
    identity = _identity(directory, path)
    if isinstance(identity, Err):
        return identity
    agent, kind = identity.value
    contents = _contents(path)
    if isinstance(contents, Err):
        return contents
    text, values = contents.value
    evidence = values.get("evidence", "")
    if not evidence or evidence not in text:
        return Err(FixtureError("evidence span is absent from fixture: " + str(path)))
    provenance = _provenance(agent, values)
    if isinstance(provenance, Err):
        return provenance
    baseline = _baseline(directory, path, agent, values.get("baseline"))
    if isinstance(baseline, Err):
        return baseline
    return Ok(
        Fixture(
            path,
            agent,
            kind,
            text,
            provenance.value,
            evidence,
            values["note"],
            baseline.value,
        )
    )


def _identity(
    directory: Path, path: Path
) -> Result[tuple[AgentName, ScreenClass], FixtureError]:
    """Read only the directory's agent and expected class."""
    parts = path.relative_to(directory).parts
    if len(parts) != PATH_PARTS or parts[0] not in {"claude", "codex"}:
        return Err(FixtureError("invalid fixture path: " + str(path)))
    agent: AgentName = "claude" if parts[0] == "claude" else "codex"
    kind = next((kind for kind in ScreenClass if kind.value == parts[1]), None)
    return (
        Err(FixtureError("unknown screen class: " + parts[1]))
        if kind is None
        else Ok((agent, kind))
    )


def _contents(path: Path) -> Result[tuple[str, dict[str, str]], FixtureError]:
    """Translate expected filesystem, decoding and TOML errors at the edge."""
    sidecar = path.with_suffix(".toml")
    if not sidecar.is_file():
        return Err(FixtureError("missing provenance sidecar: " + str(path)))
    try:
        text = path.read_text(encoding="utf-8")
        raw: object = tomllib.loads(sidecar.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as error:
        return Err(FixtureError("invalid fixture bytes: " + str(error)))
    assert isinstance(raw, dict)
    fields: dict[str, object] = {str(key): value for key, value in raw.items()}
    if any(
        not isinstance(value, str) or not value.strip() for value in fields.values()
    ):
        return Err(FixtureError("provenance fields must be nonempty strings"))
    return Ok(
        (text, {key: value for key, value in fields.items() if isinstance(value, str)})
    )


def _baseline(
    directory: Path, path: Path, agent: AgentName, value: str | None
) -> Result[Path | None, FixtureError]:
    """Require an existing overload twin inside the same agent's fixture tree."""
    if value is None:
        return Ok(None)
    baseline = (path.parent / value).resolve()
    if (
        not baseline.is_relative_to((directory / agent).resolve())
        or baseline.parent.name != ScreenClass.OVERLOADED
        or not baseline.is_file()
    ):
        return Err(FixtureError("invalid precedence baseline: " + str(path)))
    return Ok(baseline)


def _provenance(
    agent: AgentName, values: dict[str, str]
) -> Result[Documented | Captured, FixtureError]:
    """Keep optional captures distinct from examples sourced from official docs."""
    common = {"provenance", "evidence", "note"}
    optional = {"baseline"} if "baseline" in values else set()
    match values.get("provenance"):
        case "documented":
            if set(values) != common | optional | {"source"}:
                return Err(
                    FixtureError("documented provenance has missing or unknown fields")
                )
            return _documented(agent, values["source"])
        case "captured":
            if set(values) != common | optional | {"agent_version", "capture_command"}:
                return Err(
                    FixtureError("captured provenance needs version and exact command")
                )
            return Ok(Captured(values["agent_version"], values["capture_command"]))
        case _:
            return Err(FixtureError("unknown fixture provenance"))


def _documented(agent: AgentName, source: str) -> Result[Documented, FixtureError]:
    """Accept only an official HTTPS documentation URL for this agent."""
    try:
        url = urlsplit(source)
        host = url.hostname
    except ValueError:
        return Err(FixtureError("invalid documented source URL"))
    allowed = (
        {"code.claude.com", "platform.claude.com", "docs.anthropic.com"}
        if agent == "claude"
        else {"developers.openai.com", "platform.openai.com", "learn.chatgpt.com"}
    )
    if (
        url.scheme != "https"
        or host not in allowed
        or url.username is not None
        or url.password is not None
    ):
        return Err(FixtureError("documented source must be an official HTTPS URL"))
    return Ok(Documented(source))
