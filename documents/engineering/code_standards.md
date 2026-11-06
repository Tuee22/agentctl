# Code Standards

**Status**: Authoritative source
**Supersedes**: N/A
**Owning phase**: [Haskell package, quality legs and digest-keyed build](../../DEVELOPMENT_PLAN/phase-3-haskell-package-and-build.md)

> **Purpose**: State the rules every Python and Haskell module of agentctl follows, why each exists, and which leg or check holds it.

These rules carry over the concept note's engineering rules (strict typing, functional style and result types;
[the concept-note disposition](../../DEVELOPMENT_PLAN/rationale.md#concept-note-disposition), rows CN-14 and
CN-32 to CN-39) wherever they fit a permanent pipx application, and drop `uv`, which R1 excludes as a host
dependency. The legs of [the quality gate](quality_gate.md#the-eight-legs) and the `src.*` checks hold the
mechanical part. Agents apply authoring rules that name no mechanism; human review is optional and never a
gate-closure condition. Tests follow the same rules as the package, and ruff and ty run over both.

## Python

**Types.**

- Every function, parameter, return value and callback is annotated (ruff's `ANN` rules under
  `select = ["ALL"]`), and ty checks with every rule an error, untyped decorators included.
- No `Any`, `typing.cast` or `typing.no_type_check`: ruff's banned-api rejects the imports, and
  `src.suppression-ban` rejects the names wherever an alias could carry them
  (`tests/governance/test_source_guards.py::test_suppression_ban_fixtures`).
- Native API coverage exceptions match the complete definition line, path and physical line number. The fixed
  entries are `src/agentctl/check/preconditions.py:127` for kernel advisory locking, `src/agentctl/process.py:125`
  for the POSIX liveness syscall, and `src/agentctl/process.py:136` for Win32 query handles. Each API requires its
  native kernel. A moved line, altered text or another path loses the exception
  (`tests/governance/test_source_guards.py::test_coverage_exception_scope`). Native hosts exercise real lock
  contention and owned live/reaped processes (`tests/integration/test_runtime_boundaries.py::test_single_run_lock_releases`,
  `tests/integration/test_guard.py::test_containment_detects_owned_leak`). Windows confirmation belongs to
  [Windows and psmux acceptance](../../DEVELOPMENT_PLAN/phase-14-windows-psmux-acceptance.md).
- No ignore comment of any kind: `# type: ignore`, `# ty: ignore`, `# noqa` and `# ruff: noqa` are banned by
  `src.suppression-ban`, and `# pragma: no cover` stands only at a line its allowlist names
  (`tests/governance/test_source_guards.py::test_suppression_ban_fixtures`).
- Closed vocabularies are `enum.Enum` members or `Literal` unions, records are frozen dataclasses, and choices are
  unions of record types. `dict[str, object]` never appears in core logic, and `TypedDict` only at a parsing
  boundary.
- No custom `.pyi` stub exists unless a dependency ships without types; click 8.5.0 ships its own. A stub that
  does exist is narrow, pinned to its dependency's version, and tested.
- No `from __future__ import annotations` and no `if TYPE_CHECKING:` block. The body of such a block never runs,
  so full branch coverage would need the exclusion that `pragma: no cover` bans; an import used only in
  annotations is an ordinary import.
- click's `Context.obj` is typed `Any`, so values travel as explicit parameters; `CliRunner.isolated_filesystem`
  is deprecated in click 8.5, and `filterwarnings = ["error"]` turns its warning into an error, so tests use
  `tmp_path`.

**Results, not expected exceptions.**

- `src/agentctl/result.py` defines `Ok` and `Err` as frozen, slotted generic dataclasses in Python 3.12
  type-parameter syntax, and `Result` as their union. Each module declares its own union of error records, and a
  function whose failure is anticipated (a missing tool, a declined consent, a digest mismatch, a build error)
  returns `Err` of one of them.
- Only an I/O adapter catches an exception, only a narrow standard-library one such as `OSError`,
  `subprocess.TimeoutExpired` or `urllib.error.URLError`, and it translates it to a typed error where it arises.
  An unexpected defect propagates as a traceback; nothing swallows it, and no retry loop is driven by
  exceptions.
- `main(argv)` in `src/agentctl/cli.py` turns a `Result` into the exit code and the message the user sees.
- A `match` over a closed union names every member and has no wildcard case, so a new member is a type error at
  every match instead of a silent fallthrough; the pinned-config co-design confirms that ty reports the gap.

**Values and purity.**

- Functions map immutable values to immutable values: `@dataclass(frozen=True, slots=True)`, tuples and
  frozensets. No mutable global, mutable default or in-place update of a domain value exists.
- Expressions, comprehensions, pattern matching and small functions are preferred to imperative mutation, without
  forcing every branch into an expression where a plain statement is clearer.
- Decisions are pure: the provisioning plan, the leg table and verdict, the digest rule, the lane predicates and
  `paths.py` over OS family, environment and home take values and return values, so their tests are `value`
  evidence on every host.
- Platform choices are functions of the OS value `hostfacts.py` gathers once. No other module branches on
  `sys.platform` or `os.name`, so every platform's branch runs, is covered and is type-checked on every host.

**Spawns only in `process.py`, and other effects at the edge.**

- Every spawn and exec goes through `src/agentctl/process.py`, the only module that imports `subprocess` or calls
  an `os.exec*`, `os.spawn*`, `os.posix_spawn` or `os.system` function (`src.one-process-module`), and the only one
  where ruff allows S603 and S606.
- An argv is always a list. Nothing runs a shell or builds a command string, so no user text is ever re-parsed.
- Filesystem writes, the urllib download and the handoff live in thin adapters. A file agentctl owns is written
  to a temporary file in the same directory and renamed into place, so an interrupted install or build leaves
  the old file or nothing, and private files are created with their final mode (0600, in a 0700 directory).
- agentctl unpacks no archive and reads no project configuration, and its only network request is the pinned
  ghcup URL; cabal and ghcup reach Hackage and downloads.haskell.org as spawned tools. No secret goes on an argv
  or into a log.

**Typed parsing at boundaries.** Everything from outside, whether TOML (the pins, the oracles), JSON
(`direct_url.json`, `agentctl-core-eval` output), process output, `/etc/os-release`, environment variables or
downloaded bytes, is parsed into a domain value where it arrives or turned there into a typed error, so core logic
never handles an unparsed `str`, `bytes` or `dict`. Process output is decoded as UTF-8 explicitly, never through
the locale. TOML and JSON use only the standard library's `tomllib` and `json`; host discovery uses the standard
library's `shlex` for the shell-quoted `ID` and `VERSION_ID` fields of `os-release`.

**Tests.** `unittest.mock` is banned, and `monkeypatch` serves only `setenv`, `delenv` and `chdir`; effects are
observed through the spawn audit and the fake agent ([testing](testing.md#observers-and-nonces)).

The check lock loads the standard-library OS extension through a runtime-checked protocol. This keeps the Windows and POSIX interfaces typed without importing an unavailable extension on the other OS; the adapter holds the operating-system lock until its scope exits.

The run-integrity adapter reads raw symlink text, and its PTH115 exception is scoped to that module and tested against the same source at a different path (`tests/integration/test_static_legs.py::test_raw_link_rule_exception_is_narrow`). Native Windows liveness uses query-only process handles; the POSIX signal-zero probe is never selected for Windows.

## Haskell

**The warnings stanza.** Every component of `agentctl-core.cabal` (the library, the three executables and the
test suite) imports one common stanza, so the application's build refuses exactly what the gate's `cabal-build` leg
refuses (`tests/integration/test_haskell_legs.py::test_werror_fires`):

```text
common warnings
  ghc-options: -Wall -Wcompat -Werror -Wpartial-fields -Wincomplete-uni-patterns
               -Wincomplete-record-updates -Wredundant-constraints -Wunused-packages
```

- `-Wpartial-fields` is there because a record selector on a multi-constructor type throws at the call site
  instead of being a compile error; fields of a sum type are matched positionally.
- No `{-# OPTIONS_GHC -Wno-... #-}` pragma (`src.suppression-ban`), and no `-Wwarn` or `-w` anywhere: a warning
  is fixed, never silenced. `tests/integration/test_haskell_legs.py::test_werror_fires` builds a temp copy with an
  unused binding and requires the build leg to fail.
- No Haskell CPP: the handshake needs none, because it carries no digest, and a module whose meaning depends on CPP is
  one the style legs cannot read as written.
- No package the build compiles from Hackage uses `build-type: Configure`, because Windows provisioning installs
  no MSYS2; that this holds on a real Windows host is confirmed by
  [Windows and psmux acceptance](../../DEVELOPMENT_PLAN/phase-14-windows-psmux-acceptance.md).
- Dependencies are few and resolved at the pinned `index-state`, starting from the concept note's candidates
  (`optparse-applicative`, `process`, `directory`, `filepath`, `time`, `async`, `stm`, `tasty`); no TOML parser
  is needed, because agentctl reads no configuration file. `-Wunused-packages` removes any that a component stops
  using.

**Style.** `fourmolu.yaml` and `.hlint.yaml` live in `src/agentctl/haskell/`. `fourmolu.yaml` writes out
every setting, so a formatter upgrade changes no style; `.hlint.yaml` keeps hlint's default hints and has no
`ignore` entry. No `HLINT ignore` annotation appears in a source (`src.suppression-ban`), and no region turns the
formatter off. The pinned fourmolu and hlint run from `cache/tools/<pin-digest>`, never from PATH.

Fourmolu is pinned to 0.19.0.1 and HLint to 3.10, with `ghc-lib-parser ==9.12.3.20251228` shared by their builds.
The complete root `fourmolu.yaml` states every setting; the root `.hlint.yaml` is the empty list `[]`, preserving
the built-in hint set. Missing or duplicated settings and nested configurations fail before a style tool runs
(`tests/governance/test_style_config.py::test_style_configs_have_no_ignores`).

**Opaque types for capabilities.** The module that establishes a condition exports its type but not its
constructor, so holding a value proves the check ran.

- `Ready` belongs to `AgentCtl.Preflight`, and `AgentCtl.Launch` creates a session only from a `Ready`, so a launch
  path that skips preflight does not compile. A compile-fail fixture matched by its GHC diagnostic code, beside a
  twin that compiles, keeps the constructor private
  (`tests/integration/test_ready_opaque.py::test_ready_constructor_is_not_exported`;
  [launch contract](../architecture/launch_contract.md#preflight)).
- `SessionName` comes only from the smart constructor in `AgentCtl.Session.Name`, so an unvalidated name cannot
  reach a multiplexer command. A compiling checked-name caller and an external constructor caller rejected with
  the pinned compiler's `GHC-01928` diagnostic protect the private export
  (`tests/integration/test_mux_resolution.py::test_session_name_constructor_is_private`).
- A forbidden action is unrepresentable: the typed multiplexer vocabulary has no `kill-server`, respawn or
  shell-string command ([multiplexer adapter](../architecture/multiplexer_adapter.md)), and no type constructs a
  login command or login keystrokes (`src.no-login-construction`).

**Typed errors and total functions.** States, screen classes, commands and failures are closed sum types, and
each module exports the error type of its own failures. Every match handles every constructor (`-Wall` reports
incomplete patterns, and `-Wincomplete-uni-patterns` extends that to lambdas and pattern bindings). The library
calls no `error`, no `undefined` and no partial function such as `head`, `fromJust` or `read`. An IO exception is
caught at the runner or the file edge and turned into a typed error, and one function maps the error type to the
exit code.

**Pure kernels, effects at the edge.**

- `AgentCtl.Process` is the one runner: pure modules build typed commands as values, and it interprets them,
  performing every spawn and exec in the binary. It is the only importer of `System.Process`
  (`src.one-process-module`).
- The kernels (argv assembly, session names, auth classification, the preflight decision, screen classification,
  fingerprints, the recovery transitions and backoff) take values and return values. They are what
  `agentctl-core-eval` exposes as `value` evidence. Mutation checks also exercise bounded effects against private
  native backends and controlled observers; no mutant uses a live-agent test as its killer.
- Process output is decoded as UTF-8 explicitly, and no module computes a per-user directory: `AgentCtl.Paths`
  receives them from the handoff.

The bounded native process runner receives an absolute executable, literal argv, working directory, environment and deadline.
It drains stdout and stderr concurrently as binary streams, then decodes UTF-8 and preserves the exit status.
Its input handle is an explicitly opened null device. This supplies no input and keeps native pipe allocation
valid when the caller has already closed stdin, as the command fixture does before invoking the runner
(`tests/integration/test_mux_real.py::test_private_server_roundtrip`,
`haskell:agentctl-core-test/ProcessReal/closed-parent-input`).
Relative executables, invalid deadlines and spawn errors are typed failures. Text commands also refuse invalid
UTF-8. The status-only operation shares the same process lifecycle and drains raw bytes without decoding them;
auth classification consumes only its actual exit code
(`haskell:agentctl-core-test/ProcessReal/status-only-ignores-bytes`). The invocation has no
`Show` instance because it contains environment values
(`haskell:agentctl-core-test/ProcessReal/utf8-argv-environment-and-status`,
`haskell:agentctl-core-test/ProcessReal/line-endings-preserved`,
`haskell:agentctl-core-test/ProcessReal/missing-and-relative-executables`,
`haskell:agentctl-core-test/ProcessReal/invalid-utf8-is-refused`,
`haskell:agentctl-core-test/ProcessReal/timeout-cleans-up`).

The controlled text fixture sets UTF-8 and disables newline translation explicitly. A separate binary fixture emits
mixed LF and CRLF bytes on both streams, which the runner preserves before decoding; newline normalisation belongs
to pane observation (`haskell:agentctl-core-test/ProcessReal/line-endings-preserved`).

Executable components link with `-threaded` so a native process wait permits timeout delivery. The deadline control
also closes both child output streams before sleeping and checks monotonic elapsed time, exercising the wait after
pipe draining (`haskell:agentctl-core-test/ProcessReal/timeout-after-streams-close`).

The small native C ABI supplies filesystem observations, owned file locks, stop handlers and private-directory creation unavailable through one
unconditional Haskell API on all hosts. It refuses a foreign, linked or overly permissive existing directory.
Haskell modules and Cabal components remain unconditional; C selects POSIX or Win32 bindings and compiles with
`-std=c11 -Wall -Wextra -Werror`. The snapshot reports actual owner, kind and permissions with the file's bytes;
Windows uses owner-SID and DACL queries rather than emulated POSIX ownership. The Haskell policy consumes these
facts, and native controls exercise private files, missing files and the snapshot size bound
(`haskell:agentctl-core-test/SpecReal/snapshot-is-owned-and-private`,
`haskell:agentctl-core-test/SpecReal/missing-spec-is-refused`,
`haskell:agentctl-core-test/SpecReal/oversized-spec-is-refused`).

Darwin filesystem sources and their native state fixture enable `_DARWIN_C_SOURCE` before system headers alongside
`_POSIX_C_SOURCE`, exposing the SDK's no-follow open flags and advisory file locks under the strict C compilation mode.

The supervisor and watch lock files are retained and written in place while their native handle holds exclusion.
Their inode must not be replaced by the temporary-file publication used for ordinary data files. Native stop
handlers only set a flag; cleanup and multiplexer effects stay in the foreground loop. Scoped adapters release
locks and restore prior handlers on both normal and exceptional exit.

The source walk includes C and headers. Only `native_process.c` may call execve or its wide Windows counterpart;
native shell and other spawn APIs are forbidden. Only AgentCtl.Process owns the Haskell import of that exec
binding. Native warning suppressions and test-control environment branches fail the same source guards
(`tests/governance/test_source_guards.py::test_native_process_boundary`,
`tests/governance/test_source_guards.py::test_native_controls_and_walk`).

`AgentCtl.Process.requestReap` is the sole owner of the native SIGCHLD notification. Its public input is a checked
multiplexer and command context, never an arbitrary pid; it validates the backend's live pid response before the
native call. Native signal-name translation uses the host's actual signal constants rather than a cross-platform
numeric table.

Environment-bearing spec values have equality and JSON codecs with no Show instance. Their round-trip control
preserves arbitrary environment values and literal argument elements
(`haskell:agentctl-core-test/PaneExec/spec-round-trip`). The pane environment keeps only TERM, TMUX and TMUX_PANE
from the pane and takes other variables from the spec (`haskell:agentctl-core-test/PaneExec/pane-environment`).

`AgentCtl.Process` also owns inherited-stream foreground programs and the native exec binding. Foreground agents
and terminal clients run for their process lifetime; bounded command queries retain explicit deadlines. The POSIX
trampoline replaces itself with the program, while Windows waits for its child and atomically publishes status.
Program validation refuses relative paths, embedded NULs and invalid environment names before the spec is consumed
(`tests/integration/test_pane_exec.py::test_spec_deleted_and_status_propagated`,
`tests/integration/test_pane_exec.py::test_malformed_spec_preserved`).

The Python handoff flushes both streams before transport. Its inherited-stream child waits on a worker thread
so console interrupts in the main thread cannot discard the native child status; the main thread waits for that
recorded result. Native controls require exit 3 after an actual parent interrupt and a typed refusal on a broken
output pipe (`tests/integration/test_handoff.py::test_child_wait_survives_parent_console_interrupt`,
`tests/integration/test_handoff.py::test_flush_failure_prevents_handoff`).

The filesystem edge distinguishes strict privacy validation from application state preparation. The strict
`ensurePrivateDirectory` operation continues to refuse overpermissive existing directories. State preparation
first verifies an owned ordinary directory without following a final link, then tightens that root to private
access. POSIX uses its opened descriptor; Windows uses a protected owner-only DACL and an exclusive root handle,
preventing inheritance changes to existing children. The native control starts with deliberately broad directory
access, proves strict refusal and private preparation, and compares an existing child's bytes and file permissions
before and after (`haskell:agentctl-core-test/SpecReal/state-directory-preparation`).

The recovery machine is a pure, total decision kernel over a closed mode and action vocabulary. Its only send
path requires a matching unhandled overload and a reached deadline; effects remain in the supervisor interpreter.
Generated sequences cover unsafe screens and require successful safe sends as their positive control
(`haskell:agentctl-core-test/Machine/never-send-unsafe`).

## WRONG and RIGHT

| WRONG | RIGHT | Why the WRONG one is wrong |
|---|---|---|
| `except Exception: return None` around the ghcup download | catch `urllib.error.URLError` and `OSError` in `ghcup.py` and return `Err` of a download error | the broad catch turns a programming defect into "no ghcup", and `None` tells the caller nothing it can print |
| `subprocess.run(argv)` in `bootstrap/build.py` | `build.py` passes the argv to `process.py` | a second spawner is a path the spawn audit's single module does not cover, and `src.one-process-module` rejects it (`tests/governance/test_source_guards.py::test_subprocess_import_outside_process_module`) |
| `if sys.platform == "win32":` inside the handoff | the handoff branches on the OS value from `hostfacts.py` | the Windows branch never runs on Linux, so coverage cannot reach it and ty narrows it away |
| `module AgentCtl.Preflight (Ready (..), preflight) where` | `module AgentCtl.Preflight (Ready, preflight) where` | exporting the constructor lets any module build a `Ready` and launch without preflight |
| `{-# OPTIONS_GHC -Wno-incomplete-patterns #-}` above a classifier | a match that handles every constructor | the pragma silences the gate for one module, so an unhandled screen class becomes a runtime crash |

## Related

- [quality_gate.md](quality_gate.md#tool-configuration) — the pinned ruff, ty, pytest and coverage configuration behind these rules.
- [testing.md](testing.md) — why mocks and test-only branches never count as evidence.
- [binary_build.md](binary_build.md) — the Cabal project that carries the warnings stanza and style files.
- [python_haskell_boundary.md](../architecture/python_haskell_boundary.md) — the single owners these rules protect.
- [system-components.md](../../DEVELOPMENT_PLAN/system-components.md#haskell-package) — every module these rules apply to.
- [rationale.md](../../DEVELOPMENT_PLAN/rationale.md#concept-note-disposition) — where the concept note's engineering rules went.
- [Haskell package, quality legs and digest-keyed build](../../DEVELOPMENT_PLAN/phase-3-haskell-package-and-build.md) — the phase that builds the warnings stanza and the style legs.
