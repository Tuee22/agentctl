# Copyright (c) 2026 agentctl contributors.
"""Host-confined coverage declarations and their report arguments."""

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
