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

from agentctl.check.mutants import scratch
from agentctl.check.steps import CheckRun, finalize, validate_and_run, verify_baseline
from agentctl.check.steps import environment as child_environment
from agentctl.check.writeguard import (
    Snapshot,
    compare,
    containment,
    environment,
    recorded_files,
    refs,
    snapshot,
    socket_check,
    tree,
)
from agentctl.paths import Family
from agentctl.process import alive, run, start, stop
from agentctl.result import Err, Ok
from tests.harness.git import repository


def _family() -> Family:
    """Pass the observed native family to the typed gate coordinator."""
    family = platform.system()
    assert family in {"Linux", "Darwin", "Windows"}
    return family


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
        (observers / "owned.json").write_text(
            json.dumps({"nonce": nonce, "pid": child.value.pid}), encoding="utf-8"
        )
        assert isinstance(containment(tmp_path, nonce, family), Err), (
            "owned process leak was accepted"
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
    observer = run_dir / "observers/broken.json"
    observer.parent.mkdir()
    observer.write_text("invalid JSON", encoding="utf-8")
    assert finalize(context, before.value, 0) == 1
    observer.unlink()
    (subject / "subject.txt").write_text("changed", encoding="utf-8")
    assert finalize(context, before.value, 0) == 1
    shutil.rmtree(subject)
    assert finalize(context, before.value, 0) == 1


@pytest.mark.evidence("real")
def test_validation_failure_stages(root: Path, tmp_path: Path) -> None:
    """Empty targets, invalid documents and an invalid oracle stop before tools."""
    assert validate_and_run(tmp_path, tmp_path, "nonce", _family()) == 1
    (tmp_path / "src").mkdir()
    (tmp_path / "src/subject.py").write_text("value = 1\n", encoding="utf-8")
    assert validate_and_run(tmp_path, tmp_path, "nonce", _family()) == 1
    subject = tmp_path / "subject"
    assert scratch(root, subject) == Ok(subject)
    (subject / "tests/oracles/auth_status.toml").write_text("", encoding="utf-8")
    assert validate_and_run(subject, tmp_path, "nonce", _family()) == 1
    (subject / "tests/oracles/auth_status.toml").write_bytes(
        (root / "tests/oracles/auth_status.toml").read_bytes()
    )
    record = subject / "tests/mutants/gate.toml"
    original = record.read_bytes()
    record.write_text("", encoding="utf-8")
    assert validate_and_run(subject, tmp_path, "nonce", _family()) == 1
    record.write_bytes(original)
    (subject / "tests/integration/test_guard.py").unlink()
    assert validate_and_run(subject, tmp_path, "nonce", _family()) == 1


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
                env=os.environ,
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
    for mode in ("spawn", "file", "pid"):
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
