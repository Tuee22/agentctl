# Copyright (c) 2026 agentctl contributors.
"""The sole Python process creation boundary."""

import os
import subprocess
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from agentctl.foundation import Err, Family, Ok, Result
from agentctl.foundation_process_identity import (
    alive,
    linux_birth,
    native_process_image,
    process_birth,
    registered_alive,
    windows_birth,
)
from agentctl.foundation_process_values import ByteOutput, Output, SpawnError

__all__ = [
    "ByteOutput",
    "Child",
    "ObservationRequest",
    "Output",
    "SpawnError",
    "alive",
    "finish",
    "foreground",
    "linux_birth",
    "process_birth",
    "registered_alive",
    "replace",
    "run",
    "run_bytes",
    "run_observed",
    "start",
    "start_protocol",
    "stop",
    "windows_birth",
]


@dataclass(frozen=True, slots=True)
class Child:
    """An owned background process whose handle remains with its creator."""

    handle: subprocess.Popen[bytes]

    @property
    def pid(self) -> int:
        """Expose the operating-system pid observed after process creation."""
        return self.handle.pid


@dataclass(frozen=True, slots=True)
class ObservationRequest:
    """Native family and release input for one observed process."""

    family: Family
    input_text: str
    timeout: float = 600


def run(
    argv: list[str],
    *,
    cwd: Path,
    env: Mapping[str, str],
    timeout: float = 600,
    input_text: str | None = None,
) -> Result[Output, SpawnError]:
    """Run an argv without a shell, decoding both streams as UTF-8."""
    try:
        child = subprocess.run(
            argv,
            cwd=cwd,
            env=env,
            timeout=timeout,
            check=False,
            capture_output=True,
            text=False,
            input=None if input_text is None else input_text.encode("utf-8"),
        )
        return Ok(_decoded(child.returncode, child.stdout, child.stderr))
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        return Err(SpawnError(str(exc)))


def run_bytes(
    argv: list[str], *, cwd: Path, env: Mapping[str, str], timeout: float = 600
) -> Result[ByteOutput, SpawnError]:
    """Run without a shell and retain bytes for an explicitly decoded protocol."""
    try:
        child = subprocess.run(
            argv, cwd=cwd, env=env, timeout=timeout, check=False, capture_output=True
        )
        return Ok(ByteOutput(child.returncode, child.stdout, child.stderr))
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        return Err(SpawnError(str(exc)))


def start(
    argv: list[str], *, cwd: Path, env: Mapping[str, str]
) -> Result[Child, SpawnError]:
    """Start an owned observer process for explicit teardown by its caller."""
    try:
        handle = subprocess.Popen(
            argv,
            cwd=cwd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=False,
        )
    except (OSError, ValueError) as exc:
        return Err(SpawnError(str(exc)))
    return Ok(Child(handle))


def start_protocol(
    argv: list[str], *, cwd: Path, env: Mapping[str, str]
) -> Result[Child, SpawnError]:
    """Start an owned child with its input held until an explicit exchange."""
    try:
        handle = subprocess.Popen(
            argv,
            cwd=cwd,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=False,
        )
    except (OSError, ValueError) as exc:
        return Err(SpawnError(str(exc)))
    return Ok(Child(handle))


def stop(child: Child) -> Result[Output, SpawnError]:
    """Kill a running owned child and reap it, bounding both waits.

    Force termination prevents uncooperative observers from retaining private
    processes and streams. Completed children retain their status and output.
    """
    try:
        if child.handle.poll() is None:
            child.handle.kill()
        stdout, stderr = child.handle.communicate(timeout=5)
        code = child.handle.wait(timeout=5)
        return Ok(_decoded(code, stdout, stderr))
    except (OSError, subprocess.TimeoutExpired, UnicodeError) as exc:
        return Err(SpawnError(str(exc)))


def replace(argv: list[str], *, env: Mapping[str, str]) -> Result[int, SpawnError]:
    """Replace this process with inherited terminal handles and literal arguments."""
    try:
        os.execve(argv[0], argv, dict(env))
    except (OSError, ValueError, IndexError) as exc:
        return Err(SpawnError(str(exc)))


def foreground(
    argv: list[str], *, cwd: Path, env: Mapping[str, str]
) -> Result[int, SpawnError]:
    """Inherit the terminal and wait while the child handles console interrupts."""
    try:
        with (
            subprocess.Popen(argv, cwd=cwd, env=env) as child,
            ThreadPoolExecutor(max_workers=1) as waiter,
        ):
            status = waiter.submit(child.wait)
            while True:
                try:
                    return Ok(status.result())
                except KeyboardInterrupt:
                    continue
    except (OSError, ValueError) as exc:
        return Err(SpawnError(str(exc)))


def finish(
    child: Child, *, timeout: float = 600, input_text: str | None = None
) -> Result[Output, SpawnError]:
    """Wait for an owned child and decode drained bytes without terminating it."""
    if input_text is not None and (
        child.handle.stdin is None or child.handle.stdin.closed
    ):
        return Err(SpawnError("child input is unavailable"))
    try:
        stdout, stderr = child.handle.communicate(
            input=None if input_text is None else input_text.encode("utf-8"),
            timeout=timeout,
        )
        code = child.handle.wait(timeout=timeout)
        return Ok(_decoded(code, stdout, stderr))
    except (OSError, subprocess.TimeoutExpired, UnicodeError, ValueError) as exc:
        return Err(SpawnError(str(exc)))


def run_observed(
    argv: list[str],
    *,
    cwd: Path,
    env: Mapping[str, str],
    request: ObservationRequest,
) -> Result[Output, SpawnError]:
    """Observe an owned child before releasing its explicit input protocol."""
    if not request.input_text:
        return Err(SpawnError("observed child requires explicit input"))
    started = start_protocol(argv, cwd=cwd, env=env)
    if isinstance(started, Err):
        return started
    child = started.value
    observed = native_process_image(request.family, child.pid)
    completed = finish(child, timeout=request.timeout, input_text=request.input_text)
    if isinstance(completed, Ok):
        return Ok(
            Output(
                completed.value.code,
                completed.value.stdout,
                completed.value.stderr,
                observed,
            )
        )
    cleaned = stop(child)
    if isinstance(cleaned, Err):
        return Err(
            SpawnError(completed.error.message + "; cleanup: " + cleaned.error.message)
        )
    return Ok(
        Output(
            1,
            cleaned.value.stdout,
            cleaned.value.stderr
            + "\nprocess failure: "
            + completed.error.message
            + "\n",
            observed,
        )
    )


def _decoded(code: int, stdout: bytes, stderr: bytes) -> Output:
    """Decode after pipe draining so invalid bytes fail on the caller's thread."""
    output = stdout.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
    errors = stderr.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
    return Output(code, output, errors)
