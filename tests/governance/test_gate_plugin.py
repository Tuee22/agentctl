# Copyright (c) 2026 agentctl contributors.
"""Two-sided pytester evidence for the full-suite discipline plugin."""

import json
import os
import sys
from pathlib import Path

import pytest

from agentctl.check.gate_plugin import orphan_modules
from agentctl.check.legs import coverage_commands
from agentctl.process import run
from agentctl.result import Ok

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


def test_coverage_gap_fails(tmp_path: Path) -> None:
    """A real uncovered branch fails at 100; exercising both arms qualifies."""
    (tmp_path / "pyproject.toml").write_text(
        '[tool.coverage.run]\nbranch = true\nsource = ["subject"]\n'
        "[tool.coverage.report]\nfail_under = 100\n",
        encoding="utf-8",
    )
    (tmp_path / "subject.py").write_text(
        "def choose(value: bool) -> int:\n"
        "    if value:\n        return 1\n    return 2\n",
        encoding="utf-8",
    )
    program = tmp_path / "exercise.py"
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
