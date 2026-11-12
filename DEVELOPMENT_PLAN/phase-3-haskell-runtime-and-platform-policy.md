# Phase 3 — Haskell runtime and platform policy

**Status**: Planned
**Depends on**: [Phase 2 — Python bootstrap and handoff](phase-2-python-bootstrap-and-handoff.md)
**Host lane**: linux
**Gate**: `agentctl check`
**Gate kind**: self-verifying
**Closes**: R15, R22

> **Purpose**: Haskell owns runtime host policy, typed effect interpretation, consent and reusable artifact preparation.

## Phase Objective

Haskell owns runtime host policy, typed effect interpretation, consent and reusable artifact preparation. Debian Linux is the Linux runtime contract; unsupported distributions fail before runtime provisioning. Platform-specific backend phases extend these capabilities without moving policy back into Python.

This phase needs Linux only. The declared tests are executable contracts; an absent required test is unmet evidence, not existing proof. Acceptance-only test implementations belong to the prerequisite owner named in the inventory. Existing incompatible code is inventoried in the deletion ledger. No old implementation or unqualified receipt establishes this revised contract.

## Gate Integrity

| Requirement | Oracle | Observer | Mutants | Tests |
|---|---|---|---|---|
| R22 — Native effects and runtime host facts | `tests/oracles/requirements.toml` | value; observer: independent inputs and nonce-bound native observations | `M-host-accepts-id-like`, `M-process-second-spawner` | `haskell:agentctl-core-test/Host/debian-exact-id`, `haskell:agentctl-core-test/Host/unsupported-linux-no-effects`, `haskell:agentctl-core-test/ProcessReal/timeout-cleans-up` |
| R15 — Provisioning plans, consent and owned publication | `tests/oracles/requirements.toml` | value; observer: independent inputs and nonce-bound native observations | `M-provision-privilege-implies-consent`, `M-provision-partial-publish` | `haskell:agentctl-core-test/Provision/idempotent-plan`, `haskell:agentctl-core-test/Provision/noninteractive-no-consent`, `haskell:agentctl-core-test/Provision/atomic-publish-and-lock` |

## Not Proven By This Gate

- A receipt's digest establishes input currency, not an independently attested historical run. Local receipt authenticity has the documented honest ceiling.
- A source rule or finite corpus does not prove arbitrary callback purity, universal termination or agent-internal readiness. Native operation and resource assumptions remain explicit.
- Foreign-kernel behavior is outside this phase's Linux verdict. Later native implementation extends the common contract and cannot retroactively add a foreign-hardware requirement here.

## Sprints

### Sprint 3.1: Native effects and runtime host facts [Planned]

**Status**: Planned
**Implementation**: `src/agentctl/haskell/src/AgentCtl/Process.hs`, `src/agentctl/haskell/src/AgentCtl/Native.hs`, `src/agentctl/haskell/src/AgentCtl/Host.hs`, `src/agentctl/haskell/src/AgentCtl/Paths.hs`
**Validation tests**: `haskell:agentctl-core-test/Host/debian-exact-id`, `haskell:agentctl-core-test/Host/unsupported-linux-no-effects`, `haskell:agentctl-core-test/ProcessReal/timeout-cleans-up`
**Mutants**: `M-host-accepts-id-like`, `M-process-second-spawner`
**Closes**: R22
**Docs to update**: `documents/architecture/python_haskell_boundary.md`, `documents/engineering/toolchain_bootstrap.md`, `documents/engineering/code_standards.md`

#### Objective

Native effects and runtime host facts supplies its complete owned contract through the single phase-scoped gate verdict.

#### Deliverables

Introduce tests/integration/test_owned_resources.py, including portable policy and actual host-specific cleanup branches later consumed by native acceptance. Gather immutable runtime facts in Haskell, including exact Debian identity from os-release. One process runner accepts absolute executables, literal argv, explicit environment and deadlines, drains bytes and preserves UTF-8/exit outcomes. Typed native filesystem/liveness operations expose no arbitrary global kill.

#### Validation

Accept Debian and reject an apt-bearing non-Debian host before any install effect. Construct malformed host facts, missing native handles, invalid UTF-8 and timeouts and require typed errors. Native OS ABI obligations name their own hardware lane.

Required executable evidence: `haskell:agentctl-core-test/Host/debian-exact-id`, `haskell:agentctl-core-test/Host/unsupported-linux-no-effects`, `haskell:agentctl-core-test/ProcessReal/timeout-cleans-up`. Every named mutant must die for its recorded reason in those tests; a baseline failure or unrelated exception is not a kill.

#### Remaining Work

The whole sprint.

### Sprint 3.2: Provisioning plans, consent and owned publication [Planned]

**Status**: Planned
**Implementation**: `src/agentctl/haskell/src/AgentCtl/Provision.hs`, `src/agentctl/haskell/src/AgentCtl/Provision/Artifact.hs`, `src/agentctl/haskell/src/AgentCtl/Protocol.hs`
**Validation tests**: `haskell:agentctl-core-test/Provision/idempotent-plan`, `haskell:agentctl-core-test/Provision/noninteractive-no-consent`, `haskell:agentctl-core-test/Provision/atomic-publish-and-lock`
**Mutants**: `M-provision-privilege-implies-consent`, `M-provision-partial-publish`
**Closes**: R15
**Docs to update**: `documents/architecture/python_haskell_boundary.md`, `documents/engineering/toolchain_bootstrap.md`, `documents/engineering/code_standards.md`

#### Objective

Provisioning plans, consent and owned publication supplies its complete owned contract through the single phase-scoped gate verdict.

#### Deliverables

Use pure dependency plans and explicit typed interpreters, shared for every runtime backend. Separate consent from privilege and from raw agent arguments. Noninteractive absent consent or privilege returns an actionable refusal; ordinary check never installs host packages or answers dialogs. Immutable artifact identity includes all build and policy inputs.

#### Validation

Observe one cold plan, an empty warm plan, concurrent winner reuse and failed publication preserving its predecessor. Block package-manager spawns in tests and prove the real runner's intended invocation through independent observers. Production preparation is an explicit pre-gate action, with a bound machine receipt.

Required executable evidence: `haskell:agentctl-core-test/Provision/idempotent-plan`, `haskell:agentctl-core-test/Provision/noninteractive-no-consent`, `haskell:agentctl-core-test/Provision/atomic-publish-and-lock`. Every named mutant must die for its recorded reason in those tests; a baseline failure or unrelated exception is not a kill.

#### Remaining Work

The whole sprint.

## Remaining Work

The whole phase: Sprints 3.1–3.2.

## Documentation Requirements

**Architecture docs to create/update:**

- `documents/architecture/python_haskell_boundary.md` — this phase's owned contract and links to prerequisite interfaces.

**Engineering docs to create/update:**

- `documents/engineering/toolchain_bootstrap.md` — doctrine, mechanisms and scope of executable evidence.
- `documents/engineering/code_standards.md` — doctrine, mechanisms and scope of executable evidence.

**Operations and reference docs to create/update:**

- None.

**Cross-references to add:**

- `DEVELOPMENT_PLAN/00-overview.md` — requirement closure and lower-phase dependencies.
- `DEVELOPMENT_PLAN/system-components.md` — stable capability/path ownership.
- `DEVELOPMENT_PLAN/legacy_tracking_for_deletion.md` — remaining incompatible implementation shapes.
