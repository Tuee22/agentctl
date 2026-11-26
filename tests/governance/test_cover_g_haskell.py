# Copyright (c) 2026 agentctl contributors.
"""Native Haskell evidence refusals exercised through test-owned executables."""

import json
import stat
import sys
from dataclasses import dataclass, replace
from pathlib import Path

import pytest

from agentctl.bootstrap import build
from agentctl.bootstrap.toolchain import Toolchain
from agentctl.check import haskell
from agentctl.check.evidence import RunEvidence
from agentctl.result import Err, Ok
from tests.harness.bootstrap import context as host_context

pytestmark = pytest.mark.evidence("value")

CASE = "agentctl-core-test.Group.case-one"
NODE = "haskell:agentctl-core-test/Group/case-one"
SOURCE = "test/Main.hs"
PREFIX = "src/agentctl/haskell/"
CABAL_SCRIPT = """#!{python}
import sys
from pathlib import Path

here = Path(__file__).parent
if sys.argv[1] == "list-bin":
    sys.stdout.write((here / "list-bin.txt").read_text())
elif (here / "test-fail").exists():
    sys.exit(5)
"""
TEST_SCRIPT = """#!{python}
import shutil
import sys
from pathlib import Path

here = Path(__file__).parent
sys.stdout.write((here / ("out" + sys.argv[1])).read_text())
if (here / ("fail" + sys.argv[1])).exists():
    sys.exit(3)
removal = here / "remove-project"
if removal.exists() and sys.argv[1] == "--agentctl-test-sources":
    shutil.rmtree(removal.read_text())
"""


@dataclass(frozen=True, slots=True)
class Fixture:
    """A build context whose cabal and test executables are owned scripts."""

    context: build.BuildContext
    bin: Path
    build: Path


def _script(path: Path, template: str) -> None:
    path.write_text(template.format(python=sys.executable), encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def _fixture(root: Path) -> Fixture:
    project = root / "project"
    (project / "test").mkdir(parents=True)
    (project / SOURCE).write_text("module Main where\n", encoding="utf-8")
    cabal_file = build.bundled_project() / "agentctl-core.cabal"
    (project / "agentctl-core.cabal").write_bytes(cabal_file.read_bytes())
    tools = root / "bin"
    tools.mkdir()
    output = root / "build"
    output.mkdir()
    _script(tools / "cabal", CABAL_SCRIPT)
    (tools / "ghc").write_text("ghc", encoding="utf-8")
    _script(output / "native-test", TEST_SCRIPT)
    (tools / "list-bin.txt").write_text(
        str(output / "native-test") + "\n", encoding="utf-8"
    )
    (output / "out--list-tests").write_text(CASE + "\n", encoding="utf-8")
    (output / "out--agentctl-test-sources").write_text(
        CASE + "\t" + SOURCE + "\n", encoding="utf-8"
    )
    host = host_context(root / "host")
    value = build.BuildContext(
        project, output, host, Toolchain(str(tools / "ghc"), str(tools / "cabal"))
    )
    return Fixture(value, tools, output)


def _expected() -> frozenset[str]:
    return frozenset({NODE})


def test_owned_executables_observe_sources(tmp_path: Path) -> None:
    """The owned script pair yields the exact source join the parser expects."""
    fixture = _fixture(tmp_path)
    observed = haskell.observe_sources(fixture.context, _expected())
    assert observed == Ok(((NODE, PREFIX + SOURCE),))


def test_observe_sources_refuses_unrunnable_binary(tmp_path: Path) -> None:
    """A binary that cannot start is a typed error."""
    fixture = _fixture(tmp_path)
    (fixture.build / "native-test").chmod(stat.S_IRUSR | stat.S_IWUSR)
    assert isinstance(haskell.observe_sources(fixture.context, _expected()), Err)


def test_observe_sources_refuses_failing_listing(tmp_path: Path) -> None:
    """A nonzero source-listing status is refused."""
    fixture = _fixture(tmp_path)
    (fixture.build / "fail--agentctl-test-sources").write_text("", encoding="utf-8")
    result = haskell.observe_sources(fixture.context, _expected())
    assert result == Err(build.BuildError("Native case source listing failed"))


def test_observe_sources_refuses_malformed_listing(tmp_path: Path) -> None:
    """Unparseable listing output is refused."""
    fixture = _fixture(tmp_path)
    (fixture.build / "out--agentctl-test-sources").write_text(
        "junk\n", encoding="utf-8"
    )
    result = haskell.observe_sources(fixture.context, _expected())
    assert result == Err(build.BuildError("Invalid native case source listing"))


def test_observe_sources_refuses_absent_source(tmp_path: Path) -> None:
    """A reported source file that does not exist is refused."""
    fixture = _fixture(tmp_path)
    (fixture.context.project / SOURCE).unlink()
    result = haskell.observe_sources(fixture.context, _expected())
    assert result == Err(build.BuildError("Native case source path is unavailable"))


def test_observe_sources_refuses_vanished_project(tmp_path: Path) -> None:
    """A project removed during observation is a typed inspection failure."""
    fixture = _fixture(tmp_path)
    (fixture.build / "remove-project").write_text(
        str(fixture.context.project), encoding="utf-8"
    )
    result = haskell.observe_sources(fixture.context, _expected())
    assert isinstance(result, Err)
    assert result.error.message.startswith("Cannot inspect native case source: ")


def test_decode_source_record_refuses_row_shapes() -> None:
    """Rows outside the node/source pair shape, or unlisted nodes, are refused."""
    decode = haskell.__dict__["_decode_source_record"]
    bad_row = {"nonce": "n", "sources": [["only-one"]]}
    assert decode(bad_row, "n", _expected(), ()) == Err(
        build.BuildError("Invalid native case source record")
    )
    unlisted = {
        "nonce": "n",
        "sources": [["haskell:agentctl-core-test/Other/case", PREFIX + SOURCE]],
    }
    assert isinstance(decode(unlisted, "n", _expected(), ()), Err)


def test_read_sources_refuses_symlink(tmp_path: Path) -> None:
    """The retained source record cannot be a symbolic link."""
    target = tmp_path / "target.json"
    target.write_text(json.dumps({}), encoding="utf-8")
    (tmp_path / "haskell-sources.json").symlink_to(target)
    result = haskell.read_sources(tmp_path, "n", _expected(), ())
    assert result == Err(build.BuildError("Native case source record is a symlink"))


def test_artifact_facts_refuse_escaping_test_binary(tmp_path: Path) -> None:
    """A test executable outside the build root is refused."""
    fixture = _fixture(tmp_path)
    outside = tmp_path / "outside-test"
    outside.write_text("x", encoding="utf-8")
    (fixture.bin / "list-bin.txt").write_text(str(outside) + "\n", encoding="utf-8")
    result = haskell.native_artifact_facts(fixture.context)
    assert result == Err(
        build.BuildError("Native test executable escapes the build root")
    )


def test_artifact_facts_refuse_non_regular_tool(tmp_path: Path) -> None:
    """A directory standing in for a tool is not a regular file."""
    fixture = _fixture(tmp_path)
    directory = tmp_path / "ghc-directory"
    directory.mkdir()
    tools = replace(fixture.context.tools, ghc=str(directory))
    result = haskell.native_artifact_facts(replace(fixture.context, tools=tools))
    assert result == Err(build.BuildError("Native artifact is not a regular file"))


def test_artifact_facts_refuse_missing_tool(tmp_path: Path) -> None:
    """A missing tool is an inspection failure."""
    fixture = _fixture(tmp_path)
    tools = replace(fixture.context.tools, ghc=str(tmp_path / "absent-ghc"))
    result = haskell.native_artifact_facts(replace(fixture.context, tools=tools))
    assert isinstance(result, Err)
    assert result.error.message.startswith("Cannot inspect native artifacts: ")


def test_selected_artifacts_refuse_unprepared_host(tmp_path: Path) -> None:
    """Without recorded tools the selection cannot be resolved."""
    host = host_context(tmp_path / "host")
    result = haskell.selected_artifact_facts(host, tmp_path / "project")
    assert isinstance(result, Err)


def test_run_suites_refuses_unrunnable_listing(tmp_path: Path) -> None:
    """A test binary that cannot execute fails the listing step."""
    fixture = _fixture(tmp_path)
    (fixture.build / "native-test").chmod(stat.S_IRUSR | stat.S_IWUSR)
    result = haskell.run_suites(fixture.context, tmp_path / "evidence", "nonce")
    assert isinstance(result, Err)


def test_run_suites_refuses_failing_sources(tmp_path: Path) -> None:
    """A failing source observation stops before any suite run."""
    fixture = _fixture(tmp_path)
    (fixture.build / "fail--agentctl-test-sources").write_text("", encoding="utf-8")
    result = haskell.run_suites(fixture.context, tmp_path / "evidence", "nonce")
    assert result == Err(build.BuildError("Native case source listing failed"))


def test_test_and_record_refuses_unusable_directory(tmp_path: Path) -> None:
    """A report directory below a regular file is a typed failure."""
    fixture = _fixture(tmp_path)
    blocker = tmp_path / "blocker"
    blocker.write_text("file", encoding="utf-8")
    result = haskell.__dict__["_test_and_record"](
        fixture.context, blocker / "tasty.xml", _expected(), "nonce"
    )
    assert isinstance(result, Err)
    assert result.error.message.startswith("Cannot run fresh Tasty execution: ")


def test_record_artifacts_refuses_existing_record(tmp_path: Path) -> None:
    """An already present artifact record cannot be overwritten."""
    fixture = _fixture(tmp_path)
    facts = haskell.native_artifact_facts(fixture.context)
    assert isinstance(facts, Ok)
    directory = tmp_path / "evidence"
    directory.mkdir()
    (directory / "native-artifacts.json").write_text("{}", encoding="utf-8")
    record = haskell.__dict__["_record_native_artifacts"]
    accepted = record(fixture.context, directory, "n", facts.value, Ok(None))
    assert isinstance(accepted, Err)
    assert accepted.error.message.startswith("cannot retain native artifacts: ")
    failed = record(
        fixture.context, directory, "n", facts.value, Err(build.BuildError("suite"))
    )
    assert isinstance(failed, Err)
    assert failed.error.message.startswith("suite; cannot retain native artifacts: ")


def _native() -> RunEvidence:
    return RunEvidence("n", _expected(), frozenset(), frozenset(), (), ())


def test_compare_native_report_refuses_bad_reports(tmp_path: Path) -> None:
    """Absent, symlinked and malformed retained reports are refused."""
    compare = haskell.__dict__["_compare_native_report"]
    assert isinstance(compare(tmp_path, _native(), "n"), Err)
    target = tmp_path / "real.xml"
    target.write_text("<testsuites/>", encoding="utf-8")
    (tmp_path / "tasty.xml").symlink_to(target)
    assert compare(tmp_path, _native(), "n") == Err(
        build.BuildError("Native report is a symlink")
    )
    (tmp_path / "tasty.xml").unlink()
    (tmp_path / "tasty.xml").write_text("<testsuites/>", encoding="utf-8")
    assert isinstance(compare(tmp_path, _native(), "n"), Err)
