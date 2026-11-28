# Phase 7 — Pane observation and classification

**Status**: Planned
**Depends on**: [Phase 6 — Session management and adoption](phase-6-session-management-and-adoption.md)
**Host lane**: linux
**Gate**: `agentctl check`
**Gate kind**: self-verifying
**Closes**: R18.1, R18.2

> **Purpose**: The generic observation and guarded-input contract precedes recovery and every foreign backend.

## Phase Objective

The generic observation and guarded-input contract precedes recovery and every foreign backend. Debian tmux capability qualification proves its concrete implementation; unsupported or ambiguous observations never authorize input. Windows implements this contract rather than weakening or replacing it.

This phase's verdict evaluates the `linux` half ([T.V](development_plan_standards.md#tv-verdict) V8) at stage 2 ([T.W](development_plan_standards.md#tw-staged-enforcement)) and needs no logged-in agent. Every cited artifact is owned within closure(7) ([§ A](development_plan_standards.md#a-well-ordered-constructive-narrative)), a planned absence is unmet work of this phase ([T.F](development_plan_standards.md#tf-shared-and-owned-failures)), and present incompatible code is a deletion-ledger row of its owner. The logged-in live screen classes are owed to the `linux-live` half of [Linux live and clean acceptance](phase-12-linux-live-and-clean-acceptance.md), and each foreign backend implements this contract in its own modules; neither is a gap in this verdict. Its Haskell modules and native tests form this phase's own build component, discovered through the `cabal.project` package glob of [Python bootstrap and handoff](phase-2-python-bootstrap-and-handoff.md); it edits no earlier component ([§ A](development_plan_standards.md#a-well-ordered-constructive-narrative) A1, A2).

## Gate Integrity

| Requirement | Oracle | Observer | Mutants | Tests |
|---|---|---|---|---|
| R18.1 — Coherent terminal observation and normalization | `tests/oracles/requirements.toml` | value: independent normalization idempotence expectations; observer: nonce-bound private-server capture observations of cursor, content and wrap changes | `M-capture-ignore-cursor-change`, `M-capture-normalise-not-idempotent` | `tests/integration/test_capture_observation.py::test_hard_soft_and_wide_wraps`, `tests/integration/test_capture_observation.py::test_same_cursor_content_change_is_detected`, `tests/integration/test_capture_real.py::test_capture_retries_changed_cursor`, `haskell:agentctl-core-test/Normalize/idempotent` |
| R18.1 — Per-agent classifiers and fingerprint laws | `tests/oracles/requirements.toml` | value: independent fixture-class, precedence, fingerprint, dead-pane and placeholder expectations; observer: nonce-bound status-screen classification with the session's own agent; owed: linux-live-and-clean-acceptance | `M-capture-fingerprint-constant`, `M-capture-fingerprint-includes-redraw`, `M-classify-auth-error-as-overload`, `M-classify-context-as-overload`, `M-classify-dead-pane-by-text`, `M-classify-ignore-partial-input`, `M-classify-overload-over-approval`, `M-classify-overload-over-working`, `M-classify-placeholder-as-partial`, `M-classify-placeholder-ignores-cursor`, `M-classify-placeholder-ignores-style`, `M-classify-status-other-agent`, `M-classify-usage-limit-as-overload` | `tests/unit/test_screen_classes.py::test_fixtures_classify_as_their_directory`, `tests/unit/test_screen_classes.py::test_precedence_pairs`, `tests/e2e/test_status_screen.py::test_screen_column_uses_the_agents_classifier`, `haskell:agentctl-core-test/Fingerprint/stable-under-redraw`, `haskell:agentctl-core-test/Fingerprint/different-error-differs`, `haskell:agentctl-core-test/Classify/dead-pane-is-exited`, `haskell:agentctl-core-test/Classify/placeholder-needs-visual-evidence` |
| R18.2 — Concrete guarded-submission capability | `tests/oracles/requirements.toml` | real: server-ordered conditional submission on the installed tmux; observer: nonce-bound barrier observations of pane input, output and target identity | none — planned mutants are named in the Deliverables of this row's sprint until their corpus rows land | `tests/integration/test_guarded_submit.py::test_changed_input_or_output_refuses`, `tests/integration/test_guarded_submit.py::test_missing_target_never_falls_back`, `tests/integration/test_guarded_submit.py::test_literal_and_enter_are_one_submission` |

## Not Proven By This Gate

- Limits: [T.C](development_plan_standards.md#tc-ceiling); none is a closure condition.
- Terminal observation proves rendered screen state only, never an agent's latent internal state ([T.C](development_plan_standards.md#tc-ceiling) C5).

## Sprints

### Sprint 7.1: Coherent terminal observation and normalization [Planned]

**Status**: Planned
**Implementation**: `src/agentctl/haskell/src/AgentCtl/Observe/Capture.hs`, `src/agentctl/haskell/src/AgentCtl/Observe/Normalize.hs`, `tests/fixtures/terminal/`, `tests/integration/test_capture_observation.py`
**Validation tests**: `tests/integration/test_capture_observation.py::test_hard_soft_and_wide_wraps`, `tests/integration/test_capture_observation.py::test_same_cursor_content_change_is_detected`, `tests/integration/test_capture_real.py::test_capture_retries_changed_cursor`, `haskell:agentctl-core-test/Normalize/idempotent`
**Mutants**: `M-capture-ignore-cursor-change`, `M-capture-normalise-not-idempotent`
**Closes**: none
**Docs to update**: migrates `documents/architecture/multiplexer_adapter.md` (owner [Debian tmux and multiplexer](phase-4-debian-tmux-and-multiplexer.md)), migrates `documents/engineering/testing.md` (owner [Python discipline and gate integrity](phase-1-python-discipline-and-gate-integrity.md))

#### Objective

Coherent terminal observation and normalization supplies its complete owned contract through the single phase-scoped gate verdict.

#### Deliverables

Read a coherent backend observation with checked instance identity, content/activity revision, joined text, styled viewport, cursor, geometry and dead status. Preserve hard line breaks and true soft wraps, including wide-character edge cases. Repeated cursor facts alone do not establish coherence. This sprint's capture controls live in `tests/integration/test_capture_observation.py`; it consumes `tests/integration/test_capture_real.py`, whose changed-cursor case kills the capture mutant declared here. The backend join and locale-decoding mutants target earlier-owned modules and are declared by [Debian tmux and multiplexer](phase-4-debian-tmux-and-multiplexer.md) and [Haskell runtime and platform policy](phase-3-haskell-runtime-and-platform-policy.md) ([T.M](development_plan_standards.md#tm-adequacy) M1). The planned mutant `M-snapshot-mixed-content` is named here until its corpus row lands ([§ C](development_plan_standards.md#c-honest-completion-tracking)).

`Observe/Capture.capture` runs over the effect records of D-173, and the screen-grid model (soft wrap, wide glyphs and dead status) attaches through the tmux model's pane-program hook without editing it (D-177).

#### Validation

Independently render bounded terminal corpora and compare raw backend capture with expected bytes/rows before testing production normalization. Change text while preserving cursor/geometry and require mismatch or rejection; resizing and scrollback cannot silently combine different observations.

Every node in **Validation tests** passes in a verified run and every named mutant is killed per [T.K](development_plan_standards.md#tk-kill) at stage 2.

#### Remaining Work

The whole sprint.

### Sprint 7.2: Per-agent classifiers and fingerprint laws [Planned]

**Status**: Planned
**Implementation**: `src/agentctl/haskell/src/AgentCtl/Observe/Classify.hs`, `src/agentctl/haskell/src/AgentCtl/Observe/Classify/`, `src/agentctl/haskell/src/AgentCtl/Observe/Fingerprint.hs`, `tests/fixtures/screens/`, `tests/harness/screens.py`, `tests/live/test_live_classification.py`
**Validation tests**: `tests/unit/test_screen_classes.py::test_fixtures_classify_as_their_directory`, `tests/unit/test_screen_classes.py::test_precedence_pairs`, `haskell:agentctl-core-test/Fingerprint/stable-under-redraw`, `tests/e2e/test_status_screen.py::test_screen_column_uses_the_agents_classifier`, `tests/governance/test_screen_fixtures.py::test_every_fixture_has_provenance`, `haskell:agentctl-core-test/Fingerprint/different-error-differs`, `haskell:agentctl-core-test/Classify/dead-pane-is-exited`, `haskell:agentctl-core-test/Classify/placeholder-needs-visual-evidence`, `tests/live/test_live_classification.py::test_live_classification_refuses_without_login`
**Mutants**: `M-capture-fingerprint-constant`, `M-capture-fingerprint-includes-redraw`, `M-classify-auth-error-as-overload`, `M-classify-context-as-overload`, `M-classify-dead-pane-by-text`, `M-classify-ignore-partial-input`, `M-classify-overload-over-approval`, `M-classify-overload-over-working`, `M-classify-placeholder-as-partial`, `M-classify-placeholder-ignores-cursor`, `M-classify-placeholder-ignores-style`, `M-classify-status-other-agent`, `M-classify-usage-limit-as-overload`
**Closes**: R18.1
**Docs to update**: migrates `documents/architecture/multiplexer_adapter.md` (owner [Debian tmux and multiplexer](phase-4-debian-tmux-and-multiplexer.md)), migrates `documents/engineering/testing.md` (owner [Python discipline and gate integrity](phase-1-python-discipline-and-gate-integrity.md))

#### Objective

Per-agent classifiers and fingerprint laws supplies its complete owned contract through the single phase-scoped gate verdict.

#### Deliverables

This sprint owns the no-input live classification observer `tests/live/test_live_classification.py` and cites its portable refusal node; its logged-in screen-class node, declared to the `linux-live` half ([T.X](development_plan_standards.md#tx-terms)), is the `linux-live` evidence of [Linux live and clean acceptance](phase-12-linux-live-and-clean-acceptance.md). Parse validated observations into closed classes and typed error blocks. Typed user input, work and dialogs dominate overload text; an empty recognized prompt is necessary for readiness. Fixture provenance distinguishes documented illustrations from sanctioned captured evidence. Planned mutants, named here until their corpus rows land ([§ C](development_plan_standards.md#c-honest-completion-tracking)): `M-classify-dialog-loses-precedence` and `M-fingerprint-surrounding-output`.

#### Validation

Exercise complete class/precedence tables, hostile faint-style encodings, drafts at Home and unchanged stale output. Dead state comes from backend facts, never text. Documented-only classes carry no live-confirmation claim.

Every node in **Validation tests** passes in a verified run and every named mutant is killed per [T.K](development_plan_standards.md#tk-kill) at stage 2.

#### Remaining Work

The whole sprint.

### Sprint 7.3: Concrete guarded-submission capability [Planned]

**Status**: Planned
**Implementation**: `src/agentctl/haskell/src/AgentCtl/Mux/Guarded.hs`, `tests/harness/guarded_input.py`, `tests/integration/test_guarded_submit.py`, `tests/oracles/recovery_transitions.toml`
**Validation tests**: `tests/integration/test_guarded_submit.py::test_changed_input_or_output_refuses`, `tests/integration/test_guarded_submit.py::test_missing_target_never_falls_back`, `tests/integration/test_guarded_submit.py::test_literal_and_enter_are_one_submission`
**Mutants**: none — planned mutants are named in this sprint's Deliverables until their corpus rows land
**Closes**: R18.2
**Docs to update**: migrates `documents/architecture/multiplexer_adapter.md` (owner [Debian tmux and multiplexer](phase-4-debian-tmux-and-multiplexer.md)), migrates `documents/engineering/testing.md` (owner [Python discipline and gate integrity](phase-1-python-discipline-and-gate-integrity.md))

#### Objective

Concrete guarded-submission capability supplies its complete owned contract through the single phase-scoped gate verdict.

#### Deliverables

Qualify a concrete server-ordered implementation for the installed APT tmux, using its supported control/command primitives where sufficient. Check target and observable input/output revisions and submit literal text+Enter as one noninterleaved operation. If those primitives cannot establish the contract, record unsupported capability and implement/prove an adequate solution before closure; repeated client-side captures are not a substitute. `tests/integration/test_guarded_submit.py` holds only these generic guarded-input controls; supervisor delivery and backend guard nodes live in modules that their own phases own ([§ A](development_plan_standards.md#a-well-ordered-constructive-narrative) A3). Planned mutants, named here until their corpus rows land ([§ C](development_plan_standards.md#c-honest-completion-tracking)): `M-submit-active-pane-fallback`, `M-submit-split-literal-enter` and `M-submit-stale-revision`.

#### Validation

Use barrier-controlled concurrent user input, pane output, target deletion/recreation and connection loss at every decision/delivery boundary. A changed or missing target receives no bytes and no sibling receives input. State the ordering guarantee and its observable domain explicitly: terminal evidence does not reveal an agent's latent internal state. Ordinary separate capture and send calls are not proof of server-ordered conditional submission, and a missing concrete tmux implementation is unmet work, never a weaker passing mode.

Every node in **Validation tests** passes in a verified run and every named mutant is killed per [T.K](development_plan_standards.md#tk-kill) at stage 2.

#### Remaining Work

The whole sprint.

## Remaining Work

The whole phase: Sprints 7.1–7.3.

## Documentation Requirements

**Architecture docs to create/update:**

- migrates `documents/architecture/multiplexer_adapter.md` (owner [Debian tmux and multiplexer](phase-4-debian-tmux-and-multiplexer.md)) — this phase's owned contract and links to prerequisite interfaces.

**Engineering docs to create/update:**

- migrates `documents/engineering/testing.md` (owner [Python discipline and gate integrity](phase-1-python-discipline-and-gate-integrity.md)) — doctrine, mechanisms and scope of executable evidence.

**Operations and reference docs to create/update:**

- None.

**Cross-references to add:**

- `DEVELOPMENT_PLAN/00-overview.md` — requirement closure and lower-phase dependencies.
- `DEVELOPMENT_PLAN/system-components.md` — stable capability/path ownership.
- `DEVELOPMENT_PLAN/legacy_tracking_for_deletion.md` — remaining incompatible implementation shapes.
