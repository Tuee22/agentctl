# Copyright (c) 2026 agentctl contributors.
"""Compatibility exports for the shared process boundary."""

from agentctl.foundation_process import (
    ByteOutput,
    Child,
    Output,
    SpawnError,
    alive,
    finish,
    foreground,
    linux_birth,
    process_birth,
    registered_alive,
    replace,
    run,
    run_bytes,
    start,
    start_protocol,
    stop,
    windows_birth,
)

__all__ = [
    "ByteOutput",
    "Child",
    "Output",
    "SpawnError",
    "alive",
    "finish",
    "foreground",
    "linux_birth",
    "process_birth",
    "registered_alive",
    "replace",
    "run",
    "run_bytes",
    "start",
    "start_protocol",
    "stop",
    "windows_birth",
]
