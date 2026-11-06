# Phase 6 — Launch command and passthrough

**Status**: Done
**Depends on**: [Phase 5 — Agent adapters and preflight](phase-5-agent-adapters-and-preflight.md)
**Host lane**: agent-host
**Gate**: `agentctl check`
**Gate kind**: self-verifying
**Closes**: R6, R7, R8, R9, R10, R11, R12

> **Purpose**: Make `agentctl claude|codex [ARGS...]` create or re-attach the session named from the invoking folder, run the agent there through the pane trampoline, leave nothing behind with a warning and a non-zero exit on any failure, and carry every command except `check` raw from the click app to the core binary.

## Phase Objective

This phase turns the values of the lower phases into the launch command. Sprint 6.1 derives the
session name from the canonical folder as a pure decision. Sprint 6.2 builds `AgentCtl.Launch`,
whose decisions are a pure plan over what the multiplexer reports and whose shell runs that plan
through `AgentCtl.Process`; it closes R7, R8, R10, R11 and R12 because only a created session shows
the name, the re-attach, the final argv and the cleanup together. Sprint 6.3 makes the passthrough
raw at the Python layer, hands off to the binary, and closes R6 and R9 on rows that cross the whole
stack.

- Sessions live on the user's normal tmux server, identified by the session options `@agentctl_agent`,
  `@agentctl_folder` and `@agentctl_owner`; no file records a managed session. Tests run every launch
  against a private server (`TMUX_TMPDIR` under the run dir, `TMUX` unset).
- The pane runs `agentctl-core pane-exec <spec>` from Sprint 4.2. The spec holds the final argv, the
  canonical folder and the caller's environment, so neither the folder nor ARGS reach tmux or psmux
  parsing; environment values stay off the multiplexer command line.
- agentctl never answers a trust or bypass-warning dialog; it starts the agent and hands the terminal
  to the user. The supervisor phases treat both dialogs as screens where nothing is sent.
- `AgentCtl.Paths` receives the `cache`, `data` and `state` dirs through the handoff protocol and
  computes none; `src/agentctl/paths.py` decides them.

## Gate Integrity

| Requirement | Oracle | Observer | Mutants | Tests |
|---|---|---|---|---|
| R6 — every command except check passes through to the core binary, which is never on PATH and never named to the user | `tests/oracles/command_surface.toml` | value: the complete transport table and host handoff modes against the command-surface rows; real: the binary's handshake command list, its direct-run refusal and its usage text; observer: spawn audit records only the binary's POSIX execve or Windows child creation for a warm passthrough; owed: macos-acceptance; owed: windows-psmux-acceptance | `M-pass-table-drops-command`, `M-pass-binary-runs-without-protocol`, `M-pass-progname-core`, `M-pass-rebuild-on-hit`, `M-pass-windows-execve`, `M-pass-child-exit-zero` | `tests/unit/test_passthrough.py::test_passthrough_table_matches_oracle`, `tests/unit/test_passthrough.py::test_every_command_but_check_passes_through`, `tests/integration/test_passthrough.py::test_passthrough_table_equals_binary_commands`, `tests/integration/test_passthrough.py::test_binary_refuses_direct_run`, `tests/integration/test_passthrough.py::test_usage_text_names_agentctl`, `tests/integration/test_passthrough.py::test_warm_passthrough_spawns_only_the_binary`, `tests/unit/test_handoff.py::test_handoff_mode_by_os_family`, `tests/integration/test_handoff.py::test_child_mode_propagates_exit_status` |
| R7 — agentctl claude and agentctl codex launch the agent inside a tmux or psmux session | `tests/oracles/mux_commands.toml` | value: launch handover plans and native invocation cwd separate from argv; real: list-sessions, session options and pane state on a private tmux server under a PTY; observer: fake agent record of argv, cwd, environment keys, session and nonce; owed: live-agent-acceptance; owed: macos-acceptance | `M-launch-env-not-caller`, `M-launch-notty-attaches`, `M-launch-cwd-on-mux-line` | `tests/unit/test_launch_plan.py::test_launch_plan_matches_oracle`, `tests/unit/test_mux_values.py::test_invocation_cwd_stays_off_argv`, `tests/integration/test_mux_reap.py::test_reap_request_validates_pid_before_notification`, `tests/e2e/test_launch.py::test_creates_named_session_with_flags_last`, `tests/e2e/test_launch.py::test_no_tty_prints_attach_command`, `tests/e2e/test_launch.py::test_inside_tmux_switches_client`, `tests/e2e/test_launch.py::test_attach_under_pty`, `tests/e2e/test_launch.py::test_hostile_folder_name_runs_nothing`, `tests/live/test_live_launch.py::test_live_launch` |
| R8 — the session name derives from the invoking folder, a hash form separates another folder with the same basename, and a re-run re-attaches | `tests/oracles/session_names.toml` | value: agentctl-core-eval session-name and decision cases; real: two folders with one basename and a re-run on a private tmux server; observer: fake agent launch count with nonce stays one across the re-run; owed: windows-psmux-acceptance | `M-name-hash-basename`, `M-name-plain-for-foreign`, `M-launch-kill-on-reattach`, `M-launch-preflight-on-reattach`, `M-launch-reattach-dead` | `tests/unit/test_session_names.py::test_session_names_match_oracle`, `tests/unit/test_session_names.py::test_decision_rows_match_oracle`, `tests/e2e/test_launch.py::test_rerun_reattaches_without_preflight`, `tests/e2e/test_launch.py::test_same_basename_other_folder_gets_hash_form`, `tests/e2e/test_launch.py::test_dead_leftover_pane_is_replaced` |
| R10 — the claude argv always ends with --dangerously-skip-permissions | `tests/oracles/launch_argv.toml` | observer: fake agent argv record with nonce from the launched pane; real: logged-out claude accepts the final argv in a private-server pane and rejects an argv it refuses within the same window; owed: live-agent-acceptance | `M-launch-skip-launch-argv`, `M-launch-wrong-agent-row` | `tests/e2e/test_launch.py::test_creates_named_session_with_flags_last`, `tests/integration/test_agent_argv_real.py::test_final_argv_accepted_logged_out`, `tests/live/test_live_launch.py::test_live_launch` |
| R11 — the codex argv always ends with --dangerously-bypass-approvals-and-sandbox --no-daemon | `tests/oracles/launch_argv.toml` | observer: fake agent argv record with nonce from the launched pane; real: logged-out codex accepts the final argv in a private-server pane and rejects an argv it refuses within the same window; owed: live-agent-acceptance | `M-launch-skip-launch-argv`, `M-launch-wrong-agent-row` | `tests/e2e/test_launch.py::test_creates_named_session_with_flags_last`, `tests/integration/test_agent_argv_real.py::test_final_argv_accepted_logged_out`, `tests/live/test_live_launch.py::test_live_launch` |
| R12 — on any failed check no session is left, the warning reaches the caller's terminal and the exit is non-zero | `tests/oracles/preflight.toml` | value: agentctl-core-eval launch-plan failure cases; real: has-session -t =NAME on the private tmux server after each failure; observer: fake agent record that the session existed, as the positive control | `M-launch-keep-session-on-instant-exit`, `M-launch-warn-into-pane`, `M-launch-exit-zero-on-failure` | `tests/unit/test_launch_plan.py::test_launch_plan_matches_oracle`, `tests/e2e/test_launch.py::test_instant_exit_relays_output_and_leaves_nothing`, `tests/e2e/test_launch.py::test_preflight_failure_leaves_nothing`, `tests/e2e/test_launch.py::test_failed_discovery_leaves_no_native_session` |
| R9 — additional ARGS pass through verbatim | `tests/oracles/launch_argv.toml` | value: pure argv assembly against the through-stack rows; real: installed-agent launch or refusal under its existing authentication state; observer: the public raw command under CliRunner with a nonce-bound audit veto; observer: fake agent argv record with nonce for each through-stack row under a PTY; owed: live-agent-acceptance | `M-pass-click-parses-tail`, `M-pass-split-drops-empty`, `M-launch-argv-on-mux-line` | `tests/unit/test_launch_argv.py::test_launch_argv_matches_oracle`, `tests/unit/test_passthrough.py::test_raw_tail_keeps_dashdash_and_help`, `tests/e2e/test_passthrough_argv.py::test_through_stack_rows[claude]`, `tests/e2e/test_passthrough_argv.py::test_through_stack_rows[codex]`, `tests/live/test_live_launch.py::test_live_launch` |

## Not Proven By This Gate

- A logged-in claude and codex launched by agentctl, staying alive past the startup window with the mandatory flags at the end of `/proc/<pane_pid>/cmdline`. — owed to [Phase 11 — Live agent acceptance](phase-11-live-agent-acceptance.md).
- A visible `switch-client` inside the user's own tmux server, which tests never touch; the evidence is the same move on a private server. — not proven by any phase.
- The relay of a real agent's own argv rejection through `agentctl claude` or `agentctl codex`, which needs a logged-in agent; the relay is proven with the fake agent and the rejection with the trampoline run directly. — not proven by any phase.
- The exec handoff and a tmux launch on Darwin, where no `/proc` exists and the argv evidence is the fake agent's record. — owed to [Phase 13 — macOS acceptance](phase-13-macos-acceptance.md).
- psmux sessions, the trampoline status file behind instant-exit capture, the child-process exit status of the Windows handoff and case-folded folder identity. — owed to [Phase 14 — Windows and psmux acceptance](phase-14-windows-psmux-acceptance.md).
- Tamper resistance extends only to data already present in the available HEAD baseline ([§ P](development_plan_standards.md#p-the-ratchet-and-automatic-closure)); uncommitted inputs have no historical protection. — not proven by any phase.

## Sprints

### Sprint 6.1: Folder-derived session names [Done]

**Status**: Done
**Implementation**: `src/agentctl/haskell/src/AgentCtl/Session/Name.hs`, `src/agentctl/haskell/src/AgentCtl/Agent/Types.hs`, `src/agentctl/haskell/src/AgentCtl/Agent.hs`, `src/agentctl/haskell/agentctl-core.cabal`, `src/agentctl/haskell/app/`, `tests/unit/test_session_names.py`, `src/agentctl/haskell/test/`, `tests/oracles/session_names.toml`, `tests/mutants/names.toml`
**Validation tests**: `tests/unit/test_session_names.py::test_session_names_match_oracle`, `tests/unit/test_session_names.py::test_decision_rows_match_oracle`, `haskell:agentctl-core-test/Name/always-valid`
**Mutants**: `M-name-no-collapse`, `M-name-hash-basename`, `M-name-posix-case-fold`, `M-name-plain-for-foreign`, `M-name-keep-underscore-runs`
**Closes**: none
**Docs to update**: `documents/architecture/launch_contract.md`, `documents/reference/external_tool_facts.md`

#### Objective

Derive the session name and the create-or-re-attach decision as pure functions of the canonical
folder, the agent and the sessions the multiplexer reports.

#### Deliverables

- The base is the canonical (realpath) folder's basename, sanitised: characters outside
  `[A-Za-z0-9_-]` map to `-`, runs collapse, `__` never survives, the result never starts with `-`,
  and a basename that sanitises to nothing takes a fixed fallback base. The name is `<base>-<agent>`
  and passes the `SessionName` smart constructor of Sprint 4.1.
- The hash form is `<base>-<h>-<agent>`, where `<h>` is the first 8 hex digits of the sha256 of the
  canonical path in UTF-8, case-folded on Windows only.
- The decision takes the canonical folder, the agent and each live session's name and options: a
  session whose `@agentctl_folder` and `@agentctl_agent` match, under either form, is re-attached; a
  free plain name is created; a plain name held by another folder's session or by a session without
  agentctl options sends this folder to the hash form.
- The canonical path itself is resolved by `AgentCtl.Launch` (Sprint 6.2); this sprint stays pure.
- Ownership requires the owner, agent and canonical folder to match; absent options are foreign. Windows compares
  names and folders case-folded and returns the existing session's actual name for attachment. The closed agent
  identity lives in `AgentCtl.Agent.Types`, re-exported by `AgentCtl.Agent`, so naming has no dependency on mux IO.
- `agentctl-core-eval` gains the session-name and decision subjects.

#### Validation

1. Names equal every `tests/oracles/session_names.toml` row (plain, Unicode, dots, spaces, `#(`, a leading `-`, `__` runs, an empty basename, Windows paths differing only in case), with each hash recomputed by Python's hashlib — `tests/unit/test_session_names.py::test_session_names_match_oracle`; fails when runs are not collapsed, the hash covers the basename, or POSIX paths differing in case share a hash; mutants `M-name-no-collapse`, `M-name-hash-basename`, `M-name-posix-case-fold`.
2. Decisions equal the oracle's decision rows: re-attach own, create free, hash form for another folder, hash form for a session without options — `tests/unit/test_session_names.py::test_decision_rows_match_oracle`; fails when a session without agentctl options is treated as this folder's; mutant `M-name-plain-for-foreign`.
3. For generated folder paths, every derived name is accepted by the `SessionName` smart constructor — `haskell:agentctl-core-test/Name/always-valid`; fails when a `__` run survives sanitising; mutant `M-name-keep-underscore-runs`.

#### Remaining Work

None.

### Sprint 6.2: Launch orchestration [Done]

**Status**: Done
**Implementation**: `src/agentctl/haskell/src/AgentCtl/Launch.hs`, `src/agentctl/haskell/src/AgentCtl/Paths.hs`, `src/agentctl/haskell/src/AgentCtl/Preflight.hs`, `src/agentctl/haskell/src/AgentCtl/Native.hs`, `src/agentctl/haskell/src/AgentCtl/native_fs.c`, `src/agentctl/haskell/src/AgentCtl/native_process.c`, `src/agentctl/haskell/src/AgentCtl/Process.hs`, `src/agentctl/haskell/agentctl-core.cabal`, `tests/harness/launch.py`, `tests/harness/terminal.py`, `tests/harness/passthrough.py`, `tests/harness/host.py`, `tests/harness/tmux.py`, `tests/support.txt`, `tests/mutants/launch.toml`, `tests/oracles/preflight.toml`, `src/agentctl/haskell/app/`, `tests/unit/test_launch_plan.py`, `tests/e2e/test_launch.py`, `tests/integration/test_mux_reap.py`, `tests/integration/test_agent_argv_real.py`, `tests/live/test_live_launch.py`
**Validation tests**: `tests/unit/test_launch_plan.py::test_launch_plan_matches_oracle`, `tests/unit/test_mux_values.py::test_invocation_cwd_stays_off_argv`, `tests/integration/test_mux_reap.py::test_reap_request_validates_pid_before_notification`, `tests/e2e/test_launch.py::test_creates_named_session_with_flags_last`, `tests/e2e/test_launch.py::test_rerun_reattaches_without_preflight`, `tests/e2e/test_launch.py::test_same_basename_other_folder_gets_hash_form`, `tests/e2e/test_launch.py::test_dead_leftover_pane_is_replaced`, `tests/e2e/test_launch.py::test_instant_exit_relays_output_and_leaves_nothing`, `tests/e2e/test_launch.py::test_preflight_failure_leaves_nothing`, `tests/e2e/test_launch.py::test_failed_discovery_leaves_no_native_session`, `tests/e2e/test_launch.py::test_no_tty_prints_attach_command`, `tests/e2e/test_launch.py::test_inside_tmux_switches_client`, `tests/e2e/test_launch.py::test_attach_under_pty`, `tests/e2e/test_launch.py::test_hostile_folder_name_runs_nothing`, `tests/integration/test_agent_argv_real.py::test_final_argv_accepted_logged_out`, `tests/live/test_live_launch.py::test_live_launch`
**Mutants**: `M-launch-keep-session-on-instant-exit`, `M-launch-warn-into-pane`, `M-launch-exit-zero-on-failure`, `M-launch-kill-on-reattach`, `M-launch-reattach-dead`, `M-launch-preflight-on-reattach`, `M-launch-env-not-caller`, `M-launch-notty-attaches`, `M-launch-cwd-on-mux-line`, `M-launch-skip-launch-argv`, `M-launch-wrong-agent-row`
**Closes**: R7, R8, R10, R11, R12
**Docs to update**: `documents/architecture/launch_contract.md`, `documents/operations/troubleshooting.md`, `documents/reference/files_and_state.md`, `documents/engineering/testing.md`

#### Objective

Create or re-attach the folder's session with the final argv, and on every failure leave no session,
warn on the caller's terminal and exit non-zero.

#### Deliverables

- The binary's `claude` and `codex` commands dispatch on the raw argument list, before
  optparse-applicative sees it, to `AgentCtl.Launch`; their decisions form a pure launch plan over
  the multiplexer's reports, run by the shell through `AgentCtl.Process`.
- Re-attach: when Sprint 6.1 decides re-attach and the pane is alive, preflight is skipped, the
  session is never killed, and ARGS given now produce a notice on stderr that they were not applied.
  A dead leftover pane is replaced by a fresh launch.
- Create: the login refusals and `launchArgv` (Sprints 5.1 and 5.2) run first, then preflight yields `Ready`.
  Reserve a spec path under the 0700 launch directory without publishing its contents. Create the session with
  the waiting trampoline, set the pane's remain-on-exit and all identity options, then atomically publish the
  0600 spec (final argv, canonical folder, caller's environment). The agent cannot start before that publication.
- Instant-exit capture: when the pane dies within the startup window, its output is captured and
  relayed to the caller's stderr, the session is killed with `kill-session -t =NAME`, and agentctl
  exits with the agent's status. A pane alive after the window has remain-on-exit turned off.
- Hand-over: with a TTY and `TMUX` unset, attach; with `TMUX` set, `switch-client` on that server;
  with no TTY, the session stays, the attach command is printed and the exit is 0.
- Failure: a refusal or a failed preflight creates nothing, and every warning goes to the invoking
  process's stderr, never into a pane, with the non-zero status from `tests/oracles/preflight.toml`.
- `tests/integration/test_agent_argv_real.py` runs the trampoline directly on a private server with
  the final argv for logged-out claude and codex, so the real agents' argv acceptance is checked
  without a login. The compiled mux relay is published by rename over the test-owned native client copy,
  including a read-only native executable, while retaining the real backend separately.
- `tests/live/test_live_launch.py` runs in the fixed live folder under the real `state` dir with
  `DISABLE_AUTOUPDATER=1` on a private server and branches on each agent's login state: logged in,
  the pane is alive after the startup window and, on Linux, `/proc/<pane_pid>/cmdline` ends with the
  ARGS row and the mandatory flags; logged out, the refusal and its remedy. It sends no input.

#### Validation

1. The launch plan equals every `tests/oracles/preflight.toml` and `tests/oracles/mux_commands.toml` launch row (refusal, failed preflight, instant exit with status 0 and 3, alive pane, re-attach, dead leftover pane, each TTY and `TMUX` case) — `tests/unit/test_launch_plan.py::test_launch_plan_matches_oracle`; fails when an instant exit keeps its session or a failure exits 0; mutants `M-launch-keep-session-on-instant-exit`, `M-launch-exit-zero-on-failure`, `M-launch-notty-attaches`.
2. `claude` and `codex` from a temp folder each create the oracle-named session, whose options name the folder and agent, and the fake agent records the oracle argv, the canonical folder as cwd, the caller's `CLAUDE_CONFIG_DIR` and `CODEX_HOME` keys, the session and the nonce — `tests/e2e/test_launch.py::test_creates_named_session_with_flags_last`; fails when the spec skips `launchArgv`, uses the other agent's row, or carries the server's environment; mutants `M-launch-skip-launch-argv`, `M-launch-wrong-agent-row`, `M-launch-env-not-caller`.
3. A re-run in the same folder keeps the session id, the fake agent's launch count stays one, no second auth probe is recorded against the first run's probe as positive control, and new ARGS draw the not-applied notice; on Windows the rerun uses a different letter case for that canonical folder — `tests/e2e/test_launch.py::test_rerun_reattaches_without_preflight`; fails when re-attach kills and recreates, reruns preflight or case-folding creates a second session; mutants `M-launch-kill-on-reattach`, `M-launch-preflight-on-reattach`.
4. Two temp folders with one basename get the plain and the hash-form session, each re-attachable — `tests/e2e/test_launch.py::test_same_basename_other_folder_gets_hash_form`; fails when the second folder attaches to the first's session; mutant `M-name-plain-for-foreign`.
5. A session whose pane is dead is replaced by a live pane under the same name — `tests/e2e/test_launch.py::test_dead_leftover_pane_is_replaced`; fails when the dead pane is re-attached; mutant `M-launch-reattach-dead`.
6. A fake agent scripted to print a nonce line and exit 3 makes agentctl print that line on its own stderr and exit 3, and afterwards `has-session -t =NAME` fails, against the fake's record that the session existed — `tests/e2e/test_launch.py::test_instant_exit_relays_output_and_leaves_nothing`; fails when the session survives or the line goes into the pane; mutants `M-launch-keep-session-on-instant-exit`, `M-launch-warn-into-pane`.
7. A refused login-shaped ARGS, a constructed PATH without the agent and a fake agent scripted logged out each leave no session and exit non-zero with the oracle warning, while a run in the same test with the agent present creates its session — `tests/e2e/test_launch.py::test_preflight_failure_leaves_nothing`; fails when a failure exits 0; mutant `M-launch-exit-zero-on-failure`.
8. With no TTY the session exists afterwards, the printed attach command names it, and the exit is 0 — `tests/e2e/test_launch.py::test_no_tty_prints_attach_command`; fails when the no-TTY path tries to attach; mutant `M-launch-notty-attaches`.
9. Under a PTY with `TMUX` unset the client attaches and the session reports one attached client — `tests/e2e/test_launch.py::test_attach_under_pty`; fails when the TTY path prints the attach command instead; mutant `M-launch-notty-attaches`.
10. With a client already attached to the private server under a PTY and `TMUX` set, that client switches to the new session and no nested client starts — `tests/e2e/test_launch.py::test_inside_tmux_switches_client`; fails when an attach is tried inside tmux; mutant `M-launch-notty-attaches`.
11. The production invocation carries cwd separately from argv. A folder named with `#(touch <sentinel>)` gets a sanitised session whose pane cwd is that folder, and the sentinel never appears, against a run whose folder name is plain. The compiled observer relays clients to the genuine private backend and records both create argv with the fresh nonce; neither contains `-c` — `tests/unit/test_mux_values.py::test_invocation_cwd_stays_off_argv`, `tests/e2e/test_launch.py::test_hostile_folder_name_runs_nothing`; fails when the folder reaches the multiplexer's command line; mutant `M-launch-cwd-on-mux-line`.
12. Logged-out claude and codex keep their panes alive past the startup window with the final argv, and on Linux `/proc/<pane_pid>/cmdline` ends with the mandatory flags, while the negative controls (claude ARGS `auth status`, which rejects the appended flag, and codex ARGS `exec`, which rejects `--no-daemon`) leave dead panes within the same window — `tests/integration/test_agent_argv_real.py::test_final_argv_accepted_logged_out`; fails when the window is too short to see a rejection or the argv carries the wrong agent's flags; mutant `M-launch-wrong-agent-row`.
13. The live branch for each agent holds as Deliverables state — `tests/live/test_live_launch.py::test_live_launch`; fails when a logged-in pane dies or its argv tail differs from the oracle row; no mutant: no mutant names a live test as its killer, so none runs against a real agent.

14. Malformed server identities fail without notification, and the production runner notifies a valid test-owned pid, whose compiled observer records the nonce beside its genuine native signal; psmux performs no reap query or notification — `tests/integration/test_mux_reap.py::test_reap_request_validates_pid_before_notification`; fails when a malformed pid is accepted or a valid POSIX notification is absent; no mutant: malformed identities and the observed native signal provide two-sided controls.

#### Remaining Work

None.

### Sprint 6.3: Raw passthrough and handoff [Done]

**Status**: Done
**Implementation**: `src/agentctl/cli.py`, `src/agentctl/bootstrap/handoff.py`, `src/agentctl/process.py`, `tests/harness/passthrough.py`, `tests/harness/terminal.py`, `tests/support.txt`, `tests/mutants/passthrough.toml`, `tests/oracles/command_surface.toml`, `tests/oracles/launch_argv.toml`, `src/agentctl/check/mutants.py`, `tests/governance/test_mutants.py`, `src/agentctl/paths.py`, `src/agentctl/haskell/app/`, `src/agentctl/haskell/src/AgentCtl/Protocol.hs`, `tests/unit/test_passthrough.py`, `tests/unit/test_handoff.py`, `tests/integration/test_passthrough.py`, `tests/integration/test_handoff.py`, `tests/e2e/test_passthrough_argv.py`, `tests/integration/test_command_surface.py`
**Validation tests**: `tests/unit/test_passthrough.py::test_passthrough_table_matches_oracle`, `tests/unit/test_passthrough.py::test_every_command_but_check_passes_through`, `tests/unit/test_passthrough.py::test_raw_tail_keeps_dashdash_and_help`, `tests/unit/test_handoff.py::test_handoff_mode_by_os_family`, `tests/integration/test_passthrough.py::test_passthrough_table_equals_binary_commands`, `tests/integration/test_passthrough.py::test_binary_refuses_direct_run`, `tests/integration/test_passthrough.py::test_usage_text_names_agentctl`, `tests/integration/test_passthrough.py::test_warm_passthrough_spawns_only_the_binary`, `tests/integration/test_handoff.py::test_child_mode_propagates_exit_status`, `tests/integration/test_handoff.py::test_handoff_refuses_missing_program_and_unsupported_host`, `tests/integration/test_handoff.py::test_unreadable_pins_refuse_before_transport`, `tests/integration/test_handoff.py::test_child_wait_survives_parent_console_interrupt`, `tests/integration/test_handoff.py::test_flush_failure_prevents_handoff`, `tests/e2e/test_passthrough_argv.py::test_through_stack_rows[claude]`, `tests/e2e/test_passthrough_argv.py::test_through_stack_rows[codex]`, `tests/integration/test_command_surface.py::test_cli_reference_joins_click_and_handshake`
**Mutants**: `M-pass-click-parses-tail`, `M-pass-split-drops-empty`, `M-pass-table-drops-command`, `M-pass-binary-runs-without-protocol`, `M-pass-progname-core`, `M-pass-rebuild-on-hit`, `M-pass-windows-execve`, `M-pass-child-exit-zero`, `M-launch-argv-on-mux-line`
**Closes**: R6, R9
**Docs to update**: `documents/architecture/python_haskell_boundary.md`, `documents/operations/installation.md`, `documents/reference/cli_reference.md`, `documents/engineering/testing.md`, `documents/engineering/code_standards.md`

#### Objective

Carry every command except `check` from the user's shell to the core binary with its arguments
untouched, and keep the binary out of the user's sight.

#### Deliverables

- `main(argv)` enters the click group, which parses only global options before the command. Each
  passthrough uses `RawCommand.parse_args` to retain the entire tail before a command parser can
  consume the first bare `--` or answer `--help`. `RawCommand.invoke` returns explicit transport data
  to the group dispatcher; `--assume-yes` before the command stays Python's.
- The PASSTHROUGH table lists every command except `check`, and it equals the command list the
  binary reports in its handshake (Sprint 3.1); a command reaches the user only when both sides
  name it. The CLI reference rows join both ways to click and that handshake; later commands extend the same join.
- `bootstrap/handoff.py` ensures the binary for the current digest through the one build function of
  Sprint 3.3 (a digest hit spawns nothing), passes the `cache`, `data` and `state` dirs from
  `paths.py` through the handoff protocol, flushes stdout and stderr, then calls `os.execve` on
  POSIX, or runs the binary as a child and exits with its status on Windows.
- The binary refuses to run without the handoff protocol, with a message that names `agentctl`, and
  every command it parses with optparse-applicative uses the program name `agentctl`, so neither
  usage nor error text names the core binary.
- Python never spawns tmux, psmux, claude or codex: under the spawn audit a warm passthrough's only
  spawn is the binary's execve on POSIX or its child creation on Windows.
- The through-stack rows of `tests/oracles/launch_argv.toml` (`--`, `-- --yolo`, `--help`, `-h`, an
  empty string, an element ending in `;`, `#{pane_id}`, `$(id)` and an element holding a newline)
  run as `agentctl claude …` and `agentctl codex …` under a PTY against the fake agent.

#### Validation

1. Every command of `tests/oracles/command_surface.toml` except `check`, run through the public click group under CliRunner, reaches the binary with its raw tail through POSIX execve or Windows child creation, recorded and vetoed by the spawn audit — `tests/unit/test_passthrough.py::test_every_command_but_check_passes_through`; fails when a command is missing from the table; mutant `M-pass-table-drops-command`.
2. The recorded tails of `claude -- --yolo`, `codex --help`, `claude -h` and `claude ''` equal their inputs element for element — `tests/unit/test_passthrough.py::test_raw_tail_keeps_dashdash_and_help`; fails when click parses the tail or the split drops an empty element; mutants `M-pass-click-parses-tail`, `M-pass-split-drops-empty`.
3. The handoff mode is execve for Linux and macOS and a child process for Windows — `tests/unit/test_handoff.py::test_handoff_mode_by_os_family`; fails when Windows is given execve; mutant `M-pass-windows-execve`.
4. The child mode, run on any host with the real binary scripted through a fake agent to exit 3, exits 3 — `tests/integration/test_handoff.py::test_child_mode_propagates_exit_status`; fails when the child's status is replaced by 0; mutant `M-pass-child-exit-zero`.
5. The PASSTHROUGH table equals the binary's handshake command list — `tests/integration/test_passthrough.py::test_passthrough_table_equals_binary_commands`; fails when either side lacks a command; mutant `M-pass-table-drops-command`.
6. The binary run without the handoff protocol exits non-zero with a message naming `agentctl`, while the same invocation with the protocol runs — `tests/integration/test_passthrough.py::test_binary_refuses_direct_run`; fails when the binary runs unprotected; mutant `M-pass-binary-runs-without-protocol`.
7. An unknown option to an optparse-parsed command prints usage naming `agentctl` and never `agentctl-core` — `tests/integration/test_passthrough.py::test_usage_text_names_agentctl`; fails when the program name defaults to the executable's; mutant `M-pass-progname-core`.
8. On a digest hit the spawn audit records exactly one spawn, POSIX execve or Windows child creation of the binary, and no cabal or multiplexer spawn — `tests/integration/test_passthrough.py::test_warm_passthrough_spawns_only_the_binary`; fails when the handoff rebuilds on a hit; mutant `M-pass-rebuild-on-hit`.
9. For every through-stack row and both agents, the fake agent's argv equals the row's `launchArgv` result, the literal `$(id)`, `#{pane_id}`, trailing `;` and newline arrive unchanged, and its record carries the run's nonce — `tests/e2e/test_passthrough_argv.py::test_through_stack_rows[claude]`, `tests/e2e/test_passthrough_argv.py::test_through_stack_rows[codex]`; fails when any layer parses or expands ARGS or puts the agent argv on the multiplexer's command line; mutants `M-pass-click-parses-tail`, `M-launch-argv-on-mux-line`.
10. CLI reference rows whose owning capabilities are introduced equal click's current command surface and the handshake plus Python's `check`, in both directions; other rows must name Planned owners — `tests/integration/test_command_surface.py::test_cli_reference_joins_click_and_handshake`; fails when an introduced command row is missing or duplicated, or a row has no declared owner, with a minimal complete table as the positive control; no mutant: explicit table fixtures prove both joins and the live table is checked in the same test.

#### Remaining Work

None.

## Remaining Work

None.

## Documentation Requirements

**Architecture docs to create/update:**

- `documents/architecture/launch_contract.md` — Session Names states the base, the hash form and the decision; Create or Attach states re-attach, the not-applied notice, the dead-pane replacement and the TTY, `TMUX` and no-TTY hand-over; Instant Exit and Failure and Warnings state the relay, the cleanup and the exit statuses; The Pane Trampoline states the spec launch uses.
- `documents/architecture/python_haskell_boundary.md` — the raw command parser reached by `main(argv)`, the PASSTHROUGH table and its equality with the handshake command list, the execve and child-process handoff, the dirs passed to the binary, the program name and the Python spawn set.

**Engineering docs to create/update:**

- `documents/engineering/testing.md` — the through-stack rows under a PTY, the launch tests on a private server, the direct trampoline run for real argv acceptance, and the live-test rules: branch on login state, never send input, the fixed folder and the `/proc` check.

**Operations and reference docs to create/update:**

- `documents/operations/installation.md` — the first passthrough command builds the core binary, upgrade is a pipx reinstall, removal is `pipx uninstall agentctl` plus the per-user dirs, and agentctl never logs in.
- `documents/operations/troubleshooting.md` — the relayed instant-exit output, the not-applied notice, the printed attach command and each launch warning, with what the user types.
- `documents/reference/cli_reference.md` — `agentctl claude` and `agentctl codex`, their ARGS rule and their exit statuses.
- `documents/reference/files_and_state.md` — the launch spec: its dir and modes under `state`, its fields, and its deletion by the trampoline.

**Cross-references to add:**

- `documents/architecture/multiplexer_adapter.md` — links the launch contract's Create or Attach section for `=NAME` targeting, the session options and `switch-client`.
