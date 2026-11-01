# Phase 9 — Recovery state machine and backoff

**Status**: Planned
**Depends on**: [Phase 8 — Pane observation and classification](phase-8-pane-observation-and-classification.md)
**Host lane**: any-host
**Gate**: `agentctl check`
**Gate kind**: self-verifying
**Closes**: R18.2, R18.3, R18.4

> **Purpose**: Make every recovery decision a pure, exhaustively tested transition function over the recovery states, guarded by safety predicates and fingerprint gating, with bounded exponential backoff, seeded jitter and escalating notifications.

## Phase Objective

This phase decides, and does nothing. `AgentCtl.Recovery.Machine` is a pure, total step function
from the timing values, the state, the time and one poll's observation to the next state and a list
of actions, over the states MONITORING, SUSPECTED_FAILURE, CONFIRM_IDLE, BACKOFF, RECOVERY_SENT,
VERIFY and ESCALATE. `AgentCtl.Recovery.Backoff` computes each delay and each escalation record. An
observation is a screen class from [Phase 8 — Pane observation and classification](phase-8-pane-observation-and-classification.md),
with the fingerprint of its error block where it has one and the normalised text it came from.

- The actions form a closed type: wait until a deadline, send the agent's recovery text, notify, and
  escalate. No constructor kills, respawns, switches models or logs in, so no decision of this phase
  can ask for one; [Phase 10 — Recovery supervisor](phase-10-supervisor.md) renders the actions into
  multiplexer commands and closes R18, R17 and R19 over them.
- Every (state, observation) cell is a row of `tests/oracles/recovery_transitions.toml`, and every
  delay bound is a row of `tests/oracles/backoff.toml`, both frozen in
  [Phase 1 — Gate-integrity apparatus](phase-1-gate-integrity-apparatus.md) from the request and the
  concept note's safety rules, before this code exists.
- The lane is any-host because every subject is pure; the eval subjects run through the binary that
  [Phase 3 — Haskell package, quality legs and digest-keyed build](phase-3-haskell-package-and-build.md)
  builds.

## Gate Integrity

| Requirement | Oracle | Observer | Mutants | Tests |
|---|---|---|---|---|
| R18.2 — input is never sent during active work, approval dialogs or partially typed input | `tests/oracles/recovery_transitions.toml` | value: agentctl-core-eval step cases for every cell, and a never-send property over generated observation sequences whose cover requires each unsafe class and a reachable send | `M-machine-send-on-partial-input`, `M-machine-send-during-working`, `M-machine-send-in-dialog` | `tests/unit/test_recovery_transitions.py::test_every_cell_matches_oracle`, `haskell:agentctl-core-test/Machine/never-send-unsafe` |
| R18.3 — errors are fingerprinted so stale scrollback never re-triggers, and a new transition is required before another injection | `tests/oracles/recovery_transitions.toml` | value: agentctl-core-eval step cases for handled, stale and new fingerprints, and once-per-fingerprint and acknowledgement properties | `M-machine-refire-handled-fingerprint`, `M-machine-unchanged-is-success` | `tests/unit/test_recovery_transitions.py::test_every_cell_matches_oracle`, `haskell:agentctl-core-test/Machine/one-send-per-fingerprint`, `haskell:agentctl-core-test/Machine/verify-needs-change` |
| R18.4 — backoff is bounded exponential with jitter, with escalating notifications | `tests/oracles/backoff.toml` | value: agentctl-core-eval delay and escalation cases, and seeded properties for the jitter bounds, growth to the cap and determinism | `M-backoff-uncapped`, `M-backoff-no-jitter`, `M-backoff-jitter-unbounded`, `M-backoff-notify-never-escalates` | `tests/unit/test_backoff.py::test_delays_and_escalations_match_oracle`, `haskell:agentctl-core-test/Backoff/within-bounds`, `haskell:agentctl-core-test/Backoff/grows-to-cap`, `haskell:agentctl-core-test/Backoff/seed-determines-delays` |
| R18 — the recovery state machine runs MONITORING, SUSPECTED_FAILURE, CONFIRM_IDLE, BACKOFF, RECOVERY_SENT, VERIFY, then MONITORING or ESCALATE | `tests/oracles/recovery_transitions.toml` | value: agentctl-core-eval step cases for every cell of the transition table | `M-machine-skip-confirm-idle`, `M-machine-skip-verify` | `tests/unit/test_recovery_transitions.py::test_every_cell_matches_oracle` |

## Not Proven By This Gate

- That a recovery text sent at a backoff deadline resumes a real agent after a genuine provider overload, which no lane can induce. — not proven by any phase.
- That the concept note's default timings (30 s initial delay, multiplier 2, 900 s cap, jitter 0.2) suit a real provider's recovery time. — not proven by any phase.
- That an empty input prompt beneath an overload error, as the classifiers recognise it, is the moment a real agent accepts input; the machine trusts the screen class it is given. — not proven by any phase.
- Tamper resistance is bounded by [§ P](development_plan_standards.md#p-the-ratchet-and-the-users-commit-points): it holds against a HEAD the user has committed. — not proven by any phase.

## Sprints

### Sprint 9.1: Transition function and safety predicates [Planned]

**Status**: Planned
**Implementation**: `src/agentctl/haskell/src/AgentCtl/Recovery/Machine.hs`, `src/agentctl/haskell/app/`, `src/agentctl/haskell/test/`, `tests/unit/test_recovery_transitions.py`
**Validation tests**: `tests/unit/test_recovery_transitions.py::test_every_cell_matches_oracle`, `haskell:agentctl-core-test/Machine/never-send-unsafe`, `haskell:agentctl-core-test/Machine/one-send-per-fingerprint`, `haskell:agentctl-core-test/Machine/verify-needs-change`
**Mutants**: `M-machine-skip-confirm-idle`, `M-machine-skip-verify`, `M-machine-send-on-partial-input`, `M-machine-send-during-working`, `M-machine-send-in-dialog`, `M-machine-refire-handled-fingerprint`, `M-machine-unchanged-is-success`, `M-machine-retry-terminal-class`
**Closes**: R18.2, R18.3
**Docs to update**: `documents/architecture/supervisor_contract.md`, `documents/engineering/testing.md`

#### Objective

Encode the concept note's safety rules as one pure transition function that can only send at a
moment it has proven safe.

#### Deliverables

- `AgentCtl.Recovery.Machine` defines the closed state, observation and action types and `step`, a
  total function; `agentctl-core-eval` gains it as a subject, and every cell of
  `tests/oracles/recovery_transitions.toml` is a case.
- MONITORING opens an incident in SUSPECTED_FAILURE on `Overloaded` with a fresh fingerprint; the
  same fingerprint on the next poll moves it to CONFIRM_IDLE and once more to BACKOFF, so backoff
  starts only after three consecutive polls of one fingerprint (the error the latest output, the
  input prompt empty) and unchanged output alone never implies idleness.
- Before the send, `Working`, a blocking screen (`TrustDialog`, `BypassWarning`, `ApprovalDialog`,
  `PartialInput`) or `IdlePrompt` ends the incident in MONITORING with its fingerprint handled, and
  another fresh overload fingerprint restarts it at SUSPECTED_FAILURE.
- BACKOFF sends only once its delay from Sprint 9.2 has elapsed and the observation is still
  `Overloaded` with the incident's fingerprint; the state becomes RECOVERY_SENT.
- The safety predicate allows a send for nothing else: no `Working`, blocking, `LoginScreen`,
  `Exited` or `Unknown` observation yields one, from any state.
- A send needs acknowledgement: a screen unchanged since the send (class, fingerprint and normalised
  text) escalates as not acknowledged once one initial delay has passed, `Working` or `IdlePrompt` in
  VERIFY closes the incident as recovered, and a fresh overload fingerprint in VERIFY returns to
  BACKOFF with the attempt advanced. An unchanged screen is never success.
- A handled fingerprint never opens an incident, so stale scrollback never re-triggers and every
  further injection needs a fresh pass through BACKOFF.
- The hard classes `UsageLimit`, `AuthError`, `ContextExhausted` and `LoginScreen`, and `Exited`,
  lead to ESCALATE with a notify from any state and never to a send; ESCALATE returns to MONITORING
  on `Working` or `IdlePrompt`, and only `Overloaded` is retried.

#### Validation

1. Every (state, observation) cell yields the oracle's next state and actions — `tests/unit/test_recovery_transitions.py::test_every_cell_matches_oracle`; fails when CONFIRM_IDLE or VERIFY is skipped, an unchanged screen counts as success, or a usage limit is retried; mutants `M-machine-skip-confirm-idle`, `M-machine-skip-verify`, `M-machine-unchanged-is-success`, `M-machine-retry-terminal-class`.
2. Over generated observation sequences, no step whose observation is `Working`, blocking, `LoginScreen`, `Exited` or `Unknown` returns a send, and the cover obligations require each of those classes and a share of sequences that do reach a send, as the positive control — `haskell:agentctl-core-test/Machine/never-send-unsafe`; fails when typed input, work or a dialog is sent to; mutants `M-machine-send-on-partial-input`, `M-machine-send-during-working`, `M-machine-send-in-dialog`.
3. Over generated sequences, each fingerprint receives at most one send, a re-shown handled fingerprint receives none, and the cover requires a changed error block with a fresh fingerprint to receive a second send — `haskell:agentctl-core-test/Machine/one-send-per-fingerprint`; fails when stale scrollback re-triggers; mutant `M-machine-refire-handled-fingerprint`.
4. After a send, a screen unchanged since the send escalates as not acknowledged once one initial delay has passed and never returns to MONITORING, while `Working` or `IdlePrompt` returns to MONITORING — `haskell:agentctl-core-test/Machine/verify-needs-change`; fails when the unchanged screen counts as acknowledgement; mutant `M-machine-unchanged-is-success`.

#### Remaining Work

The whole sprint.

### Sprint 9.2: Bounded backoff with seeded jitter and escalation [Planned]

**Status**: Planned
**Implementation**: `src/agentctl/haskell/src/AgentCtl/Recovery/Backoff.hs`, `src/agentctl/haskell/src/AgentCtl/Recovery/Machine.hs`, `src/agentctl/haskell/app/`, `src/agentctl/haskell/test/`, `tests/unit/test_backoff.py`, `tests/unit/test_recovery_transitions.py`
**Validation tests**: `tests/unit/test_backoff.py::test_delays_and_escalations_match_oracle`, `tests/unit/test_recovery_transitions.py::test_backoff_deadlines_match_oracle`, `haskell:agentctl-core-test/Backoff/within-bounds`, `haskell:agentctl-core-test/Backoff/grows-to-cap`, `haskell:agentctl-core-test/Backoff/seed-determines-delays`
**Mutants**: `M-backoff-uncapped`, `M-backoff-no-jitter`, `M-backoff-jitter-unbounded`, `M-backoff-notify-never-escalates`, `M-backoff-attempt-not-advanced`
**Closes**: R18.4
**Docs to update**: `documents/architecture/supervisor_contract.md`, `documents/engineering/testing.md`

#### Objective

Space the retries of a transient overload by a bounded exponential delay with reproducible jitter,
and make each retry raise a notification whose level escalates.

#### Deliverables

- The backoff policy is a value of initial delay, multiplier, max delay and jitter fraction; the
  `supervisor run` flags of Sprint 10.2 supply it, defaulting to 30 s, 2, 900 s and 0.2 (D-39).
- Attempts start at 1. The delay for attempt *n* is the exponential delay, `initial × multiplier^(n-1)` capped at the max
  delay, with jitter of at most the jitter fraction either way, and lies within the bounds
  `tests/oracles/backoff.toml` gives for that attempt.
- Jitter comes from a seeded pure generator carried in the machine's state, so one seed and one
  observation sequence always give the same delays; the caller supplies the seed.
- Each scheduled retry yields an escalation record (target, attempt, level, reason and next delay)
  whose level rises at the attempt counts the oracle gives and stays at its top level once the delay
  reaches the cap; retries of `Overloaded` continue for as long as the class holds.
- The machine's BACKOFF deadline is this delay for the current attempt, and a new transition after
  a send advances the attempt.
- `agentctl-core-eval` gains the delay and escalation subjects; the notification sink of Sprint 10.2
  writes the records to stderr and as JSONL `notify` records.

#### Validation

1. For the oracle's policies and seeds, every delay lies within its row's bounds and every escalation level equals its row — `tests/unit/test_backoff.py::test_delays_and_escalations_match_oracle`; fails when a delay passes the cap or the level never rises; mutants `M-backoff-uncapped`, `M-backoff-notify-never-escalates`.
2. The BACKOFF rows of `tests/oracles/recovery_transitions.toml` schedule their deadlines at the backoff delay of their attempt, and a fresh overload fingerprint after a send schedules the next attempt's delay — `tests/unit/test_recovery_transitions.py::test_backoff_deadlines_match_oracle`; fails when the attempt never advances; mutant `M-backoff-attempt-not-advanced`.
3. For generated policies, attempts and seeds, each delay lies within the jitter band around the capped exponential delay — `haskell:agentctl-core-test/Backoff/within-bounds`; fails when jitter can leave the band; mutant `M-backoff-jitter-unbounded`.
4. For generated policies, the jitter-free delay never decreases with the attempt, reaches the max delay after finitely many attempts and stays there — `haskell:agentctl-core-test/Backoff/grows-to-cap`; fails when the delay grows without bound; mutant `M-backoff-uncapped`.
5. One seed gives one delay sequence, and the cover requires seed pairs whose sequences differ, as the positive control that jitter is applied — `haskell:agentctl-core-test/Backoff/seed-determines-delays`; fails when every seed gives the jitter-free delays; mutant `M-backoff-no-jitter`.

#### Remaining Work

The whole sprint.

## Remaining Work

The whole phase: Sprints 9.1–9.2.

## Documentation Requirements

**Architecture docs to create/update:**

- `documents/architecture/supervisor_contract.md` — the recovery states and their transitions, the safety predicate, fingerprint gating, the acknowledgement rule, the closed action vocabulary, the backoff delay and its bounds and defaults, and the escalation records.

**Engineering docs to create/update:**

- `documents/engineering/testing.md` — exhaustive transition-table cases, property tests whose cover obligations act as positive controls, and seeded jitter.

**Operations and reference docs to create/update:**

- None.

**Cross-references to add:**

- `documents/engineering/code_standards.md` — cites the recovery machine as the model of a pure, total function over closed types.
