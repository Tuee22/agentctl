# Copyright (c) 2026 agentctl contributors.
"""Two-sided pytester evidence for the full-suite discipline plugin."""

import json
import os
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from agentctl.check import coverage_hosts, steps
from agentctl.check.evidence import Entry, ToolSubsteps, parse_manifest, source_census
from agentctl.check.gate_plugin import orphan_modules
from agentctl.check.legs import Leg, coverage_commands
from agentctl.check.phase_reports import (
    CollectionScope,
    PhaseInputs,
    collection_failures,
    observe_collection,
)
from agentctl.check.steps import CheckRun, capture_coverage, coverage_snapshot_unchanged
from agentctl.process import run
from agentctl.result import Err, Ok, Result

pytestmark = pytest.mark.evidence("real")
SAMPLE = (
    'import pytest\npytestmark = pytest.mark.evidence("value")\n'
    "def test_one():\n    assert 1 == 1\n"
    "def test_two():\n    assert 2 == 2\n"
)
CONFIG = "[pytest]\nmarkers = evidence(cls): evidence class\n"


def _suite(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch, source: str = SAMPLE
) -> Path:
    """Prepare a fresh nested session and independently located manifest."""
    pytester.makeini(CONFIG)
    pytester.makepyfile(source)
    manifest = pytester.path / "manifest.json"
    monkeypatch.setenv("AGENTCTL_CHECK_NONCE", "nested-nonce")
    monkeypatch.setenv("AGENTCTL_CHECK_MANIFEST", str(manifest))
    monkeypatch.setenv("PYTEST_DISABLE_PLUGIN_AUTOLOAD", "1")
    return manifest


def _run(pytester: pytest.Pytester, *arguments: str) -> pytest.RunResult:
    """Load the same plugin used by check, without foreign plugin autoload."""
    return pytester.runpytest_subprocess(
        "-p", "no:cacheprovider", "-p", "agentctl.check.gate_plugin", ".", *arguments
    )


def test_killer_outcomes_are_retained_from_real_execution(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A real nested corpus case publishes its observed baseline and kill."""
    manifest = _suite(pytester, monkeypatch)
    case = pytester.path / "tests/governance/test_mutants.py"
    case.parent.mkdir(parents=True)
    case.write_text(
        """import pytest
from agentctl.check.gate_plugin import KILLER_EXECUTION
from agentctl.check.mutants import (KillerExecution, Mutant, Operator,
                                   exercise_observed, killer_verdict)
from agentctl.foundation import Ok
pytestmark = pytest.mark.evidence("real")
@pytest.mark.parametrize("identifier", ["M-test-control"])
def test_corpus(identifier, request, tmp_path):
    source = tmp_path / "src"
    cases = tmp_path / "tests/unit"
    source.mkdir(parents=True)
    cases.mkdir(parents=True)
    (source / "sample.py").write_text("def answer():\\n    return 2\\n")
    (cases / "test_sample.py").write_text(
        "from sample import answer\\ndef test_answer():\\n"
        "    assert answer() == 2, 'named defect'\\n")
    record = Mutant(identifier, Operator.REPLACE_LITERAL, "src/sample.py",
                    "return 2", "return 3",
                    ("tests/unit/test_sample.py::test_answer",), "named defect")
    observed = exercise_observed(tmp_path, record)
    request.node.stash[KILLER_EXECUTION] = KillerExecution(record, observed)
    assert killer_verdict(record, observed) == Ok(None)
""",
        encoding="utf-8",
    )
    result = _run(pytester)
    assert result.ret == 0, result.stdout.str() + result.stderr.str()
    data = json.loads(
        (manifest.parent / "mutant-killers.json").read_text(encoding="utf-8")
    )
    assert data == {
        "nonce": "nested-nonce",
        "records": [
            {
                "identifier": "M-test-control",
                "error": "",
                "killers": [
                    {
                        "node": "tests/unit/test_sample.py::test_answer",
                        "baseline": "passed",
                        "mutation": "killed",
                    }
                ],
            }
        ],
    }, "real killer observations were not retained"


def test_incomplete_killer_observation_fails_gate(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A corpus case cannot publish an empty result for a required killer."""
    _suite(pytester, monkeypatch)
    case = pytester.path / "tests/governance/test_mutants.py"
    case.parent.mkdir(parents=True)
    case.write_text(
        """import pytest
from agentctl.check.gate_plugin import KILLER_EXECUTION
from agentctl.check.mutants import KillerExecution, Mutant, Operator
from agentctl.foundation import Ok
pytestmark = pytest.mark.evidence("value")
@pytest.mark.parametrize("identifier", ["M-test-control"])
def test_corpus(identifier, request):
    record = Mutant(identifier, Operator.DELETE, "src/sample.py", "a", "b",
                    ("tests/unit/test_sample.py::test_answer",), "named defect")
    request.node.stash[KILLER_EXECUTION] = KillerExecution(record, Ok(()))
""",
        encoding="utf-8",
    )
    result = _run(pytester)
    assert result.ret == 1, "invalid killer observation accepted"


def test_failed_baseline_is_retained_without_a_mutant_kill(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failed real baseline does not hide a second, independently killed case."""
    manifest = _suite(pytester, monkeypatch)
    case = pytester.path / "tests/governance/test_mutants.py"
    case.parent.mkdir(parents=True)
    case.write_text(
        """import pytest
from agentctl.check.gate_plugin import KILLER_EXECUTION
from agentctl.check.mutants import (KillerExecution, Mutant, Operator,
                                   exercise_observed, killer_verdict)
from agentctl.foundation import Ok
pytestmark = pytest.mark.evidence("real")
@pytest.mark.parametrize("identifier", ["M-test-control"])
def test_corpus(identifier, request, tmp_path):
    source = tmp_path / "src"
    cases = tmp_path / "tests/unit"
    source.mkdir(parents=True)
    cases.mkdir(parents=True)
    (source / "sample.py").write_text("def answer():\\n    return 2\\n")
    (cases / "test_sample.py").write_text(
        "from sample import answer\\ndef test_broken():\\n"
        "    assert False, 'baseline failure'\\ndef test_answer():\\n"
        "    assert answer() == 2, 'named defect'\\n")
    record = Mutant(identifier, Operator.REPLACE_LITERAL, "src/sample.py",
                    "return 2", "return 3",
                    ("tests/unit/test_sample.py::test_broken",
                     "tests/unit/test_sample.py::test_answer"), "named defect")
    observed = exercise_observed(tmp_path, record)
    request.node.stash[KILLER_EXECUTION] = KillerExecution(record, observed)
    assert killer_verdict(record, observed) == Ok(None)
""",
        encoding="utf-8",
    )
    result = _run(pytester)
    assert result.ret == 1
    data = json.loads(
        (manifest.parent / "mutant-killers.json").read_text(encoding="utf-8")
    )
    assert data["records"][0]["killers"] == [
        {
            "node": "tests/unit/test_sample.py::test_broken",
            "baseline": "failed:baseline",
            "mutation": "not-run",
        },
        {
            "node": "tests/unit/test_sample.py::test_answer",
            "baseline": "passed",
            "mutation": "killed",
        },
    ], "failed baseline or independent kill was hidden"


def test_killer_report_refuses_existing_file(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An existing run artifact is never replaced by a new observation."""
    manifest = _suite(pytester, monkeypatch)
    report = manifest.parent / "mutant-killers.json"
    report.write_bytes(b"foreign report")
    case = pytester.path / "tests/governance/test_mutants.py"
    case.parent.mkdir(parents=True)
    case.write_text(
        """import pytest
from agentctl.check.gate_plugin import KILLER_EXECUTION
from agentctl.check.mutants import KillerExecution, KillerOutcome, Mutant, Operator
from agentctl.foundation import Ok
pytestmark = pytest.mark.evidence("value")
@pytest.mark.parametrize("identifier", ["M-test-control"])
def test_corpus(identifier, request):
    node = "tests/unit/test_sample.py::test_answer"
    record = Mutant(identifier, Operator.DELETE, "src/sample.py", "a", "b",
                    (node,), "named defect")
    request.node.stash[KILLER_EXECUTION] = KillerExecution(
        record, Ok((KillerOutcome(node, Ok(None), Ok(None)),)))
""",
        encoding="utf-8",
    )
    result = _run(pytester)
    assert result.ret != 0, "existing killer report was overwritten"
    assert report.read_bytes() == b"foreign report", "foreign killer report changed"


def test_skip_fails_session(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Reject skip markers, runtime skips and importorskip with passing twins."""
    manifest = _suite(pytester, monkeypatch)
    assert _run(pytester).ret == 0
    for statement in (
        "pytest.skip('negative')",
        "pytest.importorskip('agentctl_nonexistent_dependency')",
    ):
        pytester.makepyfile(SAMPLE.replace("assert 1 == 1", statement))
        assert _run(pytester).ret == 1, "skip outcome was accepted"
        assert "forbidden outcome" in manifest.read_text(encoding="utf-8")
    for marker in (
        "@pytest.mark.skip(reason='negative')",
        "@pytest.mark.skipif(False, reason='inactive negative')",
    ):
        pytester.makepyfile(SAMPLE.replace("def test_one", marker + "\ndef test_one"))
        assert _run(pytester).ret == 1, "skip marker was accepted"


def test_xfail_fails_session(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fail both expected failures and unexpected passes, including inactive marks."""
    _suite(pytester, monkeypatch)
    assert _run(pytester).ret == 0
    for expression in ("1 == 1", "1 == 2"):
        pytester.makepyfile(
            SAMPLE.replace(
                "def test_one", "@pytest.mark.xfail(reason='negative')\ndef test_one"
            ).replace("assert 1 == 1", "assert " + expression)
        )
        assert _run(pytester).ret == 1, "xfail outcome was accepted"


def test_selector_under_check_fails(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Reject every public narrowing route against an unselected positive run."""
    _suite(pytester, monkeypatch)
    assert _run(pytester).ret == 0
    for options in (
        ("-k", "test_one or test_two"),
        ("-k", "test_one"),
        ("-m", "value"),
        ("--lf",),
        ("--deselect", "test_selector_under_check_fails.py::test_one"),
        ("test_selector_under_check_fails.py::test_one",),
        ("test_selector_under_check_fails.py",),
        ("--collect-only",),
    ):
        result = _run(pytester, *options)
        assert result.ret != 0, "selector was accepted"
        assert (
            "forbidden" in result.stderr.str()
            or "unrecognized arguments: --lf" in result.stderr.str()
        )


def test_deselection_fails_session(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Observe deselection initiated by another plugin without selector flags."""
    manifest = _suite(pytester, monkeypatch)
    assert _run(pytester).ret == 0
    pytester.makeconftest(
        "def pytest_collection_modifyitems(config, items):\n"
        "    removed = items.pop()\n"
        "    config.hook.pytest_deselected(items=[removed])\n"
    )
    assert _run(pytester).ret == 1
    assert "deselected:" in manifest.read_text(encoding="utf-8")


def test_duplicate_nodes_fail_session(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Duplicate collection and execution cannot collapse into passing sets."""
    manifest = _suite(pytester, monkeypatch)
    assert _run(pytester).ret == 0
    pytester.makeconftest(
        "def pytest_collection_modifyitems(config, items):\n"
        "    items.append(items[-1])\n"
    )
    assert _run(pytester).ret == 1
    observed = manifest.read_text(encoding="utf-8")
    assert "duplicate collected node id" in observed, (
        "duplicate collection was not reported"
    )
    assert "duplicate execution:" in observed, "duplicate execution was not reported"


def test_orphan_module_fails(tmp_path: Path) -> None:
    """Reject uncited, uncollected and support-hidden test modules."""
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_example.py").write_text("", encoding="utf-8")
    (tests / "helper.py").write_text("", encoding="utf-8")
    collected = frozenset({"tests/test_example.py::test_example"})
    cited = frozenset({"tests/test_example.py"})
    support = frozenset({"tests/helper.py"})
    assert orphan_modules(tmp_path, collected, cited, support) == ()
    assert orphan_modules(tmp_path, collected, frozenset(), support) == (
        "tests/test_example.py",
    )
    assert orphan_modules(tmp_path, frozenset(), cited, support) == (
        "tests/test_example.py",
    )
    assert orphan_modules(tmp_path, collected, cited, support | cited) == (
        "tests/test_example.py",
    )
    assert orphan_modules(tmp_path, frozenset(), cited, support, cited) == ()
    assert orphan_modules(tmp_path, frozenset(), frozenset(), support, cited) == (
        "tests/test_example.py",
    )
    missing = frozenset({"tests/test_missing.py"})
    assert orphan_modules(tmp_path, collected, cited | missing, support, missing) == (
        "tests/test_missing.py",
    )


def test_evidence_marker_required(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Require a singular marker from the closed evidence vocabulary."""
    _suite(pytester, monkeypatch)
    assert _run(pytester).ret == 0
    for marker in (
        "",
        'pytestmark = pytest.mark.evidence("owed")',
        'pytestmark = [pytest.mark.evidence("value"), pytest.mark.evidence("real")]',
        'pytestmark = pytest.mark.evidence("value", extra=True)',
    ):
        pytester.makepyfile(
            SAMPLE.replace('pytestmark = pytest.mark.evidence("value")', marker)
        )
        assert _run(pytester).ret == 1


def test_manifest_matches_execution(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Distinguish collected ids from actually executed and passed ids."""
    path = _suite(pytester, monkeypatch)
    assert _run(pytester).ret == 0
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["nonce"] == "nested-nonce"
    assert data["collected"] == data["executed"] == data["passed"]
    assert data["collected"]
    pytester.makeconftest(
        "def pytest_collection_finish(session):\n"
        "    session.shouldstop = 'negative interrupted session'\n"
    )
    assert _run(pytester).ret != 0
    data = json.loads(path.read_text(encoding="utf-8"))
    assert set(data["collected"]) != set(data["executed"]), (
        "manifest invented execution"
    )


def test_collection_error_preserves_other_execution(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A broken module is recorded while an independent test really executes."""
    manifest = _suite(pytester, monkeypatch)
    assert _run(pytester, "--continue-on-collection-errors").ret == 0
    (pytester.path / "tests").mkdir()
    (pytester.path / "test_collection_error_preserves_other_execution.py").rename(
        pytester.path / "tests/test_early.py"
    )
    (pytester.path / "tests/test_broken.py").write_text(
        "def invalid(:\n", encoding="utf-8"
    )
    plan = pytester.path / "DEVELOPMENT_PLAN"
    plan.mkdir()
    (plan / "phase-example.md").write_text(
        "`tests/test_early.py::test_one`\n`tests/test_broken.py::test_missing`\n",
        encoding="utf-8",
    )
    assert _run(pytester, "--continue-on-collection-errors").ret != 0
    data = json.loads(manifest.read_text(encoding="utf-8"))
    assert "collection failed: tests/test_broken.py" in data["forbidden"]
    assert data["executed"] == [
        "tests/test_early.py::test_one",
        "tests/test_early.py::test_two",
    ]
    assert data["collected"] == data["executed"] == data["passed"]
    parsed = parse_manifest(data)
    assert isinstance(parsed, Ok)
    scopes = (
        CollectionScope(
            0,
            frozenset({"tests/test_early.py::test_one"}),
            frozenset({"tests/test_early.py"}),
        ),
        CollectionScope(
            1,
            frozenset({"tests/test_broken.py::test_missing"}),
            frozenset({"tests/test_broken.py"}),
        ),
    )
    observed = observe_collection(parsed.value, "nested-nonce")
    result = collection_failures(scopes, observed)
    assert isinstance(result, Ok)
    assert not result.value[0][1]
    assert "collection failed: tests/test_broken.py" in result.value[1][1]


def test_parametrized_phase_citation_uses_real_execution(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Use the real plugin's case IDs and outcomes for a phase test citation."""
    source = (
        'import pytest\npytestmark = pytest.mark.evidence("value")\n'
        '@pytest.mark.parametrize("case", ["first", "second"])\n'
        "def test_cases(case):\n    assert case != 'FAIL'\n"
    )
    manifest = _suite(pytester, monkeypatch, source)
    citation = "test_parametrized_phase_citation_uses_real_execution.py::test_cases"
    phases = (
        PhaseInputs(0, frozenset({"source"}), frozenset({citation}), frozenset()),
    )
    passed_checks = steps.__dict__["_passed_phase_checks"]
    assert _run(pytester).ret == 0
    complete = parse_manifest(json.loads(manifest.read_text(encoding="utf-8")))
    assert isinstance(complete, Ok)
    assert passed_checks(phases, complete.value, "nested-nonce") == frozenset(
        {citation}
    ), "passing parameter cases were lost"
    (
        pytester.path / "test_parametrized_phase_citation_uses_real_execution.py"
    ).write_text(source.replace("'FAIL'", "'second'"), encoding="utf-8")
    assert _run(pytester).ret != 0
    failed = parse_manifest(json.loads(manifest.read_text(encoding="utf-8")))
    assert isinstance(failed, Ok)
    assert citation not in passed_checks(phases, failed.value, "nested-nonce"), (
        "incomplete parameter cases passed"
    )


def test_fixture_failures_remain_shared(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Setup and teardown failures cannot masquerade as local test-body failures."""
    manifest = _suite(pytester, monkeypatch)
    module = "test_fixture_failures_remain_shared.py"
    early, late = module + "::test_one", module + "::test_two"
    scopes = (
        CollectionScope(0, frozenset({early}), frozenset({module})),
        CollectionScope(1, frozenset({late}), frozenset({module})),
    )
    consumers = ((early, frozenset({0})), (late, frozenset({1})))
    for body in (
        "raise RuntimeError('setup')\n    yield",
        "yield\n    raise RuntimeError('teardown')",
    ):
        (pytester.path / module).write_text(
            'import pytest\npytestmark = pytest.mark.evidence("value")\n'
            "@pytest.fixture\ndef fixture():\n    " + body + "\n"
            "def test_one():\n    assert True\n"
            "def test_two(fixture):\n    assert True\n",
            encoding="utf-8",
        )
        assert _run(pytester).ret != 0
        parsed = parse_manifest(json.loads(manifest.read_text(encoding="utf-8")))
        assert isinstance(parsed, Ok)
        observation = observe_collection(parsed.value, "nested-nonce")
        result = collection_failures(scopes, observation, case_consumers=consumers)
        assert isinstance(result, Ok)
        assert all(
            "fixture phase failed: " + late in failures for _, failures in result.value
        ), "fixture failure did not invalidate all consumers"


def test_coverage_gap_fails(tmp_path: Path) -> None:
    """A real uncovered branch fails at 100; exercising both arms qualifies."""
    (tmp_path / "pyproject.toml").write_text(
        '[tool.coverage.run]\nbranch = true\nsource = ["subject"]\n'
        "[tool.coverage.report]\nfail_under = 100\n",
        encoding="utf-8",
    )
    source = tmp_path / "src" / "agentctl"
    source.mkdir(parents=True)
    (source / "subject.py").write_text(
        "def choose(value: bool) -> int:\n"
        "    if value:\n        return 1\n    return 2\n",
        encoding="utf-8",
    )
    program = source / "exercise.py"
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("COVERAGE_")
    }
    for calls, expected in (("choose(True)", 2), ("choose(True); choose(False)", 0)):
        program.write_text(
            "from subject import choose\n" + calls + "\n", encoding="utf-8"
        )
        result = run(
            [
                sys.executable,
                "-m",
                "coverage",
                "run",
                "--rcfile=pyproject.toml",
                "--data-file=coverage",
                str(program),
            ],
            cwd=tmp_path,
            env=env,
        )
        assert isinstance(result, Ok)
        assert result.value.code == 0
        report = run(
            list(coverage_commands(sys.executable, tmp_path, tmp_path)[-1]),
            cwd=tmp_path,
            env=env,
        )
        assert isinstance(report, Ok)
        assert report.value.code == expected, "coverage gap was accepted"


def test_coverage_json_reports_native_branches(tmp_path: Path) -> None:
    """The real coverage tool reports a missing branch, then complete coverage."""
    source = tmp_path / "src" / "agentctl"
    source.mkdir(parents=True)
    subject = source / "subject.py"
    subject.write_text(
        "import sys\nif sys.argv[1] == 'yes':\n    print('yes')\n"
        "else:\n    print('no')\n",
        encoding="utf-8",
    )
    (tmp_path / "pyproject.toml").write_text(
        '[project.optional-dependencies]\ndev = ["coverage==7.17.0"]\n'
        '[tool.coverage.run]\nbranch = true\nsource = ["src/agentctl"]\n',
        encoding="utf-8",
    )
    manifest = source / "check" / "coverage_hosts.toml"
    manifest.parent.mkdir()
    manifest.write_text(
        "version = 1\n[[source]]\npath = 'src/agentctl/subject.py'\n"
        "hosts = ['Linux', 'Darwin', 'Windows']\n",
        encoding="utf-8",
    )
    (manifest.parent / "source_ownership.toml").write_text(
        "version = 1\n"
        "[[phases]]\nnumber = 0\nprerequisites = []\n"
        "[[phases]]\nnumber = 1\nprerequisites = [0]\n"
        "[[artifacts]]\npath = 'src/agentctl/subject.py'\n"
        "capability = 'subject'\nowner = 0\nconsumers = [0, 1]\nrequired = true\n",
        encoding="utf-8",
    )
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("COVERAGE_")
    }
    for argument, append, expected in (
        ("yes", (), (1, 1)),
        ("no", ("--append",), (0, 0)),
    ):
        recorded = run(
            [
                sys.executable,
                "-m",
                "coverage",
                "run",
                "--rcfile=pyproject.toml",
                "--data-file=coverage",
                *append,
                str(subject),
                argument,
            ],
            cwd=tmp_path,
            env=env,
        )
        assert isinstance(recorded, Ok)
        assert recorded.value.code == 0
        rendered = run(
            [
                sys.executable,
                "-m",
                "coverage",
                "json",
                "--rcfile=pyproject.toml",
                "--data-file=coverage",
                "-o",
                "real-report.json",
            ],
            cwd=tmp_path,
            env=env,
        )
        assert isinstance(rendered, Ok)
        assert rendered.value.code == 0
        observed = coverage_hosts.parse_report(
            (tmp_path / "real-report.json").read_text(encoding="utf-8"), "7.17.0"
        )
        assert isinstance(observed, Ok)
        assert observed == Ok(
            (coverage_hosts.CoverageFact("src/agentctl/subject.py", *expected),)
        )
        transcript = run(
            [
                sys.executable,
                "-m",
                "coverage",
                "report",
                "--rcfile=pyproject.toml",
                "--data-file=coverage",
                "--fail-under=100",
            ],
            cwd=tmp_path,
            env=env,
        )
        assert isinstance(transcript, Ok)
        assert steps.coverage_text_floor(transcript.value) == Ok(
            "floor" if argument == "yes" else "complete"
        )
        if argument == "yes":
            _check_incomplete_coverage_capture(tmp_path, observed.value)
        else:
            _check_complete_coverage_capture(tmp_path, observed.value)


def _finalizer_marker(directory: Path, nonce: str) -> str:
    """Read the real finalizer record used by a coverage handoff control."""
    final = steps.finalizer_observation(directory, nonce)
    assert isinstance(final, Ok)
    return steps.finalizer_seal(final.value)


def _check_incomplete_coverage_capture(
    tmp_path: Path, facts: tuple[coverage_hosts.CoverageFact, ...]
) -> None:
    """Refuse changed, replayed or inconsistent incomplete reports."""
    report_file = tmp_path / "real-report.json"
    report_bytes = report_file.read_bytes()
    render = steps.__dict__["_coverage_rendered"]
    for json_status, report_status in ((0, 2), (2, 0)):
        assert isinstance(
            render(
                report_bytes,
                report_bytes.decode("utf-8"),
                steps.CoverageRequest("7.17.0", (), report_status),
                json_status,
                report_file.stat(),
            ),
            Err,
        ), "coverage status mismatch was accepted"
    entries = source_census(tmp_path)
    assert isinstance(entries, Ok)
    nonce = "a" * 32
    leg = Leg("pytest", (), coverage_commands(sys.executable, tmp_path, tmp_path))
    substeps = Ok(ToolSubsteps(nonce, (("pytest", (0, 0, 2)),)))
    context = CheckRun(tmp_path, tmp_path, nonce, "Linux")
    assert isinstance(
        capture_coverage(
            replace(context, nonce="bad"),
            entries.value,
            leg,
            Ok(ToolSubsteps("bad", (("pytest", (0, 0, 2)),))),
        ),
        Err,
    ), "invalid coverage nonce was accepted"
    assert isinstance(capture_coverage(context, (), leg, substeps), Err)
    assert isinstance(
        capture_coverage(context, entries.value, replace(leg, after=()), substeps),
        Err,
    )
    assert isinstance(
        capture_coverage(
            context,
            entries.value,
            leg,
            Ok(ToolSubsteps(nonce, (("pytest", (0, 0)),))),
        ),
        Err,
    )
    captured = capture_coverage(context, entries.value, leg, substeps)
    assert isinstance(captured, Ok), captured
    assert captured.value.facts == facts
    _check_coverage_phase_observation(entries.value, captured.value, has_gap=True)
    assert coverage_snapshot_unchanged(tmp_path, nonce, captured) == 0
    _check_coverage_parent_retention(tmp_path, captured.value)
    seal = steps.coverage_seal(nonce, captured.value.record, captured.value.report)
    output = f"{seal}\nkiller\nprovisional\n{_finalizer_marker(tmp_path, nonce)}\n"
    assert steps.verify_coverage_handoff(tmp_path, nonce, output) == Ok(None)
    assert isinstance(
        steps.verify_coverage_handoff(tmp_path, nonce, seal + "\n" + output), Err
    ), "ambiguous coverage handoff was accepted"
    revised_raw = json.dumps(json.loads(captured.value.report), sort_keys=True).encode()
    assert revised_raw != captured.value.report
    revised_record = json.loads(captured.value.record)
    revised_record["report"] = revised_raw.decode("utf-8")
    (tmp_path / "coverage-raw.json").write_bytes(revised_raw)
    (tmp_path / "coverage-report.json").write_text(
        json.dumps(revised_record, sort_keys=True), encoding="utf-8"
    )
    assert steps.verify_coverage_handoff(tmp_path, nonce, output) == Err(
        "coverage handoff digest mismatch"
    ), "coverage handoff digest mismatch was ignored"
    (tmp_path / "coverage-raw.json").write_bytes(captured.value.report)
    (tmp_path / "coverage-report.json").write_bytes(captured.value.record)
    assert coverage_snapshot_unchanged(tmp_path, nonce, captured) == 0
    assert isinstance(capture_coverage(context, entries.value, leg, substeps), Err), (
        "coverage capture overwrote an existing report"
    )
    assert coverage_snapshot_unchanged(tmp_path, nonce, captured) == 0, (
        "coverage raw report was overwritten"
    )
    (tmp_path / "coverage-report.json").write_bytes(captured.value.record + b" ")
    assert coverage_snapshot_unchanged(tmp_path, nonce, captured) == 1, (
        "changed coverage record was accepted"
    )
    (tmp_path / "coverage-report.json").write_bytes(captured.value.record)
    assert coverage_snapshot_unchanged(tmp_path, "b" * 32, captured) == 1, (
        "foreign coverage nonce was accepted"
    )
    raw = tmp_path / "coverage-raw.json"
    raw.write_bytes(captured.value.report + b" ")
    assert coverage_snapshot_unchanged(tmp_path, nonce, captured) == 1, (
        "changed raw coverage was accepted"
    )
    raw.write_bytes(captured.value.report)
    assert coverage_snapshot_unchanged(tmp_path, nonce, captured) == 0
    replacement = tmp_path / "replacement.json"
    replacement.write_bytes(captured.value.record)
    replacement.replace(tmp_path / "coverage-report.json")
    assert coverage_snapshot_unchanged(tmp_path, nonce, captured) == 1, (
        "replaced coverage record was accepted"
    )


def _check_coverage_parent_retention(
    run_dir: Path, captured: steps.CoverageSnapshot
) -> None:
    """Change only the parent's copied coverage report with a real audit hook."""
    script = (
        "import sys\nfrom pathlib import Path\n"
        "from agentctl.check import mutant_report, steps\n"
        "from agentctl.foundation import Err, Ok\n"
        "from agentctl.foundation_process_values import Output\n"
        "run_dir, root, state = map(Path, sys.argv[1:4]); nonce = sys.argv[4]\n"
        "root.mkdir()\n"
        "killer_path = run_dir / 'mutant-killers.json'\n"
        'killer_path.write_text(\'{"nonce":"\' + nonce + \'","records":[]}\', '
        "encoding='utf-8')\n"
        "killer = mutant_report.read(killer_path, nonce)\n"
        "ruff = steps.record_ruff_snapshot(run_dir, "
        "steps.RuffSnapshot(nonce, root, Output(0, '[]', ''), ()))\n"
        "final = steps.record_finalizers(run_dir, nonce, "
        "tuple((name, int(name in {'python-commands', 'ruff-format-observation', "
        "'tool-outcomes', 'pytest-manifest', 'oracle-outcomes', 'host-observation', "
        "'native-observation', 'ty-observation', "
        "'coverage-text-observation'})) "
        "for name in steps.FINALIZER_NAMES[:-1]))\n"
        "phase = steps.record_provisional_phases(run_dir, nonce, Err('unavailable'))\n"
        "assert isinstance(ruff, Ok) and isinstance(killer, Ok) "
        "and isinstance(final, Ok) "
        "and isinstance(phase, Ok)\n"
        "record = (run_dir / 'coverage-report.json').read_bytes()\n"
        "raw = (run_dir / 'coverage-raw.json').read_bytes()\n"
        "output = '\\n'.join((steps.ruff_seal(nonce, ruff.value.record), "
        "steps.coverage_seal(nonce, record, raw), "
        "steps.killer_seal(nonce, killer.value), "
        "steps.provisional_seal(nonce, phase.value), "
        "steps.finalizer_seal(final.value), ''))\n"
        "assert steps.verify_coverage_handoff(run_dir, nonce, output) == Ok(None)\n"
        "ok_state = state.with_name(state.name + '-ok')\n"
        "context = steps.CheckRun(root, run_dir, nonce, sys.argv[5])\n"
        "valid = steps.retain_verified_gate_output("
        "context, ok_state, (output, 'primary\\n'), verify_handoff=True)\n"
        "assert isinstance(valid, Ok), valid\n"
        "assert (valid.value / 'coverage-raw.json').read_bytes() == raw\n"
        "assert (valid.value / 'coverage-report.json').read_bytes() == record\n"
        "target = state / 'check-reports' / nonce / 'coverage-raw.json'\n"
        "seen = [False]\n"
        "def audit(event, args):\n"
        "    if (not seen[0] and event == 'open' and str(args[0]) == str(target) "
        "and 'r' in str(args[1]) and target.exists()):\n"
        "        seen[0] = True\n"
        "        with target.open('ab') as stream: stream.write(b' ')\n"
        "sys.addaudithook(audit)\n"
        "result = steps.retain_verified_gate_output("
        "context, state, (output, 'primary\\n'), verify_handoff=True)\n"
        "assert isinstance(result, Err), 'post-copy coverage tampering was accepted'\n"
        "assert seen[0], 'coverage tamper hook did not run'\n"
        "retained = state / 'check-reports' / nonce\n"
        "assert 'coverage handoff' in "
        "(retained / 'finalizer-handoff.txt').read_text()\n"
        "assert (retained / 'stderr.txt').read_text() == 'primary\\n'\n"
    )
    family = sys.platform
    native = (
        "Windows" if family == "win32" else "Darwin" if family == "darwin" else "Linux"
    )
    root = run_dir / "checkout"
    state = run_dir.parent / (run_dir.name + "-coverage-state")
    child = run(
        [
            sys.executable,
            "-c",
            script,
            str(run_dir),
            str(root),
            str(state),
            captured.nonce,
            native,
        ],
        cwd=run_dir,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    assert isinstance(child, Ok)
    assert child.value.code == 0, child.value.stderr


def _check_coverage_phase_observation(
    entries: tuple[Entry, ...], captured: steps.CoverageSnapshot, *, has_gap: bool
) -> None:
    """Join the real report to the exact captured census and host family."""
    phases = (
        steps.phase_reports.PhaseInputs(
            0, frozenset({"early"}), frozenset({"a"}), frozenset()
        ),
        steps.phase_reports.PhaseInputs(
            1, frozenset({"late"}), frozenset({"b"}), frozenset({0})
        ),
    )
    host = Ok(
        steps.lanes.HostFacts(
            family="Linux", architecture="x86_64", checkout=True, git=True
        )
    )
    substeps = Ok(
        ToolSubsteps(captured.nonce, (("pytest", (0, 0, 2 if has_gap else 0)),))
    )
    inputs = steps.CoverageAttributionInputs(
        entries, phases, captured.nonce, "Linux", host, Ok(captured), substeps
    )
    gap = (
        frozenset({"coverage incomplete: src/agentctl/subject.py"})
        if has_gap
        else frozenset()
    )
    assert steps.coverage_phase_observations(inputs) == Ok(((0, gap), (1, gap))), (
        "captured coverage did not reach every source consumer"
    )
    tools = steps.ToolOutcome(1, Err("unused"), substeps, host=host)
    provisional = steps.ProvisionalCapture(
        Ok(entries),
        Err("unused"),
        tools,
        None,
        Err("unused"),
        captured.nonce,
        (),
        (),
        coverage=Ok(captured),
        family="Linux",
    )
    initial = steps.ToolFailureAttribution(
        frozenset({"coverage report failed"}), ((0, frozenset()), (1, frozenset()))
    )
    join = steps.__dict__["_coverage_provisional_attribution"]
    assert join(provisional, entries, phases, initial) == Ok(
        steps.ToolFailureAttribution(initial.shared, ((0, gap), (1, gap)))
    ), "provisional coverage scope was lost"
    assert isinstance(
        join(replace(provisional, coverage=None), entries, phases, initial), Err
    ), "missing captured coverage was accepted"
    duplicate = replace(
        initial, scoped=((0, frozenset()), (0, frozenset()), (1, frozenset()))
    )
    assert isinstance(join(provisional, entries, phases, duplicate), Err), (
        "duplicate coverage phase scope was accepted"
    )
    for invalid in (
        replace(inputs, nonce="stale"),
        replace(
            inputs,
            host=Ok(
                steps.lanes.HostFacts(
                    family="Windows", architecture="x86_64", checkout=True, git=True
                )
            ),
        ),
        replace(inputs, coverage=Ok(replace(captured, entries=()))),
        replace(inputs, coverage=Ok(replace(captured, nonce="b" * 32))),
        replace(inputs, coverage=Ok(replace(captured, facts=()))),
        replace(inputs, coverage=Ok(replace(captured, record=b"{}"))),
        replace(inputs, coverage=Ok(replace(captured, report=captured.report + b" "))),
        replace(inputs, coverage=None),
        replace(inputs, host=None),
        replace(inputs, substeps=Err("unavailable")),
        replace(inputs, substeps=Ok(ToolSubsteps("stale", substeps.value.outcomes))),
        replace(
            inputs, substeps=Ok(ToolSubsteps(captured.nonce, (("pytest", (0, 0, 1)),)))
        ),
    ):
        assert isinstance(steps.coverage_phase_observations(invalid), Err), (
            "foreign or inconsistent coverage observation was accepted"
        )
    unowned = (*entries, Entry("src/agentctl/unowned.py", "file", (b"pass\n",)))
    invalid = replace(
        inputs, entries=unowned, coverage=Ok(replace(captured, entries=unowned))
    )
    assert isinstance(steps.coverage_phase_observations(invalid), Err), (
        "unowned coverage source was accepted"
    )


def _check_complete_coverage_capture(
    tmp_path: Path, facts: tuple[coverage_hosts.CoverageFact, ...]
) -> None:
    """Capture complete coverage and reject raw-file replacement."""
    complete_run = tmp_path / "complete-run"
    complete_run.mkdir()
    (complete_run / "coverage").write_bytes((tmp_path / "coverage").read_bytes())
    entries = source_census(tmp_path)
    assert isinstance(entries, Ok)
    nonce = "c" * 32
    leg = Leg("pytest", (), coverage_commands(sys.executable, tmp_path, complete_run))
    captured = capture_coverage(
        CheckRun(tmp_path, complete_run, nonce, "Linux"),
        entries.value,
        leg,
        Ok(ToolSubsteps(nonce, (("pytest", (0, 0, 0)),))),
    )
    assert isinstance(captured, Ok), captured
    assert captured.value.facts == facts
    _check_coverage_phase_observation(entries.value, captured.value, has_gap=False)
    assert coverage_snapshot_unchanged(complete_run, nonce, captured) == 0
    replacement = complete_run / "replacement-raw.json"
    replacement.write_bytes(captured.value.report)
    replacement.replace(complete_run / "coverage-raw.json")
    assert coverage_snapshot_unchanged(complete_run, nonce, captured) == 1, (
        "replaced raw coverage was accepted"
    )


def test_plugin_collection_boundaries(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Observe an empty suite, actual failures and a cited/support module join."""
    manifest = _suite(pytester, monkeypatch)
    assert _run(pytester).ret == 0
    original = pytester.path / "test_plugin_collection_boundaries.py"
    original.write_text("", encoding="utf-8")
    assert _run(pytester).ret == 1
    assert "empty collection" in manifest.read_text(encoding="utf-8")
    original.write_text(
        SAMPLE.replace("assert 1 == 1", "assert 1 == 2"), encoding="utf-8"
    )
    assert _run(pytester).ret == 1
    assert "failed:" in manifest.read_text(encoding="utf-8")
    assert _run(pytester, "-p", "no:terminal").ret == 1
    tests = pytester.path / "tests"
    tests.mkdir()
    original.unlink()
    (tests / "test_subject.py").write_text(SAMPLE, encoding="utf-8")
    (tests / "__init__.py").write_text("", encoding="utf-8")
    (tests / "support.txt").write_text("tests/__init__.py\n", encoding="utf-8")
    plan = pytester.path / "DEVELOPMENT_PLAN"
    plan.mkdir()
    (plan / "phase-example.md").write_text(
        "`tests/test_subject.py::test_one`\n", encoding="utf-8"
    )
    assert _run(pytester).ret == 0
    (tests / "helper.py").write_text("value = 1", encoding="utf-8")
    assert _run(pytester).ret == 1
    assert "tests.orphan-modules" in manifest.read_text(encoding="utf-8")
    (tests / "helper.py").unlink()
    (tests / "support.txt").unlink()
    assert _run(pytester).ret == 1
    (tests / "__init__.py").unlink()
    assert _run(pytester).ret == 0
    monkeypatch.delenv("AGENTCTL_CHECK_MANIFEST")
    monkeypatch.delenv("AGENTCTL_CHECK_NONCE")
    assert _run(pytester).ret == 0


def test_coverage_text_parent_joins_real_report_and_retained_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Join a real coverage report to its retained facts and subprocess statuses."""
    project, directory = tmp_path / "project", tmp_path / "run"
    source = project / "src/agentctl"
    source.mkdir(parents=True)
    directory.mkdir()
    subject = source / "subject.py"
    subject.write_text(
        "if __name__ == '__main__':\n    print('run')\n", encoding="utf-8"
    )
    (project / "pyproject.toml").write_text(
        '[project.optional-dependencies]\ndev = ["coverage==7.17.0"]\n'
        '[tool.coverage.run]\nbranch = true\nsource = ["src/agentctl"]\n',
        encoding="utf-8",
    )
    manifest = source / "check/coverage_hosts.toml"
    manifest.parent.mkdir()
    manifest.write_text(
        "version = 1\n[[source]]\npath = 'src/agentctl/subject.py'\n"
        "hosts = ['Linux', 'Darwin', 'Windows']\n",
        encoding="utf-8",
    )
    (manifest.parent / "source_ownership.toml").write_text(
        "version = 1\n"
        "[[phases]]\nnumber = 0\nprerequisites = []\n"
        "[[phases]]\nnumber = 1\nprerequisites = [0]\n"
        "[[artifacts]]\npath = 'src/agentctl/subject.py'\n"
        "capability = 'later'\nowner = 1\nconsumers = [1]\nrequired = true\n",
        encoding="utf-8",
    )
    nonce = "a" * 32
    context = CheckRun(project, directory, nonce, "Linux")
    commands = coverage_commands(sys.executable, project, directory)
    leg = Leg(
        "pytest",
        (
            sys.executable,
            "-m",
            "coverage",
            "run",
            "--branch",
            "--parallel-mode",
            f"--rcfile={project / 'pyproject.toml'}",
            f"--data-file={directory / 'coverage'}",
            str(subject),
        ),
        commands,
        after_failure=True,
    )
    observed = steps.__dict__["_run_leg_observed"](project, directory, nonce, leg)
    assert observed.substeps == (0, 0, steps.COVERAGE_REPORT_FAILURE)
    text = observed.coverage_text
    assert isinstance(text, Ok), "real report transcript was not captured"
    entries = source_census(project)
    assert isinstance(entries, Ok)
    substeps = Ok(ToolSubsteps(nonce, (("pytest", observed.substeps),)))
    coverage = capture_coverage(context, entries.value, leg, substeps)
    assert isinstance(coverage, Ok), coverage
    inputs = steps.CoverageTextInputs(
        context, entries.value, leg, substeps, text, coverage
    )
    assert steps.coverage_text_agreement(inputs) == Ok(None)
    _check_coverage_text_json_integrity(inputs, coverage.value)
    for name, outcomes in (
        ("tool-outcomes.json", [["pytest", 2]]),
        ("tool-substeps.json", [["pytest", [0, 0, 2]]]),
    ):
        (directory / name).write_text(
            json.dumps({"nonce": nonce, "outcomes": outcomes}), encoding="utf-8"
        )
    _check_coverage_text_localization(inputs, monkeypatch)
    tools = steps.__dict__["_read_sealed_tool_results"](directory, nonce)
    assert isinstance(tools, Ok)
    passed = {
        "coverage-text-observation",
        "coverage-observation",
        "tool-outcomes",
        "tool-substeps",
    }
    final = steps.record_finalizers(
        directory,
        nonce,
        tuple((name, int(name not in passed)) for name in steps.FINALIZER_NAMES[:-1]),
    )
    phase = steps.record_provisional_phases(directory, nonce, Err("unavailable"))
    assert isinstance(final, Ok)
    assert isinstance(phase, Ok)
    output = "\n".join(
        (
            steps.coverage_text_seal(nonce, text.value.record),
            steps.tool_results_seal(nonce, *tools.value),
            steps.coverage_seal(nonce, coverage.value.record, coverage.value.report),
            steps.provisional_seal(nonce, phase.value),
            steps.finalizer_seal(final.value),
            "",
        )
    )
    monkeypatch.setattr(
        steps.ownership, "guarded_census", lambda _root: source_census(project)
    )
    assert steps.verify_coverage_text_handoff(context, directory, output) == Ok(None)
    retained = steps.retain_verified_gate_output(
        context, tmp_path / "state", (output, ""), verify_handoff=True
    )
    assert isinstance(retained, Ok), retained
    _check_coverage_text_copy(context, tmp_path, output, monkeypatch)
    _check_coverage_text_forgery(context, output, text.value.record)


def _check_coverage_text_localization(
    inputs: steps.CoverageTextInputs, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Keep earlier phases clear only for an intact later-owned floor failure."""
    phases = (
        steps.phase_reports.PhaseInputs(0, frozenset(), frozenset(), frozenset()),
        steps.phase_reports.PhaseInputs(1, frozenset(), frozenset(), frozenset({0})),
    )
    host = Ok(
        steps.lanes.HostFacts(
            family="Linux", architecture="x86_64", checkout=True, git=True
        )
    )
    tools = steps.ToolOutcome(
        1, Err("unused"), inputs.substeps, host=host, coverage_text=inputs.text
    )
    capture = steps.ProvisionalCapture(
        Ok(inputs.entries),
        Err("unused"),
        tools,
        None,
        Err("unused"),
        inputs.context.nonce,
        (),
        (),
        coverage=inputs.coverage,
        family="Linux",
        coverage_context=inputs.context,
        coverage_leg=inputs.leg,
    )
    initial = steps.ToolFailureAttribution(
        frozenset({"coverage report failed", "independent failure"}),
        ((0, frozenset()), (1, frozenset())),
    )
    join = steps.__dict__["_coverage_provisional_attribution"]
    result = join(capture, inputs.entries, phases, initial)
    assert result == Ok(
        steps.ToolFailureAttribution(
            frozenset({"independent failure"}),
            (
                (0, frozenset()),
                (1, frozenset({"coverage incomplete: src/agentctl/subject.py"})),
            ),
        )
    ), "later coverage floor failure was not localized"
    _check_parent_coverage_scopes(inputs, phases, host, monkeypatch)
    missing = replace(capture, tools=replace(tools, coverage_text=None))
    refused = join(missing, inputs.entries, phases, initial)
    assert isinstance(refused, Ok)
    assert refused.value.shared == initial.shared, (
        "unverified coverage failure was localized"
    )
    assert isinstance(inputs.text, Ok)
    stale = replace(
        capture,
        tools=replace(
            tools, coverage_text=Ok(replace(inputs.text.value, nonce="b" * 32))
        ),
    )
    refused = join(stale, inputs.entries, phases, initial)
    assert isinstance(refused, Ok)
    assert refused.value.shared == initial.shared, (
        "foreign coverage transcript was localized"
    )
    record = inputs.context.directory / "coverage-text.json"
    record.write_bytes(inputs.text.value.record + b" ")
    damaged = join(capture, inputs.entries, phases, initial)
    record.write_bytes(inputs.text.value.record)
    assert isinstance(damaged, Ok)
    assert damaged.value.shared == initial.shared, (
        "changed coverage transcript was localized"
    )
    assert isinstance(inputs.coverage, Ok)
    json_record = inputs.context.directory / "coverage-report.json"
    json_record.write_bytes(inputs.coverage.value.record + b" ")
    damaged_json = join(capture, inputs.entries, phases, initial)
    json_record.write_bytes(inputs.coverage.value.record)
    assert isinstance(damaged_json, Ok)
    assert damaged_json.value.shared == initial.shared, (
        "changed coverage JSON was localized"
    )


def _check_parent_coverage_scopes(
    inputs: steps.CoverageTextInputs,
    phases: tuple[steps.phase_reports.PhaseInputs, ...],
    host: Result[steps.lanes.HostFacts, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Check retained real coverage gaps against phase ownership and both routes."""
    observed = (
        steps.phase_reports.PhaseResult(0, "a" * 64, frozenset({"unverified-run"})),
        steps.phase_reports.PhaseResult(
            1,
            "b" * 64,
            frozenset(
                {"unverified-run", "coverage incomplete: src/agentctl/subject.py"}
            ),
        ),
    )
    forged = (observed[0], replace(observed[1], failures=frozenset({"unverified-run"})))
    scope = steps.CoverageAttributionInputs(
        inputs.entries,
        phases,
        inputs.context.nonce,
        inputs.context.family,
        host,
        inputs.coverage,
        inputs.substeps,
    )
    assert steps.verify_phase_coverage_failures(scope, observed) == Ok(None)
    assert isinstance(steps.verify_phase_coverage_failures(scope, forged), Err), (
        "parent accepted hidden coverage gap"
    )
    with monkeypatch.context() as patch:
        patch.setattr(steps, "_parent_bound_census", lambda *_args: Ok(inputs.entries))
        patch.setattr(steps, "census_phases", lambda *_args: Ok(()))
        work = steps.ownership.ScopedPhaseWork(
            steps.ownership.PhaseWork(phases, ()), ()
        )
        patch.setattr(steps, "scoped_source_inputs", lambda *_args: Ok(work))
        patch.setattr(steps, "host_observation", lambda *_args: host)
        rebuilt = steps.__dict__["_parent_coverage_inputs"](
            inputs.context, inputs.context.directory, ""
        )
        assert isinstance(rebuilt, Ok), rebuilt
        assert steps.verify_phase_coverage_failures(rebuilt.value, observed) == Ok(None)
        patch.setattr(
            steps.ownership, "guarded_census", lambda *_args: Ok(inputs.entries)
        )
        patch.setattr(steps, "_parent_bound_census", lambda *_args: Err("changed"))
        assert isinstance(
            steps.__dict__["_parent_coverage_inputs"](
                inputs.context, inputs.context.directory, ""
            ),
            Err,
        ), "unbound parent coverage census was accepted"
        patch.setattr(steps, "_parent_bound_census", lambda *_args: Ok(inputs.entries))
        _check_parent_coverage_routes(
            inputs.context, rebuilt.value, observed, forged, patch
        )


def _check_parent_coverage_routes(
    context: CheckRun,
    inputs: steps.CoverageAttributionInputs,
    observed: tuple[steps.phase_reports.PhaseResult, ...],
    forged: tuple[steps.phase_reports.PhaseResult, ...],
    patch: pytest.MonkeyPatch,
) -> None:
    """Run the parent coverage recheck on both live and retained paths."""
    final = steps.evidence.LegEvidence(
        context.nonce, tuple((name, 0) for name in steps.FINALIZER_NAMES[:-1])
    )
    assert isinstance(inputs.coverage, Ok)
    assert isinstance(inputs.host, Ok)
    assert isinstance(inputs.outcomes, Ok)
    assert isinstance(inputs.substeps, Ok)
    coverage, host, outcomes, substeps = (
        inputs.coverage.value,
        inputs.host.value,
        inputs.outcomes.value,
        inputs.substeps.value,
    )
    output = "\n".join(
        (
            steps.coverage_seal(context.nonce, coverage.record, coverage.report),
            steps.host_observation_seal(context.nonce, host),
            steps.tool_results_seal(context.nonce, outcomes, substeps),
        )
    )
    output += "\n" + steps.finalizer_seal(final)
    assert steps.coverage_inputs_sealed(inputs, output)
    patch.setattr(steps, "finalizer_observation", lambda *_args: Ok(final))
    patch.setattr(
        steps, "_provisional_values_for_identity", lambda *_args: Ok(observed)
    )
    for name in (
        "verify_python_commands_handoff",
        "verify_coverage_handoff",
        "verify_coverage_text_handoff",
        "verify_host_handoff",
        "verify_tool_results_handoff",
        "_verify_provisional_census",
        "verify_python_plan_handoff",
        "verify_provisional_input_identities",
        "verify_pytest_handoff",
        "verify_oracle_handoff",
        "verify_native_handoff",
        "verify_ty_handoff",
        "verify_provisional_collection",
        "verify_provisional_oracle",
        "verify_provisional_host",
        "verify_provisional_static",
        "verify_provisional_tools",
        "verify_provisional_validation",
        "verify_provisional_prerequisites",
        "verify_provisional_source",
        "verify_finalizer_handoff",
        "verify_provisional_handoff",
        "verify_provisional_finalizers",
        "verify_killer_handoff",
        "verify_ruff_handoff",
        "verify_ruff_format_handoff",
        "retain_handoff_failure",
    ):
        patch.setattr(steps, name, lambda *_args, **_kwargs: Ok(None))
    assert steps.verify_provisional_coverage(context, context.directory, output) == Ok(
        None
    )
    patch.setattr(steps, "_provisional_values_for_identity", lambda *_args: Ok(forged))
    assert isinstance(
        steps.verify_provisional_coverage(context, context.directory, output), Err
    ), "parent accepted hidden coverage gap"
    assert isinstance(steps.verify_python_handoffs(context, output), Err), (
        "live parent accepted hidden coverage gap"
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
    assert isinstance(retained, Err), "retained parent accepted hidden coverage gap"
    changed_report = coverage.report + b" "
    changed_wrapper = json.loads(coverage.record)
    changed_wrapper["report"] = changed_report.decode("utf-8")
    changed_record = json.dumps(changed_wrapper, sort_keys=True).encode()
    changes = (
        (
            replace(inputs, coverage=Ok(replace(coverage, facts=()))),
            "changed coverage facts were accepted",
        ),
        (
            replace(
                inputs,
                coverage=Ok(
                    replace(coverage, record=changed_record, report=changed_report)
                ),
            ),
            "changed coverage bytes after seal were accepted",
        ),
        (
            replace(
                inputs, coverage=Ok(replace(coverage, record=coverage.record + b" "))
            ),
            "changed coverage report was accepted",
        ),
        (
            replace(inputs, host=Ok(replace(host, checkout=not host.checkout))),
            "changed coverage host was accepted",
        ),
        (
            replace(inputs, outcomes=Ok(replace(outcomes, outcomes=()))),
            "changed coverage outcomes were accepted",
        ),
        (
            replace(inputs, substeps=Ok(replace(substeps, outcomes=()))),
            "changed coverage substeps were accepted",
        ),
        (
            replace(inputs, outcomes=Ok(replace(outcomes, nonce="stale"))),
            "stale coverage outcome nonce was accepted",
        ),
        (
            replace(inputs, substeps=Ok(replace(substeps, nonce="stale"))),
            "stale coverage substep nonce was accepted",
        ),
        (
            replace(inputs, coverage=Ok(replace(coverage, nonce="stale"))),
            "stale coverage nonce was accepted",
        ),
    )
    patch.setattr(steps, "verify_phase_coverage_failures", lambda *_args: Ok(None))
    for changed, reason in changes:
        assert not steps.coverage_inputs_sealed(changed, output), reason
        patch.setattr(
            steps,
            "_parent_coverage_inputs",
            lambda *_args, changed=changed: Ok(changed),
        )
        assert isinstance(
            steps.verify_provisional_coverage(context, context.directory, output), Err
        ), "parent accepted changed coverage inputs after seal"
        assert isinstance(steps.verify_python_handoffs(context, output), Err)
        assert isinstance(
            steps.retain_verified_gate_output(
                context, Path("/state"), (output, ""), verify_handoff=True
            ),
            Err,
        )


def _check_coverage_text_forgery(context: CheckRun, output: str, record: bytes) -> None:
    """Refuse a freshly sealed transcript that contradicts retained observations."""
    altered = json.loads(record)
    altered["code"] = 0
    altered["stdout"] = "TOTAL 1 0 100%\n"
    changed = json.dumps(altered, sort_keys=True).encode()
    (context.directory / "coverage-text.json").write_bytes(changed)
    forged = output.replace(
        steps.coverage_text_seal(context.nonce, record),
        steps.coverage_text_seal(context.nonce, changed),
    )
    assert isinstance(
        steps.verify_coverage_text_handoff(context, context.directory, forged), Err
    ), "a sealed transcript inconsistent with the real coverage facts was accepted"


def _check_coverage_text_json_integrity(
    inputs: steps.CoverageTextInputs, coverage: steps.CoverageSnapshot
) -> None:
    """Reject cached facts or raw JSON that differ from the original capture."""
    for invalid in (
        replace(coverage, facts=()),
        replace(
            coverage,
            facts=(
                replace(
                    coverage.facts[0],
                    missing_statements=coverage.facts[0].missing_statements + 1,
                ),
            ),
        ),
        replace(coverage, report=coverage.report + b" "),
        replace(coverage, record=b"{}"),
    ):
        assert isinstance(
            steps.coverage_text_agreement(replace(inputs, coverage=Ok(invalid))), Err
        ), "changed coverage facts or JSON were accepted"


def _check_coverage_text_copy(
    context: CheckRun, tmp_path: Path, output: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Refuse a transcript changed after the parent has retained the report."""
    original_retain = steps.retain_gate_output

    def corrupt_copy(
        root: Path, state: Path, run_dir: Path, run_nonce: str, streams: tuple[str, str]
    ) -> Result[Path, str]:
        result = original_retain(root, state, run_dir, run_nonce, streams)
        if isinstance(result, Ok):
            target = result.value / "coverage-text.json"
            target.write_bytes(target.read_bytes() + b" ")
        return result

    monkeypatch.setattr(steps, "retain_gate_output", corrupt_copy)
    altered_copy = steps.retain_verified_gate_output(
        context, tmp_path / "tampered-state", (output, "primary\n"), verify_handoff=True
    )
    assert isinstance(altered_copy, Err), "a changed retained transcript was accepted"
    assert (
        tmp_path / "tampered-state/check-reports" / context.nonce / "stderr.txt"
    ).read_text() == "primary\n"
