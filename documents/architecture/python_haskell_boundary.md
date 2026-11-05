# Python and Haskell Boundary

**Status**: Authoritative source
**Supersedes**: N/A
**Owning phase**: [Launch command and passthrough](../../DEVELOPMENT_PLAN/phase-6-launch-and-passthrough.md)

> **Purpose**: State what the Python click layer owns, what the core binary owns, how a command crosses from
> one to the other, and which single module owns each invariant that spans both layers.

## TL;DR

- Python (`src/agentctl/`) owns only what must happen before a binary exists, plus the gate: the per-user
  directories, the OS prerequisites (with consent), ghcup, GHC and cabal, the digest-keyed build, and
  `agentctl check`. It implements no launch, session or supervisor behaviour, and it never spawns tmux, psmux,
  claude or codex.
- The core binary, `agentctl-core`, owns everything after bootstrap: the multiplexer, the agent argv,
  preflight, launch, session management and the supervisor. Every warning after bootstrap is the binary's.
- Every command except `check` passes through raw. `main(argv)` in `src/agentctl/cli.py` lets the group parse global options, then
  `RawCommand` preserves the entire tail before command parsing, and the binary dispatches `claude` and `codex` on its raw arguments before
  option parsing, so ARGS reach the agent byte for byte.
- The handoff is `execve` on POSIX and a child process whose exit status becomes agentctl's on Windows. The
  binary is never on PATH, answers a handshake (protocol version and command list), and refuses to run
  without the handoff.
- Each invariant that spans both layers has one owner, and the other layer holds no copy of it.

## What Python Owns

Python runs first, because something must exist before the binary does. Its responsibilities, in the order
a first run meets them:

1. **Per-user directories.** `src/agentctl/paths.py` decides `cache`, `data` and `state`, honouring the XDG
   overrides on every OS. Their defaults and contents are in [files and state](../reference/files_and_state.md).
2. **OS prerequisites.** `src/agentctl/bootstrap/prereqs.py` probes the C compiler and linker, `-lgmp`, curl
   or wget, CA certificates and make. An interactive run asks before installing; a non-interactive run requires
   the global `--assume-yes` as consent and root or `sudo -n` for privilege, and never prompts. Passwordless sudo
   alone grants no consent; [the bootstrap consent contract](../engineering/toolchain_bootstrap.md#os-prerequisites)
   owns the OS-specific commands and the macOS dialog.
3. **ghcup.** `src/agentctl/bootstrap/ghcup.py` reuses an existing ghcup at or above the floor, or downloads
   the pinned binary with urllib and verifies its published SHA-256.
4. **GHC and cabal.** `src/agentctl/bootstrap/toolchain.py` installs the pins without changing the user's
   default selection and invokes both by the absolute paths `ghcup whereis` prints.
   It verifies both versions before atomically recording those strings; a warm ensure runs only their two version
   checks. `check/toolchain.py` supplies native readiness observations and invokes the same selection-preserving
   code path (`tests/integration/test_toolchain.py::test_warm_run_spawns_only_version_checks`).
5. **The build.** `src/agentctl/bootstrap/build.py` builds the bundled Cabal project into
   `cache/build/<digest>` and publishes the binary atomically into `data/bin/<digest>`; a digest hit builds
   nothing.
6. **The handoff.** `src/agentctl/bootstrap/handoff.py` ensures the binary for the current digest exists,
   then hands the command to it.

Steps 2 to 5 belong to [the toolchain bootstrap](../engineering/toolchain_bootstrap.md) and
[the binary build](../engineering/binary_build.md). `agentctl check` is Python's own command and never passes
through; [the quality gate](../engineering/quality_gate.md#check-steps) owns its steps and legs. The global
option `--assume-yes` is Python's: it governs consent for step 2 and is never forwarded.

## What the Core Binary Owns

- Multiplexer resolution, version floors and the typed tmux and psmux vocabulary
  ([multiplexer adapter](multiplexer_adapter.md)).
- The agent table, argument assembly, login refusals, auth classification, preflight and the opaque `Ready`,
  launch, instant-exit capture and the pane trampoline ([launch contract](launch_contract.md)).
- `list`, `status`, `attach`, `stop` and `adopt` ([sessions and ownership](sessions_and_ownership.md)).
- `watch`, `unwatch`, `pause`, `resume-watch`, `logs` and `supervisor run`
  ([supervisor contract](supervisor_contract.md)).

The binary never invokes ghcup, GHC or cabal: its one runner, `AgentCtl.Process`, interprets typed commands,
and the vocabulary has no command for them.

## Raw Passthrough

A parser that interprets the tail would change it: click claims `--help` for itself and treats the first bare
`--` as its own separator, so `agentctl claude -- --yolo` would reach the agent without its `--`. Both layers
therefore split before they parse.

- **Python.** `main(argv)` enters the click group, which reads global options before the command. A passthrough
  command uses `RawCommand.parse_args` to retain every tail element without a command parser, and its invoke method
  returns explicit transport data to the group dispatcher. The tail goes to the binary unchanged:
  `agentctl --assume-yes claude --model opus -- fix` forwards `claude --model opus -- fix`, while
  `agentctl claude --assume-yes` forwards `--assume-yes` to claude. Only `check` and the global options are
  parsed by click, and click's command table lists the passthrough commands so that `agentctl --help`
  shows them (`tests/unit/test_passthrough.py::test_every_command_but_check_passes_through`,
  `tests/unit/test_passthrough.py::test_raw_tail_keeps_dashdash_and_help`).
- **The binary.** `agentctl-core` dispatches `claude` and `codex` on its raw arguments before
  optparse-applicative runs, and parses the session and supervisor commands normally. Usage and error text
  name the program `agentctl`, so runtime output never shows the binary's name either
  (`tests/integration/test_passthrough.py::test_usage_text_names_agentctl`).
- **The command surface.** Python's passthrough table equals the command list the binary reports in its
  handshake, and both follow `tests/oracles/command_surface.toml`; a command present on one side only fails
  (`tests/integration/test_passthrough.py::test_passthrough_table_equals_binary_commands`).
- **Through-stack rows.** The R9 rows of `tests/oracles/launch_argv.toml` include `--`, `-- --yolo`, `--help`,
  `-h`, the empty string, `x;`, `#{pane_id}`, `$(id)` and an embedded newline. Each is compared at three
  points: the tail Python hands off (the spawn audit), the pure argv assembly (`agentctl-core-eval`), and the
  argv the agent receives, recorded by `agentctl-fake-agent` with its nonce
  (`tests/e2e/test_passthrough_argv.py::test_through_stack_rows`).

## The Handoff

`bootstrap/handoff.py` builds the binary's argv as the command name followed by the raw tail, and sets the
protocol version and the absolute `cache`, `data` and `state` paths in the binary's environment as
`AGENTCTL_CACHE_DIR`, `AGENTCTL_DATA_DIR` and `AGENTCTL_STATE_DIR`. `AgentCtl.Paths` validates these supplied
paths and derives only owned subdirectories; it never computes a per-user location. The handoff also supplies
`AGENTCTL_DISTRIBUTION` for the platform-specific install hints.

- **POSIX: `execve`.** On Unix the new executable is loaded into the current process with the same process
  id. The binary then owns the user's terminal, signals and exit status directly, and no Python process
  stays alive beside it. Python flushes stdout and stderr first, because `exec` discards unflushed buffers.
- **Windows: a child process.** Windows has no in-place replacement of that kind, so Python starts the binary
  as a child with inherited stdio, leaves console interrupts to the child while it waits, and exits with the
  child's exit code. `ty` and hostbootstrap hand off the same way.

Either way, the exit status agentctl reports is the binary's own; for a launch whose agent exits during
startup it is the agent's ([instant exit](launch_contract.md#instant-exit)). The mode is a pure choice by OS
family (`tests/unit/test_handoff.py::test_handoff_mode_by_os_family`), and the child mode is run on every host
to show the child's status survives (`tests/integration/test_handoff.py::test_child_mode_propagates_exit_status`).

## The Handshake and Direct Invocation

The handshake is the binary's answer to one question: which protocol version it speaks and which commands it
provides. It carries no digest and needs no CPP; the binary's identity is the sha256 of the path
`cabal list-bin` prints, which [the binary build](../engineering/binary_build.md) owns.

The protocol version is `1`, supplied as `AGENTCTL_PROTOCOL_VERSION`; `--handshake` answers a JSON object with
`protocol` and `commands`. The command list excludes Python's `check`. Missing and different versions refuse
ordinary commands before dispatch, and the JSONL evaluator checks the same pure protocol kernel against
`tests/oracles/protocol.toml`
(`tests/integration/test_haskell_legs.py::test_direct_invocation_refused`,
`tests/integration/test_eval_executable.py::test_every_case_answered`).

- Python publishes a build only after the binary answers with the protocol version Python expects, and the
  passthrough table is compared with the command list the binary answers.
- The binary refuses every command when the protocol version from the handoff is absent or different, and its
  refusal tells the user to run `agentctl` instead, without naming the binary
  (`tests/integration/test_passthrough.py::test_binary_refuses_direct_run`).
- `pane-exec` is the one command the multiplexer, not Python, invokes; the pane's environment is the server's,
  so it carries no handoff. Its authority is its spec file instead, whose rules are in
  [the pane trampoline](launch_contract.md#the-pane-trampoline).
- The refusal guards against accidental direct use and is not a security boundary: a user who finds the
  binary under `data/bin/<digest>` and sets the variables can run it.

## The Python Spawn Set

Every Python spawn goes through `src/agentctl/process.py`, the only module that spawns or execs
(`src.one-process-module`), and downloads use urllib, never a spawned downloader.

| Executable | Spawned by | When |
|---|---|---|
| the core binary | `bootstrap/handoff.py`, `bootstrap/build.py` | each passthrough command, after the digest check; the handshake after a build |
| ghcup, the reused or the verified pinned binary | `bootstrap/ghcup.py`, `bootstrap/toolchain.py` | `install ghc`, `install cabal --no-set` and `whereis`, only while a pin is missing |
| GHC and cabal, by absolute path | `bootstrap/toolchain.py`, `bootstrap/build.py`, `check/legs.py` | `--numeric-version` on warm runs; build, test and `list-bin`; building fourmolu and hlint into `cache/tools/<pin-digest>` |
| the C compiler | `bootstrap/prereqs.py` | the link probe against `-lgmp` |
| sudo with the OS package manager; `xcode-select --install` on macOS | `bootstrap/prereqs.py` | after interactive consent; non-interactively only with `--assume-yes` and root or `sudo -n`, with the macOS dialog handled as the bootstrap contract states |
| ruff, ty, pytest, fourmolu, hlint | `check/legs.py` | `agentctl check` only |
| git | `check/preconditions.py`, `check/ratchet.py` | `agentctl check` only, read-only |

Python never spawns tmux, psmux, claude, codex, a shell, curl or wget, or the ghcup bootstrap script. The
spawn audit in `src/agentctl/check/audit.py`, a `sys.addaudithook` observer, records every spawn the suite's
subjects make: a digest hit records only the binary's execve on POSIX or child creation on Windows
(`tests/integration/test_passthrough.py::test_warm_passthrough_spawns_only_the_binary`), a bootstrap run's ghcup argv must
match the provisioning plan in `tests/oracles/bootstrap_plan.toml`, and package-manager and sudo spawns are
vetoed so that no test runs one. Each absence assertion is paired with the recorded spawn that proves the audit was live.

## Single Owners

| Invariant | Owner | The other layer | Enforced by |
|---|---|---|---|
| Session names | `AgentCtl.Session.Name` | Python computes no name | `tests/oracles/session_names.toml`; the spawn audit shows Python forwarding only the raw tail |
| Mandatory flags, their placement and dedupe | `AgentCtl.Agent.Argv` | Python forwards ARGS unchanged | `tests/oracles/launch_argv.toml`, through the stack |
| Login refusals and remedies | `AgentCtl.Agent.Argv`, `AgentCtl.Agent.Auth` | nothing constructs a login | `src.no-login-construction` |
| Spawning and exec | `src/agentctl/process.py`, `AgentCtl.Process` | nothing else imports a process API | `src.one-process-module` |
| Per-user directories | `src/agentctl/paths.py` | `AgentCtl.Paths` receives them and computes none | `paths.py` is pure over OS family, environment and home, so its tests cover every OS family on any host |
| The right to launch | `AgentCtl.Preflight`, the only producer of `Ready` | `AgentCtl.Launch` creates a session only from a `Ready` | a compile-fail fixture matched by GHC diagnostic code, with a compiling twin |
| The command surface | the binary's handshake command list | Python's passthrough table equals it | `tests/oracles/command_surface.toml`, both directions |
| Toolchain and build | `src/agentctl/bootstrap/` | the binary's runner has no ghcup, GHC or cabal command | `src.one-process-module` |
| Warnings after bootstrap | the binary, on the invoking terminal | Python prints only bootstrap progress, consent prompts and check output | `tests/oracles/preflight.toml` |

The per-user directories have one owner because the two languages disagree: Python's platformdirs and
Haskell's `getXdgDirectory` give different macOS and Windows paths, so two computations would publish a
binary where the other side never looks.

## WRONG and RIGHT

```text
WRONG  Python appends the mandatory flags: handoff(["claude", *args, "--dangerously-skip-permissions"])
RIGHT  Python forwards the raw tail: handoff(["claude", *raw_tail]); AgentCtl.Agent.Argv assembles the argv
```

The WRONG form puts a second copy of the argv rules in Python, which drifts from the binary's dedupe and `--`
placement, and by the time click has parsed `args` the user's first `--` is already gone.

```text
WRONG  agentctl list runs `tmux list-sessions` from Python
RIGHT  agentctl list passes through; AgentCtl.Sessions reads the session options and the adopted registry
```

The WRONG form spawns tmux from Python, outside the spawn set, and rebuilds the session model in a second
language that cannot see the adopted registry's rules.

```text
WRONG  AgentCtl.Paths computes its own cache directory with getXdgDirectory
RIGHT  AgentCtl.Paths takes cache, data and state from the handoff that paths.py prepared
```

The WRONG form publishes into one macOS or Windows directory and looks for the binary in another.

## Related

- [launch contract](launch_contract.md) — what the binary does with the raw tail it receives.
- [multiplexer adapter](multiplexer_adapter.md) — the typed vocabulary behind the binary's one runner.
- [binary build](../engineering/binary_build.md) — the digest, the atomic publish and binary identity.
- [toolchain bootstrap](../engineering/toolchain_bootstrap.md) — the prerequisites, ghcup, GHC and cabal steps.
- [quality gate](../engineering/quality_gate.md) — `agentctl check`, the one command that never passes through.
- [testing](../engineering/testing.md#observers-and-nonces) — how the spawn audit and the fake agent observe.
- [files and state](../reference/files_and_state.md) — the per-user directories Python decides.
- [system components](../../DEVELOPMENT_PLAN/system-components.md) — the inventory of both packages.
- [Launch command and passthrough](../../DEVELOPMENT_PLAN/phase-6-launch-and-passthrough.md) — the phase that
  builds this boundary.
