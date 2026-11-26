# Copyright (c) 2026 agentctl contributors.
"""Closed host-lane predicates and full-pass-only evidence formatting."""

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from agentctl.foundation import Err, Ok, Result

type Lane = Literal[
    "any-host",
    "mux-host",
    "agent-host",
    "live-agents",
    "clean-container",
    "macos",
    "windows-psmux",
]
type PhaseLane = Literal["linux", "linux-windows", "linux-macos", "linux-live-clean"]
LANES: tuple[Lane, ...] = (
    "any-host",
    "mux-host",
    "agent-host",
    "live-agents",
    "clean-container",
    "macos",
    "windows-psmux",
)
QUALIFICATIONS = (
    "checkout",
    "git",
    "mux",
    "agents",
    "authenticated",
    "clean",
    "xcode",
    "debian",
)


@dataclass(frozen=True, slots=True)
class LaneError:
    """An unknown lane cannot be treated as an unmet optional capability."""

    message: str


@dataclass(frozen=True, slots=True)
class HostFacts:
    """Observed base facts and qualifications supplied by their owning harnesses."""

    family: str
    architecture: str
    checkout: bool
    git: bool
    mux: bool = False
    agents: bool = False
    authenticated: bool = False
    clean: bool = False
    xcode: bool = False
    debian: bool = False


@dataclass(frozen=True, slots=True)
class LaneState:
    """One predicate evaluated from the recorded host facts."""

    lane: Lane
    met: bool


@dataclass(frozen=True, slots=True)
class Declaration:
    """A phase's raw status, gate kind and requested lane."""

    name: str
    status: str
    kind: str
    lane: str


def parse_host(value: object, nonce: str) -> Result[HostFacts, LaneError]:
    """Require this run's identity and every typed observation, including false ones."""
    if (
        not isinstance(value, dict)
        or set(value) != {"nonce", "facts"}
        or not nonce
        or value.get("nonce") != nonce
    ):
        return Err(LaneError("host observation nonce or fields mismatch"))
    facts = value["facts"]
    if not isinstance(facts, dict) or set(facts) != {
        "family",
        "architecture",
        *QUALIFICATIONS,
    }:
        return Err(LaneError("invalid host observation fields"))
    family, machine = facts["family"], facts["architecture"]
    if (
        not isinstance(family, str)
        or not isinstance(machine, str)
        or not all(isinstance(facts[name], bool) for name in QUALIFICATIONS)
    ):
        return Err(LaneError("invalid host observation types"))
    return Ok(
        HostFacts(
            family=family,
            architecture=machine,
            checkout=bool(facts["checkout"]),
            git=bool(facts["git"]),
            mux=bool(facts["mux"]),
            agents=bool(facts["agents"]),
            authenticated=bool(facts["authenticated"]),
            clean=bool(facts["clean"]),
            xcode=bool(facts["xcode"]),
            debian=bool(facts["debian"]),
        )
    )


def _unique_host_fields(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """Reject duplicate fields at every level of a host observation."""
    result = dict(pairs)
    if len(result) != len(pairs):
        message = "duplicate host observation field"
        raise ValueError(message)
    return result


def read_host(path: Path, nonce: str) -> Result[HostFacts, LaneError]:
    """Read the harness observation without inferring unimplemented capabilities."""
    try:
        if path.is_symlink():
            return Err(LaneError("host observation is a symlink"))
        value: object = json.loads(
            path.read_text(encoding="utf-8"), object_pairs_hook=_unique_host_fields
        )
    except (OSError, UnicodeError, ValueError) as exc:
        return Err(LaneError(str(exc)))
    return parse_host(value, nonce)


def parse_lane(value: str) -> Result[Lane, LaneError]:
    """Accept only the canonical vocabulary, including optional acceptance lanes."""
    if value in {
        "any-host",
        "mux-host",
        "agent-host",
        "live-agents",
        "clean-container",
        "macos",
        "windows-psmux",
    }:
        return Ok(value)
    return Err(LaneError("unknown host lane: " + value))


def parse_phase_lane(value: str) -> Result[PhaseLane, LaneError]:
    """Parse the plan's closed cross-host receipt vocabulary."""
    if value in {"linux", "linux-windows", "linux-macos", "linux-live-clean"}:
        return Ok(value)
    return Err(LaneError("unknown phase lane: " + value))


def architecture(family: str, observed: str) -> str:
    """Normalize the host's spelling to the lane table's architecture names."""
    name = {"amd64": "x86_64", "arm64": "aarch64"}.get(
        observed.lower(), observed.lower()
    )
    return "arm64" if family == "Darwin" and name == "aarch64" else name


def debian_release(text: str) -> bool:
    """Accept exactly one Debian ID from the native operating-system release."""
    candidates = tuple(
        line for line in text.splitlines() if re.match(r"^\s*ID\s*=", line)
    )
    if len(candidates) != 1:
        return False
    ids = re.findall(r'(?m)^ID=(?:"([^"\n]+)"|([^\s"\n]+))$', text)
    return tuple(quoted or plain for quoted, plain in ids) == ("debian",)


def phase_lane_host(lane: PhaseLane, facts: HostFacts) -> bool:
    """Check the native family and base capabilities for one phase lane."""
    arch = architecture(facts.family, facts.architecture)
    base = facts.checkout and facts.git
    linux = facts.family == "Linux" and arch in {"x86_64", "aarch64"} and facts.debian
    windows = facts.family == "Windows" and arch == "x86_64"
    macos = facts.family == "Darwin" and arch in {"x86_64", "arm64"}
    return base and (
        (linux and lane in {"linux", "linux-windows", "linux-macos"})
        or (
            linux
            and lane == "linux-live-clean"
            and facts.mux
            and facts.agents
            and facts.authenticated
            and facts.clean
        )
        or (windows and lane == "linux-windows")
        or (macos and lane == "linux-macos")
    )


def evaluate(facts: HostFacts) -> tuple[LaneState, ...]:
    """Require every prerequisite; unavailable capability observations remain false."""
    supported = {
        "Linux": {"x86_64", "aarch64"},
        "Darwin": {"x86_64", "arm64"},
        "Windows": {"x86_64"},
    }
    base = (
        facts.checkout
        and facts.git
        and architecture(facts.family, facts.architecture)
        in supported.get(facts.family, set())
    )
    mux = base and facts.mux
    agents = mux and facts.agents
    return (
        LaneState("any-host", base),
        LaneState("mux-host", mux),
        LaneState("agent-host", agents),
        LaneState(
            "live-agents", agents and facts.family == "Linux" and facts.authenticated
        ),
        LaneState("clean-container", base and facts.clean),
        LaneState("macos", agents and facts.family == "Darwin" and facts.xcode),
        LaneState("windows-psmux", agents and facts.family == "Windows"),
    )


def refusals(
    declarations: tuple[Declaration, ...], states: tuple[LaneState, ...]
) -> tuple[str, ...]:
    """Refuse an unmet lane of every Done self-verifying phase."""
    met = frozenset(state.lane for state in states if state.met)
    problems: tuple[str, ...] = ()
    for declaration in declarations:
        lane = parse_lane(declaration.lane)
        if isinstance(lane, Err):
            problems += ("plan.lanes: " + declaration.name + ": " + lane.error.message,)
        elif (
            declaration.status == "Done"
            and declaration.kind == "self-verifying"
            and lane.value not in met
        ):
            problems += (
                "plan.lanes: unmet " + lane.value + " for " + declaration.name,
            )
    return problems


def evidence_lines(
    code: int, states: tuple[LaneState, ...], day: str, tree: str, detail: str
) -> tuple[str, ...]:
    """Return evidence only after every earlier step and finalizer has succeeded."""
    if code:
        return ()
    return tuple(
        (
            f"EVIDENCE {day} ; {state.lane} ; agentctl check ; pass ; "
            f"tree {tree} ; {detail}"
        )
        for state in states
        if state.met
    )
