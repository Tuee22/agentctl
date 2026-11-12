# Phase 2 — Python bootstrap and handoff

**Status**: Planned
**Depends on**: [Phase 1 — Python discipline and gate integrity](phase-1-python-discipline-and-gate-integrity.md)
**Host lane**: linux
**Gate**: `agentctl check`
**Gate kind**: self-verifying
**Closes**: R2, R3, R4, R5, R6, R14

> **Purpose**: A portable pipx/Click entry point and only the Python work needed before Haskell exists: bootstrap directories, pinned ghcup/GHC/cabal, native source build and raw handoff.

## Phase Objective

A portable pipx/Click entry point and only the Python work needed before Haskell exists: bootstrap directories, pinned ghcup/GHC/cabal, native source build and raw handoff. The Haskell package includes the runtime primitives and data contracts needed by later additive features, with no placeholder runtime commands.

This phase needs Linux only. The declared tests are executable contracts; an absent required test is unmet evidence, not existing proof. Acceptance-only test implementations belong to the prerequisite owner named in the inventory. Existing incompatible code is inventoried in the deletion ledger. No old implementation or unqualified receipt establishes this revised contract.

## Gate Integrity

| Requirement | Oracle | Observer | Mutants | Tests |
|---|---|---|---|---|
| R3 — Minimal bootstrap and verified toolchain | `tests/oracles/requirements.toml` | value; observer: independent inputs and nonce-bound native observations | `M-bootstrap-unverified-download`, `M-bootstrap-user-default-changed` | `tests/unit/test_plan.py::test_plan_oracle`, `tests/integration/test_ghcup.py::test_truncated_download_leaves_nothing`, `tests/integration/test_toolchain.py::test_warm_run_spawns_only_version_checks` |
| R2 — Digest build, packaging and raw transport | `tests/oracles/requirements.toml` | value; observer: independent inputs and nonce-bound native observations | `M-cache-hit-ignored`, `M-cache-nonatomic-publish`, `M-handoff-consent-in-agent-tail` | `tests/integration/test_build_cache.py::test_second_run_spawns_nothing`, `tests/integration/test_passthrough.py::test_passthrough_table_equals_binary_commands`, `tests/integration/test_handoff.py::test_child_mode_propagates_exit_status`, `tests/integration/test_bootstrap_consent.py::test_typed_handoff_consent` |
| R14 — Native quality legs and bootstrap isolation | `tests/oracles/requirements.toml` | value; observer: independent inputs and nonce-bound native observations | `M-legs-native-suite-omitted`, `M-build-owned-root-unregistered` | `tests/integration/test_haskell_legs.py::test_werror_fires`, `tests/integration/test_haskell_style_legs.py::test_hlint_fires`, `tests/integration/test_static_legs.py::test_raw_link_rule_exception_is_narrow`, `tests/integration/test_owned_resources.py::test_short_native_workspace_budget` |

## Not Proven By This Gate

- A receipt's digest establishes input currency, not an independently attested historical run. Local receipt authenticity has the documented honest ceiling.
- A source rule or finite corpus does not prove arbitrary callback purity, universal termination or agent-internal readiness. Native operation and resource assumptions remain explicit.
- Foreign-kernel behavior is outside this phase's Linux verdict. Later native implementation extends the common contract and cannot retroactively add a foreign-hardware requirement here.

## Sprints

### Sprint 2.1: Minimal bootstrap and verified toolchain [Planned]

**Status**: Planned
**Implementation**: `src/agentctl/bootstrap/`, `src/agentctl/hostfacts.py`, `src/agentctl/paths.py`
**Validation tests**: `tests/unit/test_plan.py::test_plan_oracle`, `tests/integration/test_ghcup.py::test_truncated_download_leaves_nothing`, `tests/integration/test_toolchain.py::test_warm_run_spawns_only_version_checks`
**Mutants**: `M-bootstrap-unverified-download`, `M-bootstrap-user-default-changed`
**Closes**: R3, R4
**Docs to update**: `documents/architecture/python_haskell_boundary.md`, `documents/engineering/toolchain_bootstrap.md`, `documents/engineering/binary_build.md`, `documents/operations/installation.md`

#### Objective

Minimal bootstrap and verified toolchain supplies its complete owned contract through the single phase-scoped gate verdict.

#### Deliverables

Keep only Haskell-build prerequisites and toolchain work in Python. Reuse suitable installed tools without changing defaults; otherwise fetch digest-verified pinned assets and install missing pins. Reject unsupported bootstrap hosts before host mutation. Download/build state is private and bounded.

#### Validation

Compare pure plan rows with independent expectations. Require verified downloads, warm no-install behavior, named refusals and unchanged shell profiles/default selection. Native Windows and Darwin bootstrap confirmation are separate receipts, not prerequisites for this Linux verdict.

Required executable evidence: `tests/unit/test_plan.py::test_plan_oracle`, `tests/integration/test_ghcup.py::test_truncated_download_leaves_nothing`, `tests/integration/test_toolchain.py::test_warm_run_spawns_only_version_checks`. Every named mutant must die for its recorded reason in those tests; a baseline failure or unrelated exception is not a kill.

#### Remaining Work

The whole sprint.

### Sprint 2.2: Digest build, packaging and raw transport [Planned]

**Status**: Planned
**Implementation**: `src/agentctl/cli.py`, `src/agentctl/bootstrap/binary.py`, `src/agentctl/bootstrap/handoff.py`, `src/agentctl/haskell/`
**Validation tests**: `tests/integration/test_build_cache.py::test_second_run_spawns_nothing`, `tests/integration/test_passthrough.py::test_passthrough_table_equals_binary_commands`, `tests/integration/test_handoff.py::test_child_mode_propagates_exit_status`, `tests/integration/test_bootstrap_consent.py::test_typed_handoff_consent`
**Mutants**: `M-cache-hit-ignored`, `M-cache-nonatomic-publish`, `M-handoff-consent-in-agent-tail`
**Closes**: R2, R5, R6
**Docs to update**: `documents/architecture/python_haskell_boundary.md`, `documents/engineering/toolchain_bootstrap.md`, `documents/engineering/binary_build.md`, `documents/operations/installation.md`

#### Objective

Digest build, packaging and raw transport supplies its complete owned contract through the single phase-scoped gate verdict.

#### Deliverables

Ship Haskell sources as package data, lock per input digest, build through the application-owned path and atomically publish a handshake-verified binary. Forward raw arguments and bootstrap consent as separate typed protocol data. The handshake enumerates only real introduced commands, possibly no product commands at this boundary; it never advertises future stub handlers. Haskell owns runtime distribution detection; Python carries no tmux/psmux/Rust/agent policy.

#### Validation

Change sources/pins and require distinct builds; unchanged inputs reuse the winner under contention. Reject an incomplete publish and preserve the previous artifact. A native test receiver independently observes raw transport of --, empty values, hostile text and a tail --assume-yes without invoking a later product command; the global option authorizes only the typed provisioning policy.

Required executable evidence: `tests/integration/test_build_cache.py::test_second_run_spawns_nothing`, `tests/integration/test_passthrough.py::test_passthrough_table_equals_binary_commands`, `tests/integration/test_handoff.py::test_child_mode_propagates_exit_status`, `tests/integration/test_bootstrap_consent.py::test_typed_handoff_consent`. Every named mutant must die for its recorded reason in those tests; a baseline failure or unrelated exception is not a kill.

#### Remaining Work

The whole sprint.

### Sprint 2.3: Native quality legs and bootstrap isolation [Planned]

**Status**: Planned
**Implementation**: `src/agentctl/check/haskell.py`, `src/agentctl/check/style.py`, `src/agentctl/bootstrap/build.py`, `tests/lanes/`
**Validation tests**: `tests/integration/test_haskell_legs.py::test_werror_fires`, `tests/integration/test_haskell_style_legs.py::test_hlint_fires`, `tests/integration/test_static_legs.py::test_raw_link_rule_exception_is_narrow`, `tests/integration/test_owned_resources.py::test_short_native_workspace_budget`
**Mutants**: `M-legs-native-suite-omitted`, `M-build-owned-root-unregistered`
**Closes**: R14
**Docs to update**: `documents/architecture/python_haskell_boundary.md`, `documents/engineering/toolchain_bootstrap.md`, `documents/engineering/binary_build.md`, `documents/operations/installation.md`

#### Objective

Native quality legs and bootstrap isolation supplies its complete owned contract through the single phase-scoped gate verdict.

#### Deliverables

Introduce tests/integration/test_release_install.py with generic source-only installed-package/introduced-resource controls, consumed by final acceptance. Factor actual protocol/foundation and native transport-test components so their source/import closure contains no later product module. Later libraries and the complete product executable are additive components, not placeholder handlers in this early subject. Add the native build/test/style legs to the same complete gate and verify nonempty suite routing. Allocate short registered native workspaces by an executable path budget; keep package sources and the checkout unwritten. A lock retains its inode while held.

#### Validation

Require real positive builds of the actual introduced foundation/transport components and named negative controls, rather than requiring a later product executable to compile. The gate still attempts every present component and attributes a later component failure to its owner and real consumers. A deep profile path or generated component suffix cannot bypass the path budget. Every external workspace is nonce-bound, snapshotted where applicable, waited for and included in containment before verified-path cleanup.

Required executable evidence: `tests/integration/test_haskell_legs.py::test_werror_fires`, `tests/integration/test_haskell_style_legs.py::test_hlint_fires`, `tests/integration/test_static_legs.py::test_raw_link_rule_exception_is_narrow`, `tests/integration/test_owned_resources.py::test_short_native_workspace_budget`. Every named mutant must die for its recorded reason in those tests; a baseline failure or unrelated exception is not a kill.

#### Remaining Work

The whole sprint.

## Remaining Work

The whole phase: Sprints 2.1–2.3.

## Documentation Requirements

**Architecture docs to create/update:**

- `documents/architecture/python_haskell_boundary.md` — this phase's owned contract and links to prerequisite interfaces.

**Engineering docs to create/update:**

- `documents/engineering/toolchain_bootstrap.md` — doctrine, mechanisms and scope of executable evidence.
- `documents/engineering/binary_build.md` — doctrine, mechanisms and scope of executable evidence.

**Operations and reference docs to create/update:**

- `documents/operations/installation.md` — preparation, qualified host observations and actionable refusals.

**Cross-references to add:**

- `DEVELOPMENT_PLAN/00-overview.md` — requirement closure and lower-phase dependencies.
- `DEVELOPMENT_PLAN/system-components.md` — stable capability/path ownership.
- `DEVELOPMENT_PLAN/legacy_tracking_for_deletion.md` — remaining incompatible implementation shapes.
