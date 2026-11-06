# Copyright (c) 2026 agentctl contributors.
"""Native prerequisite effects against independently linked and absent controls."""

import os
import platform
import shutil
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from agentctl.bootstrap.prereqs import invoke, probe
from agentctl.check.lanes import HostFacts
from agentctl.hostfacts import HostContext, Prerequisite, current
from agentctl.process import Output, SpawnError, run
from agentctl.result import Ok, Result
from tests.harness.host import observe_xcode

pytestmark = pytest.mark.evidence("real")


def test_probe_matches_independent_observer(
    tmp_path: Path, record_host: HostFacts
) -> None:
    """Compare native probes and always reject an unusable constructed compiler."""
    context = replace(current(tmp_path / "subject-cache"), cwd=tmp_path)
    measured = probe(context)
    assert isinstance(measured, Ok)
    family = platform.system()
    assert not observe_xcode("Darwin", tmp_path, {"PATH": ""})
    assert record_host.xcode == (family == "Darwin"), (
        "host observation lost the native Command Line Tools qualification"
    )
    if family == "Linux":
        compiler = shutil.which("cc")
        assert compiler is not None
        source = tmp_path / "independent.c"
        source.write_text("int main(void) { return 0; }\n", encoding="utf-8")
        result = run(
            [
                compiler,
                str(source),
                "-lgmp",
                "-o",
                str(tmp_path / "independent-output"),
            ],
            cwd=tmp_path,
            env=os.environ,
        )
        assert isinstance(result, Ok)
        assert result.value.code == 0, result.value.stderr
        assert measured.value[0] == Prerequisite("compiler-and-gmp", ready=True)
    elif family == "Darwin":
        xcode = shutil.which("xcode-select")
        assert xcode is not None
        result = run([xcode, "-p"], cwd=tmp_path, env=os.environ)
        assert isinstance(result, Ok)
        assert result.value.code == 0, result.value.stderr
        assert measured.value == (Prerequisite("xcode-clt", ready=True),)
    else:
        assert family == "Windows"
        assert measured.value == ()
    binaries = tmp_path / "unusable-compiler"
    binaries.mkdir()
    compiler_name = "cc.exe" if family == "Windows" else "cc"
    (binaries / compiler_name).write_text(
        "discovery-only compiler candidate", encoding="utf-8"
    )
    (binaries / compiler_name).chmod(0o755)
    env = {**os.environ, "PATH": str(binaries), "PYTHONDONTWRITEBYTECODE": "1"}
    constructed = replace(
        context,
        family="Linux",
        cache=tmp_path / "negative-cache",
        environment=tuple(env.items()),
    )
    assert shutil.which("cc", path=str(binaries)) is not None

    def unusable(
        arguments: tuple[str, ...], value: HostContext
    ) -> Result[Output, SpawnError]:
        assert arguments[2:4] == ("-lgmp", "-o")
        return invoke((sys.executable, *arguments[1:]), value)

    rejected = probe(constructed, unusable, certificates=(None, None))
    assert isinstance(rejected, Ok)
    assert rejected.value[0] == Prerequisite("compiler-and-gmp", ready=False), (
        "compiler presence replaced the GMP link probe"
    )
    missing = probe(
        replace(constructed, environment=(("PATH", ""),)), certificates=(None, None)
    )
    assert missing == Ok(
        (
            Prerequisite("compiler-and-gmp", ready=False),
            Prerequisite("downloader", ready=False),
            Prerequisite("ca-certificates", ready=False),
            Prerequisite("make", ready=False),
        )
    )
