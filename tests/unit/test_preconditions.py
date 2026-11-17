# Copyright (c) 2026 agentctl contributors.
"""Independent disk, network and bindist readiness decisions."""

from importlib import import_module
from pathlib import Path

import pytest

from agentctl.check.preconditions import (
    ToolchainReadiness,
    private_socket_path,
    socket_path_length,
    toolchain_preconditions,
)
from agentctl.result import Ok
from tests.harness.oracle import Object, Store, Value, assert_oracle, read_homes
from tests.harness.oracle import load as oracle_load

pytestmark = pytest.mark.evidence("value")


def test_socket_path_length(tmp_path: Path) -> None:
    """P6 counts encoded bytes, accepts its bound and excludes Windows sockets."""
    assert socket_path_length(Path("/" + "a" * 99)) == ()
    assert socket_path_length(Path("/" + "a" * 100)), "socket length was not checked"
    assert socket_path_length(Path("/" + "é" * 50)), "socket length was not checked"
    expected = tmp_path / "mux/00000000" / "tmux-1234/default"
    assert private_socket_path(tmp_path, 1234) == expected


def _integer(value: Value) -> int:
    """Require integer capacity data independently of the subject."""
    assert isinstance(value, int)
    assert not isinstance(value, bool)
    return value


def _boolean(value: Value) -> bool:
    """Require explicit readiness observations rather than truthy strings."""
    assert isinstance(value, bool)
    return value


def test_toolchain_preconditions(root: Path) -> None:
    """Compare all readiness outcomes and remedies with independent oracle rows."""
    pins = import_module("agentctl.bootstrap.pins").load()
    assert isinstance(pins, Ok)
    store = oracle_load(
        root / "tests/oracles/toolchain_preconditions.toml", read_homes(root)
    )
    assert isinstance(store, Store)
    assert store.effective
    for row in store.effective:
        assert isinstance(row.inputs, Object)
        fields = dict(row.inputs.items)
        family, machine = fields["family"], fields["architecture"]
        assert isinstance(family, str)
        assert family in {"Linux", "Darwin", "Windows"}
        assert isinstance(machine, str)
        assert machine in {
            "x86_64",
            "aarch64",
            "arm64",
            "unsupported",
        }
        readiness = ToolchainReadiness(
            family,
            machine,
            _integer(fields["ghcup_free"]),
            _integer(fields["cache_free"]),
            _integer(fields["ghcup_required"]),
            _integer(fields["cache_required"]),
            _boolean(fields["pins_ready"]),
            _boolean(fields["downloads_reachable"]),
            _boolean(fields["hackage_reachable"]),
        )
        assert_oracle(
            lambda facts: toolchain_preconditions(facts, pins.value),
            readiness,
            row.expected,
            row_id="toolchain preconditions differ: " + row.identifier,
        )


def test_prerequisite_precondition(root: Path) -> None:
    """P9 needs ready probes or explicit non-interactive install capability."""
    prerequisites = import_module("agentctl.check.prerequisites")
    store = oracle_load(root / "tests/oracles/prerequisites.toml", read_homes(root))
    assert isinstance(store, Store)
    compared = 0
    for row in store.effective:
        assert isinstance(row.inputs, Object)
        fields = dict(row.inputs.items)
        if fields["subject"] == "prerequisite-precondition":
            family = fields.get("family", "Linux")
            assert isinstance(family, str)
            assert family in {"Linux", "Darwin", "Windows"}
            readiness = prerequisites.PrerequisiteReadiness(
                ready=_boolean(fields["ready"]),
                assume_yes=_boolean(fields["assume_yes"]),
                is_root=_boolean(fields["is_root"]),
                passwordless=_boolean(fields["passwordless"]),
                family=family,
                verified_packages=_boolean(fields.get("verified_packages", True)),
            )
            assert_oracle(
                lambda facts: not prerequisites.prerequisite_precondition(facts),
                readiness,
                row.expected,
                row_id="prerequisite consent was bypassed: " + row.identifier,
            )
            compared += 1
    assert compared > 0
