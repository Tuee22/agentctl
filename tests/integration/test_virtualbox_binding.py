# Copyright (c) 2026 agentctl contributors.
"""The live checkout's pre-gate VirtualBox binding receipt and its refusals."""

import json
import os
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from agentctl.check import virtualbox_bind, virtualbox_binding
from agentctl.check.evidence import Entry
from agentctl.check.virtualbox_binding import (
    GuestFacts,
    Receipt,
    census_digest,
    decode,
    decode_facts,
    encode,
    facts_json,
    meminfo,
    mount_line,
    observe_guest,
    platform_family,
    verify_capacity,
    verify_identity,
    virtualbox_guest,
)
from agentctl.foundation import Err, Ok
from agentctl.foundation_paths import directories
from agentctl.foundation_process import run

pytestmark = pytest.mark.evidence("observer")

SHARE = "agentctl-src"
MOUNT = (
    "76 29 0:37 / /srv/agentctl rw,nodev,relatime shared:22 - vboxsf agentctl-src "
    "rw,uid=1000"
)
DEPENDENCIES = (
    ("gcc", "14.2.0"),
    ("git", "git version 2.47.3"),
    ("pipx", "1.7.1"),
    ("python", "Python 3.13.5"),
    ("tmux", "tmux 3.5a"),
)
FACTS = GuestFacts("a" * 64, 3, MOUNT, 4, 1000, 10, 50, DEPENDENCIES)
RECEIPT = Receipt(
    "0" * 32,
    "9d7dc4eb-c2b5-4044-8bf1-8d8a6c684df8",
    SHARE,
    "C:/Users/example/agentctl",
    "/srv/agentctl",
    FACTS,
)


def _product() -> str:
    """Read the DMI product name a VirtualBox guest reports, if any."""
    path = Path("/sys/class/dmi/id/product_name")
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def _receipt() -> Receipt:
    """Read the stored receipt from the guest user's private state directory."""
    path = (
        directories("Linux", os.environ, Path.home()).state
        / virtualbox_binding.RECEIPT_NAME
    )
    assert path.is_file(), "pre-gate VirtualBox binding receipt is missing"
    parsed = decode(path.read_text(encoding="utf-8"))
    assert isinstance(parsed, Ok), parsed
    return parsed.value


def _native_linux_claims_no_share(root: Path) -> None:
    """Outside a VirtualBox guest, the checkout is not a VirtualBox shared folder."""
    mountinfo = Path("/proc/self/mountinfo").read_text(encoding="utf-8")
    assert isinstance(mount_line(mountinfo, root.as_posix(), SHARE), Err)


def test_shared_checkout_identity(root: Path) -> None:
    """In the guest, the live census and mount equal the pre-gate exchange."""
    family = platform_family()
    if family != "Linux":
        refused = observe_guest(root, SHARE, family)
        assert isinstance(refused, Err), "foreign host minted guest binding facts"
        assert "only inside the Linux guest" in refused.error
    elif virtualbox_guest(_product()):
        receipt = _receipt()
        observed = observe_guest(root, receipt.share, family)
        assert isinstance(observed, Ok), observed
        assert verify_identity(receipt, root.as_posix(), observed.value) == Ok(None)
    else:
        _native_linux_claims_no_share(root)


def test_capacity_and_dependency_receipt(root: Path) -> None:
    """In the guest, the allocation and dependencies equal the receipt."""
    family = platform_family()
    if family != "Linux":
        assert isinstance(observe_guest(root, SHARE, family), Err)
    elif virtualbox_guest(_product()):
        receipt = _receipt()
        observed = observe_guest(root, receipt.share, family)
        assert isinstance(observed, Ok), observed
        assert verify_capacity(receipt, observed.value) == Ok(None)
        assert receipt.facts.storage_free_bytes > 0
    else:
        _native_linux_claims_no_share(root)


def test_receipt_round_trip_and_refusals() -> None:
    """Encoding round-trips, and malformed or extended receipts are refused."""
    assert decode(encode(RECEIPT)) == Ok(RECEIPT)
    assert decode_facts(json.loads(facts_json(FACTS))) == Ok(FACTS)
    value = json.loads(encode(RECEIPT))
    refused = (
        "not json",
        json.dumps({**value, "extra": 1}),
        json.dumps({**value, "nonce": "XYZ"}),
        json.dumps({**value, "vm": "not-a-uuid"}),
        json.dumps({**value, "share": "bad share"}),
        json.dumps({**value, "guest_root": "relative"}),
        json.dumps({**value, "source": ""}),
        json.dumps({**value, "facts": {**value["facts"], "entries": 0}}),
        json.dumps({**value, "facts": {**value["facts"], "cpus": True}}),
        json.dumps({**value, "facts": {**value["facts"], "dependencies": {}}}),
        json.dumps({**value, "facts": {**value["facts"], "mount": "a\nb"}}),
    )
    accepted = tuple(text for text in refused if not isinstance(decode(text), Err))
    assert accepted == (), "invalid binding receipt accepted"


def test_identity_and_capacity_refuse_changes() -> None:
    """Changed roots, censuses, mounts, capacity and dependencies are refused."""
    assert verify_identity(RECEIPT, "/srv/agentctl", FACTS) == Ok(None)
    assert verify_identity(RECEIPT, "/other", FACTS) == Err(
        "binding receipt names a different guest root"
    )
    assert verify_identity(RECEIPT, "/srv/agentctl", replace(FACTS, entries=4)) == Err(
        "source census changed since the binding exchange"
    )
    assert verify_identity(RECEIPT, "/srv/agentctl", replace(FACTS, mount="x")) == Err(
        "source mount changed since the binding exchange"
    )
    assert verify_capacity(RECEIPT, FACTS) == Ok(None)
    assert verify_capacity(RECEIPT, replace(FACTS, cpus=2)) == Err(
        "guest capacity changed since the binding exchange"
    )
    changed = replace(FACTS, dependencies=(("gcc", "13"), *DEPENDENCIES[1:]))
    assert verify_capacity(RECEIPT, changed) == Err(
        "guest dependencies changed since the binding exchange"
    )


def test_mount_and_meminfo_values() -> None:
    """Only one vboxsf entry for the exact share and root is accepted."""
    assert mount_line(MOUNT, "/srv/agentctl", SHARE) == Ok(MOUNT)
    assert isinstance(mount_line(MOUNT, "/srv/other", SHARE), Err)
    assert isinstance(mount_line(MOUNT + "\n" + MOUNT, "/srv/agentctl", SHARE), Err)
    assert isinstance(mount_line(MOUNT, "/srv/agentctl", "other-share"), Err)
    assert isinstance(
        mount_line(MOUNT.replace("vboxsf", "ext4"), "/srv/agentctl", SHARE), Err
    )
    unseparated = MOUNT.replace(" - ", " + ")
    assert mount_line(unseparated, "/srv/agentctl", SHARE) == Err(
        "malformed mountinfo entry"
    )
    assert meminfo("MemTotal:  1000 kB\n", "MemTotal") == Ok(1000)
    assert isinstance(meminfo("MemTotal: x kB\n", "MemTotal"), Err)
    assert isinstance(meminfo("", "SwapTotal"), Err)
    assert virtualbox_guest("VirtualBox\n")
    assert not virtualbox_guest("Standard PC")


def test_census_digest_binds_paths_kinds_and_bytes() -> None:
    """Any path, kind or payload change alters the digest."""
    base = (Entry("a", "file", (b"x",)), Entry("d", "directory", ()))
    digest = census_digest(base)
    assert census_digest(tuple(reversed(base))) == digest
    assert census_digest((Entry("a", "file", (b"y",)), base[1])) != digest
    assert census_digest((Entry("b", "file", (b"x",)), base[1])) != digest
    assert census_digest((Entry("a", "symlink", (b"x",)), base[1])) != digest


def test_guest_observer_refusals(
    root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Foreign hosts, absent roots, absent shares and unreadable storage fail."""
    assert isinstance(observe_guest(root, SHARE, "Windows"), Err)
    if platform_family() == "Linux":
        assert isinstance(observe_guest(tmp_path / "missing", SHARE, "Linux"), Err)
        empty = tmp_path / "empty"
        empty.mkdir()
        unshared = observe_guest(empty, SHARE, "Linux")
        assert isinstance(unshared, Err)
        assert "not exactly one mount point" in unshared.error
        monkeypatch.setenv("HOME", str(tmp_path / "absent-home"))
        unreadable = observe_guest(empty, SHARE, "Linux")
        assert isinstance(unreadable, Err)
        assert "cannot read guest facts" in unreadable.error
    else:
        assert isinstance(observe_guest(root, SHARE, "Darwin"), Err)


def test_dependency_version_query_failures(tmp_path: Path) -> None:
    """A missing tool or failing query is reported rather than recorded."""
    version = virtualbox_binding.__dict__["_version"]
    missing = version(("agentctl-definitely-missing-tool",), tmp_path)
    assert isinstance(missing, Err)
    assert "is unavailable" in missing.error
    failing = version((sys.executable, "-c", "raise SystemExit(3)"), tmp_path)
    assert failing == Err(sys.executable + " version query failed")
    found = version((sys.executable, "--version"), tmp_path)
    assert isinstance(found, Ok)
    assert found.value.startswith("Python ")


def test_module_entry_points(root: Path, tmp_path: Path) -> None:
    """The guest entry point prints usage, refusal or facts as one line."""
    usage = run(
        [sys.executable, "-m", "agentctl.check.virtualbox_binding"],
        cwd=tmp_path,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    assert isinstance(usage, Ok)
    assert (usage.value.code, usage.value.stdout) == (2, "usage: observe ROOT SHARE\n")
    refused = virtualbox_binding.main(("observe", str(tmp_path / "missing"), SHARE))
    assert refused == 1
    if platform_family() == "Linux" and virtualbox_guest(_product()):
        assert virtualbox_binding.main(("observe", root.as_posix(), SHARE)) == 0


def test_host_binding_values() -> None:
    """The host tool's SSH prefix, VM identity and guest encoding are fixed."""
    prefix = virtualbox_bind.ssh_command(Path("/k"), Path("/h"), 44223, "agentctl")
    assert prefix[-1] == "agentctl@127.0.0.1"
    assert "StrictHostKeyChecking=yes" in prefix
    assert "BatchMode=yes" in prefix
    text = 'name="vm"\nUUID="9d7dc4eb-c2b5-4044-8bf1-8d8a6c684df8"\n'
    assert virtualbox_bind.vm_uuid(text, "vm") == Ok(RECEIPT.vm)
    assert isinstance(virtualbox_bind.vm_uuid(text, "other"), Err)
    assert isinstance(virtualbox_bind.vm_uuid(text + text, "vm"), Err)
