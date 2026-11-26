# Copyright (c) 2026 agentctl contributors.
"""Native warning, suite routing, private configuration and package-data controls."""

import hashlib
import json
import os
import shutil
import sys
import tarfile
import zipfile
from contextlib import chdir
from dataclasses import replace
from pathlib import Path

import pytest
from hatchling.build import build_sdist, build_wheel

from agentctl.bootstrap import build
from agentctl.check import haskell, ownership, steps
from agentctl.check.evidence import Entry, source_census
from agentctl.check.steps import (
    _run_tools_observed,
    native_snapshot_unchanged,
    run_tools,
)
from agentctl.process import Output, run
from agentctl.result import Err, Ok, Result
from tests.harness.haskell import copy_project
from tests.harness.haskell_fixtures import haskell_build as _haskell_build_fixture

haskell_build = _haskell_build_fixture
PROTOCOL_VERSION = 2

pytestmark = pytest.mark.evidence("real")


def test_native_handoff_binds_real_execution(
    haskell_build: build.BuildContext,
    root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The handoff accepts the application's real native execution and sources."""
    directory = tmp_path / "native"
    assert isinstance(haskell.run_suites(haskell_build, directory, "real-native"), Ok)
    artifacts: object = json.loads((directory / "native-artifacts.json").read_text())
    assert isinstance(artifacts, dict)
    assert artifacts["nonce"] == "real-native"
    rows = artifacts["artifacts"]
    assert isinstance(rows, list)
    assert [row[0] for row in rows] == ["ghc", "cabal", "native-test"]
    assert all(
        len(row[2]) == steps.SHA256_HEX_LENGTH and Path(row[1]).is_file()
        for row in rows
    )
    for _role, path, digest in rows:
        with Path(path).open("rb") as stream:
            assert hashlib.file_digest(stream, "sha256").hexdigest() == digest
    census = ownership.guarded_census(root)
    assert isinstance(census, Ok)
    captured = steps.native_snapshot(directory, "real-native", census.value)
    assert isinstance(captured, Ok), captured

    def selected(
        _context: steps.CheckRun,
    ) -> Result[tuple[tuple[str, str, str], ...], str]:
        facts = haskell.native_artifact_facts(haskell_build)
        return Err(facts.error.message) if isinstance(facts, Err) else facts

    monkeypatch.setattr(steps, "_selected_native_artifacts", selected)
    marker = steps.native_observation_seal("real-native", captured.value)
    assert isinstance(marker, Ok)
    failed = {
        "python-commands",
        "tool-outcomes",
        "pytest-manifest",
        "oracle-outcomes",
        "host-observation",
        "ruff-observation",
        "ruff-format-observation",
        "coverage-observation",
        "mutant-killers",
        "ty-observation",
        "coverage-text-observation",
    }
    outcomes = tuple((name, int(name in failed)) for name in steps.FINALIZER_NAMES[:-1])
    final = steps.record_finalizers(directory, "real-native", outcomes)
    assert isinstance(final, Ok)
    context = steps.CheckRun(root, directory, "real-native", "Linux")
    assert steps.verify_native_handoff(
        context,
        directory,
        marker.value + "\nphase\n" + steps.finalizer_seal(final.value) + "\n",
    ) == Ok(None)


def _warning(context: build.BuildContext) -> None:
    """Add a valid unexported binding whose unused warning -Werror must reject."""
    module = context.project / "src/AgentCtl/Protocol.hs"
    with module.open("a", encoding="utf-8") as stream:
        stream.write("\nunusedControl :: Int\nunusedControl = 7\n")


def test_werror_fires(root: Path, tmp_path: Path) -> None:
    """A compiling twin precedes a real unused-binding compilation failure."""
    context = copy_project(root, tmp_path)
    assert haskell.compile_all(context) == Ok(None)
    _warning(context)
    result = haskell.compile_all(context)
    assert isinstance(result, Err), "unused binding did not fail the Werror build"
    assert "unusedControl" in result.error.message
    assert "Werror=unused-top-binds" in result.error.message


def test_failed_native_suite_preserves_case_observation(
    root: Path, tmp_path: Path
) -> None:
    """A real failed suite retains its case outcome without becoming a pass."""
    context = copy_project(root, tmp_path)
    main = context.project / "test/Main.hs"
    source = main.read_text(encoding="utf-8")
    original = "validHandoff Nothing @?= False"
    assert source.count(original) == 1
    main.write_text(
        source.replace(original, "validHandoff Nothing @?= True"), encoding="utf-8"
    )
    assert haskell.compile_all(context) == Ok(None)
    directory = tmp_path / "report"
    result = haskell.run_suites(context, directory, "native-failure")
    assert isinstance(result, Err), "failed native suite was accepted"
    observed = haskell.native_observation(directory, "native-failure")
    assert isinstance(observed, Ok), "failed native suite lost its observations"
    node = "haskell:agentctl-core-test/Handshake/handoff-required"
    assert node in observed.value.executed
    assert node not in observed.value.passed
    assert "failed: " + node in observed.value.forbidden
    assert "native-command-failed" in observed.value.forbidden
    assert isinstance(haskell.native_evidence(directory, "native-failure"), Err)
    source_entries = tuple(
        Entry(
            "src/agentctl/haskell/" + path.relative_to(context.project).as_posix(),
            "file",
            (path.read_bytes(),),
        )
        for path in sorted((context.project / "test").glob("*.hs"))
    )
    sources = haskell.read_sources(
        directory, "native-failure", observed.value.collected, source_entries
    )
    assert isinstance(sources, Ok), sources
    assert dict(sources.value)[node] == "src/agentctl/haskell/test/Main.hs"


def test_native_case_sources_match_compiled_callsites(
    haskell_build: build.BuildContext,
) -> None:
    """Every actual listed case has one compiler-reported source file."""
    listed = build.execute_binary(
        haskell_build, build.BinaryCall("test:agentctl-core-test", ("--list-tests",))
    )
    sources = build.execute_binary(
        haskell_build,
        build.BinaryCall("test:agentctl-core-test", ("--agentctl-test-sources",)),
    )
    assert isinstance(listed, Ok)
    assert listed.value.code == 0
    assert isinstance(sources, Ok)
    assert sources.value.code == 0
    rows = tuple(line.split("\t") for line in sources.value.stdout.splitlines())
    pair_fields = 2
    assert rows
    assert all(len(row) == pair_fields and row[1] for row in rows)
    names = tuple(row[0] for row in rows)
    assert len(set(names)) == len(names)
    assert frozenset(names) == frozenset(listed.value.stdout.splitlines())
    expected = haskell.listed(listed.value.stdout)
    assert isinstance(expected, Ok)
    observed = haskell.observe_sources(haskell_build, expected.value)
    assert isinstance(observed, Ok), observed
    assert {node for node, _path in observed.value} == expected.value
    mapped = {name: Path(path).as_posix() for name, path in rows}
    assert mapped["agentctl-core-test.Handshake.protocol-fields"].endswith(
        "test/Main.hs"
    )
    assert mapped["agentctl-core-test.Backoff.grows-to-cap"].endswith(
        "test/RecoveryTests.hs"
    )
    assert mapped["agentctl-core-test.ProcessReal.invalid-utf8-is-refused"].endswith(
        "test/ProcessTests.hs"
    )
    assert mapped["agentctl-core-test.MuxReal.host-multiplexer-meets-floor"].endswith(
        "test/MuxTests.hs"
    )
    for path in mapped.values():
        assert (haskell_build.project / path).is_file(), path


def test_user_cabal_config_ignored(root: Path, tmp_path: Path) -> None:
    """A test-owned user configuration cannot relax the application's warnings."""
    context = copy_project(root, tmp_path)
    configuration = context.host.home / ".cabal/config"
    configuration.parent.mkdir()
    configuration.write_text("package *\n  ghc-options: -Wno-error\n", encoding="utf-8")
    inherited = dict(context.host.environment)
    inherited.update(
        {"CABAL_DIR": str(configuration.parent), "CABAL_CONFIG": str(configuration)}
    )
    context = replace(
        context, host=replace(context.host, environment=tuple(inherited.items()))
    )
    assert build.environment(context)["CABAL_DIR"] == str(
        context.host.cache / "cabal"
    ), "user Cabal configuration replaced the private directory"
    assert haskell.compile_all(context) == Ok(None)
    _warning(context)
    result = haskell.compile_all(context)
    assert isinstance(result, Err), "user Cabal configuration relaxed Werror"
    assert "unusedControl" in result.error.message
    assert (
        configuration.read_text(encoding="utf-8")
        == "package *\n  ghc-options: -Wno-error\n"
    )


def test_every_suite_routed(
    haskell_build: build.BuildContext, root: Path, tmp_path: Path
) -> None:
    """The complete native suite passes; extra, conditional and empty suites fail."""
    verified = haskell.run_suites(haskell_build, tmp_path / "positive", "fresh")
    assert isinstance(verified, Ok), verified
    assert (
        "haskell:agentctl-core-test/Handshake/protocol-fields" in verified.value.passed
    )
    context = copy_project(root, tmp_path / "negative")
    cabal = context.project / "agentctl-core.cabal"
    original = cabal.read_text(encoding="utf-8")
    for extra in (
        "\ntest-suite unregistered\n  type: exitcode-stdio-1.0\n",
        "\nflag selectable\n",
        "\n  if flag(selectable)\n",
        "\n  buildable: False\n",
    ):
        cabal.write_text(original + extra, encoding="utf-8")
        assert isinstance(haskell.declared(context.project), Err), (
            "unrouted suite was accepted"
        )
        result = haskell.run_suites(context, tmp_path / "unrouted", "fresh")
        assert isinstance(result, Err), "unrouted suite was accepted"
        assert isinstance(haskell.compile_all(context), Err)
    cabal.write_text(original, encoding="utf-8")
    (context.project / "test/Main.hs").write_text(
        "module Main (main) where\n"
        "import AgentCtl.Protocol (handshake, handshakeProtocol)\n"
        "import Test.Tasty "
        "(defaultIngredients, defaultMainWithIngredients, testGroup)\n"
        "import Test.Tasty.HUnit (assertEqual)\n"
        "import Test.Tasty.Runners.AntXML (antXMLRunner)\n"
        "main :: IO ()\nmain = do\n"
        '  assertEqual "fixture protocol" 2 (handshakeProtocol handshake)\n'
        "  defaultMainWithIngredients (antXMLRunner : defaultIngredients) "
        '(testGroup "agentctl-core-test" [])\n',
        encoding="utf-8",
    )
    assert isinstance(build.compile_project(context), Ok)
    empty = haskell.run_suites(context, tmp_path / "empty", "fresh")
    assert isinstance(empty, Err), "empty suite was accepted"
    assert "listing" in empty.error.message


def test_direct_invocation_refused(haskell_build: build.BuildContext) -> None:
    """Absent and different versions refuse every command; the correct handoff works."""
    for supplied in (None, "0", "1"):
        for arguments in (("--handshake",), ("list",), ()):
            result = build.execute_binary(
                haskell_build,
                build.BinaryCall("exe:agentctl-core", arguments, protocol=supplied),
            )
            assert isinstance(result, Ok), result
            assert result.value.code != 0, (
                "core accepted invocation without the handoff"
            )
            assert "agentctl" in result.value.stderr
            assert "agentctl-core" not in result.value.stderr
    result = build.execute_binary(
        haskell_build, build.BinaryCall("exe:agentctl-core", ("--handshake",))
    )
    assert isinstance(result, Ok), result
    assert result.value.code == 0
    assert json.loads(result.value.stdout)["protocol"] == PROTOCOL_VERSION
    for consent in (None, "", "TRUE", "1"):
        refused = build.execute_binary(
            haskell_build,
            build.BinaryCall("exe:agentctl-core", ("--handshake",), consent=consent),
        )
        assert isinstance(refused, Ok), refused
        assert refused.value.code != 0, "core accepted invalid consent"
        assert "agentctl" in refused.value.stderr
    accepted = build.execute_binary(
        haskell_build,
        build.BinaryCall("exe:agentctl-core", ("--handshake",), consent="true"),
    )
    assert isinstance(accepted, Ok), accepted
    assert accepted.value.code == 0, "core refused valid consent"
    assert build.execute_binary(
        haskell_build, build.BinaryCall("exe:agentctl-core", ("unknown",))
    ) == Ok(Output(1, "", "Run agentctl to manage terminal agents.\n"))


def test_wheel_ships_haskell_sources(root: Path, tmp_path: Path) -> None:
    """Both source distributions carry checkout data without requiring git tracking."""
    source = tmp_path / "checkout"
    shutil.copytree(root / "src", source / "src")
    for name in ("pyproject.toml", ".gitignore", "README.md"):
        shutil.copyfile(root / name, source / name)
    project = source / "src/agentctl/haskell"
    (project / "uncommitted-source.txt").write_text(
        "source without git", encoding="utf-8"
    )
    expected = {
        path.relative_to(project).as_posix()
        for path in project.rglob("*")
        if path.is_file()
    }
    garbage = project / "dist-newstyle/generated.o"
    garbage.parent.mkdir()
    garbage.write_bytes(b"not source")
    outputs = tmp_path / "archives"
    outputs.mkdir()
    with chdir(source):
        wheel = outputs / build_wheel(str(outputs))
        sdist = outputs / build_sdist(str(outputs))
    with zipfile.ZipFile(wheel) as archive:
        actual = {
            name.removeprefix("agentctl/haskell/")
            for name in archive.namelist()
            if name.startswith("agentctl/haskell/")
        }
        assert actual == expected, "wheel excludes Haskell checkout sources"
        assert not any("dist-newstyle/" in name for name in archive.namelist())
    with tarfile.open(sdist) as archive:
        actual = {
            name.split("/src/agentctl/haskell/", 1)[1]
            for name in archive.getnames()
            if "/src/agentctl/haskell/" in name
        }
        assert actual == expected
        assert not any("dist-newstyle/" in name for name in archive.getnames())


def test_native_leg_execution_and_failures(
    root: Path, haskell_build: build.BuildContext, tmp_path: Path
) -> None:
    """The real gate path executes both native legs and reports refused contexts."""
    build_step = haskell.HaskellStep(
        "cabal-build", haskell_build.host, haskell_build.project
    )
    assert run_tools(haskell_build.project, tmp_path, "fresh", (build_step,)) == 0
    captured = source_census(root)
    assert isinstance(captured, Ok)
    test_step = haskell.HaskellStep(
        "cabal-test", haskell_build.host, haskell_build.project
    )
    observed = _run_tools_observed(
        haskell_build.project,
        tmp_path,
        "fresh",
        (test_step,),
        source_entries=captured.value,
    )
    assert observed.code == 0
    assert isinstance(observed.native, Ok), "real native evidence was not captured"
    assert native_snapshot_unchanged(tmp_path, "fresh", observed.native) == 0
    missing = replace(haskell_build.host, cache=tmp_path / "absent-cache")
    assert (
        haskell.run_step(
            haskell.HaskellStep("cabal-build", missing, haskell_build.project),
            tmp_path,
            "fresh",
        )
        == 1
    )
    assert (
        haskell.run_step(
            haskell.HaskellStep(
                "cabal-build", haskell_build.host, tmp_path / "absent-project"
            ),
            tmp_path,
            "fresh",
        )
        == 1
    )


def test_process_utf8_input(tmp_path: Path) -> None:
    """The sole process boundary forwards real multiline UTF-8 stdin exactly once."""
    text = "one\nλ二\n"
    result = run(
        [sys.executable, "-c", "import sys; sys.stdout.write(sys.stdin.read())"],
        cwd=tmp_path,
        env=os.environ,
        input_text=text,
    )
    assert result == Ok(Output(0, text, ""))
