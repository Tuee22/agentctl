# Copyright (c) 2026 agentctl contributors.
"""Real disposable trees, refs, distributions and process leaks test the guard."""

import json
import os
import platform
import secrets
import shutil
import stat
import sys
import sysconfig
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from agentctl.check.evidence import read_legs
from agentctl.check.mutants import scratch
from agentctl.check.process_identity import linux_birth_stat
from agentctl.check.steps import CheckRun, finalize, finalize_observed, verify_baseline
from agentctl.check.steps import environment as child_environment
from agentctl.check.writeguard import (
    Snapshot,
    compare,
    containment,
    environment,
    filesystem_path,
    recorded_files,
    refs,
    same_process_birth,
    snapshot,
    socket_check,
    tree,
)
from agentctl.paths import Family
from agentctl.process import alive, process_birth, registered_alive, run, start, stop
from agentctl.result import Err, Ok
from tests.harness.git import repository


@pytest.mark.evidence("value")
def test_process_birth_identifies_reuse() -> None:
    """Missing or changed native birth cannot identify the registered process."""
    assert same_process_birth(100, 100)
    assert not same_process_birth(100, 101), (
        "reused process identity was treated as owned"
    )
    assert not same_process_birth(100, None)


@pytest.mark.evidence("value")
def test_linux_birth_parses_kernel_stat() -> None:
    """Start ticks remain identifiable despite arbitrary process-name bytes."""
    sample = b"123 (odd )\xff) S" + b" 0" * 18 + b" 42\n"
    assert linux_birth_stat(sample, 123) == Ok(42), "Linux process start time differs"
    for malformed in (
        b"",
        sample.replace(b"123 (", b"124 ("),
        sample[:-3],
        sample.replace(b" 42\n", b" -1\n"),
    ):
        assert isinstance(linux_birth_stat(malformed, 123), Err), (
            "invalid Linux process identity was accepted"
        )


def _family() -> Family:
    """Pass the observed native family to the typed gate coordinator."""
    family = platform.system()
    assert family in {"Linux", "Darwin", "Windows"}
    return family


@pytest.mark.evidence("real")
def test_containment_handles_deep_run_paths(tmp_path: Path) -> None:
    """Containment observes deep files without losing Windows path access."""
    windows_legacy_limit = 260
    root = filesystem_path(tmp_path)
    folders = tuple(
        root.joinpath(*(["segment0123456789"] * count)) for count in range(1, 15)
    )
    leaf = folders[-1] / "owned.txt"
    try:
        for folder in folders:
            folder.mkdir()
        leaf.write_text("owned", encoding="utf-8")
        assert len(str(leaf)) > windows_legacy_limit
        assert containment(tmp_path, "nonce", _family()) == Ok(None)
    finally:
        leaf.unlink(missing_ok=True)
        for folder in reversed(folders):
            if folder.exists():
                folder.rmdir()


@pytest.mark.evidence("observer")
def test_containment_refuses_unreadable_subtree(tmp_path: Path) -> None:
    """A scan error cannot be mistaken for an empty, contained run."""
    (tmp_path / "unreadable").mkdir()
    script = (
        "import platform, sys\nfrom pathlib import Path\n"
        "from agentctl.check.writeguard import containment\n"
        "from agentctl.result import Err\n"
        "def observe(event, values):\n"
        "    if event == 'os.scandir' and str(values[0]).endswith('unreadable'):\n"
        "        raise PermissionError('owned directory veto')\n"
        "sys.addaudithook(observe)\n"
        "result = containment(Path(sys.argv[1]), 'nonce', platform.system())\n"
        "assert isinstance(result, Err), "
        "'unreadable containment subtree was accepted'\n"
        "assert 'owned directory veto' in result.error.message, result\n"
    )
    result = run(
        [sys.executable, "-c", script, str(tmp_path)], cwd=tmp_path, env=os.environ
    )
    assert isinstance(result, Ok)
    assert result.value.code == 0, result.value.stderr
    (tmp_path / "observers").write_text("not a directory", encoding="utf-8")
    assert isinstance(containment(tmp_path, "nonce", _family()), Err)
    assert isinstance(containment(tmp_path / "missing", "nonce", _family()), Err)


FINALIZER_PROBE = """import json
import platform
import sys
from pathlib import Path
from agentctl.check.steps import execute

def main(root: Path, run_dir: Path, nonce: str, report: Path) -> int:
    events: list[str] = []
    def audit(event: str, args: tuple[object, ...]) -> None:
        if event == "open" and str(args[0]) == str(root / "pyproject.toml"):
            events.append("after" if "veto" in events else "before")
        if event == "subprocess.Popen":
            argv = args[1]
            text = (
                " ".join(str(item) for item in argv)
                if isinstance(argv, (list, tuple)) else str(argv)
            )
            if "ruff" in text:
                events.append("veto")
                raise OSError("controlled static-leg veto")
            if "git" in text:
                events.append("git")
            elif "tests.harness.oracle" not in text:
                raise OSError("controlled later-leg veto")
    family = platform.system()
    if family not in {"Linux", "Darwin", "Windows"}:
        raise RuntimeError("unsupported host")
    sys.addaudithook(audit)
    code = execute(root, run_dir, nonce, family)
    report.write_text(json.dumps({"nonce": nonce, "events": events}), encoding="utf-8")
    return code

sys.exit(main(Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3], Path(sys.argv[4])))
"""


@pytest.mark.evidence("real")
def test_write_detected(tmp_path: Path) -> None:
    """Detect changed, added and removed bytes with an unchanged twin."""
    path = tmp_path / "subject"
    path.write_bytes(b"original")
    before = tree(tmp_path)
    assert isinstance(before, Ok)
    assert tree(tmp_path) == before
    (tmp_path / ".git").write_text(
        "gitdir: owned-worktree-metadata\n", encoding="utf-8"
    )
    assert tree(tmp_path) == before
    for contents in (b"different", b"original with additional bytes"):
        path.write_bytes(contents)
        after = tree(tmp_path)
        assert isinstance(after, Ok)
        assert compare(
            Snapshot(before.value, (), ()), Snapshot(after.value, (), ())
        ) == ("tree",)
    linked = tmp_path / "link"
    if platform.system() == "Windows":
        linked.hardlink_to(path)
        assert linked.read_bytes() == b"original with additional bytes"
        linked.unlink()
    else:
        linked.symlink_to("./subject")
        original_link = tree(tmp_path)
        linked.unlink()
        linked.symlink_to("subject/.")
        assert tree(tmp_path) != original_link, (
            "raw symlink text change was not detected"
        )
        linked.unlink()
    path.unlink()
    assert tree(tmp_path) != before


@pytest.mark.evidence("real")
def test_ignored_write_detected(tmp_path: Path) -> None:
    """Ignore rules and untracked status cannot hide guard inputs."""
    (tmp_path / ".gitignore").write_text(".ignored/\n", encoding="utf-8")
    hidden = tmp_path / ".ignored"
    hidden.mkdir()
    path = hidden / "subject"
    path.write_bytes(b"original")
    before = tree(tmp_path)
    assert isinstance(before, Ok)
    assert tree(tmp_path) == before
    path.write_bytes(b"different")
    assert tree(tmp_path) != before, "ignored write was not detected"


@pytest.mark.evidence("real")
def test_ref_change_detected(tmp_path: Path) -> None:
    """Read ref changes from a disposable git object fixture only."""
    repository(tmp_path, (("file", b"value"),), with_head=True)
    first = refs(tmp_path)
    assert isinstance(first, Ok)
    assert refs(tmp_path) == first
    (tmp_path / ".git/refs/heads/main").write_text("f" * 40 + "\n", encoding="ascii")
    second = refs(tmp_path)
    assert isinstance(second, Ok)
    assert compare(Snapshot((), first.value, ()), Snapshot((), second.value, ())) == (
        "refs",
    ), "ref change was not detected"


@pytest.mark.evidence("real")
def test_index_change_detected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Creation, replacement and removal of the real index change the snapshot."""
    repository(tmp_path)
    index = tmp_path / ".git/index"
    absent = refs(tmp_path)
    assert isinstance(absent, Ok)
    index.write_bytes(b"index one")
    before = refs(tmp_path)
    assert isinstance(before, Ok)
    assert before != absent, "index creation was not detected"
    index.write_bytes(b"index two")
    changed = refs(tmp_path)
    assert isinstance(changed, Ok)
    assert changed != before, "index change was not detected"
    index.unlink()
    assert refs(tmp_path) == absent
    index.mkdir()
    assert isinstance(refs(tmp_path), Err)
    index.rmdir()
    alternate = tmp_path / "private-index"
    monkeypatch.setenv("GIT_INDEX_FILE", str(alternate))
    overridden = refs(tmp_path)
    assert isinstance(overridden, Ok)
    assert overridden != absent
    alternate.write_bytes(b"alternate index")
    assert refs(tmp_path) != overridden


@pytest.mark.evidence("real")
def test_venv_change_detected(tmp_path: Path) -> None:
    """Read real distribution metadata inside a disposable standard-library venv."""
    venv = tmp_path / "venv"
    made = run(
        [sys.executable, "-m", "venv", "--without-pip", str(venv)],
        cwd=tmp_path,
        env=os.environ,
    )
    assert isinstance(made, Ok)
    assert made.value.code == 0
    purelib = Path(
        sysconfig.get_path("purelib", vars={"base": str(venv), "platbase": str(venv)})
    )
    assert purelib.is_relative_to(venv)
    metadata = purelib / "guard_fixture-0.1.dist-info"
    metadata.mkdir(parents=True)
    (metadata / "METADATA").write_text(
        "Metadata-Version: 2.1\nName: guard-fixture\nVersion: 0.1\n", encoding="utf-8"
    )
    (metadata / "RECORD").write_text(
        "guard_fixture.py,,\nguard_fixture-0.1.dist-info/METADATA,,\nguard_fixture-0.1.dist-info/RECORD,,\n",
        encoding="utf-8",
    )
    path = purelib / "guard_fixture.py"
    path.write_text('VALUE = "original"\n', encoding="utf-8")
    first = environment((str(purelib),))
    assert isinstance(first, Ok)
    assert environment((str(purelib),)) == first
    path.write_text('VALUE = "different"\n', encoding="utf-8")
    second = environment((str(purelib),))
    assert isinstance(second, Ok)
    assert compare(Snapshot((), (), first.value), Snapshot((), (), second.value)) == (
        "environment",
    ), "venv change was not detected"


@pytest.mark.evidence("real")
def test_containment_detects_owned_leak(tmp_path: Path) -> None:
    """Detect a registered owned child and accept its reaped-pid control."""
    family = platform.system()
    assert family in {"Linux", "Darwin", "Windows"}
    nonce = secrets.token_hex(16)
    observers = tmp_path / "observers"
    observers.mkdir()
    child = start(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        cwd=tmp_path,
        env=os.environ,
    )
    assert isinstance(child, Ok)
    try:
        assert alive(family, child.value.pid) == Ok(value=True)
        assert registered_alive(family, child.value.pid, None) == Ok(value=True)
        (observers / "owned.json").write_text(
            json.dumps({"nonce": nonce, "pid": child.value.pid}), encoding="utf-8"
        )
        assert isinstance(containment(tmp_path, nonce, family), Err), (
            "owned process leak was accepted"
        )
        if family in {"Windows", "Linux"}:
            birth = process_birth(family, child.value.pid)
            assert isinstance(birth, Ok)
            assert birth.value is not None
            assert registered_alive(family, child.value.pid, birth.value) == Ok(
                value=True
            )
            assert registered_alive(family, child.value.pid, birth.value + 1) == Ok(
                value=False
            ), "reused PID blocked owned-process teardown"
            assert isinstance(registered_alive(family, child.value.pid, 0), Err)
            (observers / "owned.json").write_text(
                json.dumps(
                    {"nonce": nonce, "pid": child.value.pid, "birth": birth.value}
                ),
                encoding="utf-8",
            )
            assert isinstance(containment(tmp_path, nonce, family), Err), (
                "matching live observer was ignored"
            )
            (observers / "owned.json").write_text(
                json.dumps(
                    {"nonce": nonce, "pid": child.value.pid, "birth": birth.value + 1}
                ),
                encoding="utf-8",
            )
            assert containment(tmp_path, nonce, family) == Ok(None), (
                "reused process identity was treated as owned"
            )
            (observers / "owned.json").write_text(
                json.dumps({"nonce": nonce, "pid": child.value.pid, "birth": True}),
                encoding="utf-8",
            )
            assert isinstance(containment(tmp_path, nonce, family), Err)
            (observers / "owned.json").write_text(
                json.dumps(
                    {"nonce": nonce, "pid": child.value.pid, "birth": birth.value}
                ),
                encoding="utf-8",
            )
    finally:
        assert isinstance(stop(child.value), Ok)
    assert containment(tmp_path, nonce, family) == Ok(None)
    (observers / "owned.json").write_text(
        json.dumps({"nonce": nonce + ".observer", "pid": child.value.pid}),
        encoding="utf-8",
    )
    assert containment(tmp_path, nonce, family) == Ok(None)
    assert isinstance(containment(tmp_path, "another-run", family), Err)
    assert isinstance(alive(family, 0), Err)


@pytest.mark.evidence("observer")
def test_finalizers_run_after_failed_leg(root: Path, tmp_path: Path) -> None:
    """Observe actual post-veto source reads independently of check's output."""
    nonce = secrets.token_hex(16)
    report = tmp_path / "observation.json"
    with TemporaryDirectory(prefix="ac-guard-") as temporary:
        run_dir = Path(temporary)
        result = run(
            [
                sys.executable,
                "-c",
                FINALIZER_PROBE,
                str(root),
                str(run_dir),
                nonce,
                str(report),
            ],
            cwd=root,
            env={
                **child_environment(os.environ, run_dir, nonce),
                **{
                    key: value
                    for key, value in os.environ.items()
                    if key == "COVERAGE_PROCESS_CONFIG"
                },
            },
        )
    assert isinstance(result, Ok)
    assert result.value.code == 1
    observed = json.loads(report.read_text(encoding="utf-8"))
    assert observed["nonce"] == nonce
    assert "git" in observed["events"]
    assert "veto" in observed["events"]
    assert "before" in observed["events"]
    assert "after" in observed["events"], (
        "snapshot finalizer did not re-read its subject"
    )


@pytest.mark.evidence("real")
def test_snapshot_error_boundaries(tmp_path: Path) -> None:
    """Invalid roots, repositories and distribution layouts produce typed errors."""
    missing = tmp_path / "missing"
    assert isinstance(tree(missing), Err)
    ordinary = tmp_path / "file"
    ordinary.write_text("not a directory", encoding="utf-8")
    assert isinstance(tree(ordinary), Err)
    assert isinstance(tree(Path(os.devnull)), Err)
    assert isinstance(refs(tmp_path), Err)
    assert isinstance(snapshot(missing), Err)
    assert isinstance(snapshot(tmp_path), Err)
    assert isinstance(environment(()), Err)
    library = tmp_path / "library"
    metadata = library / "boundary-0.1.dist-info"
    metadata.mkdir(parents=True)
    facts = metadata / "METADATA"
    facts.write_text("Version: 0.1\n", encoding="utf-8")
    assert isinstance(environment((str(library),)), Err)
    facts.write_text("Name: boundary\nVersion: 0.1\n", encoding="utf-8")
    assert isinstance(environment((str(library),)), Err)
    (metadata / "RECORD").write_text("missing.py,,\n", encoding="utf-8")
    assert isinstance(environment((str(library),)), Err)
    (metadata / "RECORD").write_text("incomplete\n", encoding="utf-8")
    assert isinstance(environment((str(library),)), Err)
    archive = tmp_path / "distribution.zip"
    with zipfile.ZipFile(archive, "w") as compressed:
        compressed.writestr(
            "boundary-0.1.dist-info/METADATA", "Name: boundary\nVersion: 0.1\n"
        )
        compressed.writestr("boundary-0.1.dist-info/RECORD", "boundary.py,,\n")
        compressed.writestr("boundary.py", "value = 1\n")
    zipped = environment((str(archive),))
    assert isinstance(zipped, Err)
    assert "not stored as filesystem files" in zipped.error.message


@pytest.mark.evidence("real")
def test_invalid_observer_registry(tmp_path: Path) -> None:
    """Malformed JSON, invalid identities and stale records cannot clear teardown."""
    family = platform.system()
    assert family in {"Linux", "Darwin", "Windows"}
    directory = tmp_path / "observers"
    directory.mkdir()
    path = directory / "record.json"
    for value in (
        [],
        {},
        {"nonce": "nonce", "pid": False},
        {"nonce": "nonce", "pid": 0},
        {"nonce": "nonce", "pid": "1"},
    ):
        path.write_text(json.dumps(value), encoding="utf-8")
        assert isinstance(containment(tmp_path, "nonce", family), Err)
    path.write_text("invalid JSON", encoding="utf-8")
    assert isinstance(containment(tmp_path, "nonce", family), Err)


@pytest.mark.evidence("value")
def test_record_schema() -> None:
    """A complete quoted CSV record qualifies; ambiguity and malformed rows fail."""
    assert recorded_files('"file,with,commas.py",,\nother.py,,\n') == Ok(
        ("file,with,commas.py", "other.py")
    )
    for text in ("", '"unterminated', "one,two\n", ",,\n", "same.py,,\nsame.py,,\n"):
        assert isinstance(recorded_files(text), Err)
    assert socket_check(()) == Ok(None)
    assert socket_check((stat.S_IFREG, stat.S_IFDIR)) == Ok(None)
    assert isinstance(socket_check((stat.S_IFREG, stat.S_IFSOCK)), Err)


@pytest.mark.evidence("real")
def test_ratchet_runs_after_earlier_failure(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A failed earlier leg cannot hide a separate baseline failure."""
    earlier_status = 7
    assert verify_baseline(tmp_path, earlier_status) == earlier_status
    assert "ratchet:" in capsys.readouterr().err


@pytest.mark.evidence("real")
def test_finalizer_outcomes(tmp_path: Path) -> None:
    """Actual repository reads preserve failure and reject each changed boundary."""
    family = platform.system()
    assert family in {"Linux", "Darwin", "Windows"}
    subject = tmp_path / "subject"
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    repository(subject, (("subject.txt", b"original"),), with_head=True)
    before = snapshot(subject)
    assert isinstance(before, Ok)
    context = CheckRun(subject, run_dir, "nonce", family)
    assert verify_baseline(subject, 1) == 1
    assert verify_baseline(subject, 0) == 0
    assert verify_baseline(run_dir, 0) == 1
    assert finalize(context, before.value, 0) == 0
    assert finalize(context, before.value, 1) == 1
    clean = finalize_observed(context, before.value, 0)
    assert (clean.containment, clean.write_guard) == (0, 0)
    observer = run_dir / "observers/broken.json"
    observer.parent.mkdir()
    observer.write_text("invalid JSON", encoding="utf-8")
    containment = finalize_observed(context, before.value, 0)
    assert (containment.containment, containment.write_guard) == (1, 0), (
        "containment failure was lost"
    )
    assert finalize(context, before.value, 0) == 1
    observer.unlink()
    (subject / "subject.txt").write_text("changed", encoding="utf-8")
    guard = finalize_observed(context, before.value, 0)
    assert (guard.containment, guard.write_guard) == (0, 1), (
        "write guard failure was lost"
    )
    assert finalize(context, before.value, 0) == 1
    shutil.rmtree(subject)
    assert finalize(context, before.value, 0) == 1


@pytest.mark.evidence("observer")
def test_later_readiness_does_not_prevent_validation(
    root: Path, tmp_path: Path
) -> None:
    """A cold invalid toolchain record does not prevent guarded plan validation."""
    cache = tmp_path / "cache/agentctl"
    cache.mkdir(parents=True)
    (cache / "toolchain-paths.toml").write_text("invalid = [", encoding="utf-8")
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    script = (
        "import sys\nfrom pathlib import Path\n"
        "from agentctl.check.steps import execute\n"
        "root, run_dir, marker = map(Path, sys.argv[1:4])\n"
        "seen = {'readiness': False, 'plan': False, 'passed': False}\n"
        "def profile(frame, event, arg):\n"
        "    if event == 'call' and frame.f_code.co_name == '_validate_and_observe':\n"
        "        seen['passed'] = bool(frame.f_locals.get('readiness'))\n"
        "        sys.setprofile(None)\n"
        "def audit(event, args):\n"
        "    if event == 'open':\n"
        "        path = str(args[0])\n"
        "        if path.endswith('toolchain-paths.toml'):\n"
        "            seen['readiness'] = True\n"
        "        if seen['readiness'] and path == str(\n"
        "            root / 'DEVELOPMENT_PLAN/README.md'):\n"
        "            seen['plan'] = True\n"
        "    if (seen['readiness'] and event == 'subprocess.Popen'\n"
        "            and 'git' not in str(args[1]).lower()):\n"
        "        raise OSError('owned tool veto')\n"
        "sys.addaudithook(audit)\n"
        "sys.setprofile(profile)\n"
        "code = execute(root, run_dir, 'test-nonce', sys.argv[4])\n"
        "sys.setprofile(None)\n"
        "marker.write_text(str(seen), encoding='utf-8')\n"
        "assert code != 0 and seen['readiness'] and seen['plan'], seen\n"
        "assert seen['passed'], 'later readiness was not passed to validation'\n"
    )
    result = run(
        [
            sys.executable,
            "-c",
            script,
            str(root),
            str(run_dir),
            str(tmp_path / "seen"),
            _family(),
        ],
        cwd=root,
        env={
            **os.environ,
            "XDG_CACHE_HOME": str(tmp_path / "cache"),
            "PYTHONPATH": str(root / "src"),
            "PYTHONUTF8": "1",
            "PYTHONIOENCODING": "utf-8",
        },
    )
    assert isinstance(result, Ok)
    assert result.value.code == 0, result.value.stderr
    assert "cannot read toolchain path record" in result.value.stderr
    assert "write-guard-compare: pass" in result.value.stdout


def _vetoed_validation(subject: Path, run_dir: Path) -> tuple[int, str, str]:
    """Observe attempted tool launches without recursively running this suite."""
    script = (
        "import sys\nfrom pathlib import Path\n"
        "from agentctl.check.steps import validate_and_run\n"
        "def audit(event, args):\n"
        "    if event == 'subprocess.Popen':\n"
        "        if 'tests.harness.oracle' in str(args[1]): return\n"
        "        raise OSError('owned tool veto')\n"
        "sys.addaudithook(audit)\n"
        "subject, run_dir = map(Path, sys.argv[1:3])\n"
        "sys.exit(validate_and_run(subject, run_dir, 'nonce', sys.argv[3]))\n"
    )
    result = run(
        [sys.executable, "-c", script, str(subject), str(run_dir), _family()],
        cwd=subject,
        env={
            **os.environ,
            "XDG_CACHE_HOME": str(run_dir / "cache"),
            "PYTHONUTF8": "1",
            "PYTHONIOENCODING": "utf-8",
        },
    )
    assert isinstance(result, Ok)
    return result.value.code, result.value.stdout, result.value.stderr


@pytest.mark.evidence("real")
def test_validation_binds_census_to_original_guard(root: Path, tmp_path: Path) -> None:
    """A changed source is refused by the actual validation handoff."""
    subject = tmp_path / "subject"
    assert scratch(root, subject) == Ok(subject)
    script = (
        "import sys\nfrom pathlib import Path\n"
        "from agentctl.check.steps import CheckRun, _validate_and_observe\n"
        "from agentctl.check.writeguard import tree\n"
        "from agentctl.foundation import Err, Ok\n"
        "root, state = map(Path, sys.argv[1:3])\n"
        "before = tree(root)\n"
        "assert isinstance(before, Ok)\n"
        "path = root / 'src/agentctl/foundation.py'\n"
        "path.write_bytes(path.read_bytes() + b'\\n')\n"
        "def audit(event, args):\n"
        "    if event == 'subprocess.Popen': raise OSError('owned tool veto')\n"
        "sys.addaudithook(audit)\n"
        "outcome = _validate_and_observe(CheckRun(root, state, 'nonce', sys.argv[3]), "
        "original_tree=before.value)\n"
        "assert outcome.code == 1\n"
        "assert isinstance(outcome.phase_observations, Err), "
        "'gate lost original phase observations'\n"
    )
    result = run(
        [sys.executable, "-c", script, str(subject), str(tmp_path), _family()],
        cwd=subject,
        env={
            **os.environ,
            "PYTHONPATH": str(subject / "src"),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONUTF8": "1",
        },
    )
    assert isinstance(result, Ok)
    assert result.value.code == 0, result.value.stderr
    assert "source census differs from original write guard" in result.value.stderr, (
        "validation omitted the original census guard"
    )


@pytest.mark.evidence("real")
def test_validation_reports_independent_failures(root: Path, tmp_path: Path) -> None:
    """A document error does not hide a separate static ownership error."""
    subject = tmp_path / "subject"
    assert scratch(root, subject) == Ok(subject)
    (subject / "docs").mkdir()
    phase = subject / "DEVELOPMENT_PLAN/phase-0-governance-and-phase-evidence.md"
    text = phase.read_text(encoding="utf-8")
    phase.write_text(text.replace("| R26 —", "| R999 —", 1), encoding="utf-8")
    code, output, error = _vetoed_validation(subject, tmp_path)
    assert code == 1
    assert "docs.taxonomy: docs/" in error
    assert "undeclared requirement R999" in error
    assert "ruff-check: FAIL" in output
    assert "pytest: FAIL" in output


@pytest.mark.evidence("real")
def test_validation_failure_stages(root: Path, tmp_path: Path) -> None:
    """Invalid subjects remain failures as independent tools are attempted."""
    assert _vetoed_validation(tmp_path, tmp_path)[0] == 1
    (tmp_path / "src").mkdir()
    (tmp_path / "src/subject.py").write_text("value = 1\n", encoding="utf-8")
    assert _vetoed_validation(tmp_path, tmp_path)[0] == 1
    subject = tmp_path / "subject"
    assert scratch(root, subject) == Ok(subject)
    (subject / "tests/oracles/auth_status.toml").write_text("", encoding="utf-8")
    assert _vetoed_validation(subject, tmp_path)[0] == 1
    (subject / "tests/oracles/auth_status.toml").write_bytes(
        (root / "tests/oracles/auth_status.toml").read_bytes()
    )
    record = subject / "tests/mutants/gate.toml"
    original = record.read_bytes()
    record.write_text("", encoding="utf-8")
    assert _vetoed_validation(subject, tmp_path)[0] == 1
    record.write_bytes(original)
    (subject / "tests/integration/test_guard.py").unlink()
    assert _vetoed_validation(subject, tmp_path)[0] == 1


@pytest.mark.evidence("real")
def test_oracle_failure_survives_invalid_corpus(root: Path, tmp_path: Path) -> None:
    """A malformed mutation corpus cannot prevent independent oracle validation."""
    subject = tmp_path / "subject"
    assert scratch(root, subject) == Ok(subject)
    (subject / "tests/oracles/auth_status.toml").write_text("", encoding="utf-8")
    (subject / "tests/mutants/gate.toml").write_text("", encoding="utf-8")
    code, _output, error = _vetoed_validation(subject, tmp_path)
    assert code == 1
    assert "auth_status" in error
    assert "nonempty mutant rows required" in error
    assert "oracle-observation phase" in error, "oracle source attribution was omitted"
    details = json.loads((tmp_path / "oracle-details.json").read_text(encoding="utf-8"))
    assert details["nonce"] == "nonce"
    assert any(
        issue[0] == "tests/oracles/auth_status.toml" for issue in details["issues"]
    ), "failed oracle source was not recorded"


@pytest.mark.evidence("observer")
def test_oracle_and_bootstrap_spawn_failures_preserved(
    root: Path, tmp_path: Path
) -> None:
    """Independent real spawn vetoes preserve both diagnostics in one run."""
    failed_run = tmp_path / "failed-run"
    failed_run.mkdir()
    script = (
        "import sys\nfrom pathlib import Path\n"
        "from agentctl.check.steps import oracle_check\n"
        "def observe(event, args):\n"
        "    if event == 'subprocess.Popen':\n"
        "        if 'tests.harness.oracle' in str(args[1]):\n"
        "            raise OSError('oracle observer veto')\n"
        "        if 'tests.harness.bootstrap_origin' in str(args[1]):\n"
        "            raise OSError('bootstrap observer veto')\n"
        "sys.addaudithook(observe)\n"
        "assert oracle_check(Path(sys.argv[1]), Path(sys.argv[2]), 'nonce') == 1\n"
    )
    observed = run(
        [sys.executable, "-c", script, str(root), str(failed_run)],
        cwd=root,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    assert isinstance(observed, Ok)
    assert observed.value.code == 0, observed.value.stderr
    assert "oracle observer veto" in observed.value.stderr
    assert "bootstrap observer veto" in observed.value.stderr, (
        "bootstrap observer failure was hidden"
    )
    names = ("oracle-validation", "bootstrap-provenance")
    failures = read_legs(failed_run / "oracle-outcomes.json", "nonce", names)
    assert isinstance(failures, Ok)
    assert failures.value.outcomes == ((names[0], 1), (names[1], 1)), (
        "oracle or bootstrap spawn failure was misrecorded"
    )
    existing = (failed_run / "oracle-outcomes.json").read_bytes()
    repeated = run(
        [sys.executable, "-c", script, str(root), str(failed_run)],
        cwd=root,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    assert isinstance(repeated, Ok)
    assert repeated.value.code == 0, repeated.value.stderr
    assert "oracle outcomes: cannot write run record" in repeated.value.stderr, (
        "existing oracle outcomes were overwritten"
    )
    assert (failed_run / "oracle-outcomes.json").read_bytes() == existing
    successful_bootstrap = (
        "import sys\nfrom pathlib import Path\n"
        "from agentctl.check.steps import oracle_check\n"
        "def observe(event, args):\n"
        "    if (event == 'subprocess.Popen'\n"
        "            and 'tests.harness.oracle' in str(args[1])):\n"
        "        raise OSError('oracle observer veto')\n"
        "sys.addaudithook(observe)\n"
        "assert oracle_check(Path(sys.argv[1]), Path(sys.argv[2]), 'nonce') == 1\n"
    )
    partial_run = tmp_path / "partial-run"
    partial_run.mkdir()
    observed = run(
        [sys.executable, "-c", successful_bootstrap, str(root), str(partial_run)],
        cwd=root,
        env={
            **os.environ,
            "PYTHONDONTWRITEBYTECODE": "1",
            "XDG_STATE_HOME": str(tmp_path / "state"),
            "GHCUP_INSTALL_BASE_PREFIX": str(tmp_path / "ghcup"),
        },
    )
    assert isinstance(observed, Ok)
    assert observed.value.code == 0, observed.value.stderr
    assert "oracle observer veto" in observed.value.stderr
    receipt = json.loads(
        (partial_run / "bootstrap-host.json").read_text(encoding="utf-8")
    )
    assert receipt["nonce"] == "nonce"
    isolated = read_legs(partial_run / "oracle-outcomes.json", "nonce", names)
    assert isinstance(isolated, Ok)
    assert isolated.value.outcomes == ((names[0], 1), (names[1], 0)), (
        "independent oracle outcomes were lost"
    )


def _fixture_failure_case(
    root: Path,
    tmp_path: Path,
    relative: str,
    later: str,
    early: str = "tests/governance/test_ratchet.py::test_deleted_row_rejected",
) -> None:
    """Run one disposable checkout with a deliberately broken native fixture."""
    tmp_path.mkdir()
    subject = tmp_path / "subject"
    assert scratch(root, subject) == Ok(subject)
    fixture = subject / relative
    fixture.write_text(
        "raise ImportError('later native fixture unavailable')\n", encoding="utf-8"
    )
    home = tmp_path / "home"
    home.mkdir()
    outer = tmp_path / "outer-gate"
    inherited = {
        **os.environ,
        "AGENTCTL_CHECK_NONCE": "outer-nonce",
        "AGENTCTL_CHECK_MANIFEST": str(outer / "manifest.json"),
    }
    observed = run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-p",
            "no:cacheprovider",
            "--continue-on-collection-errors",
            early,
            later,
            "-q",
        ],
        cwd=subject,
        env={
            **{
                key: value
                for key, value in inherited.items()
                if key
                not in {
                    "AGENTCTL_CHECK_NONCE",
                    "AGENTCTL_CHECK_MANIFEST",
                    "AGENTCTL_MUTANT_BUILD",
                    "AGENTCTL_TEST_NATIVE_ROOT",
                }
            },
            "PATH": "",
            "HOME": str(home),
            "USERPROFILE": str(home),
            "LOCALAPPDATA": str(home / "local"),
            "XDG_STATE_HOME": str(home / "state"),
            "XDG_CACHE_HOME": str(home / "cache"),
            "XDG_CONFIG_HOME": str(home / "config"),
            "XDG_DATA_HOME": str(home / "data"),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
            "PYTHONPATH": os.pathsep.join((str(subject / "src"), str(subject))),
        },
        timeout=120,
    )
    assert isinstance(observed, Ok)
    (tmp_path / "nested-stdout.txt").write_text(observed.value.stdout, encoding="utf-8")
    (tmp_path / "nested-stderr.txt").write_text(observed.value.stderr, encoding="utf-8")
    assert observed.value.code != 0
    completed = "1 passed" in observed.value.stdout
    assert completed, "later fixture blocked governance collection"
    assert "later native fixture unavailable" in observed.value.stdout
    assert not outer.exists(), "nested fixture touched outer gate state"


@pytest.mark.evidence("real")
def test_later_fixture_failure_preserves_governance_collection(
    root: Path, tmp_path: Path
) -> None:
    """A broken native fixture is local while an independent governance test runs."""
    _fixture_failure_case(
        root,
        tmp_path / "haskell",
        "tests/harness/haskell_fixtures.py",
        "tests/unit/test_backoff.py",
    )
    _fixture_failure_case(
        root,
        tmp_path / "mux",
        "tests/harness/tmux_fixtures.py",
        "tests/e2e/test_launch.py",
    )
    _fixture_failure_case(
        root,
        tmp_path / "bootstrap",
        "src/agentctl/bootstrap/build.py",
        "tests/unit/test_backoff.py",
    )
    _fixture_failure_case(
        root,
        tmp_path / "socket",
        "src/agentctl/bootstrap/build.py",
        "tests/integration/test_mux_resolution.py",
        "tests/integration/test_socket_preconditions.py::test_socket_directory_inspection",
    )
    _fixture_failure_case(
        root,
        tmp_path / "socket-pins",
        "src/agentctl/bootstrap/pins.py",
        "tests/integration/test_mux_resolution.py",
        "tests/integration/test_socket_preconditions.py::test_socket_directory_inspection",
    )
    _fixture_failure_case(
        root,
        tmp_path / "unit-pins",
        "src/agentctl/bootstrap/pins.py",
        "tests/unit/test_preconditions.py::test_toolchain_preconditions",
        "tests/unit/test_preconditions.py::test_socket_path_length",
    )
    _fixture_failure_case(
        root,
        tmp_path / "unit-prerequisites",
        "src/agentctl/check/prerequisites.py",
        "tests/unit/test_preconditions.py::test_prerequisite_precondition",
        "tests/unit/test_preconditions.py::test_socket_path_length",
    )


@pytest.mark.evidence("observer")
def test_gate_read_and_oracle_vetoes(root: Path) -> None:
    """Real audit vetoes make an unreadable snapshot and an unstartable oracle fail."""
    script = (
        "import sys\nfrom pathlib import Path\n"
        "from agentctl.check.steps import execute, validate_and_run\n"
        "root, run_dir = Path(sys.argv[1]), Path(sys.argv[2])\n"
        "def observe(event, values):\n"
        "    if (sys.argv[3] == 'read' and event == 'open'\n"
        "            and str(values[0]) == str(root / 'pyproject.toml')):\n"
        "        raise OSError('owned snapshot veto')\n"
        "    if (sys.argv[3] == 'oracle' and event == 'subprocess.Popen'\n"
        "            and 'tests.harness.oracle' in str(values[1])):\n"
        "        raise OSError('owned oracle veto')\n"
        "    if event == 'subprocess.Popen' and 'git' not in str(values[1]).lower():\n"
        "        raise OSError('owned tool veto')\n"
        "sys.addaudithook(observe)\n"
        "if sys.argv[3] == 'read':\n"
        "    code = execute(root, run_dir, 'nonce', sys.argv[4])\n"
        "else: code = validate_and_run(root, run_dir, 'nonce', sys.argv[4])\n"
        "assert code == 1\n"
    )
    for mode in ("read", "oracle"):
        with TemporaryDirectory(prefix="ac-veto-") as temporary:
            result = run(
                [
                    sys.executable,
                    "-c",
                    script,
                    str(root),
                    temporary,
                    mode,
                    platform.system(),
                ],
                cwd=root,
                env={**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"},
            )
        assert isinstance(result, Ok)
        assert result.value.code == 0, result.value.stderr
        assert (
            "owned snapshot veto" if mode == "read" else "owned oracle veto"
        ) in result.value.stderr


@pytest.mark.evidence("observer")
def test_ref_and_liveness_read_errors(tmp_path: Path) -> None:
    """Expose native read failures with a live audit veto."""
    subject = tmp_path / "subject"
    repository(subject)
    (subject / ".git/index").write_bytes(b"index")
    observers = tmp_path / "observers"
    observers.mkdir()
    (observers / "owned.json").write_text(
        json.dumps({"nonce": "nonce", "pid": os.getpid()}), encoding="utf-8"
    )
    script = (
        "import platform, sys\nfrom pathlib import Path\n"
        "from agentctl.check.writeguard import refs, containment\n"
        "from agentctl.result import Err\n"
        "def observe(event, values):\n"
        "    if sys.argv[2] == 'spawn' and event == 'subprocess.Popen':\n"
        "        raise OSError('owned read veto')\n"
        "    if (sys.argv[2] == 'file' and event == 'open'\n"
        "            and Path(str(values[0])).as_posix().endswith('/.git/HEAD')):\n"
        "        raise OSError('owned read veto')\n"
        "    if (sys.argv[2] == 'index' and event == 'open'\n"
        "            and Path(str(values[0])).as_posix().endswith('/.git/index')):\n"
        "        raise OSError('owned read veto')\n"
        "    if sys.argv[2] == 'pid' and event in ('os.kill', 'ctypes.dlopen'):\n"
        "        raise OSError('owned read veto')\n"
        "sys.addaudithook(observe)\n"
        "root = Path(sys.argv[1])\n"
        "if sys.argv[2] == 'pid':\n"
        "    result = containment(root, 'nonce', platform.system())\n"
        "else: result = refs(root / 'subject')\n"
        "assert isinstance(result, Err)\n"
        "assert result.error.message == 'owned read veto', result\n"
    )
    for mode in ("spawn", "file", "index", "pid"):
        result = run(
            [sys.executable, "-c", script, str(tmp_path), mode],
            cwd=tmp_path,
            env=os.environ,
        )
        assert isinstance(result, Ok)
        assert result.value.code == 0, result.value.stderr
    result = run(
        [
            sys.executable,
            "-c",
            (
                "from pathlib import Path; from agentctl.check.writeguard import refs; "
                "print(refs(Path.cwd()).error.message)"
            ),
        ],
        cwd=tmp_path,
        env={**os.environ, "PATH": ""},
    )
    assert isinstance(result, Ok)
    assert result.value.stdout.strip() == "git is required for the ref snapshot"
