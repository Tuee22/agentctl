# Copyright (c) 2026 agentctl contributors.
"""Closed-shape Hyper-V observer data and native refusal controls."""

import json
from pathlib import Path

import pytest

from agentctl.check.hyperv_observe import observe, parse
from agentctl.foundation import Err, Ok

pytestmark = pytest.mark.evidence("value")


def test_parse_rejects_ambiguous_and_incomplete_vm_observations() -> None:
    """Only complete typed rows, including a disk list, produce observed facts."""
    row = {
        "name": "one",
        "identifier": "id",
        "state": "Running",
        "generation": 2,
        "processors": 4,
        "startup_memory": 1024,
        "dynamic_memory": False,
        "disk_paths": [r"C:\private\one.vhdx"],
        "processor_limit": 100,
        "processor_reserve": 0,
        "disk_virtual_sizes": [100000],
    }
    assert isinstance(parse(json.dumps(row)), Ok)
    for bad in (
        {**row, "processors": True},
        {**row, "processor_limit": True},
        {**row, "processor_reserve": "zero"},
        {**row, "disk_virtual_sizes": [True]},
        {**row, "disk_paths": "disk"},
        {**row, "extra": 1},
        {key: value for key, value in row.items() if key != "state"},
    ):
        assert isinstance(parse(json.dumps(bad)), Err)
    assert isinstance(parse('{"name":"a","name":"b"}'), Err)


def test_observer_rejects_bad_identifier(tmp_path: Path) -> None:
    """A malformed VM identifier cannot become a PowerShell argument."""
    assert isinstance(observe("not-a-uuid", cwd=tmp_path), Err)
