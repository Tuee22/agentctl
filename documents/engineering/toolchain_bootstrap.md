# Toolchain Bootstrap

**Status**: Authoritative source
**Supersedes**: N/A
**Owning phase**: [Haskell runtime and platform policy](../../DEVELOPMENT_PLAN/phase-3-haskell-runtime-and-platform-policy.md)

> **Purpose**: Specify the minimal Python build bootstrap and Haskell-owned runtime dependencies, their idempotence, consent and preparation evidence.

This page defines the required contract. Owning phases join actual source, native controls and receipts;
a cached executable does not establish qualification. [The boundary contract](../architecture/python_haskell_boundary.md)
owns the Python/Haskell division.

## The Provisioning Plan

Python obtains the Haskell application before transferring commands. It owns only necessary bootstrap host
facts and directories, GHC prerequisites, verified ghcup acquisition, pinned GHC and cabal, the digest-keyed
Haskell build and handoff. It contains no Rust, psmux, tmux, agent-installation or runtime-session workflow.
Pipx installation requires Python and Python package dependencies; native compilation happens on first use,
not inside the Python package build backend.

After handoff, Haskell owns runtime platform policy, dependency facts, pure installation plans, consent,
source acquisition, tool execution, qualification and publication. It validates Debian itself on Linux.
The Windows path builds native psmux from pinned source. Haskell HTTPS and archive adapters avoid assuming
Git, curl or an extraction CLI; any genuinely required external tool has an owned provisioning contract.
Both layers use immutable observed facts, pure typed plans and thin effect interpreters. Anticipated
failures carry named outcomes; failed actions retain the last accepted artifact and never loop installers.

Installation consent crosses the handoff separately from raw agent arguments. Python neither parses nor
duplicates the runtime plan. Supplied directories and consent belong to the versioned handoff protocol.

## OS Prerequisites

| Stage | Owner | Required behavior |
|---|---|---|
| Haskell application build | Python | Supply only prerequisites required before Haskell can run, using declared platform policy and exact GHC/cabal paths |
| Debian runtime | Haskell | Require exact Debian identity; reuse suitable tmux or install it through the qualified APT transaction and verify the result |
| Windows runtime | Haskell | Probe native Rust/Cargo, MSVC linker/libraries, Windows SDK and resource compiler; provide supported missing prerequisites before building psmux |
| macOS runtime | Haskell | Add native macOS preparation in its own phase without making Linux or Windows validation depend on a Mac |
| Agent CLIs | Haskell | Check the requested user-installed claude or codex; report missing, non-native or unauthenticated tools; never install or log them in |

Debian admission requires `ID=debian` in `os-release`, not merely APT or an `ID_LIKE` family. Unsupported Linux
distributions fail before runtime mutation. Suitable tmux is reused; otherwise Haskell refreshes package
metadata and installs it using the qualified APT plan. An inadequate repository candidate produces a typed
remedy rather than repeated installation, added repositories or a silently substituted platform.

Windows qualification probes actual compile/link/resource capability, not only PATH or installer metadata.
Existing qualified MSVC/SDK components can be reused without changing defaults. Missing components use the
declared official installer and exact plan. Missing elevation, installer contention and restart-required
outcomes remain unmet prerequisites. Automation opens no approval dialog, forces no application closed and
never restarts the host.

## Consent

Plans distinguish observation, user-directory downloads/builds and system package installation. A privileged
mutation requires the repository's explicit consent policy and the concrete action list. Noninteractive
commands require supplied consent and already available privilege; privilege alone grants no consent.
Consent never authorizes changes to profiles, user toolchain defaults, credentials or unrelated installations.

`agentctl check` never prompts. Its prerequisite observations report missing preparation with a remedy.
Tests run no actual package managers, sudo or Microsoft installers. Cold-provisioning acceptance prepares an
owned disposable host through the public application outside the test subprocess tree, then runs the gate
against that host and its independently observed preparation receipt. Constructed controls separately prove
planner refusals and interpreter action order.

## ghcup

Python reuses responding ghcup at the supported floor. Old or unanswering installations produce an upgrade
instruction rather than replacement. With no reusable ghcup, it downloads the declared platform asset,
checks its advertised length when available and pinned SHA-256, and publishes from private staging.
It runs no shell bootstrap script and edits no profile. Pins have their data home in the packaged manifest;
[external tool facts](../reference/external_tool_facts.md) records the official selection facts.

## GHC and cabal

Python installs missing pinned GHC and cabal without changing the user's default selections. It resolves and
verifies absolute executable paths before atomically recording the pair. A warm application digest hit needs
no toolchain probe or build; a warm toolchain ensure performs no package-manager or network work when its
recorded pins qualify. [Binary build](binary_build.md) owns source identity and publication.

## Windows Rust and psmux

Haskell owns private `RUSTUP_HOME` and `CARGO_HOME` roots and selects an exact native Windows MSVC toolchain.
It preserves PATH, profiles and the user's rustup default. The pinned official initializer is verified before
use. MSVC is resolved first, preventing rustup from offering an unattended product installation.

The initial upstream source candidate is `063ca7026eb2b7b91a74d3f858bdec3dfc841dbb`. Its archive digest, complete
ordered patches, workspace/lockfile inputs, compiler/target, linker/SDK identities and build settings define
its source-build identity. Qualification is required; a printed package version such as `3.4.0` is not enough.
Archive extraction refuses traversal, unexpected links and incomplete inventories. Build provenance cannot
come from an unrelated enclosing Git repository.

The locked build uses short, registered app-owned storage. Haskell verifies staged candidate build identity, records executable hashes and atomically publishes immutable candidate directories. Build publication is complete without later runtime-profile qualification. A separate profile receipt keyed to those exact bytes supplies qualified capabilities before session/recovery use. Interprocess locking and a second
cache check let concurrent callers reuse the winner. Failed acquisition, build or qualification never replaces
a good artifact or changes a running server. The [multiplexer adapter](../architecture/multiplexer_adapter.md)
owns runtime backend selection, registry isolation and server compatibility.

## The Clean-Lane Recipe

Linux clean acceptance begins from pipx/Python in dedicated Debian, observes initial dependency absence,
prepares through the public application and runs `agentctl check`. Windows cold acceptance uses an owned native
Windows environment with declared installer privilege. Receipts identify actual actions, before/after facts,
versions and executable hashes; they are not manually asserted pristine-host certificates.

A Windows workstation can supply Linux evidence through a dedicated, resource-budgeted WSL2 Debian instance
and a verified bind mount of the same checkout. The [validation runbook](../operations/validation_runbook.md)
owns that procedure. WSL2 cannot supply native Windows or macOS evidence.

## What Each Step Proves

| Evidence | Establishes | Does not establish |
|---|---|---|
| Pure plan cases | Exact actions and refusals for declared facts | Installation on another host |
| Owned native probes | Recorded compile/link/run capability and identity | Every future environment or release |
| Cold receipt | Observed public preparation within its supported scope | Unobserved host cleanliness |
| Warm/concurrent controls | No redundant actions and one accepted publish | Races absent from the controls |
| Backend qualification | Capabilities of the exact built artifact | Universal bug freedom or compatibility of old servers |

## Related

- [python_haskell_boundary.md](../architecture/python_haskell_boundary.md) — ownership and consent handoff.
- [binary_build.md](binary_build.md) — application build and immutable publication.
- [multiplexer_adapter.md](../architecture/multiplexer_adapter.md) — backend identity and isolation.
- [quality_gate.md](quality_gate.md) — prerequisite observations and phase verdicts.
- [validation_runbook.md](../operations/validation_runbook.md) — native and WSL2 preparation.
- [external_tool_facts.md](../reference/external_tool_facts.md) — upstream tool facts.
- [Python bootstrap and handoff](../../DEVELOPMENT_PLAN/phase-2-python-bootstrap-and-handoff.md) — bootstrap owner.
- [Windows toolchain and psmux build](../../DEVELOPMENT_PLAN/phase-9-windows-toolchain-and-psmux-build.md) — native Windows preparation.
