# Copyright (c) 2026 agentctl contributors.
"""Independent host multiplexer qualification observes actual private probes."""

import json
import os
import platform
import shutil
from pathlib import Path

import pytest

from agentctl.process import run
from agentctl.result import Ok
from tests.harness.host import multiplexer
from tests.harness.nonce import fresh

pytestmark = pytest.mark.evidence("real")


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
