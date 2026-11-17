# Copyright (c) 2026 agentctl contributors.
"""Build the actual early protocol component independently of later code."""

import json
import os
import platform
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from agentctl.bootstrap import build
from agentctl.check.preconditions import exclusive_file
from agentctl.process import run
from agentctl.result import Err, Ok
from tests.harness.haskell import copy_project
from tests.harness.nonce import fresh

pytestmark = pytest.mark.evidence("real")


def test_bootstrap_protocol_build_is_independent(root: Path, tmp_path: Path) -> None:
    """A broken later module cannot mask or supply the early protocol build."""
    context = replace(
        copy_project(root, tmp_path), prepared_index_only=True, options=("--offline",)
    )
    later = context.project / "src/AgentCtl/Protocol.hs"
    later.write_text("not valid Haskell\n", encoding="utf-8")
    with exclusive_file(context.directory / "build.lock") as held:
        assert held == Ok(None)
        result = build.compile_target(context, "lib:bootstrap")
        assert isinstance(result, Ok), (
            f"bootstrap protocol depended on later source: {result!a}"
        )
        early = context.project / "bootstrap-src/AgentCtl/Bootstrap/Protocol.hs"
        early.write_text("not valid Haskell\n", encoding="utf-8")
        assert isinstance(build.compile_target(context, "lib:bootstrap"), Err), (
            "broken bootstrap protocol compiled"
        )


def test_bootstrap_native_receiver_preserves_raw_tail(
    root: Path, tmp_path: Path
) -> None:
    """A real early-only receiver observes literal arguments through the handoff."""
    context = replace(
        copy_project(root, tmp_path), prepared_index_only=True, options=("--offline",)
    )
    later = context.project / "src/AgentCtl/Protocol.hs"
    later.write_text("not valid Haskell\n", encoding="utf-8")
    with exclusive_file(context.directory / "build.lock") as held:
        assert held == Ok(None)
        compiled = build.compile_target(context, "exe:agentctl-bootstrap-probe")
        assert isinstance(compiled, Ok), compiled
    probe = build.binary(context, "exe:agentctl-bootstrap-probe")
    assert isinstance(probe, Ok), probe
    nonce = fresh(os.environ.get("AGENTCTL_CHECK_NONCE", "focused"))
    arguments = ("--", "", "--assume-yes", "é", "a\nb", "$(id)", "#{pane_id}")
    program = (
        "import os, platform, sys\n"
        "from pathlib import Path\n"
        "from agentctl.bootstrap.handoff import Transfer, mode, transfer\n"
        "from agentctl.result import Err\n"
        "request = Transfer(mode(platform.system()), Path(sys.argv[1]), "
        "tuple(sys.argv[2:]), Path.cwd(), tuple(os.environ.items()))\n"
        "result = transfer(request)\n"
        "raise SystemExit(1 if isinstance(result, Err) else result.value)\n"
    )
    family = platform.system()
    assert family in {"Linux", "Darwin", "Windows"}
    observed = run(
        [sys.executable, "-c", program, str(probe.value), *arguments],
        cwd=tmp_path,
        env={
            **os.environ,
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPATH": str(root / "src") + os.pathsep + str(root),
            "AGENTCTL_TRANSPORT_NONCE": nonce,
            "AGENTCTL_ASSUME_YES": "invalid",
        },
    )
    assert isinstance(observed, Ok), observed
    assert observed.value.code == 0, observed.value.stderr
    unchanged = json.loads(observed.value.stdout) == {
        "handshake": {"protocol": 2, "commands": []},
        "arguments": list(arguments),
        "consent": None,
        "nonce": nonce,
    }
    assert unchanged, (
        f"bootstrap native receiver observed a changed tail: {observed.value.stdout!a}"
    )


def test_bootstrap_cli_consent_is_separate_from_tail(
    root: Path, tmp_path: Path
) -> None:
    """The public global flag reaches a native receiver independently of the tail."""
    context = replace(
        copy_project(root, tmp_path), prepared_index_only=True, options=("--offline",)
    )
    (context.project / "src/AgentCtl/Protocol.hs").write_text(
        "not valid Haskell\n", encoding="utf-8"
    )
    with exclusive_file(context.directory / "build.lock") as held:
        assert held == Ok(None)
        compiled = build.compile_target(context, "exe:agentctl-bootstrap-probe")
        assert isinstance(compiled, Ok), compiled
    probe = build.binary(context, "exe:agentctl-bootstrap-probe")
    assert isinstance(probe, Ok), probe
    program = (
        "import sys\n"
        "from pathlib import Path\n"
        "from agentctl.bootstrap import handoff\n"
        "from agentctl.cli import main\n"
        "from agentctl.result import Ok\n"
        "handoff.binary.ensure = lambda _request: Ok(Path(sys.argv[1]))\n"
        "main(sys.argv[2:])\n"
    )
    nonce = fresh(os.environ.get("AGENTCTL_CHECK_NONCE", "focused"))
    environment = {
        **os.environ,
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPATH": str(root / "src") + os.pathsep + str(root),
        "AGENTCTL_TRANSPORT_NONCE": nonce,
        "AGENTCTL_ASSUME_YES": "true",
        "HOME": str(tmp_path),
        "USERPROFILE": str(tmp_path),
        "LOCALAPPDATA": str(tmp_path / "local"),
        "XDG_CACHE_HOME": str(tmp_path / "cache"),
        "XDG_DATA_HOME": str(tmp_path / "data"),
        "XDG_STATE_HOME": str(tmp_path / "state"),
    }
    for global_options, expected in (((), False), (("--assume-yes",), True)):
        tail = ("claude", "--", "--assume-yes", "")
        observed = run(
            [sys.executable, "-c", program, str(probe.value), *global_options, *tail],
            cwd=tmp_path,
            env=environment,
        )
        assert isinstance(observed, Ok), observed
        assert observed.value.code == 0, observed.value.stderr
        assert json.loads(observed.value.stdout) == {
            "handshake": {"protocol": 2, "commands": []},
            "arguments": list(tail),
            "consent": expected,
            "nonce": nonce,
        }, "global consent did not reach native receiver separately"
