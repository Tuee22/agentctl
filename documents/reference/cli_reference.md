# CLI Reference

**Status**: Authoritative source
**Supersedes**: N/A
**Owning phase**: [Recovery and supervisor](../../DEVELOPMENT_PLAN/phase-8-recovery-and-supervisor.md)

> **Purpose**: Define public commands, raw transport, runtime preparation, capability reporting and exit outcomes.

`agentctl` is the permanent pipx/Click entry point. Python obtains the source-built Haskell application and
forwards product commands. The developer-only `check` command reports complete phase/lane evidence.
The [plan](../../DEVELOPMENT_PLAN/README.md) owns completion status; a command is exposed only when its real
owning contract is introduced, with no future placeholder in the handshake.

## Global Options

Global options precede the command. Every token after `claude` or `codex`, including `--help`, belongs to
that agent's raw tail except the checked mandatory-flag/login rules in the launch contract.

| Option | Meaning | Owner |
|---|---|---|
| `--assume-yes` | Authorizes a concrete missing-prerequisite preparation plan under the applicable privilege policy. Python uses it for bootstrap and passes a typed consent value to Haskell for runtime preparation; it is not appended to agent argv. Privilege alone grants no consent. Tests and check do not run real package managers or installer dialogs. | [Haskell runtime and platform policy](../../DEVELOPMENT_PLAN/phase-3-haskell-runtime-and-platform-policy.md) |
| `--help` | Describes the introduced public surface without installing runtime dependencies. Agent-side help remains a raw agent argument. | [Python bootstrap and handoff](../../DEVELOPMENT_PLAN/phase-2-python-bootstrap-and-handoff.md) |

## Names

Managed names derive from canonical folder plus agent, with a path-hash disambiguator for equal basenames.
Targets retain exact namespace/registry, server/session instance and native pane identity.
Debian tmux uses the selected user server; managed Windows sessions use agentctl's stable private registry.
A system psmux command's default listing does not include that private namespace.

External adoption names its registry/endpoint explicitly through the target descriptor defined by
[sessions and ownership](../architecture/sessions_and_ownership.md#identity). An ambiguous bare pane id is
refused. A live external session can be incompatible with observation or guarded input even when attachment
is permitted; compatibility grants no ownership.

## Commands

| Command | Arguments | Contract | Owner |
|---|---|---|---|
| `agentctl claude [ARGS...]` | Literal agent arguments | For a new launch, check the user-installed claude and authentication early, prepare/qualify the host backend under consent, create its folder session and attach. Place the required bypass flag before a first bare -- or at the end. Reattach preserves the running process without agent reinstall or fresh authentication. | [Agent preflight and launch](../../DEVELOPMENT_PLAN/phase-5-agent-preflight-and-launch.md) |
| `agentctl codex [ARGS...]` | Literal agent arguments | The corresponding codex launch, preserving its required bypass and no-daemon flags and refusing login-shaped arguments. A missing selected agent fails clearly; agentctl never installs either CLI. | [Agent preflight and launch](../../DEVELOPMENT_PLAN/phase-5-agent-preflight-and-launch.md) |
| `agentctl list` | none | List managed and explicitly adopted targets with ownership, identity, lifecycle and backend qualification; no agent login is required. | [Session management and adoption](../../DEVELOPMENT_PLAN/phase-6-session-management-and-adoption.md) |
| `agentctl status [NAME]` | Optional exact target | Show target/process/dead facts, backend profile and observed class/watch state where qualified; unavailable facts remain explicitly unavailable. | [Session management and adoption](../../DEVELOPMENT_PLAN/phase-6-session-management-and-adoption.md) |
| `agentctl attach NAME` | Managed exact target | Use its compatible qualified client/endpoint, switch inside the same namespace where valid, or report an attach instruction without a terminal. Do not restart or migrate the session. | [Session management and adoption](../../DEVELOPMENT_PLAN/phase-6-session-management-and-adoption.md) |
| `agentctl stop NAME` | Exact managed/adopted target | End only a revalidated managed session; forget an adoption without ending its pane. | [Session management and adoption](../../DEVELOPMENT_PLAN/phase-6-session-management-and-adoption.md) |
| `agentctl adopt PANE --agent AGENT` | Explicit pane/endpoint descriptor and agent | Record checked external identity without ownership or changing its settings. External Windows registry selection is explicit, not inherited from the managed namespace. | [Session management and adoption](../../DEVELOPMENT_PLAN/phase-6-session-management-and-adoption.md) |
| `agentctl watch NAME` | Exact target | Enable opt-in supervision only with the required checked observation/input capabilities; incompatible targets receive a named refusal. | [Recovery and supervisor](../../DEVELOPMENT_PLAN/phase-8-recovery-and-supervisor.md) |
| `agentctl unwatch NAME` | Exact target | Remove watch intent without touching its process or session. | [Recovery and supervisor](../../DEVELOPMENT_PLAN/phase-8-recovery-and-supervisor.md) |
| `agentctl pause NAME` | Exact target | Keep watch intent but stop observations/recovery and discard the open incident. | [Recovery and supervisor](../../DEVELOPMENT_PLAN/phase-8-recovery-and-supervisor.md) |
| `agentctl resume-watch NAME` | Exact target | Take a fresh baseline and resume supervision, not the agent's internal goal. | [Recovery and supervisor](../../DEVELOPMENT_PLAN/phase-8-recovery-and-supervisor.md) |
| `agentctl logs NAME` | Exact target | Print complete decision, observation, attempt, delivery and notification records without secrets or captured private screen content. | [Recovery and supervisor](../../DEVELOPMENT_PLAN/phase-8-recovery-and-supervisor.md) |
| `agentctl supervisor run [OPTIONS]` | Timing policy | Run the explicit foreground loop with one owner lock and qualified conditional submission. Unknown delivery halts/escalates rather than replaying input. Stop releases its lock without ending targets. | [Recovery and supervisor](../../DEVELOPMENT_PLAN/phase-8-recovery-and-supervisor.md) |
| `agentctl check` | none | Run all introduced legs and present tests, retain all failures and emit complete per-phase/lane and overall reports. | [Governance and phase evidence](../../DEVELOPMENT_PLAN/phase-0-governance-and-phase-evidence.md) |

The [launch contract](../architecture/launch_contract.md) owns exact flags, login refusal and startup behavior.
The [supervisor contract](../architecture/supervisor_contract.md) owns state progression, fingerprints,
guarded submission and explicit limits. Public tables use escaped/structured fields so hostile folder text
cannot create extra rows. No command prints credentials, full environments or source-build secrets.

Timing options remain explicit values: poll interval, initial/max delay, multiplier and jitter fraction.
Their defaults and bounds live in the independent backoff/settings oracle and are validated as a whole.
No hidden profile/config parser changes these values.

## Exit Status

Successful product operations return zero; typed usage/readiness/ownership/authentication/capability failures
return nonzero with the specific problem and remedy on stderr. An agent exiting inside the startup window
propagates its actual status and captured output, with no failed owned session left behind.
A later interactive detach does not claim to report the agent's eventual exit.

A failed source build, missing consent/elevation, pending reboot, unsupported Linux distribution, malformed
artifact, missing requested agent or unqualified backend creates no new agent session. Bootstrap failure
precedes product dispatch and preserves its complete diagnostic.

The gate's overall exit reports complete checkout health. Phase closure instead consumes the canonical
complete passing phase/lane report over current owned and prerequisite inputs; a later-only failure remains
visible without erasing earlier trustworthy evidence. Final product closure requires aggregate success.

## Related

- [installation](../operations/installation.md) — pipx and first-use preparation.
- [troubleshooting](../operations/troubleshooting.md) — named refusals and remedies.
- [files and state](files_and_state.md) — private artifacts and runtime registries.
- [launch](../architecture/launch_contract.md) — exact argv and startup.
- [sessions](../architecture/sessions_and_ownership.md) — ownership and adoption.
- [supervisor](../architecture/supervisor_contract.md) — guarded recovery.
- [gate](../engineering/quality_gate.md) — phase evidence and overall result.
