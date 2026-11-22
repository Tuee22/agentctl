# Copyright (c) 2026 agentctl contributors.
"""Actual local host sampling, with no Linux workload or WSL invocation."""

import os
import platform
import sys
from pathlib import Path

import pytest

from agentctl.check.wsl_host_sample import observe
from agentctl.process import run
from agentctl.result import Err, Ok

pytestmark = pytest.mark.evidence("real")


def test_host_sample_uses_native_counters(tmp_path: Path) -> None:
    """Windows reads native counters; other hosts explicitly refuse this adapter."""
    result = observe(tmp_path, tmp_path, tmp_path)
    if platform.system() != "Windows":
        assert isinstance(result, Err)
        assert "requires Windows" in result.error
    else:
        assert isinstance(result, Ok), result
        assert result.value.cpus == os.cpu_count()
        assert result.value.available_memory > 0
        assert result.value.commit_headroom >= 0
        assert result.value.vhd_free > 0
        assert result.value.source_free > 0
        assert result.value.shared_volume


def test_host_counter_executable_ignores_environment_redirect(tmp_path: Path) -> None:
    """An isolated spawn audit checks the counter executable before it can run."""
    script = (
        "import os, platform, sys\nfrom pathlib import Path\n"
        "from agentctl.check.hyperv_observe import system_powershell\n"
        "from agentctl.check.wsl_host_sample import _counters\n"
        "from agentctl.foundation import Err, Ok\n"
        "expected = system_powershell()\n"
        "seen = []\n"
        "def audit(event, args):\n"
        "    if event == 'subprocess.Popen':\n"
        "        seen.append(str(args[1]))\n"
        "        raise OSError('owned audit veto')\n"
        "sys.addaudithook(audit)\n"
        "os.environ['SYSTEMROOT'] = sys.argv[1]\n"
        "outcome = _counters(Path(sys.argv[1]))\n"
        "assert isinstance(outcome, Err)\n"
        "if platform.system() == 'Windows':\n"
        "    assert isinstance(expected, Ok)\n"
        "    prefix = str(expected.value)\n"
        "    assert len(seen) == 1 and (seen[0].startswith(prefix + ' ') or "
        "seen[0].startswith(chr(34) + prefix + chr(34) + ' ')), "
        "'host counter executable was redirected'\n"
        "else:\n"
        "    assert isinstance(expected, Err) and not seen\n"
    )
    result = run(
        [sys.executable, "-c", script, str(tmp_path)],
        cwd=tmp_path,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    assert isinstance(result, Ok), result
    assert result.value.code == 0, result.value.stderr
