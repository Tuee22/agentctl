# Troubleshooting

**Status**: Authoritative source
**Supersedes**: N/A
**Owning phase**: [Haskell runtime and platform policy](../../DEVELOPMENT_PLAN/phase-3-haskell-runtime-and-platform-policy.md)

> **Purpose**: Describe actionable bootstrap, backend, agent, session and validation failures without confusing missing evidence with success.

The required diagnostic contract preserves the original typed cause, action and remedy. Installed package
metadata or a version banner alone cannot substitute for a qualifying executable or live server identity.
The [quality gate](../engineering/quality_gate.md) reports failures by phase (`phase-failure` lines), source owner
and half ([T.O](../../DEVELOPMENT_PLAN/development_plan_standards.md#to-output)).

## Multiplexer Missing

On Debian, Haskell observes missing or inadequate tmux and produces its qualified APT plan. Missing consent,
privilege or a suitable repository version stops preparation with the exact unmet prerequisite. Other Linux
distributions fail host policy before mutation. On Windows, Haskell prepares the private pinned source build;
a missing system PATH psmux is not an installation error. A system psmux is not a substitute for the selected
private artifact. Candidate build/capability failure leaves the previous accepted entry untouched.

## Agent Missing

Install the requested claude or codex outside agentctl, then retry. The diagnostic names the requested tool
and the observed resolution failure. Agentctl installs neither CLI, and a new launch fails before a lengthy
runtime build when that agent is absent. Session listing and logs do not require unrelated agents.

## Windows .cmd Shim Refused

Use the native Windows executable required by the agent invocation contract. A command shim must not silently
introduce shell re-parsing. The diagnostic includes the conflicting resolved path and supported installation
remedy without exposing credentials or environment values.

## Logged Out

Authenticate using the agent's own discrete command outside agentctl, then retry. Agentctl observes status
but never starts login, supplies login input or answers dialogs. Validation observes the current state rather
than asking for a login to obtain a pass.

## Login-Shaped ARGS Refused

A login-shaped agent tail is refused before any session is created. Follow the separate authentication remedy;
user arguments are never interpreted as permission to answer a login, trust or approval dialog.

## Auth Check Failed

A timeout, missing executable, malformed native observation or unexpected status produces an auth-probe error,
not a guessed logged-in state. The diagnostic retains the probe's supported status information without logging
identity or credential output. No session is created after an unresolved preflight failure.

## Instant Exit

The trampoline reports its own failure or actual child exit status, including Windows where backend dead-status
fields can be placeholders. Captured failure output and cleanup outcomes remain available. A successful process
spawn alone is not evidence that the agent reached a usable prompt.

## Prerequisite Missing in a Non-Interactive Run

Supply explicit installation consent and available privilege through the supported public preparation path.
A check run never opens a package manager, sudo prompt, UAC dialog or installer interaction. Windows restart-
required and installer-busy outcomes are reported distinctly; agentctl never reboots or forces an application
closed. No setup needs a host restart; a setup that would leaves its capability absent.

## ghcup Below the Floor

An old or unanswering existing ghcup is preserved and receives an explicit upgrade remedy. Bootstrap does not
replace the user's installation or change default GHC/cabal selections. A supported responding installation
is reused by absolute path.

## ghcup Download Failed Verification

A digest, advertised-length or transport failure publishes no executable. Retry only after resolving the named
cause. Never weaken a pin or accept an incomplete file because the expected destination exists.

## Unsupported Platform

Linux runtime policy requires exact Debian identity. A dedicated Debian VirtualBox guest supplies the Linux halves
only with complete dependencies, a measured resource budget and a verified bind mount of the shared checkout
([validation runbook](validation_runbook.md)). A missing native Windows or macOS half prints `absent`, so the phase
is at best `awaiting:<half>` ([T.V](../../DEVELOPMENT_PLAN/development_plan_standards.md#tv-verdict)), and guest
output never substitutes for it.

## Native Build, Cache or Binary Identity Failed

The diagnostic identifies source/patch/toolchain digest, owned build root, actual compiler/backend path and the
failed stage. Windows build paths include a full descendant budget. A long-path, sharing, disk-space or cleanup
failure is retained as its own cause; it does not justify an ignored file, relaxed assertion or leaked process.
Private Rust roots and absolute compiler paths preserve the user's existing selections. MSVC/SDK discovery
probes compile/link/resource behavior and reports missing capabilities rather than trusting registry entries.

A damaged immutable publication fails identity without being overwritten. Replacement is a new qualified
digest. Before removing an owned failed staging directory, verify its canonical owner and absence of active
children; never recursively delete a computed path without checking its final target.

## Session Exists, ARGS Not Applied

Re-running a live folder-derived session reattaches. Additional launch arguments do not retroactively change
an already running agent. A new binary/client path does not replace the server or agent inside that session.
Compatibility diagnostics distinguish private qualified sessions from explicitly selected external ones.

## Stop Refused, Pane Forgotten or Stale

Managed sessions can be stopped only by their exact owned target. An adopted session is forgotten rather than
killed. A missing/replaced server or pane invalidates the recorded identity; capture never falls back to another
active pane. A reused PID, session name or pane ID alone cannot restore authority.

## Supervisor Already Running

The native supervisor lock prevents competing senders. Do not delete or replace a held lock file. Stop the
owned foreground supervisor through its ordinary lifecycle; watched panes continue independently.

## Watch Target Refused

The diagnostic names ownership, backend capability or identity mismatches. Unknown, changing, stale or
unqualified observations authorize no recovery input. A conditional submission rejected for changed state is
logged and observed again; uncertain delivery does not trigger an automatic duplicate send.

## No Terminal

Noninteractive launch reports the supported attach command. Foreground attachment needs a real terminal;
validation uses an owned terminal/client fixture for its declared native claims, never manual attachment as
an acceptance oracle.

## Invalid Adopted-Pane Registry

Malformed, foreign, linked, overpermissive or stale registry data produces a typed refusal. User credentials,
external multiplexer registries and unrelated sessions are untouched. Recover by correcting or deliberately
forgetting the exact owned record through the supported command, not by broad state deletion.

## Validation Failures

Each `PHASE` line carries one verdict of
[T.V](../../DEVELOPMENT_PLAN/development_plan_standards.md#tv-verdict), published by the verified parent as the
[quality gate](../engineering/quality_gate.md) describes. Follow the remedy for what the run prints:

| Output | Meaning | Remedy |
|---|---|---|
| `fail` with its `phase-failure` lines | The phase has an owned failure, or the run has a shared failure | Fix each named failure and rerun only its own test first, as the [testing-cost method](../../AGENTS.md#testing-cost-method) describes |
| `awaiting:<half>` | The phase's only gap is a required half with no current stored receipt | Run `agentctl check` on a host that supplies that half, as the [validation runbook](validation_runbook.md#select-the-halves) describes |
| `awaiting:setup:<capability>` | The capability's probe reports it absent, and every failure of that half is attributable to it | Perform its [one-time host setup](validation_runbook.md#one-time-host-setup), then rerun |
| `awaiting:prerequisite` | The only gap is a prerequisite phase that is itself awaiting a half or a capability | Resolve the prerequisite's awaiting verdict first |
| `phase verdicts withheld: <reason>` | The parent cannot verify the run, so it publishes no phase verdict | Remove the named cause and rerun the [canonical run sequence](validation_runbook.md#canonical-run-sequence) |

Exactly the shared failures of
[T.F](../../DEVELOPMENT_PLAN/development_plan_standards.md#tf-shared-and-owned-failures) affect every phase; every
other failure stays with its owner, so a later failure leaves an earlier `pass` unchanged. A nonzero exit can
coexist with an earlier phase's `pass`, and only `EVIDENCE pass` is whole-product acceptance.

For the VirtualBox guest, a binding receipt that no longer matches means the source changed after binding: rerun
the binder, then the guest gate, with no edit between them. Also inspect the guest's cgroup and affinity limits,
disk and free-space budget and actual Linux tool paths. A copied checkout, one-way synchronization or imported
stale commit is not the shared source bridge. The mount's permission, lock, case and symlink behavior is a
recorded mount fact, never repaired by changing another VM or its settings.

## Related

- [installation.md](installation.md) — user preparation and first use.
- [validation_runbook.md](validation_runbook.md) — dedicated VirtualBox and native procedures.
- [toolchain_bootstrap.md](../engineering/toolchain_bootstrap.md) — consent and typed readiness.
- [quality_gate.md](../engineering/quality_gate.md) — verdict mechanics, `phase-failure` lines and stored receipts.
- [sessions_and_ownership.md](../architecture/sessions_and_ownership.md) — managed/adopted authority.
- [supervisor_contract.md](../architecture/supervisor_contract.md) — no-send and recovery outcomes.
- [Agent preflight and launch](../../DEVELOPMENT_PLAN/phase-5-agent-preflight-and-launch.md) — diagnostic owner.
