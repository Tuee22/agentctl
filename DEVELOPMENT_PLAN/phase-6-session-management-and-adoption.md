# Phase 6 — Session management and adoption

**Status**: Planned
**Depends on**: [Phase 5 — Agent preflight and launch](phase-5-agent-preflight-and-launch.md)
**Host lane**: linux
**Gate**: `agentctl check`
**Gate kind**: self-verifying
**Closes**: R16, R17.1

> **Purpose**: Session management and adoption use checked instance identity and retain the distinction between access, ownership and supervision.

## Phase Objective

Session management and adoption use checked instance identity and retain the distinction between access, ownership and supervision. Private Windows registries extend this endpoint model without taking ownership of external sessions.

This phase's verdict evaluates the `linux` half ([T.V](development_plan_standards.md#tv-verdict) V8) at stage 2 ([T.W](development_plan_standards.md#tw-staged-enforcement)). Every cited artifact is owned within closure(6) ([§ A](development_plan_standards.md#a-well-ordered-constructive-narrative)), a planned absence is unmet work of this phase ([T.F](development_plan_standards.md#tf-shared-and-owned-failures)), and present incompatible code is a deletion-ledger row of its owner. Native Windows registry and endpoint identity is owed to [Windows application acceptance](phase-11-windows-application-acceptance.md); it is not a gap in this verdict. Its Haskell modules and native tests form this phase's own build component, discovered through the `cabal.project` package glob of [Python bootstrap and handoff](phase-2-python-bootstrap-and-handoff.md); it edits no earlier component ([§ A](development_plan_standards.md#a-well-ordered-constructive-narrative) A1, A2).

## Gate Integrity

| Requirement | Oracle | Observer | Mutants | Tests |
|---|---|---|---|---|
| R16 — Managed session commands and durable identity | `tests/oracles/requirements.toml` | value: independent list-row, attach-plan and stop-plan expectations; real: managed listing, dead-pane and folder-default status, attachment and foreign-stop refusal through real tmux; observer: nonce-bound prefix-sibling and status-screen observations; owed: windows-application-acceptance | `M-classify-status-stale-capture`, `M-sessions-attach-wrong-target`, `M-sessions-dead-as-alive`, `M-sessions-list-includes-foreign`, `M-sessions-status-wrong-folder`, `M-sessions-stop-kills-foreign` | `tests/e2e/test_sessions.py::test_list_shows_only_managed`, `tests/e2e/test_sessions.py::test_stop_never_prefix_matches`, `tests/e2e/test_sessions.py::test_status_defaults_to_current_folder`, `tests/e2e/test_status_screen.py::test_screen_column_shows_fixture_class`, `tests/unit/test_sessions_values.py::test_attach_plan_matches_oracle`, `tests/e2e/test_sessions.py::test_attach_and_switch_under_pty`, `tests/e2e/test_sessions.py::test_attach_without_tty_prints_command`, `tests/unit/test_sessions_values.py::test_list_rows_match_oracle`, `tests/e2e/test_sessions.py::test_status_reports_dead_pane`, `tests/unit/test_sessions_values.py::test_stop_plan_matches_oracle`, `tests/e2e/test_sessions.py::test_stop_refuses_foreign_session` |
| R17.1 — Explicit adoption and nonownership | `tests/oracles/requirements.toml` | value: independent adoption-row expectations; real: stale adoption after a server restart; observer: nonce-bound pane, process and option observations before and after adoption | `M-adopt-no-pid-revalidation`, `M-adopt-no-socket-revalidation`, `M-adopt-sets-session-options`, `M-adopt-stop-kills` | `tests/e2e/test_adopt.py::test_adopt_does_not_take_ownership`, `tests/e2e/test_adopt.py::test_stale_entry_after_server_restart`, `tests/unit/test_adopt_values.py::test_adopt_rows_match_oracle` |

## Not Proven By This Gate

- Limits: [T.C](development_plan_standards.md#tc-ceiling); none is a closure condition.
- Observed instance identity proves which server, session and pane existed when observed, never exclusive access to an adopted endpoint.

## Sprints

### Sprint 6.1: Managed session commands and durable identity [Planned]

**Status**: Planned
**Implementation**: `src/agentctl/haskell/src/AgentCtl/Sessions.hs`, `src/agentctl/haskell/src/AgentCtl/Session/Identity.hs`, `tests/harness/sessions.py`
**Validation tests**: `tests/e2e/test_sessions.py::test_list_shows_only_managed`, `tests/e2e/test_sessions.py::test_stop_never_prefix_matches`, `tests/e2e/test_sessions.py::test_status_defaults_to_current_folder`, `tests/unit/test_sessions_values.py::test_list_rows_match_oracle`, `tests/e2e/test_status_screen.py::test_screen_column_shows_fixture_class`, `tests/unit/test_sessions_values.py::test_attach_plan_matches_oracle`, `tests/e2e/test_sessions.py::test_attach_and_switch_under_pty`, `tests/e2e/test_sessions.py::test_attach_without_tty_prints_command`, `tests/e2e/test_sessions.py::test_status_reports_dead_pane`, `tests/unit/test_sessions_values.py::test_stop_plan_matches_oracle`, `tests/e2e/test_sessions.py::test_stop_refuses_foreign_session`
**Mutants**: `M-classify-status-stale-capture`, `M-sessions-attach-wrong-target`, `M-sessions-dead-as-alive`, `M-sessions-list-includes-foreign`, `M-sessions-status-wrong-folder`, `M-sessions-stop-kills-foreign`
**Closes**: R16
**Docs to update**: `documents/architecture/sessions_and_ownership.md`, migrates `documents/reference/files_and_state.md` (owner [Haskell runtime and platform policy](phase-3-haskell-runtime-and-platform-policy.md))

#### Objective

Managed session commands and durable identity supplies its complete owned contract through the single phase-scoped gate verdict.

#### Deliverables

Implement list/status/attach/stop with exact targeting, immutable instance records and command-specific prerequisites. Separate session observation from later screen-classification helpers and prove it remains usable. Preserve the stale-capture mutant and its status observation while separating that test from the later classifier. Discoverability includes the registry/namespace and server provenance, never only a numeric pane id. State files publish atomically while held lock files retain their inode. Planned mutants, named here until their corpus rows land ([§ C](development_plan_standards.md#c-honest-completion-tracking)): `M-session-stale-instance-accepted` and `M-session-stop-prefix`.

`Sessions.run` and its readers run over the effect records of D-173. The session and foreign-population models compose only the tmux, files and clock models owned within this closure (D-177); e2e killers convert in place where they still kill for their reason (D-178).

#### Validation

Construct sibling names, foreign sessions and a replaced server. Require complete public output, exact stop ownership and no unrelated session effects. Concurrent state writes preserve every accepted entry or return a named refusal.

Every node in **Validation tests** passes in a verified run and every named mutant is killed per [T.K](development_plan_standards.md#tk-kill) at stage 2.

#### Remaining Work

The whole sprint.

### Sprint 6.2: Explicit adoption and nonownership [Planned]

**Status**: Planned
**Implementation**: `src/agentctl/haskell/src/AgentCtl/Adopt.hs`
**Validation tests**: `tests/e2e/test_adopt.py::test_adopt_does_not_take_ownership`, `tests/e2e/test_adopt.py::test_stale_entry_after_server_restart`, `tests/unit/test_adopt_values.py::test_adopt_rows_match_oracle`
**Mutants**: `M-adopt-no-pid-revalidation`, `M-adopt-no-socket-revalidation`, `M-adopt-sets-session-options`, `M-adopt-stop-kills`
**Closes**: R17.1
**Docs to update**: `documents/architecture/sessions_and_ownership.md`, migrates `documents/reference/files_and_state.md` (owner [Haskell runtime and platform policy](phase-3-haskell-runtime-and-platform-policy.md))

#### Objective

Explicit adoption and nonownership supplies its complete owned contract through the single phase-scoped gate verdict.

#### Deliverables

Adoption names an explicit endpoint and records a revalidated identity without changing its configuration. Access to an external backend does not grant qualified capture or input capabilities. Stop on an adopted target only forgets it. This sprint consumes `src/agentctl/haskell/src/AgentCtl/Paths.hs`, whose path derivation supplies the registry location. The planned mutant `M-adopt-stop-kills-target` is named here until its corpus row lands ([§ C](development_plan_standards.md#c-honest-completion-tracking)).

#### Validation

Observe original pane/process/options before adoption and after adoption and forgetting. Every identity is unchanged; replacing the server makes its adoption stale rather than attaching to a recycled pane id.

Every node in **Validation tests** passes in a verified run and every named mutant is killed per [T.K](development_plan_standards.md#tk-kill) at stage 2.

#### Remaining Work

The whole sprint.

## Remaining Work

The whole phase: Sprints 6.1–6.2.

## Documentation Requirements

**Architecture docs to create/update:**

- `documents/architecture/sessions_and_ownership.md` — this phase's owned contract and links to prerequisite interfaces.

**Engineering docs to create/update:**

- None.

**Operations and reference docs to create/update:**

- migrates `documents/reference/files_and_state.md` (owner [Haskell runtime and platform policy](phase-3-haskell-runtime-and-platform-policy.md)) — preparation, qualified host observations and actionable refusals.

**Cross-references to add:**

- `DEVELOPMENT_PLAN/00-overview.md` — requirement closure and lower-phase dependencies.
- `DEVELOPMENT_PLAN/system-components.md` — stable capability/path ownership.
- `DEVELOPMENT_PLAN/legacy_tracking_for_deletion.md` — remaining incompatible implementation shapes.
