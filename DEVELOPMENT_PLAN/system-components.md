# System Components

**Status**: Authoritative source
**Supersedes**: N/A

> **Purpose**: Inventory the modules, executables, test apparatus, external tools and per-user directories the phases build, with the phase that owns each.

Every row states what its owning phase builds; the [status table](README.md#current-phase-status) records which phases
are Done. The inventory owns no contract (standards § F): each section links the documents that do.

Each invariant that spans both layers has exactly one owner:

- **Session names.** `AgentCtl.Session.Name` alone derives a session name from the invoking folder; Python never
  computes one.
- **Mandatory flags.** `AgentCtl.Agent.Argv` alone removes user copies of the mandatory flags and appends them;
  Python forwards ARGS unchanged.
- **Spawning.** `src/agentctl/process.py` and `AgentCtl.Process` are the only modules that spawn or exec a process,
  and `AgentCtl.Process` is the only importer of `System.Process` (`src.one-process-module`, Sprint 1.4).
- **Per-user directories.** `src/agentctl/paths.py` decides every directory and passes it to the binary;
  `AgentCtl.Paths` receives them and computes none.
- **The right to launch.** Only `AgentCtl.Preflight` produces `Ready`, and `AgentCtl.Launch` creates a session only
  from a `Ready`.
- **Login.** No module constructs a login command or login keystrokes; `AgentCtl.Agent.Auth` names the command the
  user types (`src.no-login-construction`, Sprint 1.4).

## Python Package

The Python layer provisions the toolchain, builds the binary, runs `check`, and hands every other command to the
binary; [the Python/Haskell boundary](../documents/architecture/python_haskell_boundary.md) owns that split.

| Component | Path | Responsibility | Owning phase |
|---|---|---|---|
| Project metadata | `pyproject.toml` | hatchling build, `requires-python` at least 3.12, the exact pins of click and of the `dev` extra (ruff, ty, pytest, coverage), and the tool configuration that `tests/oracles/lint_config.toml` freezes | [Phase 0 — Governance, documentation standards and the check skeleton](phase-0-governance-and-check-skeleton.md) |
| Command group | `src/agentctl/cli.py` | The click group: `check`, the passthrough commands and the global `--assume-yes`. `main(argv)` splits the raw passthrough tail before click parses, so ARGS reach the binary unchanged; that split lands with [Phase 6 — Launch command and passthrough](phase-6-launch-and-passthrough.md) | [Phase 0 — Governance, documentation standards and the check skeleton](phase-0-governance-and-check-skeleton.md) |
| Result type | `src/agentctl/result.py` | The `Result` values that fallible functions return ([code standards](../documents/engineering/code_standards.md)) | [Phase 0 — Governance, documentation standards and the check skeleton](phase-0-governance-and-check-skeleton.md) |
| Process module | `src/agentctl/process.py` | The only Python module that spawns or execs a process | [Phase 0 — Governance, documentation standards and the check skeleton](phase-0-governance-and-check-skeleton.md) |
| Per-user paths | `src/agentctl/paths.py` | Decides the `cache`, `data` and `state` directories, honouring XDG overrides on every OS | [Phase 0 — Governance, documentation standards and the check skeleton](phase-0-governance-and-check-skeleton.md) |
| Host facts | `src/agentctl/hostfacts.py` | OS family, architecture, distribution and package manager, privilege, and any existing ghcup, GHC and cabal, gathered once as a value | [Phase 2 — Toolchain bootstrap](phase-2-toolchain-bootstrap.md) |
| Provisioning plan | `src/agentctl/bootstrap/plan.py` | A pure function from host facts to the ordered provisioning actions; re-planning after they are applied yields none | [Phase 2 — Toolchain bootstrap](phase-2-toolchain-bootstrap.md) |
| Pin parsing | `src/agentctl/bootstrap/pins.py` | Parses package data into numeric versions and immutable assets; selects only declared platform bindists | [Phase 2 — Toolchain bootstrap](phase-2-toolchain-bootstrap.md) |
| OS prerequisites | `src/agentctl/bootstrap/prereqs.py` | Probes the C compiler and linker, `-lgmp`, curl or wget, CA certificates and make; asks for consent, then runs the OS package manager | [Phase 2 — Toolchain bootstrap](phase-2-toolchain-bootstrap.md) |
| ghcup | `src/agentctl/bootstrap/ghcup.py` | Reuses an existing ghcup at or above the floor; otherwise downloads the pinned ghcup with urllib and verifies its SHA-256. Never runs the official bootstrap script, never edits rc files | [Phase 2 — Toolchain bootstrap](phase-2-toolchain-bootstrap.md) |
| Toolchain | `src/agentctl/bootstrap/toolchain.py` | Installs the pinned GHC and cabal without changing the user's default, resolves their absolute paths, and runs as the `toolchain-ensure` check step | [Phase 2 — Toolchain bootstrap](phase-2-toolchain-bootstrap.md) |
| Pins | `src/agentctl/bootstrap/pins.toml` | Package data: the ghcup, GHC and cabal pins, the ghcup floor, and the fourmolu and hlint pins | [Phase 2 — Toolchain bootstrap](phase-2-toolchain-bootstrap.md) |
| Build | `src/agentctl/bootstrap/build.py` | The one compiler-pinned Cabal path, private configuration and store, native builds and binary lookup | [Phase 3 — Haskell package, quality legs and digest-keyed build](phase-3-haskell-package-and-build.md) |
| Binary cache identity | `src/agentctl/bootstrap/cache.py` | Canonical source inventory, length-prefixed source/pin/platform digest and immutable cache paths | [Phase 3 — Haskell package, quality legs and digest-keyed build](phase-3-haskell-package-and-build.md) |
| Binary preparation | `src/agentctl/bootstrap/binary.py` | Spawn-free hits, locked builds, handshake-checked atomic publication and actual file hashes | [Phase 3 — Haskell package, quality legs and digest-keyed build](phase-3-haskell-package-and-build.md) |
| Binary identity gate | `src/agentctl/check/identity.py` | Current Cabal output and published bytes must agree and the core binary must resolve nowhere on PATH | [Phase 3 — Haskell package, quality legs and digest-keyed build](phase-3-haskell-package-and-build.md) |
| Handoff | `src/agentctl/bootstrap/handoff.py` | Ensures the binary for the current digest and hands off to it: `execve` on POSIX, a child process whose exit status is propagated on Windows | [Phase 6 — Launch command and passthrough](phase-6-launch-and-passthrough.md) |
| Haskell project | `src/agentctl/haskell/` | The Cabal project, shipped as package data with no hatchling force-include | [Phase 3 — Haskell package, quality legs and digest-keyed build](phase-3-haskell-package-and-build.md) |
| Check legs | `src/agentctl/check/legs.py` | The legs of `tests/oracles/check_legs.toml`: each leg's argv, environment and non-empty target set | [Phase 0 — Governance, documentation standards and the check skeleton](phase-0-governance-and-check-skeleton.md) |
| Check steps | `src/agentctl/check/steps.py` | The ordered steps of `tests/oracles/check_steps.toml`, the scrubbed environment allowlist, and the verdict: a step or leg that fails or does not run fails check | [Phase 0 — Governance, documentation standards and the check skeleton](phase-0-governance-and-check-skeleton.md) |
| Preconditions | `src/agentctl/check/preconditions.py` | Dependency and checkout diagnostics using only the standard library, the single-run lock, and toolchain readiness values | [Phase 0 — Governance, documentation standards and the check skeleton](phase-0-governance-and-check-skeleton.md) |
| Prerequisite readiness | `src/agentctl/check/prerequisites.py` | P9 probes and consent/privilege readiness after dependency validation, without prompting or opening the Xcode installer | [Phase 2 — Toolchain bootstrap](phase-2-toolchain-bootstrap.md) |
| Toolchain readiness and gate step | `src/agentctl/check/toolchain.py` | Native P7/P8/P10 observations, shared-volume budgets and the selection-preserving provisioning step after ty | [Phase 2 — Toolchain bootstrap](phase-2-toolchain-bootstrap.md) |
| Gate plugin | `src/agentctl/check/gate_plugin.py` | The pytest plugin check loads: it fails the session on any skip, xfail, deselection or selection, records collected and executed ids with the run's nonce, and runs `tests.orphan-modules` | [Phase 0 — Governance, documentation standards and the check skeleton](phase-0-governance-and-check-skeleton.md) |
| Documentation validator | `src/agentctl/check/validator/docs.py` | The `docs.*` checks | [Phase 0 — Governance, documentation standards and the check skeleton](phase-0-governance-and-check-skeleton.md) |
| Plan validator | `src/agentctl/check/validator/plan.py` | The `plan.*` checks | [Phase 0 — Governance, documentation standards and the check skeleton](phase-0-governance-and-check-skeleton.md) |
| Plan declarations | `src/agentctl/check/plan_data.py` | Shared immutable phase and sprint records and nonexecuting Markdown parsing | [Phase 1 — Gate-integrity apparatus](phase-1-gate-integrity-apparatus.md) |
| Closure joins | `src/agentctl/check/validator/closure.py` | Completion paths, current cited results, integrity rows, owed confirmations, nonempty subjects and acceptance-row currency | [Phase 1 — Gate-integrity apparatus](phase-1-gate-integrity-apparatus.md) |
| Python startup policy | `src/agentctl/resources/python-startup.pth` | Disables import bytecode in the private application environment before editable-source imports | [Phase 1 — Gate-integrity apparatus](phase-1-gate-integrity-apparatus.md) |
| Mutant runner | `src/agentctl/check/mutants.py` | Applies exact-match patches to scratch copies, runs named killers and checks the named failure reason | [Phase 1 — Gate-integrity apparatus](phase-1-gate-integrity-apparatus.md) |
| Native gate execution | `src/agentctl/check/haskell.py` | Closed Cabal component routing, native build and test legs, fresh Tasty listings and XML, and the current-run evidence join | [Phase 3 — Haskell package, quality legs and digest-keyed build](phase-3-haskell-package-and-build.md) |
| Style cache values | `src/agentctl/bootstrap/style.py` | Style pin digest, absolute native cache paths and exact compiler-pinned install arguments | [Phase 3 — Haskell package, quality legs and digest-keyed build](phase-3-haskell-package-and-build.md) |
| Native style execution | `src/agentctl/check/style.py` | Complete root configuration, nonempty Haskell targets, cache preparation and native formatter/linter verdicts | [Phase 3 — Haskell package, quality legs and digest-keyed build](phase-3-haskell-package-and-build.md) |
| Native mutant execution | `src/agentctl/check/haskell_mutants.py` | One outside-tree unoptimised scratch build and exact selected pure Tasty case failures | [Phase 3 — Haskell package, quality legs and digest-keyed build](phase-3-haskell-package-and-build.md) |
| Source and configuration guards | `src/agentctl/check/validator/source.py` | The `src.*`, `config.*`, `tree.*` and `oracles.*` source, configuration and provenance checks | [Phase 1 — Gate-integrity apparatus](phase-1-gate-integrity-apparatus.md) |
| Ratchet | `src/agentctl/check/ratchet.py` | `ratchet.append-only` and the `ratchet` step, reading HEAD with read-only git | [Phase 1 — Gate-integrity apparatus](phase-1-gate-integrity-apparatus.md) |
| Write-guard | `src/agentctl/check/writeguard.py` | The `write-guard-snapshot`, `write-guard-compare` and `containment` steps | [Phase 1 — Gate-integrity apparatus](phase-1-gate-integrity-apparatus.md) |
| Spawn audit | `src/agentctl/check/audit.py` | The `sys.addaudithook` spawn audit, an observer that records Python spawns under the suite and vetoes forbidden ones | [Phase 1 — Gate-integrity apparatus](phase-1-gate-integrity-apparatus.md) |
| Evidence | `src/agentctl/check/evidence.py` | The `post-run-verifier` step, the tree digest over Evidence covers, and the EVIDENCE line | [Phase 1 — Gate-integrity apparatus](phase-1-gate-integrity-apparatus.md) |
| Lanes | `src/agentctl/check/lanes.py` | Evaluates the lane predicates over the harness's host observations, prints the `lane-summary` step, and fails check when a Done self-verifying phase's lane is unmet | [Phase 1 — Gate-integrity apparatus](phase-1-gate-integrity-apparatus.md) |

The `validators` step also runs the `tests.*`, `oracles.*`, `ratchet.*`, `tree.*`, `src.*`, `config.*` and
`validator.*` checks; the [plan standards](development_plan_standards.md) name the sprint that lands each.

## Haskell Package

Paths are relative to `src/agentctl/haskell/`. The binary's contracts live in
[the multiplexer adapter](../documents/architecture/multiplexer_adapter.md),
[the launch contract](../documents/architecture/launch_contract.md),
[sessions and ownership](../documents/architecture/sessions_and_ownership.md) and
[the supervisor contract](../documents/architecture/supervisor_contract.md).

| Component | Path | Responsibility | Owning phase |
|---|---|---|---|
| Package description | `agentctl-core.cabal` | The library, the executables and the test suite below, with a common warnings stanza carrying `-Werror` | [Phase 3 — Haskell package, quality legs and digest-keyed build](phase-3-haskell-package-and-build.md) |
| Project file | `cabal.project` | The pinned Hackage index-state | [Phase 3 — Haskell package, quality legs and digest-keyed build](phase-3-haskell-package-and-build.md) |
| Style configuration | `fourmolu.yaml`, `.hlint.yaml` | The complete formatter and default-hint linter configuration, with no ignores | [Phase 3 — Haskell package, quality legs and digest-keyed build](phase-3-haskell-package-and-build.md) |
| Source roots | `app/`, `src/`, `test/` | The executables' mains, the `AgentCtl.*` library and the tasty suite | [Phase 3 — Haskell package, quality legs and digest-keyed build](phase-3-haskell-package-and-build.md) |
| `agentctl-core` | executable in `agentctl-core.cabal` | The core binary: never on PATH and refuses to run without the handoff. It dispatches `claude` and `codex` on the raw arguments before option parsing and names itself `agentctl` in usage text, both from [Phase 6 — Launch command and passthrough](phase-6-launch-and-passthrough.md) | [Phase 3 — Haskell package, quality legs and digest-keyed build](phase-3-haskell-package-and-build.md) |
| `agentctl-core-eval` | executable in `agentctl-core.cabal` | Reads JSON cases on stdin, applies pure Haskell subjects and prints results, which Python compares with oracle rows | [Phase 3 — Haskell package, quality legs and digest-keyed build](phase-3-haskell-package-and-build.md) |
| `agentctl-fake-agent` | executable in `agentctl-core.cabal`, outside suite routing | The observer stand-in, copied into a temp bin as `claude` or `codex`; records argv, cwd, environment keys, the multiplexer session and the nonce | [Phase 4 — Multiplexer adapter](phase-4-multiplexer-adapter.md) |
| Scripted agent observer | `app/ScriptedAgent.hs`, `app/fake_signals.c` | Private terminal input mode and fixture frames advanced by file, byte count or time, with flushed nonce-bound frame and byte receipts | [Phase 10 — Recovery supervisor](phase-10-supervisor.md) |
| Native command fixture | `test/MuxFixture.hs` | Test-binary entry invoking the production typed command interpreter and status reader under the harness-owned environment | [Phase 4 — Multiplexer adapter](phase-4-multiplexer-adapter.md) |
| Native auth fixture | `test/AgentFixture.hs` | Test-binary entry invoking the production exit-code-only auth probe and preflight interpreter under the harness-owned caller environment | [Phase 5 — Agent adapters and preflight](phase-5-agent-adapters-and-preflight.md) |
| `agentctl-core-test` | test suite in `agentctl-core.cabal`, under `test/` | The tasty suite the `cabal-test` leg runs; its cases are cited as `haskell:agentctl-core-test/<Group>/<case>` | [Phase 3 — Haskell package, quality legs and digest-keyed build](phase-3-haskell-package-and-build.md) |
| `AgentCtl.Protocol` | `src/AgentCtl/Protocol.hs` | The handshake (protocol version and command list) and the refusal to run without Python's handoff | [Phase 3 — Haskell package, quality legs and digest-keyed build](phase-3-haskell-package-and-build.md) |
| `AgentCtl.Process` | `src/AgentCtl/Process.hs` | The one runner: it interprets typed commands and performs every spawn and exec in the binary, and it is the only importer of `System.Process` | [Phase 4 — Multiplexer adapter](phase-4-multiplexer-adapter.md) |
| `AgentCtl.Mux` | `src/AgentCtl/Mux.hs` | Resolves tmux (Linux, macOS) or psmux (Windows) to an absolute path and enforces the version floors | [Phase 4 — Multiplexer adapter](phase-4-multiplexer-adapter.md) |
| `AgentCtl.Mux.Command` | `src/AgentCtl/Mux/Command.hs` | The typed multiplexer command vocabulary, opaque pane ids and identity values, and dead-status source policy | [Phase 4 — Multiplexer adapter](phase-4-multiplexer-adapter.md) |
| `AgentCtl.Mux.Types` | `src/AgentCtl/Mux/Types.hs` | Internal shared family, kind and checked multiplexer representation; the public Mux export keeps the capability constructor private | [Phase 4 — Multiplexer adapter](phase-4-multiplexer-adapter.md) |
| `AgentCtl.Mux.Tmux` | `src/AgentCtl/Mux/Tmux.hs` | Renders the vocabulary as tmux argv | [Phase 4 — Multiplexer adapter](phase-4-multiplexer-adapter.md) |
| `AgentCtl.Mux.Psmux` | `src/AgentCtl/Mux/Psmux.hs` | Renders the vocabulary as psmux argv, always invoking `psmux`, never its `tmux` alias | [Phase 4 — Multiplexer adapter](phase-4-multiplexer-adapter.md) |
| `AgentCtl.PaneExec` | `src/AgentCtl/PaneExec.hs` | The pane trampoline `agentctl-core pane-exec <spec>`: reads and deletes the 0600 spec, then, through `AgentCtl.Process`, calls `execve` on POSIX, or runs the agent as a child and writes a status file on Windows | [Phase 4 — Multiplexer adapter](phase-4-multiplexer-adapter.md) |
| `AgentCtl.PaneExec.Spec` | `src/AgentCtl/PaneExec/Spec.hs` | The spec codec, pure access policy and pane-environment selection | [Phase 4 — Multiplexer adapter](phase-4-multiplexer-adapter.md) |
| `AgentCtl.Native` | `src/AgentCtl/Native.hs`, `src/AgentCtl/native_fs.c`, `src/AgentCtl/native_utf8.h` | The bounded filesystem snapshot ABI with POSIX descriptor facts and native Windows owner-SID/DACL observations | [Phase 4 — Multiplexer adapter](phase-4-multiplexer-adapter.md) |
| Owned state-directory control | `test/state_fixture.c`, `test/SpecTests.hs` | Constructs overpermissive owned directory access through native chmod or independent Win32 SDDL, then proves strict refusal and private state preparation without changing an existing child | [Phase 7 — Session management and adoption](phase-7-session-management-and-adoption.md) |
| Native execution ABI | `src/AgentCtl/native_process.c` | The actual exec binding called only by AgentCtl.Process, with explicit UTF-8 arguments and environment | [Phase 4 — Multiplexer adapter](phase-4-multiplexer-adapter.md) |
| Controlled terminal closure | `app/fake_signals.c` | Fake-agent-only SIGHUP handling keeps the closed-stream observer alive until its owned release file appears | [Phase 4 — Multiplexer adapter](phase-4-multiplexer-adapter.md) |
| `AgentCtl.Session.Name` | `src/AgentCtl/Session/Name.hs` | The `SessionName` smart constructor (`[A-Za-z0-9_-]`, never `__`, never empty). Its derivation from the canonical folder, and the hash form for a different folder with the same base, come from [Phase 6 — Launch command and passthrough](phase-6-launch-and-passthrough.md) | [Phase 4 — Multiplexer adapter](phase-4-multiplexer-adapter.md) |
| `AgentCtl.Agent` | `src/AgentCtl/Agent.hs` | The closed agent table: native executable names, mandatory flags and aliases, auth argv, login remedies and variants, OS install hints and recovery text, plus pure PATH selection and its native filesystem adapter | [Phase 5 — Agent adapters and preflight](phase-5-agent-adapters-and-preflight.md) |
| `AgentCtl.Agent.Types` | `src/AgentCtl/Agent/Types.hs` | Shared closed agent identity and its literal text codec, re-exported by AgentCtl.Agent without introducing a dependency from naming to mux IO | [Phase 6 — Launch command and passthrough](phase-6-launch-and-passthrough.md) |
| `AgentCtl.Agent.Argv` | `src/AgentCtl/Agent/Argv.hs` | Pure argv assembly plus checked assembly: removes user copies of mandatory flags, places them before the first bare `--` or at the end, and refuses login-shaped ARGS before preflight with its exit-2 remedy | [Phase 5 — Agent adapters and preflight](phase-5-agent-adapters-and-preflight.md) |
| `AgentCtl.Agent.Auth` | `src/AgentCtl/Agent/Auth.hs` | Builds the closed auth-status invocation, preserves caller environment, classifies only the exit code and renders a distinct failed-probe warning or login remedy | [Phase 5 — Agent adapters and preflight](phase-5-agent-adapters-and-preflight.md) |
| `AgentCtl.Preflight` | `src/AgentCtl/Preflight.hs` | Checks the multiplexer, then the agent, then auth; success is the opaque `Ready`, whose constructor is not exported | [Phase 5 — Agent adapters and preflight](phase-5-agent-adapters-and-preflight.md) |
| `AgentCtl.Paths` | `src/AgentCtl/Paths.hs` | Receives the per-user directories Python passes in; computes none | [Phase 6 — Launch command and passthrough](phase-6-launch-and-passthrough.md) |
| `AgentCtl.Launch` | `src/AgentCtl/Launch.hs` | Create-or-attach, instant-exit capture, failure cleanup with the warning on the caller's terminal, no-TTY and `$TMUX` handling, and the `@agentctl_agent`, `@agentctl_folder` and `@agentctl_owner` session options | [Phase 6 — Launch command and passthrough](phase-6-launch-and-passthrough.md) |
| `AgentCtl.Sessions` | `src/AgentCtl/Sessions.hs` | `list`, `status`, `attach` and `stop` over managed sessions, identified by their session options | [Phase 7 — Session management and adoption](phase-7-session-management-and-adoption.md) |
| `AgentCtl.Session.Identity` | `src/AgentCtl/Session/Identity.hs` | Shared session-option parsing and strict unpadded base64url UTF-8 identity codecs, used by launch and session queries | [Phase 7 — Session management and adoption](phase-7-session-management-and-adoption.md) |
| `AgentCtl.Adopt` | `src/AgentCtl/Adopt.hs` | Strict, private adopted-pane registry, native endpoint/pane/pid revalidation and adoption decisions; stop forgets and never kills | [Phase 7 — Session management and adoption](phase-7-session-management-and-adoption.md) |
| `AgentCtl.Observe.Capture` | `src/AgentCtl/Observe/Capture.hs` | Bounded joined UTF-8 capture, coherent native dead/cursor/style observations and typed capture failures | [Phase 8 — Pane observation and classification](phase-8-pane-observation-and-classification.md) |
| `AgentCtl.Observe.Normalize` | `src/AgentCtl/Observe/Normalize.hs` | Pure CR/LF normalization, trailing horizontal-space and blank-line removal, and the bounded tail | [Phase 8 — Pane observation and classification](phase-8-pane-observation-and-classification.md) |
| `AgentCtl.Observe.Fingerprint` | `src/AgentCtl/Observe/Fingerprint.hs` | Typed error blocks with surrounding text kept separate; SHA-256 consumes normalized error content alone | [Phase 8 — Pane observation and classification](phase-8-pane-observation-and-classification.md) |
| `AgentCtl.Observe.Classify`, `AgentCtl.Observe.Classify.Claude`, `AgentCtl.Observe.Classify.Codex` | `src/AgentCtl/Observe/Classify.hs`, `src/AgentCtl/Observe/Classify/Claude.hs`, `src/AgentCtl/Observe/Classify/Codex.hs` | Per-agent classifiers onto the closed screen-class vocabulary of the supervisor contract | [Phase 8 — Pane observation and classification](phase-8-pane-observation-and-classification.md) |
| `AgentCtl.Observe.Classify.Input` | `src/AgentCtl/Observe/Classify/Input.hs` | Conservative composer interpretation from matching faint styling, text and cursor facts | [Phase 8 — Pane observation and classification](phase-8-pane-observation-and-classification.md) |
| `AgentCtl.Observe.Classify.Agent` | `src/AgentCtl/Observe/Classify/Agent.hs` | The shared closed agent-to-classifier dispatch used by live session status | [Phase 8 — Pane observation and classification](phase-8-pane-observation-and-classification.md) |
| `AgentCtl.Recovery.Machine` | `src/AgentCtl/Recovery/Machine.hs` | The pure total recovery step, handled fingerprint identities, deadlines, closed actions and per-decision notification projection | [Phase 9 — Recovery state machine and backoff](phase-9-recovery-state-machine.md) |
| `AgentCtl.Recovery.Backoff` | `src/AgentCtl/Recovery/Backoff.hs` | Validated finite policies, arbitrary-precision attempts, bounded exponential delays, seeded Word64 jitter and escalation records | [Phase 9 — Recovery state machine and backoff](phase-9-recovery-state-machine.md) |
| `AgentCtl.Supervisor.Watch` | `src/AgentCtl/Supervisor/Watch.hs` | The revisioned watch set, pure intent transitions and public watch-state columns | [Phase 10 — Recovery supervisor](phase-10-supervisor.md) |
| `AgentCtl.Supervisor` | `src/AgentCtl/Supervisor.hs` | `supervisor run`, the foreground poll loop: it re-captures and re-classifies immediately before `send-keys -l` and aborts if the screen changed | [Phase 10 — Recovery supervisor](phase-10-supervisor.md) |
| `AgentCtl.Supervisor.Runtime` | `src/AgentCtl/Supervisor/Runtime.hs` | Native capture, identity revalidation, guarded delivery and logging interpreter under the supervisor and watch locks | [Phase 10 — Recovery supervisor](phase-10-supervisor.md) |
| `AgentCtl.Supervisor.Lock` | `src/AgentCtl/Supervisor/Lock.hs` | Scoped native supervisor exclusion and bounded serialization of watch intent updates | [Phase 10 — Recovery supervisor](phase-10-supervisor.md) |
| `AgentCtl.Supervisor.Commands` | `src/AgentCtl/Supervisor/Commands.hs` | The pure command plan: fixed recovery text and separate Enter, with no commands for shutdown, unwatch or terminal outcomes | [Phase 10 — Recovery supervisor](phase-10-supervisor.md) |
| `AgentCtl.Supervisor.Guard` | `src/AgentCtl/Supervisor/Guard.hs` | The send-time equality check over overload class, fingerprint and normalized text | [Phase 10 — Recovery supervisor](phase-10-supervisor.md) |
| `AgentCtl.Supervisor.Delivery` | `src/AgentCtl/Supervisor/Delivery.hs` | Commits delivered input, defers a second send proposal, rebases identity changes and closes failed attempts without retrying partial input | [Phase 10 — Recovery supervisor](phase-10-supervisor.md) |
| `AgentCtl.Supervisor.Poll` | `src/AgentCtl/Supervisor/Poll.hs` | Capture requests, revision baselines, retained handled fingerprints, recovery steps and notifications for both sinks | [Phase 10 — Recovery supervisor](phase-10-supervisor.md) |
| `AgentCtl.Supervisor.Settings` | `src/AgentCtl/Supervisor/Settings.hs` | Shared timing option parser and validated finite poll and backoff settings | [Phase 10 — Recovery supervisor](phase-10-supervisor.md) |
| `AgentCtl.Supervisor.Log` | `src/AgentCtl/Supervisor/Log.hs` | Closed record types, complete poll records, exact target selection and strict JSONL decoding | [Phase 10 — Recovery supervisor](phase-10-supervisor.md) |
| `AgentCtl.Supervisor.Log.File` | `src/AgentCtl/Supervisor/Log/File.hs` | Native owned append, writer lifetime under the supervisor lock, concurrent readers and startup refusal of corrupt history | [Phase 10 — Recovery supervisor](phase-10-supervisor.md) |

## Test Apparatus

How each piece is used, and what each evidence class proves, is in [testing](../documents/engineering/testing.md).

| Component | Path | Responsibility | Owning phase |
|---|---|---|---|
| Oracle comparison | `tests/harness/oracle.py` | `assert_oracle`, the one comparison of subject results with independent oracle rows; it imports nothing from `agentctl` | [Phase 0 — Governance, documentation standards and the check skeleton](phase-0-governance-and-check-skeleton.md) |
| Host observation | `tests/harness/host.py` | The one observation of the host states tests may branch on (login state, multiplexer kind, OS family, toolchain provenance) and of the lane predicates, recorded with the run's nonce for the lane summary | [Phase 1 — Gate-integrity apparatus](phase-1-gate-integrity-apparatus.md) |
| Nonces | `tests/harness/nonce.py` | A fresh nonce for each observer run | [Phase 1 — Gate-integrity apparatus](phase-1-gate-integrity-apparatus.md) |
| Local downloads | `tests/harness/http.py` | A loopback-only server with fixed complete, corrupt and truncated bodies, an independent request record, and explicit thread teardown | [Phase 2 — Toolchain bootstrap](phase-2-toolchain-bootstrap.md) |
| Bootstrap observations | `tests/harness/bootstrap.py`, `tests/harness/bootstrap_origin.py` | Owned contexts, typed native paths and independent filesystem observations before provisioning; a standard-library-only absence witness shared with the clean recipe | [Phase 2 — Toolchain bootstrap](phase-2-toolchain-bootstrap.md) |
| Native build fixtures | `tests/harness/haskell.py`, `tests/harness/binary.py` | Actual bundled sources and pinned tools, with owned source copies, build directories, homes, pin files and published data; only compiled dependencies are shared | [Phase 3 — Haskell package, quality legs and digest-keyed build](phase-3-haskell-package-and-build.md) |
| Private tmux servers | `tests/harness/tmux.py` | Servers with `TMUX_TMPDIR` set to a short temp dir and `TMUX` unset, and kill-server only after asserting the socket is under the run dir | [Phase 4 — Multiplexer adapter](phase-4-multiplexer-adapter.md) |
| Native launch callers | `tests/harness/launch.py`, `tests/harness/passthrough.py`, `tests/harness/terminal.py` | Private caller homes, native fake agents, nonce-bound mux-client relay records, real-agent trampoline panes, public callers in a second private server's native PTY, native child-notification controls and application-owned core invocation against the test's private server | [Phase 6 — Launch command and passthrough](phase-6-launch-and-passthrough.md) |
| Native session tables | `tests/harness/sessions.py` | Independently parses every required table column and JSON text cell for session-management and adoption controls | [Phase 7 — Session management and adoption](phase-7-session-management-and-adoption.md) |
| Supervisor observers | `tests/harness/supervisor.py`, `tests/e2e/test_scripted_fake.py` | Independently reads complete fake event records and validates byte counts, native timestamps, per-target identity and receiving controls | [Phase 10 — Recovery supervisor](phase-10-supervisor.md) |
| Scripted supervisor matrix | `tests/harness/supervisor_cases.py`, `tests/harness/supervisor_barrier.py`, `app/SupervisorFixture.hs` | Independent scenario expectations and real receiving controls; a compiled native relay holds guarded captures or refuses a literal after genuine logged proposals | [Phase 10 — Recovery supervisor](phase-10-supervisor.md) |
| Native supervisor lifecycle observer | `tests/harness/supervisor_signals.py`, `test/ConsoleFixture.hs`, `test/console_fixture.c` | Owned POSIX signals or isolated Windows console events, actual child exit before cleanup, unchanged targets and lock reuse | [Phase 10 — Recovery supervisor](phase-10-supervisor.md) |
| Isolated agent observations | `tests/harness/agents.py`, `tests/harness/evaluate.py` | Disposable agent configurations, file-only Codex credential storage, native auth/preflight probes and effective independent oracle comparisons | [Phase 5 — Agent adapters and preflight](phase-5-agent-adapters-and-preflight.md) |
| Command-surface and leg oracles | `tests/oracles/command_surface.toml`, `tests/oracles/check_legs.toml` | The command surface and the check legs | [Phase 0 — Governance, documentation standards and the check skeleton](phase-0-governance-and-check-skeleton.md) |
| Frozen oracles | `tests/oracles/launch_argv.toml`, `session_names.toml`, `preflight.toml`, `auth_status.toml`, `recovery_transitions.toml`, `backoff.toml`, `check_steps.toml`, `lint_config.toml` | Expected argv, names, preflight and auth outcomes, recovery transitions and backoff, authored before product code, plus the check steps and the frozen tool configuration | [Phase 1 — Gate-integrity apparatus](phase-1-gate-integrity-apparatus.md) |
| Bootstrap oracles | `tests/oracles/prerequisites.toml`, `bootstrap_plan.toml`, `pins.toml`, `toolchain_preconditions.toml` | Prerequisite sets, the provisioning plan, toolchain pins and capacity/network/platform boundaries | [Phase 2 — Toolchain bootstrap](phase-2-toolchain-bootstrap.md) |
| Multiplexer oracle | `tests/oracles/mux_commands.toml` | Independent native version floors, executable candidates, remedies and rendered tmux/psmux commands | [Phase 4 — Multiplexer adapter](phase-4-multiplexer-adapter.md) |
| Ownership oracle | `tests/oracles/session_ownership.toml` | Managed and adopted session behaviour | [Phase 7 — Session management and adoption](phase-7-session-management-and-adoption.md) |
| Supervisor oracles | `tests/oracles/forbidden_actions.toml`, `log_records.toml` | The actions the supervisor never takes, and the log records | [Phase 10 — Recovery supervisor](phase-10-supervisor.md) |
| Mutant corpus | `tests/mutants/<capability>.toml` | Mutant records (id, operator, exact-once patch, killers, reason substring); each phase adds records under its own prefixes | [Phase 1 — Gate-integrity apparatus](phase-1-gate-integrity-apparatus.md) |
| Static negatives | `tests/fixtures/static_negative/` | `*.py.txt` sources the static legs and source guards must reject, copied to a temp dir before use | [Phase 0 — Governance, documentation standards and the check skeleton](phase-0-governance-and-check-skeleton.md) |
| Validator negatives | `tests/fixtures/docs_negative/` | Minimal trees that each yield exactly one named validator violation | [Phase 0 — Governance, documentation standards and the check skeleton](phase-0-governance-and-check-skeleton.md) |
| Screen fixtures | `tests/fixtures/screens/<agent>/<class>/<id>.txt` | Screens with a provenance sidecar, `captured` or `documented`, that the classifiers are tested against | [Phase 8 — Pane observation and classification](phase-8-pane-observation-and-classification.md) |
| Screen fixture boundary | `tests/harness/screens.py` | Independent closed class vocabulary, complete agent/class matrix and strict provenance/precedence parsing | [Phase 8 — Pane observation and classification](phase-8-pane-observation-and-classification.md) |
| Live launch harness | `tests/harness/live.py` | Authentication-state branching, preserved native launch/argv/refusal observations and independent live classification without input | [Phase 8 — Pane observation and classification](phase-8-pane-observation-and-classification.md) |
| Test tiers | `tests/unit/`, `tests/integration/`, `tests/e2e/`, `tests/live/`, `tests/governance/` | The tier each test module lives in; every module is collected and cited (`tests.orphan-modules`, Sprint 0.3) | [Phase 0 — Governance, documentation standards and the check skeleton](phase-0-governance-and-check-skeleton.md) |
| Clean-lane recipe | `tests/lanes/clean-host.Dockerfile` | The two-stage recipe of the clean-container lane, run as a non-root user with NOPASSWD sudo | [Phase 2 — Toolchain bootstrap](phase-2-toolchain-bootstrap.md) |

`tests/support.txt` declares support modules for the collection join; `tests/harness/trees.py` constructs negative governed trees from fixture edit instructions. Both belong to [Phase 0 — Governance, documentation standards and the check skeleton](phase-0-governance-and-check-skeleton.md).

`tests/harness/git.py` constructs disposable git object fixtures for the run-integrity checks, owned by [Phase 1 — Gate-integrity apparatus](phase-1-gate-integrity-apparatus.md).

## External Tools

This table says who invokes each tool and how. Versions, pins and floors are in
[external tool facts](../documents/reference/external_tool_facts.md),
[the toolchain bootstrap](../documents/engineering/toolchain_bootstrap.md) and
[the multiplexer adapter](../documents/architecture/multiplexer_adapter.md).

| Tool | Invoked by | How | Owning phase |
|---|---|---|---|
| pipx | the user | `pipx install` to use agentctl; an editable install of a checkout, `pipx install --editable '.[dev]'` or `uv tool install --editable '.[dev]'`, to run check (precondition P1) | [Phase 0 — Governance, documentation standards and the check skeleton](phase-0-governance-and-check-skeleton.md) |
| ghcup | `bootstrap/ghcup.py` and `bootstrap/toolchain.py`, through `process.py` | An existing ghcup at or above the floor is reused, never replaced or upgraded; otherwise the pinned binary is downloaded with urllib and its SHA-256 verified. It installs GHC without `--set` and cabal with `--no-set`, and `ghcup whereis` gives their paths | [Phase 2 — Toolchain bootstrap](phase-2-toolchain-bootstrap.md) |
| ghc | cabal, given the absolute path from `ghcup whereis`; `bootstrap/toolchain.py` | Always by absolute path, never through the user's default selection; warm runs verify it with `--numeric-version` | [Phase 2 — Toolchain bootstrap](phase-2-toolchain-bootstrap.md) |
| cabal | `bootstrap/build.py` and `check/legs.py` | By absolute path: the `cabal-build` and `cabal-test` legs, `cabal list-bin` for binary identity, and building the pinned fourmolu and hlint into `cache/tools/<pin-digest>` | [Phase 3 — Haskell package, quality legs and digest-keyed build](phase-3-haskell-package-and-build.md) |
| fourmolu | `check/legs.py` | From `cache/tools/<pin-digest>`, in check mode, with the repository `fourmolu.yaml` | [Phase 3 — Haskell package, quality legs and digest-keyed build](phase-3-haskell-package-and-build.md) |
| hlint | `check/legs.py` | From `cache/tools/<pin-digest>`, with the repository `.hlint.yaml`, which has no ignores | [Phase 3 — Haskell package, quality legs and digest-keyed build](phase-3-haskell-package-and-build.md) |
| ruff | `check/legs.py` | From agentctl's own environment: `ruff check` and `ruff format --check`, with `select = ["ALL"]` | [Phase 0 — Governance, documentation standards and the check skeleton](phase-0-governance-and-check-skeleton.md) |
| ty | `check/legs.py` | `ty check` with `--python sys.executable`, an isolated config home, `all = "error"`, `respect-type-ignore-comments = false` and error-on-warning | [Phase 0 — Governance, documentation standards and the check skeleton](phase-0-governance-and-check-skeleton.md) |
| pytest | `check/legs.py` | The entire suite, with the gate plugin, `strict = true` and `filterwarnings = ["error"]`; pytester inside the suite | [Phase 0 — Governance, documentation standards and the check skeleton](phase-0-governance-and-check-skeleton.md) |
| coverage | `check/legs.py` | Wraps the pytest leg with branch coverage and a fail-under of 100 | [Phase 1 — Gate-integrity apparatus](phase-1-gate-integrity-apparatus.md) |
| tmux | the binary through `AgentCtl.Process`, rendered by `AgentCtl.Mux.Tmux`; tests through `tests/harness/tmux.py` | Resolved once to an absolute path and held to its floor. Sessions live on the user's normal server and are targeted as `=NAME`; tests use private servers only | [Phase 4 — Multiplexer adapter](phase-4-multiplexer-adapter.md) |
| psmux | the binary through `AgentCtl.Process`, rendered by `AgentCtl.Mux.Psmux` | Always as `psmux`, never its `tmux` alias, held to its floor; tests set `PSMUX_DATA_DIR` and `PSMUX_NO_WARM=1` | [Phase 4 — Multiplexer adapter](phase-4-multiplexer-adapter.md) |
| claude | `AgentCtl.Agent.Auth`; the pane, through `AgentCtl.PaneExec` | `claude auth status`, judged by exit code alone, with a timeout. The pane runs the resolved executable (native `claude.exe` on Windows) with `--dangerously-skip-permissions` at the end, or before the first bare `--` | [Phase 5 — Agent adapters and preflight](phase-5-agent-adapters-and-preflight.md) |
| codex | `AgentCtl.Agent.Auth`; the pane, through `AgentCtl.PaneExec` | `codex login status`, judged by exit code alone, with a timeout. The pane runs the resolved executable (native `codex.exe` on Windows) with `--dangerously-bypass-approvals-and-sandbox --no-daemon` at the end, or before the first bare `--` | [Phase 5 — Agent adapters and preflight](phase-5-agent-adapters-and-preflight.md) |
| OS package managers | `bootstrap/prereqs.py`, through `process.py` | `apt`, `dnf` or `pacman` after consent, with `sudo` when interactive and `sudo -n` or `--assume-yes` otherwise; `xcode-select --install` on macOS. Tests never run one: the spawn audit vetoes it | [Phase 2 — Toolchain bootstrap](phase-2-toolchain-bootstrap.md) |
| C compiler, make, curl or wget | `bootstrap/prereqs.py` probes them; ghcup uses them | Presence checks and a link test against `-lgmp`; ghcup downloads with curl or wget and installs GHC bindists with make | [Phase 2 — Toolchain bootstrap](phase-2-toolchain-bootstrap.md) |
| git | `check/preconditions.py` and `check/ratchet.py` | Read-only: precondition P4 requires a work tree, and the ratchet reads HEAD; agentctl never changes the repository | [Phase 0 — Governance, documentation standards and the check skeleton](phase-0-governance-and-check-skeleton.md) |
| docker | the agent closing the clean-host phase, on a gate host | Clean lane only: builds and runs `tests/lanes/clean-host.Dockerfile`. Neither agentctl nor check invokes it | [Phase 12 — Clean-host bootstrap acceptance](phase-12-clean-container-acceptance.md) |

## Per-User Directories

`src/agentctl/paths.py` decides three directories, honouring XDG overrides on every OS, and passes them to the binary,
which computes none. Their platform defaults and the format of every file in them are in
[files and state](../documents/reference/files_and_state.md), the canonical home.

| Directory | Holds | Owning phase |
|---|---|---|
| `cache` | Build trees under `cache/build/<digest>`, and the pinned fourmolu and hlint under `cache/tools/<pin-digest>` | [Phase 3 — Haskell package, quality legs and digest-keyed build](phase-3-haskell-package-and-build.md) |
| `data` | Binaries published atomically into `data/bin/<digest>`, never on PATH | [Phase 3 — Haskell package, quality legs and digest-keyed build](phase-3-haskell-package-and-build.md) |
| `state` | Locks, starting with check's single-run lock | [Phase 0 — Governance, documentation standards and the check skeleton](phase-0-governance-and-check-skeleton.md) |
| `state` | Launch specs: 0600 files in a 0700 directory, each deleted by the pane trampoline after reading | [Phase 6 — Launch command and passthrough](phase-6-launch-and-passthrough.md) |
| `state` | The adopted-pane registry | [Phase 7 — Session management and adoption](phase-7-session-management-and-adoption.md) |
| `state` | The watch set, the JSONL log and the supervisor lock | [Phase 10 — Recovery supervisor](phase-10-supervisor.md) |

## Update Rule

- Change this inventory in the same change as the component it lists, the phase that builds it and the document that
  owns its contract.
- A row's owning phase is the phase that introduces the component. A later phase that extends it lists the path in
  its own sprint's `**Implementation**`, and the row names that phase where the extension is part of the component's
  responsibility.
- Rows use registry names verbatim and carry no status, no counts and no API sketches.
- No validator compares this inventory with the tree; agents keep it aligned with the components they change.
  Human review is optional and never a completion condition.

## Related

- [README.md](README.md) — the status table this inventory defers to.
- [development_plan_standards.md](development_plan_standards.md) — § F, the rule that the inventory owns no contract.
- [00-overview.md](00-overview.md) — the architecture these components realise.
- [python_haskell_boundary.md](../documents/architecture/python_haskell_boundary.md) — the split between the two packages.
- [files_and_state.md](../documents/reference/files_and_state.md) — the canonical home of the per-user directories.
- [testing.md](../documents/engineering/testing.md) — how the test apparatus is used.
