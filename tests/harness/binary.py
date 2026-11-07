# Copyright (c) 2026 agentctl contributors.
"""Owned binary build caches sharing only agentctl's immutable dependency store."""

import os
import secrets
import shutil
from dataclasses import replace
from pathlib import Path

from agentctl.bootstrap import binary, build, toolchain
from agentctl.result import Ok
from tests.harness.haskell import copy_project


def request(root: Path, directory: Path) -> binary.Request:
    """Keep source, output, homes, locks and pin edits in the test's own directory."""
    context = copy_project(root, directory)
    shared = context.host.cache / "cabal"
    storage = os.environ.get("AGENTCTL_TEST_NATIVE_ROOT")
    cache = (
        Path(storage) / secrets.token_hex(4)
        if storage is not None
        else directory / "cache"
    )
    host = replace(context.host, cache=cache, interactive=False, assume_yes=False)
    assert toolchain.record(context.tools, host.cache) == Ok(context.tools)
    private = host.cache / "cabal"
    private.mkdir(parents=True)
    (private / "config").write_text(
        "repository hackage.haskell.org\n  url: https://hackage.haskell.org/\n"
        f"store-dir: {shared / 'store'}\nremote-repo-cache: {shared / 'packages'}\n",
        encoding="utf-8",
    )
    index = private / "packages/hackage.haskell.org/01-index.tar"
    index.parent.mkdir(parents=True)
    original = shared / "packages/hackage.haskell.org/01-index.tar"
    try:
        index.hardlink_to(original)
    except OSError:
        shutil.copyfile(original, index)
    state = build.index_state(context.project)
    assert isinstance(state, Ok)
    (private / "agentctl-index-state").write_text(state.value, encoding="utf-8")
    pins = directory / "pins.toml"
    shutil.copyfile(root / "src/agentctl/bootstrap/pins.toml", pins)
    return binary.Request(context.project, pins, host, directory / "data")
