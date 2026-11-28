# Phase 14 — Release evidence and closure

**Status**: Planned
**Depends on**: [Phase 11 — Windows application acceptance](phase-11-windows-application-acceptance.md), [Phase 12 — Linux live and clean acceptance](phase-12-linux-live-and-clean-acceptance.md), [Phase 13 — macOS acceptance](phase-13-macos-acceptance.md)
**Host lane**: linux
**Gate**: `agentctl check`
**Gate kind**: host-acceptance
**Closes**: none
**Gate evidence**: none recorded
**Evidence covers**: phase input closure and verified prerequisite receipts

> **Purpose**: Whole-product closure joins every phase's current verified halves and requires an empty migration ledger.

## Phase Objective

Whole-product closure joins every phase's current verified halves and requires an empty migration ledger. It runs on Linux and consumes already obtained native evidence; it does not require one machine or one phase to run both Windows and macOS.

This phase's verdict evaluates the `linux` half ([T.V](development_plan_standards.md#tv-verdict) V8) at stage 2 ([T.W](development_plan_standards.md#tw-staged-enforcement)) and requires every other phase to pass in the same verified run, each half the run does not evaluate natively coming from its latest stored receipt with equal logical and prerequisite identities (V8, V9); a Done status binds only a verified `pass` ([T.D](development_plan_standards.md#td-status-and-progression)). A gap that is only a prerequisite's absent half leaves this phase `awaiting:prerequisite` ([T.V](development_plan_standards.md#tv-verdict)). [macOS acceptance](phase-13-macos-acceptance.md) is worked while its verdict is `fail` and is blocked as `awaiting:macos` only once its `linux` half passes and `macos` is its only gap, so until a Mac exists the terminal state is `selection: stop` listing what each blocked phase awaits. Every cited artifact is owned within closure(14) ([§ A](development_plan_standards.md#a-well-ordered-constructive-narrative)), a planned absence is unmet work of this phase ([T.F](development_plan_standards.md#tf-shared-and-owned-failures)), and present incompatible code is a deletion-ledger row of its owner. `EVIDENCE pass` is printed only when every phase passes ([T.O](development_plan_standards.md#to-output)).

## Gate Integrity

| Requirement | Oracle | Observer | Mutants | Tests |
|---|---|---|---|---|
| R24 — Current requirement and artifact evidence join | `tests/oracles/requirements.toml` | value: independent requirement-receipt, half-join and foreign-identity expectations | none — closure-owned mutants with all their killers follow P0-18 | `tests/governance/test_release_receipts.py::test_complete_current_requirement_receipts`, `tests/governance/test_release_receipts.py::test_foreign_receipt_input_identity` |
| R14 — Installed-package and exit definition | `tests/oracles/requirements.toml` | value: independent installed-package, empty-ledger and exit expectations | none — closure-owned mutants with all their killers follow P0-18 | `tests/integration/test_release_install.py::test_source_only_pipx_package`, `tests/governance/test_release_exit.py::test_empty_legacy_ledger_and_complete_gate` |

## Not Proven By This Gate

- Limits: [T.C](development_plan_standards.md#tc-ceiling); none is a closure condition.
- Whole-product closure covers the halves that verified runs supplied, never publication or installation on another host.

## Confirms

- Complete current phase input receipts cover every required Linux, Windows and macOS capability and the complete product input identity.
- Installed package evidence includes source/patch resources and excludes distributed precompiled product/backend binaries.

## Sprints

### Sprint 14.1: Current requirement and artifact evidence join [Planned]

**Status**: Planned
**Implementation**: none — this sprint records acceptance evidence
**Validation tests**: `tests/governance/test_release_receipts.py::test_complete_current_requirement_receipts`, `tests/governance/test_release_receipts.py::test_foreign_receipt_input_identity`
**Mutants**: none — closure-owned mutants with all their killers follow P0-18
**Closes**: none
**Docs to update**: migrates `documents/operations/installation.md` (owner [Python bootstrap and handoff](phase-2-python-bootstrap-and-handoff.md))

#### Objective

Current requirement and artifact evidence join supplies its complete owned contract through the single phase-scoped gate verdict.

#### Deliverables

Join every phase's current verified halves: each phase passes in this verified run, and each half the run does not evaluate natively comes from its latest stored receipt with equal logical and prerequisite identities ([T.V](development_plan_standards.md#tv-verdict) V8, V9). Require every requirement closed once, no ledger shape, and all current source/backend/toolchain identities covered. The final aggregate receipt binds the complete product tree. This sprint consumes the receipt record validators of [Governance and phase evidence](phase-0-governance-and-phase-evidence.md); once P0-18 lets a row cite mutants owned within its closure, each Gate Integrity row of this phase cites them with every killer.

#### Validation

Modify an owned/shared input, backend artifact, patch set or receipt nonce and require affected evidence invalidation. A later-only change cannot invalidate unrelated earlier inputs, but the whole-product digest changes. A prerequisite's absent half yields `awaiting:prerequisite` rather than a demand for both foreign hosts in this phase.

Every node in **Validation tests** passes in a verified run and every named mutant is killed per [T.K](development_plan_standards.md#tk-kill) at stage 2.

#### Remaining Work

The whole sprint.

### Sprint 14.2: Installed-package and exit definition [Planned]

**Status**: Planned
**Implementation**: `tests/governance/test_release_exit.py`
**Validation tests**: `tests/integration/test_release_install.py::test_source_only_pipx_package`, `tests/governance/test_release_exit.py::test_empty_legacy_ledger_and_complete_gate`
**Mutants**: none — closure-owned mutants with all their killers follow P0-18
**Closes**: none
**Docs to update**: migrates `documents/operations/installation.md` (owner [Python bootstrap and handoff](phase-2-python-bootstrap-and-handoff.md))

#### Objective

Installed-package and exit definition supplies its complete owned contract through the single phase-scoped gate verdict.

#### Deliverables

Verify source-only wheel/sdist contents, installed Click entry point, pinned build inputs and public documentation through the same Linux application. `EVIDENCE pass` is printed only when every phase passes, and the exit code is 0 only when V1 holds, every step code is 0 and every phase passes ([T.O](development_plan_standards.md#to-output)); no commit, publish or human review is necessary. This phase's own `tests/governance/test_release_exit.py` holds the empty-ledger and complete-gate exit check of the whole product, and this sprint consumes the installed-package node of [Python bootstrap and handoff](phase-2-python-bootstrap-and-handoff.md).

#### Validation

Install the owned package in isolated Linux storage and verify first-run/warm reuse and raw commands. Refuse a shipped native runtime artifact, missing source/patch resource, hidden Python file, stale receipt or residual deletion row. Publishing remains outside the gate.

Every node in **Validation tests** passes in a verified run and every named mutant is killed per [T.K](development_plan_standards.md#tk-kill) at stage 2.

#### Remaining Work

The whole sprint.

## Remaining Work

The whole phase: Sprints 14.1–14.2.

## Documentation Requirements

**Architecture docs to create/update:**

- None.

**Engineering docs to create/update:**

- None.

**Operations and reference docs to create/update:**

- migrates `documents/operations/installation.md` (owner [Python bootstrap and handoff](phase-2-python-bootstrap-and-handoff.md)) — preparation, qualified host observations and actionable refusals.

**Cross-references to add:**

- `DEVELOPMENT_PLAN/00-overview.md` — requirement closure and lower-phase dependencies.
- `DEVELOPMENT_PLAN/system-components.md` — stable capability/path ownership.
- `DEVELOPMENT_PLAN/legacy_tracking_for_deletion.md` — remaining incompatible implementation shapes.
