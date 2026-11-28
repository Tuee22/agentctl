# Quality Gate

**Status**: Authoritative source
**Supersedes**: N/A
**Owning phase**: [Governance and phase evidence](../../DEVELOPMENT_PLAN/phase-0-governance-and-phase-evidence.md)

> **Purpose**: Specify the mechanics by which one no-argument `agentctl check` run decides the phase verdicts of the plan standards: census, legs, seals, attribution, identity, receipts and publication.

`agentctl check` is the sole closure gate. It runs from the editable checkout with development dependencies
installed. Focused tools, including the stepwise sweep of the testing-cost method in [AGENTS.md](../../AGENTS.md),
assist diagnosis but close no work.
[§ T](../../DEVELOPMENT_PLAN/development_plan_standards.md#t-unspoofable-evidence-and-phase-verdicts) owns the
evidence definition, the verdict predicate, the `PHASE` grammar, progression and limits; this page owns the
mechanics that decide them, and the plan README owns status. This page states the target mechanics, and the
[deletion ledger](../../DEVELOPMENT_PLAN/legacy_tracking_for_deletion.md) records each place where present code
differs from them.

## Check Steps

The gate constructs one complete filesystem census of source, tests, support, stubs, oracles, mutants and
configured native components. Every artifact has exactly one stable capability owner and owning phase.
Uncommitted and ignored files remain visible. The legacy ledger records incompatible standing shapes and
their migration owners; it never excludes source, suppresses a finding or supplies a passing verdict.

Execution has these ordered boundaries:

1. Resolve the checkout/interpreter/dev installation, read the complete plan/capability declarations and the plan
   README's Validation Hosts table, which changes selection only
   ([T.C](../../DEVELOPMENT_PLAN/development_plan_standards.md#tc-ceiling) C7), observe host and prerequisite
   facts, allocate run-owned resources, and snapshot the tree and read-only Git state.
2. Run structural validators and all introduced static/build/test legs over their complete present target
   inventories. Findings are attributed to their source owners and dependency consumers, and a finding of a rule
   that a later phase introduced to the consumers whose closure contains that phase, and to that phase when the
   source lies within its closure (T.F).
3. Collect and execute the entire present pytest suite and every native suite appropriate to the observed host.
   No skip, xfail, deselection, selection option or empty-suite success substitutes for evidence.
4. Verify exact collected/executed identities, fresh nonces, evidence classes, independent expectations,
   applicable mutant kills and complete coverage for each declared phase subject and its prerequisites
   ([T.E](../../DEVELOPMENT_PLAN/development_plan_standards.md#te-unspoofable-test),
   [T.K](../../DEVELOPMENT_PLAN/development_plan_standards.md#tk-kill),
   [T.M](../../DEVELOPMENT_PLAN/development_plan_standards.md#tm-adequacy)). Every Gate Integrity row cites at least
   one applicable mutant (T.M M3), so a phase whose row cites none does not pass (T.V V5).
5. Reap owned children, inspect private endpoints and registered roots, compare the write-guard and verify the
   append-only baseline against unchanged HEAD. The child seals its per-step codes in a health record that the
   parent verifies before cleanup deletes the run directory; the parent then verifies V1 and publishes the
   verdicts ([T.V](../../DEVELOPMENT_PLAN/development_plan_standards.md#tv-verdict),
   [T.O](../../DEVELOPMENT_PLAN/development_plan_standards.md#to-output)).

A product failure is retained while independent work continues. A step unable to run because its prerequisite
failed is reported as unexecuted with that dependency, not as passed. Common corruption or an unsafe run can
stop execution, but finalizers still run wherever resources have been allocated. Exactly the failures that
[T.F](../../DEVELOPMENT_PLAN/development_plan_standards.md#tf-shared-and-owned-failures) lists are shared and fail
every phase; every other failure is owned by its locus and never changes an earlier verdict. The parent classifies
failures by the closed vocabulary of step prefixes, and an unclassified failure is shared.

A later module's syntax, import or collection failure confined to that module is owned by its consumers while
independent earlier modules still collect and execute (T.F). Its uncollected expected nodes remain unmet, never
skipped or silently omitted. Own-module collection and exact collected/executed equality stay mandatory for a
closing scope. Shared or ambiguous collection damage, such as a failed collector that no manifest row owns, is
shared (`tests/governance/test_phase_reports.py::test_owned_collection_error_is_local`).

The pytest leg continues after collection errors and records each failed collector in its manifest, while an
independent module still executes and its phase gains no collection failure
(`tests/governance/test_gate_plugin.py::test_collection_error_preserves_other_execution`).

The pytest leg attempts its coverage followups even when pytest fails, retaining the primary failure and reporting any failed followup. A followup whose own prerequisite fails is not run.

The provisional tool join refuses a successful subprocess-backed leg if its captured results omit any scheduled
subprocess. A failed leg may stop before the end of its schedule; its failure remains visible
(`tests/governance/test_ownership_manifest.py::test_provisional_tools_preserve_shared_failures`).
An incomplete sequence ending in a successful follow-up is also refused, because the runner continues after that
follow-up and cannot produce the truncated result by a normal early stop.
The provisional join also checks the planned after-failure policy: only a leg that permits it can continue after
its primary failure, and no leg can continue after a failed follow-up.

Source guard findings retain the path inspected and are provisionally attributed using the captured census and
declared consumers. The guards also evaluate the captured census bytes and require their findings to agree with the
live source walk; a disagreement remains shared. Findings with missing or unowned paths remain shared.

The Ruff check and format legs emit structured JSON and capture their subprocess outputs with the run nonce. Valid
diagnostics are provisionally mapped to their source consumers. Each original record is checked through finalizers
and sealed; the parent verifies its nonce, checkout root, contents and seal before and after retention. Each valid
diagnostic is owned by its source's consumers, unless a later phase introduced the rule that produced it, in which
case the consumers whose closure contains that phase own the diagnostic, as does that phase when the source lies
within its closure, and the step failure is shared only when no parseable finding carries the step's prefix (T.F).

The Python tool target list must match the ordered `src` and `tests` paths in the guarded source census. A
mismatch remains a shared validation failure; it does not stop the other planned tools from being attempted.
The runner also captures attempted Python command prefixes and compares them with that census, host-specific
coverage declarations, the plan, nonce and subprocess statuses. The command record binds the original Python
source digest and is checked through finalizers; its seal is verified before and after retention. After verifying
the child seal, the parent obtains a fresh guarded census and independently compares its digest and expected
Python command prefixes to the captured record. Failed containment or write-guard observations invalidate that
join. The child also seals its original ordered tool outcomes and subprocess statuses together; the parent
verifies the live and retained records against that seal. These seals are part of V1 (T.V).

The captured pytest manifest is sealed from its original collection, execution, outcome, forbidden-record and
evidence-class values after finalization. The parent verifies the live and retained manifests against that seal;
a failed manifest finalizer cannot produce a successful handoff.

The original oracle and bootstrap statuses and their per-file diagnostics are sealed together after both oracle
finalizers. The parent verifies the live and retained records against that seal, while a failed finalizer retains
its partial failure without claiming a successful oracle handoff.

Host facts and native case observations also receive separate seals after their finalizers. The native seal binds
case outcomes and source mappings to the captured native source bytes. The parent verifies each live and retained
record, and requires a passing write guard and containment observation for the native join.

The parent retains the child output before cleaning the private run root. It publishes verdicts once V1 holds:
the handoffs, the sealed health record and retention are verified and the child finalizers and cleanup have
passed, whatever the child's own exit code; the exit code then follows T.O. It snapshots retained evidence file
identities and contents before and after the handoff checks, and separately checks both output streams. A change
still present at the final comparison invalidates the handoff.
The parent carries the snapshots used by retained handoff verification across
temporary-root cleanup and compares them with the report immediately before
publication; a remaining difference withholds evidence and fails the check.
The parent also compares its selected Python interpreter's file identity and
digest before and after the child run, binds that observation to the run nonce in
the retained report, and checks it again before publication.
On Linux and Windows, the parent also observes the held gate child's native
process identity and image before releasing a private nonce to its standard
input. It hashes the image file while the child is held, compares the Linux
file with the kernel's process-image link, and joins that sample to a later
file observation and the retained nonce-bound record. The Windows process-image observer reads a path, creation
time and wait state through one process handle and refuses a dead or ambiguous image
(`tests/governance/test_process_image.py::test_checked_image_refuses_dead_or_ambiguous_values`). An unavailable or
changed observation withholds publication while preserving the child's diagnostics: the run prints
`phase verdicts withheld: <reason>` and exits 1 (T.O). These observations cover the direct child; their limits are
[T.C](../../DEVELOPMENT_PLAN/development_plan_standards.md#tc-ceiling) C1 and C4. Darwin image observation is
built by [macOS acceptance](../../DEVELOPMENT_PLAN/phase-13-macos-acceptance.md), and the Windows observer is a
host-declared source of
[Windows toolchain and psmux build](../../DEVELOPMENT_PLAN/phase-9-windows-toolchain-and-psmux-build.md).
Child-originated `PHASE` and `EVIDENCE` lines are relayed only as `withheld unverified:` on both streams; only the
parent publishes, after V1 (T.O).

Before the write-guard snapshot, a Linux checkout on a VirtualBox shared folder must have a private stored binding
whose guest root, mount, current source census and guest CPU, memory and swap allocations still match. The guest must
identify itself as Debian on VirtualBox. Ordinary Linux filesystems do not require this receipt. The binding receipt
proves only that the binding is current (T.C C1); the binder's nonce exchange precedes it
(`tests/integration/test_virtualbox_binding.py::test_shared_checkout_identity`).

The host observation records whether the Linux release identifies itself as Debian. The sealed host family decides
which halves a run evaluates natively (T.V V8): `linux-clean` and `linux-live` are separate halves whose clean state
and logged-in agents are observed under the run nonce, and any other half comes from the
[receipt store](#receipt-store) or prints `absent`, and the phase's verdict then follows
[T.V](../../DEVELOPMENT_PLAN/development_plan_standards.md#tv-verdict), at best `awaiting:<half>`.

The strict type-checking leg emits structured diagnostics over the same complete target set. The gate captures the
actual subprocess result and provisionally maps each valid diagnostic to its source consumers. Its exclusive record
is checked through the finalizers and sealed for verification before and after report retention. Each valid
diagnostic is owned by its source's consumers, or, when a later phase introduced its rule, by the consumers whose
closure contains that phase and by that phase when the source lies within its closure, the step failure is shared
only without a parseable diagnostic, and missing or
inconsistent diagnostics cannot qualify a phase (T.F).

Provisional phase calculations propagate observed prerequisite failures before adding the mandatory provisional
marker ([T.X](../../DEVELOPMENT_PLAN/development_plan_standards.md#tx-terms)), which keeps the marker from inventing
failures on dependent phases. The child marks every phase provisional; after V1 the parent strips exactly the
enumerated provisional-marker strings before it evaluates V4 (T.V).

The provisional tool join assigns a failed binary-identity step to the consumers of its captured bootstrap and
identity sources, after checking their ownership and presence. Any other nonzero sealed step code with no failure
carrying that step's prefix is shared (T.F).

When the source guard and Python command record pass, the parent independently recalculates provisional phase
input identities from its guarded census and compares the census digest to the captured command record. It
repeats the identity comparison after retention. Each phase identity is computed over closure(p), with
closure-record values replaced by placeholders at a single encoding point
([T.I](../../DEVELOPMENT_PLAN/development_plan_standards.md#ti-identity)), and V2 compares it. The parent also
rejoins the sealed pytest, mutant-killer and native-source observations to phase ownership and rejects a phase
observation that omits an attributable collection, killer or native case failure. A separate recheck rejoins sealed
oracle outcomes and details to source consumers. These checks run before and after retention when their supporting
records and guards pass.
The coverage recheck reconstructs gaps from the sealed report and assigns them to source consumers. Each of these
parent joins binds its own census to the captured command digest before attributing failures.
The static recheck separately verifies Ruff, Ruff format and ty records against their subprocess statuses and
phase consumers.
The host recheck applies the sealed native host facts to each phase's halves and rejects omitted host eligibility
failures; other halves come only from stored receipts (T.V V8).
The parent also reconstructs the tool schedule and compares the sealed outcomes with owned and shared phase
failures. It relies on the separately verified coverage join before excluding a coverage-report failure from that
tool comparison.
The parent checks that every failed shared finalizer remains on every phase, and recomputes source-policy and
missing-input failures from the bound census.
It also rechecks prerequisite propagation, excluding the provisional marker and finalizer failures added after the
phase calculation so that neither creates a false prerequisite failure.

The coverage report keeps the 100% branch floor over Python sources and includes only the checkout's
`src/agentctl` sources, so copied trees under a run root are never reported as checkout code.
`src/agentctl/check/coverage_hosts.toml` declares sources whose native paths execute only on the named host
families `Windows`, `Linux` and `Darwin`. A host run omits only the declared sources foreign to its family, so each
host-declared source is measured on its own family (T.V V6), and a declared family outside its owner's lane is owed
to a later phase whose lane includes it. An unreadable or invalid manifest, or a declared source missing from the
census, is a validator failure, and the leg then omits nothing
(`tests/unit/test_coverage_hosts.py::test_invalid_or_absent_manifest_omits_nothing`). Haskell and C sources close by
named-reason kills and native accepting and refusing twins instead of the floor (R20.2).

The constructed coverage-attribution join maps a source's missing statements and branches to its declared phase
consumers, and refuses an incomplete or ambiguous host source set
(`tests/unit/test_coverage_hosts.py::test_coverage_gaps_follow_source_consumers`,
`tests/unit/test_coverage_hosts.py::test_coverage_attribution_refuses_incomplete_census`). Provisional observations
join the captured report with its original source census, ownership, host family, nonce and pytest substep statuses.
The coverage JSON decoder checks the declared tool version and branch mode, canonical source paths, duplicate
fields, per-file line and branch observations, and per-file and aggregate statement and branch counts. A real coverage process exercises
incomplete and complete reports (`tests/governance/test_gate_plugin.py::test_coverage_json_reports_native_branches`);
the gate captures its own report with the run nonce and rechecks the original files through finalizers. The child
seals both original files; the parent verifies their nonce-bound contents before and after retaining them. The
original coverage-report command and transcript are separately captured and sealed. The parent checks that their
status and floor result agree with the retained coverage facts and pytest substeps, and rejects post-copy changes
(`tests/governance/test_gate_plugin.py::test_coverage_text_parent_joins_real_report_and_retained_evidence`). A
verified coverage-floor failure is owned by the affected source consumers, or, when it arises on a run outside
their lanes, by the owner that T.F names; an unavailable, inconsistent or
changed transcript keeps the failure shared.

When strict mutant ownership cannot be established, the child and parent may use a scoped provisional mapping only
while retaining every unresolved ownership failure on its phase and checking present native killer identities
against the captured sources. Mutant ownership may be observed with unrelated declared missing inputs only after
validating every present census entry and the actual target and killer sources; missing bytes remain absent and are
attributed separately. A source-ownership failure is provisionally localized only when an independently valid scoped
census proves that its entire diagnostic consists of declared missing sources; such a localized failure still
leaves the run's exit code nonzero (T.O), and ambiguous or unowned damage stays shared. Applicable Gate Integrity
rows also join captured Python and native execution classes to the owning provisional phase; the parent
independently recomputes the join. The finalizer
record retains failures of pre-finalizer record integrity and invocation joins as shared damage, including transient
failures that later reads cannot reproduce. The finalizer record also retains an initial oracle-details integrity
failure even if the later check succeeds, and marks that failure shared across provisional phases. The parent also
reruns shared static validators against the bound census and checks their findings against every provisional phase
(`tests/unit/test_steps_census.py::test_parent_rechecks_shared_validation_failures`); a census that changes before
or after retention fails V1 (T.V), so the run publishes no verdict. Mutant ownership follows
[T.M](../../DEVELOPMENT_PLAN/development_plan_standards.md#tm-adequacy) M1, and unresolved or ambiguous ownership
damage stays shared (T.F).

The toolchain and style readiness steps refuse missing prepared tools without installing them. Native gate builds
require a previously prepared matching private index and use offline Cabal arguments. A missing prepared tool needed
only by some phases is reported absent by its capability probe, leaving those phases at best
`awaiting:setup:<capability>` (T.V).

The write guard snapshots the Git index path reported by Git and, when present, its bytes alongside refs and
checkout files. A changed index fails the guard comparison
(`tests/integration/test_guard.py::test_index_change_detected`); the comparison is part of V1 (T.V), against spoof
S9 of [T.S](../../DEVELOPMENT_PLAN/development_plan_standards.md#ts-defended-spoofs).

The constructed receipt-join controls require each declared native family, matching logical input and prerequisite identities, per-half native identities, and the required test, mutant and coverage sets. The parent applies these joins to stored receipts (T.V V8, V9).
Receipt values have a canonical, versioned encoding covering those fields and
host facts. Decoding refuses duplicate keys, duplicate evidence members,
malformed values and alternate byte encodings. A decoded receipt is accepted on
content and identity equality only (T.C C3).
Record aggregation applies the same lane and prerequisite checks to decoded
bytes. An invalid record fails its own capability before dependency propagation,
while unrelated earlier capabilities keep their results. The parent aggregates
only receipts written by verified runs.
The parent also reconstructs a provisional receipt-input capture from the
retained census and sealed Python, native, mutant, host and coverage records,
and carries it across cleanup. A missing or inconsistent capture cannot establish
a receipt; the parent writes a receipt only after V1, into the [receipt store](#receipt-store).
The parent scopes candidate test, mutant and coverage sets to each phase and
retains missing evidence as failures. These child-side candidates keep the
provisional marker; only the parent's post-V1 verdict becomes a receipt. Native requirements include cited
cases and mutation killers even when missing from the execution manifest; explicit case
citations determine their consumers when a native source is shared.
When the provisional capture is complete, the parent retains its scoped
`phase-candidates.json` record in the external check report. It first rechecks
the complete source census and verified report snapshot, then checks the expanded
snapshot before publication. The record keeps the provisional marker; only a published `pass` closes a phase
([T.D](../../DEVELOPMENT_PLAN/development_plan_standards.md#td-status-and-progression)).
An absent native observation can reach the provisional receipt-input capture
only when the parent revalidates its sealed absence, localized finalizer and
consumer scopes. Native consumers retain the absence, and unrelated earlier
phases are unaffected (T.F).

The exit code is 0 only when V1 holds, every step code is 0 and every phase passes (T.O). Phase closure consumes
that phase's own `pass` across its required halves (T.D) and never needs a later phase to pass. Failure reports
remain visible, and the final release phase requires the complete product result. No agent may hand-select a
convenient subset, rewrite a scope after seeing failures or ignore a shared prerequisite.

## The Eight Legs

The application retains ruff check, ruff format, ty, fourmolu, hlint, Cabal build, Cabal test and pytest under
coverage as the introduced native quality legs. Their actual command tables and pins are package-owned data;
no Makefile, shell runner, hook or alternate CI gate replaces `agentctl check`.

| Leg | Required subject and result |
|---|---|
| `ruff-check` | Every declared Python source, test and stub under the pinned complete lint configuration |
| `ruff-format` | The same complete Python file inventory in canonical formatting |
| `ty` | Explicit resolved source/test roots, strict errors, no ignored diagnostics and nonempty measured targets |
| `fourmolu` | Every declared Haskell source under the complete owned formatter configuration |
| `hlint` | Every declared Haskell component under the owned hint configuration without suppression |
| `cabal-build` | All introduced native components with the pinned compiler, warning policy and explicit build directory |
| `cabal-test` | Every introduced suite, a fresh listing/report, nonempty cases and native execution identities |
| `pytest` | Every present collected case, exact execution census, phase-attributed branch coverage and mutant corpus |

Static diagnostics are mapped by source ownership, and cross-module errors invalidate every consumer whose
contract depends on the affected symbol. Coverage has complete owned source/dependency inventories; unmet
coverage fails that scope. No omitted file or altered oracle turns an incomplete phase into a passing one.
A planned absence is owned by the citing phase only and never enters another phase (T.F, V3). Present tests are
always collected and executed even when their owner is later.

## Preconditions

| Observation | Required outcome |
|---|---|
| Editable checkout and dev tools | The actual console entry, package sources and tool interpreter agree with the current checkout |
| Source and plan census | Every present artifact has one owner; all referenced closure inputs are explicit |
| Native host | OS/architecture and actual available capabilities are observed with the run nonce |
| Debian Linux | Exact Debian identity and phase-appropriate space/tools; native compilers are required only for introduced subjects that use them. A VirtualBox guest additionally has a current binder receipt |
| Windows | Native execution and the selected private backend/build provenance; guest (Linux) observations cannot replace them |
| macOS | Native Darwin toolchain, multiplexer and filesystem evidence within its separate phase |
| Preparation | Missing runtime build dependencies receive typed readiness failures and remedies; the gate never opens installers or prompts, and a missing setup capability is reported absent, leaving the phases that need it at best `awaiting:setup:<capability>` |
| Resources | Registered short roots, valid ownership/permissions, bounded CPU/memory/storage plan and adequate remaining capacity |

A missing half or capability prints `absent` for the phases that need it, and their verdicts follow T.V: at best
`awaiting:<half>` or `awaiting:setup:<capability>`, never `pass`. A portable test of host detection can pass
without claiming the unavailable backend ran.
Foreign-host requirements never make an earlier Linux phase require Windows and macOS together; each phase
declares at most one additional hardware family.

## Tool Configuration

`pyproject.toml` owns Python package/tool configuration; packaged pin data and independently ratcheted oracles
own exact versions and command expectations. No new suppression, skip, expected failure, lower coverage target
or weaker mutant makes migration easier. The Python source discipline and its controls are owned in
[code standards](code_standards.md). Their migration includes package code, gate code, tests and boundary stubs.
A rule is mechanically claimed only when its accepting/refusing controls and named mutant are part of this gate.

The run environment removes inherited tool overrides and supplies explicit UTF-8, private temporary storage,
bytecode/cache roots and declared live-auth inputs. Child stdout/stderr drain concurrently as bytes and decode
explicitly. Logs survive malformed output, parent output encodings and cleanup errors. The retained report
preserves the original failure and attaches finalizer failures rather than replacing one traceback with another.
Tool/build/mutation deadlines are declared resource bounds and do not change assertions or evidence obligations;
the Python leg deadline is the bound that decision D-139 records.

## Phase Verdicts and Evidence Line

Only the verified parent publishes, after V1, one `PHASE` line per phase in the
[T.O](../../DEVELOPMENT_PLAN/development_plan_standards.md#to-output) grammar, then the `phase-failure` lines, the
`sprint` readiness lines and one `selection:` line. Child-originated `PHASE` and `EVIDENCE` lines are relayed only
as `withheld unverified:` on both streams, and an unverified run prints `phase verdicts withheld: <reason>` and
exits 1. `EVIDENCE pass` is printed only when every phase passes; it is whole-product acceptance, distinct from a
phase's `pass`.

Each receipt binds the phase, half, per-closure identity
([T.I](../../DEVELOPMENT_PLAN/development_plan_standards.md#ti-identity)), prerequisite identities, tool and
backend identities, observed host facts, run nonce, execution, coverage and mutant manifests and the shared
integrity result. Date and diagnostic host metadata aid interpretation only (T.C C1). Receipts for a phase with
Linux and one additional hardware family join only compatible input identities. A later-only artifact or row never
stales an earlier identity; a changed shared input does.

A nonzero overall exit can coexist with an earlier phase's `pass`. An absent native run, stale source or backend
identity, missing assertion or failed shared prerequisite never produces a passing receipt. Final release closure
requires the complete tree, an empty ledger and a current receipt for every required half.

## Receipt Store

After V1 the parent stores one receipt per phase for each half the run evaluated natively, at
`<state>/validation/receipts/<phase>/<half>/<identity>/<seq>-<nonce>.json` under the private agentctl state
directory (D-130). It creates each file exclusively, without following links and with mode 0600, refuses a path
inside the checkout and never overwrites or rewrites a stored receipt. A run reads a foreign half only from the
latest stored receipt of a verified run on that half whose logical and prerequisite identities equal its own
([T.V](../../DEVELOPMENT_PLAN/development_plan_standards.md#tv-verdict) V8); otherwise that half prints `absent` and
the phase's verdict follows T.V, at best `awaiting:<half>`. The store's import and export copy receipts byte for
byte between stores and never rewrite or overwrite one, and they belong to
[Governance and phase evidence](../../DEVELOPMENT_PLAN/phase-0-governance-and-phase-evidence.md), so a later
phase adds only the channel that carries the bytes:

- [Windows toolchain and psmux build](../../DEVELOPMENT_PLAN/phase-9-windows-toolchain-and-psmux-build.md) carries guest and Windows host receipts
  over the binder's SSH channel;
- [Linux live and clean acceptance](../../DEVELOPMENT_PLAN/phase-12-linux-live-and-clean-acceptance.md) imports the clean container's receipts
  into the guest store;
- [macOS acceptance](../../DEVELOPMENT_PLAN/phase-13-macos-acceptance.md) carries receipts between the Mac and the Linux store
  over a channel the agent prepares.

What a stored receipt proves is bounded by [T.C](../../DEVELOPMENT_PLAN/development_plan_standards.md#tc-ceiling) C1
and C3.

## Selection and Sprint Readiness

The parent computes the `sprint` readiness lines and the `selection:` line from the verified verdicts, the plan
statuses and the plan README's [Validation Hosts](../../DEVELOPMENT_PLAN/README.md#validation-hosts) table, as
[T.D](../../DEVELOPMENT_PLAN/development_plan_standards.md#td-status-and-progression) defines. A sprint reads
`ready` when the verified run shows its paths present, its cited tests passed and its cited mutants killed, and
`open` otherwise. The `selection:` line uses the closed grammar of T.D. Regressed, awaiting and blocked are
computed, never authored. Each setup capability has a probe, a host-declared module of the phase that awaits it,
which reports presence or absence under the run nonce. The gate loads probes from `src/agentctl/check/probes/`
lazily, as it loads its discovered command and gate-leg modules, so an import or execution failure of one is
owned by that module's owner and, for a probe, by the phases awaiting its capability
([T.F](../../DEVELOPMENT_PLAN/development_plan_standards.md#tf-shared-and-owned-failures)); it is never a shared
failure, and a probe that fails never reports an absence. A half or capability that Validation Hosts lists as `no`
blocks only the phases that await it, directly or through a blocked prerequisite, and a `fail` is never blocked. After two
consecutive verified runs with the same selection, identity and failure set, the line reads
`stop no-progress <n>`, and an agent reports the repeated failure set instead of retrying.

When the selected phase's only gap is a half that this run's host does not supply and that Validation Hosts lists
as `yes`, the line reads `run <n> <half>`: it asks for the next run on a host that supplies that half, made by the
[canonical run sequence](../operations/validation_runbook.md#canonical-run-sequence). A native Windows run whose
store lacks the current `linux` receipts therefore names the lowest such phase, and the sequence imports those
receipts before the Windows gate. A gap that is a setup capability listed as `yes` reads `setup <n> <capability>`.

## Enforcement Stages

Each `PHASE` line prints the stage at which its verdict is judged
([T.W](../../DEVELOPMENT_PLAN/development_plan_standards.md#tw-staged-enforcement)). Stage 1 uses the Governance
mechanisms: run freshness, the complete census, named-reason kills, coverage scoped to the Governance closure, the
ratchet and the native host family. The stage-2 checkers are deliverables of
[Python discipline and gate integrity](../../DEVELOPMENT_PLAN/phase-1-python-discipline-and-gate-integrity.md),
and an earlier line keeps the stage it prints.

The non-disruptive gate environment of [§ Q](../../DEVELOPMENT_PLAN/development_plan_standards.md#q-containment-and-user-state-protection) is planned work of [Governance and phase evidence](../../DEVELOPMENT_PLAN/phase-0-governance-and-phase-evidence.md): the run's parent is to observe host facts
once and seal them for every child, so the host fixture starts no agent CLI or multiplexer; the pytest leg, nested
sessions and every killer child are to run with run-owned homes, a `PATH` of run-owned shims and private
multiplexer roots; every killer is to have a deadline that reaps its descendants; and evidence classes are to be
derived from nonce-bound records of production native interpreters, so a model-backed node is never native (rows
P0-34 to P0-39). A model-backed kill counts only in a run in which its model is conformant, a check of
[Python discipline and gate integrity](../../DEVELOPMENT_PLAN/phase-1-python-discipline-and-gate-integrity.md).


## Governed Protected-Row Changes

A protected row changes only through a record of
[T.G](../../DEVELOPMENT_PLAN/development_plan_standards.md#tg-governed-changes) that the gate validates and lists
in the same run, and requirement rows are append-only.

- **Amendments.** Mutant source migrations retain each original record and append an amendment in the same corpus
  file. The loader binds both record versions by their canonical content hashes, checks a decision naming the
  mutant, and preserves its target, operator, killers and reason. Further amendments form an ordered chain: each
  binds its immediate predecessor and changes the record. The ratchet protects the original and every amendment
  independently and retains them beside the mutant; the amended defect still requires its passing baseline and
  named kill.
- **Relocations.** A record in the optional `tests/mutant_relocations.toml` moves an unchanged row between corpus
  files. The ratchet compares every baseline and current corpus row, requires exact content hashes and documented
  decisions, and keeps amendments with their original records
  (`tests/governance/test_ratchet.py::test_relocations_preserve_committed_rows`).
- **Retirements.** `tests/mutant_retirements.toml` holds the retirement records T.G defines; the ratchet evaluates
  them before its append-only comparison and lists each one in the run.
- **Same-owner retargets.** A retarget record appended beside its row in the same corpus file changes only the
  row's target, to another file of the same owner after the searched code has moved there. It is a stage-1 record,
  which the ratchet evaluates with the retirements and lists in the run.
- **Stage-2 records.** Re-anchor, every other retarget, killer addition, killer relocation and closure-set records
  are built by
  [Python discipline and gate integrity](../../DEVELOPMENT_PLAN/phase-1-python-discipline-and-gate-integrity.md).

An oracle `amends` case is to become a governed record that binds the prior row's hash and a decision row and is
listed in the run, and a transcript row is never amended (P0-40). `haskell:` killers are to name their suite, and
nodes declared to `linux-live` kill only rows declared wholly to that half (P0-41). On Windows, a gate leg of
[Windows toolchain and psmux build](../../DEVELOPMENT_PLAN/phase-9-windows-toolchain-and-psmux-build.md) runs
agentctl's own provisioning once per run, never per mutation (D-180).


## Cross-Lane Input Identity

Linux and foreign-native receipts agree on the shared logical source, policy and prerequisite-contract
digest (T.I). Each additionally binds its own platform/toolchain/build/backend sub-identities and native host facts.
Those native executable hashes normally differ; equality across operating systems is not a join condition.
Reject a changed shared source/policy or a mismatched artifact within its own half.

## Related

- [testing.md](testing.md) — evidence classes, independent observers and isolation.
- [code_standards.md](code_standards.md) — strict Python and Haskell source doctrine.
- [toolchain_bootstrap.md](toolchain_bootstrap.md) — preparation versus validation.
- [binary_build.md](binary_build.md) — native builds and immutable identities.
- [validation_runbook.md](../operations/validation_runbook.md) — VirtualBox, native Windows and Darwin procedures.
- [development_plan_standards.md § T](../../DEVELOPMENT_PLAN/development_plan_standards.md#t-unspoofable-evidence-and-phase-verdicts) — the verdict definition, `PHASE` grammar and progression.
- [Governance and phase evidence](../../DEVELOPMENT_PLAN/phase-0-governance-and-phase-evidence.md) — gate/report migration owner.
