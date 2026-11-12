# Phase 8 — Recovery and supervisor

**Status**: Planned
**Depends on**: [Phase 7 — Pane observation and classification](phase-7-pane-observation-and-classification.md)
**Host lane**: linux
**Gate**: `agentctl check`
**Gate kind**: self-verifying
**Closes**: R17, R18, R18.3, R18.4, R18.5, R18.6, R19

> **Purpose**: The complete Linux recovery application consumes the already-qualified observation and conditional-submission capability.

## Phase Objective

The complete Linux recovery application consumes the already-qualified observation and conditional-submission capability. It never invents backend safety from a version string, a stable cursor or a successful first half of a split send.

This phase needs Linux only. The declared tests are executable contracts; an absent required test is unmet evidence, not existing proof. Acceptance-only test implementations belong to the prerequisite owner named in the inventory. Existing incompatible code is inventoried in the deletion ledger. No old implementation or unqualified receipt establishes this revised contract.

## Gate Integrity

| Requirement | Oracle | Observer | Mutants | Tests |
|---|---|---|---|---|
| R18 — Pure recovery transitions and bounded timing | `tests/oracles/requirements.toml` | value; observer: independent inputs and nonce-bound native observations | `M-machine-send-during-work`, `M-backoff-unbounded`, `M-machine-stale-fingerprint` | `tests/unit/test_recovery_transitions.py::test_every_cell_matches_oracle`, `haskell:agentctl-core-test/Machine/never-send-unsafe` |
| R17 — Supervisor lifecycle, receipts and scenarios | `tests/oracles/requirements.toml` | value; observer: independent inputs and nonce-bound native observations | `M-supervisor-stop-kills-session`, `M-delivery-uncertain-repeated`, `M-log-observation-omitted` | `tests/e2e/test_supervisor_scenarios.py::test_stop_supervisor_keeps_sessions`, `tests/e2e/test_supervisor_run.py::test_sends_once_after_initial_delay`, `tests/integration/test_guarded_submit.py::test_unknown_delivery_never_retries_blindly`, `tests/e2e/test_supervisor_log.py::test_records_match_schema` |

## Not Proven By This Gate

- A receipt's digest establishes input currency, not an independently attested historical run. Local receipt authenticity has the documented honest ceiling.
- A source rule or finite corpus does not prove arbitrary callback purity, universal termination or agent-internal readiness. Native operation and resource assumptions remain explicit.
- Foreign-kernel behavior is outside this phase's Linux verdict. Later native implementation extends the common contract and cannot retroactively add a foreign-hardware requirement here.

## Sprints

### Sprint 8.1: Pure recovery transitions and bounded timing [Planned]

**Status**: Planned
**Implementation**: `src/agentctl/haskell/src/AgentCtl/Recovery/`, `tests/oracles/recovery_transitions.toml`, `tests/oracles/backoff.toml`
**Validation tests**: `tests/unit/test_recovery_transitions.py::test_every_cell_matches_oracle`, `haskell:agentctl-core-test/Machine/never-send-unsafe`
**Mutants**: `M-machine-send-during-work`, `M-backoff-unbounded`, `M-machine-stale-fingerprint`
**Closes**: R18, R18.3, R18.4, R19
**Docs to update**: `documents/architecture/supervisor_contract.md`, `documents/reference/cli_reference.md`, `documents/engineering/testing.md`

#### Objective

Pure recovery transitions and bounded timing supplies its complete owned contract through the single phase-scoped gate verdict.

#### Deliverables

Implement closed recovery states, explicit monotonic time and seeded jitter, fingerprint handling and bounded retries. The action vocabulary contains conditional submission and notification, never login, model change or arbitrary restart.

#### Validation

Enumerate the independent transition oracle and generated finite histories beside successful recovery controls. Stale text, unknown observations, work and dialogs cannot generate submission. Invalid backoff inputs produce named failures.

Required executable evidence: `tests/unit/test_recovery_transitions.py::test_every_cell_matches_oracle`, `haskell:agentctl-core-test/Machine/never-send-unsafe`. Every named mutant must die for its recorded reason in those tests; a baseline failure or unrelated exception is not a kill.

#### Remaining Work

The whole sprint.

### Sprint 8.2: Supervisor lifecycle, receipts and scenarios [Planned]

**Status**: Planned
**Implementation**: `src/agentctl/haskell/src/AgentCtl/Supervisor/`, `src/agentctl/haskell/app/ScriptedAgent.hs`, `tests/e2e/test_supervisor_scenarios.py`
**Validation tests**: `tests/e2e/test_supervisor_scenarios.py::test_stop_supervisor_keeps_sessions`, `tests/e2e/test_supervisor_run.py::test_sends_once_after_initial_delay`, `tests/integration/test_guarded_submit.py::test_unknown_delivery_never_retries_blindly`, `tests/e2e/test_supervisor_log.py::test_records_match_schema`
**Mutants**: `M-supervisor-stop-kills-session`, `M-delivery-uncertain-repeated`, `M-log-observation-omitted`
**Closes**: R17, R18.5, R18.6
**Docs to update**: `documents/architecture/supervisor_contract.md`, `documents/reference/cli_reference.md`, `documents/engineering/testing.md`

#### Objective

Supervisor lifecycle, receipts and scenarios supplies its complete owned contract through the single phase-scoped gate verdict.

#### Deliverables

Introduce tests/live/test_live_supervisor.py with ordinary no-live-input controls and authenticated-lane observer receipts. Implement watch/pause/unwatch/resume/logs and single-instance foreground supervision with immutable decision records. Unknown delivery is explicit and halts or escalates rather than blindly resending. Strict finite fixture reads close handles before generation+ack marker replacement; no lazy file handle survives a poll.

#### Validation

Drive native fake agents with nonce-bound frame/input receipts and barriers, not sleeps as proof. Assert exact submitted bytes, one recovery transition, no unsafe input, unchanged managed/adopted identities after stop, lock release and complete logs. Diagnose pause failures independently of rendering or memory defects.

Required executable evidence: `tests/e2e/test_supervisor_scenarios.py::test_stop_supervisor_keeps_sessions`, `tests/e2e/test_supervisor_run.py::test_sends_once_after_initial_delay`, `tests/integration/test_guarded_submit.py::test_unknown_delivery_never_retries_blindly`, `tests/e2e/test_supervisor_log.py::test_records_match_schema`. Every named mutant must die for its recorded reason in those tests; a baseline failure or unrelated exception is not a kill.

#### Remaining Work

The whole sprint.

## Remaining Work

The whole phase: Sprints 8.1–8.2.

## Documentation Requirements

**Architecture docs to create/update:**

- `documents/architecture/supervisor_contract.md` — this phase's owned contract and links to prerequisite interfaces.

**Engineering docs to create/update:**

- `documents/engineering/testing.md` — doctrine, mechanisms and scope of executable evidence.

**Operations and reference docs to create/update:**

- `documents/reference/cli_reference.md` — preparation, qualified host observations and actionable refusals.

**Cross-references to add:**

- `DEVELOPMENT_PLAN/00-overview.md` — requirement closure and lower-phase dependencies.
- `DEVELOPMENT_PLAN/system-components.md` — stable capability/path ownership.
- `DEVELOPMENT_PLAN/legacy_tracking_for_deletion.md` — remaining incompatible implementation shapes.
