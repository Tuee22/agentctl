# Phase 5 — Agent adapters and preflight

**Status**: Planned
**Depends on**: [Phase 4 — Multiplexer adapter](phase-4-multiplexer-adapter.md)
**Host lane**: agent-host
**Gate**: `agentctl check`
**Gate kind**: self-verifying
**Closes**: R12.2, R13

> **Purpose**: Give the core binary each agent's table and pure launch argv, an exit-code-only login check with the remedy the user types, the refusal of login-shaped ARGS, and a preflight whose only success is the opaque `Ready`.

## Phase Objective

This phase builds every agent-specific decision the launch command needs, before any session exists.
`AgentCtl.Agent` holds one closed table per agent, `AgentCtl.Agent.Argv` turns the user's ARGS into
the final argv, `AgentCtl.Agent.Auth` classifies the login probe by exit code alone, and
`AgentCtl.Preflight` runs the three checks in the order multiplexer, agent, auth. Its only success is
`Ready`, whose constructor is not exported, so code that creates a session without a passing
preflight does not compile.

Ownership across phases:

- `launchArgv` lands here with value evidence for R9, R10 and R11. Those requirements close where the
  whole stack is observed: R10 and R11 in Sprint 6.2, through the fake agent's argv record and the
  live `/proc/<pane_pid>/cmdline` check, and R9 in Sprint 6.3, through the raw passthrough.
- No phase keeps a subcommand, conflict or informational-flag table. An argv the agent itself
  rejects, such as codex's `-a never` beside the bypass flag, reaches the agent unchanged and is
  relayed by instant-exit capture, which [Phase 6 — Launch command and passthrough](phase-6-launch-and-passthrough.md)
  builds. The login refusals are the one table, because forwarding them would make agentctl log in.
- The per-agent recovery text lives in the agent table; the supervisor of
  [Phase 10 — Recovery supervisor](phase-10-supervisor.md) is the only code that sends it.

Every real agent run in this phase is logged out by construction: an empty `CLAUDE_CONFIG_DIR`, an
empty `CODEX_HOME` whose `config.toml` sets `cli_auth_credentials_store = "file"`, the auth
environment variables removed and `DISABLE_AUTOUPDATER=1`. The user's login state therefore never
changes what these tests assert, and no test reads or writes a credential.

## Gate Integrity

| Requirement | Oracle | Observer | Mutants | Tests |
|---|---|---|---|---|
| R13 — a logged-out agent yields a warning naming the discrete login command, and agentctl never runs a login or forwards login-shaped ARGS | `tests/oracles/auth_status.toml` | value: agentctl-core-eval classifyAuth, remedy and login-refusal cases; real: logged-out claude and codex with isolated config dirs; observer: fake agent invocation record with nonce, holding the auth-status probe and no login invocation; owed: macos-acceptance | `M-auth-exit2-as-logged-out`, `M-auth-remedy-wrong-command`, `M-auth-pass-setup-token` | `tests/unit/test_auth_status.py::test_classify_auth_matches_oracle`, `tests/unit/test_auth_status.py::test_remedy_names_the_command_to_type`, `tests/unit/test_auth_status.py::test_login_shaped_args_refused`, `tests/integration/test_agent_real.py::test_logged_out_by_construction`, `tests/integration/test_agent_auth_probe.py::test_preflight_never_runs_login` |
| R12.2 — the agent CLI is resolved and its login checked before any session exists | `tests/oracles/preflight.toml` | value: agentctl-core-eval preflight decision, warning and agent-resolution cases; real: constructed PATH without the agent, compile-fail fixture with its compiling twin; observer: fake agent records no invocation while the multiplexer is missing; owed: windows-psmux-acceptance | `M-preflight-auth-before-mux`, `M-preflight-export-ready-constructor`, `M-preflight-accept-cmd-shim` | `tests/unit/test_preflight.py::test_failure_warnings_match_oracle`, `tests/unit/test_agent_resolution.py::test_resolution_matches_oracle`, `tests/integration/test_preflight.py::test_order_mux_then_agent_then_auth`, `tests/integration/test_preflight.py::test_missing_agent_names_install_hint`, `tests/integration/test_ready_opaque.py::test_ready_constructor_is_not_exported` |
| R10 — the claude argv ends with `--dangerously-skip-permissions`, placed before a first bare `--` | `tests/oracles/launch_argv.toml` | value: agentctl-core-eval launchArgv cases; real: claude `--help` canary with a nonce-named negative control | `M-argv-flags-after-dashdash`, `M-argv-misspell-skip-permissions` | `tests/unit/test_launch_argv.py::test_launch_argv_matches_oracle`, `tests/integration/test_agent_real.py::test_help_canaries_list_mandatory_flags` |
| R11 — the codex argv ends with `--dangerously-bypass-approvals-and-sandbox --no-daemon`, placed before a first bare `--` | `tests/oracles/launch_argv.toml` | value: agentctl-core-eval launchArgv cases and the codex table row; real: codex `--help` canaries with a nonce-named negative control | `M-argv-keep-yolo`, `M-argv-drop-no-daemon` | `tests/unit/test_launch_argv.py::test_launch_argv_matches_oracle`, `tests/unit/test_agent_table.py::test_agent_table_matches_oracle`, `tests/integration/test_agent_real.py::test_help_canaries_list_mandatory_flags` |
| R9 — ARGS pass through verbatim apart from removed copies of the mandatory flags | `tests/oracles/launch_argv.toml` | value: agentctl-core-eval launchArgv cases and an order-preservation property | `M-argv-dedupe-past-dashdash`, `M-argv-keep-yolo` | `tests/unit/test_launch_argv.py::test_launch_argv_matches_oracle`, `haskell:agentctl-core-test/Argv/user-order-and-single-flags` |

## Not Proven By This Gate

- That a real logged-in agent passes the auth probe and accepts the final argv in a live pane. — owed to [Phase 11 — Live agent acceptance](phase-11-live-agent-acceptance.md).
- That `CLAUDE_CONFIG_DIR` also keys the macOS Keychain entry, so the logged-out-by-construction runs stay logged out on Darwin. — owed to [Phase 13 — macOS acceptance](phase-13-macos-acceptance.md).
- Native `.exe` resolution through a real Windows PATH and PATHEXT, and the refusal of a real npm `.cmd` shim. — owed to [Phase 14 — Windows and psmux acceptance](phase-14-windows-psmux-acceptance.md).
- Whether `claude auth status` exits 0 for an `ANTHROPIC_API_KEY` the user has not yet approved, or for an `apiKeyHelper` it does not run. — not proven by any phase.
- Exit-code semantics and mandatory flags at agent versions other than the one the run observes. — not proven by any phase.
- Tamper resistance is bounded by [§ P](development_plan_standards.md#p-the-ratchet-and-the-users-commit-points): it holds against a HEAD the user has committed. — not proven by any phase.

## Sprints

### Sprint 5.1: Agent table and launch argv [Planned]

**Status**: Planned
**Implementation**: `src/agentctl/haskell/src/AgentCtl/Agent.hs`, `src/agentctl/haskell/src/AgentCtl/Agent/Argv.hs`, `src/agentctl/haskell/app/`, `src/agentctl/haskell/test/`, `tests/unit/test_launch_argv.py`, `tests/unit/test_agent_table.py`
**Validation tests**: `tests/unit/test_launch_argv.py::test_launch_argv_matches_oracle`, `tests/unit/test_agent_table.py::test_agent_table_matches_oracle`, `haskell:agentctl-core-test/Argv/user-order-and-single-flags`, `haskell:agentctl-core-test/Agent/recovery-text-is-plain`
**Mutants**: `M-argv-flags-after-dashdash`, `M-argv-keep-yolo`, `M-argv-dedupe-past-dashdash`, `M-argv-drop-no-daemon`, `M-argv-misspell-skip-permissions`, `M-argv-recovery-slash-command`
**Closes**: none
**Docs to update**: `documents/architecture/launch_contract.md`, `documents/reference/external_tool_facts.md`

#### Objective

Make each agent a closed table entry and its final argv a pure function of the user's ARGS.

#### Deliverables

- `AgentCtl.Agent` defines the closed agent type, claude and codex, and one table row per agent: the
  executable name (native `claude.exe` and `codex.exe` on Windows), the mandatory flags in order, the
  removable aliases, the auth-status argv, the login remedy text, the per-OS install hints and the
  recovery text.
- Mandatory flags: claude `--dangerously-skip-permissions`; codex
  `--dangerously-bypass-approvals-and-sandbox` then `--no-daemon`. Codex's only removable alias is
  `--yolo`, the alias of its bypass flag.
- Auth-status argv: `claude auth status` and `codex login status`. Remedy text: `claude auth login`,
  with `--console` for Console billing and `--sso` named as variants, and `codex login`, with
  `codex login --device-auth` for a headless or SSH host.
- Install hints come from the official commands in external tool facts: for claude,
  `curl -fsSL https://claude.ai/install.sh | bash` on macOS and Linux and
  `winget install Anthropic.ClaudeCode` on Windows; for codex,
  `curl -fsSL https://chatgpt.com/codex/install.sh | sh` on macOS and Linux and the official
  PowerShell installer on Windows.
- `AgentCtl.Agent.Argv.launchArgv` keeps ARGS verbatim, removes every element before the first bare
  `--` that equals a mandatory flag or a removable alias (codex exits 2 on a repeated flag), then
  inserts the mandatory flags immediately before that `--`, or appends them when there is none.
- Elements after the first bare `--` are positional text: they are never removed or reordered, so
  `-- --yolo` reaches codex as text after its flags.
- The recovery text equals the constant in [decision D-48](rationale.md#decisions), frozen in the
  agent-table rows of `tests/oracles/launch_argv.toml`. It is one line with no leading `/`, so it
  can never be a slash command such as `/model` or `/login`.
- `agentctl-core-eval` gains the `launchArgv` and agent-table subjects, which Python compares with
  `tests/oracles/launch_argv.toml` and `tests/oracles/auth_status.toml`.

#### Validation

1. `launchArgv` equals every row of `tests/oracles/launch_argv.toml`, including empty ARGS, user copies of each mandatory flag, `--yolo`, a bare `--`, `-- --yolo` and a second `--` — `tests/unit/test_launch_argv.py::test_launch_argv_matches_oracle`; fails when the flags land after the first bare `--`, a user `--yolo` survives, or a `--yolo` after `--` is removed; mutants `M-argv-flags-after-dashdash`, `M-argv-keep-yolo`, `M-argv-dedupe-past-dashdash`.
2. For generated ARGS, the result holds each mandatory flag exactly once before the first bare `--`, counting `--yolo` as the bypass flag, and every other user element in its original order — `haskell:agentctl-core-test/Argv/user-order-and-single-flags`; fails when dedupe reorders the user's elements or keeps an alias; mutant `M-argv-keep-yolo`.
3. The agent table's executables, mandatory flags, aliases, auth-status argv, remedies and literal recovery texts equal the oracle rows — `tests/unit/test_agent_table.py::test_agent_table_matches_oracle`; fails when the codex row drops `--no-daemon`, the claude flag is misspelled or a recovery text gains a leading slash; mutants `M-argv-drop-no-daemon`, `M-argv-misspell-skip-permissions`, `M-argv-recovery-slash-command`.
4. Each recovery text is one line, does not begin with `/`, and contains no remedy command from `tests/oracles/auth_status.toml` — `haskell:agentctl-core-test/Agent/recovery-text-is-plain`; fails when a text gains a leading `/`; mutant `M-argv-recovery-slash-command`.

#### Remaining Work

The whole sprint.

### Sprint 5.2: Auth classification, remedies and login refusals [Planned]

**Status**: Planned
**Implementation**: `src/agentctl/haskell/src/AgentCtl/Agent/Auth.hs`, `src/agentctl/haskell/src/AgentCtl/Agent/Argv.hs`, `tests/unit/test_auth_status.py`, `tests/integration/test_agent_real.py`, `tests/integration/test_agent_auth_probe.py`
**Validation tests**: `tests/unit/test_auth_status.py::test_classify_auth_matches_oracle`, `tests/unit/test_auth_status.py::test_remedy_names_the_command_to_type`, `tests/unit/test_auth_status.py::test_login_shaped_args_refused`, `tests/integration/test_agent_real.py::test_logged_out_by_construction`, `tests/integration/test_agent_real.py::test_help_canaries_list_mandatory_flags`, `tests/integration/test_agent_auth_probe.py::test_preflight_never_runs_login`, `tests/integration/test_agent_auth_probe.py::test_probe_sees_caller_environment`
**Mutants**: `M-auth-exit2-as-logged-out`, `M-auth-timeout-as-logged-in`, `M-auth-remedy-wrong-command`, `M-auth-pass-setup-token`, `M-auth-probe-drops-env`
**Closes**: R13
**Docs to update**: `documents/architecture/launch_contract.md`, `documents/operations/troubleshooting.md`, `documents/engineering/testing.md`

#### Objective

Decide login state from exit codes alone, name the command the user types, and refuse every ARGS
shape that would make agentctl log in.

#### Deliverables

- `classifyAuth` maps the auth probe's result: exit 0 is logged in, exit 1 is logged out, and any
  other exit, a signal or no exit within the probe timeout is `check failed`. Output is never read:
  claude prints JSON on stdout and codex writes only to stderr, in wording that changes between
  versions.
- The probe runs the agent's auth-status argv through `AgentCtl.Process`, by the resolved absolute
  path, with the timeout and with the caller's environment, which is the environment the pane
  trampoline gives the agent; the probe and the agent therefore read the same `CLAUDE_CONFIG_DIR`
  and `CODEX_HOME`.
- Logged out renders a warning naming the agent's remedy command for the user to type. `check failed`
  renders a distinct warning naming the probe and its exit status, never a login command, so a usage
  error or a hung probe never tells a logged-in user to log in again.
- The probe vocabulary holds the auth-status probe and nothing else: no module constructs a login
  command or login keystrokes, which gives `src.no-login-construction` (Sprint 1.4) its first
  product subject.
- `launchArgv` refuses login-shaped ARGS before preflight: for claude, an element `setup-token`, or
  `auth` followed by `login`, before the first bare `--`, and anywhere an element that is `/login` or
  begins with `/login` and whitespace; for codex, an element `login` before the first bare `--`. With
  no flag table the subcommand's position is unknown, so the shape is refused anywhere before the
  `--`. The refusal is the R13 warning with the remedy, and nothing is spawned.
- Real runs are logged out by construction: an empty `CLAUDE_CONFIG_DIR`, an empty `CODEX_HOME` whose
  `config.toml` sets `cli_auth_credentials_store = "file"` so keyring credentials cannot answer, the
  auth variables removed, and `DISABLE_AUTOUPDATER=1`.
- The `--help` canaries confirm the installed CLIs know the mandatory flags. codex checks flags
  before printing help, so `codex --no-daemon --help` and
  `codex --dangerously-bypass-approvals-and-sandbox --help` must exit 0 while a nonce-named bogus
  flag exits 2. claude's `--help` hides argument errors, so its help text must list
  `--dangerously-skip-permissions` while the nonce-named flag is absent from it.

#### Validation

1. `classifyAuth` equals the `tests/oracles/auth_status.toml` rows for exits 0, 1, 2 and 127, a signal and a timeout — `tests/unit/test_auth_status.py::test_classify_auth_matches_oracle`; fails when exit 2 reads as logged out or a timeout reads as logged in; mutants `M-auth-exit2-as-logged-out`, `M-auth-timeout-as-logged-in`.
2. The logged-out warning names `claude auth login` or `codex login` exactly as the oracle row does, and the `check failed` warning names no login command — `tests/unit/test_auth_status.py::test_remedy_names_the_command_to_type`; fails when the claude remedy names a different command; mutant `M-auth-remedy-wrong-command`.
3. Every refusal row is refused with the remedy, and its positive-control rows (`auth status`, `logout`, a prompt that mentions login without the slash command) pass through unchanged — `tests/unit/test_auth_status.py::test_login_shaped_args_refused`; fails when `setup-token` passes through; mutant `M-auth-pass-setup-token`.
4. The real claude and codex probes exit 1 under the isolated config dirs, and the binary renders the oracle remedy — `tests/integration/test_agent_real.py::test_logged_out_by_construction`; fails when the probe environment lets the user's own credentials answer; mutant `M-auth-exit2-as-logged-out`.
5. The canaries accept every mandatory flag from the agent table and reject the nonce-named flag — `tests/integration/test_agent_real.py::test_help_canaries_list_mandatory_flags`; fails when a table flag is misspelled or the installed CLI drops it, and the negative control fails when the canary could not see an unknown flag; mutant `M-argv-misspell-skip-permissions`.
6. With the fake agent installed as `claude` and as `codex` and scripted to exit 1, a preflight records exactly one auth-status invocation carrying the run's nonce (the positive control) and no login invocation and no interactive start — `tests/integration/test_agent_auth_probe.py::test_preflight_never_runs_login`; fails when a remedy is executed instead of printed; mutant `M-auth-remedy-wrong-command`.
7. The fake agent's record of the probe holds the `CLAUDE_CONFIG_DIR` and `CODEX_HOME` keys the caller set — `tests/integration/test_agent_auth_probe.py::test_probe_sees_caller_environment`; fails when the probe drops the caller's environment; mutant `M-auth-probe-drops-env`.

#### Remaining Work

The whole sprint.

### Sprint 5.3: Preflight and the opaque Ready [Planned]

**Status**: Planned
**Implementation**: `src/agentctl/haskell/src/AgentCtl/Preflight.hs`, `src/agentctl/haskell/src/AgentCtl/Agent.hs`, `tests/unit/test_preflight.py`, `tests/unit/test_agent_resolution.py`, `tests/integration/test_preflight.py`, `tests/integration/test_ready_opaque.py`, `tests/fixtures/static_negative/ready_constructed.hs.txt`, `tests/fixtures/static_negative/ready_from_preflight.hs.txt`
**Validation tests**: `tests/unit/test_preflight.py::test_failure_warnings_match_oracle`, `tests/unit/test_agent_resolution.py::test_resolution_matches_oracle`, `tests/integration/test_preflight.py::test_order_mux_then_agent_then_auth`, `tests/integration/test_preflight.py::test_missing_agent_names_install_hint`, `tests/integration/test_ready_opaque.py::test_ready_constructor_is_not_exported`
**Mutants**: `M-preflight-auth-before-mux`, `M-preflight-skip-auth`, `M-preflight-export-ready-constructor`, `M-preflight-accept-cmd-shim`, `M-preflight-relative-agent-path`
**Closes**: R12.2
**Docs to update**: `documents/architecture/launch_contract.md`, `documents/operations/troubleshooting.md`, `documents/engineering/code_standards.md`

#### Objective

Make a passing preflight the only source of the right to launch.

#### Deliverables

- `AgentCtl.Preflight` checks the multiplexer (the resolution and floor of Sprint 4.1), then the
  agent, then auth (Sprint 5.2), and stops at the first failure; the decision is a pure function of
  the three observations, and the effectful shell runs each probe only after the previous one passed.
- Success is `Ready`, which carries the resolved multiplexer, the agent's absolute path and the auth
  result. Its constructor is not exported, and `AgentCtl.Launch` accepts only a `Ready`.
- Agent resolution is a pure function of the PATH entries, PATHEXT and directory listings, and yields
  an absolute path. On Windows only a native `.exe` is accepted: a `.cmd` or `.bat` shim is refused
  with a remedy naming the native installer, because cmd.exe re-parses the arguments of a shim
  started through CreateProcessW. These rows run as values on every host.
- Each failure class has its own warning lines and non-zero exit status from
  `tests/oracles/preflight.toml`: multiplexer missing, multiplexer below its floor, agent missing
  (with the install hint for the host's OS), shim refused, logged out (with the remedy) and auth
  check failed. Warnings go to the invoking process's stderr.
- Preflight creates nothing: no session, no spec file and no state, so a failure leaves nothing to
  clean up.
- A two-sided compile-fail fixture keeps `Ready` opaque: `ready_constructed.hs.txt` constructs
  `Ready` as an expression outside `AgentCtl.Preflight` and must fail with GHC diagnostic code
  `GHC-88464` (data constructor not in scope), and its twin `ready_from_preflight.hs.txt` obtains `Ready` from `preflight` and must
  compile. Both are copied to a temp dir and compiled with the pinned GHC against the built library.

#### Validation

1. Each failure class renders exactly its oracle warning lines and exit status, and a passing decision yields `Ready` — `tests/unit/test_preflight.py::test_failure_warnings_match_oracle`; fails when a logged-out agent reads as ready; mutant `M-preflight-skip-auth`.
2. Resolution equals the `tests/oracles/preflight.toml` rows: the first executable PATH match as an absolute path, PATHEXT order with case-insensitive extensions, `.exe` accepted, `.cmd` and `.bat` refused with the remedy — `tests/unit/test_agent_resolution.py::test_resolution_matches_oracle`; fails when a `.cmd` shim is accepted or a bare name is returned; mutants `M-preflight-accept-cmd-shim`, `M-preflight-relative-agent-path`.
3. Under a constructed PATH holding no tmux, the fake agent records no invocation; with tmux added to the same PATH, it records exactly one auth-status invocation with the run's nonce (the positive control) — `tests/integration/test_preflight.py::test_order_mux_then_agent_then_auth`; fails when auth is probed before the multiplexer check; mutants `M-preflight-auth-before-mux`, `M-preflight-skip-auth`.
4. Under a constructed PATH holding tmux but no agent, preflight prints the agent-missing warning with the install hint for the host's OS and exits with the oracle status — `tests/integration/test_preflight.py::test_missing_agent_names_install_hint`; fails when the resolved path is relative and so passes a later check against the wrong file; mutant `M-preflight-relative-agent-path`.
5. The constructing expression fixture fails with `GHC-88464` and its twin compiles — `tests/integration/test_ready_opaque.py::test_ready_constructor_is_not_exported`; fails when `AgentCtl.Preflight` exports the constructor, and the twin catches a fixture that fails for an unrelated reason; mutant `M-preflight-export-ready-constructor`.

#### Remaining Work

The whole sprint.

## Remaining Work

The whole phase: Sprints 5.1–5.3.

## Documentation Requirements

**Architecture docs to create/update:**

- `documents/architecture/launch_contract.md` — Argument Assembly states the agent table, the mandatory flags, the removable alias and the first-bare-`--` rule; Login Refusals states the refused shapes and the remedy; Preflight states the order, the exit-code auth rule, Windows resolution and the opaque `Ready`.

**Engineering docs to create/update:**

- `documents/engineering/testing.md` — the logged-out-by-construction recipe, the `--help` canaries with their negative control, and the fake agent as the auth-probe observer.
- `documents/engineering/code_standards.md` — opaque types such as `Ready`, held by a two-sided compile-fail fixture matched by GHC diagnostic code.

**Operations and reference docs to create/update:**

- `documents/operations/troubleshooting.md` — each preflight warning (multiplexer missing or too old, agent missing, shim refused, logged out, auth check failed, login-shaped ARGS) and what the user types.
- `documents/reference/external_tool_facts.md` — the auth-status exit codes and output streams, the mandatory flags, `--yolo`, codex's exit 2 on a repeated flag, claude's `--help` behaviour and the official install commands, each with its version.

**Cross-references to add:**

- `documents/architecture/multiplexer_adapter.md` — links the launch contract's Preflight section as the consumer of multiplexer resolution and its floors.
