# Phase 0 — Governance and phase evidence

**Status**: Active
**Depends on**: nothing
**Host lane**: linux
**Gate**: `agentctl check`
**Gate kind**: self-verifying
**Closes**: R14.1, R26

> **Purpose**: The governed target architecture, requirement ownership, legacy census and one gate with independent phase and lane verdicts.

## Phase Objective

The governed target architecture, requirement ownership, legacy census and one gate with independent phase and lane verdicts. The first migration replaces global early-abort closure and whole-tree-only phase evidence without weakening any test, mutant or integrity oracle.

This phase needs Linux only. The declared tests are executable contracts; an absent required test is unmet evidence, not existing proof. Acceptance-only test implementations belong to the prerequisite owner named in the inventory. Existing incompatible code is inventoried in the deletion ledger. No old implementation or unqualified receipt establishes this revised contract.

## Gate Integrity

| Requirement | Oracle | Observer | Mutants | Tests |
|---|---|---|---|---|
| R26 — Plan and ownership contracts | `tests/oracles/phase_ownership.toml` | value; observer: independent inputs and nonce-bound native observations | `M-phase-hardware-budget` | `tests/governance/test_plan_validator.py::test_plan_fileset`, `tests/governance/test_phase_reports.py::test_hardware_budget`, `tests/integration/test_wsl_binding.py::test_shared_checkout_identity` |
| R14.1 — Independent phase verdicts and input identity | `tests/oracles/phase_ownership.toml` | value; observer: independent inputs and nonce-bound native observations | `M-phase-later-failure-poisons-earlier`, `M-phase-shared-failure-ignored`, `M-phase-input-dependency-omitted` | `tests/governance/test_phase_reports.py::test_later_failure_preserves_earlier_verdict`, `tests/governance/test_phase_reports.py::test_shared_failure_invalidates_dependents`, `tests/governance/test_phase_reports.py::test_receipt_input_closure` |
| R14.1 — Complete collection and governance validation | `tests/oracles/phase_ownership.toml` | value; observer: independent inputs and nonce-bound native observations | `M-phase-incomplete-collection`, `M-phase-future-id-gates-earlier` | `tests/governance/test_gate_plugin.py::test_no_skip`, `tests/governance/test_phase_reports.py::test_complete_collection_without_selection`, `tests/governance/test_phase_reports.py::test_future_missing_ids_are_owned` |

## Not Proven By This Gate

- A receipt's digest establishes input currency, not an independently attested historical run. Local receipt authenticity has the documented honest ceiling.
- A source rule or finite corpus does not prove arbitrary callback purity, universal termination or agent-internal readiness. Native operation and resource assumptions remain explicit.
- Foreign-kernel behavior is outside this phase's Linux verdict. Later native implementation extends the common contract and cannot retroactively add a foreign-hardware requirement here.

## Sprints

### Sprint 0.1: Plan and ownership contracts [Active]

**Status**: Active
**Implementation**: `tests/integration/test_wsl_binding.py`, `tests/oracles/phase_ownership.toml`, `DEVELOPMENT_PLAN/`, `AGENTS.md`, `CLAUDE.md`, `documents/`
**Validation tests**: `tests/governance/test_plan_validator.py::test_plan_fileset`, `tests/governance/test_phase_reports.py::test_hardware_budget`, `tests/integration/test_wsl_binding.py::test_shared_checkout_identity`
**Mutants**: `M-phase-hardware-budget`
**Closes**: R26
**Docs to update**: `documents/documentation_standards.md`, `documents/engineering/quality_gate.md`, `documents/engineering/testing.md`, `documents/operations/validation_runbook.md`

#### Objective

Plan and ownership contracts supplies its complete owned contract through the single phase-scoped gate verdict.

#### Deliverables

Declare the source/test/receipt ownership model, revised statuses and deletion owners. Document dedicated Debian WSL2 capacity, dependencies and the same-checkout bind mount before Linux validation.

#### Validation

Construct a phase requiring both Windows and macOS and require refusal; accept Linux with either family separately. On ordinary Debian, constructed host/mount facts prove both route-policy branches without requiring Windows. When this Linux run uses WSL2, its actual pre-gate bind-mounted nonce written from each side must identify the same checkout, including unstaged and untracked files. No git commit or copied checkout can satisfy that route evidence.

Required executable evidence: `tests/governance/test_plan_validator.py::test_plan_fileset`, `tests/governance/test_phase_reports.py::test_hardware_budget`, `tests/integration/test_wsl_binding.py::test_shared_checkout_identity`. Every named mutant must die for its recorded reason in those tests; a baseline failure or unrelated exception is not a kill.

#### Remaining Work

Reconcile the governed documents and ownership declarations and implement their validation controls. Sprints 0.2 and 0.3 supply the gate/report instrumentation needed to close this sprint; work them in order and return here for executable closure. Specification edits alone do not close this sprint.

### Sprint 0.2: Independent phase verdicts and input identity [Planned]

**Status**: Planned
**Implementation**: `src/agentctl/check/steps.py`, `src/agentctl/check/evidence.py`, `src/agentctl/check/phase_reports.py`, `src/agentctl/check/validator/`
**Validation tests**: `tests/governance/test_phase_reports.py::test_later_failure_preserves_earlier_verdict`, `tests/governance/test_phase_reports.py::test_shared_failure_invalidates_dependents`, `tests/governance/test_phase_reports.py::test_receipt_input_closure`
**Mutants**: `M-phase-later-failure-poisons-earlier`, `M-phase-shared-failure-ignored`, `M-phase-input-dependency-omitted`
**Closes**: none
**Docs to update**: `documents/documentation_standards.md`, `documents/engineering/quality_gate.md`, `documents/engineering/testing.md`, `documents/operations/validation_runbook.md`

#### Objective

Independent phase verdicts and input identity supplies its complete owned contract through the single phase-scoped gate verdict.

#### Deliverables

Implement the generic receipt/aggregate validators and their tests in tests/governance/test_release_receipts.py, plus the requirements/host-lane schema oracles. These validate constructed complete/missing receipt sets here; final product acceptance consumes their actual current receipts. Run every introduced leg, retain failures and emit nonce-bound per-phase/per-lane reports. An immutable ownership manifest and prerequisite closure define phase input digests independently of the numbering. Overall failure remains visible; only the complete relevant phase verdict authorizes its closure.

#### Validation

Make a later owned test or native component build fail and require an earlier complete verdict to pass while the overall verdict fails. Accept a lower host-acceptance receipt as an explicit prerequisite and refuse a same/higher prerequisite. Change a shared prerequisite or corrupt a nonce and require every consuming verdict to fail. Change later-only source and require an earlier input digest to remain stable; change its shared source and require invalidation.

Required executable evidence: `tests/governance/test_phase_reports.py::test_later_failure_preserves_earlier_verdict`, `tests/governance/test_phase_reports.py::test_shared_failure_invalidates_dependents`, `tests/governance/test_phase_reports.py::test_receipt_input_closure`. Every named mutant must die for its recorded reason in those tests; a baseline failure or unrelated exception is not a kill.

#### Remaining Work

The whole sprint.

### Sprint 0.3: Complete collection and governance validation [Planned]

**Status**: Planned
**Implementation**: `src/agentctl/check/gate_plugin.py`, `src/agentctl/check/legs.py`, `src/agentctl/check/validator/`, `tests/oracles/check_steps.toml`
**Validation tests**: `tests/governance/test_phase_reports.py::test_owned_collection_error_is_local`, `tests/governance/test_gate_plugin.py::test_no_skip`, `tests/governance/test_phase_reports.py::test_complete_collection_without_selection`, `tests/governance/test_phase_reports.py::test_future_missing_ids_are_owned`
**Mutants**: `M-phase-incomplete-collection`, `M-phase-future-id-gates-earlier`
**Closes**: R14.1
**Docs to update**: `documents/documentation_standards.md`, `documents/engineering/quality_gate.md`, `documents/engineering/testing.md`, `documents/operations/validation_runbook.md`

#### Objective

Complete collection and governance validation supplies its complete owned contract through the single phase-scoped gate verdict.

#### Deliverables

Census every present first-party file, test, oracle and mutant, including recorded legacy shapes. Run all present collected tests without selection. Attribute absent future tests to their declared capability; an absent required test fails its owner, never supplies a pass.

#### Validation

Require exact collected/executed equality and refuse skip, xfail, deselection, absent targets and unowned artifacts. A missing future test keeps its phase incomplete without invalidating a complete earlier verdict. An independently owned later syntax/import/collection error is retained as a failed-module record while independent earlier modules still collect and execute; shared or ambiguous collection damage invalidates every consumer. Collection or observer integrity failures invalidate the consumers whose evidence is untrustworthy.

Required executable evidence: `tests/governance/test_gate_plugin.py::test_no_skip`, `tests/governance/test_phase_reports.py::test_complete_collection_without_selection`, `tests/governance/test_phase_reports.py::test_future_missing_ids_are_owned`. Every named mutant must die for its recorded reason in those tests; a baseline failure or unrelated exception is not a kill.

#### Remaining Work

The whole sprint.

## Remaining Work

Sprints 0.1–0.3 require executable governance/ownership controls, independent phase/lane reporting, current input identity and complete collection evidence. Existing validators and monolithic gate behavior require migration; no phase closure is claimed.

## Documentation Requirements

**Architecture docs to create/update:**

- None.

**Engineering docs to create/update:**

- `documents/documentation_standards.md` — doctrine, mechanisms and scope of executable evidence.
- `documents/engineering/quality_gate.md` — doctrine, mechanisms and scope of executable evidence.
- `documents/engineering/testing.md` — doctrine, mechanisms and scope of executable evidence.

**Operations and reference docs to create/update:**

- `documents/operations/validation_runbook.md` — preparation, qualified host observations and actionable refusals.

**Cross-references to add:**

- `DEVELOPMENT_PLAN/00-overview.md` — requirement closure and lower-phase dependencies.
- `DEVELOPMENT_PLAN/system-components.md` — stable capability/path ownership.
- `DEVELOPMENT_PLAN/legacy_tracking_for_deletion.md` — remaining incompatible implementation shapes.
