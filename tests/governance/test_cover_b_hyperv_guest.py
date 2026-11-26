# Copyright (c) 2026 agentctl contributors.
"""Refusal paths of the Hyper-V guest identity observer on a Linux guest."""

from pathlib import Path

import pytest

from agentctl.check import hyperv_guest
from agentctl.foundation import Err

pytestmark = pytest.mark.evidence("value")
STATUS_PATH = Path("/proc/self/status")
PRODUCT_PATH = Path("/sys/class/dmi/id/product_name")
OTHER_FAMILY = "Windows"


def _other_family() -> str:
    """Report a family other than Linux."""
    return OTHER_FAMILY


def test_observation_requires_linux(monkeypatch: pytest.MonkeyPatch) -> None:
    """A non-Linux family is refused by facts and by the policy observer."""
    monkeypatch.setattr(hyperv_guest.platform, "system", _other_family)
    expected = Err("guest observation requires Linux")
    assert hyperv_guest.observe_facts() == expected
    assert hyperv_guest.observe() == expected


def test_observation_refuses_unavailable_uid(monkeypatch: pytest.MonkeyPatch) -> None:
    """A process status without one Uid field is not an identity."""
    real = Path.read_text

    def read_text(self: Path, encoding: str | None = None) -> str:
        """Withhold the Uid field from the status file only."""
        return "Name:\tx\n" if self == STATUS_PATH else real(self, encoding=encoding)

    monkeypatch.setattr(Path, "read_text", read_text)
    assert hyperv_guest.observe_facts() == Err("guest UID is unavailable")


def test_observation_reports_unreadable_identity_files(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unreadable DMI file becomes a structured observation failure."""
    real = Path.read_text
    message = "denied"

    def read_text(self: Path, encoding: str | None = None) -> str:
        """Fail only the DMI product read."""
        if self == PRODUCT_PATH:
            raise PermissionError(message)
        return real(self, encoding=encoding)

    monkeypatch.setattr(Path, "read_text", read_text)
    result = hyperv_guest.observe_facts()
    assert isinstance(result, Err)
    assert result.error.startswith("cannot observe guest identity: ")
