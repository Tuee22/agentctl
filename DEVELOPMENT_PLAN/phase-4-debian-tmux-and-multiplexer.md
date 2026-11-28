# Phase 4 — Debian tmux and multiplexer

**Status**: Planned
**Depends on**: [Phase 3 — Haskell runtime and platform policy](phase-3-haskell-runtime-and-platform-policy.md)
**Host lane**: linux
**Gate**: `agentctl check`
**Gate kind**: self-verifying
**Closes**: R12.1

> **Purpose**: The common checked-backend interface and Debian tmux implementation, including Haskell-owned APT provisioning and a private pane trampoline.

## Phase Objective

The common checked-backend interface and Debian tmux implementation, including Haskell-owned APT provisioning and a private pane trampoline. This phase establishes identity, capability and ownership types that every backend implements; it introduces no PATH-based Windows fallback, and Sprint 4.1 moves the present Windows candidate, remedy and psmux version-banner arms of `Mux.hs` behind this interface into a host-declared module of [Windows toolchain and psmux build](phase-9-windows-toolchain-and-psmux-build.md) (D-152).

This phase's verdict evaluates the `linux` half ([T.V](development_plan_standards.md#tv-verdict) V8) at stage 2 ([T.W](development_plan_standards.md#tw-staged-enforcement)). Every cited artifact is owned within closure(4) ([§ A](development_plan_standards.md#a-well-ordered-constructive-narrative)), a planned absence is unmet work of this phase ([T.F](development_plan_standards.md#tf-shared-and-owned-failures)), and present incompatible code is a deletion-ledger row of its owner. The genuine clean APT preparation receipt is owed to the `linux-clean` half of [Linux live and clean acceptance](phase-12-linux-live-and-clean-acceptance.md), which consumes this phase's clean-host recipe unchanged, and native Darwin tmux readiness is owed to [macOS acceptance](phase-13-macos-acceptance.md); neither is a gap in this verdict. Its Haskell modules and native tests form this phase's own build component, discovered through the `cabal.project` package glob of [Python bootstrap and handoff](phase-2-python-bootstrap-and-handoff.md); it edits no earlier component ([§ A](development_plan_standards.md#a-well-ordered-constructive-narrative) A1, A2).

## Gate Integrity

| Requirement | Oracle | Observer | Mutants | Tests |
|---|---|---|---|---|
| R12.1 — Debian tmux readiness and APT preparation | `tests/oracles/requirements.toml` | value: independent version-floor, resolution-candidate and remedy expectations; owed: linux-live-and-clean-acceptance | `M-mux-floor-3-1`, `M-mux-letter-suffix-refused`, `M-mux-remedy-wrong-os`, `M-mux-tmux-alias-on-windows`, `M-mux-version-banner-unchecked` | `haskell:agentctl-core-test/TmuxProvision/reuse-supported-install`, `haskell:agentctl-core-test/TmuxProvision/apt-plan-and-refusals`, `tests/integration/test_tmux_provision.py::test_unsupported_linux_never_installs`, `tests/unit/test_mux_values.py::test_version_floor_oracle`, `tests/unit/test_mux_values.py::test_remedy_oracle`, `tests/unit/test_mux_values.py::test_resolution_candidates_oracle` |
| R12.1 — Clean-host recipe | `tests/oracles/bootstrap_plan.toml` | value: independent clean-host recipe expectations | `M-boot-recipe-stage-a-root` | `tests/unit/test_clean_host_recipe.py::test_recipe_stages_match_oracle` |
| R12.1 — Typed mux operations and pane execution | `tests/oracles/requirements.toml` | value: independent render, pane-target, process-tree, reap, spec and stop-plan expectations; real: private-server exit status, pane-spec execution, harness socket refusal and named-session stop; observer: nonce-bound private-server, fake-agent, sibling-isolation and capture observations | `M-mux-bare-target`, `M-mux-bare-target-at-boundary`, `M-mux-create-job-retained`, `M-mux-dead-before-status`, `M-mux-fake-record-drops-nonce`, `M-mux-harness-kills-foreign-socket`, `M-mux-pane-ambiguity-accepted`, `M-mux-pane-target-unscoped`, `M-mux-psmux-status-from-pane`, `M-mux-reap-policy-inverted`, `M-mux-remain-on-exit-off`, `M-mux-shell-joined-command`, `M-mux-spec-decode-drops-environment`, `M-mux-spec-drops-environment`, `M-mux-spec-mode-unchecked`, `M-mux-spec-mode-unchecked-at-boundary`, `M-sessions-stop-kill-server`, `M-sessions-stop-prefix-target`, `M-capture-no-join` | `tests/integration/test_mux_real.py::test_private_server_roundtrip`, `tests/integration/test_mux_real.py::test_instant_exit_status`, `tests/integration/test_pane_exec.py::test_private_spec_policy`, `tests/unit/test_mux_values.py::test_render_oracle`, `tests/integration/test_mux_real.py::test_exact_target_spares_prefix_sibling`, `tests/unit/test_mux_values.py::test_process_tree_policy_oracle`, `tests/integration/test_mux_real.py::test_closed_terminal_does_not_publish_exit_status`, `tests/integration/test_fake_agent.py::test_record_carries_nonce`, `tests/integration/test_tmux_harness.py::test_kill_server_refuses_foreign_socket`, `tests/unit/test_mux_values.py::test_pane_target_oracle`, `tests/unit/test_mux_values.py::test_dead_status_rule_oracle`, `tests/unit/test_mux_values.py::test_reap_policy_oracle`, `tests/integration/test_pane_exec.py::test_spec_deleted_and_status_propagated`, `haskell:agentctl-core-test/PaneExec/spec-round-trip`, `tests/unit/test_mux_values.py::test_spec_acceptance_oracle`, `tests/integration/test_pane_exec.py::test_unsafe_spec_refused`, `tests/unit/test_sessions_values.py::test_stop_plan_matches_oracle`, `tests/e2e/test_sessions.py::test_stop_kills_only_the_named_managed_session`, `tests/e2e/test_sessions.py::test_stop_never_prefix_matches`, `tests/integration/test_capture_real.py::test_capture_roundtrip_on_private_server` |
| R12.1 — Backend capability and instance identity | `tests/oracles/requirements.toml` | value: independent backend identity and capability contract expectations; observer: nonce-bound routing of equal pane ids across distinct private servers | none — planned mutants are named in the Deliverables of this row's sprint until their corpus rows land | `haskell:agentctl-core-test/Backend/identity-and-capability-contract`, `tests/integration/test_mux_real.py::test_pane_targets_distinguish_servers` |

## Not Proven By This Gate

- Limits: [T.C](development_plan_standards.md#tc-ceiling); none is a closure condition.
- Foreign multiplexer backends lie outside this Linux verdict; each adds its own modules behind this phase's interface.

## Sprints

### Sprint 4.1: Debian tmux readiness and APT preparation [Planned]

**Status**: Planned
**Implementation**: `src/agentctl/haskell/src/AgentCtl/Mux.hs`, `src/agentctl/haskell/src/AgentCtl/Provision/Tmux.hs`, `tests/lanes/clean-host.Dockerfile`, `tests/integration/test_tmux_provision.py`, `tests/integration/test_clean_runtime.py`, `tests/unit/test_mux_oracles.py`
**Validation tests**: `haskell:agentctl-core-test/TmuxProvision/reuse-supported-install`, `haskell:agentctl-core-test/TmuxProvision/apt-plan-and-refusals`, `tests/integration/test_tmux_provision.py::test_unsupported_linux_never_installs`, `tests/unit/test_clean_host_recipe.py::test_recipe_stages_match_oracle`, `tests/integration/test_host_mux_probe.py::test_host_probe_and_constructed_absence`, `tests/unit/test_mux_values.py::test_version_floor_oracle`, `tests/unit/test_mux_values.py::test_remedy_oracle`, `tests/unit/test_mux_values.py::test_resolution_candidates_oracle`, `tests/integration/test_clean_runtime.py::test_preparation_receipt_contract`
**Mutants**: `M-boot-recipe-stage-a-root`, `M-mux-floor-3-1`, `M-mux-letter-suffix-refused`, `M-mux-remedy-wrong-os`, `M-mux-tmux-alias-on-windows`, `M-mux-version-banner-unchecked`
**Closes**: R12.1
**Docs to update**: `documents/architecture/multiplexer_adapter.md`, migrates `documents/engineering/toolchain_bootstrap.md` (owner [Haskell runtime and platform policy](phase-3-haskell-runtime-and-platform-policy.md)) except its D-153 frozen spans

#### Objective

Debian tmux readiness and APT preparation supplies its complete owned contract through the single phase-scoped gate verdict.

#### Deliverables

Migrate the clean-host recipe and its host observations. Its Debian base replaces the Ubuntu base through `amends` cases appended to the `bootstrap.clean-host.recipe` case, never a rewrite: this sprint migrates `tests/oracles/bootstrap_plan.toml` (owner [Python bootstrap and handoff](phase-2-python-bootstrap-and-handoff.md)) only by those appended cases (D-142), and [Linux live and clean acceptance](phase-12-linux-live-and-clean-acceptance.md) consumes the recipe unchanged. Introduce `tests/integration/test_clean_runtime.py` with the production-preparation receipt contract, its portable control and `tests/integration/test_clean_runtime.py::test_pipx_to_haskell_to_apt_tmux`, the clean-runtime acceptance node, declared to the `linux-clean` half ([T.X](development_plan_standards.md#tx-terms)), that the `linux-clean` half of that phase cites; test execution vetoes real package managers, and the genuine outer preparation receipt is owed to that half. Reuse a qualified tmux; when absent or inadequate, Haskell prepares a concrete APT plan under consent, applies it outside checks and re-probes. Reject repositories unable to provide supported behavior rather than adding repositories or reinstalling forever. Agent CLI packages never enter this plan. Planned mutants, named here until their corpus rows land ([§ C](development_plan_standards.md#c-honest-completion-tracking)): `M-tmux-apt-on-unsupported-host` and `M-tmux-warm-reinstalls`. This sprint moves the present Windows candidate, remedy and psmux version-banner arms of `src/agentctl/haskell/src/AgentCtl/Mux.hs` behind the backend interface to `src/agentctl/haskell/src/AgentCtl/Mux/Windows.hs` (owner [Windows toolchain and psmux build](phase-9-windows-toolchain-and-psmux-build.md)), the host-declared module that phase lists in its Implementation ([§ A](development_plan_standards.md#a-well-ordered-constructive-narrative) A3). In that change `M-mux-tmux-alias-on-windows`, `M-mux-remedy-wrong-os` and `M-mux-version-banner-unchecked` follow their target through stage-2 retarget or re-anchor records and change owner with it ([T.M](development_plan_standards.md#tm-adequacy) M1): the change drops them from this phase's `R12.1 — Debian tmux readiness and APT preparation` row and this sprint's Mutants, and adds them to the Sprint 9.2 Mutants of that phase and, with all their killers and the oracle rows those killers load, to its `R23 — Private Rust, native prerequisites and pinned sources` row. The `mux.candidates.windows` and `mux.remedy.windows` oracle rows gain appended `amends` cases that T.I projects to that phase, and the Windows cases of their killers move to its nodes through killer-relocation records ([T.G](development_plan_standards.md#tg-governed-changes)), so no later phase edits `Mux.hs` (D-152). Those killers and the other multiplexer oracle nodes arrive in `tests/unit/test_mux_oracles.py` when [Haskell runtime and platform policy](phase-3-haskell-runtime-and-platform-policy.md) splits its value module by owner (D-155), and this phase splits nodes only in its own modules.

#### Validation

Construct missing, supported, old and failed-package states and pin the exact effects/refusals. This phase proves the preparation-receipt contract and the package-manager veto; the genuine clean Debian preparation receipt is owed to the `linux-clean` half of [Linux live and clean acceptance](phase-12-linux-live-and-clean-acceptance.md), and no native Windows or macOS receipt enters this verdict.

Every node in **Validation tests** passes in a verified run and every named mutant is killed per [T.K](development_plan_standards.md#tk-kill) at stage 2.

#### Remaining Work

The whole sprint.

### Sprint 4.2: Typed mux operations and pane execution [Planned]

**Status**: Planned
**Implementation**: `src/agentctl/haskell/src/AgentCtl/Mux/Command.hs`, `src/agentctl/haskell/src/AgentCtl/Mux/Tmux.hs`, `src/agentctl/haskell/src/AgentCtl/PaneExec.hs`, `src/agentctl/haskell/src/AgentCtl/PaneExec/Spec.hs`, `src/agentctl/haskell/app/FakeAgent.hs`, `src/agentctl/haskell/test/MuxFixture.hs`, `tests/harness/tmux.py`, `tests/harness/tmux_fixtures.py`
**Validation tests**: `tests/integration/test_mux_reap.py::test_reap_observer_imports_without_launch`, `tests/integration/test_mux_reap.py::test_reap_request_validates_pid_before_notification`, `tests/integration/test_mux_real.py::test_private_server_roundtrip`, `tests/integration/test_mux_real.py::test_instant_exit_status`, `tests/integration/test_pane_exec.py::test_private_spec_policy`, `tests/integration/test_fake_agent.py::test_record_carries_nonce`, `tests/integration/test_tmux_harness.py::test_psmux_pid_record_shapes`, `tests/unit/test_mux_values.py::test_render_oracle`, `tests/integration/test_mux_real.py::test_exact_target_spares_prefix_sibling`, `tests/unit/test_mux_values.py::test_process_tree_policy_oracle`, `tests/integration/test_mux_real.py::test_closed_terminal_does_not_publish_exit_status`, `tests/integration/test_tmux_harness.py::test_kill_server_refuses_foreign_socket`, `tests/unit/test_mux_values.py::test_pane_target_oracle`, `tests/unit/test_mux_values.py::test_dead_status_rule_oracle`, `tests/unit/test_mux_values.py::test_reap_policy_oracle`, `tests/integration/test_pane_exec.py::test_spec_deleted_and_status_propagated`, `haskell:agentctl-core-test/PaneExec/spec-round-trip`, `tests/unit/test_mux_values.py::test_spec_acceptance_oracle`, `tests/integration/test_pane_exec.py::test_unsafe_spec_refused`, `tests/unit/test_sessions_values.py::test_stop_plan_matches_oracle`, `tests/e2e/test_sessions.py::test_stop_kills_only_the_named_managed_session`, `tests/e2e/test_sessions.py::test_stop_never_prefix_matches`, `tests/integration/test_capture_real.py::test_capture_roundtrip_on_private_server`
**Mutants**: `M-mux-bare-target`, `M-mux-bare-target-at-boundary`, `M-mux-create-job-retained`, `M-mux-dead-before-status`, `M-mux-fake-record-drops-nonce`, `M-mux-harness-kills-foreign-socket`, `M-mux-pane-ambiguity-accepted`, `M-mux-pane-target-unscoped`, `M-mux-psmux-status-from-pane`, `M-mux-reap-policy-inverted`, `M-mux-remain-on-exit-off`, `M-mux-shell-joined-command`, `M-mux-spec-decode-drops-environment`, `M-mux-spec-drops-environment`, `M-mux-spec-mode-unchecked`, `M-mux-spec-mode-unchecked-at-boundary`, `M-sessions-stop-kill-server`, `M-sessions-stop-prefix-target`, `M-capture-no-join`
**Closes**: none
**Docs to update**: `documents/architecture/multiplexer_adapter.md`, migrates `documents/engineering/toolchain_bootstrap.md` (owner [Haskell runtime and platform policy](phase-3-haskell-runtime-and-platform-policy.md)) except its D-153 frozen spans

#### Objective

Typed mux operations and pane execution supplies its complete owned contract through the single phase-scoped gate verdict.

#### Deliverables

Deliver the independent base fake-agent/private-mux observer here, including strict finite file reads and deterministic handle closure; later scripted frames are additive observers. Separate the base fake from its later supervisor fixture while preserving the extension's observations. Provide independent mux mutation and reap controls before later capture, session and launch tests, preserving their existing observations. Create the closed command vocabulary, exact session/native pane targeting and checked identities. The trampoline reads a private bounded spec with argv, cwd and caller environment; it supplies reliable startup/exit observations. Production code has no kill-server, global option reset or shell-string command. `M-capture-no-join` targets the capture join of `Mux/Tmux.hs`, so it is declared here with its killer ([T.M](development_plan_standards.md#tm-adequacy) M1). Planned mutants, named here until their corpus rows land ([§ C](development_plan_standards.md#c-honest-completion-tracking)): `M-mux-prefix-target` and `M-pane-spec-environment-on-argv`. This sprint splits the render oracle node by backend once it arrives in `tests/unit/test_mux_oracles.py` (D-155): the node keeps the tmux rows that kill this phase's render mutants, and the psmux rows move to a node owned by [Windows backend qualification](phase-10-windows-backend-qualification.md), which takes the killer entries of `M-mux-remain-session-unqualified` and `M-mux-render-psmux-alias` through killer-relocation records ([T.G](development_plan_standards.md#tg-governed-changes)), so no node this phase cites executes `Mux/Psmux.hs` (D-152). This sprint moves the psmux arms of `tests/harness/tmux.py`, which `mux_server` of `tests/harness/tmux_fixtures.py` reaches, and the Windows branches of the `tests/integration/test_mux_real.py` nodes to `tests/harness/psmux.py` (owner [Windows backend qualification](phase-10-windows-backend-qualification.md)), the host-declared module that phase lists in its Implementation and `foundation_host` reaches lazily, so the native Windows outcomes and kills of the nodes that reach them belong to that phase ([T.F](development_plan_standards.md#tf-shared-and-owned-failures), D-167). It appends host-declaration rows that declare `src/agentctl/haskell/src/AgentCtl/Mux/Tmux.hs` and the tmux harness left in `tests/harness/tmux.py` to the Linux and Darwin families, so their mutants, which only real tmux kills, are no kill obligation on a Windows run ([T.K](development_plan_standards.md#tk-kill) K6).

Debian tmux and multiplexer owns the tmux model behind a backend-generic interface, the pane-exec, fake-agent and APT program models and their transcript rows, with native replay twins on private tmux servers (D-173, D-177); later owners attach state through the model's extension slot and pane-program hook and never edit it. `tests/harness/tmux.py` keeps every test inside the closed list of [§ Q](development_plan_standards.md#q-containment-and-user-state-protection): tmux uses `kill-server` only on an owned `-S` socket after the scope check and only harness-owned foreground servers, while psmux never uses `kill-server`, ends a session by its exact target after its registry PID and creation identity are verified and refuses a version whose teardown is not namespace-scoped. `src/agentctl/haskell/app/FakeAgent.hs` becomes a registered stand-in with conformance cases and owner mutants (D-174). Planned mutants, named here until their corpus rows land: `M-harness-psmux-kill-server-used`, `M-harness-psmux-version-unchecked`, `M-model-tmux-duplicate-session-accepted`.

#### Validation

Use real private tmux with an independently recording fake agent. Assert literal hostile arguments, exact sibling isolation, caller environment, instant exit and fail-clean startup. Verify private endpoint ownership before teardown; a user's normal server remains untouched.

Every node in **Validation tests** passes in a verified run and every named mutant is killed per [T.K](development_plan_standards.md#tk-kill) at stage 2.

#### Remaining Work

The whole sprint.

### Sprint 4.3: Backend capability and instance identity [Planned]

**Status**: Planned
**Implementation**: `src/agentctl/haskell/src/AgentCtl/Mux/Types.hs`
**Validation tests**: `haskell:agentctl-core-test/Backend/identity-and-capability-contract`, `tests/integration/test_mux_real.py::test_pane_targets_distinguish_servers`
**Mutants**: none — planned mutants are named in this sprint's Deliverables until their corpus rows land
**Closes**: none
**Docs to update**: `documents/architecture/multiplexer_adapter.md`, migrates `documents/engineering/toolchain_bootstrap.md` (owner [Haskell runtime and platform policy](phase-3-haskell-runtime-and-platform-policy.md)) except its D-153 frozen spans

#### Objective

Backend capability and instance identity supplies its complete owned contract through the single phase-scoped gate verdict.

#### Deliverables

A backend handle records actual server/session/pane instance identity, executable provenance and qualified capabilities; the instance identity types live in `Mux/Types.hs`, which [Session management and adoption](phase-6-session-management-and-adoption.md) consumes. Observation and guarded input are separate capabilities; possession of a version banner alone grants neither. A later backend adds its own modules and build component and never edits `Mux/Types.hs`; a needed interface widening is this phase's work ([§ A](development_plan_standards.md#a-well-ordered-constructive-narrative) A1). The planned mutant `M-backend-client-version-as-server-proof` is named here until its corpus row lands ([§ C](development_plan_standards.md#c-honest-completion-tracking)).

#### Validation

Construct same numeric pane ids on different server instances and require exact routing. Replace a server or pane and require revalidation failure. A compatible client connected to an unqualified server cannot authorize automatic input.

Every node in **Validation tests** passes in a verified run and every named mutant is killed per [T.K](development_plan_standards.md#tk-kill) at stage 2.

#### Remaining Work

The whole sprint.

## Remaining Work

The whole phase: Sprints 4.1–4.3.

## Documentation Requirements

**Architecture docs to create/update:**

- `documents/architecture/multiplexer_adapter.md` — this phase's owned contract and links to prerequisite interfaces.

**Engineering docs to create/update:**

- migrates `documents/engineering/toolchain_bootstrap.md` (owner [Haskell runtime and platform policy](phase-3-haskell-runtime-and-platform-policy.md)) except its D-153 frozen spans — doctrine, mechanisms and scope of executable evidence.

**Operations and reference docs to create/update:**

- None.

**Cross-references to add:**

- `DEVELOPMENT_PLAN/00-overview.md` — requirement closure and lower-phase dependencies.
- `DEVELOPMENT_PLAN/system-components.md` — stable capability/path ownership.
- `DEVELOPMENT_PLAN/legacy_tracking_for_deletion.md` — remaining incompatible implementation shapes.
