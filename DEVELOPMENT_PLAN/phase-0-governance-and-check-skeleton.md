# Phase 0 — Governance, documentation standards and the check skeleton

**Status**: Done
**Depends on**: nothing
**Host lane**: any-host
**Gate**: `agentctl check`
**Gate kind**: self-verifying
**Closes**: R2, R14.1

> **Purpose**: Establish the governed plan and documentation, the permanent click package and Python check legs, the test-discipline plugin, both structural validators and the root entry documents.

## Phase Objective

This phase supplies the executable governance foundation. `agentctl check` runs the Python legs that exist at
this point: `ruff-check`, `ruff-format`, `ty` and `pytest`. Each subsequent capability adds its real check step
with its implementation; the skeleton contains no successful placeholder for a missing toolchain or Haskell leg.
[The quality gate](../documents/engineering/quality_gate.md) owns the resulting full command's contract.

The governed suite is Sprint 0.1's artifact. It stays Active until the validators of Sprints 0.4 and 0.5 examine
it through the real check command. Work advances through the other sprints in id order while 0.1 remains open,
as [Working the Plan](README.md#working-the-plan) specifies. Root-document presence becomes mandatory with
Sprint 0.6; it is not a reason to waive metadata or link checks on documents that already exist.

The mutant ids below declare the negative transformations the gate-integrity apparatus executes retrospectively.
Negative-fixture tests prove the Phase 0 checks directly; the independent mutant runner and immutable corpus belong
to [Phase 1 — Gate-integrity apparatus](phase-1-gate-integrity-apparatus.md). From Sprint 1.2 onward every run also
kills the Phase 0 mutants; initial Phase 0 closure rests on the direct negative controls, with no claimed mutant
verdict. Per-user paths originate here for the single-run lock; the later handoff passes those same paths
to Haskell rather than introducing another directory policy.

## Gate Integrity

| Requirement | Oracle | Observer | Mutants | Tests |
|---|---|---|---|---|
| R2 — agentctl is a click application tested with pytest | `tests/oracles/command_surface.toml`, `tests/oracles/check_legs.toml` | value: the click command surface and leg plans equal independently authored rows; real: click invocation and pytester exercise the installed editable package | `M-legs-drop-pytest`, `M-legs-ignore-exit` | `tests/unit/test_cli.py::test_cli_is_click_group`, `tests/unit/test_check_legs.py::test_leg_table_matches_oracle`, `tests/unit/test_check_legs.py::test_failing_leg_fails_check` |
| R14.1 — ruff, strict ty and the entire pytest suite form the Python gate | `tests/oracles/check_legs.toml` | value: the Python leg set, arguments and failure verdict match the oracle; real: pinned tools reject copied negative fixtures and pytester proves selection and outcome discipline | `M-legs-drop-ty`, `M-legs-ty-rule-warn`, `M-plugin-allow-skip`, `M-plugin-allow-selector` | `tests/unit/test_check_legs.py::test_leg_table_matches_oracle`, `tests/integration/test_static_legs.py::test_ty_fires_on_fixture`, `tests/governance/test_gate_plugin.py::test_skip_fails_session`, `tests/governance/test_gate_plugin.py::test_selector_under_check_fails` |
| R20 — structural plan and document checks reject known violations (contributing) | none — minimal negative trees name the governance rule each breaks, with an otherwise valid twin | value: each validator sees one named violation in a negative tree and none in its valid twin or the live governed tree | `M-docval-skip-anchor`, `M-docval-binary-name-blind`, `M-planval-forward-dependency`, `M-planval-closure-at-least-once` | `tests/governance/test_doc_validator.py::test_docs_links`, `tests/governance/test_doc_validator.py::test_docs_binary_unnamed`, `tests/governance/test_plan_validator.py::test_plan_dependency_direction`, `tests/governance/test_plan_validator.py::test_plan_requirements_table` |

## Not Proven By This Gate

- That the direct negative fixtures or later mutants exhaust every possible weakness in a test's assertions. — not proven by any phase.
- A current evidence digest proves the covered bytes, not that a gate run happened. — not proven by any phase.
- Completeness of the concept-note disposition cannot be re-checked once agentctl-plan.md is deleted. — not proven by any phase.
- Tamper resistance extends only to data already present in the available HEAD baseline ([§ P](development_plan_standards.md#p-the-ratchet-and-automatic-closure)); uncommitted inputs have no historical protection. — not proven by any phase.

## Sprints

### Sprint 0.1: Governed plan and documentation suite [Done]

**Status**: Done
**Implementation**: `DEVELOPMENT_PLAN/`, `documents/`
**Validation tests**: `tests/governance/test_doc_validator.py::test_live_docs_clean`, `tests/governance/test_plan_validator.py::test_live_plan_clean`
**Mutants**: none — the content is examined by the two validators; their negative transformations belong to Sprints 0.4 and 0.5
**Closes**: none
**Docs to update**: `documents/README.md`, `documents/documentation_standards.md`

#### Objective

Preserve the user's requirements and decisions as a complete constructive plan and a suite of canonical contracts.

#### Deliverables

- The fixed plan file set, single status table, phase and sprint structure, component inventory and empty deletion ledger.
- `00-overview.md`'s requirement rows, each quoting the verbatim request block in `rationale.md` and naming exactly one closing sprint.
- `rationale.md`'s decisions and concept-note disposition, checked for heading and bullet-group coverage while the note exists.
- The documentation taxonomy, metadata, canonical contract homes, relative links, indexes and glossary; root entry documents remain Sprint 0.6's scope.

#### Validation

1. The live documentation satisfies the documented rules — `tests/governance/test_doc_validator.py::test_live_docs_clean`; fails when a live page loses its Purpose block, while a minimal valid page passes; no mutant: the rule-specific killers are assigned to Sprint 0.4.
2. The live plan has complete requirement closure and consistent structure — `tests/governance/test_plan_validator.py::test_live_plan_clean`; fails when a requirement loses its only closing sprint, while the valid plan twin passes; no mutant: Sprint 0.5 owns the rule-specific killers.

#### Remaining Work

None.

### Sprint 0.2: Package skeleton and the check command [Done]

**Status**: Done
**Implementation**: `pyproject.toml`, `src/agentctl/__init__.py`, `src/agentctl/cli.py`, `src/agentctl/result.py`, `src/agentctl/process.py`, `src/agentctl/paths.py`, `src/agentctl/check/legs.py`, `src/agentctl/check/steps.py`, `src/agentctl/check/preconditions.py`, `tests/harness/oracle.py`, `tests/oracles/command_surface.toml`, `tests/oracles/check_legs.toml`, `tests/support.txt`, `tests/harness/trees.py`, `tests/unit/test_cli.py`, `tests/unit/test_check_legs.py`, `tests/unit/test_identity.py`, `tests/unit/test_paths.py`, `tests/integration/test_static_legs.py`, `tests/fixtures/static_negative/`
**Validation tests**: `tests/unit/test_cli.py::test_cli_is_click_group`, `tests/unit/test_cli.py::test_check_rejects_arguments`, `tests/unit/test_check_legs.py::test_leg_table_matches_oracle`, `tests/unit/test_check_legs.py::test_failing_leg_fails_check`, `tests/unit/test_check_legs.py::test_empty_target_set_fails`, `tests/unit/test_identity.py::test_non_editable_refused`, `tests/unit/test_identity.py::test_other_checkout_refused`, `tests/unit/test_paths.py::test_xdg_overrides_on_every_os`, `tests/integration/test_static_legs.py::test_ruff_fires_on_fixture`, `tests/integration/test_static_legs.py::test_ruff_format_fires_on_fixture`, `tests/integration/test_static_legs.py::test_ty_fires_on_fixture`, `tests/integration/test_static_legs.py::test_ty_ignores_user_config`, `tests/integration/test_static_legs.py::test_raw_link_rule_exception_is_narrow`
**Mutants**: `M-legs-drop-pytest`, `M-legs-drop-ty`, `M-legs-ignore-exit`, `M-legs-empty-target`, `M-legs-ty-rule-warn`, `M-legs-ty-user-config-leak`
**Closes**: R2
**Docs to update**: `documents/engineering/quality_gate.md`, `documents/engineering/code_standards.md`, `documents/reference/cli_reference.md`, `documents/reference/files_and_state.md`

#### Objective

Install one permanent click application whose check command actually runs the pinned Python tools against this checkout.

#### Deliverables

- A hatchling `src` package, console entry point and `dev` extra; Python is at least 3.12, click is pinned to 8.5.0, ruff to 0.17.3, ty to 0.0.95, pytest to 9.2.0 and coverage to 7.17.0.
- The click group exposes `check` with no command arguments and the global `--assume-yes`; it provides no placeholder passthrough command. `Result`, the one process module and the directory policy are real minimal utilities used by check.
- `preconditions.py` implements P1–P5: PEP 610 editable identity and module location, exact installed pins, the Python floor, a git work tree and a state-directory single-run lock. Preconditions for absent capabilities arrive with those capabilities, never as canned successes.
- `steps.py` owns a fresh temporary run directory, nonce and scrubbed child environment; `legs.py` supplies the Python legs in oracle order, using `sys.executable`, explicit configuration, no fix/cache writes, an isolated ty configuration home and non-empty filesystem target walks.
- `tests/harness/oracle.py` compares pure subjects with independently authored TOML rows without importing `agentctl`; the initial command and Python-leg rows carry request or decision provenance and grow with implemented capabilities.
- The ruff, ty, pytest and coverage configuration is co-designed with the pinned tools, including the raw-link reader's narrowly scoped PTH115 exception, then recorded for freezing by the gate-integrity apparatus. Strict ty means every rule is an error, ignore comments are disrespected and warnings fail; user configuration cannot weaken it.
- The verdict propagates every failed or unrun leg, with its name; temporary cache, pytest and tool output lives under the run directory, and every leg is demonstrated rejecting a copied `*.py.txt` negative with a passing twin.

#### Validation

1. The installed group is click, exposes `check` and refuses trailing check arguments — `tests/unit/test_cli.py::test_cli_is_click_group`, `tests/unit/test_cli.py::test_check_rejects_arguments`; fails when check is absent or accepts a selector, while plain `check` parses; no mutant: the command parsing has direct positive and negative controls.
2. Leg values and failure propagation match independent rows — `tests/unit/test_check_legs.py::test_leg_table_matches_oracle`, `tests/unit/test_check_legs.py::test_failing_leg_fails_check`; fails when a leg is omitted or a failing outcome yields success, while all-success outcomes pass; mutants `M-legs-drop-ty`, `M-legs-ignore-exit`.
3. A file walk cannot pass empty — `tests/unit/test_check_legs.py::test_empty_target_set_fails`; fails when an empty input is accepted, with a one-file input as the positive control; mutant `M-legs-empty-target`.
4. Identity refuses non-editable and other-checkout installs — `tests/unit/test_identity.py::test_non_editable_refused`, `tests/unit/test_identity.py::test_other_checkout_refused`; fails when either invalid PEP 610 fixture is accepted, and the matching editable identity passes; no mutant: these pure negative fixtures directly exercise P1.
5. Paths obey the supplied XDG roots across OS-family inputs — `tests/unit/test_paths.py::test_xdg_overrides_on_every_os`; fails when a Windows or Darwin case chooses a platform default over its override, with unset-variable default cases as twins; no mutant: the directory cases are direct value evidence.
6. Each real pinned static tool rejects its own negative and accepts its valid twin — `tests/integration/test_static_legs.py::test_ruff_fires_on_fixture`, `tests/integration/test_static_legs.py::test_ruff_format_fires_on_fixture`, `tests/integration/test_static_legs.py::test_ty_fires_on_fixture`; fails if F401, a formatting difference or the chosen implicit-type diagnostic is absent or merely a warning; mutant `M-legs-ty-rule-warn`.
7. A user ty configuration cannot downgrade the negative — `tests/integration/test_static_legs.py::test_ty_ignores_user_config`; fails when a fake configuration home turns its error into a pass, while the same fixture fails under the isolated home and its valid twin passes; mutant `M-legs-ty-user-config-leak`.
8. The raw-link canary passes only at the approved module path and the same source elsewhere reports PTH115 — `tests/integration/test_static_legs.py::test_raw_link_rule_exception_is_narrow`; fails when the exception is removed or widened; no mutant: the real pinned linter supplies both controls.

#### Remaining Work

None.

### Sprint 0.3: Test-discipline gate plugin [Done]

**Status**: Done
**Implementation**: `src/agentctl/check/gate_plugin.py`, `src/agentctl/check/legs.py`, `tests/governance/test_gate_plugin.py`, `pyproject.toml`
**Validation tests**: `tests/governance/test_gate_plugin.py::test_skip_fails_session`, `tests/governance/test_gate_plugin.py::test_xfail_fails_session`, `tests/governance/test_gate_plugin.py::test_selector_under_check_fails`, `tests/governance/test_gate_plugin.py::test_deselection_fails_session`, `tests/governance/test_gate_plugin.py::test_orphan_module_fails`, `tests/governance/test_gate_plugin.py::test_evidence_marker_required`, `tests/governance/test_gate_plugin.py::test_manifest_matches_execution`
**Mutants**: `M-plugin-allow-skip`, `M-plugin-allow-xfail`, `M-plugin-allow-selector`, `M-plugin-orphan-blind`, `M-plugin-manifest-collected-only`
**Closes**: R14.1
**Docs to update**: `documents/engineering/quality_gate.md`, `documents/engineering/testing.md`

#### Objective

Make the pytest leg mean the entire collected suite executed successfully, with no reduced verdict hidden by pytest options.

#### Deliverables

- Check explicitly loads `agentctl.check.gate_plugin`, disables third-party plugin autoload, removes `PYTEST_ADDOPTS` and `PYTEST_PLUGINS`, and runs the whole `tests` root with pytester and no cache provider.
- Under check the plugin fails any skip, skipif, xfail, xpass, importorskip or deselection and refuses selectors, including `-k`, `-m`, node ids and last-failed options; nested pytester negatives are isolated sessions whose expected failure is asserted by the outer test.
- `tests.orphan-modules` joins collected test modules to sprint citations, and every Python file under `tests/` is collected or explicitly declared in `tests/support.txt`. Support declarations cannot hide a file matching the test-module naming convention.
- Every pytest test carries exactly one registered evidence marker, `value`, `real` or `observer`; a missing, duplicate or unknown class fails, and `owed` is never a test marker.
- The plugin exports separate collected, executed and passed node-id sets with the fresh run nonce. Collection alone cannot stand for execution, and an empty collection fails.

#### Validation

1. Skip and expected-failure outcomes fail a real pytester session — `tests/governance/test_gate_plugin.py::test_skip_fails_session`, `tests/governance/test_gate_plugin.py::test_xfail_fails_session`; fails when the forbidden outcome exits successfully, with an otherwise identical passing test as the control; mutants `M-plugin-allow-skip`, `M-plugin-allow-xfail`.
2. Every selector and deselection fails under check — `tests/governance/test_gate_plugin.py::test_selector_under_check_fails`, `tests/governance/test_gate_plugin.py::test_deselection_fails_session`; fails when narrowing a two-test pytester suite succeeds, while its unselected whole run passes; mutant `M-plugin-allow-selector`.
3. Orphan detection checks both collection and citations — `tests/governance/test_gate_plugin.py::test_orphan_module_fails`; fails when an uncited collected module or an uncollected test-named file is accepted, while a cited collected module and declared support helper pass; mutant `M-plugin-orphan-blind`.
4. Evidence markers form a closed, singular set — `tests/governance/test_gate_plugin.py::test_evidence_marker_required`; fails when absent, repeated or invalid markers pass collection, while one valid marker passes; no mutant: pytester supplies each negative and its valid twin.
5. The manifest records execution separately from collection — `tests/governance/test_gate_plugin.py::test_manifest_matches_execution`; fails when a collected-but-never-executed case is reported passed or the nonce differs, while a normally completed pytester suite has equal collected, executed and passed ids; mutant `M-plugin-manifest-collected-only`.

#### Remaining Work

None.

### Sprint 0.4: Documentation validator [Done]

**Status**: Done
**Implementation**: `src/agentctl/check/validator/docs.py`, `src/agentctl/check/steps.py`, `tests/governance/test_doc_validator.py`, `tests/fixtures/docs_negative/`
**Validation tests**: `tests/governance/test_doc_validator.py::test_docs_metadata`, `tests/governance/test_doc_validator.py::test_docs_structure`, `tests/governance/test_doc_validator.py::test_docs_taxonomy`, `tests/governance/test_doc_validator.py::test_docs_links`, `tests/governance/test_doc_validator.py::test_docs_owning_phase`, `tests/governance/test_doc_validator.py::test_docs_no_status`, `tests/governance/test_doc_validator.py::test_docs_phase_citation`, `tests/governance/test_doc_validator.py::test_docs_binary_unnamed`, `tests/governance/test_doc_validator.py::test_docs_enforcement_cited`, `tests/governance/test_doc_validator.py::test_live_docs_clean`
**Mutants**: `M-docval-skip-anchor`, `M-docval-binary-name-blind`, `M-docval-taxonomy-open`
**Closes**: none
**Docs to update**: `documents/documentation_standards.md`, `documents/README.md`

#### Objective

Turn each documentation rule into a pure check with a minimal rejecting fixture and a valid twin.

#### Deliverables

- `validator/docs.py` supplies `docs.metadata`, `docs.structure`, `docs.taxonomy`, `docs.links`, `docs.owning-phase`, `docs.no-status`, `docs.phase-citation`, `docs.binary-unnamed` and `docs.enforcement-cited`, with the exact semantics and fixtures in [documentation standards](../documents/documentation_standards.md).
- The `validators` step runs these checks over existing governed pages and the plan's links; root pages receive metadata and link checks when present, while `docs.root-entry`'s required root-file presence lands with Sprint 0.6.
- Link and content checks ignore fenced examples, including nested fence lengths; `docs.binary-unnamed` alone also reads fenced content. Local anchors resolve from target headings without network access.
- Each registered rule has its named `test_docs_...` test and negative directory; each negative yields exactly its violation and no other, its valid twin yields none, and the same check sees the live tree.

#### Validation

1. Metadata, section order and taxonomy reject their named minimal trees — `tests/governance/test_doc_validator.py::test_docs_metadata`, `tests/governance/test_doc_validator.py::test_docs_structure`, `tests/governance/test_doc_validator.py::test_docs_taxonomy`; fails when an invalid Status, missing Related or unregistered category is accepted, while each valid twin passes; mutant `M-docval-taxonomy-open`.
2. Links and owning-phase identities resolve, without parsing fenced examples as links — `tests/governance/test_doc_validator.py::test_docs_links`, `tests/governance/test_doc_validator.py::test_docs_owning_phase`; fails when a missing anchor or wrong owning-phase title is accepted, while a real anchor and fenced non-link twin pass; mutant `M-docval-skip-anchor`.
3. Status, numbered phase citations and internal binary names stay out of the documented scopes — `tests/governance/test_doc_validator.py::test_docs_no_status`, `tests/governance/test_doc_validator.py::test_docs_phase_citation`, `tests/governance/test_doc_validator.py::test_docs_binary_unnamed`; fails when a negative is undetected, while the same vocabulary in its permitted scope passes; mutant `M-docval-binary-name-blind`.
4. An enforcement claim needs its test id — `tests/governance/test_doc_validator.py::test_docs_enforcement_cited`; fails when an uncited enforcement claim is accepted, while its cited twin passes; no mutant: the paired rule fixtures directly prove the check.
5. All documentation checks examine the governed live pages — `tests/governance/test_doc_validator.py::test_live_docs_clean`; fails when a deliberately malformed live-tree copy yields no named violation, while the actual governed tree yields none; no mutant: the per-rule negative fixtures supply the controls.

#### Remaining Work

None.

### Sprint 0.5: Plan validator core [Done]

**Status**: Done
**Implementation**: `src/agentctl/check/validator/plan.py`, `src/agentctl/check/steps.py`, `tests/governance/test_plan_validator.py`, `tests/fixtures/docs_negative/`
**Validation tests**: `tests/governance/test_plan_validator.py::test_plan_fileset`, `tests/governance/test_plan_validator.py::test_plan_header`, `tests/governance/test_plan_validator.py::test_plan_status_harmony`, `tests/governance/test_plan_validator.py::test_plan_sprint_structure`, `tests/governance/test_plan_validator.py::test_plan_status_consequences`, `tests/governance/test_plan_validator.py::test_plan_dependency_direction`, `tests/governance/test_plan_validator.py::test_plan_requirements_table`, `tests/governance/test_plan_validator.py::test_plan_legacy_ledger`, `tests/governance/test_plan_validator.py::test_plan_disposition_table`, `tests/governance/test_plan_validator.py::test_plan_no_narrative`, `tests/governance/test_plan_validator.py::test_live_plan_clean`
**Mutants**: `M-planval-forward-dependency`, `M-planval-closure-at-least-once`, `M-planval-status-table-blind`, `M-planval-open-header`
**Closes**: none
**Docs to update**: `documents/documentation_standards.md`, `documents/engineering/testing.md`

#### Objective

Validate the plan's structural truth without demanding artifacts of capabilities that have not been built.

#### Deliverables

- `plan.fileset`, `plan.header`, `plan.status-harmony`, `plan.sprint-structure`, `plan.status-consequences`, `plan.dependency-direction`, `plan.requirements-table`, `plan.legacy-ledger`, `plan.disposition-table` and `plan.no-narrative` join the validators step.
- The status table is parsed for complete unique rows before comparison to phase headers. Headers and sprint fields have closed grammars, and the phase sections occur in their documented order.
- Requirement quotes are exact substrings of the verbatim originating-request block, every id has exactly one closing sprint and every phase's Closes equals its sprint union. A duplicated or missing closure fails independently of the prose statement.
- Dependencies point strictly lower, acceptance phases are terminal, and Remaining Work cites no higher phase. Active work names its remainder; Done work has none and its phase dependencies are Done. The declared Sprint 0.1 validator bootstrap and independent acceptance lanes are permitted explicitly.
- The deletion ledger has its fixed header and valid deleting phases; disposition rows use the closed vocabulary and resolving destinations. The preserved disposition is checked structurally after note deletion, without pretending to reconstruct the deleted source's completeness.
- Each check has its named `test_plan_...` case and an isolated minimal tree under `tests/fixtures/docs_negative/`, with exactly the named violation and a valid twin. Narrative checks exempt verbatim source blocks and provenance rather than banning the user's own quoted words.

#### Validation

1. File-set, header and sprint grammars are closed — `tests/governance/test_plan_validator.py::test_plan_fileset`, `tests/governance/test_plan_validator.py::test_plan_header`, `tests/governance/test_plan_validator.py::test_plan_sprint_structure`; fails when a phase is missing, an undeclared field appears or a sprint tag disagrees, with valid twins passing; mutant `M-planval-open-header`.
2. Status harmony validates the table before joining it — `tests/governance/test_plan_validator.py::test_plan_status_harmony`; fails when a row is missing, duplicated, malformed or different from its phase, with the complete matching table as the positive control; mutant `M-planval-status-table-blind`.
3. Status consequences and dependency direction reject invalid completion and forward dependency — `tests/governance/test_plan_validator.py::test_plan_status_consequences`, `tests/governance/test_plan_validator.py::test_plan_dependency_direction`; fails when Done work has a remainder or a dependency points forward, while the explicit 0.1 bootstrap and terminal acceptance branches pass; mutant `M-planval-forward-dependency`.
4. Requirement closure is exact and request-anchored — `tests/governance/test_plan_validator.py::test_plan_requirements_table`; fails for an altered quote, a missing closure or duplicate closures, with a once-closed anchored row as the positive control; mutant `M-planval-closure-at-least-once`.
5. Ledger and disposition rows retain their closed formats — `tests/governance/test_plan_validator.py::test_plan_legacy_ledger`, `tests/governance/test_plan_validator.py::test_plan_disposition_table`; fails for a nonexistent deleting phase or invalid disposition, while the empty ledger and valid mapped concept row pass; no mutant: the named negative trees directly prove the rules.
6. Narrative and the live plan satisfy the governance grammar — `tests/governance/test_plan_validator.py::test_plan_no_narrative`, `tests/governance/test_plan_validator.py::test_live_plan_clean`; fails when a dated closure narrative or forbidden phase title is inserted, while a verbatim request block and valid source-provenance twin pass; no mutant: direct negative trees prove these text rules.

#### Remaining Work

None.

### Sprint 0.6: Root entry documents [Done]

**Status**: Done
**Implementation**: `README.md`, `AGENTS.md`, `CLAUDE.md`, `src/agentctl/check/validator/docs.py`, `tests/governance/test_doc_validator.py`, `tests/fixtures/docs_negative/docs_root_entry/`
**Validation tests**: `tests/governance/test_doc_validator.py::test_docs_root_entry`, `tests/governance/test_doc_validator.py::test_live_docs_clean`, `tests/governance/test_plan_validator.py::test_live_plan_clean`
**Mutants**: `M-docval-root-pointer-extra-rule`, `M-docval-root-index-blind`
**Closes**: none
**Docs to update**: `documents/README.md`, `documents/documentation_standards.md`

#### Objective

Provide one reader entry point and one agent-policy home, with CLAUDE.md importing that policy.

#### Deliverables

- The root `README.md` describes the project, links both indexes and exposes only commands whose owning phase is built. It carries no phase status and never names the internal binary.
- `AGENTS.md` states plan-order execution, the single gate, automatic closure without a commit or human checkpoint, no staging/commit/push, no login or direct binary/cabal commands, no skips/suppressions or weakened oracle/mutant data, the isolation rules, and the fixed live folder.
- The policy states the optional screen-fixture capture procedure and its quota implications outside gate closure; ordinary check runs send no live input and never answer dialogs.
- `CLAUDE.md` contains its metadata block, one pointer sentence and `@AGENTS.md`, without parallel rules; `README.md` and `CLAUDE.md` use Reference only and `AGENTS.md` Authoritative source.
- `docs.root-entry` requires the root files, links and pointer shape from this sprint onward, with no permanent missing-root exception; the complete documentation and plan validators run over the full governed tree.

#### Validation

1. The root entry shapes are exact — `tests/governance/test_doc_validator.py::test_docs_root_entry`; fails when a root index link is missing, a root file is absent or CLAUDE.md carries a second policy rule, while the minimal complete root twin passes; mutants `M-docval-root-pointer-extra-rule`, `M-docval-root-index-blind`.
2. Root documents pass the same metadata, link and vocabulary checks as their scopes require — `tests/governance/test_doc_validator.py::test_live_docs_clean`; fails when a root README exposes the binary name, while the user-command twin passes; mutant `M-docval-binary-name-blind`.
3. The governed suite and status table agree after root entry creation — `tests/governance/test_plan_validator.py::test_live_plan_clean`; fails when Phase 0 is marked Done while a sprint still has work, while the fully closed synthetic phase twin passes; no mutant: the completion rules' negative trees are Sprint 0.5's controls.

#### Remaining Work

None.

## Remaining Work

None.

## Documentation Requirements

**Architecture docs to create/update:**

- None.

**Engineering docs to create/update:**

- `documents/engineering/quality_gate.md` — the Python legs, their installed-checkout identity, configurations and initial preconditions.
- `documents/engineering/testing.md` — the evidence markers, pytester controls, full-suite manifest and validator fixtures.
- `documents/engineering/code_standards.md` — the Result/process utilities and pinned Python conventions.

**Operations and reference docs to create/update:**

- `documents/reference/cli_reference.md` — the check command and global option.
- `documents/reference/files_and_state.md` — the directory policy, check lock and temporary run files.

**Cross-references to add:**

- `documents/README.md` — the governed page index and glossary linked from the root README.
- `documents/documentation_standards.md` — the validator check names, their tests and negative fixtures, and the root entry rules.
