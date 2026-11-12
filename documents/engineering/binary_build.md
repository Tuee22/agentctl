# Binary Build

**Status**: Authoritative source
**Supersedes**: N/A
**Owning phase**: [Python bootstrap and handoff](../../DEVELOPMENT_PLAN/phase-2-python-bootstrap-and-handoff.md)

> **Purpose**: Define source-built executable identities, immutable caches, qualification and publication for the Haskell application and its Haskell-managed Windows backend.

This page specifies the required contract. The phases join source, packaging, native controls and receipts;
an existing cache entry does not establish conformance to its build or capability policy.

## The Cabal Project as Package Data

The Python distribution carries Haskell sources beside the bootstrap. Pipx exposes Click without native
compilation during wheel installation. First use obtains the pinned toolchain and builds those installed
sources. Editable installs read the live checkout, including uncommitted files; builds require no commit or
clean worktree. Output and dependency stores remain outside package sources.

The inventory includes the Cabal manifest/project and every declared application, library and test source. Actual foundation/protocol and transport-test components have only introduced prerequisite imports; later product libraries and the final command executable extend that component graph. No early component advertises a future stub. The complete gate attempts every present component, while early build-mechanism evidence uses its actual independent native component and failure controls.
The Python package ships no developer-built application binary. After bootstrap, Haskell owns the native
Windows psmux source-build workflow and its independent source/patch/toolchain identity.

## The Digest

Each native component identity length-prefixes its actual source/dependency-closure path/body pairs, relevant manifest/pins and platform identity. An early foundation/transport component contains no later product source. The full runtime executable has its own cumulative implemented-source identity; a later executable change does not alter an earlier independent component receipt. Missing required sources, links, special entries and incomplete traversal return typed errors.
Style configuration has a separate identity unless it changes compilation. Inventory projection is pure;
filesystem reads and native hashing capabilities stay at explicit edges.

The psmux digest includes upstream revision/archive, complete ordered patch contents, workspace and lockfile
inputs, exact Rust compiler/target, relevant MSVC/SDK identities, build flags and backend capability schema.
Its banner is not its identity. Cached dependencies are admitted by recorded inputs rather than presence alone.

## Build and Publish

An accepted application digest entry is checked before provisioning. A miss acquires a native build lock,
checks again, ensures the exact toolchain, builds in owned storage, verifies the handshake and publishes a
sibling staging directory with one rename. Published entries remain immutable. Concurrent waiters reuse the
qualified winner; failed builds and incomplete staged entries never replace a previous executable.

Haskell uses the same lifecycle for psmux with a separate lock. The reusable builder publishes a build-verified candidate; the separate backend-profile admission requires native behavioral qualification before runtime use. A later profile supplies exact patch/recipe bytes as consumer inputs, without making that profile a prerequisite for the earlier generic builder contract. Cargo uses the locked
dependency graph and an explicit compiler rather than PATH or an upstream moving default. Online locked
resolution and offline frozen resolution have distinct readiness requirements; a lockfile alone does not
promise an offline build.

Windows roots have a measured native path budget including the deepest generated component filename. A short
root is registered with canonical path, owner and run nonce before use. Roots outside the main temporary
folder remain subject to accounting, containment and cleanup. Changing global long-path policy is not a
validation prerequisite. All build and probe children are reaped before final resource inspection.

## Binary Identity

The independently located application compiler output and published executable have the same SHA-256 and
answer the required handoff protocol. The public command is `agentctl`; the internal application runs only
through its wrapper, application-owned build/test path or authorized pane trampoline.

A psmux receipt records source, patches, toolchain, build settings, all produced alias hashes and capability
results. Agentctl invokes the selected absolute `psmux.exe` path, never installs replacement system aliases,
and separately identifies the actual running server. Replacing a file or changing a client path upgrades
neither old servers nor attached clients. [Multiplexer adapter](../architecture/multiplexer_adapter.md)
owns runtime compatibility and isolation.

## Packaging

Wheel/sdist controls inspect installed package resources, Haskell sources, pins and owned backend patch data.
Their filesystem census includes newly introduced uncommitted files. Binaries, local builds, credentials,
user configuration and developer caches are excluded. Runtime dependencies remain separate from optional
development tools. Strict Python doctrine is project-owned and introduces no helper-package dependency.

## Upgrade

Changed accepted inputs select a new immutable directory. Upgrades replace no executable in use, restart no
agent, silently migrate no server and erase no known-good entry. Failed qualification leaves the prior
artifact available. Explicit migration reports affected sessions and their capabilities; ordinary session
commands do not turn an upgrade into an implicit restart.

## Related

- [toolchain_bootstrap.md](toolchain_bootstrap.md) — the two preparation stages.
- [python_haskell_boundary.md](../architecture/python_haskell_boundary.md) — raw handoff and ownership.
- [multiplexer_adapter.md](../architecture/multiplexer_adapter.md) — backend/server identity.
- [files_and_state.md](../reference/files_and_state.md) — build, publication and receipt locations.
- [quality_gate.md](quality_gate.md) — native identity and phase-input evidence.
- [code_standards.md](code_standards.md) — immutable inventories and typed failures.
- [Python bootstrap and handoff](../../DEVELOPMENT_PLAN/phase-2-python-bootstrap-and-handoff.md) — application build owner.
- [Windows toolchain and psmux build](../../DEVELOPMENT_PLAN/phase-9-windows-toolchain-and-psmux-build.md) — backend build owner.
