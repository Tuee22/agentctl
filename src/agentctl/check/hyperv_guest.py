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


def problems(identity: GuestIdentity) -> tuple[str, ...]:
    """Reject non-Debian, root, malformed and non-Hyper-V guest observations."""
    ids = re.findall(r'(?m)^ID=(?:"([^"\n]+)"|([^\s"\n]+))$', identity.release)
    observed = tuple(quoted or plain for quoted, plain in ids)
    return (
        *(
            ("guest is not Debian Linux",)
            if identity.family != "Linux" or observed != ("debian",)
            else ()
        ),
        *(
            ("guest is not a Hyper-V virtual machine",)
            if identity.vendor != "Microsoft Corporation"
            or identity.product != "Virtual Machine"
            or not identity.kernel
            or "microsoft-standard-wsl2" in identity.kernel.lower()
            else ()
        ),
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


def effective_uid(status: str) -> Result[int, str]:
    """Read exactly one Linux effective UID field from the current process status."""
    values = re.findall(r"(?m)^Uid:\s+\d+\s+(\d+)\s+\d+\s+\d+\s*$", status)
    return Ok(int(values[0])) if len(values) == 1 else Err("guest UID is unavailable")


def observe() -> Result[GuestIdentity, str]:
    """Read current guest facts; a host-side channel must authenticate the peer."""
    if platform.system() != "Linux":
        return Err("Hyper-V guest observation requires Linux")
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
        return Err("cannot observe Hyper-V guest identity: " + str(exc))
    failures = problems(identity)
    return Err("; ".join(failures)) if failures else Ok(identity)
