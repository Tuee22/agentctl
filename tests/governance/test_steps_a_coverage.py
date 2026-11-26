# Copyright (c) 2026 agentctl contributors.
"""Coverage capture, agreement and attribution refuse damaged observations."""

import os
import sys
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path

import pytest

from agentctl.check import steps
from agentctl.check.evidence import Entry, ToolSubsteps, source_census
from agentctl.check.legs import Leg, coverage_commands
from agentctl.check.plan_data import Phase
from agentctl.check.validator.source import SourceIssue
from agentctl.foundation import Err, Ok
from agentctl.foundation_process_values import Output

pytestmark = pytest.mark.evidence("value")
NONCE = "a" * 32
VERSION = "7.17.0"
FAILED_STATUS = 1
LINK_SUFFIX = ".extra"
MANIFEST = "src/agentctl/check/source_ownership.toml"
CONFIG = (
    '[project.optional-dependencies]\ndev = ["coverage==7.17.0"]\n'
    '[tool.coverage.run]\nbranch = true\nsource = ["src/agentctl"]\n'
)
HOSTS = (
    "version = 1\n[[source]]\npath = 'src/agentctl/subject.py'\n"
    "hosts = ['Linux', 'Darwin', 'Windows']\n"
)
OWNERSHIP = (
    "version = 1\n"
    "[[phases]]\nnumber = 0\nprerequisites = []\n"
    "[[phases]]\nnumber = 1\nprerequisites = [0]\n"
    "[[artifacts]]\npath = 'src/agentctl/subject.py'\n"
    "capability = 'subject'\nowner = 0\nconsumers = [0, 1]\nrequired = true\n"
)


@dataclass(frozen=True)
class Project:
    """A real covered project, its run directory and the original observations."""

    context: steps.CheckRun
    entries: tuple[Entry, ...]
    leg: Leg
    substeps: ToolSubsteps
    text: steps.CoverageTextSnapshot


def _project(tmp_path: Path) -> Project:
    root, directory = tmp_path / "project", tmp_path / "run"
    source = root / "src/agentctl"
    (source / "check").mkdir(parents=True)
    directory.mkdir()
    subject = source / "subject.py"
    subject.write_text("if __name__ == '__main__':\n    print('run')\n", "utf-8")
    (root / "pyproject.toml").write_text(CONFIG, encoding="utf-8")
    (source / "check/coverage_hosts.toml").write_text(HOSTS, encoding="utf-8")
    (source / "check/source_ownership.toml").write_text(OWNERSHIP, encoding="utf-8")
    leg = Leg(
        "pytest",
        (
            sys.executable,
            "-m",
            "coverage",
            "run",
            "--branch",
            "--parallel-mode",
            f"--rcfile={root / 'pyproject.toml'}",
            f"--data-file={directory / 'coverage'}",
            str(subject),
        ),
        coverage_commands(sys.executable, root, directory),
        after_failure=True,
    )
    observed = steps.__dict__["_run_leg_observed"](root, directory, NONCE, leg)
    entries = source_census(root)
    assert isinstance(entries, Ok)
    assert isinstance(observed.coverage_text, Ok)
    return Project(
        steps.CheckRun(root, directory, NONCE, "Linux"),
        entries.value,
        leg,
        ToolSubsteps(NONCE, (("pytest", observed.substeps),)),
        observed.coverage_text.value,
    )


def _linking_open(real: Callable[..., int], victim: Path) -> Callable[..., int]:
    def racing(path: str | Path, flags: int, *args: int, **kwargs: int) -> int:
        descriptor = real(path, flags, *args, **kwargs)
        if Path(path) == victim:
            os.link(victim, victim.with_name(victim.name + LINK_SUFFIX))
        return descriptor

    return racing


def _command_request(script: str, run_dir: Path) -> steps.CoverageRequest:
    raw = str(run_dir / "coverage-raw.json")
    return steps.CoverageRequest(VERSION, (sys.executable, "-c", script, raw), 0)


def test_real_capture_is_joined_to_its_report_text(tmp_path: Path) -> None:
    """A captured report joins its text, survives, and fails once it is removed."""
    project = _project(tmp_path)
    run_dir = project.context.directory
    captured = steps.__dict__["_capture_tool_coverage"](
        project.context, Ok(project.entries), (project.leg,), Ok(project.substeps)
    )
    assert isinstance(captured, Ok)
    tools = steps.ToolOutcome(
        1,
        Err("unused"),
        Ok(project.substeps),
        coverage_text=Ok(project.text),
    )
    assert (
        steps.coverage_text_integrity(
            project.context, Ok(project.entries), (project.leg,), tools, captured
        )
        == 0
    )
    inputs = steps.CoverageTextInputs(
        project.context,
        project.entries,
        project.leg,
        Ok(project.substeps),
        Ok(project.text),
        captured,
    )
    unavailable = "coverage text or JSON observation unavailable"
    assert steps.coverage_text_agreement(replace(inputs, text=None)) == Err(unavailable)
    undecodable = Ok(replace(captured.value, report=b"\xff"))
    assert steps.coverage_text_agreement(replace(inputs, coverage=undecodable)) == Err(
        "coverage JSON report is not UTF-8"
    )
    invalid_context = replace(project.context, nonce="bad")
    assert steps.coverage_text_agreement(
        replace(inputs, context=invalid_context)
    ) == Err("invalid coverage capture nonce")
    (run_dir / "coverage-raw.json").unlink()
    assert steps.coverage_snapshot_unchanged(run_dir, NONCE, captured) == FAILED_STATUS


def test_render_refuses_command_and_file_damage(tmp_path: Path) -> None:
    """The reserved report must survive its command with one link and valid text."""
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    context = steps.CheckRun(tmp_path, run_dir, NONCE, "Linux")
    render = steps.__dict__["_render_coverage"]
    missing = steps.CoverageRequest(VERSION, (str(tmp_path / "absent-tool"),), 0)
    failed = render(context, missing)
    assert isinstance(failed, Err)
    assert failed.error.startswith("coverage JSON command failed: ")
    scripts = (
        ("import os,sys; os.link(sys.argv[1], sys.argv[1] + '.x')", "identity"),
        ("import os,sys; os.unlink(sys.argv[1])", "cannot read"),
        ("import sys; open(sys.argv[1], 'wb').write(b'\\xff')", "cannot read"),
    )
    for script, message in scripts:
        (run_dir / "coverage-raw.json").unlink(missing_ok=True)
        (run_dir / "coverage-raw.json.x").unlink(missing_ok=True)
        refused = render(context, _command_request(script, run_dir))
        assert isinstance(refused, Err)
        assert message in refused.error


def test_rendered_report_must_parse(tmp_path: Path) -> None:
    """Unparsable report text is not joined to statuses."""
    rendered = steps.__dict__["_coverage_rendered"](
        b"x", "x", steps.CoverageRequest(VERSION, (), 0), 0, tmp_path.stat()
    )
    assert isinstance(rendered, Err)
    assert rendered.error.startswith("coverage JSON report: ")


def test_record_coverage_refuses_encoding_races_and_existing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A raw report must be text, and its record must stay private and new."""
    context = steps.CheckRun(tmp_path, tmp_path, NONCE, "Linux")
    request = steps.CoverageRequest(VERSION, (), 0)
    record = steps.__dict__["_record_coverage"]
    assert record(context, request, steps.CoverageRendered((), b"\xff", (0, 0))) == (
        Err("invalid coverage report encoding")
    )
    rendered = steps.CoverageRendered((), b"{}", (0, 0))
    target = tmp_path / "coverage-report.json"
    with monkeypatch.context() as patch:
        patch.setattr(steps.os, "open", _linking_open(os.open, target))
        raced = record(context, request, rendered)
    assert raced == Err("coverage capture changed during recording")
    existing = record(context, request, rendered)
    assert isinstance(existing, Err)
    assert existing.error.startswith("cannot record coverage capture: ")


def test_coverage_source_owners_refuse_unreadable_manifests() -> None:
    """Ownership must come from a parsed manifest in the source census."""
    owners = steps.__dict__["_coverage_source_owners"]
    missing = owners((), ())
    assert isinstance(missing, Err)
    assert missing.error.startswith("coverage ownership unavailable: ")
    broken = owners((Entry(MANIFEST, "file", (b"= not toml",)),), ())
    assert isinstance(broken, Err)
    assert broken.error.startswith("invalid coverage ownership: ")


def test_provisional_coverage_needs_a_host_family() -> None:
    """A captured report without its host family cannot be attributed."""
    tools = steps.ToolOutcome(1, Err("unused"), Err("unused"))
    captured = steps.ProvisionalCapture(
        Ok(()),
        Err("unused"),
        tools,
        None,
        Err("unused"),
        NONCE,
        (),
        (),
        coverage=Err("captured"),
    )
    attribution = steps.ToolFailureAttribution(frozenset(), ())
    join = steps.__dict__["_coverage_provisional_attribution"]
    assert join(captured, (), (), attribution) == Err(
        "coverage host family unavailable"
    )


def _host_capture() -> steps.ProvisionalCapture:
    host = Ok(steps.lanes.HostFacts("Linux", "x86_64", checkout=True, git=True))
    tools = steps.ToolOutcome(1, Err("unused"), Err("unused"), host=host)
    return steps.ProvisionalCapture(
        Ok(()), Err("unused"), tools, None, Err("unused"), NONCE, (), (), family="Linux"
    )


def test_phase_host_attribution_refuses_scope_and_lane_damage(tmp_path: Path) -> None:
    """Host attribution needs matching phase scopes and a known host lane."""
    declaration = Phase(0, tmp_path / "phase.md", "**Host lane**: linux\n", ())
    unlaned = Phase(0, tmp_path / "phase.md", "no lane\n", ())
    scoped = steps.ToolFailureAttribution(frozenset(), ((0, frozenset()),))
    unscoped = steps.ToolFailureAttribution(frozenset(), ())
    assert steps.phase_host_attribution(
        _host_capture(), (declaration,), unscoped
    ) == Err("phase native host scopes differ")
    assert steps.phase_host_attribution(_host_capture(), (unlaned,), scoped) == Err(
        "invalid phase native host lane"
    )


def test_source_validation_refuses_unreadable_ownership() -> None:
    """Source issues need a parsed ownership manifest to be scoped."""
    issues = (SourceIssue("src/x.py", "bad"),)
    missing = steps.source_validation_attribution((), (), issues)
    assert isinstance(missing, Err)
    assert "missing or duplicate census declaration" in missing.error
    broken = steps.source_validation_attribution(
        (Entry(MANIFEST, "file", (b"= not toml",)),), (), issues
    )
    assert isinstance(broken, Err)


def test_ruff_validation_refuses_failed_or_unrecorded_tools() -> None:
    """A failed Ruff observation or unavailable tool status is propagated."""
    failed = steps.ToolOutcome(1, Err("unused"), Err("unused"), ruff=Err("ruff failed"))
    captured = steps.ProvisionalCapture(
        Ok(()), Err("unused"), failed, None, Err("unused"), NONCE, (), ()
    )
    assert steps.ruff_validation_attribution(captured, (), ()) == Err("ruff failed")
    snapshot = steps.RuffSnapshot(NONCE, Path("/"), Output(0, "[]", ""), ())
    unavailable = replace(failed, ruff=Ok(snapshot))
    assert steps.ruff_validation_attribution(
        replace(captured, tools=unavailable), (), ()
    ) == Err("Ruff tool status unavailable")
