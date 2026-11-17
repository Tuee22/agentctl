# Copyright (c) 2026 agentctl contributors.
"""Real bootstrap publication without an agent or multiplexer fixture."""

import os
import sys
from pathlib import Path

import pytest

from agentctl.bootstrap import binary, build
from agentctl.foundation import Ok
from agentctl.process import run
from tests.harness.bootstrap_caller import CallerRequest, publish
from tests.harness.haskell_fixtures import haskell_build as _haskell_build_fixture

haskell_build = _haskell_build_fixture
pytestmark = pytest.mark.evidence("real")


def test_published_caller_without_launch_fixture(
    root: Path, tmp_path: Path, haskell_build: build.BuildContext
) -> None:
    """The lower bootstrap boundary publishes and verifies the real native binary."""
    family = haskell_build.host.family
    assert family in {"Linux", "Darwin", "Windows"}
    environment = {
        **os.environ,
        "HOME": str(tmp_path),
        "USERPROFILE": str(tmp_path),
        "LOCALAPPDATA": str(tmp_path / "local"),
        "XDG_CACHE_HOME": str(tmp_path / "cache"),
        "XDG_DATA_HOME": str(tmp_path / "data"),
        "XDG_STATE_HOME": str(tmp_path / "state"),
    }
    caller = publish(
        CallerRequest(root, haskell_build, family, tmp_path, tuple(environment.items()))
    )
    assert caller.executable.is_file()
    assert caller.executable.is_relative_to(caller.paths.data)
    assert binary.verify_handshake(haskell_build, caller.executable) == Ok(None)
    assert dict(caller.environment)["HOME"] == str(tmp_path)


@pytest.mark.evidence("real")
def test_bootstrap_caller_import_without_later_helpers(
    root: Path, tmp_path: Path
) -> None:
    """Publication and real transport execution avoid later fixture imports."""
    script = (
        "import importlib.abc, sys\n"
        "class Refuse(importlib.abc.MetaPathFinder):\n"
        "    def find_spec(self, fullname, path=None, target=None):\n"
        "        if fullname in {'tests.harness.launch', 'tests.harness.tmux', "
        "'tests.harness.tmux_fixtures', 'tests.harness.passthrough'}:\n"
        "            raise ImportError('later helper unavailable: ' + fullname)\n"
        "        return None\n"
        "sys.meta_path.insert(0, Refuse())\n"
        "import tests.harness.bootstrap_caller as caller\n"
        "import tests.harness.transport_fixture\n"
        "assert callable(caller.publish)\n"
        "import pytest\n"
        "code = pytest.main(['-p', 'no:cacheprovider', "
        "'tests/unit/test_passthrough.py::"
        "test_passthrough_table_matches_oracle', "
        "'tests/unit/test_passthrough.py::"
        "test_raw_tail_keeps_dashdash_and_help', "
        "'tests/integration/test_passthrough.py::"
        "test_passthrough_table_equals_binary_commands', "
        "'tests/integration/test_passthrough.py::"
        "test_binary_refuses_direct_run', '-q'])\n"
        "raise SystemExit(code)\n"
    )
    environment = {
        key: value
        for key, value in os.environ.items()
        if key
        not in {"AGENTCTL_CHECK_NONCE", "AGENTCTL_CHECK_MANIFEST", "PYTEST_ADDOPTS"}
    }
    result = run(
        [sys.executable, "-c", script],
        cwd=root,
        env={
            **environment,
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
            "XDG_STATE_HOME": str(tmp_path / "state"),
        },
    )
    assert isinstance(result, Ok)
    assert result.value.code == 0, (
        "bootstrap caller needs later helper: "
        + result.value.stdout
        + result.value.stderr
    )


def test_early_transport_does_not_import_later_helpers(
    root: Path, tmp_path: Path
) -> None:
    """Observe actual imports without substituting or refusing any module."""
    script = (
        "import sys\n"
        "import tests.harness.bootstrap_caller\n"
        "import tests.harness.transport_fixture\n"
        "import tests.unit.test_passthrough\n"
        "import tests.integration.test_passthrough\n"
        "later = {'tests.harness.launch', 'tests.harness.tmux', "
        "'tests.harness.tmux_fixtures', 'tests.harness.passthrough'}\n"
        "loaded = sorted(later.intersection(sys.modules))\n"
        "print(', '.join(loaded))\n"
        "raise SystemExit(bool(loaded))\n"
    )
    result = run(
        [sys.executable, "-c", script],
        cwd=root,
        env={
            **os.environ,
            "PYTHONDONTWRITEBYTECODE": "1",
            "XDG_STATE_HOME": str(tmp_path / "state"),
        },
    )
    assert isinstance(result, Ok)
    assert result.value.code == 0, (
        "early transport imported later helper: "
        + result.value.stdout
        + result.value.stderr
    )
