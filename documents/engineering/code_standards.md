# Code Standards

**Status**: Authoritative source
**Supersedes**: N/A
**Owning phase**: [Python discipline and gate integrity](../../DEVELOPMENT_PLAN/phase-1-python-discipline-and-gate-integrity.md)

> **Purpose**: Define the required Python and Haskell source discipline, its rationale, and the evidence each named check supplies.

These rules carry over the concept note's engineering rules (strict typing, functional style and result types;
[the concept-note disposition](../../DEVELOPMENT_PLAN/rationale.md#concept-note-disposition), rows CN-14 and
CN-32 to CN-39) wherever they fit a permanent pipx application, and drop `uv`, which R1 excludes as a host
dependency. The legs of [the quality gate](quality_gate.md#the-eight-legs) and the `src.*` checks hold the
mechanical part. Agents apply authoring rules that name no mechanism; human review is optional and never a
gate-closure condition. Tests follow the same rules as the package, and ruff and ty run over both.

## Python

**Authoring doctrine and evidence.** Python is the bootstrap and command-transport layer described by
[the boundary contract](../architecture/python_haskell_boundary.md). Its decisions are total functions over
validated immutable values; its effects occur in explicit adapters. Failures carry typed reasons, values are
never mutated, names are assigned once, and closed choices are handled exhaustively. These requirements apply
to package code, tests and boundary declarations. They are agentctl's own source discipline and introduce no
additional runtime library or alternative checker command.

A named check establishes only the rule and cases its cited tests exercise. The remaining requirements are
mandatory authoring doctrine, not claims that the current source guards mechanically establish purity,
immutability or totality. Adding a mechanical rule requires accepting and refusing controls and an applicable
mutant in the existing gate. An implementation needing migration gains no exemption from a passing subset of
checks, and a documentation change supplies no source-conformance evidence.

**Pure core and effectful edge.**

- Each module has an explicit role: pure calculation or effectful adapter. The role follows its actual
  operations and dependencies. Relabelling calculation code as an adapter does not permit hidden mutable
  domain state. The import graph is acyclic, and a pure module imports no effectful module.
- Core computations take all inputs as values. Filesystem and process access, environment reads, working
  directory, clocks, randomness, parser execution, Click, logging and terminal output belong to adapters.
  `PurePath` can represent a path in calculations; a filesystem capability cannot stand in for a path value.
- A read-only interface or callback annotation alone proves neither purity nor stable ownership. Any native
  capability or callback used by core has an explicit effect-free implementation and lifetime contract.
  Adapters snapshot external state before passing ordinary values to calculations.
- Time, locale choices and random state arrive explicitly. A pure random algorithm returns its next immutable
  state along with its result. Decimal arithmetic, where used, takes an explicit context rather than reading
  ambient settings. Repeating a calculation with the same supported inputs preserves both inputs and result.

**Totality and finite inputs.**

- A core function returns its declared outcome for every input in its supported domain. The contract states
  size and depth bounds, native-operation assumptions and resource limits; an annotation alone supplies none
  of these guarantees. Expected failure is a value, and genuine absence has a separate representation.
- A core function has no `raise`, statement `for` or `while`, suspension, resource management or recursion
  driven by input depth. Use finite comprehensions, exhaustive matches and bounded folds. Internal lazy
  producers require a justified finite bound and an effect-free producer.
- Indexing, mapping lookup, numeric conversion, division, extrema, regular-expression groups and other
  partial operations require a sufficient validated domain, a total accessor, or an explicitly named
  failure outcome. A guard covers all relevant failures of the operation, including overflow and subtype
  behavior, rather than just its most familiar error.
- Public collection calculations consume finite immutable snapshots. Caller-owned iterators can mutate
  state, perform I/O, raise or fail to terminate; an `Iterable` annotation does not make them suitable inputs.
  An adapter materializes a bounded snapshot before calling core.

**Types.**

- Every function, parameter, return value and callback is annotated (ruff's `ANN` rules under
  `select = ["ALL"]`), and ty checks with every rule an error, untyped decorators included.
- No `Any`, `typing.cast` or `typing.no_type_check`: ruff's banned-api rejects the imports, and
  `src.suppression-ban` rejects the names wherever an alias could carry them
  (`tests/governance/test_source_guards.py::test_suppression_ban_fixtures`).
- No `object` annotation or top-type substitute hides unknown data. This applies inside aliases, generics,
  forward references and bounds as well as direct annotations. Literal values and annotation metadata retain
  their value meaning; a vocabulary member whose spelling is `object` is not a type annotation.
- No `isinstance`, `issubclass`, comparison of `type(...)`, or reflective narrowing through `getattr`,
  `hasattr`, `callable` or computed method lookup. Parse structural input with `match` at its declared boundary,
  then carry the validated type. Order overlapping patterns most-specific first: `bool` precedes `int`.
- Native API evidence names its actual kernel and complete owned subprocess/ABI subject. Linux controls do
  not establish Windows or Darwin syscalls. Native receipts are independent requirements of their own lanes,
  while portable planning and refusal controls execute on Linux.
- No source-level ignore, noqa, formatter-disable, type-ignore or coverage pragma supplies acceptance.
  Existing native exceptions are migration inputs in the deletion ledger, not doctrine exemptions. Native
  per-subject coverage and receipts preserve the required evidence without adding an unreachable-arm exclusion.
- Closed vocabularies are enum members, `Literal` unions or unions of records. Domain records are final,
  frozen, slotted, keyword-only dataclasses with recursively immutable fields. Behavior lives in module-level
  functions; ordinary mutable classes and concrete domain inheritance are excluded. Protocols describe
  capabilities, and exceptions belong to named edge failure contracts. Concrete first-party classes are final.
- A validated domain value is constructed only through its defining module's factory returning `Result`.
  Direct constructors, `NewType`, `TypeGuard`, `TypeIs` and record replacement cannot bypass its invariants.
  Replacement remains appropriate for ordinary frozen records without construction invariants.
- A project-owned `.pyi` declaration exists only where a native or third-party API lacks sufficiently precise
  types for its supported boundary. It describes actual runtime names, signatures, borrowing and return shapes,
  including native mutable parser trees. Its version and native conformance are tested. It never invents an
  immutable result or a nonexistent export to satisfy a type checker.
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
- `None` represents genuine optional absence, never a failed parse, failed lookup or validation error whose
  cause the caller needs. Collection composition preserves input order and failure reasons; it does not
  discard unsuccessful elements or introduce another competing outcome convention.
- Only an I/O adapter catches an exception, only a narrow standard-library one such as `OSError`,
  `subprocess.TimeoutExpired` or `urllib.error.URLError`, and it translates it to a typed error where it arises.
  An unexpected defect propagates as a traceback; nothing swallows it, and no retry loop is driven by
  exceptions.
- `main(argv)` in `src/agentctl/cli.py` turns a `Result` into the exit code and the message the user sees.
- A `match` over a closed union names every member without a success catch-all. A new variant must produce a
  diagnostic from the pinned type/source controls in every relevant return shape, rather than silently falling
  through. No type-checker capability is assumed without its accepting and refusing control.
  Open boundary parsers may use a rejecting wildcard, and a generic success-payload extractor may handle its
  declared open payload domain. Neither permits a success catch-all over a closed domain. Exhaustiveness
  evidence covers functions returning `None` as well as value-returning functions; an unreachable assertion
  does not authorize a coverage exclusion or other suppression.

**Values and purity.**

- Owned values, fields and returns are concrete recursively immutable values: tuples, frozensets, immutable
  scalars, enums and frozen records. An outer frozen record or tuple containing mutable data is insufficient.
  A live mapping proxy is a view, not an immutable snapshot. Generic payloads obey the same ownership contract.
- Read-only parameter interfaces can restrict the callee's operations but do not establish immutable backing
  storage, finiteness or stability through another alias. Native parser nodes, handles and framework objects
  are explicitly borrowed edge capabilities with bounded lifetimes, not owned application values. Mutable
  collection annotations belong only to honest native decoder contracts, not domain APIs.
- No first-party in-place container mutation, attribute mutation, `global`, `nonlocal`, shared mutable state,
  mutable default or hidden cache exists. This includes local accumulator containers, aliases to mutators,
  subscript assignment or deletion, descriptor writes and reflective mutation. Native I/O necessarily changes
  external state; that change remains confined to its named adapter and is not a mutable domain model.
- A local name is bound once per scope, across assignments, parameters, loop targets, captures, context-manager
  and exception binders, and assignment expressions. Branches return values rather than rebind an accumulator.
  A comprehension's fresh iteration binding is distinct from assigning a previously bound name. `_` is a
  discard only when no later read resolves to that binding.
- Prefer small named functions, expressions, comprehensions and structural matches. Data records carry no
  behavioral methods. Ordinary values are assembled completely at construction and replaced by new values.
- Decisions are pure: the provisioning plan, the leg table and verdict, the digest rule, the lane predicates and
  `paths.py` over OS family, environment and home take values and return values, so their tests are `value`
  evidence on every host.
- Platform choices are functions of the OS value `hostfacts.py` gathers once. No other module branches on
  `sys.platform` or `os.name`, so all pure platform-policy values can be exercised and type-checked on Linux. Native adapters execute only on their actual kernel lane and require its separate receipt; pure policy tests cannot stand in for those syscalls.

**Spawns only in `process.py`, and other effects at the edge.**

- Every spawn and exec goes through `src/agentctl/process.py`, the only module that imports `subprocess` or calls
  an `os.exec*`, `os.spawn*`, `os.posix_spawn` or `os.system` function (`src.one-process-module`), and the only one
  where ruff allows S603 and S606.
- An argv is an immutable sequence of separate argument values. The process adapter materializes the native
  library's required container at the boundary. Nothing runs a shell or builds a command string, so no user
  text is ever re-parsed.
- Filesystem writes, the urllib download and the handoff live in thin adapters. A file agentctl owns is written
  to a temporary file in the same directory and renamed into place, so an interrupted install or build leaves
  the old file or nothing, and private files are created with their final mode (0600, in a 0700 directory).
- The Python bootstrap unpacks no archive and reads no project configuration, and its only network request is the pinned
  ghcup URL; cabal and ghcup reach Hackage and downloads.haskell.org as spawned tools. No secret goes on an argv
  or into a log.

**Typed parsing at boundaries.** Everything from outside, whether TOML (the pins, the oracles), JSON
(`direct_url.json`, `agentctl-core-eval` output), process output, `/etc/os-release`, environment variables or
downloaded bytes, is parsed into a domain value where it arrives or turned there into a typed error, so core logic
never handles an unparsed `str`, `bytes` or native mapping. Decoder aliases describe the complete supported
recursive native value vocabulary. The parser validates structure, bounds and invariants once and constructs
an immutable domain value; it does not launder untyped data through `object`, casts or dishonest annotations.
Process output is decoded as UTF-8 explicitly, never through
the locale. Python subprocess pipes drain bytes before the caller decodes them and applies universal-newline
handling, so an invalid byte becomes a typed error rather than an exception in a Windows reader thread
(`tests/integration/test_runtime_boundaries.py::test_process_errors_and_teardown`,
`tests/integration/test_runtime_boundaries.py::test_owned_child_decoding_failure`).
TOML and JSON use only the standard library's `tomllib` and `json`; host discovery uses the standard
library's `shlex` for the shell-quoted `ID` and `VERSION_ID` fields of `os-release`.

**Tests.** `unittest.mock` is banned, and `monkeypatch` serves only `setenv`, `delenv` and `chdir`; effects are
observed through the spawn audit and the fake agent ([testing](testing.md#observers-and-nonces)).

Each pure contract has executable accepting, hostile-input, failure, composition and collection cases where
applicable, with explicit finite bounds. Repeated evaluations preserve inputs and results. Relevant ambient
perturbations exercise independence from locale, timezone, working directory, hash order and external state.
An edge refusal checks the typed reason and observable behavior, not merely a nonzero exit that could hide a
traceback. Source-rule controls and mutants establish their named obligations; finite examples do not prove
universal termination, arbitrary callback purity or the soundness of every native dependency.

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
- Every new Haskell dependency has verified native build requirements for its supported platform. A dependency
  requiring Unix configure tools cannot silently rely on an unprovisioned Windows environment; its real build
  requirements belong to the bootstrap plan and native evidence.
- Dependencies are few and resolved at the pinned `index-state`, starting from the concept note's candidates
  (`optparse-applicative`, `process`, `directory`, `filepath`, `time`, `async`, `stm`, `tasty`); runtime pins and state are validated package-owned data; a parser adds no user-project configuration surface. `-Wunused-packages` removes any that a component stops
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
Windows uses the explicit `\\.\NUL` device path; other hosts use `/dev/null`.
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
Foreground execution keeps Windows handle inheritance enabled: the pinned process library's `close_fds` setting
disables inheritance of redirected standard handles as well. POSIX foreground execution closes other descriptors.
Foreground clients retain only client lifetime ownership, so forwarding a multiplexer invocation preserves its
server. The Windows trampoline waits for its direct program child and publishes that child's status; detached
sessions created by a program inside that pane do not extend the trampoline's wait. Bounded queries retain
process-tree ownership.
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
access. POSIX uses its opened descriptor; Windows uses a protected owner-only DACL and an exclusive root handle
opened with `MAXIMUM_ALLOWED`,
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
- [Python bootstrap and handoff](../../DEVELOPMENT_PLAN/phase-2-python-bootstrap-and-handoff.md) — the phase that builds the warnings stanza and the style legs.
