# Code Standards

**Status**: Authoritative source
**Supersedes**: N/A
**Owning phase**: [Haskell package, quality legs and digest-keyed build](../../DEVELOPMENT_PLAN/phase-3-haskell-package-and-build.md)

> **Purpose**: State the rules every Python and Haskell module of agentctl follows, why each exists, and which leg or check holds it.

These rules carry over the concept note's engineering rules (strict typing, functional style and result types;
[the concept-note disposition](../../DEVELOPMENT_PLAN/rationale.md#concept-note-disposition), rows CN-14 and
CN-32 to CN-39) wherever they fit a permanent pipx application, and drop `uv`, which R1 excludes as a host
dependency. The legs of [the quality gate](quality_gate.md#the-eight-legs) and the `src.*` checks hold the
mechanical part; a rule that names no mechanism is applied when the user reviews a change. Tests follow the same
rules as the package, and ruff and ty run over both.

## Python

**Types.**

- Every function, parameter, return value and callback is annotated (ruff's `ANN` rules under
  `select = ["ALL"]`), and ty checks with every rule an error, untyped decorators included.
- No `Any`, `typing.cast` or `typing.no_type_check`: ruff's banned-api rejects the imports, and
  `src.suppression-ban` rejects the names wherever an alias could carry them
  (`tests/governance/test_source_guards.py::test_suppression_ban_fixtures`).
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
the locale, and the standard library's `tomllib` and `json` are the only parsers.

**Tests.** `unittest.mock` is banned, and `monkeypatch` serves only `setenv`, `delenv` and `chdir`; effects are
observed through the spawn audit and the fake agent ([testing](testing.md#observers-and-nonces)).

## Haskell

**The warnings stanza.** Every component of `agentctl-core.cabal` (the library, the three executables and the
test suite) imports one common stanza, so a bare `cabal build` refuses exactly what the gate's `cabal-build` leg
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
- No CPP: the handshake needs none, because it carries no digest, and a module whose meaning depends on CPP is
  one the style legs cannot read as written.
- No package the build compiles from Hackage uses `build-type: Configure`, because Windows provisioning installs
  no MSYS2; that this holds on a real Windows host is confirmed by
  [Windows and psmux acceptance](../../DEVELOPMENT_PLAN/phase-14-windows-psmux-acceptance.md).
- Dependencies are few and resolved at the pinned `index-state`, starting from the concept note's candidates
  (`optparse-applicative`, `process`, `directory`, `filepath`, `time`, `async`, `stm`, `tasty`); no TOML parser
  is needed, because agentctl reads no configuration file. `-Wunused-packages` removes any that a component stops
  using.

**Style.** `fourmolu.yaml` and `.hlint.yaml` are committed in `src/agentctl/haskell/`. `fourmolu.yaml` writes out
every setting, so a formatter upgrade changes no style; `.hlint.yaml` keeps hlint's default hints and has no
`ignore` entry. No `HLINT ignore` annotation appears in a source (`src.suppression-ban`), and no region turns the
formatter off. The pinned fourmolu and hlint run from `cache/tools/<pin-digest>`, never from PATH.

**Opaque types for capabilities.** The module that establishes a condition exports its type but not its
constructor, so holding a value proves the check ran.

- `Ready` belongs to `AgentCtl.Preflight`, and `AgentCtl.Launch` creates a session only from a `Ready`, so a launch
  path that skips preflight does not compile. A compile-fail fixture matched by its GHC diagnostic code, beside a
  twin that compiles, keeps the constructor private
  (`tests/integration/test_ready_opaque.py::test_ready_constructor_is_not_exported`;
  [launch contract](../architecture/launch_contract.md#preflight)).
- `SessionName` comes only from the smart constructor in `AgentCtl.Session.Name`, so an unvalidated name cannot
  reach a multiplexer command.
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
  `agentctl-core-eval` exposes as `value` evidence and what Haskell mutants target.
- Process output is decoded as UTF-8 explicitly, and no module computes a per-user directory: `AgentCtl.Paths`
  receives them from the handoff.

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
