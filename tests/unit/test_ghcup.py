# Copyright (c) 2026 agentctl contributors.
"""Package pin equality and malformed-data boundary controls."""

import tomllib
from pathlib import Path

import pytest

from agentctl.bootstrap.pins import load, parse, version
from agentctl.result import Err, Ok
from tests.harness.oracle import Object, Store, assert_oracle, freeze, read_homes
from tests.harness.oracle import load as oracle_load

pytestmark = pytest.mark.evidence("value")


def test_pins_match_oracle(root: Path) -> None:
    """Compare every shipped version, URL and digest with independent literals."""
    pins = load()
    assert isinstance(pins, Ok)
    store = oracle_load(root / "tests/oracles/pins.toml", read_homes(root))
    assert isinstance(store, Store)
    assert len(pins.value.assets) == sum(
        row.identifier.startswith("pins.ghcup.")
        and isinstance(row.inputs, Object)
        and dict(row.inputs.items).get("subject") == "ghcup-artifact"
        for row in store.effective
    )
    for row in store.effective:
        assert isinstance(row.inputs, Object)
        inputs = dict(row.inputs.items)
        match inputs["subject"]:
            case "toolchain-pins":
                observed = freeze(
                    {"ghc": pins.value.ghc.text, "cabal": pins.value.cabal.text}
                )
            case "ghcup-download-version":
                observed = pins.value.ghcup.text
            case "ghcup-reuse-floor":
                observed = pins.value.ghcup_floor.text
            case "style-pins":
                observed = freeze(
                    {
                        "fourmolu": pins.value.fourmolu.text,
                        "hlint": pins.value.hlint.text,
                        "ghc_lib_parser": pins.value.ghc_lib_parser.text,
                    }
                )
            case "binary-digest":
                # The independent filesystem consumer lives in test_digest.py.
                assert isinstance(row.expected, bool)
                continue
            case "ghcup-artifact":
                assets = tuple(
                    asset
                    for asset in pins.value.assets
                    if (asset.family, asset.architecture)
                    == (inputs["family"], inputs["architecture"])
                )
                assert len(assets) == 1
                observed = freeze({"url": assets[0].url, "sha256": assets[0].sha256})
            case _:
                pytest.fail("unknown independent pin subject")
        assert_oracle(
            lambda value: value,
            observed,
            row.expected,
            row_id="package pins differ: " + row.identifier,
        )


def test_pin_parser_rejects_malformed_data(root: Path, tmp_path: Path) -> None:
    """Reject structural, version, asset and duplicate errors beside valid data."""
    data = tomllib.loads(
        (root / "src/agentctl/bootstrap/pins.toml").read_text(encoding="utf-8")
    )
    assert isinstance(parse(data), Ok)
    for value in (None, {}, {**data, "extra": True}):
        assert isinstance(parse(value), Err)
    for versions in (None, {}, {**data["versions"], "extra": "1.2"}):
        assert isinstance(parse({**data, "versions": versions}), Err)
    for name in data["versions"]:
        assert isinstance(
            parse({**data, "versions": {**data["versions"], name: "invalid"}}), Err
        )
    for assets in (
        None,
        [],
        [None],
        [{**data["asset"][0], "extra": True}],
        [data["asset"][0], data["asset"][0]],
    ):
        assert isinstance(parse({**data, "asset": assets}), Err)
    for field, invalid in (
        ("family", []),
        ("family", "Other"),
        ("architecture", []),
        ("architecture", "s390x"),
        ("url", 1),
        ("url", "http://untrusted.invalid/ghcup"),
        ("sha256", 1),
        ("sha256", "broken"),
    ):
        assert isinstance(
            parse({**data, "asset": [{**data["asset"][0], field: invalid}]}), Err
        )
    assert isinstance(load(tmp_path / "missing"), Err)
    invalid = tmp_path / "invalid.toml"
    invalid.write_text("[broken", encoding="utf-8")
    assert isinstance(load(invalid), Err)
    invalid.write_bytes(b"\xff")
    assert isinstance(load(invalid), Err)
    assert version(None) is None
    for text in ("", "1", "1.2.3.4.5", "1.2\n", "\uff11.2", "1.a"):
        assert version(text) is None
    parsed = version("0.1.50.2")
    assert parsed is not None
    assert parsed.text == "0.1.50.2"
