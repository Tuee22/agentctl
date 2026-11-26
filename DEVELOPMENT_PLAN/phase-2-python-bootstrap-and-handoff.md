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
| R3 — Minimal bootstrap and verified toolchain | `tests/oracles/requirements.toml` | value: independent expected values for the owned pure contract; observer: independent inputs and nonce-bound native observations | `M-bootstrap-unverified-download`, `M-bootstrap-user-default-changed` | `tests/unit/test_plan.py::test_plan_oracle`, `tests/integration/test_ghcup.py::test_truncated_download_leaves_nothing`, `tests/integration/test_toolchain.py::test_warm_run_spawns_only_version_checks` |
| R2 — Digest build, packaging and raw transport | `tests/oracles/requirements.toml` | value: independent expected values for the owned pure contract; observer: independent inputs and nonce-bound native observations | `M-boot-early-child-exit-zero`, `M-boot-native-consent-not-validated`, `M-boot-old-protocol-accepted`, `M-boot-native-consent-dropped`, `M-boot-native-consent-forged`, `M-boot-native-tail-drops-empty`, `M-boot-foundation-digest-omitted`, `M-boot-foundation-imports-later-protocol`, `M-boot-handshake-refuses-empty-commands`, `M-boot-handshake-imports-later-terminal`, `M-boot-transport-fixture-imports-later-mux`, `M-boot-caller-imports-later-launch`, `M-cache-hit-ignored`, `M-cache-nonatomic-publish`, `M-handoff-consent-in-agent-tail` | `tests/integration/test_build_boundaries.py::test_parent_resolves_selected_native_artifacts`, `tests/integration/test_build_boundaries.py::test_native_artifact_change_preserves_suite_failure`, `tests/integration/test_haskell_legs.py::test_direct_invocation_refused`, `tests/unit/test_digest.py::test_old_protocol_handshake_is_rejected`, `tests/integration/test_bootstrap_foundation.py::test_bootstrap_cli_consent_is_separate_from_tail`, `tests/integration/test_bootstrap_foundation.py::test_bootstrap_native_receiver_preserves_raw_tail`, `tests/integration/test_bootstrap_foundation.py::test_bootstrap_protocol_build_is_independent`, `tests/integration/test_bootstrap_caller.py::test_child_transfer_preserves_exit_without_launch`, `tests/integration/test_bootstrap_caller.py::test_early_transport_does_not_import_later_helpers`, `tests/integration/test_build_cache.py::test_second_run_spawns_nothing`, `tests/integration/test_passthrough.py::test_passthrough_table_equals_binary_commands`, `tests/integration/test_handoff.py::test_child_mode_propagates_exit_status`, `tests/integration/test_bootstrap_consent.py::test_typed_handoff_consent`, `tests/unit/test_digest.py::test_foundation_changes_binary_digest`, `tests/unit/test_digest.py::test_inventory_and_protocol_boundaries`, `tests/integration/test_build_cache.py::test_failed_build_keeps_previous` |
| R14 — Native quality legs and bootstrap isolation | `tests/oracles/requirements.toml` | value: independent expected values for the owned pure contract; observer: independent inputs and nonce-bound native observations | `M-boot-foundation-style-omitted`, `M-legs-native-suite-omitted`, `M-build-native-artifact-change-ignored`, `M-build-owned-root-unregistered` | `tests/integration/test_haskell_legs.py::test_failed_native_suite_preserves_case_observation`, `tests/integration/test_haskell_legs.py::test_werror_fires`, `tests/integration/test_haskell_style_legs.py::test_hlint_fires`, `tests/integration/test_static_legs.py::test_raw_link_rule_exception_is_narrow`, `tests/integration/test_owned_resources.py::test_short_native_workspace_budget`, `tests/unit/test_style_tools.py::test_style_identity_and_install_arguments`, `tests/integration/test_build_boundaries.py::test_native_artifact_change_preserves_suite_failure` |

## Not Proven By This Gate

- A receipt's digest establishes input currency, not an independently attested historical run. Local receipt authenticity has the documented honest ceiling.
- A source rule or finite corpus does not prove arbitrary callback purity, universal termination or agent-internal readiness. Native operation and resource assumptions remain explicit.
- Foreign-kernel behavior is outside this phase's Linux verdict. Later native implementation extends the common contract and cannot retroactively add a foreign-hardware requirement here.

## Sprints

### Sprint 2.1: Minimal bootstrap and verified toolchain [Planned]

**Status**: Planned
**Implementation**: `src/agentctl/bootstrap/`, `src/agentctl/hostfacts.py`, `src/agentctl/paths.py`, `src/agentctl/foundation_paths.py`, `src/agentctl/foundation_host.py`
**Validation tests**: `tests/unit/test_plan.py::test_plan_oracle`, `tests/integration/test_ghcup.py::test_truncated_download_leaves_nothing`, `tests/integration/test_toolchain.py::test_warm_run_spawns_only_version_checks`, `tests/unit/test_prerequisite_readiness.py::test_prerequisite_inspection_consent_and_privilege`, `tests/unit/test_prerequisite_readiness.py::test_prerequisite_inspection_platforms_and_errors`, `tests/integration/test_hostfacts.py::test_native_context_and_numeric_failure`, `tests/integration/test_prereqs_consent.py::test_declined_spawns_nothing`, `tests/integration/test_prereqs_real.py::test_probe_matches_independent_observer`, `tests/integration/test_toolchain_real.py::test_resolved_ghc_reports_pin`, `tests/unit/test_ghcup.py::test_pins_match_oracle`, `tests/unit/test_hostfacts.py::test_ghcup_discovery_order`, `tests/unit/test_prereqs.py::test_package_sets_match_oracle`, `tests/unit/test_toolchain.py::test_apply_sequence_and_verified_record`, `tests/unit/test_toolchain_gate.py::test_storage_budget_values`
**Mutants**: `M-bootstrap-unverified-download`, `M-bootstrap-user-default-changed`, `M-boot-cabal-without-no-set`, `M-boot-ghc-from-path`, `M-boot-ghcup-on-warm-run`, `M-boot-ghcup-prefix-ignored`, `M-boot-links-unchecked`, `M-boot-reinstall-present`, `M-boot-replace-old-ghcup`, `M-boot-spawn-adds-set`, `M-build-drop-werror`, `M-build-eval-drops-case`, `M-build-handoff-unchecked`, `M-build-handshake-drops-commands`, `M-build-routing-blind`, `M-build-tests-disabled`, `M-build-user-cabal-dir`, `M-cache-digest-includes-style-config`, `M-cache-digest-omits-cabal-file`, `M-cache-identity-unchecked`, `M-cache-skip-handshake`, `M-evidence-startup-bytecode`, `M-ghcup-edits-rc`, `M-ghcup-nonatomic-write`, `M-ghcup-overwrite-existing`, `M-ghcup-skip-verify`, `M-pass-binary-runs-without-protocol`, `M-pass-child-exit-zero`, `M-pass-click-parses-tail`, `M-pass-progname-core`, `M-pass-rebuild-on-hit`, `M-pass-split-drops-empty`, `M-pass-table-drops-command`, `M-pass-windows-execve`, `M-pins-digest-swapped`, `M-prereq-flag-dropped`, `M-prereq-gmp-dropped`, `M-prereq-probe-ignores-link`, `M-prereq-prompt-without-tty`, `M-prereq-skip-consent`, `M-prereq-sudo-may-prompt`, `M-style-hlint-exit-ignored`, `M-style-hlint-ignore-allowed`, `M-style-reinstall-always`, `M-style-tools-from-path`
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
**Implementation**: `src/agentctl/cli.py`, `src/agentctl/bootstrap/binary.py`, `src/agentctl/bootstrap/handoff.py`, `src/agentctl/haskell/`, `tests/harness/bootstrap_caller.py`, `tests/harness/transport_fixture.py`, `tests/harness/passthrough.py`, `tests/harness/terminal.py`
**Validation tests**: `tests/integration/test_build_boundaries.py::test_parent_resolves_selected_native_artifacts`, `tests/integration/test_build_boundaries.py::test_native_artifact_change_preserves_suite_failure`, `tests/integration/test_haskell_legs.py::test_direct_invocation_refused`, `tests/unit/test_digest.py::test_old_protocol_handshake_is_rejected`, `tests/integration/test_bootstrap_foundation.py::test_bootstrap_cli_consent_is_separate_from_tail`, `tests/integration/test_bootstrap_foundation.py::test_bootstrap_native_receiver_preserves_raw_tail`, `tests/integration/test_bootstrap_foundation.py::test_bootstrap_protocol_build_is_independent`, `tests/integration/test_bootstrap_caller.py::test_child_transfer_preserves_exit_without_launch`, `tests/integration/test_bootstrap_caller.py::test_early_transport_does_not_import_later_helpers`, `tests/integration/test_bootstrap_caller.py::test_bootstrap_caller_import_without_later_helpers`, `tests/integration/test_bootstrap_caller.py::test_published_caller_without_launch_fixture`, `tests/integration/test_build_cache.py::test_second_run_spawns_nothing`, `tests/integration/test_passthrough.py::test_passthrough_table_equals_binary_commands`, `tests/integration/test_handoff.py::test_child_mode_propagates_exit_status`, `tests/integration/test_bootstrap_consent.py::test_typed_handoff_consent`, `tests/integration/test_binary_boundaries.py::test_source_pin_and_toolchain_failures`, `tests/integration/test_bootstrap_origin.py::test_absence_record_precedes_first_file`, `tests/integration/test_build_boundaries.py::test_native_command_and_artifact_failures`, `tests/integration/test_eval_executable.py::test_every_case_answered`, `tests/integration/test_python_startup.py::test_startup_precedes_editable_imports`, `tests/unit/test_cli.py::test_cli_is_click_group`, `tests/unit/test_digest.py::test_foundation_changes_binary_digest`, `tests/unit/test_digest.py::test_inventory_and_protocol_boundaries`, `tests/unit/test_digest.py::test_oracle_rows`, `tests/unit/test_handoff.py::test_handoff_mode_by_os_family`, `tests/unit/test_paths.py::test_xdg_overrides_on_every_os`, `tests/integration/test_command_surface.py::test_cli_reference_joins_click_and_handshake`, `tests/unit/test_passthrough.py::test_passthrough_table_matches_oracle`, `tests/unit/test_passthrough.py::test_every_command_but_check_passes_through`, `tests/unit/test_passthrough.py::test_raw_tail_keeps_dashdash_and_help`
**Mutants**: `M-boot-early-child-exit-zero`, `M-boot-native-consent-not-validated`, `M-boot-old-protocol-accepted`, `M-boot-native-consent-dropped`, `M-boot-native-consent-forged`, `M-boot-native-tail-drops-empty`, `M-boot-foundation-digest-omitted`, `M-boot-foundation-imports-later-protocol`, `M-boot-handshake-refuses-empty-commands`, `M-boot-handshake-imports-later-terminal`, `M-boot-transport-fixture-imports-later-mux`, `M-boot-caller-imports-later-launch`, `M-cache-hit-ignored`, `M-cache-nonatomic-publish`, `M-handoff-consent-in-agent-tail`
**Closes**: R2, R5, R6
**Docs to update**: `documents/architecture/python_haskell_boundary.md`, `documents/engineering/toolchain_bootstrap.md`, `documents/engineering/binary_build.md`, `documents/operations/installation.md`

#### Objective

Digest build, packaging and raw transport supplies its complete owned contract through the single phase-scoped gate verdict.

#### Deliverables

Ship Haskell sources as package data, lock per input digest, build through the application-owned path and atomically publish a handshake-verified binary. Separate the transport observer and bootstrap handshake audit from later launch and whole-product command helpers, preserving both observations and proving the lower contract remains usable. Forward raw arguments and bootstrap consent as separate typed protocol data. The handshake enumerates only real introduced commands, possibly no product commands at this boundary; it never advertises future stub handlers. Haskell owns runtime distribution detection; Python carries no tmux/psmux/Rust/agent policy.

#### Validation

Change sources/pins and require distinct builds; unchanged inputs reuse the winner under contention. Reject an incomplete publish and preserve the previous artifact. A native test receiver independently observes raw transport of --, empty values, hostile text and a tail --assume-yes without invoking a later product command; the global option authorizes only the typed provisioning policy.

Required executable evidence: `tests/integration/test_build_cache.py::test_second_run_spawns_nothing`, `tests/integration/test_passthrough.py::test_passthrough_table_equals_binary_commands`, `tests/integration/test_handoff.py::test_child_mode_propagates_exit_status`, `tests/integration/test_bootstrap_consent.py::test_typed_handoff_consent`. Every named mutant must die for its recorded reason in those tests; a baseline failure or unrelated exception is not a kill.

#### Remaining Work

The whole sprint.

### Sprint 2.3: Native quality legs and bootstrap isolation [Planned]

**Status**: Planned
**Implementation**: `src/agentctl/haskell/test/TestSource.hs`, `src/agentctl/check/haskell.py`, `src/agentctl/check/style.py`, `src/agentctl/bootstrap/build.py`, `tests/lanes/`
**Validation tests**: `tests/integration/test_haskell_legs.py::test_native_leg_execution_and_failures`, `tests/integration/test_haskell_legs.py::test_native_case_sources_match_compiled_callsites`, `tests/unit/test_haskell_gate.py::test_native_source_listing_requires_exact_cases`, `tests/unit/test_haskell_gate.py::test_native_source_record_joins_guarded_files`, `tests/integration/test_haskell_legs.py::test_werror_fires`, `tests/integration/test_haskell_style_legs.py::test_hlint_fires`, `tests/integration/test_static_legs.py::test_raw_link_rule_exception_is_narrow`, `tests/integration/test_owned_resources.py::test_short_native_workspace_budget`, `tests/governance/test_style_config.py::test_style_configs_have_no_ignores`, `tests/integration/test_haskell_mutations.py::test_native_edge_vetoes`, `tests/integration/test_style_cache.py::test_tools_publish_together_and_keep_existing`, `tests/unit/test_haskell_gate.py::test_failed_native_cases_are_retained_without_passing`, `tests/unit/test_haskell_gate.py::test_closed_components_and_listings`, `tests/unit/test_style_tools.py::test_style_identity_and_install_arguments`
**Mutants**: `M-build-native-source-census-omitted`, `M-build-native-report-comparison-omitted`, `M-boot-foundation-style-omitted`, `M-legs-native-suite-omitted`, `M-build-native-artifact-change-ignored`, `M-build-owned-root-unregistered`
**Closes**: R14
**Docs to update**: `documents/architecture/python_haskell_boundary.md`, `documents/engineering/toolchain_bootstrap.md`, `documents/engineering/binary_build.md`, `documents/operations/installation.md`

#### Objective

Native quality legs and bootstrap isolation supplies its complete owned contract through the single phase-scoped gate verdict.

#### Deliverables

Introduce tests/integration/test_release_install.py with generic source-only installed-package/introduced-resource controls, consumed by final acceptance. The native protocol data now builds as an internal library without later product modules and participates in the native style census. Complete the early handoff policy and native transport-test components so their source/import closure contains no later product module. Later libraries and the complete product executable are additive components, not placeholder handlers in this early subject. Add the native build/test/style legs to the same complete gate and verify nonempty suite routing. Allocate short registered native workspaces by an executable path budget; keep package sources and the checkout unwritten. A lock retains its inode while held.

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
