# Copyright (c) 2026 agentctl contributors.
"""Constructed registration facts are consistency checks, not ownership proof."""

import json
from dataclasses import replace

import pytest

from agentctl.check.wsl_registration import (
    Registration,
    listed_version,
    parse,
    select,
    version_bytes_result,
    version_result,
)
from agentctl.process import ByteOutput, Output
from agentctl.result import Err, Ok

pytestmark = pytest.mark.evidence("value")

IDENTIFIER = "{854ac4df-1457-43ff-905e-2262d4de1f10}"
OWNED = r"C:\agentctl-validation"
BASE = r"C:\agentctl-validation\debian"


def test_registration_requires_exact_owned_wsl2_identity() -> None:
    """A different version, identifier or storage boundary refuses selection."""
    expected = Registration(IDENTIFIER, "dedicated", BASE, 2)
    assert select((expected,), expected, OWNED, 2) == Ok(expected)
    assert isinstance(select((expected,), expected, OWNED, 1), Err), (
        "WSL1 listing was accepted"
    )
    assert isinstance(
        select((replace(expected, version=1),), expected, OWNED, 2), Err
    ), "WSL1 registration was accepted"
    changed = replace(expected, identifier="{11111111-1111-1111-1111-111111111111}")
    assert isinstance(select((changed,), expected, OWNED, 2), Err), (
        "wrong WSL registration was accepted"
    )
    outside = replace(expected, base=r"C:\personal\debian")
    assert isinstance(select((outside,), outside, OWNED, 2), Err), (
        "unowned WSL storage was accepted"
    )
    assert isinstance(select((expected, expected), expected, OWNED, 2), Err)
    assert isinstance(
        select((expected, replace(expected, name="other")), expected, OWNED, 2), Err
    )
    assert isinstance(select((expected,), expected, BASE, 2), Err)
    assert isinstance(select((expected,), expected, r"D:\other", 2), Err)


def test_registration_parser_refuses_ambiguous_rows() -> None:
    """Duplicate identifiers, malformed paths and non-integer versions refuse."""
    row = {"identifier": IDENTIFIER, "name": "dedicated", "base": BASE, "version": 2}
    parsed = parse(json.dumps([row]))
    assert parsed == Ok((Registration(IDENTIFIER, "dedicated", BASE, 2),))
    assert isinstance(parse(json.dumps([row, row])), Err)
    assert isinstance(parse(json.dumps([{**row, "version": True}])), Err)
    assert isinstance(
        parse(json.dumps([{**row, "base": r"C:\agentctl\..\other"}])), Err
    )
    assert isinstance(parse('{"identifier":"x","identifier":"y"}'), Err)
    assert isinstance(parse("not json"), Err)


def test_version_listing_requires_exact_unambiguous_name() -> None:
    """The native listing identifies the requested row and its actual version."""
    listing = (
        "  NAME                   STATE      VERSION\n"
        "* personal               Running    1\n"
        "  dedicated-other        Stopped    1\n"
        "  dedicated              Running    2\n"
    )
    assert listed_version(listing, "dedicated") == Ok(2)
    assert listed_version("\x00".join(listing), "dedicated") == Ok(2)
    assert listed_version(listing, "personal") == Ok(1)
    assert isinstance(listed_version(listing, "missing"), Err)
    assert isinstance(
        listed_version(listing + "  dedicated Stopped 1\n", "dedicated"), Err
    ), "ambiguous WSL listing was accepted"
    assert isinstance(listed_version(listing, " "), Err)
    assert listed_version("  Débian-日本 Running 2\n", "Débian-日本") == Ok(2)
    assert version_result(Output(0, listing, ""), "dedicated") == Ok(2)
    assert isinstance(version_result(Output(1, listing, "failure"), "dedicated"), Err)
    assert isinstance(
        version_result(Output(0, "\x00".join(listing), ""), "dedicated"), Err
    ), "non-UTF-8 WSL output was accepted"


def test_version_listing_decodes_utf16_without_losing_names() -> None:
    """Native UTF-16LE and requested UTF-8 preserve the exact Unicode name."""
    name = "D\u00e9bian-\u65e5\u672c"
    listing = "  NAME STATE VERSION\n  " + name + " Running 2\n"
    for encoding in ("utf-8", "utf-16", "utf-16-le"):
        output = ByteOutput(0, listing.encode(encoding), b"")
        assert version_bytes_result(output, name) == Ok(2), (
            "Unicode WSL listing was rejected"
        )
        assert isinstance(version_bytes_result(output, name + "-other"), Err)
    for output in (
        ByteOutput(0, b"\xff", b""),
        ByteOutput(0, b"\xff\xfe\x00", b""),
        ByteOutput(1, listing.encode("utf-8"), b"failure"),
    ):
        assert isinstance(version_bytes_result(output, name), Err)
