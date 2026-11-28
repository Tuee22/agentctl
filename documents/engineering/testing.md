# Testing

**Status**: Authoritative source
**Supersedes**: N/A
**Owning phase**: [Python discipline and gate integrity](../../DEVELOPMENT_PLAN/phase-1-python-discipline-and-gate-integrity.md)

> **Purpose**: Define how tests meet the plan standards' admissibility, kill and adequacy clauses: evidence classes, isolation, observers, oracles, mutants and native controls.

Whether a test is admissible closure evidence is
[T.E](../../DEVELOPMENT_PLAN/development_plan_standards.md#te-unspoofable-test), what counts as a kill is
[T.K](../../DEVELOPMENT_PLAN/development_plan_standards.md#tk-kill) and when a phase's tests and mutants are adequate
is [T.M](../../DEVELOPMENT_PLAN/development_plan_standards.md#tm-adequacy); this page states how tests meet them. The
[quality gate](quality_gate.md) executes them through one no-argument command, and the plan owns closure and
migration status. No commit, human attestation, answered dialog, manual fixture capture or clean worktree
substitutes for execution. Preparation and optional fixture capture remain outside ordinary check execution.

## Evidence Classes

| Class | Evidence produced | Limit |
|---|---|---|
| `value` | Independent expected values compared with a pure subject over declared finite inputs | Does not establish behavior outside its supported domain |
| `real` | An actual native tool or public application in a verified owned scope, with observed executable identity | Does not establish another release, host or backend |
| `observer` | An independent receiver/process/filesystem witness records actual operations and their absence beside a live positive control | Does not establish an unobserved native behavior |
| `owed` | Native confirmation that a lower phase cannot observe, assigned to a later phase whose lane includes that family or half ([T.X](../../DEVELOPMENT_PLAN/development_plan_standards.md#tx-terms)); a host-declared kill target records `owed:<family>` on another family's run ([T.K](../../DEVELOPMENT_PLAN/development_plan_standards.md#tk-kill) K6) | Is not a passing test or a replacement for native execution |

Each collected case declares its evidence class. An available foreign-host detection branch can establish
capability absence, but supplies no native behavior receipt. All present tests run; an absent planned case is a
planned absence of the citing phase and never enters another phase
([T.F](../../DEVELOPMENT_PLAN/development_plan_standards.md#tf-shared-and-owned-failures), V3). A phase's verdict is
[T.V](../../DEVELOPMENT_PLAN/development_plan_standards.md#tv-verdict) over its own and prerequisite executions,
coverage and mutant outcomes, and it never requires a later phase to pass.

Skipped, deselected, expected-failure, zero-assert, stale or subject-generated expectations establish no claim
(T.E E1 and E3; [T.S](../../DEVELOPMENT_PLAN/development_plan_standards.md#ts-defended-spoofs) S3 and S6).
Documented-only screens are not live captures. Passing exit status alone is insufficient when a traceback or
incomplete report could produce the same status convention. Limits:
[T.C](../../DEVELOPMENT_PLAN/development_plan_standards.md#tc-ceiling) C5.

## Isolation

Real tools receive private homes, XDG roots, registries, caches and unique run identities. The subject uses its
production path, and there is no production test branch, mocked implementation or monkeypatched calculation. A
test controls only environment variables, the working directory and values passed through the subject's declared
parameters, and owned fake agents are explicit boundary controls
([T.E](../../DEVELOPMENT_PLAN/development_plan_standards.md#te-unspoofable-test) E4). E4 is judged at stage 2
([T.W](../../DEVELOPMENT_PLAN/development_plan_standards.md#tw-staged-enforcement)), and per-file caps freeze the
known substitutions, each a shape of the
[deletion ledger](../../DEVELOPMENT_PLAN/legacy_tracking_for_deletion.md).

- tmux uses a short, private socket directory, an empty owned configuration and no inherited mux routing.
  A server is ended only after its endpoint is verified inside a registered owned root.
- psmux receives an absolute private `PSMUX_DATA_DIR`, controlled configuration and warm-server disabling for
  tests. Teardown identifies actual owned processes and endpoints; it never kills an executable image name.
- Native build roots carry a full descendant-path budget and run registration even outside the main temporary
  directory. Native children and file handles finish before scanning/removing their files. Missing build files
  during an undisciplined broad walk are not evidence of a live mux server.
- Windows fixture markers use strict finite reads with deterministic handle closure and generation/acknowledgment
  synchronization. A sleep or a lazy file handle cannot be the synchronization oracle. Sharing violations are
  diagnosed and fixed without suppressing the test or weakening the screen comparison.
- Agent logged-out controls use empty private configuration and remove provider credentials. Live acceptance
  runs on the `linux-live` half with logged-in agents
  ([T.X](../../DEVELOPMENT_PLAN/development_plan_standards.md#tx-terms)), launches only in the fixed state-owned
  folder with updating disabled, sends no input and answers no dialogs.
- Test bodies run no package manager, sudo, login or real installer. Cold, partial and failing installations are
  proven against installer models, and agentctl's own Windows provisioning runs once per run in a gate leg of
  its owner, never per mutation (D-180).
- Code is never restructured only to change coverage measurement; a host-state guard stays only where real state
  on its family reaches it ([T.S](../../DEVELOPMENT_PLAN/development_plan_standards.md#ts-defended-spoofs) S11).

A Windows workstation supplies the Linux halves only through the dedicated Debian VirtualBox procedure in the
[validation runbook](../operations/validation_runbook.md). The live source bind mount is shared; Linux dependency
stores, sockets, homes and build output remain on dedicated guest storage. Windows and guest checks do not
write the shared checkout concurrently. Guest evidence stays Linux evidence
([T.E](../../DEVELOPMENT_PLAN/development_plan_standards.md#te-unspoofable-test) E6), and agent credentials reach
the guest only through the runbook's
[read-only shares or their 0600 copy fallback](../operations/validation_runbook.md#agent-credentials-in-the-vm).

## Observers and Nonces

Every run and owned child carries fresh identity. Receipts include canonical source scope, actual executable
path/hash, native process creation identity where relevant, and their positive observation controls. PID alone
is insufficient when reuse is possible. A timeout observes/re-polls the same process or handle before deciding
whether execution ended; absence of output or an old lock file is not a liveness oracle.

For subprocesses, independent witnesses inspect actual argv, working directory, environment selection,
exit status and surviving owned descendants. For terminal submission, the independent receiver records exact
bytes and count. A negative no-send control must demonstrate that the receiver was alive and capable of
receiving a safe positive submission.

## Oracles

Oracles are independently derived from the user requirements and verified external tool facts. Their exact
inputs, expectations, provenance and amendment relationships remain explicit. An expectation is a literal in the
test or a row of an oracle that the cited Gate Integrity row names and the test loads, judged at stage 2
([T.E](../../DEVELOPMENT_PLAN/development_plan_standards.md#te-unspoofable-test) E3). Gate configuration, source
rules and native boundaries have two-sided controls. A supported-input domain records its finite bounds,
accepted/refused cases and assumptions rather than claiming all annotated Python values are total.

The Python migration adds executable checks for structural narrowing, immutable owned values, single assignment,
closed construction, total pure kernels, explicit effects and honest decoder/native declarations. Native
type tests, mutation and broad object annotations are removed from migrated code rather than hidden behind
renamed helpers, reflection or a blanket shell classification. Existing local typed outcomes remain the
success/failure vocabulary. Tests and gate implementation are in the same migration census.

## Mutants

Every declared mutation has a source target, exact change, independent killer and named failure reason. What
counts as a kill, and the stage at which each kill condition applies, is
[T.K](../../DEVELOPMENT_PLAN/development_plan_standards.md#tk-kill); the ownership and adequacy of a phase's mutants
are [T.M](../../DEVELOPMENT_PLAN/development_plan_standards.md#tm-adequacy). Corpus cases retain complete result
records and restore scratch targets. Named killer execution inside the mutation harness is part of the registered
corpus, not an alternative phase-closing runner. The runner observes individual baseline and eligible mutation
outcomes, including failures from later named killers. The pytest observer writes their statuses to a separate run
artifact, which the parent retains with the report
(`tests/governance/test_gate_plugin.py::test_killer_outcomes_are_retained_from_real_execution`,
`tests/integration/test_runtime_boundaries.py::test_gate_reports_are_retained_outside_checkout`). The parent joins
that artifact to the captured corpus and pytest outcomes and checks its original bytes after follow-up commands and
finalizers. The parent checks a child-issued digest against both the live report and its retained copy.
Provisional phase observations retain individual failed killers under their declared mutant owner while
preserving the aggregate failure. A kill failure is owned by the mutant's owner
([T.F](../../DEVELOPMENT_PLAN/development_plan_standards.md#tf-shared-and-owned-failures)), and a failed baseline is
never a kill (T.K K2).

New discipline controls include accepting twins and mutations demonstrating that each banned spelling or
escape path changes the expected verdict. Existing oracle rows and committed mutations remain ratcheted
against unchanged HEAD: a protected row changes only through a
[T.G](../../DEVELOPMENT_PLAN/development_plan_standards.md#tg-governed-changes) record, and an amendment does not
erase the expectation it corrects. Rows added since the last user commit have current-run protection only
([T.C](../../DEVELOPMENT_PLAN/development_plan_standards.md#tc-ceiling) C2).

## Gate Legs and What Each Proves

Static tools measure the complete current file census and attribute diagnostics to stable owners. Type errors
in a shared prerequisite invalidate its consumers. Native builds prove the actual compiled input identity;
unit/value tests establish declared functions on independent examples; real backend tests establish only their
observed artifact and host. Coverage and collection manifests are exact per declared subject, with no hidden
legacy roots. Exactly the failures that
[T.F](../../DEVELOPMENT_PLAN/development_plan_standards.md#tf-shared-and-owned-failures) lists are shared and fail
every phase; every other failure is owned by its locus.

Haskell and C sources close by named-reason kills plus native accepting and refusing twins on their own family
([T.X](../../DEVELOPMENT_PLAN/development_plan_standards.md#tx-terms)), while the coverage floor applies to Python
sources (R20.2).

A deliberately broken later capability leaves an unrelated earlier phase verdict unchanged, while a stale nonce,
omitted execution or changed common prerequisite invalidates the corresponding consumer. These are required gate
controls, not assumptions inferred from a readable report; the spoof matrix and live-plan independence controls of
`tests/governance/test_phase_verdicts.py` are deliverables of
[Governance and phase evidence](../../DEVELOPMENT_PLAN/phase-0-governance-and-phase-evidence.md).

## Unsupported Paths

A half that no verified run has supplied prints `absent`, so the phases that require it are at best
`awaiting:<half>` ([T.V](../../DEVELOPMENT_PLAN/development_plan_standards.md#tv-verdict)), never an emulated pass.
A Linux guest cannot establish Win32 process, filesystem, console or psmux behavior, and Linux cannot establish
Darwin SDK or Keychain behavior (T.E E6). Documented screen classes cannot claim live confirmation, and tests do not spend
provider quota to manufacture failures.
A short native stress test supports its measured workload, not arbitrary messages or universal bug freedom.

## Native multiplexer ownership

Backend qualification identifies both the selected client executable and the actual running server. A new
client does not upgrade an old server. Tests retain exact server-instance, session/pane generation and process
creation identities, including duplicate pane IDs across servers, disappearing explicit targets, reconnect,
client-only termination and continued agent execution. Missing explicit targets must fail rather than fall
back to an active pane. Adopted sessions never become owned because they appear in an agentctl registry.

Windows memory qualification includes independently capped vulnerable controls, synthetic blocked-output
clients, real-server stalls beyond the server timeout, repeated resume cycles, multiple clients, mixed
frame/no-change/directive workloads, latest-screen delivery, control ordering and clipboard/bell preservation.
It measures private committed memory rather than resident RAM. Clipboard and bell one-shots are observed only
through synthetic test clients; no test writes the OS clipboard (D-172).

## Auth probes and installed-agent controls

The application never installs an agent CLI or logs it in; a validation host receives the CLIs through
agent-performed [one-time setup](../operations/validation_runbook.md#one-time-host-setup). Fresh launch checks only
the requested agent and fails before costly backend preparation when that executable is absent. Session listing,
logs and reattachment do not demand unrelated agent executables or fresh authentication. Authentication status is
observed without a login or any response to a trust/approval dialog. Private logged-out controls prove credential
isolation rather than guessing it.

## Terminal closure and exit status

The pane trampoline reports a real child status independently of backend placeholder dead-status fields.
Tests cover immediate exit, retained/dead panes, binary UTF-8 output, inherited streams, closed parent input,
process timeouts and native shutdown. Foreground-client failure never implicitly ends the supervised session.
Supervisor stop/unwatch leaves managed and adopted pane identities intact.

## Launch callers and child accounting

The application receives separate argv/cwd/environment fields and applies no shell parsing to user text.
Hostile punctuation, empty strings, separators, Unicode and spaces survive the public wrapper, Haskell
application, mux trampoline and receiver. Exact session/pane targets never affect prefix siblings.
Every child and registered external root has a bounded lifecycle and independent teardown record; cleanup
failure is retained alongside the original failure and cannot turn an incomplete run into a pass.

## Related

- [quality_gate.md](quality_gate.md) — gate mechanics and phase verdicts.
- [development_plan_standards.md § T](../../DEVELOPMENT_PLAN/development_plan_standards.md#t-unspoofable-evidence-and-phase-verdicts) — admissible tests, kills, adequacy and their limits.
- [code_standards.md](code_standards.md) — Python doctrine and native boundary rules.
- [validation_runbook.md](../operations/validation_runbook.md) — VirtualBox, native Windows and Darwin runs.
- [toolchain_bootstrap.md](toolchain_bootstrap.md) — installation versus ordinary testing.
- [multiplexer_adapter.md](../architecture/multiplexer_adapter.md) — backend identity and isolation.
- [files_and_state.md](../reference/files_and_state.md) — owned roots and retained receipts.
- [Python discipline and gate integrity](../../DEVELOPMENT_PLAN/phase-1-python-discipline-and-gate-integrity.md) — migration and controls.
