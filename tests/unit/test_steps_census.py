# Copyright (c) 2026 agentctl contributors.
"""Census-derived validator inputs refuse absent, invalid or ambiguous entries."""

from pathlib import Path

import pytest

from agentctl.check import steps
from agentctl.check.evidence import Entry, source_census
from agentctl.check.mutants import census_corpus
from agentctl.foundation import Err, Ok

pytestmark = pytest.mark.evidence("value")

MANIFEST = "src/agentctl/check/source_ownership.toml"
PHASE0 = "src/agentctl/check/phase0_mutant_ownership.toml"
FRAGMENT = "src/agentctl/check/governance_mutant_ownership.toml"
STANDARDS = "DEVELOPMENT_PLAN/development_plan_standards.md"
OVERVIEW = "DEVELOPMENT_PLAN/00-overview.md"


def _census(root: Path) -> tuple[Entry, ...]:
    """Observe the live checkout once for a calculation."""
    entries = source_census(root)
    assert isinstance(entries, Ok), entries
    return entries.value


def _without(entries: tuple[Entry, ...], *paths: str) -> tuple[Entry, ...]:
    """Remove the named entries."""
    return tuple(entry for entry in entries if entry.path not in paths)


def _replaced(
    entries: tuple[Entry, ...], path: str, payload: bytes
) -> tuple[Entry, ...]:
    """Replace one regular file's bytes."""
    return tuple(
        Entry(entry.path, entry.kind, (payload,)) if entry.path == path else entry
        for entry in entries
    )


def _without_phases(entries: tuple[Entry, ...]) -> tuple[Entry, ...]:
    """Remove every phase document from the census."""
    return tuple(
        entry
        for entry in entries
        if not entry.path.startswith("DEVELOPMENT_PLAN/phase-")
    )


def test_census_text_requires_one_utf8_regular_file() -> None:
    """Missing, duplicate, non-file and non-UTF-8 declarations are refused."""
    text = steps.__dict__["_census_text"]
    file = Entry("a.toml", "file", (b"ok",))
    assert text((file,), "a.toml") == Ok("ok")
    assert isinstance(text((), "a.toml"), Err)
    assert isinstance(text((file, file), "a.toml"), Err)
    assert isinstance(text((Entry("a.toml", "directory", ()),), "a.toml"), Err)
    assert isinstance(text((Entry("a.toml", "file", (b"\xff",)),), "a.toml"), Err)


def test_phase_declarations_require_phase_documents(root: Path) -> None:
    """Missing or non-phase plan documents yield no phase declarations."""
    entries = _census(root)
    assert isinstance(steps.census_phases(root, entries), Ok)
    assert isinstance(steps.census_phases(root, _without_phases(entries)), Err)
    unparsable = (Entry("DEVELOPMENT_PLAN/phase-x.md", "file", (b"no header",)),)
    assert isinstance(steps.census_phases(root, unparsable), Err)
    linked = (Entry("DEVELOPMENT_PLAN/phase-x.md", "symlink", (b"target",)),)
    assert isinstance(steps.census_phases(root, linked), Err)


def test_claim_and_consumer_validators_report_unreadable_inputs(root: Path) -> None:
    """Each validator names its unreadable or invalid source declaration."""
    entries = _census(root)
    records = census_corpus(entries)
    assert isinstance(records, Ok), records
    assert steps.phase0_claim_problems(root, _without(entries, PHASE0), ()) != ()
    assert steps.phase0_claim_problems(root, _without_phases(entries), ()) != ()
    assert (
        steps.phase0_claim_problems(root, _replaced(entries, PHASE0, b"x = ["), ())
        != ()
    )
    phase0 = "DEVELOPMENT_PLAN/phase-0-governance-and-phase-evidence.md"
    assert steps.phase0_claim_problems(root, _without(entries, phase0), ()) == (
        "validators: missing or duplicate Phase 0 declaration",
    )
    for broken in (_without(entries, MANIFEST), _replaced(entries, MANIFEST, b"x")):
        assert steps.test_consumer_problems(root, broken) != ()
        assert steps.fragment_claim_problems(broken, records.value) != ()
        assert isinstance(steps.complete_mutant_owners(broken, records.value), Err)
        assert isinstance(steps.scoped_source_inputs(broken, ()), Err)
    assert steps.test_consumer_problems(root, _without_phases(entries)) != ()
    for fragment in (_without(entries, FRAGMENT), _replaced(entries, FRAGMENT, b"[")):
        assert steps.fragment_claim_problems(fragment, records.value) != ()
        assert isinstance(steps.provisional_mutant_owners(fragment, records.value), Err)
        assert isinstance(
            steps.observed_native_mutant_owners(fragment, records.value, ()), Err
        )
        assert isinstance(steps.scoped_mutant_ownership(fragment, records.value), Err)


def test_policy_and_collection_scopes_refuse_invalid_inputs(root: Path) -> None:
    """Closure policy and collection scopes need complete, unique inputs."""
    entries = _census(root)
    assert isinstance(steps.census_policy(_without(entries, STANDARDS), None), Err)
    assert isinstance(steps.census_policy(_without(entries, OVERVIEW), None), Err)
    phases = steps.census_phases(root, entries)
    assert isinstance(phases, Ok), phases
    manifest_text = steps.__dict__["_census_text"](entries, MANIFEST)
    assert isinstance(manifest_text, Ok)
    manifest = steps.ownership.parse_manifest(manifest_text.value)
    assert isinstance(manifest, Ok)
    duplicated = (*phases.value, phases.value[0])
    assert steps.diagnostic_collection_scopes(manifest.value, duplicated) == Err(
        "invalid collection phase declarations"
    )
    assert isinstance(steps.scoped_source_inputs(entries, duplicated), Err)


def test_provisional_observation_refusals(root: Path) -> None:
    """Provisional joins refuse missing ownership, owners, nonces and readiness."""
    entries = _census(root)
    phases = steps.census_phases(root, entries)
    assert isinstance(phases, Ok), phases
    run = steps.evidence.RunEvidence(
        "fresh", frozenset(), frozenset(), frozenset(), (), ()
    )
    broken = _without(entries, MANIFEST)
    assert isinstance(
        steps.collection_observations(broken, phases.value, run, "fresh", None), Err
    )
    unowned = steps.collection_observations(entries, phases.value, run, "fresh", None)
    assert unowned == Err("complete mutation ownership unavailable")
    duplicated = (*phases.value, phases.value[0])
    assert isinstance(
        steps.collection_observations(entries, duplicated, run, "fresh", None), Err
    )
    assert steps.report_collection(Err("unavailable")) == 1
    snapshot = steps.NativeSnapshot(run, (), broken)
    assert isinstance(
        steps.native_failure_observations(snapshot, "fresh", phases.value, (), ()), Err
    )
    wrong = steps.NativeSnapshot(run, (), entries)
    assert steps.native_failure_observations(wrong, "fresh", (), (), ()) == Err(
        "native phase declarations differ from ownership"
    )
    owned = steps.provisional_owned_tool_failures
    assert isinstance(owned(entries, (), frozenset(), readiness=("",)), Err)
    assert isinstance(owned(broken, (), frozenset(), readiness=("later",)), Err)
    assert isinstance(
        owned(_replaced(entries, MANIFEST, b"x"), (), frozenset(), readiness=("l",)),
        Err,
    )
    assert isinstance(
        steps.provisional_work_and_tools(broken, phases.value, frozenset(), ()), Err
    )
    assert steps.report_provisional_phases(Err("missing")) == 1
    assert steps.provisional_phase_record("", None) == Err(
        "invalid provisional phase nonce"
    )
    assert steps.provisional_phase_record("fresh", Err("")) == Err(
        "empty provisional phase failure"
    )
    assert steps.provisional_finalizer_failures(Ok(()), ()) == Err(
        "incomplete or ambiguous finalizer observations"
    )
