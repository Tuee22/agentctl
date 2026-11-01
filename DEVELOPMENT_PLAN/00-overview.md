# Development Plan Overview

**Status**: Authoritative source
**Supersedes**: N/A

> **Purpose**: State the architecture the phases build, hold the only requirements table, and say
> what each phase is responsible for and why the phases run in this order.

This file states no status; [README.md](README.md#current-phase-status) holds the only status table.

## Architecture

agentctl has two layers. The Python layer, `src/agentctl/`, is a click application installed once
with `pipx install`, and it is the only command the user runs. It decides the per-user dirs,
provisions the OS prerequisites (with consent), ghcup, GHC and cabal, builds the core binary
`agentctl-core` from the Cabal project shipped inside the package whenever no binary exists for the
current digest of its sources and pins, and runs `agentctl check`. Every other command passes through
raw to the core binary, by `execve` on POSIX or as a child process on Windows. The binary is never on
PATH and refuses direct invocation without the handoff protocol.
[python_haskell_boundary.md](../documents/architecture/python_haskell_boundary.md) states the
boundary.

The core binary owns everything after bootstrap: multiplexer resolution and the typed tmux and psmux
command vocabulary; the agent argv and the preflight (multiplexer, agent, login) that yields the
opaque `Ready`; launch with create-or-attach and instant-exit capture; list, attach, stop, status and
adopt; and the recovery supervisor with capture, classification, the state machine, backoff and the
decision log. Sessions live on the user's normal tmux server. Each pane runs the pane trampoline,
which reads and deletes a 0600 spec file and then becomes the agent (`execve`, POSIX) or runs it as a
child that reports its exit status (Windows).

```text
user shell
  │  agentctl <command> [ARGS...]
  ▼
agentctl            Python click: bootstrap, check, raw passthrough
  │  handoff: execve on POSIX, child process on Windows
  ▼
core binary         Haskell: multiplexer, preflight, launch, sessions, supervisor
  │  new-session, attach or switch-client, capture-pane, send-keys -l
  ▼
tmux or psmux pane  the user's normal server
  │  agentctl-core pane-exec <spec>
  ▼
pane trampoline     reads and deletes the 0600 spec: argv, cwd, environment
  │  execve on POSIX; child process and status file on Windows
  ▼
claude or codex     ARGS verbatim, mandatory flags last
```

## Requirements

This table is the only home of the requirements; each row is closed by exactly one sprint, and its
quote is an exact substring of the request block in [rationale.md](rationale.md#originating-request).

| ID | Requirement | Quote | Closing sprint | Evidence classes | Prose home | Data home |
|---|---|---|---|---|---|---|
| R1 | The build chain needs only pipx and its Python: agentctl itself installs OS build prerequisites (with consent), ghcup, GHC and cabal; tmux/psmux and the agent CLIs are runtime prerequisites the binary checks and names install commands for. | `pipx is the only host dependency that's required here` | [Sprint 12.1](phase-12-clean-container-acceptance.md) | value; owed | [documents/operations/installation.md](../documents/operations/installation.md) | `tests/oracles/bootstrap_plan.toml` |
| R2 | agentctl is a click application tested with pytest. | `agentctl is a click application using pytest` | [Sprint 0.2](phase-0-governance-and-check-skeleton.md) | real; value | [documents/engineering/quality_gate.md](../documents/engineering/quality_gate.md) | `tests/oracles/command_surface.toml` |
| R3 | The Python layer idempotently provides ghcup the OS-appropriate way: it reuses an existing ghcup at or above the floor, otherwise downloads the pinned binary and verifies its SHA-256, and it never edits rc files. | `idempotently installs ghcup in the manner appropriate for the OS in question` | [Sprint 2.3](phase-2-toolchain-bootstrap.md) | value; real; observer; owed | [documents/engineering/toolchain_bootstrap.md](../documents/engineering/toolchain_bootstrap.md) | `tests/oracles/pins.toml` |
| R4 | The Python layer installs the pinned cabal and GHC through ghcup without changing the user's default selection. | `b) installs cabal` | [Sprint 2.4](phase-2-toolchain-bootstrap.md) | value; real; observer | [documents/engineering/toolchain_bootstrap.md](../documents/engineering/toolchain_bootstrap.md) | `tests/oracles/pins.toml` |
| R5 | The Python layer builds the bundled Haskell binary host-native and idempotently, keyed by a digest of its sources and pins. | `c) builds the haskell binary` | [Sprint 3.3](phase-3-haskell-package-and-build.md) | real; value | [documents/engineering/binary_build.md](../documents/engineering/binary_build.md) | `tests/oracles/pins.toml` |
| R6 | Every command except check passes through to the Haskell binary, which is never on PATH and never named in user-facing docs. | `the user shouldn't need to call the haskell binary directly` | [Sprint 6.3](phase-6-launch-and-passthrough.md) | value; real; observer; owed | [documents/architecture/python_haskell_boundary.md](../documents/architecture/python_haskell_boundary.md) | `tests/oracles/command_surface.toml` |
| R7 | agentctl claude and agentctl codex launch the agent inside a tmux (macOS/Linux) or psmux (Windows) session. | `codex and claude are both commands` | [Sprint 6.2](phase-6-launch-and-passthrough.md) | real; observer; owed | [documents/architecture/launch_contract.md](../documents/architecture/launch_contract.md) | `tests/oracles/mux_commands.toml` |
| R8 | The session name is mandatory and derived from the invoking folder; a hash form disambiguates a different folder with the same basename; re-running in the same folder re-attaches. | `a mandatory name for the tmux session which should be based on the folder the command calls it from` | [Sprint 6.2](phase-6-launch-and-passthrough.md) | value; real; observer; owed | [documents/architecture/launch_contract.md](../documents/architecture/launch_contract.md) | `tests/oracles/session_names.toml` |
| R9 | Additional ARGS pass through verbatim. | `any additional command parameters are passed through to either codex or claude` | [Sprint 6.3](phase-6-launch-and-passthrough.md) | value; observer; owed | [documents/architecture/launch_contract.md](../documents/architecture/launch_contract.md) | `tests/oracles/launch_argv.toml` |
| R10 | The claude argv always ends with --dangerously-skip-permissions (placed before a first bare --, if any). | `claude always includes "--dangerously-skip-permissions"` | [Sprint 6.2](phase-6-launch-and-passthrough.md) | value; real; observer; owed | [documents/architecture/launch_contract.md](../documents/architecture/launch_contract.md) | `tests/oracles/launch_argv.toml` |
| R11 | The codex argv always ends with --dangerously-bypass-approvals-and-sandbox --no-daemon (placed before a first bare --, if any). | `codex always includes "--dangerously-bypass-approvals-and-sandbox --no-daemon"` | [Sprint 6.2](phase-6-launch-and-passthrough.md) | value; real; observer; owed | [documents/architecture/launch_contract.md](../documents/architecture/launch_contract.md) | `tests/oracles/launch_argv.toml` |
| R12 | On any failed check no session is left behind, a warning reaches the user's own terminal, and the exit is non-zero. | `if any of these are not the case tmux should be closed and a warning message printed` | [Sprint 6.2](phase-6-launch-and-passthrough.md) | value; real; observer | [documents/architecture/launch_contract.md](../documents/architecture/launch_contract.md) | `tests/oracles/preflight.toml` |
| R12.1 | The binary checks that tmux (Linux/macOS, at least 3.2) or psmux (Windows, at least 3.4.0) is available. | `haskell is responsible for ensuring tmux/psmux are available` | [Sprint 4.1](phase-4-multiplexer-adapter.md) | value; real; owed | [documents/architecture/multiplexer_adapter.md](../documents/architecture/multiplexer_adapter.md) | `tests/oracles/mux_commands.toml` |
| R12.2 | The binary checks that the agent CLI is available and logged in before any session is created. | `that claude / codex is available, and that the session is logged in` | [Sprint 5.3](phase-5-agent-adapters-and-preflight.md) | value; real; observer; owed | [documents/architecture/launch_contract.md](../documents/architecture/launch_contract.md) | `tests/oracles/preflight.toml` |
| R13 | When the agent is not logged in, the warning names the discrete auth command for the user to type; agentctl never runs a login command, never types into a REPL to log in, and refuses login-shaped ARGS. | `agentctl should instruct the user to do so themselves with the appropriate command (eg claude auth login)` | [Sprint 5.2](phase-5-agent-adapters-and-preflight.md) | value; real; observer; owed | [documents/architecture/launch_contract.md](../documents/architecture/launch_contract.md) | `tests/oracles/auth_status.toml` |
| R14 | agentctl check runs ruff check, ruff format --check, ty, fourmolu, hlint, cabal build, cabal test and the entire pytest suite; any failing leg fails check. | `Also fourmolu + hlint` | [Sprint 3.2](phase-3-haskell-package-and-build.md) | real; value | [documents/engineering/quality_gate.md](../documents/engineering/quality_gate.md) | `tests/oracles/check_legs.toml` |
| R14.1 | check runs ruff, ty with every rule an error, and the entire test suite, with no skip, selection or deselection possible. | `the check command should run ruff, ty (strict) and the entire test suite` | [Sprint 0.3](phase-0-governance-and-check-skeleton.md) | real; value | [documents/engineering/quality_gate.md](../documents/engineering/quality_gate.md) | `tests/oracles/check_legs.toml` |
| R15 | GHC's OS prerequisites are probed; when one is missing agentctl asks for consent and then runs the OS package manager; a non-interactive run never prompts. | `Install with consent` | [Sprint 2.2](phase-2-toolchain-bootstrap.md) | value; observer; owed | [documents/engineering/toolchain_bootstrap.md](../documents/engineering/toolchain_bootstrap.md) | `tests/oracles/prerequisites.toml` |
| R16 | list, attach, stop and status for agentctl-managed sessions. | `then session management (list/attach/stop)` | [Sprint 7.2](phase-7-session-management-and-adoption.md) | value; real | [documents/architecture/sessions_and_ownership.md](../documents/architecture/sessions_and_ownership.md) | `tests/oracles/session_ownership.toml` |
| R17 | Stopping the supervisor or unwatching never kills a managed or adopted session. | `adopted sessions are not killed by stopping the supervisor` | [Sprint 10.4](phase-10-supervisor.md) | value; real; observer | [documents/architecture/supervisor_contract.md](../documents/architecture/supervisor_contract.md) | `tests/oracles/forbidden_actions.toml` |
| R17.1 | adopt registers a pre-existing pane without taking ownership; stopping an adopted pane only forgets it. | `adopt pre-existing panes without taking ownership` | [Sprint 7.3](phase-7-session-management-and-adoption.md) | value; real; observer | [documents/architecture/sessions_and_ownership.md](../documents/architecture/sessions_and_ownership.md) | `tests/oracles/session_ownership.toml` |
| R18 | The recovery supervisor watches sessions with the state machine MONITORING, SUSPECTED_FAILURE, CONFIRM_IDLE, BACKOFF, RECOVERY_SENT, VERIFY, then MONITORING or ESCALATE. | `Supervise capacity/overload failures without changing the selected model` | [Sprint 10.4](phase-10-supervisor.md) | value; real; observer; owed | [documents/architecture/supervisor_contract.md](../documents/architecture/supervisor_contract.md) | `tests/oracles/recovery_transitions.toml` |
| R18.1 | Screens are classified per agent, distinguishing transient overload from usage limits, authentication errors, context exhaustion and crashes. | `Distinguish transient overload from usage limits, authentication errors, context exhaustion, and crashes` | [Sprint 8.2](phase-8-pane-observation-and-classification.md) | value; real; owed | [documents/architecture/supervisor_contract.md](../documents/architecture/supervisor_contract.md) | `tests/fixtures/screens/` |
| R18.2 | Input is never sent during active work, approval dialogs or partially typed input. | `Never send input during active work, approval dialogs, or partially typed user input` | [Sprint 9.1](phase-9-recovery-state-machine.md) | value | [documents/architecture/supervisor_contract.md](../documents/architecture/supervisor_contract.md) | `tests/oracles/recovery_transitions.toml` |
| R18.3 | Errors are fingerprinted so stale scrollback never re-triggers, and a new transition is required before another injection. | `Fingerprint errors to avoid retrying stale scrollback` | [Sprint 9.1](phase-9-recovery-state-machine.md) | value | [documents/architecture/supervisor_contract.md](../documents/architecture/supervisor_contract.md) | `tests/oracles/recovery_transitions.toml` |
| R18.4 | Backoff is bounded exponential with jitter, with escalating notifications. | `Use bounded exponential backoff with jitter` | [Sprint 9.2](phase-9-recovery-state-machine.md) | value | [documents/architecture/supervisor_contract.md](../documents/architecture/supervisor_contract.md) | `tests/oracles/backoff.toml` |
| R18.5 | Every observation, decision, attempt and result is logged, and logs shows them. | `Log each observation, decision, attempt, and result` | [Sprint 10.3](phase-10-supervisor.md) | real; observer; value | [documents/architecture/supervisor_contract.md](../documents/architecture/supervisor_contract.md) | `tests/oracles/log_records.toml` |
| R18.6 | watch, unwatch, pause and resume-watch give manual pause and opt-out. | `Support manual pause and opt-out` | [Sprint 10.1](phase-10-supervisor.md) | value; real | [documents/architecture/supervisor_contract.md](../documents/architecture/supervisor_contract.md) | `tests/oracles/command_surface.toml` |
| R19 | The supervisor never switches models, never restarts crashed processes and never sends login input. | `Never automatically switch models or restart arbitrary crashed processes` | [Sprint 10.4](phase-10-supervisor.md) | value; observer | [documents/architecture/supervisor_contract.md](../documents/architecture/supervisor_contract.md) | `tests/oracles/forbidden_actions.toml` |
| R20 | Every phase has strict validation that cannot be spoofed and that an agent runs automatically with no human input. | `phases should have strict validation criteria that cannot be spoofed and which an agent can validate automatically without human input` | [Sprint 1.5](phase-1-gate-integrity-apparatus.md) | real; value; observer | [documents/engineering/testing.md](../documents/engineering/testing.md) | `tests/oracles/check_steps.toml` |

## Phase Responsibilities

Each phase builds on everything beneath it. The self-verifying phases are re-proved by every
`agentctl check` run; the host-acceptance phases add no code and confirm, on their lane's host, what
the lower phases owe them.

| Phase | Builds | Host lane | Gate kind |
|---|---|---|---|
| [Phase 0 — Governance, documentation standards and the check skeleton](phase-0-governance-and-check-skeleton.md) | The governed plan and documentation suite; the package skeleton, with the click group and `agentctl check` running the Python legs; the test-discipline gate plugin; the documentation validator and the plan validator core; the root entry documents. | any-host | self-verifying |
| [Phase 1 — Gate-integrity apparatus](phase-1-gate-integrity-apparatus.md) | The oracle store with the request-derived oracles, frozen before any product code; the mutant runner and corpus; the ratchet, write-guard and venv integrity; the spawn audit, source guards and branch coverage; the plan closure rules, the lane summary and the EVIDENCE line. | any-host | self-verifying |
| [Phase 2 — Toolchain bootstrap](phase-2-toolchain-bootstrap.md) | Host facts and the pure provisioning plan; OS prerequisites with consent; ghcup reuse or the pinned, SHA-256-verified download; the pinned GHC and cabal, installed without changing the user's selection; the clean-lane recipe. | any-host | self-verifying |
| [Phase 3 — Haskell package, quality legs and digest-keyed build](phase-3-haskell-package-and-build.md) | The Cabal project as package data, with its `-Werror` build and test legs and the handshake; the fourmolu and hlint legs that complete the eight; the digest-keyed build cache and binary identity. | any-host | self-verifying |
| [Phase 4 — Multiplexer adapter](phase-4-multiplexer-adapter.md) | tmux and psmux resolution with version floors, and session names as validated values; the typed command vocabulary, the one runner and the pane trampoline; real isolated-server behaviour and the fake agent. | mux-host | self-verifying |
| [Phase 5 — Agent adapters and preflight](phase-5-agent-adapters-and-preflight.md) | The agent table and the pure launch argv; auth classification by exit code, login remedies and login refusals; the preflight that yields the opaque `Ready`. | agent-host | self-verifying |
| [Phase 6 — Launch command and passthrough](phase-6-launch-and-passthrough.md) | Folder-derived session names; launch orchestration with create-or-attach, instant-exit capture, and nothing left behind on failure; raw passthrough at both layers and the handoff to the core binary. | agent-host | self-verifying |
| [Phase 7 — Session management and adoption](phase-7-session-management-and-adoption.md) | `list` and `status` from session options; `attach` and `stop`; `adopt` without ownership. | agent-host | self-verifying |
| [Phase 8 — Pane observation and classification](phase-8-pane-observation-and-classification.md) | Capture, normalisation and fingerprints; the claude and codex screen classifiers over fixtures with provenance; the screen column in `status` and live classification. | agent-host | self-verifying |
| [Phase 9 — Recovery state machine and backoff](phase-9-recovery-state-machine.md) | The pure transition function with its safety predicates and fingerprint gating; bounded backoff with seeded jitter and escalation. | any-host | self-verifying |
| [Phase 10 — Recovery supervisor](phase-10-supervisor.md) | Watch state and its commands; `supervisor run`; the decision log and `logs`; the scenario matrix showing that the supervisor never kills a session, switches models, restarts a process or sends login input. | agent-host | self-verifying |
| [Phase 11 — Live agent acceptance](phase-11-live-agent-acceptance.md) | No code. Confirms the logged-in launch, live screen classes and live no-send supervision on a host whose agents are logged in. | live-agents | host-acceptance |
| [Phase 12 — Clean-host bootstrap acceptance](phase-12-clean-container-acceptance.md) | No code. Runs the two-stage clean-host recipe, confirming that pipx alone is enough to provision the toolchain, build the binary and pass the gate (R1). | clean-container | host-acceptance |
| [Phase 13 — macOS acceptance](phase-13-macos-acceptance.md) | No code. Confirms the darwin ghcup, Keychain-keyed isolation, the exec handoff and Homebrew tmux. | macos | host-acceptance |
| [Phase 14 — Windows and psmux acceptance](phase-14-windows-psmux-acceptance.md) | No code. Confirms the mingw64 `ghcup.exe`, real psmux, the trampoline status file, subprocess exit codes, PATHEXT resolution and case-folded identity. | windows-psmux | host-acceptance |

## Dependency Flow

Phases 0 to 10 form one chain: each depends on the phase before it, so the plan runs in numerical order
and every phase needs only what lies beneath it
([§ A](development_plan_standards.md#a-one-continuous-constructive-narrative)). The chain is a
layering:

- **Governance.** [Phase 0 — Governance, documentation standards and the check skeleton](phase-0-governance-and-check-skeleton.md)
  and [Phase 1 — Gate-integrity apparatus](phase-1-gate-integrity-apparatus.md) come first because an
  unenforced standard is only a preference, and Phase 1 freezes the request-derived oracles before any
  product code exists, so no oracle is written to match an implementation.
- **Bootstrap and build.** [Phase 2 — Toolchain bootstrap](phase-2-toolchain-bootstrap.md) provides
  the toolchain that [Phase 3 — Haskell package, quality legs and digest-keyed build](phase-3-haskell-package-and-build.md)
  needs, and no Haskell behaviour can be tested before the binary builds.
- **Adapters.** Launch needs a multiplexer it can drive,
  [Phase 4 — Multiplexer adapter](phase-4-multiplexer-adapter.md), and an argv and preflight it can
  trust, [Phase 5 — Agent adapters and preflight](phase-5-agent-adapters-and-preflight.md).
- **Launch and sessions.** [Phase 6 — Launch command and passthrough](phase-6-launch-and-passthrough.md)
  creates the sessions that [Phase 7 — Session management and adoption](phase-7-session-management-and-adoption.md)
  lists, attaches, stops and adopts beside.
- **Supervision.** The supervisor needs a classified screen,
  [Phase 8 — Pane observation and classification](phase-8-pane-observation-and-classification.md), and
  a pure recovery decision, [Phase 9 — Recovery state machine and backoff](phase-9-recovery-state-machine.md),
  before [Phase 10 — Recovery supervisor](phase-10-supervisor.md) may send anything.

The four acceptance phases, 11 to 14, each depend on
[Phase 10 — Recovery supervisor](phase-10-supervisor.md), and nothing depends on any of them. They add
no code: each runs the same `agentctl check` on its lane's host and confirms the `owed` rows that lower
phases name. Because no self-verifying phase waits on them, a missing macOS host, Windows host or
logged-in agent never blocks the chain. They close last because each evidence line carries a tree
digest over `src/`, `tests/` and `pyproject.toml`, which goes stale whenever a lower phase changes
covered code; closing them after the chain is complete means their evidence covers the finished stack.

```text
Phase 0   governance, documentation standards and the check skeleton
   │
Phase 1   gate-integrity apparatus
   │
Phase 2   toolchain bootstrap
   │
Phase 3   Haskell package, quality legs and digest-keyed build
   │
Phase 4   multiplexer adapter
   │
Phase 5   agent adapters and preflight
   │
Phase 6   launch command and passthrough
   │
Phase 7   session management and adoption
   │
Phase 8   pane observation and classification
   │
Phase 9   recovery state machine and backoff
   │
Phase 10  recovery supervisor
   ├──► Phase 11  live agent acceptance             lane live-agents
   ├──► Phase 12  clean-host bootstrap acceptance   lane clean-container
   ├──► Phase 13  macOS acceptance                  lane macos
   └──► Phase 14  Windows and psmux acceptance      lane windows-psmux
```

## Non-Goals

Each of these concept-note features is deliberately absent; rationale.md says why.

- Named profiles, project defaults and any project-local configuration file; passthrough ARGS take
  their place ([Rejected Alternatives](rationale.md#rejected-alternatives)).
- A `start` command with `--name`, `--cwd` or `--profile`, and a detach command; the invoking folder
  supplies the name and working directory ([Rejected Alternatives](rationale.md#rejected-alternatives)).
- Installing tmux, psmux, claude or codex; they are runtime prerequisites that the core binary checks
  and names install commands for ([Concept-Note Disposition](rationale.md#concept-note-disposition)).
- Any login automation: running a login command, typing a login into a REPL, or forwarding
  login-shaped ARGS ([Concept-Note Disposition](rationale.md#concept-note-disposition)).
- Switching models, restarting crashed processes, or sending anything but the per-agent recovery text
  ([Concept-Note Disposition](rationale.md#concept-note-disposition)).
- A binary on PATH, a Python-free runtime, an ephemeral `pipx run` installer, installer flags and an
  uninstall command ([Rejected Alternatives](rationale.md#rejected-alternatives)).
- A distribution phase; tag and archive installs need a release the user publishes
  ([Rejected Alternatives](rationale.md#rejected-alternatives)).
- CI workflows; the gate of record is `agentctl check` on the declared host
  ([Rejected Alternatives](rationale.md#rejected-alternatives)).
- A supervisor config file, OS service integration, supervisor reconnection, external alerts and
  lifecycle hooks ([Rejected Alternatives](rationale.md#rejected-alternatives)).
- uv or poetry as host dependencies, GPG verification of ghcup, and an MSYS2 bootstrap on Windows
  ([Rejected Alternatives](rationale.md#rejected-alternatives)).

## Related

- [README.md](README.md) — the only status table, and how to work the plan.
- [rationale.md](rationale.md#originating-request) — the request block every quote above is a
  substring of, plus the decisions and rejected alternatives behind the architecture.
- [development_plan_standards.md](development_plan_standards.md#k-requirement-anchoring) — § K says how
  each row is anchored and closed exactly once.
- [system-components.md](system-components.md) — the inventory of the modules, tools and dirs the
  phases build.
- [python_haskell_boundary.md](../documents/architecture/python_haskell_boundary.md) — the full
  contract of the boundary the Architecture section summarises.
