# Copyright (c) 2026 agentctl contributors.
"""Independent verified package sets, command vectors and consent values."""

import platform
from dataclasses import replace
from pathlib import Path

import pytest

from agentctl.bootstrap.prereqs import (
    GrantedPrerequisites,
    PackageInstall,
    PrerequisiteError,
    XcodeInstall,
    affirmative,
    apply,
    certificate_store,
    commands_of,
    complete,
    consented,
    link_gmp,
    observe,
    packages,
    probe,
    proposal,
    successful,
)
from agentctl.hostfacts import Distribution, HostContext, HostFacts, Prerequisite
from agentctl.process import Output, SpawnError
from agentctl.result import Err, Ok, Result
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
LINK_ARGUMENT_COUNT = 5


def _rows(root: Path, subject: str) -> tuple[Row, ...]:
    """Select one independently specified subject without dropping any of its rows."""
    store = oracle_load(root / "tests/oracles/prerequisites.toml", read_homes(root))
    assert isinstance(store, Store)
    rows = tuple(
        row
        for row in store.effective
        if isinstance(row.inputs, Object)
        and dict(row.inputs.items)["subject"] == subject
    )
    assert rows
    return rows


def _fields(value: Value) -> dict[str, Value]:
    """Unwrap immutable input data only at the test's parsing boundary."""
    assert isinstance(value, Object)
    return dict(value.items)


def _facts(value: Value, directory: Path) -> HostFacts:
    """Construct host decisions from the oracle's explicit distribution and flags."""
    fields = _fields(value)
    family, distribution, major = (
        fields["family"],
        fields["distribution"],
        fields["major"],
    )
    assert isinstance(family, str)
    assert family in {"Linux", "Darwin", "Windows"}
    assert isinstance(distribution, str)
    assert distribution in {"ubuntu", "debian", "fedora", "arch", "other"}
    assert isinstance(major, int)
    root, assume_yes = fields["is_root"], fields["assume_yes"]
    assert isinstance(root, bool)
    assert isinstance(assume_yes, bool)
    return HostFacts(
        family,
        "x86_64",
        directory / "ghcup",
        None,
        None,
        None,
        distribution=Distribution(distribution, major),
        is_root=root,
        assume_yes=assume_yes,
    )


def _projection(facts: HostFacts) -> Value:
    """Expose fixed package and argv values without reading any expected output."""
    selected = proposal(facts)
    if isinstance(selected, Err):
        result = freeze({"kind": "refused", "reason": selected.error.reason})
    elif not selected.value:
        result = freeze({"kind": "none", "packages": [], "commands": []})
    else:
        assert len(selected.value) == 1
        action = selected.value[0]
        result = freeze(
            {
                "kind": "packages" if isinstance(action, PackageInstall) else "xcode",
                "packages": list(action.packages)
                if isinstance(action, PackageInstall)
                else [],
                "commands": [list(command) for command in commands_of(action)],
            }
        )
    assert not isinstance(result, Problem)
    return result


def test_package_sets_match_oracle(root: Path, tmp_path: Path) -> None:
    """Every verified set and refusal, across root and sudo modes, matches its row."""
    for row in _rows(root, "package-set"):
        assert_oracle(
            _projection,
            _facts(row.inputs, tmp_path),
            row.expected,
            row_id="prerequisite argv differs: " + row.identifier,
        )
    assert isinstance(packages(None), Err)
    assert isinstance(packages(Distribution("ubuntu", None)), Err)
    assert isinstance(packages(Distribution("debian", None)), Err)


def test_consent_policy_matches_oracle(root: Path) -> None:
    """Only an explicit flag or affirmative answer supplies consent."""
    for row in _rows(root, "consent-policy"):
        fields = _fields(row.inputs)
        assume_yes, accepted = fields["assume_yes"], fields["accepted"]
        assert isinstance(assume_yes, bool)
        assert isinstance(accepted, bool)
        assert_oracle(
            lambda values: consented(assume_yes=values[0], accepted=values[1]),
            (assume_yes, accepted),
            row.expected,
            row_id="prerequisite consent was bypassed: " + row.identifier,
        )
    for row in _rows(root, "prompt-answer"):
        assert_oracle(
            affirmative,
            _fields(row.inputs)["answer"],
            row.expected,
            row_id=row.identifier,
        )


def _context(directory: Path, family: str = "Linux") -> HostContext:
    """Construct every path and environment input without consulting host absence."""
    directory.mkdir(parents=True, exist_ok=True)
    return HostContext(
        family,
        "x86_64",
        directory / "home",
        directory / "cache",
        directory,
        (("PATH", str(directory / "bin")),),
        is_root=False,
        interactive=False,
        assume_yes=False,
    )


def _tool(directory: Path, name: str) -> str:
    """Create a discovery-only tool that injected value observations never execute."""
    path = directory / (name + (".exe" if platform.system() == "Windows" else ""))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("discovery candidate", encoding="utf-8")
    path.chmod(0o755)
    return str(path)


def test_probe_values_and_private_link_artifacts(tmp_path: Path) -> None:
    """Explicit boundary outcomes cover Linux linking and the Xcode probe."""
    context = _context(tmp_path)
    binary = tmp_path / "bin"
    compiler = _tool(binary, "cc")
    curl = Path(_tool(binary, "curl"))
    _tool(binary, "make")
    certificate = tmp_path / "ca.pem"
    certificate.write_text("owned certificate-store observation", encoding="utf-8")
    observed: list[tuple[str, ...]] = []

    def success(
        arguments: tuple[str, ...], _context: HostContext
    ) -> Result[Output, SpawnError]:
        observed.append(arguments)
        if len(arguments) == LINK_ARGUMENT_COUNT:
            assert (
                Path(arguments[1]).read_text(encoding="utf-8")
                == "int main(void) { return 0; }\n"
            )
            assert arguments[2:4] == ("-lgmp", "-o")
            assert Path(arguments[1]).is_relative_to(context.cache)
            assert Path(arguments[4]).is_relative_to(context.cache)
        else:
            assert arguments[1:] == ("-p",)
        return Ok(Output(0, "", ""))

    measured = probe(context, success, (str(certificate), None))
    assert measured == Ok(
        (
            Prerequisite("compiler-and-gmp", ready=True),
            Prerequisite("downloader", ready=True),
            Prerequisite("ca-certificates", ready=True),
            Prerequisite("make", ready=True),
        )
    )
    assert Path(observed[0][0]) == Path(compiler)
    assert list(context.cache.iterdir()) == []
    curl.unlink()
    _tool(binary, "wget")
    assert probe(context, success, (None, str(tmp_path))) == measured
    Path(compiler).unlink()
    absent = probe(context, success, (None, None))
    assert absent == Ok(
        (
            Prerequisite("compiler-and-gmp", ready=False),
            Prerequisite("downloader", ready=True),
            Prerequisite("ca-certificates", ready=False),
            Prerequisite("make", ready=True),
        )
    )
    mac = replace(context, family="Darwin")
    assert probe(mac, success) == Ok((Prerequisite("xcode-clt", ready=False),))
    xcode = _tool(binary, "xcode-select")
    assert probe(mac, success) == Ok((Prerequisite("xcode-clt", ready=True),))
    assert Path(observed[-1][0]) == Path(xcode)
    assert observed[-1][1:] == ("-p",)
    assert probe(replace(context, family="Windows"), success) == Ok(())
    assert isinstance(probe(replace(context, family="Other"), success), Err)
    assert certificate_store((str(certificate), None))
    assert certificate_store((str(tmp_path / "absent-ca"), str(tmp_path)))
    assert not certificate_store((str(tmp_path / "absent-ca"), None))
    assert not certificate_store((None, str(tmp_path / "absent-directory")))


def test_probe_failures_are_not_ready(tmp_path: Path) -> None:
    """Failed invocations and inaccessible probe storage never count as success."""
    context = _context(tmp_path)
    compiler = _tool(tmp_path / "bin", "cc")

    def failed(
        _arguments: tuple[str, ...], _context: HostContext
    ) -> Result[Output, SpawnError]:
        return Err(SpawnError("constructed launch failure"))

    assert link_gmp(compiler, context, failed) == Ok(value=False)
    assert isinstance(probe(context, failed), Ok)
    context.cache.rmdir()
    context.cache.write_text("blocks directory creation", encoding="utf-8")
    assert isinstance(link_gmp(compiler, context, failed), Err)
    assert isinstance(probe(context, failed), Err)
    assert successful(Ok(Output(0, "", "")))
    assert not successful(Ok(Output(1, "", "")))
    assert not successful(Err(SpawnError("not executable")))


def _approved(
    root: Path, directory: Path
) -> tuple[GrantedPrerequisites, HostContext, tuple[Value, ...]]:
    """Pair a rendered action with independently stored command expectations."""
    row = next(
        row
        for row in _rows(root, "package-set")
        if row.identifier == "prerequisites.packages.ubuntu.user.assume-yes"
    )
    selected = proposal(_facts(row.inputs, directory))
    assert isinstance(selected, Ok)
    assert len(selected.value) == 1
    expected = _fields(row.expected)["commands"]
    assert isinstance(expected, tuple)
    assert expected
    return GrantedPrerequisites(selected.value[0]), _context(directory), expected


def _ready() -> tuple[Prerequisite, ...]:
    """Construct the fixed Linux post-install observation rather than infer it."""
    return (
        Prerequisite("compiler-and-gmp", ready=True),
        Prerequisite("downloader", ready=True),
        Prerequisite("ca-certificates", ready=True),
        Prerequisite("make", ready=True),
    )


def test_apply_sequence_and_first_failure(root: Path, tmp_path: Path) -> None:
    """Apply approved argv in order and stop before later commands or a re-probe."""
    granted, context, expected = _approved(root, tmp_path)
    calls: list[tuple[str, ...]] = []
    examinations: list[HostContext] = []

    def attempt(
        arguments: tuple[str, ...], _context: HostContext
    ) -> Result[Output, SpawnError]:
        calls.append(arguments)
        return Ok(Output(0, "", ""))

    def examine(
        value: HostContext,
    ) -> Result[tuple[Prerequisite, ...], PrerequisiteError]:
        examinations.append(value)
        return Ok(_ready())

    assert apply(granted, context, examine, attempt) == Ok(_ready())
    assert freeze([list(command) for command in calls]) == expected
    assert examinations == [context]
    calls.clear()
    examinations.clear()

    def failed(
        arguments: tuple[str, ...], _context: HostContext
    ) -> Result[Output, SpawnError]:
        calls.append(arguments)
        return Ok(Output(1, "", "controlled failure"))

    result = apply(granted, context, examine, failed)
    assert isinstance(result, Err)
    assert result.error.reason == "prerequisite-install-failed"
    assert freeze([list(command) for command in calls]) == (expected[0],)
    assert examinations == []


def test_post_probe_failure_does_not_reinstall(root: Path, tmp_path: Path) -> None:
    """Failed or incomplete post-install probes report errors after one attempt."""
    granted, context, expected = _approved(root, tmp_path)
    calls: list[tuple[str, ...]] = []
    examinations: list[HostContext] = []

    def attempt(
        arguments: tuple[str, ...], _context: HostContext
    ) -> Result[Output, SpawnError]:
        calls.append(arguments)
        return Ok(Output(0, "", ""))

    observations: tuple[
        tuple[Result[tuple[Prerequisite, ...], PrerequisiteError], str], ...
    ] = (
        (
            Ok((*_ready()[:-1], Prerequisite("make", ready=False))),
            "prerequisite-still-missing",
        ),
        (
            Err(PrerequisiteError("prerequisite-probe-failed", "controlled failure")),
            "prerequisite-probe-failed",
        ),
        (Ok(()), "prerequisite-probe-failed"),
    )
    for observation, reason in observations:
        calls.clear()
        examinations.clear()

        def examine(
            value: HostContext,
            result: Result[tuple[Prerequisite, ...], PrerequisiteError] = observation,
        ) -> Result[tuple[Prerequisite, ...], PrerequisiteError]:
            examinations.append(value)
            return result

        result = apply(granted, context, examine, attempt)
        assert isinstance(result, Err)
        assert result.error.reason == reason
        assert freeze([list(command) for command in calls]) == expected
        assert examinations == [context]
    assert not complete("Other", ())
    assert not complete("Linux", _ready()[::-1])
    assert complete("Windows", ())


def test_xcode_pending_does_not_probe(tmp_path: Path) -> None:
    """A successful dialog request stops immediately without a re-probe or install."""
    context = replace(_context(tmp_path), family="Darwin")
    calls: list[tuple[str, ...]] = []
    examinations: list[HostContext] = []

    def attempt(
        arguments: tuple[str, ...], _context: HostContext
    ) -> Result[Output, SpawnError]:
        calls.append(arguments)
        return Ok(Output(0, "", ""))

    def examine(
        value: HostContext,
    ) -> Result[tuple[Prerequisite, ...], PrerequisiteError]:
        examinations.append(value)
        return Ok(())

    result = apply(GrantedPrerequisites(XcodeInstall()), context, examine, attempt)
    assert isinstance(result, Err)
    assert result.error.reason == "xcode-pending"
    assert calls == [("xcode-select", "--install")]
    assert examinations == []


def test_observation_completes_cold_facts_and_preserves_warm_pins(
    root: Path, tmp_path: Path
) -> None:
    """Cold facts gain one complete probe result; warm facts trigger no probe."""
    row = next(
        row
        for row in _rows(root, "package-set")
        if row.identifier == "prerequisites.packages.ubuntu.user.assume-yes"
    )
    facts = _facts(row.inputs, tmp_path)
    context = _context(tmp_path)
    calls: list[HostContext] = []

    def healthy(
        value: HostContext,
    ) -> Result[tuple[Prerequisite, ...], PrerequisiteError]:
        calls.append(value)
        return Ok(_ready())

    assert observe(facts, context, healthy) == Ok(
        replace(facts, prerequisites=_ready())
    )
    assert calls == [context]
    calls.clear()
    warm = replace(facts, ghc=str(tmp_path / "ghc"), cabal=str(tmp_path / "cabal"))
    assert observe(warm, context, healthy) == Ok(warm)
    assert calls == []

    def incomplete(
        _context: HostContext,
    ) -> Result[tuple[Prerequisite, ...], PrerequisiteError]:
        return Ok(())

    incomplete_result = observe(facts, context, incomplete)
    assert isinstance(incomplete_result, Err)
    assert incomplete_result.error.reason == "prerequisite-probe-failed"

    def broken(
        _context: HostContext,
    ) -> Result[tuple[Prerequisite, ...], PrerequisiteError]:
        return Err(PrerequisiteError("prerequisite-probe-failed", "controlled failure"))

    assert observe(facts, context, broken) == Err(
        PrerequisiteError("prerequisite-probe-failed", "controlled failure")
    )
