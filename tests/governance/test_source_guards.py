# Copyright (c) 2026 agentctl contributors.
"""Independent invalid source/configuration examples and legal controls."""

from pathlib import Path

import pytest

from agentctl.check.validator.source import (
    configuration,
    native_source,
    python_source,
    sources,
)

pytestmark = pytest.mark.evidence("value")
SUBJECT = "src/agentctl/subject.py"


def _reject(rule: str, source: str) -> None:
    """Require exactly the intended diagnostic from a minimal source example."""
    assert python_source(source, SUBJECT) == (rule + ": " + SUBJECT,), (
        rule + " was bypassed"
    )


def test_subprocess_import_outside_process_module() -> None:
    """Aliased imports, OS calls and dynamic imports share the same boundary."""
    for source in (
        "import subprocess as sp\nsp.run(['echo'])",
        "from subprocess import Popen as spawn\nspawn(['echo'])",
        "import os as operating\noperating.execv('echo', ['echo'])",
        "from os import spawnv as spawn\nspawn(0, 'echo', ['echo'])",
        "import os\nos.system('echo')",
        "import os\nos.posix_spawn('echo', ['echo'], {})",
        "import importlib as imp\nimp.import_module('subprocess')",
        "__import__('subprocess')",
    ):
        _reject("src.one-process-module", source)
        assert python_source(source, "src/agentctl/process.py") == ()
    assert (
        python_source("from agentctl.process import run\nrun(['echo'])", SUBJECT) == ()
    )
    assert python_source("import os\nos.getpid()", SUBJECT) == ()


def test_suppression_ban_fixtures() -> None:
    """Actual comments and executable suppressions fail; quoted examples pass."""
    for source in (
        "value = 1  # noqa: F401",
        "value = 1  # type: ignore",
        "value = 1  # ty: ignore",
        "# fmt: off\nvalue = 1",
        "# pragma: no cover\nvalue = 1",
        "from typing import Any as Unknown\nvalue: Unknown",
        "import typing as t\nt.cast(int, 1)",
        "from typing import TYPE_CHECKING\nif TYPE_CHECKING: pass",
        "import warnings as w\nw.filterwarnings('ignore')",
        "import warnings\nwarnings.simplefilter('ignore')",
        "import warnings\nwarnings.catch_warnings()",
        "import pytest as p\np.skip('reason')",
        "import pytest\npytest.importorskip('missing')",
        "import pytest\n@pytest.mark.xfail\ndef test_example(): pass",
    ):
        _reject("src.suppression-ban", source)
    assert python_source('example = "# noqa: F401"', SUBJECT) == ()
    assert python_source("value: int = 1", SUBJECT) == ()


def test_no_test_branches() -> None:
    """Environment access cannot change product behavior under tests."""
    for source in (
        "import os\nif os.environ.get('AGENTCTL_TEST_MODE'): pass",
        "from os import getenv as get\nif get('PYTEST_CURRENT_TEST'): pass",
        "import os as o\nif o.environ['TESTING']: pass",
        "import os\nif os.getenv('AGENTCTL_CHECK_NONCE'): pass",
    ):
        _reject("src.no-test-branches", source)
    assert python_source("import os\nos.getenv('HOME')", SUBJECT) == ()
    assert (
        python_source(
            "import os\nos.getenv('AGENTCTL_CHECK_NONCE')",
            "src/agentctl/check/subject.py",
        )
        == ()
    )


def test_no_login_construction() -> None:
    """Login execution and keystrokes fail while user remedy strings remain valid."""
    for source in (
        "from agentctl.process import run\nrun(['claude', 'auth', 'login'])",
        "from agentctl.process import run as invoke\ninvoke(('codex', 'login'))",
        "terminal.send_keys('codex login\\n')",
    ):
        _reject("src.no-login-construction", source)
    assert python_source('remedy = "Run codex login in your terminal"', SUBJECT) == ()
    assert (
        python_source(
            "from agentctl.process import run\nrun(['codex', 'login-status'])", SUBJECT
        )
        == ()
    )


def test_live_tree_clean(root: Path) -> None:
    """The complete current source walk is nonempty and has no exemptions."""
    assert sources(root) == ()


def test_native_process_boundary(tmp_path: Path) -> None:
    """Only the native exec adapter and its Haskell owner may invoke exec."""
    allowed = "src/agentctl/haskell/src/AgentCtl/native_process.c"
    other = "src/agentctl/haskell/src/AgentCtl/native_fs.c"
    for call in ("execve(path, argv, env);", "_wexecve(path, argv, env);"):
        assert native_source(call, allowed) == ()
        assert native_source(call, other) == ("src.one-process-module: " + other,), (
            "native exec scope was bypassed"
        )
    for call in (
        "system(text);",
        "popen(text);",
        "fork();",
        "vfork();",
        "posix_spawn(path);",
        "posix_spawnp(path);",
        "_wspawnv(path);",
        "CreateProcessW(path);",
        "ShellExecuteExW(path);",
        "syscall(number);",
        "killpg(group, signal);",
        "raise(signal);",
    ):
        assert native_source(call, allowed) == (
            "src.one-process-module: " + allowed,
        ), "native shell or spawn was admitted"
    assert native_source("bytes = read(fd, buffer, size);", other) == ()
    assert native_source("kill(pid, SIGCHLD);", allowed) == ()
    assert native_source("kill(pid, SIGCHLD);", other) == (
        "src.one-process-module: " + other,
    ), "native signal escaped its owner"
    package = tmp_path / "src"
    package.mkdir()
    tests = tmp_path / "tests"
    tests.mkdir()
    (package / "subject.py").write_text("value = 1\n", encoding="utf-8")
    (tests / "test_example.py").write_text("value = 1\n", encoding="utf-8")
    owner = package / "AgentCtl/Process.hs"
    owner.parent.mkdir()
    binding = 'foreign import ccall safe "agentctl_exec" execProgram :: IO Int\n'
    owner.write_text(binding, encoding="utf-8")
    assert sources(tmp_path) == ()
    outside = package / "Other.hs"
    outside.write_text(binding, encoding="utf-8")
    assert sources(tmp_path) == ("src.one-process-module: src/Other.hs",), (
        "foreign exec binding escaped its owner"
    )
    reap_binding = (
        'foreign import ccall unsafe "agentctl_request_reap" request :: IO Int\n'
    )
    owner.write_text(reap_binding, encoding="utf-8")
    outside.unlink()
    assert sources(tmp_path) == ()
    outside.write_text(reap_binding, encoding="utf-8")
    assert sources(tmp_path) == ("src.one-process-module: src/Other.hs",), (
        "foreign reap binding escaped its owner"
    )


def test_native_controls_and_walk(tmp_path: Path) -> None:
    """C and headers reject warning suppression and test controls in the walk."""
    location = "src/native_fs.c"
    for text in (
        '#pragma GCC diagnostic ignored "-Wunused"',
        '#pragma clang diagnostic ignored "-Wunused"',
        "#pragma warning(disable: 4100)",
        '_Pragma("GCC diagnostic ignored \\"-Wunused\\"")',
        'const char *option = "-Wno-unused";',
    ):
        assert native_source(text, location) == ("src.suppression-ban: " + location,), (
            "native warning suppression was admitted"
        )
    for key in (
        "AGENTCTL_TEST_MODE",
        "AGENTCTL_MOCK_IO",
        "AGENTCTL_CHECK_NONCE",
        "PYTEST_CURRENT_TEST",
        "TEST_MODE",
        "TESTING",
    ):
        assert native_source(f'getenv("{key}");', location) == (
            "src.no-test-branches: " + location,
        ), "native test branch was admitted"
    assert native_source('getenv("HOME");', location) == ()
    package = tmp_path / "src"
    package.mkdir()
    tests = tmp_path / "tests"
    tests.mkdir()
    (package / "subject.py").write_text("value = 1\n", encoding="utf-8")
    (tests / "test_example.py").write_text("value = 1\n", encoding="utf-8")
    for suffix in ("c", "h"):
        path = package / ("native." + suffix)
        path.write_text("execve(path, argv, env);", encoding="utf-8")
        assert sources(tmp_path) == ("src.one-process-module: src/native." + suffix,), (
            "native source walk was bypassed"
        )
        path.write_bytes(b"\xff")
        assert sources(tmp_path) == ("src.parse: src/native." + suffix,)
        path.unlink()
    assert sources(tmp_path) == ()


def test_lint_config_matches_oracle(root: Path, tmp_path: Path) -> None:
    """An exact copy qualifies; independent configuration drift is rejected."""
    directory = tmp_path / "tests/oracles"
    directory.mkdir(parents=True)
    (directory / "lint_config.toml").write_bytes(
        (root / "tests/oracles/lint_config.toml").read_bytes()
    )
    config = tmp_path / "pyproject.toml"
    original = (root / "pyproject.toml").read_text(encoding="utf-8")
    assert configuration(tmp_path)
    for search, replacement in (
        ('select = ["ALL"]', 'select = ["F"]'),
        ('all = "error"', 'all = "warn"'),
        ("strict = true", "strict = false"),
        ("fail_under = 100", "fail_under = 99"),
        ("[tool.ruff.lint]", '[tool.ruff]\nexclude = ["src"]\n[tool.ruff.lint]'),
    ):
        config.write_text(original, encoding="utf-8")
        assert configuration(tmp_path) == ()
        config.write_text(original.replace(search, replacement), encoding="utf-8")
        assert configuration(tmp_path) == (
            "config.pinned: tool configuration differs from oracle",
        ), "config drift was accepted"


def test_invalid_and_empty_source_tree(tmp_path: Path) -> None:
    """Unreadable grammar and an empty owned walk cannot qualify as clean."""
    assert python_source("def broken(", SUBJECT) == ("src.parse: " + SUBJECT,)
    assert sources(tmp_path) == (
        "validator.non-vacuous: Python source and tests are required",
    )
    package = tmp_path / "src"
    package.mkdir()
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_example.py").write_text("value = 1\n", encoding="utf-8")
    path = package / "subject.py"
    path.write_bytes(b"\xff")
    assert sources(tmp_path) == ("src.parse: src/subject.py",)
    path.write_text("value = 1\n", encoding="utf-8")
    assert sources(tmp_path) == ()
    native = package / "AgentCtl/Process.hs"
    native.parent.mkdir()
    native.write_text("import System.Process\n", encoding="utf-8")
    assert sources(tmp_path) == ()
    outside = package / "Other.hs"
    outside.write_text("import qualified System.Process as P\n", encoding="utf-8")
    assert sources(tmp_path) == ("src.one-process-module: src/Other.hs",)
    outside.write_text("{-# OPTIONS_GHC -Wno-unused-imports #-}\n", encoding="utf-8")
    assert sources(tmp_path) == ("src.suppression-ban: src/Other.hs",)
    outside.write_bytes(b"\xff")
    assert sources(tmp_path) == ("src.parse: src/Other.hs",)
    outside.unlink()
    fixture = tests / "fixtures/negative.hs"
    fixture.parent.mkdir()
    fixture.write_text("import System.Process\n", encoding="utf-8")
    assert sources(tmp_path) == ()


def test_invalid_config_schema(root: Path, tmp_path: Path) -> None:
    """Absent, malformed and ambiguous oracle/config inputs never match."""
    assert configuration(tmp_path) == (
        "config.pinned: unreadable configuration or oracle",
    )
    (tmp_path / "pyproject.toml").write_bytes((root / "pyproject.toml").read_bytes())
    directory = tmp_path / "tests/oracles"
    directory.mkdir(parents=True)
    path = directory / "lint_config.toml"
    for text in ("bad = [", "", "case = []", "case = [1]"):
        path.write_text(text, encoding="utf-8")
        assert configuration(tmp_path)
    path.write_text('[[case]]\nid = "one"\n[[case]]\nid = "two"', encoding="utf-8")
    assert configuration(tmp_path) == ("config.pinned: ambiguous configuration",)


def test_coverage_exception_scope() -> None:
    """Only the documented native definition at its exact path and line qualifies."""
    for path, line, definition in (
        (
            "src/agentctl/check/preconditions.py",
            127,
            "def _file_lock(handle: IO[str], *, unlock: bool) -> None:",
        ),
        (
            "src/agentctl/process.py",
            125,
            "def _posix_alive(pid: int) -> Result[bool, SpawnError]:",
        ),
        (
            "src/agentctl/process.py",
            136,
            "def _windows_alive(pid: int) -> Result[bool, SpawnError]:",
        ),
    ):
        source = "\n" * (line - 1) + definition + "  # pragma: no cover\n    pass\n"
        assert python_source(source, path) == ()
        for altered, location in (
            ("\n" + source, path),
            (source, "src/agentctl/another.py"),
            (source.replace("  # pragma", " # pragma"), path),
        ):
            assert python_source(altered, location) == (
                "src.suppression-ban: " + location,
            )
