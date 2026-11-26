# Copyright (c) 2026 agentctl contributors.
"""Structural boundary for explicit phase and artifact ownership declarations."""

import hashlib
import re
import tomllib
from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import Path, PurePosixPath

from agentctl.check.evidence import (
    SYMLINK_PAYLOADS,
    Entry,
    OracleDetails,
    source_census,
)
from agentctl.check.mutants import Mutant
from agentctl.check.phase_reports import (
    ArtifactOwnership,
    CollectionScope,
    OwnershipPhase,
    PhaseInputs,
    ownership_inputs,
)
from agentctl.check.writeguard import FileFact, tree
from agentctl.foundation import Err, Ok, Result

type TomlValue = (
    str
    | int
    | float
    | bool
    | date
    | datetime
    | time
    | list[TomlValue]
    | dict[str, TomlValue]
)


@dataclass(frozen=True, slots=True)
class OwnershipManifest:
    """Exact declarations before they are joined to an observed checkout."""

    phases: tuple[OwnershipPhase, ...]
    artifacts: tuple[ArtifactOwnership, ...]


@dataclass(frozen=True, slots=True)
class OwnershipSnapshot:
    """Declared phase inputs bound to observed entry kinds and contents."""

    phase_inputs: tuple[tuple[int, frozenset[str]], ...]
    sources: tuple[tuple[str, bytes], ...]


@dataclass(frozen=True, slots=True)
class PhaseWork:
    """Bound input values and explicitly assigned checks for calculation."""

    phases: tuple[PhaseInputs, ...]
    sources: tuple[tuple[str, bytes], ...]


@dataclass(frozen=True, slots=True)
class ScopedPhaseWork:
    """Phase inputs and missing-source failures, before run authentication."""

    work: PhaseWork
    missing: tuple[tuple[int, frozenset[str]], ...]


@dataclass(frozen=True, slots=True)
class MutantOwnership:
    """Explicit owner and source mapping for each named mutation killer."""

    identifier: str
    owner: int
    killer_sources: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class MutantScope:
    """Ownership failures for one phase, not mutation execution results."""

    number: int
    failures: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ScopedMutantMapping:
    """Declared owners and mandatory phase-local ownership failures."""

    owners: tuple[tuple[str, int], ...]
    scopes: tuple[MutantScope, ...]


@dataclass(frozen=True, slots=True)
class OracleScope:
    """Oracle diagnostics for one consumer, not a phase verdict."""

    number: int
    failures: tuple[str, ...]


def oracle_issue_scopes(
    manifest: OwnershipManifest,
    entries: tuple[Entry, ...],
    details: OracleDetails,
    status: int,
) -> Result[tuple[OracleScope, ...], str]:
    """Attribute oracle issues using the captured files and explicit consumers.

    This calculation does not authenticate the supplied run, source snapshot,
    ownership declarations or tool status and cannot issue a phase verdict.
    """
    paths = tuple(entry.path for entry in entries)
    sources = frozenset(
        entry.path
        for entry in entries
        if PurePosixPath(entry.path).parent == PurePosixPath("tests/oracles")
        and entry.path.endswith(".toml")
    )
    artifacts = {artifact.path: artifact for artifact in manifest.artifacts}
    if (
        len(paths) != len(set(paths))
        or frozenset(details.sources) != sources
        or len(details.sources) != len(sources)
        or any(path not in artifacts for path in sources)
        or any(
            entry.path in sources and entry.kind not in {"file", "symlink"}
            for entry in entries
        )
        or (status == 0) != (not details.issues)
        or any(
            source is not None
            and (
                source not in sources
                or not message.startswith(
                    "oracles.independence: " + PurePosixPath(source).name + ": "
                )
                or "duplicate row id across files" in message
            )
            for source, message in details.issues
        )
    ):
        return Err("oracle details do not match the captured source and status")
    missing = tuple(
        artifact
        for artifact in manifest.artifacts
        if artifact.required
        and PurePosixPath(artifact.path).parent == PurePosixPath("tests/oracles")
        and artifact.path.endswith(".toml")
        and artifact.path not in sources
    )
    return Ok(
        tuple(
            OracleScope(
                phase.number,
                tuple(
                    message
                    for source, message in details.issues
                    if source is None or phase.number in artifacts[source].consumers
                )
                + tuple(
                    "required oracle missing: " + artifact.path
                    for artifact in missing
                    if phase.number in artifact.consumers
                ),
            )
            for phase in manifest.phases
        )
    )


def test_consumer_problems(
    manifest: OwnershipManifest, citations: tuple[tuple[int, str], ...]
) -> tuple[str, ...]:
    """Identify cited Python modules absent from their phase's declared inputs.

    This checks declarations only: collection, execution and native case identity
    must be independently observed before a phase verdict can be issued.
    """
    artifacts = {artifact.path: artifact for artifact in manifest.artifacts}
    numbers = frozenset(phase.number for phase in manifest.phases)
    return tuple(
        sorted(
            {
                f"phase {number}: {node}: test source is unowned or not consumed"
                for number, node in citations
                if number not in numbers
                or not node.startswith("tests/")
                or "::" not in node
                or node.split("::", 1)[0] not in artifacts
                or number not in artifacts[node.split("::", 1)[0]].consumers
            }
        )
    )


def collection_scopes(
    manifest: OwnershipManifest,
    checks: tuple[tuple[int, frozenset[str]], ...],
) -> Result[tuple[CollectionScope, ...], str]:
    """Derive collection consumers from exact test-source declarations.

    This checks declarations only. The caller must still bind the manifest to
    a protected census and authenticate the collection observation.
    """
    numbers = tuple(number for number, _nodes in checks)
    if (
        len(set(numbers)) != len(numbers)
        or frozenset(numbers) != frozenset(phase.number for phase in manifest.phases)
        or any(not nodes for _number, nodes in checks)
        or test_consumer_problems(
            manifest,
            tuple((number, node) for number, nodes in checks for node in nodes),
        )
    ):
        return Err("invalid collection phase assignments")
    assignments = dict(checks)
    scopes = tuple(
        CollectionScope(
            phase.number,
            assignments[phase.number],
            frozenset(
                artifact.path
                for artifact in manifest.artifacts
                if artifact.path.startswith("tests/")
                and artifact.path.endswith(".py")
                and phase.number in artifact.consumers
            ),
        )
        for phase in manifest.phases
    )
    return Ok(scopes)


def case_consumers(
    scopes: tuple[CollectionScope, ...],
    records: tuple[Mutant, ...],
    owners: tuple[tuple[str, int], ...],
) -> Result[tuple[tuple[str, frozenset[int]], ...], str]:
    """Combine cited cases and every Python mutant killer's consumers.

    This is a calculation on declarations, not an authentication of the
    captured corpus, ownership, collection or test execution.
    """
    identifiers = tuple(record.identifier for record in records)
    owner_ids = tuple(identifier for identifier, _owner in owners)
    numbers = tuple(scope.number for scope in scopes)
    if (
        len(identifiers) != len(set(identifiers))
        or len(owner_ids) != len(set(owner_ids))
        or frozenset(identifiers) != frozenset(owner_ids)
        or len(numbers) != len(set(numbers))
        or any(owner not in numbers for _identifier, owner in owners)
    ):
        return Err("incomplete or ambiguous test consumer inputs")
    by_owner = dict(owners)
    declared = tuple(
        (node, scope.number) for scope in scopes for node in scope.required
    )
    killers = tuple(
        (node, by_owner[record.identifier])
        for record in records
        for node in record.killers
        if node.startswith("tests/")
    )
    if any(
        "::" not in node
        or not any(
            scope.number == number and node.split("::", 1)[0] in scope.modules
            for scope in scopes
        )
        for node, number in (*declared, *killers)
    ):
        return Err("test consumer lacks an owned source module")
    pairs = frozenset((*declared, *killers))
    return Ok(
        tuple(
            (node, frozenset(number for case, number in pairs if case == node))
            for node in sorted({case for case, _number in pairs})
        )
    )


def partial_claim_problems(
    manifest: OwnershipManifest,
    entries: tuple[Entry, ...],
    records: tuple[Mutant, ...],
    claims: tuple[MutantOwnership, ...],
) -> tuple[str, ...]:
    """Report inconsistent partial claims without granting a complete verdict."""
    artifacts = {item.path: item for item in manifest.artifacts}
    files = frozenset(entry.path for entry in entries if entry.kind == "file")
    by_id = {record.identifier: record for record in records}
    identifiers = tuple(claim.identifier for claim in claims)
    return tuple(
        sorted(
            frozenset(
                (
                    *(
                        ("duplicate mutant claim",)
                        if len(identifiers) != len(set(identifiers))
                        else ()
                    ),
                    *(
                        ("duplicate mutant record",)
                        if len(by_id) != len(records)
                        else ()
                    ),
                    *(
                        problem
                        for claim in claims
                        for problem in _partial_claim_errors(
                            claim, by_id, artifacts, files
                        )
                    ),
                )
            )
        )
    )


def _partial_claim_errors(
    claim: MutantOwnership,
    records: dict[str, Mutant],
    artifacts: dict[str, ArtifactOwnership],
    files: frozenset[str],
) -> tuple[str, ...]:
    record = records.get(claim.identifier)
    if record is None:
        return ("claim has no corpus record: " + claim.identifier,)
    target = artifacts.get(record.target)
    nodes = tuple(node for node, _path in claim.killer_sources)
    return (
        *(
            ("unverified mutant target owner: " + claim.identifier,)
            if target is None
            or record.target not in files
            or target.owner != claim.owner
            else ()
        ),
        *(
            ("mutant killer declaration mismatch: " + claim.identifier,)
            if len(set(nodes)) != len(nodes)
            or frozenset(nodes) != frozenset(record.killers)
            else ()
        ),
        *(
            problem
            for node, path in claim.killer_sources
            for problem in _partial_killer_errors(
                claim.owner, node, path, artifacts, files
            )
        ),
    )


def _partial_killer_errors(
    owner: int,
    node: str,
    path: str,
    artifacts: dict[str, ArtifactOwnership],
    files: frozenset[str],
) -> tuple[str, ...]:
    if not node.startswith("tests/") or node.split("::", 1)[0] != path:
        return ("unverified killer identity: " + node,)
    if path not in files or path not in artifacts:
        return ("unowned killer source: " + path,)
    return (
        ("killer omits mutant consumer: " + path,)
        if owner not in artifacts[path].consumers
        else ()
    )


def check_phase_claims(
    claims: tuple[MutantOwnership, ...],
    records: tuple[Mutant, ...],
    declared: frozenset[str],
    entries: tuple[Entry, ...],
    phase: int,
) -> Result[None, str]:
    """Compare partial claims with a phase declaration and current files.

    This does not establish source ownership or authorize a phase verdict.
    Native killer-to-source identity remains a separate unmet observation.
    """
    identifiers = tuple(claim.identifier for claim in claims)
    by_id = {record.identifier: record for record in records}
    files = frozenset(entry.path for entry in entries if entry.kind == "file")
    if (
        not declared
        or len(identifiers) != len(set(identifiers))
        or frozenset(identifiers) != declared
        or not declared <= by_id.keys()
        or len(by_id) != len(records)
    ):
        return Err("partial mutant claims do not match phase declarations and corpus")
    for claim in claims:
        record = by_id[claim.identifier]
        nodes = tuple(node for node, _path in claim.killer_sources)
        if (
            claim.owner != phase
            or record.target not in files
            or len(nodes) != len(set(nodes))
            or frozenset(nodes) != frozenset(record.killers)
            or len(nodes) != len(record.killers)
            or any(
                not node.startswith("tests/")
                or node.split("::", 1)[0] != path
                or path not in files
                for node, path in claim.killer_sources
            )
        ):
            return Err("partial mutant claim mismatch: " + claim.identifier)
    return Ok(None)


def bind_mutants(
    manifest: OwnershipManifest,
    entries: tuple[Entry, ...],
    records: tuple[Mutant, ...],
    claims: tuple[MutantOwnership, ...],
) -> Result[tuple[tuple[str, int], ...], str]:
    """Require each real mutant and killer to match explicit source ownership.

    Native case-to-source identity is not yet observed, so native killers are
    refused. This join is not proof that a baseline or mutant was executed.
    """
    match bind_census(manifest, entries):
        case Err(error):
            return Err(error)
    return _bind_mutants_after_census(manifest, entries, records, claims)


def bind_mutants_observed(
    manifest: OwnershipManifest,
    entries: tuple[Entry, ...],
    records: tuple[Mutant, ...],
    claims: tuple[MutantOwnership, ...],
    native_sources: tuple[tuple[str, str], ...],
) -> Result[tuple[tuple[str, int], ...], str]:
    """Join native case-source observations to all explicit mutant claims.

    This calculation does not authenticate the supplied observations or prove
    execution. Callers must independently verify both before any verdict.
    """
    census = bind_census(manifest, entries)
    if isinstance(census, Err):
        return census
    return _bind_observed_after_census(
        manifest, entries, records, claims, native_sources
    )


def bind_mutants_with_missing_inputs(
    manifest: OwnershipManifest,
    entries: tuple[Entry, ...],
    records: tuple[Mutant, ...],
    claims: tuple[MutantOwnership, ...],
    native_sources: tuple[tuple[str, str], ...] | None,
) -> Result[tuple[tuple[str, int], ...], str]:
    """Bind present mutant inputs while keeping other declared absences explicit.

    Missing source bytes are never synthesized. Callers must independently
    attribute every absent required artifact to its consumers before a verdict.
    """
    paths = tuple(entry.path for entry in entries)
    missing = tuple(
        artifact.path
        for artifact in manifest.artifacts
        if artifact.required and artifact.path not in paths
    )
    if not missing:
        return Err("no missing required inputs to scope")
    checked = ownership_inputs(manifest.phases, manifest.artifacts, (*paths, *missing))
    if isinstance(checked, Err):
        return checked
    for entry in entries:
        encoded = _entry_bytes(entry)
        if isinstance(encoded, Err):
            return encoded
    return (
        _bind_mutants_after_census(manifest, entries, records, claims)
        if native_sources is None
        else _bind_observed_after_census(
            manifest, entries, records, claims, native_sources
        )
    )


def _bind_observed_after_census(
    manifest: OwnershipManifest,
    entries: tuple[Entry, ...],
    records: tuple[Mutant, ...],
    claims: tuple[MutantOwnership, ...],
    native_sources: tuple[tuple[str, str], ...],
) -> Result[tuple[tuple[str, int], ...], str]:
    """Bind observed claims after the caller validates the appropriate census."""
    identifiers = tuple(record.identifier for record in records)
    claimed = tuple(claim.identifier for claim in claims)
    native_nodes = tuple(node for node, _path in native_sources)
    if (
        not records
        or len(identifiers) != len(set(identifiers))
        or len(claimed) != len(set(claimed))
        or frozenset(identifiers) != frozenset(claimed)
        or len(native_nodes) != len(set(native_nodes))
        or any(
            re.fullmatch(
                r"haskell:agentctl-core-test/[A-Za-z0-9_-]+/[A-Za-z0-9_-]+", node
            )
            is None
            for node in native_nodes
        )
    ):
        return Err("mutant or native source ownership is incomplete or ambiguous")
    artifacts = {artifact.path: artifact for artifact in manifest.artifacts}
    present = frozenset(entry.path for entry in entries if entry.kind == "file")
    sources = dict(native_sources)
    if any(
        path not in present
        or path not in artifacts
        or re.fullmatch(r"src/agentctl/haskell/test/[A-Za-z0-9_-]+\.hs", path) is None
        for _node, path in native_sources
    ):
        return Err("native case source is missing or unowned")
    by_id = {claim.identifier: claim for claim in claims}
    for record in records:
        claim = by_id[record.identifier]
        target = artifacts.get(record.target)
        killers = tuple(node for node, _path in claim.killer_sources)
        if (
            target is None
            or record.target not in present
            or claim.owner != target.owner
            or len(killers) != len(set(killers))
            or len(record.killers) != len(set(record.killers))
            or frozenset(killers) != frozenset(record.killers)
            or not killers
            or any(
                path not in present
                or path not in artifacts
                or claim.owner not in artifacts[path].consumers
                or not (
                    (node.startswith("tests/") and node.split("::", 1)[0] == path)
                    or (
                        node.startswith("haskell:agentctl-core-test/")
                        and sources.get(node) == path
                    )
                )
                for node, path in claim.killer_sources
            )
        ):
            return Err(
                "mutant target or killer ownership mismatch: " + record.identifier
            )
    return Ok(tuple(sorted((claim.identifier, claim.owner) for claim in claims)))


def _bind_mutants_after_census(
    manifest: OwnershipManifest,
    entries: tuple[Entry, ...],
    records: tuple[Mutant, ...],
    claims: tuple[MutantOwnership, ...],
) -> Result[tuple[tuple[str, int], ...], str]:
    """Join claims after the caller has validated the complete census."""
    identifiers = tuple(record.identifier for record in records)
    claimed = tuple(claim.identifier for claim in claims)
    if (
        not records
        or len(set(identifiers)) != len(identifiers)
        or len(set(claimed)) != len(claimed)
        or frozenset(identifiers) != frozenset(claimed)
    ):
        return Err("mutant ownership is incomplete or ambiguous")
    artifacts = {artifact.path: artifact for artifact in manifest.artifacts}
    present = frozenset(entry.path for entry in entries if entry.kind == "file")
    by_id = {claim.identifier: claim for claim in claims}
    for record in records:
        claim = by_id[record.identifier]
        target = artifacts.get(record.target)
        killers = tuple(node for node, _path in claim.killer_sources)
        if (
            target is None
            or record.target not in present
            or target.owner != claim.owner
            or len(killers) != len(set(killers))
            or len(record.killers) != len(set(record.killers))
            or frozenset(killers) != frozenset(record.killers)
            or not killers
            or any(
                path not in present
                or path not in artifacts
                or claim.owner not in artifacts[path].consumers
                or not node.startswith("tests/")
                or node.split("::", 1)[0] != path
                for node, path in claim.killer_sources
            )
        ):
            return Err(
                "mutant target or killer ownership mismatch: " + record.identifier
            )
    return Ok(tuple(sorted((claim.identifier, claim.owner) for claim in claims)))


def attribute_mutant_claims(
    manifest: OwnershipManifest,
    entries: tuple[Entry, ...],
    records: tuple[Mutant, ...],
    claims: tuple[MutantOwnership, ...],
    native_sources: tuple[tuple[str, str], ...] | None = None,
) -> Result[tuple[MutantScope, ...], str]:
    """Attribute known killer failures after validating declared target ownership.

    An absent claim fails its independently established target owner. Unknown or
    conflicting target ownership remains shared damage. A native killer without
    source identity fails its owner; it is not a mutation execution. Observed
    sources are supplied separately and do not authenticate themselves.
    """
    paths = tuple(entry.path for entry in entries)
    missing = tuple(
        artifact
        for artifact in manifest.artifacts
        if artifact.required and artifact.path not in paths
    )
    checked = ownership_inputs(
        manifest.phases, manifest.artifacts, (*paths, *(item.path for item in missing))
    )
    if isinstance(checked, Err):
        return checked
    for entry in entries:
        encoded = _entry_bytes(entry)
        if isinstance(encoded, Err):
            return encoded
    identifiers = tuple(record.identifier for record in records)
    claim_ids = tuple(claim.identifier for claim in claims)
    if (
        not records
        or len(set(identifiers)) != len(identifiers)
        or len(set(claim_ids)) != len(claim_ids)
        or not frozenset(claim_ids) <= frozenset(identifiers)
    ):
        return Err("mutant ownership is incomplete or ambiguous")
    if native_sources is not None and len({node for node, _ in native_sources}) != len(
        native_sources
    ):
        return Err("native source ownership is ambiguous")
    by_id = {claim.identifier: claim for claim in claims}
    artifacts = {artifact.path: artifact for artifact in manifest.artifacts}
    if any(
        record.target not in artifacts
        or (
            record.identifier in by_id
            and artifacts[record.target].owner != by_id[record.identifier].owner
        )
        for record in records
    ):
        return Err("mutant target ownership is missing or ambiguous")
    outcomes: tuple[tuple[int, str], ...] = tuple(
        (consumer, "required source artifact missing: " + artifact.path)
        for artifact in missing
        for consumer in sorted(artifact.consumers)
    )
    for record in records:
        if record.identifier not in by_id:
            outcomes += (
                (
                    artifacts[record.target].owner,
                    "missing mutant claim: " + record.identifier,
                ),
            )
            continue
        claim = by_id[record.identifier]
        checked_claim = (
            _bind_mutants_after_census(manifest, entries, (record,), (claim,))
            if native_sources is None
            else _bind_observed_after_census(
                manifest,
                entries,
                (record,),
                (claim,),
                tuple(item for item in native_sources if item[0] in record.killers),
            )
        )
        match checked_claim:
            case Err(error):
                outcomes += ((claim.owner, error),)
    return Ok(
        tuple(
            MutantScope(
                phase.number,
                tuple(error for owner, error in outcomes if owner == phase.number),
            )
            for phase in manifest.phases
        )
    )


def scoped_mutant_mapping(
    manifest: OwnershipManifest,
    entries: tuple[Entry, ...],
    records: tuple[Mutant, ...],
    claims: tuple[MutantOwnership, ...],
    native_sources: tuple[tuple[str, str], ...] | None = None,
) -> Result[ScopedMutantMapping, str]:
    """Derive declared owners together with all mandatory unresolved failures.

    This mapping is provisional; every returned failure must be joined to its
    phase before the mapping can contribute to any authenticated result.
    """
    scoped = attribute_mutant_claims(manifest, entries, records, claims, native_sources)
    if isinstance(scoped, Err):
        return scoped
    artifacts = {artifact.path: artifact for artifact in manifest.artifacts}
    files = frozenset(entry.path for entry in entries if entry.kind == "file")
    if native_sources is not None and any(
        path not in files
        or path not in artifacts
        or re.fullmatch(r"src/agentctl/haskell/test/[A-Za-z0-9_-]+\.hs", path) is None
        or re.fullmatch(
            r"haskell:agentctl-core-test/[A-Za-z0-9_-]+/[A-Za-z0-9_-]+", node
        )
        is None
        for node, path in native_sources
    ):
        return Err("native source ownership is invalid")
    return Ok(
        ScopedMutantMapping(
            tuple(
                sorted(
                    (record.identifier, artifacts[record.target].owner)
                    for record in records
                )
            ),
            scoped.value,
        )
    )


def census_matches_guard(
    entries: tuple[Entry, ...], facts: tuple[FileFact, ...]
) -> Result[None, str]:
    """Compare independently collected entry kinds and bytes to the guard tree.

    This comparison is not a replacement for pre/post write-guard snapshots.
    """
    roots = tuple(fact for fact in facts if fact.path == ".")
    observed = tuple(fact for fact in facts if fact.path != ".")
    if (
        len(roots) != 1
        or roots[0].kind != "directory"
        or len({entry.path for entry in entries}) != len(entries)
        or len({fact.path for fact in observed}) != len(observed)
        or frozenset(entry.path for entry in entries)
        != frozenset(fact.path for fact in observed)
    ):
        return Err("source census and guard paths differ")
    by_path = {fact.path: fact for fact in observed}
    for entry in entries:
        match _entry_bytes(entry):
            case Err(error):
                return Err(error)
        fact = by_path[entry.path]
        payload = entry.payloads[0]
        if (
            fact.kind != entry.kind
            or fact.size != len(payload)
            or fact.digest != hashlib.sha256(payload).hexdigest()
        ):
            return Err("source census and guard entry differ: " + entry.path)
    return Ok(None)


def census_link_targets_match_guard(
    entries: tuple[Entry, ...],
    facts: tuple[FileFact, ...],
    targets: tuple[tuple[str, str], ...],
) -> Result[None, str]:
    """Bind captured link target bytes to their exact guarded file paths."""
    links = tuple(entry for entry in entries if entry.kind == "symlink")
    names = tuple(name for name, _target in targets)
    if len(names) != len(set(names)) or frozenset(names) != frozenset(
        entry.path for entry in links
    ):
        return Err("source census link target mapping differs")
    by_path = {fact.path: fact for fact in facts}
    if len(by_path) != len(facts):
        return Err("duplicate write guard paths")
    mapped = dict(targets)
    for entry in links:
        target = by_path.get(mapped[entry.path])
        if (
            len(entry.payloads) != SYMLINK_PAYLOADS
            or target is None
            or target.kind != "file"
            or target.size != len(entry.payloads[1])
            or target.digest != hashlib.sha256(entry.payloads[1]).hexdigest()
        ):
            return Err("source census link target differs: " + entry.path)
    return Ok(None)


def census_link_targets(
    root: Path, entries: tuple[Entry, ...]
) -> Result[tuple[tuple[str, str], ...], str]:
    """Resolve source links to guarded checkout paths without accepting escapes."""
    try:
        base = root.resolve(strict=True)
        targets = tuple(
            (
                entry.path,
                (base / entry.path).resolve(strict=True).relative_to(base).as_posix(),
            )
            for entry in entries
            if entry.kind == "symlink"
        )
    except (OSError, RuntimeError, ValueError) as exc:
        return Err("cannot resolve source census link: " + str(exc))
    return Ok(targets)


def _guard_links(
    root: Path, entries: tuple[Entry, ...], facts: tuple[FileFact, ...]
) -> Result[tuple[Entry, ...], str]:
    """Verify link target contents and recheck the tree after resolution."""
    targets = census_link_targets(root, entries)
    if isinstance(targets, Err):
        return targets
    checked = census_link_targets_match_guard(entries, facts, targets.value)
    if isinstance(checked, Err):
        return checked
    if targets.value:
        after_links = tree(root)
        if isinstance(after_links, Err) or after_links.value != facts:
            return Err("checkout changed during source link observation")
    return Ok(entries)


def guarded_census(
    root: Path, *, expected: tuple[FileFact, ...] | None = None
) -> Result[tuple[Entry, ...], str]:
    """Compare the full census with surrounding and optional original snapshots."""
    before = tree(root)
    observed = source_census(root)
    after = tree(root)
    match before, observed, after:
        case Ok(first), Ok(entries), Ok(last):
            if expected is not None and first != expected:
                return Err("source census differs from original write guard")
            if first != last:
                return Err("checkout changed during source census")
            matched = census_matches_guard(entries, first)
            if isinstance(matched, Err):
                return matched
            return _guard_links(root, entries, first)
        case _:
            return Err("unable to read source census and guard snapshots")


def _entry_bytes(entry: Entry) -> Result[bytes, str]:
    """Encode the entry without ambiguity between kinds or payload fields."""
    match entry.kind, entry.payloads:
        case "file", (bytes(),):
            pass
        case "directory", (b"",):
            pass
        case "symlink", (bytes(), bytes()):
            pass
        case _:
            return Err("invalid source entry")
    fields = (entry.kind.encode("ascii"), *entry.payloads)
    return Ok(b"".join(len(field).to_bytes(8, "big") + field for field in fields))


def bind_census(
    manifest: OwnershipManifest, entries: tuple[Entry, ...]
) -> Result[OwnershipSnapshot, str]:
    """Bind declarations to census values; this does not issue a gate receipt."""
    inputs = ownership_inputs(
        manifest.phases, manifest.artifacts, tuple(entry.path for entry in entries)
    )
    if isinstance(inputs, Err):
        return inputs
    sources: tuple[tuple[str, bytes], ...] = ()
    for entry in sorted(entries):
        payload = _entry_bytes(entry)
        if isinstance(payload, Err):
            return payload
        sources += ((entry.path, payload.value),)
    return Ok(OwnershipSnapshot(inputs.value, sources))


def phase_work(
    manifest: OwnershipManifest,
    entries: tuple[Entry, ...],
    checks: tuple[tuple[int, frozenset[str]], ...],
) -> Result[PhaseWork, str]:
    """Join the observed census and exact check assignments to declared phases.

    The caller still has to authenticate the snapshot and actual check outcomes.
    """
    numbers = tuple(number for number, _checks in checks)
    if (
        len(numbers) != len(set(numbers))
        or frozenset(numbers) != frozenset(phase.number for phase in manifest.phases)
        or any(not assigned or "" in assigned for _number, assigned in checks)
    ):
        return Err("invalid phase check assignments")
    bound = bind_census(manifest, entries)
    if isinstance(bound, Err):
        return bound
    input_map = dict(bound.value.phase_inputs)
    check_map = dict(checks)
    return Ok(
        PhaseWork(
            tuple(
                PhaseInputs(
                    phase.number,
                    input_map[phase.number],
                    check_map[phase.number],
                    phase.prerequisites,
                )
                for phase in manifest.phases
            ),
            bound.value.sources,
        )
    )


def scoped_phase_work(
    manifest: OwnershipManifest,
    entries: tuple[Entry, ...],
    checks: tuple[tuple[int, frozenset[str]], ...],
) -> Result[ScopedPhaseWork, str]:
    """Preserve earlier phase identities when only later required inputs are absent.

    Missing entries remain absent from the source values while their declared
    paths remain phase inputs. The observations still require authentication.
    """
    paths = tuple(entry.path for entry in entries)
    missing = tuple(
        artifact
        for artifact in manifest.artifacts
        if artifact.required and artifact.path not in paths
    )
    inputs = ownership_inputs(
        manifest.phases,
        manifest.artifacts,
        (*paths, *(artifact.path for artifact in missing)),
    )
    if isinstance(inputs, Err):
        return inputs
    numbers = tuple(number for number, _checks in checks)
    if (
        len(numbers) != len(set(numbers))
        or frozenset(numbers) != frozenset(phase.number for phase in manifest.phases)
        or any(not assigned or "" in assigned for _number, assigned in checks)
    ):
        return Err("invalid phase check assignments")
    encoded: tuple[tuple[str, bytes], ...] = ()
    for entry in sorted(entries):
        value = _entry_bytes(entry)
        if isinstance(value, Err):
            return value
        encoded += ((entry.path, value.value),)
    input_map = dict(inputs.value)
    check_map = dict(checks)
    return Ok(
        ScopedPhaseWork(
            PhaseWork(
                tuple(
                    PhaseInputs(
                        phase.number,
                        input_map[phase.number],
                        check_map[phase.number],
                        phase.prerequisites,
                    )
                    for phase in manifest.phases
                ),
                tuple(sorted(encoded)),
            ),
            tuple(
                (
                    phase.number,
                    frozenset(
                        "required source artifact missing: " + artifact.path
                        for artifact in missing
                        if phase.number in artifact.consumers
                    ),
                )
                for phase in manifest.phases
            ),
        )
    )


def _natural(value: TomlValue) -> Result[int, str]:
    """Accept nonnegative integers, never TOML booleans as integers."""
    match value:
        case bool():
            return Err("expected nonnegative integer")
        case int() as number if number >= 0:
            return Ok(number)
        case _:
            return Err("expected nonnegative integer")


def _killer_source(value: TomlValue) -> Result[tuple[str, str], str]:
    match value:
        case {"node": str() as node, "path": str() as path, **extra} if (
            not extra and node and path
        ):
            return Ok((node, path))
    return Err("invalid killer source")


def _mutant_claim(value: TomlValue) -> Result[MutantOwnership, str]:
    match value:
        case {
            "identifier": str() as identifier,
            "owner": int() as owner,
            "killer_sources": list() as sources,
            **extra,
        } if not extra:
            number = _natural(owner)
            parsed = tuple(_killer_source(item) for item in sources)
            values = tuple(
                pair for item in parsed for pair in _killer_source_item(item)
            )
            match number:
                case Ok(parsed_owner) if (
                    re.fullmatch(r"M-[a-z]+-[a-z0-9-]+", identifier)
                    and values
                    and len(values) == len(parsed)
                    and len({node for node, _path in values}) == len(values)
                ):
                    return Ok(MutantOwnership(identifier, parsed_owner, values))
    return Err("invalid mutant ownership claim")


def _killer_source_item(
    result: Result[tuple[str, str], str],
) -> tuple[tuple[str, str], ...]:
    return (result.value,) if isinstance(result, Ok) else ()


def parse_mutant_claims(text: str) -> Result[tuple[MutantOwnership, ...], str]:
    """Parse exact ownership claims without treating them as observed records."""
    try:
        value = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        return Err(str(exc))
    match value:
        case {"version": version, "claims": list() as claims, **extra} if not extra:
            parsed = tuple(_mutant_claim(claim) for claim in claims)
            values = tuple(
                claim for item in parsed for claim in _mutant_claim_item(item)
            )
            if (
                _natural(version) == Ok(1)
                and values
                and len(values) == len(parsed)
                and len({claim.identifier for claim in values}) == len(values)
            ):
                return Ok(values)
    return Err("invalid mutant ownership manifest")


def _mutant_claim_item(
    result: Result[MutantOwnership, str],
) -> tuple[MutantOwnership, ...]:
    return (result.value,) if isinstance(result, Ok) else ()


def _numbers(value: TomlValue) -> Result[frozenset[int], str]:
    """Parse an explicit set while refusing duplicate elements."""
    match value:
        case list() as values:
            parsed = tuple(_natural(item) for item in values)
            numbers = tuple(number for item in parsed for number in _number_item(item))
            if len(numbers) != len(parsed):
                return Err("invalid phase list")
            return (
                Ok(frozenset(numbers))
                if len(numbers) == len(set(numbers))
                else Err("duplicate phase")
            )
        case _:
            return Err("expected phase list")


def _number_item(value: Result[int, str]) -> tuple[int, ...]:
    return (value.value,) if isinstance(value, Ok) else ()


def _phase(value: TomlValue) -> Result[OwnershipPhase, str]:
    """Parse the exact phase record grammar."""
    match value:
        case {
            "number": int() as number,
            "prerequisites": list() as prerequisites,
            **extra,
        } if not extra:
            parsed_number = _natural(number)
            parsed_prerequisites = _numbers(prerequisites)
            match parsed_number, parsed_prerequisites:
                case Ok(parsed), Ok(dependencies):
                    return Ok(OwnershipPhase(parsed, dependencies))
    return Err("invalid phase record")


def _artifact(value: TomlValue) -> Result[ArtifactOwnership, str]:
    """Parse one exact artifact declaration with a stable capability name."""
    match value:
        case {
            "path": str() as path,
            "capability": str() as capability,
            "owner": int() as owner,
            "consumers": list() as consumers,
            "required": bool() as required,
            **extra,
        } if not extra:
            parsed_owner = _natural(owner)
            parsed_consumers = _numbers(consumers)
            match parsed_owner, parsed_consumers:
                case Ok(parsed), Ok(uses):
                    return Ok(
                        ArtifactOwnership(path, parsed, uses, required, capability)
                    )
    return Err("invalid artifact record")


def _phase_item(value: Result[OwnershipPhase, str]) -> tuple[OwnershipPhase, ...]:
    return (value.value,) if isinstance(value, Ok) else ()


def _artifact_item(
    value: Result[ArtifactOwnership, str],
) -> tuple[ArtifactOwnership, ...]:
    return (value.value,) if isinstance(value, Ok) else ()


def parse_manifest(text: str) -> Result[OwnershipManifest, str]:
    """Parse the closed manifest and validate declared ownership relationships.

    No declaration counts as an observed source or as a gate receipt.
    """
    try:
        value = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        return Err(str(exc))
    match value:
        case {
            "version": version,
            "phases": list() as phases,
            "artifacts": list() as artifacts,
            **extra,
        } if not extra:
            parsed_version = _natural(version)
            parsed_phases = tuple(_phase(item) for item in phases)
            parsed_artifacts = tuple(_artifact(item) for item in artifacts)
            phase_values = tuple(
                phase for item in parsed_phases for phase in _phase_item(item)
            )
            artifact_values = tuple(
                artifact
                for item in parsed_artifacts
                for artifact in _artifact_item(item)
            )
            if (
                parsed_version != Ok(1)
                or len(phase_values) != len(parsed_phases)
                or len(artifact_values) != len(parsed_artifacts)
            ):
                return Err("invalid ownership manifest")
            result = OwnershipManifest(
                phase_values,
                artifact_values,
            )
            required = tuple(item.path for item in result.artifacts if item.required)
            checked = ownership_inputs(result.phases, result.artifacts, required)
            if isinstance(checked, Err):
                return checked
            return Ok(result)
    return Err("invalid ownership manifest fields")


def read_manifest(path: Path) -> Result[OwnershipManifest, str]:
    """Read the declared manifest without manufacturing a missing file."""
    try:
        return parse_manifest(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError) as exc:
        return Err(str(exc))
