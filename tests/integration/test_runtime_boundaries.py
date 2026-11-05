# Copyright (c) 2026 agentctl contributors.
"""Real operating-system errors, owned children and file-lock contention."""

import json
import os
import platform
import shutil
import sys
import time
from pathlib import Path

import coverage
import pytest

from agentctl.check.legs import Leg
from agentctl.check.preconditions import inspect, single_run
from agentctl.check.steps import check, execute, run_leg, run_tools
from agentctl.paths import directories
from agentctl.process import alive, run, start, stop
from agentctl.result import Err, Ok

pytestmark = pytest.mark.evidence("real")
CONTROL_EXIT = 7


def test_process_errors_and_teardown(tmp_path: Path) -> None:
    """Actual missing executables, deadlines and undecodable bytes yield errors."""
    missing = [str(tmp_path / "missing-executable")]
    assert isinstance(run(missing, cwd=tmp_path, env=os.environ), Err)
    assert isinstance(start(missing, cwd=tmp_path, env=os.environ), Err)
    assert isinstance(
        run(
            [sys.executable, "-c", "import time; time.sleep(60)"],
            cwd=tmp_path,
            env=os.environ,
            timeout=0.01,
        ),
        Err,
    )
    assert isinstance(
        run(
            [sys.executable, "-c", "import os; os.write(1, bytes([255]))"],
            cwd=tmp_path,
            env=os.environ,
        ),
        Err,
    )
    family = platform.system()
    assert family in {"Linux", "Darwin", "Windows"}
    assert isinstance(alive(family, -1), Err)
    child = start(
        [sys.executable, "-c", "print('finished')"], cwd=tmp_path, env=os.environ
    )
    assert isinstance(child, Ok)
    deadline = time.monotonic() + 10
    while child.value.handle.poll() is None and time.monotonic() < deadline:
        time.sleep(0.01)
    assert child.value.handle.poll() == 0
    result = stop(child.value)
    assert isinstance(result, Ok)
    assert result.value.stdout == "finished\n"
    assert alive(family, child.value.pid) == Ok(value=False)


def test_owned_child_escalation(tmp_path: Path) -> None:
    """A POSIX child ignoring terminate is killed and reaped within the bound."""
    ready = tmp_path / "ready"
    script = (
        "import os, signal, sys, time\nfrom pathlib import Path\n"
        "if os.name != 'nt': signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
        "Path(sys.argv[1]).write_text('ready')\ntime.sleep(60)\n"
    )
    child = start(
        [sys.executable, "-c", script, str(ready)], cwd=tmp_path, env=os.environ
    )
    assert isinstance(child, Ok)
    try:
        deadline = time.monotonic() + 10
        while not ready.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert ready.read_text(encoding="utf-8") == "ready"
    finally:
        result = stop(child.value)
    assert isinstance(result, Ok)
    assert result.value.code != 0
    assert child.value.handle.poll() is not None


def test_owned_child_decoding_failure(tmp_path: Path) -> None:
    """Reap an owned child even when its raw output is invalid UTF-8."""
    ready = tmp_path / "ready"
    script = (
        "import os, sys, time\nfrom pathlib import Path\n"
        "os.write(1, bytes([255]))\n"
        "Path(sys.argv[1]).write_text('ready')\ntime.sleep(60)\n"
    )
    child = start(
        [sys.executable, "-c", script, str(ready)], cwd=tmp_path, env=os.environ
    )
    assert isinstance(child, Ok)
    try:
        deadline = time.monotonic() + 10
        while not ready.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert ready.read_text(encoding="utf-8") == "ready"
    finally:
        result = stop(child.value)
    assert isinstance(result, Err)
    assert child.value.handle.poll() is not None


def test_single_run_lock_releases(tmp_path: Path) -> None:
    """A competing real handle is refused, and scope exit releases the lock."""
    with single_run(tmp_path) as first:
        assert first == ()
        with single_run(tmp_path) as second:
            assert second
            assert second[0].startswith("P5:")
    with single_run(tmp_path) as after:
        assert after == ()


def test_preconditions_real_interpreters(root: Path, tmp_path: Path) -> None:
    """Observe the installed checkout and an interpreter with no site packages."""
    assert inspect(root) == ()
    before = tuple(
        (path.as_posix(), path.read_bytes())
        for path in sorted((root / "src").rglob("*.pyc"))
    )
    metadata = tmp_path / "agentctl-0.1.dist-info"
    metadata.mkdir()
    (metadata / "METADATA").write_text(
        "Name: agentctl\nVersion: 0.1\n", encoding="utf-8"
    )
    (metadata / "direct_url.json").write_text("invalid JSON", encoding="utf-8")
    instrument = tmp_path / "instrumentation"
    shutil.copytree(Path(coverage.__file__).parent, instrument / "coverage")
    script = (
        "import json, sys\nsys.dont_write_bytecode = True\nfrom pathlib import Path\n"
        "sys.path[:0] = [sys.argv[1], sys.argv[2], sys.argv[4]]\n"
        "import coverage\ncoverage.process_startup()\n"
        "from agentctl.check.preconditions import inspect\n"
        "from agentctl.check.writeguard import snapshot\n"
        "from agentctl.result import Err\n"
        "assert isinstance(snapshot(Path(sys.argv[3])), Err)\n"
        "print(json.dumps(inspect(Path(sys.argv[3]))))\n"
    )
    for search, env, expected in (
        (str(tmp_path), os.environ, {"P1", "P2"}),
        (str(tmp_path / "absent"), {**os.environ, "PATH": ""}, {"P1", "P2", "P4"}),
    ):
        result = run(
            [
                sys.executable,
                "-S",
                "-c",
                script,
                str(root / "src"),
                search,
                str(root),
                str(instrument),
            ],
            cwd=root,
            env={
                key: value
                for key, value in env.items()
                if key not in {"PYTHONPYCACHEPREFIX", "PYTHONDONTWRITEBYTECODE"}
            },
        )
        assert isinstance(result, Ok)
        assert result.value.code == 0, result.value.stderr
        problems = json.loads(result.value.stdout)
        assert {message.split(":", 1)[0] for message in problems} == expected
    assert any(problem.startswith("P4:") for problem in inspect(tmp_path))
    assert (
        tuple(
            (path.as_posix(), path.read_bytes())
            for path in sorted((root / "src").rglob("*.pyc"))
        )
        == before
    )


def test_leg_followups_and_failures(tmp_path: Path) -> None:
    """A failed command prevents followups; a successful chain executes each."""
    effect = tmp_path / "effect"
    write = (
        sys.executable,
        "-c",
        "from pathlib import Path; import sys; Path(sys.argv[1]).write_text('ran')",
        str(effect),
    )
    success = (sys.executable, "-c", "print('success')")
    assert run_leg(tmp_path, tmp_path, "nonce", Leg("probe", success, (write,))) == 0
    assert effect.read_text(encoding="utf-8") == "ran"
    effect.unlink()
    assert (
        run_leg(
            tmp_path,
            tmp_path,
            "nonce",
            Leg("probe", (sys.executable, "-c", "raise SystemExit(7)"), (write,)),
        )
        == CONTROL_EXIT
    )
    assert not effect.exists()
    assert run_tools(tmp_path, tmp_path, "nonce", (Leg("positive", success),)) == 0
    assert run_tools(tmp_path, tmp_path, "nonce", ()) == 1
    assert (
        run_tools(
            tmp_path,
            tmp_path,
            "nonce",
            (Leg("failed", (str(tmp_path / "missing"),)), Leg("unrun", write)),
        )
        == 1
    )
    assert not effect.exists()


def test_check_command_failure_paths(tmp_path: Path) -> None:
    """Report real identity, lock and temporary-root failures at the public entry."""
    family = platform.system()
    assert family in {"Linux", "Darwin", "Windows"}
    assert check("unsupported-host") == 1
    env = {**os.environ, "XDG_STATE_HOME": str(tmp_path / "state")}
    program = "from agentctl.cli import main; main(['check'])"
    result = run([sys.executable, "-c", program], cwd=tmp_path, env=env)
    assert isinstance(result, Ok)
    assert result.value.code == 1
    assert "P1:" in result.value.stdout + result.value.stderr
    assert execute(tmp_path, tmp_path, "nonce", family) == 1
    state = directories(family, env, Path.home()).state
    with single_run(state) as locked:
        assert locked == ()
        result = run([sys.executable, "-c", program], cwd=tmp_path, env=env)
        assert isinstance(result, Ok)
        assert result.value.code == 1
        assert "P5:" in result.value.stdout + result.value.stderr
    result = run(
        [sys.executable, "-c", program],
        cwd=tmp_path,
        env={**env, **dict.fromkeys(("TMPDIR", "TEMP", "TMP"), str(tmp_path))},
    )
    assert isinstance(result, Ok)
    assert result.value.code == 1
    assert "Set TMPDIR outside" in result.value.stderr
    veto = (
        "import sys\n"
        "def observe(event, values):\n"
        "    if event == 'subprocess.Popen': raise OSError('owned outer veto')\n"
        "sys.addaudithook(observe)\n" + program
    )
    result = run([sys.executable, "-c", veto], cwd=tmp_path, env=env)
    assert isinstance(result, Ok)
    assert result.value.code == 1
    assert "owned outer veto" in result.value.stderr
