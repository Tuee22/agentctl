# Phase 5 — Agent preflight and launch

**Status**: Planned
**Depends on**: [Phase 4 — Debian tmux and multiplexer](phase-4-debian-tmux-and-multiplexer.md)
**Host lane**: linux
**Gate**: `agentctl check`
**Gate kind**: self-verifying
**Closes**: R7, R8, R9, R10, R11, R12, R12.2, R13

> **Purpose**: User-installed agent discovery, authentication refusal, immutable argv assembly and folder-derived launch/reattach.

## Phase Objective

User-installed agent discovery, authentication refusal, immutable argv assembly and folder-derived launch/reattach. Haskell fails early on a missing requested agent and never installs agents or logs them in.

This phase's verdict evaluates the `linux` half ([T.V](development_plan_standards.md#tv-verdict) V8) at stage 2 ([T.W](development_plan_standards.md#tw-staged-enforcement)) and needs no logged-in agent. Every cited artifact is owned within closure(5) ([§ A](development_plan_standards.md#a-well-ordered-constructive-narrative)), a planned absence is unmet work of this phase ([T.F](development_plan_standards.md#tf-shared-and-owned-failures)), and present incompatible code is a deletion-ledger row of its owner. Native Windows PATHEXT discovery and verbatim argv are owed to [Windows application acceptance](phase-11-windows-application-acceptance.md), and the logged-in live launch is owed to the `linux-live` half of [Linux live and clean acceptance](phase-12-linux-live-and-clean-acceptance.md); neither is a gap in this verdict. Its Haskell modules and native tests form this phase's own build component, discovered through the `cabal.project` package glob of [Python bootstrap and handoff](phase-2-python-bootstrap-and-handoff.md); it edits no earlier component ([§ A](development_plan_standards.md#a-well-ordered-constructive-narrative) A1, A2).

## Gate Integrity

| Requirement | Oracle | Observer | Mutants | Tests |
|---|---|---|---|---|
| R9 — Agent boundary and exact argv | `tests/oracles/requirements.toml` | value: independent argv, agent-table, resolution, authentication-status and preflight-warning expectations; real: the pinned compiler refusing direct construction of the readiness capability; observer: nonce-bound caller-environment and preflight-order observations; owed: windows-application-acceptance | `M-argv-dedupe-past-dashdash`, `M-argv-drop-no-daemon`, `M-argv-flags-after-dashdash`, `M-argv-keep-yolo`, `M-argv-misspell-skip-permissions`, `M-argv-recovery-slash-command`, `M-auth-exit2-as-logged-out`, `M-auth-pass-setup-token`, `M-auth-probe-drops-env`, `M-auth-remedy-wrong-command`, `M-auth-timeout-as-logged-in`, `M-preflight-accept-cmd-shim`, `M-preflight-allow-logged-out`, `M-preflight-auth-before-mux`, `M-preflight-export-ready-constructor`, `M-preflight-relative-agent-path`, `M-preflight-skip-auth` | `tests/unit/test_launch_argv.py::test_launch_argv_matches_oracle`, `tests/integration/test_agent_auth_probe.py::test_auth_probe_is_status_only`, `tests/integration/test_agent_install_refusal.py::test_missing_requested_agent_has_no_install_effects`, `tests/unit/test_agent_table.py::test_agent_table_matches_oracle`, `tests/unit/test_auth_status.py::test_classify_auth_matches_oracle`, `tests/unit/test_auth_status.py::test_login_shaped_args_refused`, `tests/integration/test_agent_auth_probe.py::test_probe_sees_caller_environment`, `tests/unit/test_auth_status.py::test_remedy_names_the_command_to_type`, `tests/unit/test_agent_resolution.py::test_resolution_matches_oracle`, `tests/unit/test_preflight.py::test_failure_warnings_match_oracle`, `tests/integration/test_preflight.py::test_order_mux_then_agent_then_auth`, `tests/integration/test_ready_opaque.py::test_ready_constructor_is_not_exported` |
| R7 — Named launch, reattach and startup failure | `tests/oracles/requirements.toml` | value: independent launch-plan and session-name expectations; real: dead-pane replacement, logged-out final argv and the private session-name constructor; observer: nonce-bound through-stack argv, named-session, reattachment and instant-exit observations; owed: linux-live-and-clean-acceptance | `M-launch-argv-on-mux-line`, `M-launch-env-not-caller`, `M-launch-exit-zero-on-failure`, `M-launch-keep-session-on-instant-exit`, `M-launch-kill-on-reattach`, `M-launch-notty-attaches`, `M-launch-preflight-on-reattach`, `M-launch-reattach-dead`, `M-launch-skip-launch-argv`, `M-launch-warn-into-pane`, `M-launch-wrong-agent-row`, `M-mux-name-allows-double-underscore`, `M-mux-name-constructor-exported`, `M-name-hash-basename`, `M-name-keep-underscore-runs`, `M-name-no-collapse`, `M-name-plain-for-foreign`, `M-name-posix-case-fold` | `tests/e2e/test_launch.py::test_rerun_reattaches_without_preflight`, `tests/e2e/test_launch.py::test_instant_exit_relays_output_and_leaves_nothing`, `tests/e2e/test_passthrough_argv.py::test_through_stack_rows[claude]`, `tests/e2e/test_passthrough_argv.py::test_through_stack_rows[codex]`, `tests/e2e/test_launch.py::test_creates_named_session_with_flags_last`, `tests/e2e/test_launch.py::test_dead_leftover_pane_is_replaced`, `tests/unit/test_launch_plan.py::test_launch_plan_matches_oracle`, `tests/integration/test_agent_argv_real.py::test_final_argv_accepted_logged_out`, `tests/unit/test_mux_values.py::test_session_name_oracle`, `tests/integration/test_mux_resolution.py::test_session_name_constructor_is_private`, `tests/unit/test_session_names.py::test_session_names_match_oracle`, `tests/unit/test_session_names.py::test_decision_rows_match_oracle`, `haskell:agentctl-core-test/Name/always-valid` |

## Not Proven By This Gate

- Limits: [T.C](development_plan_standards.md#tc-ceiling); none is a closure condition.
- A status probe and help canaries observe only what the installed agent CLI reports, never agent-internal readiness ([T.C](development_plan_standards.md#tc-ceiling) C5).

## Sprints

### Sprint 5.1: Agent boundary and exact argv [Planned]

**Status**: Planned
**Implementation**: `src/agentctl/haskell/src/AgentCtl/Agent.hs`, `src/agentctl/haskell/src/AgentCtl/Agent/`, `src/agentctl/haskell/src/AgentCtl/Preflight.hs`, `tests/integration/test_agent_install_refusal.py`
**Validation tests**: `tests/unit/test_launch_argv.py::test_launch_argv_matches_oracle`, `tests/integration/test_agent_auth_probe.py::test_auth_probe_is_status_only`, `tests/integration/test_agent_install_refusal.py::test_missing_requested_agent_has_no_install_effects`, `tests/integration/test_agent_argv_real.py::test_final_argv_accepted_logged_out`, `tests/integration/test_preflight.py::test_order_mux_then_agent_then_auth`, `tests/integration/test_ready_opaque.py::test_ready_constructor_is_not_exported`, `tests/unit/test_agent_resolution.py::test_resolution_matches_oracle`, `tests/unit/test_agent_table.py::test_agent_table_matches_oracle`, `tests/unit/test_auth_status.py::test_classify_auth_matches_oracle`, `tests/unit/test_preflight.py::test_failure_warnings_match_oracle`, `tests/unit/test_auth_status.py::test_login_shaped_args_refused`, `tests/unit/test_auth_status.py::test_remedy_names_the_command_to_type`, `tests/integration/test_agent_auth_probe.py::test_probe_sees_caller_environment`, `tests/integration/test_agent_real.py::test_logged_out_by_construction`, `tests/integration/test_agent_real.py::test_help_canaries_list_mandatory_flags`
**Mutants**: `M-argv-dedupe-past-dashdash`, `M-argv-drop-no-daemon`, `M-argv-flags-after-dashdash`, `M-argv-keep-yolo`, `M-argv-misspell-skip-permissions`, `M-argv-recovery-slash-command`, `M-auth-exit2-as-logged-out`, `M-auth-pass-setup-token`, `M-auth-probe-drops-env`, `M-auth-remedy-wrong-command`, `M-auth-timeout-as-logged-in`, `M-preflight-accept-cmd-shim`, `M-preflight-allow-logged-out`, `M-preflight-auth-before-mux`, `M-preflight-export-ready-constructor`, `M-preflight-relative-agent-path`, `M-preflight-skip-auth`
**Closes**: R9, R10, R11, R12.2, R13
**Docs to update**: `documents/architecture/launch_contract.md`, migrates `documents/architecture/python_haskell_boundary.md` (owner [Python bootstrap and handoff](phase-2-python-bootstrap-and-handoff.md)), migrates `documents/operations/installation.md` (owner [Python bootstrap and handoff](phase-2-python-bootstrap-and-handoff.md))

#### Objective

Agent boundary and exact argv supplies its complete owned contract through the single phase-scoped gate verdict.

#### Deliverables

Check only the requested agent for a fresh launch, before costly backend preparation. Authentication is an observed status-only query; no credentials are modified. Preserve raw tail semantics, mandatory flags and discrete user-facing remedies. list/attach/logs do not require fresh agent authentication. This sprint moves the Windows multiplexer arm of `src/agentctl/haskell/src/AgentCtl/Preflight.hs`, the `psmux` name and `3.4.0` version floor that `multiplexerWarning` chooses for the Windows family, behind its interface to `src/agentctl/haskell/src/AgentCtl/Preflight/Windows.hs` (owner [Windows toolchain and psmux build](phase-9-windows-toolchain-and-psmux-build.md)), the host-declared module that phase lists in its Implementation ([§ A](development_plan_standards.md#a-well-ordered-constructive-narrative) A3). In the same change the Windows multiplexer warning rows of `tests/oracles/preflight.toml` gain appended `amends` cases that T.I projects to that phase, their cases move to its nodes with any killer entries through killer-relocation records ([T.G](development_plan_standards.md#tg-governed-changes)), and both phases' fields are edited, so no node this phase cites executes that module and no later phase edits `Preflight.hs` (D-157). Planned mutants, named here until their corpus rows land ([§ C](development_plan_standards.md#c-honest-completion-tracking)): `M-agent-auto-install`, `M-argv-mandatory-flags-first` and `M-auth-login-spawn`.

Agent preflight and launch owns the agent-CLI model (argv grammar, status, version and startup screens) anchored to transcript rows; replaying those rows against the installed agents is a confirmation that the implementing change owes to [Linux live and clean acceptance](phase-12-linux-live-and-clean-acceptance.md), landing with its Confirms line there. Outside the live half no test runs the installed agents (D-172): `tests/integration/test_agent_real.py`, `tests/integration/test_agent_argv_real.py` and the real-agent cases of `tests/integration/test_preflight.py` convert in place to the agent-CLI model under their node ids, keeping each killer's reason, so `tests/integration/test_agent_argv_real.py::test_final_argv_accepted_logged_out` still kills `M-launch-wrong-agent-row` (D-178).

#### Validation

Independently record final argv including -- and hostile arguments. Constructed Windows executable/PATHEXT selector states and logged-out states produce exact nonzero refusals and zero install/login effects. No test sends live agent input.

Every node in **Validation tests** passes in a verified run and every named mutant is killed per [T.K](development_plan_standards.md#tk-kill) at stage 2.

#### Remaining Work

The whole sprint.

### Sprint 5.2: Named launch, reattach and startup failure [Planned]

**Status**: Planned
**Implementation**: `src/agentctl/haskell/src/AgentCtl/Launch.hs`, `src/agentctl/haskell/src/AgentCtl/Session/Name.hs`, `tests/harness/live.py`, `tests/live/test_live_launch.py`
**Validation tests**: `tests/e2e/test_launch.py::test_rerun_reattaches_without_preflight`, `tests/e2e/test_launch.py::test_instant_exit_relays_output_and_leaves_nothing`, `tests/e2e/test_passthrough_argv.py::test_through_stack_rows[claude]`, `tests/e2e/test_passthrough_argv.py::test_through_stack_rows[codex]`, `tests/integration/test_mux_resolution.py::test_session_name_constructor_is_private`, `tests/unit/test_launch_plan.py::test_launch_plan_matches_oracle`, `tests/unit/test_session_names.py::test_session_names_match_oracle`, `tests/e2e/test_launch.py::test_creates_named_session_with_flags_last`, `tests/e2e/test_launch.py::test_dead_leftover_pane_is_replaced`, `tests/integration/test_agent_argv_real.py::test_final_argv_accepted_logged_out`, `tests/unit/test_mux_values.py::test_session_name_oracle`, `tests/unit/test_session_names.py::test_decision_rows_match_oracle`, `haskell:agentctl-core-test/Name/always-valid`, `tests/live/test_live_launch.py::test_live_launch_refuses_without_login`
**Mutants**: `M-launch-argv-on-mux-line`, `M-launch-env-not-caller`, `M-launch-exit-zero-on-failure`, `M-launch-keep-session-on-instant-exit`, `M-launch-kill-on-reattach`, `M-launch-notty-attaches`, `M-launch-preflight-on-reattach`, `M-launch-reattach-dead`, `M-launch-skip-launch-argv`, `M-launch-warn-into-pane`, `M-launch-wrong-agent-row`, `M-mux-name-allows-double-underscore`, `M-mux-name-constructor-exported`, `M-name-hash-basename`, `M-name-keep-underscore-runs`, `M-name-no-collapse`, `M-name-plain-for-foreign`, `M-name-posix-case-fold`
**Closes**: R7, R8, R12
**Docs to update**: `documents/architecture/launch_contract.md`, migrates `documents/architecture/python_haskell_boundary.md` (owner [Python bootstrap and handoff](phase-2-python-bootstrap-and-handoff.md)), migrates `documents/operations/installation.md` (owner [Python bootstrap and handoff](phase-2-python-bootstrap-and-handoff.md))

#### Objective

Named launch, reattach and startup failure supplies its complete owned contract through the single phase-scoped gate verdict.

#### Deliverables

Deliver the launch observer with generation/acknowledgment marker publication and closed handles, extending the already usable base mux observer. Separate live launch observation from later session helpers and prove it remains usable. Derive canonical folder+agent names, disambiguate collisions and reattach without repeating unnecessary readiness work. A checked Ready capability authorizes creation; failed creation leaves no managed session. Startup exit reports actual child status and output. Planned mutants, named here until their corpus rows land ([§ C](development_plan_standards.md#c-honest-completion-tracking)): `M-launch-failure-leaks-session` and `M-launch-folder-collision`.

`Launch.execute` runs over the effect records of D-173, so its launch, reattach and startup paths run as model twins on every host. `tests/live/test_live_launch.py` and `tests/harness/live.py` move to [Linux live and clean acceptance](phase-12-linux-live-and-clean-acceptance.md) (D-179), and this phase keeps a portable refusal case against the fake agent, planned as `tests/integration/test_launch.py::test_launch_refuses_without_login`.

#### Validation

The no-input live launch observer `tests/live/test_live_launch.py` stays independent of ordinary fake-agent controls: this sprint cites its portable refusal node, and its logged-in launch node, declared to the `linux-live` half ([T.X](development_plan_standards.md#tx-terms)), is the `linux-live` evidence of [Linux live and clean acceptance](phase-12-linux-live-and-clean-acceptance.md). Launch the native fake agent through the public Python command and real tmux. Repeated same-folder launch retains pane/process identity, hostile folder text executes nothing, failed preflight leaves no session, and an instant exit preserves its actual status.

Every node in **Validation tests** passes in a verified run and every named mutant is killed per [T.K](development_plan_standards.md#tk-kill) at stage 2.

#### Remaining Work

The whole sprint.

## Remaining Work

The whole phase: Sprints 5.1–5.2.

## Documentation Requirements

**Architecture docs to create/update:**

- `documents/architecture/launch_contract.md` — this phase's owned contract and links to prerequisite interfaces.
- migrates `documents/architecture/python_haskell_boundary.md` (owner [Python bootstrap and handoff](phase-2-python-bootstrap-and-handoff.md)) — this phase's owned contract and links to prerequisite interfaces.

**Engineering docs to create/update:**

- None.

**Operations and reference docs to create/update:**

- migrates `documents/operations/installation.md` (owner [Python bootstrap and handoff](phase-2-python-bootstrap-and-handoff.md)) — preparation, qualified host observations and actionable refusals.

**Cross-references to add:**

- `DEVELOPMENT_PLAN/00-overview.md` — requirement closure and lower-phase dependencies.
- `DEVELOPMENT_PLAN/system-components.md` — stable capability/path ownership.
- `DEVELOPMENT_PLAN/legacy_tracking_for_deletion.md` — remaining incompatible implementation shapes.
