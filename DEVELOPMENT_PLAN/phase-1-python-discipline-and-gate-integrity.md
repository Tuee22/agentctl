# Phase 1 — Python discipline and gate integrity

**Status**: Planned
**Depends on**: [Phase 0 — Governance and phase evidence](phase-0-governance-and-phase-evidence.md)
**Host lane**: linux
**Gate**: `agentctl check`
**Gate kind**: self-verifying
**Closes**: R20, R21

> **Purpose**: Project-owned strict Python doctrine, local executable enforcement, typed native boundaries and migration of existing package, gate and test code.

## Phase Objective

Project-owned strict Python doctrine, local executable enforcement, typed native boundaries and migration of existing package, gate and test code. This phase removes incompatible implementation shapes rather than granting a legacy suppression or adding a second checker.

This phase needs Linux only. The declared tests are executable contracts; an absent required test is unmet evidence, not existing proof. Acceptance-only test implementations belong to the prerequisite owner named in the inventory. Existing incompatible code is inventoried in the deletion ledger. No old implementation or unqualified receipt establishes this revised contract.

## Gate Integrity

| Requirement | Oracle | Observer | Mutants | Tests |
|---|---|---|---|---|
| R21 — Typed immutable Python migration | `tests/oracles/python_discipline.toml` | value; observer: independent inputs and nonce-bound native observations | `M-python-runtime-type-test`, `M-python-object-annotation`, `M-python-container-mutation`, `M-python-rebinding` | `tests/governance/test_python_discipline.py::test_boundary_narrowing_controls`, `tests/governance/test_python_discipline.py::test_immutable_records_and_bindings`, `tests/integration/test_python_boundaries.py::test_native_declarations_conform` |
| R20 — Pure kernels and totality | `tests/oracles/python_discipline.toml` | value; observer: independent inputs and nonce-bound native observations | `M-python-core-ambient-read`, `M-python-partial-access`, `M-python-open-closed-match` | `tests/governance/test_python_discipline.py::test_core_edge_census`, `tests/governance/test_python_discipline.py::test_partial_operations_and_closed_matches`, `tests/integration/test_python_laws.py::test_repeatability_and_argument_preservation` |
| R20 — Gate, harness and native evidence migration | `tests/oracles/python_discipline.toml` | value; observer: independent inputs and nonce-bound native observations | `M-python-test-source-hidden`, `M-guard-owned-leak-ignored`, `M-report-primary-error-erased` | `tests/governance/test_source_guards.py::test_suppression_ban_fixtures`, `tests/governance/test_python_discipline.py::test_complete_first_party_census`, `tests/integration/test_owned_resources.py::test_cleanup_preserves_primary_failure`, `tests/integration/test_guard.py::test_containment_detects_owned_leak` |

## Not Proven By This Gate

- A receipt's digest establishes input currency, not an independently attested historical run. Local receipt authenticity has the documented honest ceiling.
- A source rule or finite corpus does not prove arbitrary callback purity, universal termination or agent-internal readiness. Native operation and resource assumptions remain explicit.
- Foreign-kernel behavior is outside this phase's Linux verdict. Later native implementation extends the common contract and cannot retroactively add a foreign-hardware requirement here.

## Sprints

### Sprint 1.1: Typed immutable Python migration [Planned]

**Status**: Planned
**Implementation**: `src/agentctl/`, `tests/`, `stubs/`
**Validation tests**: `tests/governance/test_python_discipline.py::test_boundary_narrowing_controls`, `tests/governance/test_python_discipline.py::test_immutable_records_and_bindings`, `tests/integration/test_python_boundaries.py::test_native_declarations_conform`
**Mutants**: `M-python-runtime-type-test`, `M-python-object-annotation`, `M-python-container-mutation`, `M-python-rebinding`
**Closes**: R21
**Docs to update**: `documents/engineering/code_standards.md`, `documents/engineering/testing.md`, `documents/engineering/quality_gate.md`

#### Objective

Typed immutable Python migration supplies its complete owned contract through the single phase-scoped gate verdict.

#### Deliverables

Migrate isinstance/issubclass/type comparisons and object annotations to structural boundary parsers with precise native decoder unions. Preserve local Ok/Err; use final frozen slotted keyword-only records, module-level behavior, recursively immutable owned values and single assignment. Replace mutable Click subclasses and reflective framework access with narrow typed adapters.

#### Validation

Accept correct structural parsers, finite immutable records and native borrowed capabilities. Refuse each forbidden spelling through direct and aliased forms. Verify native decoder/stub names, signatures and supported return shapes; bool/int overlap and malformed input yield typed reasons instead of a traceback.

Required executable evidence: `tests/governance/test_python_discipline.py::test_boundary_narrowing_controls`, `tests/governance/test_python_discipline.py::test_immutable_records_and_bindings`, `tests/integration/test_python_boundaries.py::test_native_declarations_conform`. Every named mutant must die for its recorded reason in those tests; a baseline failure or unrelated exception is not a kill.

#### Remaining Work

The whole sprint.

### Sprint 1.2: Pure kernels and totality [Planned]

**Status**: Planned
**Implementation**: `src/agentctl/bootstrap/`, `src/agentctl/paths.py`, `src/agentctl/result.py`, `src/agentctl/check/validator/`, `tests/oracles/python_discipline.toml`
**Validation tests**: `tests/governance/test_python_discipline.py::test_core_edge_census`, `tests/governance/test_python_discipline.py::test_partial_operations_and_closed_matches`, `tests/integration/test_python_laws.py::test_repeatability_and_argument_preservation`
**Mutants**: `M-python-core-ambient-read`, `M-python-partial-access`, `M-python-open-closed-match`
**Closes**: none
**Docs to update**: `documents/engineering/code_standards.md`, `documents/engineering/testing.md`, `documents/engineering/quality_gate.md`

#### Objective

Pure kernels and totality supplies its complete owned contract through the single phase-scoped gate verdict.

#### Deliverables

Declare every Python module's core/edge role and approved native capability boundary. Separate source-field projection from mutable hashing and all I/O. Core has finite supported domains, explicit ambient inputs, guarded partial operations and exhaustive closed vocabularies; boundary wildcards reject unknown data. No coverage exclusion is added for an unreachable assertion.

#### Validation

Perturb environment, working directory, locale and hash order within supported domains and require identical pure results and unchanged inputs. Refuse a core import of an effect adapter, a mutable borrowed input posing as a snapshot, unbounded producer, unsupported recursion and an unhandled closed variant.

Required executable evidence: `tests/governance/test_python_discipline.py::test_core_edge_census`, `tests/governance/test_python_discipline.py::test_partial_operations_and_closed_matches`, `tests/integration/test_python_laws.py::test_repeatability_and_argument_preservation`. Every named mutant must die for its recorded reason in those tests; a baseline failure or unrelated exception is not a kill.

#### Remaining Work

The whole sprint.

### Sprint 1.3: Gate, harness and native evidence migration [Planned]

**Status**: Planned
**Implementation**: `src/agentctl/check/`, `tests/harness/`, `tests/oracles/`, `tests/mutants/`
**Validation tests**: `tests/governance/test_source_guards.py::test_suppression_ban_fixtures`, `tests/governance/test_python_discipline.py::test_complete_first_party_census`, `tests/integration/test_owned_resources.py::test_cleanup_preserves_primary_failure`, `tests/integration/test_guard.py::test_containment_detects_owned_leak`
**Mutants**: `M-python-test-source-hidden`, `M-guard-owned-leak-ignored`, `M-report-primary-error-erased`
**Closes**: R20
**Docs to update**: `documents/engineering/code_standards.md`, `documents/engineering/testing.md`, `documents/engineering/quality_gate.md`

#### Objective

Gate, harness and native evidence migration supplies its complete owned contract through the single phase-scoped gate verdict.

#### Deliverables

Apply the same doctrine to gate and test support; do not hide legacy files or exempt the checker. Keep source-independent oracles, exact named mutant kills, no mocks, complete coverage and read-only HEAD ratchet. Replace source coverage suppressions with native subprocess ownership and receipts; foreign kernel obligations remain explicitly owed to their native acceptance lane.

#### Validation

Require accepting and refusing controls for every new mechanical rule. Native report/readiness branches execute on Linux; foreign syscalls need native receipts without skip markers or broad exclusions. Cleanup failures preserve the original diagnostic, fail the relevant verdict and retain owned evidence.

Required executable evidence: `tests/governance/test_source_guards.py::test_suppression_ban_fixtures`, `tests/governance/test_python_discipline.py::test_complete_first_party_census`, `tests/integration/test_owned_resources.py::test_cleanup_preserves_primary_failure`, `tests/integration/test_guard.py::test_containment_detects_owned_leak`. Every named mutant must die for its recorded reason in those tests; a baseline failure or unrelated exception is not a kill.

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
- `documents/engineering/quality_gate.md` — doctrine, mechanisms and scope of executable evidence.

**Operations and reference docs to create/update:**

- None.

**Cross-references to add:**

- `DEVELOPMENT_PLAN/00-overview.md` — requirement closure and lower-phase dependencies.
- `DEVELOPMENT_PLAN/system-components.md` — stable capability/path ownership.
- `DEVELOPMENT_PLAN/legacy_tracking_for_deletion.md` — remaining incompatible implementation shapes.
