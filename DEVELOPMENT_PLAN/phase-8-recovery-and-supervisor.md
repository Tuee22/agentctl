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

This phase's verdict evaluates the `linux` half ([T.V](development_plan_standards.md#tv-verdict) V8) at stage 2 ([T.W](development_plan_standards.md#tw-staged-enforcement)) and needs no logged-in agent. Every cited artifact is owned within closure(8) ([§ A](development_plan_standards.md#a-well-ordered-constructive-narrative)), a planned absence is unmet work of this phase ([T.F](development_plan_standards.md#tf-shared-and-owned-failures)), and present incompatible code is a deletion-ledger row of its owner. Native Windows console stop is owed to [Windows application acceptance](phase-11-windows-application-acceptance.md), the logged-in live supervisor observation to the `linux-live` half of [Linux live and clean acceptance](phase-12-linux-live-and-clean-acceptance.md), and native Darwin confirmation to [macOS acceptance](phase-13-macos-acceptance.md); none is a gap in this verdict. Its Haskell modules and native tests form this phase's own build component, discovered through the `cabal.project` package glob of [Python bootstrap and handoff](phase-2-python-bootstrap-and-handoff.md); it edits no earlier component ([§ A](development_plan_standards.md#a-well-ordered-constructive-narrative) A1, A2).

## Gate Integrity

| Requirement | Oracle | Observer | Mutants | Tests |
|---|---|---|---|---|
| R18 — Pure recovery transitions and bounded timing | `tests/oracles/requirements.toml` | value: independent transition, backoff-deadline, delay, escalation, jitter-bound and fingerprint expectations; owed: linux-live-and-clean-acceptance | `M-backoff-attempt-not-advanced`, `M-backoff-jitter-unbounded`, `M-backoff-no-jitter`, `M-backoff-nonfinite-jitter-accepted`, `M-backoff-notify-never-escalates`, `M-backoff-uncapped`, `M-machine-refire-handled-fingerprint`, `M-machine-retry-terminal-class`, `M-machine-send-during-working`, `M-machine-send-in-dialog`, `M-machine-send-on-partial-input`, `M-machine-skip-confirm-idle`, `M-machine-skip-verify`, `M-machine-unchanged-is-success` | `tests/unit/test_recovery_transitions.py::test_every_cell_matches_oracle`, `haskell:agentctl-core-test/Machine/never-send-unsafe`, `tests/unit/test_recovery_transitions.py::test_backoff_deadlines_match_oracle`, `haskell:agentctl-core-test/Backoff/within-bounds`, `haskell:agentctl-core-test/Backoff/seed-determines-delays`, `tests/unit/test_backoff.py::test_delays_and_escalations_match_oracle`, `haskell:agentctl-core-test/Backoff/grows-to-cap`, `haskell:agentctl-core-test/Machine/one-send-per-fingerprint`, `haskell:agentctl-core-test/Machine/verify-needs-change` |
| R17 — Supervisor lifecycle, receipts and scenarios | `tests/oracles/requirements.toml` | value: independent command-plan, delivery-commit, poll-step, send-guard, log and watch-transition expectations; observer: nonce-bound scripted-agent session, send-timing and log-schema observations; owed: windows-application-acceptance | `M-super-commit-aborted-send`, `M-super-deadline-ignored`, `M-super-enter-in-literal`, `M-super-escalation-sends-model`, `M-super-failure-keeps-send-pending`, `M-super-guard-ignores-change`, `M-super-log-accepts-extra-fields`, `M-super-log-drops-result`, `M-super-log-ignores-truncated-tail`, `M-super-log-skips-repeat`, `M-super-logs-prefix-match`, `M-super-notify-stderr-only`, `M-super-pause-recorded-as-watched`, `M-super-paused-target-stepped`, `M-super-respawn-on-exit`, `M-super-stop-kills-watched`, `M-super-unwatch-kills`, `M-super-watch-accepts-foreign` | `tests/e2e/test_supervisor_scenarios.py::test_stop_supervisor_keeps_sessions`, `tests/e2e/test_supervisor_run.py::test_sends_once_after_initial_delay`, `tests/integration/test_supervisor_delivery.py::test_unknown_delivery_never_retries_blindly`, `tests/e2e/test_supervisor_log.py::test_records_match_schema`, `tests/unit/test_supervisor_values.py::test_delivery_commit_oracle`, `tests/unit/test_supervisor_values.py::test_poll_step_oracle`, `tests/unit/test_supervisor_values.py::test_command_plan_oracle`, `tests/unit/test_supervisor_values.py::test_send_guard_oracle`, `tests/unit/test_supervisor_values.py::test_log_decoding_oracle`, `tests/unit/test_supervisor_values.py::test_poll_records_oracle`, `tests/unit/test_supervisor_values.py::test_logs_selection_oracle`, `tests/unit/test_watch_values.py::test_watch_transitions_oracle` |

## Not Proven By This Gate

- Limits: [T.C](development_plan_standards.md#tc-ceiling); none is a closure condition.
- A delivery receipt proves the server-ordered submission it observed, never that the agent acted on that input.

## Sprints

### Sprint 8.1: Pure recovery transitions and bounded timing [Planned]

**Status**: Planned
**Implementation**: `src/agentctl/haskell/src/AgentCtl/Recovery/`, `tests/oracles/backoff.toml`
**Validation tests**: `tests/unit/test_recovery_transitions.py::test_every_cell_matches_oracle`, `haskell:agentctl-core-test/Machine/never-send-unsafe`, `tests/unit/test_backoff.py::test_delays_and_escalations_match_oracle`, `tests/unit/test_recovery_transitions.py::test_backoff_deadlines_match_oracle`, `haskell:agentctl-core-test/Backoff/within-bounds`, `haskell:agentctl-core-test/Backoff/seed-determines-delays`, `haskell:agentctl-core-test/Backoff/grows-to-cap`, `haskell:agentctl-core-test/Machine/one-send-per-fingerprint`, `haskell:agentctl-core-test/Machine/verify-needs-change`
**Mutants**: `M-backoff-attempt-not-advanced`, `M-backoff-jitter-unbounded`, `M-backoff-no-jitter`, `M-backoff-nonfinite-jitter-accepted`, `M-backoff-notify-never-escalates`, `M-backoff-uncapped`, `M-machine-refire-handled-fingerprint`, `M-machine-retry-terminal-class`, `M-machine-send-during-working`, `M-machine-send-in-dialog`, `M-machine-send-on-partial-input`, `M-machine-skip-confirm-idle`, `M-machine-skip-verify`, `M-machine-unchanged-is-success`
**Closes**: R18, R18.3, R18.4, R19
**Docs to update**: `documents/architecture/supervisor_contract.md` except its D-153 frozen spans, `documents/reference/cli_reference.md`, migrates `documents/engineering/testing.md` (owner [Python discipline and gate integrity](phase-1-python-discipline-and-gate-integrity.md))

#### Objective

Pure recovery transitions and bounded timing supplies its complete owned contract through the single phase-scoped gate verdict.

#### Deliverables

Implement closed recovery states, explicit monotonic time and seeded jitter, fingerprint handling and bounded retries. The action vocabulary contains conditional submission and notification, never login, model change or arbitrary restart. This sprint consumes `tests/oracles/recovery_transitions.toml`. Planned mutants, named here until their corpus rows land ([§ C](development_plan_standards.md#c-honest-completion-tracking)): `M-backoff-unbounded`, `M-machine-send-during-work` and `M-machine-stale-fingerprint`.

#### Validation

Enumerate the independent transition oracle and generated finite histories beside successful recovery controls. Stale text, unknown observations, work and dialogs cannot generate submission. Invalid backoff inputs produce named failures.

Every node in **Validation tests** passes in a verified run and every named mutant is killed per [T.K](development_plan_standards.md#tk-kill) at stage 2.

#### Remaining Work

The whole sprint.

### Sprint 8.2: Supervisor lifecycle, receipts and scenarios [Planned]

**Status**: Planned
**Implementation**: `src/agentctl/haskell/src/AgentCtl/Supervisor/`, `src/agentctl/haskell/app/ScriptedAgent.hs`, `src/agentctl/haskell/app/SupervisorFixture.hs`, `tests/e2e/test_supervisor_scenarios.py`, `tests/integration/test_supervisor_delivery.py`, `tests/live/test_live_supervisor.py`, `src/agentctl/haskell/product-linux/`
**Validation tests**: `tests/e2e/test_supervisor_scenarios.py::test_stop_supervisor_keeps_sessions`, `tests/e2e/test_supervisor_run.py::test_sends_once_after_initial_delay`, `tests/integration/test_supervisor_delivery.py::test_unknown_delivery_never_retries_blindly`, `tests/e2e/test_supervisor_log.py::test_records_match_schema`, `tests/e2e/test_scripted_fake.py::test_scripted_agent_records_every_byte`, `tests/e2e/test_watch_commands.py::test_concurrent_watch_updates_preserve_entries`, `tests/unit/test_supervisor_values.py::test_command_plan_oracle`, `tests/unit/test_watch_values.py::test_watch_transitions_oracle`, `tests/unit/test_supervisor_values.py::test_delivery_commit_oracle`, `tests/unit/test_supervisor_values.py::test_poll_step_oracle`, `tests/unit/test_supervisor_values.py::test_send_guard_oracle`, `tests/unit/test_supervisor_values.py::test_log_decoding_oracle`, `tests/unit/test_supervisor_values.py::test_poll_records_oracle`, `tests/unit/test_supervisor_values.py::test_logs_selection_oracle`, `tests/live/test_live_supervisor.py::test_live_supervisor_refuses_without_login`
**Mutants**: `M-super-commit-aborted-send`, `M-super-deadline-ignored`, `M-super-enter-in-literal`, `M-super-escalation-sends-model`, `M-super-failure-keeps-send-pending`, `M-super-guard-ignores-change`, `M-super-log-accepts-extra-fields`, `M-super-log-drops-result`, `M-super-log-ignores-truncated-tail`, `M-super-log-skips-repeat`, `M-super-logs-prefix-match`, `M-super-notify-stderr-only`, `M-super-pause-recorded-as-watched`, `M-super-paused-target-stepped`, `M-super-respawn-on-exit`, `M-super-stop-kills-watched`, `M-super-unwatch-kills`, `M-super-watch-accepts-foreign`
**Closes**: R17, R18.5, R18.6
**Docs to update**: `documents/architecture/supervisor_contract.md` except its D-153 frozen spans, `documents/reference/cli_reference.md`, migrates `documents/engineering/testing.md` (owner [Python discipline and gate integrity](phase-1-python-discipline-and-gate-integrity.md))

#### Objective

Supervisor lifecycle, receipts and scenarios supplies its complete owned contract through the single phase-scoped gate verdict.

#### Deliverables

Implement `tests/live/test_live_supervisor.py` with its portable refusal node and `tests/live/test_live_supervisor.py::test_live_supervisor_never_sends`, which sends no live input and is declared to the `linux-live` half ([T.X](development_plan_standards.md#tx-terms)); that logged-in observation is the `linux-live` evidence of [Linux live and clean acceptance](phase-12-linux-live-and-clean-acceptance.md). It preserves the no-input observation of the adaptive legacy node `tests/live/test_live_supervision.py::test_live_watch_sends_nothing`, which supervises real agents whenever their status probe succeeds and which the same change deletes, so this verdict never depends on logged-in agents (ledger). Supervisor delivery controls live in `tests/integration/test_supervisor_delivery.py`. Implement watch/pause/unwatch/resume/logs and single-instance foreground supervision with immutable decision records. Unknown delivery is explicit and halts or escalates rather than blindly resending. Strict finite fixture reads close handles before generation+ack marker replacement; no lazy file handle survives a poll. `src/agentctl/haskell/product-linux/` is the Linux product component, whose executable links the packages owned within this phase's closure and is the installed executable on Linux hosts (D-163). Planned mutants, named here until their corpus rows land ([§ C](development_plan_standards.md#c-honest-completion-tracking)): `M-delivery-uncertain-repeated`, `M-log-observation-omitted` and `M-supervisor-stop-kills-session`.

`Supervisor.Runtime` runs over the effect records of D-173, and a scenario interpreter over the models evaluates the supervisor-scenario rows of `tests/oracles/forbidden_actions.toml` through the evaluator. `src/agentctl/haskell/test/console_fixture.c` sends console control events only to a console the run created, whose attached processes are all run-owned ([§ Q](development_plan_standards.md#q-containment-and-user-state-protection)).

#### Validation

Drive native fake agents with nonce-bound frame/input receipts and barriers, not sleeps as proof. Assert exact submitted bytes, one recovery transition, no unsafe input, unchanged managed/adopted identities after stop, lock release and complete logs. Diagnose pause failures independently of rendering or memory defects.

Every node in **Validation tests** passes in a verified run and every named mutant is killed per [T.K](development_plan_standards.md#tk-kill) at stage 2.

#### Remaining Work

The whole sprint.

## Remaining Work

The whole phase: Sprints 8.1–8.2.

## Documentation Requirements

**Architecture docs to create/update:**

- `documents/architecture/supervisor_contract.md` except its D-153 frozen spans — this phase's owned contract and links to prerequisite interfaces.

**Engineering docs to create/update:**

- migrates `documents/engineering/testing.md` (owner [Python discipline and gate integrity](phase-1-python-discipline-and-gate-integrity.md)) — doctrine, mechanisms and scope of executable evidence.

**Operations and reference docs to create/update:**

- `documents/reference/cli_reference.md` — preparation, qualified host observations and actionable refusals.

**Cross-references to add:**

- `DEVELOPMENT_PLAN/00-overview.md` — requirement closure and lower-phase dependencies.
- `DEVELOPMENT_PLAN/system-components.md` — stable capability/path ownership.
- `DEVELOPMENT_PLAN/legacy_tracking_for_deletion.md` — remaining incompatible implementation shapes.
