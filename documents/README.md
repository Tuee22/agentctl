# agentctl Documentation

**Status**: Authoritative source
**Supersedes**: N/A
**Owning phase**: [Governance, documentation standards and the check skeleton](../DEVELOPMENT_PLAN/phase-0-governance-and-check-skeleton.md)

> **Purpose**: Index every governed page under `documents/` with the topic it owns and the phase that builds it, and define the terms those pages share.

`documents/` is agentctl's only documentation root. Each page owns one topic, and
[documentation_standards.md](documentation_standards.md) says how pages are written, linked and validated. The plan in
`DEVELOPMENT_PLAN/` says in what order the phases build agentctl, and its
[requirements table](../DEVELOPMENT_PLAN/00-overview.md#requirements) names the page here that states each requirement.

**Status lives in one place.** The plan's [status table](../DEVELOPMENT_PLAN/README.md#current-phase-status) is the only
record of which phases are built. Every page here states the contract its owning phase builds, in the present tense, and
reads the same before and after that phase is built; no page states a phase's status.

The repository root also holds three entry documents, `README.md`, `AGENTS.md` and `CLAUDE.md`, which the documentation
standards describe; they are not pages of this index.

## Index

`architecture/` states the product contracts, `engineering/` says how agentctl is provisioned, built, tested and gated,
`operations/` says what a user does, and `reference/` holds lookup material.

| Document | Owns | Owning phase |
|---|---|---|
| [README.md](README.md) | This index and the glossary of shared terms | [Governance, documentation standards and the check skeleton](../DEVELOPMENT_PLAN/phase-0-governance-and-check-skeleton.md) |
| [documentation_standards.md](documentation_standards.md) | The rules for every governed document, and each `docs.*` check with its test and negative fixture | [Governance, documentation standards and the check skeleton](../DEVELOPMENT_PLAN/phase-0-governance-and-check-skeleton.md) |
| [architecture/python_haskell_boundary.md](architecture/python_haskell_boundary.md) | The split between the Python layer and the core binary: raw passthrough, the handoff, the handshake, the Python spawn set and the directories passed to the binary | [Launch command and passthrough](../DEVELOPMENT_PLAN/phase-6-launch-and-passthrough.md) |
| [architecture/multiplexer_adapter.md](architecture/multiplexer_adapter.md) | The typed tmux and psmux command vocabulary, version floors, exact `=NAME` targeting, session options and isolation variables | [Multiplexer adapter](../DEVELOPMENT_PLAN/phase-4-multiplexer-adapter.md) |
| [architecture/launch_contract.md](architecture/launch_contract.md) | Session names, argument assembly, login refusals, preflight and the opaque `Ready`, failures and warnings, create-or-attach, instant exit and the pane trampoline | [Launch command and passthrough](../DEVELOPMENT_PLAN/phase-6-launch-and-passthrough.md) |
| [architecture/sessions_and_ownership.md](architecture/sessions_and_ownership.md) | Managed sessions and adopted panes, and `list`, `status`, `attach`, `stop` and `adopt` | [Session management and adoption](../DEVELOPMENT_PLAN/phase-7-session-management-and-adoption.md) |
| [architecture/supervisor_contract.md](architecture/supervisor_contract.md) | Capture and fingerprints, screen classes and fixture provenance, the recovery state machine and its safety rules, backoff, send discipline, the decision log, notifications and forbidden actions | [Recovery supervisor](../DEVELOPMENT_PLAN/phase-10-supervisor.md) |
| [engineering/toolchain_bootstrap.md](engineering/toolchain_bootstrap.md) | OS prerequisites and consent, ghcup reuse or the pinned download, the GHC and cabal pins, idempotence and the clean-lane recipe | [Toolchain bootstrap](../DEVELOPMENT_PLAN/phase-2-toolchain-bootstrap.md) |
| [engineering/binary_build.md](engineering/binary_build.md) | The source digest, the build cache, atomic publish, packaging and binary identity | [Haskell package, quality legs and digest-keyed build](../DEVELOPMENT_PLAN/phase-3-haskell-package-and-build.md) |
| [engineering/quality_gate.md](engineering/quality_gate.md) | The steps and legs of `agentctl check`, tool configuration, preconditions, the lane summary and the EVIDENCE line | [Haskell package, quality legs and digest-keyed build](../DEVELOPMENT_PLAN/phase-3-haskell-package-and-build.md) |
| [engineering/testing.md](engineering/testing.md) | Evidence-class mechanics, isolation recipes, observers and nonces, oracles, mutants, what each gate leg proves, and unsupported paths | [Gate-integrity apparatus](../DEVELOPMENT_PLAN/phase-1-gate-integrity-apparatus.md) |
| [engineering/code_standards.md](engineering/code_standards.md) | The Python rules (no `Any`, `cast` or ignores; `Result` values; frozen dataclasses; one process module) and the Haskell rules (the warnings stanza, fourmolu and hlint, opaque types, one runner) | [Haskell package, quality legs and digest-keyed build](../DEVELOPMENT_PLAN/phase-3-haskell-package-and-build.md) |
| [operations/installation.md](operations/installation.md) | Installing pipx and agentctl, the first run and its consent prompt, upgrading, removal, and the login rule | [Launch command and passthrough](../DEVELOPMENT_PLAN/phase-6-launch-and-passthrough.md) |
| [operations/troubleshooting.md](operations/troubleshooting.md) | Each warning agentctl prints, what the user sees and what to type | [Launch command and passthrough](../DEVELOPMENT_PLAN/phase-6-launch-and-passthrough.md) |
| [reference/cli_reference.md](reference/cli_reference.md) | Every command with its arguments, behaviour and exit status | [Recovery supervisor](../DEVELOPMENT_PLAN/phase-10-supervisor.md) |
| [reference/files_and_state.md](reference/files_and_state.md) | The per-user directories on each OS and the format of every file agentctl writes in them | [Recovery supervisor](../DEVELOPMENT_PLAN/phase-10-supervisor.md) |
| [reference/external_tool_facts.md](reference/external_tool_facts.md) | Verified facts about claude, codex, tmux, psmux, ghcup, GHC, cabal and the Python tools, each with version, date and source | [Gate-integrity apparatus](../DEVELOPMENT_PLAN/phase-1-gate-integrity-apparatus.md) |

## Glossary

Each term means what this table says on every page; a page that needs a narrower sense says so rather than redefining
the term.

| Term | Meaning | Home |
|---|---|---|
| core binary | The Haskell executable agentctl builds from the sources bundled in its package and hands every command except `check` to. It is never on PATH and refuses to run unless agentctl starts it. | [python_haskell_boundary.md](architecture/python_haskell_boundary.md) |
| managed session | A tmux or psmux session that `agentctl claude` or `agentctl codex` created, named from its folder and agent. Its identity lives in its own session options, and `agentctl stop` ends it. | [sessions_and_ownership.md](architecture/sessions_and_ownership.md) |
| adopted pane | A pane agentctl did not create, registered with `agentctl adopt`. agentctl never owns it: `agentctl stop` forgets it and leaves it running. | [sessions_and_ownership.md](architecture/sessions_and_ownership.md) |
| watched session | A managed session or adopted pane in the watch set that `agentctl supervisor run` observes. `pause` keeps it watched while nothing is sent to it, `unwatch` removes it, and neither touches the session. | [supervisor_contract.md](architecture/supervisor_contract.md) |
| lane | A named class of host that a gate runs on, such as `any-host`, `agent-host` or `macos`, with the predicate a host must meet, what observes it and the remedy. Each phase declares one. | [§ N of the plan standards](../DEVELOPMENT_PLAN/development_plan_standards.md#n-the-single-gate-gate-kinds-and-host-lanes) |
| evidence class | The kind of evidence a test or Gate Integrity entry is, and so what it can prove: `value`, `real`, `observer` or `owed`. | [testing.md](engineering/testing.md#evidence-classes) |
| oracle | Committed expected values under `tests/oracles/`. Each row carries its provenance, the request, a verified tool fact or a recorded decision, and no row is output of the code it checks. | [testing.md](engineering/testing.md#oracles) |
| mutant | A recorded deliberate defect: a patch applied exactly once to a scratch copy, which the tests it names must kill, for its named reason, in every `agentctl check` run. | [testing.md](engineering/testing.md#mutants) |
| observer | A stand-in at a boundary that records what agentctl sent: the fake agent, which records its argv, folder, environment and session, or the spawn audit of Python processes. Each run of one uses a fresh nonce. | [testing.md](engineering/testing.md#observers-and-nonces) |
| owed confirmation | A live confirmation that no self-verifying run can produce, such as a launch with a logged-in agent. Exactly one host-acceptance phase names it in its `## Confirms`, and it is proven once that phase's evidence row is current. | [testing.md](engineering/testing.md#evidence-classes) |
| preflight | The checks before a launch creates anything: the multiplexer, then the agent, then its login. Only a passing preflight yields the `Ready` value a launch needs. | [launch_contract.md](architecture/launch_contract.md#preflight) |
| pane trampoline | The core binary's `pane-exec` command, which every agent pane runs. It reads and deletes a private spec file holding the agent's argv, its folder and the caller's environment, then becomes the agent (Linux, macOS) or runs it and records its exit status (Windows). | [launch_contract.md](architecture/launch_contract.md#the-pane-trampoline) |
| instant-exit capture | When the agent exits during the startup window, agentctl shows the pane's output on the user's terminal, closes the session and exits with the agent's status. | [launch_contract.md](architecture/launch_contract.md#instant-exit) |

## Related

- [documentation_standards.md](documentation_standards.md) — the rules every page in this index follows.
- [DEVELOPMENT_PLAN/README.md](../DEVELOPMENT_PLAN/README.md) — the status table, and how the plan is worked.
- [00-overview.md](../DEVELOPMENT_PLAN/00-overview.md#requirements) — each requirement with its prose home here and its data home.
- [development_plan_standards.md § S](../DEVELOPMENT_PLAN/development_plan_standards.md#s-contract-homes) — which page is the home of each product contract.
- [system-components.md](../DEVELOPMENT_PLAN/system-components.md) — the modules, tools and directories these pages describe.
