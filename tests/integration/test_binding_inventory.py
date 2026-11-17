# Copyright (c) 2026 agentctl contributors.
"""Independent process inventories compare actual complete checkout bytes."""

import json
import os
import secrets
import sys
from pathlib import Path

import pytest

from agentctl.check.binding_inventory import compare, decode, observe
from agentctl.process import run
from agentctl.result import Err, Ok

pytestmark = pytest.mark.evidence("real")


def test_independent_inventory_includes_untracked_and_ignored(
    root: Path, tmp_path: Path
) -> None:
    """A peer interpreter observes ignored bytes, additions and modifications."""
    source = tmp_path / "source"
    source.mkdir()
    (source / ".git").mkdir()
    (source / ".git" / "config").write_bytes(b"private git metadata")
    (source / ".gitignore").write_text("ignored.txt\n", encoding="utf-8")
    (source / "ignored.txt").write_bytes(b"ignored\x00bytes")
    (source / "untracked.txt").write_bytes(b"")
    nonce = secrets.token_hex(16)
    program = (
        "import sys\nfrom pathlib import Path\n"
        "sys.path.insert(0, sys.argv[1])\n"
        "from agentctl.check.binding_inventory import observe\n"
        "from agentctl.result import Ok\n"
        "result = observe(Path(sys.argv[2]), sys.argv[3])\n"
        "assert isinstance(result, Ok), result\n"
        "print(result.value)\n"
    )
    peer = run(
        [sys.executable, "-c", program, str(root / "src"), str(source), nonce],
        cwd=tmp_path,
        env=os.environ,
    )
    assert isinstance(peer, Ok), peer
    assert peer.value.code == 0, peer.value.stderr
    inventory = decode(peer.value.stdout, nonce)
    assert isinstance(inventory, Ok), inventory
    assert tuple(item.path for item in inventory.value) == (
        ".gitignore",
        "ignored.txt",
        "untracked.txt",
    )
    assert compare(source, nonce, peer.value.stdout) == Ok(None)
    (source / "ignored.txt").write_bytes(b"changed\x00bytes")
    assert isinstance(compare(source, nonce, peer.value.stdout), Err), (
        "changed inventory was accepted"
    )
    (source / "ignored.txt").write_bytes(b"ignored\x00bytes")
    (source / "new-untracked.txt").write_bytes(b"new")
    assert isinstance(compare(source, nonce, peer.value.stdout), Err), (
        "changed inventory was accepted"
    )
    (source / "new-untracked.txt").unlink()
    (source / "untracked.txt").unlink()
    (source / "untracked.txt").mkdir()
    assert isinstance(compare(source, nonce, peer.value.stdout), Err), (
        "changed inventory was accepted"
    )
    (source / "untracked.txt").rmdir()
    (source / "untracked.txt").write_bytes(b"")
    (source / "ignored.txt").unlink()
    (source / "ignored.txt").mkdir()
    assert isinstance(compare(source, nonce, peer.value.stdout), Err), (
        "changed inventory was accepted"
    )


def test_inventory_refuses_stale_and_malformed_data(tmp_path: Path) -> None:
    """Stale nonce, duplicate paths, malformed bytes and path aliases fail closed."""
    (tmp_path / "entry").write_bytes(b"hello")
    nonce = secrets.token_hex(16)
    captured = observe(tmp_path, nonce)
    assert isinstance(captured, Ok)
    assert isinstance(decode(captured.value, secrets.token_hex(16)), Err), (
        "stale inventory was accepted"
    )
    payload = json.loads(captured.value)
    payload["entries"].append(payload["entries"][0])
    assert isinstance(decode(json.dumps(payload), nonce), Err), (
        "duplicate inventory path was accepted"
    )
    invalid = (
        '{"nonce":"' + nonce + '","nonce":"' + nonce + '","entries":[]}',
        json.dumps({"nonce": nonce, "entries": [["../outside", "file", ["YQ=="]]]}),
        json.dumps({"nonce": nonce, "entries": [[".", "file", ["YQ=="]]]}),
        json.dumps({"nonce": nonce, "entries": [["entry", "file", ["***"]]]}),
        json.dumps({"nonce": nonce, "entries": [["entry", "directory", ["YQ=="]]]}),
    )
    for text in invalid:
        assert isinstance(decode(text, nonce), Err)
