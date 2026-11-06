# Copyright (c) 2026 agentctl contributors.
"""Nonce-bound host observations, extended when each tool capability exists."""

import importlib.metadata
import json
import os
import platform
import re
import shutil
import tomllib
from collections.abc import Mapping
from dataclasses import asdict
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

import agentctl
from agentctl.check.lanes import HostFacts
from agentctl.paths import directories
from agentctl.process import run
from agentctl.result import Ok
from tests.harness.agents import isolated_environment
from tests.harness.bootstrap_origin import capture, state_directory


def live_folder(family: str, environment: Mapping[str, str]) -> Path:
    """Use the sole real-agent working folder without changing its configuration."""
    assert family in {"Linux", "Darwin", "Windows"}
    folder = directories(family, environment, Path.home()).state / "live-acceptance"
    folder.mkdir(parents=True, mode=0o700, exist_ok=True)
    return folder


def observe_authentication(
    family: str, directory: Path, nonce: str, environment: Mapping[str, str]
) -> bool:
    """Record only read-only probe statuses; retain no credential or identity output."""
    folder = live_folder(family, environment)
    statuses: list[int | None] = []
    for agent, arguments in (
        ("claude", ["auth", "status"]),
        ("codex", ["login", "status"]),
    ):
        executable = shutil.which(
            agent + (".exe" if family == "Windows" else ""),
            path=environment.get("PATH", ""),
        )
        status = None
        if executable is not None:
            result = run(
                [executable, *arguments],
                cwd=folder,
                env={**environment, "DISABLE_AUTOUPDATER": "1"},
                timeout=10,
            )
            if isinstance(result, Ok):
                status = result.value.code
        statuses.append(status)
    (directory / "authentication.json").write_text(
        json.dumps({"nonce": nonce, "statuses": statuses}), encoding="utf-8"
    )
    return statuses == [0, 0]


def bootstrap_before(directory: Path, nonce: str) -> None:
    """Capture raw filesystem provenance before the gate's provisioning step."""
    capture(directory, nonce, platform.system(), os.environ, Path.home())


def observe_xcode(family: str, directory: Path, environment: Mapping[str, str]) -> bool:
    """Qualify Darwin only when the native Command Line Tools probe succeeds."""
    executable = shutil.which("xcode-select", path=environment.get("PATH", ""))
    if family != "Darwin" or executable is None:
        return False
    result = run([executable, "-p"], cwd=directory, env=environment, timeout=10)
    return isinstance(result, Ok) and result.value.code == 0


def clean_recipe() -> bool:
    """Recognise Docker's marker and the recipe's independent Stage A observation."""
    initial = (
        state_directory(platform.system(), os.environ, Path.home())
        / "clean-host-stage-a/bootstrap-host.json"
    )
    if not Path("/.dockerenv").is_file() or not initial.is_file():
        return False
    value: object = json.loads(initial.read_text(encoding="utf-8"))
    return bool(
        isinstance(value, dict)
        and value.get("origin") == "agentctl-installed"
        and value.get("found") is None
        and value.get("configured_existed") is False
        and value.get("family") == platform.system()
    )


def multiplexer(
    family: str, directory: Path, nonce: str, environment: Mapping[str, str]
) -> bool:
    """Observe the real executable independently of the Haskell resolution kernel."""
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    home = directory / "home"
    home.mkdir(mode=0o700, exist_ok=True)
    name = "psmux.exe" if family == "Windows" else "tmux"
    executable = shutil.which(name, path=environment.get("PATH", ""))
    version = ""
    accepted = False
    if executable is not None:
        result = run(
            [executable, "-V"],
            cwd=directory,
            env={
                **{
                    key: value
                    for key, value in environment.items()
                    if key not in {"TMUX", "TMUX_PANE"}
                },
                "HOME": str(home),
                "USERPROFILE": str(home),
                "PSMUX_DATA_DIR": str(directory / "psmux"),
                "PSMUX_NO_WARM": "1",
                **{
                    f"XDG_{kind}_HOME": str(directory / kind.lower())
                    for kind in ("CACHE", "CONFIG", "DATA", "STATE")
                },
            },
            timeout=10,
        )
        if isinstance(result, Ok) and result.value.code == 0:
            version = result.value.stdout.strip()
            pattern = (
                r"psmux (\d+)\.(\d+)\.(\d+)(?: \([^()\r\n]*\))?"
                if family == "Windows"
                else r"tmux (\d+)\.(\d+)[a-z]?"
            )
            match = re.fullmatch(pattern, version)
            if match is not None:
                observed = tuple(int(part) for part in match.groups())
                accepted = observed >= ((3, 4, 0) if family == "Windows" else (3, 2))
    (directory / "mux-host.json").write_text(
        json.dumps(
            {
                "nonce": nonce,
                "executable": executable,
                "version": version,
                "met": accepted,
            }
        ),
        encoding="utf-8",
    )
    return accepted


def observe_agents(
    family: str, directory: Path, nonce: str, environment: Mapping[str, str]
) -> bool:
    """Qualify installed CLIs through independent private version observations."""
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    observations: list[dict[str, object]] = []
    met = True
    with TemporaryDirectory(prefix="versions-", dir=directory) as temporary:
        for name in ("claude", "codex"):
            executable = shutil.which(name, path=environment.get("PATH", ""))
            native = executable is not None and (
                family != "Windows" or Path(executable).suffix.lower() == ".exe"
            )
            version = ""
            accepted = False
            if native:
                scope = Path(temporary) / name
                result = run(
                    [executable, "--version"],
                    cwd=directory,
                    env=isolated_environment(scope, environment),
                    timeout=10,
                )
                if isinstance(result, Ok) and result.value.code == 0:
                    version = result.value.stdout.strip()
                    pattern = (
                        r"\d+\.\d+\.\d+(?:[-+.][^ ]+)? \(Claude Code\)"
                        if name == "claude"
                        else r"codex-cli \d+\.\d+\.\d+(?:[-+.]\S+)?"
                    )
                    accepted = re.fullmatch(pattern, version) is not None
            observations.append(
                {
                    "agent": name,
                    "executable": executable,
                    "version": version,
                    "met": accepted,
                }
            )
            met = met and accepted
    (directory / "agents-host.json").write_text(
        json.dumps({"nonce": nonce, "tools": observations, "met": met}),
        encoding="utf-8",
    )
    return met


def observe(root: Path, nonce: str, destination: Path) -> HostFacts:
    """Record actual OS, architecture, editable-checkout and git observations."""
    raw = importlib.metadata.distribution("agentctl").read_text("direct_url.json")
    metadata: object = json.loads(raw) if raw is not None else None
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))[
        "project"
    ]
    dependencies: object = project["optional-dependencies"]["dev"]
    assert isinstance(dependencies, list)
    assert dependencies
    pins = True
    for dependency in dependencies:
        assert isinstance(dependency, str)
        name, separator, version = dependency.partition("==")
        assert separator == "=="
        pins = pins and importlib.metadata.version(name) == version
    editable = (
        isinstance(metadata, dict)
        and metadata.get("url") == root.resolve().as_uri()
        and isinstance(metadata.get("dir_info"), dict)
        and metadata["dir_info"].get("editable") is True
    )
    checkout = (
        editable
        and pins
        and Path(str(agentctl.__file__))
        .resolve()
        .is_relative_to(root.resolve() / "src/agentctl")
    )
    facts = HostFacts(
        family=platform.system(),
        architecture=platform.machine(),
        checkout=checkout,
        git=shutil.which("git") is not None,
        mux=multiplexer(
            platform.system(), destination.parent / "mux-host", nonce, os.environ
        ),
        agents=observe_agents(
            platform.system(), destination.parent / "agent-host", nonce, os.environ
        ),
        authenticated=observe_authentication(
            platform.system(), destination.parent, nonce, os.environ
        ),
        clean=clean_recipe(),
        xcode=observe_xcode(platform.system(), destination.parent, os.environ),
    )
    destination.write_text(
        json.dumps({"nonce": nonce, "facts": asdict(facts)}), encoding="utf-8"
    )
    return facts


@pytest.fixture(scope="session", autouse=True)
def record_host(root: Path, tmp_path_factory: pytest.TempPathFactory) -> HostFacts:
    """Keep the whole-suite observation under its own run identity and storage."""
    nonce = os.environ.get("AGENTCTL_CHECK_NONCE", "focused")
    manifest = os.environ.get("AGENTCTL_CHECK_MANIFEST")
    directory = (
        Path(manifest).parent
        if manifest is not None
        else tmp_path_factory.mktemp("host")
    )
    return observe(root, nonce, directory / "host.json")
