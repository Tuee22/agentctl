# Installation

**Status**: Authoritative source
**Supersedes**: N/A
**Owning phase**: [Python bootstrap and handoff](../../DEVELOPMENT_PLAN/phase-2-python-bootstrap-and-handoff.md)

> **Purpose**: Describe pipx installation, automatic source builds, host-owned runtime preparation, external agent prerequisites and safe upgrades.

This page states the required user-facing contract. The plan and gate receipts establish which implemented
host paths satisfy it; a successful Python package installation is not proof of native backend qualification.

## Requirements

Pipx and its Python are the starting build dependency. The package is a portable Python wrapper with bundled
Haskell source; installation exposes `agentctl` without compiling native programs during wheel installation.
First use bootstraps the native application. Python owns only the prerequisites needed before Haskell exists;
Haskell owns runtime platform policy and multiplexer preparation.

| Host | Runtime preparation | External user responsibility |
|---|---|---|
| Debian Linux | Haskell reuses or installs supported tmux through APT | Install the requested claude or codex CLI and arrange authentication |
| Native Windows | Haskell provides private Rust/build prerequisites and builds qualified pinned psmux source | Supply permission for required system prerequisites; install native agent executables and arrange authentication |
| Native macOS | Its own qualified native bootstrap/multiplexer path | Install agent CLIs and arrange authentication |

Linux requires exact Debian identity. A Linux machine with APT but another distribution is unsupported rather
than silently accepted. Windows backend preparation is native; WSL2 can provide a separate Debian validation
lane but cannot replace native Windows execution. [Validation runbook](validation_runbook.md) defines that setup.

Agentctl never installs claude or codex. A new launch checks its requested executable early and reports the
missing tool before an expensive backend build. Listing, logs and reattachment require only their actual
runtime prerequisites, not both agent CLIs or repeated login checks.

## Install pipx

Use the platform's supported pipx installation method and ensure its exposed command directory is reachable.
Python and development-tool versions come from the package metadata and pin manifests, not an assumed global
interpreter. [External tool facts](../reference/external_tool_facts.md) holds the upstream installation sources.
Agentctl does not edit shell startup files or global PATH.

## Install agentctl

Install the checkout with pipx, or install a published source/wheel artifact carrying the same bundled sources.
A Git URL needs Git for pipx's acquisition; installing a local checkout does not. Contributors use
`pipx install --editable '.[dev]'` from the editable checkout, then run `agentctl check` there.
A commit, staged index or clean worktree is never required for editable development or validation.

## First Run

1. Python validates bootstrap host facts, prepares pinned ghcup/GHC/cabal when needed, source-builds the
   Haskell application and hands over the command with immutable directory/protocol/consent values.
2. Haskell validates runtime host policy and checks a requested external agent before costly provisioning.
3. On Debian, it reuses suitable tmux or presents the needed APT installation plan and verifies the result.
4. On Windows, it reuses a qualified private backend digest or prepares the native Rust/linker/SDK chain,
   downloads verified source/patch inputs, builds and qualifies psmux, and atomically publishes the result.
5. Only after prerequisites and authentication checks succeed does the application create the agent session.
   Re-running a live session reattaches under the session contract rather than reinstalling dependencies.

Warm accepted inputs cause no redundant package-manager action, source download or native build. Concurrent
commands share a lock and reuse the accepted winner. A failed install/build publishes nothing and retains
previous immutable entries. Preparation requiring restart, unavailable privilege or policy permission stops
with a specific remedy; the application never answers a system dialog or restarts the host.

Windows psmux lives under agentctl's private data tree and uses a stable private registry and controlled
configuration. Its clients and servers coexist with a system psmux installation without replacing system
aliases or operating on that installation's registry. Plain system psmux discovery does not expose the private
sessions; use `agentctl list` and `agentctl attach`. Explicit adoption of an external registry requires the
separate ownership/compatibility policy and never grants ownership of the external session.

## Runs Without a Terminal

Noninteractive preparation cannot prompt. Explicit installation consent and already available privilege are
required for system changes. Global consent travels separately from raw agent arguments; a similarly spelled
flag in the agent's tail remains the agent's argument. Authentication dialogs and login operations are never
part of automatic preparation. `agentctl check` reports missing setup without opening installers.

## Logging In

The user installs and authenticates the selected agent outside agentctl. Agentctl observes authentication
status and reports the appropriate discrete remedy when logged out; it never runs login, types login input,
answers trust/bypass/approval dialogs or installs the agent's package manager.

## Upgrade

Upgrade the Python package through pipx. Changed native source/toolchain/backend inputs choose new immutable
cache entries, leaving running executables and sessions intact. A new attached client and a new server are
separate upgrades; agentctl reports compatibility and requires deliberate session recreation when a server
cannot supply a needed capability. A failed candidate qualification keeps prior known-good entries available.

## Removal

Remove the exposed application using pipx. Application-owned caches, publications and state are separate
per-user directories described by [files and state](../reference/files_and_state.md). Their removal must not
end unrelated sessions, remove user agent credentials or uninstall shared system build prerequisites.
Delete only verified owned paths, after their clients/servers and build processes have ended through the
normal lifecycle. No image-name kill or recursive removal of an inferred user directory is permitted.

## Related

- [toolchain_bootstrap.md](../engineering/toolchain_bootstrap.md) — bootstrap and Haskell preparation.
- [binary_build.md](../engineering/binary_build.md) — source builds and immutable caches.
- [multiplexer_adapter.md](../architecture/multiplexer_adapter.md) — private Windows registry and compatibility.
- [launch_contract.md](../architecture/launch_contract.md) — preflight, argv and reattachment.
- [validation_runbook.md](validation_runbook.md) — native and WSL2 validation preparation.
- [troubleshooting.md](troubleshooting.md) — actionable refusal and readiness outcomes.
- [files_and_state.md](../reference/files_and_state.md) — owned directories and removal boundaries.
- [Python bootstrap and handoff](../../DEVELOPMENT_PLAN/phase-2-python-bootstrap-and-handoff.md) — installation owner.
