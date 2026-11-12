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

This phase needs Linux only. The declared tests are executable contracts; an absent required test is unmet evidence, not existing proof. Acceptance-only test implementations belong to the prerequisite owner named in the inventory. Existing incompatible code is inventoried in the deletion ledger. No old implementation or unqualified receipt establishes this revised contract.

## Gate Integrity

| Requirement | Oracle | Observer | Mutants | Tests |
|---|---|---|---|---|
| R18.1 — Coherent terminal observation and normalization | `tests/oracles/requirements.toml` | value; observer: independent inputs and nonce-bound native observations | `M-capture-no-join`, `M-capture-locale-decoding`, `M-snapshot-mixed-content` | `tests/integration/test_capture_real.py::test_capture_roundtrip_on_private_server`, `tests/integration/test_snapshot_identity.py::test_same_cursor_content_change_is_detected` |
| R18.1 — Per-agent classifiers and fingerprint laws | `tests/oracles/requirements.toml` | value; observer: independent inputs and nonce-bound native observations | `M-classify-dialog-loses-precedence`, `M-fingerprint-surrounding-output` | `tests/unit/test_screen_classes.py::test_fixtures_classify_as_their_directory`, `tests/unit/test_screen_classes.py::test_precedence_pairs`, `haskell:agentctl-core-test/Fingerprint/stable-under-redraw` |
| R18.2 — Concrete guarded-submission capability | `tests/oracles/requirements.toml` | value; observer: independent inputs and nonce-bound native observations | `M-submit-stale-revision`, `M-submit-active-pane-fallback`, `M-submit-split-literal-enter` | `tests/integration/test_guarded_submit.py::test_changed_input_or_output_refuses`, `tests/integration/test_guarded_submit.py::test_missing_target_never_falls_back`, `tests/integration/test_guarded_submit.py::test_literal_and_enter_are_one_submission` |

## Not Proven By This Gate

- A receipt's digest establishes input currency, not an independently attested historical run. Local receipt authenticity has the documented honest ceiling.
- A source rule or finite corpus does not prove arbitrary callback purity, universal termination or agent-internal readiness. Native operation and resource assumptions remain explicit.
- Foreign-kernel behavior is outside this phase's Linux verdict. Later native implementation extends the common contract and cannot retroactively add a foreign-hardware requirement here.
- Ordinary separate capture/send calls are not proof of server-ordered conditional submission. A missing concrete tmux implementation is unmet work, never a weaker passing mode.

## Sprints

### Sprint 7.1: Coherent terminal observation and normalization [Planned]

**Status**: Planned
**Implementation**: `src/agentctl/haskell/src/AgentCtl/Observe/`, `tests/fixtures/terminal/`, `tests/integration/test_capture_real.py`
**Validation tests**: `tests/integration/test_capture_real.py::test_capture_roundtrip_on_private_server`, `tests/integration/test_snapshot_identity.py::test_same_cursor_content_change_is_detected`
**Mutants**: `M-capture-no-join`, `M-capture-locale-decoding`, `M-snapshot-mixed-content`
**Closes**: none
**Docs to update**: `documents/architecture/supervisor_contract.md`, `documents/architecture/multiplexer_adapter.md`, `documents/engineering/testing.md`

#### Objective

Coherent terminal observation and normalization supplies its complete owned contract through the single phase-scoped gate verdict.

#### Deliverables

Read a coherent backend observation with checked instance identity, content/activity revision, joined text, styled viewport, cursor, geometry and dead status. Preserve hard line breaks and true soft wraps, including wide-character edge cases. Repeated cursor facts alone do not establish coherence.

#### Validation

Independently render bounded terminal corpora and compare raw backend capture with expected bytes/rows before testing production normalization. Change text while preserving cursor/geometry and require mismatch or rejection; resizing and scrollback cannot silently combine different observations.

Required executable evidence: `tests/integration/test_capture_real.py::test_capture_roundtrip_on_private_server`, `tests/integration/test_snapshot_identity.py::test_same_cursor_content_change_is_detected`. Every named mutant must die for its recorded reason in those tests; a baseline failure or unrelated exception is not a kill.

#### Remaining Work

The whole sprint.

### Sprint 7.2: Per-agent classifiers and fingerprint laws [Planned]

**Status**: Planned
**Implementation**: `src/agentctl/haskell/src/AgentCtl/Observe/Classify/`, `src/agentctl/haskell/src/AgentCtl/Observe/Fingerprint.hs`, `tests/fixtures/screens/`
**Validation tests**: `tests/unit/test_screen_classes.py::test_fixtures_classify_as_their_directory`, `tests/unit/test_screen_classes.py::test_precedence_pairs`, `haskell:agentctl-core-test/Fingerprint/stable-under-redraw`
**Mutants**: `M-classify-dialog-loses-precedence`, `M-fingerprint-surrounding-output`
**Closes**: R18.1
**Docs to update**: `documents/architecture/supervisor_contract.md`, `documents/architecture/multiplexer_adapter.md`, `documents/engineering/testing.md`

#### Objective

Per-agent classifiers and fingerprint laws supplies its complete owned contract through the single phase-scoped gate verdict.

#### Deliverables

Introduce tests/live/test_live_classification.py and its no-input, observed-authentication receipt contract. Parse validated observations into closed classes and typed error blocks. Typed user input, work and dialogs dominate overload text; an empty recognized prompt is necessary for readiness. Fixture provenance distinguishes documented illustrations from sanctioned captured evidence.

#### Validation

Exercise complete class/precedence tables, hostile faint-style encodings, drafts at Home and unchanged stale output. Dead state comes from backend facts, never text. Documented-only classes carry no live-confirmation claim.

Required executable evidence: `tests/unit/test_screen_classes.py::test_fixtures_classify_as_their_directory`, `tests/unit/test_screen_classes.py::test_precedence_pairs`, `haskell:agentctl-core-test/Fingerprint/stable-under-redraw`. Every named mutant must die for its recorded reason in those tests; a baseline failure or unrelated exception is not a kill.

#### Remaining Work

The whole sprint.

### Sprint 7.3: Concrete guarded-submission capability [Planned]

**Status**: Planned
**Implementation**: `src/agentctl/haskell/src/AgentCtl/Mux/Guarded.hs`, `tests/harness/guarded_input.py`
**Validation tests**: `tests/integration/test_guarded_submit.py::test_changed_input_or_output_refuses`, `tests/integration/test_guarded_submit.py::test_missing_target_never_falls_back`, `tests/integration/test_guarded_submit.py::test_literal_and_enter_are_one_submission`
**Mutants**: `M-submit-stale-revision`, `M-submit-active-pane-fallback`, `M-submit-split-literal-enter`
**Closes**: R18.2
**Docs to update**: `documents/architecture/supervisor_contract.md`, `documents/architecture/multiplexer_adapter.md`, `documents/engineering/testing.md`

#### Objective

Concrete guarded-submission capability supplies its complete owned contract through the single phase-scoped gate verdict.

#### Deliverables

Qualify a concrete server-ordered implementation for the installed APT tmux, using its supported control/command primitives where sufficient. Check target and observable input/output revisions and submit literal text+Enter as one noninterleaved operation. If those primitives cannot establish the contract, record unsupported capability and implement/prove an adequate solution before closure; repeated client-side captures are not a substitute.

#### Validation

Use barrier-controlled concurrent user input, pane output, target deletion/recreation and connection loss at every decision/delivery boundary. A changed or missing target receives no bytes and no sibling receives input. State the ordering guarantee and its observable domain explicitly: terminal evidence does not reveal an agent's latent internal state.

Required executable evidence: `tests/integration/test_guarded_submit.py::test_changed_input_or_output_refuses`, `tests/integration/test_guarded_submit.py::test_missing_target_never_falls_back`, `tests/integration/test_guarded_submit.py::test_literal_and_enter_are_one_submission`. Every named mutant must die for its recorded reason in those tests; a baseline failure or unrelated exception is not a kill.

#### Remaining Work

The whole sprint.

## Remaining Work

The whole phase: Sprints 7.1–7.3.

## Documentation Requirements

**Architecture docs to create/update:**

- `documents/architecture/supervisor_contract.md` — this phase's owned contract and links to prerequisite interfaces.
- `documents/architecture/multiplexer_adapter.md` — this phase's owned contract and links to prerequisite interfaces.

**Engineering docs to create/update:**

- `documents/engineering/testing.md` — doctrine, mechanisms and scope of executable evidence.

**Operations and reference docs to create/update:**

- None.

**Cross-references to add:**

- `DEVELOPMENT_PLAN/00-overview.md` — requirement closure and lower-phase dependencies.
- `DEVELOPMENT_PLAN/system-components.md` — stable capability/path ownership.
- `DEVELOPMENT_PLAN/legacy_tracking_for_deletion.md` — remaining incompatible implementation shapes.
