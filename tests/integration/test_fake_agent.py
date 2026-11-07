# Copyright (c) 2026 agentctl contributors.
"""Native observer identity, literal argv and non-secret environment-key records."""

import json
from pathlib import Path

import pytest

from agentctl.bootstrap import build
from agentctl.process import finish, stop
from agentctl.result import Ok
from tests.harness.nonce import fresh
from tests.harness.tmux import object_value, validate_record

pytestmark = pytest.mark.evidence("observer")
EXIT_STATUS = 3


def test_record_carries_nonce(
    haskell_build: build.BuildContext, tmp_path: Path
) -> None:
    """The actual process records its pid and nonce; missing/replayed rows fail."""
    records = tmp_path / "records"
    records.mkdir(mode=0o700)
    nonce = fresh("fake-direct")
    arguments = ("x;", "", "one\ntwo", "--agentctl-observer-nonce", nonce)
    child = build.start_binary(
        haskell_build,
        build.BinaryCall(
            "exe:agentctl-fake-agent",
            arguments,
            protocol=None,
            settings=(
                ("AGENTCTL_FAKE_RECORD_DIR", str(records)),
                ("AGENTCTL_FAKE_EXIT", "3"),
                ("OBSERVER_VALUE", "private-fixture-value"),
            ),
        ),
    )
    assert isinstance(child, Ok), child
    try:
        completed = finish(child.value, timeout=10)
        assert isinstance(completed, Ok), completed
        stdout, stderr = completed.value.stdout, completed.value.stderr
        assert child.value.handle.returncode == EXIT_STATUS, stderr
        assert stdout == "ready:" + nonce + "\n"
        assert not stderr
        files = tuple(records.glob("*.json"))
        assert len(files) == 1
        raw = files[0].read_text(encoding="utf-8")
        value = object_value(raw)
        validate_record(value, nonce)
        assert value["pid"] == child.value.pid
        assert value["argv"] == list(arguments)
        assert Path(str(value["cwd"])).resolve() == haskell_build.project.resolve()
        assert value["session"] is None
        assert value["pane"] is None
        keys = value["env_keys"]
        assert isinstance(keys, list)
        assert "OBSERVER_VALUE" in keys
        assert "private-fixture-value" not in raw
        missing = dict(value)
        del missing["nonce"]
        for invalid in (missing, {**value, "nonce": "replayed"}):
            with pytest.raises(AssertionError, match="fake record dropped nonce"):
                validate_record(invalid, nonce)
        assert json.loads(raw)["nonce"] == nonce
    finally:
        assert isinstance(stop(child.value), Ok)
