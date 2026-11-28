# agentctl Development Plan Standards

**Status**: Authoritative source
**Supersedes**: N/A

> **Purpose**: Define a well-ordered constructive plan whose phase verdicts are unspoofable, decidable by one gate run and bounded in hardware.

## Core Principles

### A. Well-Ordered Constructive Narrative

A phase adds a complete contract using strictly lower prerequisites. Phase numbers are a topological order of
**Depends on**, which equals the ownership manifest's `[[phases]]` prerequisites, so ascending order is a valid
work order and equals the `selection:` order (T.D). The plan is well-ordered when, for every phase p and every
later phase q, A1 and A2 hold.

- **A1. Later never contradicts or undoes earlier.** q never removes, reverses, weakens or silently strengthens
  what p owns: requirement rows, closing sprints, Gate Integrity rows, cited tests, mutants and their killers,
  oracle rows, owned documents and the behavior of preparation tools that p's runs use. q extends p only through
  interfaces p defines; a backend or foreign-family implementation adds its own host-declared module or build
  component instead of editing p's interface. A needed change to p's contract is p's work while p is not Done,
  and afterwards a governed change (T.G) after which p still passes at its own stage. q edits a file owned within
  closure(p) only when the same verified run shows every Done phase passing, and never removes or narrows a test
  that executes earlier-owned sources unless that run keeps them fully covered. A rule q introduces judges files
  only inside verdicts whose closure contains q (T.F); p's verdict and printed stage never change because q exists.
- **A2. Incomplete later work never blocks earlier validation.** Except for the shared failures of T.F, p's
  verdict and identity depend only on closure(p): every module p's gate route imports or runs, every native build
  component p's evidence uses, every file p's tests read, every evidence citation of p, every killer of p's mutants,
  every test p's coverage relies on, every oracle and data home they load, and every half p requires is owned within
  closure(p). A later artifact, row, citation, planned absence, row-level plan or document defect, failure, status,
  ledger row or missing host never enters p's identity or verdict (T.I, T.F, V3). Preparation (VM, binder,
  credential shares, one-time setup) runs outside `agentctl check`; p re-observes prepared state under the run
  nonce with checks owned within closure(p), so preparation can leave p unrun but never makes p pass.
- **A3. Authoring consequences.**
  - Implementation lists only paths owned by or planned for p. Deliverables name earlier-owned paths as
    "consumes `<path>`" or, for a permitted A1 edit, "migrates `<path>` (owner `<title>`)", and Docs to update and
    Documentation Requirements name an earlier-owned page under `documents/` only in that "migrates" form. The
    Cross-references to add label names the companions plainly, because a later phase's companion edits are rows
    that T.I projects to it. A re-homing change of p may name the receiving host-declared module of a later phase
    whose lane includes its family as "moves … to `<path>` (owner `<title>`)", and that phase lists the module in
    its Implementation as planned for it; otherwise later-owned paths never appear.
  - Each test module has one owner, who cites its portable nodes; a node declared to the `linux-clean` or
    `linux-live` half (T.X) is cited only by phases whose lanes include that half. An evidence citation of p names a
    node in a module owned within closure(p). A later phase adds nodes, corpus rows, oracle rows and support rows
    only to files it owns, with two exceptions: the mixed-owner data files `tests/support.txt`,
    `src/agentctl/check/coverage_hosts.toml`, `tests/oracles/requirements.toml`, `tests/oracles/check_legs.toml`,
    `tests/oracles/host_lanes.toml`, `tests/oracles/phase_ownership.toml`, `tests/oracles/backend_profiles.toml`,
    `tests/oracles/lint_config.toml`, `tests/oracles/forbidden_surfaces.toml` and `tests/mutants/phase.toml`, and
    the file of a protected row that an appended `amends` case or T.G record must sit beside. In these it only
    appends rows that T.I projects to it and never edits an existing row, and Deliverables name an appended
    `amends` case or record as "migrates `<path>` (owner `<title>`)".
  - Re-homing: misplaced work moves to its owner. Python code that only a foreign family executes, and any
    foreign-family arm that a later phase would otherwise have to edit, moves to a host-declared module owned by
    the earliest phase whose lane includes that family and whose closure contains every first-party module and
    native package the arm needs, reached lazily through `foundation_host` (D-167); any other
    foreign-family branch of a Haskell or C source stays with its owner as a host-declared region (T.X), whose
    native confirmation is owed as below (D-162). A mutant moves to
    its target's owner (T.M M1) with a decision row naming each protected id. A test node moves to the owner of
    the contract it discriminates. Confirmation a lower phase cannot observe is `owed:` to a later phase whose lane
    includes that family or half and whose closure contains the source, paired with that phase's Confirms line;
    it is never a gap in the lower verdict.
  - A ledger row's Location lies in artifacts owned within the closure of its Deleted-by phase; a migration
    spanning owners is one row per owner.
  - Shared doctrine (companions, `AGENTS.md`, `CLAUDE.md`, the root README and pages owned by
    [Governance and phase evidence](phase-0-governance-and-phase-evidence.md)) is completed by that phase;
    afterwards it changes only through closure records, rows that T.I projects to their owners, or a governed
    change whose decision row names the consumers it invalidates. Later phases never list a page under
    `documents/` that Governance owns in Docs to update or Documentation Requirements, and their companion edits
    are rows that T.I projects to them.
  - A page links an anchor only in a page owned within its owner's closure or in a companion; links into
    later-owned pages target the file.
- **A4. Interim.** Until per-locus attribution and identity projection land, every plan and document defect is
  shared and every companion edit re-hashes every phase; each edit keeps both validators clean on the whole tree.
  These gaps are ledger rows of [Governance and phase evidence](phase-0-governance-and-phase-evidence.md).

| Obligation | Enforced now | Target |
|---|---|---|
| Lower Depends on; no forward number in Remaining Work | `plan.dependency-direction` | Depends on equals manifest; closure-owned paths, citations, killers and Locations (`plan.well-ordering`) |
| Activation only after Done prerequisites | `plan.status-consequences` | Done bound to a verified `pass`; regressed computed |
| Protected rows change only through records | ratchet | retirement, relocation and same-owner retarget records; every applied record listed in the run |
| Stage-2 governed records, owned by [Python discipline and gate integrity](phase-1-python-discipline-and-gate-integrity.md) | — | re-anchor, retarget, killer-addition, killer-relocation and closure-set records (T.G) |
| Each mutant declared by its owner with every killer cited | `plan.gate-integrity` | anti-laundering ownership; a Gate Integrity row of any phase cites mutants owned within its closure with every killer |
| Every Gate Integrity row cites an applicable mutant (T.M M3) | — | a phase whose row cites no applicable mutant fails V5 |
| Owed confirmation paired | `plan.gate-integrity` (host-acceptance receivers), `plan.header` | any lane-including receiver, with Confirms on a self-verifying receiver; an owed item discharged only by passing `real` or `observer` citations on its half (D-159) |
| Later failures stay with their locus | — | per-finding and per-half attribution, including lazily loaded command, gate-leg and probe modules; attribution of a later-introduced rule to its introducer |
| Closure-only identity, imports and coverage | — | identity projection, including the rows of § A and § U; gate import closure; closure-scoped coverage of the verdict of Governance and phase evidence |
| Closure-scoped coverage of every stage-2 verdict, owned by [Python discipline and gate integrity](phase-1-python-discipline-and-gate-integrity.md) | — | V6 over each stage-2 verdict's closure |
| Closure-scoped native components, owned by [Python bootstrap and handoff](phase-2-python-bootstrap-and-handoff.md) | — | per-owner native components, each holding its owner's model library and test suite, which no product component links; each verdict's product executable, evaluator, test suites and build fixture built from its closure only (D-163) |
| Per-half verdicts; foreign halves from stored receipts | — | per-half verdict, with V3–V6 and V10 judged per half of the lane and mutants applicable per half; nodes declared to a half; receipt store with byte-for-byte import and export |
| Gate evidence `none recorded` or `current verdict`, with no dated row | `plan.evidence-rows` (an acceptance phase covering its input closure stays Planned or Active; another records a dated row once Done) | `current verdict` accepted |
| Non-disruptive gate environment | — | host facts observed once by the parent and sealed for every child, so the host fixture spawns nothing and agent probes run only on the bound dedicated guest; a run-owned test environment for the pytest leg, nested sessions and every killer child, with live inputs only for `linux-live` nodes; per-killer deadlines that reap every descendant; vetoes on resolved spawn paths outside the allowed roots, on registry and clipboard calls and on signals to unregistered processes (§ Q, D-172) |
| Derived evidence classes | — | each node's class derived from the nonce-bound records that its interpreters write, never declared by its author (T.E E5, D-175) |
| Oracle `amends` cases as records | — | an appended `amends` case binds the hash of the row it amends and a decision row naming that row's id, and the run lists it; a transcript row is never amended (T.G, D-174) |
| Half-declared branch assertion | — | half-declared nodes collected and executed on every run, each asserting the branch its half's sealed qualification requires; a qualifying `linux-live` run holds an observer record of the installed agent from each live node; a declaration admitted only when observed, and never moving a mutant's owner without a T.G record listed in the run (§ O, D-150, D-179) |
| Killer grammar for suites and live rows | — | suite-qualified `haskell:<suite>/<Group>/<case>` killers beside the present form; `linux-live` nodes as killers only of rows declared wholly to that half (T.K K6, D-163, D-179) |
| Model admission and closed-list source rules, owned by [Python discipline and gate integrity](phase-1-python-discipline-and-gate-integrity.md) | — | model registry and independence; conformance only from ratcheted rows; model adequacy; conformance-gated kills; seed rows with a nonce-seeded baseline; the revised E4 with the per-file caps lifted; the source rules of the closed list (T.E E3, E4 and E7, T.K K7, T.M M5, T.S S12–S15, D-174) |
| Harness provisioning, owned by [Windows toolchain and psmux build](phase-9-windows-toolchain-and-psmux-build.md) | — | a Windows gate leg that runs agentctl's own psmux provisioning once per run, never per mutation, in a validation-only private root with pinned, digest-checked downloads and bounded parallelism, its code mutants killed by installer and toolchain models (§ Q, D-180) |

Each implementing change moves its row from Target to Enforced now in the same change. A row whose Obligation
names an owner belongs to that phase, and every other row belongs to
[Governance and phase evidence](phase-0-governance-and-phase-evidence.md); T.I projects each row to its owner, so
the change that moves a later-owned row re-hashes only the verdicts whose closure contains that owner (D-165).
§ U names the test of every rule in the Enforced now column.

### B. Detailed, Implementation-Oriented Content

Name concrete modules, resources, tests, mutants, observer outputs and failure criteria. Planned paths and node
ids are deliverables of Planned and Active sprints, explicitly distinguished from existing evidence (§ C); a Done
sprint cites only present paths and present, passing nodes. Every validation action states its input/setup,
observable pass and refusal conditions, and source-independent expectation. A prose claim, version banner,
hand-built receipt or successful exit alone is not behavioral proof.

External facts have version/revision, verification method and source in
[external tool facts](../documents/reference/external_tool_facts.md). A candidate pin is not a proven artifact.

### C. Honest Completion Tracking

| Status | Meaning |
|---|---|
| Planned | Execution of the revised contract is not started; existing incompatible artifacts are ledger inputs |
| Active | Work on the revised contract has started and Remaining Work names every unmet obligation |
| Done | The owned contract is complete, its verdict is `pass` in a verified run (T.D) and no owned deletion remains |

Only the status table in README rolls up phase status. Headers and sprint tags agree with it. Statuses are
authored only as Planned, Active and Done; regressed, awaiting and blocked are computed (T.D). A Done phase that
later fails is regressed and is repaired in place, never set back to Active; every verdict whose closure contains
it fails until it passes again (V9).

Done requires all sprints Done and Remaining Work `None.`. A phase can have several Active sprints. A Planned
sprint's Remaining Work is `The whole sprint.`; its phase names its whole sprint range. A Planned consumer may
contain existing code but cannot claim readiness from it.

An Active phase's Remaining Work is a table with the columns ID, Obligation, Closing check and Sprint. Each
closing check is a node id, a mutant id or a rule name, and no cell holds a count, run id or date. A planned test
node is an unmet deliverable of the citing phase (T.F, V3), so a Planned or Active sprint can cite it in
Validation tests and a new Gate Integrity row can cite it in its Tests cell. Until its corpus row exists, a
planned mutant id appears only in a Planned sprint's Deliverables, marked as planned, or in this table: the
activation edit replaces the whole-phase string with this table, naming every planned node, mutant id and rule
the phase owes, and the change that adds a corpus row moves its id into sprint and Gate Integrity fields. A
Mutants field or cell without a corpus mutant says, after `none — `, where its planned ids are named.

### D. Declarative Current-State Language

Contracts use present tense; status supplies completion, not verb tense. Phase files and companions carry no
narrative test counts, run ids, dated completion claims or historical cleanup sprints. Gate evidence carries no
run date once Gate evidence accepts `current verdict` (§ A); until then § U states the form the check enforces.
Rationale can preserve quoted provenance and explicitly amended decisions; current contracts
follow the applicable amendment.

### E. One Canonical Folder Model

`DEVELOPMENT_PLAN/` contains README, these standards, overview, inventory, rationale, deletion ledger and one
contiguously numbered phase file per README row. Phase numbers and filenames are fixed: work is reordered by
re-homing obligations to their owners (§ A), never by renumbering.
Governed prose lives under `documents/` in architecture, engineering, operations and reference.
No alternate roadmap, workflow runner, hidden source directory or duplicate contract home is introduced.

### F. System Component Inventory

[system-components.md](system-components.md) inventories target modules, shipped resources, tools, tests and
owned directories with stable capability ownership and one phase owner. The gate's executable ownership
manifest covers every present artifact, including ledger inputs, and its mapping agrees with this inventory.
The inventory shows each present artifact's current manifest owner; an artifact due to move or to be deleted
carries a move note naming the Remaining Work or ledger row that moves it.
Shared inputs belong to their earliest substantive owner and are included in every actual consumer's digest.

### G. Phase and Sprint Document Requirements

Each phase declares Status, lower Depends on links, Host lane, the sole Gate `agentctl check`, Gate kind and
Closes. Host-acceptance phases also carry Gate evidence and Evidence covers; Gate evidence is `none recorded` or
`current verdict`, because the verdict itself is the current verified `PHASE` line (T.O), and § A names the form
enforced until `current verdict` is accepted. Ordered sections are
Phase Objective, Gate Integrity, Not Proven By This Gate, Confirms, Sprints, Remaining Work and Documentation
Requirements. Confirms is mandatory for host-acceptance phases. A self-verifying phase carries Confirms only as
the receiver of owed items, from the change that lets owed pairing accept any receiver whose lane includes the
family (§ A). A Confirms line pairs an owed item with its receiver; it never discharges the item, which is
discharged only when the `real` or `observer` citations of its source row pass natively on the owed half (T.V,
D-159).

Each sprint has a contiguous id, status tag and matching Status; Implementation paths; Validation tests; Mutants;
Closes; Docs to update; then Objective, Deliverables, Validation and Remaining Work. A planned node id can be
absent before its owner is implemented; it is never represented as collected or passing until observed. An
evidence citation is a node in a Validation tests field or a Gate Integrity Tests cell, and V10 judges it under
T.E in its context, the citing row or, for a node only a sprint cites, that sprint; any other backticked node is a census citation, which counts toward the orphan-module census but is never
judged as evidence (T.X).

Gate Integrity names a requirement, independent oracle, observer, applicable mutants and actual test nodes.
A Mutants cell without a corpus mutant starts `none — ` and holds no backticked mutant id. A pure, native or
observer control states what it proves. Missing required evidence fails its own verdict.

### H. Documentation Requirements Section

Every phase names architecture, engineering, operations/reference and cross-reference changes, or None.
Documents state target contracts in present tense and name actual enforcement separately, only beside an
existing passing node. Every documented target that present code does not meet is a ledger row with exactly one
owner that is not Done, split into one row per owner when it spans owners (§ I). The ledger, not misleading
implementation prose or stale Done status, owns standing deviations. Each amended implementation updates
its contract, inventory, oracle amendment and deletion row in the same change.

### I. Absence Guards and the Legacy Ledger

[legacy_tracking_for_deletion.md](legacy_tracking_for_deletion.md) is a census of still-present unwanted shapes
and of documented targets that present code does not meet, with concrete locations, the behavioral reason and
exactly one non-Done deletion owner. A shape or gap spanning owners is one row per owner, and each row's Location
lies in artifacts owned within the closure of its owner (§ A). The owner's deliverables
and Remaining Work include the migration. A ledger entry is not a scanner suppression, excluded source set or
license to weaken tests. Remove its row only with the actual shape; assert the desired shape with positive
delivery evidence as well as absence controls. No closing phase can retain its owned rows.

### J. README and Documents Harmony

README is the only cross-phase status table. Every phase appears in both its table and index. Documents cite
phases by linked title, not ordinal. Root AGENTS carries the authoritative VirtualBox/no-commit policy; CLAUDE
imports AGENTS and states no rule of its own. Documents link the § T clauses they rely on and never restate them.
No document asserts that an unimplemented new rule already has enforcement.

### K. Requirement Anchoring

The overview has one row per stable requirement ID, an exact request anchor, one closing sprint, evidence
classes and canonical prose/data homes. Requirement rows are append-only: a committed row, its closing sprint
included, never changes, and an obligation that moves to another owner is an appended row plus a decision row
naming the ids it affects. A requirement's prose home is a page owned within its closing phase's closure; a
committed row whose home a later phase owns keeps its contract text frozen in the spans that D-153 names, which
change only through a governed change (T.G). Preserve original request
text and trace amended intent explicitly. A new user
instruction can replace a planner decision; record its precedence and tests instead of weakening an oracle
silently.

### L. Evidence Classes and What Cannot Count

- `value`: independent expected values for a pure contract, and model-backed behavior: unchanged production
  code run through a declared effect interpreter against a conformant environment model ([T.X](#tx-terms)).
  Generated property cases over pure code and model-based cases are `value`, and a model-backed node is `value`
  and never native.
- `real`: production code through production native interpreters, with no environment model bound to them, on
  run-owned real resources of the named host, namely helper processes, registered stand-in executables among
  them, private multiplexer servers and the harness provisioning
  ([§ Q](#q-containment-and-user-state-protection)).
- `observer`: nonce-bound independent observation of effects, bytes or resource identities within the closed
  list of § Q; an environment model's trace is `value`, never `observer`.
- `owed`: native or live confirmation a lower phase cannot observe, assigned per § A A3 to one later receiver
  whose lane includes that family or half and paired with that receiver's Confirms line; only `real` or
  `observer` citations discharge it (T.V).

A node's class is derived from the nonce-bound records that its interpreters write, never declared by its author
(T.E E5, D-175). A documented fixture supports classification consistency, not a real agent screen claim, and an
environment model supports only the behavior that its conformance rows anchor ([T.C](#tc-ceiling) C8). A test
counts as evidence only when [T.E](#te-unspoofable-test) admits it in its citing context at the citing phase's
stage (T.W). Finite tests have declared bounds; they prove neither universal totality nor invisible agent state
(T.C C5). Manual review, a commit, answered dialog, fixture capture request or fabricated attestation is never
gate evidence.

### M. Gate Integrity

Every named applicable mutant is killed as [T.K](#tk-kill) defines at the citing phase's stage: against a
passing baseline it dies for its specified reason in its named killer. An import or syntax error, or a failed
build of the mutated native component, is never a kill; from stage 2 neither is a crash, timeout, teardown error or
other unrelated exception ([T.S](#ts-defended-spoofs) S5). Mutant ownership and adequacy follow
[T.M](#tm-adequacy). Accepting and refusing twins cover failure paths: model twins on every run of each family a
source executes on, and native twins for the thin native layer on its own family (T.X, V6). The
subject is never substituted: its production code runs unchanged, and its environment is replaced only by a
registered environment model bound to a declared effect interpreter (E4 of [T.E](#te-unspoofable-test), D-170,
D-174). `unittest.mock` stays banned, and no test uses another mock framework or substitutes a first-party
attribute; from stage 2 this is clause E4, and until then per-file caps freeze the substitution forms already
present. The full relevant test, mutant, coverage and source census is independently joined to nonce-bound
execution.

New source rules have alias-aware positive/refusing controls and mutants in agentctl's own gate. Strict Python
migration covers product, checker, harness, tests, environment models and native boundary declarations. Checker
labels do not exempt mutable state or opaque types. No package/library is adopted solely to impose this
doctrine; QuickCheck, through the `TestSource` wrapper, is adopted for testing as a product-closure dependency
once its versions and native builds are verified (D-176).

### N. The Single Gate, Gate Kinds and Host Lanes

`agentctl check` takes no arguments and is the only closure entry point. It runs every introduced leg and
collects/executes every present test without selection. It retains complete diagnostics; its verified parent
publishes one verdict per phase and the overall exit code (T.O). A failure owned by a later locus never changes
an earlier verdict (§ A, T.F).
Independently owned later syntax/import/collection failures retain failed-module and missing-node evidence while
unrelated earlier modules continue. Shared or ambiguous collection damage, stale nonces, unowned artifacts,
write-guard damage, containment failures and the other shared failures of [T.F](#tf-shared-and-owned-failures)
fail every phase, even if a convenient subset of tests passed.

A self-verifying phase requires current evidence over its full input/prerequisite closure. A host-acceptance
phase consumes or records actual native/live receipts and adds no product implementation. Every phase requires
Linux plus at most one foreign family. Its lane is one of the following, and each lane is evaluated by its
halves (T.V V8):

| Lane | Halves | Required observed evidence | Foreign family |
|---|---|---|---|
| linux | `linux` | Debian Linux editable dev checkout, git and tools introduced by that phase | none |
| linux-windows | `linux`, `windows` | Linux receipt plus native Windows x86_64 receipt for this input closure | Windows |
| linux-macos | `linux`, `macos` | Linux receipt plus native Darwin receipt for this input closure | macOS |
| linux-live-clean | `linux-clean`, `linux-live` | Debian Linux, real two-stage clean preparation (`linux-clean`) and logged-in agents (`linux-live`) | none |

One census runs on every host: every run collects and executes the same complete census (§ O), model and value
nodes never branch on host family, and only native-resource tests and the harness branch, on the sealed family
(D-170). The parent's agent probes start an agent CLI only on the bound dedicated guest
([§ Q](#q-containment-and-user-state-protection), T.X), so only that guest supplies the `linux-live` half. Only
the clean container that guest builds supplies the `linux-clean` half (D-142), and the lanes, their halves and
the lane predicate are unchanged (D-179).

On Windows, a dedicated Debian VirtualBox guest can supply the Linux halves only when its observed capacities,
installed Linux dependencies and same-checkout bind mount satisfy [the runbook](../documents/operations/validation_runbook.md).
Guest evidence supplies no Windows/Darwin ABI proof.
Linux pure/refusal branches of foreign tests execute without skip markers, but do not mint native receipts.
A half that no verified run has supplied prints `absent` (T.O), so each phase that requires it is at best
`awaiting:<half>` and its verdict follows T.V; passing values from another half never substitute for it.

A cross-lane join matches shared logical source/policy/prerequisite contract identity; it separately verifies
per-half native toolchain/artifact sub-identities. Linux and Windows executable or compiler hashes are not required to
equal each other. Phase identity is the per-closure identity of [T.I](#ti-identity): it binds the owned and shared
source, oracle, config and patch bytes, relevant artifacts and tools, and prerequisite identities within the
phase's closure. A later-only source change or row preserves every earlier identity. A shared contract change
invalidates its consumers. A final product receipt covers the complete tree and native backend identities.
Receipt records include phase, half, identity, nonce, test/mutant/coverage sets, host facts, prerequisite
identities, outcome and retained diagnostics. Gate evidence records `none recorded` or `current verdict` (§ G);
the verdict is the current verified `PHASE` line, and whole-product acceptance is `EVIDENCE pass` (T.O). A digest
is not independent attestation that a run happened (T.C C1).

### O. The No-Skip Suite and Host-State Adaptivity

No skip, xfail, importorskip, deselection, `-k`, `-m` or node narrowing is possible inside the closing gate.
Every present test executes; every present source file and deferred shape is inventoried. A planned missing
test is unmet work of the phase that cites it (T.F). Host-state branches assert their declared actual behavior
or refusal; they never silently return early. A half-declared node (T.X) is collected and executed on every run
and asserts the branch that its half's sealed qualification requires: the live or clean branch on a run that
natively evaluates that half, and on every other run the refusal branch, which starts no agent CLI, container or
installer (D-150, T.S S17). A branch chooses only from the sealed host facts and its half's qualification, never
by probing an agent CLI or a tool outside the closed list of
[§ Q](#q-containment-and-user-state-protection). An unavailable foreign half stays unavailable, regardless of
passing Linux or model values.

Lint, types and coverage run over complete owned censuses and report source locations/capabilities. Legacy
findings remain visible and fail the consumers of their source; they are global integrity failures only when
[T.F](#tf-shared-and-owned-failures) lists them as shared. Shared modules and shared test support cannot be
mislabelled as later-only to launder a failure. No legacy source disappears from final whole-product acceptance.

### P. The Ratchet and Automatic Closure

HEAD is a read-only external baseline; agents never stage, commit, push or move it. An unborn repository has
no historical baseline. Independent current-run evidence remains mandatory either way.
Committed oracle/mutant provenance and requirement identities are retained; corrections append explicit
content-bound amendments, and every protected-row change is a governed record of [T.G](#tg-governed-changes).
Requirement rows are append-only, and an owner change is a decision row, never a renumbering. Validator
migration tests distinguish authorized metadata amendments from removed oracle cases, broadened suppressions and
weakened expected behavior.

Phase closure consumes the phase's own `pass` in a verified run (T.V), never another phase's incomplete verdict
or the overall later-only failure. Final product closure requires every phase to pass, with foreign halves from
current stored receipts (V8), and is printed as `EVIDENCE pass` (T.O).
No approval, clean tree, signature, publishing action or manual inspection is required to advance.

### Q. Containment and User-State Protection

Tests disturb nothing the run did not create. This section holds containment, non-disruption and user-state
protection: the closed list of what a test may touch, its teardown and failure rules, and the setup and
credentials that preparation may use (D-170, D-172).

Production and gate code never alter user credentials, agent configuration, shell profiles, toolchain defaults
or unrelated sessions. Native package/toolchain preparation is consented outer work, with no package managers,
sudo, login or dialogs inside tests; the harness provisioning below is the one gate leg that provisions, and
only into its validation-only private root. No ordinary check prompts. Privilege is not consent. Preparation
runs outside `agentctl check` and is never evidence: a phase re-observes prepared state under the run nonce
(§ A).

**A test may touch** only the closed list, and every test multiplexer, endpoint, process and external short
build root in it is nonce-registered and owned (D-172):

- **Run-owned temporary roots.** The checkout and the application's own state directories are read-only to
  tests, apart from the live folder of the `linux-live` half (live inputs, below).
- **Processes it starts and owns.** These include helpers, fixtures, agentctl's own executables and the gate's
  declared tools. They run in a run-owned process group or job, with CPU, memory and duration bounds and a
  constructed `PATH` of run-owned shims.
- **Private tmux or psmux servers under run-owned names.** Every invocation carries a private home, an absolute
  `PSMUX_DATA_DIR`, `PSMUX_NO_WARM=1`, a private `TMUX_TMPDIR` and no inherited `TMUX`.
- **Read-only copies of host-installed tools**, such as ghcup, tmux and psmux, under private routing.
- **Prepared state**, read only.
- **Loopback networking.** Only the `linux-live` half and the pinned downloads of the harness provisioning
  reach further.

**A test never touches** these; the one exception is the `linux-live` half on the bound dedicated guest, whose
nodes run the installed agent CLIs with the live inputs below:

- the user's agent CLIs, credentials, settings or sessions;
- installers, package managers, `sudo` or login;
- the registry or the OS clipboard;
- console control events outside a console the run created;
- other VMs, or shared tool stores and index updates.

**Host facts** are observed once by the parent and sealed for every child, so no test probes the host for them,
and an agent probe starts an agent CLI only on the bound dedicated guest (D-172, D-179).

**Live inputs**, namely the real home and profile, the agent configuration directories, agent `PATH` entries
and credential variables, reach only nodes declared to the `linux-live` half, and only on the bound dedicated
guest, where those nodes also create and use `<state>/live-acceptance` (D-179). Every other test, killer child
and nested session runs with run-owned roots and a `PATH` through which no agent CLI resolves.

**The harness provisioning** is the gate leg of
[Windows toolchain and psmux build](phase-9-windows-toolchain-and-psmux-build.md) that runs agentctl's own
psmux provisioning once per Windows run, never per mutation: a cold build on a host's first run and an
idempotent re-check afterwards, in a validation-only private root with bounded parallelism. Its pinned,
digest-checked downloads are the only network use outside the `linux-live` half, and it changes no `PATH`,
profile or toolchain default (D-180).

**Teardown** waits for actual child and handle release and verifies endpoint and resolved absolute path
ownership before any kill or removal. Nothing is killed by image name, and no computed or unverified path is
deleted recursively:

- tmux uses `kill-server` only on an owned `-S` socket, after the scope check.
- psmux never uses `kill-server`. A psmux session ends by its exact target after its registry PID and creation
  identity are verified, and no test starts a psmux of an unsupported version.
- A real psmux client runs only in a terminal the test created, and attaches only to run-owned servers whose
  panes emit no OSC 52 or bell, which a synthetic test client checks first.
- Clipboard and bell one-shots go only to synthetic test clients.
- A test signals only processes it started.

**Failures:** a vetoed effect is a failure of its node, and a leaked run-owned resource is a shared containment
failure (T.F). Primary and cleanup failures are reported separately, and diagnostic receipts are retained
outside disposable directories. Until the non-disruptive gate environment and the half-declared branch
assertion of § A are enforced, no test runs natively on the Windows host or the Mac and tests run in the bound
dedicated guest; native Windows runs also wait for the Windows containment arm of
[Windows toolchain and psmux build](phase-9-windows-toolchain-and-psmux-build.md) (D-181).

A Windows agent can create an agentctl-only Debian VirtualBox VM sized from observed host capacity with
headroom, install all needed Linux dependencies, and bind mount the host checkout. Observe VM CPU, memory,
swap and virtual disk/free-storage capacity, and record allocations and usage when practical. Proof of
cross-project CPU, memory or storage isolation is not a prerequisite for Linux validation.
Do not alter other VMs or existing sessions.
Host/guest changes are the same live unstaged/untracked tree, never a commit/copy synchronization scheme. The
clean container of the `linux-clean` half and a native Darwin run each hold a byte-identical tree of the bound
checkout, taken after binding with no edit before their gate finishes, whose logical identity equals that of the
guest's stored receipts; neither substitutes for the bind mount (D-142, D-151). The container run natively
evaluates only the `linux-clean` half, qualified by the clean state it observes under its own nonce, and its
receipts join the guest's only with equal identities (V8, D-164).
The bind mount must prove source identity, complete byte census agreement, two-way fresh nonce visibility
including unstaged and untracked state, ordinary read/write and owned-sentinel cleanup. When it cannot, the binding
is not established: the guest gate is not run, so the halves it would evaluate stay unrun (T.X, § A A2), and a
run on the bound checkout without a current binding receipt fails
`tests/integration/test_virtualbox_binding.py::test_shared_checkout_identity`; a run in the guest on a non-shared
tree, such as the clean container, claims no shared-folder binding (D-164). The mount's permission-change,
lock, case and symlink behavior is observed and recorded as a mount fact rather than a qualification prerequisite.
Tests needing POSIX filesystem semantics use dedicated Linux roots, never the source mount.

Besides the dedicated VM and its shared folders, validation agents may perform only this enumerated host setup,
as preparation:

- install Visual Studio Build Tools and the Windows SDK;
- install a container runtime and the agent CLIs inside the dedicated VM;
- maintain a Claude Code permission allowlist in the user-level `~/.claude/settings.json`, outside the checkout,
  limited to ssh to the dedicated VM, `VBoxManage` for that VM, the binder, `agentctl` and deletion of verified
  cache paths, with no wildcard grant.

No setup, preparation, run or check restarts a host or uses a disposable OS environment, and a setup whose
outcome needs a restart leaves its capability absent (D-141, D-171). Because the allowlist file is user-level,
an edit to it also reaches the host user's Claude Code sessions that are already running (D-141).

Agent credentials reach the VM through transient VirtualBox shared folders of the host `.claude` and `.codex`
folders, mounted read-only at `/mnt/host-agents/{claude,codex}`. Only `~/.claude/.credentials.json` and
`~/.codex/auth.json` are symlinked; the guest keeps its own writable `~/.claude.json` and settings; binaries are
never mounted, and the host stays the single writer of refreshed tokens. If the status probe fails, or the
tokens desynchronize, those two files are copied with mode 0600 instead and the choice is recorded in host
facts. Credential copies remain private. The guest can refresh the shared login while host sessions use it
([T.C](#tc-ceiling) C10).

Login commands and login keystrokes, changes to other VMs or sessions, wildcard permissions and changes to host
agent configuration beyond the allowlist remain forbidden. When a capability is missing, its probe reports
absence, and only the phases awaiting it wait, each at best `awaiting:setup:<name>` (T.V).

### R. Imported Practices and Explicit Non-Adoption

Adopt independent oracles, immutable typed models, scoped effects behind declared effect interpreters,
conformant environment models, property-based and model-based testing with Haskell's test tools (D-176),
executable closure, full test census, content-bound mutants and explicit evidence ceilings ([T.C](#tc-ceiling)).
Tooling remains the project's own pinned gate. Do not introduce alternate workflow runners, automatic
user-session migration, package-manager tests, mock frameworks or attribute substitution of first-party code,
host restarts or disposable OS environments, source suppressions, snapshot-only fake native evidence or
prebuilt product/backend distribution; registered environment models are the sanctioned mocks (D-170). The
focused `pytest --stepwise` sweep of the testing-cost method in [AGENTS.md](../AGENTS.md) is a development tool,
not a workflow runner: it runs with a private `cache_dir` and closes no work, and `--stepwise` is never passed to
`agentctl check`.

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
| Gate mechanics | [quality gate](../documents/engineering/quality_gate.md) | [Governance and phase evidence](phase-0-governance-and-phase-evidence.md) |
| Unspoofable evidence, verdicts, progression and limits | [§ T](#t-unspoofable-evidence-and-phase-verdicts) | [Governance and phase evidence](phase-0-governance-and-phase-evidence.md) |
| Evidence, isolation and observers | [testing](../documents/engineering/testing.md) | [Python discipline and gate integrity](phase-1-python-discipline-and-gate-integrity.md) |
| Native/VirtualBox preparation | [runbook](../documents/operations/validation_runbook.md) | [Governance and phase evidence](phase-0-governance-and-phase-evidence.md) |

### T. Unspoofable Evidence and Phase Verdicts

These clauses define admissible evidence, phase verdicts, progression and their limits. Documents link the
clause they rely on instead of restating it (§ J). They rest on eight testing principles (D-170):

1. Behavior is proven by unchanged production code against conformant environment models (E3, E7).
2. The subject is never substituted (E4).
3. Tests touch only the closed list of [§ Q](#q-containment-and-user-state-protection).
4. Only the thin native layer, private multiplexer servers and the harness provisioning earn `real` evidence
   (§ L).
5. One census runs on every host (§ N, § O).
6. Live and clean acceptance happen only in the dedicated VM (§ N).
7. No host restart and no disposable OS environment ever supplies setup or evidence (§ Q).
8. Named-reason mutation kills stay the backbone (T.K, T.M).

#### T.0 Principle

A phase verdict is unspoofable when the only changes that can turn it from `fail` to `pass` make the claimed
behavior real, or are governed records the gate validates and lists in the same run (T.G). A `value` claim is
real when the unchanged production code meets its independent expectations, against conformant environment
models wherever its environment is modeled (E3, E7); a `real` or `observer` claim is real when it is observed on
run-owned resources or read-only prepared state of the named host (§ Q, E6). One no-argument `agentctl check`
run decides every clause. No clause needs a commit, review, login command or login keystroke, dialog,
attestation or host restart; a logged-in agent (T.X) is a setup capability, never an action of the run.

#### T.A Adversary

An agent with write access to the checkout, its state directory and the run environment, seeking the cheapest
passing verdict.

#### T.S Defended spoofs

Each defended spoof names the stage that first enforces it (T.W).

- S1 stale or replayed records (stage 1; stored foreign receipts per T.C C3).
- S2 hand-written or edited reports, `PHASE` lines or statuses (stage 1).
- S3 partial execution: skip, xfail, deselection, a missing cited node or a missing leg (stage 1).
- S4 tests that no named defect makes fail (stage 1).
- S5 kills by crash, import, build, timeout or teardown error (import and syntax errors and a failed build of a
  mutated Haskell component at stage 1, the rest at stage 2).
- S6 subject-derived expectations (stage 2).
- S7 substitution of the subject or the verification chain, including a mock framework or an attribute
  substitution of first-party code (stage 2).
- S8 evidence from a host outside the claimed half (stage 1).
- S9 checkout, index, refs, interpreter or report changed during the run (stage 1).
- S10 weakening protected rows (stage 1), or shrinking a Done phase's cited sets outside a closure-set record of
  T.G (stage 2).
- S11 laundered attribution, or restructuring code only to change coverage (stage 2).
- S12 a permissive, subject-derived or unregistered environment model: one that accepts or answers what the
  real tool refuses or answers otherwise, shares the subject's decision code or codecs, or is built outside a
  registered model module (stage 2).
- S13 conformance anchors edited together with the model they anchor, such as an oracle `amends` case, an
  amended transcript row, a facts row or a test literal standing in for a ratcheted row (stage 1 for oracle
  `amends` cases and transcript rows, stage 2 otherwise).
- S14 seed shopping: the seed, size or count of a generated case chosen so that a baseline passes or a mutant
  survives (stage 2).
- S15 effects outside the closed list of § Q, or an observation of a resource the run does not own presented as
  a private one (stage 1 for the vetoes and the run-owned environment, stage 2 for the source rules).
- S16 half-declaration laundering: a declaration to a half that no record of that half's resource justifies,
  used to move a node out of a verdict or a mutant to another owner (stage 1).
- S17 a half-declared node passing by a branch other than the one its half's sealed qualification requires, or
  a live node on a qualifying run with no observer record of the installed agent (stage 1).
- S18 value evidence presented as native: a model-backed node offered as `real` or `observer` evidence
  (stage 1).

#### T.E Unspoofable test

Each evidence citation of a test T by phase p has a context c: the Gate Integrity row whose Tests cell names T,
or, for a node that a sprint's Validation tests field names and no Gate Integrity row of p cites, that sprint,
whose Mutants field supplies the mutants of E2 and whose Implementation field, or a Gate Integrity row of p,
names the oracles of E3 (D-160). T is admissible in context c of phase p in run r if and only if:

- E1 Executed: collected and executed under r's nonce; collected equals executed; nothing skipped, xfailed or
  selected; T passed.
- E2 Discriminating: a mutant m cited in c and applicable to p (T.X) names T as a killer and is killed on each
  half of p's lane where it is applicable, natively in r or in that half's current stored receipt (V8), or in a
  run that T.V shares within the half's family. T would have failed, for the stated reason, had the behavior been
  removed.
- E3 Independent (stage 2): expectations are literals in T, rows of an oracle that c names and T loads, or the
  answers, state and trace of an environment model that satisfies E7; no expectation is computed by subject
  code. A refusal case asserts the typed reason.
- E4 Unsubstituted (stage 2): T runs the subject's production code unchanged and controls only environment
  variables, the working directory and values passed through the subject's declared parameters; a declared
  effect-interpreter parameter is bound only to a production native interpreter or a registered environment
  model, and a stand-in executable that answers a third-party command is such a model too (T.X, D-174). T sets,
  deletes and wraps no first-party attribute, uses no mock framework, and fakes no host identity, native library
  or handle except as the answers of such a model through a declared effect interpreter.
- E5 Classified (stage 1): the class is derived from the nonce-bound records that the interpreters write during
  T's call phase, never declared by its author. A model-backed node (T.X) derives `value`; `real` and
  `observer` derive only from records of production native interpreters acting, with no model interpreter, on
  run-owned resources, on read-only prepared state or on the `linux-live` half; and a declared class, such as a
  marker or a group name, equals the derived class (§ L, D-175).
- E6 Native: a `real` or `observer` claim for family f counts only on a run whose sealed host family is f.
- E7 Conformant (stage 2): every environment model that T uses is built by a registered model module, imports
  only raw boundary types, passes all its conformance cases in r, and has owner mutants that those cases alone
  kill (T.M M5, D-174).

#### T.K Kill

A mutant m is killed in r if and only if, in a scratch copy of r's census:

- K1: the search occurs exactly once in the target and the patched bytes differ.
- K2: every named killer passes unmutated without the reason, and (stage 2) executes the mutated span.
- K3: under m every named killer fails with the reason in its assertion output, with no ImportError,
  ModuleNotFoundError, SyntaxError or INTERNALERROR, and a Haskell killer whose mutated component fails to build
  is not killed. From stage 2 the failure is raised in the call phase from the killer's own module, and setup and
  teardown pass.
- K4: the target is restored, and (stage 2) the scratch digest equals the census.
- K5 (stage 2, new rows): the reason is a literal in the killer and absent from the target and the replacement.
- K6 (stage 2): a mutant whose target is a host-declared source, or whose search lies in a host-declared region
  (T.X), is a kill obligation only on the runs of its declared families, and a row declared wholly to one half,
  every named killer of which is declared to that half, is a kill obligation only on runs that natively evaluate
  that half; other runs record `owed:<family>` or `owed:<half>`, never a skip (D-167, D-168). A half-declared
  node is a named killer only of a row declared wholly to its half, so no row mixes portable and half-declared
  killers, and the live mutants of
  [Linux live and clean acceptance](phase-12-linux-live-and-clean-acceptance.md) are such rows of the
  `linux-live` half (D-179).
- K7 (stage 2): a generated killer runs under the seed, size and count of a ratcheted row that names it, and its
  kill is judged under that seed; the baseline also runs it once with a seed derived from r's nonce, which a
  failure prints (D-174, D-176).

No kill, baseline or mutant outcome is reused from another run. From stage 2, a kill by a killer that uses an
environment model counts only when that model satisfies E7 in the same run (D-174).

#### T.M Adequacy

- M1 Ownership: a mutant is owned by its target's owner. A later phase owns it only if no killer is owned within
  the target owner's closure, or if every killer is declared to one half outside the target owner's lane, when the
  lowest phase whose lane includes that half and whose closure contains the target owns it (D-168). A change of
  owner of a HEAD-protected mutant, or of its killers' modules, needs a decision row naming the id.
- M2: every applicable mutant (T.X) is killed by each named killer on each half of p's lane where it is
  applicable, natively in r or in that half's current stored receipt (V8), or in a run that T.V shares within the
  half's family.
- M3: every Gate Integrity row cites at least one applicable mutant and every killer of each cited mutant.
- M4 (stage 2): generated decision mutants are killed.
  - The mutated decisions are negated conditions, swapped arms, dropped refusal returns, swapped Ok/Err and
    deleted appended problems.
  - Selection is deterministic per unit, seeded by the unit's content hash and bounded by declared resource
    limits.
  - A survivor no killer executes is reported as dead code to delete; an AST-equal mutant is discarded. There is
    no other equivalence escape.
- M5 (stage 2) Model adequacy: every environment model has owner mutants, which weaken its refusals or answers,
  killed only by its conformance cases, and those cases alone execute all of its code: for a Python model,
  coverage from its conformance nodes alone; for a Haskell model, M4 mutants generated inside its modules, whose
  only admissible killers are its conformance cases (D-174).

#### T.V Verdict

PASS(p, r) holds if and only if V1–V10 hold:

- V1 Verified: the parent verified every child seal against r's nonce before and after retention, including the
  sealed per-step health record. The report is retained outside the checkout and unchanged; the guarded census
  equals the captured census; write guard, containment, cleanup and finalizers passed; the interpreter is
  unchanged.
- V2 Current: p's and its prerequisites' identities equal the parent's recomputation (T.I).
- V3 Complete: every required test, mutant and coverage subject is present and passed, killed or covered, and
  every owed item that p receives is discharged (below). Other phases' planned absences never enter p.
- V4 Intact: once the provisional marker is stripped, p carries no owned failure and r has no shared failure. The
  stripped strings are enumerated exactly.
- V5 Adequate: T.M holds at p's stage.
- V6 Covered: every statement and branch of every Python source p consumes is executed on its family by tests
  owned within closure(p), except sources declared foreign to it; every Haskell and C source p consumes, other than
  a native test fixture or a registered model module (M5), closes instead by the evidence form of R20.2:
  named-reason kills, model twins on every run of each family the source executes on (T.X), and native
  accepting and refusing twins of the thin native layer on its own family (D-143). Governance and phase evidence
  scopes its own coverage this way at stage 1; every other verdict's scoping and the R20.2 evidence form are
  stage-2 checks.
- V7 Ratcheted: every HEAD-protected row is unchanged except through T.G records.
- V8 Native, per half: r natively evaluates only the halves its sealed host qualifies. Every other half of p and
  of each prerequisite comes from the latest stored receipt of a verified run on that half, with equal logical
  and prerequisite identities.
- V9 Prerequisites: every prerequisite passes under the same per-half rule.
- V10 Admissible: every evidence citation of p satisfies T.E at p's stage.

V3–V6 and V10 hold for each half of p's lane, each judged on the run that natively evaluates that half or read
from that half's current stored receipt (V8); E2 and M2 join a mutant's kills across the halves where it is
applicable (T.X). Halves of one family share kills and coverage: on a half of p's lane, E2, M2 and V6 count a
kill, or an executed statement or branch, from the current verified run of any half of the same family that p or
a prerequisite requires, with equal logical identity, while node outcomes, E1, probes and half-declared citations
stay per half, so neither half's run substitutes for the other's (§ N, D-168). A node outcome, kill obligation or
coverage gap that arises on a run whose natively evaluated halves all lie outside p's lane never enters p's
verdict, and T.F names its owner. An owed item that p receives
(§ G) is discharged on its owed half only when the `real` or `observer` citations of its source row, whose class
is derived (E5), pass there natively and satisfy T.E at p's stage; `value` citations, model-backed nodes among
them, never discharge it. Until then that half has a gap (V3), which never enters the source phase's verdict
(D-159). R20's native observations are read per half: a self-verifying phase keeps at least one `real` or
`observer` citation on each half of its lane, and a half with none has a gap (V3), while the rest of its
evidence may be `value` evidence against conformant environment models (D-175).

The verdict is `pass`, `awaiting:<half>`, `awaiting:setup:<capability>`, `awaiting:prerequisite` or `fail`:

- `pass`: PASS(p, r) holds.
- `awaiting:<half>`: the only gap is a half with no current stored receipt.
- `awaiting:setup:<capability>`: a named probe reports absence and every failure of that half is attributable to
  it.
- `awaiting:prerequisite`: the only gap is an awaiting prerequisite. A gap that is only a prerequisite's absent
  half or capability yields `awaiting:prerequisite`, never that half or capability.
- `fail`: otherwise.

When several halves or capabilities qualify, the verdict names the first such half in the T.O half order, as its
`awaiting:setup:<capability>` when that half's probe reports absence, and the `phase-failure` lines list every
gap. A half with no current stored receipt, or whose probe reports absence, prints `absent` in the `halves=`
field (T.O). A probe judges its capability only on the host that prepares it, so the clean container of the
`linux-clean` half never evaluates `setup:container-runtime` (D-164).

#### T.I Identity

- Identity is per phase over closure(p), hashing p's input bytes.
- It includes only those rows of the ownership manifest, coverage hosts, requirements table, decision tables,
  ledger, inventory, Document Index, the § A obligation and § U rule tables of these standards and mixed-owner
  data files (corpus, oracle and support files) whose owner or consumers intersect closure(p).
- Status cells, sprint tags, Remaining Work bodies, Gate evidence values and the Validation Hosts table are
  replaced by placeholders.
- A later-only artifact or row never changes an earlier identity.
- The cross-lane join uses this logical identity; native tool and executable hashes are per-half sub-identities.

#### T.F Shared and owned failures

Shared failures fail every phase. They are exactly:

- an unparseable manifest, corpus, host-declaration file or companion file, or an unowned present artifact;
- write-guard differences;
- stale nonces, and seal, retention, report or interpreter changes;
- shared or ambiguous collection damage;
- containment, cleanup or finalizer failures;
- tool schedule or identity mismatches;
- a nonzero sealed step code with no failure carrying that step's prefix.

Every other failure is owned by its locus:

- a planned absence, by the citing phase;
- a failing, erroring or missing node, by every phase whose evidence citations name it; an uncited present node,
  by its module's owner and that module's consumers, or, when the node is declared to a half, by the phases whose
  lanes include that half;
- an import or execution failure of a module discovered in the commands, gate-leg or probe directory, by that
  module's owner and, for a probe, by the phases awaiting its capability;
- collection damage confined to one module, by its consumers;
- static, validator, coverage and native findings, by their source's consumers;
- a row-level plan or document defect, by the row's or page's owner;
- a cross-file plan defect, by the highest-numbered phase involved (an owed mismatch by the receiver, a duplicate
  closure by the later closer);
- a build failure of a native component, by that component's owner and the verdicts whose closure contains it; a
  verdict's closure-scoped build never includes a component outside that closure, so no earlier native node waits
  on it (D-163);
- a kill, by the mutant's owner;
- a failure of a rule introduced by phase q, by those of the phases that the clauses above give it whose closure
  contains q, and also by q when its locus is owned within closure(q), as T.W applies to a stage-2 finding. A
  finding of an earlier phase's rule in a later-owned locus therefore stays with that locus, no rule changes a
  verdict whose closure lacks it, and a failure left with no owner enters no verdict and stays in the run's report
  and exit code (T.O). Every validator rule, gate leg, stage-2 checker and rule-bearing oracle row declares the
  phase that introduces it;
- a node outcome, kill obligation or coverage gap that arises on a run whose natively evaluated halves all lie
  outside the lane of a phase that cites or owns it never enters that phase's verdict (T.V); it is owned by the
  receiver to which that phase owes that family or half (§ A A3), otherwise by the lowest phase whose lane
  includes such a half and whose closure contains the locus and every first-party module and native package that
  the locus, or for a kill obligation each killer of the mutant, loads or runs on that half (D-167). Such a kill
  obligation or coverage gap enters no verdict when the current verified run of another half of the same family
  meets it with equal logical identity (D-168), and when no phase qualifies it enters no verdict and stays in the
  run's report and exit code (T.O).

The last two clauses take precedence over the clauses before them. Unclassified failures are shared.

#### T.O Output

Only the parent publishes, after V1, one line per phase in ascending order:

```text
PHASE <n> <verdict> status=<s> lane=<lane> host=<family> stage=<1|2> identity=<64hex> prerequisites=<n>=<hex>,… halves=<half>:<own|stored|absent|failed>,… failures=<k> nonce=<32hex>
```

- The halves are `linux`, `windows`, `macos`, `linux-clean` and `linux-live`. A half prints `own` when this run
  evaluated it natively and it passes, `stored` when it comes from a current stored receipt that passed, `absent`
  when no current stored receipt exists or its probe reports absence, and `failed` otherwise.
- Failures follow as `phase-failure <n>: …`, then `sprint <n.m>: ready|open` lines, then one `selection:` line in
  the grammar of T.D.
- Child-originated `PHASE` and `EVIDENCE` lines are relayed only as `withheld unverified:`, on both streams.
- `EVIDENCE pass …` is printed only when every phase passes.
- The exit code is 0 only when V1 holds, every step code is 0 and every phase passes.
- An unverified run prints `phase verdicts withheld: <reason>` and exits 1.

#### T.D Status and progression

Statuses stay Planned, Active and Done. Regressed, awaiting and blocked are computed, never authored.

- Done requires `pass` in a verified run. A Done phase that later fails is regressed and is repaired in place.
- Blocked means awaiting a half or capability that the plan README's Validation Hosts table lists as `no`, or
  `awaiting:prerequisite` whose awaited prerequisite is blocked. A `fail` is never blocked.
- `selection:` names one phase and its action, choosing in order:
  1. the lowest regressed or awaiting Done phase that is not blocked: `repair` when it fails, otherwise the action
     for its gap;
  2. the lowest unblocked Active phase: `close` when it passes, `work` when it fails, otherwise the action for its
     gap;
  3. the lowest Planned phase whose prerequisites are Done and pass: `activate`;
  4. otherwise `stop`, listing each blocked phase and what it awaits.
- The action for a gap is `run` when the phase awaits a half that this run's host does not supply, and `setup`
  when it awaits a setup capability; since the phase is not blocked, Validation Hosts lists either as `yes`. A run
  with `run` selected asks for the next run on a host that supplies that half. A phase awaiting a prerequisite is
  never selected ahead of that prerequisite.
- After two consecutive verified runs with the same selection, identity and failure set, the line reads
  `stop no-progress` with the selected phase instead.
- The line has this closed grammar, where `<awaited>` is a half, `setup:<capability>` or `prerequisite`:

  ```text
  selection: repair <n>
  selection: work <n>
  selection: close <n>
  selection: activate <n>
  selection: run <n> <half>
  selection: setup <n> <capability>
  selection: stop [<n>=<awaited>,…]
  selection: stop no-progress <n>
  ```

- A sprint is Done when a verified run shows its paths present, its cited tests passed and its cited mutants
  killed.

#### T.G Governed changes

A protected row changes only through a record that binds the prior row's hash and a unique decision row naming
the id, validated and listed in the same run. The record kinds are:

- Amendment: search and replace only.
- Oracle amendment: an appended oracle `amends` case, which binds the hash of the row it amends and a decision
  row naming that row's id. A transcript row is never amended; a new tool version appends a row instead
  (D-174).
- Relocation: an unchanged row moved between corpus files.
- Retirement: the target is absent from the census and lay, at HEAD, outside the static import closure of every
  non-test entry point. When the retired behavior survives in another target, a successor row keeps at least one
  original killer and the reason; when the behavior is deleted with its target, the decision row names the
  decision or user instruction that removes it, and a quoted user instruction counts only if its quote is present
  in HEAD's Originating Request.
- Re-anchor and retarget (stage 2): a re-anchor changes the search and replacement, a retarget changes the target
  file, and one record can do both. The reason and killers stay byte-identical, the new search occurs exactly
  once in the new target (K1), and every killer fails under the new mutant for the row's reason (K3). A
  same-owner retarget, which changes only the target, to another file of the same owner after the searched code
  has moved there so that the search no longer occurs in the old target, is instead a stage-1 record (D-169).
- Killer addition (stage 2): adds a named killer that fails under the mutant for the row's reason (K3) and is
  owned within the closure of the mutant's owner.
- Killer relocation (stage 2): replaces or removes named killers of a row while at least one killer remains. Each
  replacement fails under the mutant for the row's reason, and every remaining killer is owned within the closure
  of the mutant's owner.
- Closure-set record (stage 2): removes a node or mutant from a Done phase's cited sets. It binds the prior set's
  hash and a decision row naming the phase and the ids, and the phase still passes at its stage.

A killer that touches the host is converted in place, keeping its node id and its kill for the row's reason,
wherever the converted node still kills, and the row then changes through no record; otherwise killer-addition
and killer-relocation records migrate it (D-178).

A governed change of a contract that a Done phase owns, or of a frozen prose span (§ K, D-153), is an edit made
together with a new decision row that names the requirement or contract, its owner and every phase whose verdict
the edit invalidates. The edit changes each named phase's identity (T.I), so each is judged again at its own stage,
and selection repairs it first if it fails (T.D, D-161). Requirement rows are append-only.

#### T.C Ceiling

This is the only statement of limits; it is never a closure condition.

- C1: a seal or digest proves what this run's verified parent observed, not that any past run happened.
- C2: an author who rewrites the gate, its tests, corpus, oracles and decisions together is not resisted. Rows
  added since the last user commit have current-run protection only.
- C3: stored foreign receipts are accepted on content and identity equality, so they are forgeable by whoever
  writes the state directory.
- C4: a compromised host, VM, kernel, interpreter or tool is out of scope beyond recorded identities. This
  includes isolation, continuous immutability, inode reuse and escaped descendants.
- C5: finite tests and mutants prove only the cases they exercise.
- C6: stage-2 clauses are authoring doctrine until enforced; each verdict prints its stage.
- C7: Validation Hosts changes selection, never a verdict.
- C8: a claim that rests on an environment model, a stand-in executable included, proves agentctl's behavior
  against that model; agreement with the real tools rests only on conformance rows and on native or live replay
  of transcript rows (D-174).
- C9: the gate never observes a cold Visual Studio Build Tools installation, the hop from a real client to the
  OS clipboard, or that the cached candidate an idempotent harness provisioning run re-checks was built by
  agentctl (D-171, D-180).
- C10: on the bound dedicated guest, the shared host login can be refreshed while host sessions use it; the user
  accepted this when keeping live acceptance (D-179).

#### T.W Staged enforcement

The definition is complete; each clause is enforced from the sprint that builds its checker.

- Stage 1 ([Governance and phase evidence](phase-0-governance-and-phase-evidence.md)) uses existing mechanisms.
- Stage-2 checkers are deliverables of
  [Python discipline and gate integrity](phase-1-python-discipline-and-gate-integrity.md) (R20).
- Every verdict whose closure contains that phase is judged at stage 2 over its whole closure, earlier-owned
  files included. Earlier lines keep the stage they print.
- A stage-2 finding in a file owned by phase o is owned by max(that phase, o) and its later consumers, which
  repair it under A1.
- Known stage-2 violations are frozen by per-file caps at current counts.
- Closure-scoped coverage (V6) is a stage-1 mechanism for the verdict of
  [Governance and phase evidence](phase-0-governance-and-phase-evidence.md) and a stage-2 check for every other
  verdict.
- M4 is report-only until the Sprint 1.3 change that enforces it, which lands before Python discipline and gate
  integrity closes, so enforcing it never strengthens a Done verdict (A1); until that change M4 is authoring
  doctrine (T.C C6).
- The testing doctrine stages the same way (D-170). Its stage-1 clauses, the E5 class derivation, the mechanics
  of S15–S18 and the records of oracle `amends` cases (S13), are mechanisms that
  [Governance and phase evidence](phase-0-governance-and-phase-evidence.md) builds (D-172, D-175). Its stage-2
  clauses, E3, E4, E7, K7, M5 and the source rules of S12–S15, are checkers of
  [Python discipline and gate integrity](phase-1-python-discipline-and-gate-integrity.md) (D-174). Until a
  clause is enforced it is authoring doctrine (T.C C6).

#### T.X Terms

- closure(p): p plus its transitive prerequisites.
- stage(p): 2 if and only if closure(p) contains R20's closing phase.
- non-test entry point: HEAD `[project.scripts]` targets, closed under static imports and `-m` launches inside
  that closure.
- owned within closure(p): the manifest owner is in closure(p), or an unmanifested planned path is a deliverable
  of the citing phase or of a phase in its closure.
- evidence citation: a node in a Validation tests field or a Gate Integrity Tests cell, judged in its T.E context.
  Any other backticked node is a census citation, which V10 does not judge.
- applicable mutant: a corpus mutant that p cites and whose target is owned within closure(p). It is applicable
  on a half of p's lane when it is a kill obligation on that half (T.K K6), and a mutant applicable on no half of
  p's lane is not applicable to p.
- preparation: as A2 defines it.
- unrun: a half that no verified run on a host qualifying it has evaluated, and a phase is unrun on such a half;
  other runs print the half `absent`, and the phase's verdict follows T.V.
- logged-in: an agent CLI whose status probe succeeds on the bound dedicated guest; on any other host the probe
  starts no agent CLI and reports absence (D-179).
- attested: historical proof; never required.
- native twin: accepting and refusing cases of one production function of the thin native layer on one host in
  one run.
- model twin: accepting and refusing cases that run one production function unchanged through its declared
  effect interpreter over a registered environment model, on every run of each family its source is declared
  to execute on, or of every family when the source is not host-declared (D-143).
- owed: native or live confirmation assigned per A3 and discharged only by `real` or `observer` citations (T.V).
- host-declared: listed in the host-declaration file as executing only on its named families, either as a source
  or as a region of a shared Haskell or C source; a host-declared module is reached lazily through
  `foundation_host`, and a host-declared region stays with its source's owner (§ A A3). The file can also declare
  a test node to the `linux-clean` or `linux-live` half: that node is evidence, and a killer (T.K K6), only for
  that half, so only a phase whose lane includes it cites the node.
- host-declaration file: `src/agentctl/check/coverage_hosts.toml`.
- portable node: a node of a test module that is neither host-declared nor declared to a half, so every run
  executes it as evidence of each half of the run's family that the run natively evaluates.
- half-declared node: a node that the host-declaration file declares to the `linux-clean` or `linux-live` half.
  It is collected and executed on every run and asserts the branch that its half's sealed qualification
  requires, and its declaration is admitted only when its records on a run that natively evaluates the half
  observe that half's resource, a spawn of the installed agent CLI or a clean-state observation (§ O, D-150). A
  node that starts an agent CLI, logged in or not, lies in a module that
  [Linux live and clean acceptance](phase-12-linux-live-and-clean-acceptance.md) owns and is declared to the
  `linux-live` half (D-179).
- closure record: a value that T.I replaces with a placeholder, namely a status cell, sprint tag, Remaining Work
  body, Gate evidence value or the Validation Hosts table.
- provisional marker: the enumerated strings that the child adds to every phase it reports and that V4 strips
  after V1.
- edit: any change of the census digest.
- environment model: a pure, total and deterministic model of an external tool, OS facility, agent CLI or
  installer that answers a subject's effect operations as that facility would. Every value other than a
  production native interpreter that a test binds to a declared effect-interpreter parameter, and every stand-in
  executable that answers a third-party command, is an environment model, admitted only when a registered model
  module builds it (D-174). A model is owned by the owner of the contract it models; a later owner adds state and
  program models only through the world type's `ext` slot in its own modules, and an earlier model never changes
  for a later need (§ A A1, D-177).
- registered model module: a module of an owner's model library, which lives in that owner's package and which
  no product component links, `exe:agentctl-core` included (D-163), or of the registered `tests/models/` Python
  package. It imports only raw boundary types, never a subject module, renderer, parser or codec (D-174).
- model-backed node: a node that binds an environment model to a declared effect-interpreter parameter, so that
  a model interpreter answers its subject's effect operations; it is `value` evidence and never native. A
  registered stand-in executable that the subject starts through a production native interpreter runs as a
  run-owned helper process and does not by itself make its node model-backed (§ L, D-175).
- effect interpreter: the declared parameter through which a subject performs its effects. For Haskell code it
  is a record of operations at the raw OS boundary, `Effects m`, for processes, files, the clock and the
  console, passed through the existing `ExceptT failure m` shells, with one production native interpreter and
  one model interpreter per subsystem; `System.Info.os` appears only in production interpreters, and elsewhere
  the host family is a declared value (D-173). For Python code it is a declared adapter parameter. Production
  passes the native interpreter, a test may pass a registered model, and the subject's code is the same under
  both.
- raw OS boundary: the level of every effect operation. For a process it takes the absolute executable,
  argument vector, working directory, environment, stdin bytes and deadline, and returns the exit status, the
  output bytes and whether it timed out; files, the clock and the console have their raw calls and values. It
  carries no renderer, parser or codec of any tool's grammar.
- program model: an environment model of an external program, such as tmux, psmux, claude, codex, cargo or an
  installer, installed at an executable path in the modeled process table. It parses its argument vector with
  its own code and never imports a subject renderer, parser or codec (D-173).
- conformance case: a `value` case that checks an environment model against ratcheted oracle rows, transcript
  or conformance rows that it loads or streams as JSON to its owner's evaluator subject. An external tool facts
  row is provenance for such a row, never an expectation, and a test literal never anchors a model (D-174).
- transcript row: an append-only oracle row that records the operations sent to a real tool on run-owned
  resources and the tool's observations, with its version, command and host. It is never amended, a new tool
  version appends a row, and a native replay twin re-checks it against the real tool wherever that tool runs on
  a private server or on the `linux-live` half (D-174).
- model mutant: a corpus mutant whose target is a registered model module; it is owned by the model's owner and
  killed only by that model's conformance cases (T.M M5).
- run-owned resource: a temporary root, process, endpoint, private multiplexer server or record that the run
  started or registered under its nonce.
- closed list: the enumeration in § Q of what a test may touch, and of what it never touches outside the
  `linux-live` half on the bound dedicated guest (D-172).
- private multiplexer server: a tmux or psmux server that the run starts under a run-owned socket or registry
  name with the private routing of § Q; it never lists, attaches to, signals or ends a server or session that
  the run did not start.
- synthetic test client: a run-owned program that connects to a private multiplexer server in place of a real
  client and records what it receives, such as clipboard and bell one-shots, without touching the OS clipboard
  or a console the run did not create.
- thin native layer: the production native interpreters and the native code beneath them that perform real OS
  effects and that no environment model stands in for in their own tests, such as the native interpreters of
  `AgentCtl.Process` and `AgentCtl.Native` with their C ABI, the Python process foundation and the
  host-declared native adapters. Its native twins run on run-owned resources of its own family (V6).
- bound dedicated guest: the dedicated Debian VirtualBox guest of the
  [runbook](../documents/operations/validation_runbook.md) on a run whose sealed host facts carry a current
  binding receipt of the bind-mounted live checkout; the clean container, which claims no binding (D-164), is
  not the bound guest.
- live inputs: the real home and profile, the agent configuration directories, agent `PATH` entries and
  credential variables. They reach only nodes declared to the `linux-live` half, on the bound dedicated guest
  (§ Q, D-179).
- harness provisioning: the Windows gate leg of
  [Windows toolchain and psmux build](phase-9-windows-toolchain-and-psmux-build.md) that runs agentctl's own
  psmux provisioning once per run, never per mutation (§ Q, D-180).

### U. Plan and Closure Checks

Each row states what its check enforces, and the change that builds or alters a check updates or appends its
owner's row in the same change. Every row below belongs to
[Governance and phase evidence](phase-0-governance-and-phase-evidence.md); a later phase that builds or extends a
check appends its own row, naming itself in the Enforces cell, and never edits an existing row, and T.I projects
each row to its owner (D-165). A rule that is not built never appears here; § A's Target column or its owner's
Remaining Work names it. `tests/governance/test_plan_validator.py::test_live_plan_clean` runs every structural `plan.` rule over
the live plan.

| Rule | Enforces | Test |
|---|---|---|
| `plan.fileset` | `DEVELOPMENT_PLAN/` holds exactly the companions § E names and the phase files that the README Current Phase Status table links; phase files are named `phase-<n>-<slug>.md` and their numbers run contiguously from 0 | `tests/governance/test_plan_validator.py::test_plan_fileset` |
| `plan.header` | Each phase file starts `# Phase <n> — <title>`; its header holds exactly Status, Depends on, Host lane, Gate, Gate kind and Closes, plus Gate evidence and Evidence covers when Gate kind is `host-acceptance`; Status is Planned, Active or Done, Gate is `agentctl check` and Gate kind is `self-verifying` or `host-acceptance`; its `##` sections follow § G, with Confirms present exactly on host-acceptance phases; its Documentation Requirements holds the four fixed labels in order. Each companion starts with a title and carries Status, Supersedes, a Purpose line and `## Related` | `tests/governance/test_plan_validator.py::test_plan_header` |
| `plan.status-harmony` | The README Current Phase Status table has the columns #, Phase and Status and one row per phase in number order, whose linked file and status equal that phase's file and header Status | `tests/governance/test_plan_validator.py::test_plan_status_harmony` |
| `plan.sprint-structure` | Each phase has at least one sprint; sprint headings read `### Sprint <n>.<m>: <title> [<tag>]` with ids contiguous from `<n>.1`; each tag is Planned, Active or Done and equals the sprint's Status field; each sprint holds exactly the fields Status, Implementation, Validation tests, Mutants, Closes and Docs to update, in order, and exactly the `####` headings Objective, Deliverables, Validation and Remaining Work | `tests/governance/test_plan_validator.py::test_plan_sprint_structure` |
| `plan.status-consequences` | A Done phase has Remaining Work `None.` and only Done sprints; a Planned phase has the exact whole-phase Remaining Work string and only Planned sprints; an Active phase has Remaining Work that is neither empty nor `None.`; a phase that is not Planned depends only on Done phases; a sprint's Remaining Work is `None.` when Done, `The whole sprint.` when Planned, and other non-empty text when Active | `tests/governance/test_plan_validator.py::test_plan_status_consequences` |
| `plan.dependency-direction` | The first phase depends on `nothing`; every other phase's Depends on links at least one phase, each existing and lower-numbered; no phase or sprint Remaining Work names a `Phase <n>` numbered above its own phase | `tests/governance/test_plan_validator.py::test_plan_dependency_direction` |
| `plan.requirements-table` | The overview Requirements table has its fixed header and rows of seven cells with unique `R<n>` or `R<n>.<m>` ids; each Quote is a backticked substring of the rationale's Originating Request; every requirement is closed by exactly one sprint, whose link starts its Closing sprint cell, and no sprint closes an undeclared id; each phase's header Closes equals the union of its sprints' Closes | `tests/governance/test_plan_validator.py::test_plan_requirements_table` |
| `plan.legacy-ledger` | The ledger table has the header Shape, Location, Why it must go and Deleted by; every row has four cells and its Deleted by cell names the file of a phase that is not Done | `tests/governance/test_plan_validator.py::test_plan_legacy_ledger` |
| `plan.disposition-table` | The rationale Concept-Note Disposition table has at least one data row; each has six cells, a Disposition of `adopted`, `adapted`, `rejected` or `deferred-to-phase` and a non-empty Destination | `tests/governance/test_plan_validator.py::test_plan_disposition_table` |
| `plan.no-narrative` | No phase heading of levels one to three contains Historical, Superseded, Corrected, Deprecated or Legacy; no unfenced phase text counts tests, test passes or killed mutants, or holds an ISO date outside a Gate evidence line; the plan README has at most 200 lines | `tests/governance/test_plan_validator.py::test_plan_no_narrative` |
| `plan.gate-integrity` | Each phase's Gate Integrity table has the header Requirement, Oracle, Observer, Mutants and Tests and at least one row; each row has five cells, a requirement id the overview declares, `kind: detail` observer items whose kind is `value`, `real`, `observer` or `owed`, at least one cited test, and oracle and mutant citations or `none — ` reasons; every mutant a row or sprint cites is owned by the citing phase under explicit source owners that cover the corpus exactly once, every corpus mutant is declared in a sprint Mutants field, and a Done sprint declares only corpus mutants; a row of a Done phase, or a row citing a corpus mutant, cites present canonical oracle files and every corpus killer of its mutants, and after the run its cited cases passed with evidence classes equal to its non-owed kinds; every `owed:` item of a self-verifying phase pairs with a Confirms line of the one host-acceptance phase it names, and every Confirms line of the form `- R<id> — …` that links a source phase pairs with an owed item | `tests/governance/test_plan_validator.py::test_plan_gate_integrity`, `tests/governance/test_plan_validator.py::test_explicit_mutant_owner_refusal` |
| `plan.cited-paths` | Each Done sprint's Implementation cites at least one backticked path or starts `none — `; each path is relative, contains no `..`, lies outside `.build` and `logs/`, is not a `.log` file and is present in the census | `tests/governance/test_plan_validator.py::test_plan_cited_paths` |
| `plan.cited-ids` | Each Done sprint's Validation tests cites at least one pytest or Haskell case id, and every cited id matches cases that the run collected, all of which passed | `tests/governance/test_plan_validator.py::test_plan_cited_ids` |
| `plan.evidence-rows` | A host-acceptance phase whose Evidence covers is `phase input closure and verified prerequisite receipts` records Gate evidence `none recorded` and is Planned or Active; any other host-acceptance phase covers `src/`, `tests/` and `pyproject.toml` and records `none recorded` while it is not Done, or, once Done, the dated row whose lane, gate, outcome and covered-tree digest equal its Host lane, `agentctl check`, `pass` and the current tree | `tests/governance/test_plan_validator.py::test_plan_evidence_rows` |
| `plan.lanes` | Every Host lane is `linux`, `linux-windows`, `linux-macos` or `linux-live-clean`; after the run, every Done phase with such a lane yields the failure `current phase receipts unavailable` for its file | `tests/governance/test_plan_validator.py::test_plan_lanes` |
| `validator.non-vacuous` | The documentation, phase-file, oracle, mutant and Haskell-source subject classes are each non-empty, unless the phase that introduces the class is Planned, in which case the class is reported not applicable | `tests/governance/test_plan_validator.py::test_validator_non_vacuous` |
| `ratchet` | Every HEAD requirement row of the overview survives with identical cells; every HEAD oracle case, mutant row and amendment row survives with identical contents, and a mutant or amendment row moves to another corpus file only through a relocation record that binds its hash and a decision row naming the mutant id; HEAD `pyproject.toml` tool tables only tighten | `tests/governance/test_ratchet.py::test_head_adapter_real`, `tests/governance/test_ratchet.py::test_ratchet_parser_boundaries`, `tests/governance/test_ratchet.py::test_edited_row_rejected`, `tests/governance/test_ratchet.py::test_relocations_preserve_committed_rows`, `tests/governance/test_ratchet.py::test_config_weakening_rejected` |

## Related

- [README](README.md) — execution and status.
- [overview](00-overview.md) — requirement ownership.
- [inventory](system-components.md) — components.
- [rationale](rationale.md) — request and amendments.
- [ledger](legacy_tracking_for_deletion.md) — current migration inputs.
- [documentation standards](../documents/documentation_standards.md) — governed prose.
