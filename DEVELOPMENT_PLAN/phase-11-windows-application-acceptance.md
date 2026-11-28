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

Native Windows acceptance of the shared application, private psmux artifact and registered resources. It adds no product behavior and confirms lower contracts through public commands; the dedicated guest supplies only the `linux` half and never replaces these native observations ([T.E](development_plan_standards.md#te-unspoofable-test) E6). A Windows source revision or same-version banner is not proof that a running server or client contains the accepted fixes.

This phase's verdict evaluates the `linux` and `windows` halves ([T.V](development_plan_standards.md#tv-verdict) V8) at stage 2 ([T.W](development_plan_standards.md#tw-staged-enforcement)); a native Windows run reads the `linux` half from the latest stored guest receipt with equal logical and prerequisite identities. Every cited artifact is owned within closure(11) ([§ A](development_plan_standards.md#a-well-ordered-constructive-narrative)), and each acceptance node is implemented in a module of the lower phase that owns its contract; a planned absence is unmet work of this phase ([T.F](development_plan_standards.md#tf-shared-and-owned-failures)), and present incompatible code is a deletion-ledger row of its owner. This phase receives the native Windows confirmations that lower phases owe it, each paired with one Confirms line.

## Gate Integrity

| Requirement | Oracle | Observer | Mutants | Tests |
|---|---|---|---|---|
| R7 — Native launch, handoff and logged-out refusal | `tests/oracles/mux_commands.toml` | real: installed agent status commands refusing in isolated private configuration on the named host; observer: nonce-bound native reattachment and child-handoff exit-status observations | none — closure-owned mutants with all their killers follow P0-18 | `tests/e2e/test_launch.py::test_rerun_reattaches_without_preflight`, `tests/integration/test_handoff.py::test_child_mode_propagates_exit_status`, `tests/integration/test_agent_real.py::test_logged_out_by_construction` |
| R17 — Native supervisor stop keeps sessions | `tests/oracles/forbidden_actions.toml` | observer: nonce-bound native session and process observations across a supervisor stop | none — closure-owned mutants with all their killers follow P0-18 | `tests/e2e/test_supervisor_scenarios.py::test_stop_supervisor_keeps_sessions` |
| R16 — Windows owned-resource and artifact evidence | `tests/oracles/backend_profiles.toml` | real: native Windows owned-resource cleanup and running-artifact identity on the named host | none — closure-owned mutants with all their killers follow P0-18 | `tests/integration/test_owned_resources.py::test_native_windows_ownership_and_cleanup`, `tests/integration/test_psmux_isolation.py::test_manifest_matches_running_backend` |

## Not Proven By This Gate

- Limits: [T.C](development_plan_standards.md#tc-ceiling); none is a closure condition.
- Native observations cover only the Windows host and psmux artifact that the verified run recorded.

## Confirms

A native Windows run confirms, through public commands, each lower item that no Linux run can observe; native clients and servers match the qualified artifact, and no system registry or existing session is mutated. Each item is discharged on the `windows` half only when the evidence citations of its source row pass natively there and satisfy [T.E](development_plan_standards.md#te-unspoofable-test) at this phase's stage, and a failure of those citations on that half is this phase's (D-159).

- R3 — native Windows ghcup, GHC and cabal bootstrap (owed by [Python bootstrap and handoff](phase-2-python-bootstrap-and-handoff.md)).
- R22 — Win32 process, ACL and console-stop branches (owed by [Haskell runtime and platform policy](phase-3-haskell-runtime-and-platform-policy.md)).
- R9 — PATHEXT discovery and verbatim argv (owed by [Agent preflight and launch](phase-5-agent-preflight-and-launch.md)).
- R16 — Windows registry and endpoint identity (owed by [Session management and adoption](phase-6-session-management-and-adoption.md)).
- R17 — Windows console stop keeps managed and adopted sessions (owed by [Recovery and supervisor](phase-8-recovery-and-supervisor.md)).

## Sprints

### Sprint 11.1: Native application and lifecycle receipts [Planned]

**Status**: Planned
**Implementation**: none — this sprint records acceptance evidence
**Validation tests**: `tests/e2e/test_launch.py::test_rerun_reattaches_without_preflight`, `tests/integration/test_handoff.py::test_child_mode_propagates_exit_status`, `tests/e2e/test_supervisor_scenarios.py::test_stop_supervisor_keeps_sessions`, `tests/integration/test_agent_real.py::test_logged_out_by_construction`
**Mutants**: none — closure-owned mutants with all their killers follow P0-18
**Closes**: none
**Docs to update**: none — this sprint changes no page; the Governance pages already state its mechanics (D-148)

#### Objective

Native application and lifecycle receipts supplies its complete owned contract through the single phase-scoped gate verdict.

#### Deliverables

Record native Windows executable/PATHEXT, folder case identity, argv, UTF-8, trampoline exit status, managed/adopted lifecycle and real guarded-supervisor receipts. Agent status branches assert their observed refusal or launch without sending live prompts. Once P0-18 lets a row cite mutants owned within its closure, each Gate Integrity row of this phase cites them with every killer.

Owed Windows items are discharged only when the `real` or `observer` citations of their source rows pass natively here; value and model-backed citations never discharge them (D-159, D-175).

#### Validation

Run public commands against native psmux and native fake agents. Preserve exact bytes, instance identities and native stop/lock behavior; a stopped supervisor never kills a target. Native status probes use copied private or empty test state, never login operations.

Every node in **Validation tests** passes in a verified run and every named mutant is killed per [T.K](development_plan_standards.md#tk-kill) at stage 2.

#### Remaining Work

The whole sprint.

### Sprint 11.2: Windows owned-resource and artifact evidence [Planned]

**Status**: Planned
**Implementation**: none — this sprint records acceptance evidence
**Validation tests**: `tests/integration/test_owned_resources.py::test_native_windows_ownership_and_cleanup`, `tests/integration/test_psmux_isolation.py::test_manifest_matches_running_backend`
**Mutants**: none — closure-owned mutants with all their killers follow P0-18
**Closes**: none
**Docs to update**: none — this sprint changes no page; the Governance pages already state its mechanics (D-148)

#### Objective

Windows owned-resource and artifact evidence supplies its complete owned contract through the single phase-scoped gate verdict.

#### Deliverables

Evaluate this phase's `windows` half over its input closure, including the actual backend artifact and build policy, and read its `linux` half from the receipt store. Include short external workspaces, private registries, process/job identity and full diagnostics in containment. [Windows backend qualification](phase-10-windows-backend-qualification.md) implements the owned-resource and running-artifact nodes in its own modules, and this sprint consumes them.

#### Validation

Fail the Windows verdict for a live owned process, leaked endpoint, unsafe path, undeleted private workspace or erased primary failure. Accept reaped controls, require executable identity to match the receipt and retain the report outside disposable storage.

Every node in **Validation tests** passes in a verified run and every named mutant is killed per [T.K](development_plan_standards.md#tk-kill) at stage 2.

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

- None.

**Cross-references to add:**

- `DEVELOPMENT_PLAN/00-overview.md` — requirement closure and lower-phase dependencies.
- `DEVELOPMENT_PLAN/system-components.md` — stable capability/path ownership.
- `DEVELOPMENT_PLAN/legacy_tracking_for_deletion.md` — remaining incompatible implementation shapes.
