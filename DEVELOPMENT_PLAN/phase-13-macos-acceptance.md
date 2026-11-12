# Phase 13 — macOS acceptance

**Status**: Planned
**Depends on**: [Phase 8 — Recovery and supervisor](phase-8-recovery-and-supervisor.md)
**Host lane**: linux-macos
**Gate**: `agentctl check`
**Gate kind**: self-verifying
**Closes**: none

> **Purpose**: The additive Darwin implementation and native acceptance of bootstrap, process/filesystem semantics and the common tmux backend contract.

## Phase Objective

The additive Darwin implementation and native acceptance of bootstrap, process/filesystem semantics and the common tmux backend contract. This phase needs Linux and macOS only; Windows evidence belongs to its independent capabilities.

This phase needs Linux and native macOS. Its receipts can come from separate runs with the same logical source/policy/prerequisite identity and separately verified lane-native artifact/toolchain identities; no other foreign hardware is required. The declared tests are executable contracts; an absent required test is unmet evidence, not existing proof. Acceptance-only test implementations belong to the prerequisite owner named in the inventory. Existing incompatible code is inventoried in the deletion ledger. No old implementation or unqualified receipt establishes this revised contract.

## Gate Integrity

| Requirement | Oracle | Observer | Mutants | Tests |
|---|---|---|---|---|
| R20 — Darwin bootstrap and Haskell tmux readiness | `tests/oracles/requirements.toml` | value; observer: independent inputs and nonce-bound native observations | `M-darwin-prompts-in-check` | `tests/integration/test_darwin_runtime.py::test_native_bootstrap_and_tmux_readiness`, `tests/integration/test_darwin_runtime.py::test_missing_clt_is_noninteractive_refusal` |
| R20 — Native Darwin session and supervisor confirmation | `tests/oracles/requirements.toml` | value; observer: independent inputs and nonce-bound native observations | none — native positive/refusing twins | `tests/integration/test_mux_real.py::test_private_server_roundtrip`, `tests/e2e/test_supervisor_scenarios.py::test_stop_supervisor_keeps_sessions`, `tests/integration/test_guarded_submit.py::test_changed_input_or_output_refuses` |

## Not Proven By This Gate

- A receipt's digest establishes input currency, not an independently attested historical run. Local receipt authenticity has the documented honest ceiling.
- A source rule or finite corpus does not prove arbitrary callback purity, universal termination or agent-internal readiness. Native operation and resource assumptions remain explicit.

## Sprints

### Sprint 13.1: Darwin bootstrap and Haskell tmux readiness [Planned]

**Status**: Planned
**Implementation**: `src/agentctl/haskell/src/AgentCtl/Provision/Darwin.hs`, `src/agentctl/bootstrap/`
**Validation tests**: `tests/integration/test_darwin_runtime.py::test_native_bootstrap_and_tmux_readiness`, `tests/integration/test_darwin_runtime.py::test_missing_clt_is_noninteractive_refusal`
**Mutants**: `M-darwin-prompts-in-check`
**Closes**: none
**Docs to update**: `documents/engineering/toolchain_bootstrap.md`, `documents/architecture/multiplexer_adapter.md`, `documents/operations/validation_runbook.md`

#### Objective

Darwin bootstrap and Haskell tmux readiness supplies its complete owned contract through the single phase-scoped gate verdict.

#### Deliverables

Reuse verified Command Line Tools and native build tools or report unmet readiness without opening setup dialogs. Haskell reuses qualified tmux, or prepares a verified existing Homebrew installation's tmux plan under consent; it does not bootstrap global Homebrew or alter shell setup. The same common identity/observation/guarded-input contract applies.

#### Validation

Linux exercises pure Darwin plans/refusals. A native Mac proves actual build, exec handoff, filesystem ownership and tmux behavior; missing CLT/Homebrew readiness never counts as a degraded pass or a human validation task.

Required executable evidence: `tests/integration/test_darwin_runtime.py::test_native_bootstrap_and_tmux_readiness`, `tests/integration/test_darwin_runtime.py::test_missing_clt_is_noninteractive_refusal`. Every named mutant must die for its recorded reason in those tests; a baseline failure or unrelated exception is not a kill.

#### Remaining Work

The whole sprint.

### Sprint 13.2: Native Darwin session and supervisor confirmation [Planned]

**Status**: Planned
**Implementation**: none — this sprint records acceptance evidence
**Validation tests**: `tests/integration/test_mux_real.py::test_private_server_roundtrip`, `tests/e2e/test_supervisor_scenarios.py::test_stop_supervisor_keeps_sessions`, `tests/integration/test_guarded_submit.py::test_changed_input_or_output_refuses`
**Mutants**: none — native positive/refusing twins
**Closes**: none
**Docs to update**: `documents/engineering/toolchain_bootstrap.md`, `documents/architecture/multiplexer_adapter.md`, `documents/operations/validation_runbook.md`

#### Objective

Native Darwin session and supervisor confirmation supplies its complete owned contract through the single phase-scoped gate verdict.

#### Deliverables

Record Linux and macOS receipts over this phase's actual prerequisite inputs. Preserve private socket path/permissions, Keychain-aware logged-out controls and no-input live evidence limits.

#### Validation

Run the public lifecycle and adversarial guarded-submission scenarios through real native tmux. Require no foreign-session changes, exact ownership and cleanup; a Linux/WSL result cannot stand in for a Darwin kernel observation.

Required executable evidence: `tests/integration/test_mux_real.py::test_private_server_roundtrip`, `tests/e2e/test_supervisor_scenarios.py::test_stop_supervisor_keeps_sessions`, `tests/integration/test_guarded_submit.py::test_changed_input_or_output_refuses`. Positive and refusing native controls retain independent expected outputs and actual resource observations.

#### Remaining Work

The whole sprint.

## Remaining Work

The whole phase: Sprints 13.1–13.2.

## Documentation Requirements

**Architecture docs to create/update:**

- `documents/architecture/multiplexer_adapter.md` — this phase's owned contract and links to prerequisite interfaces.

**Engineering docs to create/update:**

- `documents/engineering/toolchain_bootstrap.md` — doctrine, mechanisms and scope of executable evidence.

**Operations and reference docs to create/update:**

- `documents/operations/validation_runbook.md` — preparation, qualified host observations and actionable refusals.

**Cross-references to add:**

- `DEVELOPMENT_PLAN/00-overview.md` — requirement closure and lower-phase dependencies.
- `DEVELOPMENT_PLAN/system-components.md` — stable capability/path ownership.
- `DEVELOPMENT_PLAN/legacy_tracking_for_deletion.md` — remaining incompatible implementation shapes.
