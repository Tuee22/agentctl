# Copyright (c) 2026 agentctl contributors.
"""Constructed host counter records cannot establish live resource evidence."""

import json

import pytest

from agentctl.check.wsl_host_sample import Counters, parse_counters, shared_volume
from agentctl.result import Err, Ok

pytestmark = pytest.mark.evidence("value")
EXPECTED_HEADROOM = 3000


def test_host_counter_schema_and_commit_headroom() -> None:
    """Counter records preserve the difference between the limit and commitment."""
    parsed = parse_counters(
        json.dumps({"available": 4000, "committed": 6000, "limit": 9000})
    )
    assert parsed == Ok(Counters(4000, 6000, 9000))
    assert isinstance(parsed, Ok)
    assert parsed.value.headroom == EXPECTED_HEADROOM, "commitment was not subtracted"
    assert isinstance(
        parse_counters(
            json.dumps({"available": 4000, "committed": 9001, "limit": 9000})
        ),
        Err,
    ), "invalid commit counters were accepted"
    for value in (
        {"available": True, "committed": 6000, "limit": 9000},
        {"available": 4000, "committed": 6000},
        {"available": 4000, "committed": 6000, "limit": 9000, "extra": 1},
    ):
        assert isinstance(parse_counters(json.dumps(value)), Err)
    assert isinstance(parse_counters('{"available":1,"available":2}'), Err)
    assert isinstance(parse_counters("not json"), Err)
    assert shared_volume(123, 123), "shared host volume was not recognized"
    assert not shared_volume(123, 456), "separate host volumes were conflated"
    assert not shared_volume(0, 0)
