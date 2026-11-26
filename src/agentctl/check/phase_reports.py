# Copyright (c) 2026 agentctl contributors.
"""Pure phase-input and outcome calculations; no receipt is issued here."""

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Literal

from agentctl.check import lanes
from agentctl.check.evidence import LegEvidence, RunEvidence, ToolSubsteps
from agentctl.foundation import Err, Ok, Result

MOUNTINFO_FIXED_FIELDS = 6
FIRST_PRINTABLE_ASCII = 32
ATTRIBUTED_COLLECTION_FIELDS = 3
SCOPED_COLLECTION_FIELDS = 4
PYTEST_COMBINE_STEPS = 2
PYTEST_FULL_STEPS = 3
RECEIPT_PAIR_FIELDS = 2


@dataclass(frozen=True, slots=True)
class PhaseInputs:
    """A capability's explicit inputs, required checks and lower prerequisites."""

    number: int
    inputs: frozenset[str]
    checks: frozenset[str]
    prerequisites: frozenset[int]


@dataclass(frozen=True, slots=True)
class PhaseResult:
    """A calculation result, not proof that the supplied observations are real."""

    number: int
    identity: str
    failures: frozenset[str]


@dataclass(frozen=True, slots=True)
class AdditionalFailures:
    """Complete phase-indexed native and oracle observations for one calculation."""

    native: tuple[tuple[int, frozenset[str]], ...]
    oracle: tuple[tuple[int, frozenset[str]], ...]


@dataclass(frozen=True, slots=True)
class MountFact:
    """One kernel mount record with decoded source and mount paths."""

    identifier: int
    device: str
    root: str
    mountpoint: str
    filesystem: str
    source: str


def _mount_unescape(value: str) -> Result[str, str]:
    """Decode only the kernel's four defined mountinfo escapes."""
    if re.search(r"\\(?!040|011|012|134)", value):
        return Err("invalid mountinfo escape")
    decoded = re.sub(
        r"\\(040|011|012|134)",
        lambda match: {"040": " ", "011": "\t", "012": "\n", "134": "\\"}[match[1]],
        value,
    )
    return Ok(decoded)


def _mount_record(line: str) -> Result[MountFact, str]:
    """Parse one complete mountinfo line without inferring mount identity."""
    fields = line.split()
    if "-" not in fields:
        return Err("missing mountinfo separator")
    separator = fields.index("-")
    if (
        separator < MOUNTINFO_FIXED_FIELDS
        or len(fields) != separator + 4
        or not re.fullmatch(r"[0-9]+", fields[0])
        or not re.fullmatch(r"[0-9]+", fields[1])
        or not re.fullmatch(r"[0-9]+:[0-9]+", fields[2])
        or not fields[5]
        or not fields[separator + 1]
        or not fields[separator + 3]
    ):
        return Err("invalid mountinfo fields")
    values = tuple(_mount_unescape(fields[index]) for index in (3, 4, separator + 2))
    if any(isinstance(value, Err) for value in values):
        return Err("invalid mountinfo escape")
    root, mountpoint, source = tuple(
        value.value for value in values if isinstance(value, Ok)
    )
    if (
        not PurePosixPath(root).is_absolute()
        or not PurePosixPath(mountpoint).is_absolute()
    ):
        return Err("mount paths must be absolute")
    return Ok(
        MountFact(
            int(fields[0]), fields[2], root, mountpoint, fields[separator + 1], source
        )
    )


def parse_mountinfo(text: str) -> Result[tuple[MountFact, ...], str]:
    """Reject incomplete, duplicate or malformed kernel mount observations."""
    if not text or not text.endswith("\n"):
        return Err("incomplete mountinfo")
    records: tuple[MountFact, ...] = ()
    for line in text.splitlines():
        parsed = _mount_record(line)
        if isinstance(parsed, Err):
            return parsed
        records += (parsed.value,)
    if not records or len({record.identifier for record in records}) != len(records):
        return Err("empty or duplicate mount identifiers")
    return Ok(records)


def containing_mount(
    path: str, records: tuple[MountFact, ...]
) -> Result[MountFact, str]:
    """Select the longest containing mount and refuse a stacked ambiguity."""
    subject = PurePosixPath(path)
    if not subject.is_absolute() or subject.as_posix() != path or ".." in subject.parts:
        return Err("source path must be canonical and absolute")
    matches = tuple(
        record
        for record in records
        if subject.is_relative_to(PurePosixPath(record.mountpoint))
    )
    if not matches:
        return Err("source path is not mounted")
    longest = max(len(PurePosixPath(record.mountpoint).parts) for record in matches)
    selected = tuple(
        record
        for record in matches
        if len(PurePosixPath(record.mountpoint).parts) == longest
    )
    return Ok(selected[0]) if len(selected) == 1 else Err("ambiguous stacked mount")


def same_bind_source(
    source: str, target: str, records: tuple[MountFact, ...]
) -> Result[None, str]:
    """Compare kernel mount mappings; this alone is not a binding receipt."""
    source_mount = containing_mount(source, records)
    target_mount = containing_mount(target, records)
    match source_mount, target_mount:
        case Ok(original), Ok(bound):
            source_path = PurePosixPath(source)
            target_path = PurePosixPath(target)
            original_root = PurePosixPath(original.root) / source_path.relative_to(
                PurePosixPath(original.mountpoint)
            )
            if (
                source_path == target_path
                or bound.mountpoint != target
                or original.identifier == bound.identifier
                or (original.device, original.filesystem, original.source)
                != (bound.device, bound.filesystem, bound.source)
                or original_root != PurePosixPath(bound.root)
            ):
                return Err("mount mapping does not identify a separate bind")
            return Ok(None)
        case _:
            return Err("source or target mount is unavailable or ambiguous")


@dataclass(frozen=True, slots=True)
class BindingObservation:
    """Separately collected pre-gate binding facts, not an authenticated receipt."""

    nonce: str
    windows_write: bytes
    linux_read: bytes
    linux_write: bytes
    windows_read: bytes
    windows_inventory: tuple[tuple[str, bytes], ...]
    linux_inventory: tuple[tuple[str, bytes], ...]
    git_before: bytes
    git_after: bytes
    windows_clean: bool
    linux_clean: bool


def binding_problems(
    source: str,
    target: str,
    mounts: tuple[MountFact, ...],
    observation: BindingObservation,
) -> tuple[str, ...]:
    """Check the mount, two-way challenge, inventory and cleanup observations.

    The caller must independently collect these facts before the write guard and
    authenticate their provenance; matching supplied values alone proves neither.
    """
    mount = same_bind_source(source, target, mounts)
    nonce = observation.nonce
    expected_windows = ("windows:" + nonce).encode("utf-8")
    expected_linux = ("linux:" + nonce).encode("utf-8")
    windows_paths = tuple(path for path, _content in observation.windows_inventory)
    linux_paths = tuple(path for path, _content in observation.linux_inventory)
    return (
        *(("mount mapping",) if isinstance(mount, Err) else ()),
        *(
            ("bidirectional nonce",)
            if not nonce
            or observation.windows_write != expected_windows
            or observation.linux_read != expected_windows
            or observation.linux_write != expected_linux
            or observation.windows_read != expected_linux
            else ()
        ),
        *(
            ("source inventory",)
            if not windows_paths
            or len(windows_paths) != len(set(windows_paths))
            or len(linux_paths) != len(set(linux_paths))
            or any(not _canonical_path(path) for path in (*windows_paths, *linux_paths))
            or dict(observation.windows_inventory) != dict(observation.linux_inventory)
            else ()
        ),
        *(
            ("git baseline",)
            if not observation.git_before
            or observation.git_before != observation.git_after
            else ()
        ),
        *(
            ("sentinel cleanup",)
            if not observation.windows_clean or not observation.linux_clean
            else ()
        ),
    )


@dataclass(frozen=True, slots=True)
class OwnershipPhase:
    """One phase and its explicitly declared lower prerequisite phases."""

    number: int
    prerequisites: frozenset[int]


@dataclass(frozen=True, slots=True)
class ArtifactOwnership:
    """One exact source path, its owner, consumers and current requirement."""

    path: str
    owner: int
    consumers: frozenset[int]
    required: bool
    capability: str


def _canonical_path(value: str) -> bool:
    """Refuse aliases, absolute paths and platform-specific path spellings."""
    path = PurePosixPath(value)
    return bool(
        value
        and path.parts
        and not path.is_absolute()
        and path.as_posix() == value
        and all(part not in {".", ".."} for part in path.parts)
        and "\\" not in value
        and ":" not in value
        and all(ord(character) >= FIRST_PRINTABLE_ASCII for character in value)
    )


def _ownership_closures(
    phases: tuple[OwnershipPhase, ...],
) -> tuple[tuple[int, frozenset[int]], ...]:
    """Compute prerequisite closures in already validated phase order."""
    if not phases:
        return ()
    previous = _ownership_closures(phases[:-1])
    current = phases[-1]
    dependencies = current.prerequisites | frozenset[int](
        ancestor
        for number, ancestors in previous
        if number in current.prerequisites
        for ancestor in ancestors
    )
    return (*previous, (current.number, dependencies))


def ownership_inputs(
    phases: tuple[OwnershipPhase, ...],
    artifacts: tuple[ArtifactOwnership, ...],
    observed_paths: tuple[str, ...],
) -> Result[tuple[tuple[int, frozenset[str]], ...], str]:
    """Join an explicit ownership manifest to an independently observed census.

    This calculation is not itself a filesystem walk. Future non-required paths
    may be absent, but every observed path must have one explicit owner.
    """
    numbers = tuple(phase.number for phase in phases)
    paths = tuple(artifact.path for artifact in artifacts)
    if (
        not phases
        or not artifacts
        or numbers != tuple(range(len(numbers)))
        or any(isinstance(number, bool) for number in numbers)
        or any(number < 0 for number in numbers)
        or len(set(paths)) != len(paths)
        or len(set(observed_paths)) != len(observed_paths)
        or any(not _canonical_path(path) for path in (*paths, *observed_paths))
        or any(
            isinstance(dependency, bool)
            or dependency not in numbers
            or dependency >= phase.number
            for phase in phases
            for dependency in phase.prerequisites
        )
        or any(
            isinstance(artifact.owner, bool)
            or any(isinstance(consumer, bool) for consumer in artifact.consumers)
            or artifact.owner not in numbers
            or artifact.owner not in artifact.consumers
            or not artifact.consumers <= frozenset(numbers)
            or not re.fullmatch(r"[a-z][a-z0-9-]*", artifact.capability)
            for artifact in artifacts
        )
        or any(
            first.owner != second.owner
            for first in artifacts
            for second in artifacts
            if first.capability == second.capability
        )
    ):
        return Err("invalid ownership declarations or source census")
    observed = frozenset(observed_paths)
    unowned = tuple(sorted(observed - frozenset(paths)))
    missing = tuple(
        sorted(
            artifact.path
            for artifact in artifacts
            if artifact.required and artifact.path not in observed
        )
    )
    gaps = (
        *("unowned source artifact: " + path for path in unowned),
        *("required source artifact missing: " + path for path in missing),
    )
    if gaps:
        return Err("; ".join(gaps))
    closures = _ownership_closures(phases)
    if any(
        artifact.owner != consumer and artifact.owner not in dict(closures)[consumer]
        for artifact in artifacts
        for consumer in artifact.consumers
    ):
        return Err("consumer omits owning prerequisite")
    return Ok(
        tuple(
            (
                phase.number,
                frozenset(
                    artifact.path
                    for artifact in artifacts
                    if phase.number in artifact.consumers and artifact.path in observed
                ),
            )
            for phase in phases
        )
    )


@dataclass(frozen=True, slots=True)
class CollectionScope:
    """Expected test IDs and collection modules for one consuming phase."""

    number: int
    required: frozenset[str]
    modules: frozenset[str]


@dataclass(frozen=True, slots=True)
class CollectionObservation:
    """Independent collection and execution sets and integrity observations."""

    collected: frozenset[str]
    executed: frozenset[str]
    passed: frozenset[str]
    failed_modules: frozenset[str]
    nonce_matches: bool
    forbidden: frozenset[str]


@dataclass(frozen=True, slots=True)
class NativeAttribution:
    """Native case sources and explicit consumers captured for one run."""

    numbers: tuple[int, ...]
    sources: tuple[tuple[str, str], ...]
    consumers: tuple[tuple[str, frozenset[int]], ...]
    citations: tuple[tuple[int, str], ...]


def native_case_failures(
    manifest: RunEvidence, nonce: str, attribution: NativeAttribution
) -> Result[tuple[tuple[int, frozenset[str]], ...], str]:
    """Attribute complete native cases using observed sources and declarations.

    The caller must authenticate the snapshot, source census, ownership and
    command outcome. The returned diagnostics do not constitute a verdict.
    """
    numbers, sources, consumers, citations = (
        attribution.numbers,
        attribution.sources,
        attribution.consumers,
        attribution.citations,
    )
    by_case = dict(sources)
    by_source = dict(consumers)
    valid_numbers = frozenset(numbers)
    if (
        not nonce
        or manifest.nonce != nonce
        or not numbers
        or len(valid_numbers) != len(numbers)
        or any(isinstance(number, bool) or number < 0 for number in numbers)
        or not manifest.collected
        or manifest.collected != manifest.executed
        or not manifest.passed <= manifest.executed
        or len(by_case) != len(sources)
        or frozenset(by_case) != manifest.collected
        or len(by_source) != len(consumers)
        or any(
            not owners
            or any(isinstance(owner, bool) for owner in owners)
            or not owners <= valid_numbers
            for owners in by_source.values()
        )
        or any(path not in by_source for path in by_case.values())
        or any(
            isinstance(number, bool)
            or number not in valid_numbers
            or not node.startswith("haskell:")
            for number, node in citations
        )
        or any(
            node in by_case and number not in by_source[by_case[node]]
            for number, node in citations
        )
    ):
        return Err("invalid native case ownership or execution")
    failures = manifest.executed - manifest.passed
    expected = tuple("failed: " + node for node in sorted(failures))
    if manifest.forbidden not in (expected, (*expected, "native-command-failed")):
        return Err("invalid native failure records")
    declared = frozenset(citations)
    unexplained = not failures and "native-command-failed" in manifest.forbidden
    native_consumers = frozenset(
        owner for source in by_case.values() for owner in by_source[source]
    ) | frozenset(owner for owner, _node in citations)
    return Ok(
        tuple(
            (
                number,
                frozenset(
                    "missing native case: " + node
                    for owner, node in declared
                    if owner == number and node not in manifest.collected
                )
                | frozenset(
                    "failed native case: " + node
                    for node in failures
                    if number
                    in (
                        frozenset(owner for owner, case in declared if case == node)
                        or by_source[by_case[node]]
                    )
                )
                | (
                    frozenset({"unexplained native command failure"})
                    if unexplained and number in native_consumers
                    else frozenset[str]()
                ),
            )
            for number in numbers
        )
    )


def observe_collection(manifest: RunEvidence, nonce: str) -> CollectionObservation:
    """Convert a parsed manifest without promoting failed teardown to success.

    Recognized records become attributable only when they name a collected test
    or a concrete Python module. Unknown or malformed records remain shared damage.
    """
    failures = frozenset(
        record.removeprefix("failed: ")
        for record in manifest.forbidden
        if record.startswith("failed: ")
        and record.removeprefix("failed: ") in manifest.collected
    )
    modules = frozenset(
        record.removeprefix("collection failed: ")
        for record in manifest.forbidden
        if record.startswith("collection failed: tests/")
        and record.removeprefix("collection failed: ").endswith(".py")
        and "::" not in record
    )
    recognized = frozenset("failed: " + node for node in failures) | frozenset(
        "collection failed: " + module for module in modules
    )
    return CollectionObservation(
        manifest.collected,
        manifest.executed,
        manifest.passed - failures,
        modules,
        bool(nonce) and manifest.nonce == nonce,
        frozenset(manifest.forbidden) - recognized,
    )


def pytest_leg_failures(
    manifest: RunEvidence, tools: LegEvidence, substeps: ToolSubsteps
) -> Result[frozenset[str], str]:
    """Separate attributable test failures from shared coverage or run damage.

    These values do not authenticate the run or identify phase verdicts. The
    caller must separately verify the complete collection and all finalizers.
    """
    tool_codes = tuple(code for name, code in tools.outcomes if name == "pytest")
    command_codes = tuple(
        codes for name, codes in substeps.outcomes if name == "pytest"
    )
    if (
        not manifest.nonce
        or manifest.nonce != tools.nonce
        or manifest.nonce != substeps.nonce
        or len(tool_codes) != 1
        or len(command_codes) != 1
    ):
        return Err("pytest evidence identity or schedule mismatch")
    codes = command_codes[0]
    if (
        len(codes) not in {PYTEST_COMBINE_STEPS, PYTEST_FULL_STEPS}
        or (len(codes) == PYTEST_COMBINE_STEPS and codes[1] == 0)
        or (len(codes) == PYTEST_FULL_STEPS and codes[1] != 0)
        or tool_codes[0] != next((code for code in codes if code != 0), 0)
    ):
        return Err("pytest subprocess outcomes are incomplete or inconsistent")
    test_damage = (
        not manifest.collected
        or manifest.collected != manifest.executed
        or manifest.collected != manifest.passed
        or bool(manifest.forbidden)
    )
    if (codes[0] != 0) != test_damage:
        return Err("pytest command status differs from its execution manifest")
    return Ok(
        frozenset(
            (
                *(
                    ("coverage combine failed", "coverage report not executed")
                    if codes[1] != 0
                    else ()
                ),
                *(
                    ("coverage report failed",)
                    if len(codes) == PYTEST_FULL_STEPS and codes[2] != 0
                    else ()
                ),
            )
        )
    )


def _case_failure_consumed(
    node: str,
    number: int,
    consumers: tuple[tuple[str, frozenset[int]], ...] | None,
) -> bool:
    """Keep unlisted cases shared and join all matching parameter declarations."""
    if consumers is None:
        return True
    matching = tuple(
        phases
        for case, phases in consumers
        if node == case or node.startswith(case + "[")
    )
    return not matching or any(number in phases for phases in matching)


def collection_failures(
    scopes: tuple[CollectionScope, ...],
    observation: CollectionObservation,
    *,
    mutation_owners: tuple[tuple[str, int], ...] | None = None,
    case_consumers: tuple[tuple[str, frozenset[int]], ...] | None = None,
) -> Result[tuple[tuple[int, frozenset[str]], ...], str]:
    """Attribute collection damage only when its module consumers are explicit.

    Inputs are observed sets, not a filesystem census or a signed execution record.
    Unknown failed modules, incomplete execution and forbidden outcomes are shared
    failures. A missing required ID fails its declared owner even if not collected.
    Mutation ownership must be authenticated by the caller before being supplied.
    """
    collected, executed, passed = (
        observation.collected,
        observation.executed,
        observation.passed,
    )
    failed_modules = observation.failed_modules
    numbers = tuple(scope.number for scope in scopes)
    if (
        not scopes
        or len(set(numbers)) != len(numbers)
        or any(
            isinstance(scope.number, bool)
            or scope.number < 0
            or not scope.required
            or not scope.modules
            for scope in scopes
        )
        or any(not name for scope in scopes for name in scope.required | scope.modules)
        or any(
            node.split("::", 1)[0] not in scope.modules
            for scope in scopes
            for node in scope.required
        )
        or not passed <= executed
        or not executed <= collected
    ):
        return Err("invalid collection declarations or observations")
    owned_modules = frozenset(module for scope in scopes for module in scope.modules)
    if case_consumers is not None and (
        len({node for node, _ in case_consumers}) != len(case_consumers)
        or any(
            not consumers
            or any(
                isinstance(owner, bool)
                or not any(
                    scope.number == owner and node.split("::", 1)[0] in scope.modules
                    for scope in scopes
                )
                for owner in consumers
            )
            for node, consumers in case_consumers
        )
        or any(
            not any(
                node == required and scope.number in owners
                for node, owners in case_consumers
            )
            for scope in scopes
            for required in scope.required
        )
    ):
        return Err("invalid test case consumer mapping")
    prefix = "tests/governance/test_mutants.py::test_corpus["
    mutation_nodes = frozenset(
        node for node in collected if node == prefix[:-1] or node.startswith(prefix)
    )
    mappings = () if mutation_owners is None else mutation_owners
    identifiers = tuple(identifier for identifier, _owner in mappings)
    if (
        len(identifiers) != len(set(identifiers))
        or any(
            re.fullmatch(r"M-[a-z0-9-]+", identifier) is None
            for identifier in identifiers
        )
        or any(
            isinstance(owner, bool) or owner not in numbers
            for _identifier, owner in mappings
        )
        or any(
            "tests/governance/test_mutants.py" not in scope.modules
            for _identifier, owner in mappings
            for scope in scopes
            if scope.number == owner
        )
        or any(
            required == prefix[:-1]
            or (required.startswith(prefix) and not required.endswith("]"))
            for scope in scopes
            for required in scope.required
        )
    ):
        return Err("invalid mutation collection ownership")
    by_node = {prefix + identifier + "]": owner for identifier, owner in mappings}
    if any(
        required.startswith(prefix) and by_node.get(required) != scope.number
        for scope in scopes
        for required in scope.required
    ):
        return Err("mutation citation has wrong or missing owner")
    unknown = (
        failed_modules | frozenset(node.split("::", 1)[0] for node in collected)
    ) - owned_modules
    shared: frozenset[str] = (
        (frozenset({"nonce"}) if not observation.nonce_matches else frozenset[str]())
        | (
            frozenset({"incomplete execution"})
            if collected != executed
            else frozenset[str]()
        )
        | observation.forbidden
        | frozenset("unowned collector: " + module for module in unknown)
        | frozenset(
            "unowned mutation: " + node for node in mutation_nodes - by_node.keys()
        )
    )
    return Ok(
        tuple(
            (
                scope.number,
                shared
                | frozenset(
                    "missing or failed: " + required
                    for required in scope.required
                    if not any(
                        node == required or node.startswith(required + "[")
                        for node in collected
                    )
                    or any(
                        node not in passed
                        for node in collected
                        if node == required or node.startswith(required + "[")
                    )
                )
                | frozenset(
                    "failed test: " + node
                    for node in collected - passed
                    if node.split("::", 1)[0] in scope.modules
                    and _case_failure_consumed(node, scope.number, case_consumers)
                    and (
                        not node.startswith(prefix) or by_node.get(node) == scope.number
                    )
                )
                | frozenset(
                    "missing mutation: " + node
                    for node, owner in by_node.items()
                    if owner == scope.number and node not in collected
                )
                | frozenset(
                    "collection failed: " + module
                    for module in scope.modules & failed_modules
                ),
            )
            for scope in scopes
        )
    )


type NativeFamily = Literal["linux", "windows", "macos"]


@dataclass(frozen=True, slots=True)
class ReceiptRequirement:
    """Current expected logical identity and evidence for one capability."""

    capability: str
    lane: lanes.PhaseLane
    identity: str
    families: frozenset[NativeFamily]
    native_identities: frozenset[tuple[NativeFamily, str]]
    run_nonces: frozenset[tuple[NativeFamily, str]]
    tests: frozenset[str]
    mutants: frozenset[str]
    coverage: frozenset[str]
    prerequisites: frozenset[tuple[str, str]]


@dataclass(frozen=True, slots=True)
class Receipt:
    """Observed lane evidence; construction alone does not authenticate a run."""

    capability: str
    family: NativeFamily
    host_family: NativeFamily
    host_facts: lanes.HostFacts
    identity: str
    native_identity: str
    nonce: str
    passed: bool
    tests: frozenset[str]
    mutants: frozenset[str]
    coverage: frozenset[str]
    prerequisites: frozenset[tuple[str, str]]
    diagnostics: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ReceiptGroup:
    """Expected capability and supplied native receipts for one numbered phase."""

    number: int
    requirement: ReceiptRequirement
    receipts: tuple[Receipt, ...]


@dataclass(frozen=True, slots=True)
class ReceiptRecordGroup:
    """Canonical receipt bytes supplied for one capability's native lanes."""

    number: int
    requirement: ReceiptRequirement
    records: tuple[bytes, ...]


@dataclass(frozen=True, slots=True)
class ReceiptAggregate:
    """Calculated receipt failures; this is not authenticated run evidence."""

    number: int
    capability: str
    identity: str
    failures: frozenset[str]


def hardware_budget(families: frozenset[NativeFamily]) -> bool:
    """Each capability requires Linux and at most one foreign host family."""
    return (
        "linux" in families
        and families <= {"linux", "windows", "macos"}
        and not {"windows", "macos"} <= families
    )


def _receipt_text(value: object) -> bool:
    """Require a nonempty string at a receipt identity boundary."""
    return isinstance(value, str) and bool(value)


def _receipt_phase_number(value: object) -> bool:
    """Require an integer phase identifier without accepting Boolean aliases."""
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _receipt_text_set(value: object) -> bool:
    """Require immutable, nonempty-string evidence members; an empty set is valid."""
    return isinstance(value, frozenset) and all(_receipt_text(item) for item in value)


def _receipt_pairs(value: object) -> bool:
    """Require immutable pairs of nonempty strings before destructuring them."""
    return isinstance(value, frozenset) and all(
        isinstance(item, tuple)
        and len(item) == RECEIPT_PAIR_FIELDS
        and all(_receipt_text(part) for part in item)
        for item in value
    )


def _receipt_diagnostics(value: object) -> bool:
    """Require an immutable sequence of nonempty retained messages."""
    return isinstance(value, tuple) and all(_receipt_text(item) for item in value)


def _receipt_host(value: object, family: str, lane: lanes.PhaseLane) -> bool:
    """Require typed host facts without authenticating their origin."""
    return (
        isinstance(value, lanes.HostFacts)
        and _receipt_text(value.architecture)
        and value.family
        == {"linux": "Linux", "windows": "Windows", "macos": "Darwin"}.get(family)
        and all(isinstance(getattr(value, name), bool) for name in lanes.QUALIFICATIONS)
        and lanes.phase_lane_host(lane, value)
    )


def _receipt_fields_valid(receipt: Receipt) -> bool:
    """Check the complete value shape without claiming its origin is authentic."""
    host = receipt.host_facts
    return (
        _receipt_text(receipt.capability)
        and receipt.family in ("linux", "windows", "macos")
        and receipt.host_family == receipt.family
        and isinstance(host, lanes.HostFacts)
        and host.family
        == {"linux": "Linux", "windows": "Windows", "macos": "Darwin"}.get(
            receipt.family
        )
        and _receipt_text(host.architecture)
        and all(isinstance(getattr(host, name), bool) for name in lanes.QUALIFICATIONS)
        and _receipt_text(receipt.identity)
        and _receipt_text(receipt.native_identity)
        and _receipt_text(receipt.nonce)
        and isinstance(receipt.passed, bool)
        and _receipt_text_set(receipt.tests)
        and _receipt_text_set(receipt.mutants)
        and _receipt_text_set(receipt.coverage)
        and _receipt_pairs(receipt.prerequisites)
        and _receipt_diagnostics(receipt.diagnostics)
    )


def receipt_bytes(receipt: Receipt) -> Result[bytes, str]:
    """Encode a complete receipt value canonically; this does not authenticate it."""
    if not _receipt_fields_valid(receipt):
        return Err("invalid receipt value")
    host = receipt.host_facts
    return Ok(
        json.dumps(
            {
                "version": 1,
                "capability": receipt.capability,
                "family": receipt.family,
                "host_family": receipt.host_family,
                "host_facts": {
                    "family": host.family,
                    "architecture": host.architecture,
                    **{name: getattr(host, name) for name in lanes.QUALIFICATIONS},
                },
                "identity": receipt.identity,
                "native_identity": receipt.native_identity,
                "nonce": receipt.nonce,
                "passed": receipt.passed,
                "tests": sorted(receipt.tests),
                "mutants": sorted(receipt.mutants),
                "coverage": sorted(receipt.coverage),
                "prerequisites": sorted(receipt.prerequisites),
                "diagnostics": list(receipt.diagnostics),
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("ascii")
    )


def _unique_receipt_fields(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """Reject duplicate JSON object keys before constructing a receipt value."""
    result = dict(pairs)
    if len(result) != len(pairs):
        message = "duplicate receipt field"
        raise ValueError(message)
    return result


def _receipt_list(value: object) -> frozenset[str] | None:
    """Decode a unique ordered list of nonempty evidence identifiers."""
    if (
        not isinstance(value, list)
        or any(not _receipt_text(item) for item in value)
        or len(value) != len(set(value))
    ):
        return None
    return frozenset(str(item) for item in value)


def _receipt_pair_list(value: object) -> frozenset[tuple[str, str]] | None:
    """Decode unique prerequisite identity pairs."""
    if not isinstance(value, list) or any(
        not isinstance(item, list)
        or len(item) != RECEIPT_PAIR_FIELDS
        or any(not _receipt_text(part) for part in item)
        for item in value
    ):
        return None
    pairs = tuple((str(item[0]), str(item[1])) for item in value)
    return frozenset(pairs) if len(pairs) == len(set(pairs)) else None


def parse_receipt(contents: bytes) -> Result[Receipt, str]:
    """Decode only complete canonical records; callers must authenticate the run."""
    try:
        value: object = json.loads(contents, object_pairs_hook=_unique_receipt_fields)
    except (UnicodeError, ValueError, RecursionError):
        return Err("invalid receipt JSON")
    if not isinstance(value, dict) or set(value) != {
        "version",
        "capability",
        "family",
        "host_family",
        "host_facts",
        "identity",
        "native_identity",
        "nonce",
        "passed",
        "tests",
        "mutants",
        "coverage",
        "prerequisites",
        "diagnostics",
    }:
        return Err("invalid receipt fields")
    family, nonce = value["family"], value["nonce"]
    if (
        type(value["version"]) is not int
        or value["version"] != 1
        or not _receipt_text(nonce)
        or not isinstance(nonce, str)
        or not isinstance(value["passed"], bool)
        or not isinstance(value["diagnostics"], list)
        or any(not _receipt_text(item) for item in value["diagnostics"])
    ):
        return Err("invalid receipt values")
    native_family: NativeFamily
    match family:
        case "linux":
            native_family = "linux"
        case "windows":
            native_family = "windows"
        case "macos":
            native_family = "macos"
        case _:
            return Err("invalid receipt values")
    host = lanes.parse_host({"nonce": nonce, "facts": value["host_facts"]}, nonce)
    tests = _receipt_list(value["tests"])
    mutants = _receipt_list(value["mutants"])
    coverage = _receipt_list(value["coverage"])
    prerequisites = _receipt_pair_list(value["prerequisites"])
    if (
        isinstance(host, Err)
        or value["host_family"] != native_family
        or tests is None
        or mutants is None
        or coverage is None
        or prerequisites is None
        or not all(
            isinstance(value[name], str)
            for name in ("capability", "host_family", "identity", "native_identity")
        )
    ):
        return Err("invalid receipt values")
    receipt = Receipt(
        capability=str(value["capability"]),
        family=native_family,
        host_family=native_family,
        host_facts=host.value,
        identity=str(value["identity"]),
        native_identity=str(value["native_identity"]),
        nonce=nonce,
        passed=value["passed"],
        tests=tests,
        mutants=mutants,
        coverage=coverage,
        prerequisites=prerequisites,
        diagnostics=tuple(value["diagnostics"]),
    )
    return (
        Ok(receipt)
        if receipt_bytes(receipt) == Ok(contents)
        else Err("invalid or noncanonical receipt")
    )


def validate_receipts(
    requirement: ReceiptRequirement, receipts: tuple[Receipt, ...]
) -> tuple[str, ...]:
    """Join current expected evidence to exactly one receipt per native family.

    The caller supplies independently observed identities, per-family run nonces
    and trustworthy receipt records. This calculation does not authenticate those
    observations or establish historical authenticity.
    """
    if (
        not _receipt_text(requirement.capability)
        or not _receipt_text(requirement.lane)
        or requirement.lane
        not in {"linux", "linux-windows", "linux-macos", "linux-live-clean"}
        or not _receipt_text(requirement.identity)
        or not requirement.tests
        or not _receipt_text_set(requirement.tests)
        or not _receipt_text_set(requirement.mutants)
        or not _receipt_text_set(requirement.coverage)
        or not _receipt_text_set(requirement.families)
        or not hardware_budget(requirement.families)
        or requirement.families
        != {
            "linux": frozenset({"linux"}),
            "linux-windows": frozenset({"linux", "windows"}),
            "linux-macos": frozenset({"linux", "macos"}),
            "linux-live-clean": frozenset({"linux"}),
        }[requirement.lane]
        or not _receipt_pairs(requirement.native_identities)
        or not _receipt_pairs(requirement.run_nonces)
        or not _receipt_pairs(requirement.prerequisites)
        or frozenset(family for family, _identity in requirement.native_identities)
        != requirement.families
        or len(requirement.native_identities) != len(requirement.families)
        or any(not identity for _family, identity in requirement.native_identities)
        or frozenset(family for family, _nonce in requirement.run_nonces)
        != requirement.families
        or len(requirement.run_nonces) != len(requirement.families)
        or any(not nonce for _family, nonce in requirement.run_nonces)
        or any(not name or not identity for name, identity in requirement.prerequisites)
        or len({name for name, _identity in requirement.prerequisites})
        != len(requirement.prerequisites)
    ):
        return ("invalid requirement",)
    families = tuple(receipt.family for receipt in receipts)
    if (
        any(not _receipt_text(family) for family in families)
        or len(set(families)) != len(families)
        or frozenset(families) != requirement.families
    ):
        return ("missing, duplicate or unexpected family",)
    return tuple(
        "invalid receipt: " + receipt.family
        for receipt in receipts
        if (
            not _receipt_text(receipt.capability)
            or not _receipt_text(receipt.host_family)
            or not _receipt_text(receipt.identity)
            or not _receipt_text(receipt.native_identity)
            or not _receipt_text(receipt.nonce)
            or receipt.capability != requirement.capability
            or receipt.family != receipt.host_family
            or not _receipt_host(receipt.host_facts, receipt.family, requirement.lane)
            or receipt.identity != requirement.identity
            or (receipt.family, receipt.native_identity)
            not in requirement.native_identities
            or (receipt.family, receipt.nonce) not in requirement.run_nonces
            or receipt.passed is not True
            or not _receipt_text_set(receipt.tests)
            or not _receipt_text_set(receipt.mutants)
            or not _receipt_text_set(receipt.coverage)
            or not _receipt_pairs(receipt.prerequisites)
            or not _receipt_diagnostics(receipt.diagnostics)
            or not requirement.tests <= receipt.tests
            or not requirement.mutants <= receipt.mutants
            or not requirement.coverage <= receipt.coverage
            or receipt.prerequisites != requirement.prerequisites
        )
    )


def aggregate_receipts(
    groups: tuple[ReceiptGroup, ...],
) -> Result[tuple[ReceiptAggregate, ...], str]:
    """Join current receipts to explicit lower capability prerequisites.

    Requirements, identities and receipt records must be authenticated by the
    caller. This calculation neither reads retained runs nor issues a verdict.
    """
    numbers = tuple(group.number for group in groups)
    capabilities = tuple(group.requirement.capability for group in groups)
    if (
        not groups
        or any(not _receipt_phase_number(number) for number in numbers)
        or numbers != tuple(sorted(set(numbers)))
        or any(not _receipt_text(capability) for capability in capabilities)
        or len(set(capabilities)) != len(capabilities)
    ):
        return Err("invalid receipt group declarations")
    declared = {group.requirement.capability: group for group in groups}
    results: tuple[ReceiptAggregate, ...] = ()
    for group in groups:
        requirement = group.requirement
        invalid = validate_receipts(requirement, group.receipts)
        prerequisites = (
            requirement.prerequisites
            if _receipt_pairs(requirement.prerequisites)
            else frozenset()
        )
        prior = {result.capability: result for result in results}
        failures = frozenset(invalid) | frozenset(
            "invalid prerequisite: " + name
            for name, identity in prerequisites
            if name not in declared
            or declared[name].number >= group.number
            or declared[name].requirement.identity != identity
            or name not in prior
            or bool(prior[name].failures)
        )
        results += (
            ReceiptAggregate(
                group.number, requirement.capability, requirement.identity, failures
            ),
        )
    return Ok(results)


def aggregate_receipt_records(
    groups: tuple[ReceiptRecordGroup, ...],
) -> Result[tuple[ReceiptAggregate, ...], str]:
    """Join canonical records without treating their bytes as run authentication.

    An invalid record fails its capability before prerequisite propagation, so
    an unrelated earlier capability can retain its own independently valid result.
    The caller must authenticate both records and current requirements.
    """
    parsed = tuple(
        tuple(parse_receipt(record) for record in group.records) for group in groups
    )
    invalid = tuple(any(isinstance(item, Err) for item in items) for items in parsed)
    decoded = tuple(
        ReceiptGroup(
            group.number,
            group.requirement,
            () if bad else tuple(item.value for item in items if isinstance(item, Ok)),
        )
        for group, items, bad in zip(groups, parsed, invalid, strict=True)
    )
    joined = aggregate_receipts(decoded)
    if isinstance(joined, Err):
        return joined
    return Ok(
        tuple(
            ReceiptAggregate(
                item.number,
                item.capability,
                item.identity,
                item.failures
                | (frozenset({"invalid receipt record"}) if bad else frozenset()),
            )
            for item, bad in zip(joined.value, invalid, strict=True)
        )
    )


def calculate(
    phases: tuple[PhaseInputs, ...],
    sources: tuple[tuple[str, bytes], ...],
    passed: frozenset[str],
    shared_failures: frozenset[str],
) -> Result[tuple[PhaseResult, ...], str]:
    """Join named checks and recursively hash complete lower input closures.

    This pure calculation assumes callers have authenticated the source census and
    execution observations. It fails closed on ambiguous or absent declarations.
    """
    numbers = tuple(phase.number for phase in phases)
    names = tuple(name for name, _value in sources)
    if (
        not phases
        or numbers != tuple(sorted(set(numbers)))
        or len(names) != len(set(names))
        or any(not name for name in names)
        or any(
            isinstance(phase.number, bool)
            or phase.number < 0
            or not phase.checks
            or not phase.inputs
            or "" in phase.checks
            or "" in phase.inputs
            for phase in phases
        )
        or any(
            isinstance(dependency, bool)
            or dependency >= phase.number
            or dependency not in numbers
            for phase in phases
            for dependency in phase.prerequisites
        )
    ):
        return Err("invalid phase declarations or source census")
    available = dict(sources)
    if any(name not in available for phase in phases for name in phase.inputs):
        return Err("missing declared phase input")
    results: tuple[PhaseResult, ...] = ()
    for phase in phases:
        previous = tuple(
            result for result in results if result.number in phase.prerequisites
        )
        fields = (
            b"agentctl-phase-input-v1",
            str(phase.number).encode("ascii"),
            *(
                value
                for name in sorted(phase.inputs)
                for value in (b"input", name.encode(), available[name])
            ),
            *(
                value
                for check in sorted(phase.checks)
                for value in (b"check", check.encode())
            ),
            *(
                value
                for result in previous
                for value in (
                    b"prerequisite",
                    str(result.number).encode("ascii"),
                    result.identity.encode("ascii"),
                )
            ),
        )
        hashed = hashlib.sha256()
        for value in fields:
            hashed.update(len(value).to_bytes(8, "big"))
            hashed.update(value)
        failures = (
            shared_failures
            | (phase.checks - passed)
            | frozenset(
                "prerequisite:" + str(result.number)
                for result in previous
                if result.failures
            )
        )
        results += (PhaseResult(phase.number, hashed.hexdigest(), failures),)
    return Ok(results)


def calculate_scoped_inputs(
    phases: tuple[PhaseInputs, ...],
    sources: tuple[tuple[str, bytes], ...],
    passed: frozenset[str],
    shared_failures: frozenset[str],
) -> Result[tuple[PhaseResult, ...], str]:
    """Retain earlier identities when a declared later input is absent.

    Input presence is encoded separately from its bytes. This calculation still
    requires an independently authenticated census and ownership declarations.
    """
    names = tuple(name for name, _value in sources)
    if len(names) != len(set(names)):
        return Err("invalid phase declarations or source census")
    available = dict(sources)
    required = frozenset(name for phase in phases for name in phase.inputs)
    missing = required - available.keys()
    marked = tuple((name, b"\x00" + value) for name, value in sources) + tuple(
        (name, b"\x01") for name in sorted(missing)
    )
    base = calculate(phases, marked, passed, shared_failures)
    if isinstance(base, Err):
        return base
    merged: tuple[PhaseResult, ...] = ()
    for phase, result in zip(phases, base.value, strict=True):
        absent = frozenset("missing-input:" + name for name in phase.inputs & missing)
        prerequisites = frozenset(
            "prerequisite:" + str(previous.number)
            for previous in merged
            if previous.number in phase.prerequisites and previous.failures
        )
        merged += (
            PhaseResult(
                result.number, result.identity, result.failures | absent | prerequisites
            ),
        )
    return Ok(merged)


def join_results[A, B](
    first: Result[A, str], second: Result[B, str]
) -> Result[tuple[A, B], str]:
    """Join two results, preserving the first error."""
    if isinstance(first, Err):
        return first
    if isinstance(second, Err):
        return second
    return Ok((first.value, second.value))


def calculate_observed(
    phases: tuple[PhaseInputs, ...],
    sources: tuple[tuple[str, bytes], ...],
    passed: frozenset[str],
    shared_failures: frozenset[str],
    collection: tuple[tuple[CollectionScope, ...], CollectionObservation]
    | tuple[
        tuple[CollectionScope, ...],
        CollectionObservation,
        tuple[tuple[str, int], ...],
    ]
    | tuple[
        tuple[CollectionScope, ...],
        CollectionObservation,
        tuple[tuple[str, int], ...],
        tuple[tuple[int, frozenset[str]], ...],
    ],
) -> Result[tuple[PhaseResult, ...], str]:
    """Join attributed collection failures into prerequisite-aware verdicts.

    This calculation does not authenticate the supplied observations, census or
    optional complete mutation ownership mapping.
    """
    scopes, observation = collection[:2]
    if frozenset(scope.number for scope in scopes) != frozenset(
        phase.number for phase in phases
    ):
        return Err("phase and collection scopes differ")
    ownership_failures = (
        collection[3]
        if len(collection) == SCOPED_COLLECTION_FIELDS
        else tuple((phase.number, frozenset[str]()) for phase in phases)
    )
    numbers = tuple(number for number, _failures in ownership_failures)
    if (
        len(numbers) != len(set(numbers))
        or any(isinstance(number, bool) for number in numbers)
        or frozenset(numbers) != frozenset(phase.number for phase in phases)
        or any("" in failures for _number, failures in ownership_failures)
    ):
        return Err("invalid scoped ownership failures")
    base = calculate_scoped_inputs(phases, sources, passed, shared_failures)
    collections = collection_failures(scopes, observation)
    if len(collection) == ATTRIBUTED_COLLECTION_FIELDS:
        collections = collection_failures(
            scopes, observation, mutation_owners=collection[2]
        )
    if len(collection) == SCOPED_COLLECTION_FIELDS:
        collections = collection_failures(
            scopes, observation, mutation_owners=collection[2]
        )
    match join_results(base, collections):
        case Err(error):
            return Err(error)
        case joined:
            results, failures = joined.value
            collection_by_phase = dict(failures)
            ownership_by_phase = dict(ownership_failures)
            merged: tuple[PhaseResult, ...] = ()
            for phase, result in zip(phases, results, strict=True):
                prerequisite_failures = frozenset(
                    "prerequisite:" + str(previous.number)
                    for previous in merged
                    if previous.number in phase.prerequisites and previous.failures
                )
                merged += (
                    PhaseResult(
                        result.number,
                        result.identity,
                        result.failures
                        | collection_by_phase[result.number]
                        | ownership_by_phase[result.number]
                        | prerequisite_failures,
                    ),
                )
            return Ok(merged)


def join_additional_failures(
    phases: tuple[PhaseInputs, ...],
    results: tuple[PhaseResult, ...],
    observations: AdditionalFailures,
) -> Result[tuple[PhaseResult, ...], str]:
    """Join complete native and oracle attribution and propagate prerequisites.

    The caller must authenticate the result identities and all observations;
    this pure join cannot itself issue a closure verdict.
    """
    numbers = tuple(phase.number for phase in phases)
    if (
        not phases
        or numbers != tuple(sorted(set(numbers)))
        or any(isinstance(number, bool) for number in numbers)
        or tuple(result.number for result in results) != numbers
        or any(isinstance(result.number, bool) for result in results)
        or any(
            re.fullmatch(r"[0-9a-f]{64}", result.identity) is None
            or "" in result.failures
            for result in results
        )
        or any(
            isinstance(dependency, bool)
            or dependency not in numbers
            or dependency >= phase.number
            for phase in phases
            for dependency in phase.prerequisites
        )
    ):
        return Err("invalid phase results")
    for values in (observations.native, observations.oracle):
        owners = tuple(number for number, _failures in values)
        if (
            len(set(owners)) != len(owners)
            or any(isinstance(owner, bool) for owner in owners)
            or frozenset(owners) != frozenset(numbers)
            or any("" in failures for _number, failures in values)
        ):
            return Err("incomplete or ambiguous attributed failures")
    native, oracle = dict(observations.native), dict(observations.oracle)
    merged: tuple[PhaseResult, ...] = ()
    for phase, result in zip(phases, results, strict=True):
        prerequisites = frozenset(
            "prerequisite:" + str(previous.number)
            for previous in merged
            if previous.number in phase.prerequisites and previous.failures
        )
        merged += (
            PhaseResult(
                result.number,
                result.identity,
                result.failures
                | native[result.number]
                | oracle[result.number]
                | prerequisites,
            ),
        )
    return Ok(merged)
