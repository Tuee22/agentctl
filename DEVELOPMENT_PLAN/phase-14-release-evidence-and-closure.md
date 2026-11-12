# Phase 14 — Release evidence and closure

**Status**: Planned
**Depends on**: [Phase 11 — Windows application acceptance](phase-11-windows-application-acceptance.md), [Phase 12 — Linux live and clean acceptance](phase-12-linux-live-and-clean-acceptance.md), [Phase 13 — macOS acceptance](phase-13-macos-acceptance.md)
**Host lane**: linux
**Gate**: `agentctl check`
**Gate kind**: host-acceptance
**Closes**: none
**Gate evidence**: none recorded
**Evidence covers**: phase input closure and verified prerequisite receipts

> **Purpose**: Whole-product closure joins current independent native receipts and requires an empty migration ledger.

## Phase Objective

Whole-product closure joins current independent native receipts and requires an empty migration ledger. It runs on Linux and consumes already obtained native evidence; it does not require one machine or one phase to run both Windows and macOS.

This phase needs Linux only. The declared tests are executable contracts; an absent required test is unmet evidence, not existing proof. Acceptance-only test implementations belong to the prerequisite owner named in the inventory. Existing incompatible code is inventoried in the deletion ledger. No old implementation or unqualified receipt establishes this revised contract.

## Gate Integrity

| Requirement | Oracle | Observer | Mutants | Tests |
|---|---|---|---|---|
| R20 — Current requirement and artifact evidence join | `tests/oracles/requirements.toml` | real: independent inputs and nonce-bound native observations | none — native positive/refusing twins | `tests/governance/test_release_receipts.py::test_complete_current_requirement_receipts`, `tests/governance/test_release_receipts.py::test_foreign_receipt_input_identity` |
| R20 — Installed-package and exit definition | `tests/oracles/requirements.toml` | real: independent inputs and nonce-bound native observations | none — native positive/refusing twins | `tests/integration/test_release_install.py::test_source_only_pipx_package`, `tests/governance/test_release_receipts.py::test_empty_legacy_ledger_and_complete_gate` |

## Not Proven By This Gate

- A receipt's digest establishes input currency, not an independently attested historical run. Local receipt authenticity has the documented honest ceiling.
- A source rule or finite corpus does not prove arbitrary callback purity, universal termination or agent-internal readiness. Native operation and resource assumptions remain explicit.

## Confirms

- Complete current phase input receipts cover every required Linux, Windows and macOS capability and the complete product input identity.
- Installed package evidence includes source/patch resources and excludes distributed precompiled product/backend binaries.

## Sprints

### Sprint 14.1: Current requirement and artifact evidence join [Planned]

**Status**: Planned
**Implementation**: none — this sprint records acceptance evidence
**Validation tests**: `tests/governance/test_release_receipts.py::test_complete_current_requirement_receipts`, `tests/governance/test_release_receipts.py::test_foreign_receipt_input_identity`
**Mutants**: none — native positive/refusing twins
**Closes**: none
**Docs to update**: `documents/engineering/quality_gate.md`, `documents/operations/installation.md`, `documents/operations/validation_runbook.md`

#### Objective

Current requirement and artifact evidence join supplies its complete owned contract through the single phase-scoped gate verdict.

#### Deliverables

Join the Linux clean/live, native Windows and native macOS receipts already earned by their owners. Require all phases Done apart from this closing phase, every requirement closed once, no ledger shape, and all current source/backend/toolchain identities covered. The final aggregate receipt binds the complete product tree.

#### Validation

Modify an owned/shared input, backend artifact, patch set or receipt nonce and require affected evidence invalidation. A later-only change cannot invalidate unrelated earlier inputs, but the whole-product digest changes. Reject absent foreign evidence rather than demand both foreign hosts in this phase.

Required executable evidence: `tests/governance/test_release_receipts.py::test_complete_current_requirement_receipts`, `tests/governance/test_release_receipts.py::test_foreign_receipt_input_identity`. Positive and refusing native controls retain independent expected outputs and actual resource observations.

#### Remaining Work

The whole sprint.

### Sprint 14.2: Installed-package and exit definition [Planned]

**Status**: Planned
**Implementation**: none — this sprint records acceptance evidence
**Validation tests**: `tests/integration/test_release_install.py::test_source_only_pipx_package`, `tests/governance/test_release_receipts.py::test_empty_legacy_ledger_and_complete_gate`
**Mutants**: none — native positive/refusing twins
**Closes**: none
**Docs to update**: `documents/engineering/quality_gate.md`, `documents/operations/installation.md`, `documents/operations/validation_runbook.md`

#### Objective

Installed-package and exit definition supplies its complete owned contract through the single phase-scoped gate verdict.

#### Deliverables

Verify source-only wheel/sdist contents, installed Click entry point, pinned build inputs and public documentation through the same Linux application. Emit the aggregate passing EVIDENCE only after all required phase/lane verdicts and containment pass; no commit, publish or human review is necessary.

#### Validation

Install the owned package in isolated Linux storage and verify first-run/warm reuse and raw commands. Refuse a shipped native runtime artifact, missing source/patch resource, hidden Python file, stale receipt or residual deletion row. Publishing remains outside the gate.

Required executable evidence: `tests/integration/test_release_install.py::test_source_only_pipx_package`, `tests/governance/test_release_receipts.py::test_empty_legacy_ledger_and_complete_gate`. Positive and refusing native controls retain independent expected outputs and actual resource observations.

#### Remaining Work

The whole sprint.

## Remaining Work

The whole phase: Sprints 14.1–14.2.

## Documentation Requirements

**Architecture docs to create/update:**

- None.

**Engineering docs to create/update:**

- `documents/engineering/quality_gate.md` — doctrine, mechanisms and scope of executable evidence.

**Operations and reference docs to create/update:**

- `documents/operations/installation.md` — preparation, qualified host observations and actionable refusals.
- `documents/operations/validation_runbook.md` — preparation, qualified host observations and actionable refusals.

**Cross-references to add:**

- `DEVELOPMENT_PLAN/00-overview.md` — requirement closure and lower-phase dependencies.
- `DEVELOPMENT_PLAN/system-components.md` — stable capability/path ownership.
- `DEVELOPMENT_PLAN/legacy_tracking_for_deletion.md` — remaining incompatible implementation shapes.
