# Phase 13 — macOS acceptance

**Status**: Planned
**Depends on**: [Phase 8 — Recovery and supervisor](phase-8-recovery-and-supervisor.md)
**Host lane**: linux-macos
**Gate**: `agentctl check`
**Gate kind**: self-verifying
**Closes**: none

> **Purpose**: The native Darwin gate entry and observers, the additive Darwin implementation and native acceptance of bootstrap, process/filesystem semantics and the common tmux backend contract.

## Phase Objective

The native Darwin gate entry and observers, the additive Darwin implementation and native acceptance of bootstrap, process/filesystem semantics and the common tmux backend contract. Windows evidence belongs to its independent capabilities.

This phase's verdict evaluates the `linux` and `macos` halves ([T.V](development_plan_standards.md#tv-verdict) V8) at stage 2 ([T.W](development_plan_standards.md#tw-staged-enforcement)): a native Darwin run evaluates the `macos` half over a byte-identical tree whose logical identity equals that of the stored `linux` receipts (D-151). While [Validation Hosts](README.md#validation-hosts) lists `macos` as `no`, selection works this phase while its verdict is `fail`, because a `fail` is never blocked; the phase is blocked as `awaiting:macos` only once its `linux` half passes and the `macos` half is its only gap, and selection then passes over it, so with no Mac the terminal state is `selection: stop` listing what each blocked phase awaits ([T.D](development_plan_standards.md#td-status-and-progression)). Every cited artifact is owned within closure(13) ([§ A](development_plan_standards.md#a-well-ordered-constructive-narrative)), a planned absence is unmet work of this phase ([T.F](development_plan_standards.md#tf-shared-and-owned-failures)), and present incompatible code is a deletion-ledger row of its owner. The native Darwin confirmations of [Python bootstrap and handoff](phase-2-python-bootstrap-and-handoff.md), [Haskell runtime and platform policy](phase-3-haskell-runtime-and-platform-policy.md), [Debian tmux and multiplexer](phase-4-debian-tmux-and-multiplexer.md) and [Recovery and supervisor](phase-8-recovery-and-supervisor.md) become owed items paired with Confirms lines of this phase in the single change that P0-16 makes. Its Haskell modules and native tests form this phase's own build component, discovered through the `cabal.project` package glob of [Python bootstrap and handoff](phase-2-python-bootstrap-and-handoff.md); it edits no earlier component ([§ A](development_plan_standards.md#a-well-ordered-constructive-narrative) A1, A2).

## Gate Integrity

| Requirement | Oracle | Observer | Mutants | Tests |
|---|---|---|---|---|
| R26 — Native Darwin gate entry and observers | `tests/oracles/phase_ownership.toml` | real: native Darwin process and interpreter identity on the named host; observer: nonce-bound join of the `macos` receipt with the stored `linux` identity | none — planned mutants enter the Remaining Work table when this phase activates | `tests/integration/test_darwin_runtime.py::test_darwin_process_identity_observer`, `tests/integration/test_darwin_runtime.py::test_macos_receipt_joins_stored_linux_identity` |
| R12.1 — Darwin bootstrap and Haskell tmux readiness | `tests/oracles/requirements.toml` | value: independent Darwin plan and noninteractive refusal expectations; real: native build, exec handoff and tmux readiness on the named host | none — planned mutants are named in the Deliverables of this row's sprint until their corpus rows land | `tests/integration/test_darwin_runtime.py::test_native_bootstrap_and_tmux_readiness`, `tests/integration/test_darwin_runtime.py::test_missing_clt_is_noninteractive_refusal` |
| R7 — Native Darwin session and supervisor confirmation | `tests/oracles/requirements.toml` | observer: nonce-bound native Darwin tmux, supervisor-stop and guarded-submission observations | none — closure-owned mutants with all their killers follow P0-18 | `tests/integration/test_mux_real.py::test_private_server_roundtrip`, `tests/e2e/test_supervisor_scenarios.py::test_stop_supervisor_keeps_sessions`, `tests/integration/test_guarded_submit.py::test_changed_input_or_output_refuses` |

## Not Proven By This Gate

- Limits: [T.C](development_plan_standards.md#tc-ceiling); none is a closure condition.
- A copied `macos` receipt is accepted on content and identity equality only ([T.C](development_plan_standards.md#tc-ceiling) C3).

## Sprints

### Sprint 13.1: Native Darwin gate entry and observers [Planned]

**Status**: Planned
**Implementation**: `src/agentctl/foundation_process_identity_darwin.py`, `tests/integration/test_darwin_runtime.py`
**Validation tests**: `tests/integration/test_darwin_runtime.py::test_darwin_process_identity_observer`, `tests/integration/test_darwin_runtime.py::test_macos_receipt_joins_stored_linux_identity`
**Mutants**: none — planned mutants enter the Remaining Work table when this phase activates
**Closes**: none
**Docs to update**: migrates `documents/engineering/toolchain_bootstrap.md` (owner [Haskell runtime and platform policy](phase-3-haskell-runtime-and-platform-policy.md)) except its D-153 frozen spans, migrates `documents/architecture/multiplexer_adapter.md` (owner [Debian tmux and multiplexer](phase-4-debian-tmux-and-multiplexer.md))

#### Objective

Native Darwin gate entry and observers supplies its complete owned contract through the single phase-scoped gate verdict.

#### Deliverables

Run the native gate on a Mac over a byte-identical tree whose logical identity equals that of the stored `linux` receipts; that tree never substitutes for the bind mount of the live checkout (D-151). The host-declared Darwin process and interpreter identity observer `src/agentctl/foundation_process_identity_darwin.py`, re-homed from [Governance and phase evidence](phase-0-governance-and-phase-evidence.md) behind `foundation_host` (D-140), records the sealed host facts, and Darwin coverage measures every host-declared Darwin source on its own family. The verified `macos` receipt enters the Linux receipt store, and the stored `linux` receipts enter the Mac's store, through the import and export of the receipt store of [Governance and phase evidence](phase-0-governance-and-phase-evidence.md) over a channel the agent prepares; the [validation runbook](../documents/operations/validation_runbook.md) gives the native Darwin run.

The same suite runs here as on every other host, plus the Darwin thin native layer; no run here probes an agent CLI or reads a Keychain entry (D-172). This phase receives the owed Darwin confirmation of the non-disruptive gate environment and the Darwin build of the Haskell test tools (D-176).

#### Validation

Linux exercises the pure observer and receipt-join values; a native Mac proves actual process and interpreter identity. A `macos` receipt that no verified run produced, or whose logical or prerequisite identity differs from the stored `linux` receipts, is refused. While no Mac is available this phase is at best `awaiting:macos` ([T.V](development_plan_standards.md#tv-verdict)), which it reports only once its `linux` half passes and `macos` is its only gap; before that its verdict is `fail`, and it is never a degraded pass.

Every node in **Validation tests** passes in a verified run and every named mutant is killed per [T.K](development_plan_standards.md#tk-kill) at stage 2.

#### Remaining Work

The whole sprint.

### Sprint 13.2: Darwin bootstrap and Haskell tmux readiness [Planned]

**Status**: Planned
**Implementation**: `src/agentctl/haskell/src/AgentCtl/Provision/Darwin.hs`, `src/agentctl/bootstrap_darwin.py`, `src/agentctl/check/probes/xcode_clt.py`, `src/agentctl/haskell/product-darwin/`
**Validation tests**: `tests/integration/test_darwin_runtime.py::test_native_bootstrap_and_tmux_readiness`, `tests/integration/test_darwin_runtime.py::test_missing_clt_is_noninteractive_refusal`
**Mutants**: none — planned mutants are named in this sprint's Deliverables until their corpus rows land
**Closes**: none
**Docs to update**: migrates `documents/engineering/toolchain_bootstrap.md` (owner [Haskell runtime and platform policy](phase-3-haskell-runtime-and-platform-policy.md)) except its D-153 frozen spans, migrates `documents/architecture/multiplexer_adapter.md` (owner [Debian tmux and multiplexer](phase-4-debian-tmux-and-multiplexer.md))

#### Objective

Darwin bootstrap and Haskell tmux readiness supplies its complete owned contract through the single phase-scoped gate verdict.

#### Deliverables

Reuse verified Command Line Tools and native build tools or report unmet readiness without opening setup dialogs. Haskell reuses qualified tmux, or prepares a verified existing Homebrew installation's tmux plan under consent; it does not bootstrap global Homebrew or alter shell setup. The same common identity/observation/guarded-input contract applies. The host-declared Darwin bootstrap module `src/agentctl/bootstrap_darwin.py` lies outside the bootstrap package and is reached lazily through `foundation_host`; this sprint consumes `src/agentctl/bootstrap/` of [Python bootstrap and handoff](phase-2-python-bootstrap-and-handoff.md) without editing it. `src/agentctl/haskell/product-darwin/` is the Darwin product component, whose executable links the packages owned within this phase's closure, the Darwin implementation included, and is the installed executable on Darwin hosts (D-163). The planned mutant `M-darwin-prompts-in-check` is named here until its corpus row lands ([§ C](development_plan_standards.md#c-honest-completion-tracking)). This phase's host-declared probe for `setup:xcode-clt` reports absence on a native Darwin run while the Command Line Tools are absent, leaving this phase at best `awaiting:setup:xcode-clt`. The Command Line Tools are host provision that the user supplies with the Mac, as [Validation Hosts](README.md#validation-hosts) records, because their installation needs a dialog that a person completes (the GHC system requirements row of [external tool facts](../documents/reference/external_tool_facts.md)); no run, check or agent answers that dialog (D-158).

#### Validation

Linux exercises pure Darwin plans/refusals. A native Mac proves actual build, exec handoff, filesystem ownership and tmux behavior; missing CLT/Homebrew readiness never counts as a degraded pass or a human validation task.

Every node in **Validation tests** passes in a verified run and every named mutant is killed per [T.K](development_plan_standards.md#tk-kill) at stage 2.

#### Remaining Work

The whole sprint.

### Sprint 13.3: Native Darwin session and supervisor confirmation [Planned]

**Status**: Planned
**Implementation**: none — this sprint records acceptance evidence
**Validation tests**: `tests/integration/test_mux_real.py::test_private_server_roundtrip`, `tests/e2e/test_supervisor_scenarios.py::test_stop_supervisor_keeps_sessions`, `tests/integration/test_guarded_submit.py::test_changed_input_or_output_refuses`
**Mutants**: none — closure-owned mutants with all their killers follow P0-18
**Closes**: none
**Docs to update**: migrates `documents/engineering/toolchain_bootstrap.md` (owner [Haskell runtime and platform policy](phase-3-haskell-runtime-and-platform-policy.md)) except its D-153 frozen spans, migrates `documents/architecture/multiplexer_adapter.md` (owner [Debian tmux and multiplexer](phase-4-debian-tmux-and-multiplexer.md))

#### Objective

Native Darwin session and supervisor confirmation supplies its complete owned contract through the single phase-scoped gate verdict.

#### Deliverables

Evaluate the `macos` half over this phase's actual prerequisite inputs and read its `linux` half from the receipt store. Preserve private socket path/permissions, Keychain-aware logged-out controls and no-input live evidence limits. Once P0-18 lets a row cite mutants owned within its closure, this sprint's Gate Integrity row cites them with every killer.

#### Validation

Run the public lifecycle and adversarial guarded-submission scenarios through real native tmux. Require no foreign-session changes, exact ownership and cleanup; a guest or other Linux result supplies only the `linux` half and cannot stand in for a Darwin kernel observation ([T.E](development_plan_standards.md#te-unspoofable-test) E6).

Every node in **Validation tests** passes in a verified run and every named mutant is killed per [T.K](development_plan_standards.md#tk-kill) at stage 2.

#### Remaining Work

The whole sprint.

## Remaining Work

The whole phase: Sprints 13.1–13.3.

## Documentation Requirements

**Architecture docs to create/update:**

- migrates `documents/architecture/multiplexer_adapter.md` (owner [Debian tmux and multiplexer](phase-4-debian-tmux-and-multiplexer.md)) — this phase's owned contract and links to prerequisite interfaces.

**Engineering docs to create/update:**

- migrates `documents/engineering/toolchain_bootstrap.md` (owner [Haskell runtime and platform policy](phase-3-haskell-runtime-and-platform-policy.md)) except its D-153 frozen spans — doctrine, mechanisms and scope of executable evidence.

**Operations and reference docs to create/update:**

- None.

**Cross-references to add:**

- `DEVELOPMENT_PLAN/00-overview.md` — requirement closure and lower-phase dependencies.
- `DEVELOPMENT_PLAN/system-components.md` — stable capability/path ownership.
- `DEVELOPMENT_PLAN/legacy_tracking_for_deletion.md` — remaining incompatible implementation shapes.
