# Copyright (c) 2026 agentctl contributors.
"""Real scratch mutation controls and every executable corpus record."""

import hashlib
import json
import os
import sys
import tomllib
from dataclasses import replace
from pathlib import Path

import pytest

from agentctl.check.evidence import Entry, source_census
from agentctl.check.gate_plugin import KILLER_EXECUTION
from agentctl.check.mutants import (
    KillerExecution,
    KillerOutcome,
    Mutant,
    MutationError,
    Operator,
    amend_records,
    baseline,
    census_corpus,
    corpus,
    exercise,
    exercise_observed,
    killed,
    killer_verdict,
    parse,
    patch,
    scratch,
)
from agentctl.process import Output, run
from agentctl.result import Err, Ok

pytestmark = pytest.mark.evidence("real")


def test_guarded_corpus_matches_live_records(root: Path) -> None:
    """Snapshot parsing retains records and refuses missing provenance."""
    observed = source_census(root)
    assert isinstance(observed, Ok)
    entries = observed.value
    snapshot = census_corpus(entries)
    assert isinstance(snapshot, Ok)
    assert snapshot == corpus(root)
    assert isinstance(census_corpus((*entries, entries[0])), Err)
    assert isinstance(
        census_corpus(
            tuple(
                entry
                for entry in entries
                if entry.path != "DEVELOPMENT_PLAN/rationale.md"
            )
        ),
        Err,
    )
    bad = Entry("tests/mutants/bad.toml", "file", (b"\xff",))
    assert isinstance(census_corpus((*entries, bad)), Err)
    unanchored = tuple(
        Entry(entry.path, "file", (b"no amendment decisions\n",))
        if entry.path == "DEVELOPMENT_PLAN/rationale.md"
        else entry
        for entry in entries
    )
    assert isinstance(census_corpus(unanchored), Err), (
        "unanchored corpus amendment was accepted"
    )


def test_mutant_amendment_refusals(root: Path, tmp_path: Path) -> None:
    """Only a unique, documented amendment bound to both exact records applies."""
    document = tomllib.loads(
        (root / "tests/mutants/evidence.toml").read_text(encoding="utf-8")
    )
    original = document["mutant"]
    amendment = document["amendment"][0]
    assert isinstance(amend_records(original, [amendment], root), Ok)
    for changed in (
        {**amendment, "prior_sha256": "0" * 64},
        {**amendment, "revised_sha256": "0" * 64},
        {**amendment, "search": "other"},
        {**amendment, "provenance": "decision:D-999999"},
        {**amendment, "id": "M-evidence-unknown"},
        {**amendment, "extra": "invalid"},
    ):
        assert isinstance(amend_records(original, [changed], root), Err)
    assert isinstance(amend_records(original, [amendment, amendment], root), Err)
    assert isinstance(amend_records(original, [amendment], tmp_path), Err)


def test_mutant_amendment_chain_requires_exact_predecessor(
    root: Path, tmp_path: Path
) -> None:
    """A second revision binds the first and refuses replay, forks and no-ops."""
    document = tomllib.loads(
        (root / "tests/mutants/gate.toml").read_text(encoding="utf-8")
    )
    original = next(
        row for row in document["mutant"] if row["id"] == "M-legs-drop-pytest"
    )
    first = next(row for row in document["amendment"] if row["id"] == original["id"])
    plan = tmp_path / "DEVELOPMENT_PLAN"
    plan.mkdir()
    (plan / "rationale.md").write_text(
        "| D-90 | `M-legs-drop-pytest` |\n| D-110 | `M-legs-drop-pytest` |\n",
        encoding="utf-8",
    )
    observed = amend_records([original], [first], tmp_path)
    assert isinstance(observed, Ok)
    current = observed.value[0]
    assert isinstance(current, dict)
    revised = {**current, "search": str(current["search"]) + " revised"}

    def digest(value: dict[str, object]) -> str:
        canonical = json.dumps(
            value, sort_keys=True, ensure_ascii=True, allow_nan=False
        )
        return hashlib.sha256(canonical.encode()).hexdigest()

    second = {
        "id": original["id"],
        "prior_sha256": digest(current),
        "revised_sha256": digest(revised),
        "search": revised["search"],
        "replace": revised["replace"],
        "provenance": "decision:D-110",
    }
    assert amend_records([original], [first, second], tmp_path) == Ok((revised,))
    for chain in (
        [second, first],
        [first, second, second],
        [first, {**second, "prior_sha256": first["prior_sha256"]}],
        [
            first,
            {**second, "search": current["search"], "revised_sha256": digest(current)},
        ],
    ):
        assert isinstance(amend_records([original], chain, tmp_path), Err), (
            "invalid amendment chain was accepted"
        )


def _sample(root: Path) -> Path:
    """Build a disposable real subject and an independently written killer."""
    (root / "src").mkdir(parents=True)
    (root / "tests/unit").mkdir(parents=True)
    (root / "src/sample.py").write_text(
        "def answer():\n    return 2\n", encoding="utf-8"
    )
    (root / "tests/unit/test_subject.py").write_text(
        "from sample import answer\ndef test_answer():\n"
        '    assert answer() == 2, "named answer defect"\n',
        encoding="utf-8",
    )
    return root


def _record(**changes: object) -> dict[str, object]:
    """Name one minimal exact-once defect with a nonrecursive killer."""
    return {
        "id": "M-mutant-control",
        "operator": "replace-literal",
        "target": "src/sample.py",
        "search": "return 2",
        "replace": "return 3",
        "killers": ["tests/unit/test_subject.py::test_answer"],
        "reason": "named answer defect",
        **changes,
    }


def _parsed(**changes: object) -> Mutant:
    """Parse the test's independently authored record before execution."""
    result = parse(_record(**changes))
    assert isinstance(result, Ok)
    return result.value


@pytest.fixture(scope="session")
def mutant_tree(root: Path, tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Share one scratch checkout, restoring its target after every case."""
    copied = scratch(root, tmp_path_factory.mktemp("mutants") / "checkout")
    assert isinstance(copied, Ok)
    return copied.value


def _records() -> tuple[Mutant, ...]:
    """Collect one ordinary pytest case per real corpus record."""
    result = corpus(Path(__file__).resolve().parents[2])
    if isinstance(result, Err):
        raise pytest.UsageError(result.error.message)
    return result.value


@pytest.mark.parametrize("record", _records(), ids=lambda record: record.identifier)
def test_corpus(
    record: Mutant, mutant_tree: Path, request: pytest.FixtureRequest
) -> None:
    """Require every declared defect to die only for its recorded reason."""
    outcomes = exercise_observed(mutant_tree, record)
    request.node.stash[KILLER_EXECUTION] = KillerExecution(record, outcomes)
    result = killer_verdict(record, outcomes)
    detail = result.error.message if isinstance(result, Err) else str(result)
    assert result == Ok(None), detail


def test_wrong_reason_rejected(tmp_path: Path) -> None:
    """Reject an unrelated runtime error beside a specifically killed defect."""
    tree = _sample(tmp_path)
    assert exercise(tree, _parsed()) == Ok(None)
    result = exercise(tree, _parsed(replace="raise ValueError('unrelated failure')"))
    assert isinstance(result, Err), "wrong failure reason was accepted"
    assert result.error.stage == "mutant"


def test_survivor_rejected(tmp_path: Path) -> None:
    """A no-op patch survives and cannot count as a mutation kill."""
    tree = _sample(tmp_path)
    assert exercise(tree, _parsed()) == Ok(None)
    result = exercise(tree, _parsed(replace="return 2"))
    assert isinstance(result, Err), "survivor was accepted"
    assert result.error.stage == "mutant"


def test_exact_once_required() -> None:
    """Require precisely one search occurrence, including nonempty search."""
    assert patch(b"return 2", b"2", b"3") == Ok(b"return 3")
    for original, search in (
        (b"return 2", b"absent"),
        (b"2 + 2", b"2"),
        (b"return 2", b""),
    ):
        assert isinstance(patch(original, search, b"3"), Err), (
            "multiple or missing patch occurrence was accepted"
        )


def test_operator_set_closed() -> None:
    """Accept all defined operators and reject an unknown spelling."""
    for member in Operator:
        result = parse(_record(operator=member.value))
        assert isinstance(result, Ok)
        assert result.value.operator == member
    assert isinstance(parse(_record(operator="invented")), Err), (
        "unknown operator was accepted"
    )


def test_corpus_killer_rejected() -> None:
    """Reject recursion, live killers, escaping targets and malformed nodes."""
    assert isinstance(parse(_record()), Ok)
    assert isinstance(
        parse(_record(killers=["tests/unit/test_subject.py::test_subject[claude]"])), Ok
    )
    for killers in (
        [],
        ["tests/governance/test_mutants.py::test_corpus"],
        ["tests/governance/test_mutants.py::test_corpus[claude]"],
        ["tests/live/test_live.py::test_live"],
        ["tests/live/test_live.py::test_live[claude]"],
        ["tests/unit/test_subject.py::test_subject[]"],
        ["tests/unit/test_subject.py::test_subject[../../live]"],
        ["tests/unit/test_subject.py::test_subject[claude] --ignore=tests"],
        ["not-a-node"],
    ):
        assert isinstance(parse(_record(killers=killers)), Err)
    for target in ("../outside.py", "/outside.py"):
        assert isinstance(parse(_record(target=target)), Err)


def test_duplicate_killers_rejected() -> None:
    """A repeated killer cannot masquerade as two independent controls."""
    node = "tests/unit/test_subject.py::test_answer"
    assert isinstance(parse(_record(killers=[node])), Ok)
    assert isinstance(parse(_record(killers=[node, node])), Err), (
        "duplicate mutant killers were accepted"
    )


def test_parameter_killers_execute_current_cases(tmp_path: Path) -> None:
    """Require both selected native pytest cases to pass and then die by name."""
    tree = _sample(tmp_path)
    (tree / "tests/unit/test_subject.py").write_text(
        "import pytest\nfrom sample import answer\n"
        "@pytest.mark.parametrize('agent', ['claude', 'codex'])\n"
        "def test_answer(agent):\n"
        "    assert agent in {'claude', 'codex'}\n"
        "    assert answer() == 2, 'named answer defect'\n",
        encoding="utf-8",
    )
    record = _parsed(
        killers=[
            "tests/unit/test_subject.py::test_answer[claude]",
            "tests/unit/test_subject.py::test_answer[codex]",
        ]
    )
    assert exercise(tree, record) == Ok(None)
    missing = _parsed(killers=["tests/unit/test_subject.py::test_answer[missing]"])
    result = exercise(tree, missing)
    assert isinstance(result, Err)
    assert result.error.stage == "baseline"
    assert missing.identifier in result.error.message
    assert missing.killers[0] in result.error.message


def test_killer_results_preserve_independent_baselines(tmp_path: Path) -> None:
    """A failed baseline cannot hide a different killer or become a mutation kill."""
    tree = _sample(tmp_path)
    subject = tree / "tests/unit/test_subject.py"
    subject.write_text(
        "from sample import answer\n"
        "def test_broken():\n"
        "    assert False, 'independent baseline failure'\n"
        "def test_answer():\n"
        "    assert answer() == 2, 'named answer defect'\n",
        encoding="utf-8",
    )
    record = _parsed(
        killers=[
            "tests/unit/test_subject.py::test_broken",
            "tests/unit/test_subject.py::test_answer",
        ]
    )
    target = tree / "src/sample.py"
    original = target.read_bytes()
    observed = exercise_observed(tree, record, timeout=30)
    assert isinstance(observed, Ok), observed
    outcomes = observed.value
    assert len(outcomes) == len(record.killers)
    assert outcomes[0].node == record.killers[0]
    assert isinstance(outcomes[0].baseline, Err)
    assert outcomes[0].mutation is None, "failed baseline became a mutant kill"
    assert outcomes[1].node == record.killers[1]
    assert outcomes[1].baseline == Ok(None), "later baseline was not observed"
    assert outcomes[1].mutation == Ok(None), "independent mutant kill was hidden"
    assert target.read_bytes() == original
    combined = exercise(tree, record)
    assert isinstance(combined, Err), "failed baseline was accepted"
    assert combined.error.stage == "baseline"
    assert record.killers[0] in combined.error.message
    assert target.read_bytes() == original


def test_killer_restoration_failure_retains_primary(root: Path, tmp_path: Path) -> None:
    """A real restore veto retains the earlier baseline failure and scratch bytes."""
    tree = _sample(tmp_path)
    subject = tree / "tests/unit/test_subject.py"
    subject.write_text(
        "from sample import answer\n"
        "def test_broken():\n"
        "    assert False, 'independent baseline failure'\n"
        "def test_answer():\n"
        "    assert answer() == 2, 'named answer defect'\n",
        encoding="utf-8",
    )
    target = tree / "src/sample.py"
    original = target.read_bytes()
    program = """import sys
from pathlib import Path
from agentctl.check.mutants import Mutant, Operator, exercise
from agentctl.foundation import Err
tree = Path(sys.argv[1])
target = tree / 'src/sample.py'
original = target.read_bytes()
state = {'active': True, 'writes': 0}
def audit(event, arguments):
    if (state['active'] and event == 'open' and str(arguments[0]) == str(target)
            and arguments[1] == 'w'):
        state['writes'] += 1
        if state['writes'] == 2:
            raise PermissionError('owned restoration veto')
sys.addaudithook(audit)
record = Mutant('M-mutant-control', Operator.REPLACE_LITERAL, 'src/sample.py',
                'return 2', 'return 3',
                ('tests/unit/test_subject.py::test_broken',
                 'tests/unit/test_subject.py::test_answer'), 'named answer defect')
try:
    result = exercise(tree, record, timeout=30)
finally:
    state['active'] = False
    target.write_bytes(original)
assert isinstance(result, Err), 'restoration failure was accepted'
assert result.error.stage == 'baseline', 'primary failure stage was hidden'
assert 'test_broken' in result.error.message, 'primary failure was hidden'
assert 'owned restoration veto' in result.error.message, (
    'restoration failure was hidden')
"""
    observed = run(
        [sys.executable, "-c", program, str(tree)],
        cwd=root,
        env={
            **os.environ,
            "PYTHONPATH": os.pathsep.join((str(root / "src"), str(root))),
            "PYTHONDONTWRITEBYTECODE": "1",
        },
        timeout=60,
    )
    assert isinstance(observed, Ok), observed
    assert observed.value.code == 0, observed.value.stderr
    assert target.read_bytes() == original


def test_all_failed_baselines_remain_visible(tmp_path: Path) -> None:
    """Every failing baseline is reported and no defective source is needed."""
    tree = _sample(tmp_path)
    subject = tree / "tests/unit/test_subject.py"
    subject.write_text(
        "def test_first():\n    assert False, 'first baseline failure'\n"
        "def test_second():\n    assert False, 'second baseline failure'\n",
        encoding="utf-8",
    )
    record = _parsed(
        killers=[
            "tests/unit/test_subject.py::test_first",
            "tests/unit/test_subject.py::test_second",
        ]
    )
    target = tree / "src/sample.py"
    original = target.read_bytes()
    result = exercise(tree, record)
    assert isinstance(result, Err)
    assert result.error.stage == "baseline"
    assert record.killers[0] in result.error.message, "first baseline was hidden"
    assert record.killers[1] in result.error.message, "second baseline was hidden"
    assert target.read_bytes() == original


def test_killer_verdict_requires_complete_matching_results() -> None:
    """Missing, replayed and baseline-inconsistent outcomes cannot pass."""
    record = _parsed()
    good = KillerOutcome(record.killers[0], Ok(None), Ok(None))
    assert killer_verdict(record, Ok((good,))) == Ok(None)
    failed = Err(MutationError("baseline", "baseline failed"))
    for outcomes in (
        (),
        (good, good),
        (replace(good, node="tests/unit/test_other.py::test_other"),),
        (replace(good, mutation=None),),
        (KillerOutcome(good.node, failed, Ok(None)),),
    ):
        assert isinstance(killer_verdict(record, Ok(outcomes)), Err), (
            "incomplete killer outcomes accepted"
        )


def test_baseline_must_pass() -> None:
    """Reject failing baselines and reason strings already present before mutation."""
    assert baseline(Output(0, "clean", ""), "named defect") == Ok(None)
    for output in (Output(1, "", ""), Output(0, "named defect", "")):
        assert isinstance(baseline(output, "named defect"), Err), (
            "failing baseline was accepted"
        )


def test_runner_restores_scratch_tree(tmp_path: Path) -> None:
    """Restore after kills, survivors, unrelated failures and child timeouts."""
    tree = _sample(tmp_path)
    target = tree / "src/sample.py"
    original = target.read_bytes()
    for replacement, expected in (
        ("return 3", Ok(None)),
        ("return 2", "mutant"),
        ("raise ValueError('unrelated')", "mutant"),
    ):
        result = exercise(tree, _parsed(replace=replacement))
        if isinstance(expected, str):
            assert isinstance(result, Err)
            assert result.error.stage == expected
        else:
            assert result == expected
        assert target.read_bytes() == original
    timed = exercise(
        tree,
        _parsed(
            replace=(
                'from pathlib import Path; Path(__file__).with_suffix(".entered")'
                '.write_text("entered", encoding="utf-8"); '
                "import time; time.sleep(60); return 3"
            )
        ),
        timeout=10,
    )
    assert target.with_suffix(".entered").read_text(encoding="utf-8") == "entered"
    assert isinstance(timed, Err)
    assert timed.error.stage == "spawn"
    assert target.read_bytes() == original
    assert isinstance(scratch(tree, tree / "recursive"), Err)
    assert isinstance(exercise(tree, replace(_parsed(), target="../outside")), Err)
    assert parse({}) == Err(
        MutationError("schema", "closed mutant record fields required")
    )


def test_mutant_input_boundaries(tmp_path: Path) -> None:
    """Malformed disk corpora and invalid identities fail before any killer runs."""
    for changes in (
        {"id": 1},
        {"id": "invalid"},
        {"search": ""},
        {"reason": ""},
        {"killers": [1]},
        {"killers": "node"},
        {"target": ""},
        {"target": "src\\subject.py"},
    ):
        assert isinstance(parse(_record(**changes)), Err)
    assert isinstance(corpus(tmp_path), Err)
    directory = tmp_path / "tests/mutants"
    directory.mkdir(parents=True)
    path = directory / "cases.toml"
    for text in ("bad = [", "mutant = []", "wrong = []", "mutant = [1]"):
        path.write_text(text, encoding="utf-8")
        assert isinstance(corpus(tmp_path), Err)
    row = (
        "[[mutant]]\n"
        + "\n".join(key + " = " + json.dumps(value) for key, value in _record().items())
        + "\n"
    )
    path.write_text(row, encoding="utf-8")
    assert isinstance(corpus(tmp_path), Ok)
    path.write_text(row + row, encoding="utf-8")
    assert isinstance(corpus(tmp_path), Err)
    path.write_bytes(b"\xff")
    assert isinstance(corpus(tmp_path), Err)
    assert isinstance(
        killed(Output(1, "E ImportError: named reason", ""), "named reason"), Err
    )


def test_mutant_filesystem_and_baseline_failures(tmp_path: Path) -> None:
    """A real missing target, failing baseline or failed copy never counts as a kill."""
    subject = _sample(tmp_path / "subject")
    assert isinstance(
        exercise(subject, replace(_parsed(), target="src/missing.py")), Err
    )
    assert isinstance(exercise(subject, replace(_parsed(), search="absent")), Err)
    copied = tmp_path / "copied"
    (subject / ".git").mkdir()
    (subject / ".git/private").write_text(
        "excluded repository metadata", encoding="utf-8"
    )
    assert scratch(subject, copied) == Ok(copied)
    assert not (copied / ".git").exists()
    assert isinstance(scratch(subject, copied), Err)
    killer = subject / "tests/unit/test_subject.py"
    killer.write_text("def test_answer():\n    assert False\n", encoding="utf-8")
    result = exercise(subject, _parsed())
    assert isinstance(result, Err)
    assert result.error.stage == "baseline"
    result = exercise(subject, _parsed(), timeout=0.001)
    assert isinstance(result, Err)
    assert result.error.stage == "spawn"
