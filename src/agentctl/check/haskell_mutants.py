# Copyright (c) 2026 agentctl contributors.
"""Application-owned native mutation runs, with one reusable unoptimised build."""

import tempfile
from pathlib import Path

from agentctl.bootstrap import build
from agentctl.check.haskell import compile_all, listed, report
from agentctl.hostfacts import HostContext
from agentctl.process import Output
from agentctl.result import Err, Ok, Result


def killer(
    tree: Path, node: str, host: HostContext
) -> Result[Output, build.BuildError]:
    """Compile the scratch sources and select exactly the declared pure Tasty case."""
    tools = build.recorded_tools(host)
    if isinstance(tools, Err):
        return tools
    context = build.BuildContext(
        tree / "src/agentctl/haskell",
        tree.parent / "haskell-mutants",
        host,
        tools.value,
        ("-O0",),
    )
    compiled = compile_all(context)
    if isinstance(compiled, Err):
        return compiled
    with tempfile.TemporaryDirectory(
        prefix="tasty-mutant-", dir=tree.parent
    ) as temporary:
        return selected_case(context, node, Path(temporary) / "tasty.xml")


def selected_case(
    context: build.BuildContext, node: str, path: Path
) -> Result[Output, build.BuildError]:
    """Normalise only actual selected-case XML failures for the named-reason check."""
    pattern = node.removeprefix("haskell:").replace("/", ".")
    arguments = ("--pattern", pattern)
    listing = build.execute_binary(
        context,
        build.BinaryCall("test:agentctl-core-test", (*arguments, "--list-tests")),
    )
    if isinstance(listing, Err):
        return listing
    selected = listed(listing.value.stdout)
    if isinstance(selected, Err) or selected.value != frozenset({node}):
        return Err(build.BuildError("Haskell killer does not select exactly its case"))
    output = build.execute_binary(
        context,
        build.BinaryCall(
            "test:agentctl-core-test", arguments, settings=(("TASTY_XML", str(path)),)
        ),
    )
    if isinstance(output, Err):
        return output
    return case_outcomes(path, node, output.value.code)


def case_outcomes(path: Path, node: str, code: int) -> Result[Output, build.BuildError]:
    """Read only actual XML outcomes, preserving the process's real exit status."""
    try:
        results = report(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError) as exc:
        return Err(build.BuildError(f"Cannot read mutant Tasty report: {exc}"))
    if isinstance(results, Err):
        return results
    if frozenset(name for name, _reason in results.value) != frozenset({node}):
        return Err(build.BuildError("Haskell killer report differs from its selection"))
    reasons = "\n".join(
        "E " + line
        for _name, reason in results.value
        if reason is not None
        for line in reason.splitlines()
    )
    return Ok(Output(code, reasons, ""))
