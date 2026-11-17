# Copyright (c) 2026 agentctl contributors.
"""Actual private multiplexer panes supply native PTYs to public application callers."""

import sys
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from tests.harness.launch import NativePane, PaneProgram, native_pane
from tests.harness.nonce import fresh
from tests.harness.passthrough import WarmCaller
from tests.harness.tmux import private_mux

CALL = """import os, sys
os.environ.pop('TMUX', None)
os.environ.pop('TMUX_PANE', None)
from agentctl.cli import main
main(sys.argv[1:])
"""
AUDITED_CALL = """import os, sys
from pathlib import Path
os.environ.pop('TMUX', None)
os.environ.pop('TMUX_PANE', None)
from agentctl.check.audit import install
from agentctl.result import Ok
assert install(Path(sys.argv[1]), sys.argv[2]) == Ok(None)
from agentctl.cli import main
main(sys.argv[3:])
"""
ATTACH = """import os, sys
os.environ.pop('TMUX', None)
os.environ.pop('TMUX_PANE', None)
from agentctl.process import foreground
from agentctl.result import Ok
from pathlib import Path
result = foreground(sys.argv[1:], cwd=Path.cwd(), env=os.environ)
assert isinstance(result, Ok), result
raise SystemExit(result.value)
"""
SWITCH = """import sys, time
from pathlib import Path
while not Path(sys.argv[1]).exists():
    time.sleep(0.01)
from agentctl.cli import main
main(sys.argv[2:])
"""


@contextmanager
def terminal(
    caller: WarmCaller,
    arguments: tuple[str, ...],
    *,
    audit: tuple[Path, str] | None = None,
) -> Generator[NativePane]:
    """Run the real public CLI inside a second private server's native terminal."""
    mux = caller.case.mux
    with private_mux(
        mux.context, mux.family, mux.run_directory, fresh(mux.nonce)
    ) as outer:
        program = CALL if audit is None else AUDITED_CALL
        tail = arguments if audit is None else (str(audit[0]), audit[1], *arguments)
        driver = native_pane(
            outer,
            "public-caller",
            PaneProgram(
                (sys.executable, "-c", program, *tail),
                caller.case.folder,
                caller.case.environment,
            ),
            binary=caller.executable,
        )
        try:
            yield driver
        finally:
            caller.case.records()


@contextmanager
def attached_seed(
    caller: WarmCaller, arguments: tuple[str, ...] | None = None
) -> Generator[tuple[NativePane, NativePane]]:
    """Attach one native client to a waiting in-server caller before releasing it."""
    mux = caller.case.mux
    release = caller.case.folder / "launch"
    seed = native_pane(
        mux,
        "seed",
        PaneProgram(
            (
                sys.executable,
                "-c",
                SWITCH,
                str(release),
                *((caller.case.agent,) if arguments is None else arguments),
            ),
            caller.case.folder,
            caller.case.environment,
        ),
        binary=caller.executable,
    )
    prefix = () if mux.family == "Windows" else ("-S", str(mux.endpoint))
    with private_mux(
        mux.context, mux.family, mux.run_directory, fresh(mux.nonce)
    ) as outer:
        driver = native_pane(
            outer,
            "outside-client",
            PaneProgram(
                (
                    sys.executable,
                    "-c",
                    ATTACH,
                    mux.executable,
                    *prefix,
                    "attach-session",
                    "-t",
                    "=seed",
                ),
                caller.case.folder,
                caller.case.environment,
            ),
            binary=caller.executable,
        )
        try:
            yield seed, driver
        finally:
            caller.case.records()
