# Copyright (c) 2026 agentctl contributors.
"""Independent positive and refusing Hyper-V configuration cases."""

from dataclasses import replace

import pytest

from agentctl.check.hyperv_facts import VmFacts, problems

pytestmark = pytest.mark.evidence("value")
IDENTIFIER = "4ba0db52-1f0c-498b-85e3-98f6c0cf0c39"
ROOT = r"C:\private\agentctl"
FACTS = VmFacts(
    "agentctl",
    IDENTIFIER,
    "Running",
    2,
    4,
    8192,
    dynamic_memory=False,
    disk_paths=(ROOT + r"\vm.vhdx",),
    processor_limit=100,
    processor_reserve=0,
    disk_virtual_sizes=(100000,),
)


def _problems(facts: VmFacts) -> tuple[str, ...]:
    return problems(facts, name="agentctl", identifier=IDENTIFIER, disk_root=ROOT)


def test_hyperv_configuration_requires_identity_limits_and_owned_disks() -> None:
    """A matching name alone cannot substitute for VM identity or bounded storage."""
    assert _problems(FACTS) == ()
    assert "VM identity mismatch" in _problems(replace(FACTS, identifier="invalid"))
    assert "VM identity mismatch" in _problems(replace(FACTS, name="another"))
    assert "VM is not a running generation 2 guest" in _problems(
        replace(FACTS, state="Off")
    )
    assert "VM CPU or fixed memory is invalid" in _problems(
        replace(FACTS, dynamic_memory=True)
    )
    assert "VM CPU or fixed memory is invalid" in _problems(
        replace(FACTS, processors=True)
    )
    for changed in (
        replace(FACTS, processor_limit=0),
        replace(FACTS, processor_limit=101),
        replace(FACTS, processor_reserve=101),
        replace(FACTS, processor_limit=25, processor_reserve=26),
        replace(FACTS, processor_limit=True),
    ):
        assert "VM CPU or fixed memory is invalid" in _problems(changed)
    for sizes in ((), (0,), (True,), (10, 20)):
        assert "VM virtual disk capacity is invalid" in _problems(
            replace(FACTS, disk_virtual_sizes=sizes)
        )
    for disk in (
        r"C:\private\agentctl-other\vm.vhdx",
        ROOT + r"\..\other\vm.vhdx",
        r"D:\vm.vhdx",
    ):
        assert "VM disks are outside the owned storage boundary" in _problems(
            replace(FACTS, disk_paths=(disk,))
        )
