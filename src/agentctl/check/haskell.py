# Copyright (c) 2026 agentctl contributors.
"""Closed Cabal components and fresh, fully routed Tasty execution evidence."""

import json
import re
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Literal
from xml.etree import ElementTree as ET
from xml.parsers import expat

import click

from agentctl.bootstrap import binary, build
from agentctl.check.evidence import RunEvidence, read_manifest, verify
from agentctl.hostfacts import HostContext
from agentctl.result import Err, Ok, Result


@dataclass(frozen=True, slots=True)
class Component:
    """One unconditional component in the bundled Cabal package."""

    kind: Literal["library", "executable", "test-suite"]
    name: str


def components(text: str) -> Result[tuple[Component, ...], build.BuildError]:
    """Reject selectable components and any suite without the owned XML route."""
    if re.search(r"(?mi)^\s*(?:flag\s|if\s|else\s*$|buildable\s*:)", text):
        return Err(
            build.BuildError("Conditional or disabled Cabal components forbidden")
        )
    found: tuple[Component, ...] = ()
    for line in text.splitlines():
        if line == "library":
            found += (Component("library", "agentctl-core"),)
        else:
            match = re.fullmatch(r"(executable|test-suite) ([a-z][a-z0-9-]*)", line)
            if match is not None:
                kind, name = match.groups()
                found += (
                    Component(
                        "executable" if kind == "executable" else "test-suite", name
                    ),
                )
    if (
        len(set(found)) != len(found)
        or Component("library", "agentctl-core") not in found
        or Component("executable", "agentctl-core") not in found
        or Component("executable", "agentctl-core-eval") not in found
        or tuple(item.name for item in found if item.kind == "test-suite")
        != ("agentctl-core-test",)
    ):
        return Err(build.BuildError("Unrouted or missing Cabal component"))
    return Ok(found)


def declared(project: Path) -> Result[tuple[Component, ...], build.BuildError]:
    """Read the actual bundled component declarations without ignoring failures."""
    try:
        return components((project / "agentctl-core.cabal").read_text(encoding="utf-8"))
    except (OSError, UnicodeError) as exc:
        return Err(build.BuildError(f"Cannot read Cabal components: {exc}"))


def compile_all(context: build.BuildContext) -> Result[None, build.BuildError]:
    """Build all unconditional components and locate every internal executable."""
    targets = declared(context.project)
    if isinstance(targets, Err):
        return targets
    compiled = build.compile_project(context)
    if isinstance(compiled, Err):
        return compiled
    for component in targets.value:
        if component.kind != "library":
            prefix = "exe" if component.kind == "executable" else "test"
            located = build.binary(context, prefix + ":" + component.name)
            if isinstance(located, Err):
                return located
    return Ok(None)


def listed(text: str) -> Result[frozenset[str], build.BuildError]:
    """Require nonempty, unique, fully qualified names from Tasty's listing."""
    names = text.splitlines()
    if (
        not names
        or len(names) != len(set(names))
        or any(
            re.fullmatch(r"agentctl-core-test\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", name)
            is None
            for name in names
        )
    ):
        return Err(build.BuildError("Empty or malformed Tasty case listing"))
    return Ok(frozenset("haskell:" + name.replace(".", "/") for name in names))


def report(text: str) -> Result[tuple[tuple[str, str | None], ...], build.BuildError]:
    """Parse case outcomes, rejecting unsupported XML and empty or duplicate cases."""
    try:
        if "<!" in text:
            return Err(build.BuildError("Declarations forbidden in Tasty XML"))
        builder = ET.TreeBuilder()
        parser = expat.ParserCreate()

        def start(tag: str, attributes: dict[str, str]) -> None:
            builder.start(tag, attributes)

        def end(tag: str) -> None:
            builder.end(tag)

        parser.StartElementHandler = start
        parser.EndElementHandler = end
        parser.CharacterDataHandler = builder.data
        parser.ParseFile(BytesIO(text.encode("utf-8")))
        document = builder.close()
    except expat.ExpatError as exc:
        return Err(build.BuildError(f"Invalid Tasty XML: {exc}"))
    cases = tuple(document.iter("testcase"))
    outcomes: tuple[tuple[str, str | None], ...] = ()
    for case in cases:
        qualified = case.get("classname", "") + "." + case.get("name", "")
        identity = listed(qualified)
        if isinstance(identity, Err):
            return identity
        failures = tuple(case.iter("failure")) + tuple(case.iter("error"))
        reason = "\n".join("".join(item.itertext()) for item in failures)
        if tuple(case.iter("skipped")):
            reason = "Tasty case skipped"
        outcomes += (
            (next(iter(identity.value)), reason if failures or reason else None),
        )
    if (
        document.tag != "testsuites"
        or not outcomes
        or len({name for name, _reason in outcomes}) != len(outcomes)
        or document.get("tests") != str(len(outcomes))
    ):
        return Err(build.BuildError("Empty, duplicate or inconsistent Tasty XML cases"))
    return Ok(outcomes)


def verify_report(
    text: str, expected: frozenset[str], nonce: str
) -> Result[RunEvidence, build.BuildError]:
    """Join separately listed and executed cases, requiring each to pass now."""
    parsed = report(text)
    if isinstance(parsed, Err):
        return parsed
    executed = frozenset(name for name, _reason in parsed.value)
    passed = frozenset(name for name, reason in parsed.value if reason is None)
    if expected != executed or passed != executed:
        return Err(
            build.BuildError("Tasty execution differs from listing or has failures")
        )
    return Ok(
        RunEvidence(
            nonce,
            expected,
            executed,
            passed,
            (),
            tuple((name, case_class(name)) for name in sorted(expected)),
        )
    )


def run_suites(
    context: build.BuildContext, directory: Path, nonce: str
) -> Result[RunEvidence, build.BuildError]:
    """Run test all into a fresh owned XML file and publish only verified evidence."""
    targets = declared(context.project)
    if isinstance(targets, Err):
        return targets
    listing = build.execute_binary(
        context, build.BinaryCall("test:agentctl-core-test", ("--list-tests",))
    )
    if isinstance(listing, Err):
        return listing
    expected = listed(listing.value.stdout if listing.value.code == 0 else "")
    if isinstance(expected, Err):
        return expected
    path = directory / "tasty.xml"
    return _test_and_record(context, path, expected.value, nonce)


def _test_and_record(
    context: build.BuildContext, path: Path, expected: frozenset[str], nonce: str
) -> Result[RunEvidence, build.BuildError]:
    """Keep report creation, suite execution and manifest publication together."""
    directory = path.parent
    try:
        directory.mkdir(parents=True, exist_ok=True)
        path.unlink(missing_ok=True)
        tested = build.invoke(
            context,
            (*build.arguments(context, "test", "all"), "--test-show-details=direct"),
            settings=(("TASTY_XML", str(path)),),
        )
        if isinstance(tested, Err):
            return tested
        return record_report(path, expected, nonce)
    except OSError as exc:
        return Err(build.BuildError(f"Cannot run fresh Tasty execution: {exc}"))


def record_report(
    path: Path, expected: frozenset[str], nonce: str
) -> Result[RunEvidence, build.BuildError]:
    """Record only a successfully read report containing every expected passing case."""
    directory = path.parent
    try:
        verified = verify_report(path.read_text(encoding="utf-8"), expected, nonce)
        if isinstance(verified, Err):
            return verified
        build.atomic_text(
            directory / "haskell-manifest.json",
            json.dumps(
                {
                    "nonce": nonce,
                    "collected": sorted(verified.value.collected),
                    "executed": sorted(verified.value.executed),
                    "passed": sorted(verified.value.passed),
                    "forbidden": [],
                    "classes": dict(verified.value.classes),
                }
            ),
        )
    except (OSError, UnicodeError) as exc:
        return Err(build.BuildError(f"Cannot record fresh Tasty execution: {exc}"))
    else:
        return verified


def case_class(name: str) -> Literal["real", "value"]:
    """Use the declared native group convention for effectful versus pure cases."""
    group = name.partition("/")[2].partition("/")[0]
    return "real" if group.endswith("Real") else "value"


def combined(
    directory: Path, python: RunEvidence, nonce: str
) -> Result[RunEvidence, build.BuildError]:
    """Require a current complete native manifest before joining Python evidence."""
    native = read_manifest(directory / "haskell-manifest.json")
    if isinstance(native, Err):
        return Err(build.BuildError(native.error.message))
    valid = verify(native.value, nonce, ())
    if isinstance(valid, Err):
        return Err(build.BuildError(valid.error.message))
    if any(
        not node.startswith("haskell:agentctl-core-test/") or kind != case_class(node)
        for node, kind in native.value.classes
    ):
        return Err(build.BuildError("Invalid Haskell evidence identity or class"))
    return Ok(
        RunEvidence(
            nonce,
            python.collected | native.value.collected,
            python.executed | native.value.executed,
            python.passed | native.value.passed,
            python.forbidden,
            (*python.classes, *native.value.classes),
        )
    )


@dataclass(frozen=True, slots=True)
class HaskellStep:
    """A Cabal leg resolved after toolchain ensure, with run-owned reports."""

    name: Literal["cabal-build", "cabal-test"]
    host: HostContext
    project: Path


def run_step(step: HaskellStep, directory: Path, nonce: str) -> int:
    """Use the recorded toolchain and the application's shared native build path."""
    prepared = binary.check_context(step.host, step.project)
    if isinstance(prepared, Err):
        click.echo(prepared.error.message, err=True)
        return 1
    context = prepared.value
    result = (
        compile_all(context)
        if step.name == "cabal-build"
        else run_suites(context, directory, nonce)
    )
    if isinstance(result, Err):
        click.echo(result.error.message, err=True)
        return 1
    return 0
