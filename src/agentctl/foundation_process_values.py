# Copyright (c) 2026 agentctl contributors.
"""Immutable process outcomes shared by the gate and the process boundary."""

from dataclasses import dataclass
from pathlib import Path

from agentctl.foundation import Family, Result


@dataclass(frozen=True, slots=True)
class ProcessImageFile:
    """File identity and digest sampled while a process image was live."""

    device: int
    inode: int
    size: int
    modified_ns: int
    sha256: str


@dataclass(frozen=True, slots=True)
class ProcessObservation:
    """A native image and creation identity observed while a child was live."""

    family: Family
    pid: int
    birth: int
    image: Path
    file: ProcessImageFile | None = None


@dataclass(frozen=True, slots=True)
class Output:
    """Decoded output and exit status from one process."""

    code: int
    stdout: str
    stderr: str
    observation: Result[ProcessObservation, "SpawnError"] | None = None


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
