# Copyright (c) 2026 agentctl contributors.
"""Real scratch mutation controls and every executable corpus record."""

import json
from dataclasses import replace
from pathlib import Path

import pytest

from agentctl.check.mutants import (
    Mutant,
    MutationError,
    Operator,
    baseline,
    corpus,
    exercise,
    killed,
    parse,
    patch,
    scratch,
)
from agentctl.process import Output
from agentctl.result import Err, Ok

pytestmark = pytest.mark.evidence("real")


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
def test_corpus(record: Mutant, mutant_tree: Path) -> None:
    """Require every declared defect to die only for its recorded reason."""
    result = exercise(mutant_tree, record)
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
