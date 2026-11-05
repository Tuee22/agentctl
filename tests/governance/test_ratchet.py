# Copyright (c) 2026 agentctl contributors.
"""Append-only values and read-only git adapters have independent controls."""

import json
import os
import sys
import zlib
from pathlib import Path

import pytest

from agentctl.check.ratchet import (
    RowFact,
    Setting,
    append_only,
    check,
    config_tightens,
    configuration,
    head,
    rows,
)
from agentctl.process import run
from agentctl.result import Err, Ok
from tests.harness.git import repository

ORACLE = (
    '[[case]]\nid = "example"\nrequirement = "R20"\nquote = "quoted"\n'
    'provenance = "request:R20"\ninput = 1\nexpected = 2\n'
)
CONFIG = (
    '[tool.ruff.lint]\nselect = ["ALL"]\nignore = ["D203"]\n'
    '[tool.ty.rules]\nall = "error"\n[tool.pytest]\nstrict = true\n'
    "[tool.coverage.report]\nfail_under = 100\n"
)


@pytest.mark.evidence("value")
def test_deleted_row_rejected() -> None:
    """Require old ids even when other rows remain unchanged."""
    before = (RowFact("first", "one"), RowFact("second", "two"))
    assert append_only(before, before) == ()
    assert append_only(before, before[1:]) == ("first",), "deleted row was accepted"


@pytest.mark.evidence("value")
def test_edited_row_rejected() -> None:
    """Keep old values immutable while allowing genuinely additional rows."""
    before = (RowFact("first", "one"),)
    assert append_only(before, (*before, RowFact("second", "two"))) == ()
    assert append_only(before, (RowFact("first", "changed"),)) == ("first",), (
        "edited row was accepted"
    )


@pytest.mark.evidence("value")
def test_amends_row_accepted() -> None:
    """An appended amendment preserves its exact original baseline row."""
    first = rows(ORACLE, "oracle")
    amendment = ORACLE + ORACLE.replace(
        'id = "example"', 'id = "amendment"\namends = "example"'
    ).replace("expected = 2", "expected = 3")
    second = rows(amendment, "oracle")
    assert isinstance(first, Ok)
    assert isinstance(second, Ok)
    assert append_only(first.value, second.value) == ()
    assert isinstance(rows(ORACLE + ORACLE, "oracle"), Err)


@pytest.mark.evidence("real")
def test_head_adapter_real(tmp_path: Path) -> None:
    """Read actual loose git objects, distinguishing absent and corrupt HEAD."""
    empty = tmp_path / "empty"
    repository(empty)
    assert head(empty) == Ok(None)
    assert check(empty) == Ok("no baseline")
    root = tmp_path / "subject"
    revision = repository(
        root, (("tests/oracles/example.toml", ORACLE.encode()),), with_head=True
    )
    assert head(root) == Ok(revision)
    assert check(root) == Ok(revision)
    path = root / "tests/oracles/example.toml"
    path.write_text(ORACLE.replace("expected = 2", "expected = 3"), encoding="utf-8")
    assert isinstance(check(root), Err)
    (root / ".git/refs/heads/main").write_text("f" * 40 + "\n", encoding="ascii")
    assert isinstance(head(root), Err)


@pytest.mark.evidence("value")
def test_config_weakening_rejected() -> None:
    """Permit a tighter ignore set, rejecting lower floors or weaker rules."""
    before = configuration(CONFIG)
    assert isinstance(before, Ok)
    assert config_tightens(before.value, before.value)
    tighter = configuration(CONFIG.replace('["D203"]', "[]"))
    assert isinstance(tighter, Ok)
    assert config_tightens(before.value, tighter.value)
    for change in (
        CONFIG.replace('["D203"]', '["D203", "F401"]'),
        CONFIG.replace('all = "error"', 'all = "warn"'),
        CONFIG.replace("fail_under = 100", "fail_under = 99"),
        CONFIG.replace("strict = true", "strict = false"),
    ):
        after = configuration(change)
        assert isinstance(after, Ok)
        assert not config_tightens(before.value, after.value), (
            "configuration weakening was accepted"
        )


@pytest.mark.evidence("value")
def test_ratchet_parser_boundaries() -> None:
    """Malformed protected documents cannot become an empty baseline."""
    for text in (
        "not TOML",
        "",
        "case = []",
        "case = [1]",
        "[[case]]\nid = 1",
        '[[case]]\nid = ""',
        '[[case]]\nid = "date"\nvalue = 2000-01-01',
        '[[case]]\nid = "nan"\nvalue = nan',
    ):
        assert isinstance(rows(text, "oracle"), Err)
    assert isinstance(rows("", "requirements"), Err)
    assert isinstance(rows("## Requirements\n", "requirements"), Err)
    assert isinstance(rows("## Requirements\n| R20 | Frozen |\n", "requirements"), Ok)
    assert isinstance(rows('[[mutant]]\nid = "M-example-one"', "mutant"), Ok)
    for text in (
        "not TOML",
        "tool = 1",
        "[tool.ruff]",
        CONFIG + "[tool.ty.extra]\nvalue = [1]",
        CONFIG + "[tool.ty.extra]\nvalue = 2000-01-01",
    ):
        assert isinstance(configuration(text), Err)
    for path, first, second, accepted in (
        (("ruff", "lint", "select"), ("F",), ("F", "E"), True),
        (("ruff", "lint", "select"), ("F", "E"), ("F",), False),
        (("ruff", "format", "other"), ("first",), ("second",), False),
        (("ty", "rules", "all"), "warn", "error", True),
        (("ty", "rules", "all"), "invalid", "error", False),
        (("pytest", "strict"), False, True, True),
        (("pytest", "strict"), False, "true", False),
        (("unknown",), 1, 2, False),
    ):
        assert (
            config_tightens((Setting(path, first),), (Setting(path, second),))
            is accepted
        )
    assert config_tightens((), (Setting(("ty", "rules", "extra"), "error"),))
    assert not config_tightens((), (Setting(("ty", "rules", "extra"), "warn"),))
    assert not config_tightens((Setting(("pytest", "strict"), value=True),), ())


@pytest.mark.evidence("real")
def test_corrupt_and_missing_baselines(tmp_path: Path) -> None:
    """Real git reads reject damaged trees, blobs and invalid protected values."""
    for index, (filename, baseline, current) in enumerate(
        (
            ("pyproject.toml", CONFIG, CONFIG),
            ("pyproject.toml", CONFIG, CONFIG.replace("100", "99")),
            ("pyproject.toml", "bad = [", CONFIG),
            ("pyproject.toml", CONFIG, "bad = ["),
            ("tests/oracles/row.toml", "bad = [", ORACLE),
            ("tests/oracles/row.toml", ORACLE, "bad = ["),
            (
                "DEVELOPMENT_PLAN/00-overview.md",
                "## Requirements\n| R20 | Frozen |\n",
                "## Requirements\n| R20 | Frozen |\n",
            ),
        )
    ):
        subject = tmp_path / str(index)
        revision = repository(subject, ((filename, baseline.encode()),), with_head=True)
        (subject / filename).write_text(current, encoding="utf-8")
        result = check(subject)
        assert (
            result == Ok(revision) if baseline == current else isinstance(result, Err)
        )
    subject = tmp_path / "missing"
    repository(subject, (("tests/oracles/row.toml", ORACLE.encode()),), with_head=True)
    (subject / "tests/oracles/row.toml").unlink()
    assert isinstance(check(subject), Err)
    for kind in (b"tree ", b"blob "):
        subject = tmp_path / kind.decode().strip()
        repository(
            subject, (("tests/oracles/row.toml", ORACLE.encode()),), with_head=True
        )
        for path in (subject / ".git/objects").rglob("*"):
            if path.is_file() and zlib.decompress(path.read_bytes()).startswith(kind):
                path.write_bytes(b"corrupt git object")
        assert isinstance(check(subject), Err)
    outside = tmp_path / "not-a-repository"
    outside.mkdir()
    assert isinstance(head(outside), Err)


@pytest.mark.evidence("observer")
def test_git_read_vetoes(tmp_path: Path) -> None:
    """A live audit observer denies each read stage without replacing git."""
    script = (
        "import json, sys\nfrom pathlib import Path\n"
        "from agentctl.check.ratchet import check\n"
        "from agentctl.result import Err\n"
        "def observe(event, values):\n"
        "    if event == 'subprocess.Popen' and sys.argv[2] in values[1]:\n"
        "        raise OSError('owned read veto')\n"
        "sys.addaudithook(observe)\n"
        "result = check(Path(sys.argv[1]))\n"
        "assert isinstance(result, Err)\n"
        "print(json.dumps(result.error.message))\n"
    )
    for command in ("rev-parse", "symbolic-ref", "show-ref", "ls-tree", "show"):
        subject = tmp_path / command
        repository(
            subject,
            (("tests/oracles/row.toml", ORACLE.encode()),),
            with_head=command in {"ls-tree", "show"},
        )
        result = run(
            [sys.executable, "-c", script, str(subject), command],
            cwd=subject,
            env=os.environ,
        )
        assert isinstance(result, Ok)
        assert result.value.code == 0, result.value.stderr
        assert json.loads(result.value.stdout) == "owned read veto"
    result = run(
        [
            sys.executable,
            "-c",
            (
                "from pathlib import Path; from agentctl.check.ratchet import head; "
                "print(head(Path.cwd()).error.message)"
            ),
        ],
        cwd=tmp_path,
        env={**os.environ, "PATH": ""},
    )
    assert isinstance(result, Ok)
    assert result.value.stdout.strip() == "git is required for the ratchet"
