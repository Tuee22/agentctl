# Phase 9 — Windows toolchain and psmux build

**Status**: Planned
**Depends on**: [Phase 8 — Recovery and supervisor](phase-8-recovery-and-supervisor.md)
**Host lane**: linux-windows
**Gate**: `agentctl check`
**Gate kind**: self-verifying
**Closes**: R23, R23.1, R25.1, R28.1

> **Purpose**: The Windows entry of binder, receipt transport and native gate precedes Haskell preparation of native Windows build dependencies and local compilation of pinned psmux sources.

## Phase Objective

The Windows entry of binder, receipt transport and native gate precedes Haskell preparation of native Windows build dependencies and local compilation of pinned psmux sources. The Python wheel stays source-only; no separately published psmux binary, manual Rust setup or system psmux PATH selection substitutes for this contract. A Windows source revision or same-version banner is not proof that a running server or client contains the accepted fixes.

This phase's verdict evaluates the `linux` and `windows` halves ([T.V](development_plan_standards.md#tv-verdict) V8) at stage 2 ([T.W](development_plan_standards.md#tw-staged-enforcement)): a native Windows run evaluates the `windows` half and reads the `linux` half from the latest stored guest receipt with equal logical and prerequisite identities, and native tool and executable hashes are per-half sub-identities ([T.I](development_plan_standards.md#ti-identity)). Every cited artifact is owned within closure(9) ([§ A](development_plan_standards.md#a-well-ordered-constructive-narrative)), a planned absence is unmet work of this phase ([T.F](development_plan_standards.md#tf-shared-and-owned-failures)), and present incompatible code is a deletion-ledger row of its owner. This phase receives the Windows-host binder with its claims from [Governance and phase evidence](phase-0-governance-and-phase-evidence.md) by P0-12 and moves the binder nodes it then cites into a module it owns through killer-relocation records ([T.G](development_plan_standards.md#tg-governed-changes)), receives the Windows arms and native Windows coverage of host-declared Windows sources (D-137, D-140), the Windows arms of `Mux.hs` from [Debian tmux and multiplexer](phase-4-debian-tmux-and-multiplexer.md) (D-152) and the Windows multiplexer arm of the preflight warning from [Agent preflight and launch](phase-5-agent-preflight-and-launch.md) (D-157), keeps the binder behavior that earlier guest runs use ([§ A](development_plan_standards.md#a-well-ordered-constructive-narrative) A1) and owes no confirmation to a later phase. Its Haskell modules and native tests form this phase's own build component, discovered through the `cabal.project` package glob of [Python bootstrap and handoff](phase-2-python-bootstrap-and-handoff.md); it edits no earlier component ([§ A](development_plan_standards.md#a-well-ordered-constructive-narrative) A1, A2).

## Gate Integrity

| Requirement | Oracle | Observer | Mutants | Tests |
|---|---|---|---|---|
| R25.1 — Windows entry: binder, receipt transport and native gate | `tests/oracles/host_lanes.toml` | real: native Windows capability probes and gate entry on the named host; observer: nonce-bound receipt transport between the guest and host receipt stores | none — the binder's claims and the nodes that kill them arrive with P0-12 of Governance and phase evidence | `tests/integration/test_receipt_transport.py::test_stored_receipt_transport_preserves_identity`, `tests/integration/test_receipt_transport.py::test_transport_refuses_unverified_or_mismatched_receipt`, `tests/integration/test_windows_setup_probes.py::test_absent_capability_awaits_setup` |
| R23 — Private Rust, native prerequisites and pinned sources | `tests/oracles/backend_profiles.toml` | value: independent pure plan, refusal, archive-digest and patch-identity expectations; real: native compiler, linker, resource and private toolchain behavior on the named host; observer: nonce-bound archive-twin and publication-refusal observations | none — planned mutants are named in the Deliverables of this row's sprint until their corpus rows land, and the Windows multiplexer-arm mutants arrive with all their killers by D-152 | `haskell:agentctl-core-test/WindowsProvision/pure-plan-controls`, `tests/integration/test_windows_toolchain.py::test_private_rust_and_native_link_probe`, `tests/integration/test_windows_toolchain.py::test_install_refusals_and_restart_required`, `tests/integration/test_psmux_source.py::test_archive_hash_and_escape_refusals`, `tests/integration/test_psmux_source.py::test_patch_and_lock_identity` |
| R23 — Idempotent native build and atomic publication | `tests/oracles/backend_profiles.toml` | real: native cold, warm and concurrent builds and failure preservation on the named host; observer: nonce-bound publication and predecessor-preservation observations | none — planned mutants are named in the Deliverables of this row's sprint until their corpus rows land | `tests/integration/test_psmux_build.py::test_cold_warm_and_concurrent_build`, `tests/integration/test_psmux_build.py::test_failure_preserves_previous_artifact` |
| R28.1 — Non-disruptive native Windows runs | `tests/oracles/host_lanes.toml` | value: independent job, console and teardown cases; observer: native Windows spawn and effect records showing only run-owned resources | none — corpus rows land with their Remaining Work rows | `tests/integration/test_windows_containment.py::test_job_reaps_descendants` |
| R23.1 — Harness provisioning once per run | `tests/oracles/backend_profiles.toml` | value: independent provisioning-plan and installer-outcome cases; real: the harness provisioning leg's receipt under the run nonce | none — corpus rows land with their Remaining Work rows | `tests/integration/test_harness_provisioning.py::test_provisioning_runs_once_per_run` |

## Not Proven By This Gate

- Limits: [T.C](development_plan_standards.md#tc-ceiling); none is a closure condition.
- A build manifest identifies the artifact it hashed, never that a running server or client started from it; [Windows backend qualification](phase-10-windows-backend-qualification.md) observes the running backend.

## Sprints

### Sprint 9.1: Windows entry: binder, receipt transport and native gate [Planned]

**Status**: Planned
**Implementation**: `src/agentctl/check/receipt_transport.py`, `tests/integration/test_receipt_transport.py`, `tests/integration/test_windows_setup_probes.py`, `src/agentctl/check/virtualbox_bind.py`, `tests/integration/test_virtualbox_binder.py`, `src/agentctl/check/probes/msvc_build_tools.py`, `src/agentctl/check/probes/agent_permissions.py`
**Validation tests**: `tests/integration/test_receipt_transport.py::test_stored_receipt_transport_preserves_identity`, `tests/integration/test_receipt_transport.py::test_transport_refuses_unverified_or_mismatched_receipt`, `tests/integration/test_windows_setup_probes.py::test_absent_capability_awaits_setup`
**Mutants**: none — the binder's claims and the nodes that kill them arrive with P0-12 of Governance and phase evidence
**Closes**: R25.1, R28.1
**Docs to update**: migrates `documents/engineering/toolchain_bootstrap.md` (owner [Haskell runtime and platform policy](phase-3-haskell-runtime-and-platform-policy.md)) except its D-153 frozen spans, migrates `documents/engineering/binary_build.md` (owner [Python bootstrap and handoff](phase-2-python-bootstrap-and-handoff.md)), migrates `documents/reference/files_and_state.md` (owner [Haskell runtime and platform policy](phase-3-haskell-runtime-and-platform-policy.md)), migrates `documents/reference/external_tool_facts.md` (owner [Python discipline and gate integrity](phase-1-python-discipline-and-gate-integrity.md))

#### Objective

Windows entry: binder, receipt transport and native gate supplies its complete owned contract through the single phase-scoped gate verdict.

#### Deliverables

The Windows-host binder attaches the live checkout to the dedicated Debian guest, verifies its nonce answer and census and writes the guest binding receipt as preparation outside `agentctl check`. The binder `src/agentctl/check/virtualbox_bind.py` and its claims arrive from [Governance and phase evidence](phase-0-governance-and-phase-evidence.md) by P0-12 (D-137), the re-homing that makes the binder path of this sprint's Implementation a path planned for this phase ([§ A](development_plan_standards.md#a-well-ordered-constructive-narrative) A3). That change adds those claims and these binder nodes of `tests/integration/test_virtualbox_binding.py` to this sprint's fields and the R25.1 row, each importing the binder lazily: the killers `test_guest_process_absence_refuses_unreadable_entries`, `test_host_binding_values` and `test_guest_peer_nonce_is_visible_until_exit`, and `test_host_share_mapping_binds_checkout` and `test_host_binding_rechecks_shared_mapping`. In its stage-2 split this sprint moves those nodes into `tests/integration/test_virtualbox_binder.py`, relocating the killer entries of the binder's claims through stage-2 killer-relocation records ([T.G](development_plan_standards.md#tg-governed-changes)), and migrates `tests/integration/test_virtualbox_binding.py` (owner [Governance and phase evidence](phase-0-governance-and-phase-evidence.md)) only by removing them while the same verified run keeps every Governance source covered, after which that module imports no binder code; it adds binder behavior only in new modules and never edits the attach, nonce answer, census and receipt behavior that earlier guest runs use ([§ A](development_plan_standards.md#a-well-ordered-constructive-narrative) A1). Receipt transport carries stored receipts between the guest and host receipt stores over the binder's SSH channel through the import and export of the receipt store of Governance and phase evidence, which copy them byte for byte and never rewrite or overwrite one, so a native Windows run reads its `linux` half from the store. The host-declared probe modules for `setup:msvc-build-tools` and `setup:agent-permissions` implement the probe interface of Governance and phase evidence; agents perform a missing one-time setup outside gate runs (D-141). The Windows arms and native Windows coverage of host-declared Windows sources arrive behind `foundation_host` by P0-12. A native Windows run follows the canonical run sequence of the [validation runbook](../documents/operations/validation_runbook.md): clear tool caches, run the binder, run the guest gate, transport its receipts and run the native Windows gate, with no edit in between.

Native Windows runs disturb nothing they did not create (R28.1, D-172): a kill-on-close job reaps every descendant of a test or killer, with breakaway only for psmux per-session servers tracked by registry PID and creation identity; console control events go only to consoles the run created; registry and clipboard calls are vetoed; and no setup restarts the host. This arm lands before any native Windows test run (D-181). Planned nodes and mutants, named here until their corpus rows land: `tests/integration/test_windows_containment.py::test_job_reaps_descendants`; `M-windows-job-breakaway-allowed`.

#### Validation

Transport a stored guest receipt and require the host store to hold identical bytes under the same phase, half and identity; refuse an unverified, stale or identity-mismatched receipt and any overwrite. An absent capability leaves only the phases that await it waiting, each at best `awaiting:setup:<capability>` with that half printed `absent` ([T.V](development_plan_standards.md#tv-verdict)), never a degraded pass. The native Windows gate starts only when the gate import-closure checks pass in the same run, so no later-owned import reaches it. Without a stored `windows` receipt this phase is at best `awaiting:windows`; a native Windows run prints its `linux` half as `stored` and its `windows` half as `own` ([T.O](development_plan_standards.md#to-output)).

Every node in **Validation tests** passes in a verified run and every named mutant is killed per [T.K](development_plan_standards.md#tk-kill) at stage 2.

#### Remaining Work

The whole sprint.

### Sprint 9.2: Private Rust, native prerequisites and pinned sources [Planned]

**Status**: Planned
**Implementation**: `src/agentctl/haskell/src/AgentCtl/Provision/Windows.hs`, `src/agentctl/haskell/src/AgentCtl/Provision/Rust.hs`, `src/agentctl/haskell/src/AgentCtl/Provision/Source.hs`, `src/agentctl/haskell/resources/psmux/`, `tests/integration/test_windows_toolchain.py`, `tests/integration/test_psmux_source.py`, `src/agentctl/haskell/src/AgentCtl/Mux/Windows.hs`, `src/agentctl/haskell/src/AgentCtl/Preflight/Windows.hs`, `tests/unit/test_mux_windows_oracles.py`, `tests/oracles/backend_profiles.toml`
**Validation tests**: `haskell:agentctl-core-test/WindowsProvision/pure-plan-controls`, `tests/integration/test_windows_toolchain.py::test_private_rust_and_native_link_probe`, `tests/integration/test_windows_toolchain.py::test_install_refusals_and_restart_required`, `tests/integration/test_psmux_source.py::test_archive_hash_and_escape_refusals`, `tests/integration/test_psmux_source.py::test_patch_and_lock_identity`
**Mutants**: none — planned mutants are named in this sprint's Deliverables until their corpus rows land, and the Windows multiplexer-arm mutants arrive by D-152
**Closes**: none
**Docs to update**: migrates `documents/engineering/toolchain_bootstrap.md` (owner [Haskell runtime and platform policy](phase-3-haskell-runtime-and-platform-policy.md)) except its D-153 frozen spans, migrates `documents/engineering/binary_build.md` (owner [Python bootstrap and handoff](phase-2-python-bootstrap-and-handoff.md)), migrates `documents/reference/files_and_state.md` (owner [Haskell runtime and platform policy](phase-3-haskell-runtime-and-platform-policy.md)), migrates `documents/reference/external_tool_facts.md` (owner [Python discipline and gate integrity](phase-1-python-discipline-and-gate-integrity.md))

#### Objective

Private Rust, native prerequisites and pinned sources supplies its complete owned contract through the single phase-scoped gate verdict.

#### Deliverables

Probe actual native compiler/linker/resource capability. Reuse qualifying MSVC/SDK read-only; otherwise prepare an explicit consent/elevation plan. Provision pinned private rustup/Rust/Cargo roots without PATH/profile/default changes. Missing elevation, policy, installer busy or restart-required outcomes remain named unmet readiness; no installer dialog or reboot is answered. Agents install Visual Studio Build Tools and the Windows SDK as one-time host setup outside gate runs and never restart the host; a setup whose outcome needs a restart leaves its capability absent (D-141, D-171); product code still prepares toolchains only under consent. Fetch the official archive with Haskell HTTPS/archive libraries, verify its digest, reject traversal/reparse/link/size violations and apply the exact content-bound patches that their consumer supplies; the pinned resources of `src/agentctl/haskell/resources/psmux/` exclude its patches directory, which that consumer owns. Source revision 063ca7026eb2b7b91a74d3f858bdec3dfc841dbb is the initial candidate baseline, not an accepted artifact by declaration. Include Cargo.lock, local workspace crates, toolchain/SDK and patch identities in the build key; override moving source toolchain defaults. This sprint removes the external psmux PATH prerequisite of its deletion-ledger row, working only in its own host-declared modules: `src/agentctl/haskell/src/AgentCtl/Mux/Windows.hs`, which receives the Windows candidate, remedy and psmux version-banner arms of `Mux.hs` from [Debian tmux and multiplexer](phase-4-debian-tmux-and-multiplexer.md) (D-152), and `src/agentctl/haskell/src/AgentCtl/Preflight/Windows.hs`, which receives the `psmux` name and version floor of the shared multiplexer warning from [Agent preflight and launch](phase-5-agent-preflight-and-launch.md) (D-157); it never edits `Mux.hs` or `Preflight.hs`. It keeps its Rust and psmux pins in the resources it owns under `src/agentctl/haskell/resources/psmux/`, never in the bootstrap pins of [Python bootstrap and handoff](phase-2-python-bootstrap-and-handoff.md) (D-157). `M-mux-tmux-alias-on-windows`, `M-mux-remedy-wrong-os` and `M-mux-version-banner-unchecked` arrive by D-152 with their target: the change that moves them adds them to this sprint's Mutants and, with all their killers and the oracle rows those killers load, to the R23 row of this sprint, and the Windows cases of those killers land in `tests/unit/test_mux_windows_oracles.py`, as do the Windows multiplexer warning cases that arrive by D-157. `tests/oracles/backend_profiles.toml` is the backend-profile oracle to which later Windows phases append rows ([§ A](development_plan_standards.md#a-well-ordered-constructive-narrative) A3). Planned mutants, named here until their corpus rows land ([§ C](development_plan_standards.md#c-honest-completion-tracking)): `M-msvc-presence-without-link-probe`, `M-rust-global-default-changed`, `M-archive-path-escape`, `M-cargo-floating-toolchain` and `M-source-digest-unchecked`.

#### Validation

Linux runs the complete pure plan/refusal corpus; native Windows proves compiler/linker/resource and private toolchain behavior from prepared fixtures. Cold, partial and failing installations are proven against installer and toolchain models (absent, present and partial Build Tools; installer outcomes 0, 3010, 1602, busy and elevation denied), and installed Build Tools and SDK are observed read-only; `setup:msvc-build-tools` gates the native twins, and an absent capability leaves this phase at best `awaiting:setup:msvc-build-tools` ([T.D](development_plan_standards.md#td-status-and-progression)). Standard user and restart-required twins publish no ready toolchain and preserve existing user tool selections. Serve independent archive twins and require bad hashes, escaping entries and mismatched patches to fail before publication. Build outside any enclosing Git tree so provenance cannot come from an unrelated repository. A warm prepared source needs no Git, fetch CLI or network.

Every node in **Validation tests** passes in a verified run and every named mutant is killed per [T.K](development_plan_standards.md#tk-kill) at stage 2.

#### Remaining Work

The whole sprint.

### Sprint 9.3: Idempotent native build and atomic publication [Planned]

**Status**: Planned
**Implementation**: `src/agentctl/haskell/src/AgentCtl/Provision/Psmux.hs`, `tests/integration/test_psmux_build.py`
**Validation tests**: `tests/integration/test_psmux_build.py::test_cold_warm_and_concurrent_build`, `tests/integration/test_psmux_build.py::test_failure_preserves_previous_artifact`
**Mutants**: none — planned mutants are named in this sprint's Deliverables until their corpus rows land
**Closes**: R23, R23.1
**Docs to update**: migrates `documents/engineering/toolchain_bootstrap.md` (owner [Haskell runtime and platform policy](phase-3-haskell-runtime-and-platform-policy.md)) except its D-153 frozen spans, migrates `documents/engineering/binary_build.md` (owner [Python bootstrap and handoff](phase-2-python-bootstrap-and-handoff.md)), migrates `documents/reference/files_and_state.md` (owner [Haskell runtime and platform policy](phase-3-haskell-runtime-and-platform-policy.md)), migrates `documents/reference/external_tool_facts.md` (owner [Python discipline and gate integrity](phase-1-python-discipline-and-gate-integrity.md))

#### Objective

Idempotent native build and atomic publication supplies its complete owned contract through the single phase-scoped gate verdict.

#### Deliverables

Build natively through private pinned Cargo with locked dependencies and measured resource/path budgets. Record source+patch/build input identity and all executable hashes; verify the staged candidate identity and atomically publish an immutable candidate version directory. Build verification grants no runtime qualification or automatic-input capability. The generic builder takes an immutable recipe value; profile-specific patch bytes are consumer inputs, not retroactive builder-phase source. Keep one stable private runtime registry independent of build revision. This sprint consumes `src/agentctl/haskell/src/AgentCtl/Provision/Artifact.hs`, the immutable artifact identity and publication contract of [Haskell runtime and platform policy](phase-3-haskell-runtime-and-platform-policy.md). Planned mutants, named here until their corpus rows land ([§ C](development_plan_standards.md#c-honest-completion-tracking)): `M-psmux-partial-promoted` and `M-psmux-warm-rebuild`.

A Windows gate leg of this phase runs agentctl's own provisioning once per run, never per mutation (R23.1, D-180): the first run on a machine performs the cold build of the private Rust toolchain and the pinned, patched psmux source, and later runs re-check the provisioned validation root in its idempotent mode, downloading and building nothing. The leg uses a validation-only private root, downloads only pinned, digest-checked sources (the only network use outside the live half), builds with bounded parallelism and changes no PATH, profile or default; mutants of the provisioning code are killed by the installer and toolchain models, never by rerunning the leg. Planned nodes and mutants, named here until their corpus rows land: `tests/integration/test_harness_provisioning.py::test_provisioning_runs_once_per_run`; `M-provision-leg-repeated-per-mutation`, `M-provision-root-shared`.

#### Validation

Native Windows cold build produces the manifest and genuine executable, a warm run spawns no installer/fetch/build, and concurrent calls reuse the winner. Failure leaves the prior build-verified candidate unchanged. Linux validates plan/digest/archive contracts without pretending to execute Windows binaries.

Every node in **Validation tests** passes in a verified run and every named mutant is killed per [T.K](development_plan_standards.md#tk-kill) at stage 2.

#### Remaining Work

The whole sprint.

## Remaining Work

The whole phase: Sprints 9.1–9.3.

## Documentation Requirements

**Architecture docs to create/update:**

- None.

**Engineering docs to create/update:**

- migrates `documents/engineering/toolchain_bootstrap.md` (owner [Haskell runtime and platform policy](phase-3-haskell-runtime-and-platform-policy.md)) except its D-153 frozen spans — doctrine, mechanisms and scope of executable evidence.
- migrates `documents/engineering/binary_build.md` (owner [Python bootstrap and handoff](phase-2-python-bootstrap-and-handoff.md)) — doctrine, mechanisms and scope of executable evidence.

**Operations and reference docs to create/update:**

- migrates `documents/reference/files_and_state.md` (owner [Haskell runtime and platform policy](phase-3-haskell-runtime-and-platform-policy.md)) — preparation, qualified host observations and actionable refusals.
- migrates `documents/reference/external_tool_facts.md` (owner [Python discipline and gate integrity](phase-1-python-discipline-and-gate-integrity.md)) — preparation, qualified host observations and actionable refusals.

**Cross-references to add:**

- `DEVELOPMENT_PLAN/00-overview.md` — requirement closure and lower-phase dependencies.
- `DEVELOPMENT_PLAN/system-components.md` — stable capability/path ownership.
- `DEVELOPMENT_PLAN/legacy_tracking_for_deletion.md` — remaining incompatible implementation shapes.
