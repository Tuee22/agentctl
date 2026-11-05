# Phase 10 — Recovery supervisor

**Status**: Done
**Depends on**: [Phase 9 — Recovery state machine and backoff](phase-9-recovery-state-machine.md)
**Host lane**: agent-host
**Gate**: `agentctl check`
**Gate kind**: self-verifying
**Closes**: R17, R18, R18.5, R18.6, R19

> **Purpose**: Add the foreground recovery supervisor: watch state and its commands, `supervisor run` with its
> literal-send discipline, the JSONL decision log with `logs`, and the scenario matrix showing that it never kills a
> session, restarts a process, switches models or sends login input.

## Phase Objective

This phase runs the pure decisions of [Phase 9 — Recovery state machine and backoff](phase-9-recovery-state-machine.md)
against live panes. It reads screens through [Phase 8 — Pane observation and classification](phase-8-pane-observation-and-classification.md),
drives tmux or psmux through the typed vocabulary of [Phase 4 — Multiplexer adapter](phase-4-multiplexer-adapter.md),
and watches the managed sessions and adopted panes of [Phase 7 — Session management and adoption](phase-7-session-management-and-adoption.md);
session management keeps working with no supervisor running.

- **Watch intent.** `watch`, `unwatch`, `pause` and `resume-watch` record intent under `state`, and `list` and
  `status` show it; none of them touches a session, so opting out never ends an agent (R18.6, R17).
- **The loop.** `agentctl supervisor run` runs in the foreground under a single-instance lock, and nothing starts it.
  Each poll steps the machine for every watched, unpaused pane and performs only what the step returns: the agent's
  recovery-text constant through `send-keys -l`, then a separate Enter, sent only if a re-capture immediately before
  it matches the capture the decision was made on. The command plan renders nothing
  `tests/oracles/forbidden_actions.toml` names (R17, R19), and every observation, decision, attempt and result is a
  JSONL record that `logs` shows (R18.5).
- **Kernels and proof.** The decisions live in pure kernels (watch transitions, the poll step, the command plan, the
  send guard, the record function, log selection), each an `agentctl-core-eval` subject whose mutants die in value
  cases. The scenario matrix then drives the real supervisor against the scripted fake agent on a private tmux
  server, and every assertion that a pane received nothing has two positive controls: the supervisor's observations
  matched by target to that fake agent's nonce-bearing record (before its pause in the paused case), and a control
  pane that does receive the recovery text. The live run's logged-in branch
  is owed to [Phase 11 — Live agent acceptance](phase-11-live-agent-acceptance.md) and real psmux to
  [Phase 14 — Windows and psmux acceptance](phase-14-windows-psmux-acceptance.md); no mutant names a live test as its
  killer.

## Gate Integrity

| Requirement | Oracle | Observer | Mutants | Tests |
|---|---|---|---|---|
| R18.6 — watch, unwatch, pause and resume-watch give manual pause and opt-out | `tests/oracles/command_surface.toml`, `tests/oracles/forbidden_actions.toml` | value: agentctl-core-eval watch-transition and poll-step cases; real: the watch columns of list and status and the watch-set file on a private tmux server; observer: the paused target's unchanged input record beside a control target receiving recovery text | `M-super-pause-recorded-as-watched`, `M-super-watch-accepts-foreign`, `M-super-paused-target-stepped` | `tests/unit/test_watch_values.py::test_watch_transitions_oracle`, `tests/unit/test_supervisor_values.py::test_poll_step_oracle`, `tests/e2e/test_watch_commands.py::test_list_and_status_show_watch_state`, `tests/e2e/test_supervisor_scenarios.py::test_paused_target_never_sent` |
| R17 — stopping the supervisor or unwatching never kills a managed or adopted session | `tests/oracles/forbidden_actions.toml`, `tests/oracles/command_surface.toml` | value: agentctl-core-eval command-plan cases for every recovery action, unwatch and shutdown; real: has-session and pane pids on a private tmux server after unwatch, SIGTERM and SIGINT; observer: the fake agents' pids and launch records with the nonce; owed: macos-acceptance; owed: windows-psmux-acceptance | `M-super-unwatch-kills`, `M-super-stop-kills-watched` | `tests/unit/test_watch_values.py::test_watch_transitions_oracle`, `tests/unit/test_supervisor_values.py::test_command_plan_oracle`, `tests/e2e/test_watch_commands.py::test_unwatch_never_touches_session`, `tests/e2e/test_supervisor_scenarios.py::test_stop_supervisor_keeps_sessions` |
| R18 — the supervisor watches sessions through the recovery state machine and sends only what it decides | `tests/oracles/recovery_transitions.toml`, `tests/oracles/backoff.toml`, `tests/oracles/forbidden_actions.toml` | value: agentctl-core-eval poll-step, send-guard and command-plan cases; real: capture-pane and send-keys -l against a private tmux server; observer: the scripted fake agent's received-bytes record with the nonce; owed: live-agent-acceptance; owed: windows-psmux-acceptance | `M-super-deadline-ignored`, `M-super-guard-ignores-change`, `M-super-enter-in-literal`, `M-super-commit-aborted-send`, `M-super-failure-keeps-send-pending` | `tests/unit/test_supervisor_values.py::test_delivery_commit_oracle`, `tests/unit/test_supervisor_values.py::test_poll_step_oracle`, `tests/unit/test_supervisor_values.py::test_send_guard_oracle`, `tests/unit/test_supervisor_values.py::test_command_plan_oracle`, `tests/e2e/test_supervisor_scenarios.py::test_overload_backoff_recovery_verify`, `tests/e2e/test_supervisor_scenarios.py::test_screen_change_aborts_send`, `tests/live/test_live_supervision.py::test_live_watch_sends_nothing` |
| R18.5 — every observation, decision, attempt and result is logged, and logs shows them | `tests/oracles/log_records.toml` | value: agentctl-core-eval record-function and log-selection cases; real: the JSONL log a scripted run writes under an isolated state dir; observer: the fake agent's record of its session and nonce, matched to the target every record names | `M-super-log-skips-repeat`, `M-super-log-drops-result`, `M-super-logs-prefix-match`, `M-super-notify-stderr-only`, `M-super-log-ignores-truncated-tail`, `M-super-log-accepts-extra-fields` | `tests/unit/test_supervisor_values.py::test_log_decoding_oracle`, `tests/unit/test_supervisor_values.py::test_poll_records_oracle`, `tests/unit/test_supervisor_values.py::test_logs_selection_oracle`, `tests/unit/test_supervisor_values.py::test_poll_step_oracle`, `tests/e2e/test_supervisor_log.py::test_records_match_schema`, `tests/e2e/test_supervisor_scenarios.py::test_failed_send_closes_unresolved`, `tests/e2e/test_supervisor_log.py::test_every_poll_logged`, `tests/e2e/test_supervisor_log.py::test_logs_selects_exact_target` |
| R19 — the supervisor never switches models, never restarts crashed processes and never sends login input | `tests/oracles/forbidden_actions.toml` | value: agentctl-core-eval command-plan cases and the agent table's recovery-text rows; observer: the scripted fake agents' received-bytes and launch records with the nonce, each absence paired with a control pane that receives the recovery text | `M-super-respawn-on-exit`, `M-super-escalation-sends-model` | `tests/unit/test_supervisor_values.py::test_command_plan_oracle`, `tests/e2e/test_supervisor_scenarios.py::test_terminal_classes_escalate_without_send`, `tests/e2e/test_supervisor_scenarios.py::test_forbidden_actions_never_taken` |

## Not Proven By This Gate

- That the recovery text resumes a real agent after a genuine provider overload, which no lane can induce; the matrix scripts the overload from fixture screens. — not proven by any phase.
- Usage-limit, authentication-error and context-exhaustion screens produced by a real agent session; the matrix replays screen fixtures with recorded provenance. — not proven by any phase.
- Supervision of logged-in claude and codex sessions, observed when `tests/live/test_live_supervision.py::test_live_watch_sends_nothing` takes its logged-in branch. — owed to [Phase 11 — Live agent acceptance](phase-11-live-agent-acceptance.md).
- Live supervision of an `IdlePrompt` screen when the user has not already trusted the live folder, since the live run then sees only `TrustDialog` or `BypassWarning`. — not proven by any phase.
- Capture, `send-keys -l` and the separate Enter through a real psmux, and the supervisor lock on Windows. — owed to [Phase 14 — Windows and psmux acceptance](phase-14-windows-psmux-acceptance.md).
- Native SIGINT and SIGTERM shutdown on Darwin, including unchanged managed and adopted pane identities and released supervisor locks. — owed to [Phase 13 — macOS acceptance](phase-13-macos-acceptance.md).
- Native Ctrl+C and Ctrl+Break shutdown in a private Windows console, including unchanged managed and adopted pane identities and released supervisor locks. — owed to [Phase 14 — Windows and psmux acceptance](phase-14-windows-psmux-acceptance.md).
- A keystroke the user types in the instant between the send-time re-capture and `send-keys -l`; the guard narrows that window to one capture but cannot close it. — not proven by any phase.
- Tamper resistance extends only to data already present in the available HEAD baseline ([§ P](development_plan_standards.md#p-the-ratchet-and-automatic-closure)); uncommitted inputs have no historical protection. — not proven by any phase.

## Sprints

### Sprint 10.1: Watch state and commands [Done]

**Status**: Done
**Implementation**: `src/agentctl/haskell/src/AgentCtl/Supervisor/Watch.hs`, `src/agentctl/haskell/src/AgentCtl/Sessions.hs`, `src/agentctl/haskell/src/AgentCtl/Protocol.hs`, `src/agentctl/haskell/app/`, `src/agentctl/haskell/agentctl-core.cabal`, `src/agentctl/cli.py`, `tests/oracles/command_surface.toml`, `tests/mutants/supervisor.toml`, `tests/unit/test_watch_values.py`, `tests/e2e/test_watch_commands.py`, `tests/harness/sessions.py`
**Validation tests**: `tests/unit/test_watch_values.py::test_watch_transitions_oracle`, `tests/e2e/test_watch_commands.py::test_list_and_status_show_watch_state`, `tests/e2e/test_watch_commands.py::test_unwatch_never_touches_session`, `tests/e2e/test_watch_commands.py::test_watch_refuses_foreign_target`, `tests/e2e/test_watch_commands.py::test_concurrent_watch_updates_preserve_entries`
**Mutants**: `M-super-pause-recorded-as-watched`, `M-super-watch-accepts-foreign`, `M-super-unwatch-kills`
**Closes**: R18.6
**Docs to update**: `documents/architecture/supervisor_contract.md`, `documents/architecture/sessions_and_ownership.md`, `documents/reference/cli_reference.md`, `documents/reference/files_and_state.md`

#### Objective

Record watch intent for each target durably, through commands that never touch a session, and show it in `list` and
`status`.

#### Deliverables

- `AgentCtl.Supervisor.Watch` keeps the watch set in a file under `state`, written to a temporary file and renamed
  into place: one `watched` or `paused` entry per target, a managed session by its NAME or an adopted pane by its
  `%ID`.
- A pure transition function, an `agentctl-core-eval` subject, applies a command to the set and the resolved target:
  the new set and the multiplexer commands to issue (resolution queries only), a notice for a repeat, or a refusal
  with exit 1 when watch or resume targets a foreign or missing target. Pause and unwatch can disable an existing
  stale entry, and revisions preserve a pause/resume event between polls.
- `watch NAME|%ID`, `unwatch NAME|%ID`, `pause NAME|%ID` and `resume-watch NAME|%ID` enter the handshake command list
  and the passthrough table, which the Sprint 6.3 equality test holds together; `resume-watch` resumes supervision,
  not the agent's goal.
- `list` and `status` gain the watched and paused columns.
- `tests/oracles/command_surface.toml` gains the four commands' transition rows anchored to R18.6, with
  `decision:D-70` provenance for revision and repeat semantics.

#### Validation

1. Every transition row holds through `agentctl-core-eval` —
   `tests/unit/test_watch_values.py::test_watch_transitions_oracle`; fails when `pause` leaves its entry `watched`, a
   foreign target is accepted, or `unwatch` plans more than resolving its target; mutants
   `M-super-pause-recorded-as-watched`, `M-super-watch-accepts-foreign`, `M-super-unwatch-kills`.
2. `list` and `status` show a watched session, a paused adopted pane and an unwatched third session as such —
   `tests/e2e/test_watch_commands.py::test_list_and_status_show_watch_state`; fails when a state is missing or shown
   against the wrong target; no mutant: the kernel's mutants die in item 1.
3. Unwatching and pausing leave a managed session and an adopted pane alive with unchanged pane pids, against the
   positive control that `status` showed both watched and nonce-bearing fake agent records name both —
   `tests/e2e/test_watch_commands.py::test_unwatch_never_touches_session`; fails when unwatching ends a target; no
   mutant: the kernel's mutants die in item 1.
4. `watch` refuses a foreign session and a missing name with exit 1, leaving the watch-set file byte-identical,
   against the control that watching the managed session succeeds —
   `tests/e2e/test_watch_commands.py::test_watch_refuses_foreign_target`; fails when a foreign session becomes
   watchable; no mutant: the kernel's mutants die in item 1.
5. Concurrent watch, pause and resume commands for distinct managed and adopted targets retain every entry and
   assign each effective update a distinct revision —
   `tests/e2e/test_watch_commands.py::test_concurrent_watch_updates_preserve_entries`; fails when a write overwrites
   another command's intent; no mutant: the native lock and complete read-modify-write scope are operating-system
   effects, with each successful command and each target's distinct revision as controls.

#### Remaining Work

None.

### Sprint 10.2: supervisor run [Done]

**Status**: Done
**Implementation**: `src/agentctl/haskell/src/AgentCtl/Supervisor.hs`, `src/agentctl/haskell/src/AgentCtl/Supervisor/Runtime.hs`, `src/agentctl/haskell/src/AgentCtl/Supervisor/Lock.hs`, `src/agentctl/haskell/src/AgentCtl/Supervisor/Commands.hs`, `src/agentctl/haskell/src/AgentCtl/Supervisor/Guard.hs`, `src/agentctl/haskell/src/AgentCtl/Supervisor/Poll.hs`, `src/agentctl/haskell/src/AgentCtl/Supervisor/Settings.hs`, `src/agentctl/haskell/src/AgentCtl/Supervisor/Delivery.hs`, `src/agentctl/haskell/src/AgentCtl/Sessions.hs`, `src/agentctl/haskell/src/AgentCtl/Supervisor/Log.hs`, `src/agentctl/haskell/src/AgentCtl/Native.hs`, `src/agentctl/haskell/src/AgentCtl/native_fs.c`, `src/agentctl/haskell/src/AgentCtl/native_stop.c`, `src/agentctl/haskell/src/AgentCtl/Protocol.hs`, `src/agentctl/haskell/app/`, `src/agentctl/haskell/test/SupervisorTests.hs`, `tests/harness/supervisor.py`, `tests/e2e/test_scripted_fake.py`, `src/agentctl/haskell/agentctl-core.cabal`, `src/agentctl/cli.py`, `tests/oracles/forbidden_actions.toml`, `tests/oracles/command_surface.toml`, `tests/mutants/supervisor.toml`
**Validation tests**: `tests/unit/test_supervisor_values.py::test_command_plan_oracle`, `tests/unit/test_supervisor_values.py::test_send_guard_oracle`, `tests/unit/test_supervisor_values.py::test_poll_step_oracle`, `tests/unit/test_supervisor_values.py::test_run_flag_defaults_oracle`, `tests/e2e/test_supervisor_run.py::test_second_instance_refused`, `tests/e2e/test_supervisor_run.py::test_sends_once_after_initial_delay`, `tests/e2e/test_supervisor_run.py::test_escalation_notifies`, `haskell:agentctl-core-test/SupervisorReal/lock-contention-and-release`, `haskell:agentctl-core-test/SupervisorReal/lock-exception-releases`, `haskell:agentctl-core-test/SupervisorReal/lock-refuses-directory`, `haskell:agentctl-core-test/SupervisorReal/stop-handler-scope-reusable`, `tests/e2e/test_scripted_fake.py::test_scripted_agent_records_every_byte`, `tests/unit/test_supervisor_values.py::test_delivery_commit_oracle`
**Mutants**: `M-super-enter-in-literal`, `M-super-respawn-on-exit`, `M-super-escalation-sends-model`, `M-super-stop-kills-watched`, `M-super-guard-ignores-change`, `M-super-paused-target-stepped`, `M-super-deadline-ignored`, `M-super-notify-stderr-only`, `M-super-commit-aborted-send`, `M-super-failure-keeps-send-pending`
**Closes**: none
**Docs to update**: `documents/architecture/supervisor_contract.md`, `documents/engineering/testing.md`, `documents/reference/cli_reference.md`, `documents/reference/files_and_state.md`, `documents/engineering/code_standards.md`, `documents/reference/external_tool_facts.md`

#### Objective

Run the recovery loop in the foreground over the watch set, sending only the agent's recovery text, only when the
machine decides to, and only into a screen unchanged since that decision.

The native lock and stop scopes, pure poll and send kernels, and foreground interpreter are small infrastructure
modules implementing this one run contract. Their boundary is process lifetime and interpretation of a recovery
decision; the scripted fake agent is its controlled observer. They share this sprint so no alternate loop or lock
path substitutes for the production interpreter.

#### Deliverables

- `agentctl supervisor run`, in the handshake command list and the passthrough table, runs until SIGINT or SIGTERM,
  which abandon any pending send, release the lock and exit 0, ending no session.
- Its timing flags default to poll 5 s, initial delay 30 s, max delay 900 s, multiplier 2 and jitter 0.2, the rows of
  `tests/oracles/command_surface.toml` with provenance `decision:D-39`; it reads no config file, and the only text it
  sends is the agent table's recovery-text constant of Sprint 5.1.
- `AgentCtl.Supervisor.Lock` holds an exclusive lock on a file under `state` for the life of the process and records
  the holder's pid, so a second `supervisor run` exits non-zero naming it.
- A pure poll step decides, per watch entry, machine state, observation and time, what the poll does: a paused entry
  is neither captured nor stepped and drops its open incident; the first capture after `watch`, `resume-watch` or
  start is a baseline whose errors count as handled; the machine's actions follow, with a notification for each
  backoff notice and each entry to ESCALATE. The loop around it captures the agent pane (an adopted pane after
  revalidating its server socket, id and pid) and drops a vanished target with a notification.
- A pure command plan renders each action, and shutdown, for tmux and psmux against the pane id: a send is
  `send-keys -l -t %<id> -- <text>` then a separate Enter, and shutdown renders nothing.
  `tests/oracles/forbidden_actions.toml` (provenance `request:R17`, `request:R19`) lists the verbs no plan renders
  (`kill-session`, `kill-server`, `kill-pane`, `respawn-pane`, `respawn-window`, `new-session`, `new-window`) and the
  tokens no sent text carries (`/model`, `/login`, each agent's login commands).
- A pure send guard compares the decision-time capture with a re-capture taken immediately before `send-keys -l`; a
  changed normalised text, class or fingerprint aborts the send, and the fresh observation is stepped instead.
- Each notification goes to the supervisor's stderr and, through `AgentCtl.Supervisor.Log`, to a `notify` record in
  the JSONL decision log under `state`.
- `agentctl-fake-agent` gains a scripted mode that plays screen fixtures advanced by time or by received input, and
  records every byte it receives with the run's nonce.

#### Validation

1. For every recovery action, and for shutdown, the command plan renders exactly the oracle's tmux and psmux argv,
   with nothing the forbidden-actions oracle lists — `tests/unit/test_supervisor_values.py::test_command_plan_oracle`;
   fails when Enter rides inside the literal, an exited pane is respawned, an escalation types `/model` or shutdown
   kills a target; mutants `M-super-enter-in-literal`, `M-super-respawn-on-exit`, `M-super-escalation-sends-model`,
   `M-super-stop-kills-watched`.
2. The send guard proceeds only on an identical re-capture —
   `tests/unit/test_supervisor_values.py::test_send_guard_oracle`; fails when a changed input line, class or
   fingerprint still proceeds, the identical row being the positive case; mutant `M-super-guard-ignores-change`.
3. The poll step equals its oracle rows: a paused entry yields nothing, BACKOFF sends only once its deadline passes,
   a baseline error is handled, and each notification reaches both sinks —
   `tests/unit/test_supervisor_values.py::test_poll_step_oracle`; fails when a paused entry is stepped, a send precedes
   its deadline or a notification skips its record; mutants `M-super-paused-target-stepped`,
   `M-super-deadline-ignored`, `M-super-notify-stderr-only`.
4. With no timing flag the policy equals the oracle defaults, and each flag changes only its own field —
   `tests/unit/test_supervisor_values.py::test_run_flag_defaults_oracle`; fails when a default departs from the
   concept note; no mutant: the rows pin a constant record.
5. A second `supervisor run` on one `state` exits non-zero naming the first's pid while the first keeps polling, and
   after SIGTERM a third takes the lock — `tests/e2e/test_supervisor_run.py::test_second_instance_refused`; fails when
   two run at once or a stopped one keeps the lock; no mutant: the lock is an operating-system effect.
6. With `agentctl supervisor run --jitter-fraction 0`, a watched scripted overload that appears after the baseline,
   at an idle prompt, receives nothing before its initial backoff deadline and then exactly the recovery text and
   Enter, while an identical unwatched pane receives nothing. The fake agent's nonce-bearing receive timestamps
   are the observer, and the watched pane's eventual received text is the positive control —
   `tests/e2e/test_supervisor_run.py::test_sends_once_after_initial_delay`; fails when a send ignores the deadline or
   reaches an unwatched pane; no mutant: the kernels' mutants die in items 1 to 3.
7. A watched usage-limit screen yields a stderr line naming the target and a `notify` record, and its pane receives
   nothing while a control pane receives the recovery text — `tests/e2e/test_supervisor_run.py::test_escalation_notifies`;
   fails when the notification reaches one sink only; no mutant: the kernels' mutants die in items 1 to 3.
8. Independent native handles contend on the supervisor lock, report its holder, retain exclusion while the watch
   lock is held, release after normal or exceptional exit, and refuse a directory without removing it —
   `haskell:agentctl-core-test/SupervisorReal/lock-contention-and-release`,
   `haskell:agentctl-core-test/SupervisorReal/lock-exception-releases`,
   `haskell:agentctl-core-test/SupervisorReal/lock-refuses-directory`; fails when two handles own the same lock, an
   exception leaves it locked or an unsafe entry is accepted; no mutant: these are native operating-system effects
   with successful acquisition before and after each negative control.
9. Stop-handler scopes refuse nesting without altering the outer scope and can be installed again after exit —
   `haskell:agentctl-core-test/SupervisorReal/stop-handler-scope-reusable`; fails when a nested scope overwrites
   handlers or cleanup prevents reuse; no mutant: the handlers are operating-system effects; actual stop signals
   remain covered by Sprint 10.4's session-preservation scenario.
10. For each fake agent, private file, input-byte and timed frame advances retain nonce-bound target identities and
    native monotonic timestamps; a partial literal is recorded before Enter, the final byte is the separate carriage
    return, and controlled stop exits cleanly —
    `tests/e2e/test_scripted_fake.py::test_scripted_agent_records_every_byte`; fails when canonical buffering hides
    an unsubmitted literal, a byte is missing, a frame advances early or a receipt names another target; no mutant:
    this is the independent receiving observer, with successful byte and frame controls for both agents.
11. Delivery commits a proposed recovery-sent state only after sent; an aborted guard steps the fresh capture and
    defers another send proposal until the next poll, while command failure clears the incident, handles its
    fingerprint and escalates with an unresolved result —
    `tests/unit/test_supervisor_values.py::test_delivery_commit_oracle`; fails when an abort marks unsent input
    handled or a failed command leaves a pending send; mutants `M-super-commit-aborted-send`,
    `M-super-failure-keeps-send-pending`.

#### Remaining Work

None.

### Sprint 10.3: Decision log and logs [Done]

**Status**: Done
**Implementation**: `src/agentctl/haskell/src/AgentCtl/Supervisor/Log.hs`, `src/agentctl/haskell/src/AgentCtl/Supervisor/Log/File.hs`, `src/agentctl/haskell/src/AgentCtl/Native.hs`, `src/agentctl/haskell/src/AgentCtl/native_fs.c`, `src/agentctl/haskell/test/SupervisorTests.hs`, `src/agentctl/haskell/src/AgentCtl/Supervisor.hs`, `src/agentctl/haskell/src/AgentCtl/Protocol.hs`, `src/agentctl/haskell/app/`, `src/agentctl/cli.py`, `tests/oracles/log_records.toml`, `tests/mutants/supervisor.toml`
**Validation tests**: `tests/unit/test_supervisor_values.py::test_poll_records_oracle`, `tests/unit/test_supervisor_values.py::test_logs_selection_oracle`, `tests/e2e/test_supervisor_log.py::test_records_match_schema`, `tests/e2e/test_supervisor_scenarios.py::test_failed_send_closes_unresolved`, `tests/e2e/test_supervisor_log.py::test_every_poll_logged`, `tests/e2e/test_supervisor_log.py::test_logs_selects_exact_target`, `tests/unit/test_supervisor_values.py::test_log_decoding_oracle`, `haskell:agentctl-core-test/SupervisorReal/log-owned-append-and-read`, `haskell:agentctl-core-test/SupervisorReal/log-refuses-directory`, `haskell:agentctl-core-test/SupervisorReal/log-refuses-public-parent`, `haskell:agentctl-core-test/SupervisorReal/log-writer-and-reader-share-history`, `haskell:agentctl-core-test/SupervisorReal/log-tail-requires-active-writer`
**Mutants**: `M-super-log-skips-repeat`, `M-super-log-drops-result`, `M-super-logs-prefix-match`, `M-super-log-ignores-truncated-tail`, `M-super-log-accepts-extra-fields`
**Closes**: R18.5
**Docs to update**: `documents/architecture/supervisor_contract.md`, `documents/reference/cli_reference.md`, `documents/reference/files_and_state.md`, `documents/reference/external_tool_facts.md`

#### Objective

Make every observation, decision, attempt and result a durable JSONL record, and let `logs` show one target's
records.

The pure record and decoding module, owned file adapter and native append/snapshot ABI implement this one storage
contract together. Their infrastructure boundary is validated record publication and concurrent reading; the
foreground recovery interpreter consumes it without another log path.

#### Deliverables

- `AgentCtl.Supervisor.Log` appends one JSON object per line to the decision log under `state`, each carrying
  `time`, a fresh `run` identifier, `target`, `agent` and `kind`. Decisions are flushed before their effects,
  attempts as soon as the guard or send outcome is known, and results at incident closure.
- A pure record function turns each poll into records beside the `notify` records of Sprint 10.2: `observation`
  (target, class, fingerprint, machine state) for every watched, unpaused pane at every poll; `decision` (from and to
  states, the rule and action that fired); `attempt` (recovery text, pre-send class and fingerprint, and outcome
  `sent`, `aborted` or `failed`); and `result` at every incident end (`recovered` for changed Working or IdlePrompt
  after a send; `ended` for closure without recovery evidence, pause and unwatch included; `not-acknowledged`
  for an unchanged verification screen; `unresolved` for command failure; `escalated` for a terminal failure).
- `tests/oracles/log_records.toml` holds each kind's required fields and the record rows of each poll outcome, with
  provenance `request:R18.5`.
- `agentctl logs NAME|%ID`, in the handshake command list and the passthrough table, prints exactly that target's
  records in order through a pure selection, and exits non-zero with the oracle message when there are none.

#### Validation

1. The record function equals its oracle rows, repeated identical observations of unpaused targets included,
   paused targets excluded, and gives every incident end its one `result`; send, abort and command failure have their
   distinct attempt outcomes — `tests/unit/test_supervisor_values.py::test_poll_records_oracle`; fails when a repeat
   goes unrecorded or a result is dropped; mutants `M-super-log-skips-repeat`, `M-super-log-drops-result`.
2. Log selection returns exactly one target's records when another session's name extends that target's name —
   `tests/unit/test_supervisor_values.py::test_logs_selection_oracle`; fails when the other session's records match;
   mutant `M-super-logs-prefix-match`.
3. Every record of a scripted run with a delivered, aborted and failed send has exactly the fields of its kind, and all five
   kinds occur — `tests/e2e/test_supervisor_log.py::test_records_match_schema`; fails on a missing or extra field or
   an absent kind; no mutant: the kernel's mutants die in item 1.
4. While a watched, unpaused pane's screen stays unchanged, every poll writes its `observation`, naming the target whose folder
   carries the run's nonce as the fake agent's record confirms — `tests/e2e/test_supervisor_log.py::test_every_poll_logged`;
   fails when an unchanged screen goes unlogged; no mutant: the kernel's mutants die in item 1.
5. `agentctl logs NAME` prints NAME's records in order and exits non-zero for a target with none —
   `tests/e2e/test_supervisor_log.py::test_logs_selects_exact_target`; fails when another target's records appear; no
   mutant: the selection's mutant dies in item 2.
6. The decoder accepts valid multi-kind records and an active writer's complete prefix, and refuses malformed
   complete records, extra fields and an unterminated suffix after the writer exits —
   `tests/unit/test_supervisor_values.py::test_log_decoding_oracle`; fails when corruption is silently dropped or
   field validation accepts a changed record; mutants `M-super-log-ignores-truncated-tail`,
   `M-super-log-accepts-extra-fields`.
7. Native append preserves earlier bytes, creates a private file, makes each write visible to an independent snapshot, and reads history beyond the
   launch-spec size limit; a directory or public parent refuses without appending, against successful private
   writes and the independently observed unsafe parent —
   `haskell:agentctl-core-test/SupervisorReal/log-owned-append-and-read`,
   `haskell:agentctl-core-test/SupervisorReal/log-refuses-directory`,
   `haskell:agentctl-core-test/SupervisorReal/log-refuses-public-parent`; fails on truncation, unsafe writes or a lost
   launch-spec size bound; no mutant: these are operating-system effects with their native positive controls.
8. The owned reader returns every appended record while the writer holds its native lock and after release; a
   deliberate partial suffix is tolerated only during that writer's scope, then refused by both reading and a new
   writer's startup — `haskell:agentctl-core-test/SupervisorReal/log-writer-and-reader-share-history`,
   `haskell:agentctl-core-test/SupervisorReal/log-tail-requires-active-writer`; fails on lost history, a reader that
   cannot coexist with the writer, or corrupt history accepted after exit; no mutant: the native lock and file
   observers bind the pure decoding controls of item 6 to actual ownership.

#### Remaining Work

None.

### Sprint 10.4: Scenario matrix [Done]

**Status**: Done
**Implementation**: `tests/oracles/forbidden_actions.toml`, `tests/harness/supervisor_cases.py`, `tests/harness/supervisor_barrier.py`, `src/agentctl/haskell/app/SupervisorFixture.hs`, `tests/live/test_live_supervision.py`, `tests/harness/supervisor_signals.py`, `tests/e2e/test_supervisor_scenarios.py`, `src/agentctl/haskell/test/ConsoleFixture.hs`, `src/agentctl/haskell/test/console_fixture.c`
**Validation tests**: `tests/e2e/test_supervisor_scenarios.py::test_overload_backoff_recovery_verify`, `tests/e2e/test_supervisor_scenarios.py::test_terminal_classes_escalate_without_send`, `tests/e2e/test_supervisor_scenarios.py::test_unsafe_screens_never_sent`, `tests/e2e/test_supervisor_scenarios.py::test_paused_target_never_sent`, `tests/e2e/test_supervisor_scenarios.py::test_screen_change_aborts_send`, `tests/e2e/test_supervisor_scenarios.py::test_forbidden_actions_never_taken`, `tests/e2e/test_supervisor_scenarios.py::test_stop_supervisor_keeps_sessions`, `tests/live/test_live_supervision.py::test_live_watch_sends_nothing`
**Mutants**: none — the matrix is real and observer evidence, and the supervisor kernels' mutants die in the value cases of Sprints 10.1 to 10.3
**Closes**: R17, R18, R19
**Docs to update**: `documents/architecture/supervisor_contract.md`, `documents/engineering/testing.md`

#### Objective

Show through the real supervisor that it recovers a scripted overload once, escalates every other failure without
sending, never sends into an unsafe or changed screen, and never kills, restarts, switches models or types a login;
then watch live sessions and send nothing.

#### Deliverables

- `tests/oracles/forbidden_actions.toml` gains a scenario row per scripted screen sequence (its fixtures, the exact
  bytes the fake agent may receive, the expected escalation), with provenance `request:R17`, `request:R18` or
  `request:R19`.
- Each scenario test runs the real `agentctl supervisor run` through the passthrough on a private tmux server
  (`TMUX_TMPDIR` under the run dir, `TMUX` unset), over scripted fake agents in folders named with the run's nonce.
- Every assertion that a pane received nothing is paired with the supervisor's lock-held observations of that pane,
  matched by target to its fake agent's nonce-bearing record (before its pause in the paused case), and with a
  control pane per agent, scripted to the overload-recovery sequence, whose received recovery text shows the byte
  record was live.
- Every logged decision equals the `tests/oracles/recovery_transitions.toml` row for its logged state and observation.
- `tests/live/test_live_supervision.py` runs in the fixed live folder under the real `state` dir with
  `DISABLE_AUTOUPDATER=1`, on a private tmux server, branching per agent on login state; it never sends input or
  answers a dialog, and no record in `tests/mutants/supervisor.toml` names it as a killer.

#### Validation

1. With `--jitter-fraction 0`, a scripted overload at an idle prompt receives one recovery text and Enter after the initial delay and returns to
   MONITORING on the screens that follow, while a pane whose screen stays unchanged after the send ends
   `not-acknowledged`, never recovered — `tests/e2e/test_supervisor_scenarios.py::test_overload_backoff_recovery_verify`;
   fails on an early or repeated send, or when an unchanged screen counts as success.
2. Usage-limit, authentication-error, context-exhaustion and exited panes each escalate with a stderr line and a
   `notify` record and receive nothing, against both controls —
   `tests/e2e/test_supervisor_scenarios.py::test_terminal_classes_escalate_without_send`; fails when one receives
   input or escalates silently.
3. An overload error in scrollback under `Working`, `ApprovalDialog`, `PartialInput`, `TrustDialog` or `BypassWarning`,
   and an error already on screen at the baseline, receive nothing, against both controls —
   `tests/e2e/test_supervisor_scenarios.py::test_unsafe_screens_never_sent`; fails when one receives input.
4. A paused pane showing an overload at an idle prompt is neither captured nor sent to over several backoff periods,
   and after `resume-watch` its baseline marks that error handled, against its observations before the pause and the
   control panes' recovery text — `tests/e2e/test_supervisor_scenarios.py::test_paused_target_never_sent`; fails when
   a paused pane is stepped or sent to.
5. A pane whose normalised screen differs between any two captures while its class and fingerprint hold receives
   nothing, each attempt on it recorded `aborted`, against both controls —
   `tests/e2e/test_supervisor_scenarios.py::test_screen_change_aborts_send`; fails when a send passes a changed screen.
6. Over a crashing, an authentication-error and a login-screen pane, each forbidden action is absent against its
   control: no kill (the live panes keep their pids while the same probe sees the crash), no respawn (the crashed pane
   keeps its pid and its agent's one recorded launch), no model switch (no input holds `/model` while the control
   input is the recovery text), no login bytes (the authentication-error and login-screen panes receive nothing) —
   `tests/e2e/test_supervisor_scenarios.py::test_forbidden_actions_never_taken`; fails on any forbidden effect.
7. Native termination and interrupt requests (SIGTERM/SIGINT on POSIX, Ctrl+Break/Ctrl+C in a private Windows console)
   end a supervisor watching managed sessions and adopted panes: it exits 0
   and releases the lock, and both stay alive with unchanged pane pids, against the control that its pid was alive and
   its log held an observation of each first, matched to their nonce-bearing fake-agent records —
   `tests/e2e/test_supervisor_scenarios.py::test_stop_supervisor_keeps_sessions`; fails when stopping ends a target.
8. Logged in, every poll classifies the live session as `TrustDialog`, `BypassWarning` or `IdlePrompt`, no `attempt`
   record appears and the harness's own capture shows no recovery text; logged out, the launch is refused with its
   remedy — `tests/live/test_live_supervision.py::test_live_watch_sends_nothing`; fails when the supervisor attempts a
   live send.

#### Remaining Work

None.

## Remaining Work

None.

## Documentation Requirements

**Architecture docs to create/update:**

- `documents/architecture/supervisor_contract.md` — the watch commands; `supervisor run` with its lock, baseline
  captures, poll loop and timing defaults; the per-agent recovery text, the send guard and `send-keys -l` then Enter;
  the stderr and `notify` sink; the five record kinds; and the forbidden actions with the scenarios that prove them.
- `documents/architecture/sessions_and_ownership.md` — `list` and `status` show each target's watch state, and
  watching never takes ownership.

**Engineering docs to create/update:**

- `documents/engineering/testing.md` — the fake agent's scripted mode and received-bytes record, the two positive
  controls of every no-input assertion, and that no mutant names a live test as its killer.

**Operations and reference docs to create/update:**

- `documents/reference/cli_reference.md` — `watch`, `unwatch`, `pause`, `resume-watch`, `logs` and `supervisor run`
  with its timing flags, defaults and exit statuses.
- `documents/reference/files_and_state.md` — the watch-set file, the supervisor lock file and the JSONL decision log.
- `documents/operations/troubleshooting.md` — a refused second `supervisor run` and a refused foreign watch target,
  each with what the user types.

**Cross-references to add:**

- `documents/architecture/supervisor_contract.md` — links `documents/architecture/multiplexer_adapter.md` for capture
  and literal send, and `documents/reference/files_and_state.md` for the record format.
