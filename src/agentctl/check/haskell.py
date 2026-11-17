# Copyright (c) 2026 agentctl contributors.
"""Closed Cabal components and fresh, fully routed Tasty execution evidence."""

import json
import re
from dataclasses import dataclass, replace
from io import BytesIO
from pathlib import Path, PurePosixPath
from typing import Literal
from xml.etree import ElementTree as ET
from xml.parsers import expat

import click

from agentctl.bootstrap import binary, build
from agentctl.check.evidence import Entry, RunEvidence, read_manifest, verify
from agentctl.foundation import Err, Ok, Result
from agentctl.foundation_host import HostContext

SOURCE_FIELDS = 2


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


def source_listing(
    text: str, expected: frozenset[str]
) -> Result[tuple[tuple[str, str], ...], build.BuildError]:
    """Join compiler-reported case locations to the independently listed cases."""
    rows = tuple(line.split("\t") for line in text.splitlines())
    if not rows or any(len(row) != SOURCE_FIELDS for row in rows):
        return Err(build.BuildError("Invalid native case source listing"))
    identities: tuple[tuple[str, str], ...] = ()
    for name, raw_path in rows:
        case = listed(name)
        path = PurePosixPath(raw_path.replace("\\", "/"))
        if (
            isinstance(case, Err)
            or not raw_path
            or path.is_absolute()
            or path.as_posix() != raw_path.replace("\\", "/")
            or ".." in path.parts
            or len(path.parts) != SOURCE_FIELDS
            or path.parts[0] != "test"
            or path.suffix != ".hs"
        ):
            return Err(build.BuildError("Invalid native case source listing"))
        identities += (
            (next(iter(case.value)), "src/agentctl/haskell/" + path.as_posix()),
        )
    names = tuple(node for node, _path in identities)
    if len(set(names)) != len(names) or frozenset(names) != expected:
        return Err(build.BuildError("Native case sources differ from test listing"))
    return Ok(tuple(sorted(identities)))


def observe_sources(
    context: build.BuildContext, expected: frozenset[str]
) -> Result[tuple[tuple[str, str], ...], build.BuildError]:
    """Read native call-site observations and verify each current source path."""
    result = build.execute_binary(
        context,
        build.BinaryCall("test:agentctl-core-test", ("--agentctl-test-sources",)),
    )
    if isinstance(result, Err):
        return result
    if result.value.code != 0:
        return Err(build.BuildError("Native case source listing failed"))
    parsed = source_listing(result.value.stdout, expected)
    if isinstance(parsed, Err):
        return parsed
    try:
        project = context.project.resolve(strict=True)
        for _node, path in parsed.value:
            relative = path.removeprefix("src/agentctl/haskell/")
            source = project / relative
            if (
                source.is_symlink()
                or not source.is_file()
                or not source.resolve(strict=True).is_relative_to(project)
            ):
                return Err(build.BuildError("Native case source path is unavailable"))
    except (OSError, RuntimeError) as exc:
        return Err(build.BuildError("Cannot inspect native case source: " + str(exc)))
    return parsed


def _unique_source_fields(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """Reject duplicate source-observation fields."""
    values = dict(pairs)
    if len(values) != len(pairs):
        message = "duplicate native source field"
        raise ValueError(message)
    return values


def _decode_source_record(
    data: object, nonce: str, expected: frozenset[str], entries: tuple[Entry, ...]
) -> Result[tuple[tuple[str, str], ...], build.BuildError]:
    """Validate a decoded source record against the captured checkout files."""
    match data:
        case {"nonce": str() as observed, "sources": list() as rows, **extra} if (
            not extra and nonce and observed == nonce
        ):
            parsed_rows: tuple[tuple[str, str], ...] = ()
            for row in rows:
                match row:
                    case [str() as node, str() as source] if node.startswith(
                        "haskell:"
                    ) and source.startswith("src/agentctl/haskell/"):
                        parsed_rows += ((node, source),)
                    case _:
                        return Err(
                            build.BuildError("Invalid native case source record")
                        )
            text = "".join(
                node.removeprefix("haskell:").replace("/", ".")
                + "\t"
                + source.removeprefix("src/agentctl/haskell/")
                + "\n"
                for node, source in parsed_rows
            )
            parsed = source_listing(text, expected)
            if isinstance(parsed, Err):
                return parsed
            paths = tuple(entry.path for entry in entries)
            files = frozenset(entry.path for entry in entries if entry.kind == "file")
            if len(paths) != len(set(paths)) or any(
                path not in files for _node, path in parsed.value
            ):
                return Err(
                    build.BuildError("Native case source absent from captured census")
                )
            return parsed
        case _:
            return Err(build.BuildError("Invalid native case source record identity"))


def read_sources(
    directory: Path, nonce: str, expected: frozenset[str], entries: tuple[Entry, ...]
) -> Result[tuple[tuple[str, str], ...], build.BuildError]:
    """Join a nonce-bound native source observation to captured checkout files."""
    path = directory / "haskell-sources.json"
    try:
        if path.is_symlink():
            return Err(build.BuildError("Native case source record is a symlink"))
        data: object = json.loads(
            path.read_text(encoding="utf-8"), object_pairs_hook=_unique_source_fields
        )
    except (OSError, UnicodeError, ValueError) as exc:
        return Err(build.BuildError("Cannot read native case sources: " + str(exc)))
    return _decode_source_record(data, nonce, expected, entries)


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


def observe_report(
    text: str, expected: frozenset[str], nonce: str
) -> Result[RunEvidence, build.BuildError]:
    """Retain complete native case outcomes without presenting them as a pass."""
    parsed = report(text)
    if isinstance(parsed, Err):
        return parsed
    executed = frozenset(name for name, _reason in parsed.value)
    passed = frozenset(name for name, reason in parsed.value if reason is None)
    if not nonce or not expected or expected != executed:
        return Err(build.BuildError("Tasty execution differs from listing"))
    return Ok(
        RunEvidence(
            nonce,
            expected,
            executed,
            passed,
            tuple("failed: " + name for name in sorted(executed - passed)),
            tuple((name, case_class(name)) for name in sorted(expected)),
        )
    )


def verify_report(
    text: str, expected: frozenset[str], nonce: str
) -> Result[RunEvidence, build.BuildError]:
    """Require a complete current report in which every native case passed."""
    observed = observe_report(text, expected, nonce)
    if isinstance(observed, Err):
        return observed
    return (
        Err(build.BuildError("Tasty execution differs from listing or has failures"))
        if observed.value.forbidden
        else observed
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
    sources = observe_sources(context, expected.value)
    if isinstance(sources, Err):
        return sources
    try:
        directory.mkdir(parents=True, exist_ok=True)
        build.atomic_text(
            directory / "haskell-sources.json",
            json.dumps({"nonce": nonce, "sources": sources.value}),
        )
    except (OSError, UnicodeError) as exc:
        return Err(build.BuildError("Cannot record native case sources: " + str(exc)))
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
        command_succeeded = isinstance(tested, Ok) and tested.value.code == 0
        recorded = record_report(
            path, expected, nonce, command_succeeded=command_succeeded
        )
        if isinstance(tested, Err):
            detail = (
                "; report: " + recorded.error.message
                if isinstance(recorded, Err)
                else ""
            )
            return Err(build.BuildError(tested.error.message + detail))
        if tested.value.code != 0:
            detail = (
                ("; report: " + recorded.error.message)
                if isinstance(recorded, Err)
                else ""
            )
            return Err(
                build.BuildError(
                    f"Tasty command failed with status {tested.value.code}" + detail
                )
            )
    except OSError as exc:
        return Err(build.BuildError(f"Cannot run fresh Tasty execution: {exc}"))
    else:
        return recorded


def record_report(
    path: Path,
    expected: frozenset[str],
    nonce: str,
    *,
    command_succeeded: bool = True,
) -> Result[RunEvidence, build.BuildError]:
    """Retain complete case outcomes while rejecting any native failure."""
    directory = path.parent
    try:
        observed = observe_report(path.read_text(encoding="utf-8"), expected, nonce)
        if isinstance(observed, Err):
            return observed
        if not command_succeeded:
            observed = Ok(
                replace(
                    observed.value,
                    forbidden=(*observed.value.forbidden, "native-command-failed"),
                )
            )
        build.atomic_text(
            directory / "haskell-manifest.json",
            json.dumps(
                {
                    "nonce": nonce,
                    "collected": sorted(observed.value.collected),
                    "executed": sorted(observed.value.executed),
                    "passed": sorted(observed.value.passed),
                    "forbidden": list(observed.value.forbidden),
                    "classes": dict(observed.value.classes),
                }
            ),
        )
    except (OSError, UnicodeError) as exc:
        return Err(build.BuildError(f"Cannot record fresh Tasty execution: {exc}"))
    else:
        return (
            Err(
                build.BuildError("Tasty execution differs from listing or has failures")
            )
            if observed.value.forbidden
            else observed
        )


def case_class(name: str) -> Literal["real", "value"]:
    """Use the declared native group convention for effectful versus pure cases."""
    group = name.partition("/")[2].partition("/")[0]
    return "real" if group.endswith("Real") else "value"


def _compare_native_report(
    directory: Path, native: RunEvidence, nonce: str
) -> Result[None, build.BuildError]:
    """Join an observed manifest to the original retained Tasty report."""
    path = directory / "tasty.xml"
    try:
        if path.is_symlink():
            return Err(build.BuildError("Native report is a symlink"))
        report_text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        return Err(build.BuildError("Cannot read native report: " + str(exc)))
    reported = observe_report(report_text, native.collected, nonce)
    if isinstance(reported, Err):
        return reported
    expected_failures = tuple(
        item for item in native.forbidden if item != "native-command-failed"
    )
    if (
        reported.value.executed != native.executed
        or reported.value.passed != native.passed
        or reported.value.classes != native.classes
        or reported.value.forbidden != expected_failures
    ):
        return Err(build.BuildError("Native manifest differs from Tasty report"))
    return Ok(None)


def native_observation(
    directory: Path, nonce: str
) -> Result[RunEvidence, build.BuildError]:
    """Read a complete current native observation, retaining individual failures."""
    native = read_manifest(directory / "haskell-manifest.json")
    if isinstance(native, Err):
        return Err(build.BuildError(native.error.message))
    if any(
        not node.startswith("haskell:agentctl-core-test/") or kind != case_class(node)
        for node, kind in native.value.classes
    ) or (
        not nonce
        or native.value.nonce != nonce
        or not native.value.collected
        or native.value.collected != native.value.executed
        or not native.value.passed <= native.value.executed
        or native.value.forbidden
        not in (
            tuple(
                "failed: " + name
                for name in sorted(native.value.executed - native.value.passed)
            ),
            (
                *tuple(
                    "failed: " + name
                    for name in sorted(native.value.executed - native.value.passed)
                ),
                "native-command-failed",
            ),
        )
    ):
        return Err(build.BuildError("Invalid Haskell evidence identity or class"))
    matched = _compare_native_report(directory, native.value, nonce)
    return matched if isinstance(matched, Err) else native


def native_evidence(
    directory: Path, nonce: str
) -> Result[RunEvidence, build.BuildError]:
    """Require all native observations to pass before issuing complete evidence."""
    native = native_observation(directory, nonce)
    if isinstance(native, Err):
        return native
    valid = verify(native.value, nonce, ())
    return (
        Err(build.BuildError(valid.error.message)) if isinstance(valid, Err) else native
    )


def combined(
    directory: Path, python: RunEvidence, nonce: str
) -> Result[RunEvidence, build.BuildError]:
    """Require a current complete native manifest before joining Python evidence."""
    native = native_evidence(directory, nonce)
    if isinstance(native, Err):
        return native
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
    context = replace(prepared.value, options=("--offline",), prepared_index_only=True)
    indexed = build.verify_prepared_index(context)
    if isinstance(indexed, Err):
        click.echo(indexed.error.message, err=True)
        return 1
    result = (
        compile_all(context)
        if step.name == "cabal-build"
        else run_suites(context, directory, nonce)
    )
    if isinstance(result, Err):
        click.echo(result.error.message, err=True)
        return 1
    return 0
