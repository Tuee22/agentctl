# Copyright (c) 2026 agentctl contributors.
"""Real operating-system errors, owned children and file-lock contention."""

import json
import os
import platform
import secrets
import shutil
import sys
import time
from pathlib import Path

import coverage
import pytest

from agentctl import process
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
from agentctl.foundation_process_values import ByteOutput, SpawnError
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
from agentctl.result import Err, Ok

pytestmark = pytest.mark.evidence("real")


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


def test_parent_rejects_postcopy_finalizer_tampering(tmp_path: Path) -> None:
    """A real audit hook alters only the copied record before parent verification."""
    script = (
        "import os, sys\nfrom pathlib import Path\n"
        "from agentctl.check import mutant_report\n"
        "from agentctl.check.steps import (CheckRun, FINALIZER_NAMES, finalizer_seal, "
        "killer_seal, provisional_seal, record_finalizers, "
        "record_provisional_phases, retain_verified_gate_output)\n"
        "from agentctl.foundation import Err, Ok\n"
        "base = Path(sys.argv[1]); root = base / 'checkout'; "
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
        "base = Path(sys.argv[1]); root = base / 'checkout'; "
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
        "base = Path(sys.argv[1]); root = base / 'checkout'; "
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
        "output + output), Err)\n"
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
        steps, "run", lambda *_args, **_kwargs: Ok(Output(0, output, ""))
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
        steps, "run", lambda *_args, **_kwargs: Ok(Output(0, output, ""))
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
    assert steps.verify_killer_handoff(tmp_path, "abc123", "") == Ok(None)


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
    context = CheckRun(checkout, run_dir, "fresh", family)
    assert isinstance(cleanup_run_root(context, temporary), Err)
    assert record.is_file()
    assert isinstance(cleanup_run_root(context, tmp_path), Err)
    assert record.is_file()
    record.unlink()
    assert cleanup_run_root(context, temporary) == Ok(None)
    assert not run_dir.exists()


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
        CheckRun(checkout, run_dir, "fresh", family), temporary
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
