# agentctl Development Plan Standards

**Status**: Authoritative source
**Supersedes**: N/A

> **Purpose**: Define how the agentctl plan is structured, how a phase or sprint earns its status, and what counts as evidence.

This file states governance only; [§ S](#s-contract-homes) names the home of each product contract. A rule enforced
mechanically names its validator check and the sprint that lands it; a rule that names no check is applied when the
user reviews the change.

## Core Principles

### A. One Continuous Constructive Narrative

The plan is a build recipe, not a repair log: following the phases in numeric order, with only the artifacts of
phases at or below *n* present at phase *n*, builds agentctl from an empty repository.

- **Numbers are execution order.** `**Depends on**` names only strictly lower phases, host-acceptance phases are
  terminal, and Remaining Work never cites a later phase, since "closes once the supervisor exists" written there is a
  forward dependency in prose (`plan.dependency-direction`, Sprint 0.5). Who owns what belongs in `## Phase Objective`.
- **Strictly additive, with no stubs.** A later phase extends an earlier phase's contract and never removes, replaces
  or reverses it; a sprint lands the real, narrow surface it names, with its tests, never a placeholder or canned
  value for a later sprint to replace.
- **A design error rewrites the phase that introduced it,** in place, and validation resumes from there; it never
  becomes a corrective sprint, a reopening narrative or a cleanup phase. Host-acceptance phases add no code, so a
  failure they expose is fixed in the phase that introduced its cause.
- **Governance comes first.** [Phase 0 — Governance, documentation standards and the check skeleton](phase-0-governance-and-check-skeleton.md)
  builds this plan, both validators and the check skeleton, and
  [Phase 1 — Gate-integrity apparatus](phase-1-gate-integrity-apparatus.md) freezes the request-derived oracles and
  the gate apparatus before any product code exists.

### B. Detailed, Implementation-Oriented Content

- The plan names real paths, modules, oracle files, node ids, mutant ids, check steps and validator checks, verbatim
  from [system-components.md](system-components.md) and the [requirements table](00-overview.md#requirements).
  Examples never contradict the architecture: TOML rows and `console` lines of `agentctl ...` are fine, fenced type
  signatures are not (a sketch becomes a second home for an API), and every fence carries a language tag.
- Every external tool fact (flag, exit code, version, URL, path) comes from
  [external tool facts](../documents/reference/external_tool_facts.md), with its version and verification command.

### C. Honest Completion Tracking

| Status | Meaning |
|---|---|
| `Done` | Built; its own gate passes on a host meeting its lane; its governed documents are aligned; nothing remains |
| `Active` | Partly built; `## Remaining Work` names what is owed |
| `Planned` | Not started |

There is no `Blocked`: a phase depends only on lower phases, so nothing waits on later work, and an unstarted phase
whose dependencies are not Done is simply not reached. There is no `Superseded`: a wrong phase is rewritten (§ A).

- **Closed values, checked consequences** (`plan.header`, `plan.sprint-structure`, `plan.status-consequences`, all
  Sprint 0.5). A Done sprint's Remaining Work is `None.`; an Active sprint or phase names what remains; a phase is
  Done only when every sprint is, and Active or Done only when every phase it depends on is Done.
- **Derived from the repository, re-proved by every run.** Status is set by checking what exists, never carried
  over: every check run requires each Done sprint's Validation tests to be collected and pass (`plan.cited-ids`) and
  its Implementation paths to exist (`plan.cited-paths`), and holds Done phases to their lanes (§ N), all from
  Sprint 1.5. The [status table](README.md#current-phase-status) is the only roll-up (§ J).
- **No hand-typed counts.** Test totals, pass counts and mutant kills exist only in the output of the run that
  produced them (`plan.no-narrative`, Sprint 0.5).

### D. Declarative Current-State Language

- Plan text says what each phase builds, in the present tense ("the binary resolves the agent to an absolute path"),
  never "will resolve", "is replaced by" or "no longer"; the present tense claims nothing about completion.
- No plan text narrates history or carries a date other than an evidence row (§ N), and no phase or sprint title
  carries `Historical`, `Superseded`, `Corrected`, `Deprecated` or `Legacy` (`plan.no-narrative`, Sprint 0.5). In
  `documents/`, dates appear only as fact provenance in external tool facts.
- Git holds the history. A rejected shape is named only in [rationale.md](rationale.md#rejected-alternatives), as
  present-tense justification, never as a chronicle.

### E. One Canonical Folder Model

- The set is fixed. `DEVELOPMENT_PLAN/` holds exactly `README.md`, `development_plan_standards.md`, `00-overview.md`,
  `system-components.md`, `rationale.md`, `legacy_tracking_for_deletion.md`, and one `phase-N-<slug>.md` per row of
  the status table, numbered contiguously from 0, as the [document index](README.md#document-index) lists them. A
  missing or extra file, a gap or a duplicate fails `plan.fileset` (Sprint 0.5). Each companion file opens with a
  title, `**Status**`, `**Supersedes**` and `> **Purpose**`, and ends with `## Related`.
- A phase's identity is its title. Inserting a phase renumbers every later one and updates `README.md`,
  `00-overview.md` and `system-components.md` in the same change. `documents/` cites by title and is unaffected, and
  no path outside `DEVELOPMENT_PLAN/` carries a phase ordinal: oracles, mutants and modules are named by capability.
- `documents/` is the only documentation root, with `architecture/`, `engineering/`, `operations/` and `reference/`
  (`docs.taxonomy`, Sprint 0.4).

### F. System Component Inventory

[system-components.md](system-components.md) lists what the phases build and where: the Python package, the Haskell
package, the test apparatus, the external tools and who invokes each, and the per-user directories, each with its
owning phase, plus the single owner of every invariant that spans both layers. It owns no contract: it summarises and
links, because once two homes for one contract disagree nothing says which is right. It carries no status and no
counts, and it changes in the same change as the component, its owning phase and its canonical document.

### G. Phase and Sprint Document Requirements

A phase file opens with this closed header:

```text
# Phase N — <Title>

**Status**: Planned
**Depends on**: [Phase M — <Title>](phase-M-<slug>.md)
**Host lane**: <lane>
**Gate**: `agentctl check`
**Gate kind**: self-verifying
**Closes**: R5, R14

> **Purpose**: <one sentence naming what this phase adds to the build>.
```

Its sections follow in order: `## Phase Objective`, `## Gate Integrity`, `## Not Proven By This Gate`, `## Confirms`
(host-acceptance only), `## Sprints`, `## Remaining Work`, `## Documentation Requirements`. No other header field
exists (`plan.header`, Sprint 0.5).

| Field | Rule | Enforced by |
|---|---|---|
| Status | `Planned`, `Active` or `Done`; equals the phase's status-table row | `plan.header`, `plan.status-harmony` (Sprint 0.5) |
| Depends on | links to strictly lower phases; `nothing` for [Phase 0 — Governance, documentation standards and the check skeleton](phase-0-governance-and-check-skeleton.md) | `plan.dependency-direction` (Sprint 0.5) |
| Host lane | one lane of the § N table | `plan.lanes` (Sprint 1.5) |
| Gate | always `agentctl check` | `plan.header` (Sprint 0.5) |
| Gate kind | `self-verifying` or `host-acceptance` | `plan.header` (Sprint 0.5) |
| Closes | requirement ids separated by `, `, or `none`; equals the union of its sprints' Closes | `plan.requirements-table` (Sprint 0.5) |
| Gate evidence | host-acceptance only, after Closes; `none recorded` until a row is recorded (§ N) | `plan.evidence-rows` (Sprint 1.5) |
| Evidence covers | host-acceptance only, after Gate evidence; exactly `` `src/` `tests/` `pyproject.toml` `` | `plan.evidence-rows` (Sprint 1.5) |

- **Gate Integrity** is a table headed `| Requirement | Oracle | Observer | Mutants | Tests |` with at least one row
  per id in Closes (rows for ids the phase only contributes to are allowed). Requirement reads
  `R8 — <short statement>`; Oracle holds backticked oracle paths or `none — <reason>`; Observer holds `; `-separated
  entries, each opening with an evidence class (§ L): `value:`, `real:`, `observer:` or
  `owed: <acceptance-phase-slug>`; Mutants holds explicit ids (§ M); Tests holds their killers. Every `owed:` entry
  appears, with its requirement id, in that phase's `## Confirms` (`plan.gate-integrity`, Sprint 1.5).
- **Not Proven By This Gate** bullets each end `— owed to [Phase 11 — Live agent acceptance](phase-11-live-agent-acceptance.md).`
  (or another acceptance phase) or `— not proven by any phase.` Every phase lists the ceiling of § P:
  `- Tamper resistance is bounded by [§ P](development_plan_standards.md#p-the-ratchet-and-the-users-commit-points): it holds against a HEAD the user has committed. — not proven by any phase.`
- **Confirms** bullets read
  `- R10 — <what is confirmed live> (owed by [Phase 6 — Launch command and passthrough](phase-6-launch-and-passthrough.md)).`
- **Remaining Work** reads `The whole phase: Sprints N.1–N.k.` while Planned and `None.` once Done; an Active phase
  names the sprints still owed.

Each sprint sits under `## Sprints` in this block:

```text
### Sprint N.M: <Name> [Planned]

**Status**: Planned
**Implementation**: `path`, `path`
**Validation tests**: `tests/<dir>/test_<x>.py::test_<y>`, `haskell:agentctl-core-test/<Group>/<case>`
**Mutants**: `M-<prefix>-<change>`, `M-<prefix>-<change>`
**Closes**: R5
**Docs to update**: `documents/engineering/binary_build.md`

#### Objective
#### Deliverables
#### Validation
#### Remaining Work

The whole sprint.
```

| Part | Rule | Enforced by |
|---|---|---|
| Heading | `### Sprint N.M: <Name> [<Status>]`; the tag equals the body Status; ids are unique | `plan.sprint-structure` (Sprint 0.5) |
| Implementation | paths the sprint creates or changes; once Done, each exists and none is under `.build/` or a `*.log` | `plan.cited-paths` (Sprint 1.5) |
| Validation tests | pytest ids under `tests/unit/`, `integration/`, `e2e/`, `live/` or `governance/`, and Haskell ids `haskell:agentctl-core-test/<Group>/<case>`; once Done, each is collected and passes in the run | `plan.cited-ids` (Sprint 1.5) |
| Mutants | explicit ids under the phase's prefixes, never wildcards; `none — <reason>` when there are none | `plan.gate-integrity` (Sprint 1.5) |
| Closes | the ids this sprint closes, or `none` (§ K) | `plan.requirements-table` (Sprint 0.5) |
| `#### Validation` | numbered items ``<claim> — `<node id>`; fails when <the negative input or twin>; mutant `M-...` ``; an item asserting an absence carries its positive control (§ M) | review |
| `#### Remaining Work` | exactly `The whole sprint.` while Planned; begins `None.` once Done | `plan.status-consequences` (Sprint 0.5) |

- **No sprint-level dependency fields.** No `Depends on` or `Blocked by`: sprints run in id order within their phase.
- **Budget.** A sprint has at most 8 deliverable bullets and one new named contract; about 300 lines of production
  code across 3 production modules is the sizing target. An infrastructure sprint may span more small modules when
  they implement its one contract together; its Objective states that boundary. Other oversized work is split.
  A live confirmation never shares a sprint with the change it confirms; it is owed to an acceptance phase.

### H. Documentation Requirements Section

Every phase file ends with `## Documentation Requirements`, holding four bold labels in this order, each followed by
bullets or by `- None.`: `**Architecture docs to create/update:**`, `**Engineering docs to create/update:**`,
`**Operations and reference docs to create/update:**` and `**Cross-references to add:**`. Each bullet is a backticked
`documents/...` path, a dash, and what the document states once the phase is built. A sprint's `**Docs to update**`
names the documents it changes, in the same change as the code, and a sprint is not Done while one of them is stale.
A document's `**Owning phase**` links an existing phase file (`docs.owning-phase`, Sprint 0.4).

### I. Absence Guards and the Legacy Ledger

- **An absence guard**, never a cleanup obligation (a cleanup is a reversal, § A), is a test or validator check
  asserting that a known-wrong shape has not crept back, and it names the [rationale.md](rationale.md#rejected-alternatives) entry that says why: for example
  `tree.forbidden-surfaces` (Sprint 1.3), `src.no-login-construction` (Sprint 1.4) and `docs.binary-unnamed`
  (Sprint 0.4). Each is shown rejecting a negative fixture, and a check that examines no subject fails unless its
  subject's owning phase is Planned (`validator.non-vacuous`, Sprint 1.5). A phase that only a guard keeps from
  introducing a bad surface is rewritten.
- **The legacy ledger**, [legacy_tracking_for_deletion.md](legacy_tracking_for_deletion.md), lists shapes still
  standing that the architecture does not want, under the exact header `| Shape | Location | Why it must go | Deleted by |`;
  each row names one existing deleting phase that is not Done (`plan.legacy-ledger`, Sprint 0.5). The ledger
  schedules nothing, since the deleting phase's Remaining Work states the work; a row leaves with its shape, and
  empty is healthy.

### J. README and Documents Harmony

- **One status source.** Each phase header's Status equals its row in the [status table](README.md#current-phase-status),
  the only place every phase's status appears; `plan.status-harmony` (Sprint 0.5) validates the table's structure
  first, so a missing or malformed row cannot pass vacuously. The plan README stays short and undated, under the
  line cap of `plan.no-narrative`.
- **Documents and root documents carry no status** (`docs.no-status`, Sprint 0.4). A document states the contract its
  owning phase builds, and `documents/README.md` says once that the plan's table records what is Done. Sprint 0.6
  writes the root `README.md` (it links both indexes and describes only commands whose owning phase is Done),
  `AGENTS.md`, and `CLAUDE.md`, a pointer plus `@AGENTS.md` (`docs.root-entry`, Sprint 0.6).
- **Outside the plan, phases are cited by title.** No text outside `DEVELOPMENT_PLAN/` names a phase or sprint by
  number (`docs.phase-citation`, Sprint 0.4); inside it, a phase is cited as a linked
  `Phase 6 — Launch command and passthrough` and a sprint as `Sprint 6.2`.
- **User-facing docs never name the core binary:** `agentctl-core` does not appear in `documents/operations/`,
  `documents/reference/` or the root README, which say "the core binary" (`docs.binary-unnamed`, Sprint 0.4).
- **Enforcement claims cite their mechanism:** a document line cites the enforcing test node id
  (`docs.enforcement-cited`, Sprint 0.4), and a plan line names the validator check and its sprint.

## agentctl Governance Contracts

These contracts say how a phase earns its status; they restate no product behaviour.

### K. Requirement Anchoring

- **The request is the anchor.** [rationale.md](rationale.md#originating-request) holds the user's request, the Q&A
  answers and the adopted concept-note excerpts verbatim, and that block only grows.
- **One home.** The [requirements table](00-overview.md#requirements), with columns
  `ID | Requirement | Quote | Closing sprint | Evidence classes | Prose home | Data home`, is the only place
  requirements are stated. Each Quote is a backticked exact substring of the request block
  (`plan.requirements-table`, Sprint 0.5). What the request leaves open is settled by a `decision:` row in
  [rationale.md](rationale.md#decisions), never by an invented requirement. A row that HEAD holds is never edited or
  deleted; a correction is an appended row naming the row it amends (`ratchet.append-only`, Sprint 1.3).
- **Each id closes exactly once.** Exactly one sprint lists each id in `**Closes**`, and a phase's Closes is the union
  of its sprints' (`plan.requirements-table`). Separable parts get clause ids (`R12.1`, `R18.4`) so each closes in the
  sprint that proves it, which is an acceptance phase's sprint only when nothing but a host-acceptance run can. An
  `owed` class is confirmed by the acceptance phase whose `## Confirms` names the id. Every Confirms entry also has
  an `owed` entry for that id in the contributing phase it names (`plan.gate-integrity`, Sprint 1.5).
- **The concept note is accounted for.** [The concept-note disposition](rationale.md#concept-note-disposition) gives
  every section of the superseded concept note a row with a closed disposition and a destination that resolves
  (`plan.disposition-table`, Sprint 0.5). Its completeness cannot be re-checked once the note is deleted, which
  [Phase 0 — Governance, documentation standards and the check skeleton](phase-0-governance-and-check-skeleton.md)
  lists as not proven.

### L. Evidence Classes and What Cannot Count

Every test and every Gate Integrity Observer entry declares exactly one evidence class and claims no more than that
class proves. The mechanics and isolation recipes live in [testing](../documents/engineering/testing.md#evidence-classes).

| Class | What it is | Proves | Cannot prove |
|---|---|---|---|
| `value` | A pure subject applied to committed oracle rows through `tests/harness/oracle.py::assert_oracle`. Haskell subjects run through the `agentctl-core-eval` executable, which reads JSON cases on stdin and prints results; Python compares them to the oracle. | The subject computes the specified function on those inputs. | That the specification matches the real tool; anything about effects. |
| `real` | The real tool in a scope the test owns: tmux on a private server; psmux with `PSMUX_DATA_DIR` and `PSMUX_NO_WARM=1`; claude and codex logged out by construction; `--help` canaries with a negative control; the pinned ghcup, GHC and cabal; pytester. | Behaviour against that tool at the version the run observes. | Other versions, other OS families, states the run did not reach. |
| `observer` | One of two boundary stand-ins: the `agentctl-fake-agent` executable, copied into a temp bin as `claude` or `codex`, which records argv, cwd, environment keys, the multiplexer session and the nonce; or the `sys.addaudithook` spawn audit, which observes and can veto Python spawns. Each needs a fresh nonce, and its absence assertions are paired with positive controls. | What the subject sent, and what it did not send while the observer was demonstrably live. | That the real tool accepts it. |
| `owed` | A live confirmation named in exactly one acceptance phase's `## Confirms`. A behaviour no lane can produce on demand, such as recovery from a genuine provider overload, is never owed: it is listed as not proven by any phase. | Nothing until that phase's evidence row is current; then, the confirmation it names. | Anything beyond that confirmation, or on a host outside that phase's lane. |

Never evidence:

- skipped, xfailed, xpassed, deselected or zero-assert tests;
- expected values produced by the subject;
- fixtures without provenance;
- subject self-reports;
- production branches that exist for tests;
- mocks or monkeypatches of the subject;
- hand-typed counts;
- cached verdicts (compilation may be cached; outcomes and mutant kills never are).

Beside the no-skip rules of § O, `oracles.independence` (Sprint 1.1), `src.no-test-branches` and
`src.suppression-ban` (Sprint 1.4) and `plan.no-narrative` enforce the list. A zero-assert test kills no mutant, so it
is never a Gate Integrity killer.

### M. Gate Integrity

- **Oracles are independent of the subject.** Every oracle row carries provenance `request:R<n>`,
  `tool:<name> <version> <source>` (a fact in external tool facts) or `decision:<rationale anchor>`. No expected
  value is subject output, and oracle loaders import nothing from `agentctl` (`oracles.independence`, Sprint 1.1).
  The request-derived oracles are frozen in [Phase 1 — Gate-integrity apparatus](phase-1-gate-integrity-apparatus.md),
  before any product phase, and a user commit point holds them (§ P).
- **Mutants die for a named reason.** A record in `tests/mutants/<capability>.toml` gives the id, an operator, a patch
  that applies exactly once to a scratch copy, the killer node ids, and a reason substring absent from the baseline
  output and present under the mutant; a patch that fails to apply or matches twice, a survivor, and a kill for
  another reason each fail the gate. Every check run applies every mutant inside the pytest leg (Sprint 1.2), and each
  Gate Integrity row has about two mutants that name the row's tests as killers (`plan.gate-integrity`, Sprint 1.5).
  Mutant ids use only their phase's prefixes (below; no two phases share one, and the acceptance phases cite no
  mutants), and Haskell mutants target pure kernels only.
- **Activation follows the apparatus.** Phase 0 initially closes on its cited tests and direct negative controls.
  Its mutant ids are declarations until Sprint 1.2 builds the runner and their records. From that sprint onward,
  every run kills those retrospective mutants as well as every applicable later mutant; no Done phase is exempt.
  A record targeting code not yet introduced remains a declaration in its Planned sprint, never an attempted kill.
- **A fresh nonce per observer run.** `tests/harness/nonce.py` issues one per run and the observer records it, so a
  replayed or pre-written record proves nothing.
- **Every absence assertion has a positive control** in the same test: "no session is left behind" is paired with the
  fake agent's record that the session existed, "no login command ran" with the recorded auth-status probe.
- **Every leg asserts a non-empty target set.** A lint leg that examines no file, a pytest run that collects nothing
  and a Haskell suite that reports no case each fail; validator checks obey the same rule (`validator.non-vacuous`).
- **Static legs and validators are shown firing.** Each lint, format and type leg rejects a fixture from
  `tests/fixtures/static_negative/` (`*.py.txt`, copied to a temp dir), and each validator check yields exactly its
  named violation on its fixture under `tests/fixtures/docs_negative/` and none on the live tree.
- **Compile-fail fixtures are two-sided.** A fixture that must not compile, such as one constructing `Ready` outside
  `AgentCtl.Preflight`, passes only when GHC reports the diagnostic code it names, and its compiling twin builds.

| Phase | Mutant prefixes |
|---|---|
| [Phase 0 — Governance, documentation standards and the check skeleton](phase-0-governance-and-check-skeleton.md) | `M-legs-`, `M-plugin-`, `M-docval-`, `M-planval-` |
| [Phase 1 — Gate-integrity apparatus](phase-1-gate-integrity-apparatus.md) | `M-oracle-`, `M-mutant-`, `M-ratchet-`, `M-guard-`, `M-audit-`, `M-evidence-` |
| [Phase 2 — Toolchain bootstrap](phase-2-toolchain-bootstrap.md) | `M-boot-`, `M-prereq-`, `M-ghcup-`, `M-pins-` |
| [Phase 3 — Haskell package, quality legs and digest-keyed build](phase-3-haskell-package-and-build.md) | `M-build-`, `M-style-`, `M-cache-` |
| [Phase 4 — Multiplexer adapter](phase-4-multiplexer-adapter.md) | `M-mux-` |
| [Phase 5 — Agent adapters and preflight](phase-5-agent-adapters-and-preflight.md) | `M-argv-`, `M-auth-`, `M-preflight-` |
| [Phase 6 — Launch command and passthrough](phase-6-launch-and-passthrough.md) | `M-name-`, `M-launch-`, `M-pass-` |
| [Phase 7 — Session management and adoption](phase-7-session-management-and-adoption.md) | `M-sessions-`, `M-adopt-` |
| [Phase 8 — Pane observation and classification](phase-8-pane-observation-and-classification.md) | `M-capture-`, `M-classify-` |
| [Phase 9 — Recovery state machine and backoff](phase-9-recovery-state-machine.md) | `M-machine-`, `M-backoff-` |
| [Phase 10 — Recovery supervisor](phase-10-supervisor.md) | `M-super-` |

### N. The Single Gate, Gate Kinds and Host Lanes

- **One gate.** Every Gate is `agentctl check`. It takes no arguments, runs from a scrubbed environment allowlist, and
  fails if any step or leg fails or does not run; [the quality gate](../documents/engineering/quality_gate.md#check-steps)
  is the home of its steps and legs, recorded in `tests/oracles/check_steps.toml` and `tests/oracles/check_legs.toml`.
  A warm run takes about 15 minutes. Inner-loop runs (one pytest node, a bare `cabal build`) are never evidence, and
  no CI, Makefile, hook or script runner exists beside the gate (`tree.forbidden-surfaces`, Sprint 1.3).
- **Gate kinds.** A self-verifying phase closes when check passes on a host meeting its lane, and every later run
  re-proves it, so it stores nothing. A host-acceptance phase adds no code and is terminal; it closes the same way
  and records the EVIDENCE line that run printed as its `**Gate evidence**`.

The lane table is canonical here, and its vocabulary is closed (`plan.lanes`, Sprint 1.5):

| Lane | Predicate | Observed by | Remedy |
|---|---|---|---|
| any-host | Linux x86_64/aarch64, macOS x86_64/arm64 or Windows x86_64; an editable install of this checkout with the `dev` extra; git | check preconditions P1–P10 | `pipx install --editable '.[dev]'` or `uv tool install --editable '.[dev]'` |
| mux-host | any-host plus tmux at least 3.2 (Linux/macOS) or psmux at least 3.4.0 (Windows) resolvable on PATH | `tests/harness/host.py` | the OS install command for tmux; `winget install psmux` |
| agent-host | mux-host plus claude and codex resolvable (native executables on Windows); login state is irrelevant | `tests/harness/host.py` | the official installer of each agent |
| live-agents | Linux, agent-host, and `claude auth status` and `codex login status` both exit 0 within 10 s in the user's real environment | `tests/harness/host.py` | the user types `claude auth login` or `codex login` |
| clean-container | the two-stage recipe `tests/lanes/clean-host.Dockerfile`, run as a non-root user with NOPASSWD sudo, on a gate host with docker | Stage A filesystem facts read by `tests/e2e/test_fresh_bootstrap.py` | build and run the recipe |
| macos | Darwin, `xcode-select -p` succeeds, tmux at least 3.2, and agent-host | `tests/harness/host.py` | install the Xcode CLT (a GUI dialog a human completes) and `brew install tmux` |
| windows-psmux | Windows x86_64, psmux at least 3.4.0, native `claude.exe` and `codex.exe` | `tests/harness/host.py` | `winget install psmux`; the official agent installers |

check fails when the lane of any Done self-verifying phase is unmet on the host running it (`plan.lanes`).
Acceptance lanes are reported in the lane summary and never required, and tests adapt only as § O allows. The
preconditions behind any-host are in [the quality gate](../documents/engineering/quality_gate.md#preconditions).

Evidence rows have one format:

```text
<YYYY-MM-DD> ; <lane> ; agentctl check ; pass ; tree <sha256> ; <detail>
```

- The `lane-summary` step (Sprint 1.5) prints `EVIDENCE` and this row for each lane the host meets; the closing agent
  copies it into the phase's `**Gate evidence**`.
- `**Evidence covers**` is fixed to `src/` `tests/` `pyproject.toml`; the plan lies outside it, so recording a row
  never stales the row. The validator recomputes the tree digest over Evidence covers and compares only the lane,
  against `**Host lane**`, and the digest; date and detail are for the reader (`plan.evidence-rows`, Sprint 1.5).
- A change under a covered path stales the digest, so the same change returns a Done host-acceptance phase to `Active`
  and its Gate evidence to `none recorded`.
- **The honest ceiling.** A digest proves currency, not that a run happened: anyone can recompute it without running
  anything, and nothing on the host can attest to a run. A row raises the cost of a false claim to deliberately
  recording a result that was not obtained, and its lane and detail tell a reader which host ran it.

### O. The No-Skip Suite and Host-State Adaptivity

- **The whole suite runs.** Under check no skip, skipif, xfail, importorskip, deselection, `-k` or `-m` selection, or
  node-id narrowing is possible: the gate plugin fails the session on any of them and records collected and executed
  ids with the run's nonce (Sprint 0.3), and the `post-run-verifier` step requires the two to match (Sprint 1.5).
  pytest runs with `strict = true` and `filterwarnings = ["error"]`. Every collected module is cited by a sprint, and
  every `.py` file under `tests/` is collected or declared support (`tests.orphan-modules`, Sprint 0.3). The
  `cabal-test` leg runs every Haskell suite, and one that reports no case fails.
- **Tests adapt only to** the login state of claude and codex, the multiplexer kind (tmux or psmux), the OS family,
  and the toolchain provenance (installed by agentctl or by the user). Each branch asserts the behaviour agentctl
  declares for the observed state, and none returns early. `tests/harness/host.py` makes the observation, records it
  with the run's nonce, and feeds the lane summary. A live test that finds an agent logged out asserts the refusal and
  its remedy; one that finds it logged in asserts the live launch, within § Q.
- **Tool absence is constructed, never observed.** A missing-tool test runs the subject under a constructed PATH that
  lacks the tool, and no test changes what it asserts after inspecting the host, so a host without tmux fails a
  mux-host test instead of passing it degraded.
- **Lanes hold where phases are Done.** check fails when a Done self-verifying phase's lane is unmet on the host
  (`plan.lanes`, § N), so no such phase stays Done on a host that cannot re-prove it.

### P. The Ratchet and the User's Commit Points

- **Append-only against HEAD.** Oracle rows under `tests/oracles/`, mutant records under `tests/mutants/` and
  requirement rows in `00-overview.md` only grow relative to HEAD, and configuration only tightens; a correction is an
  appended row naming what it amends (`ratchet.append-only`, Sprint 1.3). The live ruff, ty, pytest and coverage
  configuration equals `tests/oracles/lint_config.toml` (`config.pinned`, Sprint 1.4). The `ratchet` step reads HEAD
  with read-only git and reports the commit it compared against. Before the user's first commit there is no baseline:
  the ratchet protects nothing, and check reports that.
- **Agents never commit.** Agents never run `git add`, `git commit` or `git push`, and never move HEAD, so HEAD is the
  user's review point: every later run is held to it, and "cannot be spoofed" holds only against it. Between commits a
  change can weaken its own gate data, and the user's review of the diff is what catches it.
- **The user's commit points:**
  1. after the governed suite (this plan and `documents/`);
  2. after [Phase 1 — Gate-integrity apparatus](phase-1-gate-integrity-apparatus.md), when the request-derived oracles
     are frozen and before any product code exists;
  3. at each phase close.

### Q. Containment and User-State Protection

Neither check nor any test changes the user's environment. The `containment` and `write-guard-compare` steps
(Sprint 1.3) check what can be checked after the run; neither can see a process that never registered with an
observer.

- **The user's tmux server.** Real tmux tests use a private server (`TMUX_TMPDIR` under the run dir, `TMUX` unset),
  and the harness runs kill-server only after asserting the socket lies under the run dir. Production code ends a
  session only with `kill-session -t =NAME`. `containment` fails if a private server or an observer pid is still
  alive, or a session carrying the run's nonce exists on the user's server.
- **Credentials and agent state.** Logged-out tests use empty `CLAUDE_CONFIG_DIR` and `CODEX_HOME`, and no test writes
  credentials, `~/.claude.json` or agent configuration. Live tests start the real agent only in one fixed folder under
  the real `state` directory, with `DISABLE_AUTOUPDATER=1`, so any per-folder record the agent keeps concerns that
  folder alone; they never send input, never answer a trust or bypass-warning dialog, and never run a login command.
- **rc files and the ghcup default.** Nothing edits a shell rc or profile file, and ghcup is never installed through
  its bootstrap script. GHC installs without `--set` and cabal with `--no-set`, so the user's default selection never
  changes; warm runs verify the pinned GHC and cabal with `--numeric-version`.
- **Package managers and sudo.** Tests run neither: the spawn audit records and vetoes those spawns. check never
  prompts; installation needs explicit `--assume-yes` and privilege as root or through `sudo -n`.
- **The tree.** The write-guard snapshots the tree (ignored files included, only `.git` excluded) before the run and
  compares it after; check and its children run with `PYTHONPYCACHEPREFIX` under the run dir.

### R. Imported Practices and Explicit Non-Adoption

agentctl borrows governance from its siblings and none of their product features. A sibling practice listed as not
adopted is never a blocker or a completion criterion here.

| Imported practice | Source |
|---|---|
| The constructive narrative, Planned/Active/Done with no Blocked, the fixed file set, one status table joined to phase headers, Documentation Requirements, absence guards and the legacy ledger | hostbootstrap (§ A–J) |
| Self-verifying and deferred gate kinds, digest-bound evidence rows, a stated honest ceiling, what cannot count as evidence, and a gate that exercises the checkout it judges rather than an installed copy | hostbootstrap (§ G, § NN) |
| Independent oracles committed before the implementation, mutants that die for a named reason, fresh nonces, the write-guard, the containment scan, and validators tested two-sided | amoebius (its gate-integrity contract) |
| Gate data ratcheted against HEAD; every declared test suite routed to a runner; absence assertions paired with positive delivery | prodbox |
| No parallel workflow surfaces (Makefile, hooks, pre-commit, `.github`) | prodbox and jitML |
| A requirement floor joined both ways, so no requirement is dropped to make closure cheaper | jitML and amoebius |
| A Definition of Done and an Exit Definition derived from the requirements | prodbox and jitML |
| Skips are failures, a missing prerequisite fails fast with its remedy, and agents never commit | all five siblings |

| Not adopted | Source | Why agentctl does without it |
|---|---|---|
| Derived resume queues | prodbox | "The lowest Active phase first" orders a plan of this size. |
| Attestation stores | amoebius | Evidence is one printed EVIDENCE line plus a write-guarded tree. |
| Cohort validation waves | infernix | One gate plus terminal acceptance phases covers every host. |
| Generated-section registries | prodbox | No document section is generated. |
| `Referenced-by` fields | amoebius and jitML | Back-links drift, while forward links resolve or fail. |
| TLA+ and illegal-state catalogs | amoebius | agentctl has no authority or tenant model; opaque types and property tests over the recovery machine suffice. |
| Dhall configuration | hostbootstrap and infernix | The supervisor takes flags with defaults, and nothing else is configured. |
| A container-only code check | hostbootstrap and jitML | fourmolu and hlint run host-native inside `agentctl check`. |
| Mandatory diagrams | amoebius | No gate can check a diagram. |
| Per-family coverage manifests | hostbootstrap | Orphan-module detection and 100% branch coverage already catch a dropped test. |
| CI | a hosted CI matrix | Agents never push; the gate of record is `agentctl check`, run by an agent on the declared host. |

### S. Contract Homes

Each product contract has one home in `documents/` and one owning phase, and this file restates none of them; the
[documents index](../documents/README.md) lists every page, the user-facing ones included.

| Contract | Home | Owning phase |
|---|---|---|
| The Python/Haskell boundary: ownership split, raw passthrough, handoff, handshake, the Python spawn set, the directories passed to the binary | [python_haskell_boundary.md](../documents/architecture/python_haskell_boundary.md) | [Phase 6 — Launch command and passthrough](phase-6-launch-and-passthrough.md) |
| Launch and preflight: session names, argument assembly, login refusals, preflight and the opaque `Ready`, failures and warnings, create-or-attach, instant exit, the pane trampoline | [launch_contract.md](../documents/architecture/launch_contract.md) | [Phase 6 — Launch command and passthrough](phase-6-launch-and-passthrough.md) |
| The multiplexer adapter: the typed tmux and psmux vocabulary, version floors, `=NAME` targeting, session options, isolation variables | [multiplexer_adapter.md](../documents/architecture/multiplexer_adapter.md) | [Phase 4 — Multiplexer adapter](phase-4-multiplexer-adapter.md) |
| Sessions and ownership: managed and adopted sessions; list, attach, stop and status | [sessions_and_ownership.md](../documents/architecture/sessions_and_ownership.md) | [Phase 7 — Session management and adoption](phase-7-session-management-and-adoption.md) |
| Supervisor safety: capture and fingerprints, screen classes, the state machine and its safety rules, backoff, send discipline, the log, notifications, forbidden actions | [supervisor_contract.md](../documents/architecture/supervisor_contract.md) | [Phase 10 — Recovery supervisor](phase-10-supervisor.md) |
| The toolchain bootstrap: prerequisites and consent, ghcup reuse or the pinned download, the GHC and cabal pins, idempotence, the clean-lane recipe | [toolchain_bootstrap.md](../documents/engineering/toolchain_bootstrap.md) | [Phase 2 — Toolchain bootstrap](phase-2-toolchain-bootstrap.md) |
| The binary build: digest, cache, atomic publish, packaging, binary identity | [binary_build.md](../documents/engineering/binary_build.md) | [Phase 3 — Haskell package, quality legs and digest-keyed build](phase-3-haskell-package-and-build.md) |
| The quality gate: check steps and legs, tool configuration, preconditions, the lane summary and the EVIDENCE line | [quality_gate.md](../documents/engineering/quality_gate.md) | [Phase 3 — Haskell package, quality legs and digest-keyed build](phase-3-haskell-package-and-build.md) |
| Testing and evidence mechanics: evidence classes, isolation, observers and nonces, oracles, mutants, what each gate leg proves, unsupported paths | [testing.md](../documents/engineering/testing.md) | [Phase 1 — Gate-integrity apparatus](phase-1-gate-integrity-apparatus.md) |
| Code standards: the Python rules (no `Any`, `cast` or ignores; `Result`; one process module) and the Haskell rules (warnings stanza, fourmolu and hlint, opaque types, one runner) | [code_standards.md](../documents/engineering/code_standards.md) | [Phase 3 — Haskell package, quality legs and digest-keyed build](phase-3-haskell-package-and-build.md) |

## Related

- [README.md](README.md) — the status table § J governs, and the steps for working the plan.
- [00-overview.md](00-overview.md) — the requirements table § K anchors to the request.
- [system-components.md](system-components.md) — the inventory § F governs.
- [rationale.md](rationale.md) — the verbatim request, the decision rows and the rejected alternatives.
- [legacy_tracking_for_deletion.md](legacy_tracking_for_deletion.md) — the ledger § I governs.
- [documentation_standards.md](../documents/documentation_standards.md) — the rules for `documents/`, with every `docs.*` check.
- [testing.md](../documents/engineering/testing.md) — the mechanics behind § L and § M.
