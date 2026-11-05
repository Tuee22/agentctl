# Copyright (c) 2026 agentctl contributors.
"""Actual consent parsing and vetoed installer attempts with fresh identities."""

import json
import os
import sys
from pathlib import Path

import pytest

from agentctl.check.audit import Record, read
from agentctl.process import run
from agentctl.result import Ok
from tests.harness.nonce import fresh
from tests.harness.oracle import Object, Store, Value, freeze, read_homes
from tests.harness.oracle import load as oracle_load

pytestmark = pytest.mark.evidence("observer")


def _actor(
    root: Path, directory: Path, mode: str
) -> tuple[tuple[Record, ...], str, tuple[str, ...]]:
    """Reap a disposable actor whose private PATH contains no installer binaries."""
    directory.mkdir()
    nonce = fresh(os.environ.get("AGENTCTL_CHECK_NONCE", "focused"))
    manifest = os.environ.get("AGENTCTL_CHECK_MANIFEST")
    observers = (
        Path(manifest).parent / "observers"
        if manifest is not None and manifest != ""
        else directory
    )
    log = observers / (nonce + ".jsonl")
    result = run(
        [
            sys.executable,
            str(root / "tests/fixtures/bootstrap/prereq_actor.py.txt"),
            mode,
            str(directory),
            str(log),
            nonce,
        ],
        cwd=root,
        env=os.environ,
    )
    assert isinstance(result, Ok)
    assert result.value.code == 0, result.value.stderr
    payload: object = json.loads(result.value.stdout)
    assert isinstance(payload, dict)
    console, reasons = payload["console"], payload["reasons"]
    assert isinstance(console, str)
    assert isinstance(reasons, list)
    assert all(isinstance(reason, str) for reason in reasons)
    records = read(log, nonce)
    assert isinstance(records, Ok)
    assert all(record.nonce == nonce for record in records.value)
    compiler = tuple(record for record in records.value if "-lgmp" in record.argv)
    assert len(compiler) == 1
    assert not compiler[0].vetoed
    return records.value, console, tuple(str(reason) for reason in reasons)


def _expected(root: Path, identifier: str) -> Value:
    """Read the fixed command expectation independently of the renderer."""
    store = oracle_load(root / "tests/oracles/prerequisites.toml", read_homes(root))
    assert isinstance(store, Store)
    row = next(row for row in store.effective if row.identifier == identifier)
    assert isinstance(row.expected, Object)
    return dict(row.expected.items)["commands"]


def _installers(records: tuple[Record, ...]) -> tuple[Record, ...]:
    """Keep attempted installer events beside their unvetoed compiler control."""
    return tuple(record for record in records if "-lgmp" not in record.argv)


def test_declined_spawns_nothing(root: Path, tmp_path: Path) -> None:
    """A negative, empty or unrecognised answer declines after exactly one prompt."""
    for mode in ("declined", "declined-other", "declined-empty"):
        records, console, reasons = _actor(root, tmp_path / mode, mode)
        assert _installers(records) == (), "prerequisite consent was bypassed"
        assert reasons == ("prerequisite-declined",)
        assert console.count("run them now?") == 1


def test_accepted_runs_exact_argv(root: Path, tmp_path: Path) -> None:
    """Each consented argv is attempted and vetoed; a batch stops at its first veto."""
    records, console, reasons = _actor(root, tmp_path / "accepted", "accepted")
    installers = _installers(records)
    expected = _expected(root, "prerequisites.packages.ubuntu.user.interactive")
    assert freeze([list(record.argv) for record in installers]) == expected, (
        "prerequisite argv differs"
    )
    assert all(record.vetoed for record in installers)
    assert reasons == tuple("prerequisite-install-failed" for _ in installers)
    assert "run them now?" in console
    batch, _console, _reasons = _actor(root, tmp_path / "batch", "batch")
    assert isinstance(expected, tuple)
    assert freeze([list(record.argv) for record in _installers(batch)]) == (
        expected[0],
    )


def test_non_tty_refuses_without_assume_yes(root: Path, tmp_path: Path) -> None:
    """Non-interactive refusal never prompts, while the flag uses sudo -n."""
    refused, console, reasons = _actor(root, tmp_path / "refused", "non-tty")
    assert reasons == ("prerequisite-consent-required",), "non-interactive run prompted"
    assert "run them now?" not in console, "non-interactive run prompted"
    assert _installers(refused) == ()
    consented, console, _reasons = _actor(root, tmp_path / "flag", "assume-yes")
    expected = _expected(root, "prerequisites.packages.ubuntu.user.assume-yes")
    assert (
        freeze([list(record.argv) for record in _installers(consented)]) == expected
    ), "sudo could prompt after --assume-yes"
    assert all(record.vetoed for record in _installers(consented))
    assert "run them now?" not in console


def test_root_and_xcode_actions_are_vetoed(root: Path, tmp_path: Path) -> None:
    """Root omits sudo and macOS attempts only the installer dialog request."""
    root_records, _console, _reasons = _actor(root, tmp_path / "root", "root")
    expected = _expected(root, "prerequisites.packages.ubuntu.root.assume-yes")
    assert (
        freeze([list(record.argv) for record in _installers(root_records)]) == expected
    )
    assert all(record.vetoed for record in _installers(root_records))
    mac_records, _console, _reasons = _actor(root, tmp_path / "mac", "xcode")
    assert tuple(record.argv for record in _installers(mac_records)) == (
        ("xcode-select", "--install"),
    )
    assert all(record.vetoed for record in _installers(mac_records))


def test_global_assume_yes_reaches_check(root: Path, tmp_path: Path) -> None:
    """The real click dispatcher transports both flag values to the owned child."""
    for mode, expected in (("global-no", "no"), ("global-yes", "yes")):
        records, console, reasons = _actor(root, tmp_path / mode, mode)
        assert reasons == ("preconditions",)
        assert "P1:" in console
        children = tuple(
            record
            for record in records
            if "from agentctl.check.steps import execute" in " ".join(record.argv)
        )
        assert len(children) == 1
        assert children[0].argv[-1] == expected, (
            "global consent flag did not reach check"
        )
        assert not children[0].vetoed
