# Sessions and Ownership

**Status**: Authoritative source
**Supersedes**: N/A
**Owning phase**: [Session management and adoption](../../DEVELOPMENT_PLAN/phase-6-session-management-and-adoption.md)

> **Purpose**: Define managed and adopted identities, backend compatibility, and the authority of each session command.

## TL;DR

- A managed session is created by agentctl and carries its live owned metadata. An adoption registers an
  existing pane without transferring ownership. Other sessions remain foreign.
- A target includes its backend/namespace and live generation identity. A session name, pane number or PID
  alone cannot authorize a write after a server or pane has been replaced.
- Debian tmux uses the normal user-selected server. Managed Windows sessions use agentctl's qualified psmux
  build and stable private registry; system-installed psmux remains separate.
- Session commands do not require a supervisor or an installed agent CLI merely to manage existing work.
  Watching, human attachment and ownership are independent.
- Only explicit `stop` or cleanup of a newly failed owned launch ends a managed session. Forgetting an
  adoption, stopping the supervisor or updating a backend never ends an adopted pane.

## Managed, Adopted and Foreign

| Kind | Authority | Durable record | Ordinary address |
|---|---|---|---|
| Managed | Exact owned session operations | Live `@agentctl_*` options; no ghost-session listing file | Checked session name |
| Adopted | Read/observe, and guarded recovery only when explicitly watched and qualified | Private adopted registry | Complete pane target and backend identity |
| Foreign | No mutation or automatic recovery | None | Explicit adoption may register an eligible live pane |

Tmux's selected socket defines its namespace. A Windows backend's canonical registry/config identity defines
its namespace, and each per-session psmux server has its own generation identity. Equal pane numbers on two
servers or equal session names in two registries remain different targets. Ambient `TMUX` text is a routing
hint rather than proof that two clients belong to the same namespace.

A system psmux installation coexists with agentctl's private build. Normal system commands retain the system
registry; `agentctl list` and `agentctl attach` retain agentctl's registry. External Windows adoption names its
registry explicitly and uses a separately checked client/server compatibility path. Discovery does not alter
that registry or import its settings into the private managed backend.

## Identity

A managed session retains checked owner, agent, canonical folder, native pane and trampoline status metadata.
Its backend/profile identity records the qualified runtime at creation. Every use reads live session facts;
metadata is not proof that the recorded executable still runs. The adapter checks the actual server instance,
endpoint/registry, session creation identity, pane generation and process creation identity where available.
Canonical folder comparison is case-folded on Windows and byte-preserving on POSIX.

An adopted registry entry stores the complete checked endpoint/registry, backend identity, server generation,
session and pane identity, process creation identity and explicit agent choice. The registry is an immutable
snapshot published atomically under an owned lock. Names and `pane_current_command` are display hints; they
cannot identify the agent, take ownership or authorize a new process after PID reuse.

An entry whose endpoint, server instance, pane generation or process creation identity no longer agrees is
stale. Stale entries remain diagnosable but are never captured or sent input. A server that restarts with the
same socket, numeric pane id and PID still has a different generation; it cannot inherit old authority. An
explicit missing pane does not fall back to the active pane or a prefix sibling.

Psmux targets retain the checked session as well as the native pane id. A bare pane id is accepted only if
exactly one eligible server contains it; ambiguity is a typed refusal that changes no registry. An external
adopted pane has no agentctl trampoline status file, so unavailable exit status remains unavailable rather
than being replaced by psmux's placeholder zero.

The running server's executable provenance is checked independently from the command client's artifact.
New-client/old-server combinations expose only their qualified operations. An accepted version banner alone
never enables supervision. Backend incompatibility is distinct from a stale target: a live legacy session can
remain accessible for its tested read-only or attachment operations while automated recovery is unavailable.

## The Commands

- `list` reports managed sessions in the selected namespace and registered adopted targets, with ownership,
  agent, folder, live/dead/stale state, pane/process identity, attachment, backend/profile compatibility and
  watch state. It does not enumerate unrelated foreign sessions as managed work.
- `status [NAME]` selects an owned or registered target, or the managed sessions for the current folder. It
  adds current observation/classification only after identity and capability checks. Stale, incoherent or
  incompatible observations display `Unknown` or the named unavailable reason without sending input.
- `attach NAME` selects a managed session and invokes its exact qualified foreground client and namespace.
  Within a compatible client in that namespace it can switch; without a terminal it prints `agentctl attach
  NAME`. It changes no session metadata, agent installation or authentication state.
- `stop NAME` ends one currently revalidated managed session by exact target. For an adopted target, live or
  stale, it removes only the registration and states that the pane continues running. A foreign name refuses
  without sending a terminal command.
- `adopt PANE --agent claude|codex` registers an eligible live external pane with explicit agent choice and
  complete identity. It refuses a missing, dead, ambiguous, managed or already registered target. It never
  sets session options, types keys, installs an agent or ends a process.

[The CLI reference](../reference/cli_reference.md) owns exact syntax, output fields and exits. JSON quoting
within tabular display preserves folder, session and command text containing whitespace or control characters.
Human-readable hints remain separate from fields used for identity. An empty listing still has a header.

## What Each Command May Touch

| Action | Managed | Adopted | Foreign |
|---|---|---|---|
| List and status | Live facts and checked observation | Registered identity and checked observation | No ordinary managed row |
| Attach | Qualified foreground client | Explicit external-user workflow only | No implicit attachment |
| Session-option writes | Creation-owned metadata and bounded startup handling | Never | Never |
| Guarded recovery | Explicitly watched and fully qualified target | Explicitly watched, revalidated and fully qualified target | Never |
| Session termination | Explicit stop or cleanup of this failed new launch | Never | Never |
| Server termination, respawn, global settings | Never | Never | Never |

Exact targeting protects prefix siblings. A target is revalidated immediately before every write, and a
conditional backend operation rechecks its generation at execution. Permission to forget a registration
carries no terminal mutation capability. An adopted stale entry can be forgotten without connecting to a new
server that happens to reuse its name.

A backend build/update prepares a new immutable artifact; it does not rewrite existing sessions or aliases.
A deliberate migration identifies the client and server separately, preserves old artifacts needed by active
sessions, and recreates only sessions whose owner explicitly requests recreation. No update silently restarts
agents or turns legacy sessions into compatible ones by editing metadata.

## Independence from the Supervisor

Session management, adoption, watching and human attachment are independent. The supervisor starts only when
the user requests it. Attaching does not grant watch permission; watching does not grant ownership; pause and
unwatch change only watch intent. Stopping supervision releases its lock and leaves managed and adopted panes
and their process identities intact.

A command uses only its actual prerequisites. Listing, status, attachment and stopping do not demand both
agent CLIs or fresh authentication. Reattaching an existing live session does not apply new agent ARGS. A new
launch follows [the launch contract](launch_contract.md#preflight) and checks only its requested agent.

## WRONG and RIGHT

| WRONG | RIGHT | Why |
|---|---|---|
| Resolve a psmux pane by `%1` across every server | Retain backend registry, server/session generation and `%1` | Numeric ids can be equal on different servers |
| Trust a registry PID after restart | Compare process creation and server/pane generation identities | Numeric reuse does not preserve ownership |
| Stop an adopted pane with a terminal kill command | Forget its registration and leave it alive | Adoption transfers no ownership |
| Reconnect with any PATH psmux after an upgrade | Use the qualified client/server combination and exact registry | A new executable does not patch a running server |
| Treat a system registry as agentctl's private registry | Name and validate the external registry explicitly | Coexistence requires separate runtime state |

## Related

- [Launch contract](launch_contract.md) — canonical names and create-or-attach.
- [Multiplexer adapter](multiplexer_adapter.md) — qualification, registries and exact targets.
- [Supervisor contract](supervisor_contract.md) — watch intent and guarded recovery.
- [Files and state](../reference/files_and_state.md) — private registry and state schemas.
- [CLI reference](../reference/cli_reference.md) — syntax, output and diagnostics.
- [Session management and adoption](../../DEVELOPMENT_PLAN/phase-6-session-management-and-adoption.md) — the owning phase.
- [Windows application acceptance](../../DEVELOPMENT_PLAN/phase-11-windows-application-acceptance.md) — native Windows instance and coexistence evidence.
