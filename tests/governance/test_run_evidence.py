# Copyright (c) 2026 agentctl contributors.
"""Independent manifest records and explicit canonical digest byte vectors."""

import hashlib
import json
import os
import platform
import re
from dataclasses import asdict
from pathlib import Path
from typing import Protocol, runtime_checkable

import pytest

from agentctl.check.evidence import digest, parse_manifest, read_manifest, verify
from agentctl.check.lanes import HostFacts
from agentctl.check.mutants import Mutant, Operator
from agentctl.check.steps import CheckRun, post_run, summarize
from agentctl.result import Err, Ok
from tests.harness.git import repository

pytestmark = pytest.mark.evidence("value")
NODE = "tests/unit/test_example.py::test_one"


@runtime_checkable
class FifoOperations(Protocol):
    """The native POSIX FIFO constructor, absent from Windows' os module."""

    def mkfifo(self, path: Path) -> None:
        """Create a filesystem special entry for the digest rejection control."""
        ...


def _record(**changes: object) -> dict[str, object]:
    """Supply an independently authored complete one-case manifest."""
    return {
        "nonce": "current",
        "collected": [NODE],
        "executed": [NODE],
        "passed": [NODE],
        "forbidden": [],
        "classes": {NODE: "value"},
        **changes,
    }


def test_manifest_nonce_required() -> None:
    """An otherwise valid old run cannot qualify as the current execution."""
    manifest = parse_manifest(_record())
    assert isinstance(manifest, Ok)
    assert verify(manifest.value, "current", ()) == Ok(None)
    assert isinstance(verify(manifest.value, "different", ()), Err), (
        "stale manifest nonce was accepted"
    )


def test_collected_executed_passed_equal() -> None:
    """Each independent observation is required; forbidden outcomes never qualify."""
    for changes in (
        {"executed": []},
        {"passed": []},
        {"forbidden": ["skip"]},
        {"collected": [], "executed": [], "passed": [], "classes": {}},
    ):
        manifest = parse_manifest(_record(**changes))
        assert isinstance(manifest, Ok)
        assert isinstance(verify(manifest.value, "current", ()), Err)


def test_every_mutant_has_current_case() -> None:
    """A complete ordinary run still fails when a corpus case is missing."""
    case = "tests/governance/test_mutants.py::test_corpus[M-evidence-control]"
    manifest = parse_manifest(
        _record(
            collected=[NODE, case],
            executed=[NODE, case],
            passed=[NODE, case],
            classes={NODE: "value", case: "real"},
        )
    )
    assert isinstance(manifest, Ok)
    assert verify(manifest.value, "current", ("M-evidence-control",)) == Ok(None)
    missing = parse_manifest(_record())
    assert isinstance(missing, Ok)
    assert isinstance(verify(missing.value, "current", ("M-evidence-control",)), Err), (
        "missing mutant result was accepted"
    )


def test_manifest_schema_and_read_errors(tmp_path: Path) -> None:
    """Closed fields, node identities and actual JSON reads reject malformed inputs."""
    for value in (
        None,
        {},
        _record(extra=True),
        _record(nonce=1),
        _record(forbidden="skip"),
        _record(classes=[]),
        _record(collected="node"),
        _record(collected=[NODE, NODE]),
        _record(classes={NODE: "owed"}),
        _record(classes={}),
    ):
        assert isinstance(parse_manifest(value), Err)
    path = tmp_path / "manifest.json"
    assert isinstance(read_manifest(path), Err)
    path.write_text("invalid JSON", encoding="utf-8")
    assert isinstance(read_manifest(path), Err)
    path.write_text(json.dumps(_record()), encoding="utf-8")
    assert read_manifest(path) == parse_manifest(_record())


def _expected(entries: tuple[tuple[str, str, tuple[bytes, ...]], ...]) -> str:
    """Encode the stated rule directly, without importing the subject's encoder."""
    hashed = hashlib.sha256()
    for path, kind, payloads in sorted(entries):
        for field in (path.encode("utf-8"), kind.encode("ascii"), *payloads):
            hashed.update(len(field).to_bytes(8, "big"))
            hashed.update(field)
    return hashed.hexdigest()


def test_digest_byte_vector_and_currency(tmp_path: Path) -> None:
    """A hand-authored entry vector joins every ignored and untracked byte."""
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "pyproject.toml").write_bytes(b"project = 1\n")
    source = tmp_path / "src/example.py"
    source.write_bytes(b"answer = 42\n")
    entries = (
        ("src", "directory", (b"",)),
        ("tests", "directory", (b"",)),
        ("pyproject.toml", "file", (b"project = 1\n",)),
        ("src/example.py", "file", (b"answer = 42\n",)),
    )
    original = digest(tmp_path)
    assert original == Ok(_expected(entries))
    (tmp_path / "DEVELOPMENT_PLAN").mkdir()
    (tmp_path / "DEVELOPMENT_PLAN/row.md").write_text(
        "recording evidence", encoding="utf-8"
    )
    assert digest(tmp_path) == original
    (tmp_path / "src/.ignored").write_bytes(b"ignored")
    assert digest(tmp_path) == Ok(
        _expected((*entries, ("src/.ignored", "file", (b"ignored",))))
    )
    assert digest(tmp_path) != original
    (tmp_path / "src/.ignored").unlink()
    source.write_bytes(b"answer = 43\n")
    assert digest(tmp_path) != original


def test_digest_link_bytes_and_errors(tmp_path: Path) -> None:
    """Literal link text and resolved bytes contribute; unreadable inputs fail."""
    assert isinstance(digest(tmp_path), Err)
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    assert isinstance(digest(tmp_path), Err)
    (tmp_path / "pyproject.toml").write_bytes(b"project = 1\n")
    target = tmp_path / "src/target"
    target.write_bytes(b"content")
    before = digest(tmp_path)
    assert isinstance(before, Ok)
    link = tmp_path / "src/link"
    if platform.system() == "Windows":
        link.hardlink_to(target)
        assert digest(tmp_path) != before
        target.write_bytes(b"changed")
        assert link.read_bytes() == b"changed"
    else:
        special = tmp_path / "src/unsupported"
        assert isinstance(os, FifoOperations)
        os.mkfifo(special)
        assert isinstance(digest(tmp_path), Err)
        special.unlink()
        link.symlink_to("./target")
        first = digest(tmp_path)
        assert isinstance(first, Ok)
        link.unlink()
        link.symlink_to("target")
        assert digest(tmp_path) != first
        link.unlink()
        link.symlink_to(tmp_path.parent)
        assert isinstance(digest(tmp_path), Err)
        link.unlink()
        link.symlink_to("missing")
        assert isinstance(digest(tmp_path), Err)


def _post_tree(root: Path) -> tuple[Mutant, ...]:
    """Supply a minimal valid input for the execution-join component."""
    plan = root / "DEVELOPMENT_PLAN"
    plan.mkdir()
    filename = "phase-0-governance-and-check-skeleton.md"
    (plan / "development_plan_standards.md").write_text(
        "| [Governance](" + filename + ") | `M-legs-` |\n", encoding="utf-8"
    )
    (plan / "00-overview.md").write_text(
        "## Requirements\n\n| ID | Requirement |\n|---|---|\n| R20 | known control |\n",
        encoding="utf-8",
    )
    (plan / filename).write_text(
        "# Phase 0 — Control\n\n**Status**: Done\n**Gate kind**: self-verifying\n"
        "**Host lane**: any-host\n\n## Gate Integrity\n\n"
        "| Requirement | Oracle | Observer | Mutants | Tests |\n|---|---|---|---|---|\n"
        "| R20 — known control | none — explicit minimal input | value: known input | "
        "`M-legs-control` | `" + NODE + "` |\n\n## Sprints\n\n"
        "### Sprint 0.1: Control [Done]\n\n**Implementation**: `src/subject.py`\n"
        "**Validation tests**: `" + NODE + "`\n**Mutants**: `M-legs-control`\n"
        "\n## Remaining Work\n\nNone.\n",
        encoding="utf-8",
    )
    return (
        Mutant(
            "M-legs-control",
            Operator.REPLACE_LITERAL,
            "src/subject.py",
            "return 2",
            "return 3",
            (NODE,),
            "named control",
        ),
    )


def test_post_run_pipeline_controls(tmp_path: Path) -> None:
    """Actual manifest reads distinguish missing, stale and complete join inputs."""
    records = _post_tree(tmp_path)
    assert post_run(tmp_path, tmp_path, "current", records) == 1
    path = tmp_path / "pytest-manifest.json"
    path.write_text(json.dumps(_record(nonce="old")), encoding="utf-8")
    assert post_run(tmp_path, tmp_path, "current", records) == 1
    case = "tests/governance/test_mutants.py::test_corpus[M-legs-control]"
    complete = _record(
        collected=[NODE, case],
        executed=[NODE, case],
        passed=[NODE, case],
        classes={NODE: "value", case: "real"},
    )
    path.write_text(json.dumps(complete), encoding="utf-8")
    assert post_run(tmp_path, tmp_path, "current", records) == 1
    native = "haskell:agentctl-core-test/Handshake/protocol-fields"
    (tmp_path / "haskell-manifest.json").write_text(
        json.dumps(
            _record(
                collected=[native],
                executed=[native],
                passed=[native],
                classes={native: "value"},
            )
        ),
        encoding="utf-8",
    )
    assert post_run(tmp_path, tmp_path, "current", records) == 0
    path.write_text(
        json.dumps(
            _record(
                collected=[case], executed=[case], passed=[case], classes={case: "real"}
            )
        ),
        encoding="utf-8",
    )
    assert post_run(tmp_path, tmp_path, "current", records) == 1
    (tmp_path / "DEVELOPMENT_PLAN/phase-0-governance-and-check-skeleton.md").unlink()
    path.write_text(json.dumps(complete), encoding="utf-8")
    assert post_run(tmp_path, tmp_path, "current", records) == 1


def test_lane_summary_pipeline_controls(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Emit rows for an intact model and suppress them after each failed boundary."""
    root = tmp_path / "subject"
    root.mkdir()
    _post_tree(root)
    (root / "src").mkdir()
    (root / "tests").mkdir()
    (root / "pyproject.toml").write_bytes(b"project = 1\n")
    repository(root)
    context = CheckRun(root, tmp_path, "current", "Linux")
    assert summarize(context, 1) == 1
    assert summarize(context, 0) == 1
    assert "EVIDENCE " not in capsys.readouterr().out
    host = tmp_path / "host.json"
    facts = HostFacts(family="Linux", architecture="x86_64", checkout=True, git=True)
    host.write_text(
        json.dumps({"nonce": "current", "facts": asdict(facts)}), encoding="utf-8"
    )
    assert summarize(context, 0) == 0
    output = capsys.readouterr().out
    rows = tuple(line for line in output.splitlines() if line.startswith("EVIDENCE "))
    assert len(rows) == 1
    assert re.fullmatch(
        (
            r"EVIDENCE \d{4}-\d{2}-\d{2} ; any-host ; agentctl check ; pass ; "
            r"tree [a-f0-9]{64} ; os=Linux,arch=x86_64,baseline=no baseline"
        ),
        rows[0],
    )
    phase = root / "DEVELOPMENT_PLAN/phase-0-governance-and-check-skeleton.md"
    original = phase.read_text(encoding="utf-8")
    phase.write_text(original.replace("any-host", "mux-host"), encoding="utf-8")
    assert summarize(context, 0) == 1
    assert "EVIDENCE " not in capsys.readouterr().out
    phase.write_text(original, encoding="utf-8")
    (root / "pyproject.toml").unlink()
    assert summarize(context, 0) == 1
    assert "EVIDENCE " not in capsys.readouterr().out
    (root / "pyproject.toml").write_bytes(b"project = 1\n")
    (root / ".git/HEAD").write_text("unreadable baseline\n", encoding="utf-8")
    assert summarize(context, 0) == 1
    assert "EVIDENCE " not in capsys.readouterr().out
