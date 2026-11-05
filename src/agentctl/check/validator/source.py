# Copyright (c) 2026 agentctl contributors.
"""Static absence guards, extended as their owning capabilities land."""

import ast
import os
import re
import tokenize
import tomllib
from dataclasses import dataclass
from io import StringIO
from pathlib import Path

FORBIDDEN_NAMES = frozenset(
    {
        "Makefile",
        "makefile",
        "GNUmakefile",
        "justfile",
        "Justfile",
        "tox.ini",
        "noxfile.py",
        ".pre-commit-config.yaml",
    }
)


@dataclass(frozen=True, slots=True)
class CoverageException:
    """One exact native-API boundary with a documented reason for exclusion."""

    path: str
    line: int
    source: str
    reason: str


COVERAGE_EXCEPTIONS = (
    CoverageException(
        "src/agentctl/check/preconditions.py",
        127,
        "def _file_lock(handle: IO[str], *, unlock: bool) -> None:  # pragma: no cover",
        "Native kernel locks are covered by real contention controls on each host.",
    ),
    CoverageException(
        "src/agentctl/process.py",
        125,
        "def _posix_alive(pid: int) -> Result[bool, SpawnError]:  # pragma: no cover",
        "Signal zero needs POSIX; real owned-process controls cover this API.",
    ),
    CoverageException(
        "src/agentctl/process.py",
        136,
        "def _windows_alive(pid: int) -> Result[bool, SpawnError]:  # pragma: no cover",
        "Query handles need Win32; real owned-process controls run on Windows.",
    ),
)


def forbidden_surfaces(root: Path) -> tuple[str, ...]:
    """Keep check as the only workflow entry surface outside data fixtures."""
    names: tuple[str, ...] = ()
    for current, directories, files in os.walk(root):
        directory = Path(current)
        directories[:] = [
            name
            for name in directories
            if directory / name not in {root / ".git", root / "tests/fixtures"}
        ]
        for name in files:
            path = directory / name
            relative = path.relative_to(root)
            script = path.suffix in {".sh", ".ps1", ".bat", ".cmd"} or (
                path.suffix == ".py" and relative.parts[0] not in {"src", "tests"}
            )
            if name in FORBIDDEN_NAMES or script:
                names += (relative.as_posix(),)
    directories = tuple(
        path
        for path in (".github/workflows", ".githooks", "hooks", "scripts")
        if (root / path).exists()
    )
    return tuple(
        sorted(f"tree.forbidden-surfaces: {name}" for name in (*names, *directories))
    ) + _script_entries(root)


def _script_entries(root: Path) -> tuple[str, ...]:
    """Reject a parallel Python console entry point in project metadata."""
    path = root / "pyproject.toml"
    if not path.exists():
        return ()
    try:
        project: object = tomllib.loads(path.read_text(encoding="utf-8")).get("project")
    except (OSError, UnicodeError, tomllib.TOMLDecodeError):
        return ("tree.forbidden-surfaces: unreadable project scripts",)
    if not isinstance(project, dict) or not isinstance(project.get("scripts"), dict):
        return ("tree.forbidden-surfaces: missing project scripts",)
    return (
        ()
        if project["scripts"] == {"agentctl": "agentctl.cli:main"}
        else ("tree.forbidden-surfaces: parallel project scripts",)
    )


def _name(node: ast.AST, aliases: dict[str, str]) -> str:
    """Resolve imported names and attributes without executing a module."""
    if isinstance(node, ast.Name):
        return aliases.get(node.id, node.id)
    if isinstance(node, ast.Attribute):
        return _name(node.value, aliases) + "." + node.attr
    return ""


def _imports(tree: ast.AST) -> dict[str, str]:
    """Map both import forms to their canonical spellings."""
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                aliases[alias.asname or alias.name.split(".")[0]] = alias.name
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                aliases[alias.asname or alias.name] = (
                    (node.module or "") + "." + alias.name
                )
    return aliases


def _process(tree: ast.AST, aliases: dict[str, str], relative: str) -> bool:
    """Permit process creation imports and calls only at the one boundary."""
    if relative == "src/agentctl/process.py":
        return False
    if any(
        name == "subprocess" or name.startswith("subprocess.")
        for name in aliases.values()
    ):
        return True
    process_names = {
        "system",
        "popen",
        "fork",
        "forkpty",
        "posix_spawn",
        "posix_spawnp",
    }
    for node in ast.walk(tree):
        name = _name(node, aliases)
        if name.startswith("os.") and (
            name[3:] in process_names or name[3:].startswith(("exec", "spawn"))
        ):
            return True
        if (
            isinstance(node, ast.Call)
            and _name(node.func, aliases)
            in {
                "__import__",
                "importlib.import_module",
            }
            and (
                node.args
                and isinstance(node.args[0], ast.Constant)
                and node.args[0].value == "subprocess"
            )
        ):
            return True
    return False


def _suppression(
    tree: ast.AST, aliases: dict[str, str], text: str, relative: str
) -> bool:
    """Inspect executable forms and actual comments, leaving fixture strings alone."""
    comments = tuple(
        token.string
        for token in tokenize.generate_tokens(StringIO(text).readline)
        if token.type == tokenize.COMMENT
        and not any(
            exception.path == relative
            and exception.line == token.start[0]
            and exception.source == token.line.rstrip("\r\n")
            and exception.reason
            for exception in COVERAGE_EXCEPTIONS
        )
    )
    if any(
        re.search(
            r"noqa|type:\s*ignore|ty:\s*ignore|pragma:\s*no\s*(?:cover|branch)|(?:fmt|ruff):\s*(?:off|skip)",
            comment,
        )
        for comment in comments
    ):
        return True
    banned = {
        "typing.Any",
        "typing.cast",
        "typing.no_type_check",
        "typing.TYPE_CHECKING",
        "warnings.filterwarnings",
        "warnings.simplefilter",
        "warnings.catch_warnings",
        "pytest.skip",
        "pytest.xfail",
        "pytest.importorskip",
        "pytest.mark.skip",
        "pytest.mark.skipif",
        "pytest.mark.xfail",
    }
    return any(_name(node, aliases) in banned for node in ast.walk(tree))


def _test_branch(tree: ast.AST, aliases: dict[str, str], relative: str) -> bool:
    """Reserve check-run controls for gate infrastructure, never product behavior."""
    keys: tuple[str, ...] = ()
    for node in ast.walk(tree):
        value: ast.AST | None = None
        if (
            isinstance(node, ast.Call)
            and node.args
            and _name(node.func, aliases) in {"os.getenv", "os.environ.get"}
        ):
            value = node.args[0]
        elif (
            isinstance(node, ast.Subscript)
            and _name(node.value, aliases) == "os.environ"
        ):
            value = node.slice
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            keys += (value.value,)
    return any(
        key in {"PYTEST_CURRENT_TEST", "TEST_MODE", "TESTING"}
        or key.startswith(("AGENTCTL_TEST", "AGENTCTL_MOCK"))
        or (
            key.startswith("AGENTCTL_CHECK_")
            and not relative.startswith("src/agentctl/check/")
        )
        for key in keys
    )


def _login(tree: ast.AST, aliases: dict[str, str]) -> bool:
    """Reject executable login arguments and keystrokes, admitting remedy prose."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        argument = node.args[0]
        if isinstance(argument, (ast.List, ast.Tuple)) and any(
            isinstance(item, ast.Constant) and item.value == "login"
            for item in argument.elts
        ):
            return True
        if _name(node.func, aliases).rsplit(".", 1)[-1] in {
            "send_keys",
            "send",
            "sendline",
        } and (
            isinstance(argument, ast.Constant)
            and isinstance(argument.value, str)
            and re.search(r"\blogin\b", argument.value)
        ):
            return True
    return False


def python_source(text: str, relative: str) -> tuple[str, ...]:
    """Classify source violations independently with stable rule identifiers."""
    try:
        tree = ast.parse(text)
        aliases = _imports(tree)
        checks = (
            ("src.one-process-module", _process(tree, aliases, relative)),
            ("src.suppression-ban", _suppression(tree, aliases, text, relative)),
            ("src.no-test-branches", _test_branch(tree, aliases, relative)),
            ("src.no-login-construction", _login(tree, aliases)),
        )
    except (SyntaxError, tokenize.TokenError):
        return ("src.parse: " + relative,)
    return tuple(name + ": " + relative for name, invalid in checks if invalid)


NATIVE_PROCESS = "src/agentctl/haskell/src/AgentCtl/native_process.c"


def native_source(text: str, relative: str) -> tuple[str, ...]:
    """Restrict native exec, warning controls and test-only environment branches."""
    calls = re.findall(
        r"\b(?:exec[lv][a-z]*|_w?exec[a-z]*|_w?spawn[a-z]*|posix_spawnp?|"
        r"fork|vfork|system|popen|_wpopen|syscall|kill(?:pg)?|raise|CreateProcess[AW]?|"
        r"ShellExecute(?:Ex)?[AW]?)\s*\(",
        text,
    )
    invalid_process = any(
        call.partition("(")[0].strip() not in {"execve", "_wexecve", "kill"}
        or relative != NATIVE_PROCESS
        for call in calls
    )
    suppression = bool(
        re.search(
            r"-Wno-|(?:#\s*pragma|_Pragma)[^\n]*"
            r"(?:diagnostic[^\n]*ignored|warning\s*\([^\n]*disable)",
            text,
        )
    )
    test_branch = bool(
        re.search(
            r"\b(?:PYTEST_CURRENT_TEST|TEST_MODE|TESTING|"
            r"AGENTCTL_(?:TEST|MOCK|CHECK)_\w*)\b",
            text,
        )
    )
    return tuple(
        rule + ": " + relative
        for rule, invalid in (
            ("src.one-process-module", invalid_process),
            ("src.suppression-ban", suppression),
            ("src.no-test-branches", test_branch),
        )
        if invalid
    )


def haskell_source(text: str, relative: str) -> tuple[str, ...]:
    """Guard Haskell process imports, the native exec binding and suppressions."""
    problems: tuple[str, ...] = ()
    if re.search(
        r"^import\s+(?:qualified\s+)?System\.Process\b", text, re.MULTILINE
    ) and not relative.endswith("/AgentCtl/Process.hs"):
        problems += ("src.one-process-module: " + relative,)
    foreign_exec = bool(
        re.search(
            r'foreign\s+import[^"]*"[^"]*\bagentctl_(?:exec|request_reap)\b',
            text,
        )
    )
    if foreign_exec and not relative.endswith("/AgentCtl/Process.hs"):
        problems += ("src.one-process-module: " + relative,)
    if re.search(r"-Wno-|HLINT.*ignore|ormolu-disable|fourmolu-disable", text):
        problems += ("src.suppression-ban: " + relative,)
    return problems


def sources(root: Path) -> tuple[str, ...]:
    """Walk the complete package and tests; only product code owns process choices."""
    paths = tuple(sorted((root / "src").rglob("*.py")))
    tests = tuple(sorted((root / "tests").rglob("*.py")))
    if not paths or not tests:
        return ("validator.non-vacuous: Python source and tests are required",)
    problems: tuple[str, ...] = ()
    for path in (*paths, *tests):
        relative = path.relative_to(root).as_posix()
        try:
            found = python_source(path.read_text(encoding="utf-8"), relative)
        except (OSError, UnicodeError):
            problems += ("src.parse: " + relative,)
            continue
        problems += tuple(
            problem
            for problem in found
            if relative.startswith("src/") or problem.startswith("src.suppression-ban:")
        )
    for path in sorted(
        path for pattern in ("*.hs", "*.c", "*.h") for path in root.rglob(pattern)
    ):
        if path.is_relative_to(root / "tests/fixtures"):
            continue
        relative = path.relative_to(root).as_posix()
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            problems += ("src.parse: " + relative,)
            continue
        if path.suffix in {".c", ".h"}:
            problems += native_source(text, relative)
            continue
        problems += haskell_source(text, relative)
    return problems


def configuration(root: Path) -> tuple[str, ...]:
    """Compare each complete governed tool table to its effective frozen row."""
    try:
        document = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
        rows: object = tomllib.loads(
            (root / "tests/oracles/lint_config.toml").read_text(encoding="utf-8")
        ).get("case")
    except (OSError, UnicodeError, tomllib.TOMLDecodeError):
        return ("config.pinned: unreadable configuration or oracle",)
    if (
        not isinstance(rows, list)
        or not rows
        or not all(isinstance(row, dict) for row in rows)
    ):
        return ("config.pinned: missing configuration oracle",)
    amended = {
        row.get("amends")
        for row in rows
        if isinstance(row, dict) and isinstance(row.get("amends"), str)
    }
    effective = tuple(
        row for row in rows if isinstance(row, dict) and row.get("id") not in amended
    )
    tool = document.get("tool", {})
    if not isinstance(tool, dict) or len(effective) != 1:
        return ("config.pinned: ambiguous configuration",)
    actual = {name: tool.get(name) for name in ("ty", "pytest", "coverage")}
    actual["ruff"] = tool.get("ruff")
    return (
        ()
        if actual == effective[0].get("expected")
        else ("config.pinned: tool configuration differs from oracle",)
    )
