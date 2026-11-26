# Copyright (c) 2026 agentctl contributors.
"""Refusals of malformed binding inventories and unreadable source trees."""

import json
from pathlib import Path

import pytest

from agentctl.check import binding_inventory
from agentctl.check.evidence import Entry
from agentctl.foundation import Err, Ok

pytestmark = pytest.mark.evidence("value")
NONCE = "a" * 32
OTHER = "b" * 32
ENTRY = Entry("entry", "file", (b"bytes",))


def _text(entries: object) -> str:
    """Serialize raw rows under the expected nonce."""
    return json.dumps({"nonce": NONCE, "entries": entries})


def test_encode_refuses_bad_nonce_and_empty_inventory() -> None:
    """Both a malformed nonce and an invalid census are refused at encoding."""
    refused = Err("invalid binding inventory or nonce")
    assert binding_inventory.encode((ENTRY,), "bad") == refused
    assert binding_inventory.encode((), NONCE) == refused


def test_observe_reports_unreadable_source(tmp_path: Path) -> None:
    """A missing source root yields a census failure, never a partial inventory."""
    observed = binding_inventory.observe(tmp_path / "missing", NONCE)
    assert isinstance(observed, Err)
    assert observed.error.startswith("binding source census: ")


def test_decode_refuses_nonce_shape_fields_and_entries() -> None:
    """Stale, extra-field and malformed-row inventories do not decode."""
    assert binding_inventory.decode("{}", "bad") == Err(
        "invalid binding inventory nonce"
    )
    assert binding_inventory.decode("[]", NONCE) == Err(
        "invalid binding inventory fields"
    )
    assert binding_inventory.decode('{"nonce":"x"}', NONCE) == Err(
        "invalid binding inventory fields"
    )
    assert binding_inventory.decode(_text([["entry", "other", []]]), NONCE) == Err(
        "invalid binding inventory entry"
    )
    assert binding_inventory.decode(_text(1), NONCE) == Err(
        "binding inventory nonce or entries mismatch"
    )
    assert isinstance(binding_inventory.decode(_text([]), NONCE), Err)
    assert isinstance(binding_inventory.decode("{", NONCE), Err)


def test_compare_refuses_unreadable_source_and_undecodable_peer(
    tmp_path: Path,
) -> None:
    """The local census and the peer text must both be usable."""
    local = binding_inventory.compare(tmp_path / "missing", NONCE, "{}")
    assert isinstance(local, Err)
    assert local.error.startswith("binding source census: ")
    (tmp_path / "entry").write_bytes(b"bytes")
    undecodable = binding_inventory.compare(tmp_path, NONCE, "{")
    assert isinstance(undecodable, Err)
    assert undecodable.error.startswith("cannot decode binding inventory: ")
    matching = binding_inventory.observe(tmp_path, NONCE)
    assert isinstance(matching, Ok)
    assert binding_inventory.compare(tmp_path, NONCE, matching.value) == Ok(None)
    assert binding_inventory.compare(tmp_path, OTHER, matching.value) == Err(
        "binding inventory nonce or entries mismatch"
    )
