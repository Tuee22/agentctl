# Copyright (c) 2026 agentctl contributors.
"""Private handoff readers refuse substituted, linked and changing records."""

import json
import os
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

from agentctl.check import steps
from agentctl.check.steps import CheckRun
from agentctl.result import Err, Ok, Result

pytestmark = pytest.mark.evidence("value")

NONCE = "a" * 32
Reader = Callable[[Path], object]


def _checked(value: Result[object, str]) -> Result[object, str]:
    return value


def _plain(directory: Path, name: str) -> Path:
    path = directory / name
    path.write_bytes(b"{}")
    return path


def _hardlinked(directory: Path, name: str) -> Path:
    path = _plain(directory, name)
    os.link(path, directory / (name + ".alias"))
    return path


def _readers(root: Path, nonce: str) -> tuple[tuple[str, Reader, str, str], ...]:
    """Each reader with its record name and the private-file refusal it raises."""
    context = CheckRun(root, root, nonce, "Linux")
    return (
        (
            "tool-outcomes.json",
            lambda directory: steps.__dict__["_tool_record_rows"](
                directory / "tool-outcomes.json", nonce
            ),
            "tool results handoff is not a private regular file",
            "tool results handoff changed during inspection",
        ),
        (
            "python-commands.json",
            lambda directory: steps.__dict__["_python_commands_handoff_record"](
                directory, nonce, root
            ),
            "Python command handoff is not a private regular file",
            "Python command handoff changed during inspection",
        ),
        (
            "ruff-observation.json",
            lambda directory: steps.__dict__["_ruff_handoff_record"](
                directory, nonce, root
            ),
            "Ruff handoff is not a private regular file",
            "Ruff handoff changed during inspection",
        ),
        (
            "ty-observation.json",
            lambda directory: steps.__dict__["_ty_handoff_record"](
                directory, nonce, root
            ),
            "ty handoff is not a private regular file",
            "ty handoff changed during inspection",
        ),
        (
            "coverage-text.json",
            lambda directory: steps.__dict__["_coverage_text_handoff"](
                replace_directory(context, directory), directory
            ),
            "coverage text handoff is not a private regular file",
            "coverage text handoff changed during inspection",
        ),
    )


def replace_directory(context: CheckRun, directory: Path) -> CheckRun:
    """Rebind the run context to the directory under inspection."""
    return CheckRun(context.root, directory, context.nonce, context.family)


def test_double_read_handoffs_refuse_non_private_files(tmp_path: Path) -> None:
    """Directories, symlinks and hard-linked records are not private regular files."""
    for index, (name, read, refusal, _changed) in enumerate(_readers(tmp_path, NONCE)):
        folder = tmp_path / f"case{index}"
        folder.mkdir()
        (folder / name).mkdir()
        assert read(folder) == Err(refusal), name
        linked = tmp_path / f"link{index}"
        linked.mkdir()
        _hardlinked(linked, name)
        assert read(linked) == Err(refusal), name
        symbolic = tmp_path / f"sym{index}"
        symbolic.mkdir()
        target = _plain(symbolic, "target")
        (symbolic / name).symlink_to(target)
        assert read(symbolic) == Err(refusal), name


def test_double_read_handoffs_refuse_a_record_that_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A record whose second read differs from its first is refused."""
    original = Path.read_bytes

    def rewriting(self: Path) -> bytes:
        data = original(self)
        if data == b"{}":
            self.write_bytes(b"[]")
        return data

    monkeypatch.setattr(Path, "read_bytes", rewriting)
    for index, (name, read, _refusal, changed) in enumerate(_readers(tmp_path, NONCE)):
        folder = tmp_path / f"case{index}"
        folder.mkdir()
        _plain(folder, name)
        assert read(folder) == Err(changed), name


def test_ruff_record_names_are_a_closed_set(tmp_path: Path) -> None:
    """Only the two private Ruff record names are readable."""
    assert steps.__dict__["_ruff_handoff_record"](
        tmp_path, NONCE, tmp_path, filename="other.json"
    ) == Err("invalid Ruff handoff name")


def test_missing_records_are_unreadable_not_crashes(tmp_path: Path) -> None:
    """Each reader reports a missing file as an unreadable handoff."""
    for _name, read, _refusal, _changed in _readers(tmp_path, NONCE):
        result = read(tmp_path)
        assert isinstance(result, Err)
        assert "cannot read" in result.error


def test_coverage_text_requires_a_census_and_known_fields(tmp_path: Path) -> None:
    """The report transcript needs a source census, then an exact field set."""
    directory = tmp_path / "run"
    directory.mkdir()
    (directory / "coverage-text.json").write_bytes(b"{}")
    empty = CheckRun(tmp_path, directory, NONCE, "Linux")
    assert steps.__dict__["_coverage_text_handoff"](empty, directory) == Err(
        "coverage capture declarations unavailable"
    )
    absent = CheckRun(tmp_path / "absent", directory, NONCE, "Linux")
    assert steps.__dict__["_coverage_text_handoff"](absent, directory) == Err(
        "source census unavailable"
    )
    checkout = tmp_path / "checkout"
    (checkout / "src" / "agentctl" / "check").mkdir(parents=True)
    (checkout / "pyproject.toml").write_text(
        '[project.optional-dependencies]\ndev = ["coverage==7.0.0"]\n',
        encoding="utf-8",
    )
    (checkout / "src" / "agentctl" / "x.py").write_text("", encoding="utf-8")
    (checkout / steps.COVERAGE_HOSTS).write_text(
        'version = 1\n[[source]]\npath = "src/agentctl/x.py"\nhosts = ["Windows"]\n',
        encoding="utf-8",
    )
    live = CheckRun(checkout, directory, NONCE, "Linux")
    assert steps.__dict__["_coverage_text_handoff"](live, directory) == Err(
        "invalid coverage text identity or fields"
    )
    (directory / "coverage-text.json").write_bytes(b"{")
    broken = steps.__dict__["_coverage_text_handoff"](live, directory)
    assert isinstance(broken, Err)
    assert broken.error.startswith("cannot read coverage text handoff")
    expected = steps.coverage_commands(
        sys.executable, checkout, directory, ("src/agentctl/x.py",)
    )[-1]
    transcript = {
        "nonce": NONCE,
        "root": str(checkout),
        "command": list(expected),
        "code": 0,
        "stdout": "TOTAL 1 0 0 0 100%\n",
        "stderr": "",
    }
    record = json.dumps(transcript, sort_keys=True).encode("utf-8")
    (directory / "coverage-text.json").write_bytes(record)
    assert steps.__dict__["_coverage_text_handoff"](live, directory) == Ok(record)
    forged = json.dumps({**transcript, "code": 1}, sort_keys=True).encode("utf-8")
    (directory / "coverage-text.json").write_bytes(forged)
    assert steps.__dict__["_coverage_text_handoff"](live, directory) == Err(
        "invalid coverage text command or record"
    )


def test_provisional_reader_detects_replacement_while_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A record replaced before or after it is opened is refused."""
    original = steps.__dict__["_open_private_handoff"]
    record = _plain(tmp_path, "provisional-phases.json")
    swapped = "provisional handoff record changed during inspection"

    def replace(path: str) -> None:
        target = Path(path)
        target.rename(target.with_name("retired"))
        target.write_bytes(b"{}")

    def before_open(path: str, flags: int) -> int:
        replace(path)
        return int(original(path, flags))

    def after_open(path: str, flags: int) -> int:
        descriptor = original(path, flags)
        replace(path)
        return int(descriptor)

    monkeypatch.setattr(steps, "_open_private_handoff", before_open)
    assert steps.__dict__["_read_provisional_handoff"](record) == Err(swapped)
    (tmp_path / "retired").unlink()
    monkeypatch.setattr(steps, "_open_private_handoff", after_open)
    assert steps.__dict__["_read_provisional_handoff"](record) == Err(swapped)


def test_finalizer_reader_detects_replacement_while_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The finalizer record is refused when swapped around its checked open."""
    original = steps.__dict__["_open_private_handoff"]
    record = _plain(tmp_path, "finalizer-outcomes.json")
    swapped = "finalizer handoff record changed during inspection"

    def replace(path: str) -> None:
        target = Path(path)
        target.rename(target.with_name("retired"))
        target.write_bytes(b"{}")

    def before_open(path: str, flags: int) -> int:
        replace(path)
        return int(original(path, flags))

    def after_open(path: str, flags: int) -> int:
        descriptor = original(path, flags)
        replace(path)
        return int(descriptor)

    monkeypatch.setattr(steps, "_open_private_handoff", before_open)
    assert steps.__dict__["_read_finalizer_handoff"](record) == Err(swapped)
    (tmp_path / "retired").unlink()
    monkeypatch.setattr(steps, "_open_private_handoff", after_open)
    assert steps.__dict__["_read_finalizer_handoff"](record) == Err(swapped)


def test_observation_readers_refuse_non_private_files(tmp_path: Path) -> None:
    """Host, pytest and oracle records must be private regular files."""
    cases = (
        ("host.json", "_host_handoff_observation", "host handoff"),
        ("pytest-manifest.json", "_pytest_handoff_observation", "pytest handoff"),
    )
    for name, function, label in cases:
        folder = tmp_path / name
        folder.mkdir()
        (folder / name).mkdir()
        assert steps.__dict__[function](folder, NONCE) == Err(
            label + " is not a private regular file"
        )
    oracle = tmp_path / "oracle"
    oracle.mkdir()
    (oracle / "oracle-outcomes.json").mkdir()
    (oracle / "oracle-details.json").write_bytes(b"{}")
    assert steps.__dict__["_oracle_handoff_observations"](oracle, NONCE) == Err(
        "oracle handoff is not a private regular file"
    )


def test_observation_readers_refuse_records_swapped_during_observation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A hard link added while a record is decoded invalidates the observation."""

    def link_beside(path: Path) -> None:
        os.link(path, path.with_name(path.name + ".alias"))

    for name, function, observer, label in (
        ("host.json", "_host_handoff_observation", "host_observation", "host"),
        (
            "pytest-manifest.json",
            "_pytest_handoff_observation",
            "pytest_observation",
            "pytest",
        ),
    ):
        folder = tmp_path / label
        folder.mkdir()
        path = _plain(folder, name)
        original = steps.__dict__[observer]

        def observing(
            run_dir: Path,
            nonce: str,
            target: Path = path,
            inner: Callable[[Path, str], Result[object, str]] = original,
        ) -> Result[object, str]:
            link_beside(target)
            return inner(run_dir, nonce)

        monkeypatch.setattr(steps, observer, observing)
        assert steps.__dict__[function](folder, NONCE) == Err(
            label + " handoff changed during inspection"
        )
    oracle = tmp_path / "oracle"
    oracle.mkdir()
    first = _plain(oracle, "oracle-outcomes.json")
    _plain(oracle, "oracle-details.json")
    inner_oracle = steps.__dict__["oracle_observation"]

    def oracle_observing(run_dir: Path, nonce: str) -> Result[object, str]:
        link_beside(first)
        return _checked(inner_oracle(run_dir, nonce))

    monkeypatch.setattr(steps, "oracle_observation", oracle_observing)
    assert steps.__dict__["_oracle_handoff_observations"](oracle, NONCE) == Err(
        "oracle handoff changed during inspection"
    )


def test_native_handoff_needs_census_and_private_reports(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Native reports are joined only to a census and private regular files."""
    directory = tmp_path / "run"
    directory.mkdir()
    empty = CheckRun(tmp_path / "absent", directory, NONCE, "Linux")
    assert steps.__dict__["_native_handoff_observation"](empty, directory) == Err(
        "native handoff source census unavailable"
    )
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    live = CheckRun(checkout, directory, NONCE, "Linux")
    missing = steps.__dict__["_native_handoff_observation"](live, directory)
    assert isinstance(missing, Err)
    assert missing.error.startswith("cannot read native handoff")
    for name in ("haskell-manifest.json", "haskell-sources.json", "tasty.xml"):
        _plain(directory, name)
    (directory / "native-artifacts.json").mkdir()
    assert steps.__dict__["_native_handoff_observation"](live, directory) == Err(
        "native handoff is not a private regular file"
    )
    (directory / "native-artifacts.json").rmdir()
    target = _plain(directory, "native-artifacts.json")

    def linking(_run: Path, _nonce: str, _entries: object) -> Result[object, str]:
        os.link(target, directory / "alias")
        return Err("unused")

    monkeypatch.setattr(steps, "native_snapshot", linking)
    assert steps.__dict__["_native_handoff_observation"](live, directory) == Err(
        "native handoff changed during inspection"
    )
