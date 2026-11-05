# Copyright (c) 2026 agentctl contributors.
"""Native warning, suite routing, private configuration and package-data controls."""

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
from agentctl.check import haskell
from agentctl.check.steps import run_tools
from agentctl.process import Output, run
from agentctl.result import Err, Ok
from tests.harness.haskell import copy_project

pytestmark = pytest.mark.evidence("real")


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
        '  assertEqual "fixture protocol" 1 (handshakeProtocol handshake)\n'
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
    for supplied in (None, "0", "2"):
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
    assert json.loads(result.value.stdout)["protocol"] == 1
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
    haskell_build: build.BuildContext, tmp_path: Path
) -> None:
    """The real gate path executes both native legs and reports refused contexts."""
    for name in ("cabal-build", "cabal-test"):
        step = haskell.HaskellStep(name, haskell_build.host, haskell_build.project)
        assert run_tools(haskell_build.project, tmp_path, "fresh", (step,)) == 0
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
