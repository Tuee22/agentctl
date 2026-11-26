# Copyright (c) 2026 agentctl contributors.
"""Sealed handoff verifiers refuse unreadable or inconsistent retained records."""

import json
from collections.abc import Callable
from pathlib import Path

import pytest

from agentctl.check import evidence, steps
from agentctl.check.evidence import Entry, LegEvidence, RunEvidence
from agentctl.check.steps import CheckRun, NativeSnapshot
from agentctl.result import Err, Ok, Result

pytestmark = pytest.mark.evidence("value")

NONCE = "b" * 32
DIGEST = "0" * 64
MAX_OFFSET = 20
SHA_LENGTH = 64
ABSENT = "missing or ambiguous"
Verifier = Callable[[str], Result[None, str]]


def _clean_finalizers(
    monkeypatch: pytest.MonkeyPatch, *, failing: tuple[str, ...] = ()
) -> None:
    """Observe a finalizer record in which only the named finalizers failed."""
    observed = LegEvidence(
        NONCE,
        tuple((name, int(name in failing)) for name in steps.FINALIZER_NAMES[:-1]),
    )
    monkeypatch.setattr(
        steps, "sealed_finalizer_observation", lambda *_args: Ok(observed)
    )


def _beyond_marker(seal: str, verify: Verifier) -> Result[None, str]:
    """Place one marker where the verifier expects it and return its verdict."""
    marker = f"{seal} {NONCE} {DIGEST}"
    for offset in range(1, MAX_OFFSET + 1):
        output = "\n".join((marker, *("filler",) * (offset - 1)))
        verdict = verify(output)
        if not (isinstance(verdict, Err) and verdict.error.startswith(ABSENT)):
            return verdict
    pytest.fail("no output layout reached the record reader")


def test_handoff_verifiers_pass_unreadable_records_through(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A correctly placed marker with an absent record is reported, not trusted."""
    _clean_finalizers(monkeypatch)
    cases: tuple[tuple[str, Verifier, str], ...] = (
        (
            steps.RUFF_SEAL,
            lambda output: steps.verify_ruff_handoff(tmp_path, NONCE, output, tmp_path),
            "cannot read Ruff handoff",
        ),
        (
            steps.RUFF_FORMAT_SEAL,
            lambda output: steps.verify_ruff_format_handoff(
                tmp_path, NONCE, output, tmp_path
            ),
            "cannot read Ruff handoff",
        ),
        (
            steps.HOST_OBSERVATION_SEAL,
            lambda output: steps.verify_host_handoff(tmp_path, NONCE, output),
            "cannot read host handoff",
        ),
        (
            steps.ORACLE_RESULTS_SEAL,
            lambda output: steps.verify_oracle_handoff(tmp_path, NONCE, output),
            "cannot read oracle handoff",
        ),
        (
            steps.PYTEST_OBSERVATION_SEAL,
            lambda output: steps.verify_pytest_handoff(tmp_path, NONCE, output),
            "cannot read pytest handoff",
        ),
        (
            steps.TOOL_RESULTS_SEAL,
            lambda output: steps.verify_tool_results_handoff(tmp_path, NONCE, output),
            "tool results handoff records unavailable",
        ),
        (
            steps.PYTHON_COMMANDS_SEAL,
            lambda output: steps.verify_python_commands_handoff(
                tmp_path, NONCE, output, tmp_path
            ),
            "cannot read Python command handoff",
        ),
    )
    for seal, verify, prefix in cases:
        verdict = _beyond_marker(seal, verify)
        assert isinstance(verdict, Err), seal
        assert verdict.error.startswith(prefix), (seal, verdict)


def test_coverage_text_marker_must_match_the_retained_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The transcript handoff needs one placed marker and a matching digest."""
    _clean_finalizers(monkeypatch)
    context = CheckRun(tmp_path, tmp_path, NONCE, "Linux")
    assert steps.verify_coverage_text_handoff(context, tmp_path, "") == Err(
        "missing or ambiguous coverage text handoff"
    )
    record = b'{"nonce": "x"}'
    monkeypatch.setattr(
        steps, "_coverage_text_handoff", lambda *_args: Ok(record), raising=True
    )
    mismatch = _beyond_marker(
        steps.COVERAGE_TEXT_SEAL,
        lambda output: steps.verify_coverage_text_handoff(context, tmp_path, output),
    )
    assert mismatch == Err("coverage text handoff digest mismatch")


def test_coverage_text_agreement_requires_every_supporting_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The retained agreement reports each unavailable supporting observation."""
    context = CheckRun(tmp_path / "absent", tmp_path, NONCE, "Linux")
    agreement = steps.coverage_text_retained_agreement
    _clean_finalizers(monkeypatch, failing=("tool-outcomes",))
    assert agreement(context, tmp_path, "", b"{}") == Err(
        "coverage text supporting handoff failed"
    )
    _clean_finalizers(monkeypatch)
    assert agreement(context, tmp_path, "", b"{}") == Err(
        "coverage text supporting handoff is invalid"
    )
    monkeypatch.setattr(steps, "verify_coverage_handoff", lambda *_args: Ok(None))
    monkeypatch.setattr(steps, "verify_tool_results_handoff", lambda *_args: Ok(None))
    assert agreement(context, tmp_path, "", b"{}") == Err(
        "coverage text supporting evidence unavailable"
    )
    pair = Ok((b"{}", b"{}"))
    tools = Ok((LegEvidence(NONCE, ()), evidence.ToolSubsteps(NONCE, ())))
    monkeypatch.setattr(steps, "_coverage_handoff_files", lambda *_args: pair)
    monkeypatch.setattr(steps, "_read_sealed_tool_results", lambda *_args: tools)
    monkeypatch.setattr(
        steps, "_coverage_declarations", lambda *_args: Ok(("7.0.0", ()))
    )
    absent_census = steps.ownership.guarded_census(tmp_path / "absent")
    assert isinstance(absent_census, Err)
    empty = tmp_path / "empty"
    empty.mkdir()
    context = CheckRun(empty, tmp_path, NONCE, "Linux")
    assert agreement(context, tmp_path, "", b"{") == Err(
        "coverage text supporting evidence is malformed"
    )


def test_retained_transcripts_are_decoded_structurally() -> None:
    """The retained transcript and its report bytes must both decode."""
    values = steps.__dict__["_coverage_text_retained_values"]
    assert values(b"{", b"{}", "1") == Err(
        "coverage text supporting evidence is malformed"
    )
    assert values(b"{}", b"\xff", "1") == Err(
        "coverage text supporting evidence is malformed"
    )
    assert values(b"{}", b"{}", "1") == Err("coverage text transcript is malformed")


def test_native_source_digest_requires_consistent_native_sources() -> None:
    """The native digest needs sources, unique paths and an encodable name."""
    manifest = RunEvidence(NONCE, frozenset(), frozenset(), frozenset(), (), ())
    unavailable = Err("native source census unavailable or inconsistent")
    empty = NativeSnapshot(manifest, (), ())
    assert steps.native_source_digest(empty) == unavailable
    assert steps.native_observation_seal(NONCE, empty) == unavailable
    path = "src/agentctl/haskell/Main.hs"
    entry = Entry(path, "file", (b"x",))
    uncovered = NativeSnapshot(
        manifest, (("case", "src/agentctl/haskell/Other.hs"),), (entry,)
    )
    assert steps.native_source_digest(uncovered) == unavailable
    surrogate = Entry("src/agentctl/haskell/\ud800.hs", "file", (b"x",))
    unencodable = NativeSnapshot(manifest, (), (surrogate,))
    assert steps.native_source_digest(unencodable) == Err(
        "native source path is not encodable"
    )


def test_native_artifact_selection_requires_the_same_host_family(
    tmp_path: Path,
) -> None:
    """A run recorded for another host family cannot select native artifacts."""
    other = (
        "Windows" if steps.hostfacts.current(tmp_path).family == "Linux" else "Linux"
    )
    context = CheckRun(tmp_path, tmp_path, NONCE, other)
    assert steps.__dict__["_selected_native_artifacts"](context) == Err(
        "native artifact host family differs"
    )


def test_oracle_records_must_decode(tmp_path: Path) -> None:
    """Present but undecodable oracle records are unavailable or invalid."""
    for name in ("oracle-outcomes.json", "oracle-details.json"):
        (tmp_path / name).write_text("{}", encoding="utf-8")
    assert steps.__dict__["_oracle_handoff_observations"](tmp_path, NONCE) == Err(
        "oracle handoff records unavailable or invalid"
    )


def test_coverage_pair_reports_missing_files(tmp_path: Path) -> None:
    """An absent coverage pair is an unreadable handoff."""
    observed = steps.__dict__["_coverage_handoff_files"](tmp_path / "absent", NONCE)
    assert isinstance(observed, Err)
    assert observed.error.startswith("cannot read")


def test_coverage_wrapper_refuses_unencodable_reports() -> None:
    """A report string that cannot be encoded is not a canonical wrapper."""
    wrapper = b'{"nonce":"%s","report":"\\ud800","version":"1"}' % NONCE.encode()
    assert steps.__dict__["_parse_coverage_handoff"](NONCE, wrapper, b"") == Err(
        "invalid coverage handoff encoding"
    )


def test_ruff_record_must_be_json() -> None:
    """A retained Ruff record that is not JSON is refused."""
    assert steps.__dict__["_parse_ruff_record"](NONCE, Path(), b"{") == Err(
        "invalid Ruff handoff JSON"
    )


def _commands_record(nonce: str, root: Path, rows: object) -> bytes:
    return json.dumps(
        {
            "nonce": nonce,
            "root": str(root),
            "commands": rows,
            "source_digest": DIGEST,
        },
        sort_keys=True,
    ).encode("utf-8")


def test_python_command_records_are_validated_row_by_row(tmp_path: Path) -> None:
    """Each command row needs a name, attempts and non-empty string arguments."""
    parse = steps.__dict__["_parse_python_commands_record"]
    assert parse(NONCE, tmp_path, b"{") == Err("invalid Python command handoff JSON")
    bad_row = _commands_record(NONCE, tmp_path, [1])
    assert parse(NONCE, tmp_path, bad_row) == Err("invalid Python command handoff rows")
    bad_argument = _commands_record(NONCE, tmp_path, [["ty", [[""]]]])
    assert parse(NONCE, tmp_path, bad_argument) == Err(
        "invalid Python command handoff arguments"
    )
    wrong_names = _commands_record(NONCE, tmp_path, [["ty", [["a"]]]])
    assert parse(NONCE, tmp_path, wrong_names) == Err(
        "invalid Python command handoff names"
    )


def test_python_command_rows_are_decoded_defensively() -> None:
    """The parent decoder refuses malformed, empty and non-string attempts."""
    decode = steps.__dict__["_decoded_python_command_rows"]
    assert decode(b"{") == Err("invalid Python command rows")
    assert decode(b"[]") == Err("invalid Python command rows")
    assert decode(b'{"commands": [1]}') == Err("invalid Python command rows")
    assert decode(b'{"commands": [["ty", []]]}') == Err("invalid Python command rows")
    assert decode(b'{"commands": [["ty", [[1]]]]}') == Err(
        "invalid Python command arguments"
    )
    assert decode(b'{"commands": [["ty", [["a", "b"]]]]}') == Ok(
        (("ty", (("a", "b"),)),)
    )


def _synthetic_checkout(root: Path) -> None:
    """Create the smallest checkout whose coverage declarations are readable."""
    (root / "src" / "agentctl" / "check").mkdir(parents=True)
    (root / "tests").mkdir()
    (root / "pyproject.toml").write_text(
        '[project.optional-dependencies]\ndev = ["coverage==7.0.0"]\n',
        encoding="utf-8",
    )
    (root / "src" / "agentctl" / "x.py").write_text("", encoding="utf-8")
    (root / steps.COVERAGE_HOSTS).write_text(
        'version = 1\n[[source]]\npath = "src/agentctl/x.py"\nhosts = ["Windows"]\n',
        encoding="utf-8",
    )


def test_python_plan_refuses_unavailable_or_changed_inputs(tmp_path: Path) -> None:
    """The parent plan join needs a census, current digest and valid declarations."""
    plan = steps.__dict__["_python_plan_from_record"]
    absent = CheckRun(tmp_path / "absent", tmp_path, NONCE, "Linux")
    assert plan(absent, b"{}") == Err("Python command plan census unavailable")
    declared = tmp_path / "declared"
    declared.mkdir()
    _synthetic_checkout(declared)
    context = CheckRun(declared, tmp_path, NONCE, "Linux")
    assert plan(context, b"{}") == Err("Python command source census changed")
    census = steps.ownership.guarded_census(declared)
    assert isinstance(census, Ok)
    digest = evidence.digest_census(census.value)
    assert isinstance(digest, Ok)
    malformed = json.dumps(
        {"source_digest": digest.value, "commands": 1}, sort_keys=True
    ).encode()
    assert plan(context, malformed) == Err("Python command plan inputs invalid")
    renamed = json.dumps(
        {"source_digest": digest.value, "commands": []}, sort_keys=True
    ).encode()
    assert plan(context, renamed) == Err("Python command plan names differ")


def _write_tool_records(directory: Path, outcomes: object, substeps: object) -> None:
    for name, rows in (("tool-outcomes", outcomes), ("tool-substeps", substeps)):
        record = {"nonce": NONCE, "outcomes": rows}
        (directory / (name + ".json")).write_text(json.dumps(record), encoding="utf-8")


def test_tool_records_are_cross_checked(tmp_path: Path) -> None:
    """Tool outcomes and substeps must be present, well formed and aligned."""
    read = steps.__dict__["_read_sealed_tool_results"]
    assert read(tmp_path, NONCE) == Err("tool results handoff records unavailable")
    (tmp_path / "tool-outcomes.json").write_text("{}", encoding="utf-8")
    assert steps.__dict__["_tool_record_rows"](
        tmp_path / "tool-outcomes.json", NONCE
    ) == Err("invalid tool results handoff identity")
    cases = (
        ([1], [], "invalid tool results handoff outcomes"),
        ([["a", 0]], [1], "invalid tool results handoff substeps"),
        ([["a", 0]], [["b", [0]]], "tool results handoff schedules differ"),
        ([["a", 0]], [["a", [0]]], None),
        ([["a", 9.5]], [], "invalid tool results handoff outcomes"),
    )
    for outcomes, substeps, message in cases:
        _write_tool_records(tmp_path, outcomes, substeps)
        verdict = read(tmp_path, NONCE)
        if message is None:
            assert isinstance(verdict, Ok)
        else:
            assert verdict == Err(message)
    _write_tool_records(tmp_path, [["a", 0]], [["a", [0, True]]])
    assert read(tmp_path, NONCE) == Err("invalid tool results handoff records")


def test_finalizer_record_validation(tmp_path: Path) -> None:
    """Finalizer statuses are only zero or one, and files must stay private."""
    names = steps.FINALIZER_NAMES[:-1]
    rows = [[name, 2 if index == 0 else 0] for index, name in enumerate(names)]
    contents = json.dumps({"nonce": NONCE, "outcomes": rows}).encode()
    parse = steps.__dict__["_parse_finalizer_observation"]
    assert parse(contents, NONCE) == Err("invalid finalizer status")
    read = steps.__dict__["_read_finalizer_handoff"]
    target = tmp_path / "target"
    target.write_bytes(b"{}")
    link = tmp_path / "link"
    link.symlink_to(target)
    assert read(link) == Err("finalizer handoff record is a symlink")
    absent = read(tmp_path / "absent")
    assert isinstance(absent, Err)
    assert absent.error.startswith("cannot read finalizer handoff")


def test_finalizer_file_must_match_the_observation(tmp_path: Path) -> None:
    """A finalizer record rewritten after observation is refused."""
    verify = steps.__dict__["_verify_finalizer_file"]
    observed = LegEvidence(
        NONCE, tuple((name, 0) for name in steps.FINALIZER_NAMES[:-1])
    )
    marker = steps.finalizer_seal(observed)
    absent = verify(tmp_path, NONCE, marker, observed)
    assert isinstance(absent, Err)
    assert absent.error.startswith("cannot read finalizer handoff")
    changed = LegEvidence(
        NONCE, tuple((name, 1) for name in steps.FINALIZER_NAMES[:-1])
    )
    record = {"nonce": NONCE, "outcomes": changed.outcomes}
    (tmp_path / "finalizer-outcomes.json").write_text(
        json.dumps(record), encoding="utf-8"
    )
    assert verify(tmp_path, NONCE, marker, observed) == Err(
        "finalizer handoff record changed during inspection"
    )
