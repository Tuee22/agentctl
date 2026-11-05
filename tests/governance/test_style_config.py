# Copyright (c) 2026 agentctl contributors.
"""Complete project style configuration with no local suppression surface."""

import shutil
import tomllib
from pathlib import Path

import pytest

from agentctl.check import style
from agentctl.result import Err, Ok
from tests.harness.oracle import assert_oracle

pytestmark = pytest.mark.evidence("value")


def test_style_configs_have_no_ignores(root: Path, tmp_path: Path) -> None:
    """The real configuration passes beside ignores, missing keys and overrides."""
    project = root / "src/agentctl/haskell"
    assert style.configuration(project) == Ok(None)
    rows = tomllib.loads(
        (root / "tests/oracles/style_tools.toml").read_text(encoding="utf-8")
    )["case"]
    expected = next(row["expected"] for row in rows if row["id"] == "style.config.keys")
    assert_oracle(
        lambda _: list(
            style.keys((project / "fourmolu.yaml").read_text(encoding="utf-8"))
        ),
        None,
        expected,
        row_id="style configuration keys differ",
    )
    for name in ("fourmolu.yaml", ".hlint.yaml"):
        shutil.copyfile(project / name, tmp_path / name)
    assert style.configuration(tmp_path) == Ok(None)
    hlint = tmp_path / ".hlint.yaml"
    for text in (
        "- ignore: {name: Use fewer brackets}\n",
        '- "ignore": {}\n',
        "defaults: &hints []\nignore: *hints\n",
    ):
        hlint.write_text(text, encoding="utf-8")
        assert isinstance(style.configuration(tmp_path), Err), (
            "HLint ignore configuration was accepted"
        )
    hlint.write_text("[]\n", encoding="utf-8")
    fourmolu = tmp_path / "fourmolu.yaml"
    original = fourmolu.read_text(encoding="utf-8")
    for invalid in (
        original.replace("indentation: 2\n", ""),
        original + "indentation: 2\n",
        original + "unmodelled: true\n",
        original + "unmodelled_key: true\n",
        original + '"indentation": 1\n',
    ):
        fourmolu.write_text(invalid, encoding="utf-8")
        assert isinstance(style.configuration(tmp_path), Err)
    fourmolu.write_text(original, encoding="utf-8")
    nested = tmp_path / "src"
    nested.mkdir()
    shutil.copyfile(hlint, nested / ".hlint.yaml")
    assert isinstance(style.configuration(tmp_path), Err)
    (nested / ".hlint.yaml").unlink()
    hlint.write_bytes(b"\xff")
    assert isinstance(style.configuration(tmp_path), Err)
    hlint.unlink()
    hlint.mkdir()
    assert isinstance(style.configuration(tmp_path), Err)
    hlint.rmdir()
    assert isinstance(style.configuration(tmp_path), Err)
