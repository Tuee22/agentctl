# Copyright (c) 2026 agentctl contributors.
"""Observe VirtualBox guest facts without authenticating a host VM binding."""

from agentctl.check.hyperv_guest import GuestIdentity, common_problems, observe_facts
from agentctl.foundation import Err, Result


def problems(identity: GuestIdentity) -> tuple[str, ...]:
    """Reject malformed guest facts and foreign or WSL virtual machine identities."""
    return (
        *common_problems(identity),
        *(
            ("guest is not a VirtualBox virtual machine",)
            if identity.vendor != "innotek GmbH"
            or identity.product != "VirtualBox"
            or "microsoft-standard-wsl2" in identity.kernel.lower()
            else ()
        ),
    )


def observe() -> Result[GuestIdentity, str]:
    """Read local guest facts; the host must separately authenticate their source."""
    observed = observe_facts()
    if isinstance(observed, Err):
        return observed
    failures = problems(observed.value)
    return Err("; ".join(failures)) if failures else observed
