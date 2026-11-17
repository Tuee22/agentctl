# Copyright (c) 2026 agentctl contributors.
"""Parse native process-creation observations without assigning ownership."""

from agentctl.foundation import Err, Ok, Result


def linux_birth_stat(data: bytes, pid: int) -> Result[int, str]:
    """Parse Linux proc stat start ticks without decoding arbitrary process names."""
    closing = data.rfind(b")")
    if pid <= 0 or not data.startswith(str(pid).encode("ascii") + b" (") or closing < 0:
        return Err("invalid Linux process stat identity")
    fields = data[closing + 1 :].split()
    start_index = 19
    max_digits = 20
    if len(fields) <= start_index:
        return Err("Linux process start time unavailable")
    value = fields[start_index]
    if not value.isdigit() or len(value) > max_digits:
        return Err("invalid Linux process start time")
    start = int(value)
    if not 0 < start <= 2**64 - 1:
        return Err("invalid Linux process start time")
    return Ok(start)
