# Files and State

**Status**: Authoritative source
**Supersedes**: N/A
**Owning phase**: [Haskell runtime and platform policy](../../DEVELOPMENT_PLAN/phase-3-haskell-runtime-and-platform-policy.md)

> **Purpose**: Define owned directories, immutable executable publications, backend registries, state lifetimes and retained validation receipts.

This is the required state contract. Its schema/oracle and native controls establish accepted formats; an old
file is not silently admitted merely because it uses a familiar filename. All external data is parsed at its
boundary into bounded typed values.

## Directories

Python establishes the application roots needed for bootstrap and passes them through the versioned handoff.
Haskell derives its runtime-owned subdirectories and never duplicates a per-user-root selection rule.

| Root | Contents | Override | Linux/macOS default | Windows default |
|---|---|---|---|---|
| `cache` | Source, build trees, private dependency stores and style tools | `XDG_CACHE_HOME` | `~/.cache/agentctl` | `%LOCALAPPDATA%/agentctl/cache` |
| `data` | Immutable application/backend publications and their receipts | `XDG_DATA_HOME` | `~/.local/share/agentctl` | `%LOCALAPPDATA%/agentctl/data` |
| `state` | Backend registry, launch/adoption/watch state, logs, locks and validation reports | `XDG_STATE_HOME` | `~/.local/state/agentctl` | `%LOCALAPPDATA%/agentctl/state` |

An absolute override selects its `agentctl` child on every OS. Relative overrides are refused or handled by the
explicit root policy rather than used as arbitrary deletion/build locations. Secrets remain in user agent
configuration or short-lived private launch specs, never executable arguments or logs.

## Layout

```text
<cache>/
  toolchain-paths.toml          verified absolute application compiler/tool paths
  build/<application-digest>/  locked application build storage
  cabal/                       private Cabal configuration, package index and store
  tools/<style-digest>/        pinned formatter/linter publications
  runtime/rust/                Haskell-owned RUSTUP_HOME and CARGO_HOME
  runtime/source/<digest>/     verified source, patches and lockfile inventories
  runtime/build/<digest>/      registered native backend build storage
<data>/
  bin/<application-digest>/    immutable source-built Haskell application
  backends/psmux/<digest>/     immutable build-verified native psmux candidate and build receipt
  backend-profiles/            separate qualification receipts keyed to candidate hash/profile
  locks/                      application/backend publication locks
<state>/
  psmux/                      stable private production backend registry
  launch/                     private one-use specs and Windows child-status records
  adopted.json                explicit external-pane registrations
  watch.json                  revisioned watch intent
  supervisor.jsonl            append-only decisions and outcomes
  locks/                      check, supervisor, watch and runtime preparation locks
  live-acceptance/             fixed real-agent validation folder
  validation/                 retained reports, phase receipts and resource manifests
```

Backend registry identity is stable across executable upgrades; a build digest does not silently create a
new invisible set of sessions. Its entries identify the actual server and capabilities. System psmux keeps
its separate normal registry and configuration. A private backend publication does not replace system aliases
or modify an existing external installation.

## Launch Specs

The pane trampoline receives an absolute spec path, never the caller's complete arguments/environment on the
mux command line. Each unpredictable launch reservation contains a private `spec.json` and a matching status
path. The spec carries literal argv, canonical cwd, the intended environment and the owned status location.
The trampoline validates bytes, schema, ownership and privacy before deleting its one-use input and starting
the agent. Linux/macOS replace the pane process; Windows waits for its child and atomically reports its actual
exit status. Status remains independent of placeholder mux dead-status fields.

POSIX paths use actual owner/mode/no-follow checks; Windows uses real token-owner SID/DACL/reparse-point
observations. Emulated POSIX modes never substitute for native Windows privacy. Native reads have explicit
size bounds. A failed start removes only its exact owned reservation; unexpected child files prevent broad
cleanup and produce an observable diagnostic.

## Adopted-Pane Registry

Adoption records an explicitly selected endpoint/registry, server instance, session/pane identity, process
creation identity and known agent. Backend compatibility is distinct from ownership. A PID, pane ID or session
name alone is insufficient after restart or reuse. Every use revalidates the complete identity before capture
or submission; a missing target never resolves to the active pane.

Managed-session metadata remains tied to the session lifecycle. Adoption creates no authority to stop an
external session. Forgetting an adopted entry removes only that record. Legacy registry shapes are migrated
through an explicit bounded schema path or refused with a remedy; malformed, duplicate, foreign, linked or
unsafe files are not rewritten as if successfully parsed. State publication uses a private sibling followed
by atomic replacement under its native lock.

## Watch Set

Watch intent is revisioned globally and per target. Effective changes advance the relevant revisions, while
repeated identical commands preserve bytes. A pause/resume between polls is observable even if the final paused
value matches the prior one. A paused target yields no capture or recovery action; start/resume establishes a
baseline so existing error text cannot become a newly injected retry.

Watch state binds to validated identities/capabilities. Pause/unwatch can disable stale entries. An unrelated
target's update cannot reset a different incident or permit duplicate delivery. State locks cover reload,
transition and publication, and recovery rechecks intent at the delivery boundary.

## Decision Log

The supervisor holds its native lock while appending bounded typed JSONL records. Records identify UTC time,
supervisor run, target, agent and kind: observation, decision, attempt, result or notification. Observations
record classification/fingerprint and machine state, not captured terminal contents or credentials.

Decisions are durable before effects. Submission outcomes distinguish sent, rejected/aborted, failed and any
uncertain delivery state admitted by the backend contract; uncertainty never automatically repeats an action.
A successful send is not recovery until the declared acknowledgment observation arrives. The reader accepts
only a complete valid prefix while a live writer owns the lock; after release, an incomplete suffix is
corruption. Writers validate existing history and actual opened-file ownership before append.

## Locks

Interprocess exclusion uses native kernel locks, never mere PID-file presence. Held lock files are retained
and updated in place rather than atomically replaced, because replacement breaks inode/handle exclusion.
Diagnostic PID text grants no authority by itself. Process creation identity prevents PID reuse from naming
a different owner.

| Scope | Purpose |
|---|---|
| Check | Prevent concurrent gate mutation/resource accounting for one checkout/user scope |
| Application/backend digest build | Serialize preparation and recheck accepted publication after waiting |
| Publication | Atomically admit one qualified immutable directory |
| Supervisor | Permit one decision/delivery loop for its declared scope |
| Watch intent | Serialize changes and pre-delivery intent validation |

Each wait is bounded and reports contention separately from native locking failure. Lock release occurs on
normal, failed and interrupted owned execution without deleting another process's active lock.

## Live-Test Folder

Real agents start only in `<state>/live-acceptance/` with updating disabled. Ordinary live checks send no input
and answer no dialog. In a dedicated WSL2 environment, authorized credential copies remain private there while
the host originals remain intact. Only the dedicated environment's agent configuration can be prepared for
those tests; no user's existing Linux environment is modified.

## Check Run Directory

A check has a fresh nonce, main temporary root and complete registry of any short external build/socket roots.
Every root records canonical path, owner and intended lifetime. Bytecode, private tool homes, coverage data,
pytest/native manifests, observer records and private backend endpoints remain outside the checkout.

Retained phase/lane receipts and original logs are published to `<state>/validation/` before temporary cleanup.
Their identities include source/prerequisite scope, tool/backend hashes, host observations and execution
manifests. Reports never contain copied credentials or full terminal captures by default. A failed finalizer
is appended to the original failure rather than erasing it.

Cleanup begins only after owned children and strict file handles have ended. It verifies every resolved target
is inside the registered allowed roots, never kills by image name, and leaves an explicit retained failure if
resources cannot be reaped. A stale directory alone does not prove a live process, and a missing build file
alone does not prove a server leak. Future runs never reuse test verdicts or mutant kills from old roots.

WSL2 uses ext4-owned build/dependency/state storage with a bind-mounted shared Windows source checkout. Its
binding/resource receipt is created before the write-guard and transient source sentinels are removed before
validation. [Validation runbook](../operations/validation_runbook.md) owns the exact observed evidence.

## Related

- [installation.md](../operations/installation.md) — installation and safe removal.
- [cli_reference.md](cli_reference.md) — public state-management commands.
- [launch_contract.md](../architecture/launch_contract.md) — spec and trampoline authority.
- [sessions_and_ownership.md](../architecture/sessions_and_ownership.md) — managed/adopted identities.
- [supervisor_contract.md](../architecture/supervisor_contract.md) — intent and delivery semantics.
- [binary_build.md](../engineering/binary_build.md) — immutable publications and source identities.
- [quality_gate.md](../engineering/quality_gate.md) — phase receipts and integrity.
- [validation_runbook.md](../operations/validation_runbook.md) — shared source and native lane preparation.
- [Session management and adoption](../../DEVELOPMENT_PLAN/phase-6-session-management-and-adoption.md) — state ownership.
