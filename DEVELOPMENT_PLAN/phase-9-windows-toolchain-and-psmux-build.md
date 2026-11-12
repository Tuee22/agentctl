# Phase 9 — Windows toolchain and psmux build

**Status**: Planned
**Depends on**: [Phase 8 — Recovery and supervisor](phase-8-recovery-and-supervisor.md)
**Host lane**: linux-windows
**Gate**: `agentctl check`
**Gate kind**: self-verifying
**Closes**: R23

> **Purpose**: Haskell prepares native Windows build dependencies and compiles pinned psmux sources locally.

## Phase Objective

Haskell prepares native Windows build dependencies and compiles pinned psmux sources locally. The Python wheel stays source-only; no separately published psmux binary, manual Rust setup or system psmux PATH selection substitutes for this contract.

This phase needs Linux and native Windows. Its receipts can come from separate runs with the same logical source/policy/prerequisite identity and separately verified lane-native artifact/toolchain identities; no other foreign hardware is required. The declared tests are executable contracts; an absent required test is unmet evidence, not existing proof. Acceptance-only test implementations belong to the prerequisite owner named in the inventory. Existing incompatible code is inventoried in the deletion ledger. No old implementation or unqualified receipt establishes this revised contract.

## Gate Integrity

| Requirement | Oracle | Observer | Mutants | Tests |
|---|---|---|---|---|
| R23 — Private Rust and native Windows prerequisites | `tests/oracles/backend_profiles.toml` | value; observer: independent inputs and nonce-bound native observations | `M-rust-global-default-changed`, `M-msvc-presence-without-link-probe` | `haskell:agentctl-core-test/WindowsProvision/pure-plan-controls`, `tests/integration/test_windows_toolchain.py::test_private_rust_and_native_link_probe`, `tests/integration/test_windows_toolchain.py::test_install_refusals_and_restart_required` |
| R23 — Pinned source acquisition and bounded extraction | `tests/oracles/backend_profiles.toml` | value; observer: independent inputs and nonce-bound native observations | `M-source-digest-unchecked`, `M-archive-path-escape`, `M-cargo-floating-toolchain` | `tests/integration/test_psmux_source.py::test_archive_hash_and_escape_refusals`, `tests/integration/test_psmux_source.py::test_patch_and_lock_identity` |
| R23 — Idempotent native build and atomic publication | `tests/oracles/backend_profiles.toml` | value; observer: independent inputs and nonce-bound native observations | `M-psmux-warm-rebuild`, `M-psmux-partial-promoted` | `tests/integration/test_psmux_build.py::test_cold_warm_and_concurrent_build`, `tests/integration/test_psmux_build.py::test_failure_preserves_previous_artifact` |

## Not Proven By This Gate

- A receipt's digest establishes input currency, not an independently attested historical run. Local receipt authenticity has the documented honest ceiling.
- A source rule or finite corpus does not prove arbitrary callback purity, universal termination or agent-internal readiness. Native operation and resource assumptions remain explicit.
- WSL is Linux evidence only. A Windows source revision or same-version banner is not proof that a running server or client contains the accepted fixes.

## Sprints

### Sprint 9.1: Private Rust and native Windows prerequisites [Planned]

**Status**: Planned
**Implementation**: `src/agentctl/haskell/src/AgentCtl/Provision/Windows.hs`, `src/agentctl/haskell/src/AgentCtl/Provision/Rust.hs`
**Validation tests**: `haskell:agentctl-core-test/WindowsProvision/pure-plan-controls`, `tests/integration/test_windows_toolchain.py::test_private_rust_and_native_link_probe`, `tests/integration/test_windows_toolchain.py::test_install_refusals_and_restart_required`
**Mutants**: `M-rust-global-default-changed`, `M-msvc-presence-without-link-probe`
**Closes**: none
**Docs to update**: `documents/engineering/toolchain_bootstrap.md`, `documents/engineering/binary_build.md`, `documents/reference/files_and_state.md`, `documents/reference/external_tool_facts.md`

#### Objective

Private Rust and native Windows prerequisites supplies its complete owned contract through the single phase-scoped gate verdict.

#### Deliverables

Probe actual native compiler/linker/resource capability. Reuse qualifying MSVC/SDK read-only; otherwise prepare an explicit consent/elevation plan. Provision pinned private rustup/Rust/Cargo roots without PATH/profile/default changes. Missing elevation, policy, installer busy or restart-required outcomes remain named unmet readiness; no installer dialog or reboot is answered.

#### Validation

Linux runs the complete pure plan/refusal corpus; native Windows proves compiler/linker/resource and private toolchain behavior from prepared fixtures. Outer provisioning receipts prove actual cold installation outside tests. Standard user and restart-required twins publish no ready toolchain and preserve existing user tool selections.

Required executable evidence: `haskell:agentctl-core-test/WindowsProvision/pure-plan-controls`, `tests/integration/test_windows_toolchain.py::test_private_rust_and_native_link_probe`, `tests/integration/test_windows_toolchain.py::test_install_refusals_and_restart_required`. Every named mutant must die for its recorded reason in those tests; a baseline failure or unrelated exception is not a kill.

#### Remaining Work

The whole sprint.

### Sprint 9.2: Pinned source acquisition and bounded extraction [Planned]

**Status**: Planned
**Implementation**: `src/agentctl/haskell/src/AgentCtl/Provision/Source.hs`, `src/agentctl/haskell/resources/psmux/`
**Validation tests**: `tests/integration/test_psmux_source.py::test_archive_hash_and_escape_refusals`, `tests/integration/test_psmux_source.py::test_patch_and_lock_identity`
**Mutants**: `M-source-digest-unchecked`, `M-archive-path-escape`, `M-cargo-floating-toolchain`
**Closes**: none
**Docs to update**: `documents/engineering/toolchain_bootstrap.md`, `documents/engineering/binary_build.md`, `documents/reference/files_and_state.md`, `documents/reference/external_tool_facts.md`

#### Objective

Pinned source acquisition and bounded extraction supplies its complete owned contract through the single phase-scoped gate verdict.

#### Deliverables

Fetch the official archive with Haskell HTTPS/archive libraries, verify its digest, reject traversal/reparse/link/size violations and apply exact content-bound patches. Source revision 063ca7026eb2b7b91a74d3f858bdec3dfc841dbb is the initial candidate baseline, not an accepted artifact by declaration. Include Cargo.lock, local workspace crates, toolchain/SDK and patch identities in the build key; override moving source toolchain defaults.

#### Validation

Serve independent archive twins and require bad hashes, escaping entries and mismatched patches to fail before publication. Build outside any enclosing Git tree so provenance cannot come from an unrelated repository. A warm prepared source needs no Git, fetch CLI or network.

Required executable evidence: `tests/integration/test_psmux_source.py::test_archive_hash_and_escape_refusals`, `tests/integration/test_psmux_source.py::test_patch_and_lock_identity`. Every named mutant must die for its recorded reason in those tests; a baseline failure or unrelated exception is not a kill.

#### Remaining Work

The whole sprint.

### Sprint 9.3: Idempotent native build and atomic publication [Planned]

**Status**: Planned
**Implementation**: `src/agentctl/haskell/src/AgentCtl/Provision/Psmux.hs`, `src/agentctl/haskell/src/AgentCtl/Provision/Artifact.hs`
**Validation tests**: `tests/integration/test_psmux_build.py::test_cold_warm_and_concurrent_build`, `tests/integration/test_psmux_build.py::test_failure_preserves_previous_artifact`
**Mutants**: `M-psmux-warm-rebuild`, `M-psmux-partial-promoted`
**Closes**: R23
**Docs to update**: `documents/engineering/toolchain_bootstrap.md`, `documents/engineering/binary_build.md`, `documents/reference/files_and_state.md`, `documents/reference/external_tool_facts.md`

#### Objective

Idempotent native build and atomic publication supplies its complete owned contract through the single phase-scoped gate verdict.

#### Deliverables

Build natively through private pinned Cargo with locked dependencies and measured resource/path budgets. Record source+patch/build input identity and all executable hashes; verify the staged candidate identity and atomically publish an immutable candidate version directory. Build verification grants no runtime qualification or automatic-input capability. The generic builder takes an immutable recipe value; profile-specific patch bytes are consumer inputs, not retroactive builder-phase source. Keep one stable private runtime registry independent of build revision.

#### Validation

Native Windows cold build produces the manifest and genuine executable, a warm run spawns no installer/fetch/build, and concurrent calls reuse the winner. Failure leaves the prior build-verified candidate unchanged. Linux validates plan/digest/archive contracts without pretending to execute Windows binaries.

Required executable evidence: `tests/integration/test_psmux_build.py::test_cold_warm_and_concurrent_build`, `tests/integration/test_psmux_build.py::test_failure_preserves_previous_artifact`. Every named mutant must die for its recorded reason in those tests; a baseline failure or unrelated exception is not a kill.

#### Remaining Work

The whole sprint.

## Remaining Work

The whole phase: Sprints 9.1–9.3.

## Documentation Requirements

**Architecture docs to create/update:**

- None.

**Engineering docs to create/update:**

- `documents/engineering/toolchain_bootstrap.md` — doctrine, mechanisms and scope of executable evidence.
- `documents/engineering/binary_build.md` — doctrine, mechanisms and scope of executable evidence.

**Operations and reference docs to create/update:**

- `documents/reference/files_and_state.md` — preparation, qualified host observations and actionable refusals.
- `documents/reference/external_tool_facts.md` — preparation, qualified host observations and actionable refusals.

**Cross-references to add:**

- `DEVELOPMENT_PLAN/00-overview.md` — requirement closure and lower-phase dependencies.
- `DEVELOPMENT_PLAN/system-components.md` — stable capability/path ownership.
- `DEVELOPMENT_PLAN/legacy_tracking_for_deletion.md` — remaining incompatible implementation shapes.
