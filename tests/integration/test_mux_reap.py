# Copyright (c) 2026 agentctl contributors.
"""Native child notification is scoped by observed, validated process identity."""

import json
import os
import shutil
import sys
import time
from pathlib import Path

import pytest

from agentctl.bootstrap import build
from agentctl.process import Output, alive, run
from agentctl.result import Ok
from tests.harness.haskell_fixtures import haskell_build as _haskell_build_fixture
from tests.harness.isolation import isolated_environment
from tests.harness.nonce import fresh
from tests.harness.tmux import PrivateMux, object_value, validate_record
from tests.harness.tmux_fixtures import mux_server as _mux_server_fixture

haskell_build = _haskell_build_fixture
mux_server = _mux_server_fixture

pytestmark = pytest.mark.evidence("observer")
WAIT_SECONDS = 10
INVALID_PIDS = ("", "0\n", "-1\n", "abc\n", "1 2\n", "2147483648\n")


def _relay(mux: PrivateMux) -> tuple[dict[str, str], Path, str]:
    """Prepare a nonce-bound native relay without an agent-launch fixture."""
    nonce = fresh(mux.nonce)
    directory = mux.scope / ("reap-relay-" + nonce.rsplit(".", maxsplit=1)[-1])
    directory.mkdir(mode=0o700)
    binaries = directory / "bin"
    binaries.mkdir(mode=0o700)
    records = directory / "records"
    records.mkdir(mode=0o700)
    name = "psmux.exe" if mux.family == "Windows" else "tmux"
    backend = directory / name
    shutil.copy2(mux.executable, backend)
    fake = build.binary(mux.context, "exe:agentctl-fake-agent")
    assert isinstance(fake, Ok), fake
    shutil.copy2(fake.value, binaries / name)
    environment = {
        **isolated_environment(directory / "isolation", mux.environment),
        "PATH": str(binaries),
        "PATHEXT": os.pathsep.join((".EXE", ".CMD", ".BAT")),
        "TMUX_TMPDIR": str(mux.scope),
        "PSMUX_DATA_DIR": str(mux.endpoint),
        "AGENTCTL_FAKE_NONCE": nonce,
        "AGENTCTL_FAKE_MUX_EXECUTABLE": str(backend),
        "AGENTCTL_FAKE_MUX_RECORD_DIR": str(records),
    }
    return environment, records, nonce


def _arguments(mux: PrivateMux, directory: Path, nonce: str) -> list[list[str]]:
    """Validate and register each relay invocation before inspecting its argv."""
    invocations: list[list[str]] = []
    for path in sorted(directory.glob("*.json")):
        record = object_value(path.read_text(encoding="utf-8"))
        validate_record(record, nonce)
        pid = record["pid"]
        assert isinstance(pid, int)
        mux.register_observer(pid)
        arguments = record["argv"]
        assert isinstance(arguments, list)
        assert all(isinstance(argument, str) for argument in arguments)
        invocations.append([str(argument) for argument in arguments])
    return invocations


def _request(mux: PrivateMux, environment: dict[str, str]) -> Output:
    """Invoke the production request with a controlled native client response."""
    result = build.execute_binary(
        mux.context,
        build.BinaryCall(
            "test:agentctl-core-test",
            ("--mux-fixture",),
            input_text=json.dumps(
                {"operation": "request-reap", "directory": str(mux.scope)}
            ),
            settings=tuple(environment.items()),
        ),
    )
    assert isinstance(result, Ok), result
    return result.value


def test_reap_observer_imports_without_launch(root: Path) -> None:
    """Import this observer with the later launch helper actively vetoed."""
    program = (
        "import sys\n"
        "def observe(event, args):\n"
        "    if event == 'import' and args[0] == 'tests.harness.launch':\n"
        "        raise RuntimeError('later launch vetoed')\n"
        "sys.addaudithook(observe)\n"
        "try:\n"
        "    import tests.harness.launch\n"
        "except RuntimeError as error:\n"
        "    assert str(error) == 'later launch vetoed'\n"
        "else:\n"
        "    raise AssertionError('launch veto did not fire')\n"
        "import tests.integration.test_mux_reap\n"
    )
    result = run(
        [sys.executable, "-c", program],
        cwd=root,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    assert isinstance(result, Ok), result
    assert result.value.code == 0, result.value.stderr


def test_reap_request_validates_pid_before_notification(mux_server: PrivateMux) -> None:
    """Malformed identities cannot notify; a valid owned pid receives SIGCHLD."""
    actor = mux_server.actor("reap-observer", disposition="observe-reap")
    record = actor.record()
    pid = record["pid"]
    assert isinstance(pid, int)
    environment, records, nonce = _relay(mux_server)
    marker = actor.record_directory / "reaped"
    for raw in INVALID_PIDS:
        output = _request(
            mux_server,
            {**environment, "AGENTCTL_FAKE_MUX_PID_RESPONSE": raw},
        )
        if mux_server.family == "Windows":
            assert output.code == 0, output
        else:
            assert output.code != 0, "malformed server identity was accepted"
            assert "InvalidServerIdentity" in output.stdout, output
        assert not marker.exists(), "invalid identity sent child notification"
    positive = _request(
        mux_server,
        {**environment, "AGENTCTL_FAKE_MUX_PID_RESPONSE": str(pid)},
    )
    assert positive.code == 0, positive
    assert json.loads(positive.stdout) == {"code": 0}
    family = mux_server.family
    assert family in {"Linux", "Darwin", "Windows"}
    assert alive(family, pid) == Ok(value=True)
    if family == "Windows":
        assert not marker.exists(), "psmux sent an unnecessary child notification"
    else:
        deadline = time.monotonic() + WAIT_SECONDS
        while not marker.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert marker.read_text(encoding="utf-8") == actor.nonce, (
            "valid owned pid did not receive child notification"
        )
    invocations = _arguments(mux_server, records, nonce)
    assert ["-V"] in invocations, "native relay observer saw no version probe"
    queries = invocations.count(["list-sessions", "-F", "#{pid}"])
    assert queries == (0 if family == "Windows" else len(INVALID_PIDS) + 1)
