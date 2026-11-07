# Copyright (c) 2026 agentctl contributors.
"""Independent leg rows, environment scrubbing and complete verdicts."""

import tomllib
from pathlib import Path

import pytest

from agentctl.bootstrap import build
from agentctl.bootstrap.style import StyleTools
from agentctl.bootstrap.toolchain import Toolchain
from agentctl.check.legs import cabal_legs, python_legs, style_legs, targets, verdict
from agentctl.check.steps import environment, inapplicable_message, pipeline
from agentctl.result import Err, Ok
from tests.harness.bootstrap import context

pytestmark = pytest.mark.evidence("value")


def test_planned_owner_diagnostic() -> None:
    """A Planned capability has an explicit ceiling while a complete target has none."""
    assert inapplicable_message(("Haskell source",)) == (
        "validators: not applicable: Haskell source (owner Planned)\n"
    )
    assert inapplicable_message(()) == ""


def _strings(value: object) -> dict[str, str]:
    """Parse an oracle object's string fields at the TOML boundary."""
    assert isinstance(value, dict)
    assert all(
        isinstance(key, str) and isinstance(item, str) for key, item in value.items()
    )
    return {str(key): str(item) for key, item in value.items()}


def test_leg_table_matches_oracle(root: Path, tmp_path: Path) -> None:
    """Require every argv token and controlled environment setting."""
    oracle = tomllib.loads(
        (root / "tests/oracles/check_legs.toml").read_text(encoding="utf-8")
    )
    legs = python_legs("<py>", Path("<root>"), ("<files>",), Path("<run>"))
    amended = {row.get("amends") for row in oracle["case"]}
    expected = [
        row["expected"]
        for row in oracle["case"]
        if row["input"].get("scope") in {"python", "python-covered"}
        and row["id"] not in amended
    ]
    assert [
        {
            "name": leg.name,
            "arguments": list(leg.argv),
            **({"report_arguments": list(leg.after[-1])} if leg.after else {}),
        }
        for leg in legs
    ] == expected, "leg table differs from oracle"
    native = cabal_legs("<cabal>", "<ghc>", Path("<build>"))
    assert [{"name": leg.name, "arguments": list(leg.argv)} for leg in native] == [
        row["expected"]
        for row in oracle["case"]
        if isinstance(row["expected"], dict)
        and row["expected"].get("name") in {"cabal-build", "cabal-test"}
    ], "Cabal leg table differs from oracle"
    value = build.BuildContext(
        Path("<project>"),
        Path("<build>"),
        context(tmp_path / "native"),
        Toolchain("<ghc>", "<cabal>"),
    )
    assert ("<cabal>", *build.arguments(value, "build", "all")) == native[0].argv, (
        "Cabal build flags differ from oracle"
    )
    assert (
        "<cabal>",
        *build.arguments(value, "test", "all"),
        "--test-show-details=direct",
    ) == native[1].argv
    inherited = {
        "PATH": "/bin",
        "HOME": "/home/example",
        "PYTEST_ADDOPTS": "-k none",
        "PYTEST_PLUGINS": "bad",
        "TY_CONFIG_FILE": "bad",
        "TMUX": "foreign",
        "PYTHONPATH": "foreign",
        "VIRTUAL_ENV": "foreign",
    }
    env = environment(inherited, tmp_path, "fresh", tool="ty")
    assert env["PATH"] == "/bin"
    assert env["AGENTCTL_CHECK_NONCE"] == "fresh"
    assert env["XDG_CONFIG_HOME"] == (tmp_path / "ty-config").as_posix()
    assert env["APPDATA"] == (tmp_path / "ty-config").as_posix()
    assert not set(inherited).difference({"PATH", "HOME"}).intersection(env)
    user = {"XDG_CONFIG_HOME": "/user/config", "APPDATA": "/user/appdata"}
    regular = environment(user, tmp_path, "fresh", tool="pytest")
    assert regular["XDG_CONFIG_HOME"] == "/user/config"
    assert regular["APPDATA"] == "/user/appdata"
    for row in oracle["case"]:
        if (
            row["input"].get("subject") == "check-environment"
            and row["id"] not in amended
        ):
            tool: object = row["input"]["tool"]
            assert isinstance(tool, str)
            inputs = _strings(row["input"]["inherited"])
            expected_env = {
                key: value.replace("<run>", tmp_path.as_posix()).replace(
                    "<nonce>", "fresh"
                )
                for key, value in _strings(row["expected"]).items()
            }
            assert environment(inputs, tmp_path, "fresh", tool=tool) == expected_env


def test_failing_leg_fails_check() -> None:
    """Reject failures, missing legs, duplicates and a reordered execution."""
    names = ("ruff-check", "ruff-format", "ty", "pytest")
    successful = tuple((name, 0) for name in names)
    assert verdict(names, successful)
    for index in range(len(names)):
        assert not verdict(
            names,
            tuple(
                (name, int(position == index)) for position, name in enumerate(names)
            ),
        ), "a failed leg was accepted"
        assert not verdict(names, successful[:index] + successful[index + 1 :])
    assert not verdict(names, tuple(reversed(successful)))
    assert not verdict(names, (*successful, successful[0]))


def test_full_leg_set_matches_oracle(root: Path) -> None:
    """Both the actual pipeline and each executable leg retain all eight oracle rows."""
    rows = tomllib.loads(
        (root / "tests/oracles/check_legs.toml").read_text(encoding="utf-8")
    )["case"]
    python = python_legs("<py>", Path("<root>"), ("<files>",), Path("<run>"))
    native = style_legs(
        StyleTools(Path("<tools>/fourmolu"), Path("<tools>/hlint")), ("<hs-files>",)
    )
    legs = (
        *python[:-1],
        *native,
        *cabal_legs("<cabal>", "<ghc>", Path("<build>")),
        python[-1],
    )
    expected_order = next(
        row["expected"] for row in rows if row["id"] == "legs.complete-order"
    )
    assert [leg.name for leg in legs] == expected_order, (
        "full leg set differs from oracle"
    )
    actual = pipeline(
        Path("<root>"), Path("<run>"), ("<files>",), "Linux", assume_yes=False
    )
    assert [
        step.name
        for step in actual
        if step.name not in {"toolchain-ensure", "binary-identity"}
    ] == expected_order, "full leg set differs from oracle"
    expected = {
        row["expected"]["name"]: row["expected"]["arguments"]
        for row in rows
        if row["id"]
        in {
            "legs.haskell.fourmolu",
            "legs.haskell.hlint",
            "legs.haskell.cabal-build",
            "legs.haskell.cabal-test",
        }
    }
    for leg in (*native, *legs[-3:-1]):
        assert list(leg.argv) == expected[leg.name], (
            "native leg arguments differ from oracle"
        )


def test_empty_target_set_fails(tmp_path: Path) -> None:
    """Reject an empty walk and include ignored files in a nonempty walk."""
    assert isinstance(targets(tmp_path), Err), "empty target set was accepted"
    (tmp_path / "src").mkdir()
    path = tmp_path / "src/example.py"
    path.write_text("", encoding="utf-8")
    assert targets(tmp_path) == Ok((str(path),))
