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

This phase needs Linux only. The declared tests are executable contracts; an absent required test is unmet evidence, not existing proof. Acceptance-only test implementations belong to the prerequisite owner named in the inventory. Existing incompatible code is inventoried in the deletion ledger. No old implementation or unqualified receipt establishes this revised contract.

## Gate Integrity

| Requirement | Oracle | Observer | Mutants | Tests |
|---|---|---|---|---|
| R16 — Managed session commands and durable identity | `tests/oracles/requirements.toml` | value; observer: independent inputs and nonce-bound native observations | `M-session-stale-instance-accepted`, `M-session-stop-prefix` | `tests/e2e/test_sessions.py::test_list_shows_only_managed`, `tests/e2e/test_sessions.py::test_stop_never_prefix_matches`, `tests/e2e/test_sessions.py::test_status_defaults_to_current_folder` |
| R17.1 — Explicit adoption and nonownership | `tests/oracles/requirements.toml` | value; observer: independent inputs and nonce-bound native observations | `M-adopt-stop-kills-target` | `tests/e2e/test_adopt.py::test_adopt_does_not_take_ownership`, `tests/e2e/test_adopt.py::test_stale_entry_after_server_restart` |

## Not Proven By This Gate

- A receipt's digest establishes input currency, not an independently attested historical run. Local receipt authenticity has the documented honest ceiling.
- A source rule or finite corpus does not prove arbitrary callback purity, universal termination or agent-internal readiness. Native operation and resource assumptions remain explicit.
- Foreign-kernel behavior is outside this phase's Linux verdict. Later native implementation extends the common contract and cannot retroactively add a foreign-hardware requirement here.

## Sprints

### Sprint 6.1: Managed session commands and durable identity [Planned]

**Status**: Planned
**Implementation**: `src/agentctl/haskell/src/AgentCtl/Sessions.hs`, `src/agentctl/haskell/src/AgentCtl/Session/Identity.hs`
**Validation tests**: `tests/e2e/test_sessions.py::test_list_shows_only_managed`, `tests/e2e/test_sessions.py::test_stop_never_prefix_matches`, `tests/e2e/test_sessions.py::test_status_defaults_to_current_folder`
**Mutants**: `M-session-stale-instance-accepted`, `M-session-stop-prefix`
**Closes**: R16
**Docs to update**: `documents/architecture/sessions_and_ownership.md`, `documents/reference/files_and_state.md`, `documents/reference/cli_reference.md`

#### Objective

Managed session commands and durable identity supplies its complete owned contract through the single phase-scoped gate verdict.

#### Deliverables

Implement list/status/attach/stop with exact targeting, immutable instance records and command-specific prerequisites. Discoverability includes the registry/namespace and server provenance, never only a numeric pane id. State files publish atomically while held lock files retain their inode.

#### Validation

Construct sibling names, foreign sessions and a replaced server. Require complete public output, exact stop ownership and no unrelated session effects. Concurrent state writes preserve every accepted entry or return a named refusal.

Required executable evidence: `tests/e2e/test_sessions.py::test_list_shows_only_managed`, `tests/e2e/test_sessions.py::test_stop_never_prefix_matches`, `tests/e2e/test_sessions.py::test_status_defaults_to_current_folder`. Every named mutant must die for its recorded reason in those tests; a baseline failure or unrelated exception is not a kill.

#### Remaining Work

The whole sprint.

### Sprint 6.2: Explicit adoption and nonownership [Planned]

**Status**: Planned
**Implementation**: `src/agentctl/haskell/src/AgentCtl/Adopt.hs`, `src/agentctl/haskell/src/AgentCtl/Paths.hs`
**Validation tests**: `tests/e2e/test_adopt.py::test_adopt_does_not_take_ownership`, `tests/e2e/test_adopt.py::test_stale_entry_after_server_restart`
**Mutants**: `M-adopt-stop-kills-target`
**Closes**: R17.1
**Docs to update**: `documents/architecture/sessions_and_ownership.md`, `documents/reference/files_and_state.md`, `documents/reference/cli_reference.md`

#### Objective

Explicit adoption and nonownership supplies its complete owned contract through the single phase-scoped gate verdict.

#### Deliverables

Adoption names an explicit endpoint and records a revalidated identity without changing its configuration. Access to an external backend does not grant qualified capture or input capabilities. Stop on an adopted target only forgets it.

#### Validation

Observe original pane/process/options before adoption and after adoption and forgetting. Every identity is unchanged; replacing the server makes its adoption stale rather than attaching to a recycled pane id.

Required executable evidence: `tests/e2e/test_adopt.py::test_adopt_does_not_take_ownership`, `tests/e2e/test_adopt.py::test_stale_entry_after_server_restart`. Every named mutant must die for its recorded reason in those tests; a baseline failure or unrelated exception is not a kill.

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

- `documents/reference/files_and_state.md` — preparation, qualified host observations and actionable refusals.
- `documents/reference/cli_reference.md` — preparation, qualified host observations and actionable refusals.

**Cross-references to add:**

- `DEVELOPMENT_PLAN/00-overview.md` — requirement closure and lower-phase dependencies.
- `DEVELOPMENT_PLAN/system-components.md` — stable capability/path ownership.
- `DEVELOPMENT_PLAN/legacy_tracking_for_deletion.md` — remaining incompatible implementation shapes.
