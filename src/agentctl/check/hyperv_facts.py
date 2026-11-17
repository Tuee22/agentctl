# Copyright (c) 2026 agentctl contributors.
"""Validate independently observed Hyper-V configuration without issuing receipts."""

from dataclasses import dataclass
from pathlib import PureWindowsPath
from uuid import UUID

GENERATION = 2
MAX_PERCENT = 100


@dataclass(frozen=True, slots=True)
class VmFacts:
    """Host-observed configuration for one running validation VM."""

    name: str
    identifier: str
    state: str
    generation: int
    processors: int
    startup_memory: int
    dynamic_memory: bool
    disk_paths: tuple[str, ...]
    processor_limit: int
    processor_reserve: int
    disk_virtual_sizes: tuple[int, ...]


def problems(
    facts: VmFacts, *, name: str, identifier: str, disk_root: str
) -> tuple[str, ...]:
    """Reject mismatched identity, unbounded settings and disks outside the owned root.

    These checks do not authenticate the observation or prove live resource limits.
    """
    errors: tuple[str, ...] = ()
    try:
        valid_identity = (
            bool(name)
            and facts.name == name
            and UUID(facts.identifier) == UUID(identifier)
            and UUID(identifier).int != 0
        )
    except (ValueError, AttributeError, TypeError):
        valid_identity = False
    if not valid_identity:
        errors += ("VM identity mismatch",)
    if facts.state != "Running" or facts.generation != GENERATION:
        errors += ("VM is not a running generation 2 guest",)
    if (
        isinstance(facts.processors, bool)
        or facts.processors <= 0
        or isinstance(facts.startup_memory, bool)
        or facts.startup_memory <= 0
        or facts.dynamic_memory is not False
        or isinstance(facts.processor_limit, bool)
        or isinstance(facts.processor_reserve, bool)
        or not 0 < facts.processor_limit <= MAX_PERCENT
        or not 0 <= facts.processor_reserve <= facts.processor_limit
    ):
        errors += ("VM CPU or fixed memory is invalid",)
    root = PureWindowsPath(disk_root)
    disks = tuple(PureWindowsPath(path) for path in facts.disk_paths)
    if len(facts.disk_virtual_sizes) != len(disks) or any(
        isinstance(size, bool) or size <= 0 for size in facts.disk_virtual_sizes
    ):
        errors += ("VM virtual disk capacity is invalid",)
    if (
        not root.is_absolute()
        or ".." in root.parts
        or not disks
        or len(set(disks)) != len(disks)
        or any(
            not path.is_absolute()
            or ".." in path.parts
            or path == root
            or not path.is_relative_to(root)
            or path.suffix.lower() not in {".vhd", ".vhdx", ".avhdx"}
            for path in disks
        )
    ):
        errors += ("VM disks are outside the owned storage boundary",)
    return errors
