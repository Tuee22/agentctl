# Copyright (c) 2026 agentctl contributors.
"""Independent native style-tool digests, arguments and source target controls."""

import hashlib
import tomllib
from dataclasses import replace
from pathlib import Path

import pytest

from agentctl.bootstrap import style
from agentctl.bootstrap.pins import Version
from agentctl.check.style import targets
from agentctl.result import Err, Ok
from tests.harness.bootstrap import pins
from tests.harness.oracle import assert_oracle

pytestmark = pytest.mark.evidence("value")


def test_style_identity_and_install_arguments(root: Path, tmp_path: Path) -> None:
    """Length-prefixed independent inputs determine both native pins and cache paths."""
    selected = pins()
    fields = [
        "ghc",
        "9.12.4",
        "fourmolu",
        "0.19.0.1",
        "hlint",
        "3.10",
        "ghc_lib_parser",
        "9.12.3.20251228",
    ]
    encoded = b"".join(
        len(field.encode("ascii")).to_bytes(8, "big") + field.encode("ascii")
        for field in fields
    )
    expected = hashlib.sha256(encoded).hexdigest()
    assert style.digest(selected) == expected
    assert style.directory(tmp_path, selected) == tmp_path / "tools" / expected
    for name in ("ghc", "fourmolu", "hlint", "ghc_lib_parser"):
        assert style.digest(replace(selected, **{name: Version((99, 1))})) != expected
    assert style.digest(replace(selected, cabal=Version((99, 1)))) == expected
    assert style.paths(tmp_path, "Windows") == style.StyleTools(
        tmp_path / "fourmolu.exe", tmp_path / "hlint.exe"
    )
    assert style.paths(tmp_path, "Linux") == style.StyleTools(
        tmp_path / "fourmolu", tmp_path / "hlint"
    )
    rows = tomllib.loads(
        (root / "tests/oracles/style_tools.toml").read_text(encoding="utf-8")
    )["case"]
    expected_args = next(
        row["expected"]
        for row in rows
        if row["id"] == "style.install.arguments.compatible"
    )
    assert_oracle(
        lambda _: list(
            style.install_arguments(
                selected, "<ghc>", Path("<staged>"), Path("<build>"), "<index>"
            )
        ),
        None,
        expected_args,
        row_id="style installer arguments differ",
    )
    assert isinstance(targets(tmp_path), Err)
    source = tmp_path / "src/Ignored.hs"
    source.parent.mkdir()
    source.touch()
    (tmp_path / ".gitignore").write_text("*.hs\n", encoding="utf-8")
    assert targets(tmp_path) == Ok((str(source),))
