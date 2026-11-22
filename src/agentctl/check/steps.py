# Copyright (c) 2026 agentctl contributors.
"""Isolated orchestration for every introduced check step."""

import hashlib
import json
import os
import secrets
import shutil
import sys
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

import click

from agentctl import foundation_host as hostfacts
from agentctl.bootstrap.pins import load as load_pins
from agentctl.check import (
    coverage_hosts,
    evidence,
    haskell,
    identity,
    lanes,
    mutant_report,
    ownership,
    phase_reports,
    ratchet,
    style,
    writeguard,
)
from agentctl.check.legs import Leg, python_legs, targets, verdict
from agentctl.check.mutants import Mutant, MutationError, census_corpus, corpus
from agentctl.check.plan_data import Phase, field, phase_text, phases, section, table
from agentctl.check.preconditions import inspect, inspect_socket, single_run
from agentctl.check.prerequisites import inspect_prerequisites
from agentctl.check.toolchain import EnsureStep, inspect_toolchain, run_step
from agentctl.check.validator import closure
from agentctl.check.validator.docs import validate as docs
from agentctl.check.validator.plan import validate as plan
from agentctl.check.validator.source import configuration, forbidden_surfaces, sources
from agentctl.foundation import Err, Family, Ok, Result
from agentctl.foundation_paths import directories
from agentctl.foundation_process import run

PYTHON_LEG_TIMEOUT_SECONDS = 2 * 60 * 60
CHECK_TIMEOUT_SECONDS = 8 * PYTHON_LEG_TIMEOUT_SECONDS
ORACLE_LEGS = ("oracle-validation", "bootstrap-provenance")
FINALIZER_NAMES = (
    "ratchet",
    "containment",
    "write-guard",
    "oracle-outcomes",
    "oracle-details",
    "tool-outcomes",
    "tool-substeps",
    "pytest-manifest",
    "mutant-killers",
    "native-observation",
    "host-observation",
    "finalizer-record",
)
FINALIZER_SEAL = "agentctl-finalizer-v1"
FINALIZER_SEAL_FIELDS = 3
PROVISIONAL_SEAL = "agentctl-provisional-v1"
PROVISIONAL_HANDOFF_LINES = 2
KILLER_SEAL = "agentctl-mutant-killers-v1"
KILLER_HANDOFF_LINES = 3
TOOLCHAIN_OWNER = 2
TOOLCHAIN_SOURCE = "src/agentctl/check/toolchain.py"
PREREQUISITE_SOURCE = "src/agentctl/check/prerequisites.py"
TOOLCHAIN_FAILURE = "unattributed tool failure: toolchain-ensure"


ENVIRONMENT = frozenset(
    {
        "PATH",
        "HOME",
        "USER",
        "XDG_CACHE_HOME",
        "XDG_DATA_HOME",
        "XDG_STATE_HOME",
        "XDG_CONFIG_HOME",
        "XDG_BIN_HOME",
        "GHCUP_INSTALL_BASE_PREFIX",
        "GHCUP_USE_XDG_DIRS",
        "CLAUDE_CONFIG_DIR",
        "CLAUDE_CODE_OAUTH_TOKEN",
        "CLAUDE_CODE_USE_BEDROCK",
        "CLAUDE_CODE_USE_VERTEX",
        "CLAUDE_CODE_USE_FOUNDRY",
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_AUTH_TOKEN",
        "CODEX_HOME",
        "CODEX_SQLITE_HOME",
        "OPENAI_API_KEY",
        "CODEX_API_KEY",
        "CODEX_ACCESS_TOKEN",
        "SYSTEMROOT",
        "USERPROFILE",
        "APPDATA",
        "LOCALAPPDATA",
        "PATHEXT",
        "COMSPEC",
    }
)


@dataclass(frozen=True, slots=True)
class CheckRun:
    """The immutable subject, private storage and identity of one gate run."""

    root: Path
    directory: Path
    nonce: str
    family: Family


@dataclass(frozen=True, slots=True)
class PostRunInputs:
    """Captured corpus and optional owner and phase declarations."""

    records: tuple[Mutant, ...]
    mutant_owners: tuple[tuple[str, int], ...] | closure.CapturedPolicy | None = None
    observed_phases: tuple[Phase, ...] | None = None
    source_entries: tuple[evidence.Entry, ...] | None = None
    tool_schedule: tuple[str, ...] | None = None
    pending_native: bool = False


@dataclass(frozen=True, slots=True)
class NativeSnapshot:
    """Native cases and their sources bound to the captured checkout census."""

    manifest: evidence.RunEvidence
    sources: tuple[tuple[str, str], ...]
    entries: tuple[evidence.Entry, ...]


@dataclass(frozen=True, slots=True)
class Finalization:
    """Independent shared containment and checkout-integrity outcomes."""

    containment: int
    write_guard: int


@dataclass(frozen=True, slots=True)
class ValidationOutcome:
    """Gate status and the original oracle observation for finalizer checks."""

    code: int
    oracle: Result[evidence.LegEvidence, str]
    oracle_details: Result[evidence.OracleDetails, evidence.EvidenceError]
    tools: Result[evidence.LegEvidence, str]
    substeps: Result[evidence.ToolSubsteps, str]
    pytest: Result[evidence.RunEvidence, str] | None = None
    native: Result[NativeSnapshot, str] | None = None
    host: Result[lanes.HostFacts, str] | None = None
    phase_observations: Result[tuple[phase_reports.PhaseResult, ...], str] | None = None
    killers: Result[mutant_report.Report, str] | None = None


@dataclass(frozen=True, slots=True)
class ToolOutcome:
    """Aggregate tool status and original ordered execution observations."""

    code: int
    evidence: Result[evidence.LegEvidence, str]
    substeps: Result[evidence.ToolSubsteps, str]
    pytest: Result[evidence.RunEvidence, str] | None = None
    native: Result[NativeSnapshot, str] | None = None
    host: Result[lanes.HostFacts, str] | None = None
    killers: Result[mutant_report.Report, str] | None = None


@dataclass(frozen=True, slots=True)
class LegOutcome:
    """A leg's aggregate status and each subprocess actually attempted."""

    code: int
    substeps: tuple[int, ...]
    pytest: Result[evidence.RunEvidence, str] | None = None
    host: Result[lanes.HostFacts, str] | None = None
    killers: Result[mutant_report.Report, str] | None = None


@dataclass(frozen=True, slots=True)
class ProvisionalPhaseInputs:
    """Captured observations awaiting complete run and finalizer authentication."""

    work: ownership.ScopedPhaseWork
    manifest: evidence.RunEvidence
    nonce: str
    collection: Result[tuple[tuple[int, frozenset[str]], ...], str]
    native: Result[tuple[tuple[int, frozenset[str]], ...], str]
    oracle: Result[tuple[ownership.OracleScope, ...], str]
    shared: frozenset[str] = frozenset()
    scoped_tools: tuple[tuple[int, frozenset[str]], ...] = ()


@dataclass(frozen=True, slots=True)
class ToolFailureAttribution:
    """Conservative shared and explicitly owned tool failure observations."""

    shared: frozenset[str]
    scoped: tuple[tuple[int, frozenset[str]], ...]


@dataclass(frozen=True, slots=True)
class ProvisionalCapture:
    """The original gate observations used by the provisional phase join."""

    census: Result[tuple[evidence.Entry, ...], str]
    phases: Result[tuple[Phase, ...], str]
    tools: ToolOutcome
    claims: tuple[tuple[Mutant, ...], tuple[tuple[str, int], ...]] | None
    oracle: Result[tuple[ownership.OracleScope, ...], str]
    nonce: str
    schedule: tuple[str, ...]
    substep_schedule: tuple[tuple[str, int], ...]
    readiness: tuple[str, ...] = ()


def environment(
    inherited: Mapping[str, str], run_dir: Path, nonce: str, *, tool: str = "check"
) -> dict[str, str]:
    """Scrub inherited controls and supply only run-owned tool settings."""
    return {
        **{key: value for key, value in inherited.items() if key in ENVIRONMENT},
        "LC_ALL": "C.UTF-8",
        "PYTHONUTF8": "1",
        "PYTHONIOENCODING": "utf-8",
        "TMPDIR": run_dir.as_posix(),
        "TEMP": run_dir.as_posix(),
        "TMP": run_dir.as_posix(),
        "PYTHONPYCACHEPREFIX": (run_dir / "bytecode").as_posix(),
        **(
            {
                "XDG_CONFIG_HOME": (run_dir / "ty-config").as_posix(),
                "APPDATA": (run_dir / "ty-config").as_posix(),
            }
            if tool == "ty"
            else {}
        ),
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
        "AGENTCTL_CHECK_NONCE": nonce,
        "AGENTCTL_CHECK_MANIFEST": (run_dir / "pytest-manifest.json").as_posix(),
    }


def _run_leg_observed(root: Path, run_dir: Path, nonce: str, leg: Leg) -> LegOutcome:
    """Preserve the primary failure while running explicitly independent reports."""
    primary = 0
    substeps: tuple[int, ...] = ()
    pytest: Result[evidence.RunEvidence, str] | None = None
    host: Result[lanes.HostFacts, str] | None = None
    killers: Result[mutant_report.Report, str] | None = None
    for index, command in enumerate((leg.argv, *leg.after)):
        result = run(
            list(command),
            cwd=root,
            env=environment(os.environ, run_dir, nonce, tool=leg.name),
            timeout=PYTHON_LEG_TIMEOUT_SECONDS,
        )
        if isinstance(result, Err):
            click.echo(f"{leg.name}: {result.error.message}", err=True)
            code = 1
        else:
            click.echo(result.value.stdout, nl=False)
            click.echo(result.value.stderr, nl=False, err=True)
            code = result.value.code
        substeps += (code,)
        if leg.name == "pytest" and index == 0:
            pytest = pytest_observation(run_dir, nonce)
            host = host_observation(run_dir, nonce)
            killers = mutant_report.read(run_dir / "mutant-killers.json", nonce)
        if code:
            if index:
                click.echo(f"{leg.name}: followup failed with status {code}", err=True)
            primary = primary or code
            if index or not leg.after_failure:
                return LegOutcome(primary, substeps, pytest, host, killers)
    return LegOutcome(primary, substeps, pytest, host, killers)


def run_leg(root: Path, run_dir: Path, nonce: str, leg: Leg) -> int:
    """Run a subprocess-backed leg and expose its aggregate result."""
    return _run_leg_observed(root, run_dir, nonce, leg).code


def _run_tools_observed(
    root: Path,
    run_dir: Path,
    nonce: str,
    legs: tuple[
        Leg
        | EnsureStep
        | haskell.HaskellStep
        | style.StyleStep
        | identity.IdentityStep,
        ...,
    ],
    *,
    source_entries: tuple[evidence.Entry, ...] | None = None,
) -> ToolOutcome:
    """Run every introduced leg in order and retain each independent outcome."""
    outcomes: tuple[tuple[str, int], ...] = ()
    substeps: tuple[tuple[str, tuple[int, ...]], ...] = ()
    pytest: Result[evidence.RunEvidence, str] | None = None
    native: Result[NativeSnapshot, str] | None = None
    host: Result[lanes.HostFacts, str] | None = None
    killers: Result[mutant_report.Report, str] | None = None
    for leg in legs:
        if isinstance(leg, EnsureStep):
            code = run_step(leg)
        elif isinstance(leg, haskell.HaskellStep):
            code = haskell.run_step(leg, run_dir, nonce)
            native = _capture_native_step(leg, run_dir, nonce, source_entries) or native
        elif isinstance(leg, style.StyleStep):
            code = style.run_step(step=leg)
        elif isinstance(leg, identity.IdentityStep):
            code = identity.run_step(step=leg)
        else:
            result = _run_leg_observed(root, run_dir, nonce, leg)
            code = result.code
            substeps += ((leg.name, result.substeps),)
            pytest = result.pytest or pytest
            host = result.host or host
            killers = result.killers or killers
        outcomes += ((leg.name, code),)
        click.echo(f"{leg.name}: {'pass' if code == 0 else 'FAIL'}")
    try:
        (run_dir / "tool-outcomes.json").write_text(
            json.dumps({"nonce": nonce, "outcomes": outcomes}), encoding="utf-8"
        )
        (run_dir / "tool-substeps.json").write_text(
            json.dumps({"nonce": nonce, "outcomes": substeps}), encoding="utf-8"
        )
    except (OSError, UnicodeError) as exc:
        click.echo("tool outcomes: cannot write run record: " + str(exc), err=True)
        return ToolOutcome(
            1, Err("cannot write tool outcomes"), Err("cannot write tool substeps")
        )
    observed = evidence.read_legs(
        run_dir / "tool-outcomes.json", nonce, tuple(leg.name for leg in legs)
    )
    if isinstance(observed, Err):
        click.echo("tool outcomes: " + observed.error.message, err=True)
        return ToolOutcome(
            1, Err(observed.error.message), Err("tool outcomes unavailable")
        )
    if observed.value.outcomes != outcomes:
        click.echo("tool outcomes: execution record changed", err=True)
        return ToolOutcome(
            1, Err("tool execution record changed"), Err("tool outcomes changed")
        )
    expected_substeps = tuple(
        (leg.name, 1 + len(leg.after)) for leg in legs if isinstance(leg, Leg)
    )
    observed_substeps = evidence.read_tool_substeps(
        run_dir / "tool-substeps.json", nonce, expected_substeps
    )
    if (
        isinstance(observed_substeps, Err)
        or observed_substeps.value.outcomes != substeps
    ):
        click.echo("tool substeps: execution record changed or unreadable", err=True)
        return ToolOutcome(
            1,
            Ok(evidence.LegEvidence(nonce, outcomes)),
            Err("tool substep record changed"),
        )
    return ToolOutcome(
        0 if verdict(tuple(leg.name for leg in legs), observed.value.outcomes) else 1,
        Ok(evidence.LegEvidence(nonce, outcomes)),
        Ok(evidence.ToolSubsteps(nonce, substeps)),
        pytest,
        native,
        host,
        killers,
    )


def run_tools(
    root: Path,
    run_dir: Path,
    nonce: str,
    legs: tuple[
        Leg
        | EnsureStep
        | haskell.HaskellStep
        | style.StyleStep
        | identity.IdentityStep,
        ...,
    ],
) -> int:
    """Run the complete tool schedule and expose its aggregate status."""
    return _run_tools_observed(root, run_dir, nonce, legs).code


def tool_outcomes_unchanged(
    run_dir: Path, nonce: str, before: Result[evidence.LegEvidence, str]
) -> int:
    """Require the actual ordered tool results to survive later execution."""
    path = run_dir / "tool-outcomes.json"
    if isinstance(before, Err) or path.is_symlink():
        click.echo("tool outcomes: original record unavailable", err=True)
        return 1
    names = tuple(name for name, _code in before.value.outcomes)
    after = evidence.read_legs(path, nonce, names)
    if isinstance(after, Err) or after.value != before.value:
        click.echo("tool outcomes: missing, stale or changed run record", err=True)
        return 1
    return 0


def tool_substeps_unchanged(
    run_dir: Path, nonce: str, before: Result[evidence.ToolSubsteps, str]
) -> int:
    """Require each recorded subprocess status to survive later execution."""
    if isinstance(before, Err):
        click.echo("tool substeps: original record unavailable", err=True)
        return 1
    expected = tuple((name, len(codes)) for name, codes in before.value.outcomes)
    after = evidence.read_tool_substeps(run_dir / "tool-substeps.json", nonce, expected)
    if (
        isinstance(after, Err)
        or before.value.outcomes != after.value.outcomes
        or before.value.nonce != after.value.nonce
    ):
        click.echo("tool substeps: missing, stale or changed run record", err=True)
        return 1
    return 0


def native_snapshot(
    run_dir: Path, nonce: str, entries: tuple[evidence.Entry, ...]
) -> Result[NativeSnapshot, str]:
    """Read the native manifest, XML report and case sources from this run."""
    if (run_dir / "haskell-manifest.json").is_symlink():
        return Err("native manifest is a symlink")
    manifest = haskell.native_observation(run_dir, nonce)
    if isinstance(manifest, Err):
        return Err(manifest.error.message)
    sources = haskell.read_sources(run_dir, nonce, manifest.value.collected, entries)
    if isinstance(sources, Err):
        return Err(sources.error.message)
    return Ok(NativeSnapshot(manifest.value, sources.value, entries))


def _capture_native_step(
    leg: haskell.HaskellStep,
    run_dir: Path,
    nonce: str,
    entries: tuple[evidence.Entry, ...] | None,
) -> Result[NativeSnapshot, str] | None:
    """Capture a native test result before any following tool starts."""
    return (
        native_snapshot(run_dir, nonce, entries)
        if leg.name == "cabal-test" and entries is not None
        else None
    )


def native_snapshot_unchanged(
    run_dir: Path, nonce: str, before: Result[NativeSnapshot, str] | None
) -> int:
    """Require native execution and source evidence to remain unchanged."""
    if before is None or isinstance(before, Err):
        click.echo("native observation: original record unavailable", err=True)
        return 1
    after = native_snapshot(run_dir, nonce, before.value.entries)
    if (
        isinstance(after, Err)
        or before.value.manifest != after.value.manifest
        or before.value.sources != after.value.sources
        or before.value.entries != after.value.entries
    ):
        click.echo("native observation: missing, stale or changed record", err=True)
        return 1
    return 0


def host_observation(run_dir: Path, nonce: str) -> Result[lanes.HostFacts, str]:
    """Read this run's nonce-bound host facts without following a symlink."""
    observed = lanes.read_host(run_dir / "host.json", nonce)
    return Err(observed.error.message) if isinstance(observed, Err) else observed


def host_observation_unchanged(
    run_dir: Path, nonce: str, before: Result[lanes.HostFacts, str] | None
) -> int:
    """Require original host facts to survive later tools and finalizers."""
    after = host_observation(run_dir, nonce)
    if (
        before is None
        or isinstance(before, Err)
        or isinstance(after, Err)
        or before.value != after.value
    ):
        click.echo("host observation: missing, stale or changed record", err=True)
        return 1
    return 0


def pytest_observation(run_dir: Path, nonce: str) -> Result[evidence.RunEvidence, str]:
    """Read this run's pytest manifest without following a symlink."""
    path = run_dir / "pytest-manifest.json"
    if path.is_symlink():
        return Err("pytest manifest is a symlink")
    observed = evidence.read_manifest(path)
    if isinstance(observed, Err):
        return Err(observed.error.message)
    if not nonce or observed.value.nonce != nonce:
        return Err("pytest manifest nonce mismatch")
    return observed


def pytest_manifest_unchanged(
    run_dir: Path, nonce: str, before: Result[evidence.RunEvidence, str] | None
) -> int:
    """Require the original pytest observation to survive subsequent execution."""
    after = pytest_observation(run_dir, nonce)
    if (
        before is None
        or isinstance(before, Err)
        or isinstance(after, Err)
        or after.value != before.value
    ):
        click.echo("pytest observation: missing, stale or changed manifest", err=True)
        return 1
    return 0


def mutant_killers_unchanged(
    run_dir: Path, nonce: str, before: Result[mutant_report.Report, str] | None
) -> int:
    """Require the original per-killer record bytes to survive later execution."""
    after = mutant_report.read(run_dir / "mutant-killers.json", nonce)
    if (
        before is None
        or isinstance(before, Err)
        or isinstance(after, Err)
        or before.value != after.value
    ):
        click.echo("mutant killers: missing, stale or changed report", err=True)
        return 1
    return 0


def mutant_killers_match(
    observed: Result[mutant_report.Report, str] | None,
    records: Result[tuple[Mutant, ...], MutationError],
    pytest: Result[evidence.RunEvidence, str] | None,
) -> int:
    """Join the original report to captured corpus and pytest observations."""
    if (
        observed is None
        or isinstance(observed, Err)
        or isinstance(records, Err)
        or pytest is None
        or isinstance(pytest, Err)
    ):
        click.echo("mutant killers: captured inputs unavailable", err=True)
        return 1
    result = mutant_report.validate(observed.value, records.value, pytest.value)
    if isinstance(result, Err):
        click.echo("mutant killers: " + result.error, err=True)
        return 1
    return 0


def report_pytest_leg(run_dir: Path, tools: ToolOutcome) -> int:
    """Report shared pytest-leg damage without issuing phase verdicts."""
    manifest = evidence.read_manifest(run_dir / "pytest-manifest.json")
    if (
        isinstance(manifest, Err)
        or isinstance(tools.evidence, Err)
        or isinstance(tools.substeps, Err)
    ):
        click.echo("pytest-observation: execution evidence unavailable", err=True)
        return 1
    result = phase_reports.pytest_leg_failures(
        manifest.value, tools.evidence.value, tools.substeps.value
    )
    if isinstance(result, Err):
        click.echo("pytest-observation: " + result.error, err=True)
        return 1
    for failure in sorted(result.value):
        click.echo(
            "pytest-observation: " + failure + " (shared; not a verdict)", err=True
        )
    return int(bool(result.value))


def oracle_check(root: Path, run_dir: Path, nonce: str) -> int:
    """Run oracle validation and bootstrap provenance independently."""
    oracle = (
        "from pathlib import Path; from tests.harness.oracle import "
        "check_tree, tree_observations; "
        "import json, sys; sources, issues = tree_observations(Path(sys.argv[1])); "
        "record = {'nonce': sys.argv[3], 'sources': sources, "
        "'issues': [[issue.source, issue.message] for issue in issues]}; "
        "path = Path(sys.argv[2]) / 'oracle-details.json'; "
        "stream = path.open('x', encoding='utf-8'); "
        "json.dump(record, stream); stream.close(); "
        "sys.stderr.write('\\n'.join(issue.message for issue in issues)); "
        "sys.exit(bool(issues))"
    )
    bootstrap = (
        "from pathlib import Path; "
        "from tests.harness.bootstrap_origin import bootstrap_before; "
        "import sys; bootstrap_before(Path(sys.argv[1]), sys.argv[2])"
    )
    commands = (
        (oracle, str(root), str(run_dir), nonce),
        (bootstrap, str(run_dir), nonce),
    )
    names = ORACLE_LEGS
    outcomes: tuple[tuple[str, int], ...] = ()
    failed = False
    for name, command in zip(names, commands, strict=True):
        result = run(
            [sys.executable, "-c", *command],
            cwd=root,
            env=environment(os.environ, run_dir, nonce),
        )
        if isinstance(result, Err):
            click.echo(result.error.message, err=True)
            outcomes += ((name, 1),)
            failed = True
            continue
        click.echo(result.value.stderr, nl=False, err=True)
        outcomes += ((name, result.value.code),)
        failed = failed or result.value.code != 0
    try:
        path = run_dir / "oracle-outcomes.json"
        with path.open("x", encoding="utf-8") as stream:
            json.dump({"nonce": nonce, "outcomes": outcomes}, stream)
    except (OSError, UnicodeError) as exc:
        click.echo("oracle outcomes: cannot write run record: " + str(exc), err=True)
        return 1
    observed = evidence.read_legs(path, nonce, names)
    if isinstance(observed, Err) or observed.value.outcomes != outcomes:
        click.echo("oracle outcomes: execution record changed or unreadable", err=True)
        return 1
    return int(failed)


def oracle_observation(run_dir: Path, nonce: str) -> Result[evidence.LegEvidence, str]:
    """Read the two ordered, run-specific oracle outcomes without following links."""
    path = run_dir / "oracle-outcomes.json"
    if path.is_symlink():
        return Err("oracle outcome record is a symlink")
    observed = evidence.read_legs(path, nonce, ORACLE_LEGS)
    return Err(observed.error.message) if isinstance(observed, Err) else observed


def oracle_outcomes_unchanged(
    run_dir: Path, nonce: str, before: Result[evidence.LegEvidence, str]
) -> int:
    """Require the original oracle observation to survive the remaining tools."""
    after = oracle_observation(run_dir, nonce)
    if isinstance(before, Err) or isinstance(after, Err) or before.value != after.value:
        click.echo("oracle outcomes: missing, stale or changed run record", err=True)
        return 1
    return 0


def oracle_details_unchanged(
    run_dir: Path,
    nonce: str,
    before: Result[evidence.OracleDetails, evidence.EvidenceError],
) -> int:
    """Require the captured oracle details to survive later execution."""
    after = evidence.read_oracle_details(run_dir / "oracle-details.json", nonce)
    if isinstance(before, Err) or isinstance(after, Err) or after.value != before.value:
        click.echo("oracle details: missing, stale or changed run record", err=True)
        return 1
    return 0


def oracle_diagnostics(
    entries: tuple[evidence.Entry, ...],
    details: evidence.OracleDetails,
    outcomes: evidence.LegEvidence,
) -> Result[tuple[ownership.OracleScope, ...], str]:
    """Join recorded oracle failures to captured source ownership for diagnostics."""
    text = _census_text(entries, "src/agentctl/check/source_ownership.toml")
    if isinstance(text, Err):
        return text
    manifest = ownership.parse_manifest(text.value)
    if isinstance(manifest, Err):
        return manifest
    statuses = tuple(code for name, code in outcomes.outcomes if name == ORACLE_LEGS[0])
    if len(statuses) != 1 or details.nonce != outcomes.nonce:
        return Err("oracle details and tool outcomes have inconsistent identity")
    return ownership.oracle_issue_scopes(manifest.value, entries, details, statuses[0])


def report_oracle_diagnostics(
    run_dir: Path,
    nonce: str,
    census: Result[tuple[evidence.Entry, ...], str],
    outcomes: Result[evidence.LegEvidence, str],
) -> Result[tuple[ownership.OracleScope, ...], str]:
    """Emit attribution observations without presenting a phase verdict."""
    details = evidence.read_oracle_details(run_dir / "oracle-details.json", nonce)
    diagnostic = (
        oracle_diagnostics(census.value, details.value, outcomes.value)
        if isinstance(details, Ok)
        and isinstance(outcomes, Ok)
        and isinstance(census, Ok)
        else Err("oracle details, outcomes or source census unavailable")
    )
    if isinstance(diagnostic, Err):
        click.echo("oracle-observation: " + diagnostic.error, err=True)
    else:
        for phase in diagnostic.value:
            for failure in phase.failures:
                message = f"oracle-observation phase {phase.number}: {failure}"
                click.echo(message + " (not a verdict)", err=True)
    return diagnostic


COVERAGE_HOSTS = "src/agentctl/check/coverage_hosts.toml"


def coverage_sources(root: Path) -> Result[tuple[coverage_hosts.HostSource, ...], str]:
    """Read the declared host classes for host-confined sources."""
    try:
        text = (root / COVERAGE_HOSTS).read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        return Err("cannot read coverage host manifest: " + str(exc))
    return coverage_hosts.parse(text)


def coverage_foreign(root: Path, family: Family) -> tuple[str, ...]:
    """Omit nothing unless the complete manifest is valid."""
    declared = coverage_sources(root)
    return (
        coverage_hosts.foreign(declared.value, family)
        if isinstance(declared, Ok)
        else ()
    )


def coverage_host_problems(
    root: Path, entries: tuple[evidence.Entry, ...]
) -> tuple[str, ...]:
    """Report an invalid manifest or a declared source absent from the census."""
    declared = coverage_sources(root)
    if isinstance(declared, Err):
        return ("validators: coverage hosts: " + declared.error,)
    absent = coverage_hosts.missing(
        declared.value, frozenset(entry.path for entry in entries)
    )
    return tuple("validators: coverage hosts: missing " + path for path in absent)


def pipeline(
    root: Path,
    run_dir: Path,
    files: tuple[str, ...],
    family: Family,
    *,
    assume_yes: bool,
) -> tuple[
    Leg | EnsureStep | haskell.HaskellStep | style.StyleStep | identity.IdentityStep,
    ...,
]:
    """Insert provisioning after ty while retaining every introduced tool leg."""
    legs = python_legs(
        sys.executable, root, files, run_dir, coverage_foreign(root, family)
    )
    context = hostfacts.current(
        directories(family, os.environ, Path.home()).cache,
        assume_yes=assume_yes,
    )
    pins = load_pins()
    return (
        *legs[:-1],
        EnsureStep(replace(context, interactive=False), pins),
        style.StyleStep("fourmolu", context, root / "src/agentctl/haskell", pins),
        style.StyleStep("hlint", context, root / "src/agentctl/haskell", pins),
        haskell.HaskellStep("cabal-build", context, root / "src/agentctl/haskell"),
        identity.IdentityStep(
            context,
            root / "src/agentctl/haskell",
            directories(family, os.environ, Path.home()).data,
        ),
        haskell.HaskellStep("cabal-test", context, root / "src/agentctl/haskell"),
        legs[-1],
    )


def step_table(
    steps: tuple[
        Leg
        | EnsureStep
        | haskell.HaskellStep
        | style.StyleStep
        | identity.IdentityStep,
        ...,
    ],
) -> tuple[str, ...]:
    """Describe the full ordered gate around its actual executable middle steps."""
    return (
        "preconditions",
        "write-guard-snapshot",
        "validators",
        *(step.name for step in steps),
        "post-run-verifier",
        "ratchet",
        "containment",
        "write-guard-compare",
        "lane-summary",
    )


def inapplicable_message(subjects: tuple[str, ...]) -> str:
    """Render explicit Planned-owner observations without implying a passed check."""
    return "".join(
        "validators: not applicable: " + subject + " (owner Planned)\n"
        for subject in subjects
    )


def phase0_claim_problems(
    root: Path, entries: tuple[evidence.Entry, ...], records: tuple[Mutant, ...]
) -> tuple[str, ...]:
    """Check the declared Phase 0 subset without authorizing source ownership."""
    text = _census_text(entries, "src/agentctl/check/phase0_mutant_ownership.toml")
    if isinstance(text, Err):
        return ("validators: cannot read Phase 0 mutant claims: " + text.error,)
    observed = census_phases(root, entries)
    if isinstance(observed, Err):
        return ("validators: cannot read phase declarations: " + observed.error,)
    declarations = tuple(phase for phase in observed.value if phase.number == 0)
    parsed = ownership.parse_mutant_claims(text.value)
    if isinstance(parsed, Err):
        return ("validators: " + parsed.error,)
    if len(declarations) != 1:
        return ("validators: missing or duplicate Phase 0 declaration",)
    declared = frozenset(
        identifier
        for sprint in declarations[0].sprints
        for identifier in closure.mutant_ids(field(sprint.text, "Mutants"))
    )
    checked = ownership.check_phase_claims(parsed.value, records, declared, entries, 0)
    return ("validators: " + checked.error,) if isinstance(checked, Err) else ()


def source_ownership_problems(entries: tuple[evidence.Entry, ...]) -> tuple[str, ...]:
    """Require the current source census to have complete explicit ownership."""
    text = _census_text(entries, "src/agentctl/check/source_ownership.toml")
    if isinstance(text, Err):
        return ("validators: source ownership: " + text.error,)
    manifest = ownership.parse_manifest(text.value)
    if isinstance(manifest, Err):
        return ("validators: source ownership: " + manifest.error,)
    bound = ownership.bind_census(manifest.value, entries)
    return (
        ("validators: source ownership: " + bound.error,)
        if isinstance(bound, Err)
        else ()
    )


def test_consumer_problems(
    root: Path, entries: tuple[evidence.Entry, ...]
) -> tuple[str, ...]:
    """Compare cited Python test modules with their declared phase consumers."""
    text = _census_text(entries, "src/agentctl/check/source_ownership.toml")
    if isinstance(text, Err):
        return ("validators: test consumers: " + text.error,)
    manifest = ownership.parse_manifest(text.value)
    if isinstance(manifest, Err):
        return ("validators: test consumers: " + manifest.error,)
    declarations = census_phases(root, entries)
    if isinstance(declarations, Err):
        return ("validators: test consumers: " + declarations.error,)
    citations = phase_test_citations(declarations.value)
    return tuple(
        "validators: test consumers: " + problem
        for problem in ownership.test_consumer_problems(manifest.value, citations)
    )


def phase_test_citations(
    declarations: tuple[Phase, ...],
) -> tuple[tuple[int, str], ...]:
    """Extract each phase's cited Python tests from its captured declarations."""
    return tuple(
        (phase.number, node)
        for phase in declarations
        for text in (
            *(field(sprint.text, "Validation tests") for sprint in phase.sprints),
            *(
                cell
                for row in table(section(phase.text, "Gate Integrity"))
                for cell in row
            ),
        )
        for node in closure.test_ids(text)
        if node.startswith("tests/")
    )


def diagnostic_collection_scopes(
    manifest: ownership.OwnershipManifest, declarations: tuple[Phase, ...]
) -> Result[
    tuple[tuple[phase_reports.CollectionScope, ...], tuple[tuple[int, str], ...]], str
]:
    """Retain phase-local missing declarations without inventing ownership."""
    numbers = tuple(phase.number for phase in declarations)
    if len(numbers) != len(set(numbers)) or frozenset(numbers) != frozenset(
        phase.number for phase in manifest.phases
    ):
        return Err("invalid collection phase declarations")
    citations = phase_test_citations(declarations)
    issues = tuple(
        (number, problem)
        for number, node in citations
        for problem in ownership.test_consumer_problems(manifest, ((number, node),))
    )
    scopes = tuple(
        phase_reports.CollectionScope(
            number,
            frozenset(node for owner, node in citations if owner == number),
            frozenset(
                artifact.path
                for artifact in manifest.artifacts
                if artifact.path.startswith("tests/")
                and artifact.path.endswith(".py")
                and number in artifact.consumers
            )
            | frozenset(
                node.split("::", 1)[0] for owner, node in citations if owner == number
            ),
        )
        for number in numbers
    )
    return Ok((scopes, issues))


def fragment_claim_problems(
    entries: tuple[evidence.Entry, ...], records: tuple[Mutant, ...]
) -> tuple[str, ...]:
    """Check declared partial claim fragments without certifying corpus coverage."""
    text = _census_text(entries, "src/agentctl/check/source_ownership.toml")
    if isinstance(text, Err):
        return ("validators: mutant claims: " + text.error,)
    manifest = ownership.parse_manifest(text.value)
    if isinstance(manifest, Err):
        return ("validators: mutant claims: " + manifest.error,)
    fragments = tuple(
        item
        for item in manifest.value.artifacts
        if item.path.startswith("src/agentctl/check/")
        and item.path.endswith("_mutant_ownership.toml")
    )
    claims: tuple[ownership.MutantOwnership, ...] = ()
    problems: tuple[str, ...] = ()
    present_paths = frozenset(entry.path for entry in entries)
    for fragment in fragments:
        if not fragment.required and fragment.path not in present_paths:
            continue
        content = _census_text(entries, fragment.path)
        if isinstance(content, Err):
            problems += ("validators: mutant claims: " + content.error,)
            continue
        parsed = ownership.parse_mutant_claims(content.value)
        if isinstance(parsed, Err):
            problems += ("validators: mutant claims: " + parsed.error,)
            continue
        if any(claim.owner != fragment.owner for claim in parsed.value):
            problems += (
                "validators: mutant claim fragment owner mismatch: " + fragment.path,
            )
        claims += parsed.value
    return (
        *problems,
        *(
            "validators: mutant claims: " + problem
            for problem in ownership.partial_claim_problems(
                manifest.value, entries, records, claims
            )
        ),
    )


def _census_text(entries: tuple[evidence.Entry, ...], path: str) -> Result[str, str]:
    """Read one regular UTF-8 declaration from the supplied source observation."""
    matches = tuple(entry for entry in entries if entry.path == path)
    if len(matches) != 1:
        return Err("missing or duplicate census declaration: " + path)
    match matches[0].kind, matches[0].payloads:
        case "file", (bytes() as payload,):
            try:
                return Ok(payload.decode("utf-8"))
            except UnicodeError as exc:
                return Err(str(exc))
        case _:
            return Err("census declaration is not a regular file: " + path)


def census_phases(
    root: Path, entries: tuple[evidence.Entry, ...]
) -> Result[tuple[Phase, ...], str]:
    """Parse the observed plan files without rereading the live checkout."""
    candidates = tuple(
        entry.path
        for entry in entries
        if PurePosixPath(entry.path).parent == PurePosixPath("DEVELOPMENT_PLAN")
        and PurePosixPath(entry.path).name.startswith("phase-")
        and entry.path.endswith(".md")
    )
    if len(candidates) != len(set(candidates)):
        return Err("duplicate phase source")
    found: tuple[Phase, ...] = ()
    for path in candidates:
        content = _census_text(entries, path)
        if isinstance(content, Err):
            return content
        parsed = phase_text(
            root / path, content.value.replace("\r\n", "\n").replace("\r", "\n")
        )
        if parsed is not None:
            found += (parsed,)
    if not found or len({phase.number for phase in found}) != len(found):
        return Err("missing or duplicate phase declarations")
    return Ok(tuple(sorted(found, key=lambda phase: phase.number)))


def census_policy(
    entries: tuple[evidence.Entry, ...], owners: tuple[tuple[str, int], ...] | None
) -> Result[closure.CapturedPolicy, str]:
    """Read closure policy inputs from the guarded source observation."""
    standards = _census_text(entries, "DEVELOPMENT_PLAN/development_plan_standards.md")
    overview = _census_text(entries, "DEVELOPMENT_PLAN/00-overview.md")
    match standards, overview:
        case (Err(error), _) | (_, Err(error)):
            return Err(error)
        case Ok(standard), Ok(requirements):
            return Ok(
                closure.CapturedPolicy(
                    owners,
                    standard.replace("\r\n", "\n").replace("\r", "\n"),
                    requirements.replace("\r\n", "\n").replace("\r", "\n"),
                    frozenset(entry.path for entry in entries if entry.kind == "file"),
                    frozenset(
                        entry.path for entry in entries if entry.kind == "symlink"
                    ),
                    frozenset(
                        entry.path for entry in entries if entry.kind == "directory"
                    ),
                    evidence.digest_census(entries),
                )
            )


def _census_mutant_declarations(
    entries: tuple[evidence.Entry, ...],
) -> Result[
    tuple[ownership.OwnershipManifest, tuple[ownership.MutantOwnership, ...]], str
]:
    """Parse the manifest and claim fragments from the same observed census."""
    text = _census_text(entries, "src/agentctl/check/source_ownership.toml")
    if isinstance(text, Err):
        return text
    manifest = ownership.parse_manifest(text.value)
    if isinstance(manifest, Err):
        return Err(manifest.error)
    fragments = tuple(
        item
        for item in manifest.value.artifacts
        if item.path.startswith("src/agentctl/check/")
        and item.path.endswith("_mutant_ownership.toml")
    )
    claims: tuple[ownership.MutantOwnership, ...] = ()
    for fragment in fragments:
        if not fragment.required and not any(
            entry.path == fragment.path for entry in entries
        ):
            continue
        content = _census_text(entries, fragment.path)
        if isinstance(content, Err):
            return content
        parsed = ownership.parse_mutant_claims(content.value)
        if isinstance(parsed, Err):
            return parsed
        if any(claim.owner != fragment.owner for claim in parsed.value):
            return Err("mutant claim fragment owner mismatch: " + fragment.path)
        claims += parsed.value
    return Ok((manifest.value, claims))


def complete_mutant_owners(
    entries: tuple[evidence.Entry, ...], records: tuple[Mutant, ...]
) -> Result[tuple[tuple[str, int], ...], str]:
    """Bind the complete corpus to the guarded census and declared fragments."""
    declarations = _census_mutant_declarations(entries)
    if isinstance(declarations, Err):
        return declarations
    manifest, claims = declarations.value
    return ownership.bind_mutants(manifest, entries, records, claims)


def provisional_mutant_owners(
    entries: tuple[evidence.Entry, ...], records: tuple[Mutant, ...]
) -> Result[tuple[tuple[str, int], ...], str]:
    """Check complete declarations while leaving native locations unverified.

    The returned owners are provisional. A caller must require fresh native
    source evidence to match them before accepting a completed run.
    """
    declarations = _census_mutant_declarations(entries)
    if isinstance(declarations, Err):
        return declarations
    manifest, claims = declarations.value
    native = frozenset(
        (node, path)
        for claim in claims
        for node, path in claim.killer_sources
        if node.startswith("haskell:")
    )
    if not native:
        return Err("no native source declarations to defer")
    return ownership.bind_mutants_observed(
        manifest, entries, records, claims, tuple(sorted(native))
    )


def observed_native_mutant_owners(
    entries: tuple[evidence.Entry, ...],
    records: tuple[Mutant, ...],
    native_sources: tuple[tuple[str, str], ...],
) -> Result[tuple[tuple[str, int], ...], str]:
    """Join captured claims to native source observations without a verdict."""
    declarations = _census_mutant_declarations(entries)
    if isinstance(declarations, Err):
        return declarations
    manifest, claims = declarations.value
    return ownership.bind_mutants_observed(
        manifest, entries, records, claims, native_sources
    )


def scoped_mutant_ownership(
    entries: tuple[evidence.Entry, ...],
    records: tuple[Mutant, ...],
    native_sources: tuple[tuple[str, str], ...] | None = None,
) -> Result[tuple[ownership.MutantScope, ...], str]:
    """Observe scoped ownership problems without asserting a phase verdict."""
    declarations = _census_mutant_declarations(entries)
    if isinstance(declarations, Err):
        return declarations
    manifest, claims = declarations.value
    return ownership.attribute_mutant_claims(
        manifest, entries, records, claims, native_sources
    )


def scoped_source_inputs(
    entries: tuple[evidence.Entry, ...], declarations: tuple[Phase, ...]
) -> Result[ownership.ScopedPhaseWork, str]:
    """Derive phase source inputs and missing-source diagnostics from one census."""
    text = _census_text(entries, "src/agentctl/check/source_ownership.toml")
    if isinstance(text, Err):
        return text
    manifest = ownership.parse_manifest(text.value)
    if isinstance(manifest, Err):
        return manifest
    scopes = diagnostic_collection_scopes(manifest.value, declarations)
    if isinstance(scopes, Err):
        return scopes
    checks = tuple((scope.number, scope.required) for scope in scopes.value[0])
    return ownership.scoped_phase_work(manifest.value, entries, checks)


def report_scoped_source_inputs(
    census: Result[tuple[evidence.Entry, ...], str],
    declarations: Result[tuple[Phase, ...], str],
) -> None:
    """Report attributable missing inputs without claiming a phase verdict."""
    if isinstance(census, Err) or isinstance(declarations, Err):
        return
    observed = scoped_source_inputs(census.value, declarations.value)
    if isinstance(observed, Err):
        return
    for number, failures in observed.value.missing:
        for failure in sorted(failures):
            message = f"source-input-observation phase {number}: {failure}"
            click.echo(message + " (not a verdict)", err=True)


def ownership_observations(
    scopes: tuple[ownership.MutantScope, ...],
) -> tuple[str, ...]:
    """Render failures as diagnostics without issuing a phase verdict."""
    return tuple(
        f"ownership-observation phase {phase.number}: {failure} (not a verdict)"
        for phase in scopes
        for failure in phase.failures
    )


def join_captured_phase_failures(
    phases: tuple[phase_reports.PhaseInputs, ...],
    results: tuple[phase_reports.PhaseResult, ...],
    native: Result[tuple[tuple[int, frozenset[str]], ...], str],
    oracle: Result[tuple[ownership.OracleScope, ...], str],
) -> Result[tuple[phase_reports.PhaseResult, ...], str]:
    """Join captured attribution without asserting run or finalizer authenticity."""
    if isinstance(native, Err):
        return Err("native attribution unavailable: " + native.error)
    if isinstance(oracle, Err):
        return Err("oracle attribution unavailable: " + oracle.error)
    if any(len(set(scope.failures)) != len(scope.failures) for scope in oracle.value):
        return Err("duplicate oracle attribution")
    return phase_reports.join_additional_failures(
        phases,
        results,
        phase_reports.AdditionalFailures(
            native.value,
            tuple((scope.number, frozenset(scope.failures)) for scope in oracle.value),
        ),
    )


def provisional_phase_observations(
    captured: ProvisionalPhaseInputs,
) -> Result[tuple[phase_reports.PhaseResult, ...], str]:
    """Join captured inputs while explicitly refusing to issue closure evidence."""
    work, manifest = captured.work, captured.manifest
    if not captured.nonce or manifest.nonce != captured.nonce:
        return Err("phase observation nonce mismatch")
    if isinstance(captured.collection, Err):
        return Err("collection attribution unavailable: " + captured.collection.error)
    phases = work.work.phases
    numbers = frozenset(phase.number for phase in phases)
    scoped = (
        captured.collection.value,
        work.missing,
        captured.scoped_tools or tuple((phase.number, frozenset()) for phase in phases),
    )
    if any(
        len(dict(values)) != len(values)
        or frozenset(dict(values)) != numbers
        or any("" in failures for _number, failures in values)
        for values in scoped
    ):
        return Err("incomplete or ambiguous phase input attribution")
    base = phase_reports.calculate_scoped_inputs(
        phases,
        work.work.sources,
        manifest.passed,
        captured.shared | frozenset({"unverified-run"}),
    )
    if isinstance(base, Err):
        return base
    collection, missing, scoped_tools = (dict(values) for values in scoped)
    attributed = tuple(
        phase_reports.PhaseResult(
            item.number,
            item.identity,
            item.failures
            | collection[item.number]
            | missing[item.number]
            | scoped_tools[item.number],
        )
        for item in base.value
    )
    return join_captured_phase_failures(
        phases, attributed, captured.native, captured.oracle
    )


def _validate_and_observe(
    context: CheckRun,
    *,
    assume_yes: bool = False,
    original_tree: tuple[writeguard.FileFact, ...] | None = None,
    readiness: tuple[str, ...] = (),
) -> ValidationOutcome:
    """Run independent validators and tools while preserving every failure."""
    found, (root, run_dir, nonce, family) = (
        targets(context.root),
        (
            context.root,
            context.directory,
            context.nonce,
            context.family,
        ),
    )
    if isinstance(found, Err):
        click.echo(found.error, err=True)
        return ValidationOutcome(
            1,
            Err("oracle execution did not start"),
            Err(evidence.EvidenceError("oracle execution did not start")),
            Err("tool execution did not start"),
            Err("tool execution did not start"),
        )
    census = ownership.guarded_census(root, expected=original_tree)
    observed_phases = (
        census_phases(root, census.value)
        if isinstance(census, Ok)
        else Err("source census unavailable")
    )
    report_scoped_source_inputs(census, observed_phases)
    problems = (
        *(("validators: " + census.error,) if isinstance(census, Err) else ()),
        *(
            source_ownership_problems(census.value)
            if not isinstance(census, Err)
            else ()
        ),
        *docs(root),
        *plan(root),
        *(test_consumer_problems(root, census.value) if isinstance(census, Ok) else ()),
        *(coverage_host_problems(root, census.value) if isinstance(census, Ok) else ()),
        *(
            ("validators: phase census: " + observed_phases.error,)
            if isinstance(observed_phases, Err)
            else ()
        ),
        *forbidden_surfaces(root),
        *sources(root),
        *configuration(root),
    )
    records = census_corpus(census.value) if isinstance(census, Ok) else corpus(root)
    oracle_code, oracle_before = (
        oracle_check(root, run_dir, nonce),
        oracle_observation(run_dir, nonce),
    )
    details_before = evidence.read_oracle_details(
        run_dir / "oracle-details.json", nonce
    )
    diagnostic = report_oracle_diagnostics(run_dir, nonce, census, oracle_before)
    details_initial_integrity = oracle_details_unchanged(run_dir, nonce, details_before)
    owners: tuple[tuple[str, int], ...] | None = None
    captured_policy: closure.CapturedPolicy | None = None
    provisional: Result[tuple[tuple[str, int], ...], str] | None = None
    if isinstance(records, Err):
        completed = (records.error.message,)
    else:
        try:
            bound = (
                complete_mutant_owners(census.value, records.value)
                if not isinstance(census, Err)
                else Err("source census unavailable")
            )
            provisional = (
                provisional_mutant_owners(census.value, records.value)
                if isinstance(bound, Err) and isinstance(census, Ok)
                else None
            )
            if isinstance(provisional, Ok):
                bound = provisional
                click.echo("validators: native source identities pending observation")
            owners = bound.value if isinstance(bound, Ok) else None
            policy = (
                census_policy(census.value, owners)
                if isinstance(census, Ok)
                else Err("source census unavailable")
            )
            captured_policy = policy.value if isinstance(policy, Ok) else None
            scoped = (
                scoped_mutant_ownership(census.value, records.value)
                if isinstance(census, Ok) and isinstance(bound, Err)
                else None
            )
            if isinstance(scoped, Ok):
                for message in ownership_observations(scoped.value):
                    click.echo(message, err=True)
            completed = (
                *(
                    ("validators: closure policy: " + policy.error,)
                    if isinstance(policy, Err)
                    else ()
                ),
                *(
                    ("validators: complete mutant ownership: " + bound.error,)
                    if isinstance(bound, Err)
                    else ()
                ),
                *(
                    phase0_claim_problems(root, census.value, records.value)
                    if not isinstance(census, Err)
                    else ()
                ),
                *(
                    fragment_claim_problems(census.value, records.value)
                    if not isinstance(census, Err) and not isinstance(provisional, Ok)
                    else ()
                ),
                *closure.static(
                    root,
                    records.value,
                    mutant_owners=captured_policy,
                    observed_phases=observed_phases.value
                    if isinstance(observed_phases, Ok)
                    else (),
                ),
            )
        except (OSError, UnicodeError) as exc:
            completed = ("validators: cannot read closure inputs: " + str(exc),)
    if problems or completed:
        click.echo("\n".join((*problems, *completed)), err=True)
    else:
        click.echo(
            inapplicable_message(
                closure.inapplicable(
                    root,
                    observed_phases.value if isinstance(observed_phases, Ok) else (),
                    captured=captured_policy,
                )
            ),
            nl=False,
        )
    planned = pipeline(root, run_dir, found.value, family, assume_yes=assume_yes)
    tools = _run_tools_observed(
        root,
        run_dir,
        nonce,
        planned,
        source_entries=census.value if isinstance(census, Ok) else (),
    )
    pytest_integrity, killer_match, killer_integrity = (
        report_pytest_leg(run_dir, tools),
        mutant_killers_match(tools.killers, records, tools.pytest),
        mutant_killers_unchanged(run_dir, nonce, tools.killers),
    )
    if isinstance(records, Err):
        click.echo("post-run-verifier: mutation corpus unavailable", err=True)
        post_code = 1
    else:
        post_code = post_run(
            root,
            run_dir,
            nonce,
            PostRunInputs(
                records.value,
                captured_policy,
                observed_phases.value if isinstance(observed_phases, Ok) else (),
                census.value if isinstance(census, Ok) else (),
                tuple(leg.name for leg in planned),
                pending_native=isinstance(provisional, Ok),
            ),
        )
    oracle_integrity = oracle_outcomes_unchanged(run_dir, nonce, oracle_before)
    details_integrity = oracle_details_unchanged(run_dir, nonce, details_before)
    tools_integrity, substeps_integrity, pytest_manifest_integrity = (
        tool_outcomes_unchanged(run_dir, nonce, tools.evidence),
        tool_substeps_unchanged(run_dir, nonce, tools.substeps),
        pytest_manifest_unchanged(run_dir, nonce, tools.pytest),
    )
    native_integrity, host_integrity = (
        native_snapshot_unchanged(run_dir, nonce, tools.native),
        host_observation_unchanged(run_dir, nonce, tools.host),
    )
    return ValidationOutcome(
        int(
            bool(
                problems
                or completed
                or oracle_code
                or tools.code
                or pytest_integrity
                or killer_match
                or killer_integrity
                or post_code
                or oracle_integrity
                or details_initial_integrity
                or details_integrity
                or tools_integrity
                or substeps_integrity
                or pytest_manifest_integrity
                or native_integrity
                or host_integrity
                or isinstance(diagnostic, Err)
            )
        ),
        oracle_before,
        details_before,
        tools.evidence,
        tools.substeps,
        tools.pytest,
        tools.native,
        tools.host,
        captured_phase_observations(
            ProvisionalCapture(
                census,
                observed_phases,
                tools,
                (records.value, owners)
                if isinstance(records, Ok) and owners is not None
                else None,
                diagnostic,
                nonce,
                tuple(leg.name for leg in planned),
                tuple(
                    (leg.name, 1 + len(leg.after))
                    for leg in planned
                    if isinstance(leg, Leg)
                ),
                readiness,
            )
        ),
        Err("mutant killer observation failed")
        if killer_match or killer_integrity
        else tools.killers,
    )


def validate_and_run(
    root: Path,
    run_dir: Path,
    nonce: str,
    family: Family,
    *,
    assume_yes: bool = False,
) -> int:
    """Expose the validation status without presenting it as a phase verdict."""
    return _validate_and_observe(
        CheckRun(root, run_dir, nonce, family), assume_yes=assume_yes
    ).code


@dataclass(frozen=True, slots=True)
class CollectionClaims:
    """Captured mutant owners together with the corpus that supplies killers."""

    owners: tuple[tuple[str, int], ...] | None
    records: tuple[Mutant, ...]


def collection_observations(
    entries: tuple[evidence.Entry, ...],
    declarations: tuple[Phase, ...],
    observed: evidence.RunEvidence,
    nonce: str,
    claims: tuple[tuple[str, int], ...] | CollectionClaims | None,
) -> Result[tuple[tuple[int, frozenset[str]], ...], str]:
    """Join captured phase citations and the current Python execution record.

    These are diagnostics, not phase verdicts: callers must still authenticate
    all other inputs, tool outcomes, native observations and finalizers.
    """
    text = _census_text(entries, "src/agentctl/check/source_ownership.toml")
    if isinstance(text, Err):
        return text
    manifest = ownership.parse_manifest(text.value)
    if isinstance(manifest, Err):
        return manifest
    scopes = diagnostic_collection_scopes(manifest.value, declarations)
    if isinstance(scopes, Err):
        return scopes
    mutant_owners = claims.owners if isinstance(claims, CollectionClaims) else claims
    if mutant_owners is None:
        return Err("complete mutation ownership unavailable")
    cases = (
        ownership.case_consumers(scopes.value[0], claims.records, mutant_owners)
        if isinstance(claims, CollectionClaims)
        else None
    )
    observation = phase_reports.observe_collection(observed, nonce)
    checked = (
        cases
        if isinstance(cases, Err)
        else phase_reports.collection_failures(
            scopes.value[0],
            observation,
            mutation_owners=mutant_owners,
            case_consumers=cases.value if isinstance(cases, Ok) else None,
        )
    )
    if isinstance(checked, Err):
        return checked
    known = frozenset(artifact.path for artifact in manifest.value.artifacts)
    observed_sources = frozenset(
        entry.path for entry in entries if entry.kind in {"file", "symlink"}
    )
    collected = frozenset(node.split("::", 1)[0] for node in observed.collected)
    unowned = (collected | observation.failed_modules) - (known & observed_sources)
    shared = frozenset("unowned collector: " + path for path in unowned)
    return Ok(
        tuple(
            (
                number,
                failures
                | shared
                | frozenset(
                    issue for owner, issue in scopes.value[1] if owner == number
                ),
            )
            for number, failures in checked.value
        )
    )


def report_collection(
    result: Result[tuple[tuple[int, frozenset[str]], ...], str],
) -> int:
    """Report collection failures without presenting them as phase verdicts."""
    if isinstance(result, Err):
        click.echo("collection-observation: " + result.error, err=True)
        return 1
    for number, failures in result.value:
        for failure in sorted(failures):
            message = f"collection-observation phase {number}: {failure}"
            click.echo(message + " (not a verdict)", err=True)
    return int(any(failures for _number, failures in result.value))


def _native_failure_diagnostics(run_dir: Path, nonce: str) -> None:
    """Expose retained native case failures without claiming a phase verdict."""
    native = haskell.native_observation(run_dir, nonce)
    if isinstance(native, Ok):
        for failure in native.value.forbidden:
            click.echo("native-observation: " + failure + " (not a verdict)", err=True)


def native_failure_observations(
    snapshot: NativeSnapshot,
    nonce: str,
    declarations: tuple[Phase, ...],
    records: tuple[Mutant, ...],
    owners: tuple[tuple[str, int], ...],
) -> Result[tuple[tuple[int, frozenset[str]], ...], str]:
    """Join observed native cases to captured phase and mutant declarations."""
    text = _census_text(snapshot.entries, "src/agentctl/check/source_ownership.toml")
    if isinstance(text, Err):
        return text
    manifest = ownership.parse_manifest(text.value)
    if isinstance(manifest, Err):
        return manifest
    numbers = tuple(phase.number for phase in declarations)
    if frozenset(numbers) != frozenset(phase.number for phase in manifest.value.phases):
        return Err("native phase declarations differ from ownership")
    if len(dict(owners)) != len(owners) or frozenset(dict(owners)) != frozenset(
        record.identifier for record in records
    ):
        return Err("native mutant ownership is incomplete")
    by_owner = dict(owners)
    cited = tuple(
        (phase.number, node)
        for phase in declarations
        for text_value in (
            *(field(sprint.text, "Validation tests") for sprint in phase.sprints),
            *(
                cell
                for row in table(section(phase.text, "Gate Integrity"))
                for cell in row
            ),
        )
        for node in closure.test_ids(text_value)
        if node.startswith("haskell:")
    )
    killers = tuple(
        (by_owner[record.identifier], node)
        for record in records
        for node in record.killers
        if node.startswith("haskell:")
    )
    return phase_reports.native_case_failures(
        snapshot.manifest,
        nonce,
        phase_reports.NativeAttribution(
            numbers,
            snapshot.sources,
            tuple(
                (artifact.path, artifact.consumers)
                for artifact in manifest.value.artifacts
            ),
            (*cited, *killers),
        ),
    )


def provisional_tool_failures(
    captured: ProvisionalCapture,
    manifest: evidence.RunEvidence,
    native: NativeSnapshot,
) -> Result[frozenset[str], str]:
    """Retain shared and not-yet-attributed tool failures in provisional results."""
    tools = captured.tools
    if isinstance(tools.evidence, Err) or isinstance(tools.substeps, Err):
        return Err("captured tool observations unavailable")
    outcomes, substeps = tools.evidence.value, tools.substeps.value
    names = tuple(name for name, _code in outcomes.outcomes)
    if (
        not captured.nonce
        or outcomes.nonce != captured.nonce
        or substeps.nonce != captured.nonce
        or not names
        or len(set(names)) != len(names)
        or names != captured.schedule
        or any(isinstance(code, bool) for _, code in outcomes.outcomes)
        or isinstance(tools.code, bool)
        or tools.code != int(not verdict(captured.schedule, outcomes.outcomes))
    ):
        return Err("captured tool outcome identity or schedule mismatch")
    expected = captured.substep_schedule
    if (
        len({name for name, _limit in expected}) != len(expected)
        or tuple(name for name, _codes in substeps.outcomes)
        != tuple(name for name, _limit in expected)
        or any(
            name not in names or isinstance(limit, bool) or limit < 1
            for name, limit in expected
        )
    ):
        return Err("captured tool substep schedule mismatch")
    statuses = dict(outcomes.outcomes)
    if any(
        not codes
        or len(codes) > limit
        or any(isinstance(code, bool) for code in codes)
        or next((code for code in codes if code != 0), 0) != statuses[name]
        for (name, codes), (_expected_name, limit) in zip(
            substeps.outcomes, expected, strict=True
        )
    ):
        return Err("captured tool substeps disagree with tool outcomes")
    native_status = tuple(
        code for name, code in outcomes.outcomes if name == "cabal-test"
    )
    if len(native_status) != 1 or (native_status[0] != 0) != (
        "native-command-failed" in native.manifest.forbidden
    ):
        return Err("captured native command and observation disagree")
    coverage = phase_reports.pytest_leg_failures(manifest, outcomes, substeps)
    return (
        coverage
        if isinstance(coverage, Err)
        else Ok(
            coverage.value
            | frozenset(
                "unattributed tool failure: " + name
                for name, code in outcomes.outcomes
                if code and name not in {"pytest", "cabal-test"}
            )
        )
    )


def provisional_owned_tool_failures(
    entries: tuple[evidence.Entry, ...],
    phases: tuple[phase_reports.PhaseInputs, ...],
    failures: frozenset[str],
    *,
    readiness: tuple[str, ...] = (),
) -> Result[ToolFailureAttribution, str]:
    """Scope toolchain and readiness failures using captured source ownership."""
    empty = tuple((phase.number, frozenset[str]()) for phase in phases)
    if TOOLCHAIN_FAILURE not in failures and not readiness:
        return Ok(ToolFailureAttribution(failures, empty))
    if any(not message for message in readiness):
        return Err("empty readiness observation")
    text = _census_text(entries, "src/agentctl/check/source_ownership.toml")
    if isinstance(text, Err):
        return text
    parsed = ownership.parse_manifest(text.value)
    if isinstance(parsed, Err):
        return parsed
    declared = tuple((item.number, item.prerequisites) for item in parsed.value.phases)
    expected = tuple((item.number, item.prerequisites) for item in phases)
    required = (
        frozenset({TOOLCHAIN_SOURCE, PREREQUISITE_SOURCE})
        if readiness
        else frozenset({TOOLCHAIN_SOURCE})
    )
    artifacts = tuple(item for item in parsed.value.artifacts if item.path in required)
    sources = tuple(item for item in entries if item.path in required)
    if (
        declared != expected
        or frozenset(item.path for item in artifacts) != required
        or len(artifacts) != len(required)
        or any(item.owner != TOOLCHAIN_OWNER or not item.required for item in artifacts)
        or frozenset(item.path for item in sources) != required
        or len(sources) != len(required)
        or any(item.kind != "file" for item in sources)
    ):
        return Err("toolchain or readiness ownership is unavailable or inconsistent")
    consumers = frozenset(
        number for artifact in artifacts for number in artifact.consumers
    )
    toolchain_consumers = next(
        artifact.consumers
        for artifact in artifacts
        if artifact.path == TOOLCHAIN_SOURCE
    )
    return Ok(
        ToolFailureAttribution(
            failures - {TOOLCHAIN_FAILURE},
            tuple(
                (
                    phase.number,
                    frozenset(
                        (
                            *(
                                ("toolchain-ensure failed",)
                                if TOOLCHAIN_FAILURE in failures
                                and phase.number in toolchain_consumers
                                else ()
                            ),
                            *(
                                "later readiness: " + message
                                for message in readiness
                                if phase.number in consumers
                            ),
                        )
                    ),
                )
                for phase in phases
            ),
        )
    )


def provisional_work_and_tools(
    entries: tuple[evidence.Entry, ...],
    declarations: tuple[Phase, ...],
    failures: frozenset[str],
    readiness: tuple[str, ...],
) -> Result[tuple[ownership.ScopedPhaseWork, ToolFailureAttribution], str]:
    """Bind provisional source inputs and tool ownership to one census."""
    work = scoped_source_inputs(entries, declarations)
    if isinstance(work, Err):
        return work
    attribution = provisional_owned_tool_failures(
        entries, work.value.work.phases, failures, readiness=readiness
    )
    return (
        attribution
        if isinstance(attribution, Err)
        else Ok((work.value, attribution.value))
    )


def collection_with_killer_failures(
    collection: Result[tuple[tuple[int, frozenset[str]], ...], str],
    captured: ProvisionalCapture,
    records: tuple[Mutant, ...],
    owners: tuple[tuple[str, int], ...],
    pytest_run: evidence.RunEvidence,
) -> Result[tuple[tuple[int, frozenset[str]], ...], str]:
    """Add individually observed failures without removing aggregate failures."""
    if isinstance(collection, Err) or not records:
        return collection
    report = captured.tools.killers
    if report is None or isinstance(report, Err):
        return Err("captured mutant killer report unavailable")
    scoped = mutant_report.failure_scopes(
        report.value,
        records,
        pytest_run,
        owners,
        tuple(number for number, _failures in collection.value),
    )
    if isinstance(scoped, Err):
        return scoped
    by_number = dict(scoped.value)
    return Ok(
        tuple(
            (number, failures | by_number[number])
            for number, failures in collection.value
        )
    )


def captured_phase_observations(
    captured: ProvisionalCapture,
) -> Result[tuple[phase_reports.PhaseResult, ...], str]:
    """Join original gate observations without promoting them to a verdict."""
    match captured.census, captured.phases, captured.claims:
        case Ok(entries), Ok(declarations), (records, owners):
            pass
        case _:
            return Err(
                "source census, phase declarations or mutant ownership unavailable"
            )
    pytest_run, native_run = captured.tools.pytest, captured.tools.native
    if (
        pytest_run is None
        or isinstance(pytest_run, Err)
        or native_run is None
        or isinstance(native_run, Err)
    ):
        return Err("captured pytest or native observation unavailable")
    if native_run.value.entries != entries:
        return Err("native observation uses a different source census")
    tool_failures = provisional_tool_failures(
        captured, pytest_run.value, native_run.value
    )
    if isinstance(tool_failures, Err):
        return tool_failures
    scoped = provisional_work_and_tools(
        entries, declarations, tool_failures.value, captured.readiness
    )
    if isinstance(scoped, Err):
        return scoped
    work, attribution = scoped.value
    collection = collection_observations(
        entries,
        declarations,
        pytest_run.value,
        captured.nonce,
        CollectionClaims(owners, records),
    )
    native = native_failure_observations(
        native_run.value, captured.nonce, declarations, records, owners
    )
    return provisional_phase_observations(
        ProvisionalPhaseInputs(
            work,
            pytest_run.value,
            captured.nonce,
            collection_with_killer_failures(
                collection, captured, records, owners, pytest_run.value
            ),
            native,
            captured.oracle,
            attribution.shared,
            attribution.scoped,
        )
    )


def report_provisional_phases(
    observations: Result[tuple[phase_reports.PhaseResult, ...], str] | None,
) -> int:
    """Report provisional summaries and refuse an overall pass while they remain."""
    if isinstance(observations, Err):
        click.echo("phase-observation unavailable: " + observations.error, err=True)
    elif isinstance(observations, Ok):
        for result in observations.value:
            click.echo(
                f"phase-observation {result.number}: {result.identity} "
                f"({len(result.failures)} failures; not a verdict)"
            )
    return int(observations is not None)


def provisional_finalizer_failures(
    observations: Result[tuple[phase_reports.PhaseResult, ...], str] | None,
    statuses: tuple[tuple[str, int], ...],
) -> Result[tuple[phase_reports.PhaseResult, ...], str] | None:
    """Retain shared finalizer damage without turning observations into verdicts."""
    if observations is None or isinstance(observations, Err):
        return observations
    if tuple(name for name, _code in statuses) != FINALIZER_NAMES or any(
        isinstance(code, bool) or code not in {0, 1} for _name, code in statuses
    ):
        return Err("incomplete or ambiguous finalizer observations")
    failures = frozenset(
        "shared finalizer failed: " + name for name, code in statuses if code
    )
    return Ok(
        tuple(
            phase_reports.PhaseResult(
                item.number, item.identity, item.failures | failures
            )
            for item in observations.value
        )
    )


def provisional_phase_record(
    nonce: str,
    observations: Result[tuple[phase_reports.PhaseResult, ...], str] | None,
) -> Result[bytes, str]:
    """Encode complete provisional observations without manufacturing a verdict."""
    if not nonce:
        return Err("invalid provisional phase nonce")
    if observations is None or isinstance(observations, Err):
        reason = "not captured" if observations is None else observations.error
        return (
            Err("empty provisional phase failure")
            if not reason
            else Ok(
                json.dumps(
                    {"nonce": nonce, "status": "unavailable", "reason": reason},
                    sort_keys=True,
                ).encode("utf-8")
            )
        )
    numbers = tuple(item.number for item in observations.value)
    if (
        not numbers
        or numbers != tuple(sorted(set(numbers)))
        or any(isinstance(number, bool) or number < 0 for number in numbers)
        or any(
            len(item.identity) != 2 * hashlib.sha256().digest_size
            or any(character not in "0123456789abcdef" for character in item.identity)
            or "unverified-run" not in item.failures
            or "" in item.failures
            for item in observations.value
        )
    ):
        return Err("invalid provisional phase observations")
    return Ok(
        json.dumps(
            {
                "nonce": nonce,
                "status": "provisional",
                "phases": [
                    {
                        "number": item.number,
                        "identity": item.identity,
                        "failures": sorted(item.failures),
                    }
                    for item in observations.value
                ],
            },
            sort_keys=True,
        ).encode("utf-8")
    )


def record_provisional_phases(
    run_dir: Path,
    nonce: str,
    observations: Result[tuple[phase_reports.PhaseResult, ...], str] | None,
) -> Result[bytes, str]:
    """Create a private, exclusive record of the original provisional values."""
    encoded = provisional_phase_record(nonce, observations)
    if isinstance(encoded, Err):
        return encoded
    path = run_dir / "provisional-phases.json"
    try:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        descriptor = os.open(path, flags, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(encoded.value)
        if path.is_symlink() or path.read_bytes() != encoded.value:
            return Err("provisional phase record changed during recording")
    except (OSError, UnicodeError) as exc:
        return Err("cannot record provisional phases: " + str(exc))
    return encoded


def provisional_phases_unchanged(run_dir: Path, before: Result[bytes, str]) -> int:
    """Require the original provisional bytes immediately before reporting."""
    if isinstance(before, Err):
        click.echo("provisional phases: " + before.error, err=True)
        return 1
    path = run_dir / "provisional-phases.json"
    try:
        unchanged = not path.is_symlink() and path.read_bytes() == before.value
    except (OSError, UnicodeError):
        unchanged = False
    if not unchanged:
        click.echo("provisional phases: missing or changed record", err=True)
        return 1
    return 0


def provisional_seal(nonce: str, record: bytes) -> str:
    """Bind the original diagnostic bytes to the current child run."""
    digest = hashlib.sha256(record).hexdigest()
    return f"{PROVISIONAL_SEAL} {nonce} {digest}"


def parse_provisional_record(nonce: str, contents: bytes) -> Result[None, str]:
    """Require the canonical provisional schema, including its unverified marker."""
    try:
        value: object = json.loads(contents)
    except (ValueError, UnicodeError):
        return Err("invalid provisional record JSON")
    if not isinstance(value, dict) or value.get("nonce") != nonce or not nonce:
        return Err("invalid provisional record identity")
    if value.get("status") == "unavailable" and set(value) == {
        "nonce",
        "status",
        "reason",
    }:
        reason = value["reason"]
        encoded = (
            provisional_phase_record(nonce, Err(reason))
            if isinstance(reason, str)
            else Err("invalid provisional record reason")
        )
    elif value.get("status") == "provisional" and set(value) == {
        "nonce",
        "status",
        "phases",
    }:
        phases = value["phases"]
        if not isinstance(phases, list):
            return Err("invalid provisional record phases")
        parsed = _parse_provisional_phases(phases)
        encoded = (
            parsed
            if isinstance(parsed, Err)
            else provisional_phase_record(nonce, Ok(parsed.value))
        )
    else:
        return Err("invalid provisional record status")
    return (
        Ok(None)
        if isinstance(encoded, Ok) and encoded.value == contents
        else Err("invalid or noncanonical provisional record")
    )


def _parse_provisional_phases(
    values: list[object],
) -> Result[tuple[phase_reports.PhaseResult, ...], str]:
    """Decode complete typed phase values before canonical re-encoding."""
    results: tuple[phase_reports.PhaseResult, ...] = ()
    for value in values:
        if not isinstance(value, dict) or set(value) != {
            "number",
            "identity",
            "failures",
        }:
            return Err("invalid provisional phase fields")
        number, identity, failures = (
            value["number"],
            value["identity"],
            value["failures"],
        )
        if (
            isinstance(number, bool)
            or not isinstance(number, int)
            or not isinstance(identity, str)
            or not isinstance(failures, list)
            or not all(isinstance(failure, str) for failure in failures)
        ):
            return Err("invalid provisional phase types")
        results += (phase_reports.PhaseResult(number, identity, frozenset(failures)),)
    return Ok(results)


def verify_provisional_handoff(
    directory: Path, nonce: str, output: str
) -> Result[None, str]:
    """Check the child's provisional record before and after report retention."""
    lines = output.splitlines()
    markers = tuple(line for line in lines if line.startswith(PROVISIONAL_SEAL + " "))
    if (
        len(markers) != 1
        or len(lines) < PROVISIONAL_HANDOFF_LINES
        or lines[-PROVISIONAL_HANDOFF_LINES] != markers[0]
    ):
        return Err("missing or ambiguous provisional handoff")
    fields = markers[0].split(" ")
    if (
        len(fields) != FINALIZER_SEAL_FIELDS
        or fields[1] != nonce
        or len(fields[2]) != 2 * hashlib.sha256().digest_size
        or any(character not in "0123456789abcdef" for character in fields[2])
    ):
        return Err("invalid provisional handoff identity")
    path = directory / "provisional-phases.json"
    try:
        if path.is_symlink():
            return Err("provisional handoff record is a symlink")
        contents = path.read_bytes()
        if path.is_symlink() or path.read_bytes() != contents:
            return Err("provisional handoff record changed during inspection")
    except OSError as exc:
        return Err("cannot read provisional handoff: " + str(exc))
    return (
        parse_provisional_record(nonce, contents)
        if provisional_seal(nonce, contents) == markers[0]
        else Err("provisional handoff digest mismatch")
    )


def killer_seal(nonce: str, report: mutant_report.Report) -> str:
    """Bind the original per-killer bytes to the child handoff."""
    return f"{KILLER_SEAL} {nonce} {report.digest}"


def verify_killer_handoff(
    directory: Path, nonce: str, output: str
) -> Result[None, str]:
    """Verify the retained report whenever its finalizer claimed success."""
    finalizers = finalizer_observation(directory, nonce)
    if isinstance(finalizers, Err):
        return finalizers
    if dict(finalizers.value.outcomes)["mutant-killers"]:
        return Ok(None)
    lines = output.splitlines()
    markers = tuple(line for line in lines if line.startswith(KILLER_SEAL + " "))
    if (
        len(markers) != 1
        or len(lines) < KILLER_HANDOFF_LINES
        or lines[-KILLER_HANDOFF_LINES] != markers[0]
    ):
        return Err("missing or ambiguous mutant killer handoff")
    report = mutant_report.read(directory / "mutant-killers.json", nonce)
    if isinstance(report, Err):
        return Err("mutant killer handoff record unavailable: " + report.error)
    return (
        Ok(None)
        if killer_seal(nonce, report.value) == markers[0]
        else Err("mutant killer handoff digest mismatch")
    )


def finalizer_observation(
    run_dir: Path, nonce: str
) -> Result[evidence.LegEvidence, str]:
    """Read the exact nonce-bound finalizer record without following links."""
    path = run_dir / "finalizer-outcomes.json"
    if path.is_symlink():
        return Err("finalizer record is a symlink")
    observed = evidence.read_legs(path, nonce, FINALIZER_NAMES[:-1])
    if isinstance(observed, Err):
        return Err(observed.error.message)
    if any(code not in {0, 1} for _name, code in observed.value.outcomes):
        return Err("invalid finalizer status")
    return observed


def record_finalizers(
    run_dir: Path, nonce: str, statuses: tuple[tuple[str, int], ...]
) -> Result[evidence.LegEvidence, str]:
    """Exclusively record and reread the actual finalizer results for this run."""
    if (
        not nonce
        or tuple(name for name, _code in statuses) != FINALIZER_NAMES[:-1]
        or any(isinstance(code, bool) or code not in {0, 1} for _name, code in statuses)
    ):
        return Err("invalid finalizer observations")
    path = run_dir / "finalizer-outcomes.json"
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump({"nonce": nonce, "outcomes": statuses}, stream)
    except (OSError, UnicodeError) as exc:
        return Err("cannot record finalizer outcomes: " + str(exc))
    observed = finalizer_observation(run_dir, nonce)
    expected = evidence.LegEvidence(nonce, statuses)
    return (
        Err("finalizer outcomes changed during recording")
        if isinstance(observed, Err) or observed.value != expected
        else Ok(expected)
    )


def finalizer_outcomes_unchanged(
    run_dir: Path, nonce: str, before: Result[evidence.LegEvidence, str]
) -> int:
    """Require the captured finalizer results to remain intact before reporting."""
    after = finalizer_observation(run_dir, nonce)
    if isinstance(before, Err):
        click.echo("finalizer outcomes: " + before.error, err=True)
        return 1
    if isinstance(after, Ok) and after.value == before.value:
        return 0
    click.echo("finalizer outcomes: missing, stale or changed run record", err=True)
    return 1


def finalizer_seal(observed: evidence.LegEvidence) -> str:
    """Bind the ordered in-memory finalizer statuses to their exact JSON bytes."""
    payload = json.dumps({"nonce": observed.nonce, "outcomes": observed.outcomes})
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"{FINALIZER_SEAL} {observed.nonce} {digest}"


def _parse_finalizer_seal(nonce: str, output: str) -> Result[str, str]:
    """Read exactly one final, nonce-bound digest from the child's output."""
    lines = output.splitlines()
    markers = tuple(line for line in lines if line.startswith(FINALIZER_SEAL + " "))
    if len(markers) != 1 or not lines or lines[-1] != markers[0]:
        return Err("missing or ambiguous finalizer handoff")
    fields = markers[0].split(" ")
    if (
        len(fields) != FINALIZER_SEAL_FIELDS
        or fields[1] != nonce
        or len(fields[2]) != 2 * hashlib.sha256().digest_size
        or any(character not in "0123456789abcdef" for character in fields[2])
    ):
        return Err("invalid finalizer handoff identity")
    return Ok(markers[0])


def verify_finalizer_handoff(
    directory: Path, nonce: str, output: str
) -> Result[None, str]:
    """Compare the child's last seal to a fresh, strictly parsed retained record."""
    marker = _parse_finalizer_seal(nonce, output)
    if isinstance(marker, Err):
        return marker
    observed = finalizer_observation(directory, nonce)
    if isinstance(observed, Err):
        return Err("finalizer handoff record unavailable: " + observed.error)
    try:
        path = directory / "finalizer-outcomes.json"
        if path.is_symlink():
            return Err("finalizer handoff record is a symlink")
        first = path.read_bytes()
        checked = finalizer_observation(directory, nonce)
        if (
            isinstance(checked, Err)
            or checked.value != observed.value
            or path.read_bytes() != first
        ):
            return Err("finalizer handoff record changed during inspection")
    except (OSError, UnicodeError) as exc:
        return Err("cannot read finalizer handoff: " + str(exc))
    digest = marker.value.rsplit(" ", 1)[1]
    return (
        Err("finalizer handoff digest mismatch")
        if hashlib.sha256(first).hexdigest() != digest
        or finalizer_seal(observed.value) != marker.value
        else Ok(None)
    )


def _native_tool_join(
    run_dir: Path, nonce: str, schedule: tuple[str, ...] | None
) -> int:
    """Require the native manifest's command marker to agree with the tool record."""
    if schedule is None:
        return 0
    legs = evidence.read_legs(run_dir / "tool-outcomes.json", nonce, schedule)
    native = haskell.native_observation(run_dir, nonce)
    if isinstance(legs, Err):
        click.echo("native-tool-join: " + legs.error.message, err=True)
        return 1
    if isinstance(native, Err):
        click.echo("native-tool-join: " + native.error.message, err=True)
        return 1
    statuses = tuple(code for name, code in legs.value.outcomes if name == "cabal-test")
    if len(statuses) != 1 or (statuses[0] != 0) != (
        "native-command-failed" in native.value.forbidden
    ):
        click.echo(
            "native-tool-join: native command status differs from manifest", err=True
        )
        return 1
    return 0


def _native_source_join(
    run_dir: Path, nonce: str, entries: tuple[evidence.Entry, ...] | None
) -> int:
    """Join observed native case sources to the captured checkout census."""
    if entries is None:
        return 0
    native = haskell.native_observation(run_dir, nonce)
    if isinstance(native, Err):
        click.echo("native-source-observation: " + native.error.message, err=True)
        return 1
    sources = haskell.read_sources(run_dir, nonce, native.value.collected, entries)
    if isinstance(sources, Err):
        click.echo("native-source-observation: " + sources.error.message, err=True)
        return 1
    return 0


def _native_ownership_observation(
    run_dir: Path,
    nonce: str,
    entries: tuple[evidence.Entry, ...],
    records: tuple[Mutant, ...],
    expected: tuple[tuple[str, int], ...] | None,
) -> int:
    """Compare observed native claims to the owners used by the verifier."""
    native = haskell.native_observation(run_dir, nonce)
    if isinstance(native, Err):
        click.echo("native-ownership-observation: " + native.error.message, err=True)
        return 1
    sources = haskell.read_sources(run_dir, nonce, native.value.collected, entries)
    if isinstance(sources, Err):
        click.echo("native-ownership-observation: " + sources.error.message, err=True)
        return 1
    scoped = scoped_mutant_ownership(entries, records, sources.value)
    if isinstance(scoped, Err):
        click.echo("native-ownership-observation: " + scoped.error, err=True)
        return 1
    for message in ownership_observations(scoped.value):
        click.echo(message, err=True)
    owners = observed_native_mutant_owners(entries, records, sources.value)
    if isinstance(owners, Err):
        click.echo("native-ownership-observation: " + owners.error, err=True)
        return 1
    if expected is None or owners.value != expected:
        click.echo("native-ownership-observation: captured owners differ", err=True)
        return 1
    click.echo("native-ownership-observation: complete (not a verdict)")
    return 0


def _pending_native_evidence(inputs: PostRunInputs) -> int:
    """Require the inputs needed to resolve provisional native ownership."""
    if inputs.pending_native and (
        inputs.source_entries is None or inputs.tool_schedule is None
    ):
        click.echo(
            "post-run-verifier: provisional native ownership lacks evidence", err=True
        )
        return 1
    return 0


def _report_native_attribution(
    run_dir: Path,
    nonce: str,
    inputs: PostRunInputs,
    declarations: tuple[Phase, ...],
    guards: tuple[int, int, int],
) -> int:
    """Report native attribution only after the existing source and owner joins."""
    owner_input = inputs.mutant_owners
    owners = (
        owner_input.owners
        if isinstance(owner_input, closure.CapturedPolicy)
        else owner_input
    )
    if inputs.source_entries is None or owners is None or any(guards):
        return 0
    captured = native_snapshot(run_dir, nonce, inputs.source_entries)
    scoped = (
        native_failure_observations(
            captured.value, nonce, declarations, inputs.records, owners
        )
        if isinstance(captured, Ok)
        else captured
    )
    if isinstance(scoped, Err):
        click.echo("native-attribution: " + scoped.error, err=True)
        return 1
    for number, failures in scoped.value:
        for failure in sorted(failures):
            click.echo(
                f"native-attribution phase {number}: {failure} (not a verdict)",
                err=True,
            )
    return 0


def post_run(
    root: Path,
    run_dir: Path,
    nonce: str,
    inputs: PostRunInputs,
) -> int:
    """Join complete fresh execution to every applicable completion declaration."""
    records, owner_input, observed_phases = (
        inputs.records,
        inputs.mutant_owners,
        inputs.observed_phases,
    )
    mutant_owners = (
        owner_input.owners
        if isinstance(owner_input, closure.CapturedPolicy)
        else owner_input
    )
    native_pending_code = _pending_native_evidence(inputs)
    manifest = evidence.read_manifest(run_dir / "pytest-manifest.json")
    if isinstance(manifest, Err):
        click.echo("post-run-verifier: " + manifest.error.message, err=True)
        native = haskell.native_evidence(run_dir, nonce)
        if isinstance(native, Err):
            click.echo("post-run-verifier: " + native.error.message, err=True)
        return 1
    verified = evidence.verify(
        manifest.value, nonce, tuple(record.identifier for record in records)
    )
    if isinstance(verified, Err):
        click.echo("post-run-verifier: " + verified.error.message, err=True)
    declarations = phases(root) if observed_phases is None else observed_phases
    collection_code = 0
    if inputs.source_entries is not None:
        collection = collection_observations(
            inputs.source_entries,
            declarations,
            manifest.value,
            nonce,
            CollectionClaims(mutant_owners, records),
        )
        collection_code = report_collection(collection)
    native_tool_code = _native_tool_join(run_dir, nonce, inputs.tool_schedule)
    native_source_code = _native_source_join(run_dir, nonce, inputs.source_entries)
    native_owner_code = (
        _native_ownership_observation(
            run_dir, nonce, inputs.source_entries, records, mutant_owners
        )
        if inputs.source_entries is not None
        and inputs.tool_schedule is not None
        and not native_tool_code
        and not native_source_code
        else 0
    )
    attribution_code = _report_native_attribution(
        run_dir,
        nonce,
        inputs,
        declarations,
        (native_tool_code, native_source_code, native_owner_code),
    )
    combined = haskell.combined(run_dir, manifest.value, nonce)
    if isinstance(combined, Err):
        _native_failure_diagnostics(run_dir, nonce)
        click.echo("post-run-verifier: " + combined.error.message, err=True)
        return 1
    if not declarations:
        click.echo("post-run-verifier: empty plan target set", err=True)
        return 1
    problems = (
        *closure.cited_ids(declarations, combined.value),
        *closure.gate_integrity(
            root, declarations, records, combined.value, mutant_owners=owner_input
        ),
    )
    if problems:
        click.echo(
            "post-run-verifier: " + ("\n".join(problems) or "empty plan target set"),
            err=True,
        )
        return 1
    if mutant_owners is None:
        click.echo("post-run-verifier: explicit mutant ownership unavailable", err=True)
    collection_code = int(
        bool(
            collection_code
            or native_tool_code
            or native_source_code
            or native_owner_code
            or attribution_code
            or native_pending_code
        )
    )
    if isinstance(verified, Err) or mutant_owners is None or collection_code:
        return 1
    click.echo("post-run-verifier: pass")
    return 0


def summarize(
    context: CheckRun, code: int, original: Result[lanes.HostFacts, str] | None = None
) -> int:
    """Emit current lane observations and evidence only after integrity finalizers."""
    host = (
        host_observation(context.directory, context.nonce)
        if original is None
        else original
    )
    if code:
        if isinstance(host, Err):
            click.echo("lane-observation: " + host.error, err=True)
        else:
            for state in lanes.evaluate(host.value):
                click.echo(
                    "lane-observation "
                    + state.lane
                    + ": "
                    + ("met" if state.met else "unmet")
                    + " (not a verdict)"
                )
        return code
    if isinstance(host, Err):
        click.echo("lane-summary: " + host.error, err=True)
        return 1
    states = lanes.evaluate(host.value)
    problems = closure.lanes(phases(context.root), states)
    if problems:
        click.echo("\n".join(problems), err=True)
        return 1
    tree = evidence.digest(context.root)
    if isinstance(tree, Err):
        click.echo("lane-summary: " + tree.error.message, err=True)
        return 1
    baseline = ratchet.head(context.root)
    if isinstance(baseline, Err):
        click.echo("lane-summary: " + baseline.error.message, err=True)
        return 1
    detail = (
        "os="
        + host.value.family
        + ",arch="
        + lanes.architecture(host.value.family, host.value.architecture)
        + ",baseline="
        + (baseline.value or "no baseline")
    )
    for state in states:
        click.echo("lane " + state.lane + ": " + ("met" if state.met else "unmet"))
    for line in lanes.evidence_lines(
        code, states, datetime.now(UTC).date().isoformat(), tree.value, detail
    ):
        click.echo(line)
    return 0


def verify_baseline(root: Path, code: int) -> int:
    """Run the read-only ratchet while preserving any earlier failure."""
    baseline = ratchet.check(root)
    if isinstance(baseline, Err):
        click.echo("ratchet: " + baseline.error.message, err=True)
        return code or 1
    click.echo("ratchet: pass; " + baseline.value)
    return code


def finalize_observed(
    context: CheckRun,
    before: writeguard.Snapshot,
    code: int,
) -> Finalization:
    """Observe containment and checkout integrity as independent outcomes."""
    contained = writeguard.containment(context.directory, context.nonce, context.family)
    containment_code = code
    if isinstance(contained, Err):
        click.echo("containment: " + contained.error.message, err=True)
        containment_code = 1
    after = writeguard.snapshot(context.root)
    guard_code = code
    if isinstance(after, Err):
        click.echo("write-guard-compare: " + after.error.message, err=True)
        guard_code = 1
    elif changed := writeguard.compare(before, after.value):
        click.echo("write-guard-compare: changed " + ", ".join(changed), err=True)
        guard_code = 1
    else:
        click.echo("write-guard-compare: pass")
    return Finalization(containment_code, guard_code)


def finalize(
    context: CheckRun,
    before: writeguard.Snapshot,
    code: int,
) -> int:
    """Preserve the primary status while applying both finalizer observations."""
    result = finalize_observed(context, before, code)
    return result.containment or result.write_guard


def inspect_context(root: Path, run_dir: Path, family: Family) -> tuple[str, ...]:
    """Check the shared identity and containment prerequisites before snapshot."""
    return (*inspect(root), *inspect_socket(run_dir, family))


def inspect_later_readiness(
    run_dir: Path, family: Family, *, assume_yes: bool
) -> tuple[str, ...]:
    """Observe bootstrap prerequisites without blocking independent validation."""
    paths = directories(family, os.environ, Path.home())
    context = hostfacts.current(paths.cache, assume_yes=assume_yes)
    return (
        *inspect_prerequisites(
            replace(context, cache=run_dir / "prerequisite-probe", interactive=False)
        ),
        *inspect_toolchain(context, load_pins()),
    )


def readiness_result(validation: int, readiness: tuple[str, ...]) -> int:
    """Keep later readiness failures visible without replacing validation errors."""
    return validation or int(bool(readiness))


def emit_handoff_seals(
    nonce: str,
    recorded: Result[evidence.LegEvidence, str],
    phase_record: Result[bytes, str],
    killers: Result[mutant_report.Report, str] | None,
    codes: tuple[int, int, int],
) -> None:
    """Emit original observations only after their records remain intact."""
    record_code, phase_record_code, killer_code = codes
    if isinstance(recorded, Ok) and not record_code:
        if isinstance(phase_record, Ok) and not phase_record_code:
            if isinstance(killers, Ok) and not killer_code:
                click.echo(killer_seal(nonce, killers.value))
            click.echo(provisional_seal(nonce, phase_record.value))
        click.echo(finalizer_seal(recorded.value))


def execute(
    root: Path, run_dir: Path, nonce: str, family: Family, *, assume_yes: bool = False
) -> int:
    """Keep integrity finalizers active after every post-snapshot exit path."""
    problems = inspect_context(root, run_dir, family)
    if problems:
        click.echo("\n".join(problems), err=True)
        return 1
    before = writeguard.snapshot(root)
    if isinstance(before, Err):
        click.echo(before.error.message, err=True)
        return 1
    click.echo("write-guard-snapshot: pass")
    code = 1
    try:
        readiness = inspect_later_readiness(run_dir, family, assume_yes=assume_yes)
        if readiness:
            click.echo("\n".join(readiness), err=True)
        validation = _validate_and_observe(
            CheckRun(root, run_dir, nonce, family),
            assume_yes=assume_yes,
            original_tree=before.value.tree,
            readiness=readiness,
        )
        code = readiness_result(validation.code, readiness)
        ratchet_code = verify_baseline(root, 0)
        code = code or ratchet_code
    finally:
        finalization = finalize_observed(
            CheckRun(root, run_dir, nonce, family), before.value, 0
        )
        code = code or finalization.containment or finalization.write_guard
    oracle_after_finalizers = oracle_outcomes_unchanged(
        run_dir, nonce, validation.oracle
    )
    code = code or oracle_after_finalizers
    details_after_finalizers = oracle_details_unchanged(
        run_dir, nonce, validation.oracle_details
    )
    code = code or details_after_finalizers
    tools_after_finalizers = tool_outcomes_unchanged(run_dir, nonce, validation.tools)
    code = code or tools_after_finalizers
    substeps_after_finalizers = tool_substeps_unchanged(
        run_dir, nonce, validation.substeps
    )
    code = code or substeps_after_finalizers
    pytest_after_finalizers, killers_after_finalizers, native_after_finalizers = (
        pytest_manifest_unchanged(run_dir, nonce, validation.pytest),
        mutant_killers_unchanged(run_dir, nonce, validation.killers),
        native_snapshot_unchanged(run_dir, nonce, validation.native),
    )
    code = code or pytest_after_finalizers
    code = code or killers_after_finalizers
    code = code or native_after_finalizers
    host_after_finalizers = host_observation_unchanged(run_dir, nonce, validation.host)
    code = code or host_after_finalizers
    finalizer_statuses = (
        ("ratchet", ratchet_code),
        ("containment", finalization.containment),
        ("write-guard", finalization.write_guard),
        ("oracle-outcomes", oracle_after_finalizers),
        ("oracle-details", details_after_finalizers),
        ("tool-outcomes", tools_after_finalizers),
        ("tool-substeps", substeps_after_finalizers),
        ("pytest-manifest", pytest_after_finalizers),
        ("mutant-killers", killers_after_finalizers),
        ("native-observation", native_after_finalizers),
        ("host-observation", host_after_finalizers),
    )
    recorded = record_finalizers(run_dir, nonce, finalizer_statuses)
    record_code = finalizer_outcomes_unchanged(run_dir, nonce, recorded)
    code = code or record_code
    observations = provisional_finalizer_failures(
        validation.phase_observations,
        (*finalizer_statuses, ("finalizer-record", record_code)),
    )
    phase_record = record_provisional_phases(run_dir, nonce, observations)
    phase_record_code = provisional_phases_unchanged(run_dir, phase_record)
    code = code or phase_record_code
    provisional_code = report_provisional_phases(observations)
    code = code or provisional_code
    status = summarize(CheckRun(root, run_dir, nonce, family), code, validation.host)
    emit_handoff_seals(
        nonce,
        recorded,
        phase_record,
        validation.killers,
        (record_code, phase_record_code, killers_after_finalizers),
    )
    return status


def emit_gate_output(stdout: str, stderr: str) -> None:
    """Relay UTF-8 bytes even when the parent console uses a legacy code page."""
    click.echo(stdout.encode("utf-8"), nl=False)
    click.echo(stderr.encode("utf-8"), nl=False, err=True)


def retain_gate_output(
    root: Path, state: Path, run_dir: Path, nonce: str, streams: tuple[str, str]
) -> Result[Path, str]:
    """Retain output and available run artifacts outside the source and temp tree."""
    if not nonce or any(character not in "0123456789abcdef" for character in nonce):
        return Err("invalid report nonce")
    reports = state / "check-reports"
    try:
        state_root = state.resolve()
        report_root = reports.resolve()
        if (
            report_root.is_relative_to(root.resolve())
            or report_root.is_relative_to(run_dir.resolve())
            or not report_root.is_relative_to(state_root)
            or not run_dir.is_dir()
        ):
            return Err("report directory escapes state or enters checkout")
        artifacts: tuple[tuple[str, bytes], ...] = (
            ("stdout.txt", streams[0].encode("utf-8")),
            ("stderr.txt", streams[1].encode("utf-8")),
        )
        reports.mkdir(mode=0o700, parents=True, exist_ok=True)
        destination = reports / nonce
        destination.mkdir(mode=0o700)
        for name, contents in artifacts:
            descriptor = os.open(
                destination / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
            )
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(contents)
        for name in (
            "host.json",
            "bootstrap-host.json",
            "oracle-outcomes.json",
            "oracle-details.json",
            "pytest-manifest.json",
            "mutant-killers.json",
            "haskell-manifest.json",
            "haskell-sources.json",
            "tool-outcomes.json",
            "tool-substeps.json",
            "finalizer-outcomes.json",
            "provisional-phases.json",
            "tasty.xml",
            "coverage",
        ):
            source = run_dir / name
            if source.is_symlink():
                return Err(
                    "run artifact is a symlink: "
                    + name
                    + "; report: "
                    + str(destination)
                )
            if source.exists():
                if not source.is_file():
                    return Err(
                        "run artifact is not a file: "
                        + name
                        + "; report: "
                        + str(destination)
                    )
                contents = source.read_bytes()
                descriptor = os.open(
                    destination / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
                )
                with os.fdopen(descriptor, "wb") as stream:
                    stream.write(contents)
        return Ok(destination)
    except (OSError, UnicodeError) as exc:
        return Err("cannot retain gate report: " + str(exc))


def cleanup_run_root(context: CheckRun, temporary_root: Path) -> Result[None, str]:
    """Retain a run when its boundary or registered containment is uncertain."""
    try:
        target = context.directory.resolve(strict=True)
        allowed = temporary_root.resolve(strict=True)
        if (
            context.directory.is_symlink()
            or target.parent != allowed
            or not target.name.startswith("agentctl-check-")
            or target.is_relative_to(context.root.resolve())
        ):
            return Err("temporary run boundary is invalid")
        contained = writeguard.containment(target, context.nonce, context.family)
        if isinstance(contained, Err):
            return Err("temporary run retained: " + contained.error.message)
        shutil.rmtree(writeguard.filesystem_path(target))
        return Ok(None)
    except (OSError, UnicodeError, RuntimeError) as exc:
        return Err("temporary cleanup failure: " + _failure_text(exc))


def _failure_text(exc: BaseException) -> str:
    """Keep an exception's own message when a library adds only a filename.

    Linux fd-based tree removal assigns ``filename`` to an arbitrary OSError,
    whose default rendering then shows only ``[Errno None] None`` and the path.
    """
    if isinstance(exc, OSError) and exc.errno is None and exc.filename is not None:
        return ": ".join((*(str(item) for item in exc.args), repr(exc.filename)))
    return str(exc)


def retain_cleanup_failure(
    root: Path, state: Path, nonce: str, message: str
) -> Result[None, str]:
    """Retain cleanup evidence in the existing report without following links."""
    report = state / "check-reports" / nonce
    try:
        target = report.resolve(strict=True)
        if (
            not nonce
            or any(character not in "0123456789abcdef" for character in nonce)
            or report.is_symlink()
            or not target.is_relative_to(state.resolve())
            or target.is_relative_to(root.resolve())
            or not target.is_dir()
        ):
            return Err("cleanup report boundary is invalid")
        descriptor = os.open(
            target / "cleanup.txt", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
        )
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as stream:
            stream.write(message + "\n")
        return Ok(None)
    except (OSError, UnicodeError, RuntimeError) as exc:
        return Err("cannot retain cleanup failure: " + str(exc))


def retain_handoff_failure(
    root: Path, state: Path, report: Path, message: str
) -> Result[None, str]:
    """Keep a post-copy handoff failure in the already-owned external report."""
    try:
        target = report.resolve(strict=True)
        if (
            report.is_symlink()
            or not target.is_dir()
            or not target.is_relative_to((state / "check-reports").resolve())
            or target.is_relative_to(root.resolve())
        ):
            return Err("finalizer handoff report boundary is invalid")
        descriptor = os.open(
            target / "finalizer-handoff.txt",
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as stream:
            stream.write(message + "\n")
        return Ok(None)
    except (OSError, UnicodeError, RuntimeError) as exc:
        return Err("cannot retain finalizer handoff failure: " + str(exc))


def retain_verified_gate_output(
    context: CheckRun,
    state: Path,
    streams: tuple[str, str],
    *,
    verify_handoff: bool,
) -> Result[Path, str]:
    """Retain a report and verify its finalizer record against the child seal."""
    retained = retain_gate_output(
        context.root, state, context.directory, context.nonce, streams
    )
    if isinstance(retained, Err) or not verify_handoff:
        return retained
    checked = verify_finalizer_handoff(retained.value, context.nonce, streams[0])
    if isinstance(checked, Ok):
        checked = verify_provisional_handoff(retained.value, context.nonce, streams[0])
    if isinstance(checked, Ok):
        checked = verify_killer_handoff(retained.value, context.nonce, streams[0])
    if isinstance(checked, Err):
        message = "finalizer handoff: " + checked.error
        saved = retain_handoff_failure(context.root, state, retained.value, message)
        return Err(message + ("; " + saved.error if isinstance(saved, Err) else ""))
    return retained


def _run_check_child(context: CheckRun, state: Path, *, assume_yes: bool) -> int:
    """Run and retain one check before attempting temporary-root cleanup."""
    (context.directory / "ty-config").mkdir()
    invocation = (
        "from pathlib import Path; "
        "from agentctl.check.steps import execute; import sys; "
        "sys.exit(execute(Path(sys.argv[1]), "
        "Path(sys.argv[2]), sys.argv[3], sys.argv[4], "
        "assume_yes=sys.argv[5] == 'yes'))"
    )
    result = run(
        [
            sys.executable,
            "-c",
            invocation,
            str(context.root),
            str(context.directory),
            context.nonce,
            context.family,
            "yes" if assume_yes else "no",
        ],
        cwd=context.root,
        env=environment(os.environ, context.directory, context.nonce),
        timeout=CHECK_TIMEOUT_SECONDS,
    )
    handoff: Result[None, str] = Err("child unavailable")
    if isinstance(result, Err):
        streams, code = ("", result.error.message + "\n"), 1
    else:
        streams, code = (result.value.stdout, result.value.stderr), result.value.code
        handoff = verify_finalizer_handoff(context.directory, context.nonce, streams[0])
        if isinstance(handoff, Ok):
            handoff = verify_provisional_handoff(
                context.directory, context.nonce, streams[0]
            )
        if isinstance(handoff, Ok):
            handoff = verify_killer_handoff(
                context.directory, context.nonce, streams[0]
            )
        if isinstance(handoff, Err):
            streams = (
                streams[0],
                streams[1] + "finalizer handoff: " + handoff.error + "\n",
            )
            code = 1
    retained = retain_verified_gate_output(
        context,
        state,
        streams,
        verify_handoff=isinstance(result, Ok) and isinstance(handoff, Ok),
    )
    emit_gate_output(*streams)
    if isinstance(retained, Err):
        click.echo(retained.error, err=True)
        return 1
    click.echo("check report: " + str(retained.value))
    return code


def check(family: str, *, assume_yes: bool = False) -> int:
    """Re-enter with bytecode outside the tree and one user's lock held."""
    root = Path.cwd().resolve()
    if family not in {"Linux", "Darwin", "Windows"}:
        click.echo(f"Unsupported OS: {family}", err=True)
        return 1
    paths = directories(family, os.environ, Path.home())
    with single_run(paths.state) as problems:
        if problems:
            click.echo("\n".join(problems), err=True)
            return 1
        try:
            temporary_root = Path(tempfile.gettempdir()).resolve(strict=True)
            if temporary_root.is_relative_to(root):
                click.echo(
                    "Set TMPDIR outside the checkout before running check.", err=True
                )
                return 1
            run_dir = Path(
                tempfile.mkdtemp(prefix="agentctl-check-", dir=temporary_root)
            )
            context = CheckRun(root, run_dir, secrets.token_hex(16), family)
            code = _run_check_child(context, paths.state, assume_yes=assume_yes)
            cleaned = cleanup_run_root(context, temporary_root)
            if isinstance(cleaned, Err):
                saved = retain_cleanup_failure(
                    root, paths.state, context.nonce, cleaned.error
                )
                click.echo(
                    "check: " + cleaned.error + "; retained at " + str(run_dir),
                    err=True,
                )
                if isinstance(saved, Err):
                    click.echo(saved.error, err=True)
                return 1
        except OSError as exc:
            click.echo("check: temporary storage failure: " + str(exc), err=True)
            return 1
        return code
