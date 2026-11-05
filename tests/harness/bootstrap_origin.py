# Copyright (c) 2026 agentctl contributors.
"""Standard-library-only filesystem observations before first provisioning."""

import hashlib
import json
import os
import secrets
import shutil
from collections.abc import Mapping
from pathlib import Path

NONCE_LENGTH = 32


def location(family: str, env: Mapping[str, str], home: Path) -> Path:
    """Apply the documented prefix/XDG location independently of the subject."""
    if family == "Windows":
        return Path(env.get("GHCUP_INSTALL_BASE_PREFIX", "C:/")) / "ghcup/bin/ghcup.exe"
    if "GHCUP_USE_XDG_DIRS" in env:
        return Path(env.get("XDG_BIN_HOME", str(home / ".local/bin"))) / "ghcup"
    return Path(env.get("GHCUP_INSTALL_BASE_PREFIX", str(home))) / ".ghcup/bin/ghcup"


def found(family: str, env: Mapping[str, str], home: Path) -> Path | None:
    """Observe the configured file, PATH and default without invoking a tool."""
    candidate = location(family, env, home)
    if (
        "GHCUP_INSTALL_BASE_PREFIX" in env
        or (family != "Windows" and "GHCUP_USE_XDG_DIRS" in env)
    ) and candidate.is_file():
        return candidate.resolve()
    candidate_text = shutil.which(
        "ghcup.exe" if family == "Windows" else "ghcup", path=env.get("PATH", "")
    )
    if candidate_text is not None:
        return Path(candidate_text).resolve()
    fallback = location(family, {}, home)
    return fallback.resolve() if fallback.is_file() else None


def entries(directories: tuple[Path, ...]) -> dict[str, str]:
    """Read link targets, file bytes or absence as independent selection evidence."""
    result: dict[str, str] = {}
    for directory in directories:
        for name in ("ghc", "cabal", "ghc.exe", "cabal.exe"):
            path = directory / name
            result[str(path)] = (
                "link:" + str(path.readlink())
                if path.is_symlink()
                else "file:" + hashlib.sha256(path.read_bytes()).hexdigest()
                if path.exists()
                else "absent"
            )
    return result


def state_directory(family: str, env: Mapping[str, str], home: Path) -> Path:
    """Read the documented state location without calling the application's policy."""
    override = env.get("XDG_STATE_HOME")
    if override is not None and Path(override).is_absolute():
        return Path(override) / "agentctl"
    if family == "Windows":
        return (
            Path(env.get("LOCALAPPDATA", str(home / "AppData/Local")))
            / "agentctl/state"
        )
    return home / ".local/state/agentctl"


def capture(
    directory: Path, nonce: str, family: str, env: Mapping[str, str], home: Path
) -> dict[str, object]:
    """Record absence before provisioning, or preserve existing-tool evidence."""
    configured = location(family, env, home).absolute()
    previous = found(family, env, home)
    state = state_directory(family, env, home)
    witness = state / "pre-bootstrap.json"
    prefix = configured.parent.parent
    absent = (
        previous is None
        and all(
            shutil.which(name, path=env.get("PATH", "")) is None
            for name in ("ghc", "cabal")
        )
        and not (prefix / "ghc").exists()
        and not tuple(configured.parent.glob("cabal*"))
        and not tuple(configured.parent.glob("ghc-*"))
    )
    if absent and not witness.exists():
        state.mkdir(mode=0o700, parents=True, exist_ok=True)
        descriptor = os.open(witness, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(
                {
                    "nonce": secrets.token_hex(16),
                    "family": family,
                    "configured": str(configured),
                    "before": {"ghcup": False, "ghc": False, "cabal": False},
                },
                stream,
            )
    origin = "user"
    if witness.is_file():
        value: object = json.loads(witness.read_text(encoding="utf-8"))
        assert isinstance(value, dict)
        assert value.get("family") == family
        assert value.get("configured") == str(configured)
        assert value.get("before") == {"ghcup": False, "ghc": False, "cabal": False}
        identity = value.get("nonce")
        assert isinstance(identity, str)
        assert len(identity) == NONCE_LENGTH
        origin = "agentctl-installed"
    bindirs = (
        (configured.parent,)
        if previous is None or previous.parent == configured.parent
        else (configured.parent, previous.parent)
    )
    result: dict[str, object] = {
        "nonce": nonce,
        "family": family,
        "origin": origin,
        "configured": str(configured),
        "configured_existed": configured.exists() or configured.is_symlink(),
        "found": str(previous) if previous is not None else None,
        "sha256": hashlib.sha256(previous.read_bytes()).hexdigest()
        if previous is not None
        else None,
        "defaults": entries(bindirs),
    }
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    (directory / "bootstrap-host.json").write_text(json.dumps(result), encoding="utf-8")
    return result
