# Copyright (c) 2026 agentctl contributors.
"""Immutable process outcomes shared by the gate and the process boundary."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Output:
    """Decoded output and exit status from one process."""

    code: int
    stdout: str
    stderr: str


@dataclass(frozen=True, slots=True)
class ByteOutput:
    """Undecoded output and exit status from one process."""

    code: int
    stdout: bytes
    stderr: bytes


@dataclass(frozen=True, slots=True)
class SpawnError:
    """A process could not start or finish within its deadline."""

    message: str
