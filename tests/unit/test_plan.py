# Copyright (c) 2026 agentctl contributors.
"""Independent provisioning values, convergence and default-selection controls."""

from pathlib import Path

import pytest

from agentctl.bootstrap.pins import Pins, load, version
from agentctl.bootstrap.plan import DownloadGhcup, GhcupCommand, provision
from agentctl.bootstrap.prereqs import PackageInstall, XcodeInstall
from agentctl.hostfacts import (
    Distribution,
    Ghcup,
    HostFacts,
    Prerequisite,
    architecture,
)
from agentctl.result import Err, Ok
from tests.harness.oracle import (
    Object,
    Problem,
    Row,
    Store,
    Value,
    assert_oracle,
    freeze,
    read_homes,
)
from tests.harness.oracle import load as oracle_load

pytestmark = pytest.mark.evidence("value")


def _plan_rows(root: Path) -> tuple[Row, ...]:
    """Keep every provisioning row while the recipe has its own independent test."""
    store = oracle_load(root / "tests/oracles/bootstrap_plan.toml", read_homes(root))
    assert isinstance(store, Store)
    subjects = tuple(_fields(row.inputs)["subject"] for row in store.effective)
    assert set(subjects) <= {"bootstrap-plan", "clean-host-recipe"}
    rows = tuple(
        row
        for row, subject in zip(store.effective, subjects, strict=True)
        if subject == "bootstrap-plan"
    )
    assert rows
    return rows


def _fields(value: Value) -> dict[str, Value]:
    """Unwrap only the immutable oracle object at the test boundary."""
    assert isinstance(value, Object)
    return dict(value.items)


def _text(value: Value) -> str:
    """Require the independent table's string-valued fact fields."""
    assert isinstance(value, str)
    return value


def _facts(value: Value, directory: Path) -> HostFacts:
    """Translate oracle facts without consulting the subject's decisions."""
    fields = _fields(value)
    family = _text(fields["family"])
    assert family in {"Linux", "Darwin", "Windows"}
    cup = _text(fields["ghcup"])
    prerequisites = _text(fields["prerequisites"])
    assert prerequisites in {"present", "missing", "unobserved"}
    failed = fields.get(
        "failed_probe", "compiler-and-gmp" if family == "Linux" else "xcode-clt"
    )
    observations = (
        (
            Prerequisite(
                "compiler-and-gmp",
                ready=prerequisites == "present" or failed != "compiler-and-gmp",
            ),
            Prerequisite(
                "downloader", ready=prerequisites == "present" or failed != "downloader"
            ),
            Prerequisite(
                "ca-certificates",
                ready=prerequisites == "present" or failed != "ca-certificates",
            ),
            Prerequisite("make", ready=prerequisites == "present" or failed != "make"),
        )
        if family == "Linux"
        else (Prerequisite("xcode-clt", ready=prerequisites == "present"),)
        if family == "Darwin"
        else ()
    )
    distribution = fields.get("distribution", "ubuntu")
    major = fields.get("major", 24)
    root, interactive, assume_yes = (
        fields.get("is_root", False),
        fields.get("interactive", False),
        fields.get("assume_yes", False),
    )
    assert isinstance(distribution, str)
    assert distribution in {"ubuntu", "debian", "fedora", "arch", "other"}
    assert isinstance(major, int)
    assert isinstance(root, bool)
    assert isinstance(interactive, bool)
    assert isinstance(assume_yes, bool)
    return HostFacts(
        family,
        architecture(family, _text(fields["architecture"])),
        directory / "download/ghcup",
        None
        if cup in {"absent", "unobserved"}
        else Ghcup(directory / "existing/ghcup", version(cup)),
        str(directory / "existing/ghc") if fields["ghc"] == "present" else None,
        str(directory / "existing/cabal") if fields["cabal"] == "present" else None,
        distribution=Distribution(distribution, major),
        is_root=root,
        interactive=interactive,
        assume_yes=assume_yes,
        prerequisites=None if prerequisites == "unobserved" else observations,
    )


def _projection(facts: HostFacts, pins: Pins) -> Value:
    """Expose the plan's values in the independent oracle's data vocabulary."""
    planned = provision(facts, pins)
    if isinstance(planned, Err):
        value = freeze(
            {
                "outcome": "refused",
                "reason": planned.error.reason,
                "remedy": planned.error.remedy,
                "actions": [],
            }
        )
    else:
        actions: list[dict[str, object]] = []
        for action in planned.value:
            match action:
                case DownloadGhcup(asset, destination):
                    assert destination == facts.ghcup_destination
                    actions.append(
                        {
                            "kind": "download-ghcup",
                            "url": asset.url,
                            "sha256": asset.sha256,
                        }
                    )
                case GhcupCommand(executable, arguments):
                    assert executable == (
                        facts.ghcup.path
                        if facts.ghcup is not None
                        else facts.ghcup_destination
                    )
                    assert executable.is_absolute()
                    actions.append({"kind": "ghcup", "arguments": list(arguments)})
                case PackageInstall(packages, commands):
                    actions.append(
                        {
                            "kind": "prerequisites",
                            "packages": list(packages),
                            "commands": [list(command) for command in commands],
                        }
                    )
                case XcodeInstall(command):
                    actions.append({"kind": "xcode", "commands": [list(command)]})
        value = freeze({"outcome": "ready", "actions": actions})
    assert not isinstance(value, Problem)
    return value


def test_plan_oracle(root: Path, tmp_path: Path) -> None:
    """Require every ordered action or complete refusal from the independent rows."""
    pins = load()
    assert isinstance(pins, Ok)
    for row in _plan_rows(root):
        expected = _fields(row.expected)["plan"]
        assert_oracle(
            lambda facts: _projection(facts, pins.value),
            _facts(row.inputs, tmp_path),
            expected,
            row_id="bootstrap plan differs: " + row.identifier,
        )


def test_fully_provisioned_plan_is_empty(root: Path, tmp_path: Path) -> None:
    """Each successful nonempty row converges to the oracle's answering-pin facts."""
    pins = load()
    assert isinstance(pins, Ok)
    compared = 0
    for row in _plan_rows(root):
        expected = _fields(row.expected)
        plan = _fields(expected["plan"])
        if plan["outcome"] == "ready" and plan["actions"]:
            before = provision(_facts(row.inputs, tmp_path), pins.value)
            assert isinstance(before, Ok)
            assert before.value
            after = provision(_facts(expected["after"], tmp_path), pins.value)
            assert after == Ok(()), (
                "bootstrap plan differs: answering pins were planned again"
            )
            compared += 1
    assert compared > 0


def test_plan_never_sets_default(root: Path, tmp_path: Path) -> None:
    """Bare hosts install both pins with the no-default-selection argv contract."""
    pins = load()
    assert isinstance(pins, Ok)
    installs: set[str] = set()
    for row in _plan_rows(root):
        planned = provision(_facts(row.inputs, tmp_path), pins.value)
        if isinstance(planned, Ok):
            for action in planned.value:
                if isinstance(action, GhcupCommand):
                    assert "--set" not in action.arguments
                    assert action.arguments[0] != "set"
                    if action.arguments[:2] == ("install", "cabal"):
                        assert action.arguments[-1] == "--no-set", (
                            "cabal install changes the default"
                        )
                        installs.add("cabal")
                    if action.arguments[:2] == ("install", "ghc"):
                        installs.add("ghc")
    assert installs == {"ghc", "cabal"}
