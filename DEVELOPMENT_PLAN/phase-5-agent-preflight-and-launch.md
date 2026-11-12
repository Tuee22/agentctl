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

This phase needs Linux only. The declared tests are executable contracts; an absent required test is unmet evidence, not existing proof. Acceptance-only test implementations belong to the prerequisite owner named in the inventory. Existing incompatible code is inventoried in the deletion ledger. No old implementation or unqualified receipt establishes this revised contract.

## Gate Integrity

| Requirement | Oracle | Observer | Mutants | Tests |
|---|---|---|---|---|
| R9 — Agent boundary and exact argv | `tests/oracles/requirements.toml` | value; observer: independent inputs and nonce-bound native observations | `M-agent-auto-install`, `M-argv-mandatory-flags-first`, `M-auth-login-spawn` | `tests/unit/test_launch_argv.py::test_launch_argv_matches_oracle`, `tests/integration/test_agent_auth_probe.py::test_auth_probe_is_status_only`, `tests/integration/test_agent_install_refusal.py::test_missing_requested_agent_has_no_install_effects` |
| R7 — Named launch, reattach and startup failure | `tests/oracles/requirements.toml` | value; observer: independent inputs and nonce-bound native observations | `M-launch-folder-collision`, `M-launch-preflight-bypassed`, `M-launch-failure-leaks-session` | `tests/e2e/test_launch.py::test_rerun_reattaches_without_preflight`, `tests/e2e/test_launch.py::test_instant_exit_relays_output_and_leaves_nothing`, `tests/e2e/test_passthrough_argv.py::test_through_stack_rows` |

## Not Proven By This Gate

- A receipt's digest establishes input currency, not an independently attested historical run. Local receipt authenticity has the documented honest ceiling.
- A source rule or finite corpus does not prove arbitrary callback purity, universal termination or agent-internal readiness. Native operation and resource assumptions remain explicit.
- Foreign-kernel behavior is outside this phase's Linux verdict. Later native implementation extends the common contract and cannot retroactively add a foreign-hardware requirement here.

## Sprints

### Sprint 5.1: Agent boundary and exact argv [Planned]

**Status**: Planned
**Implementation**: `src/agentctl/haskell/src/AgentCtl/Agent/`, `src/agentctl/haskell/src/AgentCtl/Preflight.hs`
**Validation tests**: `tests/unit/test_launch_argv.py::test_launch_argv_matches_oracle`, `tests/integration/test_agent_auth_probe.py::test_auth_probe_is_status_only`, `tests/integration/test_agent_install_refusal.py::test_missing_requested_agent_has_no_install_effects`
**Mutants**: `M-agent-auto-install`, `M-argv-mandatory-flags-first`, `M-auth-login-spawn`
**Closes**: R9, R10, R11, R12.2, R13
**Docs to update**: `documents/architecture/launch_contract.md`, `documents/architecture/python_haskell_boundary.md`, `documents/operations/installation.md`

#### Objective

Agent boundary and exact argv supplies its complete owned contract through the single phase-scoped gate verdict.

#### Deliverables

Check only the requested agent for a fresh launch, before costly backend preparation. Authentication is an observed status-only query; no credentials are modified. Preserve raw tail semantics, mandatory flags and discrete user-facing remedies. list/attach/logs do not require fresh agent authentication.

#### Validation

Independently record final argv including -- and hostile arguments. Constructed Windows executable/PATHEXT selector states and logged-out states produce exact nonzero refusals and zero install/login effects. No test sends live agent input.

Required executable evidence: `tests/unit/test_launch_argv.py::test_launch_argv_matches_oracle`, `tests/integration/test_agent_auth_probe.py::test_auth_probe_is_status_only`, `tests/integration/test_agent_install_refusal.py::test_missing_requested_agent_has_no_install_effects`. Every named mutant must die for its recorded reason in those tests; a baseline failure or unrelated exception is not a kill.

#### Remaining Work

The whole sprint.

### Sprint 5.2: Named launch, reattach and startup failure [Planned]

**Status**: Planned
**Implementation**: `src/agentctl/haskell/src/AgentCtl/Launch.hs`, `src/agentctl/haskell/src/AgentCtl/Session/Name.hs`
**Validation tests**: `tests/e2e/test_launch.py::test_rerun_reattaches_without_preflight`, `tests/e2e/test_launch.py::test_instant_exit_relays_output_and_leaves_nothing`, `tests/e2e/test_passthrough_argv.py::test_through_stack_rows`
**Mutants**: `M-launch-folder-collision`, `M-launch-preflight-bypassed`, `M-launch-failure-leaks-session`
**Closes**: R7, R8, R12
**Docs to update**: `documents/architecture/launch_contract.md`, `documents/architecture/python_haskell_boundary.md`, `documents/operations/installation.md`

#### Objective

Named launch, reattach and startup failure supplies its complete owned contract through the single phase-scoped gate verdict.

#### Deliverables

Deliver the launch observer with generation/acknowledgment marker publication and closed handles, extending the already usable base mux observer. Derive canonical folder+agent names, disambiguate collisions and reattach without repeating unnecessary readiness work. A checked Ready capability authorizes creation; failed creation leaves no managed session. Startup exit reports actual child status and output.

#### Validation

Introduce the no-input live launch observer tests/live/test_live_launch.py with explicit authenticated-lane receipts, independently of ordinary fake-agent controls. Launch the native fake agent through the public Python command and real tmux. Repeated same-folder launch retains pane/process identity, hostile folder text executes nothing, failed preflight leaves no session, and an instant exit preserves its actual status.

Required executable evidence: `tests/e2e/test_launch.py::test_rerun_reattaches_without_preflight`, `tests/e2e/test_launch.py::test_instant_exit_relays_output_and_leaves_nothing`, `tests/e2e/test_passthrough_argv.py::test_through_stack_rows`. Every named mutant must die for its recorded reason in those tests; a baseline failure or unrelated exception is not a kill.

#### Remaining Work

The whole sprint.

## Remaining Work

The whole phase: Sprints 5.1–5.2.

## Documentation Requirements

**Architecture docs to create/update:**

- `documents/architecture/launch_contract.md` — this phase's owned contract and links to prerequisite interfaces.
- `documents/architecture/python_haskell_boundary.md` — this phase's owned contract and links to prerequisite interfaces.

**Engineering docs to create/update:**

- None.

**Operations and reference docs to create/update:**

- `documents/operations/installation.md` — preparation, qualified host observations and actionable refusals.

**Cross-references to add:**

- `DEVELOPMENT_PLAN/00-overview.md` — requirement closure and lower-phase dependencies.
- `DEVELOPMENT_PLAN/system-components.md` — stable capability/path ownership.
- `DEVELOPMENT_PLAN/legacy_tracking_for_deletion.md` — remaining incompatible implementation shapes.
