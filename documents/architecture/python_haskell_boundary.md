# Python and Haskell Boundary

**Status**: Authoritative source
**Supersedes**: N/A
**Owning phase**: [Python bootstrap and handoff](../../DEVELOPMENT_PLAN/phase-2-python-bootstrap-and-handoff.md)

> **Purpose**: Define the smallest Python bootstrap, the Haskell-owned runtime, and the typed handoff between them.

## TL;DR

- `pipx` installs a portable Python package with Click and bundled Haskell source. Installation of the Python
  package performs no native compilation. Python obtains the Haskell executable on its first required use.
- Python owns only bootstrap directories, the prerequisites needed to build Haskell, ghcup, pinned GHC and
  cabal, source-digest-keyed compilation and publication, raw transport, and the development gate adapter.
- Haskell owns runtime host policy, dependency planning and provisioning, multiplexer acquisition and
  qualification, agent checks, launch, sessions, observation and recovery. Python implements none of these.
- Windows Haskell builds a private psmux from pinned source using a privately selected Rust toolchain and
  qualified native linker/SDK prerequisites. Debian Haskell reuses or provisions tmux through APT.
- Claude and Codex remain user-installed. Their absence is a Haskell refusal, never an installation action.

This page states the target contract. Source shapes requiring migration are owned by the
[deletion ledger](../../DEVELOPMENT_PLAN/legacy_tracking_for_deletion.md); a document is not implementation evidence.

## What Python Owns

`src/agentctl/paths.py` derives absolute `cache`, `data` and `state` roots from explicit platform, environment
and home values. The same roots serve bootstrap and runtime; Haskell validates them and derives only owned
subdirectories. [Files and state](../reference/files_and_state.md) owns their layout.

The bootstrap ensures the core binary for the bundled sources and pins. A valid digest hit goes directly to
handoff. A miss takes a build lock, observes the missing native Haskell prerequisites, applies only the
authorized bootstrap plan, verifies ghcup and the pinned GHC/cabal, builds outside the package source tree,
checks the handshake and atomically publishes an immutable executable. A concurrent caller reuses the
published winner. [Toolchain bootstrap](../engineering/toolchain_bootstrap.md) and
[binary build](../engineering/binary_build.md) own this process.

Python follows the strict doctrine in [code standards](../engineering/code_standards.md): immutable typed
values, single assignment, total calculation kernels and explicit effect adapters. Framework capabilities and
native decoder trees remain borrowed boundaries, never mutable application state. No runtime dependency
policy is duplicated to make a Python fallback.

The development gate remains accessible only as `agentctl check`. Its Python adapter runs the quality tools
and evidence joins described by [the quality gate](../engineering/quality_gate.md), invoking Haskell-owned
runtime subjects through their public application or test interfaces. The gate contains no second installer.

## What the Core Binary Owns

The Haskell application obtains native host facts and calculates a typed runtime plan before applying it:

| Host | Haskell-owned runtime behavior |
|---|---|
| Debian Linux | Require exact Debian identity, reuse a supported tmux or provision it through APT with consent, then qualify the resolved executable |
| Windows x86_64 | Ensure qualified native linker/SDK capabilities and private pinned Rust/Cargo, fetch verified psmux source and patches, build, qualify and publish privately |
| macOS | Apply the separately declared native macOS adapter and host prerequisites; Linux or Windows evidence does not qualify it |
| Other Linux distribution or unsupported host | Return a typed unsupported-platform refusal before runtime mutation |

Source acquisition uses Haskell HTTPS and archive adapters where practical. If an external acquisition tool
is required, Haskell owns its idempotent provision and exact invocation too. The runtime does not depend on
Git, curl or an archive CLI merely to fetch the pinned psmux source. It never installs an agent CLI, npm agent
package, credential or login state.

Haskell reuses accepted runtime artifacts without package-manager, download or build work. A missing
prerequisite, denied consent, unavailable privilege, required reboot, failed verification or failed build has
a named failure outcome. It does not prompt through an installer, answer a dialog, change global toolchain
selection, or silently substitute a system psmux. [The multiplexer adapter](multiplexer_adapter.md) owns
the backend contract and [the launch contract](launch_contract.md#preflight) its use by commands.

Haskell retains one native process runner, `AgentCtl.Process`, for runtime commands and installers. Its
typed provisioning vocabulary is distinct from the session vocabulary, so permission to install tmux does
not authorize a shell command or an action against an existing session.

## Raw Passthrough

Click recognizes the public command and the global bootstrap options before the command. The remaining
argument sequence crosses unchanged: empty arguments, Unicode, newlines, `--`, `--help` and shell-like text
remain distinct values. `AgentCtl.Agent.Argv` alone assembles agent flags and rejects login-shaped input.

Global `--assume-yes` expresses consent to the concrete prerequisite plan. Click conveys its meaning through
a dedicated typed handoff field, separate from the raw command tail. Thus a global consent option authorizes
the Haskell plan, while `agentctl claude --assume-yes` still gives that tail argument to Claude. Haskell does
not recover consent by inspecting agent arguments or by observing that privileged execution is possible.

The command table and the core handshake have one contract, with the development gate adapter declared
explicitly. Through-stack tests compare the actual forwarded arguments with independent expected values
(`tests/e2e/test_passthrough_argv.py::test_through_stack_rows`).

## The Handoff

`bootstrap/handoff.py` supplies the protocol version, the absolute root directories and the explicit consent
value. Haskell validates this envelope before dispatch. Runtime OS and Debian distribution policy belong to
Haskell; a Python distribution hint is not authority to install a runtime package.

On POSIX Python flushes its streams and replaces itself with the core executable. On Windows it starts the
core as a child with inherited terminal streams, leaves console interrupts to the child, waits and returns
the child's exit status. Raw transport introduces no shell. The core executable is addressed by its published
absolute path and is never exposed as a second user command.

## The Handshake and Direct Invocation

The handshake identifies the handoff protocol and public command vocabulary. A protocol change, including
consent-envelope changes, changes its data home and has accepting and refusing protocol controls. Source and
toolchain identity are checked by the binary-build owner rather than inferred from a version banner.

Ordinary dispatch without a valid handoff refuses with a remedy naming `agentctl`. This prevents accidental
direct use and is not a security boundary against the account owner. The pane trampoline is the explicit
exception: its authority is the owned private spec described by
[the pane trampoline](launch_contract.md#the-pane-trampoline), not inherited bootstrap variables.

## The Python Spawn Set

Every Python process operation goes through `src/agentctl/process.py`. The permitted families are the core
handoff/handshake, the Haskell bootstrap toolchain and its necessary native probes, and the development gate's
declared tools and read-only evidence observers. There is no Python Rust, Cargo, psmux, tmux, Claude, Codex or
runtime package-manager execution path.

Bootstrap privilege changes use the bootstrap consent contract. Runtime privilege changes occur only in the
Haskell runtime planner. Ordinary tests veto real package-manager and sudo invocations on both paths; native
preparation uses explicitly owned setup environments outside ordinary test execution. The spawn audit pairs
each absence assertion with an observed allowed operation so an inactive observer cannot prove isolation.

## Single Owners

| Invariant | Owner | Other layer's responsibility |
|---|---|---|
| Initial executable and Haskell build toolchain | Python bootstrap | Haskell does not bootstrap itself |
| Root directory convention | `src/agentctl/paths.py` | `AgentCtl.Paths` validates supplied roots and derives owned children |
| Consent transport | Python handoff envelope | Haskell validates and applies consent to its actual runtime plan |
| Runtime platform policy and dependency provisioning | Haskell runtime planner | Python forwards the command without a runtime fallback |
| Multiplexer binary, identity and capabilities | Haskell backend owner | Python never searches for or launches a multiplexer |
| Agent availability, authentication and argv | Haskell agent/preflight modules | Python preserves raw arguments |
| Session and recovery behavior | Haskell session/supervisor modules | Python implements no parallel model |
| Development evidence and closure | `agentctl check` | Product commands expose subjects, never a second closing runner |

## WRONG and RIGHT

| WRONG | RIGHT | Why |
|---|---|---|
| Python downloads psmux or invokes Cargo before forwarding | Haskell computes and applies the Windows backend plan | Runtime policy has one owner |
| Infer runtime consent from a successful sudo probe | Carry explicit consent in the handoff | Privilege is a capability, not authorization |
| Add required agent flags in Click | Assemble them in `AgentCtl.Agent.Argv` | Raw transport must preserve the user's tail |
| Install Claude because launch cannot find it | Return an actionable missing-agent refusal | Agent installation and credentials remain user-owned |

## Related

- [Launch contract](launch_contract.md) — raw arguments, preflight and the trampoline.
- [Multiplexer adapter](multiplexer_adapter.md) — runtime provisioning and backend capabilities.
- [Code standards](../engineering/code_standards.md) — Python and Haskell source doctrine.
- [Toolchain bootstrap](../engineering/toolchain_bootstrap.md) — obtaining the initial native executable.
- [Binary build](../engineering/binary_build.md) — immutable compilation and publication.
- [Quality gate](../engineering/quality_gate.md) — one command and phase evidence.
- [Files and state](../reference/files_and_state.md) — owned storage roots.
- [Python bootstrap and handoff](../../DEVELOPMENT_PLAN/phase-2-python-bootstrap-and-handoff.md) — the owning build phase.
