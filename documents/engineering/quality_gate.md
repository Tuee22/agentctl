# Quality Gate

**Status**: Authoritative source
**Supersedes**: N/A
**Owning phase**: [Governance and phase evidence](../../DEVELOPMENT_PLAN/phase-0-governance-and-phase-evidence.md)

> **Purpose**: Specify complete no-argument gate execution, independently attributable phase/lane verdicts, shared integrity requirements and reproducible evidence.

`agentctl check` is the sole closure gate. It runs from the editable checkout with development dependencies
installed. Focused tools assist diagnosis but establish no phase closure. This page defines the required gate
contract; current command output must demonstrate its implementation before its new evidence can be used.
The [plan standards](../../DEVELOPMENT_PLAN/development_plan_standards.md) own status and receipt grammar.

Mutant row relocation uses `tests/mutant_relocations.toml` when needed. The ratchet compares every baseline and current corpus row, requires exact content hashes and documented decisions, and keeps amendments with their original records. A relocation does not establish execution or closure evidence.

## Check Steps

The gate constructs one complete filesystem census of source, tests, support, stubs, oracles, mutants and
configured native components. Every artifact has exactly one stable capability owner and owning phase.
Uncommitted and ignored files remain visible. The legacy ledger records incompatible standing shapes and
their migration owners; it never excludes source, suppresses a finding or supplies a passing verdict.

Execution has these ordered boundaries:

1. Resolve the checkout/interpreter/dev installation, read the complete plan/capability declarations, observe
   host and prerequisite facts, allocate run-owned resources, and snapshot the tree and read-only Git state.
2. Run structural validators and all introduced static/build/test legs over their complete present target
   inventories. Findings are attributed to their source owners and dependency consumers.
3. Collect and execute the entire present pytest suite and every native suite appropriate to the observed host.
   No skip, xfail, deselection, selection option or empty-suite success substitutes for evidence.
4. Verify exact collected/executed identities, fresh nonces, evidence classes, independent expectations,
   applicable mutant kills and complete coverage for each declared phase subject and its prerequisites.
5. Reap owned children, inspect private endpoints and registered roots, compare the write-guard, verify the
   append-only baseline against unchanged HEAD, then issue independent phase/lane verdicts and overall status.

A product failure is retained while independent work continues. A step unable to run because its prerequisite
failed is reported as unexecuted with that dependency, not as passed. Common corruption or an unsafe run can
stop execution, but finalizers still run wherever resources have been allocated. Missing collection, false
ownership, moved refs, changed source, stale receipts or uncontained children invalidate every dependent
verdict. An unrelated later product failure does not invalidate an earlier complete phase verdict.

An independently attributable later module syntax/import/collection failure is reported against that owner while independent earlier modules still collect and execute. Its uncollected expected nodes remain unmet, never skipped or silently omitted. Required own-module collection and exact collected/executed equality remain mandatory for a closing scope. Shared or ambiguous collection failures invalidate every affected verdict; a collector must prove this isolation with executable negative controls.

The current pytest leg continues after collection errors and records failed collector node IDs in its manifest. Until owner attribution is implemented, a recorded collection error invalidates the whole run; the continuation alone does not establish a phase verdict.

The pytest leg attempts its coverage followups even when pytest fails, retaining the primary failure and reporting any failed followup. A followup whose own prerequisite fails is not run.

The provisional tool join refuses a successful subprocess-backed leg if its captured results omit any scheduled
subprocess. A failed leg may stop before the end of its schedule; its failure remains visible
(`tests/governance/test_ownership_manifest.py::test_provisional_tools_preserve_shared_failures`). This check does not
authenticate the captured observations or establish a phase verdict.
An incomplete sequence ending in a successful follow-up is also refused, because the runner continues after that
follow-up and cannot produce the truncated result by a normal early stop.
The provisional join also checks the planned after-failure policy: only a leg that permits it can continue after
its primary failure, and no leg can continue after a failed follow-up.

Source guard findings retain the path inspected and are provisionally attributed using the captured census and
declared consumers. The guards also evaluate the captured census bytes and require their findings to agree with the
live source walk; a disagreement remains shared. Findings with missing or unowned paths remain shared. This
diagnostic attribution does not authenticate the observations or issue a phase verdict.

The Ruff check and format legs emit structured JSON and capture their subprocess outputs with the run nonce. Valid
diagnostics are provisionally mapped to their source consumers. Each original record is checked through finalizers
and sealed; the parent verifies its nonce, checkout root, contents and seal before and after retention. The shared
Ruff failures remain, and these local handoffs do not establish historical authenticity or a phase verdict.

The Python tool target list must match the ordered `src` and `tests` paths in the guarded source census. A
mismatch remains a shared validation failure; it does not stop the other planned tools from being attempted.
The runner also captures attempted Python command prefixes and compares them with that census, host-specific
coverage declarations, the plan, nonce and subprocess statuses. The command record binds the original Python
source digest and is checked through finalizers; its seal is verified before and after retention. After verifying
the child seal, the parent obtains a fresh guarded census and independently compares its digest and expected
Python command prefixes to the captured record. Failed containment or write-guard observations invalidate that
join. The child also seals its original ordered tool outcomes and subprocess statuses together; the parent
verifies the live and retained records against that seal. These observations remain provisional until the other
phase evidence is complete.

The captured pytest manifest is sealed from its original collection, execution, outcome, forbidden-record and
evidence-class values after finalization. The parent verifies the live and retained manifests against that seal;
a failed manifest finalizer cannot produce a successful handoff. This local binding does not issue a phase verdict.

The original oracle and bootstrap statuses and their per-file diagnostics are sealed together after both oracle
finalizers. The parent verifies the live and retained records against that seal, while a failed finalizer retains
its partial failure without claiming a successful oracle handoff.

Host facts and native case observations also receive separate seals after their finalizers. The native seal binds
case outcomes and source mappings to the captured native source bytes. The parent verifies each live and retained
record, and requires a passing write guard and containment observation for the native join. These bindings remain
provisional and do not themselves establish an authenticated phase verdict.

The parent retains the child output before cleaning the private run root. It publishes aggregate evidence only
after the handoffs and retention are verified, all child finalizers pass, the child succeeds, and cleanup succeeds.
It snapshots retained evidence file identities and contents before and after the handoff checks, and separately
checks both output streams. A change still present at the final comparison invalidates the handoff; the two
snapshots do not prove that no transient change occurred between them.
The parent carries the snapshots used by retained handoff verification across
temporary-root cleanup and compares them with the report immediately before
publication; a remaining difference withholds evidence and fails the check.
The parent also compares its selected Python interpreter's file identity and
digest before and after the child run, binds that observation to the run nonce in
the retained report, and checks it again before publication. These endpoint
observations do not establish continuous immutability or identify every tool.
On Linux and Windows, the parent also observes the held gate child's native
process identity and image before releasing a private nonce to its standard
input. It hashes the image file while the child is held, compares the Linux
file with the kernel's process-image link, and joins that sample to a later
file observation and the retained nonce-bound record. An unavailable or changed observation withholds trusted
publication while preserving the child's diagnostics. This observes the direct
child, not every descendant or a continuously measured executable; native
Darwin image observation remains unavailable and fails closed.
Unverified evidence text remains visible as a diagnostic. Phase lines are withheld until phase receipt
authentication is implemented.

Before the write-guard snapshot, a Linux checkout on a VirtualBox shared folder must have a private stored binding
whose guest root, mount, current source census and guest CPU, memory and swap allocations still match. The guest must
identify itself as Debian on VirtualBox. Ordinary Linux filesystems do not require this receipt. This check confirms
local currency only; the host-side nonce exchange and independently authenticated phase receipts remain necessary.

The host observation records whether the Linux release identifies itself as Debian. Provisional phase calculations
join that fact with the declared native lane: missing clean/live capabilities affect their consuming phase, while
earlier lanes need only their own base host qualifications. This identifies the current host's eligibility; it does
not supply a missing foreign-family receipt or establish a phase verdict.

The strict type-checking leg emits structured diagnostics over the same complete target set. The gate captures the
actual subprocess result and provisionally maps each valid diagnostic to its source consumers. Its exclusive record
is checked through the finalizers and sealed for verification before and after report retention. The aggregate type
failure remains shared until the complete phase evidence is authenticated; missing or inconsistent diagnostics
cannot qualify a phase.

Provisional phase calculations propagate observed prerequisite failures before adding the mandatory unverified
marker. This keeps the marker from inventing failures on dependent phases; it does not make any provisional
observation a passing receipt.

The provisional tool join assigns a failed binary-identity step to the consumers of its captured bootstrap and
identity sources, after checking their ownership and presence. Other unexplained tool failures remain shared, and
the resulting attribution does not itself authorize phase closure.

When the source guard and Python command record pass, the parent independently recalculates provisional phase
input identities from its guarded census and compares the census digest to the captured command record. It
repeats the identity comparison after retention. This checks input continuity, not the authenticity of all
phase outcomes or cross-host receipts. The parent also rejoins the sealed pytest, mutant-killer and native-source
observations to phase ownership and rejects a phase observation that omits an attributable collection, killer or native case
failure. A separate recheck rejoins sealed oracle outcomes and details to source consumers. These checks run before and
after retention when their supporting records and guards pass.
The coverage recheck reconstructs gaps from the sealed report and assigns them to source consumers. Each of these
parent joins binds its own census to the captured command digest before attributing failures.
The static recheck separately verifies Ruff, Ruff format and ty records against their subprocess statuses and
phase consumers. A failing static tool remains a shared failure even when its individual findings have owners.
The host recheck applies the sealed native host facts to each declared lane and rejects omitted host eligibility
failures; it does not create receipts for other native families.
The parent also reconstructs the tool schedule and compares the sealed outcomes with owned and shared phase
failures. It relies on the separately verified coverage join before excluding a coverage-report failure from that
tool comparison.
The parent checks that every failed shared finalizer remains on every phase, and recomputes source-policy and
missing-input failures from the bound census. These checks retain diagnostic evidence; they do not issue a receipt.
It also rechecks prerequisite propagation, excluding the provisional marker and finalizer failures added after the
phase calculation so that neither creates a false prerequisite failure.

The coverage report keeps the 100% branch floor and includes only the checkout's `src/agentctl` sources, so copied
trees under a run root are never reported as checkout code. `src/agentctl/check/coverage_hosts.toml` declares sources
whose native paths execute only on named host classes (`Windows`, `WSL`, `Linux`, `Darwin`). A host run omits only
the declared sources foreign to its family; Windows-only observers are therefore measured by the native Windows run,
and WSL-only legacy guest observers by no current lane until their ledger owner removes them. An unreadable or invalid
manifest, or a declared source missing from the census, is a validator failure, and the leg then omits nothing
(`tests/unit/test_coverage_hosts.py`).

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
(`tests/governance/test_gate_plugin.py::test_coverage_text_parent_joins_real_report_and_retained_evidence`). This local
handoff does not authenticate historical execution. A verified coverage-floor failure is provisionally assigned
to the affected source consumers; an unavailable, inconsistent or changed transcript keeps the failure shared.
When strict mutant ownership cannot be established, the child and parent may use a scoped provisional mapping only while retaining every unresolved ownership failure on its phase and checking present native killer identities against the captured sources. Mutant ownership may be observed with unrelated declared missing inputs only after validating every present census entry and the actual target and killer sources; missing bytes remain absent and are attributed separately. A source-ownership failure is provisionally localized only when an independently valid scoped census proves that its entire diagnostic consists of declared missing sources; the overall gate still fails, and ambiguous or unowned damage stays shared. Applicable Gate Integrity rows also join captured Python and native execution classes to the owning provisional phase; the parent independently recomputes the join. The finalizer record retains failures of pre-finalizer record integrity and invocation joins as shared damage, including transient failures that later reads cannot reproduce. The finalizer record also retains an initial oracle-details integrity failure even if the later check succeeds, and marks that failure shared across provisional phases. The parent also reruns shared static validators against the bound census, checks their findings against every provisional phase, and rejects a changed census before and after retention. Other shared failures and `unverified-run` remain, and these observations do not issue a verdict.

The current toolchain and style readiness steps refuse missing prepared tools without installing them. Native gate builds require a previously prepared matching private index and use offline Cabal arguments. Those checks do not establish that all native dependencies or backends were prepared successfully.

The current write guard snapshots the Git index path reported by Git and, when present, its bytes alongside refs and checkout files. A changed index fails the guard comparison; this observation does not itself establish a phase verdict.

The constructed receipt-join controls require each declared native family, matching logical input and prerequisite identities, lane-specific native identities, and the required test, mutant and coverage sets. These pure controls do not authenticate observations or issue receipts; the gate must still connect them to current native evidence.
Receipt values have a canonical, versioned encoding covering those fields and
host facts. Decoding refuses duplicate keys, duplicate evidence members,
malformed values and alternate byte encodings. A decoded value still requires
the current-run and retained-evidence authentication described above.
Record aggregation applies the same lane and prerequisite checks to decoded
bytes. An invalid record fails its own capability before dependency propagation,
while unrelated earlier capabilities keep their results. The aggregate is a
calculation over supplied records, not an authenticated gate verdict.
The parent also reconstructs a provisional receipt-input capture from the
retained census and sealed Python, native, mutant, host and coverage records,
and carries it across cleanup. A missing or inconsistent capture cannot establish
a receipt; durable authentication and publication remain open.
The parent scopes candidate test, mutant and coverage sets to each phase and
retains missing evidence as failures. These candidates keep the unverified-run
marker and are not phase receipts. Native requirements include cited cases and
mutation killers even when missing from the execution manifest; explicit case
citations determine their consumers when a native source is shared.
When the provisional capture is complete, the parent retains its scoped
`phase-candidates.json` record in the external check report. It first rechecks
the complete source census and verified report snapshot, then checks the expanded
snapshot before publication. The record is marked unverified and cannot close a phase.
An absent native observation can reach the provisional receipt-input capture
only when the parent revalidates its sealed absence, localized finalizer and
consumer scopes. Native consumers retain the absence; unrelated earlier
candidates remain provisional rather than losing their other evidence.

Mutant source migrations retain each original record and append an amendment in the same corpus file. The loader binds both record versions by their canonical content hashes, checks a decision naming the mutant, and preserves its target, operator, killers and reason. Further amendments form an ordered chain: each binds its immediate predecessor and changes the record. The ratchet protects the original and every amendment independently and retains them beside the mutant; the amended defect still requires its passing baseline and named kill.

The overall exit code reports checkout health. Phase closure consumes the gate's complete passing verdict for
that phase and its required lanes; it does not require an overall pass from unimplemented later phases.
Failure reports remain visible, and the final release phase requires the complete product result. No agent
may hand-select a convenient subset, rewrite a scope after seeing failures or ignore a shared prerequisite.

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
Missing future identifiers report obligations of their planned owner, while missing tests promised by a
closing phase fail that phase. Present tests are always collected and executed even when their owner is later.

## Preconditions

| Observation | Required outcome |
|---|---|
| Editable checkout and dev tools | The actual console entry, package sources and tool interpreter agree with the current checkout |
| Source and plan census | Every present artifact has one owner; all referenced closure inputs are explicit |
| Native host | OS/architecture and actual available capabilities are observed with the run nonce |
| Debian Linux | Exact Debian identity and phase-appropriate space/tools; native compilers are required only for introduced subjects that use them. WSL2 additionally has the required binding/resource receipt |
| Windows | Native execution and the selected private backend/build provenance; WSL observations cannot replace them |
| macOS | Native Darwin toolchain, multiplexer and filesystem evidence within its separate phase |
| Preparation | Missing runtime build dependencies receive typed readiness failures and remedies; the gate never opens installers or prompts |
| Resources | Registered short roots, valid ownership/permissions, bounded CPU/memory/storage plan and adequate remaining capacity |

A missing host capability remains unmet evidence for its native lane. A portable test of host detection can
pass without claiming the unavailable backend ran. Foreign-host requirements never make an earlier Linux
phase require Windows and macOS together; each phase declares at most one additional hardware family.

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
Tool/build/mutation deadlines are declared resource bounds and do not change assertions or evidence obligations.

## Lane Summary and Evidence Line

Each passing receipt binds the phase/capability contract, exact source and prerequisite scope digest, tool and
backend identities, observed native lane, run nonce, execution/coverage/mutant manifests and shared integrity
result. Date and diagnostic host metadata aid interpretation but do not establish that execution happened.
Receipts for a phase with Linux and one additional hardware family join only compatible input identities.
A new unrelated later artifact does not stale an earlier scope; a changed shared input does.

`PHASE` lines summarize complete phase/lane receipts in the plan grammar; aggregate `EVIDENCE` is emitted only for whole-product closure. An aggregate checkout
failure can coexist with a complete earlier phase receipt. An absent native run, stale source/backend identity,
missing assertion or failed common prerequisite can never produce a native passing receipt. Final release
closure requires the complete tree, zero remaining ledger work and all required qualified lane receipts.

## Cross-Lane Input Identity

Linux and foreign-native receipts agree on the shared logical source, policy and prerequisite-contract
digest. Each additionally binds its own platform/toolchain/build/backend sub-identities and native host facts.
Those native executable hashes normally differ; equality across operating systems is not a join condition.
Reject a changed shared source/policy or a mismatched artifact within its own declared native lane.

## Related

- [testing.md](testing.md) — evidence classes, independent observers and isolation.
- [code_standards.md](code_standards.md) — strict Python and Haskell source doctrine.
- [toolchain_bootstrap.md](toolchain_bootstrap.md) — preparation versus validation.
- [binary_build.md](binary_build.md) — native builds and immutable identities.
- [validation_runbook.md](../operations/validation_runbook.md) — native and WSL2 execution procedure.
- [development_plan_standards.md](../../DEVELOPMENT_PLAN/development_plan_standards.md) — phase closure and receipt grammar.
- [Governance and phase evidence](../../DEVELOPMENT_PLAN/phase-0-governance-and-phase-evidence.md) — gate/report migration owner.
