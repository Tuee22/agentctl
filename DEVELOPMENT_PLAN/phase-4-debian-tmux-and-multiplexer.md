# Phase 4 — Debian tmux and multiplexer

**Status**: Planned
**Depends on**: [Phase 3 — Haskell runtime and platform policy](phase-3-haskell-runtime-and-platform-policy.md)
**Host lane**: linux
**Gate**: `agentctl check`
**Gate kind**: self-verifying
**Closes**: R12.1

> **Purpose**: The common checked-backend interface and Debian tmux implementation, including Haskell-owned APT provisioning and a private pane trampoline.

## Phase Objective

The common checked-backend interface and Debian tmux implementation, including Haskell-owned APT provisioning and a private pane trampoline. This phase establishes identity, capability and ownership types that every backend implements; it introduces no PATH-based Windows fallback.

This phase needs Linux only. The declared tests are executable contracts; an absent required test is unmet evidence, not existing proof. Acceptance-only test implementations belong to the prerequisite owner named in the inventory. Existing incompatible code is inventoried in the deletion ledger. No old implementation or unqualified receipt establishes this revised contract.

## Gate Integrity

| Requirement | Oracle | Observer | Mutants | Tests |
|---|---|---|---|---|
| R12.1 — Debian tmux readiness and APT preparation | `tests/oracles/requirements.toml` | value; observer: independent inputs and nonce-bound native observations | `M-tmux-apt-on-unsupported-host`, `M-tmux-warm-reinstalls` | `haskell:agentctl-core-test/TmuxProvision/reuse-supported-install`, `haskell:agentctl-core-test/TmuxProvision/apt-plan-and-refusals`, `tests/integration/test_tmux_provision.py::test_unsupported_linux_never_installs` |
| R12.1 — Typed mux operations and pane execution | `tests/oracles/requirements.toml` | value; observer: independent inputs and nonce-bound native observations | `M-mux-prefix-target`, `M-pane-spec-environment-on-argv` | `tests/integration/test_mux_real.py::test_private_server_roundtrip`, `tests/integration/test_mux_real.py::test_instant_exit_status`, `tests/integration/test_pane_exec.py::test_private_spec_policy` |
| R12.1 — Backend capability and instance identity | `tests/oracles/requirements.toml` | value; observer: independent inputs and nonce-bound native observations | `M-backend-client-version-as-server-proof` | `haskell:agentctl-core-test/Backend/identity-and-capability-contract`, `tests/integration/test_mux_real.py::test_pane_targets_distinguish_servers` |

## Not Proven By This Gate

- A receipt's digest establishes input currency, not an independently attested historical run. Local receipt authenticity has the documented honest ceiling.
- A source rule or finite corpus does not prove arbitrary callback purity, universal termination or agent-internal readiness. Native operation and resource assumptions remain explicit.
- Foreign-kernel behavior is outside this phase's Linux verdict. Later native implementation extends the common contract and cannot retroactively add a foreign-hardware requirement here.

## Sprints

### Sprint 4.1: Debian tmux readiness and APT preparation [Planned]

**Status**: Planned
**Implementation**: `src/agentctl/haskell/src/AgentCtl/Mux.hs`, `src/agentctl/haskell/src/AgentCtl/Provision/Tmux.hs`
**Validation tests**: `haskell:agentctl-core-test/TmuxProvision/reuse-supported-install`, `haskell:agentctl-core-test/TmuxProvision/apt-plan-and-refusals`, `tests/integration/test_tmux_provision.py::test_unsupported_linux_never_installs`
**Mutants**: `M-tmux-apt-on-unsupported-host`, `M-tmux-warm-reinstalls`
**Closes**: R12.1
**Docs to update**: `documents/architecture/multiplexer_adapter.md`, `documents/architecture/launch_contract.md`, `documents/engineering/toolchain_bootstrap.md`

#### Objective

Debian tmux readiness and APT preparation supplies its complete owned contract through the single phase-scoped gate verdict.

#### Deliverables

Migrate the clean-host recipe and its host observations, and introduce tests/integration/test_clean_runtime.py and its production-preparation receipt contract for clean-host acceptance; test execution vetoes real package managers and the later acceptance lane supplies the genuine outer preparation receipt. Reuse a qualified tmux; when absent or inadequate, Haskell prepares a concrete APT plan under consent, applies it outside checks and re-probes. Reject repositories unable to provide supported behavior rather than adding repositories or reinstalling forever. Agent CLI packages never enter this plan.

#### Validation

Construct missing, supported, old and failed-package states and pin the exact effects/refusals. A production clean Debian preparation receipt proves actual installation separately from the tests' package-manager veto; no native Windows or macOS receipt is required here.

Required executable evidence: `haskell:agentctl-core-test/TmuxProvision/reuse-supported-install`, `haskell:agentctl-core-test/TmuxProvision/apt-plan-and-refusals`, `tests/integration/test_tmux_provision.py::test_unsupported_linux_never_installs`. Every named mutant must die for its recorded reason in those tests; a baseline failure or unrelated exception is not a kill.

#### Remaining Work

The whole sprint.

### Sprint 4.2: Typed mux operations and pane execution [Planned]

**Status**: Planned
**Implementation**: `src/agentctl/haskell/src/AgentCtl/Mux/`, `src/agentctl/haskell/src/AgentCtl/PaneExec.hs`, `src/agentctl/haskell/src/AgentCtl/PaneExec/Spec.hs`, `tests/harness/tmux.py`
**Validation tests**: `tests/integration/test_mux_real.py::test_private_server_roundtrip`, `tests/integration/test_mux_real.py::test_instant_exit_status`, `tests/integration/test_pane_exec.py::test_private_spec_policy`
**Mutants**: `M-mux-prefix-target`, `M-pane-spec-environment-on-argv`
**Closes**: none
**Docs to update**: `documents/architecture/multiplexer_adapter.md`, `documents/architecture/launch_contract.md`, `documents/engineering/toolchain_bootstrap.md`

#### Objective

Typed mux operations and pane execution supplies its complete owned contract through the single phase-scoped gate verdict.

#### Deliverables

Deliver the independent base fake-agent/private-mux observer here, including strict finite file reads and deterministic handle closure; later scripted frames are additive observers. Create the closed command vocabulary, exact session/native pane targeting and checked identities. The trampoline reads a private bounded spec with argv, cwd and caller environment; it supplies reliable startup/exit observations. Production code has no kill-server, global option reset or shell-string command.

#### Validation

Use real private tmux with an independently recording fake agent. Assert literal hostile arguments, exact sibling isolation, caller environment, instant exit and fail-clean startup. Verify private endpoint ownership before teardown; a user's normal server remains untouched.

Required executable evidence: `tests/integration/test_mux_real.py::test_private_server_roundtrip`, `tests/integration/test_mux_real.py::test_instant_exit_status`, `tests/integration/test_pane_exec.py::test_private_spec_policy`. Every named mutant must die for its recorded reason in those tests; a baseline failure or unrelated exception is not a kill.

#### Remaining Work

The whole sprint.

### Sprint 4.3: Backend capability and instance identity [Planned]

**Status**: Planned
**Implementation**: `src/agentctl/haskell/src/AgentCtl/Mux/Types.hs`, `src/agentctl/haskell/src/AgentCtl/Session/Identity.hs`
**Validation tests**: `haskell:agentctl-core-test/Backend/identity-and-capability-contract`, `tests/integration/test_mux_real.py::test_pane_targets_distinguish_servers`
**Mutants**: `M-backend-client-version-as-server-proof`
**Closes**: none
**Docs to update**: `documents/architecture/multiplexer_adapter.md`, `documents/architecture/launch_contract.md`, `documents/engineering/toolchain_bootstrap.md`

#### Objective

Backend capability and instance identity supplies its complete owned contract through the single phase-scoped gate verdict.

#### Deliverables

A backend handle records actual server/session/pane instance identity, executable provenance and qualified capabilities. Observation and guarded input are separate capabilities; possession of a version banner alone grants neither. Later platform implementations fulfill the same interface.

#### Validation

Construct same numeric pane ids on different server instances and require exact routing. Replace a server or pane and require revalidation failure. A compatible client connected to an unqualified server cannot authorize automatic input.

Required executable evidence: `haskell:agentctl-core-test/Backend/identity-and-capability-contract`, `tests/integration/test_mux_real.py::test_pane_targets_distinguish_servers`. Every named mutant must die for its recorded reason in those tests; a baseline failure or unrelated exception is not a kill.

#### Remaining Work

The whole sprint.

## Remaining Work

The whole phase: Sprints 4.1–4.3.

## Documentation Requirements

**Architecture docs to create/update:**

- `documents/architecture/multiplexer_adapter.md` — this phase's owned contract and links to prerequisite interfaces.
- `documents/architecture/launch_contract.md` — this phase's owned contract and links to prerequisite interfaces.

**Engineering docs to create/update:**

- `documents/engineering/toolchain_bootstrap.md` — doctrine, mechanisms and scope of executable evidence.

**Operations and reference docs to create/update:**

- None.

**Cross-references to add:**

- `DEVELOPMENT_PLAN/00-overview.md` — requirement closure and lower-phase dependencies.
- `DEVELOPMENT_PLAN/system-components.md` — stable capability/path ownership.
- `DEVELOPMENT_PLAN/legacy_tracking_for_deletion.md` — remaining incompatible implementation shapes.
