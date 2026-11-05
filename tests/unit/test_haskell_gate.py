# Copyright (c) 2026 agentctl contributors.
"""Two-sided controls for native component, report and current-evidence validation."""

import json
from dataclasses import replace
from pathlib import Path

import pytest

from agentctl.bootstrap import build
from agentctl.check import haskell
from agentctl.check.evidence import RunEvidence
from agentctl.result import Err, Ok
from tests.harness.bootstrap import context

pytestmark = pytest.mark.evidence("value")
NODE = "haskell:agentctl-core-test/Handshake/protocol-fields"
XML = (
    '<testsuites tests="1"><testsuite><testcase '
    'classname="agentctl-core-test.Handshake" name="protocol-fields"/>'
    "</testsuite></testsuites>"
)


def test_closed_components_and_listings(root: Path, tmp_path: Path) -> None:
    """A routed package and unique listing pass beside every rejected shape."""
    text = (root / "src/agentctl/haskell/agentctl-core.cabal").read_text(
        encoding="utf-8"
    )
    assert isinstance(haskell.components(text), Ok)
    for invalid in (
        "",
        text + "\nlibrary\n",
        text.replace("test-suite agentctl-core-test", "test-suite other"),
        text + "\n  else\n",
    ):
        assert isinstance(haskell.components(invalid), Err)
    assert haskell.listed("agentctl-core-test.Handshake.protocol-fields\n") == Ok(
        frozenset({NODE})
    )
    for invalid in (
        "",
        "bad",
        "agentctl-core-test.Handshake.protocol-fields\nagentctl-core-test.Handshake.protocol-fields\n",
    ):
        assert isinstance(haskell.listed(invalid), Err)
    assert isinstance(haskell.declared(tmp_path), Err)
    (tmp_path / "agentctl-core.cabal").write_bytes(b"\xff")
    assert isinstance(haskell.declared(tmp_path), Err)


def test_xml_requires_actual_nonempty_cases() -> None:
    """Malformed, skipped, failed, duplicate and differently selected cases fail."""
    expected = frozenset({NODE})
    assert haskell.verify_report(XML, expected, "fresh") == Ok(
        RunEvidence("fresh", expected, expected, expected, (), ((NODE, "value"),))
    )
    real_node = NODE.replace("Handshake", "MuxReal")
    native = haskell.verify_report(
        XML.replace("Handshake", "MuxReal"), frozenset({real_node}), "fresh"
    )
    assert isinstance(native, Ok)
    assert native.value.classes == ((real_node, "real"),)
    for invalid in (
        "",
        "<broken",
        '<!DOCTYPE root><testsuites tests="0"/>',
        '<testsuites tests="0"/>',
        XML.replace("testsuites", "other"),
        XML.replace('tests="1"', 'tests="2"'),
        XML.replace('name="protocol-fields"', 'name=""'),
        XML.replace('classname="agentctl-core-test.Handshake"', ""),
        XML.replace("/></testsuite>", "><skipped/></testcase></testsuite>"),
        XML.replace(
            "/></testsuite>", "><failure>named defect</failure></testcase></testsuite>"
        ),
        XML.replace(
            "/></testsuite>", "><error>runtime defect</error></testcase></testsuite>"
        ),
        XML.replace(
            "</testsuite>",
            '<testcase classname="agentctl-core-test.Handshake" '
            'name="protocol-fields"/></testsuite>',
        ),
    ):
        assert isinstance(haskell.verify_report(invalid, expected, "fresh"), Err), (
            invalid
        )
    assert isinstance(
        haskell.verify_report(XML, frozenset({"haskell:other"}), "fresh"), Err
    )
    failures = haskell.report(
        XML.replace(
            "/></testsuite>", "><failure>named defect</failure></testcase></testsuite>"
        )
    )
    assert failures == Ok(((NODE, "named defect"),))


def test_native_evidence_must_be_fresh_and_complete(tmp_path: Path) -> None:
    """An independent current manifest joins; stale, partial or forged classes fail."""
    python = RunEvidence(
        "fresh",
        frozenset({"python"}),
        frozenset({"python"}),
        frozenset({"python"}),
        (),
        (("python", "real"),),
    )
    assert isinstance(haskell.combined(tmp_path, python, "fresh"), Err)
    record = {
        "nonce": "fresh",
        "collected": [NODE],
        "executed": [NODE],
        "passed": [NODE],
        "forbidden": [],
        "classes": {NODE: "value"},
    }
    path = tmp_path / "haskell-manifest.json"
    path.write_text(json.dumps(record), encoding="utf-8")
    combined = haskell.combined(tmp_path, python, "fresh")
    assert isinstance(combined, Ok)
    assert combined.value.passed == frozenset({"python", NODE})
    for changes in (
        {"nonce": "old"},
        {"executed": []},
        {"classes": {NODE: "real"}},
        {
            "collected": ["python"],
            "executed": ["python"],
            "passed": ["python"],
            "classes": {"python": "value"},
        },
    ):
        path.write_text(json.dumps({**record, **changes}), encoding="utf-8")
        assert isinstance(haskell.combined(tmp_path, python, "fresh"), Err)
    real_node = NODE.replace("Handshake", "MuxReal")
    for evidence_class, accepted in (("real", True), ("value", False)):
        real_record = {
            **record,
            "collected": [real_node],
            "executed": [real_node],
            "passed": [real_node],
            "classes": {real_node: evidence_class},
        }
        path.write_text(json.dumps(real_record), encoding="utf-8")
        assert isinstance(haskell.combined(tmp_path, python, "fresh"), Ok) is accepted


def test_index_pin_and_owned_environment(tmp_path: Path) -> None:
    """Warm index predicates never accept missing, multiple or unmodelled pins."""
    project = tmp_path / "project"
    project.mkdir()
    path = project / "cabal.project"
    assert isinstance(build.index_state(project), Err)
    for text in (
        "",
        "index-state: latest",
        "index-state: 2026-10-31T00:00:00Z\nindex-state: 2026-10-31T00:00:00Z\n",
    ):
        path.write_text(text, encoding="utf-8")
        assert isinstance(build.index_state(project), Err)
    path.write_text("index-state: 2026-10-31T00:00:00Z\n", encoding="utf-8")
    assert build.index_state(project) == Ok("2026-10-31T00:00:00Z")
    for name in ("cabal.project.local", "cabal.project.freeze"):
        sidecar = project / name
        sidecar.touch()
        assert isinstance(build.index_state(project), Err)
        sidecar.unlink()
    path.write_bytes(b"\xff")
    assert isinstance(build.index_state(project), Err)
    host = context(tmp_path / "owned")
    assert isinstance(build.recorded_tools(host), Err)
    host.cache.mkdir()
    record = host.cache / "toolchain-paths.toml"
    record.write_bytes(b"invalid TOML [")
    assert isinstance(build.recorded_tools(host), Err)
    inherited = {
        "PATH": "bin",
        "HOME": str(host.home),
        "CABAL_DIR": "foreign",
        "CABAL_CONFIG": "foreign",
        "GHC_OPTIONS": "foreign",
        "TASTY_PATTERN": "none",
        "COVERAGE_PROCESS_START": "foreign",
    }
    value = build.BuildContext(
        project,
        tmp_path / "build",
        replace(host, environment=tuple(inherited.items())),
        build.Toolchain("ghc", "cabal"),
    )
    assert build.environment(value) == {
        "PATH": "bin",
        "HOME": str(host.home),
        "CABAL_DIR": str(host.cache / "cabal"),
        "LC_ALL": "C.UTF-8",
        "GHC_ENVIRONMENT": "-",
    }
    assert build.bundled_project().name == "haskell"
