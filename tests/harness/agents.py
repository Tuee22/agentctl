# Copyright (c) 2026 agentctl contributors.
"""Agent CLI observations confined to disposable homes and native fixtures."""

import json
import os
import shutil
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from agentctl.bootstrap import build
from agentctl.process import Output
from agentctl.result import Ok
from tests.harness.nonce import fresh
from tests.harness.tmux import object_value, validate_record

SYSTEM_KEYS = frozenset(
    {
        "PATH",
        "PATHEXT",
        "SYSTEMROOT",
        "SystemRoot",
        "WINDIR",
        "COMSPEC",
        "TEMP",
        "TMP",
        "TMPDIR",
        "LD_LIBRARY_PATH",
        "DYLD_LIBRARY_PATH",
    }
)


def isolated_environment(
    directory: Path, original: Mapping[str, str]
) -> dict[str, str]:
    """Expose no auth variables, project settings, user files or OS credential store."""
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    home = directory / "home"
    home.mkdir(mode=0o700)
    claude = directory / "claude"
    claude.mkdir(mode=0o700)
    codex = directory / "codex"
    codex.mkdir(mode=0o700)
    (codex / "config.toml").write_text(
        'cli_auth_credentials_store = "file"\n', encoding="utf-8"
    )
    return {
        **{key: value for key, value in original.items() if key in SYSTEM_KEYS},
        "HOME": str(home),
        "USERPROFILE": str(home),
        "APPDATA": str(directory / "appdata"),
        "LOCALAPPDATA": str(directory / "localappdata"),
        "CLAUDE_CONFIG_DIR": str(claude),
        "CODEX_HOME": str(codex),
        "DISABLE_AUTOUPDATER": "1",
        "PSMUX_DATA_DIR": str(directory / "psmux"),
        "PSMUX_NO_WARM": "1",
        "TMUX_TMPDIR": str(directory),
        **{
            f"XDG_{kind}_HOME": str(directory / kind.lower())
            for kind in ("CACHE", "CONFIG", "DATA", "STATE")
        },
    }


def native_agent(name: str, family: str, environment: Mapping[str, str]) -> Path:
    """Require a real native .exe on Windows and the PATH executable elsewhere."""
    requested = name + (".exe" if family == "Windows" else "")
    found = shutil.which(requested, path=environment.get("PATH", ""))
    assert found is not None, requested + " is required on the agent-host lane"
    path = Path(found).absolute()
    assert path.is_file()
    if family == "Windows":
        assert path.suffix.lower() == ".exe", "agent-host requires a native executable"
    return path


@dataclass(frozen=True, slots=True)
class AuthProbe:
    """One native auth request with no environment values in its representation."""

    agent: str
    executable: Path
    directory: Path
    deadline: int = 10_000_000


def probe(
    context: build.BuildContext,
    request: AuthProbe,
    environment: Mapping[str, str],
) -> dict[str, object]:
    """Invoke the real production auth probe through its native test boundary."""
    payload = {
        "agent": request.agent,
        "executable": str(request.executable),
        "directory": str(request.directory),
        "deadline": request.deadline,
    }
    answer = build.execute_binary(
        context,
        build.BinaryCall(
            "test:agentctl-core-test",
            ("--agent-fixture",),
            input_text=json.dumps(payload),
            protocol=None,
            settings=tuple(environment.items()),
        ),
    )
    assert isinstance(answer, Ok), answer
    assert answer.value.code == 0, answer.value.stderr
    return object_value(answer.value.stdout)


def preflight(
    context: build.BuildContext,
    agent: str,
    directory: Path,
    environment: Mapping[str, str],
) -> Output:
    """Expose the actual preflight exit code and invoking-process warning stream."""
    result = build.execute_binary(
        context,
        build.BinaryCall(
            "test:agentctl-core-test",
            ("--agent-fixture",),
            input_text=json.dumps(
                {
                    "operation": "preflight",
                    "agent": agent,
                    "directory": str(directory),
                    "distribution": "ubuntu",
                }
            ),
            protocol=None,
            settings=tuple(environment.items()),
        ),
    )
    assert isinstance(result, Ok), result
    return result.value


@dataclass(frozen=True, slots=True)
class PreflightScope:
    """One private PATH and nonce-bound fake agent used by native preflight tests."""

    agent: str
    directory: Path
    binaries: Path
    executable: Path
    records: Path
    nonce: str
    environment: dict[str, str]

    def record(self, reason: str) -> dict[str, object]:
        """Require one current invocation rather than accepting an absent observer."""
        files = tuple(self.records.glob("*.json"))
        assert len(files) == 1, reason
        value = object_value(files[0].read_text(encoding="utf-8"))
        validate_record(value, self.nonce)
        return value

    def add_multiplexer(self, family: str) -> None:
        """Copy only the actual native multiplexer into this test's private PATH."""
        name = "psmux.exe" if family == "Windows" else "tmux"
        original = shutil.which(name)
        assert original is not None, "the mux-host lane is required"
        shutil.copy2(original, self.binaries / name)


def preflight_scope(
    context: build.BuildContext,
    directory: Path,
    family: str,
    agent: str,
    *,
    status: str = "0",
) -> PreflightScope:
    """Install the native observer with no mux until the test supplies its control."""
    environment = isolated_environment(directory, os.environ)
    binaries = directory / "bin with spaces"
    binaries.mkdir()
    records = directory / "records"
    records.mkdir(mode=0o700)
    nonce = fresh("preflight")
    environment.update(
        {
            "PATH": str(binaries),
            "AGENTCTL_FAKE_NONCE": nonce,
            "AGENTCTL_FAKE_RECORD_DIR": str(records),
            "AGENTCTL_FAKE_EXIT": status,
        }
    )
    original = build.binary(context, "exe:agentctl-fake-agent")
    assert isinstance(original, Ok), original
    executable = binaries / (agent + (".exe" if family == "Windows" else ""))
    shutil.copy2(original.value, executable)
    return PreflightScope(
        agent, directory, binaries, executable, records, nonce, environment
    )
