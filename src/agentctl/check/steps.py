# Copyright (c) 2026 agentctl contributors.
"""Isolated orchestration for every introduced check step."""

import hashlib
import json
import os
import re
import secrets
import shutil
import stat
import sys
import tempfile
from collections.abc import Mapping
from dataclasses import asdict, dataclass, replace
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
    virtualbox_binding,
    writeguard,
)
from agentctl.check.legs import Leg, coverage_commands, python_legs, targets, verdict
from agentctl.check.mutants import Mutant, MutationError, census_corpus, corpus
from agentctl.check.plan_data import Phase, field, phase_text, phases, section, table
from agentctl.check.preconditions import inspect, inspect_socket, single_run
from agentctl.check.prerequisites import inspect_prerequisites
from agentctl.check.toolchain import EnsureStep, inspect_toolchain, run_step
from agentctl.check.validator import closure
from agentctl.check.validator.docs import validate as docs
from agentctl.check.validator.plan import validate as plan
from agentctl.check.validator.source import (
    SourceIssue,
    census_source_observations,
    configuration,
    forbidden_surfaces,
    source_observations,
)
from agentctl.foundation import Err, Family, Ok, Result
from agentctl.foundation_paths import directories
from agentctl.foundation_process import ObservationRequest, run, run_observed
from agentctl.foundation_process_values import Output, ProcessObservation, SpawnError

PYTHON_LEG_TIMEOUT_SECONDS = 4 * 60 * 60
CHECK_TIMEOUT_SECONDS = 8 * PYTHON_LEG_TIMEOUT_SECONDS
COVERAGE_NONCE_LENGTH = 32
COVERAGE_REPORT_FAILURE = 2
COVERAGE_REPORT_INDEX = 2
ORACLE_LEGS = ("oracle-validation", "bootstrap-provenance")
FINALIZER_NAMES = (
    "ratchet",
    "containment",
    "write-guard",
    "oracle-outcomes",
    "oracle-details",
    "initial-oracle-details",
    "validation-integrity",
    "tool-outcomes",
    "python-commands",
    "tool-substeps",
    "pytest-manifest",
    "mutant-killers",
    "native-observation",
    "host-observation",
    "ruff-format-observation",
    "ruff-observation",
    "ty-observation",
    "coverage-text-observation",
    "coverage-observation",
    "finalizer-record",
)
FINALIZER_SEAL = "agentctl-finalizer-v1"
FINALIZER_SEAL_FIELDS = 3
READINESS_OBSERVATION = "agentctl-readiness-v1"
PROVISIONAL_SEAL = "agentctl-provisional-v1"
PROVISIONAL_HANDOFF_LINES = 2
KILLER_SEAL = "agentctl-mutant-killers-v1"
KILLER_HANDOFF_LINES = 3
COVERAGE_SEAL = "agentctl-coverage-v1"
RUFF_SEAL = "agentctl-ruff-v1"
RUFF_FORMAT_SEAL = "agentctl-ruff-format-v1"
PYTHON_COMMANDS_SEAL = "agentctl-python-commands-v1"
TOOL_RESULTS_SEAL = "agentctl-tool-results-v1"
PYTEST_OBSERVATION_SEAL = "agentctl-pytest-observation-v1"
ORACLE_RESULTS_SEAL = "agentctl-oracle-results-v1"
HOST_OBSERVATION_SEAL = "agentctl-host-observation-v1"
NATIVE_OBSERVATION_SEAL = "agentctl-native-observation-v1"
NATIVE_ABSENCE_OBSERVATION = "agentctl-native-absence-v1"
NATIVE_REPORT_FILES = (
    "haskell-manifest.json",
    "haskell-sources.json",
    "tasty.xml",
    "native-artifacts.json",
)
TY_OBSERVATION_SEAL = "agentctl-ty-observation-v1"
COVERAGE_TEXT_SEAL = "agentctl-coverage-text-v1"
PYTHON_COMMAND_NAMES = ("ruff-check", "ruff-format", "ty", "pytest")
SHA256_HEX_LENGTH = 64
TOOLCHAIN_OWNER = 2
TOOLCHAIN_SOURCE = "src/agentctl/check/toolchain.py"
PREREQUISITE_SOURCE = "src/agentctl/check/prerequisites.py"
IDENTITY_FAILURE = "unattributed tool failure: binary-identity"
IDENTITY_OWNER = 2
IDENTITY_SOURCES = frozenset(
    {"src/agentctl/check/identity.py", "src/agentctl/bootstrap/binary.py"}
)
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
    directory_identity: tuple[int, int] | None = None


@dataclass(frozen=True, slots=True)
class RetainedReportSnapshot:
    """Retained file identities and bytes captured before temporary cleanup."""

    streams: tuple[tuple[int, int, bytes], ...]
    artifacts: tuple[tuple[str, int, int, str], ...]


@dataclass(frozen=True, slots=True)
class RetainedGateReport:
    """Retained diagnostics and the snapshot verified with their handoffs."""

    directory: Path
    snapshot: RetainedReportSnapshot | None
    receipt_inputs: Result["ReceiptInputs", str] | None = None


@dataclass(frozen=True, slots=True)
class GateInterpreterIdentity:
    """Stable observed identity and bytes of the selected gate interpreter."""

    path: Path
    device: int
    inode: int
    size: int
    modified_ns: int
    changed_ns: int
    sha256: str


@dataclass(frozen=True, slots=True)
class CheckChildResult:
    """Retained child diagnostics awaiting parent cleanup and publication."""

    code: int
    streams: tuple[str, str]
    retained: Result[Path, str]
    trusted: bool
    snapshot: RetainedReportSnapshot | None = None
    interpreter: GateInterpreterIdentity | None = None
    receipt_inputs: Result["ReceiptInputs", str] | None = None
    receipt_candidates: Result[tuple["PhaseReceiptEvidence", ...], str] | None = None


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
    artifacts: tuple[tuple[str, str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class CoverageSnapshot:
    """One original nonce-bound JSON report and its decoded observations."""

    nonce: str
    facts: tuple[coverage_hosts.CoverageFact, ...]
    record: bytes
    record_identity: tuple[int, int]
    report: bytes
    report_identity: tuple[int, int]
    entries: tuple[evidence.Entry, ...] = ()


@dataclass(frozen=True, slots=True)
class ReceiptInputs:
    """Run values independently reconstructed from a retained gate report.

    These values remain provisional; retaining them does not issue a receipt.
    """

    nonce: str
    source_digest: str
    phases: tuple[phase_reports.PhaseInputs, ...]
    observations: tuple[phase_reports.PhaseResult, ...]
    host: lanes.HostFacts
    python: evidence.RunEvidence
    native: NativeSnapshot | None
    killers: mutant_report.Report
    mutant_owners: tuple[tuple[str, int], ...]
    coverage: tuple[coverage_hosts.CoverageFact, ...]
    coverage_owners: tuple[coverage_hosts.CoverageOwner, ...]
    foreign_coverage: frozenset[str] = frozenset()
    native_citations: tuple[tuple[int, str], ...] = ()
    native_absence: tuple[tuple[int, frozenset[str]], ...] = ()
    entries: tuple[evidence.Entry, ...] = ()


@dataclass(frozen=True, slots=True)
class PhaseReceiptEvidence:
    """One phase's actual required and observed evidence, before authentication."""

    number: int
    identity: str
    prerequisites: tuple[tuple[int, str], ...]
    required_tests: frozenset[str]
    passed_tests: frozenset[str]
    required_mutants: frozenset[str]
    killed_mutants: frozenset[str]
    required_coverage: frozenset[str]
    covered: frozenset[str]
    failures: frozenset[str]


@dataclass(frozen=True, slots=True)
class ReceiptNativeInputs:
    """Retained observations needed to qualify an absent native leg."""

    context: CheckRun
    directory: Path
    output: str
    finalizers: evidence.LegEvidence
    observations: tuple[phase_reports.PhaseResult, ...]
    declarations: tuple[Phase, ...]
    collection: "ProvisionalCapture"


@dataclass(frozen=True, slots=True)
class CoverageTextSnapshot:
    """Original coverage report command, outcome and retained record identity."""

    nonce: str
    root: Path
    command: tuple[str, ...]
    output: Output
    record: bytes = b""
    record_identity: tuple[int, int] = (0, 0)


@dataclass(frozen=True, slots=True)
class CoverageTextInputs:
    """Original source, schedule and report observations for one run."""

    context: CheckRun
    entries: tuple[evidence.Entry, ...]
    leg: Leg
    substeps: Result[evidence.ToolSubsteps, str]
    text: Result[CoverageTextSnapshot, str] | None
    coverage: Result[CoverageSnapshot, str]


@dataclass(frozen=True, slots=True)
class CoverageRequest:
    """The pinned JSON command and the already-observed report status."""

    version: str
    command: tuple[str, ...]
    report_status: int
    entries: tuple[evidence.Entry, ...] = ()


@dataclass(frozen=True, slots=True)
class CoverageRendered:
    """The parsed raw report and the identity reserved before its generation."""

    facts: tuple[coverage_hosts.CoverageFact, ...]
    raw: bytes
    identity: tuple[int, int]


@dataclass(frozen=True, slots=True)
class RuffFact:
    """One structured Ruff diagnostic tied to a checkout-relative path."""

    path: str
    code: str
    row: int
    message: str


@dataclass(frozen=True, slots=True)
class RuffSnapshot:
    """The Ruff subprocess result and decoded facts captured for this run."""

    nonce: str
    root: Path
    output: Output
    facts: tuple[RuffFact, ...]
    record: bytes = b""
    record_identity: tuple[int, int] = (0, 0)


@dataclass(frozen=True, slots=True)
class TySnapshot:
    """The type checker's original subprocess result and decoded diagnostics."""

    nonce: str
    root: Path
    output: Output
    facts: tuple[RuffFact, ...]
    record: bytes = b""
    record_identity: tuple[int, int] = (0, 0)


@dataclass(frozen=True, slots=True)
class PythonCommandsSnapshot:
    """The original run-owned Python command record and its file identity."""

    nonce: str
    root: Path
    commands: tuple[tuple[str, tuple[tuple[str, ...], ...]], ...]
    record: bytes
    record_identity: tuple[int, int]


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
    coverage: Result[CoverageSnapshot, str] | None = None
    ruff: Result[RuffSnapshot, str] | None = None
    python_commands: Result[PythonCommandsSnapshot, str] | None = None
    ruff_format: Result[RuffSnapshot, str] | None = None
    ty: Result[TySnapshot, str] | None = None
    coverage_text: Result[CoverageTextSnapshot, str] | None = None
    validation_integrity: int = 1
    native_absence: str | None = None
    initial_oracle_details: int = 1


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
    ruff: Result[RuffSnapshot, str] | None = None
    commands: tuple[tuple[str, tuple[tuple[str, ...], ...]], ...] = ()
    ruff_format: Result[RuffSnapshot, str] | None = None
    ty: Result[TySnapshot, str] | None = None
    coverage_text: Result[CoverageTextSnapshot, str] | None = None
    native_absence: str | None = None


@dataclass(frozen=True, slots=True)
class LegOutcome:
    """A leg's aggregate status and each subprocess actually attempted."""

    code: int
    substeps: tuple[int, ...]
    pytest: Result[evidence.RunEvidence, str] | None = None
    host: Result[lanes.HostFacts, str] | None = None
    killers: Result[mutant_report.Report, str] | None = None
    ruff: Result[RuffSnapshot, str] | None = None
    commands: tuple[tuple[str, ...], ...] = ()
    ruff_format: Result[RuffSnapshot, str] | None = None
    ty: Result[TySnapshot, str] | None = None
    coverage_text: Result[CoverageTextSnapshot, str] | None = None


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
class CoverageAttributionInputs:
    """Captured source, host and report values for a diagnostic coverage join."""

    entries: tuple[evidence.Entry, ...]
    phases: tuple[phase_reports.PhaseInputs, ...]
    nonce: str
    family: Family
    host: Result[lanes.HostFacts, str] | None
    coverage: Result[CoverageSnapshot, str] | None
    substeps: Result[evidence.ToolSubsteps, str]
    outcomes: Result[evidence.LegEvidence, str] | None = None


@dataclass(frozen=True, slots=True)
class ParentStaticInputs:
    """Current census and sealed tool statuses for static diagnostic rechecks."""

    context: CheckRun
    directory: Path
    entries: tuple[evidence.Entry, ...]
    phases: tuple[phase_reports.PhaseInputs, ...]
    outcomes: evidence.LegEvidence
    substeps: evidence.ToolSubsteps


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
    after_failure: frozenset[str] = frozenset()
    coverage: Result[CoverageSnapshot, str] | None = None
    family: Family | None = None
    validation: tuple[str, ...] = ()
    source_issues: tuple[SourceIssue, ...] = ()
    coverage_context: CheckRun | None = None
    coverage_leg: Leg | None = None
    scoped_mutants: bool = False


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


def _ruff_fields(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """Reject duplicate JSON fields in a Ruff subprocess result."""
    fields = dict(pairs)
    if len(fields) != len(pairs):
        message = "duplicate Ruff diagnostic field"
        raise ValueError(message)
    return fields


def _ruff_fact(root: Path, value: object) -> Result[RuffFact, str]:
    """Decode one diagnostic without accepting a path outside the checkout."""
    match value:
        case {
            "filename": str() as filename,
            "code": str() as code,
            "message": str() as message,
            "location": {"row": int() as row, **_location},
            **_extra,
        } if code and message and not isinstance(row, bool) and row > 0:
            pass
        case _:
            return Err("invalid Ruff diagnostic")
    path = Path(filename)
    if not path.is_absolute() or ".." in path.parts:
        return Err("invalid Ruff diagnostic path")
    try:
        relative = path.relative_to(root).as_posix()
    except ValueError:
        return Err("Ruff diagnostic is outside checkout")
    if not relative.startswith(("src/", "tests/")) or not relative.endswith(".py"):
        return Err("Ruff diagnostic is outside Python targets")
    return Ok(RuffFact(relative, code, row, message))


def parse_ruff_output(root: Path, output: Output) -> Result[tuple[RuffFact, ...], str]:
    """Decode a complete Ruff JSON result and require status and findings to agree."""
    if (
        not root.is_absolute()
        or isinstance(output.code, bool)
        or output.code not in {0, 1}
        or output.stderr
    ):
        return Err("Ruff diagnostic status or context is unavailable")
    try:
        rows: object = json.loads(output.stdout, object_pairs_hook=_ruff_fields)
    except (ValueError, RecursionError):
        return Err("invalid Ruff JSON")
    if not isinstance(rows, list):
        return Err("invalid Ruff JSON rows")
    observed = tuple(_ruff_fact(root, row) for row in rows)
    facts = tuple(item.value for item in observed if isinstance(item, Ok))
    if len(facts) != len(rows) or (output.code == 0) != (not facts):
        return Err("Ruff diagnostics disagree with the subprocess status")
    return Ok(facts)


def _ty_fact(root: Path, value: object) -> Result[RuffFact, str]:
    """Decode one GitLab-format type diagnostic into a checked source location."""
    match value:
        case {
            "check_name": str() as code,
            "description": str() as message,
            "severity": str() as severity,
            "location": {"path": str() as path, "positions": {"begin": {"line": line}}},
        } if severity in {"blocker", "critical", "major", "minor", "info"}:
            subject = Path(path)
            if not subject.is_absolute():
                if not path or ".." in subject.parts:
                    return Err("invalid ty diagnostic path")
                subject = root / subject
            return _ruff_fact(
                root,
                {
                    "filename": str(subject),
                    "code": code,
                    "message": message,
                    "location": {"row": line},
                },
            )
        case _:
            return Err("invalid ty diagnostic")


def _ty_fields(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """Reject ambiguous type-checker JSON objects at every nesting level."""
    return _ruff_fields(pairs)


def parse_ty_output(root: Path, output: Output) -> Result[tuple[RuffFact, ...], str]:
    """Require structured type findings and the strict command status to agree."""
    if (
        isinstance(output.code, bool)
        or not root.is_absolute()
        or output.code not in {0, 1}
        or bool(output.stderr)
    ):
        return Err("ty diagnostic status or context is unavailable")
    try:
        rows: object = json.loads(output.stdout, object_pairs_hook=_ty_fields)
    except (ValueError, RecursionError):
        return Err("invalid ty JSON")
    if not isinstance(rows, list):
        return Err("invalid ty JSON rows")
    observed = tuple(_ty_fact(root, row) for row in rows)
    facts = tuple(item.value for item in observed if isinstance(item, Ok))
    if len(rows) != len(facts) or bool(facts) == (output.code == 0):
        return Err("ty diagnostics disagree with the subprocess status")
    return Ok(facts)


def record_ty_snapshot(run_dir: Path, snapshot: TySnapshot) -> Result[TySnapshot, str]:
    """Exclusively retain the original strict type-checker result."""
    parsed = parse_ty_output(snapshot.root, snapshot.output)
    if not snapshot.nonce or isinstance(parsed, Err) or parsed.value != snapshot.facts:
        return Err("invalid ty snapshot")
    record = json.dumps(
        {
            "nonce": snapshot.nonce,
            "root": str(snapshot.root),
            "code": snapshot.output.code,
            "stdout": snapshot.output.stdout,
            "stderr": snapshot.output.stderr,
        },
        sort_keys=True,
    ).encode("utf-8")
    path = run_dir / "ty-observation.json"
    try:
        flags = os.O_CREAT | os.O_WRONLY | os.O_EXCL
        descriptor = os.open(path, flags, mode=0o600)
        with os.fdopen(descriptor, "wb") as stream:
            original = os.fstat(stream.fileno())
            stream.write(record)
        after = path.lstat()
        if (
            path.is_symlink()
            or after.st_nlink != 1
            or (original.st_dev, original.st_ino) != (after.st_dev, after.st_ino)
            or path.read_bytes() != record
        ):
            return Err("ty observation changed during recording")
    except (OSError, UnicodeError) as exc:
        return Err("cannot record ty observation: " + str(exc))
    return Ok(
        replace(
            snapshot, record=record, record_identity=(original.st_dev, original.st_ino)
        )
    )


def coverage_text_floor(output: Output) -> Result[str, str]:
    """Distinguish the coverage floor from an unrelated report command error."""
    if isinstance(output.code, bool) or output.code not in {0, 2} or output.stderr:
        return Err("coverage report command failed unexpectedly")
    lines = output.stdout.splitlines()
    totals = tuple(line for line in lines if re.match(r"^TOTAL\s+", line))
    messages = tuple(line for line in lines if line.startswith("Coverage failure:"))
    expected = r"Coverage failure: total of \d+(?:\.\d+)? is less than fail-under=100"
    if len(totals) != 1 or not re.search(r"\s\d+(?:\.\d+)?%\s*$", totals[0]):
        return Err("coverage report total is missing or ambiguous")
    if output.code == COVERAGE_REPORT_FAILURE:
        return (
            Ok("floor")
            if len(messages) == 1
            and re.fullmatch(expected, messages[0])
            and lines[-1] == messages[0]
            else Err("coverage report failure is not the coverage floor")
        )
    return (
        Ok("complete")
        if not messages
        else Err("successful coverage report names a failure")
    )


def record_coverage_text(
    run_dir: Path, snapshot: CoverageTextSnapshot
) -> Result[CoverageTextSnapshot, str]:
    """Exclusively retain the report subprocess output and exact command."""
    if (
        not snapshot.nonce
        or not snapshot.root.is_absolute()
        or not snapshot.command
        or isinstance(coverage_text_floor(snapshot.output), Err)
    ):
        return Err("invalid coverage text observation")
    record = json.dumps(
        {
            "nonce": snapshot.nonce,
            "root": str(snapshot.root),
            "command": snapshot.command,
            "code": snapshot.output.code,
            "stdout": snapshot.output.stdout,
            "stderr": snapshot.output.stderr,
        },
        sort_keys=True,
    ).encode("utf-8")
    path = run_dir / "coverage-text.json"
    try:
        flags = os.O_WRONLY | os.O_EXCL | os.O_CREAT
        descriptor = os.open(path, flags, mode=0o600)
        with os.fdopen(descriptor, "wb") as stream:
            original = os.fstat(stream.fileno())
            stream.write(record)
        after = path.lstat()
        if (
            path.is_symlink()
            or after.st_nlink != 1
            or (after.st_dev, after.st_ino) != (original.st_dev, original.st_ino)
            or record != path.read_bytes()
        ):
            return Err("coverage text changed during recording")
    except (OSError, UnicodeError) as exc:
        return Err("cannot record coverage text: " + str(exc))
    return Ok(
        replace(
            snapshot, record=record, record_identity=(original.st_dev, original.st_ino)
        )
    )


def coverage_text_unchanged(
    run_dir: Path, nonce: str, before: Result[CoverageTextSnapshot, str] | None
) -> int:
    """Require the original report command record to survive later execution."""
    if before is None or isinstance(before, Err):
        click.echo("coverage-text: original capture unavailable", err=True)
        return 1
    path = run_dir / "coverage-text.json"
    try:
        current = path.lstat()
        same_nonce = before.value.nonce == nonce
        same_bytes = path.read_bytes() == before.value.record
        intact = (
            not path.is_symlink()
            and stat.S_ISREG(current.st_mode)
            and current.st_nlink == 1
            and same_nonce
            and before.value.record_identity == (current.st_dev, current.st_ino)
            and same_bytes
        )
    except OSError:
        intact = False
    if not intact:
        click.echo("coverage-text: missing or changed capture", err=True)
        return 1
    return 0


def ty_snapshot_unchanged(
    run_dir: Path, nonce: str, before: Result[TySnapshot, str] | None
) -> int:
    """Require the original type-checker record and file identity to survive."""
    if before is None or isinstance(before, Err):
        click.echo("ty-observation: original capture unavailable", err=True)
        return 1
    path = run_dir / "ty-observation.json"
    try:
        observed = path.lstat()
        contents = (
            path.read_bytes()
            if not path.is_symlink()
            and stat.S_ISREG(observed.st_mode)
            and observed.st_nlink == 1
            else b""
        )
        unchanged = (
            not path.is_symlink()
            and stat.S_ISREG(observed.st_mode)
            and observed.st_nlink == 1
            and nonce == before.value.nonce
            and before.value.record_identity == (observed.st_dev, observed.st_ino)
            and contents == before.value.record
        )
    except OSError:
        unchanged = False
    if not unchanged:
        click.echo("ty-observation: missing or changed capture", err=True)
        return 1
    return 0


def record_ruff_snapshot(
    run_dir: Path, snapshot: RuffSnapshot, *, filename: str = "ruff-observation.json"
) -> Result[RuffSnapshot, str]:
    """Exclusively record the original Ruff result with its run identity."""
    parsed = parse_ruff_output(snapshot.root, snapshot.output)
    if filename not in {"ruff-observation.json", "ruff-format-observation.json"}:
        return Err("invalid Ruff record name")
    if not snapshot.nonce or isinstance(parsed, Err) or parsed.value != snapshot.facts:
        return Err("invalid Ruff snapshot")
    record = json.dumps(
        {
            "nonce": snapshot.nonce,
            "root": str(snapshot.root),
            "code": snapshot.output.code,
            "stdout": snapshot.output.stdout,
            "stderr": snapshot.output.stderr,
        },
        sort_keys=True,
    ).encode("utf-8")
    path = run_dir / filename
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, mode=0o600)
        with os.fdopen(descriptor, "wb") as stream:
            original = os.fstat(stream.fileno())
            stream.write(record)
        after = path.lstat()
        if (
            path.is_symlink()
            or after.st_nlink != 1
            or (after.st_dev, after.st_ino) != (original.st_dev, original.st_ino)
            or path.read_bytes() != record
        ):
            return Err("Ruff observation changed during recording")
    except (OSError, UnicodeError) as exc:
        return Err("cannot record Ruff observation: " + str(exc))
    return Ok(
        replace(
            snapshot, record=record, record_identity=(original.st_dev, original.st_ino)
        )
    )


def ruff_snapshot_unchanged(
    run_dir: Path,
    nonce: str,
    before: Result[RuffSnapshot, str] | None,
    *,
    filename: str = "ruff-observation.json",
) -> int:
    """Require the original Ruff record and identity to survive later effects."""
    if (
        filename not in {"ruff-observation.json", "ruff-format-observation.json"}
        or before is None
        or isinstance(before, Err)
    ):
        click.echo("ruff-observation: original capture unavailable", err=True)
        return 1
    path = run_dir / filename
    try:
        observed = path.lstat()
        unchanged = (
            not path.is_symlink()
            and before.value.nonce == nonce
            and stat.S_ISREG(observed.st_mode)
            and observed.st_nlink == 1
            and (observed.st_dev, observed.st_ino) == before.value.record_identity
            and before.value.record == path.read_bytes()
        )
    except OSError:
        unchanged = False
    if not unchanged:
        click.echo("ruff-observation: missing or changed capture", err=True)
        return 1
    return 0


def record_python_commands(
    run_dir: Path,
    nonce: str,
    root: Path,
    observed: tuple[tuple[str, tuple[tuple[str, ...], ...]], ...],
    source_digest: str,
) -> Result[PythonCommandsSnapshot, str]:
    """Record only the attempted Python tool commands in this run."""
    commands = tuple(item for item in observed if item[0] in PYTHON_COMMAND_NAMES)
    if (
        not nonce
        or not root.is_absolute()
        or len(source_digest) != SHA256_HEX_LENGTH
        or any(character not in "0123456789abcdef" for character in source_digest)
        or tuple(name for name, _ in commands) != PYTHON_COMMAND_NAMES
        or any(
            not command or any(not arg for arg in command)
            for _, argv in commands
            for command in argv
        )
        or any(not argv for _, argv in commands)
    ):
        return Err("invalid Python command observation")
    record = json.dumps(
        {
            "nonce": nonce,
            "root": str(root),
            "commands": commands,
            "source_digest": source_digest,
        },
        sort_keys=True,
    ).encode("utf-8")
    path = run_dir / "python-commands.json"
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, mode=0o600)
        with os.fdopen(descriptor, "wb") as stream:
            original = os.fstat(stream.fileno())
            stream.write(record)
        current = path.lstat()
        if (
            path.is_symlink()
            or not stat.S_ISREG(current.st_mode)
            or current.st_nlink != 1
            or (current.st_dev, current.st_ino) != (original.st_dev, original.st_ino)
            or path.read_bytes() != record
        ):
            return Err("Python command observation changed during recording")
    except (OSError, UnicodeError) as exc:
        return Err("cannot record Python commands: " + str(exc))
    return Ok(
        PythonCommandsSnapshot(
            nonce, root, commands, record, (original.st_dev, original.st_ino)
        )
    )


def _capture_python_commands(
    context: CheckRun,
    census: Result[tuple[evidence.Entry, ...], str],
    commands: tuple[tuple[str, tuple[tuple[str, ...], ...]], ...],
) -> Result[PythonCommandsSnapshot, str]:
    """Bind the command record to the original guarded Python source bytes."""
    if isinstance(census, Err):
        return Err("Python command source census unavailable")
    digest = evidence.digest_census(census.value)
    if isinstance(digest, Err):
        return Err("Python command source digest unavailable")
    return record_python_commands(
        context.directory, context.nonce, context.root, commands, digest.value
    )


def python_commands_unchanged(
    run_dir: Path,
    nonce: str,
    root: Path,
    before: Result[PythonCommandsSnapshot, str] | None,
) -> int:
    """Check that the original command observation survived subsequent work."""
    if before is None or isinstance(before, Err):
        click.echo("python-commands: original capture unavailable", err=True)
        return 1
    path = run_dir / "python-commands.json"
    try:
        current = path.lstat()
        intact = (
            before.value.nonce == nonce
            and before.value.root == root
            and not path.is_symlink()
            and stat.S_ISREG(current.st_mode)
            and current.st_nlink == 1
            and (current.st_dev, current.st_ino) == before.value.record_identity
            and path.read_bytes() == bytes(before.value.record)
        )
    except OSError:
        intact = False
    if not intact:
        click.echo("python-commands: missing or changed capture", err=True)
        return 1
    return 0


def _capture_coverage_text_step(
    run: tuple[Path, Path, str],
    leg: Leg,
    attempt: tuple[int, tuple[str, ...], Result[Output, SpawnError]],
    previous: Result[CoverageTextSnapshot, str] | None,
) -> Result[CoverageTextSnapshot, str] | None:
    """Capture only the actual report follow-up in the pytest leg."""
    root, run_dir, nonce = run
    index, command, result = attempt
    if leg.name != "pytest" or index != COVERAGE_REPORT_INDEX:
        return previous
    return (
        record_coverage_text(
            run_dir, CoverageTextSnapshot(nonce, root, command, result.value)
        )
        if isinstance(result, Ok) and command[1:4] == ("-m", "coverage", "report")
        else Err("coverage report subprocess unavailable")
    )


def _run_leg_observed(root: Path, run_dir: Path, nonce: str, leg: Leg) -> LegOutcome:
    """Preserve the primary failure while running explicitly independent reports."""
    primary = 0
    substeps: tuple[int, ...] = ()
    pytest: Result[evidence.RunEvidence, str] | None = None
    host: Result[lanes.HostFacts, str] | None = None
    killers: Result[mutant_report.Report, str] | None = None
    ruff: Result[RuffSnapshot, str] | None = None
    commands: tuple[tuple[str, ...], ...] = ()
    ruff_format: Result[RuffSnapshot, str] | None = None
    ty: Result[TySnapshot, str] | None = None
    coverage_text: Result[CoverageTextSnapshot, str] | None = None
    for index, command in enumerate((leg.argv, *leg.after)):
        commands += (command,)
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
        if leg.name == "ruff-check" and index == 0:
            parsed = (
                parse_ruff_output(root, result.value)
                if isinstance(result, Ok) and "--output-format=json" in command
                else Err("Ruff JSON subprocess unavailable")
            )
            ruff = (
                record_ruff_snapshot(
                    run_dir, RuffSnapshot(nonce, root, result.value, parsed.value)
                )
                if isinstance(result, Ok) and isinstance(parsed, Ok)
                else Err("Ruff diagnostics unavailable or invalid")
            )
        if leg.name == "ruff-format" and index == 0:
            formatted = (
                parse_ruff_output(root, result.value)
                if isinstance(result, Ok) and "--output-format=json" in command
                else Err("Ruff format JSON subprocess unavailable")
            )
            ruff_format = (
                record_ruff_snapshot(
                    run_dir,
                    RuffSnapshot(nonce, root, result.value, formatted.value),
                    filename="ruff-format-observation.json",
                )
                if isinstance(result, Ok)
                and isinstance(formatted, Ok)
                and all(fact.code == "unformatted" for fact in formatted.value)
                else Err("Ruff format diagnostics unavailable or invalid")
            )
        if leg.name == "ty" and index == 0:
            parsed_ty = (
                parse_ty_output(root, result.value)
                if isinstance(result, Ok) and "--output-format=gitlab" in command
                else Err("ty JSON subprocess unavailable")
            )
            ty = (
                record_ty_snapshot(
                    run_dir, TySnapshot(nonce, root, result.value, parsed_ty.value)
                )
                if isinstance(result, Ok) and isinstance(parsed_ty, Ok)
                else Err("ty diagnostics unavailable or invalid")
            )
        coverage_text = _capture_coverage_text_step(
            (root, run_dir, nonce), leg, (index, command, result), coverage_text
        )
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
                return LegOutcome(
                    primary,
                    substeps,
                    pytest,
                    host,
                    killers,
                    ruff,
                    commands,
                    ruff_format,
                    ty,
                    coverage_text,
                )
    return LegOutcome(
        primary,
        substeps,
        pytest,
        host,
        killers,
        ruff,
        commands,
        ruff_format,
        ty,
        coverage_text,
    )


def run_leg(root: Path, run_dir: Path, nonce: str, leg: Leg) -> int:
    """Run a subprocess-backed leg and expose its aggregate result."""
    return _run_leg_observed(root, run_dir, nonce, leg).code


def _run_native_step_with_absence(
    leg: haskell.HaskellStep, run_dir: Path, nonce: str
) -> tuple[int, str | None]:
    """Record complete report absence immediately after a failed native step."""
    code = haskell.run_step(leg, run_dir, nonce)
    marker = None
    if leg.name == "cabal-test" and code:
        absence = native_absence_observation(run_dir, nonce, code)
        if isinstance(absence, Ok):
            marker = absence.value
            click.echo(absence.value)
    return code, marker


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
    ruff: Result[RuffSnapshot, str] | None = None
    commands: tuple[tuple[str, tuple[tuple[str, ...], ...]], ...] = ()
    ruff_format: Result[RuffSnapshot, str] | None = None
    ty: Result[TySnapshot, str] | None = None
    coverage_text: Result[CoverageTextSnapshot, str] | None = None
    native_absence: str | None = None
    for leg in legs:
        if isinstance(leg, EnsureStep):
            code = run_step(leg)
        elif isinstance(leg, haskell.HaskellStep):
            code, native_absence = _run_native_step_with_absence(leg, run_dir, nonce)
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
            ruff = result.ruff or ruff
            ruff_format = result.ruff_format or ruff_format
            ty = result.ty or ty
            coverage_text = result.coverage_text or coverage_text
            commands += ((leg.name, result.commands),)
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
        ruff,
        commands,
        ruff_format,
        ty,
        coverage_text,
        native_absence,
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


def native_absence_observation(
    directory: Path, nonce: str, code: int
) -> Result[str, str]:
    """Observe complete native report absence at a failed native step."""
    if not nonce or isinstance(code, bool) or code <= 0:
        return Err("invalid native absence identity")
    try:
        before = directory.lstat()
        if (
            directory.is_symlink()
            or directory.is_junction()
            or not stat.S_ISDIR(before.st_mode)
        ):
            return Err("native absence directory unavailable")
        for name in NATIVE_REPORT_FILES:
            try:
                (directory / name).lstat()
            except FileNotFoundError:
                continue
            return Err("native report exists")
        after = directory.lstat()
        if (
            directory.is_symlink()
            or directory.is_junction()
            or (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino)
        ):
            return Err("native absence directory changed")
    except OSError:
        return Err("native absence cannot be observed")
    return Ok(
        NATIVE_ABSENCE_OBSERVATION
        + " "
        + json.dumps({"nonce": nonce, "status": code}, sort_keys=True)
    )


def verify_native_absence_handoff(
    directory: Path, nonce: str, output: str, outcomes: evidence.LegEvidence
) -> Result[None, str]:
    """Join an original absence observation to the failed sealed native step."""
    codes = tuple(code for name, code in outcomes.outcomes if name == "cabal-test")
    if outcomes.nonce != nonce or len(codes) != 1:
        return Err("native absence tool status unavailable")
    observed = native_absence_observation(directory, nonce, codes[0])
    markers = tuple(
        line
        for line in output.splitlines()
        if line.startswith(NATIVE_ABSENCE_OBSERVATION + " ")
    )
    return (
        observed
        if isinstance(observed, Err)
        else Ok(None)
        if markers == (observed.value,)
        else Err("native absence observation missing or ambiguous")
    )


def captured_native_absence(tools: ToolOutcome, directory: Path, nonce: str) -> bool:
    """Recognize only the original failed step with complete report absence."""
    return (
        tools.native_absence is not None
        and not isinstance(tools.native, Ok)
        and isinstance(tools.evidence, Ok)
        and verify_native_absence_handoff(
            directory, nonce, tools.native_absence, tools.evidence.value
        )
        == Ok(None)
    )


def native_integrity_attribution(
    code: int, tools: ToolOutcome, directory: Path, nonce: str
) -> tuple[bool, int]:
    """Retain shared integrity failure unless original absence is observed."""
    localized = bool(code) and captured_native_absence(tools, directory, nonce)
    return localized, int(bool(code) and not localized)


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
    artifacts = native_artifact_record(run_dir, nonce)
    return (
        artifacts
        if isinstance(artifacts, Err)
        else Ok(NativeSnapshot(manifest.value, sources.value, entries, artifacts.value))
    )


def native_artifact_record(
    directory: Path, nonce: str
) -> Result[tuple[tuple[str, str, str], ...], str]:
    """Read canonical native artifact observations without issuing a receipt."""
    path = directory / "native-artifacts.json"
    if not path.exists() and not path.is_symlink():
        return Ok(())
    record = _read_provisional_handoff(path)
    if isinstance(record, Err):
        return Err("native artifact record unavailable")
    try:
        value: object = json.loads(record.value, object_pairs_hook=_ruff_record_fields)
    except (ValueError, UnicodeError, RecursionError):
        return Err("invalid native artifact record")
    if (
        not isinstance(value, dict)
        or set(value) != {"nonce", "artifacts"}
        or value.get("nonce") != nonce
        or not nonce
        or not isinstance(value.get("artifacts"), list)
    ):
        return Err("invalid native artifact record identity")
    rows = value["artifacts"]
    facts = _parse_native_artifact_rows(rows)
    if isinstance(facts, Err):
        return facts
    canonical = json.dumps({"nonce": nonce, "artifacts": facts.value}).encode("utf-8")
    return facts if record.value == canonical else Err("noncanonical native artifacts")


def _parse_native_artifact_rows(
    rows: object,
) -> Result[tuple[tuple[str, str, str], ...], str]:
    """Validate roles, absolute paths and digests before joining observations."""
    if not isinstance(rows, list):
        return Err("invalid native artifact observations")
    facts: tuple[tuple[str, str, str], ...] = ()
    for row in rows:
        match row:
            case [str() as name, str() as path, str() as digest] if (
                name
                and Path(path).is_absolute()
                and re.fullmatch(r"[0-9a-f]{64}", digest)
            ):
                facts += ((name, path, digest),)
            case _:
                return Err("invalid native artifact observations")
    return (
        Ok(facts)
        if tuple(name for name, _path, _digest in facts)
        == ("ghc", "cabal", "native-test")
        else Err("invalid native artifact roles")
    )


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
        or before.value.artifacts != after.value.artifacts
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
    fragments = _census_mutant_declarations(entries)
    if isinstance(fragments, Err):
        return ("validators: " + fragments.error,)
    partial = frozenset(claim.identifier for claim in parsed.value)
    elsewhere = frozenset(
        claim.identifier
        for claim in fragments.value[1]
        if claim.owner == 0 and claim.identifier not in partial
    )
    declared = (
        frozenset(
            identifier
            for sprint in declarations[0].sprints
            for identifier in closure.mutant_ids(field(sprint.text, "Mutants"))
        )
        - elsewhere
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


def receipt_native_citations(
    declarations: tuple[Phase, ...],
    records: tuple[Mutant, ...],
    owners: tuple[tuple[str, int], ...],
) -> Result[tuple[tuple[int, str], ...], str]:
    """Retain native requirements from both the plan and mutation corpus."""
    by_owner = dict(owners)
    numbers = frozenset(phase.number for phase in declarations)
    if (
        len(numbers) != len(declarations)
        or len(by_owner) != len(owners)
        or frozenset(by_owner) != frozenset(record.identifier for record in records)
        or len({record.identifier for record in records}) != len(records)
        or not frozenset(by_owner.values()) <= numbers
        or any(isinstance(owner, bool) for owner in by_owner.values())
    ):
        return Err("invalid receipt native citation ownership")
    cited = frozenset(
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
        if node.startswith("haskell:")
    )
    killers = frozenset(
        (by_owner[record.identifier], node)
        for record in records
        for node in record.killers
        if node.startswith("haskell:")
    )
    return Ok(tuple(sorted(cited | killers)))


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
    if isinstance(standards, Err):
        return standards
    if isinstance(overview, Err):
        return overview
    return Ok(
        closure.CapturedPolicy(
            owners,
            standards.value.replace("\r\n", "\n").replace("\r", "\n"),
            overview.value.replace("\r\n", "\n").replace("\r", "\n"),
            frozenset(entry.path for entry in entries if entry.kind == "file"),
            frozenset(entry.path for entry in entries if entry.kind == "symlink"),
            frozenset(entry.path for entry in entries if entry.kind == "directory"),
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
        return ownership.bind_mutants_with_missing_inputs(
            manifest, entries, records, claims, None
        )
    bound = ownership.bind_mutants_observed(
        manifest, entries, records, claims, tuple(sorted(native))
    )
    return (
        bound
        if isinstance(bound, Ok)
        else ownership.bind_mutants_with_missing_inputs(
            manifest, entries, records, claims, tuple(sorted(native))
        )
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
    bound = ownership.bind_mutants_observed(
        manifest, entries, records, claims, native_sources
    )
    return (
        bound
        if isinstance(bound, Ok)
        else ownership.bind_mutants_with_missing_inputs(
            manifest, entries, records, claims, native_sources
        )
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


def scoped_mutant_mapping(
    entries: tuple[evidence.Entry, ...],
    records: tuple[Mutant, ...],
    native_sources: tuple[tuple[str, str], ...] | None = None,
) -> Result[ownership.ScopedMutantMapping, str]:
    """Recover owner declarations and their mandatory scoped failures."""
    declarations = _census_mutant_declarations(entries)
    if isinstance(declarations, Err):
        return declarations
    manifest, claims = declarations.value
    return ownership.scoped_mutant_mapping(
        manifest, entries, records, claims, native_sources
    )


def declared_scoped_mutant_mapping(
    entries: tuple[evidence.Entry, ...], records: tuple[Mutant, ...]
) -> Result[ownership.ScopedMutantMapping, str]:
    """Defer native identities until the actual native snapshot is observed."""
    declarations = _census_mutant_declarations(entries)
    if isinstance(declarations, Err):
        return declarations
    manifest, claims = declarations.value
    native = tuple(
        sorted(
            {
                (node, path)
                for claim in claims
                for node, path in claim.killer_sources
                if node.startswith("haskell:")
            }
        )
    )
    return ownership.scoped_mutant_mapping(
        manifest, entries, records, claims, native or None
    )


def observed_scoped_mutant_mapping(
    entries: tuple[evidence.Entry, ...],
    records: tuple[Mutant, ...],
    native_sources: tuple[tuple[str, str], ...],
) -> Result[ownership.ScopedMutantMapping, str]:
    """Refuse invented native identities while retaining owned absences."""
    declarations = _census_mutant_declarations(entries)
    if isinstance(declarations, Err):
        return declarations
    manifest, claims = declarations.value
    present = frozenset(entry.path for entry in entries if entry.kind == "file")
    sources = dict(native_sources)
    if any(
        path in present and sources.get(node) != path
        for claim in claims
        for node, path in claim.killer_sources
        if node.startswith("haskell:")
    ):
        return Err("present native killer lacks its observed source")
    return ownership.scoped_mutant_mapping(
        manifest, entries, records, claims, native_sources
    )


def provisional_or_scoped_mutant_owners(
    entries: tuple[evidence.Entry, ...], records: tuple[Mutant, ...]
) -> Result[tuple[tuple[str, int], ...], str]:
    """Prefer verified declarations, retaining a scoped fallback for damage."""
    direct = provisional_mutant_owners(entries, records)
    if isinstance(direct, Ok):
        return direct
    scoped = declared_scoped_mutant_mapping(entries, records)
    return scoped if isinstance(scoped, Err) else Ok(scoped.value.owners)


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


def scoped_ownership_validation(
    problems: tuple[str, ...],
    census: Result[tuple[evidence.Entry, ...], str],
    declarations: Result[tuple[Phase, ...], str],
) -> tuple[str, ...]:
    """Keep independently attributable ownership damage on its consumers."""
    if isinstance(census, Err) or isinstance(declarations, Err):
        return problems
    work = scoped_source_inputs(census.value, declarations.value)
    if isinstance(work, Err):
        return problems
    missing = sorted(
        {message for _number, failures in work.value.missing for message in failures}
    )
    if not missing:
        return _scoped_test_consumer_validation(
            problems, census.value, declarations.value
        )
    ownership_failure = "validators: source ownership: " + "; ".join(missing)
    if problems.count(ownership_failure) != 1:
        return problems
    scoped = _remove_owned_source_failure(problems, ownership_failure)
    return _scoped_test_consumer_validation(scoped, census.value, declarations.value)


def scoped_mutant_declaration_validation(
    problems: tuple[str, ...],
    census: Result[tuple[evidence.Entry, ...], str],
    declarations: Result[tuple[Phase, ...], str],
    claims: tuple[tuple[Mutant, ...], tuple[tuple[str, int], ...]] | None,
) -> tuple[str, ...]:
    """Scope an exact integrity aggregate only after proving its sole cause."""
    if isinstance(census, Err) or isinstance(declarations, Err) or claims is None:
        return problems
    records, owners = claims
    policy = census_policy(census.value, owners)
    if isinstance(policy, Err):
        return problems
    proven = closure.undeclared_only_integrity(
        declarations.value, records, policy.value
    )
    prefix = "plan.gate-integrity: "
    observed = tuple(problem for problem in problems if problem.startswith(prefix))
    if isinstance(proven, Ok):
        return _scope_undeclared_integrity(problems, proven, observed, prefix)
    attributed = closure.scoped_integrity_failures(
        declarations.value, records, policy.value
    )
    return (
        tuple(problem for problem in problems if not problem.startswith(prefix))
        if isinstance(attributed, Ok) and observed == attributed.value.diagnostics
        else problems
    )


def _scope_undeclared_integrity(
    problems: tuple[str, ...],
    proven: Result[tuple[str, ...], str],
    observed: tuple[str, ...],
    prefix: str,
) -> tuple[str, ...]:
    """Retain the strict exact-match rule for omission-only integrity."""
    return (
        tuple(problem for problem in problems if not problem.startswith(prefix))
        if isinstance(proven, Ok) and observed == proven.value
        else problems
    )


def _remove_owned_source_failure(
    problems: tuple[str, ...], ownership_failure: str
) -> tuple[str, ...]:
    """Remove the uniquely matched aggregate after its consumers are known."""
    return tuple(problem for problem in problems if problem != ownership_failure)


def _scoped_test_consumer_validation(
    scoped: tuple[str, ...],
    entries: tuple[evidence.Entry, ...],
    phases: tuple[Phase, ...],
) -> tuple[str, ...]:
    """Match every consumer diagnostic to its phase collection observation."""
    text = _census_text(entries, "src/agentctl/check/source_ownership.toml")
    if isinstance(text, Err):
        return scoped
    manifest = ownership.parse_manifest(text.value)
    if isinstance(manifest, Err):
        return scoped
    collections = diagnostic_collection_scopes(manifest.value, phases)
    if isinstance(collections, Err):
        return scoped
    prefix = "validators: test consumers: "
    expected = tuple(prefix + issue for _number, issue in collections.value[1])
    observed = tuple(problem for problem in scoped if problem.startswith(prefix))
    return (
        tuple(problem for problem in scoped if not problem.startswith(prefix))
        if expected and observed == expected
        else scoped
    )


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


def _coverage_declarations(
    entries: tuple[evidence.Entry, ...], family: Family
) -> Result[tuple[str, tuple[str, ...]], str]:
    """Read a pinned version and host omissions from the guarded source census."""
    config = _census_text(entries, "pyproject.toml")
    hosts = _census_text(entries, COVERAGE_HOSTS)
    if isinstance(config, Err) or isinstance(hosts, Err):
        return Err("coverage capture declarations unavailable")
    version = coverage_hosts.pinned_version(config.value)
    declared = coverage_hosts.parse(hosts.value)
    if isinstance(version, Err) or isinstance(declared, Err):
        return Err("invalid coverage capture declarations")
    present = frozenset(entry.path for entry in entries if entry.kind == "file")
    if coverage_hosts.missing(declared.value, present):
        return Err("coverage host declarations name missing sources")
    return Ok((version.value, coverage_hosts.foreign(declared.value, family)))


def _coverage_request(
    context: CheckRun,
    entries: tuple[evidence.Entry, ...],
    leg: Leg,
    substeps: Result[evidence.ToolSubsteps, str],
) -> Result[CoverageRequest, str]:
    """Bind the JSON command to captured configuration and the actual report leg."""
    root, run_dir, nonce, family = (
        context.root,
        context.directory,
        context.nonce,
        context.family,
    )
    if len(nonce) != COVERAGE_NONCE_LENGTH or any(
        character not in "0123456789abcdef" for character in nonce
    ):
        return Err("invalid coverage capture nonce")
    declarations = _coverage_declarations(entries, family)
    if isinstance(declarations, Err):
        return declarations
    version, foreign = declarations.value
    expected = coverage_commands(sys.executable, root, run_dir, foreign)
    if leg.name != "pytest" or leg.after != expected or isinstance(substeps, Err):
        return Err("coverage capture schedule unavailable or changed")
    observations = tuple(
        codes for name, codes in substeps.value.outcomes if name == "pytest"
    )
    if (
        substeps.value.nonce != nonce
        or len(observations) != 1
        or len(observations[0]) != phase_reports.PYTEST_FULL_STEPS
        or observations[0][1] != 0
    ):
        return Err("coverage report was not executed")
    report = expected[-1]
    command = (
        *report[:3],
        "json",
        *report[4:-1],
        "-o",
        str(run_dir / "coverage-raw.json"),
    )
    return Ok(CoverageRequest(version, command, observations[0][2], entries))


def _render_coverage(
    context: CheckRun, request: CoverageRequest
) -> Result[CoverageRendered, str]:
    """Run coverage against an exclusively reserved raw report file."""
    root, run_dir, nonce = context.root, context.directory, context.nonce
    raw_path = run_dir / "coverage-raw.json"
    try:
        descriptor = os.open(raw_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            reserved = os.fstat(descriptor)
        finally:
            os.close(descriptor)
    except OSError as exc:
        return Err("cannot reserve coverage report: " + str(exc))
    result = run(
        list(request.command),
        cwd=root,
        env=environment(os.environ, run_dir, nonce, tool="pytest"),
        timeout=PYTHON_LEG_TIMEOUT_SECONDS,
    )
    if isinstance(result, Err):
        return Err("coverage JSON command failed: " + result.error.message)
    try:
        observed = raw_path.lstat()
        if (
            raw_path.is_symlink()
            or observed.st_nlink != 1
            or (observed.st_dev, observed.st_ino) != (reserved.st_dev, reserved.st_ino)
        ):
            return Err("coverage report file identity changed")
        raw = raw_path.read_bytes()
        report_text = raw.decode("utf-8")
    except (OSError, UnicodeError) as exc:
        return Err("cannot read coverage JSON report: " + str(exc))
    return _coverage_rendered(raw, report_text, request, result.value.code, reserved)


def _coverage_rendered(
    raw: bytes,
    report_text: str,
    request: CoverageRequest,
    status: int,
    reserved: os.stat_result,
) -> Result[CoverageRendered, str]:
    """Join parsed facts to both actual tool statuses and reserved identity."""
    parsed = coverage_hosts.parse_report(report_text, request.version)
    if isinstance(parsed, Err):
        return Err("coverage JSON report: " + parsed.error)
    expected_status = (
        2
        if any(
            fact.missing_statements or fact.missing_branches for fact in parsed.value
        )
        else 0
    )
    if status != expected_status or request.report_status != expected_status:
        return Err("coverage report status differs from JSON observations")
    return Ok(CoverageRendered(parsed.value, raw, (reserved.st_dev, reserved.st_ino)))


def _record_coverage(
    context: CheckRun, request: CoverageRequest, rendered: CoverageRendered
) -> Result[CoverageSnapshot, str]:
    """Record the original raw report under this run's nonce, without overwrite."""
    nonce, run_dir = context.nonce, context.directory
    try:
        report_text = rendered.raw.decode("utf-8")
    except UnicodeError:
        return Err("invalid coverage report encoding")
    record = json.dumps(
        {"nonce": nonce, "version": request.version, "report": report_text},
        sort_keys=True,
    ).encode("utf-8")
    path = run_dir / "coverage-report.json"
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, mode=0o600)
        with os.fdopen(descriptor, "wb") as stream:
            record_identity = os.fstat(stream.fileno())
            stream.write(record)
        recorded = path.lstat()
        if (
            path.is_symlink()
            or recorded.st_nlink != 1
            or (recorded.st_dev, recorded.st_ino)
            != (record_identity.st_dev, record_identity.st_ino)
            or path.read_bytes() != record
        ):
            return Err("coverage capture changed during recording")
    except (OSError, UnicodeError) as exc:
        return Err("cannot record coverage capture: " + str(exc))
    return Ok(
        CoverageSnapshot(
            nonce,
            rendered.facts,
            record,
            (record_identity.st_dev, record_identity.st_ino),
            rendered.raw,
            rendered.identity,
            request.entries,
        )
    )


def capture_coverage(
    context: CheckRun,
    entries: tuple[evidence.Entry, ...],
    leg: Leg,
    substeps: Result[evidence.ToolSubsteps, str],
) -> Result[CoverageSnapshot, str]:
    """Capture actual coverage JSON after the report, without issuing a verdict."""
    request = _coverage_request(context, entries, leg, substeps)
    if isinstance(request, Err):
        return request
    rendered = _render_coverage(context, request.value)
    if isinstance(rendered, Err):
        return rendered
    return _record_coverage(context, request.value, rendered.value)


def coverage_text_agreement(inputs: CoverageTextInputs) -> Result[None, str]:
    """Join the actual report command to the guarded JSON coverage observation."""
    context, entries, leg, substeps, text, coverage = (
        inputs.context,
        inputs.entries,
        inputs.leg,
        inputs.substeps,
        inputs.text,
        inputs.coverage,
    )
    request = _coverage_request(context, entries, leg, substeps)
    if isinstance(request, Err):
        return request
    if text is None or isinstance(text, Err) or isinstance(coverage, Err):
        return Err("coverage text or JSON observation unavailable")
    checked = _parse_coverage_handoff(
        context.nonce, coverage.value.record, coverage.value.report
    )
    try:
        report_text = coverage.value.report.decode("utf-8")
    except UnicodeError:
        return Err("coverage JSON report is not UTF-8")
    facts = coverage_hosts.parse_report(report_text, request.value.version)
    if (
        isinstance(checked, Err)
        or isinstance(facts, Err)
        or facts.value != coverage.value.facts
    ):
        return Err("coverage JSON facts differ from the captured report")
    floor = coverage_text_floor(text.value.output)
    gaps = any(
        fact.missing_statements or fact.missing_branches
        for fact in coverage.value.facts
    )
    if (
        isinstance(floor, Err)
        or text.value.nonce != context.nonce
        or text.value.root != context.root
        or text.value.command != leg.after[-1]
        or text.value.output.code != request.value.report_status
        or coverage.value.nonce != context.nonce
        or coverage.value.entries != entries
        or (floor.value == "floor") != gaps
    ):
        return Err("coverage text differs from the captured JSON report or command")
    return Ok(None)


def coverage_snapshot_unchanged(
    run_dir: Path, nonce: str, before: Result[CoverageSnapshot, str] | None
) -> int:
    """Require the captured coverage report to survive unchanged and unlinked."""
    if before is None or isinstance(before, Err):
        click.echo("coverage-observation: capture unavailable", err=True)
        return 1
    path = run_dir / "coverage-report.json"
    raw_path = run_dir / "coverage-raw.json"
    try:
        record_stat = path.lstat()
        raw_stat = raw_path.lstat()
        unchanged = (
            before.value.nonce == nonce
            and not path.is_symlink()
            and record_stat.st_nlink == 1
            and (record_stat.st_dev, record_stat.st_ino) == before.value.record_identity
            and path.read_bytes() == before.value.record
            and not raw_path.is_symlink()
            and raw_stat.st_nlink == 1
            and (raw_stat.st_dev, raw_stat.st_ino) == before.value.report_identity
            and raw_path.read_bytes() == before.value.report
        )
    except OSError:
        unchanged = False
    if not unchanged:
        click.echo("coverage-observation: missing or changed capture", err=True)
        return 1
    return 0


def _capture_tool_coverage(
    context: CheckRun,
    census: Result[tuple[evidence.Entry, ...], str],
    legs: tuple[Leg, ...],
    substeps: Result[evidence.ToolSubsteps, str],
) -> Result[CoverageSnapshot, str]:
    """Capture the unique planned pytest leg or retain its refusal."""
    pytest_legs = tuple(leg for leg in legs if leg.name == "pytest")
    result = (
        capture_coverage(context, census.value, pytest_legs[0], substeps)
        if isinstance(census, Ok) and len(pytest_legs) == 1
        else Err("coverage capture inputs unavailable")
    )
    if isinstance(result, Err):
        click.echo("coverage-observation: " + result.error, err=True)
    return result


def coverage_text_integrity(
    context: CheckRun,
    census: Result[tuple[evidence.Entry, ...], str],
    planned: tuple[Leg, ...],
    tools: ToolOutcome,
    coverage: Result[CoverageSnapshot, str],
) -> int:
    """Require the actual report command to agree with current JSON coverage."""
    legs = tuple(leg for leg in planned if leg.name == "pytest")
    agreement = (
        coverage_text_agreement(
            CoverageTextInputs(
                context,
                census.value,
                legs[0],
                tools.substeps,
                tools.coverage_text,
                coverage,
            )
        )
        if isinstance(census, Ok) and len(legs) == 1
        else Err("coverage text source or schedule unavailable")
    )
    intact = coverage_text_unchanged(
        context.directory, context.nonce, tools.coverage_text
    )
    if isinstance(agreement, Err):
        click.echo("coverage-text: " + agreement.error, err=True)
        return 1
    return intact


def _coverage_source_owners(
    entries: tuple[evidence.Entry, ...], phases: tuple[phase_reports.PhaseInputs, ...]
) -> Result[tuple[coverage_hosts.CoverageOwner, ...], str]:
    """Join every present Python source to captured phase ownership."""
    text = _census_text(entries, "src/agentctl/check/source_ownership.toml")
    if isinstance(text, Err):
        return Err("coverage ownership unavailable: " + text.error)
    manifest = ownership.parse_manifest(text.value)
    if isinstance(manifest, Err):
        return Err("invalid coverage ownership: " + manifest.error)
    declared = tuple(
        (phase.number, phase.prerequisites) for phase in manifest.value.phases
    )
    expected = tuple((phase.number, phase.prerequisites) for phase in phases)
    sources = tuple(
        entry
        for entry in entries
        if entry.path.startswith("src/agentctl/") and entry.path.endswith(".py")
    )
    artifacts = {artifact.path: artifact for artifact in manifest.value.artifacts}
    if (
        declared != expected
        or not sources
        or len({entry.path for entry in entries}) != len(entries)
        or any(entry.kind != "file" or entry.path not in artifacts for entry in sources)
    ):
        return Err("coverage source ownership or census is incomplete")
    return Ok(
        tuple(
            coverage_hosts.CoverageOwner(entry.path, artifacts[entry.path].consumers)
            for entry in sources
        )
    )


def _coverage_captured_facts(
    captured: CoverageAttributionInputs,
) -> Result[tuple[coverage_hosts.CoverageFact, ...], str]:
    """Verify that the captured report, host and source values agree."""
    if (
        captured.host is None
        or isinstance(captured.host, Err)
        or captured.coverage is None
        or isinstance(captured.coverage, Err)
        or isinstance(captured.substeps, Err)
    ):
        return Err("coverage host or report observation unavailable")
    snapshot = captured.coverage.value
    if (
        not captured.nonce
        or snapshot.nonce != captured.nonce
        or snapshot.entries != captured.entries
        or captured.host.value.family != captured.family
    ):
        return Err("coverage host, nonce or source census differs")
    checked = _parse_coverage_handoff(captured.nonce, snapshot.record, snapshot.report)
    declarations = _coverage_declarations(captured.entries, captured.family)
    if isinstance(checked, Err) or isinstance(declarations, Err):
        return Err("coverage report or declarations are invalid")
    text = snapshot.report.decode("utf-8", errors="replace")
    parsed = coverage_hosts.parse_report(text, declarations.value[0])
    if isinstance(parsed, Err) or parsed.value != snapshot.facts:
        return Err("coverage facts differ from the captured report")
    statuses = tuple(
        codes for name, codes in captured.substeps.value.outcomes if name == "pytest"
    )
    expected = (
        2
        if any(
            fact.missing_statements or fact.missing_branches for fact in parsed.value
        )
        else 0
    )
    return (
        Err("coverage report status or nonce differs")
        if (
            captured.substeps.value.nonce != captured.nonce
            or len(statuses) != 1
            or len(statuses[0]) != phase_reports.PYTEST_FULL_STEPS
            or statuses[0][1] != 0
            or statuses[0][2] != expected
        )
        else parsed
    )


def coverage_phase_observations(
    captured: CoverageAttributionInputs,
) -> Result[tuple[tuple[int, frozenset[str]], ...], str]:
    """Attribute captured coverage diagnostically; this does not issue a verdict."""
    facts = _coverage_captured_facts(captured)
    owners = _coverage_source_owners(captured.entries, captured.phases)
    hosts = _census_text(captured.entries, COVERAGE_HOSTS)
    declared = hosts if isinstance(hosts, Err) else coverage_hosts.parse(hosts.value)
    joined = phase_reports.join_results(
        phase_reports.join_results(facts, owners), declared
    )
    if isinstance(joined, Err):
        return joined
    (found, owner_values), declared_values = joined.value
    return coverage_hosts.attribute(
        found,
        owner_values,
        declared_values,
        captured.family,
        tuple(phase.number for phase in captured.phases),
    )


def _coverage_localized_shared(
    captured: ProvisionalCapture,
    entries: tuple[evidence.Entry, ...],
    attribution: ToolFailureAttribution,
    scoped: dict[int, frozenset[str]],
) -> ToolFailureAttribution:
    """Localize only an intact, independently identified coverage-floor failure."""
    context, leg, text, coverage = (
        captured.coverage_context,
        captured.coverage_leg,
        captured.tools.coverage_text,
        captured.coverage,
    )
    if (
        context is None
        or leg is None
        or text is None
        or isinstance(text, Err)
        or coverage is None
        or isinstance(coverage, Err)
        or context.nonce != captured.nonce
        or context.family != captured.family
        or text.value.output.code != COVERAGE_REPORT_FAILURE
        or not any(scoped.values())
        or "coverage report failed" not in attribution.shared
    ):
        return attribution
    agreement = coverage_text_agreement(
        CoverageTextInputs(
            context, entries, leg, captured.tools.substeps, text, coverage
        )
    )
    if (
        isinstance(agreement, Err)
        or coverage_text_unchanged(context.directory, context.nonce, text)
        or coverage_snapshot_unchanged(context.directory, context.nonce, coverage)
    ):
        return attribution
    return replace(
        attribution, shared=attribution.shared - frozenset({"coverage report failed"})
    )


def _coverage_provisional_attribution(
    captured: ProvisionalCapture,
    entries: tuple[evidence.Entry, ...],
    phases: tuple[phase_reports.PhaseInputs, ...],
    attribution: ToolFailureAttribution,
) -> Result[ToolFailureAttribution, str]:
    """Scope a floor failure only after its actual report transcript is verified."""
    if captured.family is None and captured.coverage is None:
        unchanged = ToolFailureAttribution(
            attribution.shared,
            attribution.scoped,
        )
        return Ok(unchanged)
    if captured.family is None:
        return Err("coverage host family unavailable")
    observations = coverage_phase_observations(
        CoverageAttributionInputs(
            entries,
            phases,
            captured.nonce,
            captured.family,
            captured.tools.host,
            captured.coverage,
            captured.tools.substeps,
        )
    )
    if isinstance(observations, Err):
        return observations
    scoped = dict(observations.value)
    if (
        len(scoped) != len(observations.value)
        or len({number for number, _failures in attribution.scoped})
        != len(attribution.scoped)
        or frozenset(scoped)
        != frozenset(number for number, _failures in attribution.scoped)
    ):
        return Err("coverage attribution phase scopes differ")
    attribution = _coverage_localized_shared(captured, entries, attribution, scoped)
    return Ok(
        ToolFailureAttribution(
            attribution.shared,
            tuple(
                (number, failures | scoped[number])
                for number, failures in attribution.scoped
            ),
        )
    )


def phase_host_attribution(
    captured: ProvisionalCapture,
    declarations: tuple[Phase, ...],
    attribution: ToolFailureAttribution,
) -> Result[ToolFailureAttribution, str]:
    """Add current native host eligibility without claiming cross-lane receipts."""
    if captured.family is None and captured.tools.host is None:
        return Ok(attribution)
    host = captured.tools.host
    if (
        captured.family is None
        or host is None
        or isinstance(host, Err)
        or host.value.family != captured.family
    ):
        return Err("phase native host observation unavailable or inconsistent")
    numbers = tuple(phase.number for phase in declarations)
    if (
        len(set(numbers)) != len(numbers)
        or tuple(number for number, _failures in attribution.scoped) != numbers
    ):
        return Err("phase native host scopes differ")
    parsed = tuple(
        lanes.parse_phase_lane(field(phase.text, "Host lane")) for phase in declarations
    )
    if any(isinstance(value, Err) for value in parsed):
        return Err("invalid phase native host lane")
    return Ok(
        ToolFailureAttribution(
            attribution.shared,
            tuple(
                (
                    phase.number,
                    failures
                    | (
                        frozenset({"native host lane unmet: " + lane.value})
                        if isinstance(lane, Ok)
                        and not lanes.phase_lane_host(lane.value, host.value)
                        else frozenset[str]()
                    ),
                )
                for phase, (_number, failures), lane in zip(
                    declarations, attribution.scoped, parsed, strict=True
                )
            ),
        )
    )


def _passed_phase_checks(
    phases: tuple[phase_reports.PhaseInputs, ...],
    manifest: evidence.RunEvidence,
    nonce: str,
) -> frozenset[str]:
    """Resolve each cited test against every collected case and teardown result."""
    observed = phase_reports.observe_collection(manifest, nonce)
    return frozenset(
        check
        for phase in phases
        for check in phase.checks
        if any(
            node == check or node.startswith(check + "[") for node in observed.collected
        )
        and all(
            node in observed.passed
            for node in observed.collected
            if node == check or node.startswith(check + "[")
        )
    )


def verify_phase_cited_checks(
    phases: tuple[phase_reports.PhaseInputs, ...],
    manifest: evidence.RunEvidence,
    nonce: str,
    observed: tuple[phase_reports.PhaseResult, ...],
) -> Result[None, str]:
    """Require each unpassed cited Python check in its original phase result."""
    numbers = tuple(phase.number for phase in phases)
    if (
        not nonce
        or manifest.nonce != nonce
        or not phases
        or len(set(numbers)) != len(numbers)
        or tuple(item.number for item in observed) != numbers
    ):
        return Err("phase cited check observations unavailable")
    passed = _passed_phase_checks(phases, manifest, nonce)
    return (
        Ok(None)
        if all(
            phase.checks - passed <= item.failures
            for phase, item in zip(phases, observed, strict=True)
        )
        else Err("phase cited check failures differ")
    )


def validation_diagnostics(
    problems: tuple[str, ...],
    completed: tuple[str, ...],
    statuses: tuple[tuple[str, int], ...],
) -> tuple[str, ...]:
    """Retain validator messages and failed integrity statuses without scoping them."""
    return (
        *problems,
        *completed,
        *(name + " failed" for name, code in statuses if code),
    )


def source_validation_attribution(
    entries: tuple[evidence.Entry, ...],
    phases: tuple[phase_reports.PhaseInputs, ...],
    issues: tuple[SourceIssue, ...],
) -> Result[ToolFailureAttribution, str]:
    """Scope observed source guard failures through the captured ownership census."""
    empty = tuple((phase.number, frozenset[str]()) for phase in phases)
    if not issues:
        return Ok(ToolFailureAttribution(frozenset(), empty))
    text = _census_text(entries, "src/agentctl/check/source_ownership.toml")
    if isinstance(text, Err):
        return text
    manifest = ownership.parse_manifest(text.value)
    if isinstance(manifest, Err):
        return manifest
    paths = tuple(entry.path for entry in entries)
    declared = tuple(
        (phase.number, phase.prerequisites) for phase in manifest.value.phases
    )
    expected = tuple((phase.number, phase.prerequisites) for phase in phases)
    if (
        declared != expected
        or len(set(paths)) != len(paths)
        or any(not issue.message for issue in issues)
    ):
        return Err("source validation ownership or observations differ")
    files = frozenset(entry.path for entry in entries if entry.kind == "file")
    owners = {
        artifact.path: artifact.consumers for artifact in manifest.value.artifacts
    }
    shared = frozenset(
        "unattributed validation: " + issue.message
        for issue in issues
        if issue.path not in files or issue.path not in owners
    )
    scoped = tuple(
        (
            phase.number,
            frozenset(
                "source validation: " + issue.message
                for issue in issues
                if issue.path in files
                and issue.path in owners
                and phase.number in owners[issue.path]
            ),
        )
        for phase in phases
    )
    return Ok(ToolFailureAttribution(shared, scoped))


def ruff_validation_attribution(
    captured: ProvisionalCapture,
    entries: tuple[evidence.Entry, ...],
    phases: tuple[phase_reports.PhaseInputs, ...],
) -> Result[ToolFailureAttribution, str]:
    """Join captured Ruff diagnostics without clearing its shared failure."""
    snapshot = captured.tools.ruff
    empty = tuple((phase.number, frozenset[str]()) for phase in phases)
    if snapshot is None:
        return (
            Err("Ruff observation unavailable")
            if captured.family is not None and "ruff-check" in captured.schedule
            else Ok(ToolFailureAttribution(frozenset(), empty))
        )
    if isinstance(snapshot, Err):
        return snapshot
    if isinstance(captured.tools.evidence, Err) or isinstance(
        captured.tools.substeps, Err
    ):
        return Err("Ruff tool status unavailable")
    observed = snapshot.value
    statuses = tuple(
        code
        for name, code in captured.tools.evidence.value.outcomes
        if name == "ruff-check"
    )
    substeps = tuple(
        codes
        for name, codes in captured.tools.substeps.value.outcomes
        if name == "ruff-check"
    )
    facts = parse_ruff_output(observed.root, observed.output)
    if (
        not captured.nonce
        or observed.nonce != captured.nonce
        or captured.tools.evidence.value.nonce != captured.nonce
        or captured.tools.substeps.value.nonce != captured.nonce
        or statuses != (observed.output.code,)
        or substeps != ((observed.output.code,),)
        or isinstance(facts, Err)
        or facts.value != observed.facts
    ):
        return Err("Ruff diagnostics differ from captured run")
    issues = tuple(
        SourceIssue(
            fact.path,
            f"ruff {fact.code}: {fact.path}:{fact.row}: {fact.message}",
        )
        for fact in facts.value
    )
    return source_validation_attribution(entries, phases, issues)


def ruff_format_validation_attribution(
    captured: ProvisionalCapture,
    entries: tuple[evidence.Entry, ...],
    phases: tuple[phase_reports.PhaseInputs, ...],
) -> Result[ToolFailureAttribution, str]:
    """Scope the actual formatter's JSON while retaining its shared failure."""
    snapshot = captured.tools.ruff_format
    if snapshot is None:
        if captured.family is not None and "ruff-format" in captured.schedule:
            return Err("Ruff format observation unavailable")
        return Ok(
            ToolFailureAttribution(
                frozenset(), tuple((phase.number, frozenset()) for phase in phases)
            )
        )
    if isinstance(snapshot, Err):
        return snapshot
    if isinstance(captured.tools.evidence, Err) or isinstance(
        captured.tools.substeps, Err
    ):
        return Err("Ruff format tool status unavailable")
    observed = snapshot.value
    statuses = tuple(
        code
        for name, code in captured.tools.evidence.value.outcomes
        if name == "ruff-format"
    )
    substeps = tuple(
        codes
        for name, codes in captured.tools.substeps.value.outcomes
        if name == "ruff-format"
    )
    facts = parse_ruff_output(observed.root, observed.output)
    if (
        not captured.nonce
        or captured.nonce != observed.nonce
        or captured.tools.evidence.value.nonce != captured.nonce
        or captured.tools.substeps.value.nonce != captured.nonce
        or (observed.output.code,) != statuses
        or ((observed.output.code,),) != substeps
        or isinstance(facts, Err)
        or observed.facts != facts.value
        or any(fact.code != "unformatted" for fact in observed.facts)
    ):
        return Err("Ruff format diagnostics differ from captured run")
    issues = tuple(
        SourceIssue(fact.path, f"ruff format: {fact.path}:{fact.row}: {fact.message}")
        for fact in facts.value
    )
    return source_validation_attribution(entries, phases, issues)


def ty_validation_attribution(
    captured: ProvisionalCapture,
    entries: tuple[evidence.Entry, ...],
    phases: tuple[phase_reports.PhaseInputs, ...],
) -> Result[ToolFailureAttribution, str]:
    """Scope original type diagnostics without clearing the shared tool failure."""
    snapshot = captured.tools.ty
    empty = tuple((phase.number, frozenset[str]()) for phase in phases)
    if snapshot is None:
        return (
            Err("ty observation unavailable")
            if captured.family is not None and "ty" in captured.schedule
            else Ok(ToolFailureAttribution(frozenset(), empty))
        )
    if isinstance(snapshot, Err):
        return snapshot
    if isinstance(captured.tools.evidence, Err) or isinstance(
        captured.tools.substeps, Err
    ):
        return Err("ty tool status unavailable")
    observed = snapshot.value
    statuses = tuple(
        code for name, code in captured.tools.evidence.value.outcomes if name == "ty"
    )
    substeps = tuple(
        codes for name, codes in captured.tools.substeps.value.outcomes if name == "ty"
    )
    facts = parse_ty_output(observed.root, observed.output)
    if observed.nonce != captured.nonce or (
        not captured.nonce
        or captured.tools.evidence.value.nonce != captured.nonce
        or captured.tools.substeps.value.nonce != captured.nonce
        or len(statuses) != 1
        or statuses[0] != observed.output.code
        or len(substeps) != 1
        or substeps[0] != (observed.output.code,)
        or isinstance(facts, Err)
        or tuple(facts.value) != tuple(observed.facts)
    ):
        return Err("ty diagnostics differ from captured run")
    issues = tuple(
        SourceIssue(
            fact.path, f"ty {fact.code}: {fact.path}:{fact.row}: {fact.message}"
        )
        for fact in facts.value
    )
    return source_validation_attribution(entries, phases, issues)


def _with_source_validation(
    captured: ProvisionalPhaseInputs, source: ToolFailureAttribution
) -> ProvisionalPhaseInputs:
    """Merge complete source scopes without erasing other observations."""
    source_by_phase = dict(source.scoped)
    return replace(
        captured,
        shared=captured.shared | source.shared,
        scoped_tools=tuple(
            (number, failures | source_by_phase[number])
            for number, failures in captured.scoped_tools
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
        _passed_phase_checks(phases, manifest, captured.nonce),
        captured.shared,
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
    joined = join_captured_phase_failures(
        phases, attributed, captured.native, captured.oracle
    )
    return (
        joined
        if isinstance(joined, Err)
        else Ok(
            tuple(
                replace(item, failures=item.failures | frozenset({"unverified-run"}))
                for item in joined.value
            )
        )
    )


def _source_provisional_observations(
    captured: ProvisionalPhaseInputs,
    source: ToolFailureAttribution,
    ruff: ToolFailureAttribution,
    ruff_format: ToolFailureAttribution,
    ty: ToolFailureAttribution,
) -> Result[tuple[phase_reports.PhaseResult, ...], str]:
    source_joined = _with_source_validation(captured, source)
    source_joined = _with_source_validation(source_joined, ruff_format)
    source_joined = _with_source_validation(source_joined, ty)
    return provisional_phase_observations(_with_source_validation(source_joined, ruff))


def _source_guard_observations(
    census: Result[tuple[evidence.Entry, ...], str], live: tuple[SourceIssue, ...]
) -> tuple[SourceIssue, ...]:
    """Compare the live walk with guards run over the original captured bytes."""
    if isinstance(census, Err):
        return live
    observed = census_source_observations(census.value)
    if isinstance(observed, Err):
        return (SourceIssue(None, "validator source census: " + observed.error),)
    return (
        observed.value
        if observed.value == live
        else (
            SourceIssue(None, "validator source census differs from live source walk"),
        )
    )


def python_target_census(
    root: Path, targets_found: tuple[str, ...], entries: tuple[evidence.Entry, ...]
) -> Result[None, str]:
    """Require Python tool targets to equal the original complete source census."""
    paths = tuple(entry.path for entry in entries)
    roots = {
        entry.path: entry.kind for entry in entries if entry.path in {"src", "tests"}
    }
    if (
        not root.is_absolute()
        or len(paths) != len(set(paths))
        or roots != {"src": "directory", "tests": "directory"}
        or any(
            not path
            or PurePosixPath(path).as_posix() != path
            or PurePosixPath(path).is_absolute()
            or ".." in PurePosixPath(path).parts
            or "\\" in path
            for path in paths
        )
    ):
        return Err("invalid Python source census")
    expected = tuple(
        str(path)
        for directory in ("src", "tests")
        for path in sorted(
            root / entry.path
            for entry in entries
            if entry.path.startswith(directory + "/") and entry.path.endswith(".py")
        )
    )
    return (
        Ok(None)
        if expected and targets_found == expected
        else Err("Python tool targets differ from the source census")
    )


def _python_invocation_steps_match(
    leg: Leg, commands: tuple[tuple[str, ...], ...], codes: tuple[int, ...]
) -> bool:
    """Require exactly the command prefix the runner could have attempted."""
    scheduled = (leg.argv, *leg.after)
    return bool(commands) and (
        len(commands) == len(codes)
        and commands == scheduled[: len(commands)]
        and len(commands) <= len(scheduled)
        and not any(isinstance(code, bool) for code in codes)
        and not (len(codes) < len(scheduled) and all(code == 0 for code in codes))
        and not (1 < len(codes) < len(scheduled) and codes[-1] == 0)
        and not (len(codes) > 1 and codes[0] != 0 and not leg.after_failure)
        and not any(code != 0 for code in codes[1:-1])
    )


def python_invocation_observation(
    context: CheckRun,
    targets_found: tuple[str, ...],
    entries: tuple[evidence.Entry, ...],
    planned: tuple[Leg, ...],
    tools: ToolOutcome,
) -> Result[None, str]:
    """Join actual attempted Python commands to the guarded target census."""
    target_check = python_target_census(context.root, targets_found, entries)
    declarations = _coverage_declarations(entries, context.family)
    if isinstance(target_check, Err) or isinstance(declarations, Err):
        return Err("Python invocation census or configuration unavailable")
    expected = python_legs(
        sys.executable,
        context.root,
        targets_found,
        context.directory,
        declarations.value[1],
    )
    names = tuple(leg.name for leg in expected)
    if (
        tuple(leg for leg in planned if leg.name in names) != expected
        or isinstance(tools.substeps, Err)
        or isinstance(tools.evidence, Err)
    ):
        return Err("Python invocation plan or subprocess statuses differ")
    recorded = tuple(item for item in tools.commands if item[0] in names)
    substeps = tools.substeps.value
    python_steps = tuple(item for item in substeps.outcomes if item[0] in names)
    outcomes = tuple(
        (name, code) for name, code in tools.evidence.value.outcomes if name in names
    )
    if (
        not context.nonce
        or substeps.nonce != context.nonce
        or tools.evidence.value.nonce != context.nonce
        or tuple(name for name, _ in recorded) != names
        or tuple(name for name, _ in python_steps) != names
        or tuple(name for name, _ in outcomes) != names
        or any(
            not _python_invocation_steps_match(leg, commands, codes)
            or code != next((item for item in codes if item != 0), 0)
            for leg, (_name, commands), (_step, codes), (_outcome, code) in zip(
                expected, recorded, python_steps, outcomes, strict=True
            )
        )
    ):
        return Err("Python commands differ from captured subprocess execution")
    return Ok(None)


def report_python_invocations(
    context: CheckRun,
    targets_found: tuple[str, ...],
    census: Result[tuple[evidence.Entry, ...], str],
    planned: tuple[Leg, ...],
    tools: ToolOutcome,
) -> Result[None, str]:
    """Report an unavailable or mismatched invocation join without stopping tools."""
    observed = (
        python_invocation_observation(
            context, targets_found, census.value, planned, tools
        )
        if isinstance(census, Ok)
        else Err("Python invocation source census unavailable")
    )
    if isinstance(observed, Err):
        click.echo("python-invocation-observation: " + observed.error, err=True)
    return observed


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
    observed_phases, target_census = (
        census_phases(root, census.value)
        if isinstance(census, Ok)
        else Err("source census unavailable"),
        python_target_census(root, found.value, census.value)
        if isinstance(census, Ok)
        else Err("source census unavailable"),
    )
    report_scoped_source_inputs(census, observed_phases)
    source_issues, problems = (
        source_observations(root),
        (
            *(("validators: " + census.error,) if isinstance(census, Err) else ()),
            *(
                ("validators: Python targets: " + target_census.error,)
                if isinstance(target_census, Err)
                else ()
            ),
            *(
                source_ownership_problems(census.value)
                if not isinstance(census, Err)
                else ()
            ),
            *docs(root),
            *plan(root),
            *(
                test_consumer_problems(root, census.value)
                if isinstance(census, Ok)
                else ()
            ),
            *(
                coverage_host_problems(root, census.value)
                if isinstance(census, Ok)
                else ()
            ),
            *(
                ("validators: phase census: " + observed_phases.error,)
                if isinstance(observed_phases, Err)
                else ()
            ),
            *forbidden_surfaces(root),
            *configuration(root),
        ),
    )
    records, captured_source_issues = (
        census_corpus(census.value) if isinstance(census, Ok) else corpus(root),
        _source_guard_observations(census, source_issues),
    )
    oracle_code, oracle_before, details_before = (
        oracle_check(root, run_dir, nonce),
        oracle_observation(run_dir, nonce),
        evidence.read_oracle_details(run_dir / "oracle-details.json", nonce),
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
                provisional_or_scoped_mutant_owners(census.value, records.value)
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
    if problems or captured_source_issues or completed:
        click.echo(
            "\n".join(
                (
                    *problems,
                    *(issue.message for issue in captured_source_issues),
                    *completed,
                )
            ),
            err=True,
        )
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
    coverage, invocations, python_commands = (
        _capture_tool_coverage(
            context,
            census,
            tuple(leg for leg in planned if isinstance(leg, Leg)),
            tools.substeps,
        ),
        report_python_invocations(
            context,
            found.value,
            census,
            tuple(leg for leg in planned if isinstance(leg, Leg)),
            tools,
        ),
        _capture_python_commands(context, census, tools.commands),
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
    oracle_integrity, details_integrity = (
        oracle_outcomes_unchanged(run_dir, nonce, oracle_before),
        oracle_details_unchanged(run_dir, nonce, details_before),
    )
    tools_integrity, substeps_integrity, pytest_manifest_integrity = (
        tool_outcomes_unchanged(run_dir, nonce, tools.evidence),
        tool_substeps_unchanged(run_dir, nonce, tools.substeps),
        pytest_manifest_unchanged(run_dir, nonce, tools.pytest),
    )
    (
        native_integrity_status,
        host_integrity,
        coverage_integrity,
        ruff_integrity,
        commands_integrity,
        format_integrity,
        ty_integrity,
        coverage_text_status,
    ) = (
        native_snapshot_unchanged(run_dir, nonce, tools.native),
        host_observation_unchanged(run_dir, nonce, tools.host),
        coverage_snapshot_unchanged(run_dir, nonce, coverage),
        ruff_snapshot_unchanged(run_dir, nonce, tools.ruff),
        python_commands_unchanged(run_dir, nonce, root, python_commands),
        ruff_snapshot_unchanged(
            run_dir, nonce, tools.ruff_format, filename="ruff-format-observation.json"
        ),
        ty_snapshot_unchanged(run_dir, nonce, tools.ty),
        coverage_text_integrity(
            context,
            census,
            tuple(leg for leg in planned if isinstance(leg, Leg)),
            tools,
            coverage,
        ),
    )
    localized_native, native_integrity = native_integrity_attribution(
        native_integrity_status, tools, run_dir, nonce
    )
    return ValidationOutcome(
        int(
            bool(
                problems
                or captured_source_issues
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
                or native_integrity_status
                or host_integrity
                or coverage_integrity
                or ruff_integrity
                or commands_integrity
                or format_integrity
                or ty_integrity
                or coverage_text_status
                or isinstance(invocations, Err)
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
                frozenset(
                    leg.name
                    for leg in planned
                    if isinstance(leg, Leg) and leg.after_failure
                ),
                coverage,
                family,
                validation_diagnostics(
                    problems,
                    completed,
                    (
                        ("mutant killer match", killer_match),
                        ("mutant killer integrity", killer_integrity),
                        ("oracle outcomes", oracle_integrity),
                        ("initial oracle details", details_initial_integrity),
                        ("oracle details", details_integrity),
                        ("tool outcomes", tools_integrity),
                        ("tool substeps", substeps_integrity),
                        ("pytest manifest", pytest_manifest_integrity),
                        ("native observation", native_integrity),
                        ("host observation", host_integrity),
                        ("coverage observation", coverage_integrity),
                        ("ruff observation", ruff_integrity),
                        ("python commands", commands_integrity),
                        ("ruff format observation", format_integrity),
                        ("ty observation", ty_integrity),
                        ("coverage text observation", coverage_text_status),
                    ),
                )
                + (
                    ("Python invocations: " + invocations.error,)
                    if isinstance(invocations, Err)
                    else ()
                ),
                captured_source_issues,
                context,
                next(
                    (
                        leg
                        for leg in planned
                        if isinstance(leg, Leg) and leg.name == "pytest"
                    ),
                    None,
                ),
                scoped_mutants=(
                    isinstance(census, Ok)
                    and isinstance(records, Ok)
                    and isinstance(provisional, Ok)
                    and isinstance(
                        provisional_mutant_owners(census.value, records.value), Err
                    )
                ),
            )
        ),
        Err("mutant killer observation failed")
        if killer_match or killer_integrity
        else tools.killers,
        coverage,
        tools.ruff,
        python_commands,
        tools.ruff_format,
        tools.ty,
        tools.coverage_text
        if not coverage_text_status
        else Err("coverage text integrity failed"),
        int(
            any(
                (
                    killer_match,
                    killer_integrity,
                    oracle_integrity,
                    details_initial_integrity,
                    details_integrity,
                    tools_integrity,
                    substeps_integrity,
                    pytest_manifest_integrity,
                    native_integrity,
                    host_integrity,
                    coverage_integrity,
                    ruff_integrity,
                    commands_integrity,
                    format_integrity,
                    ty_integrity,
                    coverage_text_status,
                )
            )
            or isinstance(invocations, Err)
            or isinstance(diagnostic, Err)
        ),
        tools.native_absence if localized_native else None,
        details_initial_integrity,
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


def _collection_integrity_attribution(
    entries: tuple[evidence.Entry, ...],
    declarations: tuple[Phase, ...],
    claims: tuple[tuple[str, int], ...] | CollectionClaims | None,
) -> tuple[tuple[int, frozenset[str]], ...]:
    """Attribute static rows only when captured policy permits a complete audit."""
    if not isinstance(claims, CollectionClaims) or claims.owners is None:
        return ()
    policy = census_policy(entries, claims.owners)
    if isinstance(policy, Err):
        return ()
    attributed = closure.scoped_integrity_failures(
        declarations, claims.records, policy.value
    )
    return () if isinstance(attributed, Err) else attributed.value.phases


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
    undeclared = (
        closure.undeclared_mutant_failures(declarations, claims.records, mutant_owners)
        if isinstance(claims, CollectionClaims)
        else Ok(tuple((number, frozenset[str]()) for number, _ in checked.value))
    )
    undeclared_by_phase = {} if isinstance(undeclared, Err) else dict(undeclared.value)
    integrity_by_phase = dict(
        _collection_integrity_attribution(entries, declarations, claims)
    )
    known = frozenset(artifact.path for artifact in manifest.value.artifacts)
    observed_sources = frozenset(
        entry.path for entry in entries if entry.kind in {"file", "symlink"}
    )
    collected = frozenset(node.split("::", 1)[0] for node in observed.collected)
    unowned = (collected | observation.failed_modules) - (known & observed_sources)
    shared = frozenset("unowned collector: " + path for path in unowned)
    return (
        undeclared
        if isinstance(undeclared, Err)
        else Ok(
            tuple(
                (
                    number,
                    failures
                    | shared
                    | undeclared_by_phase[number]
                    | integrity_by_phase.get(number, frozenset[str]())
                    | frozenset(
                        issue for owner, issue in scopes.value[1] if owner == number
                    ),
                )
                for number, failures in checked.value
            )
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


def unavailable_native_scopes(
    entries: tuple[evidence.Entry, ...],
    declarations: tuple[Phase, ...],
    records: tuple[Mutant, ...],
    owners: tuple[tuple[str, int], ...],
) -> Result[tuple[tuple[int, frozenset[str]], ...], str]:
    """Conservatively scope absent native evidence from captured declarations.

    These diagnostics cannot authenticate the absence or establish a verdict.
    """
    text = _census_text(entries, "src/agentctl/check/source_ownership.toml")
    if isinstance(text, Err):
        return text
    manifest = ownership.parse_manifest(text.value)
    if isinstance(manifest, Err):
        return manifest
    numbers = tuple(phase.number for phase in declarations)
    mapping = dict(owners)
    identifiers = tuple(record.identifier for record in records)
    paths = tuple(entry.path for entry in entries)
    artifacts = {artifact.path: artifact for artifact in manifest.value.artifacts}
    native = tuple(
        artifact
        for artifact in manifest.value.artifacts
        if artifact.path.startswith("src/agentctl/haskell/")
    )
    if (
        not numbers
        or tuple(phase.number for phase in manifest.value.phases) != numbers
        or len(set(numbers)) != len(numbers)
        or any(isinstance(number, bool) for number in numbers)
        or len(set(paths)) != len(paths)
        or not native
        or len(mapping) != len(owners)
        or any(
            isinstance(number, bool) or number not in numbers for _, number in owners
        )
        or len(set(identifiers)) != len(identifiers)
        or frozenset(mapping) != frozenset(identifiers)
        or any(
            record.target not in artifacts
            or artifacts[record.target].owner != mapping[record.identifier]
            for record in records
        )
        or any(
            entry.path not in artifacts
            for entry in entries
            if entry.path.startswith("src/agentctl/haskell/")
        )
    ):
        return Err("native absence ownership is incomplete or ambiguous")
    cited = frozenset(
        phase.number
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
    consumers = (
        frozenset(number for artifact in native for number in artifact.consumers)
        | cited
        | frozenset(
            mapping[record.identifier]
            for record in records
            if any(node.startswith("haskell:") for node in record.killers)
        )
    )
    return Ok(
        tuple(
            (
                number,
                frozenset({"native observation unavailable"})
                if number in consumers
                else frozenset[str](),
            )
            for number in numbers
        )
    )


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
    native: NativeSnapshot | None,
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
        or not captured.after_failure <= frozenset(name for name, _ in expected)
    ):
        return Err("captured tool substep schedule mismatch")
    statuses = dict(outcomes.outcomes)
    if any(
        not codes
        or len(codes) > limit
        or (len(codes) < limit and all(code == 0 for code in codes))
        or (1 < len(codes) < limit and codes[-1] == 0)
        or (len(codes) > 1 and codes[0] != 0 and name not in captured.after_failure)
        or any(code != 0 for code in codes[1:-1])
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
    if (
        len(native_status) != 1
        or (native is None and native_status[0] == 0)
        or (
            native is not None
            and (native_status[0] != 0)
            != ("native-command-failed" in native.manifest.forbidden)
        )
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


def provisional_identity_tool_failures(
    entries: tuple[evidence.Entry, ...],
    phases: tuple[phase_reports.PhaseInputs, ...],
    attribution: ToolFailureAttribution,
) -> Result[ToolFailureAttribution, str]:
    """Scope a failed binary identity check to its captured bootstrap consumers."""
    if IDENTITY_FAILURE not in attribution.shared:
        return Ok(attribution)
    text = _census_text(entries, "src/agentctl/check/source_ownership.toml")
    if isinstance(text, Err):
        return text
    manifest = ownership.parse_manifest(text.value)
    if isinstance(manifest, Err):
        return manifest
    declared = tuple(
        (phase.number, phase.prerequisites) for phase in manifest.value.phases
    )
    expected = tuple((phase.number, phase.prerequisites) for phase in phases)
    artifacts = tuple(
        item for item in manifest.value.artifacts if item.path in IDENTITY_SOURCES
    )
    sources = tuple(item for item in entries if item.path in IDENTITY_SOURCES)
    if (
        declared != expected
        or tuple(number for number, _failures in attribution.scoped)
        != tuple(phase.number for phase in phases)
        or frozenset(item.path for item in artifacts) != IDENTITY_SOURCES
        or len(artifacts) != len(IDENTITY_SOURCES)
        or any(item.owner != IDENTITY_OWNER or not item.required for item in artifacts)
        or frozenset(item.path for item in sources) != IDENTITY_SOURCES
        or len(sources) != len(IDENTITY_SOURCES)
        or any(item.kind != "file" for item in sources)
    ):
        return Err("binary identity ownership is unavailable or inconsistent")
    consumers = frozenset(number for item in artifacts for number in item.consumers)
    return Ok(
        ToolFailureAttribution(
            attribution.shared - {IDENTITY_FAILURE},
            tuple(
                (
                    number,
                    failures
                    | (
                        frozenset({"binary-identity failed"})
                        if number in consumers
                        else frozenset[str]()
                    ),
                )
                for number, failures in attribution.scoped
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
    identity = (
        attribution
        if isinstance(attribution, Err)
        else provisional_identity_tool_failures(
            entries, work.value.work.phases, attribution.value
        )
    )
    return identity if isinstance(identity, Err) else Ok((work.value, identity.value))


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


def _scoped_capture_mapping(
    captured: ProvisionalCapture,
    records: tuple[Mutant, ...],
) -> Result[ownership.ScopedMutantMapping, str]:
    """Retain unobserved native claims when their command failed."""
    native = captured.tools.native
    if isinstance(captured.census, Err) or captured.claims is None:
        return Err("scoped mutant observations unavailable")
    if isinstance(native, Ok):
        if (
            native.value.entries != captured.census.value
            or native.value.manifest.nonce != captured.nonce
        ):
            return Err("scoped mutant observations unavailable")
        mapping = observed_scoped_mutant_mapping(
            captured.census.value, records, native.value.sources
        )
    else:
        missing = _gate_native_manifest(captured)
        if isinstance(missing, Err) or missing.value is not None:
            return Err("scoped mutant observations unavailable")
        mapping = scoped_mutant_mapping(captured.census.value, records, ())
    return mapping


def scoped_mutant_collection(
    collection: Result[tuple[tuple[int, frozenset[str]], ...], str],
    captured: ProvisionalCapture,
    records: tuple[Mutant, ...],
) -> Result[tuple[tuple[int, frozenset[str]], ...], str]:
    """Join every provisional ownership failure before using scoped owners."""
    if isinstance(collection, Err) or not captured.scoped_mutants:
        return collection
    mapping = _scoped_capture_mapping(captured, records)
    if isinstance(mapping, Err) or captured.claims is None:
        return (
            mapping
            if isinstance(mapping, Err)
            else Err("scoped mutant claims unavailable")
        )
    scopes = mapping.value.scopes
    if mapping.value.owners != captured.claims[1] or tuple(
        scope.number for scope in scopes
    ) != tuple(number for number, _ in collection.value):
        return Err("scoped mutant ownership differs")
    failures = {
        scope.number: frozenset(
            "mutant ownership: " + issue for issue in scope.failures
        )
        | frozenset(
            "mutant ownership: native killer source unobserved: " + record.identifier
            for record in records
            if not isinstance(captured.tools.native, Ok)
            and dict(mapping.value.owners)[record.identifier] == scope.number
            and any(node.startswith("haskell:") for node in record.killers)
        )
        for scope in scopes
    }
    return Ok(
        tuple(
            (number, observed | failures[number])
            for number, observed in collection.value
        )
    )


def _gate_native_manifest(
    captured: ProvisionalCapture,
) -> Result[evidence.RunEvidence | None, str]:
    """Allow a missing native record only alongside a captured failed command."""
    native = captured.tools.native
    if isinstance(native, Ok):
        return Ok(native.value.manifest)
    outcomes = captured.tools.evidence
    if (
        isinstance(outcomes, Err)
        or not captured.nonce
        or captured.nonce != outcomes.value.nonce
    ):
        return Err("gate execution native observation unavailable")
    statuses = tuple(
        code for name, code in outcomes.value.outcomes if name == "cabal-test"
    )
    if len(statuses) != 1 or isinstance(statuses[0], bool) or statuses[0] == 0:
        return Err("gate execution native observation unavailable")
    return Ok(None)


def gate_execution_collection(
    collection: Result[tuple[tuple[int, frozenset[str]], ...], str],
    captured: ProvisionalCapture,
    declarations: tuple[Phase, ...],
    records: tuple[Mutant, ...],
    python: evidence.RunEvidence,
) -> Result[tuple[tuple[int, frozenset[str]], ...], str]:
    """Join row execution classes from the original Python and native manifests."""
    if isinstance(collection, Err):
        return collection
    native = _gate_native_manifest(captured)
    if isinstance(native, Err):
        return native
    checked = scoped_mutant_collection(collection, captured, records)
    if isinstance(checked, Err):
        return checked
    other = native.value
    if (
        not captured.nonce
        or python.nonce != captured.nonce
        or (other is not None and other.nonce != captured.nonce)
        or (other is not None and bool(python.collected & other.collected))
        or tuple(number for number, _ in collection.value)
        != tuple(phase.number for phase in declarations)
    ):
        return Err("gate execution observations differ")
    combined = (
        python
        if other is None
        else evidence.RunEvidence(
            captured.nonce,
            python.collected | other.collected,
            python.executed | other.executed,
            python.passed | other.passed,
            (*python.forbidden, *other.forbidden),
            (*python.classes, *other.classes),
        )
    )
    row_failures = dict(closure.execution_scopes(declarations, records, combined))
    return Ok(
        tuple(
            (number, failures | row_failures[number])
            for number, failures in checked.value
        )
    )


def verify_phase_collection_failures(
    captured: ProvisionalCapture,
    declarations: tuple[Phase, ...],
    observed: tuple[phase_reports.PhaseResult, ...],
) -> Result[None, str]:
    """Require each provisional phase to retain its collection and killer failures."""
    if (
        isinstance(captured.census, Err)
        or captured.claims is None
        or captured.tools.pytest is None
        or isinstance(captured.tools.pytest, Err)
    ):
        return Err("phase collection inputs unavailable")
    records, owners = captured.claims
    pytest_run = captured.tools.pytest.value
    collection = collection_observations(
        captured.census.value,
        declarations,
        pytest_run,
        captured.nonce,
        CollectionClaims(owners, records),
    )
    combined = gate_execution_collection(
        collection_with_killer_failures(
            collection, captured, records, owners, pytest_run
        ),
        captured,
        declarations,
        records,
        pytest_run,
    )
    if isinstance(combined, Err):
        return combined
    by_phase = {item.number: item.failures for item in observed}
    verified = (
        Ok(None)
        if len(by_phase) == len(observed)
        and tuple(by_phase) == tuple(number for number, _ in combined.value)
        and all(failures <= by_phase[number] for number, failures in combined.value)
        else Err("phase collection or mutant failures differ")
    )
    return (
        verified
        if isinstance(verified, Err)
        else verify_phase_native_failures(captured, declarations, observed)
    )


def verify_phase_native_failures(
    captured: ProvisionalCapture,
    declarations: tuple[Phase, ...],
    observed: tuple[phase_reports.PhaseResult, ...],
) -> Result[None, str]:
    """Require phase results to retain failures from the sealed native cases."""
    native = captured.tools.native
    if isinstance(captured.census, Err) or captured.claims is None:
        return Err("phase native evidence unavailable or inconsistent")
    records, owners = captured.claims
    available = _gate_native_manifest(captured)
    if isinstance(available, Err):
        return available
    failures = (
        native_failure_observations(
            native.value, captured.nonce, declarations, records, owners
        )
        if isinstance(native, Ok) and native.value.entries == captured.census.value
        else unavailable_native_scopes(
            captured.census.value, declarations, records, owners
        )
        if available.value is None
        else Err("phase native evidence unavailable or inconsistent")
    )
    if isinstance(failures, Err):
        return failures
    by_phase = {item.number: item.failures for item in observed}
    return (
        Ok(None)
        if len(by_phase) == len(observed)
        and tuple(by_phase) == tuple(number for number, _ in failures.value)
        and all(required <= by_phase[number] for number, required in failures.value)
        else Err("phase native failures differ")
    )


def verify_phase_oracle_failures(
    scopes: tuple[ownership.OracleScope, ...],
    observed: tuple[phase_reports.PhaseResult, ...],
) -> Result[None, str]:
    """Require every phase to retain its independently attributed oracle failures."""
    by_phase = {item.number: item.failures for item in observed}
    return (
        Ok(None)
        if len(by_phase) == len(observed)
        and tuple(by_phase) == tuple(scope.number for scope in scopes)
        and all(frozenset(scope.failures) <= by_phase[scope.number] for scope in scopes)
        else Err("phase oracle failures differ")
    )


def verify_phase_host_failures(
    captured: ProvisionalCapture,
    declarations: tuple[Phase, ...],
    observed: tuple[phase_reports.PhaseResult, ...],
) -> Result[None, str]:
    """Require current host-lane failures to remain on their consuming phases."""
    empty = ToolFailureAttribution(
        frozenset(), tuple((phase.number, frozenset()) for phase in declarations)
    )
    scopes = phase_host_attribution(captured, declarations, empty)
    if isinstance(scopes, Err):
        return scopes
    by_phase = {item.number: item.failures for item in observed}
    return (
        Ok(None)
        if len(by_phase) == len(observed)
        and tuple(by_phase) == tuple(number for number, _ in scopes.value.scoped)
        and all(
            required <= by_phase[number] for number, required in scopes.value.scoped
        )
        else Err("phase host failures differ")
    )


def verify_phase_tool_failures(
    captured: ProvisionalCapture,
    declarations: tuple[Phase, ...],
    observed: tuple[phase_reports.PhaseResult, ...],
) -> Result[None, str]:
    """Require tool failures after a separate authenticated coverage recheck."""
    if (
        isinstance(captured.census, Err)
        or captured.tools.pytest is None
        or isinstance(captured.tools.pytest, Err)
    ):
        return Err("phase tool evidence unavailable")
    native = captured.tools.native
    if isinstance(native, Ok) and native.value.entries != captured.census.value:
        return Err("phase tool native census differs")
    failures = provisional_tool_failures(
        captured,
        captured.tools.pytest.value,
        native.value if isinstance(native, Ok) else None,
    )
    if isinstance(failures, Err):
        return failures
    work = provisional_work_and_tools(
        captured.census.value,
        declarations,
        failures.value - {"coverage report failed"},
        captured.readiness,
    )
    if isinstance(work, Err):
        return work
    attribution = work.value[1]
    by_phase = {item.number: item.failures for item in observed}
    return (
        Ok(None)
        if len(by_phase) == len(observed)
        and tuple(by_phase) == tuple(number for number, _ in attribution.scoped)
        and all(
            attribution.shared | required <= by_phase[number]
            for number, required in attribution.scoped
        )
        else Err("phase tool failures differ")
    )


def verify_phase_coverage_failures(
    inputs: CoverageAttributionInputs,
    observed: tuple[phase_reports.PhaseResult, ...],
) -> Result[None, str]:
    """Require every coverage gap to remain on all of its consuming phases."""
    scopes = coverage_phase_observations(inputs)
    if isinstance(scopes, Err):
        return scopes
    by_phase = {item.number: item.failures for item in observed}
    return (
        Ok(None)
        if len(by_phase) == len(observed)
        and tuple(by_phase) == tuple(number for number, _ in scopes.value)
        and all(required <= by_phase[number] for number, required in scopes.value)
        else Err("phase coverage failures differ")
    )


def verify_phase_source_failures(
    entries: tuple[evidence.Entry, ...],
    declarations: tuple[Phase, ...],
    observed: tuple[phase_reports.PhaseResult, ...],
) -> Result[None, str]:
    """Require census-derived source and missing-input failures on consumers."""
    work = scoped_source_inputs(entries, declarations)
    issues = census_source_observations(entries)
    if isinstance(work, Err) or isinstance(issues, Err):
        return Err("phase source observations unavailable")
    scopes = source_validation_attribution(
        entries, work.value.work.phases, issues.value
    )
    if isinstance(scopes, Err):
        return scopes
    missing = dict(work.value.missing)
    available = frozenset(path for path, _contents in work.value.work.sources)
    missing_inputs = {
        phase.number: frozenset(
            "missing-input:" + path for path in phase.inputs - available
        )
        for phase in work.value.work.phases
    }
    by_phase = {item.number: item.failures for item in observed}
    return (
        Ok(None)
        if len(by_phase) == len(observed)
        and tuple(by_phase) == tuple(number for number, _ in scopes.value.scoped)
        and set(missing) == set(by_phase)
        and all(
            scopes.value.shared | required | missing[number] <= by_phase[number]
            for number, required in scopes.value.scoped
        )
        and all(missing_inputs[number] <= by_phase[number] for number in missing_inputs)
        else Err("phase source failures differ")
    )


def verify_phase_prerequisite_failures(
    phases: tuple[phase_reports.PhaseInputs, ...],
    observed: tuple[phase_reports.PhaseResult, ...],
) -> Result[None, str]:
    """Check prerequisite propagation without promoting provisional markers."""
    numbers = tuple(phase.number for phase in phases)
    if (
        not phases
        or numbers != tuple(sorted(set(numbers)))
        or tuple(item.number for item in observed) != numbers
        or any(
            prerequisite not in numbers or prerequisite >= phase.number
            for phase in phases
            for prerequisite in phase.prerequisites
        )
    ):
        return Err("invalid prerequisite observations")
    by_phase = {item.number: item for item in observed}
    for phase, item in zip(phases, observed, strict=True):
        expected = frozenset(
            "prerequisite:" + str(number)
            for number in phase.prerequisites
            if any(
                failure != "unverified-run"
                and not failure.startswith("shared finalizer failed: ")
                for failure in by_phase[number].failures
            )
        )
        actual = frozenset(
            failure for failure in item.failures if failure.startswith("prerequisite:")
        )
        if actual != expected:
            return Err("phase prerequisite failures differ")
    return Ok(None)


def verify_phase_validation_failures(
    problems: tuple[str, ...], observed: tuple[phase_reports.PhaseResult, ...]
) -> Result[None, str]:
    """Require shared validator findings to remain visible on every phase."""
    if not observed or any(not problem for problem in problems):
        return Err("invalid phase validation observations")
    required = frozenset("unattributed validation: " + problem for problem in problems)
    return (
        Ok(None)
        if all(required.issubset(item.failures) for item in observed)
        else Err("phase validation failures differ")
    )


def verify_static_phase_failures(
    inputs: ParentStaticInputs,
    tool: str,
    record: bytes,
    observed: tuple[phase_reports.PhaseResult, ...],
) -> Result[None, str]:
    """Require sealed static findings and their tool failure to remain visible."""
    try:
        value: object = json.loads(record, object_pairs_hook=_ruff_record_fields)
    except (ValueError, UnicodeError, RecursionError):
        return Err("static diagnostic record is invalid")
    match value:
        case {
            "code": int() as code,
            "stdout": str() as stdout,
            "stderr": str() as stderr,
        }:
            output = Output(code, stdout, stderr)
        case _:
            return Err("static diagnostic fields are invalid")
    statuses = tuple(code for name, code in inputs.outcomes.outcomes if name == tool)
    substeps = tuple(codes for name, codes in inputs.substeps.outcomes if name == tool)
    if (
        tool not in {"ruff-check", "ruff-format", "ty"}
        or inputs.outcomes.nonce != inputs.context.nonce
        or inputs.substeps.nonce != inputs.context.nonce
        or statuses != (output.code,)
        or substeps != ((output.code,),)
    ):
        return Err("static diagnostic status differs from the tool results")
    is_type_checker = tool == "ty"
    facts = (
        parse_ty_output(inputs.context.root, output)
        if is_type_checker
        else parse_ruff_output(inputs.context.root, output)
    )
    if isinstance(facts, Err) or (
        tool == "ruff-format"
        and any(item.code != "unformatted" for item in facts.value)
    ):
        return Err("static diagnostic output is invalid")
    issues = tuple(
        SourceIssue(
            fact.path,
            f"ruff format: {fact.path}:{fact.row}: {fact.message}"
            if tool == "ruff-format"
            else f"{('ruff' if tool == 'ruff-check' else 'ty')} {fact.code}: "
            f"{fact.path}:{fact.row}: {fact.message}",
        )
        for fact in facts.value
    )
    scoped = source_validation_attribution(inputs.entries, inputs.phases, issues)
    if isinstance(scoped, Err):
        return scoped
    shared = scoped.value.shared | (
        frozenset({"unattributed tool failure: " + tool})
        if output.code
        else frozenset()
    )
    by_phase = {item.number: item.failures for item in observed}
    return (
        Ok(None)
        if len(by_phase) == len(observed)
        and tuple(by_phase) == tuple(number for number, _ in scoped.value.scoped)
        and all(
            shared | failures <= by_phase[number]
            for number, failures in scoped.value.scoped
        )
        else Err("phase static diagnostic failures differ")
    )


def captured_phase_observations(
    captured: ProvisionalCapture,
) -> Result[tuple[phase_reports.PhaseResult, ...], str]:
    """Scope proven missing sources before joining provisional observations."""
    return _captured_phase_observations_with_declarations(
        replace(
            captured,
            validation=scoped_ownership_validation(
                captured.validation, captured.census, captured.phases
            ),
        )
    )


def _captured_phase_observations_with_declarations(
    prepared: ProvisionalCapture,
) -> Result[tuple[phase_reports.PhaseResult, ...], str]:
    """Scope only proven declaration omissions before joining observations."""
    return _captured_phase_observations(
        replace(
            prepared,
            validation=scoped_mutant_declaration_validation(
                prepared.validation, prepared.census, prepared.phases, prepared.claims
            ),
        )
    )


def _captured_phase_observations(
    captured: ProvisionalCapture,
) -> Result[tuple[phase_reports.PhaseResult, ...], str]:
    """Join original gate observations without promoting them to a verdict."""
    match captured.census, captured.phases, captured.claims:
        case Ok(entries), Ok(declarations), (records, owners) if all(
            captured.validation
        ):
            pass
        case _:
            return Err(
                "source census, phase declarations or mutant ownership unavailable"
            )
    pytest_run, native_run = captured.tools.pytest, captured.tools.native
    if pytest_run is None or isinstance(pytest_run, Err):
        return Err("captured pytest observation unavailable")
    snapshot = native_run.value if isinstance(native_run, Ok) else None
    if snapshot is not None and snapshot.entries != entries:
        return Err("native observation uses a different source census")
    if snapshot is None and records:
        captured = replace(captured, scoped_mutants=True)
    tool_failures = provisional_tool_failures(captured, pytest_run.value, snapshot)
    if isinstance(tool_failures, Err):
        return tool_failures
    scoped = provisional_work_and_tools(
        entries, declarations, tool_failures.value, captured.readiness
    )
    if isinstance(scoped, Err):
        return scoped
    work, attribution = scoped.value
    augmented = _coverage_provisional_attribution(
        captured, entries, work.work.phases, attribution
    )
    host_scoped = (
        augmented
        if isinstance(augmented, Err)
        else phase_host_attribution(captured, declarations, augmented.value)
    )
    source_validation = source_validation_attribution(
        entries, work.work.phases, captured.source_issues
    )
    ruff_validation = ruff_validation_attribution(captured, entries, work.work.phases)
    format_validation = ruff_format_validation_attribution(
        captured, entries, work.work.phases
    )
    ty_validation = ty_validation_attribution(captured, entries, work.work.phases)
    collection = collection_observations(
        entries,
        declarations,
        pytest_run.value,
        captured.nonce,
        CollectionClaims(owners, records),
    )
    native = (
        native_failure_observations(
            snapshot, captured.nonce, declarations, records, owners
        )
        if snapshot is not None
        else unavailable_native_scopes(entries, declarations, records, owners)
    )
    return (
        host_scoped
        if isinstance(host_scoped, Err)
        else source_validation
        if isinstance(source_validation, Err)
        else ruff_validation
        if isinstance(ruff_validation, Err)
        else format_validation
        if isinstance(format_validation, Err)
        else ty_validation
        if isinstance(ty_validation, Err)
        else _source_provisional_observations(
            ProvisionalPhaseInputs(
                work,
                pytest_run.value,
                captured.nonce,
                gate_execution_collection(
                    collection_with_killer_failures(
                        collection, captured, records, owners, pytest_run.value
                    ),
                    captured,
                    declarations,
                    records,
                    pytest_run.value,
                ),
                native,
                captured.oracle,
                host_scoped.value.shared
                | frozenset(
                    "unattributed validation: " + item for item in captured.validation
                ),
                host_scoped.value.scoped,
            ),
            source_validation.value,
            ruff_validation.value,
            format_validation.value,
            ty_validation.value,
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
    *,
    localized_native: bool = False,
) -> Result[tuple[phase_reports.PhaseResult, ...], str] | None:
    """Retain shared finalizer damage without turning observations into verdicts."""
    if observations is None or isinstance(observations, Err):
        return observations
    if tuple(name for name, _code in statuses) != FINALIZER_NAMES or any(
        isinstance(code, bool) or code not in {0, 1} for _name, code in statuses
    ):
        return Err("incomplete or ambiguous finalizer observations")
    if localized_native and (
        dict(statuses)["native-observation"] != 1
        or not any(
            "native observation unavailable" in item.failures
            for item in observations.value
        )
    ):
        return Err("invalid localized native finalizer")
    failures = frozenset(
        "shared finalizer failed: " + name for name, code in statuses if code
    )
    if localized_native:
        failures = failures - {"shared finalizer failed: native-observation"}
    return Ok(
        tuple(
            phase_reports.PhaseResult(
                item.number,
                item.identity,
                item.failures
                | failures
                | (
                    frozenset({"native finalizer failed: native-observation"})
                    if localized_native
                    and "native observation unavailable" in item.failures
                    else frozenset()
                ),
            )
            for item in observations.value
        )
    )


def localizable_native_finalizer(
    validation: ValidationOutcome,
    directory: Path,
    nonce: str,
    statuses: tuple[tuple[str, int], ...],
) -> bool:
    """Allow localization only while all supporting run guards remain intact."""
    outcomes = validation.tools
    marker = validation.native_absence
    checked = dict(statuses)
    required = (
        "python-commands",
        "write-guard",
        "containment",
        "pytest-manifest",
        "mutant-killers",
        "tool-outcomes",
        "tool-substeps",
        "finalizer-record",
    )
    return (
        marker is not None
        and isinstance(outcomes, Ok)
        and isinstance(validation.phase_observations, Ok)
        and checked.get("native-observation") == 1
        and all(checked.get(name) == 0 for name in required)
        and verify_native_absence_handoff(directory, nonce, marker, outcomes.value)
        == Ok(None)
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
    except (ValueError, UnicodeError, RecursionError):
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


def verify_phase_finalizer_failures(
    finalizers: evidence.LegEvidence,
    observed: tuple[phase_reports.PhaseResult, ...],
) -> Result[None, str]:
    """Require every phase to retain each failed shared finalizer."""
    if (
        not finalizers.nonce
        or tuple(name for name, _ in finalizers.outcomes) != FINALIZER_NAMES[:-1]
        or any(
            isinstance(code, bool) or code not in {0, 1}
            for _, code in finalizers.outcomes
        )
        or not observed
        or len({item.number for item in observed}) != len(observed)
    ):
        return Err("invalid phase finalizer observations")
    required = frozenset(
        "shared finalizer failed: " + name for name, code in finalizers.outcomes if code
    )
    return (
        Ok(None)
        if all(required <= item.failures for item in observed)
        else Err("phase finalizer failures differ")
    )


def verify_provisional_finalizers(
    directory: Path, nonce: str, output: str
) -> Result[None, str]:
    """Recheck finalizer damage against sealed provisional observations."""
    final = verify_finalizer_handoff(directory, nonce, output)
    provisional = verify_provisional_handoff(directory, nonce, output)
    if isinstance(final, Err) or isinstance(provisional, Err):
        return Err("phase finalizer handoff unavailable")
    finalizers = finalizer_observation(directory, nonce)
    record = _read_provisional_handoff(directory / "provisional-phases.json")
    if isinstance(record, Err):
        return Err("phase finalizer record unavailable")
    observed = _decode_provisional_for_identity(nonce, record.value, output)
    if (
        isinstance(finalizers, Err)
        or isinstance(observed, Err)
        or finalizer_seal(finalizers.value) not in output.splitlines()
    ):
        return Err("phase finalizer observations unavailable or changed")
    shared = (
        Ok(None)
        if observed.value is None
        else verify_phase_finalizer_failures(finalizers.value, observed.value)
    )
    localized = (
        shared
        if (
            isinstance(shared, Ok)
            or observed.value is None
            or dict(finalizers.value.outcomes)["native-observation"] == 0
        )
        else _verify_localized_native_finalizers(
            directory, nonce, output, finalizers.value, observed.value
        )
    )
    return (
        shared if isinstance(localized, Err) and isinstance(shared, Err) else localized
    )


def _verify_localized_native_finalizers(
    directory: Path,
    nonce: str,
    output: str,
    finalizers: evidence.LegEvidence,
    observed: tuple[phase_reports.PhaseResult, ...],
) -> Result[None, str]:
    """Reproduce localized absence from guarded source and original observations."""
    family = hostfacts.current(Path.cwd()).family
    if family not in {"Linux", "Darwin", "Windows"}:
        return Err("native finalizer host unavailable")
    context = CheckRun(Path.cwd().resolve(), directory, nonce, family)
    captured = _parent_collection_capture(context, directory, output)
    if (
        isinstance(captured, Err)
        or dict(finalizers.outcomes)["native-observation"] != 1
    ):
        return Err("native finalizer localization unavailable")
    declarations, inputs = captured.value
    if isinstance(inputs.census, Err) or inputs.claims is None:
        return Err("native finalizer ownership unavailable")
    records, owners = inputs.claims
    checks = (
        verify_python_commands_handoff(directory, nonce, output, context.root),
        verify_pytest_handoff(directory, nonce, output),
        verify_killer_handoff(directory, nonce, output),
        collection_capture_sealed(inputs, output),
        verify_phase_native_failures(inputs, declarations, observed),
    )
    if any(isinstance(item, Err) for item in checks):
        return Err("native finalizer supporting evidence invalid")
    scopes = unavailable_native_scopes(
        inputs.census.value, declarations, records, owners
    )
    if isinstance(scopes, Err):
        return scopes
    affected = frozenset(number for number, failures in scopes.value if failures)
    adjusted = replace(
        finalizers,
        outcomes=tuple(
            (name, 0 if name == "native-observation" else code)
            for name, code in finalizers.outcomes
        ),
    )
    shared = verify_phase_finalizer_failures(adjusted, observed)
    label = "native finalizer failed: native-observation"
    return (
        Err("native finalizer scope invalid")
        if isinstance(shared, Err) or not affected
        else Ok(None)
        if all(
            (label in item.failures) == (item.number in affected) for item in observed
        )
        else Err("native finalizer scope differs")
    )


def verify_phase_input_identities(
    entries: tuple[evidence.Entry, ...],
    declarations: tuple[Phase, ...],
    observed: tuple[phase_reports.PhaseResult, ...],
) -> Result[None, str]:
    """Recalculate every provisional input identity from one captured census."""
    work = scoped_source_inputs(entries, declarations)
    if isinstance(work, Err):
        return work
    calculated = phase_reports.calculate_scoped_inputs(
        work.value.work.phases, work.value.work.sources, frozenset(), frozenset()
    )
    if isinstance(calculated, Err):
        return calculated
    expected = tuple((phase.number, phase.identity) for phase in calculated.value)
    actual = tuple((phase.number, phase.identity) for phase in observed)
    return Ok(None) if expected == actual else Err("phase input identities differ")


def _provisional_values_for_identity(
    context: CheckRun, directory: Path, output: str
) -> Result[tuple[phase_reports.PhaseResult, ...] | None, str]:
    """Read only sealed provisional values with a trustworthy source guard."""
    finalizers = sealed_finalizer_observation(directory, context.nonce, output)
    if isinstance(finalizers, Err):
        return finalizers
    statuses = dict(finalizers.value.outcomes)
    if any(
        statuses[name] for name in ("python-commands", "write-guard", "containment")
    ):
        return Ok(None)
    sealed = verify_provisional_handoff(directory, context.nonce, output)
    if isinstance(sealed, Err):
        return Err("phase input identity handoff unavailable")
    record = _read_provisional_handoff(directory / "provisional-phases.json")
    if isinstance(record, Err):
        return Err("phase input identity record unavailable")
    return _decode_provisional_for_identity(context.nonce, record.value, output)


def _decode_provisional_for_identity(
    nonce: str, record: bytes, output: str
) -> Result[tuple[phase_reports.PhaseResult, ...] | None, str]:
    """Decode the exact canonical bytes bound to the child's seal."""
    try:
        value: object = json.loads(record)
    except (UnicodeError, ValueError, RecursionError):
        return Err("phase input identity record unavailable")
    checked = parse_provisional_record(nonce, record)
    if (
        isinstance(checked, Err)
        or provisional_seal(nonce, record) not in output.splitlines()
    ):
        return Err("phase input identity record changed")
    if isinstance(value, dict) and value.get("status") == "unavailable":
        return Ok(None)
    if not isinstance(value, dict) or not isinstance(value.get("phases"), list):
        return Err("phase input identity record is invalid")
    return _parse_provisional_phases(value["phases"])


def _parent_bound_census(
    context: CheckRun, directory: Path, output: str
) -> Result[tuple[evidence.Entry, ...], str]:
    """Bind this exact parent census to the captured command record."""
    commands = _python_commands_handoff_record(directory, context.nonce, context.root)
    census = ownership.guarded_census(context.root)
    if (
        isinstance(commands, Err)
        or isinstance(census, Err)
        or python_commands_seal(context.nonce, commands.value)
        not in output.splitlines()
    ):
        return Err("phase input census unavailable")
    try:
        command_value: object = json.loads(commands.value)
    except (UnicodeError, ValueError, RecursionError):
        return Err("phase input command record unavailable")
    digest = evidence.digest_census(census.value)
    if (
        isinstance(digest, Err)
        or not isinstance(command_value, dict)
        or command_value.get("source_digest") != digest.value
    ):
        return Err("phase input census differs from captured commands")
    return census


def _verify_provisional_census(
    context: CheckRun,
    directory: Path,
    observed: tuple[phase_reports.PhaseResult, ...],
    output: str,
) -> Result[None, str]:
    """Bind the fresh census to the original command record and phase inputs."""
    census = _parent_bound_census(context, directory, output)
    if isinstance(census, Err):
        return census
    declarations = census_phases(context.root, census.value)
    return (
        declarations
        if isinstance(declarations, Err)
        else verify_phase_input_identities(census.value, declarations.value, observed)
    )


def verify_provisional_input_identities(
    context: CheckRun, directory: Path, output: str
) -> Result[None, str]:
    """Rejoin sealed provisional input identities to the parent's guarded census."""
    observed = _provisional_values_for_identity(context, directory, output)
    return (
        observed
        if isinstance(observed, Err)
        else Ok(None)
        if observed.value is None
        else _verify_provisional_census(context, directory, observed.value, output)
    )


def _parent_missing_native_capture(
    context: CheckRun,
    directory: Path,
    output: str,
    captured: ProvisionalCapture,
    records: tuple[Mutant, ...],
) -> Result[tuple[tuple[Phase, ...], ProvisionalCapture], str]:
    """Rebuild an unavailable native leg only from sealed failed tool evidence."""
    finalizers = sealed_finalizer_observation(directory, context.nonce, output)
    tools = _read_sealed_tool_results(directory, context.nonce)
    if (
        isinstance(captured.census, Err)
        or isinstance(captured.phases, Err)
        or isinstance(finalizers, Err)
        or isinstance(tools, Err)
    ):
        return Err("missing native parent evidence unavailable")
    statuses = dict(finalizers.value.outcomes)
    if (
        not statuses["native-observation"]
        or any(
            statuses[name]
            for name in (
                "python-commands",
                "write-guard",
                "containment",
                "pytest-manifest",
                "mutant-killers",
                "tool-outcomes",
                "tool-substeps",
            )
        )
        or isinstance(
            verify_tool_results_handoff(directory, context.nonce, output), Err
        )
    ):
        return Err("missing native parent guards unavailable")
    absence = verify_native_absence_handoff(
        directory, context.nonce, output, tools.value[0]
    )
    if isinstance(absence, Err):
        return absence
    mapping = scoped_mutant_mapping(captured.census.value, records, ())
    if isinstance(mapping, Err):
        return mapping
    outcomes, substeps = tools.value
    restored = replace(
        captured,
        claims=(records, mapping.value.owners),
        tools=replace(captured.tools, evidence=Ok(outcomes), substeps=Ok(substeps)),
        scoped_mutants=True,
    )
    if _gate_native_manifest(restored) != Ok(None):
        return Err("missing native command was not a captured failure")
    return Ok((captured.phases.value, restored))


def _parent_collection_capture(
    context: CheckRun, directory: Path, output: str
) -> Result[tuple[tuple[Phase, ...], ProvisionalCapture], str]:
    """Recover collection inputs from retained records and a guarded census."""
    census = _parent_bound_census(context, directory, output)
    if isinstance(census, Err):
        return Err("phase collection census unavailable")
    declarations = census_phases(context.root, census.value)
    records = census_corpus(census.value)
    native = native_snapshot(directory, context.nonce, census.value)
    pytest_run = pytest_observation(directory, context.nonce)
    killers = mutant_report.read(directory / "mutant-killers.json", context.nonce)
    if isinstance(native, Err):
        if (
            isinstance(declarations, Err)
            or isinstance(records, Err)
            or isinstance(pytest_run, Err)
            or isinstance(killers, Err)
        ):
            return Err("phase collection evidence unavailable")
        partial = ProvisionalCapture(
            census,
            declarations,
            ToolOutcome(
                1,
                Err("not used"),
                Err("not used"),
                pytest=pytest_run,
                native=native,
                killers=killers,
            ),
            None,
            Err("not used"),
            context.nonce,
            (),
            (),
        )
        return _parent_missing_native_capture(
            context, directory, output, partial, records.value
        )
    match declarations, records, native, pytest_run, killers:
        case Ok(declared), Ok(corpus_records), Ok(native_run), Ok(pytest), Ok(report):
            pass
        case _:
            return Err("phase collection evidence unavailable")
    owners = complete_mutant_owners(census.value, corpus_records)
    if isinstance(owners, Err):
        owners = observed_native_mutant_owners(
            census.value, corpus_records, native_run.sources
        )
    scoped = (
        observed_scoped_mutant_mapping(census.value, corpus_records, native_run.sources)
        if isinstance(owners, Err)
        else None
    )
    if isinstance(scoped, Ok):
        owners = Ok(scoped.value.owners)
    if isinstance(owners, Err):
        return Err("phase collection mutant ownership unavailable")
    tools = ToolOutcome(
        0,
        Err("not used"),
        Err("not used"),
        pytest=Ok(pytest),
        native=Ok(native_run),
        killers=Ok(report),
    )
    capture = ProvisionalCapture(
        census,
        Ok(declared),
        tools,
        (corpus_records, owners.value),
        Err("not used"),
        context.nonce,
        (),
        (),
        scoped_mutants=isinstance(scoped, Ok),
    )
    return Ok((declared, capture))


def _missing_collection_capture_sealed(
    captured: ProvisionalCapture, output: str
) -> Result[None, str]:
    """Bind Python and killer evidence to a sealed failed native command."""
    python, killers = captured.tools.pytest, captured.tools.killers
    outcomes, substeps = captured.tools.evidence, captured.tools.substeps
    if (
        not isinstance(python, Ok)
        or not isinstance(killers, Ok)
        or isinstance(outcomes, Err)
        or isinstance(substeps, Err)
        or _gate_native_manifest(captured) != Ok(None)
    ):
        return Err("phase collection observations unavailable")
    markers = output.splitlines()
    expected = (
        pytest_manifest_seal(captured.nonce, python.value),
        killer_seal(captured.nonce, killers.value),
        tool_results_seal(captured.nonce, outcomes.value, substeps.value),
    )
    return (
        Ok(None)
        if all(
            markers.count(marker) == 1
            and sum(line.startswith(marker.partition(" ")[0] + " ") for line in markers)
            == 1
            for marker in expected
        )
        else Err("phase collection observations changed after handoff")
    )


def collection_capture_sealed(
    captured: ProvisionalCapture, output: str
) -> Result[None, str]:
    """Bind the exact values used for attribution to the verified child seals."""
    pytest_run, native_run, killers = (
        captured.tools.pytest,
        captured.tools.native,
        captured.tools.killers,
    )
    if not isinstance(native_run, Ok):
        return _missing_collection_capture_sealed(captured, output)
    if not isinstance(pytest_run, Ok) or not isinstance(killers, Ok):
        return Err("phase collection observations unavailable")
    native_seal = native_observation_seal(captured.nonce, native_run.value)
    if isinstance(native_seal, Err):
        return native_seal
    markers = output.splitlines()
    return (
        Ok(None)
        if pytest_manifest_seal(captured.nonce, pytest_run.value) in markers
        and native_seal.value in markers
        and killer_seal(captured.nonce, killers.value) in markers
        else Err("phase collection observations changed after handoff")
    )


def verify_provisional_collection(
    context: CheckRun, directory: Path, output: str
) -> Result[None, str]:
    """Recheck collection and mutant failures against the sealed run records."""
    finalizers = sealed_finalizer_observation(directory, context.nonce, output)
    if isinstance(finalizers, Err):
        return finalizers
    statuses = dict(finalizers.value.outcomes)
    if any(
        statuses[name]
        for name in (
            "python-commands",
            "write-guard",
            "containment",
            "pytest-manifest",
            "mutant-killers",
        )
    ):
        return Ok(None)
    observed = _provisional_values_for_identity(context, directory, output)
    if isinstance(observed, Err) or observed.value is None:
        return observed if isinstance(observed, Err) else Ok(None)
    seals = (
        verify_python_commands_handoff(directory, context.nonce, output, context.root),
        verify_pytest_handoff(directory, context.nonce, output),
        verify_killer_handoff(directory, context.nonce, output),
        verify_native_handoff(context, directory, output),
        _verify_provisional_census(context, directory, observed.value, output),
    )
    if any(isinstance(value, Err) for value in seals):
        return Err("phase collection supporting handoff is invalid")
    captured = _parent_collection_capture(context, directory, output)
    bound = (
        captured
        if isinstance(captured, Err)
        else collection_capture_sealed(captured.value[1], output)
    )
    checked = (
        bound
        if isinstance(bound, Err)
        else captured
        if isinstance(captured, Err)
        else verify_phase_collection_failures(
            captured.value[1], captured.value[0], observed.value
        )
    )
    return (
        checked
        if isinstance(checked, Err) or isinstance(captured, Err)
        else verify_captured_cited_checks(captured.value, context.nonce, observed.value)
    )


def verify_captured_cited_checks(
    captured: tuple[tuple[Phase, ...], ProvisionalCapture],
    nonce: str,
    observed: tuple[phase_reports.PhaseResult, ...],
) -> Result[None, str]:
    """Derive cited checks from the same bound census as the collection join."""
    declarations, inputs = captured
    if isinstance(inputs.census, Err) or not isinstance(inputs.tools.pytest, Ok):
        return Err("phase cited check observations unavailable")
    work = scoped_source_inputs(inputs.census.value, declarations)
    return (
        work
        if isinstance(work, Err)
        else verify_phase_cited_checks(
            work.value.work.phases, inputs.tools.pytest.value, nonce, observed
        )
    )


def verify_provisional_oracle(
    context: CheckRun, directory: Path, output: str
) -> Result[None, str]:
    """Recheck attributed oracle failures against the sealed original records."""
    finalizers = sealed_finalizer_observation(directory, context.nonce, output)
    if isinstance(finalizers, Err):
        return finalizers
    statuses = dict(finalizers.value.outcomes)
    if any(
        statuses[name]
        for name in (
            "python-commands",
            "write-guard",
            "containment",
            "oracle-outcomes",
            "oracle-details",
        )
    ):
        return Ok(None)
    observed = _provisional_values_for_identity(context, directory, output)
    if isinstance(observed, Err) or observed.value is None:
        return observed if isinstance(observed, Err) else Ok(None)
    checks = (
        verify_python_commands_handoff(directory, context.nonce, output, context.root),
        verify_oracle_handoff(directory, context.nonce, output),
        _verify_provisional_census(context, directory, observed.value, output),
    )
    if any(isinstance(item, Err) for item in checks):
        return Err("phase oracle supporting handoff is invalid")
    census = _parent_bound_census(context, directory, output)
    original = _oracle_handoff_observations(directory, context.nonce)
    if (
        isinstance(census, Err)
        or isinstance(original, Err)
        or oracle_results_seal(context.nonce, *original.value)
        not in output.splitlines()
    ):
        return Err("phase oracle evidence unavailable or changed after handoff")
    scopes = oracle_diagnostics(census.value, original.value[1], original.value[0])
    return (
        scopes
        if isinstance(scopes, Err)
        else verify_phase_oracle_failures(scopes.value, observed.value)
    )


def verify_provisional_host(
    context: CheckRun, directory: Path, output: str
) -> Result[None, str]:
    """Recheck native host eligibility against the sealed host observation."""
    finalizers = sealed_finalizer_observation(directory, context.nonce, output)
    if isinstance(finalizers, Err):
        return finalizers
    statuses = dict(finalizers.value.outcomes)
    if any(
        statuses[name]
        for name in (
            "python-commands",
            "write-guard",
            "containment",
            "host-observation",
        )
    ):
        return Ok(None)
    observed = _provisional_values_for_identity(context, directory, output)
    if isinstance(observed, Err) or observed.value is None:
        return observed if isinstance(observed, Err) else Ok(None)
    checks = (
        verify_python_commands_handoff(directory, context.nonce, output, context.root),
        verify_host_handoff(directory, context.nonce, output),
        _verify_provisional_census(context, directory, observed.value, output),
    )
    if any(isinstance(item, Err) for item in checks):
        return Err("phase host supporting handoff is invalid")
    census = _parent_bound_census(context, directory, output)
    host = host_observation(directory, context.nonce)
    if (
        isinstance(census, Err)
        or isinstance(host, Err)
        or host_observation_seal(context.nonce, host.value) not in output.splitlines()
    ):
        return Err("phase host evidence unavailable or changed after handoff")
    declarations = census_phases(context.root, census.value)
    tools = ToolOutcome(0, Err("not used"), Err("not used"), host=host)
    capture = ProvisionalCapture(
        census,
        declarations,
        tools,
        None,
        Err("not used"),
        context.nonce,
        (),
        (),
        family=context.family,
    )
    return (
        declarations
        if isinstance(declarations, Err)
        else verify_phase_host_failures(capture, declarations.value, observed.value)
    )


def _parent_tool_capture(
    context: CheckRun, directory: Path, output: str
) -> Result[tuple[tuple[Phase, ...], ProvisionalCapture], str]:
    """Reconstruct the current tool schedule and its sealed subprocess results."""
    base = _parent_collection_capture(context, directory, output)
    files = targets(context.root)
    tools = _read_sealed_tool_results(directory, context.nonce)
    readiness = parse_readiness_observation(context.nonce, output)
    if (
        isinstance(base, Err)
        or isinstance(files, Err)
        or isinstance(tools, Err)
        or isinstance(readiness, Err)
    ):
        return Err("phase tool inputs unavailable")
    planned = pipeline(
        context.root, context.directory, files.value, context.family, assume_yes=False
    )
    schedule = tuple(step.name for step in planned)
    substeps = tuple(
        (step.name, 1 + len(step.after)) for step in planned if isinstance(step, Leg)
    )
    after_failure = frozenset(
        step.name for step in planned if isinstance(step, Leg) and step.after_failure
    )
    outcomes, attempts = tools.value
    captured_tools = replace(
        base.value[1].tools,
        code=int(not verdict(schedule, outcomes.outcomes)),
        evidence=Ok(outcomes),
        substeps=Ok(attempts),
    )
    return Ok(
        (
            base.value[0],
            replace(
                base.value[1],
                tools=captured_tools,
                schedule=schedule,
                substep_schedule=substeps,
                after_failure=after_failure,
                readiness=readiness.value,
            ),
        )
    )


def tool_capture_sealed(captured: ProvisionalCapture, output: str) -> Result[None, str]:
    """Bind the tool and collection values consumed by the parent's join."""
    outcomes, substeps = captured.tools.evidence, captured.tools.substeps
    collection = collection_capture_sealed(captured, output)
    if (
        isinstance(outcomes, Err)
        or isinstance(substeps, Err)
        or isinstance(collection, Err)
        or outcomes.value.nonce != captured.nonce
        or substeps.value.nonce != captured.nonce
        or tool_results_seal(captured.nonce, outcomes.value, substeps.value)
        not in output.splitlines()
    ):
        return Err("phase tool observations changed after handoff")
    return Ok(None)


def verify_provisional_tools(
    context: CheckRun, directory: Path, output: str
) -> Result[None, str]:
    """Recheck tool statuses after their supporting run records are sealed."""
    finalizers = sealed_finalizer_observation(directory, context.nonce, output)
    if isinstance(finalizers, Err):
        return finalizers
    statuses = dict(finalizers.value.outcomes)
    if any(
        statuses[name]
        for name in (
            "python-commands",
            "write-guard",
            "containment",
            "tool-outcomes",
            "tool-substeps",
            "pytest-manifest",
            "mutant-killers",
            "coverage-observation",
            "coverage-text-observation",
            "host-observation",
        )
    ):
        return Ok(None)
    observed = _provisional_values_for_identity(context, directory, output)
    if isinstance(observed, Err) or observed.value is None:
        return observed if isinstance(observed, Err) else Ok(None)
    checks = (
        verify_python_commands_handoff(directory, context.nonce, output, context.root),
        verify_tool_results_handoff(directory, context.nonce, output),
        verify_pytest_handoff(directory, context.nonce, output),
        verify_native_handoff(context, directory, output),
        verify_killer_handoff(directory, context.nonce, output),
        verify_provisional_coverage(context, directory, output),
        _verify_provisional_census(context, directory, observed.value, output),
    )
    if any(isinstance(item, Err) for item in checks):
        return Err("phase tool supporting handoff is invalid")
    captured = _parent_tool_capture(context, directory, output)
    bound = (
        captured
        if isinstance(captured, Err)
        else tool_capture_sealed(captured.value[1], output)
    )
    return (
        bound
        if isinstance(bound, Err)
        else captured
        if isinstance(captured, Err)
        else verify_phase_tool_failures(
            captured.value[1], captured.value[0], observed.value
        )
    )


def _parent_coverage_inputs(
    context: CheckRun, directory: Path, output: str
) -> Result[CoverageAttributionInputs, str]:
    """Reconstruct coverage inputs from sealed reports and the guarded census."""
    census = _parent_bound_census(context, directory, output)
    pair = _coverage_handoff_files(directory, context.nonce)
    tools = _read_sealed_tool_results(directory, context.nonce)
    host = host_observation(directory, context.nonce)
    if isinstance(census, Err) or isinstance(pair, Err) or isinstance(tools, Err):
        return Err("phase coverage records unavailable")
    declarations = census_phases(context.root, census.value)
    config = _coverage_declarations(census.value, context.family)
    if isinstance(declarations, Err) or isinstance(config, Err):
        return Err("phase coverage declarations unavailable")
    work = scoped_source_inputs(census.value, declarations.value)
    try:
        text = pair.value[1].decode("utf-8")
    except UnicodeError:
        return Err("phase coverage report is not UTF-8")
    facts = coverage_hosts.parse_report(text, config.value[0])
    if isinstance(work, Err) or isinstance(facts, Err):
        return Err("phase coverage inputs are invalid")
    snapshot = CoverageSnapshot(
        context.nonce,
        facts.value,
        pair.value[0],
        (0, 0),
        pair.value[1],
        (0, 0),
        census.value,
    )
    return Ok(
        CoverageAttributionInputs(
            census.value,
            work.value.work.phases,
            context.nonce,
            context.family,
            host,
            Ok(snapshot),
            Ok(tools.value[1]),
            Ok(tools.value[0]),
        )
    )


def coverage_inputs_sealed(inputs: CoverageAttributionInputs, output: str) -> bool:
    """Bind the exact reconstructed coverage, host and tool values to the run."""
    coverage, host, outcomes, substeps = (
        inputs.coverage,
        inputs.host,
        inputs.outcomes,
        inputs.substeps,
    )
    if (
        not inputs.nonce
        or not isinstance(coverage, Ok)
        or not isinstance(host, Ok)
        or not isinstance(outcomes, Ok)
        or not isinstance(substeps, Ok)
    ):
        return False
    snapshot = coverage.value
    config = _coverage_declarations(inputs.entries, inputs.family)
    try:
        text = snapshot.report.decode("utf-8")
    except UnicodeError:
        return False
    if isinstance(config, Err):
        return False
    facts = coverage_hosts.parse_report(text, config.value[0])
    markers = output.splitlines()
    return (
        snapshot.nonce == inputs.nonce
        and outcomes.value.nonce == inputs.nonce
        and substeps.value.nonce == inputs.nonce
        and _parse_coverage_handoff(inputs.nonce, snapshot.record, snapshot.report)
        == Ok(None)
        and isinstance(facts, Ok)
        and facts.value == snapshot.facts
        and coverage_seal(inputs.nonce, snapshot.record, snapshot.report) in markers
        and host_observation_seal(inputs.nonce, host.value) in markers
        and tool_results_seal(inputs.nonce, outcomes.value, substeps.value) in markers
    )


def verify_provisional_coverage(
    context: CheckRun, directory: Path, output: str
) -> Result[None, str]:
    """Recheck phase coverage gaps against all sealed supporting observations."""
    finalizers = sealed_finalizer_observation(directory, context.nonce, output)
    if isinstance(finalizers, Err):
        return finalizers
    statuses = dict(finalizers.value.outcomes)
    if any(
        statuses[name]
        for name in (
            "python-commands",
            "write-guard",
            "containment",
            "coverage-observation",
            "coverage-text-observation",
            "host-observation",
            "tool-outcomes",
            "tool-substeps",
        )
    ):
        return Ok(None)
    observed = _provisional_values_for_identity(context, directory, output)
    if isinstance(observed, Err) or observed.value is None:
        return observed if isinstance(observed, Err) else Ok(None)
    checks = (
        verify_python_commands_handoff(directory, context.nonce, output, context.root),
        verify_coverage_handoff(directory, context.nonce, output),
        verify_coverage_text_handoff(context, directory, output),
        verify_host_handoff(directory, context.nonce, output),
        verify_tool_results_handoff(directory, context.nonce, output),
        _verify_provisional_census(context, directory, observed.value, output),
    )
    if any(isinstance(item, Err) for item in checks):
        return Err("phase coverage supporting handoff is invalid")
    inputs = _parent_coverage_inputs(context, directory, output)
    return (
        inputs
        if isinstance(inputs, Err)
        else Err("phase coverage inputs changed after handoff")
        if not coverage_inputs_sealed(inputs.value, output)
        else verify_phase_coverage_failures(inputs.value, observed.value)
    )


def _receipt_native_observation(
    inputs: ReceiptNativeInputs,
) -> Result[tuple[NativeSnapshot | None, tuple[tuple[int, frozenset[str]], ...]], str]:
    """Allow absent native evidence only after its declared consumers are proven."""
    context, directory, output = inputs.context, inputs.directory, inputs.output
    finalizers, observed = inputs.finalizers, inputs.observations
    declarations, collection = inputs.declarations, inputs.collection
    status = dict(finalizers.outcomes).get("native-observation")
    native = collection.tools.native
    if status == 0 and isinstance(native, Ok):
        return Ok((native.value, ()))
    if (
        status != 1
        or not isinstance(native, Err)
        or isinstance(collection.census, Err)
        or collection.claims is None
        or isinstance(
            _verify_localized_native_finalizers(
                directory, context.nonce, output, finalizers, observed
            ),
            Err,
        )
    ):
        return Err("receipt native evidence unavailable or unproven")
    records, owners = collection.claims
    scopes = unavailable_native_scopes(
        collection.census.value, declarations, records, owners
    )
    if isinstance(scopes, Err):
        return scopes
    values = {item.number: item.failures for item in observed}
    if (
        len(values) != len(observed)
        or tuple(number for number, _failures in scopes.value)
        != tuple(item.number for item in observed)
        or not any(failures for _number, failures in scopes.value)
        or any(not failures <= values[number] for number, failures in scopes.value)
    ):
        return Err("receipt native absence attribution differs")
    return Ok((None, scopes.value))


def retained_receipt_inputs(
    context: CheckRun, directory: Path, output: str
) -> Result[ReceiptInputs, str]:
    """Reconstruct receipt inputs only from joined, sealed run observations.

    These are inputs for later receipt authentication, not passing receipts.
    Missing or failed integrity observations cannot supply this capture.
    """
    finalizers = sealed_finalizer_observation(directory, context.nonce, output)
    if isinstance(finalizers, Err) or any(
        status
        for name, status in finalizers.value.outcomes
        if name != "native-observation"
    ):
        return Err("receipt inputs lack complete finalizers")
    observed = _provisional_values_for_identity(context, directory, output)
    captured = _parent_collection_capture(context, directory, output)
    coverage = _parent_coverage_inputs(context, directory, output)
    checks = (
        verify_provisional_input_identities(context, directory, output),
        verify_provisional_collection(context, directory, output),
        verify_provisional_coverage(context, directory, output),
        verify_host_handoff(directory, context.nonce, output),
        verify_native_handoff(context, directory, output),
    )
    if (
        isinstance(observed, Err)
        or observed.value is None
        or isinstance(captured, Err)
        or isinstance(coverage, Err)
        or any(isinstance(check, Err) for check in checks)
    ):
        return Err("receipt input evidence unavailable")
    declarations, collection = captured.value
    if (
        isinstance(collection.census, Err)
        or collection.claims is None
        or not isinstance(collection.tools.pytest, Ok)
        or not isinstance(collection.tools.killers, Ok)
        or not isinstance(coverage.value.host, Ok)
        or not isinstance(coverage.value.coverage, Ok)
        or collection.nonce != context.nonce
        or coverage.value.nonce != context.nonce
        or collection.census.value != coverage.value.entries
        or coverage.value.host.value.family != context.family
        or collection_capture_sealed(collection, output) != Ok(None)
        or not coverage_inputs_sealed(coverage.value, output)
    ):
        return Err("receipt input evidence differs")
    records, owners = collection.claims
    pytest_run = collection.tools.pytest.value
    native = _receipt_native_observation(
        ReceiptNativeInputs(
            context,
            directory,
            output,
            finalizers.value,
            observed.value,
            declarations,
            collection,
        )
    )
    native_run, native_absence = native.value if isinstance(native, Ok) else (None, ())
    killers = collection.tools.killers.value
    source = evidence.digest_census(collection.census.value)
    work = scoped_source_inputs(collection.census.value, declarations)
    verified_killers = mutant_report.validate(killers, records, pytest_run)
    facts = _coverage_captured_facts(coverage.value)
    if (
        isinstance(source, Err)
        or isinstance(native, Err)
        or isinstance(work, Err)
        or isinstance(verified_killers, Err)
        or isinstance(facts, Err)
        or work.value.work.phases != coverage.value.phases
        or (native_run is not None and native_run.manifest.nonce != context.nonce)
        or pytest_run.nonce != context.nonce
        or killers.nonce != context.nonce
    ):
        return Err("receipt input observations are invalid")
    coverage_owners = _coverage_source_owners(
        collection.census.value, work.value.work.phases
    )
    coverage_declarations = _coverage_declarations(
        collection.census.value, context.family
    )
    native_citations = receipt_native_citations(declarations, records, owners)
    if (
        isinstance(coverage_owners, Err)
        or isinstance(coverage_declarations, Err)
        or isinstance(native_citations, Err)
    ):
        return Err("receipt input declarations unavailable")
    return Ok(
        ReceiptInputs(
            context.nonce,
            source.value,
            work.value.work.phases,
            observed.value,
            coverage.value.host.value,
            pytest_run,
            native_run,
            killers,
            owners,
            facts.value,
            coverage_owners.value,
            frozenset(coverage_declarations.value[1]),
            native_citations.value,
            native_absence,
            collection.census.value,
        )
    )


def phase_receipt_evidence(
    captured: ReceiptInputs,
) -> Result[tuple[PhaseReceiptEvidence, ...], str]:
    """Scope observed tests, mutants and coverage without issuing receipts."""
    phases, observations = captured.phases, captured.observations
    numbers = tuple(phase.number for phase in phases)
    identities = {item.number: item.identity for item in observations}
    owners = dict(captured.mutant_owners)
    native_sources = (
        dict(captured.native.sources) if captured.native is not None else {}
    )
    coverage_owners = {item.path: item.consumers for item in captured.coverage_owners}
    coverage_facts = {item.path: item for item in captured.coverage}
    mutant_records = {item.identifier: item for item in captured.killers.records}
    python = captured.python
    native = captured.native.manifest if captured.native is not None else None
    absence = dict(captured.native_absence)
    if (
        not captured.nonce
        or not phases
        or any(isinstance(number, bool) or number < 0 for number in numbers)
        or numbers != tuple(sorted(set(numbers)))
        or tuple(item.number for item in observations) != numbers
        or any(
            len(item.identity) != SHA256_HEX_LENGTH
            or any(character not in "0123456789abcdef" for character in item.identity)
            for item in observations
        )
        or any("unverified-run" not in item.failures for item in observations)
        or any(
            isinstance(dependency, bool)
            or dependency >= phase.number
            or dependency not in identities
            for phase in phases
            for dependency in phase.prerequisites
        )
        or len(owners) != len(captured.mutant_owners)
        or any(isinstance(number, bool) for number in owners.values())
        or not frozenset(owners.values()) <= frozenset(numbers)
        or len(mutant_records) != len(captured.killers.records)
        or not mutant_records.keys() <= owners.keys()
        or (
            captured.native is not None
            and len(native_sources) != len(captured.native.sources)
        )
        or (native is not None and frozenset(native_sources) != native.collected)
        or (
            native is None
            and (
                len(absence) != len(captured.native_absence)
                or tuple(number for number, _failures in captured.native_absence)
                != numbers
                or not any(absence.values())
                or any(
                    not absence[item.number] <= item.failures for item in observations
                )
                or any(
                    not absence.get(number, frozenset())
                    for number, _node in captured.native_citations
                )
                or any(
                    any(
                        path.startswith("src/agentctl/haskell/")
                        for path in phase.inputs
                    )
                    and not absence.get(phase.number, frozenset())
                    for phase in phases
                )
            )
        )
        or (native is not None and bool(captured.native_absence))
        or len(set(captured.native_citations)) != len(captured.native_citations)
        or any(
            isinstance(number, bool)
            or number not in numbers
            or not node.startswith("haskell:")
            for number, node in captured.native_citations
        )
        or len(coverage_owners) != len(captured.coverage_owners)
        or len(coverage_facts) != len(captured.coverage)
        or not captured.foreign_coverage <= coverage_owners.keys()
        or frozenset(coverage_facts)
        != coverage_owners.keys() - captured.foreign_coverage
        or any(
            not consumers
            or any(isinstance(number, bool) for number in consumers)
            or not consumers <= frozenset(numbers)
            for consumers in coverage_owners.values()
        )
        or any(
            isinstance(fact.missing_statements, bool)
            or isinstance(fact.missing_branches, bool)
            or fact.missing_statements < 0
            or fact.missing_branches < 0
            for fact in captured.coverage
        )
        or python.nonce != captured.nonce
        or (native is not None and native.nonce != captured.nonce)
        or captured.killers.nonce != captured.nonce
        or not python.passed <= python.executed <= python.collected
        or (
            native is not None
            and not native.passed <= native.executed == native.collected
        )
    ):
        return Err("invalid phase receipt inputs")
    passed_checks = _passed_phase_checks(phases, python, captured.nonce)
    killed = frozenset(
        record.identifier
        for record in captured.killers.records
        if not record.error
        and record.killers
        and all(
            killer.baseline == "passed" and killer.mutation == "killed"
            for killer in record.killers
        )
        and mutant_report.PREFIX + record.identifier + "]" in python.passed
    )
    covered = frozenset(
        item.path
        for item in captured.coverage
        if not item.missing_statements and not item.missing_branches
    )
    results: tuple[PhaseReceiptEvidence, ...] = ()
    for phase, observation in zip(phases, observations, strict=True):
        native_tests = frozenset(
            node
            for node, path in native_sources.items()
            if path in phase.inputs
            and (
                not any(case == node for _number, case in captured.native_citations)
                or (phase.number, node) in captured.native_citations
            )
        ) | frozenset(
            node for number, node in captured.native_citations if number == phase.number
        )
        required_tests = phase.checks | native_tests
        passed_tests = (phase.checks & passed_checks) | (
            native_tests & native.passed if native is not None else frozenset()
        )
        required_mutants = frozenset(
            name for name, owner in owners.items() if owner == phase.number
        )
        required_coverage = frozenset(
            path
            for path, consumers in coverage_owners.items()
            if phase.number in consumers and path not in captured.foreign_coverage
        )
        phase_killed = required_mutants & killed
        phase_covered = required_coverage & covered
        failures = (
            observation.failures
            | frozenset(
                "receipt test missing: " + item
                for item in required_tests - passed_tests
            )
            | frozenset(
                "receipt mutant missing: " + item
                for item in required_mutants - phase_killed
            )
            | frozenset(
                "receipt coverage missing: " + item
                for item in required_coverage - phase_covered
            )
        )
        results += (
            PhaseReceiptEvidence(
                phase.number,
                observation.identity,
                tuple(
                    (number, identities[number])
                    for number in sorted(phase.prerequisites)
                ),
                required_tests,
                passed_tests,
                required_mutants,
                phase_killed,
                required_coverage,
                phase_covered,
                failures,
            ),
        )
    return Ok(results)


def _parent_static_inputs(
    context: CheckRun, directory: Path, output: str
) -> Result[ParentStaticInputs, str]:
    """Rebuild phase inputs and static subprocess statuses from sealed records."""
    census = _parent_bound_census(context, directory, output)
    tools = _read_sealed_tool_results(directory, context.nonce)
    if isinstance(census, Err) or isinstance(tools, Err):
        return Err("phase static evidence unavailable")
    declarations = census_phases(context.root, census.value)
    if isinstance(declarations, Err):
        return declarations
    work = scoped_source_inputs(census.value, declarations.value)
    return (
        work
        if isinstance(work, Err)
        else Ok(
            ParentStaticInputs(
                context, directory, census.value, work.value.work.phases, *tools.value
            )
        )
    )


def _static_handoff(
    inputs: ParentStaticInputs, tool: str, output: str
) -> Result[bytes, str]:
    """Verify and read the named static tool's original diagnostic record."""
    context, directory = inputs.context, inputs.directory
    is_type_checker = tool == "ty"
    if is_type_checker:
        sealed = verify_ty_handoff(directory, context.nonce, output, context.root)
        record = _ty_handoff_record(directory, context.nonce, context.root)
        seal = ty_observation_seal
    elif tool == "ruff-format":
        sealed = verify_ruff_format_handoff(
            directory, context.nonce, output, context.root
        )
        record = _ruff_handoff_record(
            directory,
            context.nonce,
            context.root,
            filename="ruff-format-observation.json",
        )
        seal = ruff_format_seal
    else:
        sealed = verify_ruff_handoff(directory, context.nonce, output, context.root)
        record = _ruff_handoff_record(directory, context.nonce, context.root)
        seal = ruff_seal
    return (
        Err("static diagnostic handoff invalid")
        if isinstance(sealed, Err)
        else record
        if isinstance(record, Err)
        else record
        if seal(context.nonce, record.value) in output.splitlines()
        else Err("static diagnostic changed after handoff")
    )


def static_inputs_sealed(inputs: ParentStaticInputs, output: str) -> bool:
    """Bind the static join's exact tool outcomes and substeps to their seal."""
    nonce = inputs.context.nonce
    return (
        bool(nonce)
        and inputs.outcomes.nonce == nonce
        and inputs.substeps.nonce == nonce
        and tool_results_seal(nonce, inputs.outcomes, inputs.substeps)
        in output.splitlines()
    )


def verify_provisional_static(
    context: CheckRun, directory: Path, output: str
) -> Result[None, str]:
    """Recheck each available sealed static diagnostic against phase results."""
    finalizers = sealed_finalizer_observation(directory, context.nonce, output)
    if isinstance(finalizers, Err):
        return finalizers
    statuses = dict(finalizers.value.outcomes)
    if any(
        statuses[name]
        for name in (
            "python-commands",
            "write-guard",
            "containment",
            "tool-outcomes",
            "tool-substeps",
        )
    ):
        return Ok(None)
    tools = tuple(
        tool
        for tool, finalizer in (
            ("ruff-check", "ruff-observation"),
            ("ruff-format", "ruff-format-observation"),
            ("ty", "ty-observation"),
        )
        if not statuses[finalizer]
    )
    if not tools:
        return Ok(None)
    observed = _provisional_values_for_identity(context, directory, output)
    if isinstance(observed, Err) or observed.value is None:
        return observed if isinstance(observed, Err) else Ok(None)
    checks = (
        verify_python_commands_handoff(directory, context.nonce, output, context.root),
        verify_tool_results_handoff(directory, context.nonce, output),
        _verify_provisional_census(context, directory, observed.value, output),
    )
    if any(isinstance(item, Err) for item in checks):
        return Err("phase static supporting handoff is invalid")
    inputs = _parent_static_inputs(context, directory, output)
    return (
        inputs
        if isinstance(inputs, Err)
        else Err("static tool inputs changed after handoff")
        if not static_inputs_sealed(inputs.value, output)
        else _verify_static_reports(inputs.value, tools, output, observed.value)
    )


def verify_provisional_source(
    context: CheckRun, directory: Path, output: str
) -> Result[None, str]:
    """Recheck source policy against the bound parent census and phase results."""
    finalizers = sealed_finalizer_observation(directory, context.nonce, output)
    if isinstance(finalizers, Err):
        return finalizers
    statuses = dict(finalizers.value.outcomes)
    if any(
        statuses[name] for name in ("python-commands", "write-guard", "containment")
    ):
        return Ok(None)
    observed = _provisional_values_for_identity(context, directory, output)
    if isinstance(observed, Err) or observed.value is None:
        return observed if isinstance(observed, Err) else Ok(None)
    checks = (
        verify_python_commands_handoff(directory, context.nonce, output, context.root),
        _verify_provisional_census(context, directory, observed.value, output),
    )
    if any(isinstance(item, Err) for item in checks):
        return Err("phase source supporting handoff is invalid")
    census = _parent_bound_census(context, directory, output)
    if isinstance(census, Err):
        return census
    declarations = census_phases(context.root, census.value)
    return (
        declarations
        if isinstance(declarations, Err)
        else verify_phase_source_failures(
            census.value, declarations.value, observed.value
        )
    )


def verify_provisional_prerequisites(
    context: CheckRun, directory: Path, output: str
) -> Result[None, str]:
    """Recheck prerequisite failures against the bound phase declarations."""
    finalizers = sealed_finalizer_observation(directory, context.nonce, output)
    if isinstance(finalizers, Err):
        return finalizers
    statuses = dict(finalizers.value.outcomes)
    if any(
        statuses[name] for name in ("python-commands", "write-guard", "containment")
    ):
        return Ok(None)
    observed = _provisional_values_for_identity(context, directory, output)
    if isinstance(observed, Err) or observed.value is None:
        return observed if isinstance(observed, Err) else Ok(None)
    checks = (
        verify_python_commands_handoff(directory, context.nonce, output, context.root),
        _verify_provisional_census(context, directory, observed.value, output),
    )
    if any(isinstance(item, Err) for item in checks):
        return Err("phase prerequisite supporting handoff is invalid")
    census = _parent_bound_census(context, directory, output)
    if isinstance(census, Err):
        return census
    declarations = census_phases(context.root, census.value)
    work = (
        declarations
        if isinstance(declarations, Err)
        else scoped_source_inputs(census.value, declarations.value)
    )
    return (
        work
        if isinstance(work, Err)
        else verify_phase_prerequisite_failures(work.value.work.phases, observed.value)
    )


def _parent_validation_problems(
    context: CheckRun, directory: Path, output: str
) -> Result[tuple[str, ...], str]:
    """Recompute shared static validators against the bound parent checkout."""
    base = _parent_collection_capture(context, directory, output)
    files = targets(context.root)
    if isinstance(base, Err) or isinstance(files, Err):
        return Err("phase validation inputs unavailable")
    declarations, captured = base.value
    if isinstance(captured.census, Err) or captured.claims is None:
        return Err("phase validation census or claims unavailable")
    entries = captured.census.value
    records, owners = captured.claims
    direct = complete_mutant_owners(entries, records)
    pending = isinstance(direct, Err)
    declared = (
        provisional_or_scoped_mutant_owners(entries, records) if pending else direct
    )
    if isinstance(declared, Err) or declared.value != owners:
        return Err("phase validation mutant ownership differs")
    policy = census_policy(entries, owners)
    target_census = python_target_census(context.root, files.value, entries)
    problems = (
        *(
            ("validators: Python targets: " + target_census.error,)
            if isinstance(target_census, Err)
            else ()
        ),
        *source_ownership_problems(entries),
        *docs(context.root),
        *plan(context.root),
        *test_consumer_problems(context.root, entries),
        *coverage_host_problems(context.root, entries),
        *forbidden_surfaces(context.root),
        *configuration(context.root),
    )
    try:
        completed = (
            *(
                ("validators: closure policy: " + policy.error,)
                if isinstance(policy, Err)
                else ()
            ),
            *phase0_claim_problems(context.root, entries, records),
            *(fragment_claim_problems(entries, records) if not pending else ()),
            *closure.static(
                context.root,
                records,
                mutant_owners=policy.value if isinstance(policy, Ok) else None,
                observed_phases=declarations,
            ),
        )
    except (OSError, UnicodeError) as exc:
        completed = ("validators: cannot read closure inputs: " + str(exc),)
    after = _parent_bound_census(context, directory, output)
    combined = (
        *scoped_ownership_validation(problems, Ok(entries), Ok(declarations)),
        *completed,
    )
    return (
        Err("phase validation census changed")
        if isinstance(after, Err) or after.value != entries
        else Ok(
            scoped_mutant_declaration_validation(
                combined,
                Ok(entries),
                Ok(declarations),
                captured.claims,
            )
        )
    )


def verify_provisional_validation(
    context: CheckRun, directory: Path, output: str
) -> Result[None, str]:
    """Recheck shared static validator findings before and after retention."""
    finalizers = sealed_finalizer_observation(directory, context.nonce, output)
    if isinstance(finalizers, Err):
        return finalizers
    statuses = dict(finalizers.value.outcomes)
    if (
        any(
            statuses[name] for name in ("python-commands", "write-guard", "containment")
        )
        or statuses["pytest-manifest"]
        or statuses["mutant-killers"]
    ):
        return Ok(None)
    observed = _provisional_values_for_identity(context, directory, output)
    if isinstance(observed, Err) or observed.value is None:
        return observed if isinstance(observed, Err) else Ok(None)
    checks = (
        verify_provisional_collection(context, directory, output),
        verify_python_commands_handoff(directory, context.nonce, output, context.root),
        _verify_provisional_census(context, directory, observed.value, output),
    )
    if any(isinstance(item, Err) for item in checks):
        return Err("phase validation supporting handoff is invalid")
    problems = _parent_validation_problems(context, directory, output)
    return (
        problems
        if isinstance(problems, Err)
        else verify_phase_validation_failures(problems.value, observed.value)
    )


def _verify_static_reports(
    inputs: ParentStaticInputs,
    tools: tuple[str, ...],
    output: str,
    observed: tuple[phase_reports.PhaseResult, ...],
) -> Result[None, str]:
    """Compare each individually sealed static record with phase failures."""
    for tool in tools:
        record = _static_handoff(inputs, tool, output)
        checked = (
            record
            if isinstance(record, Err)
            else verify_static_phase_failures(inputs, tool, record.value, observed)
        )
        if isinstance(checked, Err):
            return checked
    return Ok(None)


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
    contents = _read_provisional_handoff(directory / "provisional-phases.json")
    return (
        contents
        if isinstance(contents, Err)
        else _verify_provisional_record(nonce, contents.value, markers)
    )


def _verify_provisional_record(
    nonce: str, contents: bytes, markers: tuple[str, ...]
) -> Result[None, str]:
    """Check the original seal before decoding the private record."""
    return (
        parse_provisional_record(nonce, contents)
        if provisional_seal(nonce, contents) == markers[0]
        else Err("provisional handoff digest mismatch")
    )


def _read_provisional_handoff(path: Path) -> Result[bytes, str]:
    """Read one private provisional record while checking its identity."""
    try:
        if path.is_symlink() or path.is_junction():
            return Err("provisional handoff record is a symlink")
        before = path.lstat()
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            return Err("provisional handoff is not a private regular file")
        with open(path, "rb", opener=_open_private_handoff) as stream:
            opened = os.fstat(stream.fileno())
            if (
                not stat.S_ISREG(opened.st_mode)
                or opened.st_nlink != 1
                or (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino)
            ):
                return Err("provisional handoff record changed during inspection")
            contents = stream.read()
            stream.seek(0)
            repeated = stream.read()
            closed = os.fstat(stream.fileno())
        after = path.lstat()
        if (
            path.is_symlink()
            or path.is_junction()
            or (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino)
            or after.st_nlink != 1
            or (opened.st_dev, opened.st_ino, opened.st_nlink)
            != (closed.st_dev, closed.st_ino, closed.st_nlink)
            or repeated != contents
        ):
            return Err("provisional handoff record changed during inspection")
    except OSError as exc:
        return Err("cannot read provisional handoff: " + str(exc))
    return Ok(contents)


def _open_private_handoff(path: str, flags: int) -> int:
    """Open without following links or blocking on a substituted FIFO."""
    return os.open(
        path, flags | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    )


def killer_seal(nonce: str, report: mutant_report.Report) -> str:
    """Bind the original per-killer bytes to the child handoff."""
    return f"{KILLER_SEAL} {nonce} {report.digest}"


def verify_killer_handoff(
    directory: Path, nonce: str, output: str
) -> Result[None, str]:
    """Verify the retained report whenever its finalizer claimed success."""
    finalizers = sealed_finalizer_observation(directory, nonce, output)
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


def coverage_seal(nonce: str, record: bytes, report: bytes) -> str:
    """Bind the original coverage record and raw report to one child run."""
    digest = hashlib.sha256()
    for value in (record, report):
        digest.update(len(value).to_bytes(8, "big"))
        digest.update(value)
    return f"{COVERAGE_SEAL} {nonce} {digest.hexdigest()}"


def _coverage_handoff_files(
    directory: Path, nonce: str
) -> Result[tuple[bytes, bytes], str]:
    """Read the retained pair twice and require its canonical nonce-bound schema."""
    record_path, raw_path = (
        directory / "coverage-report.json",
        directory / "coverage-raw.json",
    )
    try:
        paths = (record_path, raw_path)
        before = tuple(path.lstat() for path in paths)
        first = tuple(_read_provisional_handoff(path) for path in paths)
        match first:
            case (Ok(record), Ok(raw)):
                pass
            case _:
                return Err("cannot read private coverage handoff")
        after = tuple(path.lstat() for path in paths)
        second = tuple(_read_provisional_handoff(path) for path in paths)
        final = tuple(path.lstat() for path in paths)
        if any(
            (initial.st_dev, initial.st_ino) != (last.st_dev, last.st_ino)
            or (initial.st_dev, initial.st_ino) != (end.st_dev, end.st_ino)
            or last.st_nlink != 1
            or end.st_nlink != 1
            or isinstance(repeated, Err)
            or original != repeated
            for initial, last, end, original, repeated in zip(
                before, after, final, first, second, strict=True
            )
        ):
            return Err("coverage handoff changed during inspection")
    except OSError as exc:
        return Err("cannot read coverage handoff: " + str(exc))
    checked = _parse_coverage_handoff(nonce, record, raw)
    return checked if isinstance(checked, Err) else Ok((record, raw))


def _parse_coverage_handoff(nonce: str, record: bytes, raw: bytes) -> Result[None, str]:
    """Require canonical wrapper bytes and a valid report for the requested nonce."""
    try:
        value: object = json.loads(record)
    except (UnicodeError, ValueError, RecursionError) as exc:
        return Err("cannot read coverage handoff: " + str(exc))
    match value:
        case {
            "nonce": str() as actual,
            "version": str() as version,
            "report": str() as text,
            **extra,
        } if not extra and actual == nonce and bool(nonce):
            pass
        case _:
            return Err("invalid coverage handoff identity")
    try:
        canonical = json.dumps(value, sort_keys=True).encode("utf-8")
        report_bytes = text.encode("utf-8")
    except UnicodeError:
        return Err("invalid coverage handoff encoding")
    if canonical != record or report_bytes != raw:
        return Err("inconsistent or noncanonical coverage handoff")
    parsed = coverage_hosts.parse_report(text, version)
    return parsed if isinstance(parsed, Err) else Ok(None)


def verify_coverage_handoff(
    directory: Path, nonce: str, output: str
) -> Result[None, str]:
    """Verify the child's original coverage pair before and after retention."""
    finalizers = sealed_finalizer_observation(directory, nonce, output)
    if isinstance(finalizers, Err):
        return finalizers
    statuses = dict(finalizers.value.outcomes)
    if statuses["coverage-observation"]:
        return Ok(None)
    lines = output.splitlines()
    markers = tuple(line for line in lines if line.startswith(COVERAGE_SEAL + " "))
    offset = (
        KILLER_HANDOFF_LINES + 1
        if not statuses["mutant-killers"]
        else KILLER_HANDOFF_LINES
    )
    if len(markers) != 1 or len(lines) < offset or lines[-offset] != markers[0]:
        return Err("missing or ambiguous coverage handoff")
    observed = _coverage_handoff_files(directory, nonce)
    if isinstance(observed, Err):
        return observed
    return (
        Ok(None)
        if coverage_seal(nonce, *observed.value) == markers[0]
        else Err("coverage handoff digest mismatch")
    )


def ruff_seal(nonce: str, record: bytes) -> str:
    """Bind the original Ruff observation bytes to one child run."""
    return f"{RUFF_SEAL} {nonce} {hashlib.sha256(record).hexdigest()}"


def _ruff_record_fields(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """Apply the duplicate-field refusal to a retained Ruff record."""
    return _ruff_fields(pairs)


def _parse_ruff_record(nonce: str, root: Path, record: bytes) -> Result[None, str]:
    """Require canonical nonce-bound Ruff output and a consistent status."""
    try:
        value: object = json.loads(record, object_pairs_hook=_ruff_record_fields)
    except (ValueError, UnicodeError, RecursionError):
        return Err("invalid Ruff handoff JSON")
    match value:
        case {
            "nonce": str() as actual,
            "root": str() as root_text,
            "code": int() as code,
            "stdout": str() as stdout,
            "stderr": str() as stderr,
            **extra,
        } if not extra and nonce and actual == nonce:
            pass
        case _:
            return Err("invalid Ruff handoff identity")
    if (
        root != Path(root_text)
        or json.dumps(value, sort_keys=True).encode("utf-8") != record
    ):
        return Err("noncanonical Ruff handoff")
    parsed = parse_ruff_output(root, Output(code, stdout, stderr))
    return parsed if isinstance(parsed, Err) else Ok(None)


def _ruff_handoff_record(
    directory: Path, nonce: str, root: Path, *, filename: str = "ruff-observation.json"
) -> Result[bytes, str]:
    """Read the original or retained Ruff record twice without following links."""
    if filename not in {"ruff-observation.json", "ruff-format-observation.json"}:
        return Err("invalid Ruff handoff name")
    path = directory / filename
    try:
        before = path.lstat()
        if (
            path.is_symlink()
            or not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
        ):
            return Err("Ruff handoff is not a private regular file")
        record = path.read_bytes()
        after = path.lstat()
        if (
            path.is_symlink()
            or (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino)
            or after.st_nlink != 1
            or path.read_bytes() != record
        ):
            return Err("Ruff handoff changed during inspection")
    except OSError as exc:
        return Err("cannot read Ruff handoff: " + str(exc))
    parsed = _parse_ruff_record(nonce, root, record)
    return parsed if isinstance(parsed, Err) else Ok(record)


def verify_ruff_handoff(
    directory: Path, nonce: str, output: str, root: Path
) -> Result[None, str]:
    """Verify the child's original Ruff result before and after retention."""
    finalizers = sealed_finalizer_observation(directory, nonce, output)
    if isinstance(finalizers, Err):
        return finalizers
    statuses = dict(finalizers.value.outcomes)
    if statuses["ruff-observation"]:
        return Ok(None)
    lines = output.splitlines()
    markers = tuple(line for line in lines if line.startswith(RUFF_SEAL + " "))
    offset = (
        3
        + int(not statuses["mutant-killers"])
        + int(not statuses["coverage-observation"])
    )
    if len(lines) < offset or len(markers) != 1 or lines[-offset] != markers[0]:
        return Err("missing or ambiguous Ruff handoff")
    record = _ruff_handoff_record(directory, nonce, root)
    if isinstance(record, Err):
        return record
    return (
        Ok(None)
        if ruff_seal(nonce, record.value) == markers[0]
        else Err("Ruff handoff digest mismatch")
    )


def ruff_format_seal(nonce: str, record: bytes) -> str:
    """Bind the formatter observation to the run's finalizer output."""
    return f"{RUFF_FORMAT_SEAL} {nonce} {hashlib.sha256(record).hexdigest()}"


def verify_ruff_format_handoff(
    directory: Path, nonce: str, output: str, root: Path
) -> Result[None, str]:
    """Verify the formatter observation before and after report retention."""
    finalizers = sealed_finalizer_observation(directory, nonce, output)
    if isinstance(finalizers, Err):
        return finalizers
    statuses = dict(finalizers.value.outcomes)
    if statuses["ruff-format-observation"]:
        return Ok(None)
    lines = output.splitlines()
    markers = tuple(line for line in lines if line.startswith(RUFF_FORMAT_SEAL + " "))
    offset = (
        3
        + int(not statuses["mutant-killers"])
        + int(not statuses["coverage-observation"])
        + int(not statuses["ruff-observation"])
        + int(not statuses["python-commands"])
    )
    if len(lines) < offset or len(markers) != 1 or markers[0] != lines[-offset]:
        return Err("missing or ambiguous Ruff format handoff")
    record = _ruff_handoff_record(
        directory, nonce, root, filename="ruff-format-observation.json"
    )
    if isinstance(record, Err):
        return record
    return (
        Ok(None)
        if ruff_format_seal(nonce, record.value) == markers[0]
        else Err("Ruff format handoff digest mismatch")
    )


def python_commands_seal(nonce: str, record: bytes) -> str:
    """Bind the observed command bytes to the current child run."""
    return f"{PYTHON_COMMANDS_SEAL} {nonce} {hashlib.sha256(record).hexdigest()}"


def native_source_digest(snapshot: NativeSnapshot) -> Result[str, str]:
    """Bind all captured native source entries, including kinds and literal bytes."""
    entries = tuple(
        sorted(
            entry
            for entry in snapshot.entries
            if entry.path == "src/agentctl/haskell"
            or entry.path.startswith("src/agentctl/haskell/")
        )
    )
    paths = tuple(entry.path for entry in entries)
    files = frozenset(entry.path for entry in entries if entry.kind == "file")
    if (
        not entries
        or len(set(paths)) != len(paths)
        or any(path not in files for _node, path in snapshot.sources)
    ):
        return Err("native source census unavailable or inconsistent")
    digest = hashlib.sha256()
    try:
        for entry in entries:
            for item in (
                entry.path.encode("utf-8"),
                entry.kind.encode("ascii"),
                *entry.payloads,
            ):
                digest.update(len(item).to_bytes(8, "big"))
                digest.update(item)
    except UnicodeError:
        return Err("native source path is not encodable")
    return Ok(digest.hexdigest())


def coverage_text_seal(nonce: str, record: bytes) -> str:
    """Bind the original coverage report command to the current run."""
    return f"{COVERAGE_TEXT_SEAL} {nonce} {hashlib.sha256(record).hexdigest()}"


def _coverage_text_handoff(context: CheckRun, directory: Path) -> Result[bytes, str]:
    """Read the retained report transcript and check its exact source-bound command."""
    path = directory / "coverage-text.json"
    try:
        before = path.lstat()
        if (
            path.is_symlink()
            or before.st_nlink != 1
            or not stat.S_ISREG(before.st_mode)
        ):
            return Err("coverage text handoff is not a private regular file")
        record = path.read_bytes()
        after = path.lstat()
        if (
            path.is_symlink()
            or after.st_nlink != 1
            or (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino)
            or path.read_bytes() != record
        ):
            return Err("coverage text handoff changed during inspection")
        value: object = json.loads(record, object_pairs_hook=_ty_fields)
    except (OSError, UnicodeError, ValueError, RecursionError) as exc:
        return Err("cannot read coverage text handoff: " + str(exc))
    census = ownership.guarded_census(context.root)
    declarations = (
        _coverage_declarations(census.value, context.family)
        if isinstance(census, Ok)
        else Err("source census unavailable")
    )
    if isinstance(declarations, Err):
        return declarations
    expected = coverage_commands(
        sys.executable, context.root, context.directory, declarations.value[1]
    )[-1]
    match value:
        case {
            "nonce": str() as nonce,
            "root": str() as root,
            "command": list() as command,
            "code": int() as code,
            "stdout": str() as stdout,
            "stderr": str() as stderr,
            **extra,
        } if not extra and nonce == context.nonce and root == str(context.root):
            floor = coverage_text_floor(Output(code, stdout, stderr))
            canonical = json.dumps(value, sort_keys=True).encode("utf-8")
            return (
                Ok(record)
                if isinstance(floor, Ok)
                and tuple(command) == expected
                and canonical == record
                else Err("invalid coverage text command or record")
            )
        case _:
            return Err("invalid coverage text identity or fields")


def _coverage_text_retained_values(
    record: bytes, raw: bytes, version: str
) -> Result[tuple[int, str, tuple[coverage_hosts.CoverageFact, ...]], str]:
    """Parse the retained transcript and JSON facts for independent comparison."""
    try:
        transcript: object = json.loads(record, object_pairs_hook=_ty_fields)
        facts = coverage_hosts.parse_report(raw.decode("utf-8"), version)
    except (UnicodeError, ValueError, RecursionError):
        return Err("coverage text supporting evidence is malformed")
    match transcript:
        case {
            "code": int() as code,
            "stdout": str() as stdout,
            "stderr": str() as stderr,
        }:
            observed = coverage_text_floor(Output(code, stdout, stderr))
        case _:
            return Err("coverage text transcript is malformed")
    return (
        Ok((code, observed.value, facts.value))
        if isinstance(facts, Ok) and isinstance(observed, Ok)
        else Err("coverage text supporting evidence is invalid")
    )


def coverage_text_retained_agreement(
    context: CheckRun, directory: Path, output: str, record: bytes
) -> Result[None, str]:
    """Independently join sealed report output, coverage facts and substeps."""
    finalizers = sealed_finalizer_observation(directory, context.nonce, output)
    if isinstance(finalizers, Err):
        return finalizers
    statuses = dict(finalizers.value.outcomes)
    if any(
        statuses[name]
        for name in ("coverage-observation", "tool-outcomes", "tool-substeps")
    ):
        return Err("coverage text supporting handoff failed")
    coverage_sealed = verify_coverage_handoff(directory, context.nonce, output)
    tools_sealed = verify_tool_results_handoff(directory, context.nonce, output)
    if isinstance(coverage_sealed, Err) or isinstance(tools_sealed, Err):
        return Err("coverage text supporting handoff is invalid")
    census = ownership.guarded_census(context.root)
    declarations = (
        _coverage_declarations(census.value, context.family)
        if isinstance(census, Ok)
        else Err("source census unavailable")
    )
    pair = _coverage_handoff_files(directory, context.nonce)
    tools = _read_sealed_tool_results(directory, context.nonce)
    if isinstance(declarations, Err) or isinstance(pair, Err) or isinstance(tools, Err):
        return Err("coverage text supporting evidence unavailable")
    values = _coverage_text_retained_values(
        record, pair.value[1], declarations.value[0]
    )
    if isinstance(values, Err):
        return values
    code, observation, facts = values.value
    steps = tuple(codes for name, codes in tools.value[1].outcomes if name == "pytest")
    gaps = any(item.missing_statements or item.missing_branches for item in facts)
    return (
        Ok(None)
        if len(steps) == 1
        and len(steps[0]) == phase_reports.PYTEST_FULL_STEPS
        and steps[0][1] == 0
        and steps[0][2] == code
        and (observation == "floor") == gaps
        else Err("coverage text disagrees with retained facts or substeps")
    )


def verify_coverage_text_handoff(
    context: CheckRun, directory: Path, output: str
) -> Result[None, str]:
    """Verify the original report transcript before and after retention."""
    finalizers = sealed_finalizer_observation(directory, context.nonce, output)
    if isinstance(finalizers, Err):
        return finalizers
    statuses = dict(finalizers.value.outcomes)
    if statuses["coverage-text-observation"]:
        return Ok(None)
    lines = output.splitlines()
    markers = tuple(line for line in lines if line.startswith(COVERAGE_TEXT_SEAL + " "))
    offset = (
        3
        + int(not statuses["mutant-killers"])
        + int(not statuses["coverage-observation"])
        + int(not statuses["ruff-observation"])
        + int(not statuses["python-commands"])
        + int(not statuses["ruff-format-observation"])
        + int(not statuses["tool-outcomes"] and not statuses["tool-substeps"])
        + int(not statuses["pytest-manifest"])
        + int(not statuses["oracle-outcomes"] and not statuses["oracle-details"])
        + int(not statuses["host-observation"])
        + int(not statuses["native-observation"])
        + int(not statuses["ty-observation"])
    )
    if len(markers) != 1 or len(lines) < offset or markers[0] != lines[-offset]:
        return Err("missing or ambiguous coverage text handoff")
    record = _coverage_text_handoff(context, directory)
    if isinstance(record, Err):
        return record
    if coverage_text_seal(context.nonce, record.value) != markers[0]:
        return Err("coverage text handoff digest mismatch")
    return coverage_text_retained_agreement(context, directory, output, record.value)


def ty_observation_seal(nonce: str, record: bytes) -> str:
    """Bind the original type-checker record to the current child run."""
    return f"{TY_OBSERVATION_SEAL} {nonce} {hashlib.sha256(record).hexdigest()}"


def _ty_handoff_record(directory: Path, nonce: str, root: Path) -> Result[bytes, str]:
    """Read and structurally validate the private type-checker handoff."""
    path = directory / "ty-observation.json"
    try:
        before = path.lstat()
        if (
            path.is_symlink()
            or before.st_nlink != 1
            or not stat.S_ISREG(before.st_mode)
        ):
            return Err("ty handoff is not a private regular file")
        record = path.read_bytes()
        after = path.lstat()
        if (
            path.is_symlink()
            or after.st_nlink != 1
            or (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino)
            or path.read_bytes() != record
        ):
            return Err("ty handoff changed during inspection")
        value: object = json.loads(record, object_pairs_hook=_ty_fields)
    except (OSError, UnicodeError, ValueError, RecursionError) as exc:
        return Err("cannot read ty handoff: " + str(exc))
    match value:
        case {
            "nonce": str() as found_nonce,
            "root": str() as found_root,
            "code": int() as code,
            "stdout": str() as stdout,
            "stderr": str() as stderr,
            **extra,
        } if not extra and found_nonce == nonce and found_root == str(root):
            parsed = parse_ty_output(root, Output(code, stdout, stderr))
            canonical = json.dumps(value, sort_keys=True).encode("utf-8")
            return (
                Ok(record)
                if isinstance(parsed, Ok) and canonical == record
                else Err("invalid ty handoff record")
            )
        case _:
            return Err("invalid ty handoff identity or fields")


def verify_ty_handoff(
    directory: Path, nonce: str, output: str, root: Path
) -> Result[None, str]:
    """Verify original type diagnostics before and after report retention."""
    finalizers = sealed_finalizer_observation(directory, nonce, output)
    if isinstance(finalizers, Err):
        return finalizers
    statuses = dict(finalizers.value.outcomes)
    if statuses["ty-observation"]:
        return Ok(None)
    lines = output.splitlines()
    markers = tuple(
        line for line in lines if line.startswith(TY_OBSERVATION_SEAL + " ")
    )
    offset = (
        3
        + int(not statuses["mutant-killers"])
        + int(not statuses["coverage-observation"])
        + int(not statuses["ruff-observation"])
        + int(not statuses["python-commands"])
        + int(not statuses["ruff-format-observation"])
        + int(not statuses["tool-outcomes"] and not statuses["tool-substeps"])
        + int(not statuses["pytest-manifest"])
        + int(not statuses["oracle-outcomes"] and not statuses["oracle-details"])
        + int(not statuses["host-observation"])
        + int(not statuses["native-observation"])
    )
    if len(markers) != 1 or len(lines) < offset or markers[0] != lines[-offset]:
        return Err("missing or ambiguous ty handoff")
    record = _ty_handoff_record(directory, nonce, root)
    if isinstance(record, Err):
        return record
    return (
        Ok(None)
        if ty_observation_seal(nonce, record.value) == markers[0]
        else Err("ty handoff digest mismatch")
    )


def native_observation_seal(nonce: str, snapshot: NativeSnapshot) -> Result[str, str]:
    """Seal native case execution, case sources and captured native source bytes."""
    source_digest = native_source_digest(snapshot)
    manifest = snapshot.manifest
    if isinstance(source_digest, Err):
        return source_digest
    if not nonce or manifest.nonce != nonce:
        return Err("native observation nonce mismatch")
    payload = json.dumps(
        {
            "nonce": nonce,
            "native_nonce": manifest.nonce,
            "native_collected": sorted(manifest.collected),
            "native_executed": sorted(manifest.executed),
            "native_passed": sorted(manifest.passed),
            "native_forbidden": manifest.forbidden,
            "native_classes": manifest.classes,
            "case_sources": snapshot.sources,
            "native_source_digest": source_digest.value,
            "native_artifacts": snapshot.artifacts,
        },
        sort_keys=True,
    ).encode("utf-8")
    return Ok(
        f"{NATIVE_OBSERVATION_SEAL} {nonce} {hashlib.sha256(payload).hexdigest()}"
    )


def _native_handoff_observation(
    context: CheckRun, directory: Path
) -> Result[NativeSnapshot, str]:
    """Join private native reports to a fresh guarded checkout census."""
    entries = ownership.guarded_census(context.root)
    if isinstance(entries, Err):
        return Err("native handoff source census unavailable")
    paths = tuple(
        directory / name
        for name in (
            "haskell-manifest.json",
            "haskell-sources.json",
            "tasty.xml",
            "native-artifacts.json",
        )
    )
    try:
        before = tuple(path.lstat() for path in paths)
        if any(
            path.is_symlink() or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
            for path, info in zip(paths, before, strict=True)
        ):
            return Err("native handoff is not a private regular file")
        observed = native_snapshot(directory, context.nonce, entries.value)
        after = tuple(path.lstat() for path in paths)
        if any(
            path.is_symlink()
            or later.st_nlink != 1
            or (earlier.st_dev, earlier.st_ino) != (later.st_dev, later.st_ino)
            for path, earlier, later in zip(paths, before, after, strict=True)
        ):
            return Err("native handoff changed during inspection")
    except OSError as exc:
        return Err("cannot read native handoff: " + str(exc))
    return observed


def _selected_native_artifacts(
    context: CheckRun,
) -> Result[tuple[tuple[str, str, str], ...], str]:
    """Independently resolve the same offline selection as the child gate."""
    env = environment(os.environ, context.directory, context.nonce)
    cache = directories(context.family, env, Path.home()).cache
    host = hostfacts.current(cache)
    if host.family != context.family:
        return Err("native artifact host family differs")
    captured = replace(
        host,
        cwd=context.root,
        environment=tuple(env.items()),
        interactive=False,
    )
    selected = haskell.selected_artifact_facts(
        captured, context.root / "src/agentctl/haskell"
    )
    return Err(selected.error.message) if isinstance(selected, Err) else selected


def verify_native_handoff(
    context: CheckRun, directory: Path, output: str
) -> Result[None, str]:
    """Verify native execution and source observations on both report copies."""
    finalizers = sealed_finalizer_observation(directory, context.nonce, output)
    if isinstance(finalizers, Err):
        return finalizers
    statuses = dict(finalizers.value.outcomes)
    if statuses["native-observation"]:
        return Ok(None)
    if statuses["write-guard"] or statuses["containment"]:
        return Err("native handoff lacks a trustworthy checkout guard")
    lines = output.splitlines()
    markers = tuple(
        line for line in lines if line.startswith(NATIVE_OBSERVATION_SEAL + " ")
    )
    offset = (
        3
        + int(not statuses["mutant-killers"])
        + int(not statuses["coverage-observation"])
        + int(not statuses["ruff-observation"])
        + int(not statuses["python-commands"])
        + int(not statuses["ruff-format-observation"])
        + int(not statuses["tool-outcomes"] and not statuses["tool-substeps"])
        + int(not statuses["pytest-manifest"])
        + int(not statuses["oracle-outcomes"] and not statuses["oracle-details"])
        + int(not statuses["host-observation"])
    )
    if len(markers) != 1 or len(lines) < offset or markers[0] != lines[-offset]:
        return Err("missing or ambiguous native handoff")
    observed = _native_handoff_observation(context, directory)
    sealed = (
        observed
        if isinstance(observed, Err)
        else native_observation_seal(context.nonce, observed.value)
    )
    checked = (
        sealed
        if isinstance(sealed, Err)
        else (
            Ok(None)
            if sealed.value == markers[0]
            else Err("native handoff digest mismatch")
        )
    )
    if isinstance(checked, Err) or isinstance(observed, Err):
        return checked
    selected = _selected_native_artifacts(context)
    return (
        selected
        if isinstance(selected, Err)
        else Ok(None)
        if selected.value == observed.value.artifacts
        else Err("native artifact selection differs")
    )


def host_observation_seal(nonce: str, facts: lanes.HostFacts) -> str:
    """Seal the original native host and capability observations."""
    payload = json.dumps(
        {"nonce": nonce, "facts": asdict(facts)}, sort_keys=True
    ).encode("utf-8")
    return f"{HOST_OBSERVATION_SEAL} {nonce} {hashlib.sha256(payload).hexdigest()}"


def _host_handoff_observation(
    directory: Path, nonce: str
) -> Result[lanes.HostFacts, str]:
    """Read the private host observation without accepting replacement or links."""
    path = directory / "host.json"
    try:
        before = path.lstat()
        if (
            path.is_symlink()
            or not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
        ):
            return Err("host handoff is not a private regular file")
        observed = host_observation(directory, nonce)
        after = path.lstat()
        if (
            path.is_symlink()
            or after.st_nlink != 1
            or (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino)
        ):
            return Err("host handoff changed during inspection")
    except OSError as exc:
        return Err("cannot read host handoff: " + str(exc))
    return observed


def verify_host_handoff(directory: Path, nonce: str, output: str) -> Result[None, str]:
    """Verify the original host observation before and after report retention."""
    finalizers = sealed_finalizer_observation(directory, nonce, output)
    if isinstance(finalizers, Err):
        return finalizers
    statuses = dict(finalizers.value.outcomes)
    if statuses["host-observation"]:
        return Ok(None)
    lines = output.splitlines()
    markers = tuple(
        line for line in lines if line.startswith(HOST_OBSERVATION_SEAL + " ")
    )
    offset = (
        3
        + int(not statuses["mutant-killers"])
        + int(not statuses["coverage-observation"])
        + int(not statuses["ruff-observation"])
        + int(not statuses["python-commands"])
        + int(not statuses["ruff-format-observation"])
        + int(not statuses["tool-outcomes"] and not statuses["tool-substeps"])
        + int(not statuses["pytest-manifest"])
        + int(not statuses["oracle-outcomes"] and not statuses["oracle-details"])
    )
    if len(markers) != 1 or len(lines) < offset or markers[0] != lines[-offset]:
        return Err("missing or ambiguous host handoff")
    observed = _host_handoff_observation(directory, nonce)
    if isinstance(observed, Err):
        return observed
    return (
        Ok(None)
        if host_observation_seal(nonce, observed.value) == markers[0]
        else Err("host handoff digest mismatch")
    )


def oracle_results_seal(
    nonce: str, outcomes: evidence.LegEvidence, details: evidence.OracleDetails
) -> str:
    """Seal the original oracle statuses and attributable diagnostics together."""
    payload = json.dumps(
        {
            "nonce": nonce,
            "outcomes_nonce": outcomes.nonce,
            "outcomes": outcomes.outcomes,
            "details_nonce": details.nonce,
            "sources": details.sources,
            "issues": details.issues,
        },
        sort_keys=True,
    ).encode("utf-8")
    return f"{ORACLE_RESULTS_SEAL} {nonce} {hashlib.sha256(payload).hexdigest()}"


def _oracle_handoff_observations(
    directory: Path, nonce: str
) -> Result[tuple[evidence.LegEvidence, evidence.OracleDetails], str]:
    """Read both private oracle records without accepting replacement or links."""
    paths = (directory / "oracle-outcomes.json", directory / "oracle-details.json")
    try:
        before = tuple(path.lstat() for path in paths)
        if any(
            path.is_symlink() or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
            for path, info in zip(paths, before, strict=True)
        ):
            return Err("oracle handoff is not a private regular file")
        outcomes = oracle_observation(directory, nonce)
        details = evidence.read_oracle_details(paths[1], nonce)
        after = tuple(path.lstat() for path in paths)
        if any(
            path.is_symlink()
            or later.st_nlink != 1
            or (earlier.st_dev, earlier.st_ino) != (later.st_dev, later.st_ino)
            for path, earlier, later in zip(paths, before, after, strict=True)
        ):
            return Err("oracle handoff changed during inspection")
    except OSError as exc:
        return Err("cannot read oracle handoff: " + str(exc))
    if isinstance(outcomes, Err) or isinstance(details, Err):
        return Err("oracle handoff records unavailable or invalid")
    return Ok((outcomes.value, details.value))


def verify_oracle_handoff(
    directory: Path, nonce: str, output: str
) -> Result[None, str]:
    """Verify original oracle observations before and after report retention."""
    finalizers = sealed_finalizer_observation(directory, nonce, output)
    if isinstance(finalizers, Err):
        return finalizers
    statuses = dict(finalizers.value.outcomes)
    if statuses["oracle-outcomes"] or statuses["oracle-details"]:
        return Ok(None)
    lines = output.splitlines()
    markers = tuple(
        line for line in lines if line.startswith(ORACLE_RESULTS_SEAL + " ")
    )
    offset = (
        3
        + int(not statuses["mutant-killers"])
        + int(not statuses["coverage-observation"])
        + int(not statuses["ruff-observation"])
        + int(not statuses["python-commands"])
        + int(not statuses["ruff-format-observation"])
        + int(not statuses["tool-outcomes"] and not statuses["tool-substeps"])
        + int(not statuses["pytest-manifest"])
    )
    if len(markers) != 1 or len(lines) < offset or markers[0] != lines[-offset]:
        return Err("missing or ambiguous oracle handoff")
    observed = _oracle_handoff_observations(directory, nonce)
    if isinstance(observed, Err):
        return observed
    return (
        Ok(None)
        if oracle_results_seal(nonce, *observed.value) == markers[0]
        else Err("oracle handoff digest mismatch")
    )


def pytest_manifest_seal(nonce: str, manifest: evidence.RunEvidence) -> str:
    """Seal the original collected, executed, passed and forbidden observations."""
    payload = json.dumps(
        {
            "nonce": nonce,
            "manifest_nonce": manifest.nonce,
            "collected": sorted(manifest.collected),
            "executed": sorted(manifest.executed),
            "passed": sorted(manifest.passed),
            "forbidden": manifest.forbidden,
            "classes": manifest.classes,
        },
        sort_keys=True,
    ).encode("utf-8")
    return f"{PYTEST_OBSERVATION_SEAL} {nonce} {hashlib.sha256(payload).hexdigest()}"


def _pytest_handoff_observation(
    directory: Path, nonce: str
) -> Result[evidence.RunEvidence, str]:
    """Read one private pytest observation without accepting replacement."""
    path = directory / "pytest-manifest.json"
    try:
        before = path.lstat()
        if (
            path.is_symlink()
            or not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
        ):
            return Err("pytest handoff is not a private regular file")
        observed = pytest_observation(directory, nonce)
        after = path.lstat()
        if (
            path.is_symlink()
            or after.st_nlink != 1
            or (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino)
        ):
            return Err("pytest handoff changed during inspection")
    except OSError as exc:
        return Err("cannot read pytest handoff: " + str(exc))
    return observed


def verify_pytest_handoff(
    directory: Path, nonce: str, output: str
) -> Result[None, str]:
    """Verify the original pytest observation before and after report retention."""
    finalizers = sealed_finalizer_observation(directory, nonce, output)
    if isinstance(finalizers, Err):
        return finalizers
    statuses = dict(finalizers.value.outcomes)
    if statuses["pytest-manifest"]:
        return Ok(None)
    lines = output.splitlines()
    markers = tuple(
        line for line in lines if line.startswith(PYTEST_OBSERVATION_SEAL + " ")
    )
    offset = (
        3
        + int(not statuses["mutant-killers"])
        + int(not statuses["coverage-observation"])
        + int(not statuses["ruff-observation"])
        + int(not statuses["python-commands"])
        + int(not statuses["ruff-format-observation"])
        + int(not statuses["tool-outcomes"] and not statuses["tool-substeps"])
    )
    if len(markers) != 1 or len(lines) < offset or markers[0] != lines[-offset]:
        return Err("missing or ambiguous pytest handoff")
    observed = _pytest_handoff_observation(directory, nonce)
    if isinstance(observed, Err):
        return observed
    return (
        Ok(None)
        if pytest_manifest_seal(nonce, observed.value) == markers[0]
        else Err("pytest handoff digest mismatch")
    )


def tool_results_seal(
    nonce: str, outcomes: evidence.LegEvidence, substeps: evidence.ToolSubsteps
) -> str:
    """Seal the original ordered tool and subprocess outcomes together."""
    payload = json.dumps(
        {"nonce": nonce, "outcomes": outcomes.outcomes, "substeps": substeps.outcomes},
        sort_keys=True,
    ).encode("utf-8")
    return f"{TOOL_RESULTS_SEAL} {nonce} {hashlib.sha256(payload).hexdigest()}"


def _tool_record_rows(path: Path, nonce: str) -> Result[tuple[object, ...], str]:
    """Read one private closed tool record with stable file identity and bytes."""
    try:
        before = path.lstat()
        if (
            path.is_symlink()
            or not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
        ):
            return Err("tool results handoff is not a private regular file")
        contents = path.read_bytes()
        after = path.lstat()
        if (
            path.is_symlink()
            or after.st_nlink != 1
            or (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino)
            or path.read_bytes() != contents
        ):
            return Err("tool results handoff changed during inspection")
        value: object = json.loads(contents, object_pairs_hook=_ruff_record_fields)
    except (OSError, ValueError, UnicodeError, RecursionError) as exc:
        return Err("cannot read tool results handoff: " + str(exc))
    match value:
        case {"nonce": str() as actual, "outcomes": list() as rows, **extra} if (
            not extra and nonce and actual == nonce
        ):
            return Ok(tuple(rows))
        case _:
            return Err("invalid tool results handoff identity")


def _read_sealed_tool_results(
    directory: Path, nonce: str
) -> Result[tuple[evidence.LegEvidence, evidence.ToolSubsteps], str]:
    """Parse full ordered status records, retaining names and every substep."""
    outcomes_path, substeps_path = (
        directory / "tool-outcomes.json",
        directory / "tool-substeps.json",
    )
    rows, steps = (
        _tool_record_rows(outcomes_path, nonce),
        _tool_record_rows(substeps_path, nonce),
    )
    if isinstance(rows, Err) or isinstance(steps, Err):
        return Err("tool results handoff records unavailable")
    names: tuple[str, ...] = ()
    limits: tuple[tuple[str, int], ...] = ()
    for row in rows.value:
        match row:
            case [str() as name, int() as code] if name and not isinstance(code, bool):
                names += (name,)
            case _:
                return Err("invalid tool results handoff outcomes")
    for row in steps.value:
        match row:
            case [str() as name, list() as codes] if name and codes:
                limits += ((name, len(codes)),)
            case _:
                return Err("invalid tool results handoff substeps")
    if tuple(name for name in names if name in {item for item, _ in limits}) != tuple(
        name for name, _ in limits
    ):
        return Err("tool results handoff schedules differ")
    parsed, parsed_steps = (
        evidence.read_legs(outcomes_path, nonce, names),
        evidence.read_tool_substeps(substeps_path, nonce, limits),
    )
    if isinstance(parsed, Err) or isinstance(parsed_steps, Err):
        return Err("invalid tool results handoff records")
    return Ok((parsed.value, parsed_steps.value))


def verify_tool_results_handoff(
    directory: Path, nonce: str, output: str
) -> Result[None, str]:
    """Check original tool outcomes against both live and retained records."""
    finalizers = sealed_finalizer_observation(directory, nonce, output)
    if isinstance(finalizers, Err):
        return finalizers
    statuses = dict(finalizers.value.outcomes)
    if statuses["tool-outcomes"] or statuses["tool-substeps"]:
        return Ok(None)
    lines = output.splitlines()
    markers = tuple(line for line in lines if line.startswith(TOOL_RESULTS_SEAL + " "))
    offset = (
        3
        + int(not statuses["mutant-killers"])
        + int(not statuses["coverage-observation"])
        + int(not statuses["ruff-observation"])
        + int(not statuses["python-commands"])
        + int(not statuses["ruff-format-observation"])
    )
    if len(markers) != 1 or len(lines) < offset or markers[0] != lines[-offset]:
        return Err("missing or ambiguous tool results handoff")
    parsed = _read_sealed_tool_results(directory, nonce)
    if isinstance(parsed, Err):
        return parsed
    return (
        Ok(None)
        if tool_results_seal(nonce, *parsed.value) == markers[0]
        else Err("tool results handoff digest mismatch")
    )


def _parse_python_commands_record(
    nonce: str, root: Path, record: bytes
) -> Result[None, str]:
    try:
        value: object = json.loads(record, object_pairs_hook=_ruff_record_fields)
    except (ValueError, UnicodeError, RecursionError):
        return Err("invalid Python command handoff JSON")
    match value:
        case {
            "nonce": str() as actual,
            "root": str() as root_text,
            "commands": list() as commands,
            "source_digest": str() as source_digest,
            **extra,
        } if (
            not extra
            and actual == nonce
            and bool(nonce)
            and len(source_digest) == SHA256_HEX_LENGTH
            and all(character in "0123456789abcdef" for character in source_digest)
        ):
            pass
        case _:
            return Err("invalid Python command handoff identity")
    if json.dumps(value, sort_keys=True).encode("utf-8") != record or root != Path(
        root_text
    ):
        return Err("noncanonical Python command handoff")
    names: tuple[str, ...] = ()
    for row in commands:
        match row:
            case [str() as name, list() as attempts] if attempts:
                names += (name,)
            case _:
                return Err("invalid Python command handoff rows")
        for command in attempts:
            if (
                not isinstance(command, list)
                or not command
                or any(not isinstance(arg, str) or not arg for arg in command)
            ):
                return Err("invalid Python command handoff arguments")
    return (
        Ok(None)
        if names == PYTHON_COMMAND_NAMES
        else Err("invalid Python command handoff names")
    )


def _python_commands_handoff_record(
    directory: Path, nonce: str, root: Path
) -> Result[bytes, str]:
    path = directory / "python-commands.json"
    try:
        before = path.lstat()
        if (
            path.is_symlink()
            or not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
        ):
            return Err("Python command handoff is not a private regular file")
        record = path.read_bytes()
        after = path.lstat()
        if (
            path.is_symlink()
            or (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino)
            or after.st_nlink != 1
            or path.read_bytes() != record
        ):
            return Err("Python command handoff changed during inspection")
    except OSError as exc:
        return Err("cannot read Python command handoff: " + str(exc))
    parsed = _parse_python_commands_record(nonce, root, record)
    return parsed if isinstance(parsed, Err) else Ok(record)


def verify_python_commands_handoff(
    directory: Path, nonce: str, output: str, root: Path
) -> Result[None, str]:
    """Verify the original command observation before and after retention."""
    finalizers = sealed_finalizer_observation(directory, nonce, output)
    if isinstance(finalizers, Err):
        return finalizers
    statuses = dict(finalizers.value.outcomes)
    if statuses["python-commands"]:
        return Ok(None)
    lines = output.splitlines()
    markers = tuple(
        line for line in lines if line.startswith(PYTHON_COMMANDS_SEAL + " ")
    )
    offset = (
        3
        + int(not statuses["mutant-killers"])
        + int(not statuses["coverage-observation"])
        + int(not statuses["ruff-observation"])
    )
    if len(markers) != 1 or len(lines) < offset or markers[0] != lines[-offset]:
        return Err("missing or ambiguous Python command handoff")
    record = _python_commands_handoff_record(directory, nonce, root)
    if isinstance(record, Err):
        return record
    return (
        Ok(None)
        if python_commands_seal(nonce, record.value) == markers[0]
        else Err("Python command handoff digest mismatch")
    )


def _decoded_python_command_rows(
    record: bytes,
) -> Result[tuple[tuple[str, tuple[tuple[str, ...], ...]], ...], str]:
    """Recover already schema-checked command rows for the parent plan join."""
    try:
        value: object = json.loads(record, object_pairs_hook=_ruff_record_fields)
    except (ValueError, UnicodeError, RecursionError):
        return Err("invalid Python command rows")
    match value:
        case {"commands": list() as rows}:
            pass
        case _:
            return Err("invalid Python command rows")
    decoded: tuple[tuple[str, tuple[tuple[str, ...], ...]], ...] = ()
    for row in rows:
        match row:
            case [str() as name, list() as attempts] if attempts:
                pass
            case _:
                return Err("invalid Python command rows")
        if any(
            not isinstance(argv, list)
            or not argv
            or any(not isinstance(arg, str) or not arg for arg in argv)
            for argv in attempts
        ):
            return Err("invalid Python command arguments")
        decoded += (
            (name, tuple(tuple(str(arg) for arg in argv) for argv in attempts)),
        )
    return Ok(decoded)


def _python_plan_from_record(context: CheckRun, record: bytes) -> Result[None, str]:
    """Compare decoded child attempts with the guarded parent-side plan."""
    found, census = targets(context.root), ownership.guarded_census(context.root)
    if isinstance(found, Err) or isinstance(census, Err):
        return Err("Python command plan census unavailable")
    source_digest = evidence.digest_census(census.value)
    value: object = json.loads(record, object_pairs_hook=_ruff_record_fields)
    if (
        isinstance(source_digest, Err)
        or not isinstance(value, dict)
        or value.get("source_digest") != source_digest.value
    ):
        return Err("Python command source census changed")
    verified = python_target_census(context.root, found.value, census.value)
    declarations = _coverage_declarations(census.value, context.family)
    commands = _decoded_python_command_rows(record)
    if (
        isinstance(verified, Err)
        or isinstance(declarations, Err)
        or isinstance(commands, Err)
    ):
        return Err("Python command plan inputs invalid")
    expected = python_legs(
        sys.executable,
        context.root,
        found.value,
        context.directory,
        declarations.value[1],
    )
    if tuple(name for name, _ in commands.value) != tuple(leg.name for leg in expected):
        return Err("Python command plan names differ")
    if any(
        attempts != (leg.argv, *leg.after)[: len(attempts)]
        for leg, (_name, attempts) in zip(expected, commands.value, strict=True)
    ):
        return Err("Python command plan differs from captured attempts")
    return Ok(None)


def verify_python_plan_handoff(context: CheckRun, output: str) -> Result[None, str]:
    """Recheck sealed Python attempts against a fresh guarded parent census.

    This requires the caller to verify the child's command seal first. It does
    not authenticate other tool outcomes or issue a phase verdict.
    """
    finalizers = sealed_finalizer_observation(context.directory, context.nonce, output)
    if isinstance(finalizers, Err):
        return finalizers
    statuses = dict(finalizers.value.outcomes)
    if statuses["python-commands"]:
        return Ok(None)
    if statuses["write-guard"] or statuses["containment"]:
        return Err("Python command plan lacks a trustworthy checkout guard")
    record = _python_commands_handoff_record(
        context.directory, context.nonce, context.root
    )
    return (
        record
        if isinstance(record, Err)
        else Err("Python command plan changed after handoff")
        if python_commands_seal(context.nonce, record.value) not in output.splitlines()
        else _python_plan_from_record(context, record.value)
    )


def finalizer_observation(
    run_dir: Path, nonce: str
) -> Result[evidence.LegEvidence, str]:
    """Read the exact nonce-bound finalizer record without following links."""
    path = run_dir / "finalizer-outcomes.json"
    if path.is_symlink():
        return Err("finalizer record is a symlink")
    try:
        if not stat.S_ISREG(path.lstat().st_mode):
            return Err("finalizer record is not a regular file")
    except OSError as exc:
        return Err("finalizer record unavailable: " + str(exc))
    contents = _read_finalizer_handoff(path)
    return (
        contents
        if isinstance(contents, Err)
        else _parse_finalizer_observation(contents.value, nonce)
    )


def _parse_finalizer_observation(
    contents: bytes, nonce: str
) -> Result[evidence.LegEvidence, str]:
    """Apply the closed finalizer schedule to already verified file bytes."""
    observed = evidence.parse_legs_bytes(contents, nonce, FINALIZER_NAMES[:-1])
    if isinstance(observed, Err):
        return Err(observed.error.message)
    if any(code not in {0, 1} for _name, code in observed.value.outcomes):
        return Err("invalid finalizer status")
    return observed


def _read_finalizer_handoff(path: Path) -> Result[bytes, str]:
    """Read one private finalizer record through its checked nonblocking handle."""
    try:
        if path.is_symlink() or path.is_junction():
            return Err("finalizer handoff record is a symlink")
        before = path.lstat()
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            return Err("finalizer handoff is not a private regular file")
        with open(path, "rb", opener=_open_private_handoff) as stream:
            opened = os.fstat(stream.fileno())
            if (
                not stat.S_ISREG(opened.st_mode)
                or opened.st_nlink != 1
                or (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino)
            ):
                return Err("finalizer handoff record changed during inspection")
            contents = stream.read()
            stream.seek(0)
            repeated = stream.read()
            closed = os.fstat(stream.fileno())
        after = path.lstat()
        if (
            path.is_symlink()
            or path.is_junction()
            or (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino)
            or after.st_nlink != 1
            or (opened.st_dev, opened.st_ino, opened.st_nlink)
            != (closed.st_dev, closed.st_ino, closed.st_nlink)
            or repeated != contents
        ):
            return Err("finalizer handoff record changed during inspection")
    except OSError as exc:
        return Err("cannot read finalizer handoff: " + str(exc))
    return Ok(contents)


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


def sealed_finalizer_observation(
    directory: Path, nonce: str, output: str
) -> Result[evidence.LegEvidence, str]:
    """Bind the finalizer statuses actually consumed to the unique child seal."""
    marker = _parse_finalizer_seal(nonce, output)
    observed = finalizer_observation(directory, nonce)
    if isinstance(marker, Err) or isinstance(observed, Err):
        return Err("sealed finalizer observation unavailable")
    return (
        observed
        if finalizer_seal(observed.value) == marker.value
        else Err("finalizer observation changed after handoff")
    )


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
    return _verify_finalizer_file(directory, nonce, marker.value, observed.value)


def _verify_finalizer_file(
    directory: Path, nonce: str, marker: str, observed: evidence.LegEvidence
) -> Result[None, str]:
    """Recheck a private finalizer record against its original observation."""
    contents = _read_finalizer_handoff(directory / "finalizer-outcomes.json")
    if isinstance(contents, Err):
        return contents
    first = contents.value
    checked = evidence.parse_legs_bytes(first, nonce, FINALIZER_NAMES[:-1])
    if isinstance(checked, Err) or checked.value != observed:
        return Err("finalizer handoff record changed during inspection")
    digest = marker.rsplit(" ", 1)[1]
    return (
        Err("finalizer handoff digest mismatch")
        if hashlib.sha256(first).hexdigest() != digest
        or finalizer_seal(observed) != marker
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
        fallback = observed_scoped_mutant_mapping(entries, records, sources.value)
        owners = fallback if isinstance(fallback, Err) else Ok(fallback.value.owners)
    if isinstance(owners, Err):
        click.echo("native-ownership-observation: " + owners.error, err=True)
        return 1
    if expected is None or owners.value != expected:
        click.echo("native-ownership-observation: captured owners differ", err=True)
        return 1
    click.echo("native-ownership-observation: attributed (not a verdict)")
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
    if inputs.source_entries is None or owners is None:
        return 0
    captured = native_snapshot(run_dir, nonce, inputs.source_entries)
    if isinstance(captured, Err):
        click.echo("native-attribution: " + captured.error, err=True)
    scoped = (
        native_failure_observations(
            captured.value, nonce, declarations, inputs.records, owners
        )
        if isinstance(captured, Ok)
        else unavailable_native_scopes(
            inputs.source_entries, declarations, inputs.records, owners
        )
    )
    if isinstance(captured, Ok) and any(guards):
        return 0
    if isinstance(scoped, Err):
        click.echo("native-attribution: " + scoped.error, err=True)
        return 1
    for number, failures in scoped.value:
        for failure in sorted(failures):
            click.echo(
                f"native-attribution phase {number}: {failure} (not a verdict)",
                err=True,
            )
    return int(isinstance(captured, Err))


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
    state = directories(family, os.environ, Path.home()).state
    binding = virtualbox_binding.check_shared_checkout(
        root, family, state / virtualbox_binding.RECEIPT_NAME
    )
    return (
        *inspect(root),
        *inspect_socket(run_dir, family),
        *(
            ("VirtualBox binding: " + binding.error,)
            if isinstance(binding, Err)
            else ()
        ),
    )


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


def readiness_observation(nonce: object, readiness: object) -> Result[str, str]:
    """Encode the original readiness messages as one nonce-bound output line."""
    if (
        not isinstance(nonce, str)
        or not nonce
        or not isinstance(readiness, tuple)
        or any(not isinstance(message, str) or not message for message in readiness)
    ):
        return Err("invalid readiness observation")
    return Ok(
        READINESS_OBSERVATION
        + " "
        + json.dumps({"nonce": nonce, "messages": readiness}, sort_keys=True)
    )


def _readiness_fields(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """Reject duplicate fields in the readiness handoff."""
    return _ruff_fields(pairs)


def parse_readiness_observation(
    nonce: str, output: str
) -> Result[tuple[str, ...], str]:
    """Require one canonical readiness observation for this exact run."""
    prefix = READINESS_OBSERVATION + " "
    markers = tuple(line for line in output.splitlines() if line.startswith(prefix))
    if not nonce or len(markers) != 1:
        return Err("missing or ambiguous readiness observation")
    try:
        value: object = json.loads(
            markers[0][len(prefix) :], object_pairs_hook=_readiness_fields
        )
    except (ValueError, UnicodeError, RecursionError):
        return Err("invalid readiness observation")
    match value:
        case {"nonce": str() as observed, "messages": list() as messages, **extra} if (
            not extra
            and observed == nonce
            and all(isinstance(message, str) and message for message in messages)
        ):
            result = tuple(message for message in messages if isinstance(message, str))
        case _:
            return Err("invalid readiness observation")
    encoded = readiness_observation(nonce, result)
    return (
        Ok(result)
        if isinstance(encoded, Ok) and encoded.value == markers[0]
        else Err("noncanonical readiness observation")
    )


def emit_readiness_observation(
    nonce: str, readiness: tuple[str, ...], code: int
) -> int:
    """Emit the child's original readiness without hiding an earlier failure."""
    observed = readiness_observation(nonce, readiness)
    if isinstance(observed, Err):
        click.echo(observed.error, err=True)
        return 1
    click.echo(observed.value)
    return code


def emit_handoff_seals(
    nonce: str,
    recorded: Result[evidence.LegEvidence, str],
    phase_record: Result[bytes, str],
    reports: tuple[
        Result[mutant_report.Report, str] | None,
        Result[CoverageSnapshot, str] | None,
    ],
    codes: tuple[int, int, int, int],
) -> None:
    """Emit original observations only after their records remain intact."""
    killers, coverage = reports
    record_code, phase_record_code, killer_code, coverage_code = codes
    if isinstance(recorded, Ok) and not record_code:
        if isinstance(phase_record, Ok) and not phase_record_code:
            if isinstance(coverage, Ok) and not coverage_code:
                click.echo(
                    coverage_seal(nonce, coverage.value.record, coverage.value.report)
                )
            if isinstance(killers, Ok) and not killer_code:
                click.echo(killer_seal(nonce, killers.value))
            click.echo(provisional_seal(nonce, phase_record.value))
        click.echo(finalizer_seal(recorded.value))


def emit_ruff_handoff(
    nonce: str,
    recorded: Result[evidence.LegEvidence, str],
    phase_record: Result[bytes, str],
    ruff: Result[RuffSnapshot, str] | None,
    codes: tuple[int, int, int],
) -> None:
    """Emit the original Ruff seal only when its supporting records survived."""
    if (
        isinstance(recorded, Ok)
        and isinstance(phase_record, Ok)
        and isinstance(ruff, Ok)
        and not any(codes)
    ):
        click.echo(ruff_seal(nonce, ruff.value.record))


def emit_python_commands_handoff(
    nonce: str,
    recorded: Result[evidence.LegEvidence, str],
    phase_record: Result[bytes, str],
    commands: Result[PythonCommandsSnapshot, str] | None,
    codes: tuple[int, int, int],
) -> None:
    """Emit the command seal only after its supporting records survive."""
    if (
        isinstance(recorded, Ok)
        and isinstance(phase_record, Ok)
        and isinstance(commands, Ok)
        and all(code == 0 for code in codes)
    ):
        click.echo(python_commands_seal(nonce, commands.value.record))


def emit_coverage_text_handoff(
    nonce: str,
    recorded: Result[evidence.LegEvidence, str],
    phase_record: Result[bytes, str],
    transcript: Result[CoverageTextSnapshot, str] | None,
    codes: tuple[int, int, int],
) -> None:
    """Seal the coverage report transcript after its finalizer succeeds."""
    if (
        isinstance(recorded, Ok)
        and isinstance(phase_record, Ok)
        and isinstance(transcript, Ok)
        and all(code == 0 for code in codes)
    ):
        click.echo(coverage_text_seal(nonce, transcript.value.record))


def emit_ty_handoff(
    nonce: str,
    recorded: Result[evidence.LegEvidence, str],
    phase_record: Result[bytes, str],
    ty: Result[TySnapshot, str] | None,
    codes: tuple[int, int, int],
) -> None:
    """Seal the captured type-checker record after its finalizer succeeds."""
    if (
        isinstance(recorded, Ok)
        and isinstance(phase_record, Ok)
        and isinstance(ty, Ok)
        and all(code == 0 for code in codes)
    ):
        click.echo(ty_observation_seal(nonce, ty.value.record))


def emit_native_handoff(
    nonce: str,
    recorded: Result[evidence.LegEvidence, str],
    phase_record: Result[bytes, str],
    native: Result[NativeSnapshot, str] | None,
    codes: tuple[int, int, int],
) -> None:
    """Seal the original native observation only when its finalizer succeeded."""
    if (
        isinstance(recorded, Ok)
        and isinstance(phase_record, Ok)
        and isinstance(native, Ok)
        and all(code == 0 for code in codes)
    ):
        marker = native_observation_seal(nonce, native.value)
        if isinstance(marker, Ok):
            click.echo(marker.value)


def emit_host_handoff(
    nonce: str,
    recorded: Result[evidence.LegEvidence, str],
    phase_record: Result[bytes, str],
    host: Result[lanes.HostFacts, str] | None,
    codes: tuple[int, int, int],
) -> None:
    """Seal the original host observation only when its finalizer succeeded."""
    if (
        isinstance(recorded, Ok)
        and isinstance(phase_record, Ok)
        and isinstance(host, Ok)
        and all(code == 0 for code in codes)
    ):
        click.echo(host_observation_seal(nonce, host.value))


def emit_oracle_handoff(
    nonce: str,
    recorded: Result[evidence.LegEvidence, str],
    phase_record: Result[bytes, str],
    validation: ValidationOutcome,
    codes: tuple[int, int, int, int],
) -> None:
    """Seal the original oracle outcomes and details after both finalizers."""
    if (
        isinstance(recorded, Ok)
        and isinstance(phase_record, Ok)
        and isinstance(validation.oracle, Ok)
        and isinstance(validation.oracle_details, Ok)
        and all(code == 0 for code in codes)
    ):
        click.echo(
            oracle_results_seal(
                nonce, validation.oracle.value, validation.oracle_details.value
            )
        )


def emit_pytest_handoff(
    nonce: str,
    recorded: Result[evidence.LegEvidence, str],
    phase_record: Result[bytes, str],
    pytest_run: Result[evidence.RunEvidence, str] | None,
    codes: tuple[int, int, int],
) -> None:
    """Seal the original pytest manifest only when its finalizer succeeded."""
    if (
        isinstance(recorded, Ok)
        and isinstance(phase_record, Ok)
        and isinstance(pytest_run, Ok)
        and all(code == 0 for code in codes)
    ):
        click.echo(pytest_manifest_seal(nonce, pytest_run.value))


def emit_tool_results_handoff(
    nonce: str,
    recorded: Result[evidence.LegEvidence, str],
    phase_record: Result[bytes, str],
    validation: ValidationOutcome,
    codes: tuple[int, int, int, int],
) -> None:
    """Emit original tool observations only after their finalizers succeed."""
    if (
        isinstance(recorded, Ok)
        and isinstance(phase_record, Ok)
        and isinstance(validation.tools, Ok)
        and isinstance(validation.substeps, Ok)
        and all(code == 0 for code in codes)
    ):
        click.echo(
            tool_results_seal(nonce, validation.tools.value, validation.substeps.value)
        )


def emit_ruff_format_handoff(
    nonce: str,
    recorded: Result[evidence.LegEvidence, str],
    phase_record: Result[bytes, str],
    observed: Result[RuffSnapshot, str] | None,
    codes: tuple[int, int, int],
) -> None:
    """Seal a formatter observation only when all supporting records survive."""
    if (
        isinstance(recorded, Ok)
        and isinstance(phase_record, Ok)
        and isinstance(observed, Ok)
        and all(code == 0 for code in codes)
    ):
        click.echo(ruff_format_seal(nonce, observed.value.record))


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
        code = readiness_result(
            validation.code or validation.initial_oracle_details, readiness
        )
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
    (
        coverage_after_finalizers,
        ruff_after_finalizers,
        commands_after_finalizers,
        format_after_finalizers,
        ty_after_finalizers,
        coverage_text_after_finalizers,
    ) = (
        coverage_snapshot_unchanged(run_dir, nonce, validation.coverage),
        ruff_snapshot_unchanged(run_dir, nonce, validation.ruff),
        python_commands_unchanged(run_dir, nonce, root, validation.python_commands),
        ruff_snapshot_unchanged(
            run_dir,
            nonce,
            validation.ruff_format,
            filename="ruff-format-observation.json",
        ),
        ty_snapshot_unchanged(run_dir, nonce, validation.ty),
        coverage_text_unchanged(run_dir, nonce, validation.coverage_text),
    )
    code = (
        code
        or coverage_after_finalizers
        or ruff_after_finalizers
        or commands_after_finalizers
        or format_after_finalizers
        or ty_after_finalizers
        or coverage_text_after_finalizers
        or validation.validation_integrity
    )
    finalizer_statuses = (
        ("ratchet", ratchet_code),
        ("containment", finalization.containment),
        ("write-guard", finalization.write_guard),
        ("oracle-outcomes", oracle_after_finalizers),
        ("oracle-details", details_after_finalizers),
        ("initial-oracle-details", validation.initial_oracle_details),
        ("validation-integrity", validation.validation_integrity),
        ("tool-outcomes", tools_after_finalizers),
        ("python-commands", commands_after_finalizers),
        ("tool-substeps", substeps_after_finalizers),
        ("pytest-manifest", pytest_after_finalizers),
        ("mutant-killers", killers_after_finalizers),
        ("native-observation", native_after_finalizers),
        ("host-observation", host_after_finalizers),
        ("ruff-format-observation", format_after_finalizers),
        ("ruff-observation", ruff_after_finalizers),
        ("ty-observation", ty_after_finalizers),
        ("coverage-text-observation", coverage_text_after_finalizers),
        ("coverage-observation", coverage_after_finalizers),
    )
    recorded = record_finalizers(run_dir, nonce, finalizer_statuses)
    record_code = finalizer_outcomes_unchanged(run_dir, nonce, recorded)
    code = code or record_code
    observations = provisional_finalizer_failures(
        validation.phase_observations,
        (*finalizer_statuses, ("finalizer-record", record_code)),
        localized_native=localizable_native_finalizer(
            validation,
            run_dir,
            nonce,
            (*finalizer_statuses, ("finalizer-record", record_code)),
        ),
    )
    phase_record = record_provisional_phases(run_dir, nonce, observations)
    phase_record_code = provisional_phases_unchanged(run_dir, phase_record)
    code = code or phase_record_code
    provisional_code = report_provisional_phases(observations)
    code = code or provisional_code
    status, _, _, _, _, _, _, _, _, _ = (
        summarize(
            CheckRun(root, run_dir, nonce, family),
            emit_readiness_observation(nonce, readiness, code),
            validation.host,
        ),
        emit_coverage_text_handoff(
            nonce,
            recorded,
            phase_record,
            validation.coverage_text,
            (record_code, phase_record_code, coverage_text_after_finalizers),
        ),
        emit_ty_handoff(
            nonce,
            recorded,
            phase_record,
            validation.ty,
            (record_code, phase_record_code, ty_after_finalizers),
        ),
        emit_native_handoff(
            nonce,
            recorded,
            phase_record,
            validation.native,
            (record_code, phase_record_code, native_after_finalizers),
        ),
        emit_host_handoff(
            nonce,
            recorded,
            phase_record,
            validation.host,
            (record_code, phase_record_code, host_after_finalizers),
        ),
        emit_oracle_handoff(
            nonce,
            recorded,
            phase_record,
            validation,
            (
                record_code,
                phase_record_code,
                oracle_after_finalizers,
                details_after_finalizers,
            ),
        ),
        emit_pytest_handoff(
            nonce,
            recorded,
            phase_record,
            validation.pytest,
            (record_code, phase_record_code, pytest_after_finalizers),
        ),
        emit_tool_results_handoff(
            nonce,
            recorded,
            phase_record,
            validation,
            (
                record_code,
                phase_record_code,
                tools_after_finalizers,
                substeps_after_finalizers,
            ),
        ),
        emit_ruff_format_handoff(
            nonce,
            recorded,
            phase_record,
            validation.ruff_format,
            (record_code, phase_record_code, format_after_finalizers),
        ),
        emit_python_commands_handoff(
            nonce,
            recorded,
            phase_record,
            validation.python_commands,
            (record_code, phase_record_code, commands_after_finalizers),
        ),
    )
    emit_ruff_handoff(
        nonce,
        recorded,
        phase_record,
        validation.ruff,
        (record_code, phase_record_code, ruff_after_finalizers),
    )
    emit_handoff_seals(
        nonce,
        recorded,
        phase_record,
        (validation.killers, validation.coverage),
        (
            record_code,
            phase_record_code,
            killers_after_finalizers,
            coverage_after_finalizers,
        ),
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
            "native-artifacts.json",
            "tool-outcomes.json",
            "python-commands.json",
            "python-runtime.json",
            "python-child.json",
            "tool-substeps.json",
            "finalizer-outcomes.json",
            "provisional-phases.json",
            "coverage-report.json",
            "coverage-raw.json",
            "coverage-text.json",
            "ruff-observation.json",
            "ruff-format-observation.json",
            "ty-observation.json",
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
        before = context.directory.lstat()
        if (
            context.directory.is_symlink()
            or context.directory.is_junction()
            or not stat.S_ISDIR(before.st_mode)
            or before.st_dev <= 0
            or before.st_ino <= 0
            or context.directory_identity != (before.st_dev, before.st_ino)
            or target.parent != allowed
            or not target.name.startswith("agentctl-check-")
            or target.is_relative_to(context.root.resolve())
        ):
            return Err("temporary run boundary is invalid")
        contained = writeguard.containment(target, context.nonce, context.family)
        if isinstance(contained, Err):
            return Err("temporary run retained: " + contained.error.message)
        after = context.directory.lstat()
        if (
            context.directory.is_symlink()
            or context.directory.is_junction()
            or context.directory.resolve(strict=True) != target
            or (after.st_dev, after.st_ino) != context.directory_identity
            or not stat.S_ISDIR(after.st_mode)
        ):
            return Err("temporary run changed during containment")
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


def retained_stream_snapshot(
    directory: Path,
) -> Result[tuple[tuple[int, int, bytes], ...], str]:
    """Read the retained output streams without accepting links or replacement."""
    paths = (directory / "stdout.txt", directory / "stderr.txt")
    try:
        before = tuple(path.lstat() for path in paths)
        contents = tuple(_read_provisional_handoff(path) for path in paths)
        after = tuple(path.lstat() for path in paths)
    except OSError:
        return Err("retained output streams unavailable")
    if any(
        isinstance(value, Err)
        or (first.st_dev, first.st_ino) != (last.st_dev, last.st_ino)
        or last.st_nlink != 1
        for first, last, value in zip(before, after, contents, strict=True)
    ):
        return Err("retained output streams changed")
    return Ok(
        tuple(
            (item.st_dev, item.st_ino, value.value)
            for item, value in zip(after, contents, strict=True)
            if isinstance(value, Ok)
        )
    )


def retained_artifact_snapshot(
    directory: Path,
) -> Result[tuple[tuple[str, int, int, str], ...], str]:
    """Capture every retained file and its identity across one private walk."""
    try:
        before = directory.lstat()
        if (
            directory.is_symlink()
            or directory.is_junction()
            or not stat.S_ISDIR(before.st_mode)
        ):
            return Err("retained report directory unavailable")
        paths = tuple(sorted(directory.iterdir(), key=lambda path: path.name))
        captured: tuple[tuple[str, int, int, str], ...] = ()
        for path in paths:
            if path.name in {"stdout.txt", "stderr.txt"}:
                continue
            first = path.lstat()
            contents = _read_provisional_handoff(path)
            last = path.lstat()
            if (
                isinstance(contents, Err)
                or (first.st_dev, first.st_ino) != (last.st_dev, last.st_ino)
                or last.st_nlink != 1
            ):
                return Err("retained report artifact changed")
            captured += (
                (
                    path.name,
                    last.st_dev,
                    last.st_ino,
                    hashlib.sha256(contents.value).hexdigest(),
                ),
            )
        after = directory.lstat()
        if (
            directory.is_symlink()
            or directory.is_junction()
            or (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino)
            or tuple(sorted(directory.iterdir(), key=lambda path: path.name)) != paths
        ):
            return Err("retained report directory changed")
    except OSError:
        return Err("retained report artifacts unavailable")
    return Ok(captured)


def verify_retained_artifacts(
    directory: Path,
    observed: Result[tuple[tuple[str, int, int, str], ...], str],
    prior: Result[None, str],
) -> Result[None, str]:
    """Preserve earlier errors while rejecting changes across report verification."""
    changed = (
        isinstance(observed, Err) or retained_artifact_snapshot(directory) != observed
    )
    return (
        Err(prior.error + "; retained report artifacts changed")
        if isinstance(prior, Err) and changed
        else prior
        if isinstance(prior, Err)
        else Err("retained report artifacts changed")
        if changed
        else Ok(None)
    )


def retained_report_snapshot(
    directory: Path, streams: tuple[str, str]
) -> Result[RetainedReportSnapshot, str]:
    """Capture the verified report and require its original output bytes."""
    output = retained_stream_snapshot(directory)
    artifacts = retained_artifact_snapshot(directory)
    if (
        isinstance(output, Err)
        or isinstance(artifacts, Err)
        or tuple(item[2] for item in output.value)
        != tuple(value.encode("utf-8") for value in streams)
    ):
        return Err("retained report snapshot unavailable")
    return Ok(RetainedReportSnapshot(output.value, artifacts.value))


def verify_retained_streams(
    directory: Path,
    streams: tuple[str, str],
    observed: Result[tuple[tuple[int, int, bytes], ...], str],
    prior: Result[None, str],
) -> Result[None, str]:
    """Require stable copied streams without hiding an earlier handoff failure."""
    expected = tuple(value.encode("utf-8") for value in streams)
    changed = (
        isinstance(observed, Err)
        or tuple(item[2] for item in observed.value) != expected
        or retained_stream_snapshot(directory) != observed
    )
    return (
        Err(prior.error + "; retained output streams changed")
        if isinstance(prior, Err) and changed
        else prior
        if isinstance(prior, Err)
        else Err("retained output streams changed")
        if changed
        else Ok(None)
    )


def _retained_verified_snapshot(
    streams: Result[tuple[tuple[int, int, bytes], ...], str],
    artifacts: Result[tuple[tuple[str, int, int, str], ...], str],
) -> RetainedReportSnapshot | None:
    """Carry the original verified values without rereading the report."""
    return (
        RetainedReportSnapshot(streams.value, artifacts.value)
        if isinstance(streams, Ok) and isinstance(artifacts, Ok)
        else None
    )


def _unverified_gate_retention(
    retained: Result[Path, str],
) -> Result[RetainedGateReport, str]:
    """Keep diagnostics when the child did not establish a verified handoff."""
    return (
        retained
        if isinstance(retained, Err)
        else Ok(RetainedGateReport(retained.value, None))
    )


def _retain_verified_gate_evidence(
    context: CheckRun,
    state: Path,
    streams: tuple[str, str],
    *,
    verify_handoff: bool,
) -> Result[RetainedGateReport, str]:
    """Retain a report and carry the exact snapshot checked against child seals."""
    retained = retain_gate_output(
        context.root, state, context.directory, context.nonce, streams
    )
    if isinstance(retained, Err) or not verify_handoff:
        return _unverified_gate_retention(retained)
    original_streams = retained_stream_snapshot(retained.value)
    original_artifacts = retained_artifact_snapshot(retained.value)
    checked = verify_finalizer_handoff(retained.value, context.nonce, streams[0])
    if isinstance(checked, Ok):
        checked = verify_provisional_handoff(retained.value, context.nonce, streams[0])
        checked = (
            checked
            if isinstance(checked, Err)
            else verify_provisional_finalizers(
                retained.value, context.nonce, streams[0]
            )
        )
    if isinstance(checked, Ok):
        checked = verify_killer_handoff(retained.value, context.nonce, streams[0])
    if isinstance(checked, Ok):
        checked = verify_coverage_handoff(retained.value, context.nonce, streams[0])
    if isinstance(checked, Ok):
        checked = verify_ruff_handoff(
            retained.value, context.nonce, streams[0], context.root
        )
    if isinstance(checked, Ok):
        checked = verify_python_commands_handoff(
            retained.value, context.nonce, streams[0], context.root
        )
        checked = (
            checked
            if isinstance(checked, Err)
            else verify_provisional_input_identities(
                context, retained.value, streams[0]
            )
        )
    if isinstance(checked, Ok):
        checked = verify_tool_results_handoff(retained.value, context.nonce, streams[0])
        checked = (
            checked
            if isinstance(checked, Err)
            else verify_pytest_handoff(retained.value, context.nonce, streams[0])
        )
        checked = (
            checked
            if isinstance(checked, Err)
            else verify_oracle_handoff(retained.value, context.nonce, streams[0])
        )
        checked = (
            checked
            if isinstance(checked, Err)
            else verify_host_handoff(retained.value, context.nonce, streams[0])
        )
        checked = (
            checked
            if isinstance(checked, Err)
            else verify_native_handoff(context, retained.value, streams[0])
        )
        checked = (
            checked
            if isinstance(checked, Err)
            else verify_ty_handoff(
                retained.value, context.nonce, streams[0], context.root
            )
        )
        checked = (
            checked
            if isinstance(checked, Err)
            else verify_coverage_text_handoff(context, retained.value, streams[0])
        )
        checked = (
            checked
            if isinstance(checked, Err)
            else verify_provisional_collection(context, retained.value, streams[0])
        )
        checked = (
            checked
            if isinstance(checked, Err)
            else verify_provisional_oracle(context, retained.value, streams[0])
        )
        checked = (
            checked
            if isinstance(checked, Err)
            else verify_provisional_host(context, retained.value, streams[0])
        )
        checked = (
            checked
            if isinstance(checked, Err)
            else verify_provisional_coverage(context, retained.value, streams[0])
        )
        checked = (
            checked
            if isinstance(checked, Err)
            else verify_provisional_static(context, retained.value, streams[0])
        )
        checked = (
            checked
            if isinstance(checked, Err)
            else verify_provisional_source(context, retained.value, streams[0])
        )
        checked = (
            checked
            if isinstance(checked, Err)
            else verify_provisional_prerequisites(context, retained.value, streams[0])
        )
        checked = (
            checked
            if isinstance(checked, Err)
            else verify_provisional_validation(context, retained.value, streams[0])
        )
        checked = (
            checked
            if isinstance(checked, Err)
            else verify_provisional_tools(context, retained.value, streams[0])
        )
    if isinstance(checked, Ok):
        checked = verify_ruff_format_handoff(
            retained.value, context.nonce, streams[0], context.root
        )
    receipt_inputs = (
        retained_receipt_inputs(context, retained.value, streams[0])
        if isinstance(checked, Ok)
        else None
    )
    checked = verify_retained_streams(
        retained.value, streams, original_streams, checked
    )
    checked = verify_retained_artifacts(retained.value, original_artifacts, checked)
    if isinstance(checked, Err):
        message = "finalizer handoff: " + checked.error
        saved = retain_handoff_failure(context.root, state, retained.value, message)
        return Err(message + ("; " + saved.error if isinstance(saved, Err) else ""))
    snapshot = _retained_verified_snapshot(original_streams, original_artifacts)
    return Ok(RetainedGateReport(retained.value, snapshot, receipt_inputs))


def retain_verified_gate_output(
    context: CheckRun,
    state: Path,
    streams: tuple[str, str],
    *,
    verify_handoff: bool,
) -> Result[Path, str]:
    """Retain the report path while preserving the verified-evidence result."""
    observed = _retain_verified_gate_evidence(
        context, state, streams, verify_handoff=verify_handoff
    )
    return observed if isinstance(observed, Err) else Ok(observed.value.directory)


def verify_python_handoffs(context: CheckRun, output: str) -> Result[None, str]:
    """Verify the child's command seal before independently joining its plan."""
    sealed = verify_python_commands_handoff(
        context.directory, context.nonce, output, context.root
    )
    checked = (
        sealed
        if isinstance(sealed, Err)
        else verify_python_plan_handoff(context, output)
    )
    phase_checked = (
        checked
        if isinstance(checked, Err)
        else verify_provisional_input_identities(context, context.directory, output)
    )
    tool_checked = (
        phase_checked
        if isinstance(phase_checked, Err)
        else verify_tool_results_handoff(context.directory, context.nonce, output)
    )
    pytest_checked = (
        tool_checked
        if isinstance(tool_checked, Err)
        else verify_pytest_handoff(context.directory, context.nonce, output)
    )
    oracle_checked = (
        pytest_checked
        if isinstance(pytest_checked, Err)
        else verify_oracle_handoff(context.directory, context.nonce, output)
    )
    host_checked = (
        oracle_checked
        if isinstance(oracle_checked, Err)
        else verify_host_handoff(context.directory, context.nonce, output)
    )
    native_checked = (
        host_checked
        if isinstance(host_checked, Err)
        else verify_native_handoff(context, context.directory, output)
    )
    ty_checked = (
        native_checked
        if isinstance(native_checked, Err)
        else verify_ty_handoff(context.directory, context.nonce, output, context.root)
    )
    coverage_checked = (
        ty_checked
        if isinstance(ty_checked, Err)
        else verify_coverage_text_handoff(context, context.directory, output)
    )
    collection_checked = (
        coverage_checked
        if isinstance(coverage_checked, Err)
        else verify_provisional_collection(context, context.directory, output)
    )
    oracle_checked = (
        collection_checked
        if isinstance(collection_checked, Err)
        else verify_provisional_oracle(context, context.directory, output)
    )
    host_phase_checked = (
        oracle_checked
        if isinstance(oracle_checked, Err)
        else verify_provisional_host(context, context.directory, output)
    )
    coverage_phase_checked = (
        host_phase_checked
        if isinstance(host_phase_checked, Err)
        else verify_provisional_coverage(context, context.directory, output)
    )
    static_checked = (
        coverage_phase_checked
        if isinstance(coverage_phase_checked, Err)
        else verify_provisional_static(context, context.directory, output)
    )
    source_checked = (
        static_checked
        if isinstance(static_checked, Err)
        else verify_provisional_source(context, context.directory, output)
    )
    prerequisites_checked = (
        source_checked
        if isinstance(source_checked, Err)
        else verify_provisional_prerequisites(context, context.directory, output)
    )
    validation_checked = (
        prerequisites_checked
        if isinstance(prerequisites_checked, Err)
        else verify_provisional_validation(context, context.directory, output)
    )
    return (
        validation_checked
        if isinstance(validation_checked, Err)
        else verify_provisional_tools(context, context.directory, output)
    )


def _successful_child_finalizers(context: CheckRun, output: str) -> bool:
    """Require a complete passing finalizer record for a successful child."""
    finalizers = sealed_finalizer_observation(context.directory, context.nonce, output)
    return isinstance(finalizers, Ok) and all(
        status == 0 for _name, status in finalizers.value.outcomes
    )


def _gate_interpreter_stat(info: os.stat_result) -> tuple[int, int, int, int]:
    """Keep the file identity and change attributes relevant to one observation."""
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)


def gate_interpreter_identity(path: Path) -> Result[GateInterpreterIdentity, str]:
    """Observe the selected interpreter's stable file identity and bytes."""
    try:
        selected = path.resolve(strict=True)
        before = selected.stat()
        if not stat.S_ISREG(before.st_mode):
            return Err("gate interpreter is not a regular file")
        with selected.open("rb") as stream:
            opened = os.fstat(stream.fileno())
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
            stream.seek(0)
            repeated = hashlib.file_digest(stream, "sha256").hexdigest()
            closed = os.fstat(stream.fileno())
        after = selected.stat()
        if (
            selected.is_symlink()
            or selected.is_junction()
            or path.resolve(strict=True) != selected
            or digest != repeated
            or before.st_ctime_ns != after.st_ctime_ns
            or opened.st_ctime_ns != closed.st_ctime_ns
            or any(
                _gate_interpreter_stat(item) != _gate_interpreter_stat(before)
                for item in (opened, closed, after)
            )
        ):
            return Err("gate interpreter changed during observation")
    except (OSError, RuntimeError, ValueError) as exc:
        return Err("cannot observe gate interpreter: " + str(exc))
    return Ok(
        GateInterpreterIdentity(
            selected,
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
            digest,
        )
    )


def record_gate_interpreter(
    directory: Path,
    nonce: str,
    path: Path,
    initial: Result[GateInterpreterIdentity, str],
) -> Result[bytes, str]:
    """Record only an interpreter observed unchanged across the child run."""
    final = gate_interpreter_identity(path)
    if not nonce or isinstance(initial, Err) or final != initial:
        return Err("gate interpreter identity unavailable or changed")
    facts = initial.value
    contents = json.dumps(
        {
            "nonce": nonce,
            "path": str(facts.path),
            "device": facts.device,
            "inode": facts.inode,
            "size": facts.size,
            "modified_ns": facts.modified_ns,
            "changed_ns": facts.changed_ns,
            "sha256": facts.sha256,
        },
        sort_keys=True,
    ).encode("utf-8")
    target = directory / "python-runtime.json"
    try:
        descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(contents)
        if _read_provisional_handoff(target) != Ok(contents):
            return Err("gate interpreter record changed")
    except OSError as exc:
        return Err("cannot record gate interpreter: " + str(exc))
    return Ok(contents)


def retained_gate_interpreter(
    report: RetainedGateReport, original: bytes
) -> Result[None, str]:
    """Join the parent's runtime record to the verified retained snapshot."""
    if report.snapshot is None:
        return Err("retained gate interpreter snapshot unavailable")
    observed = tuple(
        item[3]
        for item in report.snapshot.artifacts
        if item[0] == "python-runtime.json"
    )
    expected = hashlib.sha256(original).hexdigest()
    return (
        Ok(None)
        if observed == (expected,)
        else Err("retained gate interpreter record differs")
    )


def _gate_child_image(
    family: Family,
    output: Result[Output, SpawnError],
    selected: Result[GateInterpreterIdentity, str],
) -> Result[tuple[ProcessObservation, GateInterpreterIdentity], str]:
    """Join a live native child observation to the selected interpreter file."""
    if isinstance(output, Err) or isinstance(selected, Err):
        return Err("gate child image unavailable")
    observation = output.value.observation
    if observation is None:
        return Err("gate child image unavailable")
    if isinstance(observation, Err):
        return Err("gate child image unavailable: " + observation.error.message)
    process = observation.value
    if (
        process.family != family
        or isinstance(process.pid, bool)
        or isinstance(process.birth, bool)
        or process.pid <= 0
        or process.pid == os.getpid()
        or process.birth <= 0
        or not process.image.is_absolute()
    ):
        return Err("invalid gate child image identity")
    alternatives = (
        (selected.value.path, Path(sys.base_prefix) / "python.exe")
        if family == "Windows"
        else (selected.value.path,)
    )
    try:
        matches = any(
            process.image.samefile(path) for path in alternatives if path.is_file()
        )
    except OSError:
        return Err("cannot compare gate child image")
    image = gate_interpreter_identity(process.image)
    return (
        Err("gate child image differs from selected interpreter")
        if not matches or isinstance(image, Err)
        else _join_gate_child_file(process, image.value)
    )


def _join_gate_child_file(
    process: ProcessObservation, image: GateInterpreterIdentity
) -> Result[tuple[ProcessObservation, GateInterpreterIdentity], str]:
    """Require the post-run file to match the sample taken while the child waited."""
    facts = process.file
    if facts is None or (
        facts.device,
        facts.inode,
        facts.size,
        facts.modified_ns,
        facts.sha256,
    ) != (image.device, image.inode, image.size, image.modified_ns, image.sha256):
        return Err("gate child image changed after live observation")
    return Ok((process, image))


def record_gate_child(
    context: CheckRun,
    output: Result[Output, SpawnError],
    selected: Result[GateInterpreterIdentity, str],
) -> Result[bytes, str]:
    """Retain the parent's native child-image observation for this run."""
    if not context.nonce:
        return Err("gate child image nonce unavailable")
    observed = _gate_child_image(context.family, output, selected)
    if isinstance(observed, Err):
        return observed
    process, image = observed.value
    contents = json.dumps(
        {
            "nonce": context.nonce,
            "family": process.family,
            "pid": process.pid,
            "birth": process.birth,
            "image": str(image.path),
            "device": image.device,
            "inode": image.inode,
            "sha256": image.sha256,
        },
        sort_keys=True,
    ).encode("utf-8")
    target = context.directory / "python-child.json"
    try:
        descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(contents)
        if _read_provisional_handoff(target) != Ok(contents):
            return Err("gate child image record changed")
    except OSError as exc:
        return Err("cannot record gate child image: " + str(exc))
    return Ok(contents)


def retained_gate_child(
    report: RetainedGateReport, original: bytes
) -> Result[None, str]:
    """Join the live child-image record to the verified retained snapshot."""
    if report.snapshot is None:
        return Err("retained gate child snapshot unavailable")
    observed = tuple(
        item[3] for item in report.snapshot.artifacts if item[0] == "python-child.json"
    )
    return (
        Ok(None)
        if observed == (hashlib.sha256(original).hexdigest(),)
        else Err("retained gate child image record differs")
    )


def _gate_interpreter_failure(
    runtime: Result[bytes, str],
    streams: tuple[str, str],
    code: int,
    handoff: Result[None, str],
) -> tuple[tuple[str, str], int, Result[None, str]]:
    """Keep primary child diagnostics when interpreter evidence is unavailable."""
    return (
        (
            (streams[0], streams[1] + "gate interpreter: " + runtime.error + "\n"),
            1,
            Err("gate interpreter observation unavailable"),
        )
        if isinstance(runtime, Err)
        else (streams, code, handoff)
    )


def _join_retained_gate_interpreter(
    context: CheckRun,
    state: Path,
    report: Result[RetainedGateReport, str],
    runtime: Result[bytes, str],
    handoff: Result[None, str],
) -> Result[RetainedGateReport, str]:
    """Reject a retained report that differs from the parent's runtime record."""
    if isinstance(report, Err) or isinstance(runtime, Err) or isinstance(handoff, Err):
        return report
    joined = retained_gate_interpreter(report.value, runtime.value)
    if isinstance(joined, Ok):
        return report
    message = "gate interpreter handoff: " + joined.error
    saved = retain_handoff_failure(context.root, state, report.value.directory, message)
    return Err(
        message
        + "; report: "
        + str(report.value.directory)
        + ("; " + saved.error if isinstance(saved, Err) else "")
    )


def _gate_child_failure(
    child: Result[bytes, str],
    streams: tuple[str, str],
    code: int,
    handoff: Result[None, str],
) -> tuple[tuple[str, str], int, Result[None, str]]:
    """Keep the primary child output when its native image was not observed."""
    return (
        (
            (streams[0], streams[1] + "gate child: " + child.error + "\n"),
            1,
            Err("gate child image observation unavailable"),
        )
        if isinstance(child, Err)
        else (streams, code, handoff)
    )


def _join_retained_gate_child(
    context: CheckRun,
    state: Path,
    report: Result[RetainedGateReport, str],
    child: Result[bytes, str],
    handoff: Result[None, str],
) -> Result[RetainedGateReport, str]:
    """Reject a retained report that differs from the live child observation."""
    if isinstance(report, Err) or isinstance(child, Err) or isinstance(handoff, Err):
        return report
    joined = retained_gate_child(report.value, child.value)
    if isinstance(joined, Ok):
        return report
    message = "gate child handoff: " + joined.error
    saved = retain_handoff_failure(context.root, state, report.value.directory, message)
    return Err(
        message
        + "; report: "
        + str(report.value.directory)
        + ("; " + saved.error if isinstance(saved, Err) else "")
    )


def phase_candidate_record(
    inputs: ReceiptInputs,
    candidates: tuple[PhaseReceiptEvidence, ...],
    interpreter: GateInterpreterIdentity,
) -> Result[bytes, str]:
    """Encode the parent's provisional evidence without creating a receipt."""
    if (
        not inputs.nonce
        or len(inputs.source_digest) != SHA256_HEX_LENGTH
        or any(
            character not in "0123456789abcdef" for character in inputs.source_digest
        )
        or phase_receipt_evidence(inputs) != Ok(candidates)
    ):
        return Err("invalid phase candidate inputs")
    return Ok(
        json.dumps(
            {
                "version": 1,
                "status": "unverified",
                "nonce": inputs.nonce,
                "source_digest": inputs.source_digest,
                "host": asdict(inputs.host),
                "gate_interpreter": {
                    "path": str(interpreter.path),
                    "sha256": interpreter.sha256,
                },
                "native_artifacts": (
                    inputs.native.artifacts if inputs.native is not None else None
                ),
                "phases": [
                    {
                        "number": item.number,
                        "identity": item.identity,
                        "prerequisites": item.prerequisites,
                        "required_tests": sorted(item.required_tests),
                        "passed_tests": sorted(item.passed_tests),
                        "required_mutants": sorted(item.required_mutants),
                        "killed_mutants": sorted(item.killed_mutants),
                        "required_coverage": sorted(item.required_coverage),
                        "covered": sorted(item.covered),
                        "failures": sorted(item.failures),
                    }
                    for item in candidates
                ],
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    )


def retain_phase_candidates(
    context: CheckRun,
    state: Path,
    report: RetainedGateReport,
    streams: tuple[str, str],
    record: bytes,
) -> Result[RetainedGateReport, str]:
    """Add one provisional record while preserving the verified report snapshot."""
    if report.snapshot is None or not record:
        return Err("phase candidate snapshot or record unavailable")
    try:
        directory = report.directory.resolve(strict=True)
        expected = (state / "check-reports" / context.nonce).resolve(strict=True)
        if (
            not context.nonce
            or any(character not in "0123456789abcdef" for character in context.nonce)
            or report.directory.is_symlink()
            or report.directory.is_junction()
            or directory != expected
            or not directory.is_relative_to(state.resolve(strict=True))
            or directory.is_relative_to(context.root.resolve(strict=True))
            or retained_report_snapshot(directory, streams) != Ok(report.snapshot)
        ):
            return Err("phase candidate report boundary or snapshot differs")
        target = directory / "phase-candidates.json"
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(target, flags, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(record)
        info = target.lstat()
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_nlink != 1
            or _read_provisional_handoff(target) != Ok(record)
        ):
            return Err("phase candidate record changed during retention")
        after = retained_report_snapshot(directory, streams)
        expected_artifacts = tuple(
            sorted(
                (
                    *report.snapshot.artifacts,
                    (
                        target.name,
                        info.st_dev,
                        info.st_ino,
                        hashlib.sha256(record).hexdigest(),
                    ),
                )
            )
        )
        if (
            isinstance(after, Err)
            or after.value.streams != report.snapshot.streams
            or after.value.artifacts != expected_artifacts
        ):
            return Err("phase candidate report changed during retention")
        return Ok(replace(report, snapshot=after.value))
    except (OSError, RuntimeError, ValueError) as exc:
        return Err("cannot retain phase candidates: " + str(exc))


def _join_candidate_handoff(
    context: CheckRun,
    state: Path,
    report: Result[RetainedGateReport, str],
    streams: tuple[str, str],
    interpreter: Result[GateInterpreterIdentity, str],
) -> Result[RetainedGateReport, str]:
    """Retain candidates only while the verified source and report remain current."""
    if (
        isinstance(report, Err)
        or not isinstance(report.value.receipt_inputs, Ok)
        or isinstance(interpreter, Err)
    ):
        return report
    inputs = report.value.receipt_inputs.value
    candidates = phase_receipt_evidence(inputs)
    census = ownership.guarded_census(context.root)
    current = (
        isinstance(census, Ok)
        and census.value == inputs.entries
        and evidence.digest_census(census.value) == Ok(inputs.source_digest)
        and gate_interpreter_identity(Path(sys.executable)) == interpreter
    )
    record = (
        phase_candidate_record(inputs, candidates.value, interpreter.value)
        if current and isinstance(candidates, Ok)
        else Err("phase candidate source or observations changed")
    )
    retained = (
        retain_phase_candidates(context, state, report.value, streams, record.value)
        if isinstance(record, Ok)
        else record
    )
    if isinstance(retained, Ok):
        return retained
    message = "phase candidate handoff: " + retained.error
    saved = retain_handoff_failure(context.root, state, report.value.directory, message)
    return Err(
        message
        + "; report: "
        + str(report.value.directory)
        + ("; " + saved.error if isinstance(saved, Err) else "")
    )


def _observe_check_child(
    context: CheckRun, state: Path, *, assume_yes: bool
) -> CheckChildResult:
    """Run and retain one check before attempting temporary-root cleanup."""
    (context.directory / "ty-config").mkdir()
    interpreter = gate_interpreter_identity(Path(sys.executable))
    invocation = (
        "import sys; sys.stdin.readline() == sys.argv[3] + '\\n' or sys.exit(70); "
        "from pathlib import Path; "
        "from agentctl.check.steps import execute; import sys; "
        "sys.exit(execute(Path(sys.argv[1]), "
        "Path(sys.argv[2]), sys.argv[3], sys.argv[4], "
        "assume_yes=sys.argv[5] == 'yes'))"
    )
    result = run_observed(
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
        request=ObservationRequest(
            context.family, context.nonce + "\n", CHECK_TIMEOUT_SECONDS
        ),
    )
    runtime = record_gate_interpreter(
        context.directory, context.nonce, Path(sys.executable), interpreter
    )
    child = record_gate_child(context, result, interpreter)
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
            handoff = (
                handoff
                if isinstance(handoff, Err)
                else verify_provisional_finalizers(
                    context.directory, context.nonce, streams[0]
                )
            )
        if isinstance(handoff, Ok):
            handoff = verify_killer_handoff(
                context.directory, context.nonce, streams[0]
            )
        if isinstance(handoff, Ok):
            handoff = verify_coverage_handoff(
                context.directory, context.nonce, streams[0]
            )
        if isinstance(handoff, Ok):
            handoff = verify_ruff_handoff(
                context.directory, context.nonce, streams[0], context.root
            )
        if isinstance(handoff, Ok):
            handoff = verify_python_handoffs(context, streams[0])
        if isinstance(handoff, Ok):
            handoff = verify_ruff_format_handoff(
                context.directory, context.nonce, streams[0], context.root
            )
        if (
            isinstance(handoff, Ok)
            and code == 0
            and not _successful_child_finalizers(context, streams[0])
        ):
            handoff = Err("successful child has failed finalizers")
        if isinstance(handoff, Err):
            streams = (
                streams[0],
                streams[1] + "finalizer handoff: " + handoff.error + "\n",
            )
            code = 1
    streams, code, handoff = _gate_interpreter_failure(runtime, streams, code, handoff)
    streams, code, handoff = _gate_child_failure(child, streams, code, handoff)
    report = _retain_verified_gate_evidence(
        context,
        state,
        streams,
        verify_handoff=isinstance(result, Ok) and isinstance(handoff, Ok),
    )
    report = _join_retained_gate_interpreter(context, state, report, runtime, handoff)
    report = _join_retained_gate_child(context, state, report, child, handoff)
    report = _join_candidate_handoff(context, state, report, streams, interpreter)
    retained = report if isinstance(report, Err) else Ok(report.value.directory)
    inputs = report.value.receipt_inputs if isinstance(report, Ok) else None
    candidates = (
        phase_receipt_evidence(inputs.value) if isinstance(inputs, Ok) else inputs
    )
    return CheckChildResult(
        code,
        streams,
        retained,
        isinstance(result, Ok) and isinstance(handoff, Ok) and isinstance(retained, Ok),
        report.value.snapshot if isinstance(report, Ok) else None,
        interpreter.value
        if isinstance(runtime, Ok) and isinstance(interpreter, Ok)
        else None,
        inputs,
        candidates,
    )


def _relay_check_child(result: CheckChildResult, *, cleaned: bool) -> int:
    """Publish evidence only after trusted retention and successful cleanup."""
    trusted = result.trusted and cleaned and isinstance(result.retained, Ok)
    interpreter_changed = trusted and (
        result.interpreter is None
        or gate_interpreter_identity(Path(sys.executable)) != Ok(result.interpreter)
    )
    changed = (
        trusted
        and isinstance(result.retained, Ok)
        and (
            result.snapshot is None
            or retained_report_snapshot(result.retained.value, result.streams)
            != Ok(result.snapshot)
        )
    )
    trusted = trusted and not changed
    trusted = trusted and not interpreter_changed
    stdout = "".join(
        ("withheld unverified: " + line)
        if (
            (line.startswith("EVIDENCE ") and (not trusted or result.code != 0))
            or line.startswith("PHASE ")
        )
        else line
        for line in result.streams[0].splitlines(keepends=True)
    )
    emit_gate_output(stdout, result.streams[1])
    if changed:
        click.echo("retained report changed after verification", err=True)
    if interpreter_changed:
        click.echo("gate interpreter changed after execution", err=True)
    retained = result.retained
    if isinstance(retained, Err):
        click.echo(retained.error, err=True)
        return 1
    click.echo("check report: " + str(retained.value))
    if interpreter_changed:
        return 1
    return 1 if changed else result.code


def _run_check_child(context: CheckRun, state: Path, *, assume_yes: bool) -> int:
    """Run a child without publishing closure evidence before outer cleanup."""
    result = _observe_check_child(context, state, assume_yes=assume_yes)
    return _relay_check_child(result, cleaned=False)


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
            original = run_dir.lstat()
            context = CheckRun(
                root,
                run_dir,
                secrets.token_hex(16),
                family,
                (original.st_dev, original.st_ino),
            )
            observed = _observe_check_child(context, paths.state, assume_yes=assume_yes)
            cleaned = cleanup_run_root(context, temporary_root)
            if isinstance(cleaned, Err):
                _relay_check_child(observed, cleaned=False)
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
            code = _relay_check_child(observed, cleaned=True)
        except OSError as exc:
            click.echo("check: temporary storage failure: " + str(exc), err=True)
            return 1
        return code
