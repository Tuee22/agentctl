# Copyright (c) 2026 agentctl contributors.
"""Host-confined coverage declarations and their report arguments."""

import json
from dataclasses import replace
from pathlib import Path, PurePosixPath

import pytest

from agentctl.check import coverage_hosts
from agentctl.check.evidence import source_census
from agentctl.check.legs import coverage_commands
from agentctl.check.steps import coverage_foreign, coverage_host_problems
from agentctl.foundation import Err, Ok

pytestmark = pytest.mark.evidence("value")

VALID = """version = 1

[[source]]
path = "src/agentctl/check/native_only.py"
hosts = ["Windows"]

[[source]]
path = "src/agentctl/check/guest_only.py"
hosts = ["WSL"]

[[source]]
path = "src/agentctl/check/posix.py"
hosts = ["Linux", "Darwin"]
"""

HEADER = "version = 1\n"
ENTRY = "[[source]]\npath = 'src/agentctl/a.py'\n"
INVALID = [
    "version = [",
    "version = 2\n" + ENTRY + "hosts = ['Linux']\n",
    "version = true\n" + ENTRY + "hosts = ['Linux']\n",
    "version = 1.0\n" + ENTRY + "hosts = ['Linux']\n",
    HEADER + "source = []\n",
    HEADER + "extra = 1\n" + ENTRY + "hosts = ['Linux']\n",
    HEADER + "[[source]]\npath = 'tests/a.py'\nhosts = ['Linux']\n",
    HEADER + "[[source]]\npath = 'src/agentctl/../a.py'\nhosts = ['Linux']\n",
    HEADER + ENTRY + "hosts = []\n",
    HEADER + ENTRY + "hosts = ['Solaris']\n",
    HEADER + ENTRY + "hosts = ['Linux', 'Linux']\n",
    HEADER + ENTRY + "hosts = ['Linux']\nextra = 1\n",
    HEADER + ENTRY + "hosts = ['Linux']\n" + ENTRY + "hosts = ['Windows']\n",
]


def test_foreign_sources_follow_declared_hosts() -> None:
    """Each family omits exactly the declared sources it cannot execute."""
    parsed = coverage_hosts.parse(VALID)
    assert isinstance(parsed, Ok), parsed
    assert coverage_hosts.foreign(parsed.value, "Linux") == (
        "src/agentctl/check/guest_only.py",
        "src/agentctl/check/native_only.py",
    ), "declared source omitted on its own host"
    assert coverage_hosts.foreign(parsed.value, "Windows") == (
        "src/agentctl/check/guest_only.py",
        "src/agentctl/check/posix.py",
    )
    assert coverage_hosts.foreign(parsed.value, "Darwin") == (
        "src/agentctl/check/guest_only.py",
        "src/agentctl/check/native_only.py",
    )
    present = frozenset({"src/agentctl/check/posix.py"})
    assert coverage_hosts.missing(parsed.value, present) == (
        "src/agentctl/check/guest_only.py",
        "src/agentctl/check/native_only.py",
    )


def test_invalid_manifests_are_refused() -> None:
    """Malformed, unknown, empty and duplicate declarations omit nothing."""
    accepted = tuple(
        text for text in INVALID if not isinstance(coverage_hosts.parse(text), Err)
    )
    assert accepted == (), "invalid coverage host manifest accepted"


def test_live_manifest_names_present_sources(root: Path) -> None:
    """The governed manifest parses and every declared source is present."""
    entries = source_census(root)
    assert isinstance(entries, Ok), entries
    assert coverage_host_problems(root, entries.value) == ()
    observer = "src/agentctl/check/virtualbox_observe.py"
    assert observer in coverage_foreign(root, "Linux")
    assert observer not in coverage_foreign(root, "Windows")


def test_invalid_or_absent_manifest_omits_nothing(tmp_path: Path) -> None:
    """A missing or invalid manifest is reported and never narrows coverage."""
    assert coverage_foreign(tmp_path, "Linux") == ()
    problems = coverage_host_problems(tmp_path, ())
    assert len(problems) == 1
    assert problems[0].startswith("validators: coverage hosts: cannot read")
    manifest = tmp_path / "src/agentctl/check/coverage_hosts.toml"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(HEADER + "source = []\n", encoding="utf-8")
    assert coverage_foreign(tmp_path, "Linux") == ()
    assert coverage_host_problems(tmp_path, ()) == (
        "validators: coverage hosts: invalid or duplicate coverage host source",
    )
    manifest.write_text(VALID, encoding="utf-8")
    assert coverage_host_problems(tmp_path, ()) == (
        "validators: coverage hosts: missing src/agentctl/check/guest_only.py",
        "validators: coverage hosts: missing src/agentctl/check/native_only.py",
        "validators: coverage hosts: missing src/agentctl/check/posix.py",
    )
    for version in ("true", "1.0"):
        manifest.write_text(
            VALID.replace("version = 1", "version = " + version), encoding="utf-8"
        )
        assert coverage_foreign(tmp_path, "Linux") == (), (
            "invalid version narrowed coverage"
        )
        assert coverage_host_problems(tmp_path, ()) == (
            "validators: coverage hosts: invalid coverage host manifest fields",
        )


def test_report_scopes_checkout_and_omits_only_foreign() -> None:
    """The report includes checkout sources and omits exactly the supplied set."""
    root, run = PurePosixPath("/w"), PurePosixPath("/r")
    report = coverage_commands(
        "py", root, run, ("src/agentctl/a.py", "src/agentctl/b.py")
    )[-1]
    assert "--include=/w/src/agentctl/*" in report
    assert "--omit=/w/src/agentctl/a.py,/w/src/agentctl/b.py" in report
    assert "--fail-under=100" in report
    assert not any(
        item.startswith("--omit=") for item in coverage_commands("py", root, run)[-1]
    )


def test_coverage_gaps_follow_source_consumers() -> None:
    """Later-only gaps stay local, while shared gaps reach every consumer."""
    shared = "src/agentctl/shared.py"
    later = "src/agentctl/later.py"
    foreign_path = "src/agentctl/windows.py"
    owners = (
        coverage_hosts.CoverageOwner(shared, frozenset({0, 1})),
        coverage_hosts.CoverageOwner(later, frozenset({1})),
        coverage_hosts.CoverageOwner(foreign_path, frozenset({1})),
    )
    restricted = (coverage_hosts.HostSource(foreign_path, frozenset({"Windows"})),)
    complete = (
        coverage_hosts.CoverageFact(shared, 0, 0),
        coverage_hosts.CoverageFact(later, 0, 0),
    )
    expected = ((0, frozenset()), (1, frozenset()), (2, frozenset()))
    assert coverage_hosts.attribute(
        complete, owners, restricted, "Linux", (0, 1, 2)
    ) == Ok(expected), "foreign host source was demanded"
    late_gap = (complete[0], replace(complete[1], missing_branches=1))
    assert coverage_hosts.attribute(
        late_gap, owners, restricted, "Linux", (0, 1, 2)
    ) == Ok(
        (
            (0, frozenset()),
            (1, frozenset({"coverage incomplete: " + later})),
            (2, frozenset()),
        )
    ), "later coverage gap affected the wrong phase"
    shared_gap = (replace(complete[0], missing_statements=1), complete[1])
    assert coverage_hosts.attribute(
        shared_gap, owners, restricted, "Linux", (0, 1, 2)
    ) == Ok(
        (
            (0, frozenset({"coverage incomplete: " + shared})),
            (1, frozenset({"coverage incomplete: " + shared})),
            (2, frozenset()),
        )
    ), "shared coverage gap was lost"


def test_coverage_attribution_refuses_incomplete_census() -> None:
    """Absent, duplicated, foreign or unowned evidence cannot prove coverage."""
    path = "src/agentctl/a.py"
    fact = coverage_hosts.CoverageFact(path, 0, 0)
    owner = coverage_hosts.CoverageOwner(path, frozenset({0}))
    attribute = coverage_hosts.attribute
    assert attribute((fact,), (owner,), (), "Linux", (0,)) == Ok(((0, frozenset()),))
    invalid = (
        ((), (owner,), (), (0,)),
        ((fact, fact), (owner,), (), (0,)),
        ((fact,), (owner, owner), (), (0,)),
        ((fact,), (replace(owner, consumers=frozenset({1})),), (), (0,)),
        ((replace(fact, missing_statements=-1),), (owner,), (), (0,)),
        ((replace(fact, missing_branches=True),), (owner,), (), (0,)),
        (
            (fact,),
            (owner,),
            (coverage_hosts.HostSource(path, frozenset({"Windows"})),),
            (0,),
        ),
        (
            (fact,),
            (owner,),
            (
                coverage_hosts.HostSource(
                    "src/agentctl/missing.py", frozenset({"Linux"})
                ),
            ),
            (0,),
        ),
        ((fact,), (owner,), (), (0, 0)),
    )
    for facts, owners, restricted, phases in invalid:
        assert isinstance(attribute(facts, owners, restricted, "Linux", phases), Err), (
            "incomplete or ambiguous coverage was accepted"
        )


def test_coverage_json_refuses_inconsistent_observations() -> None:
    """The report's metadata, unique fields, source paths and counts must agree."""
    path = "src/agentctl/a.py"
    summary = {
        "num_statements": 2,
        "covered_lines": 1,
        "missing_lines": 1,
        "num_branches": 2,
        "covered_branches": 1,
        "missing_branches": 1,
    }
    source = {
        "executed_lines": [1],
        "missing_lines": [2],
        "executed_branches": [[1, 2]],
        "missing_branches": [[1, -1]],
        "summary": summary,
    }
    report = {
        "meta": {"format": 3, "version": "7.17.0", "branch_coverage": True},
        "files": {path: source},
        "totals": summary,
    }
    encoded = json.dumps(report)
    assert coverage_hosts.parse_report(encoded, "7.17.0") == Ok(
        (coverage_hosts.CoverageFact(path, 1, 1),)
    )
    windows = path.replace("/", "\\")
    assert coverage_hosts.parse_report(
        json.dumps({**report, "files": {windows: source}}), "7.17.0"
    ) == Ok((coverage_hosts.CoverageFact(path, 1, 1),))
    second = "src/agentctl/b.py"
    multi = {
        **report,
        "files": {path: source, second: source},
        "totals": {key: value * 2 for key, value in summary.items()},
    }
    assert coverage_hosts.parse_report(json.dumps(multi), "7.17.0") == Ok(
        (
            coverage_hosts.CoverageFact(path, 1, 1),
            coverage_hosts.CoverageFact(second, 1, 1),
        )
    )
    invalid = (
        "{",
        encoded.replace('"files": ', '"files": {}, "files": '),
        json.dumps({**report, "meta": {**report["meta"], "branch_coverage": False}}),
        json.dumps({**report, "meta": {**report["meta"], "format": 3.0}}),
        json.dumps({**report, "meta": {**report["meta"], "version": "other"}}),
        json.dumps({**report, "files": {"../a.py": source}}),
        json.dumps({**report, "files": {"src\\agentctl/a.py": source}}),
        json.dumps({**report, "files": {path: source, windows: source}}),
        json.dumps({**multi, "totals": summary}),
        json.dumps({**report, "files": {path: {**source, "missing_lines": [2, 2]}}}),
        json.dumps(
            {**report, "files": {path: {**source, "missing_branches": [[1, 0]]}}}
        ),
        json.dumps(
            {
                **report,
                "files": {
                    path: {**source, "summary": {**summary, "missing_lines": True}}
                },
            }
        ),
        json.dumps(
            {
                **report,
                "files": {path: {**source, "summary": {**summary, "num_branches": 3}}},
            }
        ),
        json.dumps(
            {
                **report,
                "files": {
                    path: {
                        **source,
                        "executed_branches": [[1, 2], [1, -1]],
                        "missing_branches": [],
                    }
                },
            }
        ),
        json.dumps({**report, "totals": {**summary, "missing_lines": 0}}),
        json.dumps({**report, "totals": {**summary, "missing_lines": 1.0}}),
        json.dumps({**report, "totals": {**summary, "num_statements": 3}}),
        json.dumps({**report, "totals": {**summary, "covered_lines": 2}}),
        json.dumps({**report, "totals": {**summary, "num_branches": 3}}),
        json.dumps({**report, "totals": {**summary, "covered_branches": 2}}),
        json.dumps(
            {**report, "totals": {**summary, "num_statements": 3, "covered_lines": 2}}
        ),
        json.dumps(
            {**report, "totals": {**summary, "num_branches": 3, "covered_branches": 2}}
        ),
        json.dumps(
            {
                **report,
                "files": {path: {**source, "summary": {**summary, "covered_lines": 0}}},
                "totals": {**summary, "covered_lines": 0},
            }
        ),
        json.dumps(
            {
                **report,
                "files": {
                    path: {**source, "summary": {**summary, "covered_branches": 0}}
                },
                "totals": {**summary, "covered_branches": 0},
            }
        ),
        json.dumps(
            {
                **report,
                "files": {
                    path: {**source, "summary": {**summary, "covered_lines": True}}
                },
            }
        ),
    )
    for text in invalid:
        assert isinstance(coverage_hosts.parse_report(text, "7.17.0"), Err), (
            "invalid coverage report was accepted"
        )


def test_deep_coverage_json_is_refused() -> None:
    """A deeply nested coverage report must fail without escaping its parser."""
    text = "[" * 50000 + "0" + "]" * 50000
    try:
        result = coverage_hosts.parse_report(text, "7.17.0")
    except RecursionError:
        pytest.fail("deep coverage JSON escaped its parser")
    assert isinstance(result, Err), "deep coverage JSON was accepted"


def test_coverage_capture_requires_one_exact_pin() -> None:
    """Unpinned, duplicated and malformed dependencies cannot identify the tool."""
    prefix = "[project.optional-dependencies]\ndev = "
    assert coverage_hosts.pinned_version(prefix + '["coverage==7.17.0"]') == Ok(
        "7.17.0"
    )
    for text in (
        "not toml",
        prefix + "[]",
        prefix + '["coverage>=7.17"]',
        prefix + '["coverage==7.17.0", "coverage==7.17.0"]',
        prefix + '["coverage==7.17.0", "coverage[toml]>=7"]',
    ):
        assert isinstance(coverage_hosts.pinned_version(text), Err), (
            "invalid coverage tool pin was accepted"
        )
