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
- Linux clean/live, native Windows and native macOS evidence are earned separately as halves. A run natively
  evaluates only the halves its host qualifies and reads every other half from the latest stored receipt with
  equal identities ([T.V](development_plan_standards.md#tv-verdict) V8), so no phase needs both foreign families.
- The plan is well-ordered ([§ A](development_plan_standards.md#a-well-ordered-constructive-narrative)): a later
  phase never contradicts or undoes an earlier one, and incomplete later work never blocks validating an earlier
  one. Apart from the shared failures of [T.F](development_plan_standards.md#tf-shared-and-owned-failures), an
  earlier verdict and identity ([T.I](development_plan_standards.md#ti-identity)) depend only on its closure.

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

## Validation Hosts

| Capability | Available | Provided by |
|---|---|---|
| `linux` | yes | dedicated VirtualBox guest |
| `windows` | yes | this host |
| `macos` | no | the user will provide a Mac |
| `linux-clean` | yes | agent-installed container runtime in the guest |
| `linux-live` | yes | guest with shared host credentials |
| `setup:agents-logged-in` | yes | agent |
| `setup:msvc-build-tools` | yes | agent |
| `setup:container-runtime` | yes | agent |
| `setup:agent-permissions` | yes | agent |
| `setup:xcode-clt` | no | the user, with the Mac |

Available is `yes` or `no`. The table changes only when hardware or setup changes, and it changes selection,
never a verdict ([T.C](development_plan_standards.md#tc-ceiling) C7): a phase awaiting a `no` row is blocked
([T.D](development_plan_standards.md#td-status-and-progression)). Host provision is only the Mac and its
Command Line Tools, which the `macos` and `setup:xcode-clt` rows record: the user supplies the tools with the Mac
because their installation needs a dialog that a person completes, and no other row is host provision (D-158).
Such a row reads `yes` once the user has supplied it and its probe reports presence.

## Working the Plan

1. Take the action of the latest verified run's `selection:` line. Until the gate prints one, work the lowest
   Active phase whose awaited halves are available; otherwise activate the lowest Planned phase whose
   prerequisites are Done, updating its header, first sprint, its Remaining Work (the
   [§ C](development_plan_standards.md#c-honest-completion-tracking) table naming every planned node, mutant id
   and rule it owes) and its row here together.
2. Work Active sprints, then Planned sprints in order. A later sprint of the same phase may supply an Active
   sprint's gate instrumentation; this grants no dependency on a later phase.
3. Run `agentctl check` only on the triggers of the [testing-cost method](../AGENTS.md#testing-cost-method) in
   `AGENTS.md`. It takes no arguments, runs every present test and leg and skips or deselects none; its verified
   parent publishes one verdict line per phase ([T.O](development_plan_standards.md#to-output)).
4. A sprint is Done when a verified run shows its paths present, its cited tests passed and its cited mutants
   killed ([T.D](development_plan_standards.md#td-status-and-progression)). A phase is Done only on its verified
   `pass`, with all sprints Done, Remaining Work `None.` and no ledger row naming it, set in one edit.
5. A failing Done phase is regressed and is repaired in place. Regressed, awaiting and blocked are computed,
   never authored.
6. Each phase needs Linux and at most one additional native family, Windows or macOS. A dedicated VirtualBox
   guest supplies only the Linux halves, under the [validation runbook](../documents/operations/validation_runbook.md).
   A `no` capability in Validation Hosts blocks only the phases that await it; a missing capability never becomes
   a documented-fixture or manual-attestation pass.
7. Keep the plan well-ordered ([§ A](development_plan_standards.md#a-well-ordered-constructive-narrative)): a
   later phase never removes, reverses, weakens or silently strengthens what an earlier phase owns, and it edits
   an earlier-owned file only while every Done phase passes.
8. Never stage, commit, push or move HEAD. No clean tree, review or human action inside a run is a closure
   prerequisite, and no run, check or agent answers a dialog; host provision that Validation Hosts records
   changes only selection ([T.C](development_plan_standards.md#tc-ceiling) C7, D-128).
9. Run any test or `agentctl check` natively on the Windows host or the Mac only as the interim native-run rule
   of [The Gate](../AGENTS.md#the-gate) in `AGENTS.md` allows (D-181), and keep every test within the closed list
   of [§ Q](development_plan_standards.md#q-containment-and-user-state-protection) that `AGENTS.md` links (D-172).

## Validation Policy

[§ T](development_plan_standards.md#t-unspoofable-evidence-and-phase-verdicts) defines admissible evidence and
phase verdicts. The gate implementation and validators are governed implementation work; specification edits do
not prove them. [Governance and phase evidence](phase-0-governance-and-phase-evidence.md) migrates the existing
gate and its old status and evidence assumptions to these verdicts. The `PHASE` line that the verified parent
publishes is the phase closure authority, and `EVIDENCE pass` is whole-product closure
([T.O](development_plan_standards.md#to-output)). An earlier passing verdict that satisfies § T survives a later
owned failure and a nonzero overall exit; a shared failure of
[T.F](development_plan_standards.md#tf-shared-and-owned-failures) fails every phase and cannot be attributed away.

Each phase receipt binds its phase, half, per-closure identity ([T.I](development_plan_standards.md#ti-identity)),
nonce, required test, mutant and coverage sets, prerequisite identities, relevant tool and backend identities and
observed host facts. Later-only files and rows never enter an earlier identity. Final release evidence binds the
complete source tree and a current receipt for every required half. What a digest or stored receipt proves is
bounded by [T.C](development_plan_standards.md#tc-ceiling).

## Definition of Done

- The phase's verdict is `pass` in a verified run: [T.V](development_plan_standards.md#tv-verdict) holds over its
  closure at its stage, with each required half native to the run or current in the receipt store.
- All owned sprint contracts are implemented, every sprint is Done and Remaining Work is `None.`.
- Every requirement has one closing sprint, and every standing incompatible shape or unmet documented target has
  a non-Done ledger owner.
- Every present first-party artifact is censused; no legacy label conceals code, tests, failures or coverage.
- Every prerequisite passes under the same per-half rule, and the run has no shared failure.
- No ledger row names the phase; each row it owned is removed with its actual shape.
- Governed docs, source contracts, validators, runtime behavior and the status table agree.
- The only closure command is `agentctl check`; focused tools, including the stepwise sweep, supply development
  evidence, never closure.

## Exit Definition

Exit is `EVIDENCE pass`: every requirement in [the overview](00-overview.md#requirements) is closed, every phase
is Done and passes with every half current, and the [ledger](legacy_tracking_for_deletion.md) is empty. Until the
Mac and its Command Line Tools exist, selection works [macOS acceptance](phase-13-macos-acceptance.md) while its
verdict is `fail`; it is blocked as `awaiting:macos` only once its `linux` half passes and its `macos` half is its
only gap. The terminal state is then `selection: stop`, which lists only what macOS acceptance and, through it,
[Release evidence and closure](phase-14-release-evidence-and-closure.md) still await: the Mac and its Command
Line Tools. Build/install preparation and publication are separate from noninteractive gate execution.

## Document Index

| File | Purpose |
|---|---|
| [README.md](README.md) | Own the phase status table, execution order and independent evidence needed to build and finish the product |
| [development_plan_standards.md](development_plan_standards.md) | Define a well-ordered constructive plan whose phase verdicts are unspoofable, decidable by one gate run and bounded in hardware |
| [00-overview.md](00-overview.md) | Define the additive architecture, stable requirements, phase responsibilities and scope of completion |
| [system-components.md](system-components.md) | Inventory target capabilities, paths, tools and private resources with a single substantive phase owner |
| [rationale.md](rationale.md) | Preserve request anchors, identify current decision precedence, explain the target architecture and retain concept-note provenance |
| [legacy_tracking_for_deletion.md](legacy_tracking_for_deletion.md) | Inventory standing incompatible implementations and assign each migration to its contract owner |
| [phase-0-governance-and-phase-evidence.md](phase-0-governance-and-phase-evidence.md) | Parent-published phase verdicts that satisfy [§ T](development_plan_standards.md#t-unspoofable-evidence-and-phase-verdicts) at stage 1, the governed plan and ownership census, and verdict-driven progression |
| [phase-1-python-discipline-and-gate-integrity.md](phase-1-python-discipline-and-gate-integrity.md) | Project-owned strict Python doctrine, local executable enforcement, typed native boundaries, the stage-2 evidence checkers and migration of existing Governance package, gate and test code |
| [phase-2-python-bootstrap-and-handoff.md](phase-2-python-bootstrap-and-handoff.md) | Portable pipx installation, raw Click command transport and only the Python work needed before Haskell exists: bootstrap directories, pinned ghcup/GHC/cabal, native source build and raw handoff |
| [phase-3-haskell-runtime-and-platform-policy.md](phase-3-haskell-runtime-and-platform-policy.md) | Haskell owns runtime host policy, typed effect interpretation, consent and reusable artifact preparation |
| [phase-4-debian-tmux-and-multiplexer.md](phase-4-debian-tmux-and-multiplexer.md) | The common checked-backend interface and Debian tmux implementation, including Haskell-owned APT provisioning and a private pane trampoline |
| [phase-5-agent-preflight-and-launch.md](phase-5-agent-preflight-and-launch.md) | User-installed agent discovery, authentication refusal, immutable argv assembly and folder-derived launch/reattach |
| [phase-6-session-management-and-adoption.md](phase-6-session-management-and-adoption.md) | Session management and adoption use checked instance identity and retain the distinction between access, ownership and supervision |
| [phase-7-pane-observation-and-classification.md](phase-7-pane-observation-and-classification.md) | The generic observation and guarded-input contract precedes recovery and every foreign backend |
| [phase-8-recovery-and-supervisor.md](phase-8-recovery-and-supervisor.md) | The complete Linux recovery application consumes the already-qualified observation and conditional-submission capability |
| [phase-9-windows-toolchain-and-psmux-build.md](phase-9-windows-toolchain-and-psmux-build.md) | The Windows entry of binder, receipt transport and native gate precedes Haskell preparation of native Windows build dependencies and local compilation of pinned psmux sources |
| [phase-10-windows-backend-qualification.md](phase-10-windows-backend-qualification.md) | Qualify the exact native candidate for attached-client memory behavior, capture correctness, exact identity and guarded input |
| [phase-11-windows-application-acceptance.md](phase-11-windows-application-acceptance.md) | Native Windows acceptance of the shared application, private psmux artifact and registered resources |
| [phase-12-linux-live-and-clean-acceptance.md](phase-12-linux-live-and-clean-acceptance.md) | Debian clean-host and logged-in agent acceptance, with a dedicated Debian VirtualBox VM for Linux evidence on a Windows host |
| [phase-13-macos-acceptance.md](phase-13-macos-acceptance.md) | The native Darwin gate entry and observers, the additive Darwin implementation and native acceptance of bootstrap, process/filesystem semantics and the common tmux backend contract |
| [phase-14-release-evidence-and-closure.md](phase-14-release-evidence-and-closure.md) | Whole-product closure joins every phase's current verified halves and requires an empty migration ledger |

## Related

- [standards](development_plan_standards.md) — governance.
- [overview](00-overview.md) — requirements and dependencies.
- [documents](../documents/README.md) — contract homes.
- [agent rules](../AGENTS.md) — repository working policy.
