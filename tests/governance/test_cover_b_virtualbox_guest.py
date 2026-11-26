# Copyright (c) 2026 agentctl contributors.
"""A non-Linux observation is not a VirtualBox guest identity."""

import pytest

from agentctl.check import hyperv_guest, virtualbox_guest
from agentctl.foundation import Err

pytestmark = pytest.mark.evidence("value")


def _other_family() -> str:
    """Report a family other than Linux."""
    return "Windows"


def test_guest_observation_propagates_a_failed_fact_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The policy observer returns the failed fact observation unchanged."""
    monkeypatch.setattr(hyperv_guest.platform, "system", _other_family)
    assert virtualbox_guest.observe() == Err("guest observation requires Linux")
