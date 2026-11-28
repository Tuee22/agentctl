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

This phase's verdict evaluates the `linux` and `windows` halves ([T.V](development_plan_standards.md#tv-verdict) V8) at stage 2 ([T.W](development_plan_standards.md#tw-staged-enforcement)); a native Windows run reads the `linux` half from the latest stored guest receipt with equal logical and prerequisite identities. Every cited artifact is owned within closure(10) ([§ A](development_plan_standards.md#a-well-ordered-constructive-narrative)), a planned absence is unmet work of this phase ([T.F](development_plan_standards.md#tf-shared-and-owned-failures)), and present incompatible code is a deletion-ledger row of its owner. The psmux backend implements the common multiplexer, observation and guarded-input interfaces in its own modules and tests instead of editing them ([§ A](development_plan_standards.md#a-well-ordered-constructive-narrative) A1), and this phase owes no confirmation to a later phase. Its Haskell modules and native tests form this phase's own build component, discovered through the `cabal.project` package glob of [Python bootstrap and handoff](phase-2-python-bootstrap-and-handoff.md); it edits no earlier component ([§ A](development_plan_standards.md#a-well-ordered-constructive-narrative) A1, A2).

## Gate Integrity

| Requirement | Oracle | Observer | Mutants | Tests |
|---|---|---|---|---|
| R24 — Attached-client memory and control ordering | `tests/oracles/backend_profiles.toml` | real: native client memory, blocked-reader and reconnect behavior on the named host; observer: nonce-bound frame, control-event and one-shot ordering observations | none — planned mutants are named in the Deliverables of this row's sprint until their corpus rows land | `tests/integration/test_psmux_backpressure.py::test_blocked_output_is_bounded`, `tests/integration/test_psmux_backpressure.py::test_real_session_survives_stall`, `tests/integration/test_psmux_backpressure.py::test_control_and_oneshot_order` |
| R24 — Exact psmux target and executable rendering | `tests/oracles/mux_commands.toml` | value: independent psmux command-rendering expectations | `M-mux-remain-session-unqualified`, `M-mux-render-psmux-alias` | `tests/unit/test_mux_values.py::test_render_oracle` |
| R24 — Capture, exact-target and guarded-input qualification | `tests/oracles/backend_profiles.toml` | real: native capture, missing-target refusal and conditional submission on the named host; observer: nonce-bound wrap, target-replacement and typed-input race observations | none — planned mutants are named in the Deliverables of this row's sprint until their corpus rows land | `tests/integration/test_psmux_capture.py::test_hard_soft_and_wide_wraps`, `tests/integration/test_psmux_guarded_submit.py::test_native_psmux_revision_guard`, `tests/integration/test_psmux_capture.py::test_missing_explicit_target_is_error` |
| R24 — Private coexistence and capability identity | `tests/oracles/backend_profiles.toml` | real: private executable, registry, owned-resource cleanup and running-artifact identity on the named host; observer: nonce-bound routing of same-name sessions across a separate registry | none — planned mutants are named in the Deliverables of this row's sprint until their corpus rows land | `tests/integration/test_psmux_isolation.py::test_system_install_and_registry_untouched`, `tests/integration/test_psmux_isolation.py::test_mixed_server_is_not_qualified`, `tests/integration/test_psmux_isolation.py::test_manifest_matches_running_backend`, `tests/integration/test_owned_resources.py::test_native_windows_ownership_and_cleanup` |

## Not Proven By This Gate

- Limits: [T.C](development_plan_standards.md#tc-ceiling); none is a closure condition.
- A qualified candidate proves the exact client and server artifacts its run observed, never a differently built or later upgraded psmux.

## Sprints

### Sprint 10.1: Attached-client memory and control ordering [Planned]

**Status**: Planned
**Implementation**: `src/agentctl/haskell/resources/psmux/patches/`, `src/agentctl/haskell/src/AgentCtl/Mux/Psmux.hs`, `tests/integration/test_psmux_backpressure.py`, `tests/unit/test_psmux_render.py`
**Validation tests**: `tests/integration/test_psmux_backpressure.py::test_blocked_output_is_bounded`, `tests/integration/test_psmux_backpressure.py::test_real_session_survives_stall`, `tests/integration/test_psmux_backpressure.py::test_control_and_oneshot_order`, `tests/unit/test_mux_values.py::test_render_oracle`, `tests/unit/test_psmux_render.py::test_psmux_render_oracle`
**Mutants**: `M-mux-remain-session-unqualified`, `M-mux-render-psmux-alias`
**Closes**: none
**Docs to update**: migrates `documents/architecture/multiplexer_adapter.md` (owner [Debian tmux and multiplexer](phase-4-debian-tmux-and-multiplexer.md)), migrates `documents/architecture/supervisor_contract.md` (owner [Recovery and supervisor](phase-8-recovery-and-supervisor.md)) except its D-153 frozen spans, migrates `documents/engineering/testing.md` (owner [Python discipline and gate integrity](phase-1-python-discipline-and-gate-integrity.md)), migrates `documents/reference/external_tool_facts.md` (owner [Python discipline and gate integrity](phase-1-python-discipline-and-gate-integrity.md))

#### Objective

Attached-client memory and control ordering supplies its complete owned contract through the single phase-scoped gate verdict.

#### Deliverables

Use upstream coalescing and clipboard/bell fixes as a baseline. Specify byte/frame/control budgets and explicit overload policy; adjacent-frame coalescing is not a universal bound for arbitrary Frame/NC/directive alternation. Preserve one-shot semantics and ordered control messages without blocking the socket reader into server timeouts. The present adapter renders the exact `=session:pane` target and the private `psmux.exe` executable that the independent command oracle expects. Planned mutants, named here until their corpus rows land ([§ C](development_plan_standards.md#c-honest-completion-tracking)): `M-psmux-oneshot-dropped`, `M-psmux-reader-blocking` and `M-psmux-unbounded-frame-queue`. The psmux render rows of `tests/unit/test_mux_values.py::test_render_oracle` arrive in `tests/unit/test_psmux_render.py::test_psmux_render_oracle` in ascending order: [Haskell runtime and platform policy](phase-3-haskell-runtime-and-platform-policy.md) moves the node into a module of [Debian tmux and multiplexer](phase-4-debian-tmux-and-multiplexer.md) (D-155), which then splits it by backend in that module (D-152). The new node takes the killer entries of `M-mux-remain-session-unqualified` and `M-mux-render-psmux-alias` through killer-relocation records ([T.G](development_plan_standards.md#tg-governed-changes)), and each of those changes edits this sprint's citations and its Gate Integrity row in the same change.

#### Validation

Run real candidate clients with synthetic loopback and real private servers; block stdout beyond the server timeout while measuring Windows private committed memory. Capped vulnerable and blocking-reader controls fail for their named reasons. Resume, detach and reconnect preserve server/pane identities. Clipboard and bell one-shots are observed only through synthetic test clients, never a real client or the OS clipboard; a real candidate client runs only in a terminal the test created and attaches only to run-owned servers whose panes emit no OSC 52 or bell sequence, which a synthetic observer checks before it attaches ([§ Q](development_plan_standards.md#q-containment-and-user-state-protection), D-172). The psmux model, with its restart and pane-id semantics, lives in this phase's own module behind the backend interface and replays its transcript rows on private psmux servers from the harness-provisioned candidate (D-177). Rendering controls compare every psmux command with `tests/oracles/mux_commands.toml` on every half.

Every node in **Validation tests** passes in a verified run and every named mutant is killed per [T.K](development_plan_standards.md#tk-kill) at stage 2.

#### Remaining Work

The whole sprint.

### Sprint 10.2: Capture, exact-target and guarded-input qualification [Planned]

**Status**: Planned
**Implementation**: `src/agentctl/haskell/src/AgentCtl/Mux/Psmux.hs`, `src/agentctl/haskell/resources/psmux/patches/`, `tests/integration/test_psmux_capture.py`, `tests/integration/test_psmux_guarded_submit.py`
**Validation tests**: `tests/integration/test_psmux_capture.py::test_hard_soft_and_wide_wraps`, `tests/integration/test_psmux_guarded_submit.py::test_native_psmux_revision_guard`, `tests/integration/test_psmux_capture.py::test_missing_explicit_target_is_error`
**Mutants**: none — planned mutants are named in this sprint's Deliverables until their corpus rows land
**Closes**: R24
**Docs to update**: migrates `documents/architecture/multiplexer_adapter.md` (owner [Debian tmux and multiplexer](phase-4-debian-tmux-and-multiplexer.md)), migrates `documents/architecture/supervisor_contract.md` (owner [Recovery and supervisor](phase-8-recovery-and-supervisor.md)) except its D-153 frozen spans, migrates `documents/engineering/testing.md` (owner [Python discipline and gate integrity](phase-1-python-discipline-and-gate-integrity.md)), migrates `documents/reference/external_tool_facts.md` (owner [Python discipline and gate integrity](phase-1-python-discipline-and-gate-integrity.md))

#### Objective

Capture, exact-target and guarded-input qualification supplies its complete owned contract through the single phase-scoped gate verdict.

#### Deliverables

Implement the common coherent observation and conditional-submission capability in the qualified server, including exact missing-target refusal and the wide-glyph final-column parser case. No full-width-row concatenation heuristic or repeated-cursor check replaces native wrap/revision evidence. The psmux side of the guarded-input interface of [Pane observation and classification](phase-7-pane-observation-and-classification.md) lives in this phase's modules, and `tests/integration/test_psmux_guarded_submit.py` holds its native revision guard. Planned mutants, named here until their corpus rows land ([§ C](development_plan_standards.md#c-honest-completion-tracking)): `M-psmux-missing-pane-fallback`, `M-psmux-stale-input-accepted` and `M-psmux-wide-wrap-lost`.

#### Validation

Render independent UTF-8/styled/scrollback/resize corpora through real private psmux and compare complete output. Race typed user input, output and target replacement with guarded delivery; require zero bytes on stale/foreign targets and exact literal+Enter bytes on the unchanged positive control.

Every node in **Validation tests** passes in a verified run and every named mutant is killed per [T.K](development_plan_standards.md#tk-kill) at stage 2.

#### Remaining Work

The whole sprint.

### Sprint 10.3: Private coexistence and capability identity [Planned]

**Status**: Planned
**Implementation**: `src/agentctl/haskell/src/AgentCtl/Mux/Psmux.hs`, `tests/harness/psmux.py`, `tests/integration/test_psmux_isolation.py`, `tests/integration/test_owned_resources.py`, `src/agentctl/haskell/product-windows/`
**Validation tests**: `tests/integration/test_psmux_isolation.py::test_system_install_and_registry_untouched`, `tests/integration/test_psmux_isolation.py::test_mixed_server_is_not_qualified`, `tests/integration/test_psmux_isolation.py::test_manifest_matches_running_backend`, `tests/integration/test_owned_resources.py::test_native_windows_ownership_and_cleanup`
**Mutants**: none — planned mutants are named in this sprint's Deliverables until their corpus rows land
**Closes**: none
**Docs to update**: migrates `documents/architecture/multiplexer_adapter.md` (owner [Debian tmux and multiplexer](phase-4-debian-tmux-and-multiplexer.md)), migrates `documents/architecture/supervisor_contract.md` (owner [Recovery and supervisor](phase-8-recovery-and-supervisor.md)) except its D-153 frozen spans, migrates `documents/engineering/testing.md` (owner [Python discipline and gate integrity](phase-1-python-discipline-and-gate-integrity.md)), migrates `documents/reference/external_tool_facts.md` (owner [Python discipline and gate integrity](phase-1-python-discipline-and-gate-integrity.md))

#### Objective

Private coexistence and capability identity supplies its complete owned contract through the single phase-scoped gate verdict.

#### Deliverables

Complete native Windows stop and owned-resource controls with actual process, endpoint and path receipts in `tests/integration/test_owned_resources.py` and the private psmux harness `tests/harness/psmux.py`. `tests/harness/psmux.py` receives the psmux arms of `tests/harness/tmux.py` and the Windows branches of the `tests/integration/test_mux_real.py` nodes, which [Debian tmux and multiplexer](phase-4-debian-tmux-and-multiplexer.md) moves there while it is not Done, so the native Windows outcomes and kills of the nodes that reach them are this phase's ([T.F](development_plan_standards.md#tf-shared-and-owned-failures), D-167). This sprint migrates the Windows parts that its deletion-ledger rows locate in `tests/harness/supervisor_signals.py` (owner [Recovery and supervisor](phase-8-recovery-and-supervisor.md)) and `tests/integration/test_guard.py` (owner [Governance and phase evidence](phase-0-governance-and-phase-evidence.md)) into this phase's host-declared modules, only as [§ A](development_plan_standards.md#a-well-ordered-constructive-narrative) A1 permits, and never edits `src/agentctl/haskell/src/AgentCtl/Mux.hs` (D-152). It consumes `src/agentctl/haskell/src/AgentCtl/Mux/Types.hs`, `src/agentctl/haskell/src/AgentCtl/Session/Identity.hs` and the version-banner arm of `src/agentctl/haskell/src/AgentCtl/Mux/Windows.hs` (owner [Windows toolchain and psmux build](phase-9-windows-toolchain-and-psmux-build.md)) without editing them: a released banner grants no capability here, and this phase qualifies the running client and server artifacts in its own modules, so `M-mux-version-banner-unchecked` stays with that owner (D-152). `src/agentctl/haskell/product-windows/` is the Windows product component, whose executable links the packages owned within this phase's closure, the psmux backend included, and is the installed executable on Windows hosts (D-163). Implement `tests/integration/test_psmux_isolation.py::test_manifest_matches_running_backend`, which [Windows application acceptance](phase-11-windows-application-acceptance.md) consumes with the owned-resource node. Resolve only agentctl's exact private executable and stable private PSMUX_DATA_DIR/config; disable unintended warm processes. Track server instance, process creation identity and actual executable provenance. System aliases and sessions coexist without sharing the registry. External adoption remains explicit and grants no unqualified input capability. Planned mutants, named here until their corpus rows land ([§ C](development_plan_standards.md#c-honest-completion-tracking)): `M-psmux-registry-version-coupled` and `M-psmux-system-path-fallback`.

Coexistence is proven against a second run-owned registry, never by reading the user's sessions (D-172).

#### Validation

Start private same-name/same-pane-id controls beside a separate registry and assert exact routing. Changing a client alias changes neither existing processes nor server qualification. The running server and client executables match the build manifest of the qualified candidate. Never overwrite an executable in use, repoint system aliases or automatically restart/migrate sessions.

Every node in **Validation tests** passes in a verified run and every named mutant is killed per [T.K](development_plan_standards.md#tk-kill) at stage 2.

#### Remaining Work

The whole sprint.

## Remaining Work

The whole phase: Sprints 10.1–10.3.

## Documentation Requirements

**Architecture docs to create/update:**

- migrates `documents/architecture/multiplexer_adapter.md` (owner [Debian tmux and multiplexer](phase-4-debian-tmux-and-multiplexer.md)) — this phase's owned contract and links to prerequisite interfaces.
- migrates `documents/architecture/supervisor_contract.md` (owner [Recovery and supervisor](phase-8-recovery-and-supervisor.md)) except its D-153 frozen spans — this phase's owned contract and links to prerequisite interfaces.

**Engineering docs to create/update:**

- migrates `documents/engineering/testing.md` (owner [Python discipline and gate integrity](phase-1-python-discipline-and-gate-integrity.md)) — doctrine, mechanisms and scope of executable evidence.

**Operations and reference docs to create/update:**

- migrates `documents/reference/external_tool_facts.md` (owner [Python discipline and gate integrity](phase-1-python-discipline-and-gate-integrity.md)) — preparation, qualified host observations and actionable refusals.

**Cross-references to add:**

- `DEVELOPMENT_PLAN/00-overview.md` — requirement closure and lower-phase dependencies.
- `DEVELOPMENT_PLAN/system-components.md` — stable capability/path ownership.
- `DEVELOPMENT_PLAN/legacy_tracking_for_deletion.md` — remaining incompatible implementation shapes.
