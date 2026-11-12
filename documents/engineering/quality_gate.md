# Quality Gate

**Status**: Authoritative source
**Supersedes**: N/A
**Owning phase**: [Governance and phase evidence](../../DEVELOPMENT_PLAN/phase-0-governance-and-phase-evidence.md)

> **Purpose**: Specify complete no-argument gate execution, independently attributable phase/lane verdicts, shared integrity requirements and reproducible evidence.

`agentctl check` is the sole closure gate. It runs from the editable checkout with development dependencies
installed. Focused tools assist diagnosis but establish no phase closure. This page defines the required gate
contract; current command output must demonstrate its implementation before its new evidence can be used.
The [plan standards](../../DEVELOPMENT_PLAN/development_plan_standards.md) own status and receipt grammar.

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
