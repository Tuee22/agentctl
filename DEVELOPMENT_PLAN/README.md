# agentctl Development Plan

**Status**: Authoritative source
**Supersedes**: N/A

> **Purpose**: Own the phase status table, execution order and independent evidence needed to build and finish the product.

## How to Read This Plan

The plan is a constructive recipe. Earlier phases define complete narrow contracts; later phases extend those
contracts without replacing them. Existing incompatible implementations are migration inputs owned in
[the deletion ledger](legacy_tracking_for_deletion.md), not evidence that a revised contract is complete.
[The standards](development_plan_standards.md) govern structure and closure; [the overview](00-overview.md)
owns requirements, architecture and capability dependencies.

- Governance and independent phase evidence precede strict Python enforcement and migration.
- Minimal Python bootstrap precedes Haskell runtime provisioning, Debian tmux, launch, sessions, observation and recovery.
- Native Windows preparation and qualification extend those common contracts using one private source-built backend.
- Linux clean/live, native Windows and native macOS evidence are earned separately. Final Linux aggregation reads
  their current receipts without needing both foreign hardware families in one phase.

## Current Phase Status

| # | Phase | Status |
|---|---|---|
| 0 | [Governance and phase evidence](phase-0-governance-and-phase-evidence.md) | Active |
| 1 | [Python discipline and gate integrity](phase-1-python-discipline-and-gate-integrity.md) | Planned |
| 2 | [Python bootstrap and handoff](phase-2-python-bootstrap-and-handoff.md) | Planned |
| 3 | [Haskell runtime and platform policy](phase-3-haskell-runtime-and-platform-policy.md) | Planned |
| 4 | [Debian tmux and multiplexer](phase-4-debian-tmux-and-multiplexer.md) | Planned |
| 5 | [Agent preflight and launch](phase-5-agent-preflight-and-launch.md) | Planned |
| 6 | [Session management and adoption](phase-6-session-management-and-adoption.md) | Planned |
| 7 | [Pane observation and classification](phase-7-pane-observation-and-classification.md) | Planned |
| 8 | [Recovery and supervisor](phase-8-recovery-and-supervisor.md) | Planned |
| 9 | [Windows toolchain and psmux build](phase-9-windows-toolchain-and-psmux-build.md) | Planned |
| 10 | [Windows backend qualification](phase-10-windows-backend-qualification.md) | Planned |
| 11 | [Windows application acceptance](phase-11-windows-application-acceptance.md) | Planned |
| 12 | [Linux live and clean acceptance](phase-12-linux-live-and-clean-acceptance.md) | Planned |
| 13 | [macOS acceptance](phase-13-macos-acceptance.md) | Planned |
| 14 | [Release evidence and closure](phase-14-release-evidence-and-closure.md) | Planned |

## Working the Plan

1. Work the lowest Active phase. Otherwise select the lowest eligible Planned phase whose declared prerequisites
   are Done. Update its header, first sprint and row here together.
2. Work its Active sprint, then its Planned sprints in order. A planned revised contract can have standing
   implementation artifacts; its ledger rows describe precisely what is not accepted. If an Active sprint needs a named later sprint of the same phase to provide its gate instrumentation, keep it Active, work those sprints in order, then return to close it; this grants no dependency on a later phase.
3. Run the sole no-argument gate, `agentctl check`. It inventories and runs every present test/leg and reports
   independent phase/lane verdicts alongside the overall checkout result. It neither skips nor deselects tests.
4. Close a sprint only from a complete passing verdict covering its required artifacts, tests, applicable
   mutants, coverage, prerequisites, documentation and hardware. A later owned failure stays visible without
   invalidating an earlier complete verdict. Shared integrity failures invalidate all affected consumers.
5. A phase closes only when all its sprints close and its required lane receipts match current phase input
   identities. Set every completed Remaining Work to `None.` and its row/header to Done together.
6. Each phase needs Linux and at most one additional native family, Windows or macOS. Dedicated WSL2 is Linux
   evidence only, under the [validation runbook](../documents/operations/validation_runbook.md). Missing native
   capability remains unmet; it never becomes a documented-fixture or manual-attestation pass.
7. A changed contract is rewritten at its owning phase, and its affected prerequisite consumers lose closure
   until re-proved. Evidence invalidation follows the declared input graph, not numbering or every later file.
8. Never stage, commit, push or move HEAD. No clean tree, review, dialog or human checkpoint is a closure
   prerequisite. Use current executable receipts and continue to the next eligible phase.

## Validation Policy

The gate implementation and validators are governed implementation work; specification edits do not prove them.
The first Active phase migrates the existing global early-abort gate and old status/evidence assumptions.
The `PHASE` receipt is the phase closure authority; the aggregate `EVIDENCE` receipt is whole-product closure.
A nonzero overall exit from a later failure cannot erase an independently trustworthy earlier passing receipt.
A shared write-guard, collection, nonce, source census or containment failure cannot be attributed away.

Each phase receipt binds its stable capability owner, required test/mutant/coverage set, prerequisite receipts,
all owned/shared input bytes, relevant tool/backend identities and actual host facts. Later-only files do not
enter an earlier input closure. Final release evidence binds the complete source tree and all required native
receipts. A local digest proves currency, not historical authenticity.

## Definition of Done

- All owned sprint contracts are implemented and their required executable evidence is present and passing.
- Every requirement has one closing sprint and every standing incompatible shape has a non-Done deletion owner.
- Every present first-party artifact is censused; no legacy label conceals code, tests, failures or coverage.
- Declared Linux and optional foreign receipts are current; shared prerequisite evidence is trustworthy.
- Every deletion row owned by the closing phase is removed with its actual shape.
- Governed docs, source contracts, validators, runtime behavior and the status table agree.
- The only closure command is `agentctl check`; focused tools supply development evidence, never closure.

## Exit Definition

Every requirement in [the overview](00-overview.md#requirements) is closed, every phase is Done, the
[ledger](legacy_tracking_for_deletion.md) is empty, and the aggregate gate verdict passes with current
native receipts. Build/install preparation and publication are separate from noninteractive gate execution.

## Document Index

| File | Purpose |
|---|---|
| [README.md](README.md) | Execution and the sole cross-phase status source |
| [development_plan_standards.md](development_plan_standards.md) | Phase structure, ownership, evidence, hardware and closure |
| [00-overview.md](00-overview.md) | Product requirements and additive architecture |
| [system-components.md](system-components.md) | Stable capability, module, resource and test ownership |
| [rationale.md](rationale.md) | Request anchors, current decisions, amendment precedence and alternatives |
| [legacy_tracking_for_deletion.md](legacy_tracking_for_deletion.md) | Standing incompatible shapes and their deletion owners |
| [phase-0-governance-and-phase-evidence.md](phase-0-governance-and-phase-evidence.md) | The governed target architecture, requirement ownership, legacy census and one gate with independent phase and lane verdicts |
| [phase-1-python-discipline-and-gate-integrity.md](phase-1-python-discipline-and-gate-integrity.md) | Project-owned strict Python doctrine, local executable enforcement, typed native boundaries and migration of existing package, gate and test code |
| [phase-2-python-bootstrap-and-handoff.md](phase-2-python-bootstrap-and-handoff.md) | A portable pipx/Click entry point and only the Python work needed before Haskell exists: bootstrap directories, pinned ghcup/GHC/cabal, native source build and raw handoff |
| [phase-3-haskell-runtime-and-platform-policy.md](phase-3-haskell-runtime-and-platform-policy.md) | Haskell owns runtime host policy, typed effect interpretation, consent and reusable artifact preparation |
| [phase-4-debian-tmux-and-multiplexer.md](phase-4-debian-tmux-and-multiplexer.md) | The common checked-backend interface and Debian tmux implementation, including Haskell-owned APT provisioning and a private pane trampoline |
| [phase-5-agent-preflight-and-launch.md](phase-5-agent-preflight-and-launch.md) | User-installed agent discovery, authentication refusal, immutable argv assembly and folder-derived launch/reattach |
| [phase-6-session-management-and-adoption.md](phase-6-session-management-and-adoption.md) | Session management and adoption use checked instance identity and retain the distinction between access, ownership and supervision |
| [phase-7-pane-observation-and-classification.md](phase-7-pane-observation-and-classification.md) | The generic observation and guarded-input contract precedes recovery and every foreign backend |
| [phase-8-recovery-and-supervisor.md](phase-8-recovery-and-supervisor.md) | The complete Linux recovery application consumes the already-qualified observation and conditional-submission capability |
| [phase-9-windows-toolchain-and-psmux-build.md](phase-9-windows-toolchain-and-psmux-build.md) | Haskell prepares native Windows build dependencies and compiles pinned psmux sources locally |
| [phase-10-windows-backend-qualification.md](phase-10-windows-backend-qualification.md) | Qualify the exact native candidate for attached-client memory behavior, capture correctness, exact identity and guarded input |
| [phase-11-windows-application-acceptance.md](phase-11-windows-application-acceptance.md) | Native Windows acceptance of the shared application, private psmux artifact and registered resources |
| [phase-12-linux-live-and-clean-acceptance.md](phase-12-linux-live-and-clean-acceptance.md) | Debian clean-host and logged-in agent acceptance, with dedicated WSL2 permitted for Linux evidence on a Windows host |
| [phase-13-macos-acceptance.md](phase-13-macos-acceptance.md) | The additive Darwin implementation and native acceptance of bootstrap, process/filesystem semantics and the common tmux backend contract |
| [phase-14-release-evidence-and-closure.md](phase-14-release-evidence-and-closure.md) | Whole-product closure joins current independent native receipts and requires an empty migration ledger |

## Related

- [standards](development_plan_standards.md) — governance.
- [overview](00-overview.md) — requirements and dependencies.
- [documents](../documents/README.md) — contract homes.
- [agent rules](../AGENTS.md) — repository working policy.
