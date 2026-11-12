# Testing

**Status**: Authoritative source
**Supersedes**: N/A
**Owning phase**: [Python discipline and gate integrity](../../DEVELOPMENT_PLAN/phase-1-python-discipline-and-gate-integrity.md)

> **Purpose**: Define independent behavioral evidence, complete phase/lane attribution, strict source migration, isolated native resources and honest limits.

This page states the required evidence contract. The [quality gate](quality_gate.md) executes it through one
no-argument command; the plan owns closure and migration status. No commit, human attestation, answered dialog,
manual fixture capture or clean worktree substitutes for execution. Preparation and optional fixture capture
remain outside ordinary check execution.

## Evidence Classes

| Class | Evidence produced | Limit |
|---|---|---|
| `value` | Independent expected values compared with a pure subject over declared finite inputs | Does not establish behavior outside its supported domain |
| `real` | An actual native tool or public application in a verified owned scope, with observed executable identity | Does not establish another release, host or backend |
| `observer` | An independent receiver/process/filesystem witness records actual operations and their absence beside a live positive control | Does not establish an unobserved native behavior |
| `owed` | A declared native obligation assigned to its hardware acceptance owner | Is not a passing test or a replacement for native execution |

Each collected case declares its evidence class. An available foreign-host detection branch can establish
capability absence, but supplies no native behavior receipt. All present tests run; absent future cases remain
visible obligations of their owner. The complete phase verdict joins its owned and prerequisite executions,
coverage, mutant outcomes and common integrity receipt without requiring later-phase success.

Skipped, deselected, expected-failure, zero-assert, stale or subject-generated expectations establish no claim.
Documented-only screens are not live captures. Passing exit status alone is insufficient when a traceback or
incomplete report could produce the same status convention. Finite observations cannot prove universal purity,
termination, callback ownership or soundness of every native typing declaration.

## Isolation

Real tools receive private homes, XDG roots, registries, caches and unique run identities. The subject uses its
production path; the harness controls only supported external inputs. There is no production test branch,
mocked implementation or monkeypatched calculation. Environment construction, current-directory changes and
owned fake agents are explicit boundary controls.

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
  launches only in the fixed state-owned folder with updating disabled, sends no input and answers no dialogs.
- Test bodies run no package manager, sudo, login or real installer. Cold installation is a separately observed
  preparation action in a disposable environment, followed by the same complete gate.

A Windows workstation may supply Linux runs only through the dedicated WSL2 procedure in the
[validation runbook](../operations/validation_runbook.md). The source bind mount is shared; Linux dependency
stores, sockets, homes and build output remain in the dedicated distribution. Windows and Linux checks do not
write the shared checkout concurrently. WSL evidence stays Linux evidence.

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
inputs, expectations, provenance and amendment relationships remain explicit. Gate configuration, source
rules and native boundaries have two-sided controls. A supported-input domain records its finite bounds,
accepted/refused cases and assumptions rather than claiming all annotated Python values are total.

The Python migration adds executable checks for structural narrowing, immutable owned values, single assignment,
closed construction, total pure kernels, explicit effects and honest decoder/native declarations. Native
type tests, mutation and broad object annotations are removed from migrated code rather than hidden behind
renamed helpers, reflection or a blanket shell classification. Existing local typed outcomes remain the
success/failure vocabulary. Tests and gate implementation are in the same migration census.

## Mutants

Every declared mutation has a source target, exact change, independent killer and named failure reason.
Compilation refusal, timeout, failed baseline or an unrelated teardown error does not count as the intended
runtime kill. Corpus cases retain complete result records and restore scratch targets. Named killer execution
inside the mutation harness is part of the registered corpus, not an alternative phase-closing runner.

New discipline controls include accepting twins and mutations demonstrating that each banned spelling or
escape path changes the expected verdict. Existing oracle rows and committed mutations remain ratcheted
against unchanged HEAD; amendments do not erase the expectation they correct. Uncommitted data has current-run
protection but no claimed historical independence.

## Gate Legs and What Each Proves

Static tools measure the complete current file census and attribute diagnostics to stable owners. Type errors
in a shared prerequisite invalidate its consumers. Native builds prove the actual compiled input identity;
unit/value tests establish declared functions on independent examples; real backend tests establish only their
observed artifact and host. Coverage and collection manifests are exact per declared subject, with no hidden
legacy roots. Shared run-integrity failures invalidate every dependent phase receipt.

A deliberately broken later capability must leave an unrelated earlier complete phase verdict intact, while
a stale nonce, omitted execution or changed common prerequisite invalidates the corresponding consumer.
These are required gate controls, not assumptions inferred from a readable report.

## Unsupported Paths

An unavailable native lane is unmet work rather than an emulated pass. WSL cannot establish Win32 process,
filesystem, console or psmux behavior; Linux cannot establish Darwin SDK/Keychain behavior. Documented screen
classes cannot claim live confirmation, and tests do not spend provider quota to manufacture failures.
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
It measures private committed memory rather than resident RAM. Tests using the real clipboard run in a
separate disposable Windows user/session; ordinary checks use an independent native test sink.

## Auth probes and installed-agent controls

Agent CLIs remain user-installed. Fresh launch checks only the requested agent and fails before costly backend
preparation when that executable is absent. Session listing, logs and reattachment do not demand unrelated
agent executables or fresh authentication. Authentication status is observed without a login or any response
to a trust/approval dialog. Private logged-out controls prove credential isolation rather than guessing it.

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

- [quality_gate.md](quality_gate.md) — complete execution and independent phase/lane verdicts.
- [code_standards.md](code_standards.md) — Python doctrine and native boundary rules.
- [validation_runbook.md](../operations/validation_runbook.md) — prepared native and WSL2 lanes.
- [toolchain_bootstrap.md](toolchain_bootstrap.md) — installation versus ordinary testing.
- [multiplexer_adapter.md](../architecture/multiplexer_adapter.md) — backend identity and isolation.
- [files_and_state.md](../reference/files_and_state.md) — owned roots and retained receipts.
- [Python discipline and gate integrity](../../DEVELOPMENT_PLAN/phase-1-python-discipline-and-gate-integrity.md) — migration and controls.
