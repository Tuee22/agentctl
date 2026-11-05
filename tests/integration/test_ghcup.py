# Copyright (c) 2026 agentctl contributors.
"""Verified local downloads and real existing-ghcup reuse in an owned prefix."""

import hashlib
import json
import os
import platform
import shutil
import sys
from dataclasses import replace
from pathlib import Path
from urllib.request import build_opener

import pytest

from agentctl.bootstrap.ghcup import connection, download, provide
from agentctl.bootstrap.pins import Asset, Version, load
from agentctl.check.audit import read
from agentctl.hostfacts import Ghcup, HostFacts, discover_ghcup, ghcup_destination
from agentctl.process import run
from agentctl.result import Err, Ok
from tests.harness.http import Body, serve
from tests.harness.nonce import fresh

BODY = b"independently authored ghcup fixture\n" * 4096
DIGEST = hashlib.sha256(BODY).hexdigest()
EXECUTABLE_MODE = 0o755


def _asset(url: str, *, windows: bool = False) -> Asset:
    """Name the exact local response and independently computed expected digest."""
    return Asset("Windows" if windows else "Linux", "x86_64", url, DIGEST)


@pytest.mark.evidence("observer")
def test_present_ghcup_untouched(root: Path, tmp_path: Path) -> None:
    """A real answering copy records only its version check and causes no request."""
    family = platform.system()
    assert family in {"Linux", "Darwin", "Windows"}
    original = discover_ghcup(family, os.environ, Path.home())
    assert original is not None
    home = tmp_path / "home"
    home.mkdir()
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in {"GHCUP_USE_XDG_DIRS", "XDG_BIN_HOME"}
    }
    env.update(
        {
            "HOME": str(home),
            "USERPROFILE": str(home),
            "GHCUP_INSTALL_BASE_PREFIX": str(home),
            "GHCUP_SKIP_UPDATE_CHECK": "1",
            "PATH": "",
            **{
                f"XDG_{kind}_HOME": str(home / kind.lower())
                for kind in ("CACHE", "CONFIG", "DATA", "STATE")
            },
        }
    )
    executable = ghcup_destination(family, env, home)
    executable.parent.mkdir(parents=True)
    shutil.copy2(original, executable)
    before = executable.read_bytes()
    nonce = fresh(os.environ.get("AGENTCTL_CHECK_NONCE", "focused"))
    manifest = os.environ.get("AGENTCTL_CHECK_MANIFEST")
    observers = (
        Path(manifest).parent / "observers"
        if manifest is not None and manifest != ""
        else tmp_path
    )
    log = observers / (nonce + ".jsonl")
    with serve(
        tmp_path / "server", (Body("/download", BODY, str(len(BODY))),)
    ) as server:
        with build_opener().open(server.url + "/download", timeout=5) as control:
            assert control.read() == BODY
        assert server.requests == ("/download",)
        result = run(
            [
                sys.executable,
                str(root / "tests/fixtures/bootstrap/ghcup_actor.py.txt"),
                str(tmp_path),
                str(log),
                nonce,
                server.url + "/download",
                DIGEST,
            ],
            cwd=root,
            env=env,
        )
        assert isinstance(result, Ok)
        assert result.value.code == 0, result.value.stderr
        payload: object = json.loads(result.value.stdout)
        assert payload == {"ok": True, "path": str(executable.resolve())}, (
            "existing ghcup was replaced or downloaded"
        )
        assert executable.read_bytes() == before, (
            "existing ghcup was replaced or downloaded"
        )
        assert server.requests == ("/download",), (
            "existing ghcup was replaced or downloaded"
        )
    records = read(log, nonce)
    assert isinstance(records, Ok)
    assert len(records.value) == 1
    assert records.value[0].argv == (str(executable.resolve()), "--numeric-version")
    assert not records.value[0].vetoed


@pytest.mark.evidence("real")
def test_sha_mismatch_refused_no_file(tmp_path: Path) -> None:
    """Full correct bytes publish; equally long corrupted bytes leave no artifact."""
    corrupted = b"X" + BODY[1:]
    bodies = (
        Body("/correct", BODY, str(len(BODY))),
        Body("/corrupt", corrupted, str(len(corrupted))),
    )
    with serve(tmp_path / "server", bodies) as server:
        for windows in (False, True):
            destination = tmp_path / str(windows) / "ghcup"
            assert download(
                _asset(server.url + "/correct", windows=windows), destination
            ) == Ok(destination)
            assert destination.read_bytes() == BODY
            if not windows and platform.system() != "Windows":
                assert destination.stat().st_mode & 0o777 == EXECUTABLE_MODE
        refused = tmp_path / "refused" / "ghcup"
        assert isinstance(download(_asset(server.url + "/corrupt"), refused), Err), (
            "unverified ghcup bytes were published"
        )
        assert not refused.exists(), "unverified ghcup bytes were published"
        assert tuple(refused.parent.iterdir()) == ()
        assert server.requests == ("/correct", "/correct", "/corrupt")


@pytest.mark.evidence("real")
def test_truncated_download_leaves_nothing(tmp_path: Path) -> None:
    """Both absent and overstated lengths preserve atomic failure behaviour."""
    bodies = (
        Body("/complete", BODY, None),
        Body("/truncated", BODY[:10], str(len(BODY))),
        Body("/bad-length", BODY, "invalid"),
    )
    with serve(tmp_path / "server", bodies) as server:
        installed = tmp_path / "complete" / "ghcup"
        assert download(_asset(server.url + "/complete"), installed) == Ok(installed)
        for path in ("/truncated", "/bad-length"):
            destination = tmp_path / path[1:] / "ghcup"
            assert isinstance(download(_asset(server.url + path), destination), Err)
            assert not destination.exists(), "partial ghcup was published in place"
            assert tuple(destination.parent.iterdir()) == (), (
                "partial ghcup was published in place"
            )
    destination = tmp_path / "changed" / "ghcup"

    def occupy() -> None:
        destination.write_bytes(b"concurrent owner's executable")

    with serve(
        tmp_path / "racing-server", (Body("/body", BODY, None),), occupy
    ) as server:
        assert isinstance(download(_asset(server.url + "/body"), destination), Err)
        assert destination.read_bytes() == b"concurrent owner's executable"
        assert tuple(destination.parent.iterdir()) == (destination,)


@pytest.mark.evidence("real")
def test_no_rc_file_written(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A successful install under a redirected home preserves all profile bytes."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    files = (".bashrc", ".bash_profile", ".profile", ".zshrc", ".zprofile")
    for name in files:
        (home / name).write_bytes(("owned fixture " + name).encode())
    before = tuple((name, (home / name).read_bytes()) for name in files)
    with serve(tmp_path / "server", (Body("/body", BODY, None),)) as server:
        destination = home / ".ghcup/bin/ghcup"
        pins = load()
        assert isinstance(pins, Ok)
        selected = replace(pins.value, assets=(_asset(server.url + "/body"),))
        facts = HostFacts("Linux", "x86_64", destination, None, None, None)
        assert provide(facts, selected) == Ok(destination)
        assert destination.read_bytes() == BODY
    assert tuple((name, (home / name).read_bytes()) for name in files) == before, (
        "ghcup installation edited an rc file"
    )


@pytest.mark.evidence("real")
def test_download_errors_are_typed(tmp_path: Path) -> None:
    """Unsupported responses, occupied destinations and failed requests refuse."""
    existing = tmp_path / "existing"
    existing.write_bytes(b"preserve")
    assert isinstance(download(_asset("https://unreached.invalid"), existing), Err)
    assert existing.read_bytes() == b"preserve"
    assert isinstance(
        download(_asset(existing.as_uri()), tmp_path / "destination"), Err
    )
    with (
        pytest.raises(TypeError, match="requires an HTTP response"),
        connection(existing.as_uri()),
    ):
        pytest.fail("non-HTTP response was accepted")
    assert isinstance(
        download(_asset("https://unreached.invalid"), existing / "child"), Err
    )
    with serve(tmp_path / "server", ()) as server:
        destination = tmp_path / "missing" / "ghcup"
        assert isinstance(download(_asset(server.url + "/404"), destination), Err)
        assert tuple(destination.parent.iterdir()) == ()
    pins = load()
    assert isinstance(pins, Ok)
    facts = HostFacts(
        "Linux", "x86_64", tmp_path / "unused", Ghcup(existing, None), None, None
    )
    for reported in (None, Version((0, 1, 50, 1))):
        result = provide(replace(facts, ghcup=Ghcup(existing, reported)), pins.value)
        assert isinstance(result, Err)
        assert "upgrade" in result.error.message
    assert isinstance(
        provide(replace(facts, architecture="unsupported"), pins.value), Err
    )
