# Development Plan Overview

**Status**: Authoritative source
**Supersedes**: N/A

> **Purpose**: Define the additive architecture, stable requirements, phase responsibilities and scope of completion.

## Architecture

Pipx installs a pure-Python Click entry point carrying source/package resources. Python does only what must
precede a Haskell executable: resolve bootstrap roots, prepare ghcup/GHC/cabal and their necessary OS build
prerequisites, build bundled Haskell sources by immutable input digest and perform raw handoff. Product runtime
policy does not return to Python. The existing developer gate remains a Python-owned boundary and tests the
same Haskell preparation/runtime code instead of implementing another installer.

Haskell gathers runtime host facts and owns pure provisioning plans, consent/privilege decisions, artifact
preparation, qualified multiplexer capabilities, user-agent discovery, launch, sessions, observation and recovery.
Debian is the Linux contract: exact `ID=debian` qualifies; an Ubuntu/ID_LIKE/apt-presence guess does not.
Haskell reuses supported tmux or prepares it through consented APT. The Windows path uses native pinned private
Rust/Cargo plus actual MSVC/linker/resource/SDK readiness, verified source+patch inputs and a locally compiled
psmux artifact. It uses a stable private registry/config with an absolute private binary; system psmux aliases,
registries and running sessions remain independent. Agents claude/codex are user-installed, checked early for a
fresh launch, never installed or logged in by agentctl.

The common backend contract includes actual server/session/pane instance identity, coherent observations and
conditional server-ordered literal+Enter submission. A source pin, client banner, stable cursor or repeated
capture does not establish those capabilities. Debian tmux must demonstrate a concrete sufficient protocol
using its supported primitives; failure to qualify means no automated input and an incomplete owner, never a
weaker successful mode. Windows implements the same pre-existing contract with reviewed source patches.
Observable terminal ordering does not expose an agent's latent internal state.

Every present source/test artifact remains censused. One `agentctl check` runs all introduced legs and present
tests, preserves all failures and emits independent phase/lane reports. Closure follows owned inputs and actual
prerequisites rather than every later source file or the overall result. Shared integrity failures invalidate
their consumers. Final product acceptance binds the whole subject and current native receipts.

## Requirements

The table is the sole live requirement/closing-owner join. Original requirement IDs and request anchors are
preserved; [rationale](rationale.md#current-decision-precedence) names the explicit user-authorized amendments.
A Planned test/resource is an implementation obligation, not a claim that a file or observation already exists.

| ID | Requirement | Quote | Closing sprint | Evidence classes | Prose home | Data home |
|---|---|---|---|---|---|---|
| R1 | Pipx and Python are the user-installed bootstrap prerequisites; Python provisions the Haskell build chain, Haskell provisions Debian tmux and private source-built Windows psmux/toolchains, and agents remain externally installed. | `pipx is the only host dependency that's required here` | [Sprint 12.2](phase-12-linux-live-and-clean-acceptance.md) | value; owed | [documents/operations/installation.md](../documents/operations/installation.md) | `tests/oracles/bootstrap_plan.toml` |
| R2 | agentctl is a click application tested with pytest. | `agentctl is a click application using pytest` | [Sprint 2.2](phase-2-python-bootstrap-and-handoff.md) | real; value | [documents/engineering/quality_gate.md](../documents/engineering/quality_gate.md) | `tests/oracles/command_surface.toml` |
| R3 | The Python layer idempotently provides ghcup the OS-appropriate way: it reuses an existing ghcup at or above the floor, otherwise downloads the pinned binary and verifies its SHA-256, and it never edits rc files. | `idempotently installs ghcup in the manner appropriate for the OS in question` | [Sprint 2.1](phase-2-python-bootstrap-and-handoff.md) | value; real; observer; owed | [documents/engineering/toolchain_bootstrap.md](../documents/engineering/toolchain_bootstrap.md) | `tests/oracles/pins.toml` |
| R4 | The Python layer installs the pinned cabal and GHC through ghcup without changing the user's default selection. | `b) installs cabal` | [Sprint 2.1](phase-2-python-bootstrap-and-handoff.md) | value; real; observer | [documents/engineering/toolchain_bootstrap.md](../documents/engineering/toolchain_bootstrap.md) | `tests/oracles/pins.toml` |
| R5 | The Python layer builds the bundled Haskell binary host-native and idempotently, keyed by a digest of its sources and pins. | `c) builds the haskell binary` | [Sprint 2.2](phase-2-python-bootstrap-and-handoff.md) | real; value | [documents/engineering/binary_build.md](../documents/engineering/binary_build.md) | `tests/oracles/pins.toml` |
| R6 | Click permanently exposes the CLI and preserves raw commands; Python owns only bootstrap/transport and developer gate infrastructure, while Haskell owns runtime provisioning and application behavior. | `the user shouldn't need to call the haskell binary directly` | [Sprint 2.2](phase-2-python-bootstrap-and-handoff.md) | value; real; observer; owed | [documents/architecture/python_haskell_boundary.md](../documents/architecture/python_haskell_boundary.md) | `tests/oracles/command_surface.toml` |
| R7 | agentctl claude and agentctl codex launch the agent inside a tmux (macOS/Linux) or psmux (Windows) session. | `codex and claude are both commands` | [Sprint 5.2](phase-5-agent-preflight-and-launch.md) | real; observer; owed | [documents/architecture/launch_contract.md](../documents/architecture/launch_contract.md) | `tests/oracles/mux_commands.toml` |
| R8 | The session name is mandatory and derived from the invoking folder; a hash form disambiguates a different folder with the same basename; re-running in the same folder re-attaches. | `a mandatory name for the tmux session which should be based on the folder the command calls it from` | [Sprint 5.2](phase-5-agent-preflight-and-launch.md) | value; real; observer; owed | [documents/architecture/launch_contract.md](../documents/architecture/launch_contract.md) | `tests/oracles/session_names.toml` |
| R9 | Additional ARGS pass through verbatim. | `any additional command parameters are passed through to either codex or claude` | [Sprint 5.1](phase-5-agent-preflight-and-launch.md) | value; observer; owed | [documents/architecture/launch_contract.md](../documents/architecture/launch_contract.md) | `tests/oracles/launch_argv.toml` |
| R10 | The claude argv always ends with --dangerously-skip-permissions (placed before a first bare --, if any). | `claude always includes "--dangerously-skip-permissions"` | [Sprint 5.1](phase-5-agent-preflight-and-launch.md) | value; real; observer; owed | [documents/architecture/launch_contract.md](../documents/architecture/launch_contract.md) | `tests/oracles/launch_argv.toml` |
| R11 | The codex argv always ends with --dangerously-bypass-approvals-and-sandbox --no-daemon (placed before a first bare --, if any). | `codex always includes "--dangerously-bypass-approvals-and-sandbox --no-daemon"` | [Sprint 5.1](phase-5-agent-preflight-and-launch.md) | value; real; observer; owed | [documents/architecture/launch_contract.md](../documents/architecture/launch_contract.md) | `tests/oracles/launch_argv.toml` |
| R12 | On any failed check no session is left behind, a warning reaches the user's own terminal, and the exit is non-zero. | `if any of these are not the case tmux should be closed and a warning message printed` | [Sprint 5.2](phase-5-agent-preflight-and-launch.md) | value; real; observer | [documents/architecture/launch_contract.md](../documents/architecture/launch_contract.md) | `tests/oracles/preflight.toml` |
| R12.1 | Haskell qualifies the host backend: exact Debian Linux uses APT-managed tmux, native Windows uses agentctl's private source-built psmux and registry, and unsupported Linux fails before runtime effects. | `haskell is responsible for ensuring tmux/psmux are available` | [Sprint 4.1](phase-4-debian-tmux-and-multiplexer.md) | value; real; owed | [documents/architecture/multiplexer_adapter.md](../documents/architecture/multiplexer_adapter.md) | `tests/oracles/mux_commands.toml` |
| R12.2 | The binary checks that the agent CLI is available and logged in before any session is created. | `that claude / codex is available, and that the session is logged in` | [Sprint 5.1](phase-5-agent-preflight-and-launch.md) | value; real; observer; owed | [documents/architecture/launch_contract.md](../documents/architecture/launch_contract.md) | `tests/oracles/preflight.toml` |
| R13 | When the agent is not logged in, the warning names the discrete auth command for the user to type; agentctl never runs a login command, never types into a REPL to log in, and refuses login-shaped ARGS. | `agentctl should instruct the user to do so themselves with the appropriate command (eg claude auth login)` | [Sprint 5.1](phase-5-agent-preflight-and-launch.md) | value; real; observer; owed | [documents/architecture/launch_contract.md](../documents/architecture/launch_contract.md) | `tests/oracles/auth_status.toml` |
| R14 | The single gate runs every introduced Python and Haskell quality/test leg and reports independent phase/lane verdicts plus an overall result. | `Also fourmolu + hlint` | [Sprint 2.3](phase-2-python-bootstrap-and-handoff.md) | real; value | [documents/engineering/quality_gate.md](../documents/engineering/quality_gate.md) | `tests/oracles/check_legs.toml` |
| R14.1 | The sole no-argument gate runs the complete present test/source census without skips, selection or suppression; later owned failures cannot poison complete earlier evidence. | `the check command should run ruff, ty (strict) and the entire test suite` | [Sprint 0.3](phase-0-governance-and-phase-evidence.md) | real; value | [documents/engineering/quality_gate.md](../documents/engineering/quality_gate.md) | `tests/oracles/check_legs.toml` |
| R15 | Bootstrap and runtime native prerequisites are prepared idempotently by their respective Python/Haskell owners under explicit consent; no noninteractive check, test or absent privilege prompts or installs host packages. | `Install with consent` | [Sprint 3.2](phase-3-haskell-runtime-and-platform-policy.md) | value; observer; owed | [documents/engineering/toolchain_bootstrap.md](../documents/engineering/toolchain_bootstrap.md) | `tests/oracles/prerequisites.toml` |
| R16 | list, attach, stop and status for agentctl-managed sessions. | `then session management (list/attach/stop)` | [Sprint 6.1](phase-6-session-management-and-adoption.md) | value; real | [documents/architecture/sessions_and_ownership.md](../documents/architecture/sessions_and_ownership.md) | `tests/oracles/session_ownership.toml` |
| R17 | Stopping the supervisor or unwatching never kills a managed or adopted session. | `adopted sessions are not killed by stopping the supervisor` | [Sprint 8.2](phase-8-recovery-and-supervisor.md) | value; real; observer | [documents/architecture/supervisor_contract.md](../documents/architecture/supervisor_contract.md) | `tests/oracles/forbidden_actions.toml` |
| R17.1 | adopt registers a pre-existing pane without taking ownership; stopping an adopted pane only forgets it. | `adopt pre-existing panes without taking ownership` | [Sprint 6.2](phase-6-session-management-and-adoption.md) | value; real; observer | [documents/architecture/sessions_and_ownership.md](../documents/architecture/sessions_and_ownership.md) | `tests/oracles/session_ownership.toml` |
| R18 | The recovery supervisor watches sessions with the state machine MONITORING, SUSPECTED_FAILURE, CONFIRM_IDLE, BACKOFF, RECOVERY_SENT, VERIFY, then MONITORING or ESCALATE. | `Supervise capacity/overload failures without changing the selected model` | [Sprint 8.1](phase-8-recovery-and-supervisor.md) | value; real; observer; owed | [documents/architecture/supervisor_contract.md](../documents/architecture/supervisor_contract.md) | `tests/oracles/recovery_transitions.toml` |
| R18.1 | Screens are classified per agent, distinguishing transient overload from usage limits, authentication errors, context exhaustion and crashes. | `Distinguish transient overload from usage limits, authentication errors, context exhaustion, and crashes` | [Sprint 7.2](phase-7-pane-observation-and-classification.md) | value; real; owed | [documents/architecture/supervisor_contract.md](../documents/architecture/supervisor_contract.md) | `tests/fixtures/screens/` |
| R18.2 | Input is never sent during active work, approval dialogs or partially typed input. | `Never send input during active work, approval dialogs, or partially typed user input` | [Sprint 7.3](phase-7-pane-observation-and-classification.md) | value | [documents/architecture/supervisor_contract.md](../documents/architecture/supervisor_contract.md) | `tests/oracles/recovery_transitions.toml` |
| R18.3 | Errors are fingerprinted so stale scrollback never re-triggers, and a new transition is required before another injection. | `Fingerprint errors to avoid retrying stale scrollback` | [Sprint 8.1](phase-8-recovery-and-supervisor.md) | value | [documents/architecture/supervisor_contract.md](../documents/architecture/supervisor_contract.md) | `tests/oracles/recovery_transitions.toml` |
| R18.4 | Backoff is bounded exponential with jitter, with escalating notifications. | `Use bounded exponential backoff with jitter` | [Sprint 8.1](phase-8-recovery-and-supervisor.md) | value | [documents/architecture/supervisor_contract.md](../documents/architecture/supervisor_contract.md) | `tests/oracles/backoff.toml` |
| R18.5 | Every observation, decision, attempt and result is logged, and logs shows them. | `Log each observation, decision, attempt, and result` | [Sprint 8.2](phase-8-recovery-and-supervisor.md) | real; observer; value | [documents/architecture/supervisor_contract.md](../documents/architecture/supervisor_contract.md) | `tests/oracles/log_records.toml` |
| R18.6 | watch, unwatch, pause and resume-watch give manual pause and opt-out. | `Support manual pause and opt-out` | [Sprint 8.2](phase-8-recovery-and-supervisor.md) | value; real | [documents/architecture/supervisor_contract.md](../documents/architecture/supervisor_contract.md) | `tests/oracles/command_surface.toml` |
| R19 | The supervisor never switches models, never restarts crashed processes and never sends login input. | `Never automatically switch models or restart arbitrary crashed processes` | [Sprint 8.1](phase-8-recovery-and-supervisor.md) | value; observer | [documents/architecture/supervisor_contract.md](../documents/architecture/supervisor_contract.md) | `tests/oracles/forbidden_actions.toml` |
| R20 | Every closure uses current independent tests, mutants, coverage, native observations and input-bound phase receipts without human intervention or commits. | `phases should have strict validation criteria that cannot be spoofed and which an agent can validate automatically without human input` | [Sprint 1.3](phase-1-python-discipline-and-gate-integrity.md) | real; value; observer | [documents/engineering/testing.md](../documents/engineering/testing.md) | `tests/oracles/check_steps.toml` |
| R21 | All first-party Python, checker, tests and native boundaries conform to project-owned strict functional doctrine with executable local enforcement and explicit migration. | `incorporate it's standards doctrinally` | [Sprint 1.1](phase-1-python-discipline-and-gate-integrity.md) | value; real; observer | `documents/engineering/code_standards.md` | `tests/oracles/python_discipline.toml` |
| R22 | Haskell owns runtime dependency policy, source acquisition, toolchain/backend preparation, qualification, sessions and recovery; Python owns only the prerequisite bootstrap/transport and developer gate. | `as much logic as possible should be in haskell not python` | [Sprint 3.1](phase-3-haskell-runtime-and-platform-policy.md) | value; real; observer | `documents/architecture/python_haskell_boundary.md` | `tests/oracles/runtime_provisioning.toml` |
| R23 | On native Windows Haskell idempotently provisions private Rust/Cargo and native linker/SDK requirements, fetches pinned source and patches, and builds/publishes its private psmux artifact. | `including idemmpotently installing any rust dependencies` | [Sprint 9.3](phase-9-windows-toolchain-and-psmux-build.md) | value; real; observer | `documents/engineering/toolchain_bootstrap.md` | `tests/oracles/backend_profiles.toml` |
| R24 | The exact psmux client/server artifacts meet memory/backpressure, control-event, coherent capture, exact-target and guarded-input contracts through independent native tests. | `consider both how agentctl will interact with psmux` | [Sprint 10.2](phase-10-windows-backend-qualification.md) | value; real; observer | `documents/architecture/multiplexer_adapter.md` | `tests/oracles/backend_profiles.toml` |
| R25 | Windows-host Linux validation uses a dedicated right-sized Debian WSL2 instance with all Linux dependencies and a verified bind mount of the same host checkout; no commit/copy bridge supplies evidence. | `a dedicated wsl2 instance for agentctl is used` | [Sprint 12.1](phase-12-linux-live-and-clean-acceptance.md) | value; real; observer | `documents/operations/validation_runbook.md` | `tests/oracles/host_lanes.toml` |
| R26 | Every phase is additive, independently closable from its own prerequisites and requires Linux plus at most one native foreign hardware family. | `incomplete later phases should not prevent earlier phases from being validated` | [Sprint 0.1](phase-0-governance-and-phase-evidence.md) | value; real; observer | `documents/engineering/quality_gate.md` | `tests/oracles/phase_ownership.toml` |

## Phase Responsibilities

| Phase | Builds | Host lane | Gate kind |
|---|---|---|---|
| [Governance and phase evidence](phase-0-governance-and-phase-evidence.md) | The governed target architecture, requirement ownership, legacy census and one gate with independent phase and lane verdicts | linux | self-verifying |
| [Python discipline and gate integrity](phase-1-python-discipline-and-gate-integrity.md) | Project-owned strict Python doctrine, local executable enforcement, typed native boundaries and migration of existing package, gate and test code | linux | self-verifying |
| [Python bootstrap and handoff](phase-2-python-bootstrap-and-handoff.md) | A portable pipx/Click entry point and only the Python work needed before Haskell exists: bootstrap directories, pinned ghcup/GHC/cabal, native source build and raw handoff | linux | self-verifying |
| [Haskell runtime and platform policy](phase-3-haskell-runtime-and-platform-policy.md) | Haskell owns runtime host policy, typed effect interpretation, consent and reusable artifact preparation | linux | self-verifying |
| [Debian tmux and multiplexer](phase-4-debian-tmux-and-multiplexer.md) | The common checked-backend interface and Debian tmux implementation, including Haskell-owned APT provisioning and a private pane trampoline | linux | self-verifying |
| [Agent preflight and launch](phase-5-agent-preflight-and-launch.md) | User-installed agent discovery, authentication refusal, immutable argv assembly and folder-derived launch/reattach | linux | self-verifying |
| [Session management and adoption](phase-6-session-management-and-adoption.md) | Session management and adoption use checked instance identity and retain the distinction between access, ownership and supervision | linux | self-verifying |
| [Pane observation and classification](phase-7-pane-observation-and-classification.md) | The generic observation and guarded-input contract precedes recovery and every foreign backend | linux | self-verifying |
| [Recovery and supervisor](phase-8-recovery-and-supervisor.md) | The complete Linux recovery application consumes the already-qualified observation and conditional-submission capability | linux | self-verifying |
| [Windows toolchain and psmux build](phase-9-windows-toolchain-and-psmux-build.md) | Haskell prepares native Windows build dependencies and compiles pinned psmux sources locally | linux-windows | self-verifying |
| [Windows backend qualification](phase-10-windows-backend-qualification.md) | Qualify the exact native candidate for attached-client memory behavior, capture correctness, exact identity and guarded input | linux-windows | self-verifying |
| [Windows application acceptance](phase-11-windows-application-acceptance.md) | Native Windows acceptance of the shared application, private psmux artifact and registered resources | linux-windows | host-acceptance |
| [Linux live and clean acceptance](phase-12-linux-live-and-clean-acceptance.md) | Debian clean-host and logged-in agent acceptance, with dedicated WSL2 permitted for Linux evidence on a Windows host | linux-live-clean | host-acceptance |
| [macOS acceptance](phase-13-macos-acceptance.md) | The additive Darwin implementation and native acceptance of bootstrap, process/filesystem semantics and the common tmux backend contract | linux-macos | self-verifying |
| [Release evidence and closure](phase-14-release-evidence-and-closure.md) | Whole-product closure joins current independent native receipts and requires an empty migration ledger | linux | host-acceptance |

## Dependency Flow

The common Linux path is governance, strict Python migration, minimal bootstrap, Haskell runtime foundations,
Debian backend, agent launch, sessions, observation and guarded recovery. The Windows source-build/qualification
branch consumes this common contract and requires Linux plus Windows only. Linux live/clean evidence and the
Darwin extension consume the same common contract independently of Windows. Each phase has at most one foreign
family. Release aggregation consumes already-earned native evidence on Linux; it does not add a joint
Windows/macOS execution requirement.

A later phase cannot add a retroactive closure obligation. All cross-platform interfaces, provisioning value
types and safety predicates are introduced before their platform implementations. Evidence input closures
include shared contracts automatically; foreign implementation bytes do not enter an unrelated Linux phase.

## Hardware and WSL2

Linux validation from Windows uses a dedicated Debian WSL2 instance, measured CPU/memory/storage budgets and a
verified bind mount of this live Windows checkout. Install all Linux dependencies, including pipx and the dev
extra, and keep build/temp/toolchain state on private Linux storage. A copy, detached checkout or new commit is
not synchronization. Bind-mount semantic controls, mount receipts and bidirectional pre-gate nonce markers
prove the actual source identity. Native Windows and native Darwin evidence remain distinct requirements.

## Non-Goals

No precompiled product/backend distribution, global psmux replacement, user-agent installation, login automation,
silent session migration, global toolchain default changes or guessed wrap reconstruction. No model switching,
arbitrary agent restart or claim that a provider overload is reproducible on demand. No alternate check runner,
skip, source suppression, human closure checkpoint or required commit.

## Related

- [README](README.md) — phase status and execution.
- [standards](development_plan_standards.md) — hardware and evidence policy.
- [components](system-components.md) — target and migration ownership.
- [rationale](rationale.md) — user intent and amendments.
- [ledger](legacy_tracking_for_deletion.md) — standing incompatible source.
- [documents](../documents/README.md) — canonical contracts.
