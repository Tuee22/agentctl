# Copyright (c) 2026 agentctl contributors.
"""Fail closed on reduced, unclassified or incomplete pytest executions."""

import json
import os
import re
from collections.abc import Generator
from dataclasses import dataclass, replace
from pathlib import Path

import pytest

from agentctl.check.evidence import EvidenceClass, EvidenceError, classification
from agentctl.result import Err


@dataclass(frozen=True, slots=True)
class Manifest:
    """Independent collection, execution and successful-outcome observations."""

    nonce: str
    collected: frozenset[str] = frozenset()
    executed: frozenset[str] = frozenset()
    passed: frozenset[str] = frozenset()
    forbidden: tuple[str, ...] = ()
    classes: tuple[tuple[str, EvidenceClass], ...] = ()


STATE = pytest.StashKey[Manifest]()


def orphan_modules(
    root: Path,
    collected: frozenset[str],
    cited: frozenset[str],
    support: frozenset[str],
) -> tuple[str, ...]:
    """Join filesystem modules to collection, sprint citations and support."""
    modules = frozenset(node.split("::", 1)[0] for node in collected)
    files = frozenset(
        path.relative_to(root).as_posix() for path in (root / "tests").rglob("*.py")
    )
    hidden_tests = frozenset(
        path
        for path in files
        if (Path(path).name.startswith("test_") or Path(path).name.endswith("_test.py"))
        and path in support
    )
    return tuple(sorted((files - modules - support) | (modules - cited) | hidden_tests))


def _record(config: pytest.Config, message: str) -> None:
    """Retain every forbidden observation through session finish."""
    state = config.stash[STATE]
    config.stash[STATE] = replace(state, forbidden=(*state.forbidden, message))


def pytest_configure(config: pytest.Config) -> None:
    """Initialize the manifest and refuse all suite-narrowing options."""
    nonce = os.environ.get("AGENTCTL_CHECK_NONCE", "")
    config.stash[STATE] = Manifest(nonce)
    arguments = config.invocation_params.args
    selectors = (
        "-k",
        "-m",
        "--lf",
        "--last-failed",
        "--ff",
        "--failed-first",
        "--nf",
        "--new-first",
        "--deselect",
        "--ignore",
        "--ignore-glob",
        "--stepwise",
        "--sw",
        "--pyargs",
        "--collect-only",
        "--co",
    )
    if nonce and any(
        "::" in argument
        or any(
            argument == selector
            or argument.startswith(selector + "=")
            or (selector in {"-k", "-m"} and argument.startswith(selector))
            for selector in selectors
        )
        for argument in arguments
    ):
        msg = "gate: selectors are forbidden"
        raise pytest.UsageError(msg)
    if nonce:
        option_values = tuple(str(value) for value in config.args)
        allowed = {"tests", ".", str(config.rootpath / "tests"), str(config.rootpath)}
        if any(value not in allowed for value in option_values):
            msg = "gate: node-id narrowing is forbidden"
            raise pytest.UsageError(msg)


def pytest_collection_finish(session: pytest.Session) -> None:
    """Require one evidence class, no outcome decorators and cited modules."""
    config = session.config
    state = config.stash[STATE]
    config.stash[STATE] = replace(
        state, collected=frozenset(item.nodeid for item in session.items)
    )
    if not session.items:
        _record(config, "empty collection")
    for item in session.items:
        evidence = tuple(item.iter_markers("evidence"))
        parsed = (
            Err(EvidenceError("invalid evidence marker"))
            if (len(evidence) != 1 or len(evidence[0].args) != 1 or evidence[0].kwargs)
            else classification(evidence[0].args[0])
        )
        if isinstance(parsed, Err):
            _record(config, f"evidence marker: {item.nodeid}")
        else:
            state = config.stash[STATE]
            config.stash[STATE] = replace(
                state, classes=(*state.classes, (item.nodeid, parsed.value))
            )
        if any(tuple(item.iter_markers(name)) for name in ("skip", "skipif", "xfail")):
            _record(config, f"forbidden outcome marker: {item.nodeid}")
    plan = config.rootpath / "DEVELOPMENT_PLAN"
    if plan.is_dir():
        citations = frozenset(
            re.findall(
                r"`(tests/[^`\s]+\.py)::",
                "\n".join(
                    path.read_text(encoding="utf-8") for path in plan.glob("phase-*.md")
                ),
            )
        )
        support_file = config.rootpath / "tests/support.txt"
        support = (
            frozenset(support_file.read_text(encoding="utf-8").splitlines())
            if support_file.exists()
            else frozenset()
        )
        for orphan in orphan_modules(
            config.rootpath, config.stash[STATE].collected, citations, support
        ):
            _record(config, f"tests.orphan-modules: {orphan}")


def pytest_deselected(items: list[pytest.Item]) -> None:
    """Reject any plugin or option that deselects collected items."""
    for item in items:
        _record(item.config, f"deselected: {item.nodeid}")


@pytest.hookimpl(wrapper=True)
def pytest_runtest_protocol(item: pytest.Item, nextitem: pytest.Item | None) -> object:
    """Record actual execution independently of the collection hook."""
    del nextitem
    state = item.config.stash[STATE]
    item.config.stash[STATE] = replace(state, executed=state.executed | {item.nodeid})
    return (yield)


@pytest.hookimpl(wrapper=True)
def pytest_runtest_makereport(
    item: pytest.Item, call: pytest.CallInfo[None]
) -> Generator[None, pytest.TestReport, pytest.TestReport]:
    """Observe skipped, expected-failure and unsuccessful test phases."""
    del call
    report = yield
    if report.skipped or hasattr(report, "wasxfail"):
        _record(item.config, f"forbidden outcome: {item.nodeid}")
    if report.failed:
        _record(item.config, f"failed: {item.nodeid}")
    if report.when == "call" and report.passed:
        state = item.config.stash[STATE]
        item.config.stash[STATE] = replace(state, passed=state.passed | {item.nodeid})
    return report


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """Write the observed manifest and fail every incomplete session."""
    del exitstatus
    state = session.config.stash[STATE]
    manifest = os.environ.get("AGENTCTL_CHECK_MANIFEST")
    if manifest is not None:
        Path(manifest).write_text(
            json.dumps(
                {
                    "nonce": state.nonce,
                    "collected": sorted(state.collected),
                    "executed": sorted(state.executed),
                    "passed": sorted(state.passed),
                    "forbidden": state.forbidden,
                    "classes": dict(state.classes),
                }
            ),
            encoding="utf-8",
        )
    if (
        state.forbidden
        or not state.collected
        or state.collected != state.executed
        or state.collected != state.passed
    ):
        session.exitstatus = pytest.ExitCode.TESTS_FAILED
        reporter = session.config.pluginmanager.get_plugin("terminalreporter")
        if isinstance(reporter, pytest.TerminalReporter):
            reporter.write_line(
                "gate: incomplete or forbidden session: " + "; ".join(state.forbidden)
            )
