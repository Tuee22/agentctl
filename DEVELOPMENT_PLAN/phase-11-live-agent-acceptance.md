# Phase 11 — Live agent acceptance

**Status**: Done
**Depends on**: [Phase 10 — Recovery supervisor](phase-10-supervisor.md)
**Host lane**: live-agents
**Gate**: `agentctl check`
**Gate kind**: host-acceptance
**Closes**: none
**Gate evidence**: 2026-11-09 ; live-agents ; agentctl check ; pass ; tree bf7f8da97b8ec67a89b6297e99af59cc30d1ab80afff6f56f6ac73bc11da8cec ; os=Linux,arch=x86_64,baseline=791bf661a08d531b9483c0da6baa9ac7a8fb1266
**Evidence covers**: `src/` `tests/` `pyproject.toml`

> **Purpose**: Confirm on a Linux host where claude and codex are logged in what the lower phases owe a live agent:
> the logged-in launch and its final argv, the live screen classes, and supervision that sends nothing.

## Phase Objective

This phase adds no code. It closes on the same `agentctl check`, run on a host meeting the live-agents lane: Linux,
agent-host, and `claude auth status` and `codex login status` both exiting 0 within 10 s in the user's real
environment, as `tests/harness/host.py` observes. Authentication is an existing host capability observed without
interaction; nothing in agentctl or its tests logs in or waits for a person to do so during validation.

The live tests of [Phase 6 — Launch command and passthrough](phase-6-launch-and-passthrough.md),
[Phase 8 — Pane observation and classification](phase-8-pane-observation-and-classification.md) and
[Phase 10 — Recovery supervisor](phase-10-supervisor.md) observe each agent's login state and branch on it, so on
this host they take their logged-in branch and elsewhere their logged-out one; no flag, marker or variable selects
what runs. Every live test:

- starts the real agent only in the one fixed folder under the real `state` directory, with `DISABLE_AUTOUPDATER=1`
  and codex ARGS `-c check_for_update_on_startup=false`, on a private tmux server, and lets the agent read the user's credentials in place, never copying them;
- never sends input, never answers a trust or bypass-warning dialog, never runs a login command, and accepts
  `TrustDialog`, `BypassWarning` or `IdlePrompt` as a live agent;
- reads `/proc/<pane_pid>/cmdline`, whose tail equals the independent final argv row, including the bare-separator position; an npm-installed codex
  runs as `node` with `codex.js`, so the tail is compared and not the first element.

A live launch runs the user's own claude and codex configuration as it stands, hooks and MCP servers included.
Validation and evidence recording are unattended and require no additional human approval. The lane summary prints the live-agents EVIDENCE line
only when the lane holds, and the closing agent records it as Gate evidence. A failure is fixed in the phase that
introduced its cause ([§ A](development_plan_standards.md#a-one-continuous-constructive-narrative)), which stales the
digest, and the run repeats.

## Gate Integrity

| Requirement | Oracle | Observer | Mutants | Tests |
|---|---|---|---|---|
| R7 — a logged-in agent launches into a live session whose pane stays alive | `tests/oracles/mux_commands.toml` | owed: live-agent-acceptance | none — this phase adds no code | `tests/live/test_live_launch.py::test_live_launch` |
| R9 — the user's ARGS reach the live agent's argv verbatim | `tests/oracles/launch_argv.toml` | owed: live-agent-acceptance | none — this phase adds no code | `tests/live/test_live_launch.py::test_live_launch` |
| R10 — the live claude argv ends with --dangerously-skip-permissions | `tests/oracles/launch_argv.toml` | owed: live-agent-acceptance | none — this phase adds no code | `tests/live/test_live_launch.py::test_live_launch` |
| R11 — the live codex argv ends with --dangerously-bypass-approvals-and-sandbox --no-daemon | `tests/oracles/launch_argv.toml` | owed: live-agent-acceptance | none — this phase adds no code | `tests/live/test_live_launch.py::test_live_launch` |
| R18.1 — live screens classify as TrustDialog, BypassWarning or IdlePrompt | `tests/fixtures/screens/` | owed: live-agent-acceptance | none — this phase adds no code | `tests/live/test_live_classification.py::test_live_screen_classes` |
| R18 — supervision of live sessions logs every poll and sends nothing | `tests/oracles/recovery_transitions.toml`, `tests/oracles/forbidden_actions.toml` | owed: live-agent-acceptance | none — this phase adds no code | `tests/live/test_live_supervision.py::test_live_watch_sends_nothing` |

## Not Proven By This Gate

- That the recorded run took place: the evidence row's digest proves the tree is current, not that a run happened ([§ N](development_plan_standards.md#n-the-single-gate-gate-kinds-and-host-lanes)). — not proven by any phase.
- Recovery from a genuine provider overload or usage limit, which no lane can induce. — not proven by any phase.
- Live `Overloaded`, `UsageLimit`, `AuthError` and `ContextExhausted` screens, which rest on screen fixtures alone. — not proven by any phase.
- Live `Working`, `ApprovalDialog` and `PartialInput` screens, which only a prompt that spends the user's quota reaches. — not proven by any phase.
- Live `IdlePrompt` classification and supervision when the user has not already trusted the live folder. — not proven by any phase.
- A visible `switch-client` inside the user's own tmux server, which live tests never touch; the evidence is the equivalent test on a private server. — not proven by any phase.
- A logged-in launch on macOS or Windows, whose acceptance lanes do not require a login. — not proven by any phase.
- Tamper resistance extends only to data already present in the available HEAD baseline ([§ P](development_plan_standards.md#p-the-ratchet-and-automatic-closure)); uncommitted inputs have no historical protection. — not proven by any phase.

## Confirms

- R7 — `agentctl claude` and `agentctl codex` start the logged-in agent in a session whose pane stays alive past the startup window and shows `TrustDialog`, `BypassWarning` or `IdlePrompt` (owed by [Phase 6 — Launch command and passthrough](phase-6-launch-and-passthrough.md)).
- R9 — the empty-tail and bare-separator rows with the per-invocation codex update override reach the live agent unchanged with mandatory flags in their required positions in `/proc/<pane_pid>/cmdline` (owed by [Phase 6 — Launch command and passthrough](phase-6-launch-and-passthrough.md)).
- R10 — the live claude process's argv ends with `--dangerously-skip-permissions` (owed by [Phase 6 — Launch command and passthrough](phase-6-launch-and-passthrough.md)).
- R11 — the live codex process's argv ends with `--dangerously-bypass-approvals-and-sandbox --no-daemon` (owed by [Phase 6 — Launch command and passthrough](phase-6-launch-and-passthrough.md)).
- R18.1 — live claude and codex screens classify as `TrustDialog`, `BypassWarning` or `IdlePrompt`, and as `IdlePrompt` where the user has trusted the live folder (owed by [Phase 8 — Pane observation and classification](phase-8-pane-observation-and-classification.md)).
- R18 — the supervisor watching both live sessions logs an observation at every poll and sends nothing (owed by [Phase 10 — Recovery supervisor](phase-10-supervisor.md)).

## Sprints

### Sprint 11.1: Live agent evidence [Done]

**Status**: Done
**Implementation**: none — this phase adds no code
**Validation tests**: `tests/live/test_live_launch.py::test_live_launch`, `tests/live/test_live_classification.py::test_live_screen_classes`, `tests/live/test_live_supervision.py::test_live_watch_sends_nothing`
**Mutants**: none — this phase adds no code
**Closes**: none
**Docs to update**: none — this phase changes no document

#### Objective

Record the EVIDENCE line of a passing `agentctl check` on a live-agents host, with every live test of the lower phases
taking its logged-in branch for both agents.

#### Deliverables

- A Linux host meeting the live-agents lane as `tests/harness/host.py` observes it: agent-host, with
  `claude auth status` and `codex login status` both exiting 0 within 10 s in the user's real environment.
- One unchanged `agentctl check` run there, in which the live tests of Sprints 6.2, 8.3 and 10.4 take their logged-in
  branch for claude and for codex, in the fixed live folder, on a private tmux server, with no input sent.
- The lane summary's line `EVIDENCE <YYYY-MM-DD> ; live-agents ; agentctl check ; pass ; tree <sha256> ; <detail>`,
  copied into `**Gate evidence**`; the plan validator recomputes the digest over Evidence covers and compares the lane
  and the digest only.
- A failure fixed by rewriting the phase that introduced its cause, then a fresh run on the changed tree.

#### Validation

1. Each logged-in agent's session stays alive through the startup window, shows `TrustDialog`, `BypassWarning` or
   `IdlePrompt`, and its `/proc/<pane_pid>/cmdline` equals the oracle's empty-tail or bare-separator final argv row —
   `tests/live/test_live_launch.py::test_live_launch`; fails when the pane dies or the argv tail differs from its
   `tests/oracles/launch_argv.toml` row, including the per-invocation codex update override; no mutant: this phase adds no code.
2. Each live screen classifies as `TrustDialog`, `BypassWarning` or `IdlePrompt` at every capture —
   `tests/live/test_live_classification.py::test_live_screen_classes`; fails when a live screen classifies as anything
   else; no mutant: this phase adds no code.
3. The supervisor watching both live sessions writes an `observation` at every poll and no `attempt`, and the
   harness's own capture shows no recovery text — `tests/live/test_live_supervision.py::test_live_watch_sends_nothing`;
   fails when a send is attempted into a live session; no mutant: no mutant names a live test as its killer.

#### Remaining Work

None.

## Remaining Work

None.

## Documentation Requirements

**Architecture docs to create/update:**

- None.

**Engineering docs to create/update:**

- None.

**Operations and reference docs to create/update:**

- None.

**Cross-references to add:**

- None.
