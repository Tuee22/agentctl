# Supervisor Contract

**Status**: Authoritative source
**Supersedes**: N/A
**Owning phase**: [Recovery supervisor](../../DEVELOPMENT_PLAN/phase-10-supervisor.md)

> **Purpose**: Define how the recovery supervisor observes watched panes, classifies their screens, decides
> through the recovery state machine and sends its one recovery text, and the actions it never takes.

## TL;DR

- `agentctl supervisor run` is a foreground loop only the user starts. Each poll captures and classifies the
  agent pane of every watched, unpaused target and steps a pure state machine: MONITORING, SUSPECTED_FAILURE,
  CONFIRM_IDLE, BACKOFF, RECOVERY_SENT, VERIFY, then MONITORING or ESCALATE (R18).
- It types only the per-agent recovery text, only from BACKOFF on a fresh overload at an idle prompt, and only if
  a re-capture just before `send-keys -l` shows the screen unchanged. Other failures escalate, nothing is sent
  during work, dialogs or typed input, stale scrollback never triggers, and backoff is bounded (R18.1 to R18.4).
- Every observation, decision, attempt and result is logged for `logs` (R18.5); `watch`, `unwatch`, `pause` and
  `resume-watch` give opt-in, opt-out and manual pause (R18.6).
- It never kills a session, switches models, restarts a process or sends login input (R17, R19). Whether its
  text revives an agent after a real overload is proven by no phase.

## Capture, Normalisation and Fingerprints

`AgentCtl.Observe.Capture` runs `capture-pane -p -J -t %<id> -S -100` on the agent pane, the id in
`@agentctl_pane` for a managed session or the registry's revalidated pane id for an adopted one, decodes the
output as UTF-8 and reads the pane's dead state with it, so `Exited` never depends on text. The pure
`AgentCtl.Observe.Normalize` converts CRLF and bare CR to LF, strips trailing spaces and tabs from each line,
drops trailing blank lines and keeps the final 100 lines without a trailing newline. Leading indentation and
non-ASCII text are preserved; normalising twice equals normalising once
(`tests/integration/test_capture_real.py::test_capture_roundtrip_on_private_server`,
`haskell:agentctl-core-test/Normalize/idempotent`).

Capture also reads an unjoined styled viewport with `capture-pane -p -e -S 0` and native cursor coordinates and
dimensions. Matching pane facts before and after these reads establish the visual snapshot; a changing snapshot
retries within the caller's existing deadline. Numeric facts use a printable delimiter so their parsing remains
stable under the C locale. The joined text remains the normalized classification and fingerprint input.

`AgentCtl.Observe.Fingerprint` represents an error block with separate preceding text, error content and following
text. Only the normalised error content enters its UTF-8 SHA-256 hash, rendered as lowercase hexadecimal. Redraws,
scrolling, surrounding output and a second occurrence of identical error text keep the fingerprint; a changed
normalised error block changes it (`haskell:agentctl-core-test/Fingerprint/stable-under-redraw`,
`haskell:agentctl-core-test/Fingerprint/different-error-differs`). Bounded captures expose no reliable absolute
occurrence position shared by both multiplexers, so this contract claims none.

A fingerprint is **handled** per target for the supervisor run once a baseline, send, completed incident or
escalation marks it handled. It never opens an incident again in that run, so stale scrollback never re-triggers
and every further send needs both unhandled error content and a new machine transition (R18.3). This deliberately
suppresses a genuine recurrence with identical normalised text, even after intervening work; the failure mode is
a missed recovery rather than another send to stale text. A restart or resume takes a baseline and marks its
existing error handled, so restarting supervision does not turn visible stale text into a retry.

## Screen Classes and Fixture Provenance

`AgentCtl.Observe.Classify.Claude` and `AgentCtl.Observe.Classify.Codex` map a normalised screen to the first
class that applies, in this order, so an error in scrollback never outranks a dialog, typed input or work:

| Order | Class | Meaning | Role in recovery |
|---|---|---|---|
| 1 | `Exited` | the agent's process has ended | escalate; never restarted |
| 2 | `TrustDialog` | claude's workspace-trust dialog, or codex's directory-trust screen | never sent to; never answered |
| 2 | `BypassWarning` | claude's bypass-permissions warning | never sent to; never answered |
| 2 | `ApprovalDialog` | the agent asks the user to approve an action | never sent to |
| 2 | `LoginScreen` | the agent's login onboarding | escalate; never sent login input |
| 3 | `PartialInput` | the prompt holds text the user typed | never sent to |
| 4 | `Working` | the agent is producing output or running a tool | never sent to |
| 5 | `UsageLimit`, `AuthError`, `ContextExhausted` | that error is the latest event, at an idle prompt | escalate; never retried |
| 5 | `Overloaded` | a transient capacity or overload error is the latest event, at an idle prompt | the only class that opens an incident |
| 6 | `IdlePrompt` | an empty prompt waits, and the latest event is not an error | ends an incident; after a send, the sign of recovery |
| 7 | `Unknown` | nothing recognised | never sent to; never advances an incident |

An order-5 class carries its fingerprint and applies only when the classifier positively recognises the idle,
empty prompt below the error: unchanged output is never taken as idleness.

Each class has fixtures under `tests/fixtures/screens/<agent>/<class>/<id>.txt`, the directory naming the
expected class, with a provenance sidecar: `captured`, with the agent's version and the capture command, through
a capture `AGENTS.md` sanctions (capturing `Working`, `PartialInput` or a dialog needs prompts that spend the
user's quota), or `documented`, with the URL of the official docs or changelog it reproduces. The sidecar names
an evidence span that occurs verbatim in the fixture, and a fixture without provenance never counts
(`tests/governance/test_screen_fixtures.py::test_every_fixture_has_provenance`). Every fixture classifies as its
directory names, every precedence pair is decided by its dominating element, and a dead pane is `Exited` whatever
it shows (`tests/unit/test_screen_classes.py::test_fixtures_classify_as_their_directory`,
`tests/unit/test_screen_classes.py::test_precedence_pairs`, `haskell:agentctl-core-test/Classify/dead-pane-is-exited`).

Each text file has a sibling TOML sidecar. Both provenance kinds require `evidence` and a `note` explaining the
fixture's scope. A documented sidecar carries its official HTTPS `source`; a captured sidecar instead requires
`agent_version` and the exact `capture_command`. An optional `baseline` names an overload fixture for the same
agent, making the precedence comparison explicit. Documented examples assemble the documented behavior and UI
vocabulary and state that they are illustrative; they do not attest to a live screen or an exact agent version.

The classifiers share precedence and latest-event selection while retaining per-agent prompts and markers. A
nonempty prompt is `PartialInput` unless matching styled rows show an explicit faint suggestion and the cursor is
at the input's start. Ordinary draft text at Home, whitespace drafts, a moved cursor and missing or conflicting
evidence remain blocked. Color numbers inside extended SGR sequences cannot stand in for the faint attribute.
Error recognition requires an empty prompt and a recognized error in the latest
output line above it. Later ordinary output prevents an old error from classifying the screen as a failure; an
unrecognized error remains `Unknown`. Classified errors carry their separate error block for fingerprinting.

What stays unproven is stated, never implied. A class backed only by `documented` fixtures is consistent with its
docs, not with a real screen; a genuine overload, usage limit, auth error or context exhaustion cannot be
produced on demand, so those classes stay unproven unless a sanctioned capture meets one. Live classification
accepts `TrustDialog`, `BypassWarning` or `IdlePrompt` and sends nothing
(`tests/live/test_live_classification.py::test_live_screen_classes`), and live `IdlePrompt` counts as proven only
in a folder the user has already trusted.

## The Recovery State Machine

`AgentCtl.Recovery.Machine` is a pure, total step function from the backoff policy, the state and one
observation, a screen class with its fingerprint or a deadline reached, to the next state and a list of actions.
The actions are a closed type: waiting until a deadline, sending the recovery text and notifying. Escalation
enters ESCALATE with a terminal or unacknowledged error notice. No action kills, respawns, switches models or logs in. An incident follows one unhandled
`Overloaded` fingerprint `f` and counts its attempt `n`; "hard" means `UsageLimit`, `AuthError`,
`ContextExhausted` or `LoginScreen`, and "blocking" means `TrustDialog`, `BypassWarning`, `ApprovalDialog` or
`PartialInput`. The first row that matches applies:

| From | Observation | To | Action |
|---|---|---|---|
| any but ESCALATE | hard and not yet handled, or `Exited` | ESCALATE | notify; mark the fingerprint handled |
| ESCALATE | `Working` or `IdlePrompt` | MONITORING | none |
| ESCALATE | anything else | ESCALATE | none |
| MONITORING | `Overloaded`, unhandled `f` | SUSPECTED_FAILURE | open an incident for `f` |
| MONITORING | anything else | MONITORING | none |
| SUSPECTED_FAILURE | `Overloaded`, `f`, one poll on | CONFIRM_IDLE | none |
| CONFIRM_IDLE | `Overloaded`, `f` | BACKOFF | wait until the deadline for attempt `n`; notify |
| BACKOFF | `Overloaded`, `f`, deadline not reached | BACKOFF | none |
| BACKOFF | `Overloaded`, `f`, deadline reached | RECOVERY_SENT | send, under the send discipline; mark `f` handled |
| SUSPECTED_FAILURE, CONFIRM_IDLE, BACKOFF | `Overloaded`, a new unhandled fingerprint | SUSPECTED_FAILURE | replace the incident with the new fingerprint |
| SUSPECTED_FAILURE, CONFIRM_IDLE, BACKOFF | anything else | MONITORING | mark `f` handled; end the incident without a send |
| RECOVERY_SENT | anything | VERIFY | none |
| VERIFY | `Working` or `IdlePrompt`: a changed screen without the handled error | MONITORING | close the incident as recovered |
| VERIFY | blocking | MONITORING | close the incident as ended, without sending or claiming recovery |
| VERIFY | `Overloaded`, a new fingerprint `f'` | BACKOFF | follow `f'` with attempt `n + 1`; wait for that attempt's deadline |
| VERIFY | anything else, before the verify deadline | VERIFY | none |
| VERIFY | anything else, at the verify deadline, one initial delay after the send | ESCALATE | notify: not acknowledged |

`tests/oracles/recovery_transitions.toml` holds every (state, observation) cell, frozen from the R18 state list
and the safety rules before any implementation (`tests/unit/test_recovery_transitions.py::test_every_cell_matches_oracle`).
Properties over generated sequences add that no `Working`, blocking, `LoginScreen` or `Unknown` observation yields
a send, with cover requiring sequences that do reach one (`haskell:agentctl-core-test/Machine/never-send-unsafe`),
that each fingerprint gets at most one send (`haskell:agentctl-core-test/Machine/one-send-per-fingerprint`), and
that a screen unchanged through the verify deadline escalates (`haskell:agentctl-core-test/Machine/verify-needs-change`).
In the running loop every logged decision equals the oracle row for its state and observation.

The pure state carries an ordered handled set, an arbitrary-precision attempt number, the incident deadline and
the seeded generator state. Fingerprint identities are generic keys; the supervisor supplies content fingerprints
and the evaluator supplies independent oracle aliases to the same function. Baseline capture records an existing
error as handled. A new incident requires three matching overload observations before scheduling backoff, and only
a still-matching, unhandled overload at the deadline yields a send. Missing incident or fingerprint data cannot
yield a send (`haskell:agentctl-core-test/Machine/never-send-unsafe`,
`haskell:agentctl-core-test/Machine/one-send-per-fingerprint`).

## Safety Rules

The concept note's nine rules, as this contract holds them:

1. A send needs a fresh overload at a recognised idle prompt, seen with one fingerprint on three consecutive
   polls before backoff starts; unchanged output alone never means idle.
2. Nothing is sent during work, approval dialogs or typed input; those screens, and the trust, bypass and login
   screens, outrank every error and end an incident (R18.2).
3. Stale scrollback never retries, and each send needs a fresh pass through BACKOFF (R18.3).
4. A send waits for acknowledgement, and an unchanged screen is never success.
5. Transient overload is told apart from usage limits, auth errors, context exhaustion and crashes (R18.1).
6. Backoff is bounded exponential with jitter, unbounded retries are only for `Overloaded`, and notifications
   escalate (R18.4).
7. Observations, decisions, attempts and results are logged; pause and opt-out are commands (R18.5, R18.6).
8. No model switch and no restart of a crashed process, ever (R19).
9. Recovery is conversational and cannot restore an interrupted internal tool call, so projects keep durable
   checkpoints of their own: completed steps, pending work, tests and partially completed edits.

## Backoff and Notifications

`AgentCtl.Recovery.Backoff` computes the delay before attempt `n`: `initial × multiplier^(n - 1)`, capped at the
maximum delay, times `1 + u` with `u` drawn uniformly from `[-jitter, +jitter]`, capped at the maximum again, so
no delay exceeds it. The generator is seeded: a test supplies the seed and the same seed yields the same delays,
while `supervisor run` seeds it from the clock. `tests/oracles/backoff.toml` holds the bounds per attempt.

Policies require finite values: positive initial delay, multiplier greater than one, maximum at least initial,
and jitter from zero inclusive to one exclusive. The generator advances a Word64 using a linear congruential
step and takes its high 53 bits for the jitter fraction. It advances only when scheduling a retry, so polling
never moves an existing deadline. The capped exponential base determines the notification level.

A wait carries its retry record. The confirmation's explicit notification can name the same record, and the
pure notification projection delivers that notice once per decision. A fresh overload in VERIFY therefore
keeps the transition table's wait action and also carries its next policy-eligible retry notice. Deadline controls
compare actual scheduled times and notices to the independent zero-jitter oracle rows, including the next attempt
and the send immediately at its deadline
(`tests/unit/test_recovery_transitions.py::test_backoff_deadlines_match_oracle`).

| Flag of `supervisor run` | Default |
|---|---|
| `--poll-seconds` | 5 |
| `--initial-delay-seconds` | 30 |
| `--max-delay-seconds` | 900 |
| `--multiplier` | 2 |
| `--jitter-fraction` | 0.2 |

With the defaults attempt 1 waits 24 to 36 s, attempt 2 waits 48 to 72 s, attempt 5 waits 384 to 576 s, and
attempt 6 and every later one 720 to 900 s. There is no configuration file
(`tests/unit/test_supervisor_values.py::test_run_flag_defaults_oracle`).

Each notification is a line on the supervisor's stderr and a `notify` record, the only two sinks: one at attempts
1, 2, 4, 8 and every later power of two, naming the class, the attempt and the next delay, at level `info` until
the delay reaches the maximum and `warning` after; and one at level `error` on every entry to ESCALATE, naming the
class and, for `LoginScreen` and `AuthError`, the command the user types, such as `claude auth login`
(`tests/e2e/test_supervisor_run.py::test_escalation_notifies`).

## Send Discipline

1. A send happens only on the step from BACKOFF to RECOVERY_SENT, to a target that is watched and not paused.
2. Immediately before it the supervisor re-captures, re-normalises, re-classifies and re-fingerprints the pane;
   a changed class, fingerprint or normalised text aborts the send, and the fresh observation is stepped instead
   (`tests/unit/test_supervisor_values.py::test_send_guard_oracle`,
   `tests/e2e/test_supervisor_scenarios.py::test_screen_change_aborts_send`). The guard narrows the gap to one
   capture but cannot close it: a key the user presses in that instant is not seen, and no phase proves otherwise.
   This is the same plain-text normalisation used for observations; ANSI escape bytes inside plain capture text
   remain content. Equality also requires an overload and a present fingerprint, so an identical blocked screen
   cannot authorize a send.
3. The text goes as `send-keys -l -t %<id> -- <text>`, then a separate `send-keys -t %<id> Enter`: `-l` types the
   text as characters, never reading a word such as `Enter` or `C-c` as a key name, and the separate Enter
   submits it as one keystroke rather than as a newline inside the text.
4. The target is the agent pane's id, never a session name, and an adopted pane is revalidated against its recorded
   server socket, id and pid just before; a stale entry is never sent to.

## Watch Commands and supervisor run

- **`watch NAME`** adds a managed session or an adopted pane to `<state>/watch.json`, rewritten atomically; a
  foreign session or unknown name is refused with a non-zero exit and the file left unchanged
  (`tests/e2e/test_watch_commands.py::test_watch_refuses_foreign_target`).
- **`unwatch NAME`** removes the entry and touches neither session nor pane (R17,
  `tests/e2e/test_watch_commands.py::test_unwatch_never_touches_session`).
- **`pause NAME`** marks the entry paused: no pane capture or machine step occurs, nothing is sent to it and
  an open incident is dropped
  (`tests/e2e/test_supervisor_scenarios.py::test_paused_target_never_sent`). **`resume-watch NAME`** clears the
  pause and resumes from a baseline capture whose existing errors count as handled. Watch and supervisor start
  establish the same baseline, so a stale overload cannot trigger merely because supervision starts or resumes.
  Resume restores supervision, not the agent's goal.
- **`logs NAME`** prints the records of the target named exactly `NAME`, in log order, and exits non-zero when
  there are none (`tests/e2e/test_supervisor_log.py::test_logs_selects_exact_target`).
- **`status`** shows each target's watch state, `watched` or `paused`; watching never takes ownership
  (`tests/e2e/test_watch_commands.py::test_list_and_status_show_watch_state`).
- **`supervisor run`** runs in the foreground, and nothing starts it automatically. It holds an exclusive lock on
  `<state>/locks/supervisor.lock`, which records its pid, so a second one exits non-zero naming the first
  (`tests/e2e/test_supervisor_run.py::test_second_instance_refused`). It re-reads the watch set on every poll, so
  the watch commands work whether or not it runs; an unpaused target that no longer exists is dropped with a
  notification and any open incident ends. SIGINT or SIGTERM abandons a pending send, releases the lock and exits
  0 without an ending multiplexer command,
  ending no session (R17).

Watch transitions are a pure kernel with independent rows covering every command, eligibility kind and existing
intent state. Effective changes advance the registry and entry revisions; repeats preserve the persisted bytes.
Watch commands serialize reload, transition and publication under the short native `watch.lock`, with a five-second
contention bound. The supervisor holds the same lock while checking current intent immediately before a send.
Between protected polling sections it yields twenty milliseconds with the lock released, allowing watch commands
to acquire it even when native work exceeds the poll interval. The guard and send stay in the same protected section
(`tests/e2e/test_supervisor_scenarios.py::test_paused_target_never_sent`).
The process-wide stop scope restores prior handlers when it exits; native Windows console Ctrl+C and Ctrl+Break
set the same stop request as its C runtime SIGINT/SIGTERM handlers. No handler performs logging or multiplexer I/O.
Native lifecycle acceptance sends SIGINT and SIGTERM to the owned POSIX child. On Windows a test-only fixture
starts the controller in a second private multiplexer console and sends Ctrl+C or Ctrl+Break after verifying that
the supervisor-lock PID belongs to that console. It requires the actual controller to exit before teardown can
send another stop request, then proves lock reuse and unchanged managed and adopted pane identities
(`tests/e2e/test_supervisor_scenarios.py::test_stop_supervisor_keeps_sessions`). Windows console results require a
native Windows host.
The pure poll kernel first requests a capture only for an active entry. Its per-target memory retains handled
fingerprints through pause, unwatch and rewatch for that supervisor process. Dropping an incident handles its
fingerprint and records `ended`; a revision change establishes a fresh baseline. A planned send state is committed
only after delivery, and an aborted guard steps the fresh observation from the prior state.
One target receives at most one guard/send offer per poll. If that fresh step proposes another send, the proposal
is recorded and delivery waits for the next poll without marking the unsent fingerprint handled. A command failure
handles the incident, escalates and records `unresolved`; an identity change without a safe capture ends the old
incident and resets the baseline.
The entry revision lets a later poll detect a pause and resume even if the paused state occurred between polls
(`tests/unit/test_watch_values.py::test_watch_transitions_oracle`,
`tests/e2e/test_watch_commands.py::test_list_and_status_show_watch_state`).

## The Decision Log

`AgentCtl.Supervisor.Log` appends one JSON object per line to `<state>/supervisor.jsonl`. Every record carries
`time`, `run`, `target`, `agent` and `kind`; the run identifier is fresh for each supervisor start. Decisions
are flushed before their effects, attempts as soon as the guard or send outcome is known, and results at incident closure;
[files and state](../reference/files_and_state.md) owns the format and `tests/oracles/log_records.toml` the
fields of each kind (`tests/e2e/test_supervisor_log.py::test_records_match_schema`,
`tests/e2e/test_supervisor_log.py::test_every_poll_logged`):

| Kind | Written | Carries |
|---|---|---|
| `observation` | at every capture of a watched, unpaused target, unchanged screens included | the screen class, error fingerprint and machine state |
| `decision` | at every step of the machine | the state before and after, the rule and the action, an incident's close included |
| `attempt` | after every send offered to the guard resolves | the recovery text, pre-send class and fingerprint, and outcome `sent`, `aborted` on a changed screen, or `failed` on a command error |
| `result` | once when an incident closes | `recovered`, `ended`, `not-acknowledged`, `unresolved` or `escalated` |
| `notify` | for every notification | the level and the message printed on stderr |

`recovered` requires a changed `Working` or `IdlePrompt` screen after a send; `ended` closes an incident without
that evidence, such as pause, unwatch, a vanished target or a blocking screen. An unchanged verification screen is
`not-acknowledged`, a failed command is `unresolved`, and a terminal failure is `escalated`. An aborted send is
an attempt outcome, not an incident result: the fresh capture is stepped and the incident can continue. Pausing or
unwatching an open incident writes its `ended` result when the loop sees the change, then produces no captures for it.

## Forbidden Actions

The supervisor never kills a session or pane, runs `kill-server`, switches models, restarts a process, sends
login input or answers a dialog (R17, R19). Its command plan renders only captures, pane-state queries, the
literal send and Enter, and `tests/oracles/forbidden_actions.toml` lists the verbs no action renders
(`kill-session`, `kill-server`, `kill-pane`, `respawn-pane`, `respawn-window`, `new-session`, `new-window`) and
the tokens no recovery text carries (`/model`, `/login`, each agent's login commands)
(`tests/unit/test_supervisor_values.py::test_command_plan_oracle`).

The scenario matrix runs the real `agentctl supervisor run` against scripted `agentctl-fake-agent` panes on a
private tmux server, and each fake agent records every byte it receives with the run's nonce. An overload at an
idle prompt receives one recovery text and one Enter after the initial delay
(`tests/e2e/test_supervisor_scenarios.py::test_overload_backoff_recovery_verify`); usage-limit, auth-error,
context-exhaustion and exited panes escalate and receive nothing
(`tests/e2e/test_supervisor_scenarios.py::test_terminal_classes_escalate_without_send`); overloads under work,
dialogs or typed input, and stale ones, receive nothing (`tests/e2e/test_supervisor_scenarios.py::test_unsafe_screens_never_sent`);
a crashed agent keeps its single launch and nothing receives `/model` or login bytes
(`tests/e2e/test_supervisor_scenarios.py::test_forbidden_actions_never_taken`); and SIGTERM or SIGINT leaves every
managed and adopted pane alive with its pid unchanged (`tests/e2e/test_supervisor_scenarios.py::test_stop_supervisor_keeps_sessions`).
Every "receives nothing" runs beside a control pane per agent, scripted to the recovery sequence, whose received
text shows the byte record was live. On a host with logged-in agents the live run sends nothing
(`tests/live/test_live_supervision.py::test_live_watch_sends_nothing`), confirmed by
[Live agent acceptance](../../DEVELOPMENT_PLAN/phase-11-live-agent-acceptance.md).

## The Recovery Text

The recovery text is one constant per agent in `AgentCtl.Agent`, fixed by
[decision D-48](../../DEVELOPMENT_PLAN/rationale.md#decisions) and the agent-table rows of
`tests/oracles/launch_argv.toml`: a short, single-line, plain-language request to continue the interrupted work.
It begins with no `/` and holds no remedy command
(`haskell:agentctl-core-test/Agent/recovery-text-is-plain`) and none of the forbidden tokens. It is not
configurable, because a configurable text is the channel through which `/model` or `/login` would reach
`send-keys`, and no single text is assumed right for both agents.

Its efficacy cannot be proven. No lane can produce a genuine provider overload on demand, so the scenario
matrix's fake agent recovers by script, which proves only that the supervisor sent the right bytes at the right
moment. Whether a real agent resumes its task after a real overload is proven by no phase, and rule 9 is the
honest limit: a conversation can resume, but an interrupted internal tool call is not restored.

## Related

- [sessions and ownership](sessions_and_ownership.md) — the managed sessions and adopted panes it watches.
- [multiplexer adapter](multiplexer_adapter.md) — the capture and literal-send vocabulary it uses.
- [launch contract](launch_contract.md) — the screens a new session opens on, and the dialogs no one answers.
- [testing](../engineering/testing.md#observers-and-nonces) — the fake agent and nonces the matrix relies on.
- [files and state](../reference/files_and_state.md) — the watch set, the lock and the log formats.
- [cli reference](../reference/cli_reference.md) — the supervisor commands and their exit statuses.
- [Pane observation and classification](../../DEVELOPMENT_PLAN/phase-8-pane-observation-and-classification.md) — builds the classifiers.
- [Recovery state machine and backoff](../../DEVELOPMENT_PLAN/phase-9-recovery-state-machine.md) — builds the machine.
- [Recovery supervisor](../../DEVELOPMENT_PLAN/phase-10-supervisor.md) — builds this supervisor.
