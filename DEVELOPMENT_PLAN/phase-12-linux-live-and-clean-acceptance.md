# Phase 12 — Linux live and clean acceptance

**Status**: Planned
**Depends on**: [Phase 8 — Recovery and supervisor](phase-8-recovery-and-supervisor.md)
**Host lane**: linux-live-clean
**Gate**: `agentctl check`
**Gate kind**: host-acceptance
**Closes**: R1, R25
**Gate evidence**: none recorded
**Evidence covers**: phase input closure and verified prerequisite receipts

> **Purpose**: Debian clean-host and logged-in agent acceptance, with dedicated WSL2 permitted for Linux evidence on a Windows host.

## Phase Objective

Debian clean-host and logged-in agent acceptance, with dedicated WSL2 permitted for Linux evidence on a Windows host. Actual preparation occurs before the noninteractive gate and is bound to its subject; a copied checkout or commit cannot bridge host and guest state.

This phase needs Debian Linux, its clean-host preparation and authenticated live lane. Dedicated WSL2 can supply Linux evidence under the runbook's binding and capacity rules. The declared tests are executable contracts; an absent required test is unmet evidence, not existing proof. Acceptance-only test implementations belong to the prerequisite owner named in the inventory. Existing incompatible code is inventoried in the deletion ledger. No old implementation or unqualified receipt establishes this revised contract.

## Gate Integrity

| Requirement | Oracle | Observer | Mutants | Tests |
|---|---|---|---|---|
| R25 — Dedicated WSL2 and checkout binding | `tests/oracles/requirements.toml` | real: independent inputs and nonce-bound native observations | none — native positive/refusing twins | `tests/integration/test_wsl_binding.py::test_shared_checkout_identity`, `tests/integration/test_wsl_binding.py::test_capacity_and_dependency_receipt` |
| R1 — Two-stage clean Debian bootstrap | `tests/oracles/requirements.toml` | real: independent inputs and nonce-bound native observations | none — native positive/refusing twins | `tests/e2e/test_fresh_bootstrap.py::test_ghcup_digest_matches_pin`, `tests/integration/test_clean_runtime.py::test_pipx_to_haskell_to_apt_tmux` |
| R1 — Authenticated no-input live acceptance | `tests/oracles/requirements.toml` | real: independent inputs and nonce-bound native observations | none — native positive/refusing twins | `tests/live/test_live_launch.py::test_live_launch`, `tests/live/test_live_classification.py::test_live_screen_classes`, `tests/live/test_live_supervisor.py::test_live_supervisor_never_sends` |

## Not Proven By This Gate

- A receipt's digest establishes input currency, not an independently attested historical run. Local receipt authenticity has the documented honest ceiling.
- A source rule or finite corpus does not prove arbitrary callback purity, universal termination or agent-internal readiness. Native operation and resource assumptions remain explicit.

## Confirms

- Native Debian or the dedicated bound WSL2 instance confirms source-built bootstrap and Haskell APT provisioning; existing logged-in agents supply no-input live observations.
- Clean and live receipts have separate explicit predicates; logged-out refusal does not claim authenticated evidence.

## Sprints

### Sprint 12.1: Dedicated WSL2 and checkout binding [Planned]

**Status**: Planned
**Implementation**: none — this sprint records acceptance evidence
**Validation tests**: `tests/integration/test_wsl_binding.py::test_shared_checkout_identity`, `tests/integration/test_wsl_binding.py::test_capacity_and_dependency_receipt`
**Mutants**: none — native positive/refusing twins
**Closes**: R25
**Docs to update**: `documents/operations/installation.md`, `documents/operations/validation_runbook.md`, `documents/engineering/testing.md`

#### Objective

Dedicated WSL2 and checkout binding supplies its complete owned contract through the single phase-scoped gate verdict.

#### Deliverables

When using Windows, use an agentctl-only Debian WSL2 instance with recorded CPU/memory/disk allocation, measured free capacity and all Linux dependencies. Bind mount the live Windows checkout into its Linux workspace; verify mountinfo, source identity and bidirectional nonce visibility, including uncommitted/untracked state. Native Debian uses its own corresponding host identity.

#### Validation

For the WSL2 route require a real bind mount and fail a symlink, copy, stale guest tree or different HEAD/content pairing. Native Debian instead records its direct checkout identity and exercises the WSL policy through constructed facts; it requires no Windows machine. Resource limits must cover measured build/test peak plus explicit headroom without starving Windows; disk/commit insufficiency is an unmet lane. Do not change global WSL settings or shut down unrelated distributions.

Required executable evidence: `tests/integration/test_wsl_binding.py::test_shared_checkout_identity`, `tests/integration/test_wsl_binding.py::test_capacity_and_dependency_receipt`. Positive and refusing native controls retain independent expected outputs and actual resource observations.

#### Remaining Work

The whole sprint.

### Sprint 12.2: Two-stage clean Debian bootstrap [Planned]

**Status**: Planned
**Implementation**: none — this sprint records acceptance evidence
**Validation tests**: `tests/e2e/test_fresh_bootstrap.py::test_ghcup_digest_matches_pin`, `tests/integration/test_clean_runtime.py::test_pipx_to_haskell_to_apt_tmux`
**Mutants**: none — native positive/refusing twins
**Closes**: R1
**Docs to update**: `documents/operations/installation.md`, `documents/operations/validation_runbook.md`, `documents/engineering/testing.md`

#### Objective

Two-stage clean Debian bootstrap supplies its complete owned contract through the single phase-scoped gate verdict.

#### Deliverables

Stage A records absent toolchains and tmux, installs Python build prerequisites through the real bootstrap and prepares tmux through Haskell under explicit consent. Stage B runs the unchanged noninteractive gate with package-manager vetoes. Isolated agent installation is host preparation; application code never installs agent CLIs.

#### Validation

Require actual native toolchain/build and tmux preparation receipts bound to source inputs and host, then full owned tests and immutable warm reuse. A fabricated JSON receipt without matching executable/observed state fails; receipt provenance has the documented local-attestation ceiling.

Required executable evidence: `tests/e2e/test_fresh_bootstrap.py::test_ghcup_digest_matches_pin`, `tests/integration/test_clean_runtime.py::test_pipx_to_haskell_to_apt_tmux`. Positive and refusing native controls retain independent expected outputs and actual resource observations.

#### Remaining Work

The whole sprint.

### Sprint 12.3: Authenticated no-input live acceptance [Planned]

**Status**: Planned
**Implementation**: none — this sprint records acceptance evidence
**Validation tests**: `tests/live/test_live_launch.py::test_live_launch`, `tests/live/test_live_classification.py::test_live_screen_classes`, `tests/live/test_live_supervisor.py::test_live_supervisor_never_sends`
**Mutants**: none — native positive/refusing twins
**Closes**: none
**Docs to update**: `documents/operations/installation.md`, `documents/operations/validation_runbook.md`, `documents/engineering/testing.md`

#### Objective

Authenticated no-input live acceptance supplies its complete owned contract through the single phase-scoped gate verdict.

#### Deliverables

Use existing authenticated Linux agents only in the fixed live-acceptance folder with updates disabled and no answered dialogs. Credentials copied to dedicated WSL state retain restricted permissions and leave host originals intact. Logged-out controls remain tested but do not qualify the live lane.

#### Validation

Observe real agent processes, exact launch configuration and safe classes without sending prompts. A missing authentication/capability remains unmet and cannot become a passing live receipt through a documented fixture or manual confirmation.

Required executable evidence: `tests/live/test_live_launch.py::test_live_launch`, `tests/live/test_live_classification.py::test_live_screen_classes`, `tests/live/test_live_supervisor.py::test_live_supervisor_never_sends`. Positive and refusing native controls retain independent expected outputs and actual resource observations.

#### Remaining Work

The whole sprint.

## Remaining Work

The whole phase: Sprints 12.1–12.3.

## Documentation Requirements

**Architecture docs to create/update:**

- None.

**Engineering docs to create/update:**

- `documents/engineering/testing.md` — doctrine, mechanisms and scope of executable evidence.

**Operations and reference docs to create/update:**

- `documents/operations/installation.md` — preparation, qualified host observations and actionable refusals.
- `documents/operations/validation_runbook.md` — preparation, qualified host observations and actionable refusals.

**Cross-references to add:**

- `DEVELOPMENT_PLAN/00-overview.md` — requirement closure and lower-phase dependencies.
- `DEVELOPMENT_PLAN/system-components.md` — stable capability/path ownership.
- `DEVELOPMENT_PLAN/legacy_tracking_for_deletion.md` — remaining incompatible implementation shapes.
