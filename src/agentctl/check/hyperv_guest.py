# Copyright (c) 2026 agentctl contributors.
"""Observe Linux guest identity without asserting a Hyper-V host binding."""

import platform
import re
from dataclasses import dataclass
from pathlib import Path

from agentctl.foundation import Err, Ok, Result


@dataclass(frozen=True, slots=True)
class GuestIdentity:
    """Guest-supplied identity facts, not proof of the host VM registration."""

    family: str
    kernel: str
    vendor: str
    product: str
    release: str
    machine_id: str
    uid: int


def common_problems(identity: GuestIdentity) -> tuple[str, ...]:
    """Reject malformed or non-Debian guest facts on any supported VM."""
    ids = re.findall(r'(?m)^ID=(?:"([^"\n]+)"|([^\s"\n]+))$', identity.release)
    observed = tuple(quoted or plain for quoted, plain in ids)
    return (
        *(
            ("guest is not Debian Linux",)
            if identity.family != "Linux" or observed != ("debian",)
            else ()
        ),
        *(("guest kernel is invalid",) if not identity.kernel else ()),
        *(
            ("guest machine identity is invalid",)
            if re.fullmatch(r"[0-9a-f]{32}", identity.machine_id) is None
            or identity.machine_id == "0" * 32
            else ()
        ),
        *(
            ("guest user identity is invalid",)
            if isinstance(identity.uid, bool) or identity.uid <= 0
            else ()
        ),
    )


def problems(identity: GuestIdentity) -> tuple[str, ...]:
    """Reject non-Debian, root, malformed and non-Hyper-V guest observations."""
    return (
        *common_problems(identity),
        *(
            ("guest is not a Hyper-V virtual machine",)
            if identity.vendor != "Microsoft Corporation"
            or identity.product != "Virtual Machine"
            or "microsoft-standard-wsl2" in identity.kernel.lower()
            else ()
        ),
    )


def effective_uid(status: str) -> Result[int, str]:
    """Read exactly one Linux effective UID field from the current process status."""
    lines = tuple(line for line in status.splitlines() if line.startswith("Uid:"))
    if len(lines) != 1:
        return Err("guest UID is unavailable")
    match = re.fullmatch(
        r"Uid:[ \t]+[0-9]+[ \t]+([0-9]+)[ \t]+[0-9]+[ \t]+[0-9]+[ \t]*",
        lines[0],
    )
    return Err("guest UID is unavailable") if match is None else Ok(int(match[1]))


def observe_facts() -> Result[GuestIdentity, str]:
    """Read guest-supplied facts without assigning or authenticating a VM family."""
    if platform.system() != "Linux":
        return Err("guest observation requires Linux")
    try:
        uid = effective_uid(Path("/proc/self/status").read_text(encoding="utf-8"))
        if isinstance(uid, Err):
            return uid
        identity = GuestIdentity(
            platform.system(),
            platform.release(),
            Path("/sys/class/dmi/id/sys_vendor").read_text(encoding="utf-8").strip(),
            Path("/sys/class/dmi/id/product_name").read_text(encoding="utf-8").strip(),
            Path("/etc/os-release").read_text(encoding="utf-8"),
            Path("/etc/machine-id").read_text(encoding="ascii").strip(),
            uid.value,
        )
    except (OSError, UnicodeError) as exc:
        return Err("cannot observe guest identity: " + str(exc))
    return Ok(identity)


def observe() -> Result[GuestIdentity, str]:
    """Read current guest facts; a host-side channel must authenticate the peer."""
    observed = observe_facts()
    if isinstance(observed, Err):
        return observed
    failures = problems(observed.value)
    return Err("; ".join(failures)) if failures else observed
