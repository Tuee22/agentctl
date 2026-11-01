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
| OS prerequisites | `src/agentctl/bootstrap/prereqs.py` | Probes the C compiler and linker, `-lgmp`, curl or wget, CA certificates and make; asks for consent, then runs the OS package manager | [Phase 2 — Toolchain bootstrap](phase-2-toolchain-bootstrap.md) |
| ghcup | `src/agentctl/bootstrap/ghcup.py` | Reuses an existing ghcup at or above the floor; otherwise downloads the pinned ghcup with urllib and verifies its SHA-256. Never runs the official bootstrap script, never edits rc files | [Phase 2 — Toolchain bootstrap](phase-2-toolchain-bootstrap.md) |
| Toolchain | `src/agentctl/bootstrap/toolchain.py` | Installs the pinned GHC and cabal without changing the user's default, resolves their absolute paths, and runs as the `toolchain-ensure` check step | [Phase 2 — Toolchain bootstrap](phase-2-toolchain-bootstrap.md) |
| Pins | `src/agentctl/bootstrap/pins.toml` | Package data: the ghcup, GHC and cabal pins, the ghcup floor, and the fourmolu and hlint pins | [Phase 2 — Toolchain bootstrap](phase-2-toolchain-bootstrap.md) |
| Build | `src/agentctl/bootstrap/build.py` | The digest over the Cabal project and pins, the one build function check and passthrough share, atomic publish into `data`, and the `binary-identity` step | [Phase 3 — Haskell package, quality legs and digest-keyed build](phase-3-haskell-package-and-build.md) |
| Handoff | `src/agentctl/bootstrap/handoff.py` | Ensures the binary for the current digest and hands off to it: `execve` on POSIX, a child process whose exit status is propagated on Windows | [Phase 6 — Launch command and passthrough](phase-6-launch-and-passthrough.md) |
| Haskell project | `src/agentctl/haskell/` | The Cabal project, shipped as package data with no hatchling force-include | [Phase 3 — Haskell package, quality legs and digest-keyed build](phase-3-haskell-package-and-build.md) |
| Check legs | `src/agentctl/check/legs.py` | The legs of `tests/oracles/check_legs.toml`: each leg's argv, environment and non-empty target set | [Phase 0 — Governance, documentation standards and the check skeleton](phase-0-governance-and-check-skeleton.md) |
| Check steps | `src/agentctl/check/steps.py` | The ordered steps of `tests/oracles/check_steps.toml`, the scrubbed environment allowlist, and the verdict: a step or leg that fails or does not run fails check | [Phase 0 — Governance, documentation standards and the check skeleton](phase-0-governance-and-check-skeleton.md) |
| Preconditions | `src/agentctl/check/preconditions.py` | Preconditions P1–P10, each with its remedy | [Phase 0 — Governance, documentation standards and the check skeleton](phase-0-governance-and-check-skeleton.md) |
| Gate plugin | `src/agentctl/check/gate_plugin.py` | The pytest plugin check loads: it fails the session on any skip, xfail, deselection or selection, records collected and executed ids with the run's nonce, and runs `tests.orphan-modules` | [Phase 0 — Governance, documentation standards and the check skeleton](phase-0-governance-and-check-skeleton.md) |
| Documentation validator | `src/agentctl/check/validator/docs.py` | The `docs.*` checks | [Phase 0 — Governance, documentation standards and the check skeleton](phase-0-governance-and-check-skeleton.md) |
| Plan validator | `src/agentctl/check/validator/plan.py` | The `plan.*` checks | [Phase 0 — Governance, documentation standards and the check skeleton](phase-0-governance-and-check-skeleton.md) |
| Mutant runner | `src/agentctl/check/mutants.py` | Applies exact-match patches to scratch copies, runs named killers and checks the named failure reason | [Phase 1 — Gate-integrity apparatus](phase-1-gate-integrity-apparatus.md) |
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
| Style configuration | `fourmolu.yaml`, `.hlint.yaml` | The committed formatter and linter configuration, with no ignores | [Phase 3 — Haskell package, quality legs and digest-keyed build](phase-3-haskell-package-and-build.md) |
| Source roots | `app/`, `src/`, `test/` | The executables' mains, the `AgentCtl.*` library and the tasty suite | [Phase 3 — Haskell package, quality legs and digest-keyed build](phase-3-haskell-package-and-build.md) |
| `agentctl-core` | executable in `agentctl-core.cabal` | The core binary: never on PATH and refuses to run without the handoff. It dispatches `claude` and `codex` on the raw arguments before option parsing and names itself `agentctl` in usage text, both from [Phase 6 — Launch command and passthrough](phase-6-launch-and-passthrough.md) | [Phase 3 — Haskell package, quality legs and digest-keyed build](phase-3-haskell-package-and-build.md) |
| `agentctl-core-eval` | executable in `agentctl-core.cabal` | Reads JSON cases on stdin, applies pure Haskell subjects and prints results, which Python compares with oracle rows | [Phase 3 — Haskell package, quality legs and digest-keyed build](phase-3-haskell-package-and-build.md) |
| `agentctl-fake-agent` | executable in `agentctl-core.cabal`, outside suite routing | The observer stand-in, copied into a temp bin as `claude` or `codex`; records argv, cwd, environment keys, the multiplexer session and the nonce | [Phase 4 — Multiplexer adapter](phase-4-multiplexer-adapter.md) |
| `agentctl-core-test` | test suite in `agentctl-core.cabal`, under `test/` | The tasty suite the `cabal-test` leg runs; its cases are cited as `haskell:agentctl-core-test/<Group>/<case>` | [Phase 3 — Haskell package, quality legs and digest-keyed build](phase-3-haskell-package-and-build.md) |
| `AgentCtl.Protocol` | `src/AgentCtl/Protocol.hs` | The handshake (protocol version and command list) and the refusal to run without Python's handoff | [Phase 3 — Haskell package, quality legs and digest-keyed build](phase-3-haskell-package-and-build.md) |
| `AgentCtl.Process` | `src/AgentCtl/Process.hs` | The one runner: it interprets typed commands and performs every spawn and exec in the binary, and it is the only importer of `System.Process` | [Phase 4 — Multiplexer adapter](phase-4-multiplexer-adapter.md) |
| `AgentCtl.Mux` | `src/AgentCtl/Mux.hs` | Resolves tmux (Linux, macOS) or psmux (Windows) to an absolute path and enforces the version floors | [Phase 4 — Multiplexer adapter](phase-4-multiplexer-adapter.md) |
| `AgentCtl.Mux.Command` | `src/AgentCtl/Mux/Command.hs` | The typed multiplexer command vocabulary, with exact `=NAME` targets | [Phase 4 — Multiplexer adapter](phase-4-multiplexer-adapter.md) |
| `AgentCtl.Mux.Tmux` | `src/AgentCtl/Mux/Tmux.hs` | Renders the vocabulary as tmux argv | [Phase 4 — Multiplexer adapter](phase-4-multiplexer-adapter.md) |
| `AgentCtl.Mux.Psmux` | `src/AgentCtl/Mux/Psmux.hs` | Renders the vocabulary as psmux argv, always invoking `psmux`, never its `tmux` alias | [Phase 4 — Multiplexer adapter](phase-4-multiplexer-adapter.md) |
| `AgentCtl.PaneExec` | `src/AgentCtl/PaneExec.hs` | The pane trampoline `agentctl-core pane-exec <spec>`: reads and deletes the 0600 spec, then, through `AgentCtl.Process`, calls `execve` on POSIX, or runs the agent as a child and writes a status file on Windows | [Phase 4 — Multiplexer adapter](phase-4-multiplexer-adapter.md) |
| `AgentCtl.Session.Name` | `src/AgentCtl/Session/Name.hs` | The `SessionName` smart constructor (`[A-Za-z0-9_-]`, never `__`, never empty). Its derivation from the canonical folder, and the hash form for a different folder with the same base, come from [Phase 6 — Launch command and passthrough](phase-6-launch-and-passthrough.md) | [Phase 4 — Multiplexer adapter](phase-4-multiplexer-adapter.md) |
| `AgentCtl.Agent` | `src/AgentCtl/Agent.hs` | The agent table: executable, mandatory flags and their aliases, auth-status command, login remedy | [Phase 5 — Agent adapters and preflight](phase-5-agent-adapters-and-preflight.md) |
| `AgentCtl.Agent.Argv` | `src/AgentCtl/Agent/Argv.hs` | Launch argv assembly: removes user copies of the mandatory flags, appends them at the end or immediately before the first bare `--`, and refuses login-shaped ARGS | [Phase 5 — Agent adapters and preflight](phase-5-agent-adapters-and-preflight.md) |
| `AgentCtl.Agent.Auth` | `src/AgentCtl/Agent/Auth.hs` | Classifies auth-status exit codes (0 logged in, 1 logged out, anything else or a timeout check failed) and renders the remedy the user types | [Phase 5 — Agent adapters and preflight](phase-5-agent-adapters-and-preflight.md) |
| `AgentCtl.Preflight` | `src/AgentCtl/Preflight.hs` | Checks the multiplexer, then the agent, then auth; success is the opaque `Ready`, whose constructor is not exported | [Phase 5 — Agent adapters and preflight](phase-5-agent-adapters-and-preflight.md) |
| `AgentCtl.Paths` | `src/AgentCtl/Paths.hs` | Receives the per-user directories Python passes in; computes none | [Phase 6 — Launch command and passthrough](phase-6-launch-and-passthrough.md) |
| `AgentCtl.Launch` | `src/AgentCtl/Launch.hs` | Create-or-attach, instant-exit capture, failure cleanup with the warning on the caller's terminal, no-TTY and `$TMUX` handling, and the `@agentctl_agent`, `@agentctl_folder` and `@agentctl_owner` session options | [Phase 6 — Launch command and passthrough](phase-6-launch-and-passthrough.md) |
| `AgentCtl.Sessions` | `src/AgentCtl/Sessions.hs` | `list`, `status`, `attach` and `stop` over managed sessions, identified by their session options | [Phase 7 — Session management and adoption](phase-7-session-management-and-adoption.md) |
| `AgentCtl.Adopt` | `src/AgentCtl/Adopt.hs` | The adopted-pane registry; `stop` on an adopted pane forgets it and never kills it | [Phase 7 — Session management and adoption](phase-7-session-management-and-adoption.md) |
| `AgentCtl.Observe.Capture` | `src/AgentCtl/Observe/Capture.hs` | Pane capture | [Phase 8 — Pane observation and classification](phase-8-pane-observation-and-classification.md) |
| `AgentCtl.Observe.Normalize` | `src/AgentCtl/Observe/Normalize.hs` | Normalisation of captured screens | [Phase 8 — Pane observation and classification](phase-8-pane-observation-and-classification.md) |
| `AgentCtl.Observe.Fingerprint` | `src/AgentCtl/Observe/Fingerprint.hs` | Error fingerprints, so stale scrollback never re-triggers | [Phase 8 — Pane observation and classification](phase-8-pane-observation-and-classification.md) |
| `AgentCtl.Observe.Classify.Claude`, `AgentCtl.Observe.Classify.Codex` | `src/AgentCtl/Observe/Classify/Claude.hs`, `src/AgentCtl/Observe/Classify/Codex.hs` | Per-agent classifiers onto the closed screen-class vocabulary of the supervisor contract | [Phase 8 — Pane observation and classification](phase-8-pane-observation-and-classification.md) |
| `AgentCtl.Recovery.Machine` | `src/AgentCtl/Recovery/Machine.hs` | The pure transition function over the recovery states, and its safety predicates | [Phase 9 — Recovery state machine and backoff](phase-9-recovery-state-machine.md) |
| `AgentCtl.Recovery.Backoff` | `src/AgentCtl/Recovery/Backoff.hs` | Bounded exponential backoff with seeded jitter, and escalation | [Phase 9 — Recovery state machine and backoff](phase-9-recovery-state-machine.md) |
| `AgentCtl.Supervisor.Watch` | `src/AgentCtl/Supervisor/Watch.hs` | `watch`, `unwatch`, `pause` and `resume-watch`, and the persisted watch set | [Phase 10 — Recovery supervisor](phase-10-supervisor.md) |
| `AgentCtl.Supervisor` | `src/AgentCtl/Supervisor.hs` | `supervisor run`, the foreground poll loop: it re-captures and re-classifies immediately before `send-keys -l` and aborts if the screen changed | [Phase 10 — Recovery supervisor](phase-10-supervisor.md) |
| `AgentCtl.Supervisor.Lock` | `src/AgentCtl/Supervisor/Lock.hs` | The single-instance supervisor lock | [Phase 10 — Recovery supervisor](phase-10-supervisor.md) |
| `AgentCtl.Supervisor.Log` | `src/AgentCtl/Supervisor/Log.hs` | The JSONL record of every observation, decision, attempt and result, and the `logs` command | [Phase 10 — Recovery supervisor](phase-10-supervisor.md) |

## Test Apparatus

How each piece is used, and what each evidence class proves, is in [testing](../documents/engineering/testing.md).

| Component | Path | Responsibility | Owning phase |
|---|---|---|---|
| Oracle comparison | `tests/harness/oracle.py` | `assert_oracle`, the one comparison of subject results with committed oracle rows; it imports nothing from `agentctl` | [Phase 0 — Governance, documentation standards and the check skeleton](phase-0-governance-and-check-skeleton.md) |
| Host observation | `tests/harness/host.py` | The one observation of the host states tests may branch on (login state, multiplexer kind, OS family, toolchain provenance) and of the lane predicates, recorded with the run's nonce for the lane summary | [Phase 1 — Gate-integrity apparatus](phase-1-gate-integrity-apparatus.md) |
| Nonces | `tests/harness/nonce.py` | A fresh nonce for each observer run | [Phase 1 — Gate-integrity apparatus](phase-1-gate-integrity-apparatus.md) |
| Private tmux servers | `tests/harness/tmux.py` | Servers with `TMUX_TMPDIR` set to a short temp dir and `TMUX` unset, and kill-server only after asserting the socket is under the run dir | [Phase 4 — Multiplexer adapter](phase-4-multiplexer-adapter.md) |
| Command-surface and leg oracles | `tests/oracles/command_surface.toml`, `tests/oracles/check_legs.toml` | The command surface and the check legs | [Phase 0 — Governance, documentation standards and the check skeleton](phase-0-governance-and-check-skeleton.md) |
| Frozen oracles | `tests/oracles/launch_argv.toml`, `session_names.toml`, `preflight.toml`, `auth_status.toml`, `recovery_transitions.toml`, `backoff.toml`, `check_steps.toml`, `lint_config.toml` | Expected argv, names, preflight and auth outcomes, recovery transitions and backoff, authored before product code, plus the check steps and the frozen tool configuration | [Phase 1 — Gate-integrity apparatus](phase-1-gate-integrity-apparatus.md) |
| Bootstrap oracles | `tests/oracles/prerequisites.toml`, `bootstrap_plan.toml`, `pins.toml` | Prerequisite sets, the provisioning plan and the toolchain pins | [Phase 2 — Toolchain bootstrap](phase-2-toolchain-bootstrap.md) |
| Multiplexer oracle | `tests/oracles/mux_commands.toml` | Rendered tmux and psmux commands | [Phase 4 — Multiplexer adapter](phase-4-multiplexer-adapter.md) |
| Ownership oracle | `tests/oracles/session_ownership.toml` | Managed and adopted session behaviour | [Phase 7 — Session management and adoption](phase-7-session-management-and-adoption.md) |
| Supervisor oracles | `tests/oracles/forbidden_actions.toml`, `log_records.toml` | The actions the supervisor never takes, and the log records | [Phase 10 — Recovery supervisor](phase-10-supervisor.md) |
| Mutant corpus | `tests/mutants/<capability>.toml` | Mutant records (id, operator, exact-once patch, killers, reason substring); each phase adds records under its own prefixes | [Phase 1 — Gate-integrity apparatus](phase-1-gate-integrity-apparatus.md) |
| Static negatives | `tests/fixtures/static_negative/` | `*.py.txt` sources the static legs and source guards must reject, copied to a temp dir before use | [Phase 0 — Governance, documentation standards and the check skeleton](phase-0-governance-and-check-skeleton.md) |
| Validator negatives | `tests/fixtures/docs_negative/` | Minimal trees that each yield exactly one named validator violation | [Phase 0 — Governance, documentation standards and the check skeleton](phase-0-governance-and-check-skeleton.md) |
| Screen fixtures | `tests/fixtures/screens/<agent>/<class>/<id>.txt` | Screens with a provenance sidecar, `captured` or `documented`, that the classifiers are tested against | [Phase 8 — Pane observation and classification](phase-8-pane-observation-and-classification.md) |
| Test tiers | `tests/unit/`, `tests/integration/`, `tests/e2e/`, `tests/live/`, `tests/governance/` | The tier each test module lives in; every module is collected and cited (`tests.orphan-modules`, Sprint 0.3) | [Phase 0 — Governance, documentation standards and the check skeleton](phase-0-governance-and-check-skeleton.md) |
| Clean-lane recipe | `tests/lanes/clean-host.Dockerfile` | The two-stage recipe of the clean-container lane, run as a non-root user with NOPASSWD sudo | [Phase 2 — Toolchain bootstrap](phase-2-toolchain-bootstrap.md) |

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
| fourmolu | `check/legs.py` | From `cache/tools/<pin-digest>`, in check mode, with the committed `fourmolu.yaml` | [Phase 3 — Haskell package, quality legs and digest-keyed build](phase-3-haskell-package-and-build.md) |
| hlint | `check/legs.py` | From `cache/tools/<pin-digest>`, with the committed `.hlint.yaml`, which has no ignores | [Phase 3 — Haskell package, quality legs and digest-keyed build](phase-3-haskell-package-and-build.md) |
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
- No validator compares this inventory with the tree; it stays accurate because the user reviews each change against
  it.

## Related

- [README.md](README.md) — the status table this inventory defers to.
- [development_plan_standards.md](development_plan_standards.md) — § F, the rule that the inventory owns no contract.
- [00-overview.md](00-overview.md) — the architecture these components realise.
- [python_haskell_boundary.md](../documents/architecture/python_haskell_boundary.md) — the split between the two packages.
- [files_and_state.md](../documents/reference/files_and_state.md) — the canonical home of the per-user directories.
- [testing.md](../documents/engineering/testing.md) — how the test apparatus is used.
