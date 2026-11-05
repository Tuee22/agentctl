# Copyright (c) 2026 agentctl contributors.
"""Class expectations come from fixture directories and independently paired twins."""

import difflib
import json
from pathlib import Path

import pytest

from agentctl.bootstrap import build
from agentctl.result import Ok
from tests.harness.screens import Fixture, ScreenClass, read

pytestmark = pytest.mark.evidence("value")
FIXTURE_REASON = "screen class differs from fixture directory"
PAIR_REASON = "screen precedence differs from fixture pair"


def classes(
    context: build.BuildContext, fixtures: tuple[Fixture, ...]
) -> tuple[str, ...]:
    """Send inputs only and decode the actual native result for every screen."""
    request = "\n".join(
        json.dumps(
            {
                "subject": "classify-" + fixture.agent,
                "text": fixture.text,
                "dead": fixture.kind is ScreenClass.EXITED,
            }
        )
        for fixture in fixtures
    )
    output = build.execute_binary(
        context,
        build.BinaryCall("exe:agentctl-core-eval", input_text=request + "\n"),
    )
    assert isinstance(output, Ok), output
    assert output.value.code == 0, output.value
    result: tuple[str, ...] = ()
    for line in output.value.stdout.splitlines():
        value: object = json.loads(line)
        assert isinstance(value, str), value
        result += (value,)
    assert len(result) == len(fixtures)
    return result


def test_fixtures_classify_as_their_directory(
    root: Path, haskell_build: build.BuildContext
) -> None:
    """Classify every fixture, including later-output and missing-prompt controls."""
    loaded = read(root / "tests/fixtures/screens")
    assert isinstance(loaded, Ok), loaded
    expected = tuple(fixture.kind.value for fixture in loaded.value)
    actual = classes(haskell_build, loaded.value)
    assert actual == expected, FIXTURE_REASON


def test_precedence_pairs(root: Path, haskell_build: build.BuildContext) -> None:
    """A single added dialog, typed input or work indicator outranks old overload."""
    loaded = read(root / "tests/fixtures/screens")
    assert isinstance(loaded, Ok), loaded
    by_path = {fixture.path.resolve(): fixture for fixture in loaded.value}
    pairs = tuple(fixture for fixture in loaded.value if fixture.baseline is not None)
    for agent in ("claude", "codex"):
        covered = {fixture.kind for fixture in pairs if fixture.agent == agent}
        assert {
            ScreenClass.APPROVAL,
            ScreenClass.PARTIAL,
            ScreenClass.WORKING,
        } <= covered
    baselines: tuple[Fixture, ...] = ()
    for fixture in pairs:
        assert fixture.baseline is not None
        baseline = by_path[fixture.baseline]
        assert baseline.agent == fixture.agent
        assert baseline.kind is ScreenClass.OVERLOADED
        assert baseline.evidence in fixture.text
        removed = tuple(
            line[2:].strip()
            for line in difflib.ndiff(
                baseline.text.splitlines(), fixture.text.splitlines()
            )
            if line.startswith("- ")
        )
        assert set(removed) <= {"", "\u276f" if fixture.agent == "claude" else "\u203a"}
        baselines += (baseline,)
    assert classes(haskell_build, baselines) == tuple(
        ScreenClass.OVERLOADED.value for _ in baselines
    ), PAIR_REASON
    assert classes(haskell_build, pairs) == tuple(
        fixture.kind.value for fixture in pairs
    ), PAIR_REASON
