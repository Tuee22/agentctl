# Copyright (c) 2026 agentctl contributors.
"""Two-sided oracle schema, import, provenance and amendment controls."""

import json
import shutil
from pathlib import Path

import pytest

from tests.harness.oracle import (
    Homes,
    Problem,
    Store,
    Value,
    assert_rows,
    check_tree,
    imports_subject,
    load,
    load_scoped,
    parse,
    read_homes,
    tree_observations,
)

pytestmark = pytest.mark.evidence("value")


def _case(homes: Homes, **changes: object) -> dict[str, object]:
    """Construct a request-anchored independent schema control."""
    return {
        "id": "control.first",
        "requirement": "R20",
        "quote": dict(homes.requirements)["R20"],
        "provenance": "request:R20",
        "input": "value",
        "expected": "value",
        **changes,
    }


def test_quote_must_match_requirement(root: Path) -> None:
    """Reject empty, foreign and altered quotes with a matching control."""
    homes = read_homes(root)
    assert isinstance(parse({"case": [_case(homes)]}, homes), Store)
    for quote in ("", "not in the requirement", dict(homes.requirements)["R2"]):
        assert parse({"case": [_case(homes, quote=quote)]}, homes) == Problem(
            "quote must match its requirement"
        )
    assert check_tree(root) == ()


def test_tree_reports_missing_later_anchor_locally(root: Path, tmp_path: Path) -> None:
    """A later tool anchor failure must not make unrelated rows unreadable."""
    for directory in ("DEVELOPMENT_PLAN", "tests/oracles", "tests/harness"):
        (tmp_path / directory).mkdir(parents=True)
    for name in (
        "DEVELOPMENT_PLAN/00-overview.md",
        "tests/oracles/phase_ownership.toml",
        "tests/oracles/bootstrap_plan.toml",
        "tests/harness/oracle.py",
    ):
        shutil.copyfile(root / name, tmp_path / name)
    problems = check_tree(tmp_path)
    assert any("bootstrap_plan.toml" in problem for problem in problems)
    assert all("phase_ownership.toml" not in problem for problem in problems)
    paths, issues = tree_observations(tmp_path)
    assert "tests/oracles/phase_ownership.toml" in paths
    assert any(
        issue.source == "tests/oracles/bootstrap_plan.toml" for issue in issues
    ), "later oracle failure lost its source"
    assert all(issue.source != "tests/oracles/phase_ownership.toml" for issue in issues)
    shutil.copyfile(
        tmp_path / "tests/oracles/phase_ownership.toml",
        tmp_path / "tests/oracles/phase_copy.toml",
    )
    _, duplicated = tree_observations(tmp_path)
    assert any(
        issue.source is None and "duplicate row id across files" in issue.message
        for issue in duplicated
    ), "cross-file duplicate was localized"


def test_tree_retains_problems_when_loader_unreadable(
    root: Path, tmp_path: Path
) -> None:
    """Missing or invalid loader source cannot hide independently bad rows."""
    for directory in ("DEVELOPMENT_PLAN", "tests/oracles", "tests/harness"):
        (tmp_path / directory).mkdir(parents=True)
    shutil.copyfile(
        root / "DEVELOPMENT_PLAN/00-overview.md",
        tmp_path / "DEVELOPMENT_PLAN/00-overview.md",
    )
    (tmp_path / "tests/oracles/invalid.toml").write_text("", encoding="utf-8")
    loader = tmp_path / "tests/harness/oracle.py"
    for text in (None, "def invalid(:\n"):
        if text is not None:
            loader.write_text(text, encoding="utf-8")
        problems = check_tree(tmp_path)
        assert any("invalid.toml" in problem for problem in problems)
        assert any("cannot inspect loader" in problem for problem in problems)
        _, issues = tree_observations(tmp_path)
        assert any(
            issue.source is None and "cannot inspect loader" in issue.message
            for issue in issues
        ), "loader failure was localized"


def test_duplicate_row_id_rejected(root: Path) -> None:
    """Require distinct ids and preserve both cases of a valid store."""
    homes = read_homes(root)
    assert parse({"case": [_case(homes), _case(homes)]}, homes) == Problem(
        "duplicate row id"
    )
    store = parse({"case": [_case(homes), _case(homes, id="control.second")]}, homes)
    assert isinstance(store, Store)
    assert tuple(row.identifier for row in store.rows) == (
        "control.first",
        "control.second",
    )


def test_loader_imports_no_subject(root: Path) -> None:
    """Reject direct, aliased, relative and dynamic implementation imports."""
    assert not imports_subject("import json\nfrom pathlib import Path\n")
    for source in (
        "import agentctl",
        "import agentctl as subject",
        "from agentctl import cli",
        "from . import agentctl",
        "import importlib\nimportlib.import_module('agentctl')",
        "__import__('agentctl')",
    ):
        assert imports_subject(source), "subject import was accepted"
    assert not imports_subject(
        (root / "tests/harness/oracle.py").read_text(encoding="utf-8")
    )


def test_provenance_resolves(root: Path, tmp_path: Path) -> None:
    """Resolve all source forms and reject unknown ids, versions and facts."""
    homes = read_homes(root)
    version, fact = next(
        (version, fact) for version, fact in homes.tools if version[:1].isdigit()
    )
    for source in ("request:R20", "decision:D-01", f"tool:{version}:{fact}"):
        assert isinstance(
            parse({"case": [_case(homes, provenance=source)]}, homes), Store
        )
    for source in (
        "request:R999",
        "decision:D-999",
        "tool:0.0:unknown",
        f"tool:{version}:invented fact",
        "unknown:R20",
    ):
        assert parse({"case": [_case(homes, provenance=source)]}, homes) == Problem(
            "provenance does not resolve"
        )
    assert isinstance(load(tmp_path / "absent.toml", homes), Problem)
    assert check_tree(root) == ()


def test_scoped_oracle_reads_required_anchors(root: Path, tmp_path: Path) -> None:
    """Read only named anchor families and refuse missing or unknown anchors."""
    plan = tmp_path / "DEVELOPMENT_PLAN"
    plan.mkdir()
    shutil.copyfile(root / "DEVELOPMENT_PLAN/00-overview.md", plan / "00-overview.md")
    original = (root / "tests/oracles/phase_ownership.toml").read_text(encoding="utf-8")
    oracle = tmp_path / "oracle.toml"
    oracle.write_text(original, encoding="utf-8")
    assert isinstance(load_scoped(oracle, tmp_path), Store)
    version, fact = next(
        (version, fact)
        for version, fact in read_homes(root).tools
        if version[:1].isdigit()
    )
    tool_file = tmp_path / "documents/reference/external_tool_facts.md"
    tool_file.parent.mkdir(parents=True)
    shutil.copyfile(root / "documents/reference/external_tool_facts.md", tool_file)
    tool_case = original.replace(
        '"request:R26"', json.dumps(f"tool:{version}:{fact}"), 1
    )
    oracle.write_text(tool_case, encoding="utf-8")
    assert isinstance(load_scoped(oracle, tmp_path), Store), (
        "required tool provenance did not resolve"
    )
    tool_file.unlink()
    oracle.write_text(
        original.replace("request:R26", "tool:missing:fact", 1), encoding="utf-8"
    )
    assert isinstance(load_scoped(oracle, tmp_path), Problem)
    oracle.write_text(
        original.replace("request:R26", "decision:D-01", 1), encoding="utf-8"
    )
    assert isinstance(load_scoped(oracle, tmp_path), Problem)
    oracle.write_text(
        original.replace("request:R26", "unknown:R26", 1), encoding="utf-8"
    )
    assert isinstance(load_scoped(oracle, tmp_path), Problem)


def test_empty_oracle_rejected(root: Path) -> None:
    """Require at least one compared subject application with a live control."""
    homes = read_homes(root)
    assert parse({"case": []}, homes) == Problem("empty oracle")
    assert isinstance(parse({}, homes), Problem)
    store = parse({"case": [_case(homes)]}, homes)
    assert isinstance(store, Store)
    observed: list[Value] = []

    def subject(value: Value) -> Value:
        observed.append(value)
        return value

    assert_rows(subject, store)
    assert tuple(observed) == ("value",)
    with pytest.raises(AssertionError, match="empty oracle"):
        assert_rows(subject, Store((), ()))
    with pytest.raises(AssertionError, match=r"control\.first"):
        assert_rows(lambda _value: "wrong value", store)


def test_amendment_chain_resolves(root: Path) -> None:
    """Select the latest row while retaining each prior row and forbidding cycles."""
    homes = read_homes(root)
    first = _case(homes)
    second = _case(
        homes, id="control.second", amends="control.first", expected="second"
    )
    third = _case(homes, id="control.third", amends="control.second", expected="third")
    store = parse({"case": [first, second, third]}, homes)
    assert isinstance(store, Store)
    assert tuple(row.identifier for row in store.rows) == (
        "control.first",
        "control.second",
        "control.third",
    )
    assert tuple(row.expected for row in store.effective) == ("third",)
    negatives = (
        [{**first, "amends": "control.second"}, second],
        [first, {**second, "amends": "absent"}],
        [first, second, {**third, "amends": "control.first"}],
        [
            first,
            {**second, "requirement": "R2", "quote": dict(homes.requirements)["R2"]},
        ],
    )
    for rows in negatives:
        assert isinstance(parse({"case": rows}, homes), Problem), (
            "invalid amendment chain was accepted"
        )
