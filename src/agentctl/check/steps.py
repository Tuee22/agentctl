# Copyright (c) 2026 agentctl contributors.
"""Isolated orchestration for every introduced check step."""

import os
import secrets
import sys
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

import click

from agentctl import hostfacts
from agentctl.bootstrap.pins import load as load_pins
from agentctl.check import (
    evidence,
    haskell,
    identity,
    lanes,
    ratchet,
    style,
    writeguard,
)
from agentctl.check.legs import Leg, python_legs, targets, verdict
from agentctl.check.mutants import Mutant, corpus
from agentctl.check.plan_data import phases
from agentctl.check.preconditions import inspect, inspect_socket, single_run
from agentctl.check.prerequisites import inspect_prerequisites
from agentctl.check.toolchain import EnsureStep, inspect_toolchain, run_step
from agentctl.check.validator import closure
from agentctl.check.validator.docs import validate as docs
from agentctl.check.validator.plan import validate as plan
from agentctl.check.validator.source import configuration, forbidden_surfaces, sources
from agentctl.paths import Family, directories
from agentctl.process import run
from agentctl.result import Err

PYTHON_LEG_TIMEOUT_SECONDS = 2 * 60 * 60
CHECK_TIMEOUT_SECONDS = 8 * PYTHON_LEG_TIMEOUT_SECONDS

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


def environment(
    inherited: Mapping[str, str], run_dir: Path, nonce: str, *, tool: str = "check"
) -> dict[str, str]:
    """Scrub inherited controls and supply only run-owned tool settings."""
    return {
        **{key: value for key, value in inherited.items() if key in ENVIRONMENT},
        "LC_ALL": "C.UTF-8",
        "TMPDIR": str(run_dir),
        "TEMP": str(run_dir),
        "TMP": str(run_dir),
        "PYTHONPYCACHEPREFIX": str(run_dir / "bytecode"),
        **(
            {
                "XDG_CONFIG_HOME": str(run_dir / "ty-config"),
                "APPDATA": str(run_dir / "ty-config"),
            }
            if tool == "ty"
            else {}
        ),
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
        "AGENTCTL_CHECK_NONCE": nonce,
        "AGENTCTL_CHECK_MANIFEST": str(run_dir / "pytest-manifest.json"),
    }


def run_leg(root: Path, run_dir: Path, nonce: str, leg: Leg) -> int:
    """Run a tool and its required followups, stopping on the first failure."""
    for command in (leg.argv, *leg.after):
        result = run(
            list(command),
            cwd=root,
            env=environment(os.environ, run_dir, nonce, tool=leg.name),
            timeout=PYTHON_LEG_TIMEOUT_SECONDS,
        )
        if isinstance(result, Err):
            click.echo(f"{leg.name}: {result.error.message}", err=True)
            return 1
        click.echo(result.value.stdout, nl=False)
        click.echo(result.value.stderr, nl=False, err=True)
        if result.value.code:
            return result.value.code
    return 0


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
    """Require every introduced leg in order and report each unrun leg."""
    outcomes: tuple[tuple[str, int], ...] = ()
    for leg in legs:
        if isinstance(leg, EnsureStep):
            code = run_step(leg)
        elif isinstance(leg, haskell.HaskellStep):
            code = haskell.run_step(leg, run_dir, nonce)
        elif isinstance(leg, style.StyleStep):
            code = style.run_step(step=leg)
        elif isinstance(leg, identity.IdentityStep):
            code = identity.run_step(step=leg)
        else:
            code = run_leg(root, run_dir, nonce, leg)
        outcomes += ((leg.name, code),)
        click.echo(f"{leg.name}: {'pass' if code == 0 else 'FAIL'}")
        if code:
            break
    for missing in legs[len(outcomes) :]:
        click.echo(f"{missing.name}: not run", err=True)
    return 0 if legs and verdict(tuple(leg.name for leg in legs), outcomes) else 1


def oracle_check(root: Path, run_dir: Path, nonce: str) -> int:
    """Run the independent oracle loader in a separate interpreter."""
    program = (
        "from pathlib import Path; from tests.harness.oracle import check_tree; "
        "from tests.harness.host import bootstrap_before; "
        "import sys; problems = check_tree(Path(sys.argv[1])); "
        "bootstrap_before(Path(sys.argv[2]), sys.argv[3]) if not problems else None; "
        "sys.stderr.write('\\n'.join(problems)); sys.exit(bool(problems))"
    )
    result = run(
        [sys.executable, "-c", program, str(root), str(run_dir), nonce],
        cwd=root,
        env=environment(os.environ, run_dir, nonce),
    )
    if isinstance(result, Err):
        click.echo(result.error.message, err=True)
        return 1
    click.echo(result.value.stderr, nl=False, err=True)
    return result.value.code


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
    legs = python_legs(sys.executable, root, files, run_dir)
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


def validate_and_run(
    root: Path,
    run_dir: Path,
    nonce: str,
    family: Family,
    *,
    assume_yes: bool = False,
) -> int:
    """Run validators and tools, retaining an explicit failure for unrun legs."""
    found = targets(root)
    if isinstance(found, Err):
        click.echo(found.error, err=True)
        return 1
    problems = (
        *docs(root),
        *plan(root),
        *forbidden_surfaces(root),
        *sources(root),
        *configuration(root),
    )
    if problems:
        click.echo("\n".join(problems), err=True)
        return 1
    records = corpus(root)
    if isinstance(records, Err):
        click.echo(records.error.message, err=True)
        return 1
    completed = closure.static(root, records.value)
    if completed:
        click.echo("\n".join(completed), err=True)
        return 1
    click.echo(inapplicable_message(closure.inapplicable(root, phases(root))), nl=False)
    if oracle_check(root, run_dir, nonce):
        return 1
    code = run_tools(
        root,
        run_dir,
        nonce,
        pipeline(root, run_dir, found.value, family, assume_yes=assume_yes),
    )
    return code or post_run(root, run_dir, nonce, records.value)


def post_run(root: Path, run_dir: Path, nonce: str, records: tuple[Mutant, ...]) -> int:
    """Join complete fresh execution to every applicable completion declaration."""
    manifest = evidence.read_manifest(run_dir / "pytest-manifest.json")
    if isinstance(manifest, Err):
        click.echo("post-run-verifier: " + manifest.error.message, err=True)
        return 1
    verified = evidence.verify(
        manifest.value, nonce, tuple(record.identifier for record in records)
    )
    if isinstance(verified, Err):
        click.echo("post-run-verifier: " + verified.error.message, err=True)
        return 1
    combined = haskell.combined(run_dir, manifest.value, nonce)
    if isinstance(combined, Err):
        click.echo("post-run-verifier: " + combined.error.message, err=True)
        return 1
    declarations = phases(root)
    if not declarations:
        click.echo("post-run-verifier: empty plan target set", err=True)
        return 1
    problems = (
        *closure.cited_ids(declarations, combined.value),
        *closure.gate_integrity(root, declarations, records, combined.value),
    )
    if problems:
        click.echo(
            "post-run-verifier: " + ("\n".join(problems) or "empty plan target set"),
            err=True,
        )
        return 1
    click.echo("post-run-verifier: pass")
    return 0


def summarize(context: CheckRun, code: int) -> int:
    """Emit current lane observations and evidence only after integrity finalizers."""
    if code:
        return code
    host = lanes.read_host(context.directory / "host.json", context.nonce)
    if isinstance(host, Err):
        click.echo("lane-summary: " + host.error.message, err=True)
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
    """Ratchet only a passing tool run, preserving an earlier failure."""
    if code:
        return code
    baseline = ratchet.check(root)
    if isinstance(baseline, Err):
        click.echo("ratchet: " + baseline.error.message, err=True)
        return 1
    click.echo("ratchet: pass; " + baseline.value)
    return 0


def finalize(
    context: CheckRun,
    before: writeguard.Snapshot,
    code: int,
) -> int:
    """Inspect containment and the original subject after every tool run."""
    contained = writeguard.containment(context.directory, context.nonce, context.family)
    if isinstance(contained, Err):
        click.echo("containment: " + contained.error.message, err=True)
        code = 1
    after = writeguard.snapshot(context.root)
    if isinstance(after, Err):
        click.echo("write-guard-compare: " + after.error.message, err=True)
        code = 1
    elif changed := writeguard.compare(before, after.value):
        click.echo("write-guard-compare: changed " + ", ".join(changed), err=True)
        code = 1
    else:
        click.echo("write-guard-compare: pass")
    return code


def inspect_context(
    root: Path, run_dir: Path, family: Family, *, assume_yes: bool
) -> tuple[str, ...]:
    """Combine identity and prerequisite reports before the guarded execution starts."""
    problems = (*inspect(root), *inspect_socket(run_dir, family))
    if problems:
        return problems
    paths = directories(family, os.environ, Path.home())
    context = hostfacts.current(paths.cache, assume_yes=assume_yes)
    return (
        *inspect_prerequisites(
            replace(context, cache=run_dir / "prerequisite-probe", interactive=False)
        ),
        *inspect_toolchain(context, load_pins()),
    )


def execute(
    root: Path, run_dir: Path, nonce: str, family: Family, *, assume_yes: bool = False
) -> int:
    """Keep integrity finalizers active after every post-snapshot exit path."""
    problems = inspect_context(root, run_dir, family, assume_yes=assume_yes)
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
        code = verify_baseline(
            root, validate_and_run(root, run_dir, nonce, family, assume_yes=assume_yes)
        )
    finally:
        code = finalize(CheckRun(root, run_dir, nonce, family), before.value, code)
    return summarize(CheckRun(root, run_dir, nonce, family), code)


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
        with tempfile.TemporaryDirectory(prefix="agentctl-check-") as temporary:
            run_dir = Path(temporary)
            if run_dir.is_relative_to(root):
                click.echo(
                    "Set TMPDIR outside the checkout before running check.", err=True
                )
                return 1
            (run_dir / "ty-config").mkdir()
            nonce = secrets.token_hex(16)
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
                    str(root),
                    str(run_dir),
                    nonce,
                    family,
                    "yes" if assume_yes else "no",
                ],
                cwd=root,
                env=environment(os.environ, run_dir, nonce),
                timeout=CHECK_TIMEOUT_SECONDS,
            )
            if isinstance(result, Err):
                click.echo(result.error.message, err=True)
                return 1
            click.echo(result.value.stdout, nl=False)
            click.echo(result.value.stderr, nl=False, err=True)
            return result.value.code
