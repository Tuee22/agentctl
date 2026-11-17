# Copyright (c) 2026 agentctl contributors.
"""Pinned, noninteractive guest connection construction."""

import base64
import hashlib
from dataclasses import replace
from pathlib import Path

import pytest

from agentctl.check.hyperv_ssh import ED25519_PREFIX, Connection, arguments
from agentctl.foundation import Err, Ok

pytestmark = pytest.mark.evidence("value")
KEY = ED25519_PREFIX + bytes(range(32))
ENCODED = base64.b64encode(KEY).decode("ascii")
FINGERPRINT = "SHA256:" + base64.b64encode(hashlib.sha256(KEY).digest()).decode(
    "ascii"
).rstrip("=")


def test_ssh_arguments_require_pinned_key_and_reject_injection(tmp_path: Path) -> None:
    """A connection rejects another key and shell syntax in caller data."""
    source = tmp_path / "source"
    connection = Connection(
        tmp_path / "ssh.exe",
        tmp_path / "key",
        tmp_path / "known_hosts",
        "192.168.12.9",
        22,
        "agentctl",
        "/home/agentctl/bin/python",
        FINGERPRINT,
    )
    hosts = "192.168.12.9 ssh-ed25519 " + ENCODED + "\n"
    valid = arguments(connection, source_root=source, known_hosts_text=hosts)
    assert isinstance(valid, Ok)
    assert "StrictHostKeyChecking=yes" in valid.value
    assert "BatchMode=yes" in valid.value
    for changed in (
        replace(connection, user="agentctl;id"),
        replace(connection, guest_python="/opt/python;id"),
        replace(connection, private_key=source / "key"),
        replace(connection, address="192.168.12.10"),
        replace(connection, host_fingerprint="SHA256:wrong"),
        replace(connection, port=True),
    ):
        assert isinstance(
            arguments(changed, source_root=source, known_hosts_text=hosts), Err
        )
    assert isinstance(
        arguments(connection, source_root=source, known_hosts_text=hosts + hosts), Err
    )
