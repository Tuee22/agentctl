# Phase 1 — Python discipline and gate integrity

**Status**: Planned
**Depends on**: [Phase 0 — Governance and phase evidence](phase-0-governance-and-phase-evidence.md)
**Host lane**: linux
**Gate**: `agentctl check`
**Gate kind**: self-verifying
**Closes**: R20, R20.2, R21, R29.1

> **Purpose**: Project-owned strict Python doctrine, local executable enforcement, typed native boundaries, the stage-2 evidence checkers and migration of existing Governance package, gate and test code.

## Phase Objective

Project-owned strict Python doctrine, local executable enforcement, typed native boundaries, the stage-2 evidence checkers and migration of existing Governance package, gate and test code. This phase removes incompatible implementation shapes rather than granting a legacy suppression or adding a second checker. Its checkers enforce the stage-2 clauses of [§ T](development_plan_standards.md#t-unspoofable-evidence-and-phase-verdicts): E3 oracle loading, E4 subject substitution, K2–K6 kill provenance, S10 through the closure-set records of [T.G](development_plan_standards.md#tg-governed-changes), S11 laundered attribution, M4 generated decision mutants and V6 closure-scoped coverage. Closure-scoped coverage extends the stage-1 coverage scoping of [Governance and phase evidence](phase-0-governance-and-phase-evidence.md) to every stage-2 verdict, and M4 runs report-only until the Sprint 1.3 change that enforces it, which lands before this phase closes ([T.W](development_plan_standards.md#tw-staged-enforcement)).

This phase's verdict evaluates the `linux` half ([T.V](development_plan_standards.md#tv-verdict) V8) at stage 2. Every verdict whose closure contains this phase is judged at stage 2 over its whole closure, earlier-owned files included, while [Governance and phase evidence](phase-0-governance-and-phase-evidence.md) keeps printing `stage=1` ([T.W](development_plan_standards.md#tw-staged-enforcement)); a stage-2 finding in a Governance-owned file is owned by this phase and its later consumers, which repair it under [§ A](development_plan_standards.md#a-well-ordered-constructive-narrative) A1. Every cited artifact is owned within closure(1), a planned absence is unmet work of this phase ([T.F](development_plan_standards.md#tf-shared-and-owned-failures)), and present incompatible code is a deletion-ledger row of its owner. No confirmation is owed to a later phase.

## Gate Integrity

| Requirement | Oracle | Observer | Mutants | Tests |
|---|---|---|---|---|
| R21 — Typed immutable Python migration | `tests/oracles/python_discipline.toml` | value: independent expected values for the owned pure contract; observer: independent inputs and nonce-bound native observations | none — planned mutants are named in the Deliverables of this row's sprint until their corpus rows land | `tests/governance/test_python_discipline.py::test_boundary_narrowing_controls`, `tests/governance/test_python_discipline.py::test_immutable_records_and_bindings`, `tests/integration/test_python_boundaries.py::test_native_declarations_conform` |
| R21 — Pure kernels and totality | `tests/oracles/python_discipline.toml` | value: independent expected values for the owned pure contract; observer: independent inputs and nonce-bound native observations | none — planned mutants are named in the Deliverables of this row's sprint until their corpus rows land | `tests/governance/test_python_discipline.py::test_core_edge_census`, `tests/governance/test_python_discipline.py::test_partial_operations_and_closed_matches`, `tests/integration/test_python_laws.py::test_repeatability_and_argument_preservation` |
| R20 — Gate, harness and native evidence migration | `tests/oracles/python_discipline.toml` | value: independent suppression-ban fixture cases; real: owned-leak containment in a real gate child | none — planned mutants are named in the Deliverables of this row's sprint until their corpus rows land | `tests/governance/test_python_discipline.py::test_migrated_sources_carry_no_suppression`, `tests/governance/test_python_discipline.py::test_complete_first_party_census`, `tests/integration/test_owned_cleanup.py::test_cleanup_preserves_primary_failure`, `tests/integration/test_owned_cleanup.py::test_owned_leak_fails_its_verdict` |
| R20 — Stage-2 evidence checkers | `tests/oracles/python_discipline.toml` | value: independent accepting and refusing fixture cases for each stage-2 clause | none — planned mutants enter the Remaining Work table when this phase activates | `tests/governance/test_stage2_checkers.py::test_oracle_loading_required`, `tests/governance/test_stage2_checkers.py::test_subject_substitution_refused`, `tests/governance/test_stage2_checkers.py::test_kill_provenance_conditions`, `tests/governance/test_stage2_checkers.py::test_closure_set_shrink_refused`, `tests/governance/test_stage2_checkers.py::test_generated_decision_mutants`, `tests/governance/test_stage2_checkers.py::test_coverage_scoped_to_closure`, `tests/governance/test_stage2_checkers.py::test_stage2_governed_records`, `tests/governance/test_stage2_checkers.py::test_platform_reads_only_in_dispatcher`, `tests/governance/test_stage2_checkers.py::test_laundered_attribution_refused`, `tests/governance/test_stage2_checkers.py::test_stage2_finding_owned_by_later_phase` |
| R20.2 — Haskell and C closure evidence form | `tests/oracles/python_discipline.toml` | value: independent Haskell and C fixture cases with and without a named-reason kill and native accepting and refusing twins | none — planned mutants enter the Remaining Work table when this phase activates | `tests/governance/test_stage2_checkers.py::test_native_twin_evidence_form` |
| R29.1 — Admissible environment models | `tests/oracles/python_discipline.toml` | value: independent registry, independence, conformance-gating and seed cases | none — corpus rows land with their Remaining Work rows | `tests/governance/test_stage2_checkers.py::test_unregistered_model_refused`, `tests/governance/test_stage2_checkers.py::test_model_kill_requires_conformance` |

## Not Proven By This Gate

- Limits: [T.C](development_plan_standards.md#tc-ceiling); none is a closure condition.
- A source rule or finite corpus does not prove arbitrary callback purity or universal termination ([T.C](development_plan_standards.md#tc-ceiling) C5).

## Sprints

### Sprint 1.1: Typed immutable Python migration [Planned]

**Status**: Planned
**Implementation**: `src/agentctl/process.py`, `stubs/`, `tests/governance/test_python_discipline.py`, `tests/integration/test_python_boundaries.py`
**Validation tests**: `tests/governance/test_python_discipline.py::test_boundary_narrowing_controls`, `tests/governance/test_python_discipline.py::test_immutable_records_and_bindings`, `tests/integration/test_python_boundaries.py::test_native_declarations_conform`
**Mutants**: none — planned mutants are named in this sprint's Deliverables until their corpus rows land
**Closes**: R21
**Docs to update**: `documents/engineering/code_standards.md`, `documents/engineering/testing.md`

#### Objective

Typed immutable Python migration supplies its complete owned contract through the single phase-scoped gate verdict.

#### Deliverables

Migrate isinstance/issubclass/type comparisons and object annotations to structural boundary parsers with precise native decoder unions. Preserve local Ok/Err; use final frozen slotted keyword-only records, module-level behavior, recursively immutable owned values and single assignment. Replace mutable Click subclasses and reflective framework access with narrow typed adapters. This sprint migrates `tests/oracles/lint_config.toml` and `tests/oracles/forbidden_surfaces.toml` (owner [Governance and phase evidence](phase-0-governance-and-phase-evidence.md)), which P0-24 re-owns there, only by appended rows that T.I projects to it, and each appended rule row declares this phase as its introducing phase through the rule-provenance interface of Governance and phase evidence (D-131), so its findings never enter the Governance verdict ([T.F](development_plan_standards.md#tf-shared-and-owned-failures)). It migrates the Governance-owned locations of its deletion-ledger rows (owner [Governance and phase evidence](phase-0-governance-and-phase-evidence.md)) only as [§ A](development_plan_standards.md#a-well-ordered-constructive-narrative) A1 permits; each later-owned module is migrated by its owner under that owner's ledger rows, so this phase never waits on it ([T.F](development_plan_standards.md#tf-shared-and-owned-failures)). Planned mutants, named here until their corpus rows land ([§ C](development_plan_standards.md#c-honest-completion-tracking)): `M-python-container-mutation`, `M-python-object-annotation`, `M-python-rebinding` and `M-python-runtime-type-test`.

#### Validation

Accept correct structural parsers, finite immutable records and native borrowed capabilities. Refuse each forbidden spelling through direct and aliased forms. Verify native decoder/stub names, signatures and supported return shapes; bool/int overlap and malformed input yield typed reasons instead of a traceback.

Every node in **Validation tests** passes in a verified run and every named mutant is killed per [T.K](development_plan_standards.md#tk-kill) at stage 2.

#### Remaining Work

The whole sprint.

### Sprint 1.2: Pure kernels and totality [Planned]

**Status**: Planned
**Implementation**: `src/agentctl/result.py`, `tests/oracles/python_discipline.toml`, `tests/integration/test_python_laws.py`
**Validation tests**: `tests/governance/test_python_discipline.py::test_core_edge_census`, `tests/governance/test_python_discipline.py::test_partial_operations_and_closed_matches`, `tests/integration/test_python_laws.py::test_repeatability_and_argument_preservation`
**Mutants**: none — planned mutants are named in this sprint's Deliverables until their corpus rows land
**Closes**: none
**Docs to update**: `documents/engineering/code_standards.md`, `documents/engineering/testing.md`

#### Objective

Pure kernels and totality supplies its complete owned contract through the single phase-scoped gate verdict.

#### Deliverables

Declare every Python module's core/edge role and approved native capability boundary. Separate source-field projection from mutable hashing and all I/O. Core has finite supported domains, explicit ambient inputs, guarded partial operations and exhaustive closed vocabularies; boundary wildcards reject unknown data. No coverage exclusion is added for an unreachable assertion. This sprint migrates `src/agentctl/check/validator/` (owner [Governance and phase evidence](phase-0-governance-and-phase-evidence.md)) only as [§ A](development_plan_standards.md#a-well-ordered-constructive-narrative) A1 permits; later-owned modules are migrated by their owners under their ledger rows. Planned mutants, named here until their corpus rows land ([§ C](development_plan_standards.md#c-honest-completion-tracking)): `M-python-core-ambient-read`, `M-python-open-closed-match` and `M-python-partial-access`.

#### Validation

Perturb environment, working directory, locale and hash order within supported domains and require identical pure results and unchanged inputs. Refuse a core import of an effect adapter, a mutable borrowed input posing as a snapshot, unbounded producer, unsupported recursion and an unhandled closed variant.

Every node in **Validation tests** passes in a verified run and every named mutant is killed per [T.K](development_plan_standards.md#tk-kill) at stage 2.

#### Remaining Work

The whole sprint.

### Sprint 1.3: Stage-2 evidence checkers and gate migration [Planned]

**Status**: Planned
**Implementation**: `tests/governance/test_stage2_checkers.py`, `tests/integration/test_owned_cleanup.py`
**Validation tests**: `tests/governance/test_python_discipline.py::test_migrated_sources_carry_no_suppression`, `tests/governance/test_python_discipline.py::test_complete_first_party_census`, `tests/integration/test_owned_cleanup.py::test_cleanup_preserves_primary_failure`, `tests/integration/test_owned_cleanup.py::test_owned_leak_fails_its_verdict`, `tests/governance/test_stage2_checkers.py::test_oracle_loading_required`, `tests/governance/test_stage2_checkers.py::test_subject_substitution_refused`, `tests/governance/test_stage2_checkers.py::test_kill_provenance_conditions`, `tests/governance/test_stage2_checkers.py::test_closure_set_shrink_refused`, `tests/governance/test_stage2_checkers.py::test_generated_decision_mutants`, `tests/governance/test_stage2_checkers.py::test_coverage_scoped_to_closure`, `tests/governance/test_stage2_checkers.py::test_stage2_governed_records`, `tests/governance/test_stage2_checkers.py::test_platform_reads_only_in_dispatcher`, `tests/governance/test_stage2_checkers.py::test_native_twin_evidence_form`, `tests/governance/test_stage2_checkers.py::test_laundered_attribution_refused`, `tests/governance/test_stage2_checkers.py::test_stage2_finding_owned_by_later_phase`
**Mutants**: none — the planned gate-migration mutants are named in this sprint's Deliverables and the planned stage-2 checker mutants enter the Remaining Work table when this phase activates, each until its corpus row lands
**Closes**: R20, R20.2, R29.1
**Docs to update**: `documents/engineering/code_standards.md`, `documents/engineering/testing.md`

#### Objective

The stage-2 checkers judge every verdict whose closure contains this phase ([T.W](development_plan_standards.md#tw-staged-enforcement)), and the gate, harness and Governance-owned tests meet the same doctrine without a legacy exemption.

#### Deliverables

New stage-2 checker modules in the gate package enforce E3 oracle loading and E4 subject substitution ([T.E](development_plan_standards.md#te-unspoofable-test)), K2–K6 kill provenance ([T.K](development_plan_standards.md#tk-kill)), S10 ([T.S](development_plan_standards.md#ts-defended-spoofs)), so that a Done phase's cited sets shrink only through closure-set records, M4 generated decision mutants ([T.M](development_plan_standards.md#tm-adequacy)) and V6 closure-scoped coverage of every stage-2 verdict ([T.V](development_plan_standards.md#tv-verdict)), which extends the stage-1 coverage scoping of Governance and phase evidence; M4 reports first, and the change that enforces it is a deliverable of this sprint that lands before this phase closes ([T.W](development_plan_standards.md#tw-staged-enforcement)). The ratchet gains the stage-2 records of [T.G](development_plan_standards.md#tg-governed-changes): re-anchor, retarget, killer addition, killer relocation and closure-set records. The R20.2 checker admits Haskell and C closure evidence only as named-reason kills plus native accepting and refusing twins on their own family, while the coverage floor applies to Python sources, and its controls are value cases over fixtures that need no Haskell build. Each of these checkers has a corpus mutant whose killer is its `tests/governance/test_stage2_checkers.py` node; its planned id enters this phase's Remaining Work table when the phase activates and stays there until that corpus row exists ([§ C](development_plan_standards.md#c-honest-completion-tracking)). An S11 checker refuses an ownership, consumer or host-declaration change that moves the attribution of a failing locus without a decision row naming it ([T.M](development_plan_standards.md#tm-adequacy) M1), and a change that removes statements or branches from coverage measurement without a decision row naming the source. The `tests/governance/test_stage2_checkers.py` nodes refuse the stage-2 spoofs of [T.S](development_plan_standards.md#ts-defended-spoofs): `test_oracle_loading_required` S6, `test_subject_substitution_refused` S7, `test_kill_provenance_conditions` the stage-2 kills of S5, `test_closure_set_shrink_refused` the closure-set part of S10 and `test_laundered_attribution_refused` S11, while `test_stage2_finding_owned_by_later_phase` shows a stage-2 finding in a Governance-owned file owned by this phase and its later consumers ([T.W](development_plan_standards.md#tw-staged-enforcement)). Each stage-2 checker declares this phase as its introducing phase through the rule-provenance interface of Governance and phase evidence (D-131). The change that builds each stage-2 check moves this phase's rows of [§ A](development_plan_standards.md#a-well-ordered-constructive-narrative) to Enforced now and appends this phase's rows to [§ U](development_plan_standards.md#u-plan-and-closure-checks), rows that T.I projects to this phase (D-165).

The closed-match idiom of D-138 lands once ty accepting and refusing controls exist. This sprint consumes `src/agentctl/foundation_host.py`, whose dispatcher is the only platform read, and foreign-family branches live in host-declared modules reached lazily. Each per-file cap lifts as its converted test becomes a declared-parameter or real-host control, and source coverage suppressions give way to native subprocess ownership and name-anchored exceptions. `tests/integration/test_owned_cleanup.py` holds the portable cleanup control that preserves the primary failure. This sprint migrates the Governance-owned gate, harness, oracle and corpus files (owner [Governance and phase evidence](phase-0-governance-and-phase-evidence.md)) only as [§ A](development_plan_standards.md#a-well-ordered-constructive-narrative) A1 permits, keeping each protected Governance mutant's search text unique; it hides no legacy file, exempts no checker and keeps source-independent oracles, exact named mutant kills, complete coverage and the read-only HEAD ratchet. It consumes `tests/governance/test_source_guards.py::test_suppression_ban_fixtures` and `tests/integration/test_guard.py::test_containment_detects_owned_leak` of [Governance and phase evidence](phase-0-governance-and-phase-evidence.md) as census citations; its own suppression-ban and owned-leak evidence lives in `tests/governance/test_python_discipline.py` and `tests/integration/test_owned_cleanup.py`, and the planned `M-guard-owned-leak-ignored` targets a module this phase owns and is killed by `tests/integration/test_owned_cleanup.py::test_owned_leak_fails_its_verdict` (D-166). Planned gate-migration mutants, named here until their corpus rows land ([§ C](development_plan_standards.md#c-honest-completion-tracking)): `M-guard-owned-leak-ignored`, `M-python-test-source-hidden` and `M-report-primary-error-erased`.

Model admission (R29.1, D-174) is checked at stage 2 by this sprint: an effect-interpreter parameter is bound only to a registered environment model built by a registered model module (a Haskell model library of the per-owner packages or `tests/models/`); a model imports only raw boundary types and never a subject renderer, parser or codec; each model's conformance cases, whose expectations come only from ratcheted oracle rows, execute all of its statements and branches and alone kill its owner mutants ([T.E](development_plan_standards.md#te-unspoofable-test) E3, E4 and E7; T.M M5); a model-backed kill counts only in a run in which that model is conformant; a generated killer reads its seed, size and count from a ratcheted row and the baseline adds one run with a nonce-derived seed (T.K K7); and the closed-list source rules of [§ Q](development_plan_standards.md#q-containment-and-user-state-protection) refuse registry, clipboard, foreign-console and unregistered-signal calls in tests (S15). Its killer-addition and killer-relocation records serve the conversion of disruptive killers (D-178). Planned nodes and mutants, named here until their corpus rows land: `tests/governance/test_stage2_checkers.py::test_unregistered_model_refused`, `tests/governance/test_stage2_checkers.py::test_model_importing_subject_codec_refused`, `tests/governance/test_stage2_checkers.py::test_model_kill_requires_conformance`, `tests/governance/test_stage2_checkers.py::test_generated_killer_seed_from_row`; `M-stage2-model-registry-blind`, `M-stage2-model-import-blind`, `M-stage2-model-kill-unconformant-accepted`, `M-stage2-seed-literal-accepted`.

#### Validation

Require accepting and refusing controls for every new mechanical rule, including a refused fixture for each stage-2 clause. Native report/readiness branches execute on Linux; a foreign family's Python branch lies in a host-declared module of the earliest phase whose lane includes that family and whose closure contains every module and native package the branch needs, and a foreign branch of a shared Haskell or C source is a host-declared region owed to a later phase whose lane includes that family ([§ A](development_plan_standards.md#a-well-ordered-constructive-narrative) A3), never a skip marker or broad exclusion. Cleanup failures preserve the original diagnostic, fail the relevant verdict and retain owned evidence.

Every node in **Validation tests** passes in a verified run and every named mutant is killed per [T.K](development_plan_standards.md#tk-kill) at stage 2.

#### Remaining Work

The whole sprint.

## Remaining Work

The whole phase: Sprints 1.1–1.3.

## Documentation Requirements

**Architecture docs to create/update:**

- None.

**Engineering docs to create/update:**

- `documents/engineering/code_standards.md` — doctrine, mechanisms and scope of executable evidence.
- `documents/engineering/testing.md` — doctrine, mechanisms and scope of executable evidence.

**Operations and reference docs to create/update:**

- None.

**Cross-references to add:**

- `DEVELOPMENT_PLAN/00-overview.md` — requirement closure and lower-phase dependencies.
- `DEVELOPMENT_PLAN/system-components.md` — stable capability/path ownership.
- `DEVELOPMENT_PLAN/legacy_tracking_for_deletion.md` — remaining incompatible implementation shapes.
