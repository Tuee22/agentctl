# Copyright (c) 2026 agentctl contributors.
"""Native host qualification and an opaque session-name compiler boundary."""

import json
import os
import platform
import shutil
from pathlib import Path

import pytest

from agentctl.bootstrap import build
from agentctl.check.preconditions import inspect_socket, socket_path_length
from agentctl.process import run
from agentctl.result import Err, Ok
from tests.harness.haskell import copy_project
from tests.harness.host import multiplexer
from tests.harness.nonce import fresh

pytestmark = pytest.mark.evidence("real")


def test_socket_directory_inspection(tmp_path: Path) -> None:
    """Native ownership determines the Unix path; unreadable directories refuse."""
    assert inspect_socket(tmp_path, "Windows") == ()
    path = (
        tmp_path.resolve() / "mux/00000000" / f"tmux-{tmp_path.stat().st_uid}/default"
    )
    nested = tmp_path / "nested"
    nested.mkdir()
    for family in ("Linux", "Darwin"):
        assert inspect_socket(tmp_path, family) == socket_path_length(path)
        assert inspect_socket(nested / "..", family) == socket_path_length(path)
        assert inspect_socket(tmp_path / "absent", family)[0].startswith("P6:")


def test_host_probe_and_constructed_absence(tmp_path: Path) -> None:
    """A native version probe qualifies while the same owned PATH without it refuses."""
    family = platform.system()
    assert family in {"Linux", "Darwin", "Windows"}
    name = "psmux.exe" if family == "Windows" else "tmux"
    original = shutil.which(name)
    assert original is not None
    owned_bin = tmp_path / "bin"
    owned_bin.mkdir()
    environment = {**os.environ, "PATH": str(owned_bin)}
    nonce = fresh(os.environ.get("AGENTCTL_CHECK_NONCE", "focused"))
    folder = tmp_path / "observation"
    assert not multiplexer(family, folder, nonce, environment)
    absent: object = json.loads((folder / "mux-host.json").read_text(encoding="utf-8"))
    assert isinstance(absent, dict)
    assert absent["nonce"] == nonce
    assert absent["met"] is False
    assert absent["executable"] is None
    shutil.copy2(original, owned_bin / name)
    assert multiplexer(family, folder, nonce, environment)
    payload: object = json.loads((folder / "mux-host.json").read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    assert payload["nonce"] == nonce
    assert payload["met"] is True
    assert payload["executable"] == str(owned_bin / name)
    answer = run(
        [str(owned_bin / name), "-V"],
        cwd=folder,
        env={
            **environment,
            "PSMUX_DATA_DIR": str(folder / "psmux-control"),
            "PSMUX_NO_WARM": "1",
            "HOME": str(folder / "home"),
            "USERPROFILE": str(folder / "home"),
        },
    )
    assert isinstance(answer, Ok)
    assert answer.value.code == 0
    assert payload["version"] == answer.value.stdout.strip()


def test_session_name_constructor_is_private(root: Path, tmp_path: Path) -> None:
    """A checked-name caller compiles; a constructor caller fails as specified."""
    context = copy_project(root, tmp_path)
    cabal = context.project / "agentctl-core.cabal"
    cabal.write_text(
        cabal.read_text(encoding="utf-8").replace(
            "exposed-modules: ", "exposed-modules: AgentCtl.NameWitness, ", 1
        ),
        encoding="utf-8",
    )
    witness = context.project / "src/AgentCtl/NameWitness.hs"
    legal = (
        "module AgentCtl.NameWitness (witness) where\n"
        "import AgentCtl.Session.Name\n"
        "witness :: Either NameError SessionName\n"
        'witness = makeSessionName "good"\n'
    )
    witness.write_text(legal, encoding="utf-8")
    compiled = build.compile_project(context)
    assert isinstance(compiled, Ok), compiled
    witness.write_text(
        legal.replace('makeSessionName "good"', 'Right (SessionName "bad")'),
        encoding="utf-8",
    )
    refused = build.compile_project(context)
    assert isinstance(refused, Err), "SessionName constructor escaped"
    assert "GHC-01928" in refused.error.message, refused.error.message
    assert "Illegal term-level use" in refused.error.message
    assert "SessionName" in refused.error.message
