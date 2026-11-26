# Copyright (c) 2026 agentctl contributors.
"""Refusal branches of the ownership joins, guards and manifest decoders."""

import hashlib
from pathlib import Path

import pytest

from agentctl.check import ownership
from agentctl.check.evidence import Entry, source_census
from agentctl.check.mutants import Mutant, Operator
from agentctl.check.ownership import (
    MutantOwnership,
    attribute_mutant_claims,
    bind_census,
    case_consumers,
    census_link_targets,
    census_link_targets_match_guard,
    census_matches_guard,
    guarded_census,
    parse_manifest,
    partial_claim_problems,
    phase_work,
    scoped_phase_work,
)
from agentctl.check.phase_reports import CollectionScope
from agentctl.check.writeguard import FileFact, tree
from agentctl.result import Err, Ok

pytestmark = pytest.mark.evidence("value")

MANIFEST_TEXT = (
    "version = 1\n"
    "[[phases]]\nnumber = 0\nprerequisites = []\n"
    "[[phases]]\nnumber = 1\nprerequisites = [0]\n"
    '[[artifacts]]\npath = "src/a.py"\ncapability = "core"\n'
    "owner = 0\nconsumers = [0, 1]\nrequired = true\n"
    '[[artifacts]]\npath = "tests/test_a.py"\ncapability = "core"\n'
    "owner = 0\nconsumers = [0, 1]\nrequired = true\n"
)
SOURCE = Entry("src/a.py", "file", (b"x",))
TEST = Entry("tests/test_a.py", "file", (b"t",))
BROKEN = Entry("src/a.py", "file", (b"x", b"y"))
IDENTIFIER = "M-test-example"
KILLER = "tests/test_a.py::test_kills"
CHECKS = ((0, frozenset({"c"})), (1, frozenset({"c"})))
BAD_CHECKS = ((0, frozenset({"c"})),)
EXPECTED_CONSUMER_ERROR = "test consumer lacks an owned source module"


def _manifest() -> ownership.OwnershipManifest:
    parsed = parse_manifest(MANIFEST_TEXT)
    assert isinstance(parsed, Ok)
    return parsed.value


def _mutant() -> Mutant:
    return Mutant(IDENTIFIER, Operator.NEGATE, "src/a.py", "x", "y", (KILLER,), "why")


def _fact(entry: Entry) -> FileFact:
    payload = entry.payloads[0]
    return FileFact(
        entry.path, "file", len(payload), 0, hashlib.sha256(payload).hexdigest()
    )


ROOT_FACT = FileFact(".", "directory", 0, 0, "")


def test_case_consumers_require_a_node_in_an_owned_module() -> None:
    """A cited case needs a node separator and a module in its phase scope."""
    modules = frozenset({"tests/test_a.py"})
    for node in ("tests/test_a.py", "tests/other.py::test_x"):
        scope = CollectionScope(0, frozenset({node}), modules)
        assert case_consumers((scope,), (), ()) == Err(EXPECTED_CONSUMER_ERROR)
    scope = CollectionScope(0, frozenset({KILLER}), modules)
    assert case_consumers((scope,), (), ()) == Ok(((KILLER, frozenset({0})),))


def test_partial_claims_report_unknown_corpus_records() -> None:
    """A claim naming a mutant absent from the corpus is a problem."""
    claim = MutantOwnership(IDENTIFIER, 0, ((KILLER, "tests/test_a.py"),))
    assert partial_claim_problems(_manifest(), (SOURCE, TEST), (), (claim,)) == (
        "claim has no corpus record: " + IDENTIFIER,
    )


def test_attribution_refuses_malformed_entries() -> None:
    """An entry with the wrong payload shape stops mutant attribution."""
    claim = MutantOwnership(IDENTIFIER, 0, ((KILLER, "tests/test_a.py"),))
    result = attribute_mutant_claims(
        _manifest(), (BROKEN, TEST), (_mutant(),), (claim,)
    )
    assert result == Err("invalid source entry")


def test_census_guard_comparison_refuses_malformed_entries() -> None:
    """The guard comparison reports entries that cannot be encoded."""
    facts = (ROOT_FACT, _fact(SOURCE))
    assert census_matches_guard((BROKEN,), facts) == Err("invalid source entry")
    assert census_matches_guard((SOURCE,), facts) == Ok(None)


def test_link_mapping_refuses_duplicate_guard_paths() -> None:
    """Duplicate guard facts make link target lookup ambiguous."""
    facts = (_fact(SOURCE), _fact(SOURCE))
    assert census_link_targets_match_guard((), facts, ()) == Err(
        "duplicate write guard paths"
    )


def test_link_targets_refuse_unresolvable_and_escaping_links(tmp_path: Path) -> None:
    """Dangling links and links leaving the root are refused with their cause."""
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_bytes(b"o")
    (root / "dangling").symlink_to("missing.txt")
    (root / "escape").symlink_to(outside)
    for name in ("dangling", "escape"):
        entry = Entry(name, "symlink", (b"t", b"o"))
        result = census_link_targets(root, (entry,))
        assert isinstance(result, Err)
        assert result.error.startswith("cannot resolve source census link: ")


def test_guard_links_refuse_unresolvable_and_changed_trees(tmp_path: Path) -> None:
    """Link verification stops on resolution failure and on tree movement."""
    guard_links = ownership.__dict__["_guard_links"]
    (tmp_path / "dangling").symlink_to("missing.txt")
    dangling = Entry("dangling", "symlink", (b"missing.txt", b""))
    unresolved = guard_links(tmp_path, (dangling,), ())
    assert isinstance(unresolved, Err)
    assert unresolved.error.startswith("cannot resolve source census link: ")
    (tmp_path / "target.txt").write_bytes(b"hi")
    (tmp_path / "link").symlink_to("target.txt")
    link = Entry("link", "symlink", (b"target.txt", b"hi"))
    target = FileFact("target.txt", "file", 2, 0, hashlib.sha256(b"hi").hexdigest())
    assert guard_links(tmp_path, (link,), (target,)) == Err(
        "checkout changed during source link observation"
    )
    observed = tree(tmp_path)
    assert isinstance(observed, Ok)
    assert guard_links(tmp_path, (link,), observed.value) == Ok((link,))


def test_guarded_census_detects_changes_during_the_census(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Concurrent writes and census/guard disagreement are refusals."""
    (tmp_path / "a.txt").write_bytes(b"a")

    def writing(root: Path) -> object:
        observed = source_census(root)
        (root / "late.txt").write_bytes(b"late")
        return observed

    def altered(root: Path) -> object:
        observed = source_census(root)
        assert isinstance(observed, Ok)
        return Ok(tuple(Entry(e.path, e.kind, (b"z",)) for e in observed.value))

    with monkeypatch.context() as patch:
        patch.setattr(ownership, "source_census", writing)
        assert guarded_census(tmp_path) == Err("checkout changed during source census")
    with monkeypatch.context() as patch:
        patch.setattr(ownership, "source_census", altered)
        refused = guarded_census(tmp_path)
    assert isinstance(refused, Err)
    assert refused.error.startswith("source census and guard entry differ: ")


def test_phase_work_refuses_unowned_census_paths() -> None:
    """Binding the census fails before assignments are joined."""
    stray = Entry("stray.py", "file", (b"s",))
    assert isinstance(bind_census(_manifest(), (SOURCE, TEST, stray)), Err)
    result = phase_work(_manifest(), (SOURCE, TEST, stray), CHECKS)
    assert result == Err("unowned source artifact: stray.py")


def test_scoped_phase_work_refuses_bad_assignments_and_entries() -> None:
    """Scoped work validates its check assignments and every source entry."""
    assert scoped_phase_work(_manifest(), (SOURCE, TEST), BAD_CHECKS) == Err(
        "invalid phase check assignments"
    )
    assert scoped_phase_work(_manifest(), (BROKEN, TEST), CHECKS) == Err(
        "invalid source entry"
    )


def test_manifest_phase_lists_refuse_bad_members() -> None:
    """Phase lists reject invalid members, non-lists and duplicates."""
    text = MANIFEST_TEXT.replace("prerequisites = [0]", "prerequisites = [-1]")
    assert parse_manifest(text) == Err("invalid ownership manifest")
    numbers = ownership.__dict__["_numbers"]
    assert numbers([-1]) == Err("invalid phase list")
    assert numbers([True]) == Err("invalid phase list")
    assert numbers([1, 1]) == Err("duplicate phase")
    assert numbers("x") == Err("expected phase list")
    assert numbers([2, 1]) == Ok(frozenset({1, 2}))


def test_guard_comparison_refuses_path_differences() -> None:
    """Census and guard must name exactly the same non-root paths."""
    assert census_matches_guard((SOURCE,), (ROOT_FACT,)) == Err(
        "source census and guard paths differ"
    )


def test_link_target_guard_refuses_unmapped_and_changed_targets() -> None:
    """Links need an exact mapping to a guarded file with matching bytes."""
    link = Entry("link", "symlink", (b"target.txt", b"hi"))
    unmapped = census_link_targets_match_guard((link,), (), ())
    assert unmapped == Err("source census link target mapping differs")
    changed = FileFact("target.txt", "file", 2, 0, hashlib.sha256(b"no").hexdigest())
    mapped = (("link", "target.txt"),)
    assert census_link_targets_match_guard((link,), (changed,), mapped) == Err(
        "source census link target differs: link"
    )


def test_guard_links_report_target_mismatch(tmp_path: Path) -> None:
    """A resolvable link whose guarded target differs is refused."""
    (tmp_path / "target.txt").write_bytes(b"hi")
    (tmp_path / "link").symlink_to("target.txt")
    link = Entry("link", "symlink", (b"target.txt", b"hi"))
    refused = ownership.__dict__["_guard_links"](tmp_path, (link,), ())
    assert refused == Err("source census link target differs: link")


def test_guarded_census_refuses_foreign_and_unreadable_roots(tmp_path: Path) -> None:
    """The original guard and root readability are both checked."""
    (tmp_path / "a.txt").write_bytes(b"a")
    foreign = (FileFact("other", "file", 0, 0, ""),)
    assert guarded_census(tmp_path, expected=foreign) == Err(
        "source census differs from original write guard"
    )
    assert guarded_census(tmp_path / "absent") == Err(
        "unable to read source census and guard snapshots"
    )


def test_manifest_phase_record_must_match_the_grammar() -> None:
    """A phase record with an extra field is not a phase."""
    text = MANIFEST_TEXT.replace(
        "number = 1\nprerequisites = [0]", "number = 1\nprerequisites = [0]\nextra = 1"
    )
    assert parse_manifest(text) == Err("invalid ownership manifest")
