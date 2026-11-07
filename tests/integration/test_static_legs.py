# Copyright (c) 2026 agentctl contributors.
"""Pinned tools reject copied negative fixtures and accept their twins."""

import json
import os
import sys
from pathlib import Path

import pytest

from agentctl.check.legs import python_legs
from agentctl.check.steps import environment
from agentctl.process import Output, run
from agentctl.result import Ok

pytestmark = pytest.mark.evidence("real")


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
    assert "error[invalid-assignment]" in negative.stdout, "ty did not report an error"
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
    assert "error[invalid-assignment]" in negative.stdout, "user config weakened ty"
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
