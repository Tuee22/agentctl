# Copyright (c) 2026 agentctl contributors.
"""Executable command tables join the CLI reference and declared capability owners."""

import json
import re
import tomllib
from collections.abc import Mapping
from pathlib import Path

import pytest

from agentctl.bootstrap import build
from agentctl.cli import cli
from agentctl.result import Ok

pytestmark = pytest.mark.evidence("real")
CELL_COUNT = 4
HEADER_LINES = 2
OWNER = r"phase-[0-9]+-[a-z-]+\.md"


def _rows(text: str) -> tuple[tuple[str, str], ...] | None:
    """Parse the one command table while retaining malformed-row failures."""
    section = text.partition("## Commands\n")[2].split("\n## ", maxsplit=1)[0]
    table = section.lstrip().split("\n\n", maxsplit=1)[0]
    lines = table.splitlines()
    if not lines or lines[0] != "| Command | Arguments | What it does | Owning phase |":
        return None
    if len(lines) < HEADER_LINES or lines[1] != "|---|---|---|---|":
        return None
    records = []
    for line in lines[2:]:
        cells = tuple(cell.strip() for cell in line.strip("|").split("|"))
        if len(cells) != CELL_COUNT:
            return None
        command = re.fullmatch(r"`agentctl ([a-z][a-z-]*)(?: [^`]*)?`", cells[0])
        owner = re.search(r"\((?:\.\./)*DEVELOPMENT_PLAN/(" + OWNER + r")\)", cells[-1])
        if command is None or owner is None:
            return None
        records.append((str(command.group(1)), str(owner.group(1))))
    return tuple(records)


def _joined(
    text: str,
    commands: frozenset[str],
    native: frozenset[str],
    declared: frozenset[str],
    owners: Mapping[str, str],
) -> bool:
    """Require both code-to-document joins and introduced document-to-code joins."""
    rows = _rows(text)
    if rows is None or not rows:
        return False
    names = frozenset(name for name, _ in rows)
    if len(names) != len(rows) or not names <= declared:
        return False
    if commands - {"check"} != native or not commands | native <= names:
        return False
    for name, owner in rows:
        status = owners.get(owner)
        if status not in {"Planned", "Active", "Done"}:
            return False
        if status != "Planned" and name not in commands:
            return False
    return True


def test_cli_reference_joins_click_and_handshake(
    root: Path, haskell_build: build.BuildContext
) -> None:
    """Check the real reference beside missing, duplicate and unknown-owner twins."""
    text = (root / "documents/reference/cli_reference.md").read_text(encoding="utf-8")
    owners = {}
    for path in (root / "DEVELOPMENT_PLAN").glob("phase-*.md"):
        found = re.search(
            r"(?m)^\*\*Status\*\*: (\w+)$", path.read_text(encoding="utf-8")
        )
        assert found is not None
        owners[path.name] = str(found.group(1))
    output = build.execute_binary(
        haskell_build, build.BinaryCall("exe:agentctl-core", ("--handshake",))
    )
    assert isinstance(output, Ok), output
    assert output.value.code == 0, output.value.stderr
    native = frozenset(json.loads(output.value.stdout)["commands"])
    oracle = tomllib.loads(
        (root / "tests/oracles/command_surface.toml").read_text(encoding="utf-8")
    )["case"]
    declared = frozenset(
        next(
            row["expected"]["commands"]
            for row in oracle
            if row["id"] == "surface.complete"
        )
    )
    assert _joined(text, frozenset(cli.commands), native, declared, owners), (
        "CLI reference does not join the live command surface"
    )
    header = (
        "## Commands\n\n| Command | Arguments | What it does | Owning phase |\n"
        "|---|---|---|---|\n"
    )
    check = (
        "| `agentctl check` | none | Check | "
        "[Core](../../DEVELOPMENT_PLAN/phase-0-core.md) |\n"
    )
    claude = (
        "| `agentctl claude [ARGS...]` | ARGS | Launch | "
        "[Launch](../../DEVELOPMENT_PLAN/phase-6-launch.md) |\n"
    )
    surface = frozenset({"check", "claude"})
    statuses = {"phase-0-core.md": "Done", "phase-6-launch.md": "Active"}
    assert _joined(
        header + check + claude, surface, frozenset({"claude"}), surface, statuses
    )
    for negative in (
        header + check,
        header + check + claude + claude,
        (header + check + claude).replace("phase-6-launch.md", "phase-9-unknown.md"),
        (header + check + claude).replace(
            "`agentctl claude [ARGS...]`", "`agentctl invented`"
        ),
        (header + check + claude).replace("| Command |", "| Wrong |"),
    ):
        assert not _joined(
            negative, surface, frozenset({"claude"}), surface, statuses
        ), "invalid CLI reference table was accepted"
