# Copyright (c) 2026 agentctl contributors.
"""Real operating-system errors, owned children and file-lock contention."""

import hashlib
import json
import os
import platform
import secrets
import shutil
import sys
import time
from dataclasses import replace
from pathlib import Path

import coverage
import pytest

from agentctl import foundation_process, process
from agentctl.check import mutant_report, steps
from agentctl.check.evidence import Entry, read_legs, source_census
from agentctl.check.legs import Leg
from agentctl.check.ownership import (
    _guard_links,
    census_link_targets_match_guard,
    census_matches_guard,
    guarded_census,
)
from agentctl.check.phase_reports import (
    ArtifactOwnership,
    OwnershipPhase,
    ownership_inputs,
)
from agentctl.check.preconditions import inspect, single_run
from agentctl.check.steps import (
    CheckRun,
    _run_check_child,
    _run_tools_observed,
    check,
    cleanup_run_root,
    execute,
    host_observation_unchanged,
    pytest_manifest_unchanged,
    retain_gate_output,
    retain_handoff_failure,
    run_leg,
    run_tools,
    tool_outcomes_unchanged,
    tool_substeps_unchanged,
    verify_finalizer_handoff,
)
from agentctl.check.writeguard import filesystem_path, tree
from agentctl.foundation import Family
from agentctl.foundation_process_values import (
    ByteOutput,
    ProcessObservation,
    SpawnError,
)
from agentctl.foundation_process_values import Output as FoundationOutput
from agentctl.paths import directories
from agentctl.process import (
    Output,
    alive,
    finish,
    process_birth,
    run,
    start,
    start_protocol,
    stop,
)
from agentctl.result import Err, Ok, Result

pytestmark = pytest.mark.evidence("real")


def test_gate_child_process_observed_before_release(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Observe the live child before its own nonce protocol is released."""
    family = platform.system()
    assert family in {"Linux", "Darwin", "Windows"}
    marker = tmp_path / "released"
    nonce = secrets.token_hex(16)
    command = (
        "import sys; from pathlib import Path; "
        "value = sys.stdin.readline().strip(); "
        "Path(sys.argv[1]).write_text(value, encoding='utf-8'); print(value)"
    )
    original = foundation_process.native_process_image

    def observed_before_release(
        native_family: Family, pid: int
    ) -> Result[ProcessObservation, SpawnError]:
        assert not marker.exists(), "child ran before its image was observed"
        assert native_family in {"Linux", "Darwin", "Windows"}
        return original(native_family, pid)

    monkeypatch.setattr(
        foundation_process, "native_process_image", observed_before_release
    )
    request = foundation_process.ObservationRequest(family, nonce + "\n", 10)
    result = foundation_process.run_observed(
        [sys.executable, "-c", command, str(marker)],
        cwd=tmp_path,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        request=request,
    )
    assert isinstance(result, Ok), result
    assert result.value.code == 0
    assert result.value.stdout.strip() == nonce
    assert marker.read_text(encoding="utf-8") == nonce
    if family == "Darwin":
        assert isinstance(result.value.observation, Err), (
            "unavailable native process image was accepted"
        )
    else:
        assert isinstance(result.value.observation, Ok), (
            "native child image observation missing"
        )
        image = result.value.observation.value
        assert image.family == family
        assert image.pid != os.getpid()
        assert image.birth > 0
        assert image.file is not None, "live child image file was not observed"
        assert image.file.sha256 == hashlib.sha256(image.image.read_bytes()).hexdigest()
        expected = (Path(sys.executable), Path(sys.base_prefix) / "python.exe")
        assert any(image.image.samefile(path) for path in expected if path.is_file())
        assert isinstance(original(family, image.pid), Err), "exited child was accepted"
    _assert_observer_refusal_keeps_child_output(tmp_path, family, monkeypatch)


def _assert_observer_refusal_keeps_child_output(
    tmp_path: Path, family: Family, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Keep child execution when its image observation is unavailable."""
    monkeypatch.setattr(
        foundation_process,
        "native_process_image",
        lambda *_args: Err(SpawnError("owned image observer refusal")),
    )
    request = foundation_process.ObservationRequest(family, "release\n", 10)
    result = foundation_process.run_observed(
        [sys.executable, "-c", "import sys; print(sys.stdin.readline().strip())"],
        cwd=tmp_path,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        request=request,
    )
    assert isinstance(result, Ok), result
    assert result.value.code == 0
    assert result.value.stdout.strip() == "release", "observer failure skipped child"
    assert result.value.observation == Err(SpawnError("owned image observer refusal"))


def test_observed_child_timeout_preserves_output_and_reaps(tmp_path: Path) -> None:
    """A timed-out owned child is reaped and its primary output is retained."""
    family = platform.system()
    assert family in {"Linux", "Darwin", "Windows"}
    request = foundation_process.ObservationRequest(family, "release\n", 1)
    result = foundation_process.run_observed(
        [
            sys.executable,
            "-c",
            (
                "import sys,time; sys.stdin.readline(); print('started', flush=True); "
                "time.sleep(60)"
            ),
        ],
        cwd=tmp_path,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        request=request,
    )
    assert isinstance(result, Ok), result
    assert result.value.code == 1, "timed-out child was accepted"
    assert "started" in result.value.stdout
    assert "process failure:" in result.value.stderr
    if isinstance(result.value.observation, Ok):
        assert isinstance(
            foundation_process.native_process_image(
                family, result.value.observation.value.pid
            ),
            Err,
        ), "timed-out child was not reaped"


def test_live_linux_image_replacement_is_refused(tmp_path: Path) -> None:
    """A replaced path cannot stand in for a running Linux image mapping."""
    if sys.platform != "linux":
        assert isinstance(
            foundation_process.native_process_image("Linux", os.getpid()), Err
        )
        return
    shell = shutil.which("sh")
    assert shell is not None
    image = tmp_path / "owned-shell"
    replacement = tmp_path / "replacement"
    shutil.copy2(shell, image)
    shutil.copy2(shell, replacement)
    started = start_protocol(
        [str(image), "-c", "read value; printf '%s' \"$value\""],
        cwd=tmp_path,
        env=dict(os.environ),
    )
    assert isinstance(started, Ok)
    try:
        assert isinstance(
            foundation_process.native_process_image("Linux", started.value.pid), Ok
        )
        replacement.replace(image)
        assert isinstance(
            foundation_process.native_process_image("Linux", started.value.pid), Err
        ), "replaced live process image was accepted"
    finally:
        finished = foundation_process.finish(
            started.value, timeout=10, input_text="release\n"
        )
        if isinstance(finished, Err):
            cleaned = stop(started.value)
            assert isinstance(cleaned, Ok), (finished, cleaned)
    assert isinstance(finished, Ok)
    assert finished.value.stdout == "release"


def test_invalid_process_arguments_return_typed_failures(tmp_path: Path) -> None:
    """Invalid OS arguments cannot escape the shared process boundary."""
    argv = [sys.executable, "\x00"]
    env = dict(os.environ)
    operations = (
        lambda: process.run(argv, cwd=tmp_path, env=env),
        lambda: process.run_bytes(argv, cwd=tmp_path, env=env),
        lambda: process.start(argv, cwd=tmp_path, env=env),
        lambda: process.start_protocol(argv, cwd=tmp_path, env=env),
        lambda: process.foreground(argv, cwd=tmp_path, env=env),
        lambda: process.replace(["\x00"], env=env),
        lambda: process.replace([], env=env),
    )
    for operation in operations:
        try:
            result = operation()
        except (ValueError, IndexError):
            pytest.fail("invalid process arguments escaped typed failure")
        assert isinstance(result, Err), "invalid process arguments were accepted"


def test_mutant_report_file_identity(tmp_path: Path) -> None:
    """Read real report bytes and refuse a hard-linked or changed file."""
    path = tmp_path / "mutant-killers.json"
    path.write_text('{"nonce":"current","records":[]}', encoding="utf-8")
    first = mutant_report.read(path, "current")
    assert isinstance(first, Ok), first
    alias = tmp_path / "alias"
    os.link(path, alias)
    try:
        assert isinstance(mutant_report.read(path, "current"), Err), (
            "hardlinked mutant report accepted"
        )
    finally:
        alias.unlink()
    path.write_text('{ "nonce":"current","records":[]}', encoding="utf-8")
    second = mutant_report.read(path, "current")
    assert isinstance(second, Ok), second
    assert first.value.digest != second.value.digest, (
        "changed mutant report bytes ignored"
    )


def test_process_boundary_reexports_foundation_values() -> None:
    """Existing callers and the earlier gate share exactly the same value types."""
    assert process.Output is FoundationOutput
    assert process.ByteOutput is ByteOutput
    assert process.SpawnError is SpawnError


def test_process_identity_loads_without_later_spawner(tmp_path: Path) -> None:
    """A real fresh process observes itself before the later adapter is imported."""
    script = (
        "import os, platform, sys\n"
        "from agentctl.foundation import Ok\n"
        "from agentctl.foundation_process_identity import alive, process_birth\n"
        "assert 'agentctl.process' not in sys.modules\n"
        "family = platform.system()\n"
        "assert isinstance(alive(family, os.getpid()), Ok)\n"
        "assert alive(family, os.getpid()).value is True\n"
        "if family in ('Windows', 'Linux'):\n"
        "    assert isinstance(process_birth(family, os.getpid()), Ok)\n"
        "    assert process_birth(family, os.getpid()).value > 0\n"
        "assert 'agentctl.process' not in sys.modules\n"
        "from agentctl import process\n"
        "assert (process.alive, process.process_birth) == (alive, process_birth)\n"
    )
    environment = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    result = run([sys.executable, "-c", script], cwd=tmp_path, env=environment)
    assert isinstance(result, Ok), result
    assert result.value.code == 0, result.value.stderr


def test_process_boundary_operates_without_later_product_modules(
    tmp_path: Path,
) -> None:
    """A fresh process starts and reaps children with later imports refused."""
    script = (
        "import importlib.abc, os, sys\n"
        "from pathlib import Path\n"
        "blocked = ('agentctl.bootstrap', 'agentctl.cli', 'agentctl.hostfacts', "
        "'agentctl.paths', 'agentctl.process')\n"
        "class Refuse(importlib.abc.MetaPathFinder):\n"
        "    def find_spec(self, fullname, path=None, target=None):\n"
        "        if any(fullname == name or fullname.startswith(name + '.') "
        "for name in blocked):\n"
        "            raise ImportError('later module unavailable: ' + fullname)\n"
        "        return None\n"
        "sys.meta_path.insert(0, Refuse())\n"
        "from agentctl.foundation import Ok\n"
        "from agentctl.foundation_process import run, start_protocol, finish, stop\n"
        "args = [sys.executable, '-c', 'import sys; print(sys.stdin.read())']\n"
        "direct = run(args, cwd=Path.cwd(), env=os.environ, input_text='direct')\n"
        "assert isinstance(direct, Ok) and direct.value.stdout.strip() == 'direct'\n"
        "child = start_protocol(args, cwd=Path.cwd(), env=os.environ)\n"
        "assert isinstance(child, Ok), child\n"
        "try:\n"
        "    finished = finish(child.value, input_text='held')\n"
        "    assert isinstance(finished, Ok)\n"
        "    assert finished.value.stdout.strip() == 'held'\n"
        "finally:\n"
        "    assert isinstance(stop(child.value), Ok)\n"
        "assert not any(name in sys.modules for name in blocked)\n"
    )
    environment = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    result = run([sys.executable, "-c", script], cwd=tmp_path, env=environment)
    assert isinstance(result, Ok), result
    assert result.value.code == 0, result.value.stderr


def test_python_mutant_census_without_native_bootstrap(
    root: Path, tmp_path: Path
) -> None:
    """Read the actual mutation corpus while later native modules are unavailable."""
    script = (
        "import importlib.abc, sys\n"
        "from pathlib import Path\n"
        "blocked = ('agentctl.bootstrap', 'agentctl.hostfacts', 'agentctl.process')\n"
        "class Refuse(importlib.abc.MetaPathFinder):\n"
        "    def find_spec(self, fullname, path=None, target=None):\n"
        "        if any(fullname == name or fullname.startswith(name + '.') "
        "for name in blocked):\n"
        "            raise ImportError('later module unavailable: ' + fullname)\n"
        "        return None\n"
        "sys.meta_path.insert(0, Refuse())\n"
        "from agentctl.check.mutants import corpus\n"
        "from agentctl.foundation import Ok\n"
        "result = corpus(Path(sys.argv[1]))\n"
        "assert isinstance(result, Ok), result\n"
        "assert any(item.identifier == 'M-guard-process-allowlist-wide' "
        "for item in result.value)\n"
        "assert not any(name in sys.modules for name in blocked)\n"
    )
    result = run(
        [sys.executable, "-c", script, str(root)],
        cwd=tmp_path,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    assert isinstance(result, Ok), result
    assert result.value.code == 0, result.value.stderr


def test_leg_value_controls_without_later_modules(root: Path, tmp_path: Path) -> None:
    """Execute existing leg controls when later modules fail to import."""
    script = (
        "import importlib.abc, sys\n"
        "from pathlib import Path\n"
        "sys.path.insert(0, sys.argv[2])\n"
        "blocked = ('agentctl.bootstrap', 'agentctl.check.steps', "
        "'agentctl.result', 'agentctl.paths', 'tests.harness.bootstrap')\n"
        "class Refuse(importlib.abc.MetaPathFinder):\n"
        "    def find_spec(self, fullname, path=None, target=None):\n"
        "        if any(fullname == name or fullname.startswith(name + '.') "
        "for name in blocked):\n"
        "            raise ImportError('later module unavailable: ' + fullname)\n"
        "        return None\n"
        "sys.meta_path.insert(0, Refuse())\n"
        "from tests.unit.test_check_legs import test_empty_target_set_fails, "
        "test_python_leg_table_matches_oracle, "
        "test_failing_leg_fails_check\n"
        "test_failing_leg_fails_check()\n"
        "test_python_leg_table_matches_oracle(Path(sys.argv[2]))\n"
        "test_empty_target_set_fails(Path(sys.argv[1]))\n"
        "assert not any(name in sys.modules for name in blocked)\n"
    )
    result = run(
        [sys.executable, "-c", script, str(tmp_path), str(root)],
        cwd=tmp_path,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    assert isinstance(result, Ok), result
    assert result.value.code == 0, result.value.stderr


def test_pin_values_without_later_adapters(tmp_path: Path) -> None:
    """Use the gate's pin selection with later path and bootstrap modules refused."""
    script = (
        "import importlib.abc, sys\n"
        "blocked = ('agentctl.paths', 'agentctl.bootstrap')\n"
        "class Refuse(importlib.abc.MetaPathFinder):\n"
        "    def find_spec(self, fullname, path=None, target=None):\n"
        "        if any(fullname == name or fullname.startswith(name + '.') "
        "for name in blocked):\n"
        "            raise ImportError('later adapter unavailable: ' + fullname)\n"
        "        return None\n"
        "sys.meta_path.insert(0, Refuse())\n"
        "from agentctl.check.preconditions import asset_for\n"
        "from agentctl.pin_values import Asset, Pins, Version\n"
        "v = Version((1, 2, 3))\n"
        "asset = Asset('Linux', 'x86_64', 'https://example.invalid/a', 'a' * 64)\n"
        "pins = Pins(v, v, v, v, (asset,), v, v, v)\n"
        "assert asset_for(pins, 'Linux', 'x86_64') == asset\n"
        "assert asset_for(pins, 'Windows', 'x86_64') is None\n"
        "assert not any(name in sys.modules for name in blocked)\n"
    )
    result = run(
        [sys.executable, "-c", script],
        cwd=tmp_path,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    assert isinstance(result, Ok), result
    assert result.value.code == 0, result.value.stderr


def test_leg_values_without_native_bootstrap(tmp_path: Path) -> None:
    """Construct real gate leg values without importing the bootstrap adapter."""
    script = (
        "import importlib.abc, sys\n"
        "from pathlib import Path\n"
        "class Refuse(importlib.abc.MetaPathFinder):\n"
        "    def find_spec(self, fullname, path=None, target=None):\n"
        "        if fullname == 'agentctl.bootstrap' or "
        "fullname.startswith('agentctl.bootstrap.'):\n"
        "            raise ImportError('later bootstrap unavailable: ' + fullname)\n"
        "        return None\n"
        "sys.meta_path.insert(0, Refuse())\n"
        "from agentctl.check.legs import style_legs\n"
        "from agentctl.foundation_style_values import StyleTools\n"
        "tools = StyleTools(Path('fourmolu'), Path('hlint'))\n"
        "legs = style_legs(tools, ('source.hs',))\n"
        "assert tuple(item.name for item in legs) == ('fourmolu', 'hlint')\n"
        "assert 'source.hs' in legs[0].argv\n"
        "assert legs[1].argv[1:] == ('app', 'bootstrap-src', 'src', 'test')\n"
        "assert 'agentctl.bootstrap' not in sys.modules\n"
    )
    result = run(
        [sys.executable, "-c", script],
        cwd=tmp_path,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    assert isinstance(result, Ok), result
    assert result.value.code == 0, result.value.stderr


def test_foundation_result_compatibility(tmp_path: Path) -> None:
    """The shared values load independently and retain their existing identities."""
    script = (
        "import sys\n"
        "from agentctl.foundation_process_values "
        "import ByteOutput, Output, SpawnError\n"
        "assert 'agentctl.process' not in sys.modules\n"
        "from agentctl.foundation import Err, Family, Ok, Result\n"
        "assert 'agentctl.result' not in sys.modules\n"
        "assert 'agentctl.paths' not in sys.modules\n"
        "from agentctl.foundation_host import HostContext, current, effective_root\n"
        "assert 'agentctl.hostfacts' not in sys.modules\n"
        "from agentctl.foundation_paths import Paths, directories\n"
        "assert 'agentctl.paths' not in sys.modules\n"
        "from agentctl import hostfacts, process, result\n"
        "assert (ByteOutput, Output, SpawnError) == "
        "(process.ByteOutput, process.Output, process.SpawnError)\n"
        "from agentctl import paths\n"
        "assert (HostContext, current, effective_root) == "
        "(hostfacts.HostContext, hostfacts.current, hostfacts.effective_root)\n"
        "namespace = {}\n"
        "exec('from agentctl.hostfacts import *', namespace)\n"
        "assert namespace['HostFacts'] is hostfacts.HostFacts\n"
        "assert namespace['gather'] is hostfacts.gather\n"
        "assert (Err, Ok, Result) == (result.Err, result.Ok, result.Result)\n"
        "assert (Family, Paths, directories) == "
        "(paths.Family, paths.Paths, paths.directories)\n"
        "assert isinstance(result.Ok(1), Ok)\n"
    )
    environment = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    observed = run([sys.executable, "-c", script], cwd=tmp_path, env=environment)
    assert isinstance(observed, Ok)
    assert observed.value.code == 0, (
        "foundation process values depend on later adapter: " + observed.value.stderr
    )


def test_protocol_child_waits_for_owned_input(tmp_path: Path) -> None:
    """An independently observed child receives input only when released."""
    marker = tmp_path / "received"
    script = (
        "import sys\nfrom pathlib import Path\n"
        "text = sys.stdin.read()\n"
        "Path(sys.argv[1]).write_text(text, encoding='utf-8')\n"
        "print(text)\n"
    )
    started = start_protocol(
        [sys.executable, "-c", script, str(marker)], cwd=tmp_path, env=os.environ
    )
    assert isinstance(started, Ok), started
    try:
        family = platform.system()
        assert family in {"Linux", "Darwin", "Windows"}
        birth = (
            Ok(None) if family == "Darwin" else process_birth(family, started.value.pid)
        )
        assert isinstance(birth, Ok), birth
        nonce = secrets.token_hex(16)
        registry = tmp_path / "observer.json"
        registry.write_text(
            json.dumps(
                {"nonce": nonce, "pid": started.value.pid, "birth": birth.value}
            ),
            encoding="utf-8",
        )
        assert started.value.handle.poll() is None
        assert not marker.exists(), "protocol input was released before observation"
        completed = finish(started.value, timeout=10, input_text="fresh nonce")
        assert isinstance(completed, Ok), completed
        assert completed.value.code == 0
        assert completed.value.stdout.strip() == "fresh nonce"
        assert marker.read_text(encoding="utf-8") == "fresh nonce"
        assert isinstance(finish(started.value, input_text="again"), Err)
    finally:
        assert isinstance(stop(started.value), Ok)


def test_host_fixture_rejects_mutated_observation(root: Path, tmp_path: Path) -> None:
    """A real nested pytest session notices a changed host record at teardown."""
    (tmp_path / "conftest.py").write_text(
        "import os, pytest\nfrom pathlib import Path\n"
        "@pytest.fixture(scope='session')\n"
        "def root(): return Path(os.environ['AGENTCTL_TEST_ROOT'])\n",
        encoding="utf-8",
    )
    test = tmp_path / "test_host_record.py"
    test.write_text(
        "import json, os\nfrom pathlib import Path\n"
        "def test_record():\n"
        "    if os.environ['AGENTCTL_TEST_TAMPER'] == 'yes':\n"
        "        folder = Path(os.environ['AGENTCTL_CHECK_MANIFEST']).parent\n"
        "        path = folder / 'host.json'\n"
        "        data = json.loads(path.read_text(encoding='utf-8'))\n"
        "        data['facts']['mux'] = not data['facts']['mux']\n"
        "        path.write_text(json.dumps(data), encoding='utf-8')\n",
        encoding="utf-8",
    )
    common = {
        **os.environ,
        "AGENTCTL_TEST_ROOT": str(root),
        "AGENTCTL_CHECK_NONCE": "owned-host-observation",
        "AGENTCTL_CHECK_MANIFEST": str(tmp_path / "manifest.json"),
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPATH": os.pathsep.join((str(root / "src"), str(root))),
    }
    argv = [
        sys.executable,
        "-m",
        "pytest",
        "-p",
        "no:cacheprovider",
        "-p",
        "tests.harness.host",
        "-q",
        str(test),
    ]
    valid = run(argv, cwd=tmp_path, env={**common, "AGENTCTL_TEST_TAMPER": "no"})
    assert isinstance(valid, Ok)
    assert valid.value.code == 0, valid.value.stderr + valid.value.stdout
    changed = run(argv, cwd=tmp_path, env={**common, "AGENTCTL_TEST_TAMPER": "yes"})
    assert isinstance(changed, Ok)
    assert changed.value.code != 0, "changed host observation was accepted"
    assert "host observation changed during test execution" in changed.value.stdout


def test_host_observation_captured_before_followup(tmp_path: Path) -> None:
    """A later report process cannot replace the host facts seen after pytest."""
    path = tmp_path / "host.json"
    facts = {
        "family": "Linux",
        "architecture": "x86_64",
        "checkout": True,
        "git": True,
        "mux": False,
        "agents": False,
        "authenticated": False,
        "clean": False,
        "xcode": False,
        "debian": True,
    }
    writer = (
        "from pathlib import Path; import sys; "
        "Path(sys.argv[1]).write_text(sys.argv[2], encoding='utf-8')"
    )
    initial = {"nonce": "current", "facts": facts}
    changed = {"nonce": "current", "facts": {**facts, "mux": True}}
    leg = Leg(
        "pytest",
        (sys.executable, "-c", writer, str(path), json.dumps(initial)),
        ((sys.executable, "-c", writer, str(path), json.dumps(changed)),),
    )
    observed = _run_tools_observed(tmp_path, tmp_path, "current", (leg,))
    assert isinstance(observed.host, Ok), "host observation was not captured"
    assert host_observation_unchanged(tmp_path, "current", observed.host) == 1, (
        "changed host observation was accepted after followup"
    )


def _host_observer_import(root: Path, module: str) -> Output:
    """Observe a fresh interpreter while independently vetoing one later module."""
    program = (
        "import sys\n"
        "def observe(event, args):\n"
        f"    if event == 'import' and args[0] == {module!r}:\n"
        "        raise RuntimeError('later helper vetoed')\n"
        "sys.addaudithook(observe)\n"
        "try:\n"
        f"    __import__({module!r})\n"
        "except RuntimeError as error:\n"
        "    assert str(error) == 'later helper vetoed'\n"
        "else:\n"
        "    raise AssertionError('import observer did not veto')\n"
        "import tests.harness.host\n"
    )
    result = run(
        [sys.executable, "-c", program],
        cwd=root,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    assert isinstance(result, Ok)
    return result.value


def test_host_observer_imports_without_agent_helpers(root: Path) -> None:
    """A real import observer refuses the later agent helper without hiding it."""
    observed = _host_observer_import(root, "tests.harness.agents")
    assert observed.code == 0, (
        "host observer imported later agent helpers: " + observed.stderr
    )


def test_host_observer_imports_without_bootstrap_helpers(root: Path) -> None:
    """The shared host observer does not require the bootstrap-origin module."""
    observed = _host_observer_import(root, "tests.harness.bootstrap_origin")
    assert observed.code == 0, (
        "host observer imported later bootstrap helpers: " + observed.stderr
    )


def test_source_census_includes_untracked_and_ignored(tmp_path: Path) -> None:
    """Actual files, including ignored additions, must have explicit owners."""
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git/config").write_text("metadata", encoding="utf-8")
    (tmp_path / ".gitignore").write_text("ignored.txt\n", encoding="utf-8")
    (tmp_path / "ignored.txt").write_text("initial", encoding="utf-8")
    initial = source_census(tmp_path)
    assert isinstance(initial, Ok)
    assert tuple(entry.path for entry in initial.value) == (".gitignore", "ignored.txt")
    phases = (OwnershipPhase(0, frozenset()),)
    claims = tuple(
        ArtifactOwnership(
            entry.path, 0, frozenset({0}), required=True, capability="census"
        )
        for entry in initial.value
    )
    assert isinstance(
        ownership_inputs(phases, claims, tuple(entry.path for entry in initial.value)),
        Ok,
    )
    (tmp_path / "new-untracked.txt").write_text("new", encoding="utf-8")
    changed = source_census(tmp_path)
    assert isinstance(changed, Ok)
    assert isinstance(
        ownership_inputs(phases, claims, tuple(entry.path for entry in changed.value)),
        Err,
    )
    (tmp_path / "ignored.txt").write_text("changed", encoding="utf-8")
    assert source_census(tmp_path) != changed
    assert isinstance(source_census(tmp_path / "missing"), Err)


def test_guarded_census_real_symlink(tmp_path: Path) -> None:
    """A real link is resolved inside the checkout and escaping links are refused."""
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    (checkout / "target").write_bytes(b"target bytes")
    link = checkout / "link"
    link.symlink_to("target")
    observed = guarded_census(checkout)
    assert isinstance(observed, Ok), observed
    entry = next(item for item in observed.value if item.path == "link")
    assert entry.kind == "symlink"
    assert entry.payloads == (b"target", b"target bytes")
    facts = tree(checkout)
    assert isinstance(facts, Ok)
    forged = tuple(
        Entry(item.path, item.kind, (b"target", b"forged bytes"))
        if item.path == "link"
        else item
        for item in observed.value
    )
    assert isinstance(_guard_links(checkout, forged, facts.value), Err), (
        "forged link target was accepted"
    )
    link.unlink()
    (tmp_path / "outside").write_bytes(b"outside")
    link.symlink_to("../outside")
    assert isinstance(guarded_census(checkout), Err), "escaping link was accepted"


def test_census_link_target_matches_guard(tmp_path: Path) -> None:
    """Captured link bytes must match the exact target in the guarded tree."""
    (tmp_path / "target").write_bytes(b"original")
    (tmp_path / "other").write_bytes(b"changed!")
    facts = tree(tmp_path)
    assert isinstance(facts, Ok)
    link = Entry("link", "symlink", (b"target", b"original"))
    assert census_link_targets_match_guard(
        (link,), facts.value, (("link", "target"),)
    ) == Ok(None)
    changed = Entry("link", "symlink", (b"target", b"changed!"))
    assert isinstance(
        census_link_targets_match_guard((changed,), facts.value, (("link", "target"),)),
        Err,
    ), "changed link target bytes matched original guard"
    assert isinstance(census_link_targets_match_guard((link,), facts.value, ()), Err)
    assert isinstance(
        census_link_targets_match_guard((link,), facts.value, (("link", "other"),)), Err
    )


def test_source_census_matches_write_guard(tmp_path: Path) -> None:
    """Independent observations refuse stale bytes and added or removed paths."""
    (tmp_path / "empty").mkdir()
    path = tmp_path / "untracked"
    path.write_bytes(b"before")
    entries = source_census(tmp_path)
    guard = tree(tmp_path)
    assert isinstance(entries, Ok)
    assert isinstance(guard, Ok)
    assert census_matches_guard(entries.value, guard.value) == Ok(None)
    assert guarded_census(tmp_path) == entries
    assert guarded_census(tmp_path, expected=guard.value) == entries
    path.write_bytes(b"after!")
    assert isinstance(guarded_census(tmp_path, expected=guard.value), Err), (
        "changed checkout accepted against original guard"
    )
    changed = tree(tmp_path)
    assert isinstance(changed, Ok)
    assert isinstance(census_matches_guard(entries.value, changed.value), Err), (
        "changed source bytes matched guard"
    )
    path.unlink()
    missing = tree(tmp_path)
    assert isinstance(missing, Ok)
    assert isinstance(census_matches_guard(entries.value, missing.value), Err)
    (tmp_path / "new").write_bytes(b"new")
    added = tree(tmp_path)
    assert isinstance(added, Ok)
    assert isinstance(census_matches_guard(entries.value, added.value), Err)


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
    result = finish(child.value, timeout=10)
    assert isinstance(result, Ok)
    assert result.value.stdout == "finished\n"
    assert isinstance(stop(child.value), Ok)
    assert alive(family, child.value.pid) == Ok(value=False)
    pending = start(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        cwd=tmp_path,
        env=os.environ,
    )
    assert isinstance(pending, Ok), pending
    try:
        assert isinstance(finish(pending.value, timeout=0.01), Err)
    finally:
        assert isinstance(stop(pending.value), Ok)


def test_owned_child_escalation(tmp_path: Path) -> None:
    """An owned child ignoring graceful signals is forcibly killed and reaped."""
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


def test_leg_followups_and_failures(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Independent reports run after failure; dependent followups stop on error."""
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
            Leg(
                "report-failure",
                (sys.executable, "-c", "raise SystemExit(7)"),
                ((sys.executable, "-c", "raise SystemExit(3)"), write),
                after_failure=True,
            ),
        )
        == CONTROL_EXIT
    )
    assert not effect.exists()
    assert "report-failure: followup failed with status 3" in capsys.readouterr().err
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
    assert (
        run_leg(
            tmp_path,
            tmp_path,
            "nonce",
            Leg(
                "report",
                (sys.executable, "-c", "raise SystemExit(7)"),
                (write,),
                after_failure=True,
            ),
        )
        == CONTROL_EXIT
    )
    assert effect.read_text(encoding="utf-8") == "ran"
    effect.unlink()
    assert run_tools(tmp_path, tmp_path, "nonce", (Leg("positive", success),)) == 0
    assert run_tools(tmp_path, tmp_path, "nonce", ()) == 1
    assert (
        run_tools(
            tmp_path,
            tmp_path,
            "nonce",
            (Leg("failed", (str(tmp_path / "missing"),)), Leg("later", write)),
        )
        == 1
    )
    assert effect.read_text(encoding="utf-8") == "ran"
    outcomes = read_legs(tmp_path / "tool-outcomes.json", "nonce", ("failed", "later"))
    assert isinstance(outcomes, Ok)
    assert outcomes.value.outcomes == (("failed", 1), ("later", 0))
    assert isinstance(
        read_legs(tmp_path / "tool-outcomes.json", "stale", ("failed", "later")), Err
    )


def test_tool_outcomes_survive_later_execution(tmp_path: Path) -> None:
    """Compare a real child result against the retained ordered tool record."""
    leg = Leg("tool", (sys.executable, "-c", "raise SystemExit(0)"))
    captured = _run_tools_observed(tmp_path, tmp_path, "fresh", (leg,))
    assert captured.code == 0
    assert tool_outcomes_unchanged(tmp_path, "fresh", captured.evidence) == 0
    assert tool_substeps_unchanged(tmp_path, "fresh", captured.substeps) == 0
    (tmp_path / "tool-substeps.json").write_text(
        json.dumps({"nonce": "fresh", "outcomes": [["tool", [1]]]}), encoding="utf-8"
    )
    assert tool_substeps_unchanged(tmp_path, "fresh", captured.substeps) == 1, (
        "changed tool substeps were accepted"
    )
    (tmp_path / "tool-outcomes.json").write_text(
        json.dumps({"nonce": "fresh", "outcomes": [["tool", 1]]}), encoding="utf-8"
    )
    assert tool_outcomes_unchanged(tmp_path, "fresh", captured.evidence) == 1, (
        "changed tool outcomes were accepted"
    )


def test_tool_substeps_preserve_primary_and_followup(tmp_path: Path) -> None:
    """Record both failures without inventing a later, unattempted follow-up."""
    failing = (sys.executable, "-c", "raise SystemExit(7)")
    reporting = (sys.executable, "-c", "raise SystemExit(3)")
    unused = (sys.executable, "-c", "raise SystemExit(0)")
    leg = Leg("pytest", failing, (reporting, unused), after_failure=True)
    captured = _run_tools_observed(tmp_path, tmp_path, "fresh", (leg,))
    assert captured.code == 1
    assert isinstance(captured.substeps, Ok)
    assert captured.substeps.value.outcomes == (("pytest", (7, 3)),), (
        "independent tool substeps were lost"
    )
    assert captured.commands == (("pytest", (failing, reporting)),), (
        "attempted Python commands were lost"
    )


def test_python_commands_real_handoff_and_retention(tmp_path: Path) -> None:
    """Capture real child commands and reject a valid altered retained record."""
    script = """
import json, sys
from pathlib import Path
from agentctl.check import steps
from agentctl.check.legs import Leg
from agentctl.foundation import Err, Ok
root = Path(sys.argv[1]); run_dir = root / "run"; run_dir.mkdir()
nonce = "abc123"
legs = tuple(Leg(name, (sys.executable, "-c", "pass"))
             for name in steps.PYTHON_COMMAND_NAMES)
observed = steps._run_tools_observed(root, run_dir, nonce, legs)
capture = steps.record_python_commands(
    run_dir, nonce, root, observed.commands, "0" * 64)
assert isinstance(capture, Ok), capture
assert steps.python_commands_unchanged(run_dir, nonce, root, capture) == 0
assert isinstance(steps.record_python_commands(
    run_dir, nonce, root, observed.commands, "0" * 64), Err)
assert isinstance(steps._parse_python_commands_record(
    "foreign", root, capture.value.record), Err)
assert isinstance(steps._parse_python_commands_record(
    nonce, root.parent, capture.value.record), Err)
failed = {"ruff-observation", "coverage-observation", "mutant-killers",
          "ruff-format-observation", "pytest-manifest", "oracle-outcomes",
          "host-observation", "native-observation", "ty-observation",
          "coverage-text-observation"}
statuses = tuple((name, int(name in failed)) for name in steps.FINALIZER_NAMES[:-1])
final = steps.record_finalizers(run_dir, nonce, statuses)
phase = steps.record_provisional_phases(run_dir, nonce, Err("unavailable"))
assert isinstance(final, Ok) and isinstance(phase, Ok)
marker = steps.python_commands_seal(nonce, capture.value.record)
output = "\\n".join((marker,
    steps.provisional_seal(nonce, phase.value), steps.finalizer_seal(final.value), ""))
assert isinstance(observed.evidence, Ok) and isinstance(observed.substeps, Ok)
output = (steps.tool_results_seal(nonce, observed.evidence.value,
    observed.substeps.value) + "\\n" + output)
assert steps.verify_python_commands_handoff(run_dir, nonce, output, root) == Ok(None)
missing = output.replace(marker + "\\n", "", 1)
duplicate = marker + "\\n" + output
assert isinstance(steps.verify_python_commands_handoff(
    run_dir, nonce, missing, root), Err)
assert isinstance(steps.verify_python_commands_handoff(
    run_dir, nonce, duplicate, root), Err)
context = steps.CheckRun(root, run_dir, nonce, sys.argv[2])
valid = steps.retain_verified_gate_output(context, root.parent / "state-ok",
    (output, "primary\\n"), verify_handoff=True)
assert isinstance(valid, Ok), valid
assert (valid.value / "python-commands.json").read_bytes() == capture.value.record
state = root.parent / "state-tamper"
target = state / "check-reports" / nonce / "python-commands.json"
seen = [False]
def audit(event, args):
    if (not seen[0] and event == "open" and str(args[0]) == str(target)
        and "r" in str(args[1]) and target.exists()):
        seen[0] = True
        changed = json.loads(target.read_text())
        changed["commands"][0][1][0][-1] = "changed"
        target.write_text(json.dumps(changed, sort_keys=True))
sys.addaudithook(audit)
result = steps.retain_verified_gate_output(context, state,
    (output, "primary\\n"), verify_handoff=True)
assert isinstance(result, Err), "post-copy command tampering was accepted"
assert seen[0]
report = state / "check-reports" / nonce
assert "Python command handoff digest mismatch" in (
    report / "finalizer-handoff.txt").read_text()
assert (report / "stderr.txt").read_text() == "primary\\n"
"""
    root = tmp_path / "checkout"
    root.mkdir()
    child = process.run(
        [sys.executable, "-c", script, str(root), platform.system()],
        cwd=root,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    assert isinstance(child, Ok), child
    assert child.value.code == 0, child.value.stderr


def test_host_handoff_preserves_real_observation(root: Path, tmp_path: Path) -> None:
    """A real native host observation remains bound through report retention."""
    observed_dir = tmp_path / "observed"
    observed_dir.mkdir()
    observer = (
        "from pathlib import Path; import sys; from tests.harness.host import observe; "
        "observe(Path(sys.argv[1]), 'abc123', Path(sys.argv[2]))"
    )
    observation = process.run(
        [sys.executable, "-c", observer, str(root), str(observed_dir / "host.json")],
        cwd=root,
        env={
            **os.environ,
            "PATH": "",
            "PYTHONDONTWRITEBYTECODE": "1",
            "XDG_STATE_HOME": str(tmp_path / "private-state"),
        },
    )
    assert isinstance(observation, Ok), observation
    assert observation.value.code == 0, observation.value.stderr
    project = tmp_path / "checkout"
    project.mkdir()
    script = """
import json, sys
from dataclasses import replace
from pathlib import Path
from agentctl.check import steps
from agentctl.foundation import Err, Ok
from agentctl.foundation_process_values import Output
root, original, directory, state = map(Path, sys.argv[1:5]); directory.mkdir()
nonce = "abc123"
(directory / "host.json").write_bytes(original.read_bytes())
observed = steps.host_observation(directory, nonce)
assert isinstance(observed, Ok)
failed = {"python-commands", "tool-outcomes", "pytest-manifest", "oracle-outcomes",
          "ruff-observation", "ruff-format-observation", "coverage-observation",
          "mutant-killers", "native-observation", "ty-observation",
          "coverage-text-observation"}
statuses = tuple((name, int(name in failed)) for name in steps.FINALIZER_NAMES[:-1])
final = steps.record_finalizers(directory, nonce, statuses)
phase = steps.record_provisional_phases(directory, nonce, Err("unavailable"))
assert isinstance(final, Ok) and isinstance(phase, Ok)
marker = steps.host_observation_seal(nonce, observed.value)
for field in ("family", "architecture", "checkout", "git", "mux", "agents",
              "authenticated", "clean", "xcode", "debian"):
    value = getattr(observed.value, field)
    changed = replace(observed.value, **{field: not value if isinstance(value, bool)
                                         else value + "-changed"})
    assert steps.host_observation_seal(nonce, changed) != marker, \
        "host seal omitted " + field
output = "\\n".join((marker, steps.provisional_seal(nonce, phase.value),
    steps.finalizer_seal(final.value), ""))
assert steps.verify_host_handoff(directory, nonce, output) == Ok(None)
missing = output.replace(marker + "\\n", "", 1)
duplicate = marker + "\\n" + output
assert isinstance(steps.verify_host_handoff(directory, nonce, missing), Err), \
    "missing host seal was accepted"
assert isinstance(steps.verify_host_handoff(directory, nonce, duplicate), Err), \
    "duplicate host seal was accepted"
context = steps.CheckRun(root, directory, nonce, sys.argv[5])
live = directory.parent / "live-run"; live.mkdir()
(live / "host.json").write_bytes(original.read_bytes())
assert isinstance(steps.record_finalizers(live, nonce, statuses), Ok)
assert isinstance(steps.record_provisional_phases(live, nonce, Err("unavailable")), Ok)
changed = json.loads((live / "host.json").read_text())
changed["facts"]["checkout"] = not changed["facts"]["checkout"]
(live / "host.json").write_text(json.dumps(changed))
steps.run_observed = lambda *_args, **_kwargs: Ok(Output(0, output, "primary\\n"))
live_state = state.with_name("state-live")
assert steps._run_check_child(steps.CheckRun(root, live, nonce, sys.argv[5]),
    live_state, assume_yes=False) == 1, "live host check was omitted"
live_stderr = (live_state / "check-reports" / nonce / "stderr.txt").read_text()
assert "host handoff digest mismatch" in live_stderr, "live host check was omitted"
assert "primary" in live_stderr
valid = steps.retain_verified_gate_output(context, state.with_name("state-ok"),
    (output, "primary\\n"), verify_handoff=True)
assert isinstance(valid, Ok), valid
target = state / "check-reports" / nonce / "host.json"
seen = [False]
def audit(event, args):
    if (not seen[0] and event == "open" and str(args[0]) == str(target)
        and "r" in str(args[1]) and target.exists()):
        seen[0] = True
        value = json.loads(target.read_text())
        value["facts"]["checkout"] = not value["facts"]["checkout"]
        target.write_text(json.dumps(value))
sys.addaudithook(audit)
answer = steps.retain_verified_gate_output(context, state, (output, "primary\\n"),
    verify_handoff=True)
assert isinstance(answer, Err), "post-copy host tampering was accepted"
assert seen[0]
report = state / "check-reports" / nonce
assert "host handoff digest mismatch" in (report / "finalizer-handoff.txt").read_text()
assert (report / "stderr.txt").read_text() == "primary\\n"
"""
    child = process.run(
        [
            sys.executable,
            "-c",
            script,
            str(project),
            str(observed_dir / "host.json"),
            str(tmp_path / "parent-run"),
            str(tmp_path / "state"),
            platform.system(),
        ],
        cwd=root,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    assert isinstance(child, Ok), child
    assert child.value.code == 0, child.value.stderr


def test_oracle_handoff_preserves_real_execution(
    root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Real oracle results remain bound across live and retained reports."""
    run_dir = tmp_path / "observed"
    run_dir.mkdir()
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "private-state"))
    monkeypatch.setenv("GHCUP_INSTALL_BASE_PREFIX", str(tmp_path / "private-ghcup"))
    steps.oracle_check(root, run_dir, "abc123")
    oracle = steps.oracle_observation(run_dir, "abc123")
    details = steps.evidence.read_oracle_details(
        run_dir / "oracle-details.json", "abc123"
    )
    assert isinstance(oracle, Ok), oracle
    assert isinstance(details, Ok), details
    assert details.value.sources, "real oracle source list was empty"
    project = tmp_path / "checkout"
    project.mkdir()
    script = """
import json, sys
from dataclasses import replace
from pathlib import Path
from agentctl.check import steps
from agentctl.foundation import Err, Ok
from agentctl.foundation_process_values import Output
root, source, directory, state = map(Path, sys.argv[1:5]); directory.mkdir()
nonce = "abc123"
for name in ("oracle-outcomes.json", "oracle-details.json"):
    (directory / name).write_bytes((source / name).read_bytes())
outcomes = steps.oracle_observation(directory, nonce)
details = steps.evidence.read_oracle_details(directory / "oracle-details.json", nonce)
assert isinstance(outcomes, Ok) and isinstance(details, Ok)
failed = {"python-commands", "tool-outcomes", "pytest-manifest", "ruff-observation",
          "ruff-format-observation", "coverage-observation", "mutant-killers",
          "host-observation", "native-observation", "ty-observation",
          "coverage-text-observation"}
statuses = tuple((name, int(name in failed)) for name in steps.FINALIZER_NAMES[:-1])
final = steps.record_finalizers(directory, nonce, statuses)
phase = steps.record_provisional_phases(directory, nonce, Err("unavailable"))
assert isinstance(final, Ok) and isinstance(phase, Ok)
marker = steps.oracle_results_seal(nonce, outcomes.value, details.value)
first, code = outcomes.value.outcomes[0]
variants = (("outcomes nonce", replace(outcomes.value, nonce="foreign"), details.value),
    ("outcomes", replace(outcomes.value, outcomes=((first, code + 1),
        *outcomes.value.outcomes[1:])), details.value),
    ("details nonce", outcomes.value, replace(details.value, nonce="foreign")),
    ("sources", outcomes.value, replace(details.value, sources=())),
    ("issues", outcomes.value, replace(details.value,
        issues=(*details.value.issues, (None, "damage")))))
for field, altered_outcomes, altered_details in variants:
    assert steps.oracle_results_seal(
        nonce, altered_outcomes, altered_details) != marker, \
        "oracle seal omitted " + field
output = "\\n".join((marker, steps.provisional_seal(nonce, phase.value),
    steps.finalizer_seal(final.value), ""))
assert steps.verify_oracle_handoff(directory, nonce, output) == Ok(None)
missing = output.replace(marker + "\\n", "", 1)
duplicate = marker + "\\n" + output
assert isinstance(steps.verify_oracle_handoff(directory, nonce, missing), Err), \
    "missing oracle seal was accepted"
assert isinstance(steps.verify_oracle_handoff(
    directory, nonce, duplicate), Err), \
    "duplicate oracle seal was accepted"
context = steps.CheckRun(root, directory, nonce, sys.argv[5])
live = directory.parent / "live-run"; live.mkdir()
for name in ("oracle-outcomes.json", "oracle-details.json"):
    (live / name).write_bytes((source / name).read_bytes())
assert isinstance(steps.record_finalizers(live, nonce, statuses), Ok)
assert isinstance(steps.record_provisional_phases(live, nonce, Err("unavailable")), Ok)
changed = json.loads((live / "oracle-details.json").read_text())
changed["issues"].append([None, "damage"])
(live / "oracle-details.json").write_text(json.dumps(changed))
steps.run_observed = lambda *_args, **_kwargs: Ok(Output(0, output, "primary\\n"))
live_state = state.with_name("state-live")
assert steps._run_check_child(steps.CheckRun(root, live, nonce, sys.argv[5]),
    live_state, assume_yes=False) == 1, "live oracle check was omitted"
live_stderr = (live_state / "check-reports" / nonce / "stderr.txt").read_text()
assert "oracle handoff digest mismatch" in live_stderr, "live oracle check was omitted"
assert "primary" in live_stderr
valid = steps.retain_verified_gate_output(context, state.with_name("state-ok"),
    (output, "primary\\n"), verify_handoff=True)
assert isinstance(valid, Ok), valid
for index, name in enumerate(("oracle-outcomes.json", "oracle-details.json")):
    target_state = state.with_name("state-bad-" + str(index))
    target = target_state / "check-reports" / nonce / name
    seen = [False]
    def audit(event, args):
        if (not seen[0] and event == "open" and str(args[0]) == str(target)
            and "r" in str(args[1]) and target.exists()):
            seen[0] = True
            value = json.loads(target.read_text())
            if index == 0: value["outcomes"][0][1] += 1
            else: value["issues"].append([None, "damage"])
            target.write_text(json.dumps(value))
    sys.addaudithook(audit)
    answer = steps.retain_verified_gate_output(context, target_state,
        (output, "primary\\n"), verify_handoff=True)
    assert isinstance(answer, Err), "post-copy oracle tampering was accepted"
    assert seen[0]
    report = target_state / "check-reports" / nonce
    assert "oracle handoff digest mismatch" in (
        report / "finalizer-handoff.txt").read_text()
    assert (report / "stderr.txt").read_text() == "primary\\n"
"""
    child = process.run(
        [
            sys.executable,
            "-c",
            script,
            str(project),
            str(run_dir),
            str(tmp_path / "parent-run"),
            str(tmp_path / "state"),
            platform.system(),
        ],
        cwd=root,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    assert isinstance(child, Ok), child
    assert child.value.code == 0, child.value.stderr


def test_pytest_handoff_preserves_real_execution(tmp_path: Path) -> None:
    """A real pytest manifest remains bound through parent report retention."""
    project, run_dir = tmp_path / "checkout", tmp_path / "run"
    project.mkdir()
    run_dir.mkdir()
    (project / "pytest.ini").write_text(
        "[pytest]\nmarkers = evidence(cls): class\n", encoding="utf-8"
    )
    (project / "test_sample.py").write_text(
        'import pytest\npytestmark = pytest.mark.evidence("value")\n'
        "def test_sample():\n    assert True\n",
        encoding="utf-8",
    )
    leg = Leg(
        "pytest",
        (
            sys.executable,
            "-m",
            "pytest",
            "-p",
            "no:cacheprovider",
            "-p",
            "agentctl.check.gate_plugin",
            ".",
        ),
    )
    result = steps.__dict__["_run_leg_observed"](project, run_dir, "abc123", leg)
    assert result.code == 0, "real pytest observation failed"
    assert isinstance(result.pytest, Ok), "real pytest observation unavailable"
    script = """
import json, sys
from dataclasses import replace
from pathlib import Path
from agentctl.check import steps
from agentctl.foundation import Err, Ok
from agentctl.foundation_process_values import Output
root, original, directory, state = map(Path, sys.argv[1:5]); directory.mkdir()
nonce = "abc123"
(directory / "pytest-manifest.json").write_bytes(original.read_bytes())
observed = steps.pytest_observation(directory, nonce)
assert isinstance(observed, Ok)
failed = {"python-commands", "tool-outcomes", "ruff-observation",
          "ruff-format-observation", "coverage-observation", "mutant-killers",
          "oracle-outcomes", "host-observation", "native-observation", "ty-observation",
          "coverage-text-observation"}
statuses = tuple((name, int(name in failed)) for name in steps.FINALIZER_NAMES[:-1])
final = steps.record_finalizers(directory, nonce, statuses)
phase = steps.record_provisional_phases(directory, nonce, Err("unavailable"))
assert isinstance(final, Ok) and isinstance(phase, Ok)
marker = steps.pytest_manifest_seal(nonce, observed.value)
variants = (("nonce", "foreign"), ("collected", frozenset()), ("executed", frozenset()),
            ("passed", frozenset()), ("forbidden", ("damage",)), ("classes", ()))
for field, value in variants:
    changed = replace(observed.value, **{field: value})
    assert steps.pytest_manifest_seal(nonce, changed) != marker, \
        "pytest seal omitted " + field
output = "\\n".join((marker, steps.provisional_seal(nonce, phase.value),
    steps.finalizer_seal(final.value), ""))
assert steps.verify_pytest_handoff(directory, nonce, output) == Ok(None)
missing = output.replace(marker + "\\n", "", 1)
duplicate = marker + "\\n" + output
assert isinstance(steps.verify_pytest_handoff(directory, nonce, missing), Err), \
    "missing pytest seal was accepted"
assert isinstance(steps.verify_pytest_handoff(
    directory, nonce, duplicate), Err), \
    "duplicate pytest seal was accepted"
context = steps.CheckRun(root, directory, nonce, sys.argv[5])
live = directory.parent / "live-run"; live.mkdir()
(live / "pytest-manifest.json").write_bytes(original.read_bytes())
assert isinstance(steps.record_finalizers(live, nonce, statuses), Ok)
assert isinstance(steps.record_provisional_phases(live, nonce, Err("unavailable")), Ok)
changed = json.loads((live / "pytest-manifest.json").read_text())
changed["passed"] = []
(live / "pytest-manifest.json").write_text(json.dumps(changed))
steps.run_observed = lambda *_args, **_kwargs: Ok(Output(0, output, "primary\\n"))
live_state = state.with_name("state-live")
assert steps._run_check_child(steps.CheckRun(root, live, nonce, sys.argv[5]),
    live_state, assume_yes=False) == 1, "live pytest check was omitted"
live_stderr = (live_state / "check-reports" / nonce / "stderr.txt").read_text()
assert "pytest handoff digest mismatch" in live_stderr, "live pytest check was omitted"
assert "primary" in live_stderr
valid = steps.retain_verified_gate_output(context, state.with_name("state-ok"),
    (output, "primary\\n"), verify_handoff=True)
assert isinstance(valid, Ok), valid
target = state / "check-reports" / nonce / "pytest-manifest.json"
seen = [False]
def audit(event, args):
    if (not seen[0] and event == "open" and str(args[0]) == str(target)
        and "r" in str(args[1]) and target.exists()):
        seen[0] = True
        value = json.loads(target.read_text())
        value["passed"] = []
        target.write_text(json.dumps(value))
sys.addaudithook(audit)
answer = steps.retain_verified_gate_output(context, state, (output, "primary\\n"),
    verify_handoff=True)
assert isinstance(answer, Err), "post-copy pytest tampering was accepted"
assert seen[0]
report = state / "check-reports" / nonce
assert "pytest handoff digest mismatch" in (
    report / "finalizer-handoff.txt").read_text()
assert (report / "stderr.txt").read_text() == "primary\\n"
"""
    child = process.run(
        [
            sys.executable,
            "-c",
            script,
            str(project),
            str(run_dir / "pytest-manifest.json"),
            str(tmp_path / "parent-run"),
            str(tmp_path / "state"),
            platform.system(),
        ],
        cwd=tmp_path,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    assert isinstance(child, Ok), child
    assert child.value.code == 0, child.value.stderr


def test_tool_results_handoff_preserves_real_subprocess_statuses(
    tmp_path: Path,
) -> None:
    """The retained tool and substep records must match the original child results."""
    script = """
import json, sys
from pathlib import Path
from agentctl.check import steps
from agentctl.check.legs import Leg
from agentctl.foundation import Err, Ok
root = Path(sys.argv[1]); run_dir = root / "run"; run_dir.mkdir()
nonce = "abc123"
leg = Leg("sample", (sys.executable, "-c", "raise SystemExit(7)"),
          ((sys.executable, "-c", "raise SystemExit(3)"),), after_failure=True)
observed = steps._run_tools_observed(root, run_dir, nonce, (leg,))
assert isinstance(observed.evidence, Ok) and isinstance(observed.substeps, Ok)
failed = {"python-commands", "ruff-observation", "ruff-format-observation",
          "coverage-observation", "mutant-killers", "pytest-manifest",
          "oracle-outcomes", "host-observation", "native-observation", "ty-observation",
          "coverage-text-observation"}
statuses = tuple((name, int(name in failed)) for name in steps.FINALIZER_NAMES[:-1])
final = steps.record_finalizers(run_dir, nonce, statuses)
phase = steps.record_provisional_phases(run_dir, nonce, Err("unavailable"))
assert isinstance(final, Ok) and isinstance(phase, Ok)
marker = steps.tool_results_seal(nonce, observed.evidence.value,
    observed.substeps.value)
output = "\\n".join((marker, steps.provisional_seal(nonce, phase.value),
    steps.finalizer_seal(final.value), ""))
assert steps.verify_tool_results_handoff(run_dir, nonce, output) == Ok(None)
missing = output.replace(marker + "\\n", "", 1)
duplicate = marker + "\\n" + output
assert isinstance(steps.verify_tool_results_handoff(run_dir, nonce, missing), Err), \
    "missing tool results seal was accepted"
assert isinstance(steps.verify_tool_results_handoff(
    run_dir, nonce, duplicate), Err), \
    "duplicate tool results seal was accepted"
context = steps.CheckRun(root, run_dir, nonce, sys.argv[2])
valid = steps.retain_verified_gate_output(context, root.parent / "state-ok",
    (output, "primary\\n"), verify_handoff=True)
assert isinstance(valid, Ok), valid
for index, name in enumerate(("tool-outcomes.json", "tool-substeps.json")):
    state = root.parent / ("state-bad-" + str(index))
    target = state / "check-reports" / nonce / name
    seen = [False]
    def audit(event, args):
        if (not seen[0] and event == "open" and str(args[0]) == str(target)
            and "r" in str(args[1]) and target.exists()):
            seen[0] = True
            value = json.loads(target.read_text())
            if index == 0: value["outcomes"][0][1] = 8
            else: value["outcomes"][0][1][0] = 8
            target.write_text(json.dumps(value))
    sys.addaudithook(audit)
    result = steps.retain_verified_gate_output(context, state, (output, "primary\\n"),
        verify_handoff=True)
    assert isinstance(result, Err), "post-copy tool results tampering was accepted"
    assert seen[0]
    report = state / "check-reports" / nonce
    assert "tool results handoff digest mismatch" in (
        report / "finalizer-handoff.txt").read_text()
    assert (report / "stderr.txt").read_text() == "primary\\n"
"""
    root = tmp_path / "checkout"
    root.mkdir()
    child = process.run(
        [sys.executable, "-c", script, str(root), platform.system()],
        cwd=root,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    assert isinstance(child, Ok), child
    assert child.value.code == 0, child.value.stderr


@pytest.mark.parametrize("consumer", ["finalizers", "identity"])
def test_parent_refuses_replaced_provisional_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, consumer: str
) -> None:
    """Parent rereads refuse an equal-byte hard link after the initial seal check."""
    directory = tmp_path / "run"
    directory.mkdir()
    nonce = "abc123"
    statuses = tuple((name, 0) for name in steps.FINALIZER_NAMES[:-1])
    final = steps.record_finalizers(directory, nonce, statuses)
    phase = steps.record_provisional_phases(directory, nonce, Err("unavailable"))
    assert isinstance(final, Ok)
    assert isinstance(phase, Ok)
    output = (
        steps.provisional_seal(nonce, phase.value)
        + "\n"
        + steps.finalizer_seal(final.value)
        + "\n"
    )
    context = CheckRun(tmp_path, directory, nonce, "Linux")

    def verify() -> object:
        if consumer == "finalizers":
            return steps.verify_provisional_finalizers(directory, nonce, output)
        return steps.__dict__["_provisional_values_for_identity"](
            context, directory, output
        )

    assert verify() == Ok(None)
    original = steps.__dict__["_read_provisional_handoff"]
    outside = tmp_path / "outside"
    outside.write_bytes(phase.value)
    changed: list[bool] = []

    def swap_after_read(path: Path) -> object:
        result = original(path)
        if not changed:
            path.unlink()
            os.link(outside, path)
            changed.append(True)
        return result

    monkeypatch.setattr(steps, "_read_provisional_handoff", swap_after_read)
    assert isinstance(verify(), Err), "replaced provisional record was accepted"
    assert changed == [True]


def test_failed_native_step_emits_absence_observation(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A real failed native step observes its private missing report files."""
    root, run_dir = tmp_path / "checkout", tmp_path / "run"
    root.mkdir()
    run_dir.mkdir()
    host = steps.hostfacts.current(tmp_path / "empty-cache")
    leg = steps.haskell.HaskellStep("cabal-test", host, root / "missing-project")
    observed = _run_tools_observed(root, run_dir, "abc123", (leg,))
    assert isinstance(observed.evidence, Ok)
    output = capsys.readouterr().out
    assert observed.native_absence is not None
    assert steps.native_integrity_attribution(1, observed, run_dir, "abc123") == (
        True,
        0,
    )
    assert steps.native_integrity_attribution(
        1, replace(observed, native_absence=None), run_dir, "abc123"
    ) == (False, 1), "unobserved native failure was localized"
    validation = steps.ValidationOutcome(
        1,
        Err("unused"),
        Err(steps.evidence.EvidenceError("unused")),
        observed.evidence,
        observed.substeps,
        phase_observations=Ok(()),
        native_absence=observed.native_absence,
    )
    statuses = tuple(
        (name, int(name == "native-observation")) for name in steps.FINALIZER_NAMES
    )
    assert steps.localizable_native_finalizer(validation, run_dir, "abc123", statuses)
    damaged = tuple(
        (name, 1 if name == "write-guard" else code) for name, code in statuses
    )
    assert not steps.localizable_native_finalizer(
        validation, run_dir, "abc123", damaged
    ), "damaged shared guard localized native finalizer"
    assert steps.verify_native_absence_handoff(
        run_dir, "abc123", output, observed.evidence.value
    ) == Ok(None), "failed native absence observation missing"
    (run_dir / "tasty.xml").write_text("partial", encoding="utf-8")
    assert isinstance(
        steps.verify_native_absence_handoff(
            run_dir, "abc123", output, observed.evidence.value
        ),
        Err,
    ), "partial native report was treated as absent"
    assert steps.native_integrity_attribution(1, observed, run_dir, "abc123") == (
        False,
        1,
    ), "partial native report was localized"


def test_missing_native_parent_checks_real_failed_tool_handoff(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Reconstruction refuses changed retained status from a real child process."""
    root, run_dir = tmp_path / "checkout", tmp_path / "run"
    root.mkdir()
    run_dir.mkdir()
    nonce = "abc123"
    leg = Leg("cabal-test", (sys.executable, "-c", "raise SystemExit(7)"))
    observed = _run_tools_observed(root, run_dir, nonce, (leg,))
    assert isinstance(observed.evidence, Ok)
    assert isinstance(observed.substeps, Ok)
    failed = {
        "native-observation",
        "ruff-observation",
        "ruff-format-observation",
        "coverage-observation",
    }
    statuses = tuple((name, int(name in failed)) for name in steps.FINALIZER_NAMES[:-1])
    final = steps.record_finalizers(run_dir, nonce, statuses)
    phase = steps.record_provisional_phases(run_dir, nonce, Err("unavailable"))
    assert isinstance(final, Ok)
    assert isinstance(phase, Ok)
    marker = steps.tool_results_seal(
        nonce, observed.evidence.value, observed.substeps.value
    )
    absence = steps.native_absence_observation(run_dir, nonce, 7)
    assert isinstance(absence, Ok)
    output = "\n".join(
        (
            absence.value,
            marker,
            "mutant marker",
            "command marker",
            steps.provisional_seal(nonce, phase.value),
            steps.finalizer_seal(final.value),
            "",
        )
    )
    monkeypatch.setattr(
        steps,
        "scoped_mutant_mapping",
        lambda *_args: Ok(steps.ownership.ScopedMutantMapping((), ())),
    )
    context = CheckRun(root, run_dir, nonce, "Linux")
    captured = steps.ProvisionalCapture(
        Ok(()),
        Ok(()),
        replace(observed, native=Err("unavailable")),
        None,
        Ok(()),
        nonce,
        ("cabal-test",),
        (),
    )
    reconstruct = steps.__dict__["_parent_missing_native_capture"]
    assert isinstance(reconstruct(context, run_dir, output, captured, ()), Ok)
    assert isinstance(
        reconstruct(context, run_dir, output.replace(absence.value, ""), captured, ()),
        Err,
    ), "missing native absence observation was accepted"
    assert isinstance(
        reconstruct(context, run_dir, absence.value + "\n" + output, captured, ()), Err
    ), "duplicate native absence observation was accepted"
    assert isinstance(
        steps.verify_native_absence_handoff(
            run_dir, nonce, output, replace(observed.evidence.value, nonce="stale")
        ),
        Err,
    ), "stale native absence status was accepted"
    success_marker = (
        steps.NATIVE_ABSENCE_OBSERVATION
        + " "
        + json.dumps({"nonce": nonce, "status": 0}, sort_keys=True)
    )
    assert isinstance(
        steps.verify_native_absence_handoff(
            run_dir,
            nonce,
            output.replace(absence.value, success_marker),
            replace(observed.evidence.value, outcomes=(("cabal-test", 0),)),
        ),
        Err,
    ), "successful native step was treated as absent"
    (run_dir / "haskell-manifest.json").write_text("partial", encoding="utf-8")
    assert isinstance(reconstruct(context, run_dir, output, captured, ()), Err), (
        "partial native report was treated as absent"
    )
    (run_dir / "haskell-manifest.json").unlink()
    path = run_dir / "tool-outcomes.json"
    record = json.loads(path.read_text(encoding="utf-8"))
    record["outcomes"][0][1] = 8
    path.write_text(json.dumps(record), encoding="utf-8")
    assert isinstance(reconstruct(context, run_dir, output, captured, ()), Err), (
        "changed native command status was accepted"
    )


def test_parent_rejects_changed_live_tool_results(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The parent rejects changed live subprocess statuses before retention."""
    root, run_dir, state = (tmp_path / name for name in ("checkout", "run", "state"))
    root.mkdir()
    run_dir.mkdir()
    leg = Leg("sample", (sys.executable, "-c", "raise SystemExit(7)"))
    observed = _run_tools_observed(root, run_dir, "abc123", (leg,))
    assert isinstance(observed.evidence, Ok)
    assert isinstance(observed.substeps, Ok)
    failures = {
        "python-commands",
        "pytest-manifest",
        "oracle-outcomes",
        "host-observation",
        "native-observation",
        "ty-observation",
        "coverage-text-observation",
        "ruff-observation",
        "ruff-format-observation",
        "coverage-observation",
        "mutant-killers",
    }
    statuses = tuple(
        (name, int(name in failures)) for name in steps.FINALIZER_NAMES[:-1]
    )
    final = steps.record_finalizers(run_dir, "abc123", statuses)
    phase = steps.record_provisional_phases(run_dir, "abc123", Err("unavailable"))
    assert isinstance(final, Ok)
    assert isinstance(phase, Ok)
    output = "\n".join(
        (
            steps.tool_results_seal(
                "abc123", observed.evidence.value, observed.substeps.value
            ),
            steps.provisional_seal("abc123", phase.value),
            steps.finalizer_seal(final.value),
            "",
        )
    )
    path = run_dir / "tool-substeps.json"
    changed = json.loads(path.read_text(encoding="utf-8"))
    changed["outcomes"][0][1][0] = 8
    path.write_text(json.dumps(changed), encoding="utf-8")
    monkeypatch.setattr(
        steps,
        "run_observed",
        lambda *_args, **_kwargs: Ok(FoundationOutput(0, output, "primary\n")),
    )
    family = platform.system()
    assert family in {"Linux", "Darwin", "Windows"}
    assert (
        _run_check_child(
            CheckRun(root, run_dir, "abc123", family), state, assume_yes=False
        )
        == 1
    )
    stderr = (state / "check-reports/abc123/stderr.txt").read_text(encoding="utf-8")
    assert "tool results handoff digest mismatch" in stderr, (
        "live tool results check was omitted"
    )
    assert "primary" in stderr


def _assert_python_plan_rejects_swapped_record(
    context: CheckRun, record: bytes, output: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Reject a valid command prefix substituted after handoff verification."""
    assert steps.verify_python_handoffs(context, output) == Ok(None)
    duplicate = steps.python_commands_seal(context.nonce, record) + "\n" + output
    assert isinstance(steps.verify_python_handoffs(context, duplicate), Err), (
        "unsealed Python command plan was accepted"
    )
    prefix = json.loads(record)
    assert len(prefix["commands"][-1][1]) > 1
    prefix["commands"][-1][1].pop()
    shorter = json.dumps(prefix, sort_keys=True).encode()
    assert steps.__dict__["_parse_python_commands_record"](
        context.nonce, context.root, shorter
    ) == Ok(None)
    assert steps.__dict__["_python_plan_from_record"](context, shorter) == Ok(None)
    assert isinstance(
        steps.__dict__["_parent_bound_census"](context, context.directory, output), Ok
    )
    with monkeypatch.context() as control:
        control.setattr(
            steps, "_python_commands_handoff_record", lambda *_args: Ok(shorter)
        )
        assert isinstance(
            steps.__dict__["_parent_bound_census"](context, context.directory, output),
            Err,
        ), "changed parent census command record was accepted"
    reads = 0

    def swapped_commands(*_args: object) -> Result[bytes, str]:
        nonlocal reads
        reads += 1
        return Ok(record if reads == 1 else shorter)

    with monkeypatch.context() as patch:
        patch.setattr(steps, "_python_commands_handoff_record", swapped_commands)
        assert steps.verify_python_handoffs(context, output) == Err(
            "Python command plan changed after handoff"
        ), "changed Python command plan after seal was accepted"


def test_parent_rechecks_actual_python_plan(
    root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A sealed wrong command or a newly appearing source fails the parent join."""
    project, run_dir = tmp_path / "project", tmp_path / "run"
    source, tests = project / "src/agentctl/check", project / "tests"
    source.mkdir(parents=True)
    tests.mkdir()
    run_dir.mkdir()
    (project / "pyproject.toml").write_bytes((root / "pyproject.toml").read_bytes())
    (source / "host_only.py").write_text("value = 1\n", encoding="utf-8")
    (source / "coverage_hosts.toml").write_text(
        'version = 1\n[[source]]\npath = "src/agentctl/check/host_only.py"\n'
        'hosts = ["Linux", "Windows", "Darwin"]\n',
        encoding="utf-8",
    )
    (tests / "test_small.py").write_text(
        "def test_small():\n    assert True\n", encoding="utf-8"
    )
    found, source_census_before = steps.targets(project), guarded_census(project)
    assert isinstance(found, Ok)
    assert isinstance(source_census_before, Ok)
    source_digest, legs = (
        steps.evidence.digest_census(source_census_before.value),
        steps.python_legs(sys.executable, project, found.value, run_dir),
    )
    assert isinstance(source_digest, Ok)
    tools = _run_tools_observed(project, run_dir, "abc123", legs)
    captured, tool_evidence, tool_substeps = (
        steps.record_python_commands(
            run_dir, "abc123", project, tools.commands, source_digest.value
        ),
        tools.evidence,
        tools.substeps,
    )
    assert isinstance(captured, Ok), captured
    assert isinstance(tool_evidence, Ok)
    assert isinstance(tool_substeps, Ok)
    failures = {
        "mutant-killers",
        "pytest-manifest",
        "oracle-outcomes",
        "host-observation",
        "native-observation",
        "ty-observation",
        "coverage-text-observation",
        "coverage-observation",
        "ruff-observation",
        "ruff-format-observation",
    }
    statuses = tuple(
        (name, int(name in failures)) for name in steps.FINALIZER_NAMES[:-1]
    )
    final, phase = (
        steps.record_finalizers(run_dir, "abc123", statuses),
        steps.record_provisional_phases(run_dir, "abc123", Err("unavailable")),
    )
    assert isinstance(final, Ok)
    assert isinstance(phase, Ok)
    family = platform.system()
    assert family in {"Linux", "Darwin", "Windows"}
    context = CheckRun(project, run_dir, "abc123", family)

    def output(record: bytes) -> str:
        return "\n".join(
            (
                steps.tool_results_seal(
                    "abc123", tool_evidence.value, tool_substeps.value
                ),
                steps.python_commands_seal("abc123", record),
                steps.provisional_seal("abc123", phase.value),
                steps.finalizer_seal(final.value),
                "",
            )
        )

    _assert_python_plan_rejects_swapped_record(
        context, captured.value.record, output(captured.value.record), monkeypatch
    )
    assert isinstance(
        steps.verify_python_handoffs(
            context,
            output(captured.value.record).replace(
                steps.python_commands_seal("abc123", captured.value.record),
                steps.PYTHON_COMMANDS_SEAL + " abc123 " + "0" * 64,
            ),
        ),
        Err,
    ), "unsealed Python command plan was accepted"
    path = run_dir / "python-commands.json"
    forged = json.loads(captured.value.record)
    forged["commands"][0][1][0].remove("--no-cache")
    altered = json.dumps(forged, sort_keys=True).encode()
    path.write_bytes(altered)
    assert steps.verify_python_commands_handoff(
        run_dir, "abc123", output(altered), project
    ) == Ok(None)
    assert isinstance(steps.verify_python_handoffs(context, output(altered)), Err), (
        "sealed wrong Python command was accepted"
    )
    monkeypatch.setattr(
        steps,
        "run_observed",
        lambda *_args, **_kwargs: Ok(FoundationOutput(1, output(altered), "primary\n")),
    )
    state = tmp_path / "state"
    assert _run_check_child(context, state, assume_yes=False) == 1, (
        "parent omitted Python plan verification"
    )
    stderr = (state / "check-reports/abc123/stderr.txt").read_text(encoding="utf-8")
    assert "Python command plan differs from captured attempts" in stderr, (
        "parent omitted Python plan verification"
    )
    assert "primary" in stderr
    path.write_bytes(captured.value.record)
    (source / "host_only.py").write_text("value = 2\n", encoding="utf-8")
    assert isinstance(
        steps.verify_python_handoffs(context, output(captured.value.record)), Err
    ), "changed Python source was accepted by parent plan"
    (source / "host_only.py").write_text("value = 1\n", encoding="utf-8")
    (source / "new_source.py").write_text("value = 2\n", encoding="utf-8")
    assert isinstance(
        steps.verify_python_handoffs(context, output(captured.value.record)), Err
    ), "new Python source was omitted from parent plan"


def test_parent_python_plan_requires_shared_finalizers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Containment or write-guard damage prevents trusting the parent plan join."""
    family = platform.system()
    assert family in {"Linux", "Darwin", "Windows"}
    for name in ("write-guard", "containment"):
        directory = tmp_path / name
        directory.mkdir()
        statuses = tuple(
            (item, int(item == name)) for item in steps.FINALIZER_NAMES[:-1]
        )
        assert isinstance(steps.record_finalizers(directory, "fresh", statuses), Ok)
        result = steps.verify_python_plan_handoff(
            CheckRun(tmp_path, directory, "fresh", family),
            steps.finalizer_seal(steps.evidence.LegEvidence("fresh", statuses)),
        )
        assert result == Err(
            "Python command plan lacks a trustworthy checkout guard"
        ), "damaged shared finalizer was accepted"
        with monkeypatch.context() as patch:
            changed = steps.evidence.LegEvidence(
                "fresh", tuple((item, 0) for item, _ in statuses)
            )
            patch.setattr(
                steps,
                "finalizer_observation",
                lambda *_args, changed=changed: Ok(changed),
            )
            result = steps.verify_python_plan_handoff(
                CheckRun(tmp_path, directory, "fresh", family),
                steps.finalizer_seal(steps.evidence.LegEvidence("fresh", statuses)),
            )
            assert result == Err("finalizer observation changed after handoff"), (
                "Python plan accepted changed finalizer statuses"
            )


def test_pytest_manifest_captured_before_followups(tmp_path: Path) -> None:
    """An actual follow-up cannot replace the primary test execution record."""
    manifest = tmp_path / "pytest-manifest.json"
    node = "tests/test_sample.py::test_one"
    initial = {
        "nonce": "fresh",
        "collected": [node],
        "executed": [node],
        "passed": [node],
        "forbidden": [],
        "classes": {node: "value"},
    }
    writer = (
        "from pathlib import Path; import sys; "
        "Path(sys.argv[1]).write_text(sys.argv[2], encoding='utf-8')"
    )
    primary = (
        sys.executable,
        "-c",
        writer,
        str(manifest),
        json.dumps(initial),
    )
    followup = (
        sys.executable,
        "-c",
        writer,
        str(manifest),
        json.dumps({**initial, "passed": []}),
    )
    captured = _run_tools_observed(
        tmp_path, tmp_path, "fresh", (Leg("pytest", primary, (followup,)),)
    )
    assert isinstance(captured.pytest, Ok), (
        "pytest manifest was not captured after the primary command"
    )
    assert pytest_manifest_unchanged(tmp_path, "fresh", captured.pytest) == 1, (
        "changed pytest manifest was accepted"
    )


def test_mutant_report_captured_before_followups(tmp_path: Path) -> None:
    """Preserve the primary subprocess report before a later command changes it."""
    report = tmp_path / "mutant-killers.json"
    writer = (
        "from pathlib import Path; import sys; "
        "Path(sys.argv[1]).write_text(sys.argv[2], encoding='utf-8')"
    )
    initial = '{"nonce":"fresh","records":[]}'
    primary = (sys.executable, "-c", writer, str(report), initial)
    followup = (sys.executable, "-c", writer, str(report), " " + initial)
    captured = _run_tools_observed(
        tmp_path, tmp_path, "fresh", (Leg("pytest", primary, (followup,)),)
    )
    assert isinstance(captured.killers, Ok), "mutant report was not captured"
    assert steps.mutant_killers_unchanged(tmp_path, "fresh", captured.killers) == 1, (
        "changed mutant report was accepted"
    )
    report.write_text(initial, encoding="utf-8")
    assert steps.mutant_killers_unchanged(tmp_path, "fresh", captured.killers) == 0


def test_tool_record_change_is_refused(tmp_path: Path) -> None:
    """A real read-boundary alteration cannot convert a failed leg into a pass."""
    script = (
        "import json, sys\nfrom pathlib import Path\n"
        "from agentctl.check.legs import Leg\n"
        "from agentctl.check.steps import run_tools\n"
        "root = Path(sys.argv[1]); target = root / 'tool-outcomes.json'\n"
        "def audit(event, args):\n"
        "    if event == 'open' and str(args[0]) == str(target) and args[1] == 'r':\n"
        "        value = {'nonce': 'fresh', 'outcomes': [['leg', 0]]}\n"
        "        target.write_text(json.dumps(value), encoding='utf-8')\n"
        "sys.addaudithook(audit)\n"
        "leg = Leg('leg', (sys.executable, '-c', 'raise SystemExit(7)'))\n"
        "code = run_tools(root, root, 'fresh', (leg,))\n"
        "sys.exit(0 if code == 1 else 1)\n"
    )
    result = run(
        [sys.executable, "-c", script, str(tmp_path)],
        cwd=tmp_path,
        env={**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"},
    )
    assert isinstance(result, Ok)
    assert result.value.code == 0, result.value.stderr
    assert "tool outcomes: execution record changed" in result.value.stderr


def test_gate_output_survives_legacy_console_encoding(tmp_path: Path) -> None:
    """Non-ASCII diagnostics survive a legacy parent stream without truncation."""
    script = (
        "from agentctl.check.steps import emit_gate_output\n"
        "emit_gate_output('result: \\u2713\\n', 'failure: \\u2717\\n')\n"
    )
    result = run(
        [sys.executable, "-c", script],
        cwd=tmp_path,
        env={**os.environ, "PYTHONIOENCODING": "cp1252", "PYTHONUTF8": "0"},
    )
    assert isinstance(result, Ok)
    assert result.value.code == 0, result.value.stderr
    assert result.value.stdout == "result: \u2713\n"
    assert result.value.stderr == "failure: \u2717\n"


def test_finalizer_handoff_detects_changed_retained_record(tmp_path: Path) -> None:
    """A real child seal binds both the live record and its retained copy."""
    root, run_dir, state = (tmp_path / name for name in ("checkout", "run", "state"))
    root.mkdir()
    run_dir.mkdir()
    script = (
        "from pathlib import Path\nimport sys\n"
        "from agentctl.check.steps import FINALIZER_NAMES, finalizer_seal, "
        "record_finalizers\n"
        "from agentctl.foundation import Ok\n"
        "record = record_finalizers(Path(sys.argv[1]), sys.argv[2], "
        "tuple((name, 0) for name in FINALIZER_NAMES[:-1]))\n"
        "assert isinstance(record, Ok), record\n"
        "print(finalizer_seal(record.value))\n"
    )
    child = run(
        [sys.executable, "-c", script, str(run_dir), "abc123"],
        cwd=tmp_path,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    assert isinstance(child, Ok)
    assert child.value.code == 0, child.value.stderr
    output = child.value.stdout
    assert verify_finalizer_handoff(run_dir, "abc123", output) == Ok(None)
    assert isinstance(verify_finalizer_handoff(run_dir, "stale", output), Err)
    assert isinstance(
        verify_finalizer_handoff(run_dir, "abc123", output + output), Err
    ), "ambiguous finalizer seal was accepted"
    report = retain_gate_output(root, state, run_dir, "abc123", (output, ""))
    assert isinstance(report, Ok)
    assert verify_finalizer_handoff(report.value, "abc123", output) == Ok(None)
    path = report.value / "finalizer-outcomes.json"
    path.write_bytes(path.read_bytes() + b" ")
    changed = verify_finalizer_handoff(report.value, "abc123", output)
    assert isinstance(changed, Err), "changed retained finalizer record was accepted"
    assert retain_handoff_failure(root, state, report.value, changed.error) == Ok(None)
    assert (report.value / "finalizer-handoff.txt").read_text(
        encoding="utf-8"
    ).strip() == changed.error
    assert isinstance(retain_handoff_failure(root, state, report.value, "again"), Err)


def _isolate_handoff_after(name: str) -> str:
    """Prevent unrelated later checks from masking the verifier under test."""
    checks = (
        "verify_finalizer_handoff",
        "verify_provisional_handoff",
        "verify_provisional_finalizers",
        "verify_killer_handoff",
        "verify_coverage_handoff",
        "verify_ruff_handoff",
        "verify_python_commands_handoff",
        "verify_provisional_input_identities",
        "verify_tool_results_handoff",
        "verify_pytest_handoff",
        "verify_oracle_handoff",
        "verify_host_handoff",
        "verify_native_handoff",
        "verify_ty_handoff",
        "verify_coverage_text_handoff",
        "verify_provisional_collection",
        "verify_provisional_oracle",
        "verify_provisional_host",
        "verify_provisional_coverage",
        "verify_provisional_static",
        "verify_provisional_source",
        "verify_provisional_prerequisites",
        "verify_provisional_validation",
        "verify_provisional_tools",
        "verify_ruff_format_handoff",
    )
    later = checks[checks.index(name) + 1 :]
    return (
        "import agentctl.check.steps as steps\n"
        f"for name in {later!r}: "
        "setattr(steps, name, lambda *args, **kwargs: Ok(None))\n"
    )


def test_provisional_handoff_rejects_equal_byte_replacement(tmp_path: Path) -> None:
    """Replacing a sealed record with equal bytes must still fail its identity check."""
    script = (
        "import os, sys\nfrom pathlib import Path\n"
        "from agentctl.check.steps import (record_provisional_phases, "
        "provisional_seal, verify_provisional_handoff)\n"
        "from agentctl.foundation import Err, Ok\n"
        "root = Path(sys.argv[1]); target = root / 'provisional-phases.json'\n"
        "record = record_provisional_phases(root, 'abc123', Err('missing'))\n"
        "assert isinstance(record, Ok)\n"
        "replacement = root / 'replacement.json'\n"
        "replacement.write_bytes(record.value)\n"
        "seen = [False]\n"
        "def audit(event, args):\n"
        "    if not seen[0] and event == 'open' and str(args[0]) == str(target):\n"
        "        seen[0] = True\n"
        "        os.replace(replacement, target)\n"
        "sys.addaudithook(audit)\n"
        "output = provisional_seal('abc123', record.value) + '\\nfinalizer\\n'\n"
        "result = verify_provisional_handoff(root, 'abc123', output)\n"
        "assert seen[0], 'replacement hook did not run'\n"
        "assert isinstance(result, Err), "
        "'equal-byte provisional replacement accepted'\n"
    )
    child = run(
        [sys.executable, "-c", script, str(tmp_path)],
        cwd=tmp_path,
        env={
            **os.environ,
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPATH": str(Path(__file__).resolve().parents[2] / "src"),
        },
    )
    assert isinstance(child, Ok)
    assert child.value.code == 0, child.value.stderr


def test_provisional_handoff_rejects_special_file_race(tmp_path: Path) -> None:
    """A FIFO substituted at open time cannot block or become trusted evidence."""
    script = (
        "import os, sys\nfrom pathlib import Path\n"
        "from agentctl.check.steps import (record_provisional_phases, "
        "provisional_seal, verify_provisional_handoff)\n"
        "from agentctl.foundation import Err, Ok\n"
        "root = Path(sys.argv[1]); target = root / 'provisional-phases.json'\n"
        "record = record_provisional_phases(root, 'abc123', Err('missing'))\n"
        "assert isinstance(record, Ok)\n"
        "replacement = root / 'replacement'\n"
        "if hasattr(os, 'mkfifo'): os.mkfifo(replacement)\n"
        "else: replacement.write_bytes(record.value)\n"
        "seen = [False]\n"
        "def audit(event, args):\n"
        "    if not seen[0] and event == 'open' and str(args[0]) == str(target):\n"
        "        seen[0] = True\n"
        "        os.replace(replacement, target)\n"
        "sys.addaudithook(audit)\n"
        "output = provisional_seal('abc123', record.value) + '\\nfinalizer\\n'\n"
        "result = verify_provisional_handoff(root, 'abc123', output)\n"
        "assert seen[0], 'special-file replacement hook did not run'\n"
        "assert isinstance(result, Err), 'special-file replacement accepted'\n"
    )
    child = run(
        [sys.executable, "-c", script, str(tmp_path)],
        cwd=tmp_path,
        env={
            **os.environ,
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPATH": str(Path(__file__).resolve().parents[2] / "src"),
        },
        timeout=5,
    )
    assert isinstance(child, Ok), "special-file replacement blocked the handoff"
    assert child.value.code == 0, child.value.stderr


def test_finalizer_handoff_rejects_special_file_race(tmp_path: Path) -> None:
    """A substituted FIFO cannot block the initial finalizer observation."""
    script = (
        "import os, sys\nfrom pathlib import Path\n"
        "from agentctl.check.steps import (FINALIZER_NAMES, record_finalizers, "
        "finalizer_seal, verify_finalizer_handoff)\n"
        "from agentctl.foundation import Err, Ok\n"
        "root = Path(sys.argv[1]); target = root / 'finalizer-outcomes.json'\n"
        "record = record_finalizers(root, 'abc123', "
        "tuple((name, 0) for name in FINALIZER_NAMES[:-1]))\n"
        "assert isinstance(record, Ok)\n"
        "replacement = root / 'replacement'\n"
        "if hasattr(os, 'mkfifo'): os.mkfifo(replacement)\n"
        "else: replacement.write_bytes(target.read_bytes())\n"
        "seen = [False]\n"
        "def audit(event, args):\n"
        "    if not seen[0] and event == 'open' and str(args[0]) == str(target):\n"
        "        seen[0] = True\n"
        "        os.replace(replacement, target)\n"
        "sys.addaudithook(audit)\n"
        "result = verify_finalizer_handoff(root, 'abc123', "
        "finalizer_seal(record.value))\n"
        "assert seen[0], 'special-file replacement hook did not run'\n"
        "assert isinstance(result, Err), 'special-file finalizer accepted'\n"
    )
    child = run(
        [sys.executable, "-c", script, str(tmp_path)],
        cwd=tmp_path,
        env={
            **os.environ,
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPATH": str(Path(__file__).resolve().parents[2] / "src"),
        },
        timeout=5,
    )
    assert isinstance(child, Ok), "special-file replacement blocked the finalizer"
    assert child.value.code == 0, child.value.stderr


def test_finalizer_handoff_rejects_equal_byte_replacement(tmp_path: Path) -> None:
    """A finalizer record cannot be swapped after its first identity observation."""
    script = (
        "import os, sys\nfrom pathlib import Path\n"
        "from agentctl.check.steps import (FINALIZER_NAMES, record_finalizers, "
        "finalizer_seal, verify_finalizer_handoff)\n"
        "from agentctl.foundation import Err, Ok\n"
        "root = Path(sys.argv[1]); target = root / 'finalizer-outcomes.json'\n"
        "record = record_finalizers(root, 'abc123', "
        "tuple((name, 0) for name in FINALIZER_NAMES[:-1]))\n"
        "assert isinstance(record, Ok)\n"
        "replacement = root / 'replacement.json'\n"
        "replacement.write_bytes(target.read_bytes())\n"
        "seen = [0]\n"
        "def audit(event, args):\n"
        "    if event == 'open' and str(args[0]) == str(target):\n"
        "        seen[0] += 1\n"
        "        if seen[0] == 2: os.replace(replacement, target)\n"
        "sys.addaudithook(audit)\n"
        "result = verify_finalizer_handoff(root, 'abc123', "
        "finalizer_seal(record.value))\n"
        "assert seen[0] >= 2, 'replacement hook did not run'\n"
        "assert isinstance(result, Err), 'equal-byte finalizer replacement accepted'\n"
    )
    child = run(
        [sys.executable, "-c", script, str(tmp_path)],
        cwd=tmp_path,
        env={
            **os.environ,
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPATH": str(Path(__file__).resolve().parents[2] / "src"),
        },
    )
    assert isinstance(child, Ok)
    assert child.value.code == 0, child.value.stderr


def test_parent_rejects_postcopy_finalizer_tampering(tmp_path: Path) -> None:
    """A real audit hook alters only the copied record before parent verification."""
    script = (
        "import os, sys\nfrom pathlib import Path\n"
        "from agentctl.check import mutant_report\n"
        "from agentctl.check.steps import (CheckRun, FINALIZER_NAMES, finalizer_seal, "
        "killer_seal, provisional_seal, record_finalizers, "
        "record_provisional_phases, retain_verified_gate_output)\n"
        "from agentctl.foundation import Err, Ok\n"
        + _isolate_handoff_after("verify_finalizer_handoff")
        + "base = Path(sys.argv[1]); root = base / 'checkout'; "
        "run_dir = base / 'run'; state = base / 'state'\n"
        "root.mkdir(); run_dir.mkdir()\n"
        "path = run_dir / 'mutant-killers.json'\n"
        'path.write_text(\'{"nonce":"abc123","records":[]}\', encoding=\'utf-8\')\n'
        "killers = mutant_report.read(path, 'abc123')\n"
        "assert isinstance(killers, Ok), killers\n"
        "record = record_finalizers(run_dir, 'abc123', "
        "tuple((name, 0) for name in FINALIZER_NAMES[:-1]))\n"
        "assert isinstance(record, Ok), record\n"
        "phase = record_provisional_phases(run_dir, 'abc123', Err('missing'))\n"
        "assert isinstance(phase, Ok), phase\n"
        "output = killer_seal('abc123', killers.value) + '\\n' + "
        "provisional_seal('abc123', phase.value) + '\\n' + "
        "finalizer_seal(record.value) + '\\n'\n"
        "target = state / 'check-reports' / 'abc123' / 'finalizer-outcomes.json'\n"
        "seen = [False]\n"
        "def audit(event, args):\n"
        "    if (not seen[0] and event == 'open' and str(args[0]) == str(target) "
        "and 'r' in str(args[1]) and target.exists()):\n"
        "        seen[0] = True\n"
        "        with target.open('ab') as stream: stream.write(b' ')\n"
        "sys.addaudithook(audit)\n"
        "result = retain_verified_gate_output(CheckRun(root, run_dir, 'abc123', "
        "sys.argv[2]), state, (output, 'primary\\n'), verify_handoff=True)\n"
        "assert isinstance(result, Err), 'post-copy alteration was accepted'\n"
        "assert seen[0], 'tamper hook did not run'\n"
        "report = state / 'check-reports' / 'abc123'\n"
        "assert 'digest mismatch' in (report / 'finalizer-handoff.txt').read_text()\n"
        "assert (report / 'stderr.txt').read_text() == 'primary\\n'\n"
    )
    family = platform.system()
    assert family in {"Linux", "Darwin", "Windows"}
    child = run(
        [sys.executable, "-c", script, str(tmp_path), family],
        cwd=tmp_path,
        env={
            **os.environ,
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPATH": str(Path(__file__).resolve().parents[2] / "src"),
        },
    )
    assert isinstance(child, Ok)
    assert child.value.code == 0, child.value.stderr


def test_parent_rejects_postcopy_provisional_tampering(tmp_path: Path) -> None:
    """The retained provisional bytes remain tied to the child's observations."""
    script = (
        "import sys\nfrom pathlib import Path\n"
        "from agentctl.check import mutant_report\n"
        "from agentctl.check.steps import (CheckRun, FINALIZER_NAMES, finalizer_seal, "
        "killer_seal, provisional_seal, record_finalizers, "
        "record_provisional_phases, retain_verified_gate_output, "
        "verify_provisional_handoff)\n"
        "from agentctl.foundation import Err, Ok\n"
        + _isolate_handoff_after("verify_provisional_handoff")
        + "base = Path(sys.argv[1]); root = base / 'checkout'; "
        "run_dir = base / 'run'; state = base / 'state'\n"
        "root.mkdir(); run_dir.mkdir()\n"
        "path = run_dir / 'mutant-killers.json'\n"
        'path.write_text(\'{"nonce":"abc123","records":[]}\', encoding=\'utf-8\')\n'
        "killers = mutant_report.read(path, 'abc123')\n"
        "final = record_finalizers(run_dir, 'abc123', "
        "tuple((name, 0) for name in FINALIZER_NAMES[:-1]))\n"
        "phase = record_provisional_phases(run_dir, 'abc123', Err('missing'))\n"
        "assert isinstance(killers, Ok) and isinstance(final, Ok) "
        "and isinstance(phase, Ok)\n"
        "output = killer_seal('abc123', killers.value) + '\\n' + "
        "provisional_seal('abc123', phase.value) + '\\n' + "
        "finalizer_seal(final.value) + '\\n'\n"
        "assert verify_provisional_handoff(run_dir, 'abc123', output) == Ok(None)\n"
        "assert isinstance(verify_provisional_handoff(run_dir, 'abc123', "
        "output + output), Err), 'ambiguous provisional seal was accepted'\n"
        "target = state / 'check-reports' / 'abc123' / 'provisional-phases.json'\n"
        "seen = [False]\n"
        "def audit(event, args):\n"
        "    if (not seen[0] and event == 'open' and str(args[0]) == str(target) "
        "and 'r' in str(args[1]) and target.exists()):\n"
        "        seen[0] = True\n"
        "        with target.open('wb') as stream: stream.write("
        'b\'{"nonce": "abc123", "reason": "other", '
        '"status": "unavailable"}\')\n'
        "sys.addaudithook(audit)\n"
        "result = retain_verified_gate_output(CheckRun(root, run_dir, 'abc123', "
        "sys.argv[2]), state, (output, 'primary\\n'), verify_handoff=True)\n"
        "assert isinstance(result, Err), 'post-copy provisional alteration accepted'\n"
        "assert seen[0], 'provisional tamper hook did not run'\n"
        "report = state / 'check-reports' / 'abc123'\n"
        "assert 'provisional handoff digest mismatch' in "
        "(report / 'finalizer-handoff.txt').read_text()\n"
        "assert (report / 'stderr.txt').read_text() == 'primary\\n'\n"
    )
    family = platform.system()
    assert family in {"Linux", "Darwin", "Windows"}
    child = run(
        [sys.executable, "-c", script, str(tmp_path), family],
        cwd=tmp_path,
        env={
            **os.environ,
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPATH": str(Path(__file__).resolve().parents[2] / "src"),
        },
    )
    assert isinstance(child, Ok)
    assert child.value.code == 0, child.value.stderr


def test_parent_rejects_postcopy_mutant_report_tampering(tmp_path: Path) -> None:
    """A changed retained killer report cannot accompany a passing finalizer."""
    script = (
        "import sys\nfrom pathlib import Path\n"
        "from agentctl.check import mutant_report\n"
        "from agentctl.check.steps import (CheckRun, FINALIZER_NAMES, finalizer_seal, "
        "killer_seal, provisional_seal, record_finalizers, record_provisional_phases, "
        "retain_verified_gate_output, verify_killer_handoff)\n"
        "from agentctl.foundation import Err, Ok\n"
        + _isolate_handoff_after("verify_killer_handoff")
        + "base = Path(sys.argv[1]); root = base / 'checkout'; "
        "run_dir = base / 'run'; state = base / 'state'\n"
        "root.mkdir(); run_dir.mkdir()\n"
        "path = run_dir / 'mutant-killers.json'\n"
        'path.write_text(\'{"nonce":"abc123","records":[]}\', encoding=\'utf-8\')\n'
        "report = mutant_report.read(path, 'abc123')\n"
        "final = record_finalizers(run_dir, 'abc123', "
        "tuple((name, 0) for name in FINALIZER_NAMES[:-1]))\n"
        "phase = record_provisional_phases(run_dir, 'abc123', Err('missing'))\n"
        "assert isinstance(report, Ok) and isinstance(final, Ok) "
        "and isinstance(phase, Ok)\n"
        "output = killer_seal('abc123', report.value) + '\\n' + "
        "provisional_seal('abc123', phase.value) + '\\n' + "
        "finalizer_seal(final.value) + '\\n'\n"
        "assert verify_killer_handoff(run_dir, 'abc123', output) == Ok(None)\n"
        "assert isinstance(verify_killer_handoff(run_dir, 'abc123', "
        "killer_seal('abc123', report.value) + '\\n' + output), Err)\n"
        "target = state / 'check-reports' / 'abc123' / 'mutant-killers.json'\n"
        "trigger = state / 'check-reports' / 'abc123' / 'finalizer-outcomes.json'\n"
        "seen = [False]\n"
        "def audit(event, args):\n"
        "    if (not seen[0] and event == 'open' and str(args[0]) == str(trigger) "
        "and 'r' in str(args[1]) and target.exists()):\n"
        "        seen[0] = True\n"
        "        with target.open('ab') as stream: stream.write(b' ')\n"
        "sys.addaudithook(audit)\n"
        "result = retain_verified_gate_output(CheckRun(root, run_dir, 'abc123', "
        "sys.argv[2]), state, (output, 'primary\\n'), verify_handoff=True)\n"
        "assert isinstance(result, Err), "
        "'post-copy mutant report alteration accepted'\n"
        "assert seen[0], 'mutant report tamper hook did not run'\n"
        "report_dir = state / 'check-reports' / 'abc123'\n"
        "assert 'mutant killer handoff digest mismatch' in "
        "(report_dir / 'finalizer-handoff.txt').read_text()\n"
        "assert (report_dir / 'stderr.txt').read_text() == 'primary\\n'\n"
    )
    family = platform.system()
    assert family in {"Linux", "Darwin", "Windows"}
    child = run(
        [sys.executable, "-c", script, str(tmp_path), family],
        cwd=tmp_path,
        env={
            **os.environ,
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPATH": str(Path(__file__).resolve().parents[2] / "src"),
        },
    )
    assert isinstance(child, Ok)
    assert child.value.code == 0, child.value.stderr


def test_parent_rejects_changed_live_provisional_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A changed live record fails before the parent copies its report."""
    root, run_dir, state = (tmp_path / name for name in ("checkout", "run", "state"))
    root.mkdir()
    run_dir.mkdir()
    final = steps.record_finalizers(
        run_dir, "abc123", tuple((name, 0) for name in steps.FINALIZER_NAMES[:-1])
    )
    phase = steps.record_provisional_phases(run_dir, "abc123", Err("missing"))
    assert isinstance(final, Ok)
    assert isinstance(phase, Ok)
    output = (
        steps.provisional_seal("abc123", phase.value)
        + "\n"
        + steps.finalizer_seal(final.value)
        + "\n"
    )
    (run_dir / "provisional-phases.json").write_bytes(phase.value + b" ")
    monkeypatch.setattr(
        steps, "run_observed", lambda *_args, **_kwargs: Ok(Output(0, output, ""))
    )
    family = platform.system()
    assert family in {"Linux", "Darwin", "Windows"}
    assert (
        _run_check_child(
            CheckRun(root, run_dir, "abc123", family), state, assume_yes=False
        )
        == 1
    )
    stderr = (state / "check-reports/abc123/stderr.txt").read_text(encoding="utf-8")
    assert "provisional handoff digest mismatch" in stderr, (
        "parent accepted changed live provisional record"
    )


def test_parent_rejects_changed_live_mutant_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A changed live killer report fails before the parent copies its report."""
    root, run_dir, state = (tmp_path / name for name in ("checkout", "run", "state"))
    root.mkdir()
    run_dir.mkdir()
    path = run_dir / "mutant-killers.json"
    path.write_text('{"nonce":"abc123","records":[]}', encoding="utf-8")
    original = mutant_report.read(path, "abc123")
    final = steps.record_finalizers(
        run_dir, "abc123", tuple((name, 0) for name in steps.FINALIZER_NAMES[:-1])
    )
    phase = steps.record_provisional_phases(run_dir, "abc123", Err("missing"))
    assert isinstance(original, Ok)
    assert isinstance(final, Ok)
    assert isinstance(phase, Ok)
    output = "\n".join(
        (
            steps.killer_seal("abc123", original.value),
            steps.provisional_seal("abc123", phase.value),
            steps.finalizer_seal(final.value),
            "",
        )
    )
    assert isinstance(
        steps.verify_killer_handoff(
            run_dir, "abc123", "\n".join(output.splitlines()[1:])
        ),
        Err,
    ), "missing mutant killer handoff was accepted"
    path.write_text(' {"nonce":"abc123","records":[]}', encoding="utf-8")
    monkeypatch.setattr(
        steps, "run_observed", lambda *_args, **_kwargs: Ok(Output(0, output, ""))
    )
    family = platform.system()
    assert family in {"Linux", "Darwin", "Windows"}
    assert (
        _run_check_child(
            CheckRun(root, run_dir, "abc123", family), state, assume_yes=False
        )
        == 1
    )
    stderr = (state / "check-reports/abc123/stderr.txt").read_text(encoding="utf-8")
    assert "mutant killer handoff digest mismatch" in stderr, (
        "parent accepted changed live mutant report"
    )


def test_failed_mutant_finalizer_preserves_partial_handoff(tmp_path: Path) -> None:
    """A failed killer finalizer retains its failure without requiring a false seal."""
    statuses = tuple(
        (name, int(name == "mutant-killers")) for name in steps.FINALIZER_NAMES[:-1]
    )
    assert isinstance(steps.record_finalizers(tmp_path, "abc123", statuses), Ok)
    output = steps.finalizer_seal(steps.evidence.LegEvidence("abc123", statuses))
    assert steps.verify_killer_handoff(tmp_path, "abc123", output) == Ok(None)


def test_check_parent_retains_missing_finalizer_handoff(tmp_path: Path) -> None:
    """An early child failure and its missing handoff remain in the report."""
    root, run_dir, state = (tmp_path / name for name in ("checkout", "run", "state"))
    root.mkdir()
    run_dir.mkdir()
    family = platform.system()
    assert family in {"Linux", "Darwin", "Windows"}
    context = CheckRun(root, run_dir, "abc123", family)
    assert _run_check_child(context, state, assume_yes=False) == 1
    stderr = (state / "check-reports/abc123/stderr.txt").read_text(encoding="utf-8")
    assert "finalizer handoff: missing or ambiguous finalizer handoff" in stderr, (
        "parent did not retain missing handoff failure"
    )


def test_successful_child_cannot_hide_failed_finalizers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A zero child exit cannot authorize evidence after finalizer failures."""
    root, run_dir, state = (tmp_path / name for name in ("checkout", "run", "state"))
    root.mkdir()
    run_dir.mkdir()
    statuses = tuple((name, 1) for name in steps.FINALIZER_NAMES[:-1])
    final = steps.record_finalizers(run_dir, "abc123", statuses)
    phase = steps.record_provisional_phases(run_dir, "abc123", Err("unavailable"))
    assert isinstance(final, Ok)
    assert isinstance(phase, Ok)
    output = "\n".join(
        (
            "EVIDENCE example",
            steps.provisional_seal("abc123", phase.value),
            steps.finalizer_seal(final.value),
            "",
        )
    )
    monkeypatch.setattr(
        steps,
        "run_observed",
        lambda *_args, **_kwargs: Ok(Output(0, output, "primary\n")),
    )
    family = platform.system()
    assert family in {"Linux", "Darwin", "Windows"}
    context = CheckRun(root, run_dir, "abc123", family)
    assert _run_check_child(context, state, assume_yes=False) == 1, (
        "successful child hid failed finalizers"
    )
    stdout = capsys.readouterr().out
    assert not any(line.startswith("EVIDENCE ") for line in stdout.splitlines())
    stderr = (state / "check-reports/abc123/stderr.txt").read_text(encoding="utf-8")
    assert "successful child has failed finalizers" in stderr, (
        "successful child hid failed finalizers"
    )
    assert "primary" in stderr
    changed = replace(final.value, outcomes=tuple((name, 0) for name, _ in statuses))
    monkeypatch.setattr(steps, "finalizer_observation", lambda *_args: Ok(changed))
    assert not steps.__dict__["_successful_child_finalizers"](context, output), (
        "successful child accepted changed finalizer statuses"
    )


def test_gate_reports_are_retained_outside_checkout(tmp_path: Path) -> None:
    """Retain exact streams once and refuse checkout or reused report paths."""
    root = tmp_path / "checkout"
    state = tmp_path / "state"
    run_dir = tmp_path / "run"
    root.mkdir()
    run_dir.mkdir()
    (run_dir / "pytest-manifest.json").write_bytes(b"current manifest")
    (run_dir / "mutant-killers.json").write_bytes(b"killer outcomes")
    (run_dir / "host.json").write_bytes(b"current host")
    (run_dir / "bootstrap-host.json").write_bytes(b"bootstrap host")
    (run_dir / "oracle-outcomes.json").write_bytes(b"oracle outcomes")
    (run_dir / "oracle-details.json").write_bytes(b"oracle details")
    (run_dir / "tool-substeps.json").write_bytes(b"tool substeps")
    (run_dir / "finalizer-outcomes.json").write_bytes(b"finalizer outcomes")
    (run_dir / "provisional-phases.json").write_bytes(b"provisional phases")
    (run_dir / "coverage").write_bytes(b"coverage data")
    (run_dir / "coverage-report.json").write_bytes(b"coverage record")
    (run_dir / "coverage-raw.json").write_bytes(b"coverage report")
    result = retain_gate_output(
        root, state, run_dir, "abc123", ("success \u2713\n", "failure\n")
    )
    assert isinstance(result, Ok)
    assert (result.value / "stdout.txt").read_text(
        encoding="utf-8"
    ) == "success \u2713\n"
    assert (result.value / "stderr.txt").read_text(encoding="utf-8") == "failure\n"
    assert (result.value / "pytest-manifest.json").read_bytes() == b"current manifest"
    assert (result.value / "mutant-killers.json").is_file(), (
        "mutant killer outcomes were not retained"
    )
    assert (result.value / "mutant-killers.json").read_bytes() == b"killer outcomes"
    assert (result.value / "host.json").is_file(), "host observation was not retained"
    assert (result.value / "host.json").read_bytes() == b"current host"
    for name, contents in (
        ("bootstrap-host.json", b"bootstrap host"),
        ("oracle-outcomes.json", b"oracle outcomes"),
        ("oracle-details.json", b"oracle details"),
    ):
        assert (result.value / name).is_file(), "oracle evidence was not retained"
        assert (result.value / name).read_bytes() == contents
    assert (result.value / "coverage").read_bytes() == b"coverage data"
    assert (result.value / "coverage-report.json").is_file(), (
        "coverage record was not retained"
    )
    assert (result.value / "coverage-report.json").read_bytes() == b"coverage record"
    assert (result.value / "coverage-raw.json").is_file(), (
        "raw coverage report was not retained"
    )
    assert (result.value / "coverage-raw.json").read_bytes() == b"coverage report"
    assert (result.value / "tool-substeps.json").is_file(), (
        "tool substeps were not retained"
    )
    assert (result.value / "tool-substeps.json").read_bytes() == b"tool substeps"
    assert (result.value / "finalizer-outcomes.json").is_file(), (
        "finalizer outcomes were not retained"
    )
    assert (
        result.value / "finalizer-outcomes.json"
    ).read_bytes() == b"finalizer outcomes"
    assert (result.value / "provisional-phases.json").is_file(), (
        "provisional phase record was not retained"
    )
    assert (
        result.value / "provisional-phases.json"
    ).read_bytes() == b"provisional phases"
    assert isinstance(
        retain_gate_output(root, state, run_dir, "abc123", ("new", "")), Err
    )
    assert isinstance(
        retain_gate_output(root, root / "state", run_dir, "beef", ("", "")), Err
    )
    assert isinstance(
        retain_gate_output(root, run_dir / "state", run_dir, "beef", ("", "")), Err
    )
    assert isinstance(
        retain_gate_output(root, state, run_dir, "../escape", ("", "")), Err
    )
    (run_dir / "tool-outcomes.json").mkdir()
    damaged = retain_gate_output(root, state, run_dir, "def456", ("primary", "error"))
    assert isinstance(damaged, Err)
    assert "not a file" in damaged.error
    assert (state / "check-reports/def456/stdout.txt").read_text(
        encoding="utf-8"
    ) == "primary"
    assert (state / "check-reports/def456/stderr.txt").read_text(
        encoding="utf-8"
    ) == "error"


def test_gate_preserves_primary_and_cleanup_failures(
    root: Path, tmp_path: Path
) -> None:
    """An actual cleanup veto cannot replace the original process failure."""
    script = (
        "import sys\nfrom agentctl.check.steps import check\n"
        "def audit(event, args):\n"
        "    if event == 'subprocess.Popen': raise OSError('owned spawn veto')\n"
        "    if event == 'os.rmdir': raise OSError('owned cleanup veto')\n"
        "sys.addaudithook(audit)\n"
        "sys.exit(0 if check(sys.argv[1]) == 1 else 1)\n"
    )
    result = run(
        [sys.executable, "-c", script, platform.system()],
        cwd=root,
        env={
            **os.environ,
            "XDG_STATE_HOME": str(tmp_path / "state"),
            "TEMP": str(tmp_path),
            "TMP": str(tmp_path),
            "TMPDIR": str(tmp_path),
            "PYTHONUTF8": "1",
            "PYTHONIOENCODING": "utf-8",
        },
    )
    assert isinstance(result, Ok)
    assert result.value.code == 0, result.value.stderr
    assert "owned spawn veto" in result.value.stderr
    assert "owned cleanup veto" in result.value.stderr
    reports = tuple((tmp_path / "state/agentctl/check-reports").glob("*/stderr.txt"))
    assert len(reports) == 1
    assert "owned spawn veto" in reports[0].read_text(encoding="utf-8")
    assert "owned cleanup veto" in (reports[0].parent / "cleanup.txt").read_text(
        encoding="utf-8"
    )


def test_gate_publishes_evidence_only_after_cleanup(root: Path, tmp_path: Path) -> None:
    """The public gate waits for real temporary-root cleanup before evidence."""
    script = """
import sys
from pathlib import Path
from agentctl.check import steps
from agentctl.foundation import Ok
report = Path(sys.argv[3]); report.mkdir()
streams = ("EVIDENCE example\\nPHASE example\\n", "primary diagnostic\\n")
(report / "stdout.txt").write_bytes(streams[0].encode("utf-8"))
(report / "stderr.txt").write_bytes(streams[1].encode("utf-8"))
artifact = report / "host.json"; artifact.write_bytes(b"original evidence")
snapshot = steps.retained_report_snapshot(report, streams)
assert isinstance(snapshot, Ok)
interpreter = steps.gate_interpreter_identity(Path(sys.executable))
assert isinstance(interpreter, Ok)
result = steps.CheckChildResult(0, streams, Ok(report), True,
    snapshot.value, interpreter.value)
steps._observe_check_child = lambda *_args, **_kwargs: result
def audit(event, args):
    if event == "os.rmdir":
        print("cleanup-observed", flush=True)
        if sys.argv[2] == "fail":
            raise OSError("owned cleanup veto")
        if sys.argv[2] == "tamper-artifact":
            artifact.write_bytes(b"changed evidence")
        if sys.argv[2] == "tamper-stdout":
            (report / "stdout.txt").write_bytes(b"changed stdout")
        if sys.argv[2] == "tamper-stderr":
            (report / "stderr.txt").write_bytes(b"changed stderr")
sys.addaudithook(audit)
sys.exit(steps.check(sys.argv[1]))
"""
    for mode in ("pass", "fail", "tamper-artifact", "tamper-stdout", "tamper-stderr"):
        result = run(
            [
                sys.executable,
                "-c",
                script,
                platform.system(),
                mode,
                str(tmp_path / ("report-" + mode)),
            ],
            cwd=root,
            env={
                **os.environ,
                "XDG_STATE_HOME": str(tmp_path / ("state-" + mode)),
                "TEMP": str(tmp_path),
                "TMP": str(tmp_path),
                "TMPDIR": str(tmp_path),
                "PYTHONUTF8": "1",
                "PYTHONIOENCODING": "utf-8",
            },
        )
        assert isinstance(result, Ok), result
        lines = result.value.stdout.splitlines()
        assert "cleanup-observed" in lines, "created run identity was not retained"
        assert "primary diagnostic" in result.value.stderr
        assert not any(line.startswith("PHASE ") for line in lines), (
            "unverified phase evidence was published"
        )
        if mode == "pass":
            assert result.value.code == 0
            assert lines.index("cleanup-observed") < lines.index("EVIDENCE example"), (
                "evidence was published before cleanup"
            )
        elif mode == "fail":
            assert result.value.code == 1
            assert not any(line.startswith("EVIDENCE ") for line in lines), (
                "evidence survived failed cleanup"
            )
            assert "withheld unverified: EVIDENCE example" in lines
            assert "owned cleanup veto" in result.value.stderr
        else:
            assert result.value.code == 1, "changed retained report returned success"
            assert not any(line.startswith("EVIDENCE ") for line in lines), (
                "evidence survived changed retained report"
            )
            assert "withheld unverified: EVIDENCE example" in lines
            assert "retained report changed after verification" in result.value.stderr


def _cleanup_context(checkout: Path, directory: Path, family: str) -> CheckRun:
    """Capture the created run's native identity for its owned cleanup."""
    assert family in {"Linux", "Darwin", "Windows"}
    info = directory.lstat()
    return CheckRun(checkout, directory, "fresh", family, (info.st_dev, info.st_ino))


def test_cleanup_refuses_live_observer_and_foreign_root(tmp_path: Path) -> None:
    """A registered live process or wrong boundary retains the owned tree."""
    family = platform.system()
    assert family in {"Linux", "Darwin", "Windows"}
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    temporary = tmp_path / "temporary"
    temporary.mkdir()
    run_dir = temporary / "agentctl-check-owned"
    run_dir.mkdir()
    observers = run_dir / "observers"
    observers.mkdir()
    record = observers / "live.json"
    record.write_text(
        json.dumps({"nonce": "fresh", "pid": os.getpid()}), encoding="utf-8"
    )
    context = _cleanup_context(checkout, run_dir, family)
    assert isinstance(cleanup_run_root(context, temporary), Err)
    assert record.is_file()
    assert isinstance(cleanup_run_root(context, tmp_path), Err)
    assert record.is_file()
    record.unlink()
    assert cleanup_run_root(context, temporary) == Ok(None)
    assert not run_dir.exists()


def test_cleanup_refuses_linked_run_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A junction or symlink cannot redirect cleanup into another run."""
    family = platform.system()
    assert family in {"Linux", "Darwin", "Windows"}
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    temporary = tmp_path / "temporary"
    temporary.mkdir()
    other = temporary / "agentctl-check-other"
    other.mkdir()
    sentinel = other / "preserve.txt"
    sentinel.write_text("keep", encoding="utf-8")

    def refuse_removal(*_args: object) -> None:
        pytest.fail("junction cleanup reached removal")

    with monkeypatch.context() as control:
        control.setattr(Path, "is_junction", lambda path: path == other)
        control.setattr(shutil, "rmtree", refuse_removal)
        assert isinstance(
            cleanup_run_root(_cleanup_context(checkout, other, family), temporary), Err
        ), "junction run root was accepted"
    alias = temporary / "agentctl-check-owned"
    if family == "Windows":
        command = Path(os.environ["SYSTEMROOT"]) / "System32" / "cmd.exe"
        created = run(
            [str(command), "/c", "mklink", "/J", str(alias), str(other)],
            cwd=tmp_path,
            env=os.environ,
        )
        assert isinstance(created, Ok), created
        assert created.value.code == 0, created.value.stderr
        assert alias.is_junction()
    else:
        alias.symlink_to(other, target_is_directory=True)
        assert alias.is_symlink()
    try:
        with monkeypatch.context() as control:
            control.setattr(shutil, "rmtree", refuse_removal)
            assert isinstance(
                cleanup_run_root(_cleanup_context(checkout, alias, family), temporary),
                Err,
            ), "linked run root was accepted"
        assert sentinel.read_text(encoding="utf-8") == "keep"
    finally:
        if alias.is_junction():
            alias.rmdir()
        elif alias.is_symlink():
            alias.unlink()


def test_cleanup_refuses_replaced_run_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A different directory cannot inherit an existing run's cleanup authority."""
    family = platform.system()
    assert family in {"Linux", "Darwin", "Windows"}
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    temporary = tmp_path / "temporary"
    temporary.mkdir()
    run_dir = temporary / "agentctl-check-owned"
    replacement = temporary / "replacement"
    saved = temporary / "saved"
    run_dir.mkdir()
    replacement.mkdir()
    sentinel = replacement / "preserve.txt"
    sentinel.write_text("keep", encoding="utf-8")
    context = _cleanup_context(checkout, run_dir, family)

    def refuse_unidentified(*_args: object) -> None:
        pytest.fail("unidentified run root reached removal")

    with monkeypatch.context() as control:
        control.setattr(shutil, "rmtree", refuse_unidentified)
        assert isinstance(
            cleanup_run_root(CheckRun(checkout, run_dir, "fresh", family), temporary),
            Err,
        ), "cleanup accepted a run without captured identity"

    def replace_during_containment(*_args: object) -> Ok[None]:
        assert run_dir.resolve().parent == temporary.resolve()
        assert replacement.resolve().parent == temporary.resolve()
        assert saved.parent.resolve() == temporary.resolve()
        run_dir.rename(saved)
        replacement.rename(run_dir)
        return Ok(None)

    def refuse_removal(*_args: object) -> None:
        pytest.fail("replaced run root reached removal")

    monkeypatch.setattr(steps.writeguard, "containment", replace_during_containment)
    monkeypatch.setattr(shutil, "rmtree", refuse_removal)
    assert isinstance(cleanup_run_root(context, temporary), Err), (
        "replaced run root was accepted"
    )
    assert (run_dir / "preserve.txt").read_text(encoding="utf-8") == "keep"
    assert saved.is_dir()


def test_cleanup_handles_deep_owned_run(tmp_path: Path) -> None:
    """A fully contained run can be removed even with deep Windows paths."""
    family = platform.system()
    assert family in {"Linux", "Darwin", "Windows"}
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    temporary = tmp_path / "temporary"
    temporary.mkdir()
    run_dir = temporary / "agentctl-check-owned"
    run_dir.mkdir()
    extended = filesystem_path(run_dir)
    deep = extended.joinpath(*(["segment0123456789"] * 14))
    deep.mkdir(parents=True)
    leaf = deep / "owned.txt"
    leaf.write_text("owned", encoding="utf-8")
    windows_legacy_limit = 260
    assert len(str(leaf)) > windows_legacy_limit
    assert cleanup_run_root(
        _cleanup_context(checkout, run_dir, family), temporary
    ) == Ok(None)
    assert not run_dir.exists()


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


def test_finalizer_consumers_reject_changed_statuses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every parent consumer must bind its own finalizer status read."""
    nonce = "a" * 32
    context = steps.CheckRun(tmp_path, tmp_path, nonce, "Linux")
    original = steps.evidence.LegEvidence(
        nonce, tuple((name, 0) for name in steps.FINALIZER_NAMES[:-1])
    )
    changed = steps.evidence.LegEvidence(
        nonce, tuple((name, 1) for name in steps.FINALIZER_NAMES[:-1])
    )
    output = steps.finalizer_seal(original)
    monkeypatch.setattr(steps, "finalizer_observation", lambda *_args: Ok(original))
    assert steps.sealed_finalizer_observation(tmp_path, nonce, output) == Ok(original)
    assert isinstance(steps.sealed_finalizer_observation(tmp_path, nonce, ""), Err)
    assert isinstance(
        steps.sealed_finalizer_observation(tmp_path, nonce, output + "\n" + output), Err
    )
    monkeypatch.setattr(steps, "finalizer_observation", lambda *_args: Ok(changed))
    calls = (
        (
            "phase identity",
            lambda: steps.__dict__["_provisional_values_for_identity"](
                context, tmp_path, output
            ),
        ),
        (
            "collection",
            lambda: steps.verify_provisional_collection(context, tmp_path, output),
        ),
        ("oracle", lambda: steps.verify_provisional_oracle(context, tmp_path, output)),
        ("host", lambda: steps.verify_provisional_host(context, tmp_path, output)),
        ("tools", lambda: steps.verify_provisional_tools(context, tmp_path, output)),
        (
            "coverage",
            lambda: steps.verify_provisional_coverage(context, tmp_path, output),
        ),
        ("static", lambda: steps.verify_provisional_static(context, tmp_path, output)),
        ("source", lambda: steps.verify_provisional_source(context, tmp_path, output)),
        (
            "prerequisites",
            lambda: steps.verify_provisional_prerequisites(context, tmp_path, output),
        ),
        (
            "validation",
            lambda: steps.verify_provisional_validation(context, tmp_path, output),
        ),
        (
            "killer handoff",
            lambda: steps.verify_killer_handoff(tmp_path, nonce, output),
        ),
        (
            "coverage handoff",
            lambda: steps.verify_coverage_handoff(tmp_path, nonce, output),
        ),
        (
            "ruff handoff",
            lambda: steps.verify_ruff_handoff(tmp_path, nonce, output, tmp_path),
        ),
        (
            "format handoff",
            lambda: steps.verify_ruff_format_handoff(tmp_path, nonce, output, tmp_path),
        ),
        (
            "coverage text agreement",
            lambda: steps.coverage_text_retained_agreement(
                context, tmp_path, output, b""
            ),
        ),
        (
            "coverage text handoff",
            lambda: steps.verify_coverage_text_handoff(context, tmp_path, output),
        ),
        (
            "ty handoff",
            lambda: steps.verify_ty_handoff(tmp_path, nonce, output, tmp_path),
        ),
        (
            "native handoff",
            lambda: steps.verify_native_handoff(context, tmp_path, output),
        ),
        ("host handoff", lambda: steps.verify_host_handoff(tmp_path, nonce, output)),
        (
            "oracle handoff",
            lambda: steps.verify_oracle_handoff(tmp_path, nonce, output),
        ),
        (
            "pytest handoff",
            lambda: steps.verify_pytest_handoff(tmp_path, nonce, output),
        ),
        (
            "tool handoff",
            lambda: steps.verify_tool_results_handoff(tmp_path, nonce, output),
        ),
        (
            "command handoff",
            lambda: steps.verify_python_commands_handoff(
                tmp_path, nonce, output, tmp_path
            ),
        ),
    )
    for name, call in calls:
        assert call() == Err("finalizer observation changed after handoff"), (
            "changed finalizer accepted by " + name
        )


def test_parent_refuses_omitted_finalizer_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Reject a sealed phase observation that hides shared finalizer damage."""
    root, directory = tmp_path / "root", tmp_path / "run"
    root.mkdir()
    directory.mkdir()
    nonce = "a" * 32
    statuses = tuple((name, 1) for name in steps.FINALIZER_NAMES[:-1])
    final = steps.record_finalizers(directory, nonce, statuses)
    assert isinstance(final, Ok)
    initial = (
        steps.phase_reports.PhaseResult(0, "b" * 64, frozenset({"unverified-run"})),
        steps.phase_reports.PhaseResult(1, "c" * 64, frozenset({"unverified-run"})),
    )
    damaged = steps.provisional_finalizer_failures(
        Ok(initial), (*statuses, ("finalizer-record", 0))
    )
    assert isinstance(damaged, Ok)
    recorded = steps.record_provisional_phases(directory, nonce, damaged)
    assert isinstance(recorded, Ok)
    output = (
        steps.provisional_seal(nonce, recorded.value)
        + "\n"
        + steps.finalizer_seal(final.value)
        + "\n"
    )
    assert steps.verify_provisional_finalizers(directory, nonce, output) == Ok(None)
    context = steps.CheckRun(root, directory, nonce, "Linux")
    retained = steps.retain_verified_gate_output(
        context, tmp_path / "valid-state", (output, "primary\n"), verify_handoff=True
    )
    assert isinstance(retained, Ok), retained
    forged_phase = replace(
        damaged.value[0],
        failures=damaged.value[0].failures - {"shared finalizer failed: ratchet"},
    )
    forged = steps.provisional_phase_record(nonce, Ok((forged_phase, damaged.value[1])))
    assert isinstance(forged, Ok)
    (directory / "provisional-phases.json").write_bytes(forged.value)
    forged_output = (
        steps.provisional_seal(nonce, forged.value)
        + "\n"
        + steps.finalizer_seal(final.value)
        + "\n"
    )
    assert isinstance(
        steps.verify_provisional_finalizers(directory, nonce, forged_output), Err
    ), "parent accepted hidden finalizer failure"
    rejected = steps.retain_verified_gate_output(
        context,
        tmp_path / "forged-state",
        (forged_output, "primary\n"),
        verify_handoff=True,
    )
    assert isinstance(rejected, Err), (
        "retained parent accepted hidden finalizer failure"
    )
    monkeypatch.setattr(
        steps,
        "run_observed",
        lambda *_args, **_kwargs: Ok(FoundationOutput(1, forged_output, "primary\n")),
    )
    live = steps.__dict__["_observe_check_child"](
        context, tmp_path / "live-state", assume_yes=False
    )
    assert "finalizer handoff: phase finalizer failures differ" in live.streams[1], (
        "live parent accepted hidden finalizer failure"
    )
    assert not live.trusted
    assert "primary\n" in live.streams[1]
    changed = replace(
        final.value,
        outcomes=tuple(
            (name, 0 if name == "ratchet" else code)
            for name, code in final.value.outcomes
        ),
    )

    def install_swap(verified_reads: int) -> None:
        count = 0

        def observed(*_args: object) -> Result[steps.evidence.LegEvidence, str]:
            nonlocal count
            count += 1
            return Ok(final.value if count <= verified_reads else changed)

        monkeypatch.setattr(steps, "finalizer_observation", observed)

    install_swap(1)
    assert isinstance(
        steps.verify_provisional_finalizers(directory, nonce, forged_output), Err
    ), "changed finalizer after seal was accepted"
    install_swap(2)
    changed_retained = steps.retain_verified_gate_output(
        context,
        tmp_path / "changed-state",
        (forged_output, "primary\n"),
        verify_handoff=True,
    )
    assert isinstance(changed_retained, Err), (
        "retained parent accepted a changed finalizer after seal"
    )
    changed_directory = tmp_path / "changed-live-run"
    changed_directory.mkdir()
    for name in ("finalizer-outcomes.json", "provisional-phases.json"):
        (changed_directory / name).write_bytes((directory / name).read_bytes())
    install_swap(2)
    changed_live = steps.__dict__["_observe_check_child"](
        replace(context, directory=changed_directory),
        tmp_path / "changed-live-state",
        assume_yes=False,
    )
    assert (
        "phase finalizer observations unavailable or changed" in changed_live.streams[1]
    ), "live parent accepted a changed finalizer after seal"
