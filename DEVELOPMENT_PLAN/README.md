# agentctl Development Plan

**Status**: Authoritative source
**Supersedes**: `agentctl-plan.md`, the concept note this plan replaces; [the concept-note disposition](rationale.md#concept-note-disposition) records where every item in it went.

> **Purpose**: Carry the single cross-phase status table and the rules for working, validating and finishing the plan.

## How to Read This Plan

The plan is a build recipe. Its phases build agentctl from an empty repository, and their numbers are the execution
order: at phase *n* only the artifacts of phases at or below *n* exist, and every `**Depends on**` names a lower phase
([§ A](development_plan_standards.md#a-one-continuous-constructive-narrative)).

- Phases 0 and 1 are governance: this plan, both validators and the check skeleton, then the gate-integrity apparatus
  and the request-derived oracles, frozen before any product code exists.
- Phases 2 to 10 build the product: the toolchain bootstrap, the Haskell package and build, the multiplexer adapter,
  agent adapters and preflight, the launch command, session management, pane observation, the recovery state machine
  and the supervisor.
- Phases 11 to 14 are host-acceptance phases. They add no code: each runs the same gate on a live or foreign host and
  confirms what earlier phases owe it.

[00-overview.md](00-overview.md) holds the requirements and the architecture, [rationale.md](rationale.md) says why the
design has this shape, and [development_plan_standards.md](development_plan_standards.md) governs every file here.

## Current Phase Status

This table is the sole cross-phase status source, and every phase header's `**Status**` must equal its row.

| # | Phase | Status |
|---|---|---|
| 0 | [Governance, documentation standards and the check skeleton](phase-0-governance-and-check-skeleton.md) | Done |
| 1 | [Gate-integrity apparatus](phase-1-gate-integrity-apparatus.md) | Done |
| 2 | [Toolchain bootstrap](phase-2-toolchain-bootstrap.md) | Done |
| 3 | [Haskell package, quality legs and digest-keyed build](phase-3-haskell-package-and-build.md) | Done |
| 4 | [Multiplexer adapter](phase-4-multiplexer-adapter.md) | Done |
| 5 | [Agent adapters and preflight](phase-5-agent-adapters-and-preflight.md) | Done |
| 6 | [Launch command and passthrough](phase-6-launch-and-passthrough.md) | Done |
| 7 | [Session management and adoption](phase-7-session-management-and-adoption.md) | Done |
| 8 | [Pane observation and classification](phase-8-pane-observation-and-classification.md) | Done |
| 9 | [Recovery state machine and backoff](phase-9-recovery-state-machine.md) | Done |
| 10 | [Recovery supervisor](phase-10-supervisor.md) | Done |
| 11 | [Live agent acceptance](phase-11-live-agent-acceptance.md) | Done |
| 12 | [Clean-host bootstrap acceptance](phase-12-clean-container-acceptance.md) | Done |
| 13 | [macOS acceptance](phase-13-macos-acceptance.md) | Active |
| 14 | [Windows and psmux acceptance](phase-14-windows-psmux-acceptance.md) | Active |

## Working the Plan

`AGENTS.md`, which Sprint 0.6 writes, is the canonical home of the agent working rules; these steps are the plan's
side of them.

1. Take the lowest-numbered `Active` phase. When none is Active, take the lowest-numbered `Planned` phase whose
   dependencies are all `Done`, and set it and its first sprint to `Active`, together with its row here, in one
   change. The host-acceptance phases depend only on [Phase 10 — Recovery supervisor](phase-10-supervisor.md), so
   each is taken up whenever a host meeting its lane is available, whatever the state of the others.
2. Within that phase, work the `Active` sprint first, then the `Planned` sprints in id order, setting each to `Active`
   as it starts. When the Active sprint's Remaining Work names a later sprint of the same phase, work in id order until
   that sprint is `Done`, then close the Active one.
3. A sprint closes when its Validation tests exist, are collected and pass, its applicable mutants are killed by
   the tests they name, and `agentctl check` passes. Its Status becomes `Done` and its Remaining Work becomes `None.`
   Before Sprint 1.2 introduces the mutant runner, Phase 0 uses its direct negative-control tests; its declared
   mutants become mandatory in Sprint 1.2 and re-prove Phase 0 on every run thereafter (§ M).
4. A phase closes when its last sprint closes and `agentctl check` passes on a host meeting its `**Host lane**`. Its
   header and its row here become `Done` in the same change.
5. A host-acceptance phase records, as its `**Gate evidence**`, the `EVIDENCE` line that passing run printed.
6. A change under a covered path (`src/`, `tests/` or `pyproject.toml`) reopens every Done host-acceptance phase in the
   same change: its Status and its row here return to `Active`, and its Gate evidence to `none recorded`.
7. A design error is fixed by rewriting the phase that introduced it, and validation resumes from that phase.
8. Agents never run `git add`, `git commit` or `git push`, or move HEAD. Commits and human review are optional and
   never block closure or phase advancement ([§ P](development_plan_standards.md#p-the-ratchet-and-automatic-closure)).
   After a qualifying gate pass, update the plan and continue to the next eligible sprint or phase.

## Validation Policy

A phase is `Done` when its own gate passes on a host meeting its Host lane, the governed documents it names are
aligned with what it built, and no work remains in its scope.

- Every validation criterion is executable by an agent without human intervention. No commit, clean worktree,
  review, approval, manual attestation, answered dialog or requested screen capture is a closure condition. Agents
  record machine-observed host evidence; unavailable capabilities remain unmet, and activities listed as not proven
  are outside the gate rather than manual work owed before closure.
- `agentctl check` is the only gate, and it takes no arguments. Focused tests and application-owned build calls help
  while working and never close a sprint or a phase. Agents never invoke cabal or the core binary directly.
- A **self-verifying** phase is re-proved by every check run: the tests its sprints cite are collected and pass, and
  its applicable mutants are killed, in that run, so the phase stores nothing. The Phase 0 activation boundary above
  requires no mutation claim before the runner exists and permits no later exemption.
- A **host-acceptance** phase adds no code. It records the EVIDENCE line of a passing run on its lane, and the plan
  validator recomputes that row's tree digest and compares its lane. A digest proves the tree is current, not that a
  run happened.
- What counts as evidence is in [§ L](development_plan_standards.md#l-evidence-classes-and-what-cannot-count); the
  gate, its kinds and the lanes are in [§ N](development_plan_standards.md#n-the-single-gate-gate-kinds-and-host-lanes);
  the no-skip suite is in [§ O](development_plan_standards.md#o-the-no-skip-suite-and-host-state-adaptivity); the
  ratchet and automatic closure are in
  [§ P](development_plan_standards.md#p-the-ratchet-and-automatic-closure).

## Definition of Done

A phase is `Done` when all of these hold:

1. Every sprint is `Done` with Remaining Work `None.`, the phase's own Remaining Work is `None.`, and every phase it
   depends on is `Done` — enforced by `plan.status-consequences`.
2. Every Validation test its sprints cite was collected and passed in this check run, and every Implementation path
   they cite exists — enforced by `plan.cited-ids` and `plan.cited-paths`.
3. Every Gate Integrity row's applicable mutants exist and name that row's tests as killers, and each `owed` entry
   and acceptance `## Confirms` entry match in both directions — enforced by `plan.gate-integrity`. Phase 0's
   declared mutants activate in Sprint 1.2; direct negative controls are required before that boundary.
4. `agentctl check` passes on a host meeting the phase's Host lane, and a host-acceptance phase's Gate evidence row
   matches its lane and the current tree — enforced by `plan.lanes` and `plan.evidence-rows`.
5. The phase header's Status equals its row in the status table, and no governed document states a phase's status
   — enforced by `plan.status-harmony` and `docs.no-status`.

## Exit Definition

The plan is complete when every requirement in [00-overview.md](00-overview.md#requirements) is closed and every phase
is `Done`.

## Document Index

| File | Purpose |
|---|---|
| [README.md](README.md) | This file: the status table and the rules for working the plan |
| [development_plan_standards.md](development_plan_standards.md) | How the plan is structured and how status and evidence are earned |
| [00-overview.md](00-overview.md) | The architecture, the requirements table, phase responsibilities, the dependency flow and non-goals |
| [system-components.md](system-components.md) | The inventory of modules, test apparatus, external tools and per-user directories |
| [rationale.md](rationale.md) | The verbatim request, decisions, design justification, rejected alternatives and the concept-note disposition |
| [legacy_tracking_for_deletion.md](legacy_tracking_for_deletion.md) | Unwanted shapes still standing in the tree, each with the phase that deletes it |
| [phase-0-governance-and-check-skeleton.md](phase-0-governance-and-check-skeleton.md) | The governed suite, the package skeleton, `agentctl check` with its Python legs, the gate plugin, both validators and the root documents |
| [phase-1-gate-integrity-apparatus.md](phase-1-gate-integrity-apparatus.md) | The oracle store and frozen request-derived oracles, mutants, the ratchet and write-guard, the spawn audit, source guards, coverage, closure rules and the evidence line |
| [phase-2-toolchain-bootstrap.md](phase-2-toolchain-bootstrap.md) | Host facts, OS prerequisites with consent, ghcup reuse or the pinned download, the pinned GHC and cabal, and the clean-lane recipe |
| [phase-3-haskell-package-and-build.md](phase-3-haskell-package-and-build.md) | The Cabal project, the build, test, fourmolu and hlint legs, the handshake and the digest-keyed build |
| [phase-4-multiplexer-adapter.md](phase-4-multiplexer-adapter.md) | tmux and psmux resolution and floors, the typed command vocabulary and its one runner, the pane trampoline and the fake agent |
| [phase-5-agent-adapters-and-preflight.md](phase-5-agent-adapters-and-preflight.md) | The agent table, launch argv, auth classification and login refusals, and preflight with the opaque `Ready` |
| [phase-6-launch-and-passthrough.md](phase-6-launch-and-passthrough.md) | Folder-derived session names, launch orchestration, raw passthrough and the handoff |
| [phase-7-session-management-and-adoption.md](phase-7-session-management-and-adoption.md) | `list`, `status`, `attach`, `stop` and `adopt` |
| [phase-8-pane-observation-and-classification.md](phase-8-pane-observation-and-classification.md) | Capture, normalisation, fingerprints and the per-agent screen classifiers |
| [phase-9-recovery-state-machine.md](phase-9-recovery-state-machine.md) | The pure transition function, its safety predicates, and bounded backoff with seeded jitter |
| [phase-10-supervisor.md](phase-10-supervisor.md) | The watch commands, `supervisor run`, the decision log and the scenario matrix |
| [phase-11-live-agent-acceptance.md](phase-11-live-agent-acceptance.md) | `agentctl check` on a host where both agents are logged in |
| [phase-12-clean-container-acceptance.md](phase-12-clean-container-acceptance.md) | The two-stage clean-host run that starts from pipx alone |
| [phase-13-macos-acceptance.md](phase-13-macos-acceptance.md) | `agentctl check` on macOS |
| [phase-14-windows-psmux-acceptance.md](phase-14-windows-psmux-acceptance.md) | `agentctl check` on Windows with psmux |

## Related

- [development_plan_standards.md](development_plan_standards.md) — the rules this file applies.
- [00-overview.md](00-overview.md) — the requirements the Exit Definition refers to.
- [system-components.md](system-components.md) — where each component lives and which phase owns it.
- [rationale.md](rationale.md) — why the plan has this shape and what it rejects.
- [legacy_tracking_for_deletion.md](legacy_tracking_for_deletion.md) — shapes still standing and their deleting phases.
- [documents/README.md](../documents/README.md) — the index of the governed documentation.
