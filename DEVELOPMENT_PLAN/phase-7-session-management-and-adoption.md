# Phase 7 — Session management and adoption

**Status**: Planned
**Depends on**: [Phase 6 — Launch command and passthrough](phase-6-launch-and-passthrough.md)
**Host lane**: agent-host
**Gate**: `agentctl check`
**Gate kind**: self-verifying
**Closes**: R16, R17.1

> **Purpose**: Add `list`, `status`, `attach` and `stop` over the managed sessions that launch creates, found by their session options, and `adopt`, which registers a pre-existing pane without taking ownership of it.

## Phase Objective

This phase gives the user every session command that works without a supervisor. A managed session
is one whose session options `@agentctl_agent`, `@agentctl_folder` and `@agentctl_owner` were set by
the launch of [Phase 6 — Launch command and passthrough](phase-6-launch-and-passthrough.md), so the
multiplexer is the only record of it: a session ended outside agentctl simply stops being listed,
and nothing on disk can list a ghost. The one file this phase adds is the adopted-pane registry
under `state`, because an adopted pane carries no agentctl options and agentctl does not own it.

- Every target is exact: commands address a session as `=NAME`, so `stop api` can never reach
  `api-claude`. The only command production code issues to end anything is
  `kill-session -t =NAME` on a managed session; it never issues `kill-server`, `kill-pane` or a
  respawn.
- `stop` on an adopted pane forgets it and prints a notice; a session without agentctl options is
  refused. R16 closes in Sprint 7.2, once list, status, attach and stop all exist, and R17.1 in
  Sprint 7.3.
- `status` gains a screen column in [Phase 8 — Pane observation and classification](phase-8-pane-observation-and-classification.md)
  and watch columns in [Phase 10 — Recovery supervisor](phase-10-supervisor.md); the commands of
  this phase read no supervisor state.
- Each new command enters the binary's handshake command list and the PASSTHROUGH table in the same
  sprint, held together by the Sprint 6.3 equality test.

## Gate Integrity

| Requirement | Oracle | Observer | Mutants | Tests |
|---|---|---|---|---|
| R16 — list, attach, stop and status for agentctl-managed sessions | `tests/oracles/session_ownership.toml` | value: agentctl-core-eval list, status and stop-plan cases; real: list-sessions, has-session and pane pids on a private tmux server under a PTY, beside a foreign session the harness creates as its control | `M-sessions-list-includes-foreign`, `M-sessions-dead-as-alive`, `M-sessions-stop-prefix-target`, `M-sessions-stop-kills-foreign` | `tests/unit/test_sessions_values.py::test_list_rows_match_oracle`, `tests/unit/test_sessions_values.py::test_stop_plan_matches_oracle`, `tests/e2e/test_sessions.py::test_list_shows_only_managed`, `tests/e2e/test_sessions.py::test_status_reports_dead_pane`, `tests/e2e/test_sessions.py::test_stop_kills_only_the_named_managed_session`, `tests/e2e/test_sessions.py::test_stop_refuses_foreign_session`, `tests/e2e/test_sessions.py::test_attach_and_switch_under_pty` |
| R17.1 — adopt registers a pre-existing pane without taking ownership, and stopping it only forgets it | `tests/oracles/session_ownership.toml` | value: agentctl-core-eval adopt and stop-adopted cases, socket mismatch included; real: pane liveness and pid on a private tmux server after stop and across a server restart; observer: fake agent record with nonce from the adopted pane | `M-adopt-stop-kills`, `M-adopt-no-socket-revalidation`, `M-adopt-no-pid-revalidation`, `M-adopt-sets-session-options` | `tests/unit/test_adopt_values.py::test_adopt_rows_match_oracle`, `tests/e2e/test_adopt.py::test_adopt_does_not_take_ownership`, `tests/e2e/test_adopt.py::test_stale_entry_after_server_restart` |

## Not Proven By This Gate

- The session commands against real psmux: its pane ids, session options and exact targeting. — owed to [Phase 14 — Windows and psmux acceptance](phase-14-windows-psmux-acceptance.md).
- List, status, attach and stop over sessions running real agents rather than the fake agent; the commands read only multiplexer state. — not proven by any phase.
- Adopting a pane on the user's own tmux server, which tests never touch; the evidence is the same command on a private server. — not proven by any phase.
- A restarted server that reuses an adopted entry's socket, pane id and pid for another process; those are the identity values revalidation compares. — not proven by any phase.
- Tamper resistance is bounded by [§ P](development_plan_standards.md#p-the-ratchet-and-the-users-commit-points): it holds against a HEAD the user has committed. — not proven by any phase.

## Sprints

### Sprint 7.1: list and status [Planned]

**Status**: Planned
**Implementation**: `src/agentctl/haskell/src/AgentCtl/Sessions.hs`, `src/agentctl/haskell/src/AgentCtl/Protocol.hs`, `src/agentctl/haskell/app/`, `src/agentctl/cli.py`, `tests/oracles/session_ownership.toml`, `tests/unit/test_sessions_values.py`, `tests/e2e/test_sessions.py`
**Validation tests**: `tests/unit/test_sessions_values.py::test_list_rows_match_oracle`, `tests/e2e/test_sessions.py::test_list_shows_only_managed`, `tests/e2e/test_sessions.py::test_status_reports_dead_pane`, `tests/e2e/test_sessions.py::test_status_defaults_to_current_folder`
**Mutants**: `M-sessions-list-includes-foreign`, `M-sessions-dead-as-alive`, `M-sessions-status-wrong-folder`
**Closes**: none
**Docs to update**: `documents/architecture/sessions_and_ownership.md`, `documents/reference/cli_reference.md`

#### Objective

Show the user's managed sessions as the multiplexer reports them, with nothing read from disk.

#### Deliverables

- `tests/oracles/session_ownership.toml` holds the ownership rows, with provenance `request:R16`,
  `request:R17.1`, `decision:D-09` and `decision:D-41`: managed, foreign without options, dead pane,
  attached, and missing name.
- `AgentCtl.Sessions` reads the sessions, their options and their panes through query commands only
  (list-sessions, show-options, list-panes) and keeps the sessions whose `@agentctl_owner` marks them
  managed; a session without agentctl options is never managed, whatever its name.
- A pure function turns those reports into rows: name, agent, folder, pane alive or dead with its
  exit status, and attached clients. `agentctl-core-eval` gains it as a subject.
- `list` prints one row per managed session. `status NAME` prints that session's row, and plain
  `status` prints every managed session whose recorded canonical folder equals the invoking folder, both agents
  included.
- A missing name exits non-zero with a message and touches nothing.
- `list` and `status` enter the handshake command list and the PASSTHROUGH table.

#### Validation

1. The rows equal the oracle for constructed reports of managed, foreign, dead and attached sessions — `tests/unit/test_sessions_values.py::test_list_rows_match_oracle`; fails when a session without options is listed or a dead pane reads as alive; mutants `M-sessions-list-includes-foreign`, `M-sessions-dead-as-alive`.
2. On a private tmux server with two sessions launched by agentctl and one created by the harness, `list` shows exactly the two, while the harness's own list-sessions shows all three — `tests/e2e/test_sessions.py::test_list_shows_only_managed`; fails when the foreign session is listed; mutant `M-sessions-list-includes-foreign`.
3. With remain-on-exit set on a managed session by the harness, a fake agent that exits after the startup window leaves a dead pane, which `status` reports as dead with the fake's exit status — `tests/e2e/test_sessions.py::test_status_reports_dead_pane`; fails when the dead pane reads as alive; mutant `M-sessions-dead-as-alive`.
4. Plain `status` in a folder with both agents' managed sessions prints both rows and no other — `tests/e2e/test_sessions.py::test_status_defaults_to_current_folder`; fails when it omits one agent or reports another folder's session with the same basename; mutant `M-sessions-status-wrong-folder`.

#### Remaining Work

The whole sprint.

### Sprint 7.2: attach and stop [Planned]

**Status**: Planned
**Implementation**: `src/agentctl/haskell/src/AgentCtl/Sessions.hs`, `src/agentctl/haskell/src/AgentCtl/Protocol.hs`, `src/agentctl/cli.py`, `tests/unit/test_sessions_values.py`, `tests/e2e/test_sessions.py`
**Validation tests**: `tests/unit/test_sessions_values.py::test_stop_plan_matches_oracle`, `tests/e2e/test_sessions.py::test_stop_kills_only_the_named_managed_session`, `tests/e2e/test_sessions.py::test_stop_refuses_foreign_session`, `tests/e2e/test_sessions.py::test_stop_never_prefix_matches`, `tests/e2e/test_sessions.py::test_attach_and_switch_under_pty`, `tests/e2e/test_sessions.py::test_attach_without_tty_prints_command`
**Mutants**: `M-sessions-stop-prefix-target`, `M-sessions-stop-kills-foreign`, `M-sessions-stop-kill-server`, `M-sessions-attach-wrong-target`
**Closes**: R16
**Docs to update**: `documents/architecture/sessions_and_ownership.md`, `documents/reference/cli_reference.md`, `documents/operations/troubleshooting.md`

#### Objective

Attach to a managed session and end one, exactly by name, without ever touching anything agentctl
does not own.

#### Deliverables

- `attach NAME` resolves a managed session and hands over as launch does: attach with a TTY and
  `TMUX` unset, `switch-client` with `TMUX` set, and with no TTY the printed attach command and exit
  0.
- `stop NAME` plans its commands as a pure value: for a managed session, exactly
  `kill-session -t =NAME`; for a foreign session or a missing name, a refusal with a non-zero exit
  and no command.
- No plan of any session command renders `kill-server`, `kill-pane`, `respawn-pane` or
  `respawn-window`; the stop plan's oracle rows say so for every case.
- Targets are exact `=NAME`, so a name that is only a prefix of a session matches nothing.
- `attach` and `stop` enter the handshake command list and the PASSTHROUGH table. With them, every
  session command of R16 works with no supervisor running.

#### Validation

1. The stop plan equals the oracle for managed, foreign and missing targets, and no row renders a forbidden verb — `tests/unit/test_sessions_values.py::test_stop_plan_matches_oracle`; fails when the target loses its `=` or the plan ends the server; mutants `M-sessions-stop-prefix-target`, `M-sessions-stop-kill-server`.
2. Stopping one of two managed sessions removes it and leaves the other alive with its pane pid unchanged — `tests/e2e/test_sessions.py::test_stop_kills_only_the_named_managed_session`; fails when the plan ends the server; mutant `M-sessions-stop-kill-server`.
3. `stop` on a session the harness created exits non-zero and the session survives, while `stop` on a managed session in the same test succeeds — `tests/e2e/test_sessions.py::test_stop_refuses_foreign_session`; fails when a session without options is killed; mutant `M-sessions-stop-kills-foreign`.
4. `stop api` with only `api-claude` present exits non-zero and `api-claude` survives, against `stop api-claude` succeeding — `tests/e2e/test_sessions.py::test_stop_never_prefix_matches`; fails when the target is not exact; mutant `M-sessions-stop-prefix-target`.
5. Under a PTY, `attach NAME` attaches to that session with `TMUX` unset and switches an attached client with `TMUX` set, and the attached session is the named one — `tests/e2e/test_sessions.py::test_attach_and_switch_under_pty`; fails when the client lands on another session; mutant `M-sessions-attach-wrong-target`.
6. With no TTY, `attach NAME` prints the attach command for that session and exits 0 — `tests/e2e/test_sessions.py::test_attach_without_tty_prints_command`; fails when the printed command names another session; mutant `M-sessions-attach-wrong-target`.

#### Remaining Work

The whole sprint.

### Sprint 7.3: adopt [Planned]

**Status**: Planned
**Implementation**: `src/agentctl/haskell/src/AgentCtl/Adopt.hs`, `src/agentctl/haskell/src/AgentCtl/Sessions.hs`, `src/agentctl/haskell/src/AgentCtl/Protocol.hs`, `src/agentctl/cli.py`, `tests/oracles/session_ownership.toml`, `tests/unit/test_adopt_values.py`, `tests/e2e/test_adopt.py`
**Validation tests**: `tests/unit/test_adopt_values.py::test_adopt_rows_match_oracle`, `tests/e2e/test_adopt.py::test_adopt_does_not_take_ownership`, `tests/e2e/test_adopt.py::test_stale_entry_after_server_restart`
**Mutants**: `M-adopt-stop-kills`, `M-adopt-no-socket-revalidation`, `M-adopt-no-pid-revalidation`, `M-adopt-sets-session-options`
**Closes**: R17.1
**Docs to update**: `documents/architecture/sessions_and_ownership.md`, `documents/reference/cli_reference.md`, `documents/reference/files_and_state.md`, `documents/operations/troubleshooting.md`

#### Objective

Let the user bring a pane agentctl did not start under its commands, without agentctl ever owning
or ending it.

#### Deliverables

- `adopt PANE --agent claude|codex` registers a live pane, named by its pane id such as `%3`, in the
  adopted-pane registry under `state`, written to a temporary file and renamed into place.
- An entry records the adapter's stable server endpoint identity in `socket`, the pane id, the pane pid and the
  agent. For tmux it is the socket path; for psmux it identifies the namespace and addressed server without assuming
  a filesystem socket or an undocumented format variable. The pane's current command is a hint, never identity proof.
- Adoption takes no ownership: it sets no session option, renames nothing and creates nothing, and a
  pane in a managed session is refused because agentctl already owns it.
- `list` and `status` show adopted panes, marked adopted, beside the managed sessions.
- `stop` on an adopted pane removes its entry and prints a notice that the pane was left running; it
  issues no multiplexer command beyond the resolving queries.
- Every use compares the entry's recorded socket with the addressed server and its pane id and pid with that
  server's live pane. A missing server, socket mismatch, missing pane or different pid is stale: `list` and
  `status` report it as stale, nothing acts on its pane, and `stop` forgets it.
- `tests/oracles/session_ownership.toml` gains the adoption rows, and `adopt` enters the handshake
  command list and the PASSTHROUGH table.

#### Validation

1. Adopt and stop decisions equal the oracle: adopt a live pane, refuse a managed session's pane and a missing pane, stop an adopted pane as forget-and-notice with no kill, and mark an entry stale when its socket or pid differs, beside a matching socket-and-pid control — `tests/unit/test_adopt_values.py::test_adopt_rows_match_oracle`; fails when stopping an adopted pane plans a kill or a mismatched socket or pid is accepted; mutants `M-adopt-stop-kills`, `M-adopt-no-socket-revalidation`, `M-adopt-no-pid-revalidation`.
2. A pane the harness started with the fake agent is adopted, listed as adopted with no agentctl options on its session, and after `stop` its entry is gone while the pane is alive with the same pid and the fake's record carries the nonce — `tests/e2e/test_adopt.py::test_adopt_does_not_take_ownership`; fails when adoption marks the session managed or stop kills the pane; mutants `M-adopt-sets-session-options`, `M-adopt-stop-kills`.
3. After the harness ends the private server, asserting its socket is under the run dir, and starts a new one whose first pane reuses the adopted pane id with another pid, `list` reports the entry stale, `stop` forgets it, and the new pane is alive — `tests/e2e/test_adopt.py::test_stale_entry_after_server_restart`; fails when the stale entry is applied to the new pane; mutant `M-adopt-no-pid-revalidation`.

#### Remaining Work

The whole sprint.

## Remaining Work

The whole phase: Sprints 7.1–7.3.

## Documentation Requirements

**Architecture docs to create/update:**

- `documents/architecture/sessions_and_ownership.md` — managed and adopted targets; identity in session options and the registry only for adopted panes; list, status, attach and stop with exact `=NAME` targets; `kill-session -t =NAME` as the only ending command; stop on an adopted pane forgets it; stale entries; every command working with no supervisor.

**Engineering docs to create/update:**

- `documents/engineering/testing.md` — the harness-created foreign session as the control for listing and stopping, and the server-restart test of adopted-pane revalidation.

**Operations and reference docs to create/update:**

- `documents/reference/cli_reference.md` — `list`, `status`, `attach`, `stop` and `adopt`, their arguments and exit statuses.
- `documents/reference/files_and_state.md` — the adopted-pane registry: its location under `state`, its fields and its atomic replacement.
- `documents/operations/troubleshooting.md` — a refused stop of a foreign session, the forget notice for an adopted pane, and stale entries.

**Cross-references to add:**

- `documents/architecture/launch_contract.md` — links sessions and ownership from Create or Attach for how a re-run finds its managed session.
- `documents/architecture/multiplexer_adapter.md` — links sessions and ownership for the use of `kill-session -t =NAME`.
