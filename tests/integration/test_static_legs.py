# Copyright (c) 2026 agentctl contributors.
"""Pinned tools reject copied negative fixtures and accept their twins."""

import json
import os
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from agentctl.check import steps
from agentctl.check.evidence import LegEvidence, ToolSubsteps, source_census
from agentctl.check.legs import Leg, python_legs
from agentctl.check.phase_reports import PhaseInputs
from agentctl.check.steps import (
    ProvisionalCapture,
    _run_leg_observed,
    _run_tools_observed,
    environment,
    parse_ruff_output,
    ruff_validation_attribution,
)
from agentctl.process import Output, run
from agentctl.result import Err, Ok

pytestmark = pytest.mark.evidence("real")


def test_cold_gate_tool_checks_do_not_install(root: Path, tmp_path: Path) -> None:
    """A cold gate refuses before any process or network preparation effect."""
    program = (
        "import sys\n"
        "from pathlib import Path\n"
        "from agentctl.bootstrap import build\n"
        "from agentctl.bootstrap.toolchain import Toolchain, record\n"
        "from agentctl.check.haskell import HaskellStep, run_step as haskell\n"
        "from agentctl.check.identity import IdentityStep, run_step as identity\n"
        "from agentctl.check.style import StyleStep, run_step as style\n"
        "from agentctl.check.toolchain import EnsureStep, run_step as toolchain\n"
        "from agentctl.result import Err, Ok\n"
        "from tests.harness.bootstrap import context, pins\n"
        "host = context(Path(sys.argv[1]))\n"
        "project = Path(sys.argv[2]) / 'src/agentctl/haskell'\n"
        "def audit(event, args):\n"
        "    if event in ('subprocess.Popen', 'socket.connect'):\n"
        "        raise RuntimeError('unexpected preparation effect: ' + event)\n"
        "sys.addaudithook(audit)\n"
        "assert toolchain(EnsureStep(host, Ok(pins()))) == 1\n"
        "assert style(StyleStep('fourmolu', host, project, Ok(pins()))) == 1\n"
        "assert style(StyleStep('hlint', host, project, Ok(pins()))) == 1\n"
        "assert not host.cache.exists()\n"
        "native = build.BuildContext(project, host.cache / 'build', host, "
        "Toolchain('/missing/ghc', '/missing/cabal'), "
        "options=('--offline',), prepared_index_only=True)\n"
        "assert isinstance(build.compile_target(native, 'all'), Err)\n"
        "assert not host.cache.exists()\n"
        "assert '--offline' in build.arguments(native, 'build', 'all')\n"
        "index = host.cache / 'cabal/packages/hackage.haskell.org/01-index.tar'\n"
        "index.parent.mkdir(parents=True)\n"
        "index.write_bytes(b'fixture')\n"
        "(host.cache / 'cabal/config').write_text('fixture')\n"
        "receipt = host.cache / 'cabal/agentctl-index-state'\n"
        "state = build.index_state(project)\n"
        "assert isinstance(state, Ok)\n"
        "receipt.write_text(state.value)\n"
        "assert build.verify_prepared_index(native) == Ok(None)\n"
        "receipt.write_text('stale')\n"
        "assert isinstance(build.verify_prepared_index(native), Err)\n"
        "tools = Toolchain(str(Path(sys.executable).resolve()), "
        "str(Path(sys.executable).resolve()))\n"
        "assert record(tools, host.cache) == Ok(tools)\n"
        "assert haskell(HaskellStep('cabal-build', host, project), "
        "host.cache / 'reports', 'nonce') == 1\n"
        "assert haskell(HaskellStep('cabal-test', host, project), "
        "host.cache / 'reports', 'nonce') == 1\n"
        "assert identity(IdentityStep(host, project, host.cache / 'data')) == 1\n"
    )
    result = run(
        [sys.executable, "-c", program, str(tmp_path / "private"), str(root)],
        cwd=root,
        env=os.environ,
    )
    assert isinstance(result, Ok)
    assert result.value.code == 0, result.value.stderr
    assert "prepare the pinned toolchain before check" in result.value.stderr


def test_real_binary_identity_refusal_stays_with_bootstrap(
    root: Path, tmp_path: Path
) -> None:
    """A real cold binary check fails without poisoning earlier source owners."""
    program = """
import sys
from pathlib import Path
from agentctl.check import identity, steps
from agentctl.result import Ok
from tests.harness.bootstrap import context
root, private = map(Path, sys.argv[1:])
host = context(private)
def audit(event, args):
    if event in ("subprocess.Popen", "socket.connect"):
        raise RuntimeError("unexpected preparation effect: " + event)
sys.addaudithook(audit)
status = identity.run_step(identity.IdentityStep(host, root / "src/agentctl/haskell",
                                                 private / "data"))
assert status == 1, "cold binary identity unexpectedly passed"
census = steps.ownership.guarded_census(root)
assert isinstance(census, Ok), census
text = steps._census_text(census.value, "src/agentctl/check/source_ownership.toml")
assert isinstance(text, Ok), text
manifest = steps.ownership.parse_manifest(text.value)
assert isinstance(manifest, Ok), manifest
phases = tuple(steps.phase_reports.PhaseInputs(phase.number, frozenset({"source"}),
    frozenset({"check"}), phase.prerequisites) for phase in manifest.value.phases)
initial = steps.ToolFailureAttribution(frozenset({steps.IDENTITY_FAILURE}),
    tuple((phase.number, frozenset()) for phase in phases))
result = steps.provisional_identity_tool_failures(census.value, phases, initial)
assert isinstance(result, Ok), result
scoped = dict(result.value.scoped)
assert not scoped[0] and not scoped[1], "real binary failure blocked earlier phases"
assert "binary-identity failed" in scoped[2], "real binary failure lost its owner"
assert not result.value.shared, "real binary failure remained shared"
"""
    result = run(
        [sys.executable, "-c", program, str(root), str(tmp_path / "private")],
        cwd=root,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    assert isinstance(result, Ok)
    assert result.value.code == 0, result.value.stderr


def _probe(
    root: Path, temporary: Path, tool: str, fixture: str, *, valid: bool
) -> Output:
    """Run the real leg with exactly one copied fixture outside the checkout."""
    source = root / "tests/fixtures/static_negative" / fixture
    (temporary / "pyproject.toml").write_bytes((root / "pyproject.toml").read_bytes())
    target = temporary / "subject.py"
    (temporary / "__init__.py").write_text("", encoding="utf-8")
    target.write_text(
        (source / ("valid.py.txt" if valid else "negative.py.txt")).read_text(
            encoding="utf-8"
        ),
        encoding="utf-8",
    )
    name = {"ty": "ty", "format": "ruff-format", "ruff": "ruff-check"}[tool]
    leg = next(
        leg
        for leg in python_legs(sys.executable, root, (str(target),), temporary)
        if leg.name == name
    )
    result = run(
        list(leg.argv),
        cwd=temporary,
        env=environment(os.environ, temporary, "static-control", tool=tool),
    )
    assert isinstance(result, Ok)
    return result.value


def test_ruff_fires_on_fixture(root: Path, tmp_path: Path) -> None:
    """Require the unused-import diagnostic and a completely clean twin."""
    negative = _probe(root, tmp_path, "ruff", "ruff", valid=False)
    assert negative.code != 0, "ruff leg did not reject its negative control"
    assert "F401" in negative.stdout
    assert _probe(root, tmp_path, "ruff", "ruff", valid=True).code == 0


def _assert_invalid_ruff_output(project: Path, temporary: Path, output: Output) -> None:
    assert isinstance(parse_ruff_output(project, replace(output, code=0)), Err), (
        "inconsistent Ruff status was accepted"
    )
    rows = json.loads(output.stdout)
    for bad in (
        "not json",
        json.dumps([{**rows[0], "filename": "relative.py"}]),
        json.dumps([{**rows[0], "filename": str(temporary / "outside.py")}]),
        json.dumps([{**rows[0], "location": {"row": True, "column": 1}}]),
        "[" + json.dumps(rows[0])[:-1] + ', "code": "F401"}]',
    ):
        assert isinstance(parse_ruff_output(project, Output(1, bad, "")), Err), (
            "invalid Ruff JSON was accepted"
        )
    assert isinstance(
        parse_ruff_output(project, replace(output, stderr="error")),
        Err,
    ), "Ruff stderr was ignored"
    assert isinstance(
        parse_ruff_output(project, replace(output, code=True)),
        Err,
    ), "boolean Ruff status was accepted"


def _assert_ruff_capture_integrity(run_dir: Path, captured: steps.RuffSnapshot) -> None:
    """Refuse overwritten, changed, replayed or replaced records."""
    original = Ok(captured)
    path = run_dir / "ruff-observation.json"
    assert steps.ruff_snapshot_unchanged(run_dir, captured.nonce, original) == 0
    assert isinstance(steps.record_ruff_snapshot(run_dir, captured), Err), (
        "Ruff capture overwrote an existing record"
    )
    assert steps.ruff_snapshot_unchanged(run_dir, "foreign", original) == 1, (
        "foreign Ruff nonce was accepted"
    )
    path.write_bytes(captured.record + b" ")
    assert steps.ruff_snapshot_unchanged(run_dir, captured.nonce, original) == 1, (
        "changed Ruff record was accepted"
    )
    path.write_bytes(captured.record)
    assert steps.ruff_snapshot_unchanged(run_dir, captured.nonce, original) == 0
    replacement = run_dir / "replacement.json"
    replacement.write_bytes(captured.record)
    replacement.replace(path)
    assert steps.ruff_snapshot_unchanged(run_dir, captured.nonce, original) == 1, (
        "replaced Ruff record was accepted"
    )


def _assert_ruff_parent_handoff(
    project: Path, first_run: Path, temporary: Path
) -> None:
    """Verify the copied record and detect post-copy tampering in a real process."""
    script = (
        "import json, sys\nfrom pathlib import Path\n"
        "from agentctl.check import steps\n"
        "from agentctl.foundation import Err, Ok\n"
        "from agentctl.foundation_process_values import Output\n"
        "root, original, run_dir, state = map(Path, sys.argv[1:5])\n"
        "nonce = 'abc123'; run_dir.mkdir()\n"
        "data = json.loads(original.read_text())\n"
        "out = Output(data['code'], data['stdout'], data['stderr'])\n"
        "facts = steps.parse_ruff_output(root, out)\n"
        "assert isinstance(facts, Ok), facts\n"
        "ruff = steps.record_ruff_snapshot(run_dir, "
        "steps.RuffSnapshot(nonce, root, out, facts.value))\n"
        "assert isinstance(ruff, Ok), ruff\n"
        "statuses = tuple((name, int(name in "
        "{'mutant-killers', 'coverage-observation', 'python-commands', "
        "'tool-outcomes', 'pytest-manifest', 'oracle-outcomes', 'host-observation', "
        "'native-observation', 'ty-observation', 'coverage-text-observation', "
        "'ruff-format-observation'})) "
        "for name in steps.FINALIZER_NAMES[:-1])\n"
        "final = steps.record_finalizers(run_dir, nonce, statuses)\n"
        "phase = steps.record_provisional_phases(run_dir, nonce, Err('unavailable'))\n"
        "assert isinstance(final, Ok) and isinstance(phase, Ok)\n"
        "marker = steps.ruff_seal(nonce, ruff.value.record)\n"
        "output = '\\n'.join((marker, "
        "steps.provisional_seal(nonce, phase.value), "
        "steps.finalizer_seal(final.value), ''))\n"
        "assert steps.verify_ruff_handoff(run_dir, nonce, output, root) == Ok(None)\n"
        "missing = output.replace(marker + '\\n', '', 1)\n"
        "assert isinstance(steps.verify_ruff_handoff(run_dir, nonce, missing, root), "
        "Err), "
        "'missing Ruff handoff was accepted'\n"
        "assert isinstance(steps._ruff_handoff_record(run_dir, 'foreign', root), Err), "
        "'foreign Ruff handoff was accepted'\n"
        "assert isinstance(steps._ruff_handoff_record(run_dir, nonce, "
        "root.parent), Err), "
        "'foreign Ruff root was accepted'\n"
        "empty = run_dir.parent / 'empty-root-control'; empty.mkdir()\n"
        "clean = steps.record_ruff_snapshot(empty, "
        "steps.RuffSnapshot(nonce, root, Output(0, '[]', ''), ()))\n"
        "assert isinstance(clean, Ok)\n"
        "assert isinstance(steps._ruff_handoff_record(empty, nonce, "
        "root.parent), Err), "
        "'foreign Ruff root was accepted'\n"
        "assert isinstance(steps.verify_ruff_handoff(run_dir, nonce, "
        "marker + '\\n' + output, root), Err), "
        "'ambiguous Ruff handoff was accepted'\n"
        "context = steps.CheckRun(root, run_dir, nonce, sys.argv[5])\n"
        "valid = steps.retain_verified_gate_output(context, "
        "state.with_name('state-ok'), "
        "(output, 'primary\\n'), verify_handoff=True)\n"
        "assert isinstance(valid, Ok), "
        "'Ruff handoff record was not retained: ' + str(valid)\n"
        "assert (valid.value / 'ruff-observation.json').read_bytes() "
        "== ruff.value.record\n"
        "target = state / 'check-reports' / nonce / 'ruff-observation.json'\n"
        "seen = [False]\n"
        "def audit(event, args):\n"
        "    if (not seen[0] and event == 'open' and str(args[0]) == str(target) "
        "and 'r' in str(args[1]) and target.exists()):\n"
        "        seen[0] = True\n"
        "        changed = json.loads(target.read_text())\n"
        "        changed['stdout'] = json.dumps(json.loads(changed['stdout']), "
        "sort_keys=True)\n"
        "        target.write_text(json.dumps(changed, sort_keys=True))\n"
        "sys.addaudithook(audit)\n"
        "result = steps.retain_verified_gate_output(context, state, "
        "(output, 'primary\\n'), verify_handoff=True)\n"
        "assert isinstance(result, Err), 'post-copy Ruff tampering was accepted'\n"
        "assert seen[0], 'Ruff tamper hook did not run'\n"
        "report = state / 'check-reports' / nonce\n"
        "assert 'Ruff handoff digest mismatch' in "
        "(report / 'finalizer-handoff.txt').read_text()\n"
        "assert (report / 'stderr.txt').read_text() == 'primary\\n'\n"
    )
    family = (
        "Windows"
        if sys.platform == "win32"
        else "Darwin"
        if sys.platform == "darwin"
        else "Linux"
    )
    result = run(
        [
            sys.executable,
            "-c",
            script,
            str(project),
            str(first_run / "ruff-observation.json"),
            str(temporary / "parent-run"),
            str(temporary / "state"),
            family,
        ],
        cwd=temporary,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    assert isinstance(result, Ok)
    assert result.value.code == 0, result.value.stderr


def _assert_ruff_binding(project: Path, source: Path, run_dir: Path, leg: Leg) -> None:
    ownership = source / "check/source_ownership.toml"
    ownership.parent.mkdir()
    ownership.write_text(
        "version = 1\n"
        "[[phases]]\nnumber = 0\nprerequisites = []\n"
        "[[phases]]\nnumber = 1\nprerequisites = [0]\n"
        "[[artifacts]]\npath = 'src/agentctl/subject.py'\n"
        "capability = 'subject'\nowner = 1\nconsumers = [1]\nrequired = true\n",
        encoding="utf-8",
    )
    census = source_census(project)
    assert isinstance(census, Ok)
    tools = _run_tools_observed(project, run_dir, "run-nonce", (leg,))
    assert isinstance(tools.ruff, Ok), "Ruff tool observation was lost"
    phases = (
        PhaseInputs(0, frozenset({"shared"}), frozenset({"early"}), frozenset()),
        PhaseInputs(1, frozenset({"later"}), frozenset({"late"}), frozenset({0})),
    )
    captured = ProvisionalCapture(
        census,
        Err("unused"),
        tools,
        None,
        Ok(()),
        "run-nonce",
        ("ruff-check",),
        (("ruff-check", 1),),
        family="Linux",
    )
    scoped = ruff_validation_attribution(captured, census.value, phases)
    assert isinstance(scoped, Ok), scoped
    assert not scoped.value.scoped[0][1]
    assert any("ruff F401" in item for item in scoped.value.scoped[1][1]), (
        "Ruff finding did not reach its source consumer"
    )
    _assert_static_tool_scope(
        captured, phases, scoped.value, "ruff-check", (project, run_dir)
    )
    stale_snapshot = replace(tools.ruff.value, nonce="stale")
    stale = replace(captured, tools=replace(tools, ruff=Ok(stale_snapshot)))
    assert isinstance(ruff_validation_attribution(stale, census.value, phases), Err), (
        "stale Ruff observation was accepted"
    )
    absent = replace(captured, tools=replace(tools, ruff=None))
    assert isinstance(ruff_validation_attribution(absent, census.value, phases), Err), (
        "missing Ruff observation was accepted"
    )
    forged = replace(tools.ruff.value, facts=())
    inconsistent = replace(captured, tools=replace(tools, ruff=Ok(forged)))
    assert isinstance(
        ruff_validation_attribution(inconsistent, census.value, phases), Err
    ), "changed Ruff facts were accepted"
    wrong_status = replace(tools.ruff.value, output=Output(0, "[]", ""), facts=())
    inconsistent = replace(captured, tools=replace(tools, ruff=Ok(wrong_status)))
    assert isinstance(
        ruff_validation_attribution(inconsistent, census.value, phases), Err
    ), "Ruff status mismatch was accepted"
    inconsistent = replace(
        captured,
        tools=replace(
            tools, evidence=Ok(LegEvidence("run-nonce", (("ruff-check", 0),)))
        ),
    )
    assert isinstance(
        ruff_validation_attribution(inconsistent, census.value, phases), Err
    ), "Ruff status mismatch was accepted"
    inconsistent = replace(
        captured,
        tools=replace(
            tools, substeps=Ok(ToolSubsteps("run-nonce", (("ruff-check", (0,)),)))
        ),
    )
    assert isinstance(
        ruff_validation_attribution(inconsistent, census.value, phases), Err
    ), "Ruff status mismatch was accepted"
    unowned = tuple(
        entry for entry in census.value if entry.path != "src/agentctl/subject.py"
    )
    fallback = ruff_validation_attribution(captured, unowned, phases)
    assert isinstance(fallback, Ok)
    assert any("ruff F401" in item for item in fallback.value.shared), (
        "unowned Ruff finding was localized"
    )


def _assert_ty_parent_handoff(project: Path, original: Path, tmp_path: Path) -> None:
    """Exercise live and retained verification using a real type-checker result."""
    script = """
import json, sys
from pathlib import Path
from agentctl.check import steps
from agentctl.foundation import Err, Ok
from agentctl.foundation_process_values import Output
root, original, directory, state = map(Path, sys.argv[1:5]); directory.mkdir()
nonce = "abc123"
record = original.read_bytes()
(directory / "ty-observation.json").write_bytes(record)
failed = {"python-commands", "tool-outcomes", "pytest-manifest", "oracle-outcomes",
          "host-observation", "native-observation", "ruff-observation",
          "coverage-text-observation",
          "ruff-format-observation", "coverage-observation", "mutant-killers"}
statuses = tuple((name, int(name in failed)) for name in steps.FINALIZER_NAMES[:-1])
final = steps.record_finalizers(directory, nonce, statuses)
phase = steps.record_provisional_phases(directory, nonce, Err("unavailable"))
assert isinstance(final, Ok) and isinstance(phase, Ok)
marker = steps.ty_observation_seal(nonce, record)
output = "\\n".join((marker, steps.provisional_seal(nonce, phase.value),
    steps.finalizer_seal(final.value), ""))
assert steps.verify_ty_handoff(directory, nonce, output, root) == Ok(None)
missing = output.replace(marker + "\\n", "", 1)
assert isinstance(steps.verify_ty_handoff(directory, nonce, missing, root), Err), \\
    "missing ty seal was accepted"
duplicated = steps.verify_ty_handoff(directory, nonce, marker + "\\n" + output, root)
assert isinstance(duplicated, Err), \\
    "duplicate ty seal was accepted"
foreign = steps.verify_ty_handoff(directory, nonce, output, root.parent)
assert isinstance(foreign, Err), \\
    "foreign ty root was accepted"
context = steps.CheckRun(root, directory, nonce, sys.argv[5])
valid = steps.retain_verified_gate_output(context, state.with_name("state-ok"),
    (output, "primary\\n"), verify_handoff=True)
assert isinstance(valid, Ok), "ty record was not retained: " + str(valid)
live = directory.parent / "live-ty"; live.mkdir()
(live / "ty-observation.json").write_bytes(record)
assert isinstance(steps.record_finalizers(live, nonce, statuses), Ok)
assert isinstance(steps.record_provisional_phases(live, nonce, Err("unavailable")), Ok)
changed = json.loads(record)
changed["stdout"] = json.dumps(json.loads(changed["stdout"]), sort_keys=True)
(live / "ty-observation.json").write_text(json.dumps(changed, sort_keys=True))
steps.run_observed = lambda *_args, **_kwargs: Ok(Output(0, output, "primary\\n"))
live_state = state.with_name("state-live")
assert steps._run_check_child(steps.CheckRun(root, live, nonce, sys.argv[5]),
    live_state, assume_yes=False) == 1, "live ty check was omitted"
stderr = (live_state / "check-reports" / nonce / "stderr.txt").read_text()
assert "ty handoff digest mismatch" in stderr, "live ty check was omitted"
assert "primary" in stderr
target = state / "check-reports" / nonce / "ty-observation.json"
seen = [False]
def audit(event, args):
    if (not seen[0] and event == "open" and str(args[0]) == str(target)
        and "r" in str(args[1]) and target.exists()):
        seen[0] = True
        altered = json.loads(target.read_text())
        altered["stdout"] = json.dumps(json.loads(altered["stdout"]), sort_keys=True)
        target.write_text(json.dumps(altered, sort_keys=True))
sys.addaudithook(audit)
answer = steps.retain_verified_gate_output(context, state, (output, "primary\\n"),
    verify_handoff=True)
assert isinstance(answer, Err), "post-copy ty tampering was accepted"
assert seen[0]
report = state / "check-reports" / nonce
assert "ty handoff digest mismatch" in (report / "finalizer-handoff.txt").read_text()
assert (report / "stderr.txt").read_text() == "primary\\n"
"""
    family = (
        "Windows"
        if sys.platform == "win32"
        else "Darwin"
        if sys.platform == "darwin"
        else "Linux"
    )
    result = run(
        [
            sys.executable,
            "-c",
            script,
            str(project),
            str(original),
            str(tmp_path / "parent-ty"),
            str(tmp_path / "state-ty"),
            family,
        ],
        cwd=project,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    assert isinstance(result, Ok)
    assert result.value.code == 0, result.value.stderr


def _assert_static_tool_scope(
    captured: ProvisionalCapture,
    phases: tuple[PhaseInputs, ...],
    scoped: steps.ToolFailureAttribution,
    tool: str,
    paths: tuple[Path, Path],
) -> None:
    """Check an actual Ruff result against its phase and shared failures."""
    project, directory = paths
    assert isinstance(captured.census, Ok)
    assert isinstance(captured.tools.evidence, Ok)
    assert isinstance(captured.tools.substeps, Ok)
    snapshot = (
        captured.tools.ruff if tool == "ruff-check" else captured.tools.ruff_format
    )
    assert isinstance(snapshot, Ok)
    assert not scoped.scoped[0][1]
    context = steps.CheckRun(project, directory, captured.nonce, "Linux")
    inputs = steps.ParentStaticInputs(
        context,
        directory,
        captured.census.value,
        phases,
        captured.tools.evidence.value,
        captured.tools.substeps.value,
    )
    shared = scoped.shared | frozenset(
        {"unverified-run", "unattributed tool failure: " + tool}
    )
    observed = tuple(
        steps.phase_reports.PhaseResult(number, str(number + 1) * 64, shared | failures)
        for number, failures in scoped.scoped
    )
    assert steps.verify_static_phase_failures(
        inputs, tool, snapshot.value.record, observed
    ) == Ok(None)
    forged = (observed[0], replace(observed[1], failures=shared))
    assert isinstance(
        steps.verify_static_phase_failures(inputs, tool, snapshot.value.record, forged),
        Err,
    ), "parent accepted hidden static diagnostic"


def _assert_parent_static_diagnostics(
    captured: ProvisionalCapture,
    phases: tuple[PhaseInputs, ...],
    scoped: steps.ToolFailureAttribution,
    paths: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Recheck actual type diagnostics through the parent and retained routes."""
    project, directory = paths
    assert isinstance(captured.census, Ok)
    assert isinstance(captured.tools.ty, Ok)
    assert isinstance(captured.tools.evidence, Ok)
    assert isinstance(captured.tools.substeps, Ok)
    context = steps.CheckRun(project, directory, captured.nonce, "Linux")
    inputs = steps.ParentStaticInputs(
        context,
        directory,
        captured.census.value,
        phases,
        captured.tools.evidence.value,
        captured.tools.substeps.value,
    )
    shared = scoped.shared | frozenset(
        {"unverified-run", "unattributed tool failure: ty"}
    )
    observed = tuple(
        steps.phase_reports.PhaseResult(number, str(number + 1) * 64, shared | failures)
        for number, failures in scoped.scoped
    )
    record = captured.tools.ty.value.record
    assert steps.verify_static_phase_failures(inputs, "ty", record, observed) == Ok(
        None
    )
    forged = (observed[0], replace(observed[1], failures=shared))
    assert isinstance(
        steps.verify_static_phase_failures(inputs, "ty", record, forged), Err
    ), "parent accepted hidden static diagnostic"
    no_shared = tuple(
        replace(item, failures=item.failures - {"unattributed tool failure: ty"})
        for item in observed
    )
    assert isinstance(
        steps.verify_static_phase_failures(inputs, "ty", record, no_shared), Err
    ), "parent accepted hidden static tool failure"
    wrong_status = replace(inputs, outcomes=LegEvidence(context.nonce, (("ty", 0),)))
    assert isinstance(
        steps.verify_static_phase_failures(wrong_status, "ty", record, observed), Err
    ), "parent accepted static status mismatch"
    _assert_parent_static_routes(inputs, observed, forged, record, monkeypatch)


def _assert_parent_static_routes(
    inputs: steps.ParentStaticInputs,
    observed: tuple[steps.phase_reports.PhaseResult, ...],
    forged: tuple[steps.phase_reports.PhaseResult, ...],
    record: bytes,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Require live and retained parents to invoke static attribution checks."""
    context = inputs.context
    output = steps.tool_results_seal(context.nonce, inputs.outcomes, inputs.substeps)
    with monkeypatch.context() as control:
        for name in (
            "verify_ty_handoff",
            "verify_ruff_handoff",
            "verify_ruff_format_handoff",
        ):
            control.setattr(steps, name, lambda *_args: Ok(None))
        for tool, seal in (
            ("ty", steps.ty_observation_seal),
            ("ruff-check", steps.ruff_seal),
            ("ruff-format", steps.ruff_format_seal),
        ):
            marker = seal(context.nonce, record)
            for name in ("_ty_handoff_record", "_ruff_handoff_record"):
                control.setattr(steps, name, lambda *_args, **_kwargs: Ok(record))
            assert steps.__dict__["_static_handoff"](inputs, tool, marker) == Ok(record)
            for name in ("_ty_handoff_record", "_ruff_handoff_record"):
                control.setattr(
                    steps, name, lambda *_args, **_kwargs: Ok(record + b"changed")
                )
            assert isinstance(
                steps.__dict__["_static_handoff"](inputs, tool, marker), Err
            ), "changed " + tool + " record after seal was accepted"
    failed = {"ruff-observation", "ruff-format-observation"}
    final = LegEvidence(
        context.nonce,
        tuple((name, int(name in failed)) for name in steps.FINALIZER_NAMES[:-1]),
    )
    output += "\n" + steps.finalizer_seal(final)
    with monkeypatch.context() as patch:
        patch.setattr(
            steps.ownership, "guarded_census", lambda *_args: Ok(inputs.entries)
        )
        patch.setattr(steps, "_parent_bound_census", lambda *_args: Ok(inputs.entries))
        patch.setattr(steps, "census_phases", lambda *_args: Ok(()))
        work = steps.ownership.ScopedPhaseWork(
            steps.ownership.PhaseWork(inputs.phases, ()), ()
        )
        patch.setattr(steps, "scoped_source_inputs", lambda *_args: Ok(work))
        rebuilt = steps.__dict__["_parent_static_inputs"](
            context, context.directory, ""
        )
        assert isinstance(rebuilt, Ok), rebuilt
        assert steps.verify_static_phase_failures(
            rebuilt.value, "ty", record, observed
        ) == Ok(None)
        patch.setattr(steps, "_parent_bound_census", lambda *_args: Err("changed"))
        assert isinstance(
            steps.__dict__["_parent_static_inputs"](context, context.directory, ""), Err
        ), "unbound parent static census was accepted"
        patch.setattr(steps, "_parent_bound_census", lambda *_args: Ok(inputs.entries))
        patch.setattr(steps, "finalizer_observation", lambda *_args: Ok(final))
        patch.setattr(
            steps, "_provisional_values_for_identity", lambda *_args: Ok(observed)
        )
        patch.setattr(steps, "_static_handoff", lambda *_args: Ok(record))
        for name in (
            "verify_python_commands_handoff",
            "verify_tool_results_handoff",
            "_verify_provisional_census",
            "verify_python_plan_handoff",
            "verify_provisional_input_identities",
            "verify_pytest_handoff",
            "verify_oracle_handoff",
            "verify_host_handoff",
            "verify_native_handoff",
            "verify_ty_handoff",
            "verify_coverage_text_handoff",
            "verify_provisional_collection",
            "verify_provisional_oracle",
            "verify_provisional_host",
            "verify_provisional_coverage",
            "verify_provisional_tools",
            "verify_provisional_validation",
            "verify_provisional_prerequisites",
            "verify_provisional_source",
            "verify_finalizer_handoff",
            "verify_provisional_handoff",
            "verify_provisional_finalizers",
            "verify_killer_handoff",
            "verify_coverage_handoff",
            "verify_ruff_handoff",
            "verify_ruff_format_handoff",
            "retain_handoff_failure",
        ):
            patch.setattr(steps, name, lambda *_args, **_kwargs: Ok(None))
        assert steps.verify_provisional_static(
            context, context.directory, output
        ) == Ok(None)
        patch.setattr(
            steps, "_provisional_values_for_identity", lambda *_args: Ok(forged)
        )
        assert isinstance(
            steps.verify_provisional_static(context, context.directory, output), Err
        ), "parent accepted hidden static diagnostic"
        assert isinstance(steps.verify_python_handoffs(context, output), Err), (
            "live parent accepted hidden static diagnostic"
        )
        patch.setattr(
            steps, "retain_gate_output", lambda *_args, **_kwargs: Ok(context.directory)
        )
        patch.setattr(
            steps,
            "verify_retained_streams",
            lambda _directory, _streams, _observed, prior: prior,
        )
        patch.setattr(
            steps,
            "verify_retained_artifacts",
            lambda _directory, _observed, prior: prior,
        )
        retained = steps.retain_verified_gate_output(
            context, Path("/state"), (output, ""), verify_handoff=True
        )
        assert isinstance(retained, Err), (
            "retained parent accepted hidden static diagnostic"
        )
        altered = (
            replace(inputs, outcomes=replace(inputs.outcomes, outcomes=())),
            replace(inputs, substeps=replace(inputs.substeps, outcomes=())),
            replace(inputs, outcomes=replace(inputs.outcomes, nonce="stale")),
            replace(inputs, substeps=replace(inputs.substeps, nonce="stale")),
        )
        patch.setattr(steps, "_verify_static_reports", lambda *_args: Ok(None))
        for changed in altered:
            patch.setattr(
                steps,
                "_parent_static_inputs",
                lambda *_args, changed=changed: Ok(changed),
            )
            assert isinstance(
                steps.verify_provisional_static(context, context.directory, output), Err
            ), "changed static tool inputs after seal were accepted"
            assert isinstance(steps.verify_python_handoffs(context, output), Err)
            assert isinstance(
                steps.retain_verified_gate_output(
                    context, Path("/state"), (output, ""), verify_handoff=True
                ),
                Err,
            )


def test_ty_json_is_captured_and_scoped_from_real_leg(
    root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The actual strict type checker assigns a later source failure to its owner."""
    project, run_dir = tmp_path / "project", tmp_path / "run"
    source = project / "src/agentctl"
    source.mkdir(parents=True)
    (project / "pyproject.toml").write_bytes((root / "pyproject.toml").read_bytes())
    ownership = source / "check/source_ownership.toml"
    ownership.parent.mkdir()
    ownership.write_text(
        "version = 1\n"
        "[[phases]]\nnumber = 0\nprerequisites = []\n"
        "[[phases]]\nnumber = 1\nprerequisites = [0]\n"
        "[[artifacts]]\npath = 'src/agentctl/subject.py'\n"
        "capability = 'subject'\nowner = 1\nconsumers = [1]\nrequired = true\n",
        encoding="utf-8",
    )
    subject = source / "subject.py"
    subject.write_text('value: int = "wrong"\n', encoding="utf-8")
    run_dir.mkdir()
    (run_dir / "ty-config").mkdir()
    census = source_census(project)
    assert isinstance(census, Ok)
    leg = python_legs(sys.executable, project, (str(subject),), run_dir)[2]
    tools = _run_tools_observed(project, run_dir, "abc123", (leg,))
    assert isinstance(tools.ty, Ok), "real ty diagnostics were not captured"
    _assert_ty_parent_handoff(project, run_dir / "ty-observation.json", tmp_path)
    assert tools.ty.value.output.code == 1
    assert any(fact.path == "src/agentctl/subject.py" for fact in tools.ty.value.facts)
    phases = (
        PhaseInputs(0, frozenset({"shared"}), frozenset({"early"}), frozenset()),
        PhaseInputs(1, frozenset({"later"}), frozenset({"late"}), frozenset({0})),
    )
    captured = ProvisionalCapture(
        census,
        Err("unused"),
        tools,
        None,
        Ok(()),
        "abc123",
        ("ty",),
        (("ty", 1),),
        family="Linux",
    )
    scoped = steps.ty_validation_attribution(captured, census.value, phases)
    assert isinstance(scoped, Ok), scoped
    assert not scoped.value.scoped[0][1], "later type error blocked earlier phase"
    assert any(
        "ty invalid-assignment" in value for value in scoped.value.scoped[1][1]
    ), "type diagnostic did not reach its source consumer"
    _assert_parent_static_diagnostics(
        captured, phases, scoped.value, (project, run_dir), monkeypatch
    )
    stale = replace(
        captured, tools=replace(tools, ty=Ok(replace(tools.ty.value, nonce="stale")))
    )
    assert isinstance(
        steps.ty_validation_attribution(stale, census.value, phases), Err
    ), "stale type diagnostic was accepted"
    missing = replace(captured, tools=replace(tools, ty=None))
    assert isinstance(
        steps.ty_validation_attribution(missing, census.value, phases), Err
    ), "missing type diagnostic was accepted"
    inconsistent = replace(
        captured,
        tools=replace(tools, evidence=Ok(LegEvidence("abc123", (("ty", 0),)))),
    )
    assert isinstance(
        steps.ty_validation_attribution(inconsistent, census.value, phases), Err
    ), "type status mismatch was accepted"
    changed = replace(
        captured, tools=replace(tools, ty=Ok(replace(tools.ty.value, facts=())))
    )
    assert isinstance(
        steps.ty_validation_attribution(changed, census.value, phases), Err
    ), "changed type facts were accepted"
    subject.write_text("value: int = 1\n", encoding="utf-8")
    clean_run = tmp_path / "clean-run"
    clean_run.mkdir()
    (clean_run / "ty-config").mkdir()
    clean = _run_leg_observed(project, clean_run, "clean-nonce", leg)
    assert clean.code == 0
    assert isinstance(clean.ty, Ok)
    assert not clean.ty.value.facts


def test_ruff_json_is_captured_from_the_real_leg(root: Path, tmp_path: Path) -> None:
    """The actual leg captures structured diagnostics and its subprocess status."""
    project, run_dir = tmp_path / "project", tmp_path / "run"
    source = project / "src/agentctl"
    source.mkdir(parents=True)
    (project / "pyproject.toml").write_bytes((root / "pyproject.toml").read_bytes())
    (source / "__init__.py").write_text("", encoding="utf-8")
    subject, fixture = (
        source / "subject.py",
        root / "tests/fixtures/static_negative/ruff",
    )
    subject.write_bytes((fixture / "negative.py.txt").read_bytes())
    run_dir.mkdir()
    leg = python_legs(sys.executable, project, (str(subject),), run_dir)[0]
    first_run = run_dir / "first"
    first_run.mkdir()
    failed = _run_leg_observed(project, first_run, "run-nonce", leg)
    assert failed.code == 1
    assert isinstance(failed.ruff, Ok), "real Ruff diagnostics were not captured"
    assert failed.ruff.value.nonce == "run-nonce"
    assert failed.ruff.value.output.code == 1
    assert any(
        item.path == "src/agentctl/subject.py" and item.code == "F401"
        for item in failed.ruff.value.facts
    ), "real Ruff diagnostics were not captured"
    _assert_invalid_ruff_output(project, tmp_path, failed.ruff.value.output)
    _assert_ruff_parent_handoff(project, first_run, tmp_path)
    _assert_ruff_capture_integrity(first_run, failed.ruff.value)
    _assert_ruff_binding(project, source, run_dir, leg)
    subject.write_bytes((fixture / "valid.py.txt").read_bytes())
    final_run = run_dir / "final"
    final_run.mkdir()
    passed = _run_leg_observed(project, final_run, "run-nonce", leg)
    assert passed.code == 0
    assert isinstance(passed.ruff, Ok), passed.ruff
    assert passed.ruff.value.facts == ()


def _assert_format_parent_handoff(
    project: Path, original: Path, tmp_path: Path
) -> None:
    """Require the real parent to refuse an altered copied formatter record."""
    _assert_both_ruff_legs(
        project, project / "src/agentctl/subject.py", original.parent / "both"
    )
    script = """
import json, sys
from pathlib import Path
from agentctl.check import steps
from agentctl.foundation import Err, Ok
from agentctl.foundation_process_values import Output
root, source, run_dir, state = map(Path, sys.argv[1:5]); run_dir.mkdir()
nonce = "abc123"; data = json.loads(source.read_text())
out = Output(data["code"], data["stdout"], data["stderr"])
facts = steps.parse_ruff_output(root, out)
assert isinstance(facts, Ok)
capture = steps.record_ruff_snapshot(run_dir,
    steps.RuffSnapshot(nonce, root, out, facts.value),
    filename="ruff-format-observation.json")
assert isinstance(capture, Ok)
failed = {"python-commands", "ruff-observation", "coverage-observation",
          "mutant-killers", "tool-outcomes", "pytest-manifest", "oracle-outcomes",
          "host-observation", "native-observation", "ty-observation",
          "coverage-text-observation"}
statuses = tuple((name, int(name in failed)) for name in steps.FINALIZER_NAMES[:-1])
final = steps.record_finalizers(run_dir, nonce, statuses)
phase = steps.record_provisional_phases(run_dir, nonce, Err("unavailable"))
assert isinstance(final, Ok) and isinstance(phase, Ok)
marker = steps.ruff_format_seal(nonce, capture.value.record)
output = "\\n".join((marker,
    steps.provisional_seal(nonce, phase.value), steps.finalizer_seal(final.value), ""))
assert steps.verify_ruff_format_handoff(run_dir, nonce, output, root) == Ok(None)
missing = output.replace(marker + "\\n", "", 1)
duplicate = marker + "\\n" + output
assert isinstance(steps.verify_ruff_format_handoff(
    run_dir, nonce, missing, root), Err), \
    "missing format seal was accepted"
assert isinstance(steps.verify_ruff_format_handoff(
    run_dir, nonce, duplicate, root), Err), "duplicate format seal was accepted"
context = steps.CheckRun(root, run_dir, nonce, sys.argv[5])
valid = steps.retain_verified_gate_output(context, state.with_name("state-ok"),
    (output, "primary\\n"), verify_handoff=True)
assert isinstance(valid, Ok), valid
assert ((valid.value / "ruff-format-observation.json").read_bytes()
    == capture.value.record)
target = state / "check-reports" / nonce / "ruff-format-observation.json"
seen = [False]
def audit(event, args):
    if (not seen[0] and event == "open" and str(args[0]) == str(target)
        and "r" in str(args[1]) and target.exists()):
        seen[0] = True
        value = json.loads(target.read_text())
        value["stdout"] = json.dumps(json.loads(value["stdout"]), sort_keys=True)
        target.write_text(json.dumps(value, sort_keys=True))
sys.addaudithook(audit)
result = steps.retain_verified_gate_output(context, state, (output, "primary\\n"),
    verify_handoff=True)
assert isinstance(result, Err), "post-copy format tampering was accepted"
assert seen[0]
report = state / "check-reports" / nonce
assert "Ruff format handoff digest mismatch" in (
    report / "finalizer-handoff.txt").read_text()
assert (report / "stderr.txt").read_text() == "primary\\n"
"""
    family = (
        "Windows"
        if sys.platform == "win32"
        else "Darwin"
        if sys.platform == "darwin"
        else "Linux"
    )
    child = run(
        [
            sys.executable,
            "-c",
            script,
            str(project),
            str(original),
            str(tmp_path / "format-parent"),
            str(tmp_path / "format-state"),
            family,
        ],
        cwd=tmp_path,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    assert isinstance(child, Ok), child
    assert child.value.code == 0, child.value.stderr


def _assert_both_ruff_legs(project: Path, target: Path, run_dir: Path) -> None:
    """Require both actual Ruff observations to survive the same tool schedule."""
    run_dir.mkdir()
    legs = python_legs(sys.executable, project, (str(target),), run_dir)
    tools = _run_tools_observed(project, run_dir, "both", legs[:2])
    assert isinstance(tools.ruff, Ok), "Ruff check observation was overwritten"
    assert isinstance(tools.ruff_format, Ok), "Ruff format observation was overwritten"
    assert (run_dir / "ruff-observation.json").is_file()
    assert (run_dir / "ruff-format-observation.json").is_file()


def test_ruff_format_json_is_captured_from_real_leg(root: Path, tmp_path: Path) -> None:
    """The real formatter's failing file reaches only its declared consumer."""
    project, run_dir = tmp_path / "project", tmp_path / "run"
    source = project / "src/agentctl"
    source.mkdir(parents=True)
    (project / "pyproject.toml").write_bytes((root / "pyproject.toml").read_bytes())
    (source / "__init__.py").write_text("", encoding="utf-8")
    (source / "subject.py").write_text("answer=  42\n", encoding="utf-8")
    ownership = source / "check/source_ownership.toml"
    ownership.parent.mkdir()
    ownership.write_text(
        "version = 1\n"
        "[[phases]]\nnumber = 0\nprerequisites = []\n"
        "[[phases]]\nnumber = 1\nprerequisites = [0]\n"
        "[[artifacts]]\npath = 'src/agentctl/subject.py'\n"
        "capability = 'subject'\nowner = 1\nconsumers = [1]\nrequired = true\n",
        encoding="utf-8",
    )
    run_dir.mkdir()
    leg = python_legs(sys.executable, project, (str(source / "subject.py"),), run_dir)[
        1
    ]
    census = source_census(project)
    assert isinstance(census, Ok)
    tools = _run_tools_observed(project, run_dir, "current", (leg,))
    assert isinstance(tools.ruff_format, Ok), "real format output was not captured"
    assert tools.ruff_format.value.output.code == 1
    assert {fact.path for fact in tools.ruff_format.value.facts} == {
        "src/agentctl/subject.py"
    }
    phases = (
        PhaseInputs(0, frozenset({"shared"}), frozenset({"early"}), frozenset()),
        PhaseInputs(1, frozenset({"later"}), frozenset({"late"}), frozenset({0})),
    )
    captured = ProvisionalCapture(
        census,
        Err("unused"),
        tools,
        None,
        Ok(()),
        "current",
        ("ruff-format",),
        (("ruff-format", 1),),
        family="Linux",
    )
    scoped = steps.ruff_format_validation_attribution(captured, census.value, phases)
    assert isinstance(scoped, Ok), scoped
    assert any("ruff format:" in issue for issue in scoped.value.scoped[1][1]), (
        "format finding did not reach its source consumer"
    )
    _assert_static_tool_scope(
        captured, phases, scoped.value, "ruff-format", (project, run_dir)
    )
    stale, missing = (
        replace(
            captured,
            tools=replace(
                tools, ruff_format=Ok(replace(tools.ruff_format.value, nonce="stale"))
            ),
        ),
        replace(captured, tools=replace(tools, ruff_format=None)),
    )
    assert isinstance(
        steps.ruff_format_validation_attribution(stale, census.value, phases), Err
    ), "stale format observation was accepted"
    assert isinstance(
        steps.ruff_format_validation_attribution(missing, census.value, phases), Err
    ), "missing format observation was accepted"
    altered = replace(
        captured,
        tools=replace(
            tools, ruff_format=Ok(replace(tools.ruff_format.value, facts=()))
        ),
    )
    assert isinstance(
        steps.ruff_format_validation_attribution(altered, census.value, phases), Err
    ), "changed format facts were accepted"
    mismatched = replace(
        captured,
        tools=replace(
            tools, evidence=Ok(LegEvidence("current", (("ruff-format", 0),)))
        ),
    )
    assert isinstance(
        steps.ruff_format_validation_attribution(mismatched, census.value, phases), Err
    ), "format status mismatch was accepted"
    mismatched_steps = replace(
        captured,
        tools=replace(
            tools, substeps=Ok(ToolSubsteps("current", (("ruff-format", (0,)),)))
        ),
    )
    assert isinstance(
        steps.ruff_format_validation_attribution(
            mismatched_steps, census.value, phases
        ),
        Err,
    ), "format substep mismatch was accepted"
    unowned = tuple(
        entry for entry in census.value if entry.path != "src/agentctl/subject.py"
    )
    fallback = steps.ruff_format_validation_attribution(captured, unowned, phases)
    assert isinstance(fallback, Ok)
    assert any("ruff format:" in issue for issue in fallback.value.shared), (
        "unowned format finding was localized"
    )
    path = run_dir / "ruff-format-observation.json"
    _assert_format_parent_handoff(project, path, tmp_path)
    assert (
        steps.ruff_snapshot_unchanged(
            run_dir,
            "current",
            tools.ruff_format,
            filename="ruff-format-observation.json",
        )
        == 0
    )
    path.write_bytes(path.read_bytes() + b" ")
    assert (
        steps.ruff_snapshot_unchanged(
            run_dir,
            "current",
            tools.ruff_format,
            filename="ruff-format-observation.json",
        )
        == 1
    ), "changed format observation was accepted"
    (source / "subject.py").write_text("answer = 42\n", encoding="utf-8")
    clean = run_dir / "clean"
    clean.mkdir()
    clean_leg = python_legs(
        sys.executable, project, (str(source / "subject.py"),), clean
    )[1]
    passed = _run_leg_observed(project, clean, "current", clean_leg)
    assert passed.code == 0
    assert isinstance(passed.ruff_format, Ok)
    assert not passed.ruff_format.value.facts


def test_ruff_format_fires_on_fixture(root: Path, tmp_path: Path) -> None:
    """Require a formatting difference and an accepted formatted twin."""
    negative = _probe(root, tmp_path, "format", "format", valid=False)
    assert negative.code != 0
    assert "would be reformatted" in negative.stdout
    assert _probe(root, tmp_path, "format", "format", valid=True).code == 0


def test_ty_fires_on_fixture(root: Path, tmp_path: Path) -> None:
    """Require an error diagnostic, not merely a warning or tool failure."""
    negative = _probe(root, tmp_path, "ty", "ty", valid=False)
    assert negative.code != 0
    rows = json.loads(negative.stdout)
    assert any(
        row.get("check_name") == "invalid-assignment" and row.get("severity") == "major"
        for row in rows
    ), "ty did not report an error"
    assert _probe(root, tmp_path, "ty", "ty", valid=True).code == 0


def test_ty_ignores_user_config(
    root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Isolate the user configuration home even when it disables all rules."""
    user = tmp_path / "user"
    (user / "ty").mkdir(parents=True)
    include = json.dumps("**/subject.py")
    (user / "ty/ty.toml").write_text(
        '[rules]\nall = "ignore"\n'
        f"[[overrides]]\ninclude = [{include}]\n"
        '[overrides.rules]\nall = "ignore"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("XDG_CONFIG_HOME", str(user))
    monkeypatch.setenv("APPDATA", str(user))
    monkeypatch.setenv("TY_CONFIG_FILE", str(user / "ty/ty.toml"))
    negative = _probe(root, tmp_path, "ty", "ty", valid=False)
    assert negative.code != 0, "user config weakened ty"
    rows = json.loads(negative.stdout)
    assert any(
        row.get("check_name") == "invalid-assignment" and row.get("severity") == "major"
        for row in rows
    ), "user config weakened ty"
    leaked = run(
        [
            sys.executable,
            "-m",
            "ty",
            "check",
            "--python",
            sys.executable,
            "--error-on-warning",
            str(tmp_path / "subject.py"),
        ],
        cwd=tmp_path,
        env=environment(os.environ, tmp_path, "hostile-configuration-control"),
    )
    assert isinstance(leaked, Ok)
    assert leaked.value.code == 0, "hostile configuration control did not downgrade ty"
    assert _probe(root, tmp_path, "ty", "ty", valid=True).code == 0


def test_raw_link_rule_exception_is_narrow(root: Path, tmp_path: Path) -> None:
    """Accept the raw guard reader and reject the same style elsewhere."""
    config = tmp_path / "pyproject.toml"
    config.write_bytes((root / "pyproject.toml").read_bytes())
    package = tmp_path / "src/agentctl/check"
    package.mkdir(parents=True)
    for directory in (package, package.parent):
        (directory / "__init__.py").write_text("", encoding="utf-8")
    fixture = (
        root / "tests/fixtures/static_negative/readlink/reader.py.txt"
    ).read_text(encoding="utf-8")
    for name, expected in (("writeguard.py", 0), ("another.py", 1)):
        target = package / name
        target.write_text(fixture, encoding="utf-8")
        result = run(
            [
                sys.executable,
                "-m",
                "ruff",
                "check",
                "--config",
                str(config),
                "--no-cache",
                "--no-fix",
                str(target),
            ],
            cwd=tmp_path,
            env=environment(os.environ, tmp_path, "raw-link-control"),
        )
        assert isinstance(result, Ok)
        assert result.value.code == expected
        assert ("PTH115" in result.value.stdout) == (expected != 0)
