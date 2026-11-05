# Copyright (c) 2026 agentctl contributors.
"""Two-sided oracle schema, import, provenance and amendment controls."""

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
    parse,
    read_homes,
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
