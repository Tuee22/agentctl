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

Every present source and test artifact is censused. One no-argument `agentctl check` runs every introduced leg
and present test and preserves every failure; only its verified parent publishes one verdict line per phase
([T.O](development_plan_standards.md#to-output)). A phase identity covers only that phase's closure
([T.I](development_plan_standards.md#ti-identity)). A failure fails every phase only when
[T.F](development_plan_standards.md#tf-shared-and-owned-failures) lists it as shared; every other failure stays
with its locus, so later-only work never changes an earlier verdict. Final product acceptance binds the whole
subject and a current receipt for every half.

Behavior is proven model-first: unchanged production code runs through declared effect interpreters against
conformant environment models, and only the thin native layer, private multiplexer servers and the harness
provisioning earn `real` evidence ([§ T](development_plan_standards.md#t-unspoofable-evidence-and-phase-verdicts)).
Testing is non-disruptive: every test touches only the closed list of
[§ Q](development_plan_standards.md#q-containment-and-user-state-protection), the same suite runs on every host
while each host family supplies its own halves, and live acceptance with logged-in agents runs only on the bound
dedicated guest.

## Requirements

The table is the sole live requirement/closing-owner join. Rows are append-only: a committed row, its quote and
closing sprint included, never changes, and an obligation that moves to another owner is an appended row plus a
decision row. Original requirement IDs and request anchors are preserved;
[rationale](rationale.md#current-decision-precedence) names the explicit user-authorized amendments. A planned
test or resource is an implementation obligation of the phase that cites it, not a claim that a file or
observation already exists.

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
| R20.1 | Only the verifying parent publishes phase verdicts; a phase passes only when V1–V10 hold over its closure at its stage, and child PHASE and EVIDENCE lines are relayed only as withheld. | `fix the doctrinal issues and blockers we've been discussing` | [Sprint 0.2](phase-0-governance-and-phase-evidence.md) | value; real; observer | `documents/engineering/quality_gate.md` | `tests/oracles/phase_verdicts.toml` |
| R20.2 | Haskell and C closure evidence is named-reason mutation kills plus model twins on every run of each family a source executes on, and native positive and refusing twins on their own family for the thin native layer; the coverage floor applies to Python sources. | `clearly define what unspoofable tests mean (eg mutations)` | [Sprint 1.3](phase-1-python-discipline-and-gate-integrity.md) | value; real | `documents/engineering/testing.md` | `tests/oracles/python_discipline.toml` |
| R21 | All first-party Python, checker, tests and native boundaries conform to project-owned strict functional doctrine with executable local enforcement and explicit migration. | `incorporate it's standards doctrinally` | [Sprint 1.1](phase-1-python-discipline-and-gate-integrity.md) | value; real; observer | `documents/engineering/code_standards.md` | `tests/oracles/python_discipline.toml` |
| R22 | Haskell owns runtime dependency policy, source acquisition, toolchain/backend preparation, qualification, sessions and recovery; Python owns only the prerequisite bootstrap/transport and developer gate. | `as much logic as possible should be in haskell not python` | [Sprint 3.1](phase-3-haskell-runtime-and-platform-policy.md) | value; real; observer | `documents/architecture/python_haskell_boundary.md` | `tests/oracles/runtime_provisioning.toml` |
| R23 | On native Windows Haskell idempotently provisions private Rust/Cargo and native linker/SDK requirements, fetches pinned source and patches, and builds/publishes its private psmux artifact. | `including idemmpotently installing any rust dependencies` | [Sprint 9.3](phase-9-windows-toolchain-and-psmux-build.md) | value; real; observer | `documents/engineering/toolchain_bootstrap.md` | `tests/oracles/backend_profiles.toml` |
| R23.1 | The Windows harness runs agentctl's own provisioning once per run: a cold build on the first run, idempotent afterwards, never per mutation, using a private validation root and no restart. | `i think the test harness can do it once, without repeating it for each mutation` | [Sprint 9.3](phase-9-windows-toolchain-and-psmux-build.md) | value; real; observer | `documents/engineering/toolchain_bootstrap.md` | `tests/oracles/backend_profiles.toml` |
| R24 | The exact psmux client/server artifacts meet memory/backpressure, control-event, coherent capture, exact-target and guarded-input contracts through independent native tests. | `consider both how agentctl will interact with psmux` | [Sprint 10.2](phase-10-windows-backend-qualification.md) | value; real; observer | `documents/architecture/multiplexer_adapter.md` | `tests/oracles/backend_profiles.toml` |
| R25 | Windows-host Linux validation uses a dedicated right-sized Debian Hyper-V VM with all Linux dependencies and a verified bind mount of the same host checkout; no commit/copy bridge supplies evidence. | `a dedicated wsl2 instance for agentctl is used` | [Sprint 12.1](phase-12-linux-live-and-clean-acceptance.md) | value; real; observer | `documents/operations/validation_runbook.md` | `tests/oracles/host_lanes.toml` |
| R25.1 | The Windows host binder attaches the live checkout to the dedicated Debian VirtualBox guest, verifies its nonce answer and census, writes the guest binding receipt and transports stored phase receipts. | `there must be a bind mount between the agentctl repo in wsl2 and the local host` | [Sprint 9.1](phase-9-windows-toolchain-and-psmux-build.md) | real; observer; value | `documents/operations/validation_runbook.md` | `tests/oracles/host_lanes.toml` |
| R26 | Every phase is additive, independently closable from its own prerequisites and requires Linux plus at most one native foreign hardware family. | `incomplete later phases should not prevent earlier phases from being validated` | [Sprint 0.1](phase-0-governance-and-phase-evidence.md) | value; real; observer | `documents/engineering/quality_gate.md` | `tests/oracles/phase_ownership.toml` |
| R26.1 | Later phases never contradict or undo an earlier phase; apart from shared failures, an earlier verdict and identity depend only on what is owned within its closure. | `later phases should not contradict/undo earlier phases` | [Sprint 0.3](phase-0-governance-and-phase-evidence.md) | value; real | `DEVELOPMENT_PLAN/development_plan_standards.md` | `tests/oracles/phase_ownership.toml` |
| R27 | Agents select, activate and close phases only from verified verdicts and the computed selection line; regressed, awaiting and blocked are computed, never authored, and an absent half or capability blocks only the phases awaiting it. | `will allow agents to proceed from phase to phase without human involvement` | [Sprint 0.4](phase-0-governance-and-phase-evidence.md) | value; real | `documents/engineering/quality_gate.md` | `tests/oracles/phase_verdicts.toml` |
| R28 | Tests touch only the closed list. Host facts are observed once. No agent CLI is probed or started outside the guest's live half. These mechanics are family-independent; the Darwin confirmation is owed to macOS acceptance. | `won't disrupt other tasks running on the windows machine` | [Sprint 0.5](phase-0-governance-and-phase-evidence.md) | value; observer; owed | `DEVELOPMENT_PLAN/development_plan_standards.md` | `tests/oracles/host_lanes.toml` |
| R28.1 | Native Windows runs disturb nothing they did not create (job containment, consoles, psmux teardown, no registry or clipboard writes) and never need a host restart. | `(psmux sessions, claude/codex sessions, running VMs)` | [Sprint 9.1](phase-9-windows-toolchain-and-psmux-build.md) | value; real; observer | `documents/operations/validation_runbook.md` | `tests/oracles/host_lanes.toml` |
| R29 | Effectful Haskell behaviour is validated against pure environment models through declared effect interpreters, with Haskell test tools, identically on every host. | `leverage pure functional logic using haskell's test tools to validate correct behaviour` | [Sprint 3.3](phase-3-haskell-runtime-and-platform-policy.md) | value; real | `documents/engineering/code_standards.md` | `tests/oracles/requirements.toml` |
| R29.1 | Models are registered, independent, conformance-anchored to ratcheted rows and checked by model mutants. A model-backed kill counts only with a conformant model. | `you can use pure functional models as required to mock a rich, realistic envrionment` | [Sprint 1.3](phase-1-python-discipline-and-gate-integrity.md) | value; real | `documents/engineering/testing.md` | `tests/oracles/python_discipline.toml` |

R25 preserves its protected historical wording. Its Windows-hosted Linux route is the dedicated Debian
VirtualBox VM specified by [D-107 and D-108](rationale.md#current-decision-precedence) and the
[validation runbook](../documents/operations/validation_runbook.md), and R25.1 is the Windows binder that
attaches the live checkout to that VM. [D-133 and D-134](rationale.md#current-decision-precedence) retire the
superseded binding and Hyper-V route and the diagnostic VirtualBox and WSL observers.

R1 closes in [Sprint 12.2](phase-12-linux-live-and-clean-acceptance.md) on the clean Debian path. Its clause on
private source-built Windows psmux and toolchains is evidenced by R23, which closes in
[Sprint 9.3](phase-9-windows-toolchain-and-psmux-build.md), so R1's closure never claims Windows provisioning.

R14 preserves its protected wording. Its independent phase/lane verdicts are the per-phase `PHASE` lines of
[T.O](development_plan_standards.md#to-output), whose `halves=` field reports each half of the phase's lane, and its
overall result is the run's exit code ([D-135](rationale.md#current-decision-precedence)).

## Phase Responsibilities

| Phase | Builds | Host lane | Gate kind |
|---|---|---|---|
| [Governance and phase evidence](phase-0-governance-and-phase-evidence.md) | Parent-published phase verdicts that satisfy [§ T](development_plan_standards.md#t-unspoofable-evidence-and-phase-verdicts) at stage 1, the governed plan and ownership census, and verdict-driven progression | linux | self-verifying |
| [Python discipline and gate integrity](phase-1-python-discipline-and-gate-integrity.md) | Project-owned strict Python doctrine, local executable enforcement, typed native boundaries, the stage-2 evidence checkers and migration of existing Governance package, gate and test code | linux | self-verifying |
| [Python bootstrap and handoff](phase-2-python-bootstrap-and-handoff.md) | Portable pipx installation, raw Click command transport and only the Python work needed before Haskell exists: bootstrap directories, pinned ghcup/GHC/cabal, native source build and raw handoff | linux | self-verifying |
| [Haskell runtime and platform policy](phase-3-haskell-runtime-and-platform-policy.md) | Haskell owns runtime host policy, typed effect interpretation, consent and reusable artifact preparation | linux | self-verifying |
| [Debian tmux and multiplexer](phase-4-debian-tmux-and-multiplexer.md) | The common checked-backend interface and Debian tmux implementation, including Haskell-owned APT provisioning and a private pane trampoline | linux | self-verifying |
| [Agent preflight and launch](phase-5-agent-preflight-and-launch.md) | User-installed agent discovery, authentication refusal, immutable argv assembly and folder-derived launch/reattach | linux | self-verifying |
| [Session management and adoption](phase-6-session-management-and-adoption.md) | Session management and adoption use checked instance identity and retain the distinction between access, ownership and supervision | linux | self-verifying |
| [Pane observation and classification](phase-7-pane-observation-and-classification.md) | The generic observation and guarded-input contract precedes recovery and every foreign backend | linux | self-verifying |
| [Recovery and supervisor](phase-8-recovery-and-supervisor.md) | The complete Linux recovery application consumes the already-qualified observation and conditional-submission capability | linux | self-verifying |
| [Windows toolchain and psmux build](phase-9-windows-toolchain-and-psmux-build.md) | The Windows entry of binder, receipt transport and native gate precedes Haskell preparation of native Windows build dependencies and local compilation of pinned psmux sources | linux-windows | self-verifying |
| [Windows backend qualification](phase-10-windows-backend-qualification.md) | Qualify the exact native candidate for attached-client memory behavior, capture correctness, exact identity and guarded input | linux-windows | self-verifying |
| [Windows application acceptance](phase-11-windows-application-acceptance.md) | Native Windows acceptance of the shared application, private psmux artifact and registered resources | linux-windows | host-acceptance |
| [Linux live and clean acceptance](phase-12-linux-live-and-clean-acceptance.md) | Debian clean-host and logged-in agent acceptance, with a dedicated Debian VirtualBox VM for Linux evidence on a Windows host | linux-live-clean | host-acceptance |
| [macOS acceptance](phase-13-macos-acceptance.md) | The native Darwin gate entry and observers, the additive Darwin implementation and native acceptance of bootstrap, process/filesystem semantics and the common tmux backend contract | linux-macos | self-verifying |
| [Release evidence and closure](phase-14-release-evidence-and-closure.md) | Whole-product closure joins every phase's current verified halves and requires an empty migration ledger | linux | host-acceptance |

## Dependency Flow

The common Linux path is governance, strict Python migration, minimal bootstrap, Haskell runtime foundations,
Debian backend, agent launch, sessions, observation and guarded recovery. The Windows source-build/qualification
branch consumes this common contract and requires Linux plus Windows only. Linux live/clean evidence and the
Darwin extension consume the same common contract independently of Windows. Each phase has at most one foreign
family. Release aggregation consumes already-earned native evidence on Linux, taking each foreign half from its
current stored receipt; it does not add a joint Windows/macOS execution requirement.
[macOS acceptance](phase-13-macos-acceptance.md) waits for the Mac hardware the user will provide: selection
works it while its verdict is `fail`, it is blocked as `awaiting:macos` only once its `linux` half passes and
`macos` is its only gap, and with no Mac the terminal state is `selection: stop` listing what each blocked phase
awaits.
[Release evidence and closure](phase-14-release-evidence-and-closure.md) keeps depending on it.

The plan is well-ordered ([§ A](development_plan_standards.md#a-well-ordered-constructive-narrative)). A later
phase never contradicts or undoes an earlier one (A1): it adds no retroactive closure obligation and extends
earlier contracts only through the interfaces they define. Incomplete later work never blocks validating an
earlier phase (A2): apart from shared failures, an earlier verdict and identity depend only on what is owned
within its closure, so foreign implementation bytes and later-only rows never enter an unrelated earlier phase.
All cross-platform interfaces, provisioning value types and safety predicates are introduced before their
platform implementations, and evidence input closures include shared contracts automatically.

## Hardware and VirtualBox

Linux validation from Windows uses a dedicated Debian VirtualBox VM, observed capacity with host headroom and a
verified bind mount of this live Windows checkout. Install all Linux dependencies, including pipx and the dev
extra, and keep build/temp/toolchain state on private Linux storage. A copy, detached checkout or new commit is
not synchronization. Mount receipts, the census join and bidirectional pre-gate nonce markers prove the actual
source identity; the mount's semantics are recorded facts. Native Windows and native Darwin evidence remain
distinct requirements.

## Non-Goals

No precompiled product/backend distribution, global psmux replacement, user-agent installation, login automation,
silent session migration, global toolchain default changes or guessed wrap reconstruction. No model switching,
arbitrary agent restart or claim that a provider overload is reproducible on demand. No alternate check runner,
skip, source suppression, human closure checkpoint or required commit. No local receipt authentication
([T.C](development_plan_standards.md#tc-ceiling)) and no authored regressed, awaiting or blocked status. The
focused stepwise sweep is a development tool, not a check runner, and never closes work.

## Related

- [README](README.md) — phase status and execution.
- [standards](development_plan_standards.md) — hardware and evidence policy.
- [components](system-components.md) — target and migration ownership.
- [rationale](rationale.md) — user intent and amendments.
- [ledger](legacy_tracking_for_deletion.md) — standing incompatible source.
- [documents](../documents/README.md) — canonical contracts.
