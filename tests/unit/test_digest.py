# Copyright (c) 2026 agentctl contributors.
"""Independent source/pin/platform byte streams and strict inventory controls."""

import hashlib
import stat
import tomllib
from pathlib import Path

import pytest

from agentctl.bootstrap import binary, cache
from agentctl.result import Err, Ok
from tests.harness.bootstrap import pins
from tests.harness.oracle import assert_oracle

pytestmark = pytest.mark.evidence("value")


def _tree(directory: Path) -> cache.Source:
    """Create a tiny independent source tree with code and non-code inputs."""
    project = directory / "project"
    for name in ("app", "src", "test"):
        (project / name).mkdir(parents=True)
    for name, body in {
        "agentctl-core.cabal": "name: independent\n",
        "cabal.project": "packages: .\n",
        "app/Core.hs": "main = pure ()\n",
        "src/Kernel.hs": "answer = 7\n",
        "test/Main.hs": "main = pure ()\n",
        "app/data.txt": "ordinary data\n",
        "fourmolu.yaml": "indentation: 2\n",
        ".hlint.yaml": "[]\n",
    }.items():
        (project / name).write_text(body, encoding="utf-8")
    pin_file = directory / "pins.toml"
    pin_file.write_text("pins = 'independent'\n", encoding="utf-8")
    return cache.Source(project, pin_file, "x86_64-linux")


def _expected(source: cache.Source) -> str:
    """Compute the specification directly with hashlib, without the subject helper."""
    selected = [
        source.project / "agentctl-core.cabal",
        source.project / "cabal.project",
    ]
    for name in ("app", "src", "test"):
        selected.extend(
            path for path in (source.project / name).rglob("*") if path.is_file()
        )
    fields: list[bytes] = []
    for path in sorted(
        selected, key=lambda path: path.relative_to(source.project).as_posix()
    ):
        fields.extend(
            (
                path.relative_to(source.project).as_posix().encode("utf-8"),
                path.read_bytes(),
            )
        )
    fields.extend((source.pins.read_bytes(), source.triple.encode("ascii")))
    body = b"".join(len(field).to_bytes(8, "big") + field for field in fields)
    return hashlib.sha256(body).hexdigest()


def test_oracle_rows(root: Path, tmp_path: Path) -> None:
    """Each declared edit changes exactly the inputs the independent digest covers."""
    rows = tomllib.loads(
        (root / "tests/oracles/pins.toml").read_text(encoding="utf-8")
    )["case"]
    selected = [row for row in rows if row["input"]["subject"] == "binary-digest"]
    assert selected
    for row in selected:
        source = _tree(tmp_path / row["id"])
        before = cache.digest(source)
        assert before == Ok(_expected(source)), "binary digest differs from rule"
        edit = row["input"]["edit"]
        if edit == "platform":
            source = cache.Source(source.project, source.pins, "aarch64-linux")
        else:
            path = source.pins if edit == "pins" else source.project / edit
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as stream:
                stream.write("changed\n")
        after = cache.digest(source)
        assert after == Ok(_expected(source)), "binary digest differs from rule"
        assert_oracle(
            lambda values: values[0] != values[1],
            (after, before),
            row["expected"],
            row_id="digest edit differs: " + row["id"],
        )
    layout = cache.layout(
        _tree(tmp_path / "layout"), tmp_path / "cache", tmp_path / "data", "Windows"
    )
    assert isinstance(layout, Ok)
    assert layout.value.binary.name == "agentctl-core.exe"


def test_inventory_and_protocol_boundaries(tmp_path: Path) -> None:
    """Incomplete sources, unmodelled kinds and malformed handshakes are refused."""
    source = _tree(tmp_path)
    entries = cache.inventory(source.project)
    assert isinstance(cache.digest(source), Ok)
    for kind in ("symlink", "other"):
        assert isinstance(
            cache.hash_entries(
                (*entries, cache.Entry("src/link", kind, b"")), b"pins", "x86_64-linux"
            ),
            Err,
        )
    assert isinstance(cache.hash_entries((), b"pins", "x86_64-linux"), Err)
    assert isinstance(cache.hash_entries(entries, b"pins", "λ"), Err)
    for mode, expected in (
        (stat.S_IFREG, "file"),
        (stat.S_IFDIR, "directory"),
        (stat.S_IFLNK, "symlink"),
        (stat.S_IFIFO, "other"),
    ):
        assert cache.kind(mode) == expected
    (source.project / "agentctl-core.cabal").unlink()
    assert isinstance(cache.digest(source), Err)
    assert isinstance(cache.layout(source, tmp_path, tmp_path, "Linux"), Err)
    for family, machine, expected in (
        ("Linux", "amd64", "x86_64-linux"),
        ("Linux", "aarch64", "aarch64-linux"),
        ("Darwin", "x86_64", "x86_64-apple-darwin"),
        ("Darwin", "arm64", "aarch64-apple-darwin"),
        ("Windows", "AMD64", "x86_64-mingw64"),
    ):
        assert cache.platform(pins(), family, machine) == Ok(expected)
    assert isinstance(cache.platform(pins(), "Other", "x86_64"), Err)
    assert isinstance(cache.platform(pins(), "Linux", "s390x"), Err)
    assert binary.handshake({"protocol": 1, "commands": ["claude"]})
    for value in (
        None,
        {},
        {"protocol": True, "commands": ["claude"]},
        {"protocol": 2, "commands": ["claude"]},
        {"protocol": 1, "commands": []},
        {"protocol": 1, "commands": ["claude", "claude"]},
        {"protocol": 1, "commands": [1]},
        {"protocol": 1, "commands": [{}]},
        {"protocol": 1, "commands": [""]},
        {"protocol": 1, "commands": "claude"},
    ):
        assert not binary.handshake(value)
