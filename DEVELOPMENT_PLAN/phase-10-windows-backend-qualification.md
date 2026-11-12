# Phase 10 — Windows backend qualification

**Status**: Planned
**Depends on**: [Phase 9 — Windows toolchain and psmux build](phase-9-windows-toolchain-and-psmux-build.md)
**Host lane**: linux-windows
**Gate**: `agentctl check`
**Gate kind**: self-verifying
**Closes**: R24

> **Purpose**: Qualify the exact native candidate for attached-client memory behavior, capture correctness, exact identity and guarded input.

## Phase Objective

Qualify the exact native candidate for attached-client memory behavior, capture correctness, exact identity and guarded input. Source fixes and small maintained patches satisfy the common contract; a source pin or same-version banner alone proves no behavior.

This phase needs Linux and native Windows. Its receipts can come from separate runs with the same logical source/policy/prerequisite identity and separately verified lane-native artifact/toolchain identities; no other foreign hardware is required. The declared tests are executable contracts; an absent required test is unmet evidence, not existing proof. Acceptance-only test implementations belong to the prerequisite owner named in the inventory. Existing incompatible code is inventoried in the deletion ledger. No old implementation or unqualified receipt establishes this revised contract.

## Gate Integrity

| Requirement | Oracle | Observer | Mutants | Tests |
|---|---|---|---|---|
| R24 — Attached-client memory and control ordering | `tests/oracles/backend_profiles.toml` | value; observer: independent inputs and nonce-bound native observations | `M-psmux-unbounded-frame-queue`, `M-psmux-reader-blocking`, `M-psmux-oneshot-dropped` | `tests/integration/test_psmux_backpressure.py::test_blocked_output_is_bounded`, `tests/integration/test_psmux_backpressure.py::test_real_session_survives_stall`, `tests/integration/test_psmux_backpressure.py::test_control_and_oneshot_order` |
| R24 — Capture, exact-target and guarded-input qualification | `tests/oracles/backend_profiles.toml` | value; observer: independent inputs and nonce-bound native observations | `M-psmux-wide-wrap-lost`, `M-psmux-missing-pane-fallback`, `M-psmux-stale-input-accepted` | `tests/integration/test_psmux_capture.py::test_hard_soft_and_wide_wraps`, `tests/integration/test_guarded_submit.py::test_native_psmux_revision_guard`, `tests/integration/test_psmux_capture.py::test_missing_explicit_target_is_error` |
| R24 — Private coexistence and capability identity | `tests/oracles/backend_profiles.toml` | value; observer: independent inputs and nonce-bound native observations | `M-psmux-system-path-fallback`, `M-psmux-registry-version-coupled` | `tests/integration/test_psmux_isolation.py::test_system_install_and_registry_untouched`, `tests/integration/test_psmux_isolation.py::test_mixed_server_is_not_qualified` |

## Not Proven By This Gate

- A receipt's digest establishes input currency, not an independently attested historical run. Local receipt authenticity has the documented honest ceiling.
- A source rule or finite corpus does not prove arbitrary callback purity, universal termination or agent-internal readiness. Native operation and resource assumptions remain explicit.
- WSL is Linux evidence only. A Windows source revision or same-version banner is not proof that a running server or client contains the accepted fixes.

## Sprints

### Sprint 10.1: Attached-client memory and control ordering [Planned]

**Status**: Planned
**Implementation**: `src/agentctl/haskell/resources/psmux/patches/`, `tests/integration/test_psmux_backpressure.py`
**Validation tests**: `tests/integration/test_psmux_backpressure.py::test_blocked_output_is_bounded`, `tests/integration/test_psmux_backpressure.py::test_real_session_survives_stall`, `tests/integration/test_psmux_backpressure.py::test_control_and_oneshot_order`
**Mutants**: `M-psmux-unbounded-frame-queue`, `M-psmux-reader-blocking`, `M-psmux-oneshot-dropped`
**Closes**: none
**Docs to update**: `documents/architecture/multiplexer_adapter.md`, `documents/architecture/supervisor_contract.md`, `documents/engineering/testing.md`, `documents/reference/external_tool_facts.md`

#### Objective

Attached-client memory and control ordering supplies its complete owned contract through the single phase-scoped gate verdict.

#### Deliverables

Use upstream coalescing and clipboard/bell fixes as a baseline. Specify byte/frame/control budgets and explicit overload policy; adjacent-frame coalescing is not a universal bound for arbitrary Frame/NC/directive alternation. Preserve one-shot semantics and ordered control messages without blocking the socket reader into server timeouts.

#### Validation

Run real candidate clients with synthetic loopback and real private servers; block stdout beyond the server timeout while measuring Windows private committed memory. Capped vulnerable and blocking-reader controls fail for their named reasons. Resume, detach and reconnect preserve server/pane identities. Clipboard/bell use independent sinks; real clipboard tests run only in a disposable Windows session.

Required executable evidence: `tests/integration/test_psmux_backpressure.py::test_blocked_output_is_bounded`, `tests/integration/test_psmux_backpressure.py::test_real_session_survives_stall`, `tests/integration/test_psmux_backpressure.py::test_control_and_oneshot_order`. Every named mutant must die for its recorded reason in those tests; a baseline failure or unrelated exception is not a kill.

#### Remaining Work

The whole sprint.

### Sprint 10.2: Capture, exact-target and guarded-input qualification [Planned]

**Status**: Planned
**Implementation**: `src/agentctl/haskell/src/AgentCtl/Mux/Psmux.hs`, `src/agentctl/haskell/resources/psmux/patches/`, `tests/integration/test_psmux_capture.py`
**Validation tests**: `tests/integration/test_psmux_capture.py::test_hard_soft_and_wide_wraps`, `tests/integration/test_guarded_submit.py::test_native_psmux_revision_guard`, `tests/integration/test_psmux_capture.py::test_missing_explicit_target_is_error`
**Mutants**: `M-psmux-wide-wrap-lost`, `M-psmux-missing-pane-fallback`, `M-psmux-stale-input-accepted`
**Closes**: R24
**Docs to update**: `documents/architecture/multiplexer_adapter.md`, `documents/architecture/supervisor_contract.md`, `documents/engineering/testing.md`, `documents/reference/external_tool_facts.md`

#### Objective

Capture, exact-target and guarded-input qualification supplies its complete owned contract through the single phase-scoped gate verdict.

#### Deliverables

Implement the common coherent observation and conditional-submission capability in the qualified server, including exact missing-target refusal and the wide-glyph final-column parser case. No full-width-row concatenation heuristic or repeated-cursor check replaces native wrap/revision evidence.

#### Validation

Render independent UTF-8/styled/scrollback/resize corpora through real private psmux and compare complete output. Race typed user input, output and target replacement with guarded delivery; require zero bytes on stale/foreign targets and exact literal+Enter bytes on the unchanged positive control.

Required executable evidence: `tests/integration/test_psmux_capture.py::test_hard_soft_and_wide_wraps`, `tests/integration/test_guarded_submit.py::test_native_psmux_revision_guard`, `tests/integration/test_psmux_capture.py::test_missing_explicit_target_is_error`. Every named mutant must die for its recorded reason in those tests; a baseline failure or unrelated exception is not a kill.

#### Remaining Work

The whole sprint.

### Sprint 10.3: Private coexistence and capability identity [Planned]

**Status**: Planned
**Implementation**: `src/agentctl/haskell/src/AgentCtl/Mux/`, `src/agentctl/haskell/src/AgentCtl/Session/Identity.hs`, `tests/harness/tmux.py`
**Validation tests**: `tests/integration/test_psmux_isolation.py::test_system_install_and_registry_untouched`, `tests/integration/test_psmux_isolation.py::test_mixed_server_is_not_qualified`
**Mutants**: `M-psmux-system-path-fallback`, `M-psmux-registry-version-coupled`
**Closes**: none
**Docs to update**: `documents/architecture/multiplexer_adapter.md`, `documents/architecture/supervisor_contract.md`, `documents/engineering/testing.md`, `documents/reference/external_tool_facts.md`

#### Objective

Private coexistence and capability identity supplies its complete owned contract through the single phase-scoped gate verdict.

#### Deliverables

Migrate native Windows stop/owned-resource harness controls and complete their actual process/endpoint/path receipts here. Implement tests/integration/test_psmux_build.py::test_manifest_matches_running_backend for subsequent native acceptance. Resolve only agentctl's exact private executable and stable private PSMUX_DATA_DIR/config; disable unintended warm processes. Track server instance, process creation identity and actual executable provenance. System aliases and sessions coexist without sharing the registry. External adoption remains explicit and grants no unqualified input capability.

#### Validation

Start private same-name/same-pane-id controls beside a separate registry and assert exact routing. Changing a client alias changes neither existing processes nor server qualification. Never overwrite an executable in use, repoint system aliases or automatically restart/migrate sessions.

Required executable evidence: `tests/integration/test_psmux_isolation.py::test_system_install_and_registry_untouched`, `tests/integration/test_psmux_isolation.py::test_mixed_server_is_not_qualified`. Every named mutant must die for its recorded reason in those tests; a baseline failure or unrelated exception is not a kill.

#### Remaining Work

The whole sprint.

## Remaining Work

The whole phase: Sprints 10.1–10.3.

## Documentation Requirements

**Architecture docs to create/update:**

- `documents/architecture/multiplexer_adapter.md` — this phase's owned contract and links to prerequisite interfaces.
- `documents/architecture/supervisor_contract.md` — this phase's owned contract and links to prerequisite interfaces.

**Engineering docs to create/update:**

- `documents/engineering/testing.md` — doctrine, mechanisms and scope of executable evidence.

**Operations and reference docs to create/update:**

- `documents/reference/external_tool_facts.md` — preparation, qualified host observations and actionable refusals.

**Cross-references to add:**

- `DEVELOPMENT_PLAN/00-overview.md` — requirement closure and lower-phase dependencies.
- `DEVELOPMENT_PLAN/system-components.md` — stable capability/path ownership.
- `DEVELOPMENT_PLAN/legacy_tracking_for_deletion.md` — remaining incompatible implementation shapes.
