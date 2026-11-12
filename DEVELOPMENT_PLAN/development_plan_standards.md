# agentctl Development Plan Standards

**Status**: Authoritative source
**Supersedes**: N/A

> **Purpose**: Define a constructive, migration-aware plan with independent phase evidence, complete execution and bounded hardware requirements.

## Core Principles

### A. One Continuous Constructive Narrative

A phase adds a complete contract using strictly lower prerequisites. Later phases do not remove, reverse or
silently strengthen an earlier closure condition. Platform extensions implement interfaces defined before them.
A necessary changed contract is rewritten at its owning phase. A migration is the work of that owner, not a
corrective phase appended after its consumers. Existing files do not make a revised contract complete.

### B. Detailed, Implementation-Oriented Content

Name concrete modules, resources, tests, mutants, observer outputs and failure criteria. Planned paths and node
ids are required deliverables, explicitly distinguished from existing evidence. Every validation action states
its input/setup, observable pass and refusal conditions, and source-independent expectation. A prose claim,
version banner, hand-built receipt or successful exit alone is not behavioral proof.

External facts have version/revision, verification method and source in
[external tool facts](../documents/reference/external_tool_facts.md). A candidate pin is not a proven artifact.

### C. Honest Completion Tracking

| Status | Meaning |
|---|---|
| Planned | Execution of the revised contract is not started; existing incompatible artifacts are ledger inputs |
| Active | Work on the revised contract has started and Remaining Work names every unmet obligation |
| Done | The owned contract and required phase/lane evidence are complete and current; no owned deletion remains |

Only the status table in README rolls up phase status. Headers and sprint tags agree with it.
Done requires all sprints Done and Remaining Work `None.`. A Planned sprint's Remaining Work is
`The whole sprint.`; its phase names its whole sprint range. Reopening a prerequisite invalidates
dependent closure. A Planned consumer may contain existing code but cannot claim readiness from it.

### D. Declarative Current-State Language

Contracts use present tense; status supplies completion, not verb tense. No narrative test counts, dated
completion claims or historical cleanup sprints. Evidence rows alone carry run dates. Rationale can preserve
quoted provenance and explicitly amended decisions; current contracts follow the applicable amendment.

### E. One Canonical Folder Model

`DEVELOPMENT_PLAN/` contains README, these standards, overview, inventory, rationale, deletion ledger and one
contiguously numbered phase file per README row. Renumbering updates every phase link and ownership reference.
Governed prose lives under `documents/` in architecture, engineering, operations and reference.
No alternate roadmap, workflow runner, hidden source directory or duplicate contract home is introduced.

### F. System Component Inventory

[system-components.md](system-components.md) inventories target modules, shipped resources, tools, tests and
owned directories with stable capability ownership and one phase owner. The gate's executable ownership
manifest covers every present artifact, including ledger inputs, and its mapping agrees with this inventory.
Shared inputs belong to their earliest substantive owner and are included in every actual consumer's digest.

### G. Phase and Sprint Document Requirements

Each phase declares Status, lower Depends on links, Host lane, the sole Gate `agentctl check`, Gate kind and
Closes. Host-acceptance phases also carry Gate evidence and Evidence covers. Ordered sections are Phase Objective,
Gate Integrity, Not Proven By This Gate, optional Confirms, Sprints, Remaining Work and Documentation Requirements.

Each sprint has a contiguous id, status tag and matching Status; Implementation paths; Validation tests; Mutants;
Closes; Docs to update; then Objective, Deliverables, Validation and Remaining Work. A planned node id can be
absent before its owner is implemented; it is never represented as collected or passing until observed.

Gate Integrity names a requirement, independent oracle, observer, applicable mutants and actual test nodes.
A pure, native or observer control states what it proves. Missing required evidence fails its own verdict.

### H. Documentation Requirements Section

Every phase names architecture, engineering, operations/reference and cross-reference changes, or None.
Documents state target contracts and actual named enforcement separately. The ledger, not misleading
implementation prose or stale Done status, owns standing deviations. Each amended implementation updates
its contract, inventory, oracle amendment and deletion row in the same change.

### I. Absence Guards and the Legacy Ledger

[legacy_tracking_for_deletion.md](legacy_tracking_for_deletion.md) is a census of still-present unwanted shapes,
with concrete locations, the behavioral reason and exactly one non-Done deletion owner. The owner's deliverables
and Remaining Work include the migration. A ledger entry is not a scanner suppression, excluded source set or
license to weaken tests. Remove its row only with the actual shape; assert the desired shape with positive
delivery evidence as well as absence controls. No closing phase can retain its owned rows.

### J. README and Documents Harmony

README is the only cross-phase status table. Every phase appears in both its table and index. Documents cite
phases by linked title, not ordinal. Root AGENTS and CLAUDE carry consistent WSL2/no-commit policy; CLAUDE imports
the authoritative AGENTS policy. No document asserts that an unimplemented new rule already has enforcement.

### K. Requirement Anchoring

The overview has one row per stable requirement ID, an exact request anchor, one closing sprint, evidence
classes and canonical prose/data homes. Preserve original request text and trace amended intent explicitly.
Reordering a closing owner is a governance amendment, not deletion of the requirement. A new user instruction
can replace a planner decision; record its precedence and tests instead of weakening an oracle silently.

### L. Evidence Classes and What Cannot Count

- `value`: independent expected values for a pure contract.
- `real`: actual native implementation behavior on the named host.
- `observer`: nonce-bound independent observation of effects/bytes/resource identities.
- `owed`: explicitly foreign/live confirmation owned by one acceptance capability.

A documented fixture supports classification consistency, not a real agent screen claim. Finite tests have
declared bounds; they prove neither universal totality nor invisible agent state. Manual review, a commit,
answered dialog, fixture capture request or fabricated attestation is never gate evidence.

### M. Gate Integrity

Every named applicable mutant runs against a passing baseline and dies for its specified reason in its named
killer. A syntax error, build failure or unrelated exception is not a kill. Native positive/refusing twins
cover failure paths; no mocks replace implementations. The full relevant test, mutant, coverage and source
census is independently joined to nonce-bound execution.

New source rules have alias-aware positive/refusing controls and mutants in agentctl's own gate. Strict Python
migration covers product, checker, harness, tests and native boundary declarations. Checker labels do not
exempt mutable state or opaque types. No package/library is adopted solely to impose this doctrine.

### N. The Single Gate, Gate Kinds and Host Lanes

`agentctl check` takes no arguments and is the only closure entry point. It runs every introduced leg and
collects/executes every present test without selection. It retains complete diagnostics and emits independent
phase/lane verdicts plus an overall result. A later owned failure may leave an earlier complete verdict passing.
Independently owned later syntax/import/collection failures retain failed-module and missing-node evidence while unrelated earlier modules continue; shared or ambiguous collection damage is not local. Collection corruption, stale nonces, unowned source, write-guard damage and unregistered resources invalidate
all consuming verdicts, even if a convenient subset of tests passed.

A self-verifying phase requires current evidence over its full input/prerequisite closure. A host-acceptance
phase consumes or records actual native/live receipts and adds no product implementation. Every phase requires
Linux plus at most one foreign family. Its lane is one of:

| Lane | Required observed evidence | Foreign family |
|---|---|---|
| linux | Debian Linux editable dev checkout, git and tools introduced by that phase | none |
| linux-windows | Linux receipt plus native Windows x86_64 receipt for this input closure | Windows |
| linux-macos | Linux receipt plus native Darwin receipt for this input closure | macOS |
| linux-live-clean | Debian Linux, real two-stage clean preparation and existing authenticated agents | none |

WSL2 can supply Linux only when the dedicated distro, capacities, installed Linux dependencies and same-checkout
bind mount satisfy [the runbook](../documents/operations/validation_runbook.md). It supplies no Windows/Darwin ABI proof.
Linux pure/refusal branches of foreign tests execute without skip markers, but do not mint native receipts.
The native verdict remains unmet until a real native run supplies its required observations.

A cross-lane join matches shared logical source/policy/prerequisite contract identity; it separately verifies lane-native toolchain/artifact sub-identities. Linux and Windows executable or compiler hashes are not required to equal each other. Phase input identity binds all owned/shared source bytes, oracle/config/patch bytes, relevant artifacts/tools
and recursively required receipt identities. A later-only source change preserves unrelated earlier identity.
A shared contract change invalidates its consumers. A final product receipt covers the complete tree and native
backend identities. Receipt records include phase capability, lane, input digest, nonce, test/mutant/coverage
sets, host facts, prerequisite identities, outcome and retained diagnostics. Gate evidence copies the emitted
current `PHASE` line(s); the final phase records aggregate `EVIDENCE`. Date/detail are informative; input closure,
lane and artifact agreement are executable obligations. A digest is not independent attestation that a run happened.

### O. The No-Skip Suite and Host-State Adaptivity

No skip, xfail, importorskip, deselection, `-k`, `-m` or node narrowing is possible inside the closing gate.
Every present test executes; every present source file and deferred shape is inventoried. Planned missing tests
are unmet work for their owner. Host-state branches assert their declared actual behavior or refusal; they
never silently return early. An unavailable foreign lane stays unavailable, regardless of passing Linux values.

Lint, types and coverage run over complete owned censuses and report source locations/capabilities. Legacy
findings remain visible and fail their owners. They do not count as global integrity failures unless they
damage the trustworthiness of another verdict. Shared modules and shared test support cannot be mislabelled as
later-only to launder a failure. No legacy source disappears from final whole-product acceptance.

### P. The Ratchet and Automatic Closure

HEAD is a read-only external baseline; agents never stage, commit, push or move it. An unborn repository has
no historical baseline. Independent current-run evidence remains mandatory either way.
Committed oracle/mutant provenance and requirement identities are retained; corrections append explicit
content-bound amendments. Governance-authorized owner renumbering updates path joins while preserving semantic
requirement identity. Validator migration tests distinguish authorized metadata amendments from removed oracle
cases, broadened suppressions and weakened expected behavior.

Phase closure consumes its complete relevant passing report, never another phase's incomplete verdict or the
overall later-only failure. Final product closure requires the aggregate pass and current foreign receipts.
No approval, clean tree, signature, publishing action or manual inspection is required to advance.

### Q. Containment and User-State Protection

Production and gate code never alter user credentials, agent configuration, shell profiles, toolchain defaults
or unrelated sessions. Native package/toolchain preparation is consented outer work, with no package managers,
sudo, login or dialogs inside tests. No ordinary check prompts. Privilege is not consent.

All test multiplexers, endpoints, processes and external short build roots are nonce-registered and owned.
Teardown waits for actual child/handle release and verifies endpoint/resolved absolute path ownership before
kill/removal. Never kill by image name or recursively delete a computed/unverified path. Report primary and
cleanup failures separately and retain diagnostic receipts outside disposable directories.

A Windows agent can create an agentctl-only Debian WSL2 instance with CPU/memory/storage budgets justified by
observed resources and measured peaks, install all needed Linux dependencies, and bind mount the host checkout.
Workload cgroup limits and VHD capacity must be observed; a distro name alone is not resource isolation.
Do not edit shared global WSL configuration or shut down other distributions. Credential copies remain private.
Host/guest changes are the same live unstaged/untracked tree, never a commit/copy synchronization scheme.
Writable bind-mount permissions, locks, case and symlink semantics are tested; unsupported behavior is unmet,
not a Linux pass silently measured on a different filesystem.

### R. Imported Practices and Explicit Non-Adoption

Adopt independent oracles, immutable typed models, scoped effects, executable closure, full test census,
content-bound mutants and explicit evidence ceilings. Tooling remains the project's own pinned gate.
Do not introduce alternate workflow runners, automatic user-session migration, package-manager tests,
source suppressions, snapshot-only fake native evidence or prebuilt product/backend distribution.

### S. Contract Homes

| Contract | Canonical home | Owner |
|---|---|---|
| Python doctrine and Haskell source discipline | [code standards](../documents/engineering/code_standards.md) | [Python discipline and gate integrity](phase-1-python-discipline-and-gate-integrity.md) |
| Minimal Python bootstrap and raw handoff | [boundary](../documents/architecture/python_haskell_boundary.md) | [Python bootstrap and handoff](phase-2-python-bootstrap-and-handoff.md) |
| Build identity and publication | [binary build](../documents/engineering/binary_build.md) | [Python bootstrap and handoff](phase-2-python-bootstrap-and-handoff.md) |
| Host/runtime preparation and consent | [toolchain](../documents/engineering/toolchain_bootstrap.md) | [Haskell runtime and platform policy](phase-3-haskell-runtime-and-platform-policy.md) |
| Backend identity and common vocabulary | [multiplexer](../documents/architecture/multiplexer_adapter.md) | [Debian tmux and multiplexer](phase-4-debian-tmux-and-multiplexer.md) |
| Agent discovery and launch | [launch](../documents/architecture/launch_contract.md) | [Agent preflight and launch](phase-5-agent-preflight-and-launch.md) |
| Ownership and adoption | [sessions](../documents/architecture/sessions_and_ownership.md) | [Session management and adoption](phase-6-session-management-and-adoption.md) |
| Observation and guarded recovery | [supervisor](../documents/architecture/supervisor_contract.md) | [Recovery and supervisor](phase-8-recovery-and-supervisor.md) |
| Gate mechanics and phase verdicts | [quality gate](../documents/engineering/quality_gate.md) | [Governance and phase evidence](phase-0-governance-and-phase-evidence.md) |
| Evidence, isolation and observers | [testing](../documents/engineering/testing.md) | [Python discipline and gate integrity](phase-1-python-discipline-and-gate-integrity.md) |
| Native/WSL preparation | [runbook](../documents/operations/validation_runbook.md) | [Governance and phase evidence](phase-0-governance-and-phase-evidence.md) |

## Related

- [README](README.md) — execution and status.
- [overview](00-overview.md) — requirement ownership.
- [inventory](system-components.md) — components.
- [rationale](rationale.md) — request and amendments.
- [ledger](legacy_tracking_for_deletion.md) — current migration inputs.
- [documentation standards](../documents/documentation_standards.md) — governed prose.
