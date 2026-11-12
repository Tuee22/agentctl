# Multiplexer Adapter

**Status**: Authoritative source
**Supersedes**: N/A
**Owning phase**: [Debian tmux and multiplexer](../../DEVELOPMENT_PLAN/phase-4-debian-tmux-and-multiplexer.md)

> **Purpose**: Define Haskell-owned runtime provisioning, qualified backend identity, typed terminal operations and isolated session routing.

## TL;DR

- Haskell owns runtime dependency observation, planning, consent, provisioning, qualification and execution.
  Debian uses an APT-provided tmux; Windows uses an agentctl-built, qualified native psmux.
- A backend is a capability with an absolute executable, artifact identity, namespace and supported operations.
  A version banner or a PATH match alone does not authorize automated input.
- Windows uses a stable private registry and controlled configuration. A system psmux installation and its
  sessions remain separate. Debian tmux retains the normal user-server convention for interactive sessions.
- All terminal commands and installers pass through `AgentCtl.Process`. Session operations and provisioning
  actions have separate closed vocabularies; neither accepts arbitrary shell text.
- Observation and recovery require coherent target-bound snapshots and guarded submission. An unavailable
  guarantee produces an explicit unsupported capability, not a heuristic fallback.

This contract starts with Debian and extends to the Windows backend through
[Windows toolchain and psmux build](../../DEVELOPMENT_PLAN/phase-9-windows-toolchain-and-psmux-build.md) and
[Windows backend qualification](../../DEVELOPMENT_PLAN/phase-10-windows-backend-qualification.md).
Those extensions implement the same capability contract rather than replace the Debian semantics.

## Resolution and Version Floors

`AgentCtl.Mux` consumes a Haskell runtime plan and produces an opaque qualified backend. Native OS facts are
observed in Haskell. On Linux the distribution must identify itself as Debian with exact `ID=debian` in
`/etc/os-release`. An APT executable or a Debian-like distribution name does not establish that policy.
Other Linux distributions return an unsupported-host failure before runtime installation or session mutation.

On Debian, reuse an executable only after its actual version and required behavior qualify. If tmux is absent,
Haskell presents and applies the verified APT plan with explicit consent and sufficient privilege, then
re-resolves and qualifies the result. A repository that cannot supply supported behavior yields a typed
failure; agentctl does not add package repositories or retry installation indefinitely. The supported minimum
and verified APT arguments live in [external tool facts](../reference/external_tool_facts.md) and the backend
oracle, rather than being inferred from which executable appears first on PATH.

A warm qualified runtime performs no APT operation, download or build. Consent and privilege are separate:
an elevated process or a successful sudo probe does not itself authorize installation. Noninteractive
execution without consent refuses; checks and tests answer no package-manager, approval or installer dialog.

On Windows, PATH discovery does not select the runtime backend. Haskell owns these steps:

1. Select the pinned source, patch set, build profile, Rust target and required native linker/SDK capabilities.
2. Reuse an accepted private artifact whose identity agrees with that complete build key.
3. On a miss, take an interprocess lock, recheck, observe missing prerequisites and calculate a concrete plan.
4. Provision authorized prerequisites; use private `RUSTUP_HOME` and `CARGO_HOME` and absolute compiler paths.
5. Download the verified official source archive through Haskell, validate archive entries and extract into
   short owned staging storage. Archive traversal, links and unexpected source identity are failures.
6. Apply the recorded hardening patches, build with the locked dependency plan, run artifact qualification,
   record provenance and atomically publish an immutable version directory.

The initial upstream base is `063ca7026eb2b7b91a74d3f858bdec3dfc841dbb`. It includes frame coalescing,
clipboard/bell preservation and genuine joined capture, but its name alone grants no qualification. Wide-glyph
wraps, missing explicit target behavior, queue stress and the recovery capability require independent
controls and any necessary recorded patches. No moving branch or plain `3.4.0` banner identifies an accepted
build. [External tool facts](../reference/external_tool_facts.md) owns the pinned source observations.

The toolchain contract includes a qualified x64 MSVC linker, libraries, resource compiler and Windows SDK.
Haskell observes actual compile/link/resource capability rather than assuming that Cargo or a product
registration suffices. An unavailable privilege or reboot requirement is a named not-ready outcome. Haskell
never opens UAC, answers an installer, reboots the host or changes global Rust selection and shell profiles.

The manifest binds source/archive/patch/lockfile identities, Rust and native build-tool identities, build
configuration and executable hashes. A failed or interrupted build publishes nothing. A changed pin creates a
new directory and never overwrites an executable used by a running server.

The separately declared macOS adapter uses native tmux and native host qualification. Windows psmux is never
used by Linux or macOS, and WSL tmux evidence never supplies a Windows or macOS result.

## The Typed Vocabulary and the One Runner

`AgentCtl.Mux.Command` expresses terminal intent as closed values. Backend renderers and capability adapters
interpret those values; `AgentCtl.Process` owns every native spawn, exec and bounded process lifecycle.
Provisioning commands are a different closed plan interpreted through that runner. No shell string accepts
user input as executable syntax.

| Operation | Contract |
|---|---|
| Create | Create one checked name with the absolute pane trampoline and a private spec |
| Exists and discover | Read exact session names, native panes, options and current identity |
| Inspect | Return a complete target-bound snapshot, or a named unsupported/incoherent result |
| Guarded submit | Compare the target generation and observation token and submit the permitted literal text plus Enter as one ordered operation |
| Attach or switch | Open an inherited-stream client against the exact selected backend and namespace |
| Stop | End one owned exact session; forgetting an adoption does not send a terminal command |
| Remain-on-exit | Temporarily retain the agent pane for startup status handling |

The vocabulary contains no production `kill-server`, pane respawn, global configuration change, arbitrary
shell command, login command or model-switch action. Typed construction and private capability constructors
keep provisioning authority, session ownership and the right to submit input distinct.

Bounded queries drain stdout and stderr concurrently as bytes and decode UTF-8 explicitly. Timeout, malformed
output, invalid encoding and unsupported capability remain typed failures. Foreground clients inherit terminal
streams; they do not run through a buffering capture relay. Session creation permits the owned persistent
server to outlive its creating client, while query subprocesses retain bounded process-tree ownership.

## Targets and Session Options

Every session operation identifies an exact name, using the backend's checked exact-target representation.
The name alphabet excludes target separators and namespace ambiguity. A pane identity includes the backend
kind, registry/socket identity, server generation, session identity and native pane generation. A native
`%id` alone cannot identify a psmux pane across per-session servers.

An explicit missing, dead or replaced target returns a failure. Capture and submission never fall back to
an active pane, a prefix sibling or a newly created server with a reused numeric id. Name-based hints,
command text and process names cannot substitute for process creation or backend generation identity.

Managed sessions carry the following owned metadata:

| Option | Value |
|---|---|
| `@agentctl_owner` | `agentctl` |
| `@agentctl_agent` | The checked Claude or Codex identity |
| `@agentctl_folder` | Canonical folder encoded as base64url UTF-8 |
| `@agentctl_pane` | The selected native agent pane id |
| `@agentctl_status` | Encoded private trampoline status-file path where needed |
| `@agentctl_backend` | The accepted backend/profile identity associated with creation |

Options are session-owned facts, not durable proof that an executable still runs. Observation revalidates
against the actual server instance and executable provenance. Session-server PID creation identity prevents
PID reuse from granting old authority. Artifact hash and source revision cannot be inferred from a client
version string.

On Debian, interactive tmux sessions remain on the normal user-selected server, preserving ordinary tmux
visibility and explicit adoption. On Windows, new managed sessions use an agentctl-owned stable
`PSMUX_DATA_DIR`, a controlled config and disabled unsolicited warm provisioning. That registry is separate
from the system installation; ordinary system `psmux ls` does not list agentctl's sessions. User access goes
through `agentctl list` and `agentctl attach`.

The private Windows registry is stable across accepted build versions. Before connecting or sending a write,
Haskell identifies the actual running server and applies the qualified client/server compatibility matrix.
Repointing an executable or a command alias does not update existing clients or servers. Legacy discovery
and read-only diagnostics can remain available without granting automatic recovery. Migration deliberately
recreates a session after it is drained; no upgrade silently stops or restarts an agent. External Windows
adoption names its separate registry explicitly and retains external ownership.

## Format Expansion, Separators and the Trampoline

Session creation gives the multiplexer only checked names and agentctl-generated paths. User arguments,
working directory and environment travel in the private pane spec, not a multiplexer shell command.

- No user folder is passed through a format-expanded multiplexer `-c` field. The client working directory
  and the trampoline's validated spec establish the agent's directory.
- No secret environment value is placed on a multiplexer argv with `-e`.
- No multiplexer command chain is assembled with semicolons.
- The trampoline starts the agent with its literal argv and the caller's environment, excluding injected
  multiplexer agent-tuning variables that were absent in the caller.
- Creation failures are shown on the invoking terminal, and startup cleanup touches only the new owned
  session. A previous managed, adopted or foreign session is never launch cleanup.

The Windows trampoline waits for its native agent child and publishes the actual status privately. Psmux's
placeholder pane status is not the child's exit code. On POSIX the trampoline replaces itself with the agent;
normal exit and signal observations follow the declared native status contract.

## psmux Differences

| Topic | Required handling |
|---|---|
| Per-session servers | Qualify each actual server instance; disambiguate equal native pane ids |
| Client frame queue | Coalesce superseded state without blocking the socket reader; preserve ordered controls and one-shot fields; qualify the declared workload and byte-budget policy |
| Joined text | Join only native soft-wrap continuations; retain intentional newlines, spaces and Unicode glyph boundaries |
| Dead status | Use the trampoline's status receipt instead of placeholder native dead status |
| Registry | Use the stable owned registry and controlled config for managed sessions |
| Existing system installation | Leave its executables, aliases, configuration, registry and running sessions untouched |
| Backend update | Preserve immutable builds and running sessions; use actual client/server compatibility evidence |
| Recovery input | Require the coherent observation and guarded-submit capability; ordinary separate capture/send commands do not establish it |

Frame coalescing does not by itself prove globally bounded memory under every possible stream. Qualification
includes frame/no-change alternation, control bursts, variable frame sizes and the explicit policy for
non-coalescible backlog. A blocking reader is not a permitted fix: it can move the stall to a server write
timeout and disconnect the attached client.

## Isolation

Tests supply unique nonce-bound registry/socket/config roots and owned XDG directories. Tmux tests unset the
user's `TMUX` and use a short owned socket location. Windows tests supply an absolute owned `PSMUX_DATA_DIR`,
controlled configuration and `PSMUX_NO_WARM=1` to every candidate subprocess. Production private Windows
routing is a real product property, not a hidden test-only branch.

Teardown proves ownership from the actual endpoint and process-creation identity before stopping a private
server or child. It never kills by executable image name. Native build workspaces have a complete path-length
budget and are registered with containment even when a shorter sibling storage root is necessary. Test
resource cleanup errors preserve the original diagnostic and remain failures.

The dependency's synthetic client regression and a real-server stall test measure private committed memory,
not just resident memory. A capped vulnerable negative control proves the observer sees the defect without
exhausting the workstation. Native Windows evidence, pane survival, output resumption, exact target controls,
raw joined capture and conditional-input races form separate obligations. Linux validation may use the
owned WSL2 environment described by [testing](../engineering/testing.md); it supplies Linux evidence only.

## Related

- [Python and Haskell boundary](python_haskell_boundary.md) — one runtime owner and explicit consent transport.
- [Launch contract](launch_contract.md) — checked creation and the pane trampoline.
- [Sessions and ownership](sessions_and_ownership.md) — instance identity, adoption and allowed mutations.
- [Supervisor contract](supervisor_contract.md) — snapshots, guarded delivery and safety limits.
- [Testing](../engineering/testing.md) — isolated native observers and host evidence.
- [External tool facts](../reference/external_tool_facts.md) — verified pins and native tool behavior.
- [Debian tmux and multiplexer](../../DEVELOPMENT_PLAN/phase-4-debian-tmux-and-multiplexer.md) — the common backend contract.
- [Windows toolchain and psmux build](../../DEVELOPMENT_PLAN/phase-9-windows-toolchain-and-psmux-build.md) — native source preparation.
- [Windows backend qualification](../../DEVELOPMENT_PLAN/phase-10-windows-backend-qualification.md) — accepted Windows behavior.
