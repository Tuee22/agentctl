# Copyright (c) 2026 agentctl contributors.
"""Disposable git object fixtures; no staging, commits or ref commands run."""

import hashlib
import zlib
from pathlib import Path


def _object(root: Path, kind: str, data: bytes) -> str:
    """Write an independently encoded loose object into a fixture repository."""
    payload = (
        kind.encode("ascii") + b" " + str(len(data)).encode("ascii") + b"\0" + data
    )
    identifier = hashlib.sha1(payload, usedforsecurity=False).hexdigest()
    path = root / ".git/objects" / identifier[:2] / identifier[2:]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(zlib.compress(payload))
    return identifier


def _tree(root: Path, files: tuple[tuple[str, bytes], ...]) -> str:
    """Encode nested tree entries using git's documented object representation."""
    names = tuple(sorted({name.split("/", 1)[0] for name, _data in files}))
    entries = b""
    for name in names:
        children = tuple(
            (path[len(name) + 1 :], value)
            for path, value in files
            if path.startswith(name + "/")
        )
        if children:
            mode, identifier = "40000", _tree(root, children)
        else:
            value = next(value for path, value in files if path == name)
            mode, identifier = "100644", _object(root, "blob", value)
        entries += (
            mode.encode("ascii")
            + b" "
            + name.encode("utf-8")
            + b"\0"
            + bytes.fromhex(identifier)
        )
    return _object(root, "tree", entries)


def repository(
    root: Path, files: tuple[tuple[str, bytes], ...] = (), *, with_head: bool = False
) -> str:
    """Create an owned repository with either an unborn or encoded HEAD."""
    (root / ".git/objects").mkdir(parents=True)
    (root / ".git/refs/heads").mkdir(parents=True)
    (root / ".git/HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    (root / ".git/config").write_text(
        "[core]\nrepositoryformatversion = 0\nbare = false\n", encoding="utf-8"
    )
    for filename, contents in files:
        path = root / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(contents)
    identifier = ""
    if with_head:
        tree = _tree(root, files)
        data = (
            f"tree {tree}\nauthor Fixture <fixture@example.invalid> 0 +0000\n"
            "committer Fixture <fixture@example.invalid> 0 +0000\n\nFixture\n"
        ).encode("ascii")
        identifier = _object(root, "commit", data)
        (root / ".git/refs/heads/main").write_text(identifier + "\n", encoding="ascii")
    return identifier
