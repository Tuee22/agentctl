# Copyright (c) 2026 agentctl contributors.
"""Defensive refusals of the guest-side shared-checkout binding checks."""

import os
from collections.abc import Callable, Mapping
from io import TextIOWrapper
from pathlib import Path

import pytest

from agentctl.check import virtualbox_binding
from agentctl.check.virtualbox_binding import (
    GuestFacts,
    Receipt,
    check_shared_checkout,
    encode,
)
from agentctl.foundation import Err, Ok

pytestmark = pytest.mark.evidence("value")
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
MOUNTINFO = Path("/proc/self/mountinfo")
PRODUCT = Path("/sys/class/dmi/id/product_name")
MEMINFO = Path("/proc/meminfo")
ROOT_ONLY = "1 0 0:1 / /other rw - tmpfs tmpfs rw\n"
OWNER_ONLY = 0o600


def _reader(
    overrides: Mapping[Path, str | OSError],
) -> Callable[[Path, str | None], str]:
    """Build a reader that replaces only the named files' contents or failure."""
    real = Path.read_text

    def read_text(self: Path, encoding: str | None = None) -> str:
        """Return an override for a named path, else read the real file."""
        match overrides.get(self):
            case OSError() as failure:
                raise failure
            case str() as text:
                return text
            case _:
                return real(self, encoding=encoding)

    return read_text


def _receipt_file(tmp_path: Path) -> Path:
    """Write a private, well-formed receipt."""
    path = tmp_path / "binding.json"
    path.write_text(encode(RECEIPT), encoding="utf-8")
    path.chmod(OWNER_ONLY)
    return path


def test_receipt_owner_identity_must_be_available(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A platform without user identities cannot vouch for receipt ownership."""
    reader = virtualbox_binding.__dict__["_private_receipt"]
    monkeypatch.delattr(os, "getuid")
    assert reader(_receipt_file(tmp_path)) == Err(
        "binding receipt owner identity unavailable"
    )


def test_receipt_changed_during_reading_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A receipt whose size changes while it is read is not accepted."""
    reader = virtualbox_binding.__dict__["_private_receipt"]
    path = _receipt_file(tmp_path)
    real = Path.open

    def racing(self: Path, encoding: str | None = None) -> TextIOWrapper:
        """Open the receipt, then lengthen it before the observation ends."""
        stream = real(self, encoding=encoding)
        with real(self, "a", encoding="utf-8") as writer:
            writer.write(" ")
        return stream

    monkeypatch.setattr(Path, "open", racing)
    assert reader(path) == Err("binding receipt changed during inspection")


def test_guest_capacity_refuses_unreadable_and_foreign_guests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unreadable or non-VirtualBox guest identity is refused."""
    check = virtualbox_binding.__dict__["_shared_guest_capacity"]
    monkeypatch.setattr(Path, "read_text", _reader({PRODUCT: OSError("denied")}))
    unreadable = check(RECEIPT)
    assert isinstance(unreadable, Err)
    assert unreadable.error.startswith("cannot inspect VirtualBox guest identity: ")
    monkeypatch.setattr(Path, "read_text", _reader({PRODUCT: "KVM\n"}))
    assert check(RECEIPT) == Err("shared checkout is not in a Debian VirtualBox guest")


def test_checkout_mount_refusals(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Unreadable, malformed and unrelated mount tables are refused."""
    receipt = tmp_path / "missing.json"
    assert check_shared_checkout(tmp_path, "Windows", receipt) == Ok(None)
    monkeypatch.setattr(Path, "read_text", _reader({MOUNTINFO: OSError("denied")}))
    unreadable = check_shared_checkout(tmp_path, "Linux", receipt)
    assert isinstance(unreadable, Err)
    assert unreadable.error.startswith("cannot inspect checkout mount: ")
    monkeypatch.setattr(Path, "read_text", _reader({MOUNTINFO: "garbage\n"}))
    assert isinstance(check_shared_checkout(tmp_path, "Linux", receipt), Err)
    monkeypatch.setattr(Path, "read_text", _reader({MOUNTINFO: ROOT_ONLY}))
    assert isinstance(
        check_shared_checkout(Path("/nonexistent"), "Linux", receipt), Err
    )
