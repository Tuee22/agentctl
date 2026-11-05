# Copyright (c) 2026 agentctl contributors.
"""Read the actual Dockerfile against the independent clean-lane contract."""

import json
import re
import shlex
from dataclasses import asdict, dataclass, replace
from pathlib import Path

import pytest

from tests.harness.oracle import (
    Object,
    Problem,
    Store,
    Value,
    assert_oracle,
    freeze,
    read_homes,
)
from tests.harness.oracle import load as oracle_load

pytestmark = pytest.mark.evidence("value")


@dataclass(frozen=True, slots=True)
class Stage:
    """The contract-bearing facts of one stage, independently parsed from Docker."""

    base: str
    user: str
    packages: tuple[str, ...] = ()
    programs: tuple[str, ...] = ()
    application_users: tuple[str, ...] = ()
    pipx: tuple[str, ...] = ()
    first_use: tuple[str, ...] = ()
    first_exit: int = 0
    diagnostics: tuple[str, ...] = ()
    installers: tuple[str, ...] = ()
    preparation: bool = False
    passwordless: bool = False
    command: tuple[str, ...] = ()


def _run(stage: Stage, text: str) -> Stage:
    """Extract package sets and every application command's current Docker user."""
    args = shlex.split(text)
    program = args[0]
    stage = replace(stage, programs=(*stage.programs, program))
    if program == "apt-get":
        start = args.index("install") + 1
        end = args.index("&&", start)
        return replace(
            stage,
            packages=(
                *stage.packages,
                *(arg for arg in args[start:end] if not arg.startswith("-")),
            ),
        )
    if program == "useradd":
        return replace(
            stage, passwordless="NOPASSWD: ALL" in text and "/etc/sudoers.d/" in text
        )
    if program == "python3":
        return replace(
            stage,
            preparation="from tests.harness.bootstrap_origin import capture" in text
            and "Path.home()" in text,
        )
    stage = replace(stage, application_users=(*stage.application_users, stage.user))
    if program == "pipx":
        return replace(stage, pipx=tuple(args))
    if program == "curl":
        return replace(stage, installers=(*stage.installers, args[2]))
    assert program == "agentctl", "clean-host recipe differs: unexpected stage program"
    code = re.search(r'test "\$status" -eq (\d+)', text)
    assert code is not None
    return replace(
        stage,
        first_use=tuple(args[: args.index(">")]),
        first_exit=int(code[1]),
        diagnostics=tuple(
            name for name in ("tmux", "install") if f'"{name}" in text' in text
        ),
    )


def _projection(path: Path) -> Value:
    """Keep package, command, provenance and privilege facts, not product reports."""
    stages: dict[str, Stage] = {}
    current = ""
    for line in path.read_text(encoding="utf-8").replace("\\\n", " ").splitlines():
        instruction, _space, text = line.strip().partition(" ")
        if instruction == "FROM":
            base, alias, current = shlex.split(text)
            assert alias == "AS"
            stages[current] = Stage(
                base, stages[base].user if base in stages else "root"
            )
        elif instruction == "USER":
            stages[current] = replace(stages[current], user=text)
        elif instruction == "RUN":
            stages[current] = _run(stages[current], text)
        elif instruction == "CMD":
            stage = stages[current]
            stages[current] = replace(
                stage,
                command=tuple(json.loads(text)),
                application_users=(*stage.application_users, stage.user),
            )
    normalized: object = json.loads(
        json.dumps({name: asdict(stage) for name, stage in stages.items()})
    )
    result = freeze(normalized)
    assert not isinstance(result, Problem)
    return result


def test_recipe_stages_match_oracle(root: Path) -> None:
    """Stage A remains bare, both applications run as the user and Stage B gates."""
    store = oracle_load(root / "tests/oracles/bootstrap_plan.toml", read_homes(root))
    assert isinstance(store, Store)
    compared = 0
    for row in store.effective:
        assert isinstance(row.inputs, Object)
        if dict(row.inputs.items)["subject"] == "clean-host-recipe":
            assert_oracle(
                _projection,
                root / "tests/lanes/clean-host.Dockerfile",
                row.expected,
                row_id="clean-host recipe differs: " + row.identifier,
            )
            compared += 1
    assert compared > 0
