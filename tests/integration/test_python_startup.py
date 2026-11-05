# Copyright (c) 2026 agentctl contributors.
"""The private application interpreter leaves the covered source tree untouched."""

import importlib.metadata
import os
import sys
import tomllib
from pathlib import Path

import pytest

from agentctl.process import run
from agentctl.result import Ok

pytestmark = pytest.mark.evidence("real")


def test_startup_precedes_editable_imports(root: Path, tmp_path: Path) -> None:
    """Observe installed startup policy with bytecode-writing enabled in a control."""
    oracle = tomllib.loads(
        (root / "tests/oracles/python_startup.toml").read_text(encoding="utf-8")
    )["case"][0]
    expected: object = oracle["expected"]
    assert isinstance(expected, dict)
    destination, contents = expected["destination"], expected["contents"]
    assert isinstance(destination, str)
    assert isinstance(contents, str)
    installed = importlib.metadata.distribution("agentctl").locate_file(destination)
    assert isinstance(installed, Path)
    assert installed.read_text(encoding="utf-8") == contents
    assert (root / "src/agentctl/resources/python-startup.pth").read_text(
        encoding="utf-8"
    ) == contents, "startup policy differs from frozen oracle"
    recipe = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))[
        "tool"
    ]["hatch"]["build"]["targets"]["wheel"]["force-include"]
    assert recipe == {"src/agentctl/resources/python-startup.pth": destination}, (
        "startup packaging differs from frozen oracle"
    )
    (tmp_path / "startup_fixture.py").write_text(
        "VALUE = 'observed'\n", encoding="utf-8"
    )
    env = {
        key: value for key, value in os.environ.items() if not key.startswith("PYTHON")
    }
    program = (
        "import sys\nsys.path.insert(0, sys.argv[1])\n"
        "import startup_fixture\n"
        "print(sys.dont_write_bytecode)\nprint(startup_fixture.VALUE)\n"
    )
    result = run([sys.executable, "-c", program, str(tmp_path)], cwd=tmp_path, env=env)
    assert isinstance(result, Ok)
    assert result.value.code == 0, result.value.stderr
    assert result.value.stdout.splitlines() == ["True", "observed"]
    assert not (tmp_path / "__pycache__").exists()
    control = run(
        [sys.executable, "-S", "-c", program, str(tmp_path)],
        cwd=tmp_path,
        env={
            key: value for key, value in env.items() if not key.startswith("COVERAGE_")
        },
    )
    assert isinstance(control, Ok)
    assert control.value.code == 0
    assert control.value.stdout.splitlines() == ["False", "observed"]
    assert tuple((tmp_path / "__pycache__").glob("startup_fixture.*.pyc"))
