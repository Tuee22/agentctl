# Copyright (c) 2026 agentctl contributors.
"""The application's one Cabal build path with a private configuration and store."""

import os
import re
import tempfile
from dataclasses import dataclass, replace
from pathlib import Path

from agentctl.bootstrap import style
from agentctl.bootstrap.pins import Pins
from agentctl.bootstrap.toolchain import Toolchain
from agentctl.check.preconditions import exclusive_file
from agentctl.hostfacts import HostContext, read_record
from agentctl.process import Child, Output, run, start
from agentctl.result import Err, Ok, Result

BUILD_ENVIRONMENT = frozenset(
    {
        "PATH",
        "HOME",
        "USER",
        "SYSTEMROOT",
        "USERPROFILE",
        "APPDATA",
        "LOCALAPPDATA",
        "PATHEXT",
        "COMSPEC",
        "TMPDIR",
        "TMP",
        "TEMP",
        "PYTHONPYCACHEPREFIX",
    }
)


@dataclass(frozen=True, slots=True)
class BuildError:
    """A refused or failed native build, with the external diagnostic preserved."""

    message: str


@dataclass(frozen=True, slots=True)
class BuildContext:
    """Explicit bundled sources, outside-tree outputs and the verified toolchain."""

    project: Path
    directory: Path
    host: HostContext
    tools: Toolchain
    options: tuple[str, ...] = ()

    @property
    def cabal_directory(self) -> Path:
        """Keep Cabal configuration, downloads and store inside agentctl's cache."""
        return self.host.cache / "cabal"


def bundled_project() -> Path:
    """Find ordinary package data under both editable and wheel installations."""
    return Path(__file__).resolve().parents[1] / "haskell"


def recorded_tools(host: HostContext) -> Result[Toolchain, BuildError]:
    """Require both recorded absolute paths after the native provisioning step."""
    recorded = read_record(host.cache)
    if isinstance(recorded, Err):
        return Err(BuildError(recorded.error.message))
    ghc, cabal = recorded.value
    if ghc is None or cabal is None:
        return Err(BuildError("Missing ensured native toolchain record"))
    return Ok(Toolchain(ghc, cabal))


def environment(context: BuildContext) -> dict[str, str]:
    """Discard inherited Cabal/GHC controls and select only the owned Cabal home."""
    return {
        **{
            key: value
            for key, value in context.host.environment
            if key in BUILD_ENVIRONMENT
        },
        "CABAL_DIR": str(context.cabal_directory),
        "LC_ALL": "C.UTF-8",
        "GHC_ENVIRONMENT": "-",
    }


def invoke(
    context: BuildContext,
    arguments: tuple[str, ...],
    *,
    settings: tuple[tuple[str, str], ...] = (),
) -> Result[Output, BuildError]:
    """Run the verified absolute cabal through the sole process boundary."""
    result = run(
        [context.tools.cabal, *arguments],
        cwd=context.project,
        env={**environment(context), **dict(settings)},
        timeout=1800,
    )
    if isinstance(result, Err):
        return Err(BuildError(result.error.message))
    if result.value.code:
        return Err(
            BuildError(
                f"cabal {' '.join(arguments)} exited {result.value.code}:\n"
                + result.value.stdout
                + result.value.stderr
            )
        )
    return result


def index_state(project: Path) -> Result[str, BuildError]:
    """Require one explicit UTC index pin and reject unmodelled project sidecars."""
    try:
        if any(
            (project / name).exists()
            for name in ("cabal.project.local", "cabal.project.freeze")
        ):
            return Err(
                BuildError("Remove unmodelled Cabal project sidecars before building")
            )
        states = tuple(
            str(value)
            for value in re.findall(
                r"(?m)^index-state:\s*(\S+)\s*$",
                (project / "cabal.project").read_text(encoding="utf-8"),
            )
        )
    except (OSError, UnicodeError) as exc:
        return Err(BuildError(f"Cannot read the bundled Cabal project: {exc}"))
    if (
        len(states) != 1
        or re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", states[0]) is None
    ):
        return Err(
            BuildError("The bundled Cabal project requires one pinned UTC index-state")
        )
    return Ok(states[0])


def atomic_text(path: Path, text: str) -> None:
    """Publish a private cache record without a partially written final file."""
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".record-", dir=path.parent) as temporary:
        staged = Path(temporary) / "record"
        descriptor = os.open(staged, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(text)
        staged.replace(path)


def _refresh_index(context: BuildContext, state: str) -> Result[None, BuildError]:
    """Initialise the owned configuration and record only a successful index update."""
    cabal = context.cabal_directory
    cabal.mkdir(mode=0o700, parents=True, exist_ok=True)
    configuration = cabal / "config"
    index_context = replace(context, project=cabal)
    if not configuration.exists():
        initialized = invoke(index_context, ("user-config", "init"))
        if isinstance(initialized, Err):
            return initialized
        contents = configuration.read_text(encoding="utf-8")
        contents = contents.replace(
            "url: http://hackage.haskell.org/", "url: https://hackage.haskell.org/"
        )
        atomic_text(configuration, contents)
    updated = invoke(index_context, ("update",))
    if isinstance(updated, Err):
        return updated
    if not (cabal / "packages/hackage.haskell.org/01-index.tar").is_file():
        return Err(BuildError("cabal update did not produce its private package index"))
    atomic_text(cabal / "agentctl-index-state", state)
    return Ok(None)


def ensure_index(context: BuildContext) -> Result[None, BuildError]:
    """Update only an absent or differently pinned private package index."""
    state = index_state(context.project)
    if isinstance(state, Err):
        return state
    cabal = context.cabal_directory
    receipt = cabal / "agentctl-index-state"
    index = cabal / "packages/hackage.haskell.org/01-index.tar"
    try:
        if (
            receipt.is_file()
            and receipt.read_text(encoding="utf-8") == state.value
            and index.is_file()
        ):
            return Ok(None)
        return _refresh_index(context, state.value)
    except (OSError, UnicodeError) as exc:
        return Err(BuildError(f"Cannot prepare the private Cabal index: {exc}"))


def arguments(context: BuildContext, verb: str, target: str) -> tuple[str, ...]:
    """Share the exact tests-enabled build and lookup flags across every caller."""
    return (
        verb,
        target,
        "--enable-tests",
        "-w",
        context.tools.ghc,
        f"--builddir={context.directory}",
        *context.options,
    )


def compile_target(context: BuildContext, target: str) -> Result[Output, BuildError]:
    """Compile a selected component while its caller owns the build-directory lock."""
    indexed = ensure_index(context)
    if isinstance(indexed, Err):
        return indexed
    return invoke(context, arguments(context, "build", target))


def compile_project(
    context: BuildContext, *, lock_timeout: float = 1800
) -> Result[Output, BuildError]:
    """Lock the outside-tree build directory and compile every declared component."""
    try:
        with exclusive_file(
            context.directory / "build.lock", timeout=lock_timeout
        ) as locked:
            return (
                Err(BuildError(locked.error.message))
                if isinstance(locked, Err)
                else compile_target(context, "all")
            )
    except OSError as exc:
        return Err(BuildError(f"Cannot release build lock: {exc}"))


def binary(context: BuildContext, target: str) -> Result[Path, BuildError]:
    """Resolve a built executable through cabal, then verify its actual file."""
    result = invoke(context, arguments(context, "list-bin", target))
    if isinstance(result, Err):
        return result
    path = Path(result.value.stdout.rstrip("\r\n"))
    if not path.is_absolute() or not path.is_file():
        return Err(
            BuildError("cabal list-bin did not name a built absolute executable")
        )
    return Ok(path)


@dataclass(frozen=True, slots=True)
class BinaryCall:
    """Explicit input and handoff for one application-owned internal execution."""

    target: str
    arguments: tuple[str, ...] = ()
    input_text: str | None = None
    protocol: str | None = "1"
    settings: tuple[tuple[str, str], ...] = ()


def execute_binary(
    context: BuildContext,
    call: BinaryCall,
) -> Result[Output, BuildError]:
    """Exercise an internal executable only through the application's boundary."""
    located = binary(context, call.target)
    if isinstance(located, Err):
        return located
    result = run(
        [str(located.value), *call.arguments],
        cwd=context.project,
        env=call_environment(context, call),
        input_text=call.input_text,
    )
    return Err(BuildError(result.error.message)) if isinstance(result, Err) else result


def call_environment(context: BuildContext, call: BinaryCall) -> dict[str, str]:
    """Supply the same explicit handoff and settings to each internal execution."""
    return {
        **environment(context),
        **(
            {"AGENTCTL_PROTOCOL_VERSION": call.protocol}
            if call.protocol is not None
            else {}
        ),
        **dict(call.settings),
    }


def start_binary(
    context: BuildContext, call: BinaryCall, *, cwd: Path | None = None
) -> Result[Child, BuildError]:
    """Start an internal executable with an owned handle and no supplied input."""
    if call.input_text is not None:
        return Err(BuildError("Background binary calls cannot supply input"))
    located = binary(context, call.target)
    if isinstance(located, Err):
        return located
    result = start(
        [str(located.value), *call.arguments],
        cwd=context.project if cwd is None else cwd,
        env=call_environment(context, call),
    )
    return Err(BuildError(result.error.message)) if isinstance(result, Err) else result


def verify_style_tools(
    context: BuildContext, pins: Pins, directory: Path
) -> Result[style.StyleTools, BuildError]:
    """Require both actual executable files and their pinned native version answers."""
    tools = style.paths(directory, context.host.family)
    for path, version in ((tools.fourmolu, pins.fourmolu), (tools.hlint, pins.hlint)):
        if not path.is_absolute() or not path.is_file():
            return Err(BuildError(f"Missing pinned style tool: {path}"))
        result = run(
            [str(path), "--version"],
            cwd=context.project,
            env=environment(context),
            timeout=10,
        )
        if isinstance(result, Err):
            return Err(BuildError(result.error.message))
        if (
            result.value.code
            or re.search(
                r"(?<![0-9.])" + re.escape(version.text) + r"(?![0-9.])",
                result.value.stdout,
            )
            is None
        ):
            return Err(
                BuildError(
                    f"Style tool {path} does not answer pinned version {version.text}"
                )
            )
    return Ok(tools)


def publish_style_tools(
    context: BuildContext,
    pins: Pins,
    staged: Path,
    destination: Path,
    completion: Result[Output, BuildError],
) -> Result[style.StyleTools, BuildError]:
    """Verify a completed build before publishing the whole tool directory together."""
    if isinstance(completion, Err):
        return completion
    verified = verify_style_tools(context, pins, staged)
    if isinstance(verified, Err):
        return verified
    try:
        if destination.exists():
            return verify_style_tools(context, pins, destination)
        staged.rename(destination)
    except OSError as exc:
        return Err(BuildError(f"Cannot publish pinned style tools: {exc}"))
    return Ok(style.paths(destination, context.host.family))


def ensure_style_tools(
    context: BuildContext, pins: Pins
) -> Result[style.StyleTools, BuildError]:
    """Reuse answering pins or install once into an atomic, private cache directory."""
    destination = style.directory(context.host.cache, pins)
    if destination.exists():
        return verify_style_tools(context, pins, destination)
    state = index_state(context.project)
    if isinstance(state, Err):
        return state
    indexed = ensure_index(context)
    if isinstance(indexed, Err):
        return indexed
    return _build_style_tools(context, pins, destination, state.value)


def _build_style_tools(
    context: BuildContext, pins: Pins, destination: Path, state: str
) -> Result[style.StyleTools, BuildError]:
    """Keep the installer, verification and publication inside one staging lifetime."""
    try:
        destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix=".style-", dir=destination.parent
        ) as temporary:
            staged = Path(temporary) / "tools"
            staged.mkdir(mode=0o700)
            completion = invoke(
                replace(context, project=context.cabal_directory),
                style.install_arguments(
                    pins,
                    context.tools.ghc,
                    staged,
                    context.host.cache / "build" / ("style-" + style.digest(pins)),
                    state,
                ),
            )
            return publish_style_tools(context, pins, staged, destination, completion)
    except OSError as exc:
        return Err(BuildError(f"Cannot stage pinned style tools: {exc}"))
