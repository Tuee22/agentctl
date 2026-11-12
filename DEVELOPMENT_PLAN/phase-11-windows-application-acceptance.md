# Phase 11 — Windows application acceptance

**Status**: Planned
**Depends on**: [Phase 10 — Windows backend qualification](phase-10-windows-backend-qualification.md)
**Host lane**: linux-windows
**Gate**: `agentctl check`
**Gate kind**: host-acceptance
**Closes**: none
**Gate evidence**: none recorded
**Evidence covers**: phase input closure and verified prerequisite receipts

> **Purpose**: Native Windows acceptance of the shared application, private psmux artifact and registered resources.

## Phase Objective

Native Windows acceptance of the shared application, private psmux artifact and registered resources. It adds no product behavior and confirms lower contracts through public commands; WSL Linux results cannot replace these native observations.

This phase needs Linux and native Windows. Its receipts can come from separate runs with the same logical source/policy/prerequisite identity and separately verified lane-native artifact/toolchain identities; no other foreign hardware is required. The declared tests are executable contracts; an absent required test is unmet evidence, not existing proof. Acceptance-only test implementations belong to the prerequisite owner named in the inventory. Existing incompatible code is inventoried in the deletion ledger. No old implementation or unqualified receipt establishes this revised contract.

## Gate Integrity

| Requirement | Oracle | Observer | Mutants | Tests |
|---|---|---|---|---|
| R20 — Native application and lifecycle receipts | `tests/oracles/backend_profiles.toml` | real: independent inputs and nonce-bound native observations | none — native positive/refusing twins | `tests/e2e/test_launch.py::test_rerun_reattaches_without_preflight`, `tests/integration/test_handoff.py::test_child_mode_propagates_exit_status`, `tests/e2e/test_supervisor_scenarios.py::test_stop_supervisor_keeps_sessions`, `tests/integration/test_agent_real.py::test_logged_out_by_construction` |
| R20 — Windows owned-resource and artifact evidence | `tests/oracles/backend_profiles.toml` | real: independent inputs and nonce-bound native observations | none — native positive/refusing twins | `tests/integration/test_owned_resources.py::test_native_windows_ownership_and_cleanup`, `tests/integration/test_psmux_build.py::test_manifest_matches_running_backend` |

## Not Proven By This Gate

- A receipt's digest establishes input currency, not an independently attested historical run. Local receipt authenticity has the documented honest ceiling.
- A source rule or finite corpus does not prove arbitrary callback purity, universal termination or agent-internal readiness. Native operation and resource assumptions remain explicit.
- WSL is Linux evidence only. A Windows source revision or same-version banner is not proof that a running server or client contains the accepted fixes.

## Confirms

- Native Windows confirms bootstrap, typed process/filesystem boundaries, private runtime preparation, exact target identity and guarded recovery promised by the lower common contracts.
- Native clients and servers match the qualified artifact, and no system registry or existing session is mutated.

## Sprints

### Sprint 11.1: Native application and lifecycle receipts [Planned]

**Status**: Planned
**Implementation**: none — this sprint records acceptance evidence
**Validation tests**: `tests/e2e/test_launch.py::test_rerun_reattaches_without_preflight`, `tests/integration/test_handoff.py::test_child_mode_propagates_exit_status`, `tests/e2e/test_supervisor_scenarios.py::test_stop_supervisor_keeps_sessions`, `tests/integration/test_agent_real.py::test_logged_out_by_construction`
**Mutants**: none — native positive/refusing twins
**Closes**: none
**Docs to update**: `documents/operations/validation_runbook.md`

#### Objective

Native application and lifecycle receipts supplies its complete owned contract through the single phase-scoped gate verdict.

#### Deliverables

Record native Windows executable/PATHEXT, folder case identity, argv, UTF-8, trampoline exit status, managed/adopted lifecycle and real guarded-supervisor receipts. Authentication branches assert their observed refusal or launch without sending live prompts.

#### Validation

Run public commands against native psmux and native fake agents. Preserve exact bytes, instance identities and native stop/lock behavior; a stopped supervisor never kills a target. Native auth status probes use copied private or empty test state, never login operations.

Required executable evidence: `tests/e2e/test_launch.py::test_rerun_reattaches_without_preflight`, `tests/integration/test_handoff.py::test_child_mode_propagates_exit_status`, `tests/e2e/test_supervisor_scenarios.py::test_stop_supervisor_keeps_sessions`, `tests/integration/test_agent_real.py::test_logged_out_by_construction`. Positive and refusing native controls retain independent expected outputs and actual resource observations.

#### Remaining Work

The whole sprint.

### Sprint 11.2: Windows owned-resource and artifact evidence [Planned]

**Status**: Planned
**Implementation**: none — this sprint records acceptance evidence
**Validation tests**: `tests/integration/test_owned_resources.py::test_native_windows_ownership_and_cleanup`, `tests/integration/test_psmux_build.py::test_manifest_matches_running_backend`
**Mutants**: none — native positive/refusing twins
**Closes**: none
**Docs to update**: `documents/operations/validation_runbook.md`

#### Objective

Windows owned-resource and artifact evidence supplies its complete owned contract through the single phase-scoped gate verdict.

#### Deliverables

Record current phase-input receipt rows for Linux and Windows, including the actual backend artifact and build policy. Include short external workspaces, private registries, process/job identity and full diagnostics in containment.

#### Validation

Fail the Windows verdict for a live owned process, leaked endpoint, unsafe path, undeleted private workspace or erased primary failure. Accept reaped controls, require executable identity to match the receipt and retain the report outside disposable storage.

Required executable evidence: `tests/integration/test_owned_resources.py::test_native_windows_ownership_and_cleanup`, `tests/integration/test_psmux_build.py::test_manifest_matches_running_backend`. Positive and refusing native controls retain independent expected outputs and actual resource observations.

#### Remaining Work

The whole sprint.

## Remaining Work

The whole phase: Sprints 11.1–11.2.

## Documentation Requirements

**Architecture docs to create/update:**

- None.

**Engineering docs to create/update:**

- None.

**Operations and reference docs to create/update:**

- `documents/operations/validation_runbook.md` — preparation, qualified host observations and actionable refusals.

**Cross-references to add:**

- `DEVELOPMENT_PLAN/00-overview.md` — requirement closure and lower-phase dependencies.
- `DEVELOPMENT_PLAN/system-components.md` — stable capability/path ownership.
- `DEVELOPMENT_PLAN/legacy_tracking_for_deletion.md` — remaining incompatible implementation shapes.
