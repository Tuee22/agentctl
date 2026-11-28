# Phase 3 — Haskell runtime and platform policy

**Status**: Planned
**Depends on**: [Phase 2 — Python bootstrap and handoff](phase-2-python-bootstrap-and-handoff.md)
**Host lane**: linux
**Gate**: `agentctl check`
**Gate kind**: self-verifying
**Closes**: R15, R22, R29

> **Purpose**: Haskell owns runtime host policy, typed effect interpretation, consent and reusable artifact preparation.

## Phase Objective

Haskell owns runtime host policy, typed effect interpretation, consent and reusable artifact preparation. Debian Linux is the Linux runtime contract; unsupported distributions fail before runtime provisioning. Platform-specific backend phases extend these capabilities without moving policy back into Python.

This phase's verdict evaluates the `linux` half ([T.V](development_plan_standards.md#tv-verdict) V8) at stage 2 ([T.W](development_plan_standards.md#tw-staged-enforcement)). Every cited artifact is owned within closure(3) ([§ A](development_plan_standards.md#a-well-ordered-constructive-narrative)), a planned absence is unmet work of this phase ([T.F](development_plan_standards.md#tf-shared-and-owned-failures)), and present incompatible code is a deletion-ledger row of its owner. Native Windows process, ACL and console-stop branches stay in this phase's shared sources as host-declared regions ([T.X](development_plan_standards.md#tx-terms), D-162) owed to [Windows application acceptance](phase-11-windows-application-acceptance.md), the genuine production preparation receipt is owed to the `linux-clean` half of [Linux live and clean acceptance](phase-12-linux-live-and-clean-acceptance.md), and native Darwin confirmation is owed to [macOS acceptance](phase-13-macos-acceptance.md); none is a gap in this verdict. Its Haskell modules and native tests form this phase's own build component, discovered through the `cabal.project` package glob of [Python bootstrap and handoff](phase-2-python-bootstrap-and-handoff.md); it edits no earlier component ([§ A](development_plan_standards.md#a-well-ordered-constructive-narrative) A1, A2).

## Gate Integrity

| Requirement | Oracle | Observer | Mutants | Tests |
|---|---|---|---|---|
| R22 — Native effects and runtime host facts | `tests/oracles/requirements.toml` | value: independent host-identity and invocation expectations; real: native process timeout and cleanup behavior; observer: independent launch and capture observations; owed: windows-application-acceptance | `M-launch-cwd-on-mux-line`, `M-capture-locale-decoding` | `haskell:agentctl-core-test/Host/debian-exact-id`, `haskell:agentctl-core-test/Host/unsupported-linux-no-effects`, `haskell:agentctl-core-test/ProcessReal/timeout-cleans-up`, `tests/unit/test_mux_values.py::test_invocation_cwd_stays_off_argv`, `tests/e2e/test_launch.py::test_hostile_folder_name_runs_nothing`, `tests/integration/test_capture_real.py::test_capture_roundtrip_on_private_server` |
| R15 — Provisioning plans, consent and owned publication | `tests/oracles/requirements.toml` | value: independent expected values for the owned pure contract; observer: nonce-bound observation of the provisioning runner's intended invocation with package-manager spawns blocked; owed: linux-live-and-clean-acceptance | none — planned mutants are named in the Deliverables of this row's sprint until their corpus rows land | `haskell:agentctl-core-test/Provision/idempotent-plan`, `haskell:agentctl-core-test/Provision/noninteractive-no-consent`, `haskell:agentctl-core-test/Provision/atomic-publish-and-lock`, `tests/integration/test_provision_runner.py::test_runner_invocation_observed_with_package_managers_blocked` |
| R29 — Model-first runtime evidence | `tests/oracles/requirements.toml` | value: independent model conformance and model-twin cases | none — corpus rows land with their Remaining Work rows | `haskell:agentctl-core-test/HostConformance/os-release-and-family-facts`, `haskell:agentctl-core-test/ProcessTableConformance/exit-timeout-and-reap-outcomes` |

## Not Proven By This Gate

- Limits: [T.C](development_plan_standards.md#tc-ceiling); none is a closure condition.
- Foreign-kernel process, filesystem and console behavior lies outside this Linux verdict; a mutant in a host-declared region is a kill obligation only on its own family's runs ([T.K](development_plan_standards.md#tk-kill) K6).

## Sprints

### Sprint 3.1: Native effects and runtime host facts [Planned]

**Status**: Planned
**Implementation**: `src/agentctl/haskell/src/AgentCtl/Process.hs`, `src/agentctl/haskell/src/AgentCtl/Native.hs`, `src/agentctl/haskell/src/AgentCtl/Host.hs`, `src/agentctl/haskell/src/AgentCtl/Paths.hs`, `tests/oracles/process_invocation.toml`
**Validation tests**: `haskell:agentctl-core-test/Host/debian-exact-id`, `haskell:agentctl-core-test/Host/unsupported-linux-no-effects`, `haskell:agentctl-core-test/ProcessReal/timeout-cleans-up`, `tests/unit/test_mux_values.py::test_invocation_cwd_stays_off_argv`, `tests/e2e/test_launch.py::test_hostile_folder_name_runs_nothing`, `tests/integration/test_capture_real.py::test_capture_roundtrip_on_private_server`
**Mutants**: `M-launch-cwd-on-mux-line`, `M-capture-locale-decoding`
**Closes**: R22
**Docs to update**: migrates `documents/architecture/python_haskell_boundary.md` (owner [Python bootstrap and handoff](phase-2-python-bootstrap-and-handoff.md)), `documents/engineering/toolchain_bootstrap.md` except its D-153 frozen spans, migrates `documents/engineering/code_standards.md` (owner [Python discipline and gate integrity](phase-1-python-discipline-and-gate-integrity.md))

#### Objective

Native effects and runtime host facts supplies its complete owned contract through the single phase-scoped gate verdict.

#### Deliverables

Provide independent native process and decoding controls before later mux and capture tests, preserving their named mutants and observations. This sprint splits `tests/unit/test_mux_values.py` by owner (D-155): its multiplexer oracle nodes, `test_render_oracle` among them, move to a module of [Debian tmux and multiplexer](phase-4-debian-tmux-and-multiplexer.md) and `test_session_name_oracle` to a module of [Agent preflight and launch](phase-5-agent-preflight-and-launch.md), each with its killer entries carried by killer-relocation records ([T.G](development_plan_standards.md#tg-governed-changes)) and its citations edited in the same change. `M-launch-cwd-on-mux-line` and `M-capture-locale-decoding` gain killers that load only this phase's oracle rows, such as the invocation rows of the planned `tests/oracles/process_invocation.toml` that `tests/unit/test_mux_values.py::test_invocation_cwd_stays_off_argv` loads, and their later-dependent killers leave through killer-relocation records, so this sprint cites only nodes of the process, native, host and path contracts. Gather immutable runtime facts in Haskell, including exact Debian identity from os-release. One process runner accepts absolute executables, literal argv, explicit environment and deadlines, drains bytes and preserves UTF-8/exit outcomes. Typed native filesystem/liveness operations expose no arbitrary global kill. Planned mutants, named here until their corpus rows land ([§ C](development_plan_standards.md#c-honest-completion-tracking)): `M-host-accepts-id-like` and `M-process-second-spawner`.

`MuxReal` of `src/agentctl/haskell/test/MuxTests.hs` runs a private copy of the installed multiplexer under a private home, an absolute `PSMUX_DATA_DIR`, `PSMUX_NO_WARM=1` and a private `TMUX_TMPDIR`, never the installed binary with the user's environment (D-172).

#### Validation

Accept Debian and reject an apt-bearing non-Debian host before any install effect. Construct malformed host facts, missing native handles, invalid UTF-8 and timeouts and require typed errors. Native OS ABI branches are host-declared regions of their shared sources, which this sprint appends to the host-declaration file (ledger), each a kill obligation only on its own family's runs and owed to the later phase whose lane includes that family ([T.K](development_plan_standards.md#tk-kill) K6).

Every node in **Validation tests** passes in a verified run and every named mutant is killed per [T.K](development_plan_standards.md#tk-kill) at stage 2.

#### Remaining Work

The whole sprint.

### Sprint 3.2: Provisioning plans, consent and owned publication [Planned]

**Status**: Planned
**Implementation**: `src/agentctl/haskell/src/AgentCtl/Provision.hs`, `src/agentctl/haskell/src/AgentCtl/Provision/Artifact.hs`, `tests/integration/test_provision_runner.py`
**Validation tests**: `haskell:agentctl-core-test/Provision/idempotent-plan`, `haskell:agentctl-core-test/Provision/noninteractive-no-consent`, `haskell:agentctl-core-test/Provision/atomic-publish-and-lock`, `tests/integration/test_provision_runner.py::test_runner_invocation_observed_with_package_managers_blocked`
**Mutants**: none — planned mutants are named in this sprint's Deliverables until their corpus rows land
**Closes**: R15
**Docs to update**: migrates `documents/architecture/python_haskell_boundary.md` (owner [Python bootstrap and handoff](phase-2-python-bootstrap-and-handoff.md)), `documents/engineering/toolchain_bootstrap.md` except its D-153 frozen spans, migrates `documents/engineering/code_standards.md` (owner [Python discipline and gate integrity](phase-1-python-discipline-and-gate-integrity.md))

#### Objective

Provisioning plans, consent and owned publication supplies its complete owned contract through the single phase-scoped gate verdict.

#### Deliverables

Use pure dependency plans and explicit typed interpreters, shared for every runtime backend. Separate consent from privilege and from raw agent arguments, and apply the typed global consent that the bootstrap protocol carries to every native provisioning plan (D-140). Noninteractive absent consent or privilege returns an actionable refusal; ordinary check never installs host packages or answers dialogs. Immutable artifact identity includes all build and policy inputs. This sprint consumes `src/agentctl/haskell/src/AgentCtl/Protocol.hs`. Planned mutants, named here until their corpus rows land ([§ C](development_plan_standards.md#c-honest-completion-tracking)): `M-provision-partial-publish` and `M-provision-privilege-implies-consent`.

#### Validation

Observe one cold plan, an empty warm plan, concurrent winner reuse and failed publication preserving its predecessor. Block package-manager spawns in tests and prove the real runner's intended invocation through the independent nonce-bound observer of `tests/integration/test_provision_runner.py`. Production preparation runs outside `agentctl check` and is never evidence: this phase proves the preparation-receipt contract, and the genuine production receipt is owed to the `linux-clean` half of [Linux live and clean acceptance](phase-12-linux-live-and-clean-acceptance.md), which observes clean state under the run nonce.

Every node in **Validation tests** passes in a verified run and every named mutant is killed per [T.K](development_plan_standards.md#tk-kill) at stage 2.

#### Remaining Work

The whole sprint.

### Sprint 3.3: Effect seam and runtime models [Planned]

**Status**: Planned
**Implementation**: `src/agentctl/haskell/src/AgentCtl/Effect.hs`, `src/agentctl/haskell/src/AgentCtl/Effect/Native.hs`, `src/agentctl/haskell/src/AgentCtl/Process.hs`, `src/agentctl/haskell/src/AgentCtl/Native.hs`, `src/agentctl/haskell/src/AgentCtl/Host.hs`, `src/agentctl/haskell/models/AgentCtl/Model/World.hs`, `src/agentctl/haskell/models/AgentCtl/Model/Host.hs`, `src/agentctl/haskell/models/AgentCtl/Model/ProcessTable.hs`, `src/agentctl/haskell/models/AgentCtl/Model/Files.hs`, `src/agentctl/haskell/models/AgentCtl/Model/Clock.hs`, `src/agentctl/haskell/models/AgentCtl/Model/Installer.hs`, `src/agentctl/haskell/test/EffectTests.hs`, `src/agentctl/haskell/test/MuxTests.hs`
**Validation tests**: `haskell:agentctl-core-test/HostConformance/os-release-and-family-facts`, `haskell:agentctl-core-test/ProcessTableConformance/exit-timeout-and-reap-outcomes`, `haskell:agentctl-core-test/FilesConformance/missing-private-and-locked-outcomes`, `haskell:agentctl-core-test/ClockConformance/monotonic-deadline-ordering`, `haskell:agentctl-core-test/InstallerConformance/present-partial-and-refused-outcomes`, `haskell:agentctl-core-test/ProcessModel/runner-deadline-drain-and-exit-properties`, `haskell:agentctl-core-test/HostModel/declared-family-selects-policy`, `haskell:agentctl-core-test/EffectReal/native-interpreter-twins`, `haskell:agentctl-core-test/MuxReal/absent-multiplexer-unavailable`, `haskell:agentctl-core-test/MuxReal/host-multiplexer-meets-floor`
**Mutants**: none — planned mutants are named in this sprint's Deliverables until their corpus rows land
**Closes**: R29
**Docs to update**: migrates `documents/engineering/code_standards.md` (owner [Python discipline and gate integrity](phase-1-python-discipline-and-gate-integrity.md))

#### Objective

Effect seam and runtime models supplies its complete owned contract through the single phase-scoped gate verdict.

#### Deliverables

This sprint delivers the effect seam of D-173 and the first environment models of D-177. `AgentCtl.Effect` declares `Effects m`, records of operations at the raw OS boundary for processes, files, the clock and the console, each passed as a declared parameter through the existing `ExceptT failure m` shells ([T.X](development_plan_standards.md#tx-terms)). `AgentCtl.Process` and `AgentCtl.Native` hold the production native interpreters of processes and files, and `AgentCtl.Effect.Native` those of the clock and the console; with their C ABI they form the thin native layer. `System.Info.os` appears only in these interpreters, so elsewhere the host family is a declared value and a model-backed node runs identically on every host. This phase's model library, which no product component links, `exe:agentctl-core` included (D-163), holds the host, process-table, files, clock and generic-installer models over a world type whose `ext` slot lets a later owner add state and program models in its own modules without editing these ([§ A](development_plan_standards.md#a-well-ordered-constructive-narrative) A1). Each model imports only raw boundary types, is anchored only by the ratcheted oracle rows that its conformance cases load or stream as JSON to its owner's evaluator subject, and has model mutants that only those cases kill ([T.M](development_plan_standards.md#tm-adequacy) M5). Generated properties use QuickCheck through the property form of the `TestSource` wrapper, and this sprint consumes `src/agentctl/haskell/test/TestSource.hs` (D-176). The `MuxReal` cases resolve the host multiplexer into a private copy and run it with a private home and data directory, `PSMUX_NO_WARM=1`, a private `TMUX_TMPDIR` and no inherited `TMUX` ([§ Q](development_plan_standards.md#q-containment-and-user-state-protection)).

Planned mutants, named here until their corpus rows land ([§ C](development_plan_standards.md#c-honest-completion-tracking)): the subject mutants `M-effect-timeout-outcome-dropped` and `M-effect-declared-family-ignored`, and the model mutants `M-model-host-missing-os-release-accepted`, `M-model-process-table-reused-pid-accepted`, `M-model-files-lock-never-busy`, `M-model-clock-sleep-frozen` and `M-model-installer-partial-reported-complete`, which only their models' conformance cases kill.

#### Validation

Check each model against its ratcheted rows through its conformance cases alone, and require every model mutant to die only by those cases. Run the subject over the models with generated cases whose seed, size and count come from ratcheted rows ([T.K](development_plan_standards.md#tk-kill) K7), and run the native interpreters' accepting and refusing twins on run-owned helper processes and private temporary roots. A model-backed node never branches on the host family, and the foreign-family arms of the native interpreters stay host-declared regions, each a kill obligation only on its own family's runs ([T.K](development_plan_standards.md#tk-kill) K6).

Every node in **Validation tests** passes in a verified run and every named mutant is killed per [T.K](development_plan_standards.md#tk-kill) at stage 2.

#### Remaining Work

The whole sprint.

## Remaining Work

The whole phase: Sprints 3.1–3.3.

## Documentation Requirements

**Architecture docs to create/update:**

- migrates `documents/architecture/python_haskell_boundary.md` (owner [Python bootstrap and handoff](phase-2-python-bootstrap-and-handoff.md)) — this phase's owned contract and links to prerequisite interfaces.

**Engineering docs to create/update:**

- `documents/engineering/toolchain_bootstrap.md` except its D-153 frozen spans — doctrine, mechanisms and scope of executable evidence.
- migrates `documents/engineering/code_standards.md` (owner [Python discipline and gate integrity](phase-1-python-discipline-and-gate-integrity.md)) — doctrine, mechanisms and scope of executable evidence.

**Operations and reference docs to create/update:**

- None.

**Cross-references to add:**

- `DEVELOPMENT_PLAN/00-overview.md` — requirement closure and lower-phase dependencies.
- `DEVELOPMENT_PLAN/system-components.md` — stable capability/path ownership.
- `DEVELOPMENT_PLAN/legacy_tracking_for_deletion.md` — remaining incompatible implementation shapes.
